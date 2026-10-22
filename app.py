
from flask import Flask, jsonify
from auth import auth_bp, init_db
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "local-development-only-change-me"
)

init_db()
app.register_blueprint(auth_bp)


@app.route("/")
def home():
    return jsonify({"message": "Task Manager Authentication API is running"})


if __name__ == "__main__":
    app.run(debug=True)
