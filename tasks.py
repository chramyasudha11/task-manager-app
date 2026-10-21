"""Member 2: session-authenticated task REST API using Member 1's users.db.

Role visibility is aligned with Member 2's Task API permission agreement:
ADMIN and MANAGER see all tasks; EMPLOYEE sees assigned tasks and unassigned
tasks they created. MANAGER and ADMIN can assign tasks.
"""

from datetime import date, datetime, timezone
from contextlib import contextmanager
import re

from flask import Blueprint, jsonify, request, session
from auth import get_db, login_required


tasks_bp = Blueprint("tasks", __name__)

VALID_STATUSES = {"pending", "in_progress", "completed"}
STATUS_STORAGE = {"pending": "Pending", "in_progress": "In Progress", "completed": "Completed"}
VALID_PRIORITIES = {"Low", "Medium", "High"}
EDITABLE_FIELDS = {"title", "description", "status", "priority", "category", "due_date"}
MANAGEMENT_ROLES = {"ADMIN", "MANAGER"}


@contextmanager
def _db():
    """Connect to Member 1's users.db; close and commit/roll back safely."""
    conn = get_db()
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            yield conn
    finally:
        conn.close()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _columns(conn):
    return {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}


def init_tasks_db():
    """Create tasks, preserving/migrating an older SQLite tasks table if present."""
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Pending'
                    CHECK (status IN ('Pending', 'In Progress', 'Completed')),
                priority TEXT NOT NULL DEFAULT 'Medium'
                    CHECK (priority IN ('Low', 'Medium', 'High')),
                category TEXT NOT NULL DEFAULT 'Personal',
                due_date TEXT,
                created_by INTEGER NOT NULL,
                assigned_to INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (created_by) REFERENCES users(id),
                FOREIGN KEY (assigned_to) REFERENCES users(id)
            )
        """)

        # This also supports an older task CRUD table created before auth was added.
        old_columns = _columns(conn)
        migrations = {
            "description": "TEXT NOT NULL DEFAULT ''",
            "status": "TEXT NOT NULL DEFAULT 'Pending'",
            "priority": "TEXT NOT NULL DEFAULT 'Medium'",
            "category": "TEXT NOT NULL DEFAULT 'Personal'",
            "due_date": "TEXT",
            "created_by": "INTEGER",
            "assigned_to": "INTEGER",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        }
        for name, definition in migrations.items():
            if name not in old_columns:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {definition}")

        if "is_completed" in old_columns and "status" not in old_columns:
            conn.execute(
                "UPDATE tasks SET status = 'Completed' WHERE is_completed = 1"
            )

        if "user_id" in old_columns:
            conn.execute("""
                UPDATE tasks SET created_by = user_id
                WHERE created_by IS NULL AND user_id IS NOT NULL
                  AND EXISTS (SELECT 1 FROM users WHERE users.id = tasks.user_id)
            """)

        # Normalize older JWT/SQLAlchemy conventions if an old tasks table was reused.
        # Normalize status spellings so API filters and dashboard counts agree.
        conn.execute("""UPDATE tasks SET status = 'Pending'
                     WHERE LOWER(TRIM(status)) IN ('todo', 'pending')""")
        conn.execute("""UPDATE tasks SET status = 'In Progress'
                     WHERE LOWER(TRIM(status)) IN
                           ('in progress', 'in-progress', 'in_progress')""")
        conn.execute("""UPDATE tasks SET status = 'Completed'
                     WHERE LOWER(TRIM(status)) IN ('done', 'completed')""")
        conn.execute("""UPDATE tasks SET priority = 'Low'
                     WHERE LOWER(TRIM(priority)) = 'low'""")
        conn.execute("""UPDATE tasks SET priority = 'Medium'
                     WHERE LOWER(TRIM(priority)) = 'medium'""")
        conn.execute("""UPDATE tasks SET priority = 'High'
                     WHERE LOWER(TRIM(priority)) = 'high'""")

        timestamp = _now()
        conn.execute("""
            UPDATE tasks SET created_at = ?
            WHERE created_at IS NULL OR created_at = ''
        """, (timestamp,))
        conn.execute("""
            UPDATE tasks SET updated_at = created_at
            WHERE updated_at IS NULL OR updated_at = ''
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks(assigned_to)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created_by ON tasks(created_by)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")


def _error(message, status=400):
    return jsonify({"error": message}), status


def _json_fields(allowed, require_nonempty=True):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, _error("Expected a JSON object")
    if require_nonempty and not data:
        return None, _error("Request body cannot be empty")
    unknown = set(data) - allowed
    if unknown:
        return None, _error("Unsupported field(s): " + ", ".join(sorted(unknown)))
    return data, None


