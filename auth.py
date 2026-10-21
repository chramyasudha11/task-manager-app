from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3
import os

auth_bp = Blueprint("auth", __name__)

DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.db")


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
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
    return jsonify({"message": "Authenticated access granted"})