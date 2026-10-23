"""Activity history, audit logs, and task comments/discussion API.

Member 3: Database, Activity History and Audit Logs
- Task activity history tracking
- Audit logs for assignment, status, and priority changes
- Task comments and discussion API
"""

from datetime import datetime, timezone
from flask import Blueprint, g, jsonify, request
from auth import get_db, login_required, roles_required


audit_bp = Blueprint("audit", __name__, url_prefix="/api")

VALID_AUDIT_TYPES = {"assignment", "status", "priority"}


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _get_task(conn, task_id):
    return conn.execute(
        "SELECT * FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()


def _get_employee_for_user(conn, user_id):
    if user_id is None:
        return None
    return conn.execute(
        "SELECT * FROM employees WHERE user_id = ?", (user_id,)
    ).fetchone()


def _employee_name(conn, employee_id):
    if employee_id is None:
        return "Unassigned"
    row = conn.execute(
        "SELECT name FROM employees WHERE id = ?", (employee_id,)
    ).fetchone()
    return row["name"] if row else f"Employee #{employee_id}"


def can_access_task(conn, task, user):
    """Determine whether the current user has access to a given task."""
    if task is None or user is None:
        return False

    role = (user["role"] or "").upper()
    if role in ("ADMIN", "MANAGER"):
        return True

    if role == "EMPLOYEE":
        employee = _get_employee_for_user(conn, user["id"])
        if employee and task["assignee_id"] == employee["id"]:
            return True
        # Check created_by if column exists on task
        if "created_by" in task.keys() and task["created_by"] == user["id"]:
            return True

    return False


def record_activity(conn, task_id, user_id, action, details=""):
    """Record a general activity entry for a task."""
    conn.execute(
        """
        INSERT INTO task_activities (task_id, user_id, action, details, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (task_id, user_id, action, details or "", _utc_now()),
    )


def record_audit_log(conn, task_id, user_id, change_type, old_value, new_value, details=""):
    """Record an audit log specifically for assignment, status, or priority changes."""
    if change_type not in VALID_AUDIT_TYPES:
        raise ValueError(f"Invalid change_type '{change_type}'. Must be one of {VALID_AUDIT_TYPES}")

    conn.execute(
        """
        INSERT INTO audit_logs (task_id, user_id, change_type, old_value, new_value, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            user_id,
            change_type,
            str(old_value) if old_value is not None else None,
            str(new_value) if new_value is not None else None,
            details or "",
            _utc_now(),
        ),
    )


def log_task_modifications(conn, task_id, actor_user_id, old_task, new_task):
    """Inspect differences between old and new task records and record audit & activity logs."""
    if old_task is None or new_task is None:
        return

    # 1. Status changes
    old_status = old_task["status"]
    new_status = new_task["status"]
    if old_status != new_status:
        record_audit_log(
            conn,
            task_id,
            actor_user_id,
            "status",
            old_status,
            new_status,
            f"Status changed from '{old_status}' to '{new_status}'",
        )
        record_activity(
            conn,
            task_id,
            actor_user_id,
            "status_changed",
            f"Status updated to '{new_status}'",
        )

    # 2. Priority changes
    old_priority = old_task["priority"]
    new_priority = new_task["priority"]
    if old_priority != new_priority:
        record_audit_log(
            conn,
            task_id,
            actor_user_id,
            "priority",
            old_priority,
            new_priority,
            f"Priority changed from '{old_priority}' to '{new_priority}'",
        )
        record_activity(
            conn,
            task_id,
            actor_user_id,
            "priority_changed",
            f"Priority updated to '{new_priority}'",
        )

    # 3. Assignment changes
    old_assignee_id = old_task["assignee_id"]
    new_assignee_id = new_task["assignee_id"]
    if old_assignee_id != new_assignee_id:
        old_name = _employee_name(conn, old_assignee_id)
        new_name = _employee_name(conn, new_assignee_id)
        record_audit_log(
            conn,
            task_id,
            actor_user_id,
            "assignment",
            old_name,
            new_name,
            f"Assignee changed from {old_name} to {new_name}",
        )
        record_activity(
            conn,
            task_id,
            actor_user_id,
            "assigned",
            f"Task assigned to {new_name}",
        )

    # 4. Other task field changes (e.g., name or due date)
    old_name = old_task["name"]
    new_name = new_task["name"]
    if old_name != new_name:
        record_activity(
            conn,
            task_id,
            actor_user_id,
            "renamed",
            f"Task renamed to '{new_name}'",
        )

    old_due = old_task["due_date"]
    new_due = new_task["due_date"]
    if old_due != new_due:
        record_activity(
            conn,
            task_id,
            actor_user_id,
            "due_date_changed",
            f"Due date changed to {new_due or 'Not set'}",
        )


# --- API Routes: Task Activity History ---

@audit_bp.get("/tasks/<int:task_id>/history")
@audit_bp.get("/tasks/<int:task_id>/activities")
@login_required
def get_task_history(task_id):
    """Retrieve the full activity history for a task."""
    conn = get_db()
    task = _get_task(conn, task_id)
    if task is None:
        return jsonify(error="Task not found."), 404

    if not can_access_task(conn, task, g.current_user):
        return jsonify(error="You do not have permission to view this task's history."), 403

    rows = conn.execute(
        """
        SELECT a.id, a.task_id, a.user_id, a.action, a.details, a.created_at,
               u.name AS user_name, u.email AS user_email, u.role AS user_role
        FROM task_activities a
        LEFT JOIN users u ON a.user_id = u.id
        WHERE a.task_id = ?
        ORDER BY a.created_at DESC, a.id DESC
        """,
        (task_id,),
    ).fetchall()

    activities = [
        {
            "id": row["id"],
            "taskId": row["task_id"],
            "userId": row["user_id"],
            "userName": row["user_name"] or "System",
            "userEmail": row["user_email"] or "",
            "userRole": row["user_role"] or "",
            "action": row["action"],
            "details": row["details"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]

    return jsonify(taskId=task_id, activities=activities)


# --- API Routes: Audit Logs ---

@audit_bp.get("/tasks/<int:task_id>/audit-logs")
@login_required
def get_task_audit_logs(task_id):
    """Retrieve audit logs (assignment, status, priority) for a specific task."""
    conn = get_db()
    task = _get_task(conn, task_id)
    if task is None:
        return jsonify(error="Task not found."), 404

    if not can_access_task(conn, task, g.current_user):
        return jsonify(error="You do not have permission to view audit logs for this task."), 403

    change_type = request.args.get("change_type") or request.args.get("changeType")
    params = [task_id]
    query = """
        SELECT l.id, l.task_id, l.user_id, l.change_type, l.old_value, l.new_value,
               l.details, l.created_at,
               u.name AS user_name, u.email AS user_email, u.role AS user_role
        FROM audit_logs l
        LEFT JOIN users u ON l.user_id = u.id
        WHERE l.task_id = ?
    """

    if change_type:
        if change_type not in VALID_AUDIT_TYPES:
            return jsonify(error=f"Invalid change_type filter. Must be one of {sorted(VALID_AUDIT_TYPES)}"), 400
        query += " AND l.change_type = ?"
        params.append(change_type)

    query += " ORDER BY l.created_at DESC, l.id DESC"
    rows = conn.execute(query, params).fetchall()

    logs = [
        {
            "id": row["id"],
            "taskId": row["task_id"],
            "userId": row["user_id"],
            "userName": row["user_name"] or "System",
            "userEmail": row["user_email"] or "",
            "userRole": row["user_role"] or "",
            "changeType": row["change_type"],
            "oldValue": row["old_value"],
            "newValue": row["new_value"],
            "details": row["details"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]

    return jsonify(taskId=task_id, auditLogs=logs)


@audit_bp.get("/audit-logs")
@login_required
def get_all_audit_logs():
    """List audit logs across tasks with filtering and pagination."""
    conn = get_db()
    role = (g.current_user["role"] or "").upper()

    change_type = request.args.get("change_type") or request.args.get("changeType")
    task_id = request.args.get("task_id") or request.args.get("taskId")

    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (TypeError, ValueError):
        return jsonify(error="limit and offset must be valid integers."), 400

    filters = []
    params = []

    if role == "EMPLOYEE":
        employee = _get_employee_for_user(conn, g.current_user["id"])
        employee_id = employee["id"] if employee else -1
        filters.append(
            "(t.assignee_id = ? OR (t.assignee_id IS NULL AND t.id IN (SELECT id FROM tasks WHERE created_by = ?)))"
            if "created_by" in [c[1] for c in conn.execute("PRAGMA table_info(tasks)").fetchall()]
            else "t.assignee_id = ?"
        )
        if "created_by" in [c[1] for c in conn.execute("PRAGMA table_info(tasks)").fetchall()]:
            params.extend([employee_id, g.current_user["id"]])
        else:
            params.append(employee_id)

    if task_id:
        try:
            filters.append("l.task_id = ?")
            params.append(int(task_id))
        except (TypeError, ValueError):
            return jsonify(error="task_id must be a valid integer."), 400

    if change_type:
        if change_type not in VALID_AUDIT_TYPES:
            return jsonify(error=f"Invalid change_type filter. Must be one of {sorted(VALID_AUDIT_TYPES)}"), 400
        filters.append("l.change_type = ?")
        params.append(change_type)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    count_query = f"""
        SELECT COUNT(*) AS total
        FROM audit_logs l
        JOIN tasks t ON l.task_id = t.id
        {where_clause}
    """
    total = conn.execute(count_query, params).fetchone()["total"]

    data_query = f"""
        SELECT l.id, l.task_id, l.user_id, l.change_type, l.old_value, l.new_value,
               l.details, l.created_at,
               t.name AS task_name,
               u.name AS user_name, u.email AS user_email, u.role AS user_role
        FROM audit_logs l
        JOIN tasks t ON l.task_id = t.id
        LEFT JOIN users u ON l.user_id = u.id
        {where_clause}
        ORDER BY l.created_at DESC, l.id DESC
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(data_query, [*params, limit, offset]).fetchall()

    logs = [
        {
            "id": row["id"],
            "taskId": row["task_id"],
            "taskName": row["task_name"],
            "userId": row["user_id"],
            "userName": row["user_name"] or "System",
            "userEmail": row["user_email"] or "",
            "userRole": row["user_role"] or "",
            "changeType": row["change_type"],
            "oldValue": row["old_value"],
            "newValue": row["new_value"],
            "details": row["details"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]

    return jsonify(auditLogs=logs, total=total, limit=limit, offset=offset)


# --- API Routes: Task Comments and Discussion ---

@audit_bp.get("/tasks/<int:task_id>/comments")
@login_required
def get_task_comments(task_id):
    """Retrieve comments/discussion for a specific task in chronological order."""
    conn = get_db()
    task = _get_task(conn, task_id)
    if task is None:
        return jsonify(error="Task not found."), 404

    if not can_access_task(conn, task, g.current_user):
        return jsonify(error="You do not have permission to view comments on this task."), 403

    rows = conn.execute(
        """
        SELECT c.id, c.task_id, c.user_id, c.content, c.created_at, c.updated_at,
               u.name AS user_name, u.email AS user_email, u.role AS user_role
        FROM task_comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.task_id = ?
        ORDER BY c.created_at ASC, c.id ASC
        """,
        (task_id,),
    ).fetchall()

    comments = [
        {
            "id": row["id"],
            "taskId": row["task_id"],
            "userId": row["user_id"],
            "userName": row["user_name"],
            "userEmail": row["user_email"],
            "userRole": row["user_role"],
            "content": row["content"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]

    return jsonify(taskId=task_id, comments=comments)


@audit_bp.post("/tasks/<int:task_id>/comments")
@login_required
def add_task_comment(task_id):
    """Add a new comment/discussion message to a task."""
    conn = get_db()
    task = _get_task(conn, task_id)
    if task is None:
        return jsonify(error="Task not found."), 404

    if not can_access_task(conn, task, g.current_user):
        return jsonify(error="You do not have permission to comment on this task."), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Expected a JSON object request body."), 400

    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        return jsonify(error="Comment content is required and cannot be empty."), 400

    clean_content = content.strip()
    if len(clean_content) > 2000:
        return jsonify(error="Comment cannot exceed 2000 characters."), 400

    now = _utc_now()
    cursor = conn.execute(
        """
        INSERT INTO task_comments (task_id, user_id, content, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (task_id, g.current_user["id"], clean_content, now),
    )
    comment_id = cursor.lastrowid

    # Record in activity history
    preview = clean_content[:60] + ("…" if len(clean_content) > 60 else "")
    record_activity(
        conn,
        task_id,
        g.current_user["id"],
        "comment_added",
        f"Added comment: \"{preview}\"",
    )
    conn.commit()

    created_comment = {
        "id": comment_id,
        "taskId": task_id,
        "userId": g.current_user["id"],
        "userName": g.current_user["name"],
        "userEmail": g.current_user["email"],
        "userRole": g.current_user["role"],
        "content": clean_content,
        "createdAt": now,
        "updatedAt": None,
    }

    return jsonify(comment=created_comment), 201


@audit_bp.patch("/tasks/<int:task_id>/comments/<int:comment_id>")
@login_required
def update_task_comment(task_id, comment_id):
    """Update an existing comment. Allowed for comment author or ADMIN."""
    conn = get_db()
    task = _get_task(conn, task_id)
    if task is None:
        return jsonify(error="Task not found."), 404

    if not can_access_task(conn, task, g.current_user):
        return jsonify(error="You do not have permission to access this task."), 403

    comment = conn.execute(
        "SELECT * FROM task_comments WHERE id = ? AND task_id = ?",
        (comment_id, task_id),
    ).fetchone()
    if comment is None:
        return jsonify(error="Comment not found."), 404

    # Permission check: author or ADMIN
    is_author = comment["user_id"] == g.current_user["id"]
    is_admin = g.current_user["role"] == "ADMIN"
    if not (is_author or is_admin):
        return jsonify(error="You can only edit your own comments."), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Expected a JSON object request body."), 400

    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        return jsonify(error="Comment content is required and cannot be empty."), 400

    clean_content = content.strip()
    if len(clean_content) > 2000:
        return jsonify(error="Comment cannot exceed 2000 characters."), 400

    now = _utc_now()
    conn.execute(
        """
        UPDATE task_comments
        SET content = ?, updated_at = ?
        WHERE id = ?
        """,
        (clean_content, now, comment_id),
    )
    record_activity(
        conn,
        task_id,
        g.current_user["id"],
        "comment_updated",
        "Edited a comment",
    )
    conn.commit()

    updated = conn.execute(
        """
        SELECT c.id, c.task_id, c.user_id, c.content, c.created_at, c.updated_at,
               u.name AS user_name, u.email AS user_email, u.role AS user_role
        FROM task_comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.id = ?
        """,
        (comment_id,),
    ).fetchone()

    return jsonify(
        comment={
            "id": updated["id"],
            "taskId": updated["task_id"],
            "userId": updated["user_id"],
            "userName": updated["user_name"],
            "userEmail": updated["user_email"],
            "userRole": updated["user_role"],
            "content": updated["content"],
            "createdAt": updated["created_at"],
            "updatedAt": updated["updated_at"],
        }
    )


@audit_bp.delete("/tasks/<int:task_id>/comments/<int:comment_id>")
@login_required
def delete_task_comment(task_id, comment_id):
    """Delete a comment. Allowed for comment author or ADMIN."""
    conn = get_db()
    task = _get_task(conn, task_id)
    if task is None:
        return jsonify(error="Task not found."), 404

    if not can_access_task(conn, task, g.current_user):
        return jsonify(error="You do not have permission to access this task."), 403

    comment = conn.execute(
        "SELECT * FROM task_comments WHERE id = ? AND task_id = ?",
        (comment_id, task_id),
    ).fetchone()
    if comment is None:
        return jsonify(error="Comment not found."), 404

    is_author = comment["user_id"] == g.current_user["id"]
    is_admin = g.current_user["role"] == "ADMIN"
    if not (is_author or is_admin):
        return jsonify(error="You can only delete your own comments."), 403

    conn.execute("DELETE FROM task_comments WHERE id = ?", (comment_id,))
    record_activity(
        conn,
        task_id,
        g.current_user["id"],
        "comment_deleted",
        "Deleted a comment",
    )
    conn.commit()

    return jsonify(message="Comment deleted successfully.")