def _validate_edit(data, *, creating=False):
    clean = {}
    if creating and "title" not in data:
        return None, _error("title is required")

    for key, value in data.items():
        if key == "title":
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 200:
                return None, _error("title must be 1-200 characters")
            clean[key] = value.strip()
        elif key == "description":
            if not isinstance(value, str) or len(value) > 5000:
                return None, _error("description must be a string of at most 5000 characters")
            clean[key] = value
        elif key == "category":
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 80:
                return None, _error("category must be 1-80 characters")
            clean[key] = value.strip()
        elif key == "priority":
            if not isinstance(value, str) or value.strip().capitalize() not in VALID_PRIORITIES:
                return None, _error("priority must be Low, Medium, or High")
            clean[key] = value.strip().capitalize()
        elif key == "status":
            if not isinstance(value, str):
                return None, _error("status must be pending, in_progress, or completed")
            status = value.strip().lower().replace("-", "_").replace(" ", "_")
            if status == "todo":
                status = "pending"
            if status == "done":
                status = "completed"
            if status not in VALID_STATUSES:
                return None, _error("status must be pending, in_progress, or completed")
            clean[key] = STATUS_STORAGE[status]
        elif key == "due_date":
            if value is None or value == "":
                clean[key] = None
            elif isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                try:
                    date.fromisoformat(value)
                except ValueError:
                    return None, _error("due_date must be a valid YYYY-MM-DD date")
                clean[key] = value
            else:
                return None, _error("due_date must be YYYY-MM-DD or null")
    return clean, None


