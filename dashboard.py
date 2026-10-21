
from flask import Blueprint, jsonify
from auth import get_db, login_required

dashboard_bp = Blueprint("dashboard", __name__)


def tasks_table_exists(conn):
    """Check whether Member 2 has created the tasks table."""
    result = conn.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'tasks'
    """).fetchone()

    return result is not None


def get_task_counts(conn):
    """Return total tasks, counts by status, and counts by priority."""
    status_counts = conn.execute("""
        SELECT
            LOWER(status) AS status,
            COUNT(*) AS count
        FROM tasks
        GROUP BY LOWER(status)
    """).fetchall()

    priority_counts = conn.execute("""
        SELECT
            LOWER(priority) AS priority,
            COUNT(*) AS count
        FROM tasks
        GROUP BY LOWER(priority)
    """).fetchall()

    total = conn.execute("""
        SELECT COUNT(*) AS count
        FROM tasks
    """).fetchone()["count"]

    statuses = {
        "pending": 0,
        "in_progress": 0,
        "completed": 0
    }

    for row in status_counts:
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

    for row in priority_counts:
        priority = row["priority"]

        if priority in priorities:
            priorities[priority] = row["count"]

    return {
        "total_tasks": total,
        **statuses,
        "priority": priorities
    }


def dashboard_response():
    """Get the shared task counts or a temporary response if no table exists."""
    with get_db() as conn:
        if not tasks_table_exists(conn):
            return {
                "message": (
                    "Dashboard API is ready. "
                    "Waiting for Member 2 to create the tasks table."
                ),
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

        result = get_task_counts(conn)
        result["data_ready"] = True
        return result


@dashboard_bp.route(
    "/api/dashboard/summary",
    methods=["GET"]
)
@login_required
def dashboard_summary():
    return jsonify(dashboard_response()), 200


@dashboard_bp.route(
    "/api/dashboard/tasks-by-status",
    methods=["GET"]
)
@login_required
def tasks_by_status():
    data = dashboard_response()

    return jsonify({
        "data_ready": data["data_ready"],
        "tasks_by_status": {
            "pending": data["pending"],
            "in_progress": data["in_progress"],
            "completed": data["completed"]
        }
    }), 200


@dashboard_bp.route(
    "/api/dashboard/tasks-by-priority",
    methods=["GET"]
)
@login_required
def tasks_by_priority():
    data = dashboard_response()

    return jsonify({
        "data_ready": data["data_ready"],
        "tasks_by_priority": data["priority"]
    }), 200
