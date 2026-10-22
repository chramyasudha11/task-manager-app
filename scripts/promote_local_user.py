"""LOCAL DEVELOPMENT ONLY: promote an already-registered account to MANAGER.

Usage (from project root):
  python scripts/promote_local_user.py --email manager@example.com
No route calls this command. Do not expose it via a public endpoint.
"""
import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "users.db"


def main():
    parser = argparse.ArgumentParser(description="Promote LOCAL user for testing task assignment")
    parser.add_argument("--email", required=True, help="Existing registered user email")
    args = parser.parse_args()
    email = args.email.strip().lower()
    if not DB_PATH.exists():
        parser.error(f"No existing database found: {DB_PATH}. Start app.py first.")
    with sqlite3.connect(DB_PATH) as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            parser.error("No matching registered user. Signup first, then retry.")
        conn.execute("UPDATE users SET role = 'MANAGER' WHERE id = ?", (user[0],))
    print(f"LOCAL testing only: {email} role set to MANAGER. Log in again to test assignment.")


if __name__ == "__main__":
    main()
