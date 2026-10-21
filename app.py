import os
from flask import Flask, jsonify

from auth import auth_bp, init_db
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


@app.route("/")
def home():
    return jsonify({"message": "Task Manager API is running"})


if __name__ == "__main__":
    app.run(debug=True)
