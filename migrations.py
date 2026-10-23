"""Database migration utility and safe, repeatable database initialization.

Member 3: Database, Activity History and Audit Logs
- Schema migrations tracking via `schema_migrations` table
- Idempotent, ordered migrations for core, workspace, and audit/activity/comments schemas
- Safe, repeatable initialization for application startup and CLI usage
"""

import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _column_names(conn, table_name):
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


# --- Migration definitions ---

def _migration_001_users(conn):
    """Core users table with role column."""
    conn.execute(
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
    cols = _column_names(conn, "users")
    if "role" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'EMPLOYEE'")


def _migration_002_management(conn):
    """Workspace management tables: employees, teams, team_members, projects, tasks."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            department TEXT NOT NULL DEFAULT 'General',
            title TEXT NOT NULL DEFAULT 'Employee',
            role TEXT NOT NULL DEFAULT 'EMPLOYEE'
                CHECK (role IN ('ADMIN', 'MANAGER', 'EMPLOYEE')),
            status TEXT NOT NULL DEFAULT 'Active'
                CHECK (status IN ('Active', 'Inactive')),
            start_date TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            description TEXT NOT NULL DEFAULT '',
            manager_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS team_members (
            team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            PRIMARY KEY (team_id, employee_id)
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
            manager_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
            start_date TEXT,
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'Not Started'
                CHECK (status IN ('On Track', 'In Progress', 'At Risk', 'Completed')),
            progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            assignee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
            due_date TEXT,
            priority TEXT NOT NULL DEFAULT 'Medium'
                CHECK (priority IN ('Low', 'Medium', 'High')),
            status TEXT NOT NULL DEFAULT 'Not Started'
                CHECK (status IN ('Not Started', 'In Progress', 'Completed')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
        """
    )


def _migration_003_audit_and_activity(conn):
    """Activity history, audit logs, and task comments."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS task_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_activities_task ON task_activities(task_id);
        CREATE INDEX IF NOT EXISTS idx_activities_user ON task_activities(user_id);
        CREATE INDEX IF NOT EXISTS idx_activities_created ON task_activities(created_at);

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            change_type TEXT NOT NULL
                CHECK (change_type IN ('assignment', 'status', 'priority')),
            old_value TEXT,
            new_value TEXT,
            details TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_logs(task_id);
        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
        CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_logs(change_type);
        CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);

        CREATE TABLE IF NOT EXISTS task_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_comments_task ON task_comments(task_id);
        CREATE INDEX IF NOT EXISTS idx_comments_user ON task_comments(user_id);
        CREATE INDEX IF NOT EXISTS idx_comments_created ON task_comments(created_at);
        """
    )


MIGRATIONS = [
    {
        "version": "001_users_schema",
        "description": "Initialize users table and role column",
        "up": _migration_001_users,
    },
    {
        "version": "002_management_schema",
        "description": "Initialize employees, teams, projects, and tasks tables",
        "up": _migration_002_management,
    },
    {
        "version": "003_audit_activity_comments",
        "description": "Initialize task_activities, audit_logs, and task_comments tables",
        "up": _migration_003_audit_and_activity,
    },
]


