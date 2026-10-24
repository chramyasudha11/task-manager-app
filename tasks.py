"""Member 2: session-authenticated task REST API using Member 1's users.db.

Role visibility:
ADMIN and MANAGER see all tasks; EMPLOYEE sees assigned tasks and
unassigned tasks they created. MANAGER and ADMIN can assign tasks.

Roles: ADMIN/MANAGER manage all tasks and assignments; EMPLOYEE manages
assigned tasks, or self-created tasks that have not been assigned elsewhere.
"""

import os
import re
import math
import sqlite3
import calendar
from datetime import date, datetime, timedelta, timezone
from contextlib import contextmanager
from pathlib import Path

from flask import Blueprint, jsonify, request, session, current_app, has_app_context
import auth
from auth import login_required


tasks_bp = Blueprint("tasks", __name__)

VALID_STATUSES = {"pending", "in_progress", "completed"}

STATUS_STORAGE = {
    "pending": "Pending",
    "in_progress": "In Progress",
    "completed": "Completed",
}
VALID_PRIORITIES = {"Low", "Medium", "High"}
VALID_RECURRENCES = {"none", "daily", "weekly", "monthly", "yearly"}
EDITABLE_FIELDS = {
    "title", "description", "status", "priority", "category", "due_date",
    "recurrence_pattern", "recurrence", "recurrence_interval", "recurrence_end_date"
}
STATUS_API = {
    "Pending": "pending",
    "pending": "pending",
    "Not Started": "pending",
    "not started": "pending",
    "not_started": "pending",
    "In Progress": "in_progress",
    "in progress": "in_progress",
    "in_progress": "in_progress",
    "Completed": "completed",
    "completed": "completed",
}
MANAGEMENT_ROLES = {"ADMIN", "MANAGER"}


@contextmanager
def _db(custom_conn=None):
    """Connect to users.db safely, ensuring transactions commit and connections close."""
    if custom_conn is not None:
        yield custom_conn
        return

    if has_app_context() and "DATABASE_PATH" in current_app.config:
        database_path = Path(current_app.config["DATABASE_PATH"])
    else:
        db_path = getattr(auth, "DB_NAME", None) or os.environ.get(
            "DATABASE_PATH", str(Path(__file__).resolve().parent / "users.db")
        )
        database_path = Path(db_path)

    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(database_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _columns(conn):
    return {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}


def _status_storage(conn, status_key):
    table_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'"
    ).fetchone()
    table_sql = table_row[0] if table_row else ""
    if "Not Started" in table_sql and "Pending" not in table_sql:
        mapping = {
            "pending": "Not Started",
            "in_progress": "In Progress",
            "completed": "Completed",
        }
    else:
        mapping = {
            "pending": "Pending",
            "in_progress": "In Progress",
            "completed": "Completed",
        }
    norm_key = STATUS_API.get(
        status_key, str(status_key).lower().replace("-", "_").replace(" ", "_")
    )
    return mapping.get(norm_key, "Pending")


def init_tasks_db(app=None):
    """Create tasks, preserving/migrating an older SQLite tasks table if present."""
    if app is not None:
        with app.app_context():
            return _init_tasks_db_internal()
    return _init_tasks_db_internal()


