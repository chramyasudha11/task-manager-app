 feature/member5-login-page
import re
import sqlite3
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

 feature/dashboard-reports


 main
from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3
import os

auth_bp = Blueprint("auth", __name__)

DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.db")
 feature/dashboard-reports


def get_db():
    conn = sqlite3.connect(DB_NAME)

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()

def get_db():
    conn = sqlite3.connect(DB_NAME, factory=ClosingConnection)
 main
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
 main
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
 feature/member5-login-page
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'EMPLOYEE'
            )
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
                return jsonify(error="You do not have permission to access this resource."), 403
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
    if not all(isinstance(value, str) for value in (name, email, password)):
        return jsonify(error="Name, email, and password are required."), 400
    if account_type is not None and account_type not in {"ADMIN", "EMPLOYEE"}:
        return jsonify(error="Choose Admin Login or Employee Login to create the account."), 400

    name = name.strip()
    email = email.strip().lower()
    if not name or len(name) > 120:
        return jsonify(error="Name must contain between 1 and 120 characters."), 400
    if not EMAIL_PATTERN.fullmatch(email) or len(email) > 254:
        return jsonify(error="Please enter a valid email address."), 400
    if len(password) < 8:
        return jsonify(error="Password must contain at least 8 characters."), 400

    database = get_db()
    admin_emails = configured_admin_emails(current_app.config)
    role = "ADMIN" if email in admin_emails else "EMPLOYEE"
    if account_type == "ADMIN" and role != "ADMIN":
        if current_app.config.get("ALLOW_PUBLIC_ADMIN_SIGNUP"):
            role = "ADMIN"
        elif admin_emails:
            return jsonify(error="Admin signup is limited to an email listed in ADMIN_EMAILS or ADMIN_EMAIL."), 403
        else:
            return jsonify(error="Admin signup is not configured. Set ADMIN_EMAILS before starting the app."), 403
    if account_type == "EMPLOYEE" and role == "ADMIN":
        return jsonify(error="This email is configured for Admin Login. Choose Admin Login to create the account."), 409
    try:
        employee = database.execute(
            "SELECT id, role, status, user_id FROM employees WHERE email = ? COLLATE NOCASE",
            (email,),
        ).fetchone()
        if employee and employee["user_id"] is not None:
            return jsonify(error="An account with this email already exists."), 409
        if employee and (
            employee["status"] != "Active"
            or (role != "ADMIN" and employee["role"] != "EMPLOYEE")
        ):
            return jsonify(error="This employee record cannot be registered with these details."), 409
        cursor = database.execute(
            "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
            (name, email, generate_password_hash(password), role),
        )
        if employee:
            database.execute(
                "UPDATE employees SET user_id = ?, role = ? WHERE id = ?",
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
        return jsonify(error="An account with this email already exists."), 409

    user = database.execute(
        "SELECT id, name, email, role FROM users WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    return jsonify(message="Account created successfully.", user=public_user(user)), 201


@auth_bp.post("/login")
def login():
    data = json_object()
    if data is None:
        return jsonify(error="Request body must be a JSON object."), 400

    email = data.get("email")
    password = data.get("password")
    if not isinstance(email, str) or not isinstance(password, str) or not email.strip() or not password:
        return jsonify(error="Email and password are required."), 400

    row = get_db().execute(
        "SELECT id, name, email, password, role FROM users WHERE email = ?",
        (email.strip().lower(),),
    ).fetchone()
    if row is None or not check_password_hash(row["password"], password):
        return jsonify(error="Incorrect email or password."), 401

    session.clear()
    session["user_id"] = row["id"]
    return jsonify(message="Login successful.", user=public_user(row))


@auth_bp.get("/me")
@login_required
def me():
    return jsonify(user=public_user(g.current_user))


@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify(message="Signed out successfully.")


@auth_bp.get("/admin/dashboard")
@roles_required("ADMIN")
def admin_dashboard():
    return jsonify(message="Admin access granted.", user=public_user(g.current_user))


@auth_bp.get("/manager/dashboard")
@roles_required("MANAGER", "ADMIN")
def manager_dashboard():
    return jsonify(message="Manager access granted.", user=public_user(g.current_user))


@auth_bp.get("/employee/dashboard")
@login_required
def employee_dashboard():
    return jsonify(message="Authenticated access granted.", user=public_user(g.current_user))

                password TEXT NOT NULL
            )
        """)

        columns = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        ]

        if "role" not in columns:
            conn.execute("""
                ALTER TABLE users
                ADD COLUMN role TEXT NOT NULL DEFAULT 'EMPLOYEE'
            """)


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Please login first"}), 401

        with get_db() as conn:
            user = conn.execute(
                "SELECT id FROM users WHERE id = ?",
                (session["user_id"],)
            ).fetchone()

        if user is None:
            session.clear()
            return jsonify({"error": "User not found"}), 401

        return func(*args, **kwargs)

    return wrapper


def roles_required(*allowed_roles):
    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            with get_db() as conn:
                user = conn.execute(
                    "SELECT role FROM users WHERE id = ?",
                    (session["user_id"],)
                ).fetchone()

            if user is None:
                session.clear()
                return jsonify({"error": "User not found"}), 401

            if user["role"] not in allowed_roles:
                return jsonify({"error": "Access denied"}), 403

            return func(*args, **kwargs)

        return wrapper
    return decorator


@auth_bp.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}

    name = data.get("name", "")
    email = data.get("email", "")
    password = data.get("password", "")

    if not all(isinstance(v, str) for v in (name, email, password)):
        return jsonify({"error": "Invalid input"}), 400

    name = name.strip()
    email = email.strip().lower()

    if not name or not email or len(password) < 8:
        return jsonify({
            "error": "Enter name, email and password (8+ characters)"
        }), 400

    hashed_password = generate_password_hash(password)

    # Public signup always assigns EMPLOYEE role
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO users (name, email, password, role)
                   VALUES (?, ?, ?, 'EMPLOYEE')""",
                (name, email, hashed_password)
            )

        return jsonify({"message": "Signup successful"}), 201

    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already registered"}), 409


@auth_bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    email = data.get("email", "")
    password = data.get("password", "")

    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify({"error": "Invalid email or password"}), 401

    email = email.strip().lower()

    with get_db() as conn:
        user = conn.execute(
            """SELECT id, name, email, password, role
               FROM users WHERE email = ?""",
            (email,)
        ).fetchone()

    if user is None or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    session.clear()
    session["user_id"] = user["id"]

    return jsonify({
        "message": "Login successful",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"]
        }
    })


@auth_bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logout successful"})


@auth_bp.route("/api/me", methods=["GET"])
@login_required
def me():
    with get_db() as conn:
        user = conn.execute(
            "SELECT id, name, email, role FROM users WHERE id = ?",
            (session["user_id"],)
        ).fetchone()

    if user is None:
        session.clear()
        return jsonify({"error": "User not found"}), 401

    return jsonify({"user": dict(user)})


@auth_bp.route("/api/admin/dashboard", methods=["GET"])
@roles_required("ADMIN")
def admin_dashboard():
    return jsonify({"message": "Admin access granted"})


@auth_bp.route("/api/manager/dashboard", methods=["GET"])
@roles_required("ADMIN", "MANAGER")
def manager_dashboard():
    return jsonify({"message": "Manager access granted"})


@auth_bp.route("/api/employee/dashboard", methods=["GET"])
@roles_required("ADMIN", "MANAGER", "EMPLOYEE")
def employee_dashboard():
 feature/dashboard-reports
    return jsonify({"message": "Authenticated access granted"})

    return jsonify({"message": "Authenticated access granted"})
 main
main
