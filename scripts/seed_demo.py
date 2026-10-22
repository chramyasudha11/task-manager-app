"""LOCAL DEVELOPMENT ONLY: create demo admin/manager/employees, a team, a project and tasks.

Usage (from project root):  python scripts/seed_demo.py
All demo accounts use the password  Demo@1234
"""
import os, sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from werkzeug.security import generate_password_hash
from app import init_all
from auth import get_db

PEOPLE = [
    ("Admin User", "admin@taskflow.com", "ADMIN", "Management", "Administrator"),
    ("Ramya", "ramya@taskflow.com", "MANAGER", "Engineering", "Project Manager"),
    ("Rahul", "rahul@taskflow.com", "EMPLOYEE", "Engineering", "Backend Developer"),
    ("Priya", "priya@taskflow.com", "EMPLOYEE", "Engineering", "Frontend Developer"),
    ("Arjun", "arjun@taskflow.com", "EMPLOYEE", "QA", "Tester"),
    ("Sneha", "sneha@taskflow.com", "EMPLOYEE", "Design", "UI Designer"),
]


def main():
    init_all()
    today = date.today()
    with get_db() as db:
        if db.execute("SELECT 1 FROM users WHERE email = 'admin@taskflow.com'").fetchone():
            print("Demo data already exists. Delete users.db to start fresh.")
            return
        pw = generate_password_hash("Demo@1234")
        ids = {}
        for name, email, role, dept, desig in PEOPLE:
            ids[name] = db.execute(
                "INSERT INTO users (name, email, password, role, department, designation) VALUES (?,?,?,?,?,?)",
                (name, email, pw, role, dept, desig)).lastrowid
        team = db.execute("INSERT INTO teams (name, manager_id) VALUES ('CRM Team', ?)", (ids["Ramya"],)).lastrowid
        for n in ("Rahul", "Priya", "Arjun", "Sneha"):
            db.execute("INSERT INTO team_members VALUES (?, ?)", (team, ids[n]))
        proj = db.execute(
            "INSERT INTO projects (name, description, team_id, manager_id, start_date, end_date) VALUES (?,?,?,?,?,?)",
            ("CRM System", "Customer relationship platform for the client", team, ids["Ramya"],
             today.isoformat(), (today + timedelta(days=60)).isoformat())).lastrowid
        now = today.isoformat() + "T00:00:00+00:00"
        tasks = [("API", "Rahul", "High", 3, "in_progress"), ("Testing", "Priya", "Medium", 5, "pending"),
                 ("Login screen", "Priya", "High", -2, "pending"), ("Test plan", "Arjun", "Medium", 7, "completed"),
                 ("Logo and colours", "Sneha", "Low", -1, "completed"), ("Database schema", "Rahul", "High", 1, "completed")]
        for title, who, prio, days, status in tasks:
            tid = db.execute(
                """INSERT INTO tasks (title, description, status, priority, category, due_date, created_by, assigned_to, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (title, f"{title} for the CRM System", status, prio, "Work", (today + timedelta(days=days)).isoformat(),
                 ids["Ramya"], ids[who], now, now)).lastrowid
            db.execute("INSERT INTO task_projects VALUES (?, ?)", (tid, proj))
    print("Demo data created. Logins (password Demo@1234): admin@taskflow.com, ramya@taskflow.com, rahul@taskflow.com")


if __name__ == "__main__":
    main()
