# 📋 TASKSPACE — Full-Stack Task & Team Management Platform

> A full-stack, enterprise-grade task management web application built with **Python (Flask)**, **SQLite**, and **Vanilla HTML5/CSS3/JavaScript** featuring modern Chart.js analytics, role-based workflows, and a cohesive indigo/slate design system.

---

## 👥 Project & Team Information

* **Repository:** [https://github.com/chramyasudha11/task-manager-app](https://github.com/chramyasudha11/task-manager-app)
* **Active Feature Branch:** `feature/member-6-admin-manager-dashboard`
* **Assigned Role:** **Member 6 — Admin + Manager Dashboard 📊 ⭐**

---

## ✍️ Member 6 Submission Statement (What I Personally Built)

> *"I engineered the core Member 6 Admin and Manager Dashboard featuring exact live KPI metrics (48 Employees, 326 Tasks, 218 Completed, 31 Overdue) alongside 7 interactive Chart.js visualizations.*
> *I built the 48-employee performance table with real-time search, multi-criteria filtering, sorting, pagination, and CSV export, plus the dedicated Manager Command Center with team workload progress and an overdue task alert desk.*
> *I harmonized the entire application under the modern login page design system, connected role-based persona switching, and created automated unit tests to verify all endpoints and data contracts."*

---

## 🌟 Key Features Overview

### 1. 📊 Member 6: Admin & Executive Overview (`/dashboard`)
* **KPI Metrics Cards (Exact Live Dataset):**
  * 👥 **Total Employees:** `48` active enterprise employees across 5 functional departments
  * 📋 **Total Tasks:** `326` org-wide tasks tracked across 6 key projects
  * ✅ **Completed:** `218` tasks finished (`66.9%` completion rate)
  * ⚠️ **Overdue:** `31` tasks requiring immediate managerial attention (`9.5%` overdue rate)
  * ⚡ **Secondary Metrics:** In-progress counts, active pending tasks, velocity rating, sprint period indicator

* **7 Interactive Chart.js Visualizations:**
  1. 📈 **Task Completion Trend:** Multi-week dual-line graph comparing completed vs. created velocity
  2. 🍩 **Pending vs Completed:** High-contrast doughnut breakdown of task execution status
  3. 📊 **Tasks by Priority:** Bar chart profiling distribution across High, Medium, and Low priorities
  4. 📁 **Tasks by Project:** Horizontal bar chart tracking allocation across 6 core projects
  5. 👥 **Tasks by Team:** Departmental distribution across Backend, Frontend, DevOps, QA, Product, and Design
  6. 🏋️ **Employee Workload:** Stacked bar chart showing active vs. completed capacity for team leads
  7. 🎯 **Employee Performance:** Delivery accuracy and completion rate benchmarking

### 2. 👥 Member 6: 48-Employee Breakdown Table
* **Dedicated Data Table:** Lists all 48 employees with columns:
  $$\text{Employee} \quad|\quad \text{Assigned} \quad|\quad \text{Completed} \quad|\quad \text{Pending} \quad|\quad \text{Overdue}$$
* **Interactive Controls:**
  * Real-time search by employee name, job title, or email
  * Department/Team dropdown filtering (Frontend, Backend, DevOps & Infra, QA, Product, Design)
  * One-click "Only Show Overdue" filter toggle
  * Column sorting (by assigned volume, completion %, or overdue count)
  * Responsive client-side pagination (10 per page)
  * Employee drill-down modal with full task breakdown and performance rating
  * One-click **CSV Report Export**

### 3. ⭐ Member 6: Manager View Command Center
* **Team Progress & Workload:** Card grid showcasing department leads, member counts, total assigned volume, and completion progress bars
* **Team Completion %:** Live calculated progress bars per functional group
* **Overdue Tasks Alert Desk:** High-priority management desk surfacing all **31 overdue tasks** with direct "Send Nudge" reminder actions
* **High-Priority Task Tracker:** Real-time visibility into mission-critical sprint tasks

### 4. 🎨 Design System Harmonization
* Unified visual identity matching the **Login Page**:
  * Clean canvas background (`#f5f7fb`)
  * Crisp white cards (`#ffffff`) with subtle borders (`#e8edf4`) and soft elevation
  * Royal indigo brand accent (`#4f64e8`) with dark hover (`#3e50cb`) and soft tags (`#eef0ff`)
  * Status tints: Emerald green (`#1b9b70`), Amber (`#a66b14`), Rose red (`#c94d58`)
  * Executive gradient hero banner replicating the signature brand panel

### 5. 🔐 Authentication & Workspace Integration
* Split-screen authentication (`/login`, `/signup`) with secure password hashing (`werkzeug.security`)
* 1-Click Persona Demo Switcher (Admin `Sarah Chen`, Manager `David Miller`, Employee `Liam Johnson`)
* Workspace Homepage (`/`): 326 live tasks, search `/` shortcut, category filters, task creation modal, bulk actions, and CSV export

---

## 🛠️ Technology Stack

| Layer | Technologies Used |
| :--- | :--- |
| **Backend** | Python 3.10+, Flask, SQLite3, Werkzeug Security |
| **Frontend** | HTML5, CSS3 (Modern Flexbox/Grid), Vanilla JavaScript (ES6+) |
| **Charts** | Chart.js 4.4.2 (bundled locally for offline reliability) |
| **Testing** | Python `unittest` |
| **Version Control** | Git, GitHub Feature Branching Workflow |

---

## 🚀 Quickstart & Setup Guide

### 1. Clone the Repository & Checkout Branch
```bash
git clone https://github.com/chramyasudha11/task-manager-app.git
cd task-manager-app
git checkout feature/member-6-admin-manager-dashboard
```

### 2. Set Up Virtual Environment & Dependencies
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Seed Database with 48 Employees & 326 Tasks
```bash
python seed_dashboard.py
```
*(Creates `users.db` populated with exactly 48 team members and 326 tasks matching required KPIs: 218 completed, 31 overdue, 77 in-progress/pending).*

### 4. Run the Application
```bash
python app.py
```
Open your browser to: **`http://127.0.0.1:5000`**

---

## 🌐 Application URL Reference

| View | Route | Description |
| :--- | :--- | :--- |
| **Admin & Manager Dashboard** | [`/dashboard`](http://127.0.0.1:5000/dashboard) | Member 6 core dashboard: KPIs, 7 charts, 48 employees, manager view |
| **Manager View Direct** | [`/manager`](http://127.0.0.1:5000/manager) | Deep link directly into the Manager Command Center |
| **Admin View Direct** | [`/admin`](http://127.0.0.1:5000/admin) | Deep link directly into Executive Overview |
| **Workspace Tasks** | [`/`](http://127.0.0.1:5000/) | Live workspace managing 326 tasks with filters and modals |
| **Authentication** | [`/login`](http://127.0.0.1:5000/login) | Sign in and switch roles between Admin, Manager, and Employee |

---

## 📡 REST API Reference

### Dashboard Endpoints
* **`GET /api/dashboard/kpi`** — Returns top-level KPI metrics (`total_employees`: 48, `total_tasks`: 326, `completed`: 218, `overdue`: 31).
* **`GET /api/dashboard/charts`** — Returns structured data series for all 7 Chart.js visualizations.
* **`GET /api/dashboard/employees`** — Returns list of 48 employees with `assigned`, `completed`, `pending`, and `overdue` counts.
* **`GET /api/dashboard/manager-view`** — Returns team progress, workload statistics, 31 overdue tasks, and high-priority items.
* **`POST /api/dashboard/switch-role`** — Switches active session persona (`{"role": "ADMIN" | "MANAGER" | "EMPLOYEE"}`).
* **`GET /api/dashboard/current-user`** — Returns current session persona and permissions.

### Task Management Endpoints
* **`GET /api/tasks`** — Retrieves task list with optional filtering (`category`, `priority`, `status`, `search`).
* **`POST /api/tasks`** — Creates a new task with title, category, priority, due date, and assignees.
* **`PUT /api/tasks/<id>`** — Updates an existing task.
* **`DELETE /api/tasks/<id>`** — Deletes a task.
* **`POST /api/tasks/<id>/complete`** — Toggles task completion status.

---

## 🧪 Automated Testing

Run the automated test suite to verify all metrics and API data contracts:
```bash
python -m unittest test_dashboard.py
```
**Test Coverage:**
* ✅ Exact KPI metrics validation (`48`, `326`, `218`, `31`)
* ✅ All 7 management charts data validation
* ✅ 48-employee table schema and counts validation
* ✅ Manager view, team workload, and 31 overdue tasks alert desk
* ✅ Role switching and session persona endpoints
* ✅ HTTP 200 route rendering for `/dashboard` and `/manager`

---

## 🌿 Git Strategy & Workflow

* **Branching model:** `feature/member-6-admin-manager-dashboard` branched from origin.
* **Commit discipline:** Clear semantic messages adhering to team convention.
* **Conflicts resolved:** Harmonized merge conflicts between task workspace templates and dashboard blueprints.
* **No direct pushes to main:** All feature code prepared on dedicated feature branches for peer review.
