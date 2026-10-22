"""Test suite for Member 6 — Admin + Manager Dashboard.
Verifies all KPIs, 7 charts, 48-employee table, and Manager views.
"""

import unittest
import json
from app import app


class DashboardTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_kpi_metrics(self):
        """Verify the exact required KPI card metrics:
        Total Employees: 48
        Total Tasks: 326
        Completed: 218
        Overdue: 31
        """
        response = self.client.get("/api/dashboard/kpi")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode("utf-8"))

        self.assertEqual(data["total_employees"], 48, "Total Employees KPI must be 48")
        self.assertEqual(data["total_tasks"], 326, "Total Tasks KPI must be 326")
        self.assertEqual(data["completed"], 218, "Completed Tasks KPI must be 218")
        self.assertEqual(data["overdue"], 31, "Overdue Tasks KPI must be 31")

    def test_all_seven_charts(self):
        """Verify all 7 required management charts are present and contain data:
        1. Task completion trend
        2. Pending vs completed
        3. Tasks by priority
        4. Tasks by project
        5. Tasks by team
        6. Employee workload
        7. Employee performance
        """
        response = self.client.get("/api/dashboard/charts")
        self.assertEqual(response.status_code, 200)
        charts = json.loads(response.data.decode("utf-8"))

        # 1. Completion trend
        self.assertIn("trend", charts)
        self.assertTrue(len(charts["trend"]["labels"]) > 0)
        self.assertTrue(len(charts["trend"]["completed"]) > 0)

        # 2. Pending vs completed
        self.assertIn("pending_vs_completed", charts)
        self.assertTrue(len(charts["pending_vs_completed"]["data"]) > 0)

        # 3. Tasks by priority
        self.assertIn("tasks_by_priority", charts)
        self.assertIn("High", charts["tasks_by_priority"]["labels"])

        # 4. Tasks by project
        self.assertIn("tasks_by_project", charts)
        self.assertTrue(len(charts["tasks_by_project"]["labels"]) > 0)

        # 5. Tasks by team
        self.assertIn("tasks_by_team", charts)
        self.assertTrue(len(charts["tasks_by_team"]["labels"]) > 0)

        # 6. Employee workload
        self.assertIn("employee_workload", charts)
        self.assertTrue(len(charts["employee_workload"]["labels"]) > 0)

        # 7. Employee performance
        self.assertIn("employee_performance", charts)
        self.assertTrue(len(charts["employee_performance"]["labels"]) > 0)

    def test_employee_breakdown_table(self):
        """Verify the 48-employee table data contract:
        Columns: Employee | Assigned | Completed | Pending | Overdue
        """
        response = self.client.get("/api/dashboard/employees")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode("utf-8"))

        employees = data["employees"]
        self.assertEqual(len(employees), 48, "Must return exactly 48 employees")

        for emp in employees:
            self.assertIn("name", emp)
            self.assertIn("assigned", emp)
            self.assertIn("completed", emp)
            self.assertIn("pending", emp)
            self.assertIn("overdue", emp)
            self.assertIn("team", emp)
            self.assertIn("job_title", emp)

    def test_manager_view(self):
        """Verify Manager view data:
        - Team Progress
        - Team Workload
        - Team Completion %
        - Overdue Tasks (exactly 31 overdue tasks)
        - High Priority Tasks
        """
        response = self.client.get("/api/dashboard/manager-view")
        self.assertEqual(response.status_code, 200)
        mgr = json.loads(response.data.decode("utf-8"))

        self.assertIn("team_progress", mgr)
        self.assertTrue(len(mgr["team_progress"]) > 0)

        # Verify team workload and completion percentage fields exist
        for team in mgr["team_progress"]:
            self.assertIn("team", team)
            self.assertIn("total_tasks", team)
            self.assertIn("completed", team)
            self.assertIn("completion_pct", team)

        # Overdue tasks alert desk: exactly 31 overdue tasks
        self.assertIn("overdue_tasks", mgr)
        self.assertEqual(len(mgr["overdue_tasks"]), 31, "Overdue tasks desk must have 31 tasks")

        # High priority tasks
        self.assertIn("high_priority_tasks", mgr)
        self.assertTrue(len(mgr["high_priority_tasks"]) > 0)

    def test_role_switch(self):
        """Verify role switching API works between ADMIN, MANAGER, and EMPLOYEE."""
        roles = ["ADMIN", "MANAGER", "EMPLOYEE"]
        for role in roles:
            response = self.client.post(
                "/api/dashboard/switch-role",
                data=json.dumps({"role": role}),
                content_type="application/json"
            )
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data.decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertEqual(data["user"]["role"], role)

    def test_dashboard_page_render(self):
        """Verify /dashboard and /manager render successfully with HTTP 200."""
        res1 = self.client.get("/dashboard")
        self.assertEqual(res1.status_code, 200)
        self.assertIn(b"TASKSPACE", res1.data)
        self.assertIn(b"Total Employees", res1.data)

        res2 = self.client.get("/manager")
        self.assertEqual(res2.status_code, 200)


if __name__ == "__main__":
    unittest.main()
