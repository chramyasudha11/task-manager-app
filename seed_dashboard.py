"""Seed database for Member 6 — Admin + Manager Dashboard.
Provides 48 employees and 326 total tasks (218 completed, 31 overdue, 77 pending/in-progress).
"""

import sqlite3
import os
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.db")

EMPLOYEES_DATA = [
    # Admin (1)
    ("Sarah Chen", "admin@taskspace.com", "ADMIN", "Management", "VP of Engineering & Org Admin"),
    
    # Managers (4)
    ("David Miller", "david.miller@taskspace.com", "MANAGER", "Engineering", "Engineering Manager"),
    ("Elena Rostova", "elena.rostova@taskspace.com", "MANAGER", "Product", "Lead Product Manager"),
    ("Marcus Vance", "marcus.vance@taskspace.com", "MANAGER", "DevOps & Infra", "Cloud & Infra Manager"),
    ("Aisha Patel", "aisha.patel@taskspace.com", "MANAGER", "Design & UX", "Design Systems Lead"),

    # Frontend Team (9)
    ("Liam Johnson", "liam.j@taskspace.com", "EMPLOYEE", "Frontend", "Senior React Engineer"),
    ("Emma Watson", "emma.w@taskspace.com", "EMPLOYEE", "Frontend", "Frontend UI Developer"),
    ("Noah Garcia", "noah.g@taskspace.com", "EMPLOYEE", "Frontend", "JavaScript / TS Specialist"),
    ("Olivia Martinez", "olivia.m@taskspace.com", "EMPLOYEE", "Frontend", "CSS & Animations Architect"),
    ("Lucas Brown", "lucas.b@taskspace.com", "EMPLOYEE", "Frontend", "Web Performance Engineer"),
    ("Mia Davis", "mia.d@taskspace.com", "EMPLOYEE", "Frontend", "Design-to-Code Developer"),
    ("Ethan Wilson", "ethan.w@taskspace.com", "EMPLOYEE", "Frontend", "Accessibility Specialist"),
    ("Harper Taylor", "harper.t@taskspace.com", "EMPLOYEE", "Frontend", "Mobile Web Developer"),
    ("James Anderson", "james.a@taskspace.com", "EMPLOYEE", "Frontend", "Frontend Engineer"),

    # Backend Team (11)
    ("Benjamin Thomas", "ben.t@taskspace.com", "EMPLOYEE", "Backend", "Principal Python Architect"),
    ("Amelia Jackson", "amelia.j@taskspace.com", "EMPLOYEE", "Backend", "Senior API Specialist"),
    ("Alexander White", "alex.w@taskspace.com", "EMPLOYEE", "Backend", "Database & Query Engineer"),
    ("Charlotte Harris", "charlotte.h@taskspace.com", "EMPLOYEE", "Backend", "Microservices Engineer"),
    ("Daniel Martin", "daniel.m@taskspace.com", "EMPLOYEE", "Backend", "Distributed Systems Engineer"),
    ("Sophia Thompson", "sophia.t@taskspace.com", "EMPLOYEE", "Backend", "Authentication & Security Dev"),
    ("Henry Robinson", "henry.r@taskspace.com", "EMPLOYEE", "Backend", "Backend Developer"),
    ("Isabella Clark", "isabella.c@taskspace.com", "EMPLOYEE", "Backend", "Cache & Queue Specialist"),
    ("Matthew Lewis", "matthew.l@taskspace.com", "EMPLOYEE", "Backend", "REST/gRPC Engineer"),
    ("Ava Lee", "ava.l@taskspace.com", "EMPLOYEE", "Backend", "Search & ETL Specialist"),
    ("Sebastian Hall", "sebastian.h@taskspace.com", "EMPLOYEE", "Backend", "Junior Backend Dev"),

    # DevOps & Infrastructure (6)
    ("Jack Allen", "jack.a@taskspace.com", "EMPLOYEE", "DevOps & Infra", "Kubernetes & Cloud Architect"),
    ("Evelyn Young", "evelyn.y@taskspace.com", "EMPLOYEE", "DevOps & Infra", "CI/CD Pipeline Lead"),
    ("Owen Hernandez", "owen.h@taskspace.com", "EMPLOYEE", "DevOps & Infra", "Site Reliability Engineer (SRE)"),
    ("Abigail King", "abigail.k@taskspace.com", "EMPLOYEE", "DevOps & Infra", "Terraform & IaC Specialist"),
    ("Samuel Wright", "samuel.w@taskspace.com", "EMPLOYEE", "DevOps & Infra", "Security Operations Engineer"),
    ("Chloe Lopez", "chloe.l@taskspace.com", "EMPLOYEE", "DevOps & Infra", "Monitoring & Observability Dev"),

    # Product & Architecture (5)
    ("Daniel Hill", "daniel.h@taskspace.com", "EMPLOYEE", "Product", "Senior Product Strategist"),
    ("Emily Scott", "emily.s@taskspace.com", "EMPLOYEE", "Product", "Technical Product Owner"),
    ("Michael Green", "michael.g@taskspace.com", "EMPLOYEE", "Product", "Data & Analytics PM"),
    ("Ella Adams", "ella.a@taskspace.com", "EMPLOYEE", "Product", "User Journey Researcher"),
    ("Logan Baker", "logan.b@taskspace.com", "EMPLOYEE", "Product", "Release Coordinator"),

    # Design & UI/UX (5)
    ("Grace Gonzalez", "grace.g@taskspace.com", "EMPLOYEE", "Design & UX", "Senior Product Designer"),
    ("Aiden Nelson", "aiden.n@taskspace.com", "EMPLOYEE", "Design & UX", "Interaction Designer"),
    ("Lily Carter", "lily.c@taskspace.com", "EMPLOYEE", "Design & UX", "UX Researcher & Prototyper"),
    ("Carter Mitchell", "carter.m@taskspace.com", "EMPLOYEE", "Design & UX", "Visual Design Specialist"),
    ("Zoe Perez", "zoe.p@taskspace.com", "EMPLOYEE", "Design & UX", "Design Systems Engineer"),

    # QA & Automation (7)
    ("Mason Roberts", "mason.r@taskspace.com", "EMPLOYEE", "QA & Automation", "Lead Automation Architect"),
    ("Penelope Turner", "penelope.t@taskspace.com", "EMPLOYEE", "QA & Automation", "End-to-End Test Specialist"),
    ("Leo Phillips", "leo.p@taskspace.com", "EMPLOYEE", "QA & Automation", "Load & Stress Test Engineer"),
    ("Riley Campbell", "riley.c@taskspace.com", "EMPLOYEE", "QA & Automation", "API Testing Specialist"),
    ("Gabriel Parker", "gabriel.p@taskspace.com", "EMPLOYEE", "QA & Automation", "Regression QA Engineer"),
    ("Hannah Evans", "hannah.e@taskspace.com", "EMPLOYEE", "QA & Automation", "Mobile Device QA Tester"),
    ("Wyatt Edwards", "wyatt.e@taskspace.com", "EMPLOYEE", "QA & Automation", "Security QA Analyst"),
]

