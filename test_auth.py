import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app import create_app


class AuthenticationApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "users.db"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE_PATH": str(database_path),
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def signup(self, **overrides):
        payload = {
            "name": "Taylor Brooks",
            "email": "taylor@example.test",
            "password": "password123",
        }
        payload.update(overrides)
        return self.client.post("/api/signup", json=payload)

    def test_signup_creates_employee_without_returning_password(self):
        response = self.signup(role="ADMIN")

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["user"]["role"], "EMPLOYEE")
        self.assertNotIn("password", body["user"])

    def test_configured_admin_email_gets_admin_role_at_signup(self):
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "configured-admin-test-key",
                "DATABASE_PATH": str(Path(self.temp_dir.name) / "admin-users.db"),
                "ADMIN_EMAIL": " ADMIN@example.test ",
            }
        )
        client = app.test_client()

        response = client.post(
            "/api/signup",
            json={
                "name": "Admin User",
                "email": "admin@example.test",
                "password": "password123",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["user"]["role"], "ADMIN")
        employee_signup = client.post(
            "/api/signup",
            json={
                "name": "Regular User",
                "email": "employee@example.test",
                "password": "password123",
            },
        )
        self.assertEqual(employee_signup.get_json()["user"]["role"], "EMPLOYEE")
        self.assertEqual(
            client.post(
                "/api/login",
                json={"email": "admin@example.test", "password": "password123"},
            ).get_json()["user"]["role"],
            "ADMIN",
        )
        self.assertEqual(client.get("/api/admin/dashboard").status_code, 200)

    def test_each_configured_admin_email_can_sign_up_as_admin(self):
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "configured-admin-list-test-key",
                "DATABASE_PATH": str(Path(self.temp_dir.name) / "admin-list-users.db"),
                "ADMIN_EMAILS": " first@example.test, SECOND@example.test ",
            }
        )
        client = app.test_client()

        for email in ("first@example.test", "second@example.test"):
            response = client.post(
                "/api/signup",
                json={
                    "name": "Admin User",
                    "email": email,
                    "password": "password123",
                    "accountType": "ADMIN",
                },
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.get_json()["user"]["role"], "ADMIN")

        unlisted = client.post(
            "/api/signup",
            json={
                "name": "Unlisted Admin",
                "email": "other@example.test",
                "password": "password123",
                "accountType": "ADMIN",
            },
        )
        self.assertEqual(unlisted.status_code, 403)

    def test_admin_signup_requires_configured_email_and_employee_signup_stays_employee(self):
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "configured-admin-only-test-key",
                "DATABASE_PATH": str(Path(self.temp_dir.name) / "admin-only-users.db"),
                "ADMIN_EMAIL": "admin@example.test",
            }
        )
        client = app.test_client()

        rejected_admin = client.post(
            "/api/signup",
            json={
                "name": "Unconfigured Admin",
                "email": "other@example.test",
                "password": "password123",
                "accountType": "ADMIN",
            },
        )
        self.assertEqual(rejected_admin.status_code, 403)
        self.assertIn("ADMIN_EMAILS", rejected_admin.get_json()["error"])

        employee = client.post(
            "/api/signup",
            json={
                "name": "Regular Employee",
                "email": "employee@example.test",
                "password": "password123",
                "accountType": "EMPLOYEE",
            },
        )
        self.assertEqual(employee.status_code, 201)
        self.assertEqual(employee.get_json()["user"]["role"], "EMPLOYEE")

    def test_admin_signup_requires_configuration(self):
        response = self.client.post(
            "/api/signup",
            json={
                "name": "Unconfigured Admin",
                "email": "admin@example.test",
                "password": "password123",
                "accountType": "ADMIN",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("ADMIN_EMAIL", response.get_json()["error"])

    def test_development_mode_allows_admin_signup_with_any_email(self):
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "development-open-admin-test-key",
                "DATABASE_PATH": str(Path(self.temp_dir.name) / "open-admin-users.db"),
                "APP_ENV": "development",
                "HOST": "127.0.0.1",
                "ALLOW_PUBLIC_ADMIN_SIGNUP": True,
            }
        )
        client = app.test_client()

        response = client.post(
            "/api/signup",
            json={
                "name": "Any Email Admin",
                "email": "any-email@example.test",
                "password": "password123",
                "accountType": "ADMIN",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["user"]["role"], "ADMIN")
        self.assertEqual(
            client.post(
                "/api/login",
                json={"email": "any-email@example.test", "password": "password123"},
            ).get_json()["user"]["role"],
            "ADMIN",
        )
        self.assertEqual(client.get("/api/admin/dashboard").status_code, 200)

    def test_public_admin_signup_cannot_run_outside_loopback_development(self):
        for config in (
            {"APP_ENV": "production", "HOST": "127.0.0.1"},
            {"APP_ENV": "development", "HOST": "0.0.0.0"},
        ):
            with self.subTest(config=config), self.assertRaisesRegex(
                RuntimeError, "only available in development on a loopback host"
            ):
                create_app(
                    {
                        "TESTING": True,
                        "SECRET_KEY": "unsafe-admin-config-test-key",
                        "DATABASE_PATH": str(Path(self.temp_dir.name) / "unsafe-admin.db"),
                        "ALLOW_PUBLIC_ADMIN_SIGNUP": True,
                        **config,
                    }
                )

    def test_signup_hashes_password(self):
        self.signup()
        with self.app.app_context():
            import sqlite3

            with closing(sqlite3.connect(self.app.config["DATABASE_PATH"])) as database:
                stored_password = database.execute(
                    "SELECT password FROM users WHERE email = ?",
                    ("taylor@example.test",),
                ).fetchone()[0]
        self.assertNotEqual(stored_password, "password123")

    def test_duplicate_signup_is_conflict(self):
        self.signup()
        response = self.signup()

        self.assertEqual(response.status_code, 409)
        self.assertIn("already exists", response.get_json()["error"])

    def test_signup_rejects_short_password(self):
        response = self.signup(password="short")

        self.assertEqual(response.status_code, 400)

    def test_login_session_me_and_logout(self):
        self.signup()
        login_response = self.client.post(
            "/api/login",
            json={"email": "TAYLOR@example.test", "password": "password123"},
        )

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(self.client.get("/api/me").status_code, 200)
        self.assertEqual(self.client.get("/api/employee/dashboard").status_code, 200)
        self.assertEqual(self.client.post("/api/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_login_rejects_invalid_password(self):
        self.signup()
        response = self.client.post(
            "/api/login",
            json={"email": "taylor@example.test", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 401)

    def test_role_dashboard_requires_authorized_role(self):
        self.signup()
        self.client.post(
            "/api/login",
            json={"email": "taylor@example.test", "password": "password123"},
        )

        self.assertEqual(self.client.get("/api/admin/dashboard").status_code, 403)
        self.assertEqual(self.client.get("/api/manager/dashboard").status_code, 403)

    def test_frontend_is_served_from_flask(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Teamspace", response.data)
        response.close()

    def test_api_method_errors_return_json(self):
        response = self.client.post("/api")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.mimetype, "application/json")

    def test_production_requires_a_configured_secret_key(self):
        with self.assertRaisesRegex(RuntimeError, "Set SECRET_KEY"):
            create_app({"APP_ENV": "production", "DATABASE_PATH": "unused.db"})

    def test_production_uses_secure_session_cookies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(
                {
                    "APP_ENV": "production",
                    "SECRET_KEY": "production-test-key",
                    "DATABASE_PATH": str(Path(temp_dir) / "users.db"),
                }
            )

        self.assertTrue(app.config["SESSION_COOKIE_SECURE"])


if __name__ == "__main__":
    unittest.main()
