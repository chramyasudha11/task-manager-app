import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app import create_app


class TaskWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "users.db"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "workspace-test-key",
                "DATABASE_PATH": str(self.database_path),
            }
        )
        self.client = self.app.test_client()

        # Create admin user
        self.client.post(
            "/api/signup",
            json={"name": "Admin User", "email": "admin@example.test", "password": "password123"},
        )
        with closing(sqlite3.connect(self.database_path)) as db:
            db.execute("UPDATE users SET role = 'ADMIN' WHERE email = 'admin@example.test'")
            db.execute("UPDATE employees SET role = 'ADMIN' WHERE email = 'admin@example.test'")
            db.commit()

        # Login as admin to prepare employees and projects
        self.client.post("/api/login", json={"email": "admin@example.test", "password": "password123"})
        emp_res = self.client.post(
            "/api/employees",
            json={
                "name": "Alex Employee",
                "email": "alex@example.test",
                "department": "Engineering",
                "title": "Engineer",
            },
        )
        self.employee_id = emp_res.get_json()["employee"]["id"]

        emp2_res = self.client.post(
            "/api/employees",
            json={
                "name": "Sam Employee",
                "email": "sam@example.test",
                "department": "Design",
                "title": "Designer",
            },
        )
        self.employee2_id = emp2_res.get_json()["employee"]["id"]

        proj_res = self.client.post(
            "/api/projects",
            json={"name": "Core Platform", "status": "In Progress", "progress": 50},
        )
        self.project_id = proj_res.get_json()["project"]["id"]

    def tearDown(self):
        self.temp_dir.cleanup()

    def login_as_admin(self):
        self.client.post("/api/logout")
        return self.client.post("/api/login", json={"email": "admin@example.test", "password": "password123"})

    def login_as_employee(self, email="alex@example.test"):
        self.client.post("/api/logout")
        # Employee signup links to employee record
        self.client.post("/api/signup", json={"name": "Alex", "email": email, "password": "password123"})
        return self.client.post("/api/login", json={"email": email, "password": "password123"})

    def test_kanban_task_retrieval_and_status_normalization(self):
        self.login_as_admin()

        # Create tasks in different states
        t1 = self.client.post(
            "/api/tasks",
            json={
                "name": "Task 1",
                "projectId": self.project_id,
                "assigneeId": self.employee_id,
                "priority": "High",
                "status": "To Do",  # Should normalize to "Not Started"
                "description": "Task 1 description",
            },
        )
        self.assertEqual(t1.status_code, 201)
        body1 = t1.get_json()["task"]
        self.assertEqual(body1["status"], "Not Started")
        self.assertEqual(body1["description"], "Task 1 description")

        t2 = self.client.post(
            "/api/tasks",
            json={
                "name": "Task 2",
                "projectId": self.project_id,
                "assigneeId": self.employee_id,
                "priority": "Medium",
                "status": "In Progress",
            },
        )
        self.assertEqual(t2.status_code, 201)

        t3 = self.client.post(
            "/api/tasks",
            json={
                "name": "Task 3",
                "projectId": self.project_id,
                "assigneeId": self.employee_id,
                "priority": "Low",
                "status": "Completed",
            },
        )
        self.assertEqual(t3.status_code, 201)

        tasks_res = self.client.get("/api/tasks")
        self.assertEqual(tasks_res.status_code, 200)
        tasks = tasks_res.get_json()["tasks"]
        self.assertEqual(len(tasks), 3)

        # Verify all kanban statuses are present
        statuses = {t["status"] for t in tasks}
        self.assertEqual(statuses, {"Not Started", "In Progress", "Completed"})

    def test_drag_and_drop_status_movement(self):
        self.login_as_admin()
        task = self.client.post(
            "/api/tasks",
            json={"name": "DND Task", "status": "Not Started", "assigneeId": self.employee_id},
        ).get_json()["task"]

        # Move to In Progress
        res = self.client.patch(f"/api/tasks/{task['id']}", json={"status": "In Progress"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["task"]["status"], "In Progress")

        # Move to Completed
        res = self.client.patch(f"/api/tasks/{task['id']}", json={"status": "Completed"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["task"]["status"], "Completed")

        # Move back to To Do
        res = self.client.patch(f"/api/tasks/{task['id']}", json={"status": "To Do"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["task"]["status"], "Not Started")

    def test_employee_can_only_move_own_task(self):
        self.login_as_admin()
        task_alex = self.client.post(
            "/api/tasks",
            json={"name": "Alex Task", "assigneeId": self.employee_id, "status": "Not Started"},
        ).get_json()["task"]
        task_sam = self.client.post(
            "/api/tasks",
            json={"name": "Sam Task", "assigneeId": self.employee2_id, "status": "Not Started"},
        ).get_json()["task"]

        self.login_as_employee("alex@example.test")

        # Alex can update Alex's task
        res = self.client.patch(f"/api/tasks/{task_alex['id']}", json={"status": "In Progress"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["task"]["status"], "In Progress")

        # Alex cannot update Sam's task
        res = self.client.patch(f"/api/tasks/{task_sam['id']}", json={"status": "In Progress"})
        self.assertEqual(res.status_code, 403)

    def test_task_detail_modal_endpoint(self):
        self.login_as_admin()
        task = self.client.post(
            "/api/tasks",
            json={
                "name": "Detailed Task",
                "description": "Comprehensive spec",
                "projectId": self.project_id,
                "assigneeId": self.employee_id,
                "dueDate": "2026-11-01",
                "priority": "High",
                "status": "In Progress",
            },
        ).get_json()["task"]

        res = self.client.get(f"/api/tasks/{task['id']}")
        self.assertEqual(res.status_code, 200)
        detail = res.get_json()["task"]
        self.assertEqual(detail["id"], task["id"])
        self.assertEqual(detail["name"], "Detailed Task")
        self.assertEqual(detail["description"], "Comprehensive spec")
        self.assertEqual(detail["dueDate"], "2026-11-01")
        self.assertIn("comments", detail)
        self.assertIn("activities", detail)

    def test_comments_and_activity_timeline(self):
        self.login_as_admin()
        task = self.client.post(
            "/api/tasks",
            json={"name": "Comment Task", "assigneeId": self.employee_id},
        ).get_json()["task"]

        # Post a comment as Admin
        c1 = self.client.post(
            f"/api/tasks/{task['id']}/comments",
            json={"content": "Please prioritize this today."},
        )
        self.assertEqual(c1.status_code, 201)
        comment_data = c1.get_json()["comment"]
        self.assertEqual(comment_data["content"], "Please prioritize this today.")
        self.assertEqual(comment_data["authorName"], "Admin User")

        # Post a comment as Employee
        self.login_as_employee("alex@example.test")
        c2 = self.client.post(
            f"/api/tasks/{task['id']}/comments",
            json={"content": "Working on it now!"},
        )
        self.assertEqual(c2.status_code, 201)

        # List comments
        comments_res = self.client.get(f"/api/tasks/{task['id']}/comments")
        self.assertEqual(comments_res.status_code, 200)
        comments = comments_res.get_json()["comments"]
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]["content"], "Please prioritize this today.")
        self.assertEqual(comments[1]["content"], "Working on it now!")

        # List activities
        activities_res = self.client.get(f"/api/tasks/{task['id']}/activities")
        self.assertEqual(activities_res.status_code, 200)
        activities = activities_res.get_json()["activities"]
        self.assertGreaterEqual(len(activities), 2)
        actions = [a["action"] for a in activities]
        self.assertIn("comment_added", actions)

    def test_recurring_task_controls_and_auto_generation(self):
        self.login_as_admin()

        # Create a weekly recurring task
        task = self.client.post(
            "/api/tasks",
            json={
                "name": "Weekly Sync Preparation",
                "dueDate": "2026-10-23",
                "priority": "Medium",
                "status": "In Progress",
                "isRecurring": True,
                "recurrenceInterval": "weekly",
            },
        ).get_json()["task"]

        self.assertTrue(task["isRecurring"])
        self.assertEqual(task["recurrenceInterval"], "weekly")

        # Complete the task
        res = self.client.patch(f"/api/tasks/{task['id']}", json={"status": "Completed"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["task"]["status"], "Completed")

        # Check that the next instance was automatically generated
        all_tasks = self.client.get("/api/tasks").get_json()["tasks"]
        self.assertEqual(len(all_tasks), 2)

        # Find the new recurring task
        new_task = next(t for t in all_tasks if t["id"] != task["id"])
        self.assertEqual(new_task["name"], "Weekly Sync Preparation")
        self.assertEqual(new_task["status"], "Not Started")
        self.assertEqual(new_task["dueDate"], "2026-10-30")  # +7 days
        self.assertTrue(new_task["isRecurring"])
        self.assertEqual(new_task["recurrenceInterval"], "weekly")

    def test_recurring_task_stops_at_end_date(self):
        self.login_as_admin()

        # Create a daily recurring task with end date today
        task = self.client.post(
            "/api/tasks",
            json={
                "name": "Temporary Daily Check",
                "dueDate": "2026-10-23",
                "status": "In Progress",
                "isRecurring": True,
                "recurrenceInterval": "daily",
                "recurrenceEndDate": "2026-10-23",
            },
        ).get_json()["task"]

        # Complete the task
        res = self.client.patch(f"/api/tasks/{task['id']}", json={"status": "Completed"})
        self.assertEqual(res.status_code, 200)

        # Next due date (2026-10-24) exceeds recurrenceEndDate (2026-10-23), so no new task should be generated
        all_tasks = self.client.get("/api/tasks").get_json()["tasks"]
        self.assertEqual(len(all_tasks), 1)

    def test_bulk_task_actions(self):
        self.login_as_admin()

        t1 = self.client.post("/api/tasks", json={"name": "Bulk 1", "assigneeId": self.employee_id, "status": "Not Started"}).get_json()["task"]
        t2 = self.client.post("/api/tasks", json={"name": "Bulk 2", "assigneeId": self.employee_id, "status": "Not Started"}).get_json()["task"]
        t3 = self.client.post("/api/tasks", json={"name": "Bulk 3", "assigneeId": self.employee_id, "status": "Not Started"}).get_json()["task"]

        task_ids = [t1["id"], t2["id"], t3["id"]]

        # Bulk status update
        bulk_res = self.client.post(
            "/api/tasks/bulk",
            json={"taskIds": task_ids, "action": "status", "status": "In Progress"},
        )
        self.assertEqual(bulk_res.status_code, 200)
        self.assertEqual(bulk_res.get_json()["updatedCount"], 3)

        updated_tasks = self.client.get("/api/tasks").get_json()["tasks"]
        for t in updated_tasks:
            if t["id"] in task_ids:
                self.assertEqual(t["status"], "In Progress")

        # Bulk reassign (Admin)
        reassign_res = self.client.post(
            "/api/tasks/bulk",
            json={"taskIds": task_ids, "action": "assign", "assigneeId": self.employee2_id},
        )
        self.assertEqual(reassign_res.status_code, 200)
        updated_tasks = self.client.get("/api/tasks").get_json()["tasks"]
        for t in updated_tasks:
            if t["id"] in task_ids:
                self.assertEqual(t["assigneeId"], self.employee2_id)

        # Bulk delete (Admin)
        delete_res = self.client.post(
            "/api/tasks/bulk",
            json={"taskIds": [t1["id"], t2["id"]], "action": "delete"},
        )
        self.assertEqual(delete_res.status_code, 200)
        remaining = self.client.get("/api/tasks").get_json()["tasks"]
        remaining_ids = {t["id"] for t in remaining}
        self.assertNotIn(t1["id"], remaining_ids)
        self.assertNotIn(t2["id"], remaining_ids)
        self.assertIn(t3["id"], remaining_ids)

    def test_bulk_action_employee_permissions(self):
        self.login_as_admin()
        t_alex = self.client.post("/api/tasks", json={"name": "Alex Task", "assigneeId": self.employee_id, "status": "Not Started"}).get_json()["task"]
        t_sam = self.client.post("/api/tasks", json={"name": "Sam Task", "assigneeId": self.employee2_id, "status": "Not Started"}).get_json()["task"]

        self.login_as_employee("alex@example.test")

        # Employee can bulk update own tasks
        res = self.client.post(
            "/api/tasks/bulk",
            json={"taskIds": [t_alex["id"]], "action": "status", "status": "Completed"},
        )
        self.assertEqual(res.status_code, 200)

        # Employee cannot bulk update other's task
        res = self.client.post(
            "/api/tasks/bulk",
            json={"taskIds": [t_alex["id"], t_sam["id"]], "action": "status", "status": "Completed"},
        )
        self.assertEqual(res.status_code, 403)

        # Employee cannot bulk assign or delete
        res = self.client.post(
            "/api/tasks/bulk",
            json={"taskIds": [t_alex["id"]], "action": "delete"},
        )
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
