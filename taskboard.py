"""Member 5 backend helpers for the task UI (no changes to Member 2's tasks.py).

* GET   /api/task-board            tasks + assignee name + project name (one call)
* PATCH /api/task-board/<id>/project   link/unlink a task to a project
* GET   /api/overview              numbers for the Admin / Manager / Employee dashboards
Task <-> project links live in the `task_projects` table created by Member 4.
"""
from datetime import date
from flask import Blueprint, jsonify, request

from auth import login_required, roles_required
from org_common import body, db, error, me
from projects import can_see, progress

taskboard_bp = Blueprint("taskboard", __name__)

BOARD_SQL = """
SELECT t.id, t.title, t.description, t.status, t.priority, t.category, t.due_date,
       t.created_by, t.assigned_to, t.created_at, t.updated_at,
       u.name AS assignee_name, c.name AS created_by_name,
       p.id AS project_id, p.name AS project_name
FROM tasks t
LEFT JOIN users u ON u.id = t.assigned_to
LEFT JOIN users c ON c.id = t.created_by
LEFT JOIN task_projects tp ON tp.task_id = t.id
LEFT JOIN projects p ON p.id = tp.project_id
"""


def _row(r, today):
    d = dict(r)
    d["is_overdue"] = bool(d["due_date"] and d["due_date"] < today and d["status"] != "completed")
    return d


@taskboard_bp.route("/api/task-board", methods=["GET"])
@login_required
def board():
    today = date.today().isoformat()
    filters, params = [], []
    for arg, column in (("status", "t.status"), ("priority", "t.priority")):
        if request.args.get(arg):
            filters.append(f"{column} = ?")
            params.append(request.args[arg])
    if request.args.get("project_id", "").isdigit():
        filters.append("p.id = ?")
        params.append(int(request.args["project_id"]))
    if request.args.get("search"):
        filters.append("(t.title LIKE ? OR t.description LIKE ?)")
        params += [f"%{request.args['search']}%"] * 2
    with db() as conn:
        actor = me(conn)
        if actor["role"] == "EMPLOYEE":
            filters.append("(t.assigned_to = ? OR (t.assigned_to IS NULL AND t.created_by = ?))")
            params += [actor["id"], actor["id"]]
        sql = BOARD_SQL + (" WHERE " + " AND ".join(filters) if filters else "")
        rows = conn.execute(sql + " ORDER BY t.id DESC", params).fetchall()
        return jsonify([_row(r, today) for r in rows])


@taskboard_bp.route("/api/task-board/<int:task_id>/project", methods=["PATCH"])
@roles_required("ADMIN", "MANAGER")
def set_task_project(task_id):
    data, err = body({"project_id"})
    if err:
        return err
    if "project_id" not in data:
        return error("project_id is required (ID or null)")
    with db() as conn:
        if conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is None:
            return error("Task not found", 404)
        project_id = data["project_id"]
        if project_id is None:
            conn.execute("DELETE FROM task_projects WHERE task_id = ?", (task_id,))
        else:
            project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone() \
                if type(project_id) is int else None
            if project is None:
                return error("Project not found", 404)
            if not can_see(conn, me(conn), project):
                return error("You cannot use this project", 403)
            conn.execute("INSERT OR REPLACE INTO task_projects (task_id, project_id) VALUES (?, ?)",
                         (task_id, project_id))
        return jsonify(_row(conn.execute(BOARD_SQL + " WHERE t.id = ?", (task_id,)).fetchone(),
                            date.today().isoformat()))


def _counts(rows):
    out = {"total": len(rows), "pending": 0, "in_progress": 0, "completed": 0, "overdue": 0,
           "priority": {"Low": 0, "Medium": 0, "High": 0}}
    for r in rows:
        if r["status"] in out:
            out[r["status"]] += 1
        if r["priority"] in out["priority"]:
            out["priority"][r["priority"]] += 1
        out["overdue"] += int(r["is_overdue"])
    return out


@taskboard_bp.route("/api/overview", methods=["GET"])
@login_required
def overview():
    today = date.today().isoformat()
    with db() as conn:
        actor = me(conn)
        role = actor["role"]
        all_rows = [_row(r, today) for r in conn.execute(BOARD_SQL + " ORDER BY t.due_date IS NULL, t.due_date")]
        projects = [p for p in conn.execute("SELECT * FROM projects ORDER BY name COLLATE NOCASE")
                    if can_see(conn, actor, p)]
        project_cards = [{"id": p["id"], "name": p["name"], "status": p["status"],
                          "progress": progress(conn, p["id"])} for p in projects]
        result = {"role": role, "name": actor["name"], "projects": project_cards}

        if role == "ADMIN":
            result["tasks"] = _counts(all_rows)
            result["people"] = dict(zip(("total", "active"), conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(is_active), 0) FROM users").fetchone()))
            result["teams"] = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
            result["roles"] = {r[0]: r[1] for r in conn.execute(
                "SELECT role, COUNT(*) FROM users WHERE is_active = 1 GROUP BY role")}
            result["overdue_tasks"] = [r for r in all_rows if r["is_overdue"]][:6]
        elif role == "MANAGER":
            ids = {p["id"] for p in projects}
            scoped = [r for r in all_rows if r["project_id"] in ids]
            result["tasks"] = _counts(scoped)
            load = {}
            for r in scoped:
                if r["assigned_to"] and r["status"] != "completed":
                    entry = load.setdefault(r["assigned_to"], {"id": r["assigned_to"],
                                            "name": r["assignee_name"], "open": 0, "overdue": 0})
                    entry["open"] += 1
                    entry["overdue"] += int(r["is_overdue"])
            result["workload"] = sorted(load.values(), key=lambda x: -x["open"])
            result["overdue_tasks"] = [r for r in scoped if r["is_overdue"]][:6]
        else:
            mine = [r for r in all_rows if r["assigned_to"] == actor["id"]]
            result["tasks"] = _counts(mine)
            result["upcoming"] = [r for r in mine if r["status"] != "completed"][:6]
        return jsonify(result)
