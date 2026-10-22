
import os
import secrets
import ipaddress
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from auth import auth_bp, init_db
from management import init_management_db, management_bp


BASE_DIR = Path(__file__).resolve().parent


def create_app(test_config=None):
    configured_secret = (
        (test_config or {}).get("SECRET_KEY")
        or os.environ.get("SECRET_KEY")
    )
    app_environment = (
        (test_config or {}).get("APP_ENV")
        or os.environ.get("APP_ENV", "development")
    ).lower()

    if not configured_secret and app_environment != "development":
        raise RuntimeError(
            "Set SECRET_KEY before running outside development mode."
        )

    secret_key = configured_secret or secrets.token_hex(32)

    app = Flask(__name__)

    cookie_secure = os.environ.get("SESSION_COOKIE_SECURE")
    if cookie_secure is None:
        cookie_secure = str(app_environment == "production")

    app.config.from_mapping(
        SECRET_KEY=secret_key,
        DATABASE_PATH=os.environ.get(
            "DATABASE_PATH", str(BASE_DIR / "users.db")
        ),
        HOST=os.environ.get("HOST", "127.0.0.1"),
        ADMIN_EMAILS=os.environ.get("ADMIN_EMAILS", ""),
        ADMIN_EMAIL=os.environ.get("ADMIN_EMAIL", "").strip().lower(),
        ALLOW_PUBLIC_ADMIN_SIGNUP=os.environ.get(
            "ALLOW_PUBLIC_ADMIN_SIGNUP", ""
        ).strip().lower() in {"1", "true", "yes", "on"},
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=cookie_secure.lower() == "true",
        APP_ENV=app_environment,
    )

    if test_config:
        app.config.update(test_config)

    if app.config["ALLOW_PUBLIC_ADMIN_SIGNUP"]:
        host = app.config["HOST"]
        try:
            loopback_only = (
                host.lower() == "localhost"
                or ipaddress.ip_address(host).is_loopback
            )
        except ValueError:
            loopback_only = False

        if app.config["APP_ENV"] != "development" or not loopback_only:
            raise RuntimeError(
                "ALLOW_PUBLIC_ADMIN_SIGNUP is only available in "
                "development on a loopback host."
            )

    if not configured_secret:
        app.logger.warning(
            "Using a generated development session key; "
            "set SECRET_KEY for persistent sessions."
        )

    init_db(app)
    init_management_db(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(management_bp)

    @app.get("/")
    def home():
        return send_from_directory(BASE_DIR, "index.html")

    @app.get("/styles.css")
    def styles():
        return send_from_directory(BASE_DIR, "styles.css")

    @app.get("/app.js")
    def frontend_script():
        return send_from_directory(BASE_DIR, "app.js")

    @app.get("/api")
    @app.get("/api/")
    def api_status():
        return jsonify(message="Task Manager API is running.")

    @app.errorhandler(500)
    def internal_server_error(error):
        app.logger.error("Unhandled server error: %s", error)

        if request.path.startswith("/api/"):
            return jsonify(
                error="The server could not complete the request."
            ), 500

        return "Internal server error.", 500

    @app.errorhandler(404)
    def not_found(error):
        if request.path == "/api" or request.path.startswith("/api/"):
            return jsonify(error="API route not found."), 404

        return error

    @app.errorhandler(405)
    def method_not_allowed(error):
        if request.path == "/api" or request.path.startswith("/api/"):
            return jsonify(
                error="Method not allowed for this API route."
            ), 405

        return error

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        host=app.config["HOST"],
        port=int(os.environ.get("PORT", "5005")),
        debug=False,
    )
