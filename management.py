import re
import sqlite3
from datetime import date, timedelta

from flask import Blueprint, g, jsonify, request

from auth import configured_admin_emails, get_db, login_required, roles_required


management_bp = Blueprint("management", __name__, url_prefix="/api")
ROLES = {"ADMIN", "MANAGER", "EMPLOYEE"}
EMPLOYEE_STATUSES = {"Active", "Inactive"}
PROJECT_STATUSES = {"On Track", "In Progress", "At Risk", "Completed"}
TASK_STATUSES = {"Not Started", "In Progress", "Completed"}
PRIORITIES = {"Low", "Medium", "High"}
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def init_management_db(app):
    database = sqlite3.connect(app.config["DATABASE_PATH"], timeout=10)
    try:
        database.execute("PRAGMA foreign_keys = ON")
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE SET NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                department TEXT NOT NULL DEFAULT 'General',
                title TEXT NOT NULL DEFAULT 'Employee',
                role TEXT NOT NULL DEFAULT 'EMPLOYEE'
                    CHECK (role IN ('ADMIN', 'MANAGER', 'EMPLOYEE')),
                status TEXT NOT NULL DEFAULT 'Active'
                    CHECK (status IN ('Active', 'Inactive')),
                start_date TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                description TEXT NOT NULL DEFAULT '',
                manager_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS team_members (
                team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                PRIMARY KEY (team_id, employee_id)
            );
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
                manager_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                start_date TEXT,
                due_date TEXT,
                status TEXT NOT NULL DEFAULT 'Not Started'
                    CHECK (status IN ('On Track', 'In Progress', 'At Risk', 'Completed')),
                progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                assignee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                due_date TEXT,
                priority TEXT NOT NULL DEFAULT 'Medium'
                    CHECK (priority IN ('Low', 'Medium', 'High')),
                status TEXT NOT NULL DEFAULT 'Not Started'
                    CHECK (status IN ('Not Started', 'In Progress', 'Completed')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);

            CREATE TABLE IF NOT EXISTS task_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                author_name TEXT NOT NULL,
                author_role TEXT NOT NULL DEFAULT 'EMPLOYEE',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_task_comments_task ON task_comments(task_id);

            CREATE TABLE IF NOT EXISTS task_activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                actor_name TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_task_activities_task ON task_activities(task_id);
            """
        )
        task_cols = {row[1] for row in database.execute("PRAGMA table_info(tasks)").fetchall()}
        if "description" not in task_cols:
            database.execute("ALTER TABLE tasks ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        if "is_recurring" not in task_cols:
            database.execute("ALTER TABLE tasks ADD COLUMN is_recurring INTEGER NOT NULL DEFAULT 0")
        if "recurrence_interval" not in task_cols:
            database.execute("ALTER TABLE tasks ADD COLUMN recurrence_interval TEXT NOT NULL DEFAULT 'none'")
        if "recurrence_end_date" not in task_cols:
            database.execute("ALTER TABLE tasks ADD COLUMN recurrence_end_date TEXT")
        database.execute(
            """
            INSERT OR IGNORE INTO employees (user_id, name, email, role)
            SELECT id, name, email, role FROM users
            """
        )
        admin_emails = configured_admin_emails(app.config)
        for admin_email in admin_emails:
            database.execute(
                "UPDATE users SET role = 'ADMIN' WHERE email = ? COLLATE NOCASE",
                (admin_email,),
            )
            database.execute(
                """
                UPDATE employees SET role = 'ADMIN'
                WHERE email = ? COLLATE NOCASE
                """,
                (admin_email,),
            )
        database.commit()
    finally:
        database.close()


def create_employee_for_user(database, user):
    database.execute(
        """
        INSERT OR IGNORE INTO employees (user_id, name, email, role)
        VALUES (?, ?, ?, ?)
        """,
        (user["id"], user["name"], user["email"], user["role"]),
    )


def _json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    return data


def _text(data, field, label, required=False, limit=200):
    value = data.get(field, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{label} is required.")
    if len(value) > limit:
        raise ValueError(f"{label} must be {limit} characters or fewer.")
    return value


def _optional_id(data, field, label):
    value = data.get(field)
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} is invalid.")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{label} is invalid.")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} is invalid.") from error


def _date(data, field, label):
    value = _text(data, field, label, limit=10)
    if not value:
        return None
    try:
        parsed_date = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be a valid YYYY-MM-DD date.") from error
    if parsed_date.isoformat() != value:
        raise ValueError(f"{label} must be a valid YYYY-MM-DD date.")
    return value


def _choice(data, field, allowed, default, label):
    value = data.get(field, default)
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"Please choose a valid {label.lower()}.")
    return value


def _required_record(data):
    if data is None:
        return None, (jsonify(error="Request body must be a JSON object."), 400)
    return data, None


def _employee(row):
    return {
        "id": row["id"],
        "userId": row["user_id"],
        "name": row["name"],
        "email": row["email"],
        "department": row["department"],
        "title": row["title"],
        "role": row["role"],
        "status": row["status"],
        "startDate": row["start_date"] or "",
    }


def _employees():
    return [
        _employee(row)
        for row in get_db().execute("SELECT * FROM employees ORDER BY name COLLATE NOCASE")
    ]


def _teams():
    database = get_db()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "managerId": row["manager_id"],
            "memberIds": [
                member["employee_id"]
                for member in database.execute(
                    "SELECT employee_id FROM team_members WHERE team_id = ? ORDER BY employee_id",
                    (row["id"],),
                )
            ],
        }
        for row in database.execute("SELECT * FROM teams ORDER BY name COLLATE NOCASE")
    ]


def _projects():
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "teamId": row["team_id"],
            "managerId": row["manager_id"],
            "startDate": row["start_date"] or "",
            "dueDate": row["due_date"] or "",
            "status": row["status"],
            "progress": row["progress"],
        }
        for row in get_db().execute("SELECT * FROM projects ORDER BY id DESC")
    ]


def _next_due_date(current_due, interval):
    base_date = date.today()
    if current_due:
        try:
            base_date = date.fromisoformat(current_due)
        except ValueError:
            base_date = date.today()

    if interval == "daily":
        next_d = base_date + timedelta(days=1)
    elif interval == "weekly":
        next_d = base_date + timedelta(days=7)
    elif interval == "biweekly":
        next_d = base_date + timedelta(days=14)
    elif interval == "monthly":
        year = base_date.year + (1 if base_date.month == 12 else 0)
        month = 1 if base_date.month == 12 else base_date.month + 1
        day = min(base_date.day, 28)
        try:
            next_d = date(year, month, day)
        except ValueError:
            next_d = base_date + timedelta(days=30)
    else:
        next_d = base_date + timedelta(days=7)

    return next_d.isoformat()


def _log_activity(database, task_id, action, details=""):
    try:
        user_id = g.current_user["id"] if hasattr(g, "current_user") and g.current_user else None
        actor_name = g.current_user["name"] if hasattr(g, "current_user") and g.current_user else "System"
        database.execute(
            """
            INSERT INTO task_activities (task_id, user_id, actor_name, action, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, user_id, actor_name, action, details),
        )
        database.commit()
    except Exception:
        pass


