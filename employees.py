"""Member 4: Employee management (ADMIN only, plus a read-only picker list)."""
import sqlite3
from flask import Blueprint, jsonify, request, session
from werkzeug.security import generate_password_hash

from auth import roles_required
from org_common import body, clean_text, db, error

employees_bp = Blueprint("employees", __name__)
ROLES = {"ADMIN", "MANAGER", "EMPLOYEE"}


def _public(row):
    return {
        "id": row["id"], "name": row["name"], "email": row["email"],
        "role": row["role"], "department": row["department"],
        "designation": row["designation"], "is_active": bool(row["is_active"]),
    }


def _validate(data, creating):
    out = {}
    for key, label, size in (("name", "name", 100), ("department", "department", 80),
                             ("designation", "designation", 80)):
        if key in data:
            val, err = clean_text(data[key], label, size, required=(key == "name"))
            if err:
                return None, err
            out[key] = val or ""
    if "email" in data:
        val, err = clean_text(data["email"], "email", 150)
        if err:
            return None, err
        val = val.lower()
        if "@" not in val or "." not in val.split("@")[-1]:
            return None, error("Enter a valid email")
        out["email"] = val
    if "role" in data:
        if data["role"] not in ROLES:
            return None, error("role must be ADMIN, MANAGER or EMPLOYEE")
        out["role"] = data["role"]
    if "password" in data:
        if not isinstance(data["password"], str) or len(data["password"]) < 8:
            return None, error("password must be at least 8 characters")
        out["password"] = generate_password_hash(data["password"])
    if creating:
        for needed in ("name", "email", "password"):
            if needed not in out:
                return None, error(f"{needed} is required")
        out.setdefault("role", "EMPLOYEE")
    return out, None


@employees_bp.route("/api/employees", methods=["POST"])
@roles_required("ADMIN")
def add_employee():
    data, err = body({"name", "email", "password", "role", "department", "designation"})
    if err:
        return err
    fields, err = _validate(data, creating=True)
    if err:
        return err
    try:
        with db() as conn:
            cur = conn.execute(
                f"INSERT INTO users ({', '.join(fields)}) VALUES ({', '.join('?' * len(fields))})",
                list(fields.values()))
            row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
            return jsonify(_public(row)), 201
    except sqlite3.IntegrityError:
        return error("Email already registered", 409)


@employees_bp.route("/api/employees", methods=["GET"])
@roles_required("ADMIN")
def list_employees():
    sql, params = "SELECT * FROM users WHERE 1=1", []
    q = request.args.get("q")
    if q:
        sql += " AND (name LIKE ? OR email LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if request.args.get("role") in ROLES:
        sql += " AND role = ?"
        params.append(request.args["role"])
    if request.args.get("active") in ("0", "1"):
        sql += " AND is_active = ?"
        params.append(int(request.args["active"]))
    with db() as conn:
        rows = conn.execute(sql + " ORDER BY name COLLATE NOCASE", params).fetchall()
        return jsonify([_public(r) for r in rows])


@employees_bp.route("/api/employees/options", methods=["GET"])
@roles_required("ADMIN", "MANAGER")
def employee_options():
    """Active people for dropdowns (task assignment, team members)."""
    with db() as conn:
        rows = conn.execute(
            "SELECT id, name, role FROM users WHERE is_active = 1 ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return jsonify([{"id": r["id"], "name": r["name"], "role": r["role"]} for r in rows])


@employees_bp.route("/api/employees/<int:emp_id>", methods=["GET"])
@roles_required("ADMIN")
def view_employee(emp_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (emp_id,)).fetchone()
        if row is None:
            return error("Employee not found", 404)
        result = _public(row)
        result["teams"] = [dict(t) for t in conn.execute(
            """SELECT t.id, t.name FROM teams t JOIN team_members m ON m.team_id = t.id
               WHERE m.user_id = ? ORDER BY t.name""", (emp_id,))]
        result["open_tasks"] = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE assigned_to = ? AND status != 'completed'",
            (emp_id,)).fetchone()[0]
        return jsonify(result)


@employees_bp.route("/api/employees/<int:emp_id>", methods=["PUT"])
@roles_required("ADMIN")
def edit_employee(emp_id):
    data, err = body({"name", "email", "password", "role", "department", "designation"})
    if err:
        return err
    if not data:
        return error("Request body cannot be empty")
    fields, err = _validate(data, creating=False)
    if err:
        return err
    if emp_id == session["user_id"] and fields.get("role", "ADMIN") != "ADMIN":
        return error("You cannot remove your own admin role")
    try:
        with db() as conn:
            if conn.execute("SELECT 1 FROM users WHERE id = ?", (emp_id,)).fetchone() is None:
                return error("Employee not found", 404)
            conn.execute(f"UPDATE users SET {', '.join(k + ' = ?' for k in fields)} WHERE id = ?",
                         [*fields.values(), emp_id])
            return jsonify(_public(conn.execute("SELECT * FROM users WHERE id = ?", (emp_id,)).fetchone()))
    except sqlite3.IntegrityError:
        return error("Email already registered", 409)


def _set_active(emp_id, active):
    if emp_id == session["user_id"] and not active:
        return error("You cannot deactivate your own account")
    with db() as conn:
        if conn.execute("SELECT 1 FROM users WHERE id = ?", (emp_id,)).fetchone() is None:
            return error("Employee not found", 404)
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (int(active), emp_id))
        return jsonify(_public(conn.execute("SELECT * FROM users WHERE id = ?", (emp_id,)).fetchone()))


@employees_bp.route("/api/employees/<int:emp_id>/deactivate", methods=["PATCH"])
@roles_required("ADMIN")
def deactivate_employee(emp_id):
    return _set_active(emp_id, False)


@employees_bp.route("/api/employees/<int:emp_id>/activate", methods=["PATCH"])
@roles_required("ADMIN")
def activate_employee(emp_id):
    return _set_active(emp_id, True)
