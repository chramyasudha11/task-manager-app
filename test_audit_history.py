"""Tests for Member 3 feature: Database, Activity History and Audit Logs.

Covers:
- Safe, repeatable database initialization and migration utility
- Task activity history tracking and REST API
- Audit logs for assignment, status, and priority changes
- Task comments and discussion API with role permissions
"""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app import create_app
from migrations import MigrationManager, init_database


class DatabaseMigrationAndInitTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_mig.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_migration_manager_tracks_and_applies_migrations(self):
        manager = MigrationManager(self.db_path)
        applied = manager.get_applied_migrations()
        self.assertEqual(len(applied), 0)

        pending = manager.get_pending_migrations()
        self.assertEqual(len(pending), 3)

        # Run migrations
        applied_names = manager.run_migrations()
        self.assertEqual(len(applied_names), 3)
        self.assertIn("001_users_schema", applied_names)
        self.assertIn("002_management_schema", applied_names)
        self.assertIn("003_audit_activity_comments", applied_names)

        # Second run should be idempotent
        second_run = manager.run_migrations()
        self.assertEqual(second_run, [])

        status = manager.status()
        self.assertEqual(len(status), 3)
        for item in status:
            self.assertTrue(item["applied"])
            self.assertIsNotNone(item["applied_at"])

    def test_safe_repeatable_database_initialization(self):
        # Initial run
        init_database(database_path=self.db_path)

        with closing(sqlite3.connect(self.db_path)) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            expected_tables = {
                "users",
                "employees",
                "teams",
                "team_members",
                "projects",
                "tasks",
                "schema_migrations",
                "task_activities",
                "audit_logs",
                "task_comments",
            }
            self.assertTrue(expected_tables.issubset(tables))

            # Insert test data
            conn.execute(
                "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
                ("Test User", "test@example.com", "hash", "EMPLOYEE"),
            )
            conn.commit()

        # Run initialization again (repeatable and safe)
        init_database(database_path=self.db_path)

        with closing(sqlite3.connect(self.db_path)) as conn:
            # Existing data preserved and synced to employees
            user = conn.execute("SELECT * FROM users WHERE email = 'test@example.com'").fetchone()
            self.assertIsNotNone(user)
            emp = conn.execute("SELECT * FROM employees WHERE email = 'test@example.com'").fetchone()
            self.assertIsNotNone(emp)


class ActivityHistoryAndAuditLogsApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "users.db"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "audit-test-key",
                "DATABASE_PATH": str(self.db_path),
            }
        )
        self.client = self.app.test_client()

        # Create admin user
        self.client.post(
            "/api/signup",
            json={"name": "Admin User", "email": "admin@test.local", "password": "password123"},
        )
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("UPDATE users SET role = 'ADMIN' WHERE email = 'admin@test.local'")
            conn.execute("UPDATE employees SET role = 'ADMIN' WHERE email = 'admin@test.local'")
            conn.commit()

        # Create employee 1
        self.client.post(
            "/api/signup",
            json={"name": "Alice Employee", "email": "alice@test.local", "password": "password123"},
        )
        # Create employee 2
        self.client.post(
            "/api/signup",
            json={"name": "Bob Employee", "email": "bob@test.local", "password": "password123"},
        )

        with closing(sqlite3.connect(self.db_path)) as conn:
            self.admin_id = conn.execute("SELECT id FROM users WHERE email = 'admin@test.local'").fetchone()[0]
            self.alice_user_id = conn.execute("SELECT id FROM users WHERE email = 'alice@test.local'").fetchone()[0]
            self.alice_emp_id = conn.execute("SELECT id FROM employees WHERE email = 'alice@test.local'").fetchone()[0]
            self.bob_emp_id = conn.execute("SELECT id FROM employees WHERE email = 'bob@test.local'").fetchone()[0]

    def tearDown(self):
        self.temp_dir.cleanup()

    def login_as(self, email, password="password123"):
        self.client.post("/api/logout")
        return self.client.post("/api/login", json={"email": email, "password": password})

    def create_task_as_admin(self, **overrides):
        self.login_as("admin@test.local")
        payload = {
            "name": "Audit Task",
            "priority": "Medium",
            "status": "Not Started",
            "dueDate": "2026-11-01",
        }
        payload.update(overrides)
        res = self.client.post("/api/tasks", json=payload)
        self.assertEqual(res.status_code, 201)
        return res.get_json()["task"]

    # --- Task Activity History Tests ---

    def test_task_creation_records_activity_and_initial_audit_logs(self):
        task = self.create_task_as_admin(assigneeId=self.alice_emp_id)
        task_id = task["id"]

        # View activity history
        res = self.client.get(f"/api/tasks/{task_id}/history")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["taskId"], task_id)
        actions = [a["action"] for a in body["activities"]]
        self.assertIn("created", actions)

        # View audit logs
        res = self.client.get(f"/api/tasks/{task_id}/audit-logs")
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()["auditLogs"]
        change_types = [l["changeType"] for l in logs]
        self.assertIn("status", change_types)
        self.assertIn("priority", change_types)
        self.assertIn("assignment", change_types)

    def test_audit_logs_for_status_priority_and_assignment_changes(self):
        task = self.create_task_as_admin(assigneeId=self.alice_emp_id)
        task_id = task["id"]

        # 1. Update priority and status as Admin
        res = self.client.patch(
            f"/api/tasks/{task_id}",
            json={
                "name": "Audit Task",
                "priority": "High",
                "status": "In Progress",
                "assigneeId": self.bob_emp_id,
            },
        )
        self.assertEqual(res.status_code, 200)

        # Check audit logs for the task
        res = self.client.get(f"/api/tasks/{task_id}/audit-logs")
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()["auditLogs"]

        # Find status change
        status_changes = [l for l in logs if l["changeType"] == "status" and l["oldValue"] == "Not Started"]
        self.assertTrue(len(status_changes) >= 1)
        self.assertEqual(status_changes[0]["newValue"], "In Progress")

        # Find priority change
        priority_changes = [l for l in logs if l["changeType"] == "priority" and l["oldValue"] == "Medium"]
        self.assertTrue(len(priority_changes) >= 1)
        self.assertEqual(priority_changes[0]["newValue"], "High")

        # Find assignment change
        assign_changes = [l for l in logs if l["changeType"] == "assignment" and l["oldValue"] == "Alice Employee"]
        self.assertTrue(len(assign_changes) >= 1)
        self.assertEqual(assign_changes[0]["newValue"], "Bob Employee")

    def test_employee_updating_status_records_audit_log_and_activity(self):
        task = self.create_task_as_admin(assigneeId=self.alice_emp_id)
        task_id = task["id"]

        # Alice logs in and updates task status
        self.login_as("alice@test.local")
        res = self.client.patch(f"/api/tasks/{task_id}", json={"status": "Completed"})
        self.assertEqual(res.status_code, 200)

        # Alice views audit logs
        res = self.client.get(f"/api/tasks/{task_id}/audit-logs")
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()["auditLogs"]
        completed_log = next(
            (l for l in logs if l["changeType"] == "status" and l["newValue"] == "Completed"),
            None,
        )
        self.assertIsNotNone(completed_log)
        self.assertEqual(completed_log["userName"], "Alice Employee")

        # Alice views activities
        res = self.client.get(f"/api/tasks/{task_id}/activities")
        self.assertEqual(res.status_code, 200)
        activities = res.get_json()["activities"]
        status_activity = next(
            (a for a in activities if a["action"] == "status_changed"), None
        )
        self.assertIsNotNone(status_activity)

    def test_global_audit_logs_endpoint_with_filters_and_permissions(self):
        task1 = self.create_task_as_admin(name="Task 1", assigneeId=self.alice_emp_id)
        task2 = self.create_task_as_admin(name="Task 2", assigneeId=self.bob_emp_id)

        # Admin can see all logs
        res = self.client.get("/api/audit-logs")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertIn("auditLogs", body)
        self.assertIn("total", body)
        self.assertTrue(body["total"] >= 2)

        # Filter by change_type
        res = self.client.get("/api/audit-logs?change_type=status")
        self.assertEqual(res.status_code, 200)
        for log in res.get_json()["auditLogs"]:
            self.assertEqual(log["changeType"], "status")

        # Alice (Employee) can only see logs for her tasks
        self.login_as("alice@test.local")
        res = self.client.get("/api/audit-logs")
        self.assertEqual(res.status_code, 200)
        alice_logs = res.get_json()["auditLogs"]
        for log in alice_logs:
            self.assertEqual(log["taskId"], task1["id"])

        # Bob (Employee) cannot view Task 1's audit logs directly (403)
        self.login_as("bob@test.local")
        res = self.client.get(f"/api/tasks/{task1['id']}/audit-logs")
        self.assertEqual(res.status_code, 403)


class TaskCommentsAndDiscussionApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "users.db"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "comments-test-key",
                "DATABASE_PATH": str(self.db_path),
            }
        )
        self.client = self.app.test_client()

        # Admin
        self.client.post(
            "/api/signup",
            json={"name": "Admin User", "email": "admin@test.local", "password": "password123"},
        )
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("UPDATE users SET role = 'ADMIN' WHERE email = 'admin@test.local'")
            conn.execute("UPDATE employees SET role = 'ADMIN' WHERE email = 'admin@test.local'")
            conn.commit()

        # Alice (Employee)
        self.client.post(
            "/api/signup",
            json={"name": "Alice Employee", "email": "alice@test.local", "password": "password123"},
        )
        # Bob (Employee)
        self.client.post(
            "/api/signup",
            json={"name": "Bob Employee", "email": "bob@test.local", "password": "password123"},
        )

        with closing(sqlite3.connect(self.db_path)) as conn:
            self.alice_emp_id = conn.execute("SELECT id FROM employees WHERE email = 'alice@test.local'").fetchone()[0]
            self.bob_emp_id = conn.execute("SELECT id FROM employees WHERE email = 'bob@test.local'").fetchone()[0]

        # Admin creates task assigned to Alice
        self.client.post("/api/login", json={"email": "admin@test.local", "password": "password123"})
        res = self.client.post(
            "/api/tasks",
            json={"name": "Feature Discussion Task", "assigneeId": self.alice_emp_id},
        )
        self.task_id = res.get_json()["task"]["id"]

    def tearDown(self):
        self.temp_dir.cleanup()

    def login_as(self, email, password="password123"):
        self.client.post("/api/logout")
        return self.client.post("/api/login", json={"email": email, "password": password})

    def test_comment_crud_lifecycle_and_validation(self):
        self.login_as("alice@test.local")

        # 1. Validation: empty comment rejected
        res = self.client.post(f"/api/tasks/{self.task_id}/comments", json={"content": "   "})
        self.assertEqual(res.status_code, 400)

        # 2. Add valid comment
        res = self.client.post(
            f"/api/tasks/{self.task_id}/comments",
            json={"content": "Started working on this component."},
        )
        self.assertEqual(res.status_code, 201)
        comment = res.get_json()["comment"]
        self.assertEqual(comment["content"], "Started working on this component.")
        self.assertEqual(comment["userName"], "Alice Employee")
        comment_id = comment["id"]

        # 3. List comments
        res = self.client.get(f"/api/tasks/{self.task_id}/comments")
        self.assertEqual(res.status_code, 200)
        comments = res.get_json()["comments"]
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["id"], comment_id)

        # 4. Activity history includes comment addition
        res = self.client.get(f"/api/tasks/{self.task_id}/history")
        self.assertEqual(res.status_code, 200)
        activities = res.get_json()["activities"]
        self.assertTrue(any(a["action"] == "comment_added" for a in activities))

        # 5. Update comment as author
        res = self.client.patch(
            f"/api/tasks/{self.task_id}/comments/{comment_id}",
            json={"content": "Updated: component is half done."},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["comment"]["content"], "Updated: component is half done.")

        # 6. Delete comment as author
        res = self.client.delete(f"/api/tasks/{self.task_id}/comments/{comment_id}")
        self.assertEqual(res.status_code, 200)

        # Verify comment is gone
        res = self.client.get(f"/api/tasks/{self.task_id}/comments")
        self.assertEqual(len(res.get_json()["comments"]), 0)

    def test_comment_access_control(self):
        # Alice creates comment
        self.login_as("alice@test.local")
        res = self.client.post(
            f"/api/tasks/{self.task_id}/comments",
            json={"content": "Private team note"},
        )
        self.assertEqual(res.status_code, 201)
        comment_id = res.get_json()["comment"]["id"]

        # Bob (not assigned to task) cannot view or add comments
        self.login_as("bob@test.local")
        res = self.client.get(f"/api/tasks/{self.task_id}/comments")
        self.assertEqual(res.status_code, 403)

        res = self.client.post(
            f"/api/tasks/{self.task_id}/comments",
            json={"content": "Hacking into task"},
        )
        self.assertEqual(res.status_code, 403)

        # Admin can view and delete any comment
        self.login_as("admin@test.local")
        res = self.client.get(f"/api/tasks/{self.task_id}/comments")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()["comments"]), 1)

        res = self.client.delete(f"/api/tasks/{self.task_id}/comments/{comment_id}")
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
