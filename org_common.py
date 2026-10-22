"""Member 4 shared helpers: DB access, org tables, deactivation guard.

Only NEW tables/columns are created here. Member 1 (auth.py) and Member 2
(tasks.py) files are never edited; the users table gets extra columns through
a safe ALTER TABLE migration.
"""
from contextlib import contextmanager
import sqlite3

from flask import Blueprint, jsonify, request, session
from auth import get_db

guard_bp = Blueprint("org_guard", __name__)


@contextmanager
def db():
    conn = get_db()
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            yield conn
    finally:
        conn.close()


def error(message, status=400):
    return jsonify({"error": message}), status


def me(conn):
    return conn.execute(
        "SELECT id, name, role FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()


def body(allowed):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, error("Expected a JSON object")
    unknown = set(data) - set(allowed)
    if unknown:
        return None, error("Unsupported field(s): " + ", ".join(sorted(unknown)))
    return data, None


def clean_text(value, label, max_len=200, required=True):
    if value is None and not required:
        return None, None
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > max_len:
        return None, error(f"{label} must be text (max {max_len} characters)")
    return value.strip(), None


def init_org_db():
    with db() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        if "is_active" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        if "department" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN department TEXT NOT NULL DEFAULT ''")
        if "designation" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN designation TEXT NOT NULL DEFAULT ''")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                manager_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS team_members (
                team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                PRIMARY KEY (team_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
                manager_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                start_date TEXT,
                end_date TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS task_projects (
                task_id INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE
            );
        """)


@guard_bp.before_app_request
def block_deactivated_users():
    """Deactivated employees cannot log in and lose their session.

    Lives here so Member 1's auth.py needs no change. If the migration has not
    run yet (e.g. older tests), the guard silently does nothing.
    """
    if not request.path.startswith("/api/"):
        return None
    try:
        with db() as conn:
            if request.path == "/api/login" and request.method == "POST":
                data = request.get_json(silent=True) or {}
                email = data.get("email")
                if isinstance(email, str):
                    row = conn.execute(
                        "SELECT is_active FROM users WHERE email = ?", (email.strip().lower(),)
                    ).fetchone()
                    if row is not None and not row["is_active"]:
                        return error("This account is deactivated. Contact your admin.", 403)
                return None
            uid = session.get("user_id")
            if uid is not None:
                row = conn.execute("SELECT is_active FROM users WHERE id = ?", (uid,)).fetchone()
                if row is not None and not row["is_active"]:
                    session.clear()
                    return error("Your account is deactivated.", 401)
    except sqlite3.OperationalError:
        return None
    return None
