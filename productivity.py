"""Member 7 – Employee Productivity and Notifications

Provides:
- GET  /api/productivity/summary          – personal productivity summary
- GET  /api/productivity/week             – My Week view (tasks due this ISO week)
- GET  /api/productivity/calendar         – personal task calendar (tasks with due dates)
- GET  /api/notifications                 – in-app notification list for the current employee
- POST /api/notifications/<id>/read       – mark one notification as read
- POST /api/notifications/read-all        – mark all notifications as read
- GET  /api/saved-filters                 – list saved filters for the current employee
- POST /api/saved-filters                 – save a new filter
- DELETE /api/saved-filters/<id>          – delete a saved filter

All routes require an authenticated session (login_required from auth.py).
Notification seeding: approaching-deadline and assignment notifications are
generated lazily when the employee calls GET /api/notifications so the feature
works without a background scheduler.
"""

import sqlite3
from contextlib import closing
from datetime import date, timedelta

from flask import Blueprint, g, jsonify, request

from auth import get_db, login_required

productivity_bp = Blueprint("productivity", __name__, url_prefix="/api")

# Days before a due date that trigger an approaching-deadline notification.
DEADLINE_WARNING_DAYS = 3

# Maximum characters for a saved-filter name.
FILTER_NAME_LIMIT = 100


# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------

