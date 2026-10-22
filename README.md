# TaskFlow — Task Manager (Members 1–5 integrated)

Flask + SQLite backend (one `users.db`) and a plain HTML/CSS/JS frontend served by Flask. No npm, no build step.

## Run (Windows PowerShell)
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\seed_demo.py      # optional: demo admin / manager / employees / CRM project
python app.py
```
Open http://127.0.0.1:5000 . Demo logins (password `Demo@1234`): `admin@taskflow.com`, `ramya@taskflow.com` (manager), `rahul@taskflow.com` (employee).
Tests: `python -m unittest discover -s tests -v` (temporary databases, your users.db is safe).

## The 6 dashboards / pages
| # | Page | Who sees it |
|---|------|-------------|
| 1 | Admin Dashboard (people, teams, projects, status/priority, progress, overdue) | ADMIN |
| 2 | Manager Dashboard (project progress, team workload, overdue) | MANAGER |
| 3 | My Dashboard (my counts, up next with status change, my projects) | EMPLOYEE |
| 4 | Employees & Teams (add/edit/view/deactivate, create team, members, manager) | ADMIN |
| 5 | Projects (create, assign team/manager, tree view, progress) | all (admin edits) |
| 6 | Tasks (create/edit/delete/assign/view/change status) | all (employee: view + status) |

## Who owns which file (no overlaps = no merge conflicts)
| Member | Files |
|---|---|
| 1 | `auth.py` (not modified) |
| 2 | `tasks.py`, `tests/test_tasks.py` (not modified) |
| 3 | `dashboard.py` (not modified) |
| 4 | `org_common.py`, `employees.py`, `teams.py`, `projects.py`, `tests/test_org.py`, `scripts/seed_demo.py` |
| 5 | `taskboard.py`, `static/index.html`, `static/style.css`, `static/app.js` |
| shared | `app.py`: only import + `register_blueprint` lines and `init_org_db()` |

How Members 4 and 5 avoid touching others' code:
* New tables only (`teams`, `team_members`, `projects`, `task_projects`). The task-to-project link is the `task_projects` table, so `tasks.py` needs no `project_id` column.
* New `users` columns (`is_active`, `department`, `designation`) are added by `init_org_db()` using a safe `ALTER TABLE`.
* Deactivated users are blocked by a `before_app_request` guard in `org_common.py`, so `auth.py` needs no change.
* Roles use Member 1's `roles_required`; task changes still go through Member 2's `/api/tasks` endpoints.

## Merge steps
1. Pull latest `main`.
2. Member 4: branch `feature/member4-org-management`, add Member 4 files.
3. Member 5: branch `feature/member5-task-frontend`, add Member 5 files.
4. In `app.py` add only your blueprint lines and `init_org_db()`.
5. Never commit `users.db`.

## New API summary
* Employees (ADMIN): `POST/GET /api/employees`, `GET/PUT /api/employees/<id>`, `PATCH .../deactivate|activate`; picker list `GET /api/employees/options` (ADMIN, MANAGER).
* Teams: `POST/GET /api/teams`, `GET/PUT/DELETE /api/teams/<id>`, `POST /api/teams/<id>/members`, `DELETE /api/teams/<id>/members/<uid>`, `PATCH /api/teams/<id>/manager`.
* Projects: `POST/GET /api/projects`, `GET/PUT /api/projects/<id>`, `PATCH .../team`, `PATCH .../manager`, `GET .../progress`.
* Task board: `GET /api/task-board`, `PATCH /api/task-board/<id>/project`, `GET /api/overview`.
* UI status names: `pending` = Assigned, `in_progress` = In Progress, `completed` = Completed.

Local development only: set `SECRET_KEY`, use HTTPS and CSRF protection before any real deployment.