def _init_tasks_db_internal():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Pending'
                    CHECK (status IN ('Pending', 'In Progress', 'Completed', 'Not Started')),
                priority TEXT NOT NULL DEFAULT 'Medium'
                    CHECK (priority IN ('Low', 'Medium', 'High')),
                category TEXT NOT NULL DEFAULT 'Personal',
                due_date TEXT,
                created_by INTEGER NOT NULL,
                assigned_to INTEGER,
                recurrence_pattern TEXT NOT NULL DEFAULT 'none'
                    CHECK (recurrence_pattern IN ('none', 'daily', 'weekly', 'monthly', 'yearly')),
                recurrence_interval INTEGER NOT NULL DEFAULT 1,
                recurrence_end_date TEXT,
                parent_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (created_by) REFERENCES users(id),
                FOREIGN KEY (assigned_to) REFERENCES users(id)
            )
        """)

        old_columns = _columns(conn)
        migrations = {
            "title": "TEXT NOT NULL DEFAULT ''",
            "description": "TEXT NOT NULL DEFAULT ''",
            "status": "TEXT NOT NULL DEFAULT 'Pending'",
            "priority": "TEXT NOT NULL DEFAULT 'Medium'",
            "category": "TEXT NOT NULL DEFAULT 'Personal'",
            "due_date": "TEXT",
            "created_by": "INTEGER",
            "assigned_to": "INTEGER",
            "recurrence_pattern": "TEXT NOT NULL DEFAULT 'none'",
            "recurrence_interval": "INTEGER NOT NULL DEFAULT 1",
            "recurrence_end_date": "TEXT",
            "parent_task_id": "INTEGER REFERENCES tasks(id) ON DELETE SET NULL",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        }

        for name, definition in migrations.items():
            if name not in old_columns:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {definition}")

        if "name" in old_columns and "title" in old_columns:
            conn.execute("""
                UPDATE tasks
                SET title = name
                WHERE (title IS NULL OR title = '') AND name IS NOT NULL
            """)

        if "is_completed" in old_columns and "status" not in old_columns:
            conn.execute("""
                UPDATE tasks
                SET status = 'Completed'
                WHERE is_completed = 1
            """)

        if "user_id" in old_columns:
            conn.execute("""
                UPDATE tasks
                SET created_by = user_id
                WHERE created_by IS NULL
                  AND user_id IS NOT NULL
                  AND EXISTS (
                      SELECT 1 FROM users WHERE users.id = tasks.user_id
                  )
            """)

        conn.execute("""
            UPDATE tasks SET status = 'Pending'
            WHERE LOWER(TRIM(status)) IN ('todo', 'pending')
        """)
        conn.execute("""
            UPDATE tasks SET status = 'In Progress'
            WHERE LOWER(TRIM(status)) IN
                  ('in progress', 'in-progress', 'in_progress')
        """)
        conn.execute("""
            UPDATE tasks SET status = 'Completed'
            WHERE LOWER(TRIM(status)) IN ('done', 'completed')
        """)

        conn.execute("""
            UPDATE tasks SET priority = 'Low'
            WHERE LOWER(TRIM(priority)) = 'low'
        """)
        conn.execute("""
            UPDATE tasks SET priority = 'Medium'
            WHERE LOWER(TRIM(priority)) = 'medium'
        """)
        conn.execute("""
            UPDATE tasks SET priority = 'High'
            WHERE LOWER(TRIM(priority)) = 'high'
        """)

        conn.execute("""
            UPDATE tasks SET recurrence_pattern = 'none'
            WHERE recurrence_pattern IS NULL OR recurrence_pattern = ''
        """)
        conn.execute("""
            UPDATE tasks SET recurrence_interval = 1
            WHERE recurrence_interval IS NULL OR recurrence_interval < 1
        """)

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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id)")


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


def _validate_edit(data, *, creating=False, existing=None):
    clean = {}

    if creating and "title" not in data:
        return None, _error("title is required")

    for key, value in data.items():
        if key == "title":
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 200:
                return None, _error("title must be 1-200 characters")
            clean[key] = value.strip()

        elif key == "description":
            if value is None:
                clean[key] = ""
            elif not isinstance(value, str) or len(value) > 5000:
                return None, _error(
                    "description must be a string of at most 5000 characters"
                )
            else:
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
            if status in ("todo", "not_started"):
                status = "pending"
            elif status == "done":
                status = "completed"
            if status not in VALID_STATUSES:
                return None, _error("status must be pending, in_progress, or completed")
            clean[key] = status

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

        elif key in ("recurrence", "recurrence_pattern"):
            if not isinstance(value, str):
                return None, _error(
                    "recurrence must be one of: none, daily, weekly, monthly, yearly"
                )
            rec = value.strip().lower()
            if rec not in VALID_RECURRENCES:
                return None, _error(
                    "recurrence must be one of: none, daily, weekly, monthly, yearly"
                )
            clean["recurrence_pattern"] = rec

        elif key == "recurrence_interval":
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                return None, _error("recurrence_interval must be a positive integer")
            clean[key] = value

        elif key == "recurrence_end_date":
            if value is None or value == "":
                clean[key] = None
            elif isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                try:
                    date.fromisoformat(value)
                except ValueError:
                    return None, _error(
                        "recurrence_end_date must be a valid YYYY-MM-DD date"
                    )
                clean[key] = value
            else:
                return None, _error("recurrence_end_date must be YYYY-MM-DD or null")

    effective_due = clean.get("due_date") if "due_date" in clean else (
        existing["due_date"] if existing and "due_date" in existing.keys() else None
    )
    effective_end = clean.get("recurrence_end_date") if "recurrence_end_date" in clean else (
        existing["recurrence_end_date"]
        if existing and "recurrence_end_date" in existing.keys() else None
    )
    if effective_due and effective_end and effective_end < effective_due:
        return None, _error("recurrence_end_date cannot be earlier than due_date")

    return clean, None


def _calculate_next_due_date(base_date_str, pattern, interval=1):
    """Compute the next due date based on recurrence pattern and interval."""
    if not base_date_str:
        base_date = date.today()
    else:
        try:
            base_date = date.fromisoformat(base_date_str)
        except ValueError:
            base_date = date.today()

    interval = max(1, interval or 1)
    pattern = (pattern or "none").strip().lower()

    if pattern == "daily":
        return (base_date + timedelta(days=interval)).isoformat()
    if pattern == "weekly":
        return (base_date + timedelta(weeks=interval)).isoformat()
    if pattern == "monthly":
        m = base_date.month - 1 + interval
        y = base_date.year + m // 12
        m = m % 12 + 1
        d = min(base_date.day, calendar.monthrange(y, m)[1])
        return date(y, m, d).isoformat()
    if pattern == "yearly":
        y = base_date.year + interval
        d = min(base_date.day, calendar.monthrange(y, base_date.month)[1])
        return date(y, base_date.month, d).isoformat()
    return None


def _handle_recurring_task_completion(conn, task):
    """If a task has an active recurrence pattern and completed, create its next occurrence."""
    task_keys = task.keys() if hasattr(task, "keys") else task
    pattern = task["recurrence_pattern"] if "recurrence_pattern" in task_keys else "none"
    if not pattern or pattern == "none":
        return None

    interval = task["recurrence_interval"] if "recurrence_interval" in task_keys else 1
    base_due = task["due_date"] if "due_date" in task_keys and task["due_date"] else date.today().isoformat()
    next_due = _calculate_next_due_date(base_due, pattern, interval)
    if not next_due:
        return None

    end_date = task["recurrence_end_date"] if "recurrence_end_date" in task_keys else None
    if end_date and next_due > end_date:
        return None

    parent_id = (
        task["parent_task_id"]
        if "parent_task_id" in task_keys and task["parent_task_id"] else None
    ) or task["id"]

    existing = conn.execute("""
        SELECT id FROM tasks
        WHERE (parent_task_id = ? OR id = ?)
          AND due_date = ?
          AND status NOT IN ('Completed', 'completed')
    """, (parent_id, parent_id, next_due)).fetchone()
    if existing:
        return existing["id"]

    now = _now()
    columns_in_table = _columns(conn)
    pending_status = _status_storage(conn, "pending")
    data = {
        "title": task["title"] if "title" in task_keys and task["title"] else (
            task["name"] if "name" in task_keys else ""
        ),
        "description": task["description"] if "description" in task_keys else "",
        "status": pending_status,
        "priority": task["priority"] if "priority" in task_keys else "Medium",
        "category": task["category"] if "category" in task_keys else "Personal",
        "due_date": next_due,
        "created_by": task["created_by"] if "created_by" in task_keys else 1,
        "assigned_to": task["assigned_to"] if "assigned_to" in task_keys else None,
        "recurrence_pattern": pattern,
        "recurrence_interval": interval,
        "recurrence_end_date": end_date,
        "parent_task_id": parent_id,
        "created_at": now,
        "updated_at": now,
    }
    if "name" in columns_in_table:
        data["name"] = data["title"]
    if "is_completed" in columns_in_table:
        data["is_completed"] = 0
    if "user_id" in columns_in_table:
        data["user_id"] = data["created_by"]

    names = [k for k in data if k in columns_in_table]
    placeholders = ", ".join("?" for _ in names)
    cols = ", ".join(names)
    cursor = conn.execute(
        f"INSERT INTO tasks ({cols}) VALUES ({placeholders})",
        [data[name] for name in names],
    )
    return cursor.lastrowid


def _actor(conn):
    if "user_id" not in session:
        return None
    return conn.execute(
        "SELECT id, role FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()


def _can_manage(actor):
    return str(actor["role"]).upper() in MANAGEMENT_ROLES


def _can_access(task, actor):
    role = str(actor["role"]).upper()
    if role in ("ADMIN", "MANAGER"):
        return True
    if role == "EMPLOYEE":
        task_keys = task.keys() if hasattr(task, "keys") else task
        assigned_to = task["assigned_to"] if "assigned_to" in task_keys else None
        created_by = task["created_by"] if "created_by" in task_keys else None
        return assigned_to == actor["id"] or (
            assigned_to is None and created_by == actor["id"]
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
        "due_date", "created_by", "assigned_to", "recurrence_pattern",
        "recurrence_interval", "recurrence_end_date", "parent_task_id",
        "created_at", "updated_at"
    )
    task_keys = task.keys() if hasattr(task, "keys") else task
    result = {}
    for field in fields:
        if field in task_keys:
            result[field] = task[field]
        elif field == "recurrence_pattern":
            result[field] = "none"
        elif field == "recurrence_interval":
            result[field] = 1
        else:
            result[field] = None

    if not result.get("title") and "name" in task_keys and task["name"]:
        result["title"] = task["name"]

    raw_status = str(result.get("status") or "Pending").strip()
    norm_status = STATUS_API.get(
        raw_status, raw_status.lower().replace("-", "_").replace(" ", "_")
    )
    result["status"] = norm_status
    result["recurrence"] = result.get("recurrence_pattern", "none")
    result["is_completed"] = norm_status == "completed"
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
    if "is_completed" in _columns(conn):
        conn.execute(
            "UPDATE tasks SET is_completed = ? WHERE id = ?",
            (int(STATUS_API.get(status, str(status).strip().lower()) == "completed"), task_id),
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
        role = str(actor["role"]).upper()
        if role not in {"ADMIN", "MANAGER", "EMPLOYEE"}:
            return _error("Unsupported user role", 403)
        if "assigned_to" in data and not _can_manage(actor):
            return _error("Only a manager or admin can assign tasks", 403)

        assigned_to = data.get("assigned_to")
        if role == "EMPLOYEE" and "assigned_to" not in data:
            assigned_to = actor["id"]
        error = _assignee_error(conn, assigned_to)
        if error:
            return error

        cleaned.setdefault("description", "")
        cleaned.setdefault("status", "pending")
        cleaned["status"] = _status_storage(conn, cleaned["status"])
        cleaned.setdefault("priority", "Medium")
        cleaned.setdefault("category", "Personal")
        cleaned.setdefault("due_date", None)
        cleaned.setdefault("recurrence_pattern", "none")
        cleaned.setdefault("recurrence_interval", 1)
        cleaned.setdefault("recurrence_end_date", None)
        cleaned.setdefault("parent_task_id", None)

        now = _now()
        cleaned.update({
            "created_by": actor["id"],
            "assigned_to": assigned_to,
            "created_at": now,
            "updated_at": now,
        })
        columns_in_table = _columns(conn)
        if "name" in columns_in_table:
            cleaned["name"] = cleaned["title"]
        if "user_id" in columns_in_table:
            cleaned["user_id"] = actor["id"]
        if "is_completed" in columns_in_table:
            cleaned["is_completed"] = int(
                STATUS_API.get(cleaned["status"], "") == "completed"
            )

        names = [k for k in cleaned if k in columns_in_table]
        placeholders = ", ".join("?" for _ in names)
        columns = ", ".join(names)
        cursor = conn.execute(
            f"INSERT INTO tasks ({columns}) VALUES ({placeholders})",
            [cleaned[name] for name in names],
        )
        return jsonify(_public(_task(conn, cursor.lastrowid))), 201


@tasks_bp.route("/api/tasks", methods=["GET"])
@login_required
def list_tasks():
    with _db() as conn:
        actor = _actor(conn)
        if actor is None:
            return _error("User not found", 401)
        role = str(actor["role"]).upper()
        if role not in ("ADMIN", "MANAGER", "EMPLOYEE"):
            return _error("Unsupported user role", 403)

        filters = []
        params = []

        status_raw = request.args.getlist("status")
        if status_raw:
            statuses_to_check = []
            for item in status_raw:
                statuses_to_check.extend(
                    part.strip() for part in item.split(",") if part.strip()
                )
            if statuses_to_check:
                clean_statuses = []
                for item in statuses_to_check:
                    clean, error = _validate_edit({"status": item})
                    if error:
                        return error
                    db_status = _status_storage(conn, clean["status"])
                    clean_statuses.append(db_status)
                    if clean["status"] == "pending":
                        clean_statuses.extend(["Not Started", "Pending"])
                clean_statuses = list(dict.fromkeys(clean_statuses))
                placeholders = ", ".join("?" for _ in clean_statuses)
                filters.append(f"status IN ({placeholders})")
                params.extend(clean_statuses)

        priority_raw = request.args.getlist("priority")
        if priority_raw:
            priorities = []
            for item in priority_raw:
                priorities.extend(part.strip() for part in item.split(",") if part.strip())
            if priorities:
                clean_priorities = []
                for item in priorities:
                    clean, error = _validate_edit({"priority": item})
                    if error:
                        return error
                    clean_priorities.append(clean["priority"])
                clean_priorities = list(dict.fromkeys(clean_priorities))
                placeholders = ", ".join("?" for _ in clean_priorities)
                filters.append(f"priority IN ({placeholders})")
                params.extend(clean_priorities)

        category = request.args.get("category")
        if category:
            categories = [item.strip() for item in category.split(",") if item.strip()]
            if categories:
                placeholders = ", ".join("?" for _ in categories)
                filters.append(f"category IN ({placeholders})")
                params.extend(categories)

        search = request.args.get("search") or request.args.get("q")
        if search:
            columns_in_table = _columns(conn)
            if "name" in columns_in_table and "title" in columns_in_table:
                filters.append("(title LIKE ? OR name LIKE ? OR description LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
            else:
                filters.append("(title LIKE ? OR description LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%"])

        due_date = request.args.get("due_date")
        if due_date:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_date):
                return _error("due_date must be a valid YYYY-MM-DD date")
            try:
                date.fromisoformat(due_date)
            except ValueError:
                return _error("due_date must be a valid YYYY-MM-DD date")
            filters.append("due_date = ?")
            params.append(due_date)

        due_before = request.args.get("due_before") or request.args.get("due_to") or request.args.get("date_to")
        if due_before:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_before):
                return _error("due_before must be a valid YYYY-MM-DD date")
            try:
                date.fromisoformat(due_before)
            except ValueError:
                return _error("due_before must be a valid YYYY-MM-DD date")
            filters.append("due_date IS NOT NULL AND due_date <= ?")
            params.append(due_before)

        due_after = request.args.get("due_after") or request.args.get("due_from") or request.args.get("date_from")
        if due_after:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_after):
                return _error("due_after must be a valid YYYY-MM-DD date")
            try:
                date.fromisoformat(due_after)
            except ValueError:
                return _error("due_after must be a valid YYYY-MM-DD date")
            filters.append("due_date IS NOT NULL AND due_date >= ?")
            params.append(due_after)

        created_before = request.args.get("created_before") or request.args.get("created_to")
        if created_before:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", created_before):
                return _error("created_before must be a valid YYYY-MM-DD date")
            try:
                date.fromisoformat(created_before)
            except ValueError:
                return _error("created_before must be a valid YYYY-MM-DD date")
            filters.append("substr(created_at, 1, 10) <= ?")
            params.append(created_before)

        created_after = request.args.get("created_after") or request.args.get("created_from")
        if created_after:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", created_after):
                return _error("created_after must be a valid YYYY-MM-DD date")
            try:
                date.fromisoformat(created_after)
            except ValueError:
                return _error("created_after must be a valid YYYY-MM-DD date")
            filters.append("substr(created_at, 1, 10) >= ?")
            params.append(created_after)

        overdue = request.args.get("overdue")
        if overdue and overdue.lower() in ("true", "1", "yes"):
            filters.append(
                "due_date IS NOT NULL AND due_date < ? AND status NOT IN ('Completed', 'completed')"
            )
            params.append(date.today().isoformat())

        recurrence = request.args.get("recurrence") or request.args.get("recurrence_pattern")
        if recurrence:
            rec_clean = recurrence.strip().lower()
            if rec_clean not in VALID_RECURRENCES:
                return _error("recurrence must be one of: none, daily, weekly, monthly, yearly")
            filters.append("recurrence_pattern = ?")
            params.append(rec_clean)

        assigned_to_param = request.args.get("assigned_to")
        if assigned_to_param:
            if assigned_to_param.lower() in ("null", "unassigned", "none"):
                filters.append("assigned_to IS NULL")
            else:
                try:
                    aid = int(assigned_to_param)
                    filters.append("assigned_to = ?")
                    params.append(aid)
                except ValueError:
                    return _error("assigned_to must be an integer or 'unassigned'")

        sort_by = request.args.get("sort_by") or request.args.get("order_by") or "created_at"
        allowed_sort_fields = {
            "id": "id", "title": "title", "status": "status",
            "priority": "priority", "due_date": "due_date",
            "created_at": "created_at", "updated_at": "updated_at",
        }
        if sort_by not in allowed_sort_fields:
            return _error(f"sort_by must be one of: {', '.join(sorted(allowed_sort_fields))}")

        order = (request.args.get("order") or request.args.get("sort_order") or "desc").lower()
        if order not in ("asc", "desc"):
            return _error("order must be asc or desc")
        order_clause = f"{allowed_sort_fields[sort_by]} {order.upper()}, id DESC"

        page_param = request.args.get("page")
        limit_param = request.args.get("limit") or request.args.get("per_page")
        is_paginated = page_param is not None or limit_param is not None
        page, limit = 1, 10

        if page_param is not None:
            try:
                page = int(page_param)
                if page < 1:
                    return _error("page must be a positive integer")
            except ValueError:
                return _error("page must be a positive integer")

        if limit_param is not None:
            try:
                limit = int(limit_param)
                if not 1 <= limit <= 100:
                    return _error("limit must be an integer between 1 and 100")
            except ValueError:
                return _error("limit must be an integer between 1 and 100")

        if role == "EMPLOYEE":
            filters.append("(assigned_to = ? OR (assigned_to IS NULL AND created_by = ?))")
            params.extend([actor["id"], actor["id"]])

        where_clause = " WHERE " + " AND ".join(filters) if filters else ""

        if is_paginated:
            total = conn.execute(
                f"SELECT COUNT(*) FROM tasks{where_clause}", params
            ).fetchone()[0]
            total_pages = math.ceil(total / limit) if total > 0 else 0
            offset = (page - 1) * limit
            rows = conn.execute(
                f"SELECT * FROM tasks{where_clause} ORDER BY {order_clause} LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            resp = jsonify({
                "tasks": [_public(row) for row in rows],
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
                "pagination": {
                    "total": total, "page": page, "limit": limit,
                    "total_pages": total_pages, "has_next": page < total_pages,
                    "has_prev": page > 1,
                },
            })
            resp.headers["X-Total-Count"] = str(total)
            resp.headers["X-Page"] = str(page)
            resp.headers["X-Per-Page"] = str(limit)
            resp.headers["X-Total-Pages"] = str(total_pages)
            return resp

        rows = conn.execute(
            f"SELECT * FROM tasks{where_clause} ORDER BY {order_clause}", params
        ).fetchall()
        return jsonify([_public(row) for row in rows])


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

    with _db() as conn:
        actor = _actor(conn)
        if actor is None:
            return _error("User not found", 401)
        task, error = _visible_task(conn, task_id, actor)
        if error:
            return error

        cleaned, error = _validate_edit(data, existing=task)
        if error:
            return error
        if "status" in cleaned:
            cleaned["status"] = _status_storage(conn, cleaned["status"])

        cleaned["updated_at"] = _now()
        columns_in_table = _columns(conn)
        if "title" in cleaned and "name" in columns_in_table:
            cleaned["name"] = cleaned["title"]

        assignments = ", ".join(f"{key} = ?" for key in cleaned if key in columns_in_table)
        values = [cleaned[key] for key in cleaned if key in columns_in_table]
        conn.execute(
            f"UPDATE tasks SET {assignments} WHERE id = ?",
            [*values, task_id],
        )

        if "status" in cleaned:
            _sync_legacy_completed(conn, task_id, cleaned["status"])
            if STATUS_API.get(cleaned["status"], "") == "completed":
                _handle_recurring_task_completion(conn, _task(conn, task_id))

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
        task, error = _visible_task(conn, task_id, actor)
        if error:
            return error

        db_status = _status_storage(conn, cleaned["status"])
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (db_status, _now(), task_id),
        )
        _sync_legacy_completed(conn, task_id, db_status)
        if STATUS_API.get(db_status, "") == "completed":
            _handle_recurring_task_completion(conn, _task(conn, task_id))
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
        _, error = _visible_task(conn, task_id, actor)
        if error:
            return error
        error = _assignee_error(conn, data["assigned_to"])
        if error:
            return error
        conn.execute(
            "UPDATE tasks SET assigned_to = ?, updated_at = ? WHERE id = ?",
            (data["assigned_to"], _now(), task_id),
        )
        return jsonify(_public(_task(conn, task_id)))


@tasks_bp.route("/api/tasks/bulk", methods=["PATCH", "POST"])
@tasks_bp.route("/api/tasks/bulk-update", methods=["PATCH", "POST"])
@login_required
def bulk_update_tasks():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Expected a JSON object")

    task_ids = data.get("task_ids")
    if task_ids is None:
        task_ids = data.get("ids")
    if task_ids is None or not isinstance(task_ids, list):
        return _error("task_ids must be a non-empty list of task IDs")
    if not task_ids:
        return _error("task_ids cannot be empty")
    if len(task_ids) > 100:
        return _error("Cannot bulk update more than 100 tasks at once")

    cleaned_ids = []
    for tid in task_ids:
        if isinstance(tid, bool) or not isinstance(tid, int) or tid < 1:
            return _error("Each task ID must be a positive integer")
        cleaned_ids.append(tid)

    raw_updates = data.get("updates")
    if raw_updates is None:
        raw_updates = {k: v for k, v in data.items() if k not in ("task_ids", "ids")}
    if not isinstance(raw_updates, dict) or not raw_updates:
        return _error("No update fields provided")

    forbidden = set(raw_updates) & {"id", "created_by", "created_at", "updated_at"}
    if forbidden:
        return _error(f"Cannot bulk update field(s): {', '.join(sorted(forbidden))}")

    allowed_update_keys = EDITABLE_FIELDS | {"assigned_to"}
    unknown = set(raw_updates) - allowed_update_keys
    if unknown:
        return _error(f"Unsupported field(s): {', '.join(sorted(unknown))}")

    fields = {k: v for k, v in raw_updates.items() if k != "assigned_to"}
    cleaned, error = _validate_edit(fields)
    if error:
        return error

    with _db() as conn:
        actor = _actor(conn)
        if actor is None:
            return _error("User not found", 401)
        if "assigned_to" in raw_updates:
            if not _can_manage(actor):
                return _error("Only a manager or admin can assign tasks", 403)
            assigned_to = raw_updates["assigned_to"]
            assign_err = _assignee_error(conn, assigned_to)
            if assign_err:
                return assign_err
            cleaned["assigned_to"] = assigned_to
        if not cleaned:
            return _error("No valid fields to update")

        tasks = []
        for tid in cleaned_ids:
            task = _task(conn, tid)
            if task is None:
                return _error(f"Task {tid} not found", 404)
            if not _can_access(task, actor):
                return _error(f"Access denied for task {tid}", 403)
            tasks.append(task)

        if "status" in cleaned:
            cleaned["status"] = _status_storage(conn, cleaned["status"])
        cleaned["updated_at"] = _now()
        columns_in_table = _columns(conn)
        if "title" in cleaned and "name" in columns_in_table:
            cleaned["name"] = cleaned["title"]

        assignments = ", ".join(f"{k} = ?" for k in cleaned if k in columns_in_table)
        values = [cleaned[k] for k in cleaned if k in columns_in_table]
        updated_tasks = []
        for task in tasks:
            tid = task["id"]
            conn.execute(
                f"UPDATE tasks SET {assignments} WHERE id = ?",
                [*values, tid],
            )
            if "status" in cleaned:
                _sync_legacy_completed(conn, tid, cleaned["status"])
                if STATUS_API.get(cleaned["status"], "") == "completed":
                    _handle_recurring_task_completion(conn, _task(conn, tid))
            updated_tasks.append(_task(conn, tid))

        return jsonify({
            "message": f"Successfully updated {len(updated_tasks)} tasks",
            "updated_count": len(updated_tasks),
            "updated_tasks": [_public(task) for task in updated_tasks],
        })


@tasks_bp.route("/api/tasks/<int:task_id>/duplicate", methods=["POST"])
@tasks_bp.route("/api/tasks/<int:task_id>/copy", methods=["POST"])
@login_required
def duplicate_task(task_id):
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _error("Expected a JSON object")
    allowed_overrides = EDITABLE_FIELDS | {"assigned_to"}
    unknown = set(data) - allowed_overrides
    if unknown:
        return _error(f"Unsupported field(s): {', '.join(sorted(unknown))}")

    fields = {k: v for k, v in data.items() if k != "assigned_to"}
    cleaned_overrides, error = _validate_edit(fields)
    if error:
        return error

    with _db() as conn:
        actor = _actor(conn)
        if actor is None:
            return _error("User not found", 401)
        original_task, error = _visible_task(conn, task_id, actor)
        if error:
            return error
        task_keys = original_task.keys() if hasattr(original_task, "keys") else original_task

        if "assigned_to" in data:
            if not _can_manage(actor):
                return _error("Only a manager or admin can assign tasks", 403)
            assigned_to = data["assigned_to"]
            assign_err = _assignee_error(conn, assigned_to)
            if assign_err:
                return assign_err
        elif str(actor["role"]).upper() == "EMPLOYEE":
            assigned_to = actor["id"]
        else:
            assigned_to = original_task["assigned_to"] if "assigned_to" in task_keys else None

        orig_title = (
            original_task["title"]
            if "title" in task_keys and original_task["title"]
            else (original_task["name"] if "name" in task_keys else "Task")
        )
        new_title = cleaned_overrides.get("title") or f"Copy of {orig_title}"
        if len(new_title) > 200:
            new_title = new_title[:200]

        new_desc = cleaned_overrides.get(
            "description", original_task["description"] if "description" in task_keys else ""
        )
        new_priority = cleaned_overrides.get(
            "priority", original_task["priority"] if "priority" in task_keys else "Medium"
        )
        new_category = cleaned_overrides.get(
            "category", original_task["category"] if "category" in task_keys else "Personal"
        )
        new_due_date = cleaned_overrides.get(
            "due_date", original_task["due_date"] if "due_date" in task_keys else None
        )
        new_rec_pattern = cleaned_overrides.get(
            "recurrence_pattern",
            original_task["recurrence_pattern"] if "recurrence_pattern" in task_keys else "none",
        )
        new_rec_interval = cleaned_overrides.get(
            "recurrence_interval",
            original_task["recurrence_interval"] if "recurrence_interval" in task_keys else 1,
        )
        new_rec_end_date = cleaned_overrides.get(
            "recurrence_end_date",
            original_task["recurrence_end_date"] if "recurrence_end_date" in task_keys else None,
        )

        now = _now()
        columns_in_table = _columns(conn)
        insert_data = {
            "title": new_title,
            "description": new_desc,
            "status": _status_storage(conn, "pending"),
            "priority": new_priority,
            "category": new_category,
            "due_date": new_due_date,
            "created_by": actor["id"],
            "assigned_to": assigned_to,
            "recurrence_pattern": new_rec_pattern,
            "recurrence_interval": new_rec_interval,
            "recurrence_end_date": new_rec_end_date,
            "parent_task_id": None,
            "created_at": now,
            "updated_at": now,
        }
        if "name" in columns_in_table:
            insert_data["name"] = new_title
        if "user_id" in columns_in_table:
            insert_data["user_id"] = actor["id"]
        if "is_completed" in columns_in_table:
            insert_data["is_completed"] = 0

        names = [k for k in insert_data if k in columns_in_table]
        placeholders = ", ".join("?" for _ in names)
        columns = ", ".join(names)
        cursor = conn.execute(
            f"INSERT INTO tasks ({columns}) VALUES ({placeholders})",
            [insert_data[name] for name in names],
        )
        return jsonify(_public(_task(conn, cursor.lastrowid))), 201


def create_tasks_app(test_config=None):
    """Application factory for Task Management API and its test suite."""
    from flask import Flask
    from management import init_management_db

    app = Flask(__name__)
    cfg = {
        "TESTING": True,
        "SECRET_KEY": "task-test-secret-key",
        "DATABASE_PATH": str(Path(__file__).resolve().parent / "users.db"),
    }
    if test_config:
        cfg.update(test_config)
    app.config.update(cfg)

    auth.init_db(app)
    init_management_db(app)
    init_tasks_db(app)

    app.register_blueprint(auth.auth_bp)
    app.register_blueprint(tasks_bp)
    return app