def init_productivity_db(app):
    """Create notifications and saved_filters tables if they do not exist."""
    db_path = app.config["DATABASE_PATH"]
    with closing(sqlite3.connect(db_path, timeout=10)) as database:
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL
                    REFERENCES employees(id) ON DELETE CASCADE,
                kind       TEXT NOT NULL
                    CHECK (kind IN ('assignment', 'deadline')),
                task_id    INTEGER
                    REFERENCES tasks(id) ON DELETE CASCADE,
                message    TEXT NOT NULL,
                is_read    INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_notifications_employee
                ON notifications(employee_id);
            CREATE INDEX IF NOT EXISTS idx_notifications_task
                ON notifications(task_id);

            CREATE TABLE IF NOT EXISTS saved_filters (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL
                    REFERENCES employees(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                filter_json TEXT NOT NULL DEFAULT '{}',
                created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_saved_filters_employee
                ON saved_filters(employee_id);
            """
        )
        database.commit()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _current_employee(database):
    """Return the employees row for the logged-in user, or None."""
    return database.execute(
        "SELECT id FROM employees WHERE user_id = ?",
        (g.current_user["id"],),
    ).fetchone()


def _require_employee(database):
    """Return (employee_row, None) or (None, error_response)."""
    emp = _current_employee(database)
    if emp is None:
        return None, (
            jsonify(error="No employee record is linked to your account."),
            404,
        )
    return emp, None


def _not_found(entity):
    return jsonify(error=f"{entity.capitalize()} not found."), 404


def _tasks_for_employee(database, employee_id):
    """Return all management tasks assigned to employee_id."""
    return database.execute(
        """
        SELECT tasks.id, tasks.name, tasks.status, tasks.priority,
               tasks.due_date, tasks.created_at,
               projects.name AS project_name
        FROM   tasks
        LEFT JOIN projects ON projects.id = tasks.project_id
        WHERE  tasks.assignee_id = ?
        ORDER  BY tasks.due_date ASC NULLS LAST, tasks.id DESC
        """,
        (employee_id,),
    ).fetchall()


def _public_task(row):
    return {
        "id":          row["id"],
        "name":        row["name"],
        "status":      row["status"],
        "priority":    row["priority"],
        "dueDate":     row["due_date"] or "",
        "projectName": row["project_name"] or "",
        "createdAt":   row["created_at"] or "",
    }


def _seed_notifications(database, employee_id):
    """
    Lazily generate notifications that do not yet exist:
      - 'assignment': one per task assigned to this employee (if not already noted)
      - 'deadline'  : one per task whose due_date is within DEADLINE_WARNING_DAYS
                      and is not yet Completed (if not already noted)
    """
    today = date.today()
    warning_date = (today + timedelta(days=DEADLINE_WARNING_DAYS)).isoformat()

    tasks = database.execute(
        """
        SELECT id, name, due_date, status
        FROM   tasks
        WHERE  assignee_id = ?
        """,
        (employee_id,),
    ).fetchall()

    for task in tasks:
        task_id = task["id"]

        # Assignment notification
        exists = database.execute(
            """
            SELECT 1 FROM notifications
            WHERE employee_id = ? AND kind = 'assignment' AND task_id = ?
            """,
            (employee_id, task_id),
        ).fetchone()
        if not exists:
            database.execute(
                """
                INSERT INTO notifications (employee_id, kind, task_id, message)
                VALUES (?, 'assignment', ?, ?)
                """,
                (
                    employee_id,
                    task_id,
                    f"You have been assigned the task \"{task['name']}\".",
                ),
            )

        # Deadline notification (only for upcoming / in-progress tasks)
        due = task["due_date"]
        status = task["status"]
        if due and due <= warning_date and status != "Completed":
            due_date_obj = date.fromisoformat(due)
            days_left = (due_date_obj - today).days
            if days_left < 0:
                msg = f"Task \"{task['name']}\" was due {abs(days_left)} day(s) ago."
            elif days_left == 0:
                msg = f"Task \"{task['name']}\" is due today."
            else:
                msg = (
                    f"Task \"{task['name']}\" is due in {days_left} day(s) "
                    f"({due})."
                )

            exists = database.execute(
                """
                SELECT 1 FROM notifications
                WHERE employee_id = ? AND kind = 'deadline' AND task_id = ?
                """,
                (employee_id, task_id),
            ).fetchone()
            if not exists:
                database.execute(
                    """
                    INSERT INTO notifications
                        (employee_id, kind, task_id, message)
                    VALUES (?, 'deadline', ?, ?)
                    """,
                    (employee_id, task_id, msg),
                )

    database.commit()


# ---------------------------------------------------------------------------
# Productivity summary
# ---------------------------------------------------------------------------

@productivity_bp.get("/productivity/summary")
@login_required
def productivity_summary():
    """
    Personal productivity summary for the logged-in employee.

    Returns:
        totalTasks, completed, inProgress, notStarted, overdueTasks,
        completionRate (%), upcomingDeadlines (next 7 days)
    """
    database = get_db()
    employee, error = _require_employee(database)
    if error:
        return error

    employee_id = employee["id"]
    today = date.today().isoformat()
    week_ahead = (date.today() + timedelta(days=7)).isoformat()

    tasks = _tasks_for_employee(database, employee_id)

    total = len(tasks)
    completed = sum(1 for t in tasks if t["status"] == "Completed")
    in_progress = sum(1 for t in tasks if t["status"] == "In Progress")
    not_started = sum(1 for t in tasks if t["status"] == "Not Started")
    overdue = sum(
        1 for t in tasks
        if t["due_date"] and t["due_date"] < today and t["status"] != "Completed"
    )
    upcoming = sum(
        1 for t in tasks
        if t["due_date"] and today <= t["due_date"] <= week_ahead
        and t["status"] != "Completed"
    )
    completion_rate = round((completed / total) * 100) if total else 0

    priority_counts = {"High": 0, "Medium": 0, "Low": 0}
    for t in tasks:
        p = t["priority"]
        if p in priority_counts:
            priority_counts[p] += 1

    return jsonify(
        totalTasks=total,
        completed=completed,
        inProgress=in_progress,
        notStarted=not_started,
        overdueTasks=overdue,
        upcomingDeadlines=upcoming,
        completionRate=completion_rate,
        priorityCounts=priority_counts,
    )


# ---------------------------------------------------------------------------
# My Week view
# ---------------------------------------------------------------------------

@productivity_bp.get("/productivity/week")
@login_required
def my_week():
    """
    Tasks assigned to the current employee that are due within the current
    ISO week (Monday – Sunday).  Tasks with no due date are excluded.
    """
    database = get_db()
    employee, error = _require_employee(database)
    if error:
        return error

    today = date.today()
    # Monday of the current ISO week
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    tasks = _tasks_for_employee(database, employee["id"])

    week_tasks = [
        _public_task(t)
        for t in tasks
        if t["due_date"]
        and week_start.isoformat() <= t["due_date"] <= week_end.isoformat()
    ]

    return jsonify(
        weekStart=week_start.isoformat(),
        weekEnd=week_end.isoformat(),
        tasks=week_tasks,
    )


# ---------------------------------------------------------------------------
# Personal task calendar
# ---------------------------------------------------------------------------

@productivity_bp.get("/productivity/calendar")
@login_required
def task_calendar():
    """
    All tasks assigned to the current employee that have a due date,
    grouped by date (YYYY-MM-DD) so the frontend can render a calendar.

    Optional query params:
      ?year=YYYY&month=MM   – filter to a specific calendar month
    """
    database = get_db()
    employee, error = _require_employee(database)
    if error:
        return error

    tasks = _tasks_for_employee(database, employee["id"])

    # Optional month filter
    year_param = request.args.get("year")
    month_param = request.args.get("month")
    try:
        filter_year = int(year_param) if year_param else None
        filter_month = int(month_param) if month_param else None
    except ValueError:
        return jsonify(error="year and month must be integers."), 400

    if filter_month is not None and not 1 <= filter_month <= 12:
        return jsonify(error="month must be between 1 and 12."), 400

    by_date: dict[str, list] = {}
    for t in tasks:
        due = t["due_date"]
        if not due:
            continue
        try:
            d = date.fromisoformat(due)
        except ValueError:
            continue
        if filter_year and d.year != filter_year:
            continue
        if filter_month and d.month != filter_month:
            continue
        by_date.setdefault(due, []).append(_public_task(t))

    # Return sorted list of {date, tasks}
    calendar_entries = [
        {"date": day, "tasks": day_tasks}
        for day, day_tasks in sorted(by_date.items())
    ]
    return jsonify(calendar=calendar_entries)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@productivity_bp.get("/notifications")
@login_required
def list_notifications():
    """Return in-app notifications for the current employee, newest first."""
    database = get_db()
    employee, error = _require_employee(database)
    if error:
        return error

    employee_id = employee["id"]
    _seed_notifications(database, employee_id)

    rows = database.execute(
        """
        SELECT id, kind, task_id, message, is_read, created_at
        FROM   notifications
        WHERE  employee_id = ?
        ORDER  BY created_at DESC, id DESC
        """,
        (employee_id,),
    ).fetchall()

    unread_count = sum(1 for r in rows if not r["is_read"])

    return jsonify(
        notifications=[
            {
                "id":        r["id"],
                "kind":      r["kind"],
                "taskId":    r["task_id"],
                "message":   r["message"],
                "isRead":    bool(r["is_read"]),
                "createdAt": r["created_at"],
            }
            for r in rows
        ],
        unreadCount=unread_count,
    )


@productivity_bp.post("/notifications/<int:notification_id>/read")
@login_required
def mark_notification_read(notification_id):
    """Mark a single notification as read (employee must own it)."""
    database = get_db()
    employee, error = _require_employee(database)
    if error:
        return error

    cursor = database.execute(
        """
        UPDATE notifications
        SET    is_read = 1
        WHERE  id = ? AND employee_id = ?
        """,
        (notification_id, employee["id"]),
    )
    if cursor.rowcount == 0:
        return _not_found("notification")

    database.commit()
    return jsonify(message="Notification marked as read.")


@productivity_bp.post("/notifications/read-all")
@login_required
def mark_all_notifications_read():
    """Mark every notification for the current employee as read."""
    database = get_db()
    employee, error = _require_employee(database)
    if error:
        return error

    database.execute(
        "UPDATE notifications SET is_read = 1 WHERE employee_id = ?",
        (employee["id"],),
    )
    database.commit()
    return jsonify(message="All notifications marked as read.")


# ---------------------------------------------------------------------------
# Saved filters
# ---------------------------------------------------------------------------

@productivity_bp.get("/saved-filters")
@login_required
def list_saved_filters():
    """List saved task filters for the current employee."""
    database = get_db()
    employee, error = _require_employee(database)
    if error:
        return error

    rows = database.execute(
        """
        SELECT id, name, filter_json, created_at
        FROM   saved_filters
        WHERE  employee_id = ?
        ORDER  BY created_at DESC, id DESC
        """,
        (employee["id"],),
    ).fetchall()

    import json as _json
    return jsonify(
        savedFilters=[
            {
                "id":         r["id"],
                "name":       r["name"],
                "filter":     _json.loads(r["filter_json"]),
                "createdAt":  r["created_at"],
            }
            for r in rows
        ]
    )


@productivity_bp.post("/saved-filters")
@login_required
def create_saved_filter():
    """
    Save a task filter.

    Body JSON: { "name": "...", "filter": { "status": "...", "priority": "...", ... } }
    """
    import json as _json

    database = get_db()
    employee, error = _require_employee(database)
    if error:
        return error

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Request body must be a JSON object."), 400

    name = data.get("name", "")
    if not isinstance(name, str) or not name.strip():
        return jsonify(error="Filter name is required."), 400
    name = name.strip()
    if len(name) > FILTER_NAME_LIMIT:
        return jsonify(
            error=f"Filter name must be {FILTER_NAME_LIMIT} characters or fewer."
        ), 400

    filter_obj = data.get("filter", {})
    if not isinstance(filter_obj, dict):
        return jsonify(error="filter must be a JSON object."), 400

    # Validate allowed filter keys
    allowed_filter_keys = {"status", "priority", "search", "project"}
    unknown = set(filter_obj) - allowed_filter_keys
    if unknown:
        return jsonify(
            error=f"Unknown filter key(s): {', '.join(sorted(unknown))}."
        ), 400

    filter_json = _json.dumps(filter_obj)

    cursor = database.execute(
        """
        INSERT INTO saved_filters (employee_id, name, filter_json)
        VALUES (?, ?, ?)
        """,
        (employee["id"], name, filter_json),
    )
    database.commit()

    row = database.execute(
        "SELECT id, name, filter_json, created_at FROM saved_filters WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()

    return jsonify(
        savedFilter={
            "id":        row["id"],
            "name":      row["name"],
            "filter":    _json.loads(row["filter_json"]),
            "createdAt": row["created_at"],
        }
    ), 201


@productivity_bp.delete("/saved-filters/<int:filter_id>")
@login_required
def delete_saved_filter(filter_id):
    """Delete a saved filter owned by the current employee."""
    database = get_db()
    employee, error = _require_employee(database)
    if error:
        return error

    cursor = database.execute(
        "DELETE FROM saved_filters WHERE id = ? AND employee_id = ?",
        (filter_id, employee["id"]),
    )
    if cursor.rowcount == 0:
        return _not_found("saved filter")

    database.commit()
    return jsonify(message="Saved filter deleted.")