def _task_dict(row, comments_count=0):
    keys = row.keys() if hasattr(row, "keys") else []
    description = row["description"] if "description" in keys and row["description"] else ""
    is_recurring = bool(row["is_recurring"]) if "is_recurring" in keys and row["is_recurring"] else False
    recurrence_interval = row["recurrence_interval"] if "recurrence_interval" in keys and row["recurrence_interval"] else "none"
    recurrence_end_date = row["recurrence_end_date"] if "recurrence_end_date" in keys and row["recurrence_end_date"] else ""
    created_at = row["created_at"] if "created_at" in keys and row["created_at"] else ""
    project_name = row["project_name"] if "project_name" in keys and row["project_name"] else ""
    return {
        "id": row["id"],
        "name": row["name"],
        "description": description,
        "projectId": row["project_id"],
        "projectName": project_name,
        "assigneeId": row["assignee_id"],
        "dueDate": row["due_date"] or "",
        "priority": row["priority"],
        "status": row["status"],
        "isRecurring": is_recurring,
        "recurrenceInterval": recurrence_interval,
        "recurrenceEndDate": recurrence_end_date,
        "createdAt": created_at,
        "commentsCount": comments_count,
    }


def _handle_task_recurrence(database, task):
    keys = task.keys() if hasattr(task, "keys") else []
    if "is_recurring" not in keys or not task["is_recurring"]:
        return
    interval = task["recurrence_interval"] if "recurrence_interval" in keys else "none"
    if not interval or interval == "none":
        return

    current_due = task["due_date"] or ""
    next_due = _next_due_date(current_due, interval)
    end_date = task["recurrence_end_date"] if "recurrence_end_date" in keys else None

    if end_date and next_due > end_date:
        _log_activity(database, task["id"], "recurrence_ended", f"Recurrence completed (end date {end_date} reached)")
        return

    cursor = database.execute("PRAGMA table_info(tasks)")
    table_cols = {row[1] for row in cursor.fetchall()}

    cols = ["name", "project_id", "assignee_id", "due_date", "priority", "status"]
    vals = [task["name"], task["project_id"], task["assignee_id"], next_due, task["priority"], "Not Started"]

    if "description" in table_cols:
        cols.append("description")
        vals.append(task["description"] if "description" in keys else "")
    if "is_recurring" in table_cols:
        cols.append("is_recurring")
        vals.append(1)
    if "recurrence_interval" in table_cols:
        cols.append("recurrence_interval")
        vals.append(interval)
    if "recurrence_end_date" in table_cols:
        cols.append("recurrence_end_date")
        vals.append(end_date)

    cursor = database.execute(
        f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join('?' for _ in vals)})",
        vals,
    )
    new_task_id = cursor.lastrowid
    database.commit()

    _log_activity(database, task["id"], "recurring_next", f"Completed. Next recurring instance #{new_task_id} generated for {next_due}")
    _log_activity(database, new_task_id, "created_recurring", f"Recurring task automatically scheduled for {next_due}")


