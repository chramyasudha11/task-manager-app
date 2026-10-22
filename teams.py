"""Member 4: Team management. Admin changes teams; everyone logged in can view relevant ones."""
import sqlite3
from flask import Blueprint, jsonify

from auth import login_required, roles_required
from org_common import body, clean_text, db, error, me

teams_bp = Blueprint("teams", __name__)


def person(conn, user_id):
    if user_id is None:
        return None
    r = conn.execute("SELECT id, name, role FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(r) if r else None


def team_dict(conn, row):
    members = conn.execute(
        """SELECT u.id, u.name, u.role, u.is_active FROM team_members m
           JOIN users u ON u.id = m.user_id WHERE m.team_id = ? ORDER BY u.name COLLATE NOCASE""",
        (row["id"],)).fetchall()
    return {
        "id": row["id"], "name": row["name"], "manager_id": row["manager_id"],
        "manager": person(conn, row["manager_id"]),
        "members": [dict(m) | {"is_active": bool(m["is_active"])} for m in members],
        "member_count": len(members),
    }


def _manager_error(conn, manager_id):
    if manager_id is None:
        return None
    u = conn.execute("SELECT role, is_active FROM users WHERE id = ?", (manager_id,)).fetchone()
    if u is None:
        return error("Manager not found", 404)
    if not u["is_active"] or u["role"] not in ("MANAGER", "ADMIN"):
        return error("Manager must be an active user with MANAGER or ADMIN role")
    return None


def _member_error(conn, user_id):
    if type(user_id) is not int:
        return error("user_id must be a number")
    u = conn.execute("SELECT is_active FROM users WHERE id = ?", (user_id,)).fetchone()
    if u is None:
        return error("User not found", 404)
    if not u["is_active"]:
        return error("Cannot add a deactivated employee")
    return None


@teams_bp.route("/api/teams", methods=["POST"])
@roles_required("ADMIN")
def create_team():
    data, err = body({"name", "manager_id", "member_ids"})
    if err:
        return err
    name, err = clean_text(data.get("name"), "name", 100)
    if err:
        return err
    member_ids = data.get("member_ids", [])
    if not isinstance(member_ids, list):
        return error("member_ids must be a list")
    try:
        with db() as conn:
            err = _manager_error(conn, data.get("manager_id"))
            if err:
                return err
            for uid in member_ids:
                err = _member_error(conn, uid)
                if err:
                    return err
            cur = conn.execute("INSERT INTO teams (name, manager_id) VALUES (?, ?)",
                               (name, data.get("manager_id")))
            for uid in set(member_ids):
                conn.execute("INSERT INTO team_members (team_id, user_id) VALUES (?, ?)",
                             (cur.lastrowid, uid))
            row = conn.execute("SELECT * FROM teams WHERE id = ?", (cur.lastrowid,)).fetchone()
            return jsonify(team_dict(conn, row)), 201
    except sqlite3.IntegrityError:
        return error("A team with this name already exists", 409)


@teams_bp.route("/api/teams", methods=["GET"])
@login_required
def list_teams():
    with db() as conn:
        actor = me(conn)
        if actor["role"] == "EMPLOYEE":
            rows = conn.execute(
                """SELECT t.* FROM teams t JOIN team_members m ON m.team_id = t.id
                   WHERE m.user_id = ? ORDER BY t.name COLLATE NOCASE""", (actor["id"],)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM teams ORDER BY name COLLATE NOCASE").fetchall()
        return jsonify([team_dict(conn, r) for r in rows])


@teams_bp.route("/api/teams/<int:team_id>", methods=["GET"])
@login_required
def view_team(team_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        if row is None:
            return error("Team not found", 404)
        actor = me(conn)
        if actor["role"] == "EMPLOYEE" and conn.execute(
                "SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ?",
                (team_id, actor["id"])).fetchone() is None:
            return error("Access denied for this team", 403)
        return jsonify(team_dict(conn, row))


@teams_bp.route("/api/teams/<int:team_id>", methods=["PUT"])
@roles_required("ADMIN")
def rename_team(team_id):
    data, err = body({"name"})
    if err:
        return err
    name, err = clean_text(data.get("name"), "name", 100)
    if err:
        return err
    try:
        with db() as conn:
            if conn.execute("SELECT 1 FROM teams WHERE id = ?", (team_id,)).fetchone() is None:
                return error("Team not found", 404)
            conn.execute("UPDATE teams SET name = ? WHERE id = ?", (name, team_id))
            return jsonify(team_dict(conn, conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()))
    except sqlite3.IntegrityError:
        return error("A team with this name already exists", 409)


@teams_bp.route("/api/teams/<int:team_id>", methods=["DELETE"])
@roles_required("ADMIN")
def delete_team(team_id):
    with db() as conn:
        if conn.execute("SELECT 1 FROM teams WHERE id = ?", (team_id,)).fetchone() is None:
            return error("Team not found", 404)
        conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
        return jsonify({"message": "Team deleted"})


@teams_bp.route("/api/teams/<int:team_id>/members", methods=["POST"])
@roles_required("ADMIN")
def add_member(team_id):
    data, err = body({"user_id"})
    if err:
        return err
    with db() as conn:
        row = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        if row is None:
            return error("Team not found", 404)
        err = _member_error(conn, data.get("user_id"))
        if err:
            return err
        conn.execute("INSERT OR IGNORE INTO team_members (team_id, user_id) VALUES (?, ?)",
                     (team_id, data["user_id"]))
        return jsonify(team_dict(conn, row)), 201


@teams_bp.route("/api/teams/<int:team_id>/members/<int:user_id>", methods=["DELETE"])
@roles_required("ADMIN")
def remove_member(team_id, user_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        if row is None:
            return error("Team not found", 404)
        cur = conn.execute("DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
                           (team_id, user_id))
        if cur.rowcount == 0:
            return error("This user is not in the team", 404)
        return jsonify(team_dict(conn, row))


@teams_bp.route("/api/teams/<int:team_id>/manager", methods=["PATCH"])
@roles_required("ADMIN")
def assign_team_manager(team_id):
    data, err = body({"manager_id"})
    if err:
        return err
    if "manager_id" not in data:
        return error("manager_id is required (user ID or null)")
    with db() as conn:
        if conn.execute("SELECT 1 FROM teams WHERE id = ?", (team_id,)).fetchone() is None:
            return error("Team not found", 404)
        err = _manager_error(conn, data["manager_id"])
        if err:
            return err
        conn.execute("UPDATE teams SET manager_id = ? WHERE id = ?", (data["manager_id"], team_id))
        return jsonify(team_dict(conn, conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()))
