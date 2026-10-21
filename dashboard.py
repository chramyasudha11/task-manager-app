
from flask import Blueprint, jsonify, session
from auth import get_db, login_required

dashboard_bp = Blueprint("dashboard", __name__)


def get_task_counts(conn, user_id, role):
    """
    Return dashboard counts for the authenticated user's role.

    ADMIN: all tasks.
    MANAGER: tasks created by that manager.
    EMPLOYEE: tasks assigned to that employee.
    """
    role = role.upper()

    if role == "ADMIN":
        where_clause = ""
        params = ()
    elif role == "MANAGER":
        where_clause = "WHERE created_by = ?"
        params = (user_id,)
    elif role == "EMPLOYEE":
        where_clause = "WHERE assigned_to = ?"
        params = (user_id,)
    else:
        raise ValueError("Unsupported user role")

    # Check whether Member 2's tasks table exists.
    table = conn.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'tasks'
    """).fetchone()

    if table is None:
        return {
            "message": "The tasks table is not available yet.",
            "total_tasks": 0,
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "priority": {
                "low": 0,
                "medium": 0,
                "high": 0
            },
            "data_ready": False
        }

    total = conn.execute(
        f"SELECT COUNT(*) AS count FROM tasks {where_clause}",
        params
    ).fetchone()["count"]

    status_rows = conn.execute(
        f"""
        SELECT LOWER(status) AS status, COUNT(*) AS count
        FROM tasks
        {where_clause}
        GROUP BY LOWER(status)
        """,
        params
    ).fetchall()

    priority_rows = conn.execute(
        f"""
        SELECT LOWER(priority) AS priority, COUNT(*) AS count
        FROM tasks
        {where_clause}
        GROUP BY LOWER(priority)
        """,
        params
    ).fetchall()

    statuses = {
        "pending": 0,
        "in_progress": 0,
        "completed": 0
    }

    for row in status_rows:
        status = row["status"]

        if status == "pending":
            statuses["pending"] = row["count"]
        elif status in ("in progress", "in_progress"):
            statuses["in_progress"] = row["count"]
        elif status == "completed":
            statuses["completed"] = row["count"]

    priorities = {
        "low": 0,
        "medium": 0,
        "high": 0
    }

    for row in priority_rows:
        priority = row["priority"]

        if priority in priorities:
            priorities[priority] = row["count"]

    return {
        "total_tasks": total,
        **statuses,
        "priority": priorities,
        "data_ready": True
    }


def dashboard_response():
    """Build dashboard counts for the logged-in user."""
    user_id = session.get("user_id")

    if user_id is None:
        return {"error": "Please login first"}, 401

    with get_db() as conn:
        user = conn.execute(
            "SELECT id, role FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

        if user is None:
            session.clear()
            return {"error": "User not found. Please login again."}, 401

        role = user["role"]

        if role not in ("ADMIN", "MANAGER", "EMPLOYEE"):
            return {"error": "Unsupported user role"}, 403

        try:
            return get_task_counts(conn, user["id"], role), 200
        except ValueError:
            return {"error": "Unsupported user role"}, 403


@dashboard_bp.route("/api/dashboard/summary", methods=["GET"])
@login_required
def dashboard_summary():
    data, status_code = dashboard_response()
    return jsonify(data), status_code


@dashboard_bp.route("/api/dashboard/tasks-by-status", methods=["GET"])
@login_required
def tasks_by_status():
    data, status_code = dashboard_response()

    if status_code != 200:
        return jsonify(data), status_code

    return jsonify({
        "data_ready": data["data_ready"],
        "tasks_by_status": {
            "pending": data["pending"],
            "in_progress": data["in_progress"],
            "completed": data["completed"]
        }
    }), 200


@dashboard_bp.route("/api/dashboard/tasks-by-priority", methods=["GET"])
@login_required
def tasks_by_priority():
    data, status_code = dashboard_response()

    if status_code != 200:
        return jsonify(data), status_code

    return jsonify({
        "data_ready": data["data_ready"],
        "tasks_by_priority": data["priority"]
    }), 200