def _tasks(assignee_id=None):
    database = get_db()
    has_comments = database.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'task_comments'"
    ).fetchone() is not None
    subquery = "(SELECT COUNT(*) FROM task_comments WHERE task_comments.task_id = tasks.id) AS comments_count" if has_comments else "0 AS comments_count"

    if assignee_id is None:
        rows = database.execute(
            f"""
            SELECT tasks.*, projects.name AS project_name, {subquery}
            FROM tasks
            LEFT JOIN projects ON projects.id = tasks.project_id
            ORDER BY tasks.id DESC
            """
        )
    else:
        rows = database.execute(
            f"""
            SELECT tasks.*, projects.name AS project_name, {subquery}
            FROM tasks
            LEFT JOIN projects ON projects.id = tasks.project_id
            WHERE tasks.assignee_id = ?
            ORDER BY tasks.id DESC
            """,
            (assignee_id,),
        )
    return [
        _task_dict(row, row["comments_count"] if "comments_count" in row.keys() else 0)
        for row in rows
    ]


def _not_found(entity):
    return jsonify(error=f"{entity.capitalize()} not found."), 404


def _validate_reference(database, table, record_id, label):
    if record_id is not None and database.execute(
        f"SELECT 1 FROM {table} WHERE id = ?", (record_id,)
    ).fetchone() is None:
        raise ValueError(f"Selected {label.lower()} does not exist.")


def _date_range(start, due):
    if start and due and start > due:
        raise ValueError("The due date must be on or after the start date.")


def _insert_or_update(table, record_id, columns, values):
    database = get_db()
    try:
        if record_id is None:
            cursor = database.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in values)})",
                values,
            )
            record_id = cursor.lastrowid
        else:
            cursor = database.execute(
                f"UPDATE {table} SET {', '.join(f'{column} = ?' for column in columns)} WHERE id = ?",
                (*values, record_id),
            )
            if cursor.rowcount == 0:
                database.rollback()
                return None
        database.commit()
        return record_id
    except sqlite3.IntegrityError as error:
        database.rollback()
        raise ValueError("A record with that unique value already exists or a selected record is in use.") from error


def _save_employee(data, record_id=None):
    database = get_db()
    name = _text(data, "name", "Name", required=True, limit=120)
    email = _text(data, "email", "Email", required=True, limit=254).lower()
    if not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Please enter a valid email address.")
    department = _text(data, "department", "Department", required=True, limit=100)
    title = _text(data, "title", "Job title", required=True, limit=120)
    role = _choice(data, "role", ROLES, "EMPLOYEE", "employee role")
    status = _choice(data, "status", EMPLOYEE_STATUSES, "Active", "employee status")
    start_date = _date(data, "startDate", "Start date")
    values = (name, email, department, title, role, status, start_date)
    columns = ("name", "email", "department", "title", "role", "status", "start_date")
    if record_id is None:
        employee_id = _insert_or_update("employees", None, columns, values)
    else:
        linked_user = database.execute(
            "SELECT user_id FROM employees WHERE id = ?", (record_id,)
        ).fetchone()
        if linked_user is None:
            return None
        user_id = linked_user["user_id"]
        if user_id is not None:
            try:
                database.execute(
                    "UPDATE users SET name = ?, email = ?, role = ? WHERE id = ?",
                    (name, email, role, user_id),
                )
            except sqlite3.IntegrityError as error:
                database.rollback()
                raise ValueError("An account with that email already exists.") from error
        employee_id = _insert_or_update("employees", record_id, columns, values)
    return employee_id


