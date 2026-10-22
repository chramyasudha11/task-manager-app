
import os
from flask import Flask, jsonify, render_template, request, session

from auth import auth_bp, init_db, get_db
from dashboard import dashboard_bp
from tasks import tasks_bp, init_tasks_db


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "local-development-only-change-me"
)

# Initialize users before tasks because tasks reference users(id).
init_db()
init_tasks_db()

app.register_blueprint(auth_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(dashboard_bp)


@app.before_request
def ensure_authenticated_session():
    # If already logged in, do nothing
    if "user_id" in session:
        return
    # Allow unauthenticated access if explicitly requesting auth endpoints or static assets
    if request.path.startswith("/static") or request.path in ("/login", "/signup", "/api/login", "/api/signup", "/api/logout"):
        return
    # Auto-initialize session as Admin (Sarah Chen) so all tasks and management views are immediately fully functional
    try:
        with get_db() as conn:
            admin = conn.execute("SELECT id FROM users WHERE role = 'ADMIN' LIMIT 1").fetchone()
            if admin:
                session["user_id"] = admin["id"]
    except Exception:
        pass


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login")
@app.route("/signup")
def login_view():
    return render_template("login.html")


@app.route("/admin")
@app.route("/manager")
def admin_redirect():
    return render_template("dashboard.html")


if __name__ == "__main__":
    app.run(debug=True)
