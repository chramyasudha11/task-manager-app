
import re
import sqlite3
import time
from contextlib import closing
from functools import wraps
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash


auth_bp = Blueprint("auth", __name__, url_prefix="/api")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def get_db():
    if "db" not in g:
        database_path = Path(current_app.config["DATABASE_PATH"])
        database_path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(database_path, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@auth_bp.teardown_app_request
def close_db(_error=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()


def init_db(app):
    database_path = Path(app.config["DATABASE_PATH"])
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(database_path, timeout=10)) as database:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'EMPLOYEE'
            )
            """
        )

        columns = [
    row[1]
    for row in database.execute(
        "PRAGMA table_info(users)"
    ).fetchall()
]

        if "role" not in columns:
            database.execute(
                """
                ALTER TABLE users
                ADD COLUMN role TEXT NOT NULL DEFAULT 'EMPLOYEE'
                """
            )

        
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL COLLATE NOCASE,
                ip_address TEXT,
                attempted_at INTEGER NOT NULL
            )
            """
        )
        database.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_login_attempts_lookup
                ON login_attempts(email, attempted_at)
            """
        )

        database.commit()


def public_user(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
    }


def current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None

    return get_db().execute(
        "SELECT id, name, email, role FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()

        if user is None:
            session.clear()
            return jsonify(error="Authentication required."), 401

        g.current_user = user
        return view(*args, **kwargs)

    return wrapped


def roles_required(*roles):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.current_user["role"] not in roles:
                return jsonify(
                    error="You do not have permission to access this resource."
                ), 403

            return view(*args, **kwargs)

        return wrapped

    return decorate


def json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    return data


def configured_admin_emails(config):
    emails = set()

    for setting in ("ADMIN_EMAILS", "ADMIN_EMAIL"):
        value = config.get(setting, "")
        values = value.split(",") if isinstance(value, str) else value

        if isinstance(values, (list, tuple, set)):
            emails.update(
                email.strip().lower()
                for email in values
                if isinstance(email, str) and email.strip()
            )

    return emails


@auth_bp.post("/signup")
def signup():
    data = json_object()

    if data is None:
        return jsonify(error="Request body must be a JSON object."), 400

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    account_type = data.get("accountType")

    if not all(
        isinstance(value, str)
        for value in (name, email, password)
    ):
        return jsonify(
            error="Name, email, and password are required."
        ), 400

    if account_type is not None and account_type not in {
        "ADMIN", "EMPLOYEE"
    }:
        return jsonify(
            error="Choose Admin Login or Employee Login to create the account."
        ), 400

    name = name.strip()
    email = email.strip().lower()

    if not name or len(name) > 120:
        return jsonify(
            error="Name must contain between 1 and 120 characters."
        ), 400

    if not EMAIL_PATTERN.fullmatch(email) or len(email) > 254:
        return jsonify(error="Please enter a valid email address."), 400

    if len(password) < 8:
        return jsonify(
            error="Password must contain at least 8 characters."
        ), 400

    database = get_db()
    admin_emails = configured_admin_emails(current_app.config)
    role = "ADMIN" if email in admin_emails else "EMPLOYEE"

    if account_type == "ADMIN" and role != "ADMIN":
        if current_app.config.get("ALLOW_PUBLIC_ADMIN_SIGNUP"):
            role = "ADMIN"
        elif admin_emails:
            return jsonify(
                error=(
                    "Admin signup is limited to an email listed in "
                    "ADMIN_EMAILS or ADMIN_EMAIL."
                )
            ), 403
        else:
            return jsonify(
                error=(
                    "Admin signup is not configured. "
                    "Set ADMIN_EMAILS before starting the app."
                )
            ), 403

    if account_type == "EMPLOYEE" and role == "ADMIN":
        return jsonify(
            error=(
                "This email is configured for Admin Login. "
                "Choose Admin Login to create the account."
            )
        ), 409

    try:
        employee = database.execute(
            """
            SELECT id, role, status, user_id
            FROM employees
            WHERE email = ? COLLATE NOCASE
            """,
            (email,),
        ).fetchone()

        if employee and employee["user_id"] is not None:
            return jsonify(
                error="An account with this email already exists."
            ), 409

        if employee and (
            employee["status"] != "Active"
            or (role != "ADMIN" and employee["role"] != "EMPLOYEE")
        ):
            return jsonify(
                error=(
                    "This employee record cannot be registered "
                    "with these details."
                )
            ), 409

        cursor = database.execute(
            """
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, ?)
            """,
            (name, email, generate_password_hash(password), role),
        )

        if employee:
            database.execute(
                """
                UPDATE employees
                SET user_id = ?, role = ?
                WHERE id = ?
                """,
                (cursor.lastrowid, role, employee["id"]),
            )
        else:
            database.execute(
                """
                INSERT INTO employees (user_id, name, email, role)
                VALUES (?, ?, ?, ?)
                """,
                (cursor.lastrowid, name, email, role),
            )

        database.commit()

    except sqlite3.IntegrityError:
        database.rollback()
        return jsonify(
            error="An account with this email already exists."
        ), 409

    user = database.execute(
        "SELECT id, name, email, role FROM users WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()

    return jsonify(
        message="Account created successfully.",
        user=public_user(user),
    ), 201


@auth_bp.post("/login")
def login():
    data = json_object()

    if data is None:
        return jsonify(error="Request body must be a JSON object."), 400

    email = data.get("email")
    password = data.get("password")

    if (
        not isinstance(email, str)
        or not isinstance(password, str)
        or not email.strip()
        or not password
    ):
        return jsonify(error="Email and password are required."), 400

    normalized_email = email.strip().lower()
    database = get_db()
    now = int(time.time())
    max_attempts = current_app.config.get("MAX_FAILED_LOGIN_ATTEMPTS", 5)
    window_seconds = current_app.config.get("LOGIN_LOCKOUT_WINDOW_SECONDS", 15 * 60)
    window_start = now - window_seconds

    recent_failures = database.execute(
        """
        SELECT COUNT(*) AS count
        FROM login_attempts
        WHERE email = ? COLLATE NOCASE
          AND attempted_at >= ?
        """,
        (normalized_email, window_start),
    ).fetchone()["count"]

    if recent_failures >= max_attempts:
        oldest_in_window = database.execute(
            """
            SELECT MIN(attempted_at) AS oldest
            FROM (
                SELECT attempted_at
                FROM login_attempts
                WHERE email = ? COLLATE NOCASE
                  AND attempted_at >= ?
                ORDER BY attempted_at DESC
                LIMIT ?
            )
            """,
            (normalized_email, window_start, max_attempts),
        ).fetchone()["oldest"]

        retry_after = (
            max(1, (oldest_in_window + window_seconds) - now)
            if oldest_in_window
            else window_seconds
        )
        response = jsonify(
            error="Too many failed login attempts. Please try again later."
        )
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return response

    row = database.execute(
        """
        SELECT id, name, email, password, role
        FROM users
        WHERE email = ? COLLATE NOCASE
        """,
        (normalized_email,),
    ).fetchone()

    if row is None or not check_password_hash(row["password"], password):
        ip_address = request.remote_addr or ""
        database.execute(
            """
            INSERT INTO login_attempts (email, ip_address, attempted_at)
            VALUES (?, ?, ?)
            """,
            (normalized_email, ip_address, now),
        )
        database.commit()
        return jsonify(error="Incorrect email or password."), 401

    database.execute(
        """
        DELETE FROM login_attempts
        WHERE email = ? COLLATE NOCASE
        """,
        (normalized_email,),
    )
    database.commit()

    session.clear()
    session["user_id"] = row["id"]

    return jsonify(
        message="Login successful.",
        user=public_user(row),
    )


@auth_bp.get("/me")
@login_required
def me():
    return jsonify(user=public_user(g.current_user))


@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify(message="Signed out successfully.")

@auth_bp.route("/account/password", methods=["POST", "PUT", "PATCH"])
@auth_bp.route("/profile/password", methods=["POST", "PUT", "PATCH"])
@auth_bp.route("/me/password", methods=["POST", "PUT", "PATCH"])
@auth_bp.route("/password", methods=["POST", "PUT", "PATCH"])
@login_required
def update_password():
    data = json_object()

    if data is None:
        return jsonify(error="Request body must be a JSON object."), 400

    current_password = (
        data.get("current_password")
        if data.get("current_password") is not None
        else (
            data.get("currentPassword")
            if data.get("currentPassword") is not None
            else (
                data.get("old_password")
                if data.get("old_password") is not None
                else data.get("oldPassword")
            )
        )
    )

    new_password = (
        data.get("new_password")
        if data.get("new_password") is not None
        else (
            data.get("newPassword")
            if data.get("newPassword") is not None
            else data.get("password")
        )
    )

    confirm_password = (
        data.get("confirm_password")
        if data.get("confirm_password") is not None
        else (
            data.get("confirmPassword")
            if data.get("confirmPassword") is not None
            else data.get("new_password_confirm")
        )
    )

    if (
        not isinstance(current_password, str)
        or not isinstance(new_password, str)
        or not current_password
        or not new_password
    ):
        return jsonify(
            error="Current password and new password are required."
        ), 400

    if confirm_password is not None:
        if not isinstance(confirm_password, str) or confirm_password != new_password:
            return jsonify(error="New passwords do not match."), 400

    if len(new_password) < 8:
        return jsonify(
            error="Password must contain at least 8 characters."
        ), 400

    database = get_db()
    row = database.execute(
        "SELECT id, password FROM users WHERE id = ?",
        (g.current_user["id"],),
    ).fetchone()

    if row is None or not check_password_hash(row["password"], current_password):
        return jsonify(error="Current password is incorrect."), 400

    if check_password_hash(row["password"], new_password):
        return jsonify(
            error="New password cannot be the same as the current password."
        ), 400

    database.execute(
        "UPDATE users SET password = ? WHERE id = ?",
        (generate_password_hash(new_password), g.current_user["id"]),
    )
    database.commit()

    return jsonify(
        message="Password updated successfully.",
        user=public_user(g.current_user),
    ), 200



@auth_bp.get("/admin/dashboard")
@roles_required("ADMIN")
def admin_dashboard():
    return jsonify(
        message="Admin access granted.",
        user=public_user(g.current_user),
    )


@auth_bp.get("/manager/dashboard")
@roles_required("MANAGER", "ADMIN")
def manager_dashboard():
    return jsonify(
        message="Manager access granted.",
        user=public_user(g.current_user),
    )


@auth_bp.get("/employee/dashboard")
@login_required
def employee_dashboard():
    return jsonify(
        message="Authenticated access granted.",
        user=public_user(g.current_user),
    )
