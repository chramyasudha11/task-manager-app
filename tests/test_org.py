"""Member 4 + 5 tests. Run: python -m unittest discover -s tests -v"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import auth
from app import app, init_all


class OrgTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.old = auth.DB_NAME
        auth.DB_NAME = os.path.join(self.dir.name, "users.db")
        app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
        init_all()
        self.admin, self.mgr, self.emp = app.test_client(), app.test_client(), app.test_client()
        self.admin_id = self.user(self.admin, "admin", "ADMIN")
        self.mgr_id = self.user(self.mgr, "ramya", "MANAGER")
        self.emp_id = self.user(self.emp, "rahul", "EMPLOYEE")

    def tearDown(self):
        auth.DB_NAME = self.old
        self.dir.cleanup()

    def user(self, client, name, role):
        email = f"{name}@example.com"
        client.post("/api/signup", json={"name": name, "email": email, "password": "Test12345!"})
        with auth.get_db() as c:
            c.execute("UPDATE users SET role = ? WHERE email = ?", (role, email))
        r = client.post("/api/login", json={"email": email, "password": "Test12345!"})
        self.assertEqual(r.status_code, 200)
        return r.get_json()["user"]["id"]

    def make_project(self):
        team = self.admin.post("/api/teams", json={"name": "Core", "manager_id": self.mgr_id,
                                                  "member_ids": [self.emp_id]}).get_json()
        proj = self.admin.post("/api/projects", json={"name": "CRM System", "team_id": team["id"]})
        self.assertEqual(proj.status_code, 201)
        return team, proj.get_json()

    # ---- employees
    def test_employee_crud_and_permissions(self):
        r = self.admin.post("/api/employees", json={"name": "Priya", "email": "priya@example.com",
                                                    "password": "Secret123!", "department": "QA"})
        self.assertEqual(r.status_code, 201)
        eid = r.get_json()["id"]
        self.assertEqual(self.admin.post("/api/employees", json={"name": "X", "email": "priya@example.com",
                                                                 "password": "Secret123!"}).status_code, 409)
        self.assertEqual(self.admin.put(f"/api/employees/{eid}", json={"designation": "Tester"}).get_json()["designation"], "Tester")
        self.assertEqual(self.admin.get(f"/api/employees/{eid}").status_code, 200)
        self.assertEqual(self.mgr.get("/api/employees").status_code, 403)
        self.assertEqual(self.emp.post("/api/employees", json={}).status_code, 403)
        self.assertEqual(self.mgr.get("/api/employees/options").status_code, 200)
        self.assertEqual(self.emp.get("/api/employees/options").status_code, 403)

    def test_deactivate_blocks_login_and_session(self):
        eid = self.admin.post("/api/employees", json={"name": "Arjun", "email": "arjun@example.com",
                                                      "password": "Secret123!"}).get_json()["id"]
        c = app.test_client()
        self.assertEqual(c.post("/api/login", json={"email": "arjun@example.com", "password": "Secret123!"}).status_code, 200)
        self.assertEqual(self.admin.patch(f"/api/employees/{eid}/deactivate").status_code, 200)
        self.assertEqual(c.get("/api/me").status_code, 401)
        self.assertEqual(app.test_client().post("/api/login", json={"email": "arjun@example.com", "password": "Secret123!"}).status_code, 403)
        self.admin.patch(f"/api/employees/{eid}/activate")
        self.assertEqual(app.test_client().post("/api/login", json={"email": "arjun@example.com", "password": "Secret123!"}).status_code, 200)
        self.assertEqual(self.admin.patch(f"/api/employees/{self.admin_id}/deactivate").status_code, 400)

    # ---- teams
    def test_team_members_and_manager(self):
        team = self.admin.post("/api/teams", json={"name": "Alpha"}).get_json()
        tid = team["id"]
        self.assertEqual(self.admin.post(f"/api/teams/{tid}/members", json={"user_id": self.emp_id}).status_code, 201)
        self.assertEqual(self.admin.patch(f"/api/teams/{tid}/manager", json={"manager_id": self.emp_id}).status_code, 400)
        self.assertEqual(self.admin.patch(f"/api/teams/{tid}/manager", json={"manager_id": self.mgr_id}).get_json()["manager"]["name"], "ramya")
        self.assertEqual(self.emp.get("/api/teams").get_json()[0]["member_count"], 1)
        self.assertEqual(self.mgr.post("/api/teams", json={"name": "Hack"}).status_code, 403)
        self.assertEqual(self.admin.delete(f"/api/teams/{tid}/members/{self.emp_id}").get_json()["member_count"], 0)
        self.assertEqual(self.admin.delete(f"/api/teams/{tid}/members/{self.emp_id}").status_code, 404)
        self.assertEqual(self.admin.post("/api/teams", json={"name": "Alpha"}).status_code, 409)

    # ---- projects + task board
    def test_project_task_progress_flow(self):
        team, proj = self.make_project()
        self.assertEqual(proj["manager_id"], self.mgr_id)  # defaults to team manager
        self.assertEqual(len(proj["team"]["members"]), 1)
        t = self.mgr.post("/api/tasks", json={"title": "API", "priority": "High", "category": "Work",
                                              "due_date": "2020-01-01", "assigned_to": self.emp_id}).get_json()
        link = self.mgr.patch(f"/api/task-board/{t['id']}/project", json={"project_id": proj["id"]})
        self.assertEqual(link.get_json()["project_name"], "CRM System")
        self.assertTrue(link.get_json()["is_overdue"])
        self.assertEqual(self.admin.get(f"/api/projects/{proj['id']}/progress").get_json()["percent"], 0)
        self.emp.patch(f"/api/tasks/{t['id']}/status", json={"status": "completed"})
        self.assertEqual(self.admin.get(f"/api/projects/{proj['id']}/progress").get_json()["percent"], 100)
        row = self.emp.get("/api/task-board").get_json()[0]
        self.assertEqual((row["assignee_name"], row["project_name"]), ("rahul", "CRM System"))
        self.assertEqual(self.emp.patch(f"/api/task-board/{t['id']}/project", json={"project_id": None}).status_code, 403)
        self.assertEqual(len(self.emp.get("/api/projects").get_json()), 1)

    def test_project_visibility(self):
        _, proj = self.make_project()
        stranger = app.test_client()
        self.user(stranger, "sneha", "EMPLOYEE")
        self.assertEqual(stranger.get("/api/projects").get_json(), [])
        self.assertEqual(stranger.get(f"/api/projects/{proj['id']}").status_code, 403)
        self.assertEqual(self.mgr.get(f"/api/projects/{proj['id']}").status_code, 200)

    def test_overview_for_each_role(self):
        _, proj = self.make_project()
        t = self.mgr.post("/api/tasks", json={"title": "A", "assigned_to": self.emp_id}).get_json()
        self.mgr.patch(f"/api/task-board/{t['id']}/project", json={"project_id": proj["id"]})
        a, m, e = (c.get("/api/overview").get_json() for c in (self.admin, self.mgr, self.emp))
        self.assertEqual((a["people"]["total"], a["teams"], a["tasks"]["total"]), (3, 1, 1))
        self.assertEqual(m["workload"][0]["open"], 1)
        self.assertEqual(e["tasks"]["pending"], 1)


if __name__ == "__main__":
    unittest.main()
