"""Tests for Member 7 – Employee Productivity and Notifications API.

Run from the project root:
    python -m unittest test_productivity -v
"""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app import create_app


class ProductivityApiTests(unittest.TestCase):
    """Full integration tests for all productivity endpoints."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "users.db"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "productivity-test-key",
                "DATABASE_PATH": str(self.database_path),
                "ALLOW_PUBLIC_ADMIN_SIGNUP": True,
            }
        )
        self.client = self.app.test_client()
        self._setup_users()

    def tearDown(self):
        self.temp_dir.cleanup()

    # ---- account helpers ------------------------------------------------

    def _signup(self, client, name, email, password="testpass1"):
        return client.post(
            "/api/signup",
            json={"name": name, "email": email, "password": password},
        )

    def _login(self, client, email, password="testpass1"):
        return client.post("/api/login", json={"email": email, "password": password})

    def _promote_to_admin(self, email):
        with closing(sqlite3.connect(self.database_path)) as db:
            db.execute("UPDATE users SET role = 'ADMIN' WHERE email = ?", (email,))
            db.execute("UPDATE employees SET role = 'ADMIN' WHERE email = ?", (email,))
            db.commit()

    def _setup_users(self):
        # Admin
        self.admin_client = self.app.test_client()
        self._signup(self.admin_client, "Admin User", "admin@test.test")
        self._promote_to_admin("admin@test.test")
        self._login(self.admin_client, "admin@test.test")

        # Employee 1
        self.emp_client = self.app.test_client()
        self._signup(self.emp_client, "Alice Employee", "alice@test.test")
        self._login(self.emp_client, "alice@test.test")

        # Employee 2 (no tasks)
        self.emp2_client = self.app.test_client()
        self._signup(self.emp2_client, "Bob Employee", "bob@test.test")
        self._login(self.emp2_client, "bob@test.test")

    def _employee_id_for(self, email):
        with closing(sqlite3.connect(self.database_path)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT id FROM employees WHERE email = ?", (email,)
            ).fetchone()
            return row["id"] if row else None

    def _create_task(self, name, status="Not Started", priority="Medium",
                     due_date=None, assignee_email="alice@test.test"):
        """Admin creates a management task and assigns it to the given employee."""
        assignee_id = self._employee_id_for(assignee_email)
        payload = {
            "name": name,
            "status": status,
            "priority": priority,
            "assigneeId": assignee_id,
        }
        if due_date:
            payload["dueDate"] = due_date
        return self.admin_client.post("/api/tasks", json=payload)

    # ------------------------------------------------------------------
    # Tests – Unauthenticated access
    # ------------------------------------------------------------------

    def test_all_endpoints_require_auth(self):
        guest = self.app.test_client()
        endpoints = [
            ("GET",  "/api/productivity/summary"),
            ("GET",  "/api/productivity/week"),
            ("GET",  "/api/productivity/calendar"),
            ("GET",  "/api/notifications"),
            ("POST", "/api/notifications/1/read"),
            ("POST", "/api/notifications/read-all"),
            ("GET",  "/api/saved-filters"),
            ("POST", "/api/saved-filters"),
            ("DELETE", "/api/saved-filters/1"),
        ]
        for method, path in endpoints:
            resp = guest.open(path, method=method, json={})
            self.assertEqual(
                resp.status_code, 401,
                msg=f"{method} {path} should return 401 for unauthenticated users",
            )

    # ------------------------------------------------------------------
    # Tests – Productivity summary
    # ------------------------------------------------------------------

    def test_summary_zero_tasks(self):
        resp = self.emp_client.get("/api/productivity/summary")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["totalTasks"], 0)
        self.assertEqual(body["completionRate"], 0)

    def test_summary_counts_correctly(self):
        self._create_task("T1", status="Not Started", priority="High")
        self._create_task("T2", status="In Progress", priority="Medium")
        self._create_task("T3", status="Completed", priority="Low")

        resp = self.emp_client.get("/api/productivity/summary")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["totalTasks"], 3)
        self.assertEqual(body["completed"], 1)
        self.assertEqual(body["inProgress"], 1)
        self.assertEqual(body["notStarted"], 1)
        self.assertEqual(body["completionRate"], 33)
        pc = body["priorityCounts"]
        self.assertEqual(pc["High"], 1)
        self.assertEqual(pc["Medium"], 1)
        self.assertEqual(pc["Low"], 1)

    def test_summary_overdue_counts(self):
        self._create_task("Past due", due_date="2020-01-01", status="Not Started")
        self._create_task("Completed past", due_date="2020-01-01", status="Completed")
        resp = self.emp_client.get("/api/productivity/summary")
        body = resp.get_json()
        # Only the non-completed past task is overdue
        self.assertEqual(body["overdueTasks"], 1)

    def test_summary_other_employee_not_included(self):
        self._create_task("Alice task", assignee_email="alice@test.test")
        resp = self.emp2_client.get("/api/productivity/summary")
        body = resp.get_json()
        self.assertEqual(body["totalTasks"], 0)

    # ------------------------------------------------------------------
    # Tests – My Week
    # ------------------------------------------------------------------

    def test_week_returns_correct_structure(self):
        resp = self.emp_client.get("/api/productivity/week")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("weekStart", body)
        self.assertIn("weekEnd", body)
        self.assertIn("tasks", body)
        self.assertIsInstance(body["tasks"], list)

    def test_week_task_with_current_due_date_appears(self):
        import datetime
        today = datetime.date.today().isoformat()
        self._create_task("Due today task", due_date=today)
        resp = self.emp_client.get("/api/productivity/week")
        body = resp.get_json()
        names = [t["name"] for t in body["tasks"]]
        self.assertIn("Due today task", names)

    def test_week_past_task_not_included(self):
        self._create_task("Old task", due_date="2015-06-15")
        resp = self.emp_client.get("/api/productivity/week")
        body = resp.get_json()
        names = [t["name"] for t in body["tasks"]]
        self.assertNotIn("Old task", names)

    # ------------------------------------------------------------------
    # Tests – Calendar
    # ------------------------------------------------------------------

    def test_calendar_returns_correct_structure(self):
        resp = self.emp_client.get("/api/productivity/calendar")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("calendar", body)
        self.assertIsInstance(body["calendar"], list)

    def test_calendar_groups_tasks_by_date(self):
        import datetime
        today = datetime.date.today()
        iso = today.isoformat()
        self._create_task("Cal task 1", due_date=iso)
        self._create_task("Cal task 2", due_date=iso)

        params = f"?year={today.year}&month={today.month}"
        resp = self.emp_client.get(f"/api/productivity/calendar{params}")
        body = resp.get_json()
        dates = {entry["date"]: entry["tasks"] for entry in body["calendar"]}
        self.assertIn(iso, dates)
        self.assertEqual(len(dates[iso]), 2)

    def test_calendar_month_filter_excludes_other_months(self):
        self._create_task("Jan task", due_date="2025-01-15")
        self._create_task("Jun task", due_date="2025-06-15")
        resp = self.emp_client.get("/api/productivity/calendar?year=2025&month=1")
        body = resp.get_json()
        all_dates = [e["date"] for e in body["calendar"]]
        for d in all_dates:
            self.assertTrue(d.startswith("2025-01"), msg=f"Unexpected date {d}")

    def test_calendar_invalid_month_rejected(self):
        resp = self.emp_client.get("/api/productivity/calendar?month=13")
        self.assertEqual(resp.status_code, 400)

    def test_calendar_invalid_month_string_rejected(self):
        resp = self.emp_client.get("/api/productivity/calendar?month=abc")
        self.assertEqual(resp.status_code, 400)

    # ------------------------------------------------------------------
    # Tests – Notifications
    # ------------------------------------------------------------------

    def test_notifications_returns_correct_structure(self):
        resp = self.emp_client.get("/api/notifications")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("notifications", body)
        self.assertIn("unreadCount", body)

    def test_assignment_notification_seeded_automatically(self):
        self._create_task("Notify task")
        resp = self.emp_client.get("/api/notifications")
        body = resp.get_json()
        assignment_notifs = [n for n in body["notifications"] if n["kind"] == "assignment"]
        self.assertGreaterEqual(len(assignment_notifs), 1)
        # Message should mention the task name
        messages = " ".join(n["message"] for n in assignment_notifs)
        self.assertIn("Notify task", messages)

    def test_deadline_notification_seeded_for_approaching_due_date(self):
        import datetime
        near = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
        self._create_task("Due soon task", due_date=near, status="Not Started")
        resp = self.emp_client.get("/api/notifications")
        body = resp.get_json()
        deadline_notifs = [n for n in body["notifications"] if n["kind"] == "deadline"]
        self.assertGreaterEqual(len(deadline_notifs), 1)
        messages = " ".join(n["message"] for n in deadline_notifs)
        self.assertIn("Due soon task", messages)

    def test_completed_task_does_not_trigger_deadline_notification(self):
        import datetime
        near = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        self._create_task("Done task", due_date=near, status="Completed")
        resp = self.emp_client.get("/api/notifications")
        body = resp.get_json()
        deadline_notifs = [n for n in body["notifications"] if n["kind"] == "deadline"]
        msgs = " ".join(n["message"] for n in deadline_notifs)
        self.assertNotIn("Done task", msgs)

    def test_notifications_not_duplicated_on_repeated_calls(self):
        self._create_task("No-dup task")
        self.emp_client.get("/api/notifications")
        resp2 = self.emp_client.get("/api/notifications")
        body = resp2.get_json()
        task_notifs = [
            n for n in body["notifications"]
            if n["kind"] == "assignment" and "No-dup task" in n["message"]
        ]
        self.assertEqual(len(task_notifs), 1)

    def test_mark_notification_read(self):
        self._create_task("Read task")
        notifs = self.emp_client.get("/api/notifications").get_json()["notifications"]
        target = notifs[0]
        self.assertFalse(target["isRead"])

        resp = self.emp_client.post(f"/api/notifications/{target['id']}/read")
        self.assertEqual(resp.status_code, 200)

        updated = self.emp_client.get("/api/notifications").get_json()["notifications"]
        updated_map = {n["id"]: n for n in updated}
        self.assertTrue(updated_map[target["id"]]["isRead"])

    def test_mark_all_notifications_read(self):
        self._create_task("Mass read task 1")
        self._create_task("Mass read task 2")
        self.emp_client.get("/api/notifications")  # seed
        resp = self.emp_client.post("/api/notifications/read-all")
        self.assertEqual(resp.status_code, 200)
        body = self.emp_client.get("/api/notifications").get_json()
        self.assertEqual(body["unreadCount"], 0)
        for n in body["notifications"]:
            self.assertTrue(n["isRead"])

    def test_mark_read_wrong_employee_returns_404(self):
        self._create_task("Alice only")
        notifs = self.emp_client.get("/api/notifications").get_json()["notifications"]
        notif_id = notifs[0]["id"]
        # Bob should not be able to mark Alice's notification as read
        resp = self.emp2_client.post(f"/api/notifications/{notif_id}/read")
        self.assertEqual(resp.status_code, 404)

    def test_mark_nonexistent_notification_returns_404(self):
        resp = self.emp_client.post("/api/notifications/99999/read")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # Tests – Saved filters
    # ------------------------------------------------------------------

    def test_saved_filters_empty_list(self):
        resp = self.emp_client.get("/api/saved-filters")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("savedFilters", body)
        self.assertIsInstance(body["savedFilters"], list)

    def test_create_saved_filter(self):
        resp = self.emp_client.post(
            "/api/saved-filters",
            json={"name": "High priority open", "filter": {"status": "Not Started", "priority": "High"}},
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.get_json()
        self.assertIn("savedFilter", body)
        sf = body["savedFilter"]
        self.assertEqual(sf["name"], "High priority open")
        self.assertEqual(sf["filter"]["status"], "Not Started")
        self.assertEqual(sf["filter"]["priority"], "High")
        self.assertIsNotNone(sf["id"])

    def test_list_saved_filters_returns_created_filter(self):
        self.emp_client.post(
            "/api/saved-filters",
            json={"name": "My filter", "filter": {"search": "bug"}},
        )
        resp = self.emp_client.get("/api/saved-filters")
        body = resp.get_json()
        names = [f["name"] for f in body["savedFilters"]]
        self.assertIn("My filter", names)

    def test_delete_saved_filter(self):
        create_resp = self.emp_client.post(
            "/api/saved-filters",
            json={"name": "To delete", "filter": {}},
        )
        fid = create_resp.get_json()["savedFilter"]["id"]
        del_resp = self.emp_client.delete(f"/api/saved-filters/{fid}")
        self.assertEqual(del_resp.status_code, 200)
        # Verify it's gone
        filters = self.emp_client.get("/api/saved-filters").get_json()["savedFilters"]
        self.assertNotIn(fid, [f["id"] for f in filters])

    def test_delete_other_employees_filter_returns_404(self):
        create_resp = self.emp_client.post(
            "/api/saved-filters",
            json={"name": "Private filter", "filter": {}},
        )
        fid = create_resp.get_json()["savedFilter"]["id"]
        resp = self.emp2_client.delete(f"/api/saved-filters/{fid}")
        self.assertEqual(resp.status_code, 404)

    def test_delete_nonexistent_filter_returns_404(self):
        resp = self.emp_client.delete("/api/saved-filters/99999")
        self.assertEqual(resp.status_code, 404)

    def test_saved_filter_name_required(self):
        resp = self.emp_client.post(
            "/api/saved-filters",
            json={"name": "  ", "filter": {}},
        )
        self.assertEqual(resp.status_code, 400)

    def test_saved_filter_name_too_long(self):
        resp = self.emp_client.post(
            "/api/saved-filters",
            json={"name": "x" * 101, "filter": {}},
        )
        self.assertEqual(resp.status_code, 400)

    def test_saved_filter_unknown_key_rejected(self):
        resp = self.emp_client.post(
            "/api/saved-filters",
            json={"name": "Bad filter", "filter": {"unknown_field": "value"}},
        )
        self.assertEqual(resp.status_code, 400)

    def test_saved_filter_invalid_body_rejected(self):
        resp = self.emp_client.post("/api/saved-filters", json="not an object")
        self.assertEqual(resp.status_code, 400)

    def test_saved_filter_filter_must_be_object(self):
        resp = self.emp_client.post(
            "/api/saved-filters",
            json={"name": "Bad", "filter": "not-a-dict"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_filters_are_isolated_per_employee(self):
        self.emp_client.post(
            "/api/saved-filters",
            json={"name": "Alice filter", "filter": {"status": "In Progress"}},
        )
        resp_bob = self.emp2_client.get("/api/saved-filters")
        names = [f["name"] for f in resp_bob.get_json()["savedFilters"]]
        self.assertNotIn("Alice filter", names)

    # ------------------------------------------------------------------
    # Tests – Existing tests still pass (integration smoke-test)
    # ------------------------------------------------------------------

    def test_existing_workspace_endpoint_still_works(self):
        resp = self.emp_client.get("/api/workspace")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("tasks", body)

    def test_existing_task_creation_by_admin_still_works(self):
        resp = self._create_task("Smoke test task")
        self.assertEqual(resp.status_code, 201)


if __name__ == "__main__":
    unittest.main(verbosity=2)
