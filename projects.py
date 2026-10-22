"""Member 4: Project management (create, assign team/manager, view, progress)."""
from datetime import date
import sqlite3
from flask import Blueprint, jsonify

from auth import login_required, roles_required
from org_common import body, clean_text, db, error, me
from teams import _manager_error, person, team_dict

projects_bp = Blueprint("projects", __name__)
STATUSES = {"active", "on_hold", "completed"}


def progress(conn, project_id):
    rows = conn.execute(
        """SELECT LOWER(t.status) AS s, COUNT(*) AS c FROM task_projects tp
           JOIN tasks t ON t.id = tp.task_id WHERE tp.project_id = ? GROUP BY LOWER(t.status)""",
        (project_id,)).fetchall()
    counts = {r["s"]: r["c"] for r in rows}
    total = sum(counts.values())
    done = counts.get("completed", 0)
    return {
        "total": total, "completed": done,
        "in_progress": counts.get("in_progress", 0), "pending": counts.get("pending", 0),
        "percent": round(done * 100 / total) if total else 0,
    }


def project_dict(conn, row, detail=False):
    team = conn.execute("SELECT * FROM teams WHERE id = ?", (row["team_id"],)).fetchone() if row["team_id"] else None
    result = {
        "id": row["id"], "name": row["name"], "description": row["description"],
        "status": row["status"], "start_date": row["start_date"], "end_date": row["end_date"],
        "team_id": row["team_id"], "team_name": team["name"] if team else None,
        "manager_id": row["manager_id"], "manager": person(conn, row["manager_id"]),
        "progress": progress(conn, row["id"]),
        "member_ids": [m["user_id"] for m in conn.execute(
            "SELECT user_id FROM team_members WHERE team_id = ?", (row["team_id"],))] if team else [],
    }
    if detail:
        result["team"] = team_dict(conn, team) if team else None
    return result


def _date_error(value, label):
    if value in (None, ""):
        return None, None
    try:
        return date.fromisoformat(value).isoformat(), None
    except (TypeError, ValueError):
        return None, error(f"{label} must be YYYY-MM-DD")


def _team_error(conn, team_id):
    if team_id is None:
        return None
    if type(team_id) is not int or conn.execute("SELECT 1 FROM teams WHERE id = ?", (team_id,)).fetchone() is None:
        return error("Team not found", 404)
    return None


def can_see(conn, actor, project):
    if actor["role"] == "ADMIN":
        return True
    if actor["role"] == "MANAGER":
        team_mgr = conn.execute("SELECT manager_id FROM teams WHERE id = ?", (project["team_id"],)).fetchone()
        return project["manager_id"] == actor["id"] or (team_mgr is not None and team_mgr[0] == actor["id"])
    return project["team_id"] is not None and conn.execute(
        "SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ?",
        (project["team_id"], actor["id"])).fetchone() is not None


@projects_bp.route("/api/projects", methods=["POST"])
@roles_required("ADMIN")
def create_project():
    data, err = body({"name", "description", "team_id", "manager_id", "status", "start_date", "end_date"})
    if err:
        return err
    name, err = clean_text(data.get("name"), "name", 120)
    if err:
        return err
    desc, err = clean_text(data.get("description", ""), "description", 2000, required=False)
    if err:
        return err
    status = data.get("status", "active")
    if status not in STATUSES:
        return error("status must be active, on_hold or completed")
    start, err = _date_error(data.get("start_date"), "start_date")
    if err:
        return err
    end, err = _date_error(data.get("end_date"), "end_date")
    if err:
        return err
    try:
        with db() as conn:
            err = _team_error(conn, data.get("team_id")) or _manager_error(conn, data.get("manager_id"))
            if err:
                return err
            manager_id = data.get("manager_id")
            if manager_id is None and data.get("team_id"):
                manager_id = conn.execute("SELECT manager_id FROM teams WHERE id = ?", (data["team_id"],)).fetchone()[0]
            cur = conn.execute(
                """INSERT INTO projects (name, description, status, team_id, manager_id, start_date, end_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name, desc or "", status, data.get("team_id"), manager_id, start, end))
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)).fetchone()
            return jsonify(project_dict(conn, row, detail=True)), 201
    except sqlite3.IntegrityError:
        return error("A project with this name already exists", 409)


@projects_bp.route("/api/projects", methods=["GET"])
@login_required
def list_projects():
    with db() as conn:
        actor = me(conn)
        rows = [r for r in conn.execute("SELECT * FROM projects ORDER BY name COLLATE NOCASE")
                if can_see(conn, actor, r)]
        return jsonify([project_dict(conn, r) for r in rows])


@projects_bp.route("/api/projects/<int:project_id>", methods=["GET"])
@login_required
def view_project(project_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            return error("Project not found", 404)
        if not can_see(conn, me(conn), row):
            return error("Access denied for this project", 403)
        return jsonify(project_dict(conn, row, detail=True))


@projects_bp.route("/api/projects/<int:project_id>/progress", methods=["GET"])
@login_required
def project_progress(project_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            return error("Project not found", 404)
        if not can_see(conn, me(conn), row):
            return error("Access denied for this project", 403)
        return jsonify(progress(conn, project_id))


@projects_bp.route("/api/projects/<int:project_id>", methods=["PUT"])
@roles_required("ADMIN")
def edit_project(project_id):
    data, err = body({"name", "description", "status", "start_date", "end_date"})
    if err:
        return err
    if not data:
        return error("Request body cannot be empty")
    fields = {}
    for key in data:
        if key == "name":
            fields[key], err = clean_text(data[key], "name", 120)
        elif key == "description":
            fields[key], err = clean_text(data[key], "description", 2000, required=False)
            fields[key] = fields[key] or ""
        elif key == "status":
            fields[key], err = (data[key], None) if data[key] in STATUSES else (None, error("status must be active, on_hold or completed"))
        else:
            fields[key], err = _date_error(data[key], key)
        if err:
            return err
    try:
        with db() as conn:
            if conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
                return error("Project not found", 404)
            conn.execute(f"UPDATE projects SET {', '.join(k + ' = ?' for k in fields)} WHERE id = ?",
                         [*fields.values(), project_id])
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            return jsonify(project_dict(conn, row, detail=True))
    except sqlite3.IntegrityError:
        return error("A project with this name already exists", 409)


def _assign(project_id, field, checker):
    data, err = body({field})
    if err:
        return err
    if field not in data:
        return error(f"{field} is required (ID or null)")
    with db() as conn:
        if conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
            return error("Project not found", 404)
        err = checker(conn, data[field])
        if err:
            return err
        conn.execute(f"UPDATE projects SET {field} = ? WHERE id = ?", (data[field], project_id))
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return jsonify(project_dict(conn, row, detail=True))


@projects_bp.route("/api/projects/<int:project_id>/team", methods=["PATCH"])
@roles_required("ADMIN")
def assign_project_team(project_id):
    return _assign(project_id, "team_id", _team_error)


@projects_bp.route("/api/projects/<int:project_id>/manager", methods=["PATCH"])
@roles_required("ADMIN")
def assign_project_manager(project_id):
    return _assign(project_id, "manager_id", _manager_error)
