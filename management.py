import re
import sqlite3
from datetime import date

from flask import Blueprint, g, jsonify, request

from auth import configured_admin_emails, get_db, login_required, roles_required
from audit import _employee_name, log_task_modifications, record_activity, record_audit_log


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
            """
        )
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


def _tasks(assignee_id=None):
    database = get_db()
    if assignee_id is None:
        rows = database.execute(
            """
            SELECT tasks.*, projects.name AS project_name
            FROM tasks
            LEFT JOIN projects ON projects.id = tasks.project_id
            ORDER BY tasks.id DESC
            """
        )
    else:
        rows = database.execute(
            """
            SELECT tasks.*, projects.name AS project_name
            FROM tasks
            LEFT JOIN projects ON projects.id = tasks.project_id
            WHERE tasks.assignee_id = ?
            ORDER BY tasks.id DESC
            """,
            (assignee_id,),
        )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "projectId": row["project_id"],
            "projectName": row["project_name"] or "",
            "assigneeId": row["assignee_id"],
            "dueDate": row["due_date"] or "",
            "priority": row["priority"],
            "status": row["status"],
        }
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
    existing = None
    if record_id is not None:
        existing = database.execute("SELECT * FROM employees WHERE id = ?", (record_id,)).fetchone()
        if existing is None:
            return None

    if "name" in data or existing is None:
        name = _text(data, "name", "Name", required=True, limit=120)
    else:
        name = existing["name"]

    if "email" in data or existing is None:
        email = _text(data, "email", "Email", required=True, limit=254).lower()
        if not EMAIL_PATTERN.fullmatch(email):
            raise ValueError("Please enter a valid email address.")
    else:
        email = existing["email"]

    if "department" in data or existing is None:
        department = _text(data, "department", "Department", required=True, limit=100)
    else:
        department = existing["department"]

    if "title" in data or existing is None:
        title = _text(data, "title", "Job title", required=True, limit=120)
    else:
        title = existing["title"]

    if "role" in data or existing is None:
        role = _choice(data, "role", ROLES, "EMPLOYEE", "employee role")
    else:
        role = existing["role"]

    if "status" in data or existing is None:
        status = _choice(data, "status", EMPLOYEE_STATUSES, "Active", "employee status")
    else:
        status = existing["status"]

    if "startDate" in data or existing is None:
        start_date = _date(data, "startDate", "Start date")
    else:
        start_date = existing["start_date"]

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
    existing = None
    if record_id is not None:
        existing = database.execute("SELECT * FROM teams WHERE id = ?", (record_id,)).fetchone()
        if existing is None:
            return None

    if "name" in data or existing is None:
        name = _text(data, "name", "Team name", required=True, limit=100)
    else:
        name = existing["name"]

    if "description" in data or existing is None:
        description = _text(data, "description", "Description", limit=1000)
    else:
        description = existing["description"]

    if "managerId" in data or existing is None:
        manager_id = _optional_id(data, "managerId", "Manager")
    else:
        manager_id = existing["manager_id"]
    _validate_reference(database, "employees", manager_id, "Manager")

    if "memberIds" in data or existing is None:
        member_ids = data.get("memberIds", [])
        if not isinstance(member_ids, list):
            raise ValueError("Team members must be a list.")
        try:
            member_ids = sorted(set(int(value) for value in member_ids))
        except (TypeError, ValueError) as error:
            raise ValueError("One or more team members are invalid.") from error
        for employee_id in member_ids:
            _validate_reference(database, "employees", employee_id, "Team member")
    else:
        member_ids = [
            row["employee_id"]
            for row in database.execute(
                "SELECT employee_id FROM team_members WHERE team_id = ?", (record_id,)
            )
        ]

    team_id = _insert_or_update(
        "teams", record_id, ("name", "description", "manager_id"), (name, description, manager_id)
    )
    if team_id is None:
        return None
    if "memberIds" in data or record_id is None:
        database.execute("DELETE FROM team_members WHERE team_id = ?", (team_id,))
        database.executemany(
            "INSERT INTO team_members (team_id, employee_id) VALUES (?, ?)",
            [(team_id, employee_id) for employee_id in member_ids],
        )
        database.commit()
    return team_id


def _save_project(data, record_id=None):
    database = get_db()
    existing = None
    if record_id is not None:
        existing = database.execute("SELECT * FROM projects WHERE id = ?", (record_id,)).fetchone()
        if existing is None:
            return None

    if "name" in data or existing is None:
        name = _text(data, "name", "Project name", required=True, limit=120)
    else:
        name = existing["name"]

    if "description" in data or existing is None:
        description = _text(data, "description", "Description", limit=2000)
    else:
        description = existing["description"]

    if "teamId" in data or existing is None:
        team_id = _optional_id(data, "teamId", "Team")
    else:
        team_id = existing["team_id"]

    if "managerId" in data or existing is None:
        manager_id = _optional_id(data, "managerId", "Project manager")
    else:
        manager_id = existing["manager_id"]

    _validate_reference(database, "teams", team_id, "Team")
    _validate_reference(database, "employees", manager_id, "Project manager")

    if "startDate" in data or existing is None:
        start_date = _date(data, "startDate", "Start date")
    else:
        start_date = existing["start_date"]

    if "dueDate" in data or existing is None:
        due_date = _date(data, "dueDate", "Due date")
    else:
        due_date = existing["due_date"]

    _date_range(start_date, due_date)

    if "status" in data or existing is None:
        status = _choice(data, "status", PROJECT_STATUSES, "In Progress", "project status")
    else:
        status = existing["status"]

    if "progress" in data or existing is None:
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
    else:
        progress = existing["progress"]

    return _insert_or_update(
        "projects",
        record_id,
        ("name", "description", "team_id", "manager_id", "start_date", "due_date", "status", "progress"),
        (name, description, team_id, manager_id, start_date, due_date, status, progress),
    )


def _save_task(data, record_id=None):
    database = get_db()
    name = _text(data, "name", "Task name", required=True, limit=140)
    project_id = _optional_id(data, "projectId", "Project")
    assignee_id = _optional_id(data, "assigneeId", "Assignee")
    _validate_reference(database, "projects", project_id, "Project")
    _validate_reference(database, "employees", assignee_id, "Assignee")
    due_date = _date(data, "dueDate", "Due date")
    priority = _choice(data, "priority", PRIORITIES, "Medium", "task priority")
    status = _choice(data, "status", TASK_STATUSES, "Not Started", "task status")
    return _insert_or_update(
        "tasks",
        record_id,
        ("name", "project_id", "assignee_id", "due_date", "priority", "status"),
        (name, project_id, assignee_id, due_date, priority, status),
    )


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


@management_bp.patch("/teams/<int:record_id>/members")
@roles_required("ADMIN")
def update_team_members(record_id):
    data, error = _required_record(_json_object())
    if error:
        return error
    if "memberIds" not in data or not isinstance(data.get("memberIds"), list):
        return jsonify(error="Team members must be a list."), 400
    try:
        member_ids = sorted(set(int(val) for val in data["memberIds"]))
    except (TypeError, ValueError):
        return jsonify(error="One or more team members are invalid."), 400
    database = get_db()
    if database.execute("SELECT 1 FROM teams WHERE id = ?", (record_id,)).fetchone() is None:
        return _not_found("team")
    for emp_id in member_ids:
        _validate_reference(database, "employees", emp_id, "Team member")
    database.execute("DELETE FROM team_members WHERE team_id = ?", (record_id,))
    database.executemany(
        "INSERT INTO team_members (team_id, employee_id) VALUES (?, ?)",
        [(record_id, emp_id) for emp_id in member_ids],
    )
    database.commit()
    return jsonify(team=next(team for team in _teams() if team["id"] == record_id))


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


@management_bp.patch("/projects/<int:record_id>/progress")
@roles_required("ADMIN")
def update_project_progress(record_id):
    data, error = _required_record(_json_object())
    if error:
        return error
    if "progress" not in data:
        return jsonify(error="Project completion progress is required."), 400
    raw_progress = data.get("progress")
    if isinstance(raw_progress, bool) or (
        isinstance(raw_progress, float) and not raw_progress.is_integer()
    ):
        return jsonify(error="Project completion must be a number between 0 and 100."), 400
    try:
        progress = int(raw_progress)
    except (TypeError, ValueError):
        return jsonify(error="Project completion must be a number between 0 and 100."), 400
    if not 0 <= progress <= 100:
        return jsonify(error="Project completion must be between 0 and 100."), 400
    database = get_db()
    cursor = database.execute("UPDATE projects SET progress = ? WHERE id = ?", (progress, record_id))
    if cursor.rowcount == 0:
        return _not_found("project")
    database.commit()
    return jsonify(project=next(item for item in _projects() if item["id"] == record_id))


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

    database = get_db()
    task_row = database.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if task_row:
        user_id = g.current_user["id"]
        record_activity(database, task_id, user_id, "created", f"Task '{task_row['name']}' created")
        if task_row["status"]:
            record_audit_log(database, task_id, user_id, "status", None, task_row["status"], f"Initial status set to '{task_row['status']}'")
        if task_row["priority"]:
            record_audit_log(database, task_id, user_id, "priority", None, task_row["priority"], f"Initial priority set to '{task_row['priority']}'")
        if task_row["assignee_id"]:
            emp_name = _employee_name(database, task_row["assignee_id"])
            record_audit_log(database, task_id, user_id, "assignment", None, emp_name, f"Initially assigned to {emp_name}")
        database.commit()

    return jsonify(task=next(task for task in _tasks() if task["id"] == task_id)), 201


@management_bp.patch("/tasks/<int:record_id>")
@login_required
def update_task(record_id):
    data, error = _required_record(_json_object())
    if error:
        return error
    database = get_db()
    old_task = database.execute("SELECT * FROM tasks WHERE id = ?", (record_id,)).fetchone()
    if old_task is None:
        return _not_found("task")

    if g.current_user["role"] == "EMPLOYEE":
        if set(data) != {"status"} or not isinstance(data.get("status"), str) or data["status"] not in TASK_STATUSES:
            return jsonify(error="Employees may only update task status."), 403
        employee = database.execute(
            "SELECT id FROM employees WHERE user_id = ?", (g.current_user["id"],)
        ).fetchone()
        if employee is None or old_task["assignee_id"] != employee["id"]:
            return jsonify(error="You can only update tasks assigned to you."), 403
        database.execute("UPDATE tasks SET status = ? WHERE id = ?", (data["status"], record_id))
        database.commit()
        new_task = database.execute("SELECT * FROM tasks WHERE id = ?", (record_id,)).fetchone()
        log_task_modifications(database, record_id, g.current_user["id"], old_task, new_task)
        database.commit()
    elif g.current_user["role"] == "ADMIN":
        try:
            task_id = _save_task(data, record_id)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        if task_id is None:
            return _not_found("task")
        new_task = database.execute("SELECT * FROM tasks WHERE id = ?", (record_id,)).fetchone()
        log_task_modifications(database, record_id, g.current_user["id"], old_task, new_task)
        database.commit()
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