PROJECTS = [
    ("Core Platform", 88),
    ("Customer Portal", 64),
    ("Mobile App v2", 58),
    ("Payment Gateway", 46),
    ("Security & Compliance", 40),
    ("Analytics Suite", 30)
]

def seed():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Ensure users columns
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'EMPLOYEE'
        )
    """)
    u_cols = {r[1] for r in cursor.execute("PRAGMA table_info(users)").fetchall()}
    if "team" not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN team TEXT DEFAULT 'Engineering'")
    if "job_title" not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN job_title TEXT DEFAULT 'Software Engineer'")

    # Ensure tasks columns
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Pending',
            priority TEXT NOT NULL DEFAULT 'Medium',
            category TEXT NOT NULL DEFAULT 'Personal',
            due_date TEXT,
            created_by INTEGER NOT NULL,
            assigned_to INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users(id),
            FOREIGN KEY (assigned_to) REFERENCES users(id)
        )
    """)
    t_cols = {r[1] for r in cursor.execute("PRAGMA table_info(tasks)").fetchall()}
    if "project" not in t_cols:
        cursor.execute("ALTER TABLE tasks ADD COLUMN project TEXT DEFAULT 'Core Platform'")
    if "is_completed" not in t_cols:
        cursor.execute("ALTER TABLE tasks ADD COLUMN is_completed INTEGER DEFAULT 0")

    # Clear old data for clean seed
    cursor.execute("DELETE FROM tasks")
    cursor.execute("DELETE FROM users")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('users', 'tasks')")

    default_pw = generate_password_hash("password123")
    user_ids = []
    user_team_map = {}

    for name, email, role, team, title in EMPLOYEES_DATA:
        cursor.execute("""
            INSERT INTO users (name, email, password, role, team, job_title)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, email, default_pw, role, team, title))
        uid = cursor.lastrowid
        user_ids.append(uid)
        user_team_map[uid] = team

    print(f"Seeded {len(user_ids)} users (target: 48).")

    # Target tasks: 326 total
    # 218 Completed
    # 31 Overdue (Pending / In Progress with past due date)
    # 77 Pending / In Progress (46 In Progress, 31 Pending with future/today due date)
    #
    # Priority counts:
    # High: 74
    # Medium: 182
    # Low: 70
    #
    # Projects:
    # Core Platform: 88
    # Customer Portal: 64
    # Mobile App v2: 58
    # Payment Gateway: 46
    # Security & Compliance: 40
    # Analytics Suite: 30

    # Prepare project queue matching project limits
    project_pool = []
    for proj_name, count in PROJECTS:
        project_pool.extend([proj_name] * count)

    # Prepare status & overdue setup
    # 218 Completed
    # 31 Overdue (16 High, 12 Medium, 3 Low)
    # 46 In Progress (18 High, 20 Medium, 8 Low)
    # 31 Pending (5 High, 20 Medium, 6 Low)
    # Total High: 35 (comp) + 16 (overdue) + 18 (in_prog) + 5 (pending) = 74
    # Total Low: 53 (comp) + 3 (overdue) + 8 (in_prog) + 6 (pending) = 70
    # Total Medium: 130 (comp) + 12 (overdue) + 20 (in_prog) + 20 (pending) = 182
    # Total = 74 + 70 + 182 = 326!

    specs = []
    # 1. Overdue tasks (31)
    for _ in range(16):
        specs.append({"status": "In Progress", "priority": "High", "is_overdue": True})
    for _ in range(12):
        specs.append({"status": "Pending", "priority": "Medium", "is_overdue": True})
    for _ in range(3):
        specs.append({"status": "Pending", "priority": "Low", "is_overdue": True})

    # 2. In Progress active (46)
    for _ in range(18):
        specs.append({"status": "In Progress", "priority": "High", "is_overdue": False})
    for _ in range(20):
        specs.append({"status": "In Progress", "priority": "Medium", "is_overdue": False})
    for _ in range(8):
        specs.append({"status": "In Progress", "priority": "Low", "is_overdue": False})

    # 3. Pending active (31)
    for _ in range(5):
        specs.append({"status": "Pending", "priority": "High", "is_overdue": False})
    for _ in range(20):
        specs.append({"status": "Pending", "priority": "Medium", "is_overdue": False})
    for _ in range(6):
        specs.append({"status": "Pending", "priority": "Low", "is_overdue": False})

    # 4. Completed tasks (218)
    for _ in range(35):
        specs.append({"status": "Completed", "priority": "High", "is_overdue": False})
    for _ in range(130):
        specs.append({"status": "Completed", "priority": "Medium", "is_overdue": False})
    for _ in range(53):
        specs.append({"status": "Completed", "priority": "Low", "is_overdue": False})

    assert len(specs) == 326, f"Expected 326 tasks, got {len(specs)}"
    assert len(project_pool) == 326, f"Expected 326 project slots, got {len(project_pool)}"

    # Task templates by category & project
    TASK_TITLES = {
        "Core Platform": [
            "Upgrade Redis session cache cluster", "Refactor database connection pooler",
            "Implement multi-region replication", "Optimize GraphQL query latency",
            "Zero-downtime database migration", "Kafka event streaming pipeline upgrade",
            "API Gateway rate limiter configuration", "Container autoscaling tuning",
            "Audit memory footprint on worker nodes", "Migrate legacy cron jobs to Celery"
        ],
        "Customer Portal": [
            "Redesign customer onboarding funnel", "Implement self-serve billing invoice download",
            "Add multi-factor authentication support", "Customer account activity logs view",
            "Dark mode support for dashboard settings", "Fix responsiveness on iPad viewport",
            "Improve live chat widget performance", "Export CSV reports in background job",
            "Password reset security workflow update", "Notification preference center UI"
        ],
        "Mobile App v2": [
            "Implement biometric face/fingerprint login", "Offline task sync queue with SQLite",
            "Push notification deep-linking handler", "Refactor bottom navigation gesture controller",
            "Optimize app bundle size under 25MB", "Native camera barcode scanning integration",
            "Dark theme color palette tuning", "Memory leak fix in infinite scroll list",
            "App Store submission compliance review", "Bi-directional WebSocket status sync"
        ],
        "Payment Gateway": [
            "Stripe 3D-Secure 2.0 checkout update", "PayPal recurring subscription webhook",
            "Automated refund processing endpoint", "PCI-DSS compliance log auditing",
            "Currency conversion rate caching layer", "Failed payment retry exponential backoff",
            "Invoice PDF generation speed optimization", "SEPA direct debit flow integration",
            "Fraud detection risk score thresholding", "Tax calculation integration with Avalara"
        ],
        "Security & Compliance": [
            "SOC2 Type II compliance evidence export", "Penetration test vulnerability remediation",
            "Rotate all production JWT signing keys", "Enforce strict CSP and HSTS headers",
            "GDPR right-to-be-forgotten deletion workflow", "Role-based granular access audit",
            "Static analysis code scanning CI rule", "Secrets scanning in Git commit pre-hooks",
            "Vulnerability patch for OpenSSL dependency", "Audit trail logging verification"
        ],
        "Analytics Suite": [
            "Build real-time executive dashboard widget", "Clickhouse aggregation table partitioning",
            "Export raw telemetry to Snowflake S3", "User retention cohort visualization",
            "Event tracking telemetry schema validation", "Conversion funnel drop-off analytics",
            "Scheduled email PDF digest generator", "Data freshness latency monitor",
            "Query optimizer for high-cardinality metrics", "Dashboard widget drag-and-drop builder"
        ]
    }

    base_date = datetime(2026, 10, 22, 10, 0, 0, tzinfo=timezone.utc)

    # Insert tasks
    # Distribute fairly across the 48 employees
    for i, spec in enumerate(specs):
        proj = project_pool[i]
        titles = TASK_TITLES.get(proj, ["General Engineering Task"])
        title = f"{titles[i % len(titles)]} [#{i+101}]"
        
        # Determine due date
        if spec["is_overdue"]:
            days_ago = (i % 25) + 3 # 3 to 27 days past
            due_dt = base_date - timedelta(days=days_ago)
        elif spec["status"] == "Completed":
            days_ago = (i % 45) + 2
            due_dt = base_date - timedelta(days=days_ago)
        else:
            days_future = (i % 30) + 1
            due_dt = base_date + timedelta(days=days_future)

        due_date_str = due_dt.strftime("%Y-%m-%d")
        created_dt = base_date - timedelta(days=60 - (i % 55))
        created_str = created_dt.isoformat()
        updated_str = base_date.isoformat()

        # Assignee: distribute across employees (user_ids)
        # Give managers slightly fewer tasks, non-managers standard workload
        assignee_id = user_ids[i % len(user_ids)]
        creator_id = user_ids[0] # Sarah Chen created org tasks
        is_completed_val = 1 if spec["status"] == "Completed" else 0

        cursor.execute("""
            INSERT INTO tasks (
                title, description, status, priority, category,
                project, due_date, created_by, assigned_to,
                is_completed, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            title,
            f"Execution details for {title} under project {proj}.",
            spec["status"],
            spec["priority"],
            "Work",
            proj,
            due_date_str,
            creator_id,
            assignee_id,
            is_completed_val,
            created_str,
            updated_str
        ))

    conn.commit()

    # Verification
    total_users = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_tasks = cursor.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    completed_tasks = cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'Completed'").fetchone()[0]
    today_str = base_date.strftime("%Y-%m-%d")
    overdue_tasks = cursor.execute(
        "SELECT COUNT(*) FROM tasks WHERE status != 'Completed' AND due_date < ?", (today_str,)
    ).fetchone()[0]
    pending_tasks = cursor.execute(
        "SELECT COUNT(*) FROM tasks WHERE status IN ('Pending', 'In Progress') AND due_date >= ?", (today_str,)
    ).fetchone()[0]

    print("\n--- SEED VERIFICATION ---")
    print(f"Total Employees: {total_users} (Expected: 48)")
    print(f"Total Tasks:     {total_tasks} (Expected: 326)")
    print(f"Completed:       {completed_tasks} (Expected: 218)")
    print(f"Overdue:         {overdue_tasks} (Expected: 31)")
    print(f"Active Pending:  {pending_tasks} (Expected: 77)")
    print(f"Sum (Comp+Ovd+Pend): {completed_tasks + overdue_tasks + pending_tasks} (Expected: 326)")
    conn.close()

if __name__ == "__main__":
    seed()
