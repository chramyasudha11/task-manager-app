from flask import Flask, jsonify
from auth import auth_bp, init_db
from tasks import tasks_bp, init_tasks_db
import os

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "local-development-only-change-me"
)

# Initialize Member 1's users table
init_db()

# Initialize Member 2's tasks table
# Both use the SAME users.db database
init_tasks_db()

# Register authentication routes
app.register_blueprint(auth_bp)

# Register task REST API routes
app.register_blueprint(tasks_bp)


@app.route("/")
def home():
    return jsonify({
        "message": "Task Manager API is running"
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)