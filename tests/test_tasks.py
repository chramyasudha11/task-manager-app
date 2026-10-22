"""Run with: python -m unittest discover -s tests -v"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import auth
from app import app
from tasks import init_tasks_db


class TaskApiTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.old_db = auth.DB_NAME
        auth.DB_NAME = os.path.join(self.dir.name, "users.db")
        app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
        auth.init_db()
        init_tasks_db()
        self.manager = app.test_client()
        self.employee1 = app.test_client()
        self.employee2 = app.test_client()
        self.guest = app.test_client()
        self.manager_id = self.add_user(self.manager, "manager", "MANAGER")
        self.e1_id = self.add_user(self.employee1, "employee1", "EMPLOYEE")
        self.e2_id = self.add_user(self.employee2, "employee2", "EMPLOYEE")

    def tearDown(self):
        auth.DB_NAME = self.old_db
        self.dir.cleanup()

    def add_user(self, client, username, role):
        email = f"{username}@example.com"
        response = client.post("/api/signup", json={
            "name": username, "email": email, "password": "Test12345!"
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        with auth.get_db() as db:
            db.execute("UPDATE users SET role = ? WHERE email = ?", (role, email))
        response = client.post("/api/login", json={
            "email": email, "password": "Test12345!"
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["user"]["id"]

    def new_task(self, client=None, **overrides):
        payload = {
            "title": "Prepare sprint backlog", "description": "Plan the week",
            "priority": "High", "category": "Work", "due_date": "2026-10-30"
        }
        payload.update(overrides)
        return (client or self.manager).post("/api/tasks", json=payload)

    def test_db_connections_are_closed_after_with_block(self):
        """Regression: Windows must be able to remove the temp users.db."""
        import sqlite3
        with auth.get_db() as conn:
            self.assertIsNotNone(conn.execute("SELECT 1").fetchone())
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_all_seven_endpoints_and_completion(self):
        r = self.new_task()
        self.assertEqual(r.status_code, 201)
        task = r.get_json()
        task_id = task["id"]
        self.assertEqual(task["created_by"], self.manager_id)
        self.assertIsNone(task["assigned_to"])
        self.assertEqual(task["status"], "pending")

        r = self.manager.get("/api/tasks")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()), 1)
        self.assertEqual(self.manager.get(f"/api/tasks/{task_id}").status_code, 200)

        r = self.manager.put(f"/api/tasks/{task_id}", json={
            "title": "Refined task", "priority": "Low", "category": "College"
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["title"], "Refined task")

        r = self.manager.patch(f"/api/tasks/{task_id}/assign", json={"assigned_to": self.e1_id})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["assigned_to"], self.e1_id)

        r = self.employee1.patch(f"/api/tasks/{task_id}/status", json={"status": "completed"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["is_completed"], True)
        self.assertEqual(r.get_json()["status"], "completed")

        r = self.manager.delete(f"/api/tasks/{task_id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.manager.get(f"/api/tasks/{task_id}").status_code, 404)

    def test_role_isolation_and_assignment_rules(self):
        task_id = self.new_task(assigned_to=self.e1_id).get_json()["id"]
        self.assertEqual(self.employee1.get(f"/api/tasks/{task_id}").status_code, 200)
        self.assertEqual(self.employee2.get(f"/api/tasks/{task_id}").status_code, 403)
        self.assertEqual(self.employee2.put(f"/api/tasks/{task_id}", json={"title": "hacked"}).status_code, 403)
        self.assertEqual(self.employee2.delete(f"/api/tasks/{task_id}").status_code, 403)
        self.assertEqual(self.employee2.patch(f"/api/tasks/{task_id}/status", json={"status": "completed"}).status_code, 403)
        self.assertEqual(self.employee1.patch(f"/api/tasks/{task_id}/assign", json={"assigned_to": self.e2_id}).status_code, 403)
        self.assertEqual(self.employee1.post("/api/tasks", json={"title": "invalid", "assigned_to": self.e2_id}).status_code, 403)
        self.assertEqual(self.employee2.get("/api/tasks").get_json(), [])
        self.assertEqual(self.employee1.get("/api/tasks").get_json()[0]["id"], task_id)

        # Reassignment immediately revokes the old employee's access.
        response = self.manager.patch(f"/api/tasks/{task_id}/assign", json={"assigned_to": self.e2_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.employee1.put(f"/api/tasks/{task_id}", json={"title": "no"}).status_code, 403)
        self.assertEqual(self.employee2.put(f"/api/tasks/{task_id}", json={"title": "yes"}).status_code, 200)

    def test_validation_and_unauthorized_requests(self):
        self.assertEqual(self.guest.get("/api/tasks").status_code, 401)
        self.assertEqual(self.guest.post("/api/tasks", json={"title": "hi"}).status_code, 401)
        self.assertEqual(self.new_task(title="  ").status_code, 400)
        self.assertEqual(self.new_task(due_date="2026-02-31").status_code, 400)
        self.assertEqual(self.new_task(priority="Urgent").status_code, 400)
        self.assertEqual(self.new_task(assigned_to=99999).status_code, 404)
        self.assertEqual(self.manager.get("/api/tasks?status=garbage").status_code, 400)
        task_id = self.new_task().get_json()["id"]
        self.assertEqual(self.manager.put(f"/api/tasks/{task_id}", json={"created_by": self.e2_id}).status_code, 400)
        self.assertEqual(self.manager.patch(f"/api/tasks/{task_id}/assign", json={"assigned_to": True}).status_code, 400)
        self.assertEqual(self.manager.patch(f"/api/tasks/{task_id}/status", json={"status": "finished"}).status_code, 400)

    def test_employee_created_task_and_filters(self):
        my_id = self.new_task(client=self.employee1, category="Personal", priority="Medium").get_json()["id"]
        self.assertEqual(self.employee1.put(f"/api/tasks/{my_id}", json={"title": "Updated myself"}).status_code, 200)
        r = self.employee1.get("/api/tasks?priority=Medium&category=Personal&search=Updated")
        self.assertEqual([item["id"] for item in r.get_json()], [my_id])
        r = self.employee1.patch(f"/api/tasks/{my_id}/status", json={"status": "in_progress"})
        self.assertEqual(r.get_json()["status"], "in_progress")
        self.assertEqual(len(self.employee1.get("/api/tasks?status=in_progress").get_json()), 1)
        self.assertEqual(self.employee1.get("/api/tasks?status=completed").get_json(), [])
        self.assertEqual(self.employee2.get("/api/tasks").get_json(), [])

    def test_legacy_sqlite_tasks_schema_upgrade(self):
        with auth.get_db() as db:
            db.execute("DROP TABLE tasks")
            db.execute("""CREATE TABLE tasks (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL,
                user_id INTEGER, is_completed INTEGER DEFAULT 0
            )""")
            db.execute(
                "INSERT INTO tasks (title, user_id, is_completed) VALUES (?, ?, ?)",
                ("Old completed task", self.e1_id, 1)
            )
        init_tasks_db()
        task = self.employee1.get("/api/tasks/1").get_json()
        self.assertEqual(task["created_by"], self.e1_id)
        self.assertTrue(task["is_completed"])
        self.assertEqual(task["status"], "completed")
        r = self.employee1.patch("/api/tasks/1/status", json={"status": "pending"})
        self.assertEqual(r.status_code, 200)
        with auth.get_db() as db:
            legacy_completed = db.execute("SELECT is_completed FROM tasks WHERE id=1").fetchone()[0]
        self.assertEqual(legacy_completed, 0)


if __name__ == "__main__":
    unittest.main()
