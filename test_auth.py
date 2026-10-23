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



    def test_update_password_requires_authentication(self):
        response = self.client.post(
            "/api/account/password",
            json={
                "current_password": "password123",
                "new_password": "newpassword123",
            },
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("Authentication required", response.get_json()["error"])

    def test_update_password_rejects_non_json_or_missing_fields(self):
        self.signup()
        self.client.post(
            "/api/login",
            json={"email": "taylor@example.test", "password": "password123"},
        )

        bad_requests = [
            {},
            {"current_password": "password123"},
            {"new_password": "newpassword123"},
            {"current_password": "", "new_password": "newpassword123"},
            {"current_password": "password123", "new_password": ""},
        ]
        for payload in bad_requests:
            with self.subTest(payload=payload):
                res = self.client.post("/api/account/password", json=payload)
                self.assertEqual(res.status_code, 400)
                self.assertIn("required", res.get_json()["error"])

    def test_update_password_rejects_incorrect_current_password(self):
        self.signup()
        self.client.post(
            "/api/login",
            json={"email": "taylor@example.test", "password": "password123"},
        )
        response = self.client.post(
            "/api/account/password",
            json={
                "current_password": "incorrect-password",
                "new_password": "newpassword123",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Current password is incorrect", response.get_json()["error"])

    def test_update_password_rejects_short_new_password(self):
        self.signup()
        self.client.post(
            "/api/login",
            json={"email": "taylor@example.test", "password": "password123"},
        )
        response = self.client.post(
            "/api/account/password",
            json={
                "current_password": "password123",
                "new_password": "short",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("8 characters", response.get_json()["error"])

    def test_update_password_rejects_same_new_password(self):
        self.signup()
        self.client.post(
            "/api/login",
            json={"email": "taylor@example.test", "password": "password123"},
        )
        response = self.client.post(
            "/api/account/password",
            json={
                "current_password": "password123",
                "new_password": "password123",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot be the same", response.get_json()["error"])

    def test_update_password_rejects_mismatched_confirmation(self):
        self.signup()
        self.client.post(
            "/api/login",
            json={"email": "taylor@example.test", "password": "password123"},
        )
        response = self.client.post(
            "/api/account/password",
            json={
                "current_password": "password123",
                "new_password": "newpassword123",
                "confirm_password": "differentpassword",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("do not match", response.get_json()["error"])

    def test_update_password_success_and_login_with_new_password(self):
        self.signup()
        self.client.post(
            "/api/login",
            json={"email": "taylor@example.test", "password": "password123"},
        )

        response = self.client.post(
            "/api/account/password",
            json={
                "current_password": "password123",
                "new_password": "new-strong-password-456",
                "confirm_password": "new-strong-password-456",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["message"], "Password updated successfully.")

        # Log out
        self.client.post("/api/logout")

        # Old password must fail
        old_login = self.client.post(
            "/api/login",
            json={"email": "taylor@example.test", "password": "password123"},
        )
        self.assertEqual(old_login.status_code, 401)

        # New password must succeed
        new_login = self.client.post(
            "/api/login",
            json={"email": "taylor@example.test", "password": "new-strong-password-456"},
        )
        self.assertEqual(new_login.status_code, 200)
        self.assertEqual(new_login.get_json()["user"]["email"], "taylor@example.test")

    def test_update_password_supports_route_and_field_aliases(self):
        self.signup()
        self.client.post(
            "/api/login",
            json={"email": "taylor@example.test", "password": "password123"},
        )

        # Test PATCH /api/profile/password with camelCase fields
        patch_res = self.client.patch(
            "/api/profile/password",
            json={
                "currentPassword": "password123",
                "newPassword": "alias-password-789",
                "confirmPassword": "alias-password-789",
            },
        )
        self.assertEqual(patch_res.status_code, 200)

        # Test PUT /api/me/password
        put_res = self.client.put(
            "/api/me/password",
            json={
                "oldPassword": "alias-password-789",
                "newPassword": "put-alias-password-999",
            },
        )
        self.assertEqual(put_res.status_code, 200)

        # Log out and verify login with newest password
        self.client.post("/api/logout")
        login_res = self.client.post(
            "/api/login",
            json={"email": "taylor@example.test", "password": "put-alias-password-999"},
        )
        self.assertEqual(login_res.status_code, 200)



    def test_login_rate_limiting_repeated_failures(self):
        self.signup()
        email = "taylor@example.test"
        # 5 failed attempts
        for i in range(5):
            res = self.client.post(
                "/api/login",
                json={"email": email, "password": "wrong-password"},
            )
            self.assertEqual(res.status_code, 401, f"Attempt {i+1} should return 401")
            self.assertIn("Incorrect email or password", res.get_json()["error"])

        # 6th attempt should return 429 Too Many Requests
        rate_limited_res = self.client.post(
            "/api/login",
            json={"email": email, "password": "wrong-password"},
        )
        self.assertEqual(rate_limited_res.status_code, 429)
        self.assertIn("Too many failed login attempts", rate_limited_res.get_json()["error"])
        self.assertIn("Retry-After", rate_limited_res.headers)

        # Even with the correct password, it is locked out during rate limiting
        locked_out_correct_res = self.client.post(
            "/api/login",
            json={"email": email, "password": "password123"},
        )
        self.assertEqual(locked_out_correct_res.status_code, 429)

    def test_login_rate_limiting_resets_on_successful_login(self):
        self.signup()
        email = "taylor@example.test"

        # 4 failed attempts (under the limit of 5)
        for _ in range(4):
            res = self.client.post(
                "/api/login",
                json={"email": email, "password": "wrong-password"},
            )
            self.assertEqual(res.status_code, 401)

        # Successful login resets the counter
        success_res = self.client.post(
            "/api/login",
            json={"email": email, "password": "password123"},
        )
        self.assertEqual(success_res.status_code, 200)

        # Log out
        self.client.post("/api/logout")

        # The next failed attempt should be attempt 1 (401), not attempt 5 or 6 (429)
        new_fail = self.client.post(
            "/api/login",
            json={"email": email, "password": "wrong-password"},
        )
        self.assertEqual(new_fail.status_code, 401)

    def test_login_rate_limiting_case_insensitive(self):
        self.signup()
        variations = [
            "TAYLOR@example.test",
            "taylor@example.test",
            "Taylor@Example.Test",
            "TAYLOR@EXAMPLE.TEST",
            "Taylor@example.test",
        ]
        # 5 attempts across different casing
        for variant in variations:
            res = self.client.post(
                "/api/login",
                json={"email": variant, "password": "wrong-password"},
            )
            self.assertEqual(res.status_code, 401)

        # 6th attempt with yet another casing must be rate limited
        blocked_res = self.client.post(
            "/api/login",
            json={"email": "TaYlOr@ExAmPlE.tEsT", "password": "wrong-password"},
        )
        self.assertEqual(blocked_res.status_code, 429)

    def test_login_rate_limiting_protects_nonexistent_email_without_revealing_existence(self):
        email = "doesnotexist@example.test"
        for _ in range(5):
            res = self.client.post(
                "/api/login",
                json={"email": email, "password": "any-password"},
            )
            self.assertEqual(res.status_code, 401)
            self.assertEqual(res.get_json()["error"], "Incorrect email or password.")

        blocked = self.client.post(
            "/api/login",
            json={"email": email, "password": "any-password"},
        )
        self.assertEqual(blocked.status_code, 429)

    def test_login_rate_limiting_recovery_after_lockout_window(self):
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "rate-limit-test-key",
                "DATABASE_PATH": str(Path(self.temp_dir.name) / "rate-limit-recovery.db"),
                "LOGIN_LOCKOUT_WINDOW_SECONDS": 2,
            }
        )
        client = app.test_client()

        # Sign up
        client.post(
            "/api/signup",
            json={"name": "Alex Smith", "email": "alex@example.test", "password": "password123"},
        )

        # 5 failed attempts
        for _ in range(5):
            res = client.post(
                "/api/login",
                json={"email": "alex@example.test", "password": "bad-password"},
            )
            self.assertEqual(res.status_code, 401)

        # Rate limited
        blocked = client.post(
            "/api/login",
            json={"email": "alex@example.test", "password": "password123"},
        )
        self.assertEqual(blocked.status_code, 429)

        # Wait for the 2-second window to expire
        import time
        time.sleep(2.1)

        # Now login should recover and succeed
        recovered = client.post(
            "/api/login",
            json={"email": "alex@example.test", "password": "password123"},
        )
        self.assertEqual(recovered.status_code, 200)

    def test_login_attempts_table_does_not_store_plaintext_passwords(self):
        self.client.post(
            "/api/login",
            json={"email": "taylor@example.test", "password": "super-secret-password-xyz"},
        )
        with self.app.app_context():
            import sqlite3
            with closing(sqlite3.connect(self.app.config["DATABASE_PATH"])) as database:
                columns = [col[1] for col in database.execute("PRAGMA table_info(login_attempts)").fetchall()]
                self.assertNotIn("password", columns)
                rows = database.execute("SELECT * FROM login_attempts").fetchall()
                for row in rows:
                    for val in row:
                        self.assertNotEqual(str(val), "super-secret-password-xyz")


if __name__ == "__main__":
    unittest.main()