class MigrationManager:
    """Manages schema migrations idempotently and tracks applied migrations."""

    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self):
        conn = sqlite3.connect(str(self.database_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_migrations_table(self):
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def get_applied_migrations(self):
        self.init_migrations_table()
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT version, description, applied_at FROM schema_migrations ORDER BY version"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_pending_migrations(self):
        applied_versions = {m["version"] for m in self.get_applied_migrations()}
        return [m for m in MIGRATIONS if m["version"] not in applied_versions]

    def run_migrations(self):
        """Run all pending migrations in order inside individual transactions."""
        self.init_migrations_table()
        applied = []
        pending = self.get_pending_migrations()

        for migration in pending:
            with closing(self._connect()) as conn:
                try:
                    migration["up"](conn)
                    conn.execute(
                        """
                        INSERT INTO schema_migrations (version, description, applied_at)
                        VALUES (?, ?, ?)
                        """,
                        (migration["version"], migration["description"], _utc_now()),
                    )
                    conn.commit()
                    applied.append(migration["version"])
                except Exception:
                    conn.rollback()
                    raise

        return applied

    def status(self):
        """Return migration status summary."""
        applied_map = {m["version"]: m["applied_at"] for m in self.get_applied_migrations()}
        results = []
        for m in MIGRATIONS:
            is_applied = m["version"] in applied_map
            results.append({
                "version": m["version"],
                "description": m["description"],
                "applied": is_applied,
                "applied_at": applied_map.get(m["version"]),
            })
        return results


def init_database(app=None, database_path=None):
    """Safe, repeatable database initialization.

    Runs all schema migrations, backfills employees from existing users,
    and ensures configured admin accounts are promoted.
    Can be called repeatedly without data loss or duplicate errors.
    """
    if database_path is None:
        if app is not None and "DATABASE_PATH" in app.config:
            database_path = app.config["DATABASE_PATH"]
        else:
            database_path = os.environ.get(
                "DATABASE_PATH", str(Path(__file__).resolve().parent / "users.db")
            )

    manager = MigrationManager(database_path)
    applied = manager.run_migrations()

    # Sync workspace and admin state if app or config is available
    with closing(manager._connect()) as conn:
        # Link users into employees safely if not already present
        conn.execute(
            """
            INSERT OR IGNORE INTO employees (user_id, name, email, role)
            SELECT id, name, email, role FROM users
            """
        )

        if app is not None:
            # Promote admin emails configured in app.config
            raw_emails = app.config.get("ADMIN_EMAILS", "")
            emails = set()
            if isinstance(raw_emails, str):
                emails = {e.strip().lower() for e in raw_emails.split(",") if e.strip()}
            elif isinstance(raw_emails, (list, tuple, set)):
                emails = {str(e).strip().lower() for e in raw_emails if str(e).strip()}

            single_email = (app.config.get("ADMIN_EMAIL") or "").strip().lower()
            if single_email:
                emails.add(single_email)

            for admin_email in emails:
                conn.execute(
                    "UPDATE users SET role = 'ADMIN' WHERE email = ? COLLATE NOCASE",
                    (admin_email,),
                )
                conn.execute(
                    "UPDATE employees SET role = 'ADMIN' WHERE email = ? COLLATE NOCASE",
                    (admin_email,),
                )

        conn.commit()

    return applied


def run_cli():
    """Command-line interface for database migration utility."""
    db_path = os.environ.get(
        "DATABASE_PATH", str(Path(__file__).resolve().parent / "users.db")
    )
    manager = MigrationManager(db_path)

    cmd = (sys.argv[1:2] or ["status"])[0].lower()

    if cmd == "status":
        print(f"Database: {db_path}")
        print("-" * 75)
        print(f"{'Version':<30} {'Status':<10} {'Applied At':<22} Description")
        print("-" * 75)
        for item in manager.status():
            status_text = "Applied" if item["applied"] else "Pending"
            applied_at = item["applied_at"] or "-"
            print(f"{item['version']:<30} {status_text:<10} {applied_at:<22} {item['description']}")
        print("-" * 75)

    elif cmd == "migrate":
        print(f"Applying pending migrations for: {db_path}")
        applied = manager.run_migrations()
        if applied:
            print(f"Successfully applied {len(applied)} migration(s): {', '.join(applied)}")
        else:
            print("Database is already up to date. No pending migrations.")

    elif cmd == "init":
        print(f"Initializing database: {db_path}")
        applied = init_database(database_path=db_path)
        print(f"Initialization complete. Applied {len(applied)} new migration(s).")

    else:
        print(f"Unknown command: '{cmd}'. Available commands: status, migrate, init")
        sys.exit(1)


if __name__ == "__main__":
    run_cli()