def _save_team(data, record_id=None):
    database = get_db()
    name = _text(data, "name", "Team name", required=True, limit=100)
    description = _text(data, "description", "Description", limit=1000)
    manager_id = _optional_id(data, "managerId", "Manager")
    _validate_reference(database, "employees", manager_id, "Manager")
    member_ids = data.get("memberIds", [])
    if not isinstance(member_ids, list):
        raise ValueError("Team members must be a list.")
    try:
        member_ids = sorted(set(int(value) for value in member_ids))
    except (TypeError, ValueError) as error:
        raise ValueError("One or more team members are invalid.") from error
    for employee_id in member_ids:
        _validate_reference(database, "employees", employee_id, "Team member")
    team_id = _insert_or_update(
        "teams", record_id, ("name", "description", "manager_id"), (name, description, manager_id)
    )
    if team_id is None:
        return None
    database.execute("DELETE FROM team_members WHERE team_id = ?", (team_id,))
    database.executemany(
        "INSERT INTO team_members (team_id, employee_id) VALUES (?, ?)",
        [(team_id, employee_id) for employee_id in member_ids],
    )
    database.commit()
    return team_id


def _save_project(data, record_id=None):
    database = get_db()
    name = _text(data, "name", "Project name", required=True, limit=120)
    description = _text(data, "description", "Description", limit=2000)
    team_id = _optional_id(data, "teamId", "Team")
    manager_id = _optional_id(data, "managerId", "Project manager")
    _validate_reference(database, "teams", team_id, "Team")
    _validate_reference(database, "employees", manager_id, "Project manager")
    start_date = _date(data, "startDate", "Start date")
    due_date = _date(data, "dueDate", "Due date")
    _date_range(start_date, due_date)
    status = _choice(data, "status", PROJECT_STATUSES, "In Progress", "project status")
    raw_progress = data.get("progress", 0)
    if isinstance(raw_progress, bool) or (
        isinstance(raw_progress, float) and not raw_progress.is_integer()
    ):
        raise ValueError("Project completion must be a number between 0 and 100.")
    try:
        progress = int(raw_progress)
    except (TypeError, ValueError) as error:
        raise ValueError("Project completion must be a number between 0 and 100.") from error
    if not 0 <= progress <= 100:
        raise ValueError("Project completion must be between 0 and 100.")
    return _insert_or_update(
        "projects",
        record_id,
        ("name", "description", "team_id", "manager_id", "start_date", "due_date", "status", "progress"),
        (name, description, team_id, manager_id, start_date, due_date, status, progress),
    )


def _save_task(data, record_id=None):
    database = get_db()
    existing = None
    if record_id is not None:
        existing = database.execute("SELECT * FROM tasks WHERE id = ?", (record_id,)).fetchone()
        if existing is None:
            return None

    if record_id is None or "name" in data:
        name = _text(data, "name", "Task name", required=True, limit=140)
    else:
        name = existing["name"]

    if "description" in data:
        description = _text(data, "description", "Description", limit=5000)
    elif existing and "description" in existing.keys():
        description = existing["description"]
    else:
        description = ""

    if "projectId" in data or "project_id" in data:
        project_id = _optional_id(data, "projectId" if "projectId" in data else "project_id", "Project")
    elif existing:
        project_id = existing["project_id"]
    else:
        project_id = None

    if "assigneeId" in data or "assignee_id" in data:
        assignee_id = _optional_id(data, "assigneeId" if "assigneeId" in data else "assignee_id", "Assignee")
    elif existing:
        assignee_id = existing["assignee_id"]
    else:
        assignee_id = None

    _validate_reference(database, "projects", project_id, "Project")
    _validate_reference(database, "employees", assignee_id, "Assignee")

    if "dueDate" in data or "due_date" in data:
        due_date = _date(data, "dueDate" if "dueDate" in data else "due_date", "Due date")
    elif existing:
        due_date = existing["due_date"]
    else:
        due_date = None

    if "priority" in data:
        priority = _choice(data, "priority", PRIORITIES, "Medium", "task priority")
    elif existing:
        priority = existing["priority"]
    else:
        priority = "Medium"

    if "status" in data:
        raw_status = data["status"]
        if raw_status == "To Do":
            raw_status = "Not Started"
        status = _choice({"status": raw_status}, "status", TASK_STATUSES, "Not Started", "task status")
    elif existing:
        status = existing["status"]
    else:
        status = "Not Started"

    if "isRecurring" in data or "is_recurring" in data:
        is_recurring = 1 if (data.get("isRecurring") or data.get("is_recurring")) else 0
    elif existing and "is_recurring" in existing.keys():
        is_recurring = existing["is_recurring"]
    else:
        is_recurring = 0

    if "recurrenceInterval" in data or "recurrence_interval" in data:
        recurrence_interval = data.get("recurrenceInterval") or data.get("recurrence_interval") or "none"
        if recurrence_interval not in {"none", "daily", "weekly", "biweekly", "monthly"}:
            recurrence_interval = "none"
    elif existing and "recurrence_interval" in existing.keys():
        recurrence_interval = existing["recurrence_interval"]
    else:
        recurrence_interval = "none"

    if "recurrenceEndDate" in data or "recurrence_end_date" in data:
        recurrence_end_date = _date(data, "recurrenceEndDate" if "recurrenceEndDate" in data else "recurrence_end_date", "Recurrence end date")
    elif existing and "recurrence_end_date" in existing.keys():
        recurrence_end_date = existing["recurrence_end_date"]
    else:
        recurrence_end_date = None

    cursor = database.execute("PRAGMA table_info(tasks)")
    table_cols = {row[1] for row in cursor.fetchall()}

    columns = ["name", "project_id", "assignee_id", "due_date", "priority", "status"]
    values = [name, project_id, assignee_id, due_date, priority, status]

    if "description" in table_cols:
        columns.append("description")
        values.append(description)
    if "is_recurring" in table_cols:
        columns.append("is_recurring")
        values.append(is_recurring)
    if "recurrence_interval" in table_cols:
        columns.append("recurrence_interval")
        values.append(recurrence_interval)
    if "recurrence_end_date" in table_cols:
        columns.append("recurrence_end_date")
        values.append(recurrence_end_date)

    task_id = _insert_or_update(
        "tasks",
        record_id,
        tuple(columns),
        tuple(values),
    )

    if task_id:
        if record_id is None:
            _log_activity(database, task_id, "created", f"Task '{name}' created")
        else:
            _log_activity(database, task_id, "updated", "Task details updated")

    return task_id


