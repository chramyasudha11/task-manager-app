# Teamspace task manager

A responsive, dependency-free HTML/CSS/JavaScript frontend with a Flask API and SQLite persistence for employees, teams, projects, and tasks.

## Preview it

Install the Python dependency once:

```powershell
python -m pip install -r requirements.txt
```

Start the Flask app from the project directory:

```powershell
python app.py
```

Open `http://127.0.0.1:5005`. Flask serves the frontend and API from the same origin. The API creates `users.db` in the project directory if it does not already exist. Set `PORT` if that port is already in use.

The existing `users.db` is retained. On startup, the app adds the management tables and links existing accounts to employee records without removing users. New signups also receive an employee record.

Public signup creates an `EMPLOYEE` account. To allow one or more people to create administrator accounts, set `ADMIN_EMAILS` to their comma-separated email addresses before starting Flask. Choose **Admin Login** and sign up using one of those addresses. The signup screen keeps the selected login type. Only explicitly configured addresses can register as administrators; all other signups remain employees.

For local development only, you can temporarily allow any valid email address to create an admin account:

```powershell
$env:ALLOW_PUBLIC_ADMIN_SIGNUP = "true"
python app.py
```

This option is rejected outside development or when `HOST` is not a loopback address. It does not verify that the email inbox exists; the account is protected by the password chosen at signup. Turn the option off after local testing. For deployments, use `ADMIN_EMAILS` instead.

```powershell
$env:ADMIN_EMAILS = "admin@example.com,another-admin@example.com"
python app.py
```

For compatibility, the existing single-address `ADMIN_EMAIL` setting is still supported. Configured accounts are granted administrator access at signup or promoted on startup if they already exist. Any existing account whose role is `ADMIN` can log in using Admin Login. Admins can see all tasks and manage employees, teams, projects, and tasks. Choose **Employee Login** for an employee account; employees see only their assigned tasks and can update only those tasks' statuses. The API enforces the same permissions and does not return employee, team, or project data to employee sessions.

When an admin adds an employee, that employee can create an account using the same email address; signup links the new login to the existing employee record so task assignments work.

Stop the Flask server with `Ctrl+C`.

The app provides these endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/signup` | Accepts JSON `{ "name", "email", "password", "accountType" }`; admin signup requires an address in `ADMIN_EMAILS` or the legacy `ADMIN_EMAIL`, while all other signups create employees. |
| `POST` | `/api/login` | Accepts JSON `{ "email", "password" }`; returns the authenticated user, directly or under a `user` property. |
| `GET` | `/api/me` | Returns the current user, directly or under a `user` property; returns `401` if signed out. |
| `POST` | `/api/logout` | Clears the session. |
| `GET` | `/api/admin/dashboard` | Checks admin access. |
| `GET` | `/api/manager/dashboard` | Checks manager/admin access. |
| `GET` | `/api/employee/dashboard` | Checks authenticated access. |
| `GET` | `/api/workspace` | Admin loads all records; employees receive only their assigned tasks. |
| `GET`, `POST` | `/api/employees` | Admin lists or creates employees. |
| `PATCH` | `/api/employees/{id}` | Admin updates an employee. |
| `PATCH` | `/api/employees/{id}/status` | Admin activates or deactivates an employee. |
| `GET`, `POST` | `/api/teams` | Admin lists or creates teams. |
| `PATCH`, `DELETE` | `/api/teams/{id}` | Admin updates or deletes a team. |
| `GET`, `POST` | `/api/projects` | Admin lists or creates projects. |
| `PATCH`, `DELETE` | `/api/projects/{id}` | Admin updates or deletes a project. |
| `GET`, `POST` | `/api/tasks` | Admin lists all tasks or creates a task; employees list only assigned tasks. |
| `PATCH`, `DELETE` | `/api/tasks/{id}` | Admin manages tasks; employees may update only the status of their assigned tasks. |

Successful responses should be JSON. Error responses can use `{ "error": "Readable message" }` or `{ "message": "Readable message" }`. The frontend includes cookies on requests, does not store credentials in browser storage, handles `401` as session expiry, and treats `403` as access denied without logging the user out.

Management records are stored in the same `users.db` file as authentication. Teams store members in a join table; projects store the explicitly entered progress percentage; tasks store project, assignee, due date, priority, and status. Deleting a team or project clears its references from dependent records rather than deleting those records.

Run the authentication and management tests with `python -m unittest -v test_auth test_management`.

## Production notes

Local development generates a random session key when `SECRET_KEY` is not set; sessions expire when the server restarts. Set a strong, stable `SECRET_KEY` and `APP_ENV=production` before deployment or the app will refuse to start. Enable secure cookies over HTTPS, add CSRF protection appropriate for your deployment, and run behind a production WSGI server instead of Flask's development server. This project deliberately contains no production secrets.
