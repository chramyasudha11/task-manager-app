 feature/dashboard-reports
import os
from flask import Flask, jsonify

from auth import auth_bp, init_db
from dashboard import dashboard_bp
from tasks import tasks_bp, init_tasks_db


app = Flask(__name__)

from flask import Flask, jsonify
from auth import auth_bp, init_db
from tasks import tasks_bp, init_tasks_db
import os

app = Flask(__name__)

 main
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "local-development-only-change-me"
)

feature/dashboard-reports
# Initialize users before tasks because tasks reference users(id).
init_db()
init_tasks_db()

app.register_blueprint(auth_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(dashboard_bp)

# Initialize Member 1's users table
init_db()

# Initialize Member 2's tasks table
# Both use the SAME users.db database
init_tasks_db()

# Register authentication routes
app.register_blueprint(auth_bp)

# Register task REST API routes
app.register_blueprint(tasks_bp)
 main


@app.route("/")
def home():
 feature/dashboard-reports
    return jsonify({"message": "Task Manager API is running"})


if __name__ == "__main__":
    app.run(debug=True)

    return jsonify({
        "message": "Task Manager API is running"
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
 main