@management_bp.get("/workspace")
@login_required
def workspace():
    database = get_db()
    employee = database.execute(
        "SELECT id FROM employees WHERE user_id = ?", (g.current_user["id"],)
    ).fetchone()
    if g.current_user["role"] != "ADMIN":
        employee_id = employee["id"] if employee else -1
        return jsonify(
            employees=[],
            teams=[],
            projects=[],
            tasks=_tasks(employee_id),
            currentEmployeeId=employee["id"] if employee else None,
        )
    return jsonify(
        employees=_employees(),
        teams=_teams(),
        projects=_projects(),
        tasks=_tasks(),
        currentEmployeeId=employee["id"] if employee else None,
    )


@management_bp.get("/employees")
@roles_required("ADMIN")
def list_employees():
    return jsonify(employees=_employees())


@management_bp.post("/employees")
@roles_required("ADMIN")
def create_employee():
    data, error = _required_record(_json_object())
    if error:
        return error
    try:
        employee_id = _save_employee(data)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    row = get_db().execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
    return jsonify(employee=_employee(row)), 201


@management_bp.patch("/employees/<int:record_id>")
@roles_required("ADMIN")
def update_employee(record_id):
    data, error = _required_record(_json_object())
    if error:
        return error
    try:
        employee_id = _save_employee(data, record_id)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    if employee_id is None:
        return _not_found("employee")
    row = get_db().execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
    return jsonify(employee=_employee(row))


@management_bp.patch("/employees/<int:record_id>/status")
@roles_required("ADMIN")
def update_employee_status(record_id):
    data, error = _required_record(_json_object())
    if error:
        return error
    status = data.get("status")
    if not isinstance(status, str) or status not in EMPLOYEE_STATUSES:
        return jsonify(error="Please choose a valid employee status."), 400
    database = get_db()
    cursor = database.execute("UPDATE employees SET status = ? WHERE id = ?", (status, record_id))
    if cursor.rowcount == 0:
        return _not_found("employee")
    database.commit()
    return jsonify(employee=_employee(database.execute("SELECT * FROM employees WHERE id = ?", (record_id,)).fetchone()))


@management_bp.get("/teams")
@roles_required("ADMIN")
def list_teams():
    return jsonify(teams=_teams())


@management_bp.post("/teams")
@roles_required("ADMIN")
def create_team():
    data, error = _required_record(_json_object())
    if error:
        return error
    try:
        team_id = _save_team(data)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    return jsonify(team=next(team for team in _teams() if team["id"] == team_id)), 201


