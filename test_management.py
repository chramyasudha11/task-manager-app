import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app import create_app


class ManagementApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "users.db"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "management-test-key",
                "DATABASE_PATH": str(self.database_path),
            }
        )
        self.client = self.app.test_client()
        self.client.post(
            "/api/signup",
            json={"name": "Casey Morgan", "email": "casey@example.test", "password": "password123"},
        )
        self.login()

    def tearDown(self):
        self.temp_dir.cleanup()

    def login(self, email="casey@example.test", password="password123"):
        return self.client.post("/api/login", json={"email": email, "password": password})

    def promote_to_admin(self):
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute("UPDATE users SET role = 'ADMIN' WHERE email = 'casey@example.test'")
            database.execute("UPDATE employees SET role = 'ADMIN' WHERE email = 'casey@example.test'")
            database.commit()
        self.client.post("/api/logout")
        self.login()

    def test_signup_employee_is_added_to_existing_workspace_database(self):
        response = self.client.get("/api/workspace")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["employees"], [])
        self.assertIsNotNone(body["currentEmployeeId"])
        with closing(sqlite3.connect(self.database_path)) as database:
            employee = database.execute(
                "SELECT email FROM employees WHERE id = ?",
                (body["currentEmployeeId"],),
            ).fetchone()
        self.assertEqual(employee[0], "casey@example.test")

    def test_configured_admin_email_promotes_an_existing_account(self):
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "admin-bootstrap-test-key",
                "DATABASE_PATH": str(self.database_path),
                "ADMIN_EMAIL": " CASEY@example.test ",
            }
        )
        client = app.test_client()

        self.assertEqual(client.post("/api/login", json={
            "email": "casey@example.test",
            "password": "password123",
        }).status_code, 200)
        self.assertEqual(client.post("/api/employees", json={
            "name": "New hire",
            "email": "new@example.test",
            "department": "Design",
            "title": "Designer",
        }).status_code, 201)

    def test_configured_admin_email_list_promotes_each_existing_account(self):
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                ("Jordan Lee", "jordan@example.test", "unused-password-hash"),
            )
            database.commit()
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "admin-list-bootstrap-test-key",
                "DATABASE_PATH": str(self.database_path),
                "ADMIN_EMAILS": " CASEY@example.test, jordan@example.test ",
            }
        )
        client = app.test_client()

        with closing(sqlite3.connect(self.database_path)) as database:
            roles = database.execute(
                "SELECT email, role FROM users WHERE email IN (?, ?) ORDER BY email",
                ("casey@example.test", "jordan@example.test"),
            ).fetchall()
            employee_roles = database.execute(
                "SELECT email, role FROM employees WHERE email IN (?, ?) ORDER BY email",
                ("casey@example.test", "jordan@example.test"),
            ).fetchall()
        self.assertEqual([row[1] for row in roles], ["ADMIN", "ADMIN"])
        self.assertEqual([row[1] for row in employee_roles], ["ADMIN", "ADMIN"])

    def test_employee_signup_links_to_an_employee_added_by_admin(self):
        self.promote_to_admin()
        created = self.client.post(
            "/api/employees",
            json={
                "name": "Jordan Lee",
                "email": "jordan@example.test",
                "department": "Design",
                "title": "Designer",
                "role": "EMPLOYEE",
            },
        )
        self.assertEqual(created.status_code, 201)
        employee_id = created.get_json()["employee"]["id"]
        self.client.post("/api/logout")
        signup = self.client.post(
            "/api/signup",
            json={"name": "Jordan Lee", "email": "jordan@example.test", "password": "password123"},
        )

        self.assertEqual(signup.status_code, 201)
        self.assertEqual(self.client.post("/api/login", json={
            "email": "jordan@example.test",
            "password": "password123",
        }).status_code, 200)
        self.assertEqual(
            self.client.get("/api/workspace").get_json()["currentEmployeeId"],
            employee_id,
        )

    def test_employee_can_only_view_assigned_tasks_and_cannot_manage_records(self):
        self.promote_to_admin()
        current_employee_id = self.client.get("/api/workspace").get_json()["employees"][0]["id"]
        other_employee = self.client.post(
            "/api/employees",
            json={
                "name": "Jordan Lee",
                "email": "jordan@example.test",
                "department": "Design",
                "title": "Designer",
                "role": "EMPLOYEE",
            },
        ).get_json()["employee"]
        project_id = self.client.post(
            "/api/projects",
            json={"name": "Private project", "status": "In Progress", "progress": 0},
        ).get_json()["project"]["id"]
        own_task = self.client.post(
            "/api/tasks",
            json={"name": "My task", "projectId": project_id, "assigneeId": current_employee_id},
        ).get_json()["task"]
        self.client.post(
            "/api/tasks",
            json={"name": "Other task", "projectId": project_id, "assigneeId": other_employee["id"]},
        )
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute("UPDATE users SET role = 'EMPLOYEE' WHERE email = 'casey@example.test'")
            database.execute("UPDATE employees SET role = 'EMPLOYEE' WHERE email = 'casey@example.test'")
            database.commit()
        self.client.post("/api/logout")
        self.login()

        workspace = self.client.get("/api/workspace").get_json()
        self.assertEqual(workspace["employees"], [])
        self.assertEqual(workspace["teams"], [])
        self.assertEqual(workspace["projects"], [])
        self.assertEqual([task["id"] for task in workspace["tasks"]], [own_task["id"]])
        self.assertEqual(workspace["tasks"][0]["projectName"], "Private project")
        self.assertEqual(workspace["tasks"][0]["assigneeId"], workspace["currentEmployeeId"])
        self.assertEqual([task["id"] for task in self.client.get("/api/tasks").get_json()["tasks"]], [own_task["id"]])
        self.assertEqual(self.client.get("/api/employees").status_code, 403)
        self.assertEqual(self.client.get("/api/teams").status_code, 403)
        self.assertEqual(self.client.get("/api/projects").status_code, 403)
        self.assertEqual(
            self.client.post("/api/teams", json={"name": "Restricted"}).status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/api/employees", json={"name": "Restricted"}).status_code,
            403,
        )

    def test_admin_can_create_update_and_deactivate_employee(self):
        self.promote_to_admin()
        created = self.client.post(
            "/api/employees",
            json={
                "name": "Jordan Lee",
                "email": "jordan@example.test",
                "department": "Design",
                "title": "Designer",
                "role": "MANAGER",
                "status": "Active",
                "startDate": "2025-01-15",
            },
        )
        self.assertEqual(created.status_code, 201)
        employee_id = created.get_json()["employee"]["id"]

        updated = self.client.patch(
            f"/api/employees/{employee_id}/status",
            json={"status": "Inactive"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["employee"]["status"], "Inactive")

    def test_admin_can_create_and_manage_team_project_and_task(self):
        self.promote_to_admin()
        employee = self.client.get("/api/workspace").get_json()["employees"][0]
        team = self.client.post(
            "/api/teams",
            json={"name": "Delivery", "description": "Core delivery team", "managerId": employee["id"], "memberIds": [employee["id"]]},
        )
        self.assertEqual(team.status_code, 201)
        team_id = team.get_json()["team"]["id"]

        project = self.client.post(
            "/api/projects",
            json={
                "name": "Website launch",
                "teamId": team_id,
                "managerId": employee["id"],
                "status": "In Progress",
                "progress": 25,
                "startDate": "2025-01-01",
                "dueDate": "2025-04-01",
            },
        )
        self.assertEqual(project.status_code, 201)
        project_id = project.get_json()["project"]["id"]

        task = self.client.post(
            "/api/tasks",
            json={
                "name": "Prepare release",
                "projectId": project_id,
                "assigneeId": employee["id"],
                "priority": "High",
                "status": "Not Started",
            },
        )
        self.assertEqual(task.status_code, 201)
        self.assertEqual(task.get_json()["task"]["assigneeId"], employee["id"])
        task_id = task.get_json()["task"]["id"]
        another_task = self.client.post(
            "/api/tasks",
            json={"name": "Second task", "status": "In Progress"},
        ).get_json()["task"]
        expected_task_ids = {task_id, another_task["id"]}
        self.assertEqual(
            {item["id"] for item in self.client.get("/api/tasks").get_json()["tasks"]},
            expected_task_ids,
        )
        self.assertEqual(
            {item["id"] for item in self.client.get("/api/workspace").get_json()["tasks"]},
            expected_task_ids,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/tasks/{task_id}",
                json={"name": "Prepare final release", "status": "In Progress"},
            ).status_code,
            200,
        )

        self.assertEqual(
            self.client.patch(f"/api/projects/{project_id}", json={"name": "Launch"}).status_code,
            200,
        )
        self.assertEqual(self.client.delete(f"/api/teams/{team_id}").status_code, 200)
        self.assertIsNone(self.client.get("/api/workspace").get_json()["projects"][0]["teamId"])
        self.assertEqual(self.client.delete(f"/api/projects/{project_id}").status_code, 200)
        self.assertIsNone(self.client.get("/api/workspace").get_json()["tasks"][0]["projectId"])
        self.assertEqual(self.client.delete(f"/api/tasks/{another_task['id']}").status_code, 200)

    def test_employee_can_only_complete_their_assigned_task(self):
        self.promote_to_admin()
        workspace = self.client.get("/api/workspace").get_json()
        employee_id = workspace["employees"][0]["id"]
        project = self.client.post(
            "/api/projects",
            json={"name": "Project", "status": "In Progress", "progress": 0},
        ).get_json()["project"]
        task = self.client.post(
            "/api/tasks",
            json={
                "name": "Assigned task",
                "projectId": project["id"],
                "assigneeId": employee_id,
                "status": "Not Started",
            },
        ).get_json()["task"]

        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute("UPDATE users SET role = 'EMPLOYEE' WHERE email = 'casey@example.test'")
            database.execute("UPDATE employees SET role = 'EMPLOYEE' WHERE email = 'casey@example.test'")
            database.commit()
        self.client.post("/api/logout")
        self.login()

        response = self.client.patch(f"/api/tasks/{task['id']}", json={"status": "Completed"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["task"]["status"], "Completed")
        self.assertEqual(
            self.client.patch(f"/api/tasks/{task['id']}", json={"name": "Changed"}).status_code,
            403,
        )

    def test_manager_cannot_use_admin_task_edit_endpoint(self):
        self.promote_to_admin()
        task = self.client.post(
            "/api/tasks",
            json={"name": "Admin task"},
        ).get_json()["task"]
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute("UPDATE users SET role = 'MANAGER' WHERE email = 'casey@example.test'")
            database.commit()
        self.assertEqual(
            self.client.patch(f"/api/tasks/{task['id']}", json={"name": "Unauthorized edit"}).status_code,
            403,
        )

    def test_invalid_project_progress_is_rejected(self):
        self.promote_to_admin()
        response = self.client.post(
            "/api/projects",
            json={"name": "Invalid", "status": "In Progress", "progress": 101},
        )
        self.assertEqual(response.status_code, 400)

    def test_management_endpoints_require_authentication(self):
        self.client.post("/api/logout")
        self.assertEqual(self.client.get("/api/workspace").status_code, 401)
        self.assertEqual(self.client.post("/api/tasks", json={"name": "No access"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
