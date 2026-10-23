"""Run with: python -m unittest discover -s tests -v"""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import auth
from tasks import (
    create_tasks_app,
    init_tasks_db,
    _db,
)


class TaskApiTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.dir.name) / "users.db")
        self.app = create_tasks_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret",
            "DATABASE_PATH": self.database_path,
        })
        self.manager = self.app.test_client()
        self.employee1 = self.app.test_client()
        self.employee2 = self.app.test_client()
        self.guest = self.app.test_client()
        self.manager_id = self.add_user(self.manager, "manager", "MANAGER")
        self.e1_id = self.add_user(self.employee1, "employee1", "EMPLOYEE")
        self.e2_id = self.add_user(self.employee2, "employee2", "EMPLOYEE")

    def tearDown(self):
        self.dir.cleanup()

    def add_user(self, client, username, role):
        email = f"{username}@example.com"
        response = client.post("/api/signup", json={
            "name": username, "email": email, "password": "Test12345!"
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        with self.app.app_context():
            with _db() as db:
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
        with self.app.app_context():
            with _db() as conn:
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
        with self.app.app_context():
            with _db() as db:
                db.execute("DROP TABLE tasks")
                db.execute("""CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL,
                    user_id INTEGER, is_completed INTEGER DEFAULT 0
                )""")
                db.execute(
                    "INSERT INTO tasks (title, user_id, is_completed) VALUES (?, ?, ?)",
                    ("Old completed task", self.e1_id, 1)
                )
            init_tasks_db(self.app)
        task = self.employee1.get("/api/tasks/1").get_json()
        self.assertEqual(task["created_by"], self.e1_id)
        self.assertTrue(task["is_completed"])
        self.assertEqual(task["status"], "completed")
        r = self.employee1.patch("/api/tasks/1/status", json={"status": "pending"})
        self.assertEqual(r.status_code, 200)
        with self.app.app_context():
            with _db() as db:
                legacy_completed = db.execute("SELECT is_completed FROM tasks WHERE id=1").fetchone()[0]
        self.assertEqual(legacy_completed, 0)

    # ==========================================
    # Member 2 Advanced Feature Tests
    # ==========================================

    def test_task_pagination_and_metadata(self):
        for i in range(5):
            self.new_task(title=f"Task {i}", priority="Medium")

        # Unpaginated default returns plain list
        unpaginated = self.manager.get("/api/tasks").get_json()
        self.assertIsInstance(unpaginated, list)
        self.assertEqual(len(unpaginated), 5)

        # Page 1, limit 2
        r1 = self.manager.get("/api/tasks?page=1&limit=2")
        self.assertEqual(r1.status_code, 200)
        data1 = r1.get_json()
        self.assertIn("tasks", data1)
        self.assertEqual(len(data1["tasks"]), 2)
        self.assertEqual(data1["total"], 5)
        self.assertEqual(data1["page"], 1)
        self.assertEqual(data1["limit"], 2)
        self.assertEqual(data1["total_pages"], 3)
        self.assertTrue(data1["has_next"])
        self.assertFalse(data1["has_prev"])
        self.assertEqual(r1.headers.get("X-Total-Count"), "5")
        self.assertEqual(r1.headers.get("X-Page"), "1")
        self.assertEqual(r1.headers.get("X-Per-Page"), "2")

        # Page 3, limit 2 (last page)
        r3 = self.manager.get("/api/tasks?page=3&limit=2")
        data3 = r3.get_json()
        self.assertEqual(len(data3["tasks"]), 1)
        self.assertEqual(data3["page"], 3)
        self.assertFalse(data3["has_next"])
        self.assertTrue(data3["has_prev"])

        # Page beyond total
        r4 = self.manager.get("/api/tasks?page=10&limit=2")
        data4 = r4.get_json()
        self.assertEqual(len(data4["tasks"]), 0)

    def test_task_pagination_validation(self):
        self.assertEqual(self.manager.get("/api/tasks?page=0").status_code, 400)
        self.assertEqual(self.manager.get("/api/tasks?page=-1").status_code, 400)
        self.assertEqual(self.manager.get("/api/tasks?page=abc").status_code, 400)
        self.assertEqual(self.manager.get("/api/tasks?limit=0").status_code, 400)
        self.assertEqual(self.manager.get("/api/tasks?limit=101").status_code, 400)
        self.assertEqual(self.manager.get("/api/tasks?limit=bad").status_code, 400)

    def test_advanced_status_and_priority_filters(self):
        t1 = self.new_task(title="T1", priority="High").get_json()["id"]
        t2 = self.new_task(title="T2", priority="Medium").get_json()["id"]
        t3 = self.new_task(title="T3", priority="Low").get_json()["id"]

        self.manager.patch(f"/api/tasks/{t1}/status", json={"status": "in_progress"})
        self.manager.patch(f"/api/tasks/{t2}/status", json={"status": "completed"})
        # t3 remains pending

        # Comma-separated status filtering
        r = self.manager.get("/api/tasks?status=in_progress,completed")
        self.assertEqual(r.status_code, 200)
        ids = [item["id"] for item in r.get_json()]
        self.assertIn(t1, ids)
        self.assertIn(t2, ids)
        self.assertNotIn(t3, ids)

        # Comma-separated priority filtering
        r = self.manager.get("/api/tasks?priority=High,Low")
        self.assertEqual(r.status_code, 200)
        ids = [item["id"] for item in r.get_json()]
        self.assertIn(t1, ids)
        self.assertIn(t3, ids)
        self.assertNotIn(t2, ids)

        # Combined status and priority
        r = self.manager.get("/api/tasks?status=pending&priority=Low")
        self.assertEqual(r.status_code, 200)
        ids = [item["id"] for item in r.get_json()]
        self.assertEqual(ids, [t3])

        # Invalid comma-separated values fail validation
        self.assertEqual(self.manager.get("/api/tasks?status=pending,badstatus").status_code, 400)
        self.assertEqual(self.manager.get("/api/tasks?priority=High,Critical").status_code, 400)

    def test_advanced_date_filters_and_overdue(self):
        today = date.today()
        yesterday = (today - timedelta(days=1)).isoformat()
        tomorrow = (today + timedelta(days=1)).isoformat()
        next_week = (today + timedelta(days=7)).isoformat()

        t_past = self.new_task(title="Past", due_date=yesterday).get_json()["id"]
        t_soon = self.new_task(title="Soon", due_date=tomorrow).get_json()["id"]
        t_future = self.new_task(title="Future", due_date=next_week).get_json()["id"]

        # due_before
        r = self.manager.get(f"/api/tasks?due_before={tomorrow}")
        self.assertEqual(r.status_code, 200)
        ids = [item["id"] for item in r.get_json()]
        self.assertIn(t_past, ids)
        self.assertIn(t_soon, ids)
        self.assertNotIn(t_future, ids)

        # due_after
        r = self.manager.get(f"/api/tasks?due_after={tomorrow}")
        self.assertEqual(r.status_code, 200)
        ids = [item["id"] for item in r.get_json()]
        self.assertNotIn(t_past, ids)
        self.assertIn(t_soon, ids)
        self.assertIn(t_future, ids)

        # Overdue filter (due < today and status != completed)
        r = self.manager.get("/api/tasks?overdue=true")
        self.assertEqual(r.status_code, 200)
        ids = [item["id"] for item in r.get_json()]
        self.assertIn(t_past, ids)
        self.assertNotIn(t_soon, ids)

        # Completed past task is not overdue
        self.manager.patch(f"/api/tasks/{t_past}/status", json={"status": "completed"})
        r = self.manager.get("/api/tasks?overdue=true")
        ids = [item["id"] for item in r.get_json()]
        self.assertNotIn(t_past, ids)

        # Invalid date format validation
        self.assertEqual(self.manager.get("/api/tasks?due_before=invalid-date").status_code, 400)
        self.assertEqual(self.manager.get("/api/tasks?due_after=2026-15-40").status_code, 400)

    def test_bulk_task_updates(self):
        t1 = self.new_task(title="Bulk 1", priority="Low").get_json()["id"]
        t2 = self.new_task(title="Bulk 2", priority="Low").get_json()["id"]
        t3 = self.new_task(title="Bulk 3", priority="Low").get_json()["id"]

        # Bulk update priority and status
        r = self.manager.patch("/api/tasks/bulk", json={
            "task_ids": [t1, t2],
            "updates": {
                "priority": "High",
                "status": "in_progress",
            }
        })
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["updated_count"], 2)

        check1 = self.manager.get(f"/api/tasks/{t1}").get_json()
        check2 = self.manager.get(f"/api/tasks/{t2}").get_json()
        check3 = self.manager.get(f"/api/tasks/{t3}").get_json()
        self.assertEqual(check1["priority"], "High")
        self.assertEqual(check1["status"], "in_progress")
        self.assertEqual(check2["priority"], "High")
        self.assertEqual(check3["priority"], "Low")

        # Bulk assign by manager
        r = self.manager.post("/api/tasks/bulk-update", json={
            "task_ids": [t1, t2],
            "assigned_to": self.e1_id,
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.manager.get(f"/api/tasks/{t1}").get_json()["assigned_to"], self.e1_id)

        # Employee cannot reassign tasks
        r = self.employee1.patch("/api/tasks/bulk", json={
            "task_ids": [t1],
            "assigned_to": self.e2_id,
        })
        self.assertEqual(r.status_code, 403)

        # Employee cannot update another employee's task
        r = self.employee2.patch("/api/tasks/bulk", json={
            "task_ids": [t1],
            "status": "completed",
        })
        self.assertEqual(r.status_code, 403)

    def test_bulk_update_validation(self):
        self.assertEqual(self.manager.patch("/api/tasks/bulk", json={}).status_code, 400)
        self.assertEqual(self.manager.patch("/api/tasks/bulk", json={"task_ids": []}).status_code, 400)
        self.assertEqual(self.manager.patch("/api/tasks/bulk", json={"task_ids": ["abc"]}).status_code, 400)
        self.assertEqual(self.manager.patch("/api/tasks/bulk", json={"task_ids": [1], "updates": {}}).status_code, 400)
        self.assertEqual(self.manager.patch("/api/tasks/bulk", json={
            "task_ids": [1], "updates": {"id": 99}
        }).status_code, 400)
        self.assertEqual(self.manager.patch("/api/tasks/bulk", json={
            "task_ids": [99999], "status": "completed"
        }).status_code, 404)

    def test_recurring_task_creation_and_auto_next_generation(self):
        # Create weekly recurring task
        r = self.manager.post("/api/tasks", json={
            "title": "Weekly Sprint Review",
            "due_date": "2026-10-10",
            "recurrence": "weekly",
            "recurrence_interval": 1,
        })
        self.assertEqual(r.status_code, 201)
        task = r.get_json()
        task_id = task["id"]
        self.assertEqual(task["recurrence_pattern"], "weekly")
        self.assertEqual(task["recurrence_interval"], 1)

        # Complete task - triggers next occurrence (2026-10-17)
        r = self.manager.patch(f"/api/tasks/{task_id}/status", json={"status": "completed"})
        self.assertEqual(r.status_code, 200)

        tasks = self.manager.get("/api/tasks").get_json()
        self.assertEqual(len(tasks), 2)
        next_task = next(t for t in tasks if t["id"] != task_id)
        self.assertEqual(next_task["title"], "Weekly Sprint Review")
        self.assertEqual(next_task["status"], "pending")
        self.assertEqual(next_task["due_date"], "2026-10-17")
        self.assertEqual(next_task["parent_task_id"], task_id)

    def test_recurring_task_respects_end_date(self):
        r = self.manager.post("/api/tasks", json={
            "title": "Daily Standup",
            "due_date": "2026-10-20",
            "recurrence": "daily",
            "recurrence_end_date": "2026-10-20",  # Ends on this day
        })
        self.assertEqual(r.status_code, 201)
        task_id = r.get_json()["id"]

        # Completing this task should not spawn next because next due date (2026-10-21) > end_date
        self.manager.patch(f"/api/tasks/{task_id}/status", json={"status": "completed"})
        tasks = self.manager.get("/api/tasks").get_json()
        self.assertEqual(len(tasks), 1)

    def test_recurring_validation(self):
        # Invalid recurrence pattern
        self.assertEqual(self.new_task(recurrence="hourly").status_code, 400)
        # Invalid interval
        self.assertEqual(self.new_task(recurrence="daily", recurrence_interval=0).status_code, 400)
        self.assertEqual(self.new_task(recurrence="daily", recurrence_interval="two").status_code, 400)
        # End date earlier than due date
        self.assertEqual(self.new_task(
            due_date="2026-10-30",
            recurrence="daily",
            recurrence_end_date="2026-10-10"
        ).status_code, 400)

    def test_task_duplication(self):
        orig_id = self.new_task(
            title="Original Task",
            description="Detailed notes",
            priority="High",
            category="Work",
            due_date="2026-11-15",
            assigned_to=self.e1_id,
        ).get_json()["id"]

        # Duplicate with default title
        r = self.manager.post(f"/api/tasks/{orig_id}/duplicate")
        self.assertEqual(r.status_code, 201)
        dup = r.get_json()
        self.assertNotEqual(dup["id"], orig_id)
        self.assertEqual(dup["title"], "Copy of Original Task")
        self.assertEqual(dup["description"], "Detailed notes")
        self.assertEqual(dup["priority"], "High")
        self.assertEqual(dup["category"], "Work")
        self.assertEqual(dup["status"], "pending")
        self.assertFalse(dup["is_completed"])
        self.assertEqual(dup["assigned_to"], self.e1_id)
        self.assertEqual(dup["created_by"], self.manager_id)

        # Duplicate with overrides
        r = self.manager.post(f"/api/tasks/{orig_id}/copy", json={
            "title": "Custom Duplicate Title",
            "priority": "Low",
            "due_date": "2026-12-01",
        })
        self.assertEqual(r.status_code, 201)
        dup2 = r.get_json()
        self.assertEqual(dup2["title"], "Custom Duplicate Title")
        self.assertEqual(dup2["priority"], "Low")
        self.assertEqual(dup2["due_date"], "2026-12-01")

        # Employee duplication permission: cannot assign to another employee
        e1_task_id = self.new_task(client=self.employee1, title="E1 Task").get_json()["id"]
        r = self.employee1.post(f"/api/tasks/{e1_task_id}/duplicate", json={
            "assigned_to": self.e2_id
        })
        self.assertEqual(r.status_code, 403)

        # Duplicate non-existent task
        self.assertEqual(self.manager.post("/api/tasks/99999/duplicate").status_code, 404)

    def test_improved_input_validation(self):
        # Description length boundary (> 5000 chars)
        self.assertEqual(self.new_task(description="x" * 5001).status_code, 400)
        self.assertEqual(self.new_task(description="x" * 5000).status_code, 201)

        # Title length boundary (> 200 chars)
        self.assertEqual(self.new_task(title="a" * 201).status_code, 400)
        self.assertEqual(self.new_task(title="a" * 200).status_code, 201)

        # Category length boundary (> 80 chars)
        self.assertEqual(self.new_task(category="c" * 81).status_code, 400)

        # Non-JSON or empty payload errors
        self.assertEqual(
            self.manager.post("/api/tasks", data="not json", content_type="application/json").status_code,
            400
        )
        self.assertEqual(self.manager.post("/api/tasks", json={}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