@management_bp.patch("/teams/<int:record_id>")
@roles_required("ADMIN")
def update_team(record_id):
    data, error = _required_record(_json_object())
    if error:
        return error
    try:
        team_id = _save_team(data, record_id)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    if team_id is None:
        return _not_found("team")
    return jsonify(team=next(team for team in _teams() if team["id"] == team_id))


@management_bp.delete("/teams/<int:record_id>")
@roles_required("ADMIN")
def delete_team(record_id):
    database = get_db()
    cursor = database.execute("DELETE FROM teams WHERE id = ?", (record_id,))
    if cursor.rowcount == 0:
        return _not_found("team")
    database.commit()
    return jsonify(message="Team deleted.")


@management_bp.get("/projects")
@roles_required("ADMIN")
def list_projects():
    return jsonify(projects=_projects())


@management_bp.post("/projects")
@roles_required("ADMIN")
def create_project():
    data, error = _required_record(_json_object())
    if error:
        return error
    try:
        project_id = _save_project(data)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    row = get_db().execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return jsonify(project=next(item for item in _projects() if item["id"] == row["id"])), 201


@management_bp.patch("/projects/<int:record_id>")
@roles_required("ADMIN")
def update_project(record_id):
    data, error = _required_record(_json_object())
    if error:
        return error
    try:
        project_id = _save_project(data, record_id)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    if project_id is None:
        return _not_found("project")
    return jsonify(project=next(item for item in _projects() if item["id"] == project_id))


@management_bp.delete("/projects/<int:record_id>")
@roles_required("ADMIN")
def delete_project(record_id):
    database = get_db()
    cursor = database.execute("DELETE FROM projects WHERE id = ?", (record_id,))
    if cursor.rowcount == 0:
        return _not_found("project")
    database.commit()
    return jsonify(message="Project deleted.")


@management_bp.get("/tasks")
@login_required
def list_tasks():
    if g.current_user["role"] == "ADMIN":
        return jsonify(tasks=_tasks())
    employee = get_db().execute(
        "SELECT id FROM employees WHERE user_id = ?", (g.current_user["id"],)
    ).fetchone()
    return jsonify(tasks=_tasks(employee["id"] if employee else -1))


@management_bp.post("/tasks")
@roles_required("ADMIN")
def create_task():
    data, error = _required_record(_json_object())
    if error:
        return error
    try:
        task_id = _save_task(data)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    return jsonify(task=next(task for task in _tasks() if task["id"] == task_id)), 201


@management_bp.get("/tasks/<int:record_id>")
@login_required
def get_task(record_id):
    database = get_db()
    has_comments = database.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'task_comments'"
    ).fetchone() is not None
    subquery = "(SELECT COUNT(*) FROM task_comments WHERE task_comments.task_id = tasks.id) AS comments_count" if has_comments else "0 AS comments_count"

    task = database.execute(
        f"""
        SELECT tasks.*, projects.name AS project_name, {subquery}
        FROM tasks
        LEFT JOIN projects ON projects.id = tasks.project_id
        WHERE tasks.id = ?
        """,
        (record_id,),
    ).fetchone()
    if task is None:
        return _not_found("task")

    if g.current_user["role"] == "EMPLOYEE":
        employee = database.execute(
            "SELECT id FROM employees WHERE user_id = ?", (g.current_user["id"],)
        ).fetchone()
        if employee is None or task["assignee_id"] != employee["id"]:
            return jsonify(error="Access denied for this task."), 403

    comments = []
    if has_comments:
        comments = [
            {
                "id": row["id"],
                "taskId": row["task_id"],
                "userId": row["user_id"],
                "authorName": row["author_name"],
                "authorRole": row["author_role"],
                "content": row["content"],
                "createdAt": row["created_at"],
            }
            for row in database.execute(
                "SELECT * FROM task_comments WHERE task_id = ? ORDER BY id ASC",
                (record_id,),
            )
        ]

    has_activities = database.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'task_activities'"
    ).fetchone() is not None
    activities = []
    if has_activities:
        activities = [
            {
                "id": row["id"],
                "taskId": row["task_id"],
                "userId": row["user_id"],
                "actorName": row["actor_name"],
                "action": row["action"],
                "details": row["details"],
                "createdAt": row["created_at"],
            }
            for row in database.execute(
                "SELECT * FROM task_activities WHERE task_id = ? ORDER BY id DESC",
                (record_id,),
            )
        ]

    task_data = _task_dict(task, len(comments))
    task_data["comments"] = comments
    task_data["activities"] = activities

    return jsonify(task=task_data)