def _actor(conn):
    return conn.execute(
        "SELECT id, role FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()


def _can_manage(actor):
    return actor["role"] in MANAGEMENT_ROLES


def _can_access(task, actor):
    role = str(actor["role"]).upper()
    if role in ("ADMIN", "MANAGER"):
        return True
    if role == "EMPLOYEE":
        return (
            task["assigned_to"] == actor["id"]
            or (task["assigned_to"] is None and task["created_by"] == actor["id"])
        )
    return False


def _task(conn, task_id):
    return conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


def _visible_task(conn, task_id, actor):
    task = _task(conn, task_id)
    if task is None:
        return None, _error("Task not found", 404)
    if not _can_access(task, actor):
        return None, _error("Access denied for this task", 403)
    return task, None


def _public(task):
    fields = (
        "id", "title", "description", "status", "priority", "category",
        "due_date", "created_by", "assigned_to", "created_at", "updated_at"
    )
    result = {field: task[field] for field in fields}
    result["is_completed"] = str(result["status"]).strip().lower() == "completed"
    return result


def _assignee_error(conn, assigned_to):
    if assigned_to is None:
        return None
    if type(assigned_to) is not int or assigned_to < 1:
        return _error("assigned_to must be an existing user ID or null")
    user = conn.execute("SELECT id FROM users WHERE id = ?", (assigned_to,)).fetchone()
    if user is None:
        return _error("Assignee user not found", 404)
    return None


def _sync_legacy_completed(conn, task_id, status):
    # Older SQLite tasks tables may still have this separate completion column.
    if "is_completed" in _columns(conn):
        conn.execute(
            "UPDATE tasks SET is_completed = ? WHERE id = ?",
            (int(str(status).strip().lower() == "completed"), task_id)
        )


@tasks_bp.route("/api/tasks", methods=["POST"])
@login_required
def create_task():
    data, error = _json_fields(EDITABLE_FIELDS | {"assigned_to"})
    if error:
        return error
    fields = {key: value for key, value in data.items() if key != "assigned_to"}
    cleaned, error = _validate_edit(fields, creating=True)
    if error:
        return error

    with _db() as conn:
        actor = _actor(conn)
        if actor is None:
            return _error("User not found", 401)
        if actor["role"] not in {"ADMIN", "MANAGER", "EMPLOYEE"}:
            return _error("Unsupported user role", 403)
        if "assigned_to" in data and not _can_manage(actor):
            return _error("Only a manager or admin can assign tasks", 403)
        assigned_to = data.get("assigned_to")
        # A task created by an employee is assigned to that employee so it remains
        # visible under the shared rule that employees see tasks assigned to them.
        if actor["role"] == "EMPLOYEE" and "assigned_to" not in data:
            assigned_to = actor["id"]
        error = _assignee_error(conn, assigned_to)
        if error:
            return error

        cleaned.setdefault("description", "")
        cleaned.setdefault("status", "Pending")
        cleaned.setdefault("priority", "Medium")
        cleaned.setdefault("category", "Personal")
        cleaned.setdefault("due_date", None)
        cleaned.update({
            "created_by": actor["id"],
            "assigned_to": assigned_to,
            "created_at": _now(),
            "updated_at": _now(),
        })
        if "user_id" in _columns(conn):
            # Keep older apps querying tasks.user_id compatible.
            cleaned["user_id"] = actor["id"]
        if "is_completed" in _columns(conn):
            cleaned["is_completed"] = int(str(cleaned["status"]).strip().lower() == "completed")
        names = list(cleaned)
        placeholders = ", ".join("?" for _ in names)
        columns = ", ".join(names)  # names are all validated internal constants
        cursor = conn.execute(
            f"INSERT INTO tasks ({columns}) VALUES ({placeholders})",
            [cleaned[name] for name in names]
        )
        return jsonify(_public(_task(conn, cursor.lastrowid))), 201


@tasks_bp.route("/api/tasks", methods=["GET"])
@login_required
def list_tasks():
    status = request.args.get("status")
    priority = request.args.get("priority")
    category = request.args.get("category")
    search = request.args.get("search") or request.args.get("q")

    filters = []
    params = []
    if status:
        clean, error = _validate_edit({"status": status})
        if error:
            return error
        filters.append("status = ?")
        params.append(clean["status"])
    if priority:
        clean, error = _validate_edit({"priority": priority})
        if error:
            return error
        filters.append("priority = ?")
        params.append(clean["priority"])
    if category:
        filters.append("category = ?")
        params.append(category)
    if search:
        filters.append("(title LIKE ? OR description LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    with _db() as conn:
        actor = _actor(conn)
        if actor is None:
            return _error("User not found", 401)
        role = str(actor["role"]).upper()
        if role == "EMPLOYEE":
            filters.append("(assigned_to = ? OR (assigned_to IS NULL AND created_by = ?))")
            params.extend([actor["id"], actor["id"]])
        elif role not in ("ADMIN", "MANAGER"):
            return _error("Unsupported user role", 403)

        sql = "SELECT * FROM tasks"
        if filters:
            sql += " WHERE " + " AND ".join(filters)
        sql += " ORDER BY created_at DESC, id DESC"
        return jsonify([_public(row) for row in conn.execute(sql, params).fetchall()])


@tasks_bp.route("/api/tasks/<int:task_id>", methods=["GET"])
@login_required
def get_task(task_id):
    with _db() as conn:
        actor = _actor(conn)
        if actor is None:
            return _error("User not found", 401)
        task, error = _visible_task(conn, task_id, actor)
        if error:
            return error
        return jsonify(_public(task))


@tasks_bp.route("/api/tasks/<int:task_id>", methods=["PUT"])
@login_required
def update_task(task_id):
    data, error = _json_fields(EDITABLE_FIELDS)
    if error:
        return error
    cleaned, error = _validate_edit(data)
    if error:
        return error

    with _db() as conn:
        actor = _actor(conn)
        if actor is None:
            return _error("User not found", 401)
        _, error = _visible_task(conn, task_id, actor)
        if error:
            return error
        cleaned["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in cleaned)
        conn.execute(
            f"UPDATE tasks SET {assignments} WHERE id = ?",
            [*cleaned.values(), task_id]
        )
        if "status" in cleaned:
            _sync_legacy_completed(conn, task_id, cleaned["status"])
        return jsonify(_public(_task(conn, task_id)))


@tasks_bp.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@login_required
def delete_task(task_id):
    with _db() as conn:
        actor = _actor(conn)
        if actor is None:
            return _error("User not found", 401)
        _, error = _visible_task(conn, task_id, actor)
        if error:
            return error
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return jsonify({"message": "Task deleted successfully"})


@tasks_bp.route("/api/tasks/<int:task_id>/status", methods=["PATCH"])
@login_required
def update_task_status(task_id):
    data, error = _json_fields({"status"})
    if error:
        return error
    if "status" not in data:
        return _error("status is required")
    cleaned, error = _validate_edit(data)
    if error:
        return error
    with _db() as conn:
        actor = _actor(conn)
        if actor is None:
            return _error("User not found", 401)
        _, error = _visible_task(conn, task_id, actor)
        if error:
            return error
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (cleaned["status"], _now(), task_id)
        )
        _sync_legacy_completed(conn, task_id, cleaned["status"])
        return jsonify(_public(_task(conn, task_id)))


@tasks_bp.route("/api/tasks/<int:task_id>/assign", methods=["PATCH"])
@login_required
def assign_task(task_id):
    data, error = _json_fields({"assigned_to"})
    if error:
        return error
    if "assigned_to" not in data:
        return _error("assigned_to is required (user ID or null)")
    with _db() as conn:
        actor = _actor(conn)
        if actor is None:
            return _error("User not found", 401)
        if not _can_manage(actor):
            return _error("Only a manager or admin can assign tasks", 403)
        task, error = _visible_task(conn, task_id, actor)
        if error:
            return error
        error = _assignee_error(conn, data["assigned_to"])
        if error:
            return error
        conn.execute(
            "UPDATE tasks SET assigned_to = ?, updated_at = ? WHERE id = ?",
            (data["assigned_to"], _now(), task_id)
        )
        return jsonify(_public(_task(conn, task_id)))