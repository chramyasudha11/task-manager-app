"""Task Manager Flask app: Member 1 auth + 2 tasks + 3 dashboard + 4 org + 5 task UI."""
import os

from flask import Flask, jsonify, send_from_directory

from auth import auth_bp, init_db
from tasks import tasks_bp, init_tasks_db
from dashboard import dashboard_bp
from org_common import guard_bp, init_org_db      # Member 4
from employees import employees_bp                # Member 4
from teams import teams_bp                        # Member 4
from projects import projects_bp                  # Member 4
from taskboard import taskboard_bp                # Member 5

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"), static_url_path="/static")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "local-development-only-change-me")

for blueprint in (auth_bp, tasks_bp, dashboard_bp, guard_bp,
                  employees_bp, teams_bp, projects_bp, taskboard_bp):
    app.register_blueprint(blueprint)


@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/health")
def health():
    return jsonify({"message": "Task Manager API is running"})


def init_all():
    init_db()          # Member 1: users
    init_tasks_db()    # Member 2: tasks
    init_org_db()      # Member 4: teams, projects, task links, user columns


if __name__ == "__main__":
    init_all()
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