@management_bp.patch("/tasks/<int:record_id>")
@login_required
def update_task(record_id):
    data, error = _required_record(_json_object())
    if error:
        return error
    if g.current_user["role"] == "EMPLOYEE":
        raw_status = data.get("status")
        if raw_status == "To Do":
            raw_status = "Not Started"
        if set(data) != {"status"} or not isinstance(raw_status, str) or raw_status not in TASK_STATUSES:
            return jsonify(error="Employees may only update task status."), 403
        data["status"] = raw_status
        database = get_db()
        employee = database.execute(
            "SELECT id FROM employees WHERE user_id = ?", (g.current_user["id"],)
        ).fetchone()
        task = database.execute(
            "SELECT * FROM tasks WHERE id = ?", (record_id,)
        ).fetchone()
        if task is None:
            return _not_found("task")
        if employee is None or task["assignee_id"] != employee["id"]:
            return jsonify(error="You can only update tasks assigned to you."), 403
        old_status = task["status"]
        database.execute("UPDATE tasks SET status = ? WHERE id = ?", (data["status"], record_id))
        database.commit()
        if old_status != data["status"]:
            _log_activity(database, record_id, "status_changed", f"Status changed from {old_status} to {data['status']}")
            if data["status"] == "Completed":
                _handle_task_recurrence(database, task)
    elif g.current_user["role"] == "ADMIN":
        database = get_db()
        task = database.execute("SELECT * FROM tasks WHERE id = ?", (record_id,)).fetchone()
        if task is None:
            return _not_found("task")
        old_status = task["status"]
        if "status" in data and data["status"] == "To Do":
            data["status"] = "Not Started"
        try:
            task_id = _save_task(data, record_id)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        if task_id is None:
            return _not_found("task")
        new_status = data.get("status", old_status)
        if old_status != new_status:
            _log_activity(database, record_id, "status_changed", f"Status changed from {old_status} to {new_status}")
            if new_status == "Completed":
                _handle_task_recurrence(database, task)
    else:
        return jsonify(error="You do not have permission to update tasks."), 403
    return jsonify(task=next(item for item in _tasks() if item["id"] == record_id))


@management_bp.delete("/tasks/<int:record_id>")
@roles_required("ADMIN")
def delete_task(record_id):
    database = get_db()
    cursor = database.execute("DELETE FROM tasks WHERE id = ?", (record_id,))
    if cursor.rowcount == 0:
        return _not_found("task")
    database.commit()
    return jsonify(message="Task deleted.")


@management_bp.get("/tasks/<int:record_id>/comments")
@login_required
def list_task_comments(record_id):
    database = get_db()
    task = database.execute("SELECT * FROM tasks WHERE id = ?", (record_id,)).fetchone()
    if task is None:
        return _not_found("task")
    if g.current_user["role"] == "EMPLOYEE":
        employee = database.execute(
            "SELECT id FROM employees WHERE user_id = ?", (g.current_user["id"],)
        ).fetchone()
        if employee is None or task["assignee_id"] != employee["id"]:
            return jsonify(error="Access denied for this task."), 403

    rows = database.execute(
        "SELECT * FROM task_comments WHERE task_id = ? ORDER BY id ASC",
        (record_id,),
    ).fetchall()
    comments = [
        {
            "id": row["id"],
            "taskId": row["task_id"],
            "userId": row["user_id"],
            "authorName": row["author_name"],
            "authorRole": row["author_role"],
            "content": row["content"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]
    return jsonify(comments=comments)


@management_bp.post("/tasks/<int:record_id>/comments")
@login_required
def create_task_comment(record_id):
    data, error = _required_record(_json_object())
    if error:
        return error
    content = _text(data, "content", "Comment", required=True, limit=2000)
    database = get_db()
    task = database.execute("SELECT * FROM tasks WHERE id = ?", (record_id,)).fetchone()
    if task is None:
        return _not_found("task")
    if g.current_user["role"] == "EMPLOYEE":
        employee = database.execute(
            "SELECT id FROM employees WHERE user_id = ?", (g.current_user["id"],)
        ).fetchone()
        if employee is None or task["assignee_id"] != employee["id"]:
            return jsonify(error="Access denied for this task."), 403

    user_id = g.current_user["id"]
    author_name = g.current_user["name"]
    author_role = g.current_user["role"]

    cursor = database.execute(
        """
        INSERT INTO task_comments (task_id, user_id, author_name, author_role, content)
        VALUES (?, ?, ?, ?, ?)
        """,
        (record_id, user_id, author_name, author_role, content),
    )
    comment_id = cursor.lastrowid
    database.commit()

    _log_activity(database, record_id, "comment_added", f"Comment: {content[:80]}")

    comment = database.execute("SELECT * FROM task_comments WHERE id = ?", (comment_id,)).fetchone()
    return jsonify(comment={
        "id": comment["id"],
        "taskId": comment["task_id"],
        "userId": comment["user_id"],
        "authorName": comment["author_name"],
        "authorRole": comment["author_role"],
        "content": comment["content"],
        "createdAt": comment["created_at"],
    }), 201


@management_bp.get("/tasks/<int:record_id>/activities")
@login_required
def list_task_activities(record_id):
    database = get_db()
    task = database.execute("SELECT * FROM tasks WHERE id = ?", (record_id,)).fetchone()
    if task is None:
        return _not_found("task")
    if g.current_user["role"] == "EMPLOYEE":
        employee = database.execute(
            "SELECT id FROM employees WHERE user_id = ?", (g.current_user["id"],)
        ).fetchone()
        if employee is None or task["assignee_id"] != employee["id"]:
            return jsonify(error="Access denied for this task."), 403

    rows = database.execute(
        "SELECT * FROM task_activities WHERE task_id = ? ORDER BY id DESC",
        (record_id,),
    ).fetchall()
    activities = [
        {
            "id": row["id"],
            "taskId": row["task_id"],
            "userId": row["user_id"],
            "actorName": row["actor_name"],
            "action": row["action"],
            "details": row["details"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]
    return jsonify(activities=activities)


@management_bp.post("/tasks/bulk")
@login_required
def bulk_task_action():
    data, error = _required_record(_json_object())
    if error:
        return error

    task_ids = data.get("taskIds")
    if not isinstance(task_ids, list) or not task_ids:
        return jsonify(error="taskIds must be a non-empty list of task IDs."), 400

    try:
        task_ids = [int(tid) for tid in task_ids]
    except (TypeError, ValueError):
        return jsonify(error="All taskIds must be valid numbers."), 400

    action = data.get("action")
    if action not in {"status", "assign", "delete"}:
        return jsonify(error="action must be 'status', 'assign', or 'delete'."), 400

    database = get_db()
    role = g.current_user["role"]

    placeholders = ", ".join("?" for _ in task_ids)
    existing_tasks = database.execute(
        f"SELECT * FROM tasks WHERE id IN ({placeholders})", task_ids
    ).fetchall()

    if len(existing_tasks) != len(set(task_ids)):
        return jsonify(error="One or more specified tasks do not exist."), 404

    if role == "EMPLOYEE":
        if action != "status":
            return jsonify(error="Employees may only update task status in bulk."), 403
        employee = database.execute(
            "SELECT id FROM employees WHERE user_id = ?", (g.current_user["id"],)
        ).fetchone()
        emp_id = employee["id"] if employee else -1
        for t in existing_tasks:
            if t["assignee_id"] != emp_id:
                return jsonify(error="Employees may only update tasks assigned to them."), 403

    if action == "status":
        raw_status = data.get("status")
        if raw_status == "To Do":
            raw_status = "Not Started"
        if not isinstance(raw_status, str) or raw_status not in TASK_STATUSES:
            return jsonify(error="Please choose a valid task status."), 400

        database.execute(
            f"UPDATE tasks SET status = ? WHERE id IN ({placeholders})",
            (raw_status, *task_ids),
        )
        database.commit()

        for t in existing_tasks:
            _log_activity(database, t["id"], "bulk_status_changed", f"Status changed to {raw_status} via bulk action")
            if raw_status == "Completed" and t["status"] != "Completed":
                _handle_task_recurrence(database, t)

        return jsonify(message=f"Updated status for {len(task_ids)} task(s).", updatedCount=len(task_ids))

    elif action == "assign":
        if role != "ADMIN":
            return jsonify(error="Only administrators can reassign tasks."), 403
        assignee_id = _optional_id(data, "assigneeId", "Assignee")
        _validate_reference(database, "employees", assignee_id, "Assignee")

        database.execute(
            f"UPDATE tasks SET assignee_id = ? WHERE id IN ({placeholders})",
            (assignee_id, *task_ids),
        )
        database.commit()

        for t in existing_tasks:
            _log_activity(database, t["id"], "bulk_reassigned", "Reassigned via bulk action")

        return jsonify(message=f"Reassigned {len(task_ids)} task(s).", updatedCount=len(task_ids))

    elif action == "delete":
        if role != "ADMIN":
            return jsonify(error="Only administrators can delete tasks."), 403

        database.execute(f"DELETE FROM tasks WHERE id IN ({placeholders})", task_ids)
        database.commit()

        return jsonify(message=f"Deleted {len(task_ids)} task(s).", updatedCount=len(task_ids))
