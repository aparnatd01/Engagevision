# ENGAGEVISION
## AI-Based Student Engagement Monitoring System Using Computer Vision

> **Sprint 1 + Sprint 2 — Complete Foundation: Authentication · MySQL · Role-Based Access · Teacher Management**

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [Project Structure](#3-project-structure)
4. [Prerequisites](#4-prerequisites)
5. [Database Setup](#5-database-setup)
6. [Environment Configuration](#6-environment-configuration)
7. [Installing Dependencies](#7-installing-dependencies)
8. [Creating the Admin Account](#8-creating-the-admin-account)
9. [Running the Application](#9-running-the-application)
10. [User Roles & Login Flow](#10-user-roles--login-flow)
11. [Admin: Manage Teachers](#11-admin-manage-teachers)
12. [Teacher Login Flow](#12-teacher-login-flow)
13. [Testing Sprint 1](#13-testing-sprint-1)
14. [Testing Sprint 2](#14-testing-sprint-2)
15. [Sprint 1 — Completed Features](#15-sprint-1--completed-features)
16. [Sprint 2 — Completed Features](#16-sprint-2--completed-features)
17. [Security Notes](#17-security-notes)
18. [Future Sprints Roadmap](#18-future-sprints-roadmap)

---

## 1. Project Overview

**ENGAGEVISION** is an institution-controlled web application for monitoring student engagement in classrooms using AI and Computer Vision.

The system is designed for colleges and universities.

**Two roles only:**
- **Admin** — Creates and manages teacher accounts, classes, sections, and views all reports.
- **Teacher** — Logs in with their assigned credentials, views their classes, and runs AI monitoring sessions (Sprint 3+).

**There is NO public student login or registration.** Students are tracked as classroom participants through AI video analysis only (Sprint 3+).

---

## 2. Technology Stack

| Layer            | Technology                           |
|------------------|--------------------------------------|
| Web Framework    | Flask 3.x (Python)                   |
| Database         | MySQL (via PyMySQL)                  |
| Auth             | Flask Sessions + Werkzeug hashing    |
| UI / CSS         | Vanilla CSS with custom design system|
| Icons            | Font Awesome 6                       |
| Fonts            | Google Fonts — Inter                 |
| Charts           | Chart.js 4                           |
| AI (Sprint 3+)   | YOLOv8 + MediaPipe (not yet active)  |
| PDF Reports      | ReportLab (Sprint 3+)                |

---

## 3. Project Structure

```
ENGAGEVISION/
│
├── run.py                   # Flask entry point
├── requirements.txt         # Python dependencies (Sprint 1+2)
├── schema.sql               # Database schema (root copy)
├── .env.example             # Environment variable template
├── .env                     # Your real config (DO NOT COMMIT)
├── setup_admin.py           # Admin account bootstrap script
├── README.md
│
├── database/
│   └── schema.sql           # Full database schema
│
└── app/
    ├── __init__.py          # Flask application factory
    ├── config.py            # Configuration from environment
    ├── database.py          # MySQL connection + query helpers
    ├── models.py            # All database query functions
    ├── decorators.py        # login_required, admin_required, teacher_required
    │
    ├── auth/
    │   └── routes.py        # Login / Logout routes  (/auth/login, /auth/logout)
    ├── admin/
    │   └── routes.py        # Admin CRUD: teachers, classes, sections, reports
    ├── dashboard/
    │   └── routes.py        # Teacher dashboard routes  (/teacher/dashboard)
    ├── monitoring/
    │   └── routes.py        # AI monitoring placeholder  (/monitoring/)
    ├── reports/
    │   └── routes.py        # Engagement reports + PDF  (/reports/)
    │
    ├── templates/
    │   ├── base.html        # Main layout with sidebar + topbar
    │   ├── auth/
    │   │   └── login.html   # ENGAGEVISION professional login page
    │   ├── admin/
    │   │   ├── dashboard.html       # Admin dashboard with dynamic stats
    │   │   ├── teachers.html        # Manage teachers list + search
    │   │   ├── teacher_form.html    # Add / Edit teacher form
    │   │   ├── view_teacher.html    # View teacher details
    │   │   ├── report_detail.html   # Admin session report view
    │   │   ├── reports.html         # Admin all reports list
    │   │   ├── profile.html         # Admin profile + change password
    │   │   ├── classes.html         # (Sprint 3) Class management
    │   │   ├── sections.html        # (Sprint 3) Section management
    │   │   └── assignments.html     # (Sprint 3) Teacher assignments
    │   ├── teacher/
    │   │   ├── dashboard.html           # Teacher dashboard
    │   │   ├── my_classes.html          # Teacher's assigned classes
    │   │   ├── profile.html             # Teacher profile + change password
    │   │   ├── reports.html             # Reports placeholder
    │   │   └── monitoring_placeholder.html  # Monitoring placeholder
    │   └── errors/
    │       ├── 403.html     # Access Denied
    │       ├── 404.html     # Not Found
    │       └── 500.html     # Server Error
    │
    └── static/
        ├── css/
        │   └── style.css    # Complete academic design system
        └── js/
            ├── main.js      # Sidebar toggle, flash messages, utilities
            ├── validation.js # Client-side form validation
            ├── dashboard.js  # Dashboard-specific JS
            └── reports.js    # Reports-specific JS
```

---

## 4. Prerequisites

Before you begin, ensure you have:

- **Python 3.9+** installed — [python.org](https://python.org)
- **MySQL 8.0+** installed and running — [mysql.com](https://dev.mysql.com/downloads/)
- **pip** (comes with Python)
- An internet connection (to load Google Fonts & Font Awesome CDN)

---

## 5. Database Setup

### Step 1 — Create the database and tables

Open MySQL Workbench or MySQL command line and run:

```bash
mysql -u root -p < schema.sql
```

Or in MySQL Workbench: File → Open SQL Script → select `schema.sql` → Execute.

This creates:
- Database: `engagevision`
- Table: `users` (admins and teachers — all roles)
- Table: `classes`
- Table: `sections`
- Table: `teacher_assignments`
- Table: `students`
- Table: `monitoring_sessions`
- Table: `engagement_reports`
- Table: `engagement_scores`
- Table: `reports`

> **Note:** A placeholder `admin` user is inserted by `schema.sql` with a temporary password hash.
> You MUST run `python setup_admin.py` next to set the real admin password.

---

## 6. Environment Configuration

### Step 2 — Create your .env file

```bash
copy .env.example .env
```

Open `.env` and fill in your MySQL credentials:

```env
SECRET_KEY=your-long-random-secret-key-here
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_root_password
MYSQL_DB=engagevision
FLASK_ENV=development
FLASK_DEBUG=1
```

Generate a secure SECRET_KEY:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 7. Installing Dependencies

### Step 3 — Create virtual environment (recommended)

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
```

### Step 4 — Install packages

```bash
pip install -r requirements.txt
```

---

## 8. Creating the Admin Account

### Step 5 — Run the admin setup script

```bash
python setup_admin.py
```

The script will:
1. Connect to MySQL using your `.env` configuration
2. Show any existing admin accounts
3. Prompt you for the admin username (default: `admin`)
4. Prompt for a secure password (hidden input)
5. Validate password strength (min 8 chars, 1 uppercase, 1 digit)
6. Hash the password using Werkzeug
7. Update the admin account in MySQL

> **Password requirements:** Min 8 characters · 1 uppercase letter · 1 digit

**Example session:**

```
============================================================
  EngageVision — Admin Account Setup
============================================================

Existing admin account(s):
  • ID   1 | admin                | admin@engagevision.edu

Enter admin username to update [default: admin]: admin

Enter new admin password: ●●●●●●●●●
Confirm password:        ●●●●●●●●●

✅ Password updated for admin 'admin'.

============================================================
  Setup complete! You can now log in to EngageVision.
  URL:      http://127.0.0.1:5000
  Username: admin
  Password: (the one you just set)
============================================================
```

---

## 9. Running the Application

### Step 6 — Start the Flask development server

```bash
python run.py
```

Visit: **http://127.0.0.1:5000**

The server will print:

```
============================================================
  EngageVision — AI-Based Engagement Monitoring System
  Running at: http://127.0.0.1:5000
  To create admin: python setup_admin.py
============================================================
```

---

## 10. User Roles & Login Flow

### Admin Login

```
Open http://127.0.0.1:5000
 ↓
Login page (ENGAGEVISION branded)
 ↓
Enter: username = admin
       password = (set in step 8)
 ↓
MySQL authentication + password hash check
 ↓
Session created: user_id, role='admin', full_name
 ↓
Redirect → /admin/dashboard
 ↓
Admin Dashboard — Welcome, [Admin Name]!
```

### Teacher Login

```
Open http://127.0.0.1:5000
 ↓
Login page
 ↓
Enter teacher credentials (created by Admin)
 ↓
MySQL authentication
 ↓
Session created: user_id, role='teacher', full_name
 ↓
Redirect → /teacher/dashboard
 ↓
Teacher Dashboard — Welcome back, [Teacher First Name]!
```

### Role Authorization

| URL                      | Admin | Teacher | Guest |
|--------------------------|-------|---------|-------|
| `/auth/login`            | ✅    | ✅      | ✅    |
| `/admin/dashboard`       | ✅    | ❌ 403  | ❌ Login |
| `/admin/teachers`        | ✅    | ❌ 403  | ❌ Login |
| `/teacher/dashboard`     | ❌ 403 | ✅    | ❌ Login |
| `/monitoring/`           | ❌ 403 | ✅    | ❌ Login |

---

## 11. Admin: Manage Teachers

After logging in as Admin, navigate to **Manage Teachers** in the sidebar.

### Add Teacher

1. Click **+ Add New Teacher**
2. Fill in: First Name, Last Name, Username, Email, Password, Staff ID, Department, Phone
3. Client-side validation runs first
4. Server-side validation: duplicate username, email, staff ID checks
5. Password hashed with Werkzeug `generate_password_hash()`
6. Teacher inserted into MySQL `users` table with `role='teacher'`
7. Success message: *"Teacher [Name] created successfully."*
8. New teacher appears immediately in the list

### View Teacher

Click the **View** icon to see full teacher profile including:
- Name, Username, Email, Staff ID, Department, Phone
- Account Status (Active/Inactive)
- Created Date, Last Login

> Passwords are **never displayed**.

### Edit Teacher

Click **Edit** to modify:
- Name, Email, Staff ID, Department, Phone
- Account Status (Active/Inactive toggle)

Username cannot be changed after creation.

### Activate / Deactivate

- Click **Deactivate** → teacher status = Inactive → teacher **cannot log in**
- Click **Activate** → teacher status = Active → teacher **can log in**
- Confirmation dialog shown before deactivation

### Reset Password

Click **Reset PW** → modal opens → enter new password → saves hashed password.

### Search & Filter

Use the live search box to filter teachers by:
- Name, Username, Staff ID, Department, Email

---

## 12. Teacher Login Flow

After Admin creates a teacher account:

```
Admin creates teacher account
 ↓
MySQL: users table row inserted with role='teacher'
 ↓
Teacher opens http://127.0.0.1:5000
 ↓
Login with teacher username + password
 ↓
Teacher Dashboard — Welcome back, [Teacher First Name]!
 ↓
Shows: Staff ID, Department, Total Sessions, Last Session
 ↓
My Classes section (if assigned)
```

---

## 13. Testing Sprint 1

### Test Checklist

```
✅ Open http://127.0.0.1:5000 → redirects to /auth/login
✅ Login page shows ENGAGEVISION branding + subtitle
✅ Empty username → "Username is required" (client-side)
✅ Empty password → "Password is required" (client-side)
✅ Wrong credentials → "Invalid username or password." (server-side)
✅ Admin login → Admin Dashboard
✅ Teacher login → Teacher Dashboard
✅ Admin dashboard shows "Welcome, [Admin Name]"
✅ Teacher dashboard shows "Welcome back, [Teacher First Name]"
✅ Logout → session cleared → login page
✅ After logout: /admin/dashboard → redirects to login
✅ Teacher trying /admin/dashboard → 403 Forbidden
✅ Admin trying /teacher/dashboard → 403 Forbidden
```

---

## 14. Testing Sprint 2

### Teacher Management Test Checklist

```
✅ Admin login
✅ Navigate to: Manage Teachers
✅ Empty state shows "No teachers yet" message
✅ Click + Add New Teacher
✅ Fill form with valid data → teacher created
✅ New teacher appears in list immediately
✅ Stats cards update: Total Teachers, Active Teachers
✅ Login as new teacher → success → Teacher Dashboard
✅ Name appears correctly from MySQL (not hardcoded)
✅ Edit teacher → details updated → success message
✅ Deactivate teacher → status = Inactive
✅ Try to login as deactivated teacher → "Your account has been deactivated"
✅ Activate teacher → status = Active → can login again
✅ Reset teacher password → new password works
✅ Duplicate username → validation error
✅ Duplicate email → validation error
✅ Duplicate staff ID → validation error
✅ Search box filters teacher list in real-time
✅ Admin Dashboard "Total Teachers" stat shows correct count from MySQL
```

---

## 15. Sprint 1 — Completed Features

| Feature                    | Status | Details |
|----------------------------|--------|---------|
| Flask Application          | ✅     | App factory pattern, blueprints |
| MySQL Database             | ✅     | PyMySQL, connection pooling per request |
| Environment Variables      | ✅     | python-dotenv, .env.example provided |
| Admin Authentication       | ✅     | Username + password via MySQL |
| Teacher Authentication     | ✅     | Username + password via MySQL |
| Password Hashing           | ✅     | Werkzeug generate_password_hash / check_password_hash |
| Session Management         | ✅     | user_id, role, full_name stored in session |
| Login Required Decorator   | ✅     | Redirects to login if not authenticated |
| Admin Required Decorator   | ✅     | Returns 403 if not admin |
| Teacher Required Decorator | ✅     | Returns 403 if not teacher |
| Role-based Redirects       | ✅     | Admin → /admin/dashboard, Teacher → /teacher/dashboard |
| Admin Dashboard            | ✅     | Dynamic stats from MySQL (teachers, classes, sessions) |
| Teacher Dashboard          | ✅     | Dynamic name + stats from MySQL |
| Logout                     | ✅     | Session cleared, redirect to login |
| Client-side Validation     | ✅     | JavaScript form validation |
| Server-side Validation     | ✅     | Flask/Python validation |
| Error Pages                | ✅     | 403, 404, 500 pages |
| Professional UI            | ✅     | Navy/Blue/Teal palette, Inter font, sidebar layout |
| Responsive Design          | ✅     | Works on desktop, tablet, mobile |
| No Hardcoded Credentials   | ✅     | All from MySQL only |
| No JSON Database           | ✅     | MySQL exclusively |

---

## 16. Sprint 2 — Completed Features

| Feature                     | Status | Details |
|-----------------------------|--------|---------|
| Manage Teachers Page        | ✅     | `/admin/teachers` with full table |
| Add Teacher Form            | ✅     | All fields, client + server validation |
| Duplicate Detection         | ✅     | Username, email, staff ID uniqueness checks |
| Password Hashing on Create  | ✅     | Werkzeug hash before MySQL INSERT |
| View Teacher Details        | ✅     | Full profile, no password shown |
| Edit Teacher                | ✅     | Update name, email, staff ID, dept, phone, status |
| Activate Teacher            | ✅     | `is_active = 1`, teacher can login |
| Deactivate Teacher          | ✅     | `is_active = 0`, teacher cannot login |
| Toggle Confirmation         | ✅     | Browser confirm() before deactivate |
| Reset Password              | ✅     | Modal popup, new hash saved |
| Live Search Filter          | ✅     | Client-side JS filter on all text |
| Teacher Count in Dashboard  | ✅     | Real count from MySQL |
| Teacher Login Post-Create   | ✅     | Newly created teacher can login immediately |
| Dynamic Teacher Name        | ✅     | Name from MySQL session, not hardcoded |
| Unauthorized Access Block   | ✅     | `/admin/teachers` returns 403 for teachers |

---

## 17. Security Notes

- **Passwords** are hashed using Werkzeug `pbkdf2:sha256` — never stored in plain text
- **Parameterized queries** used throughout — protected against SQL injection
- **Session cookie** set with `HTTPOnly=True`, `SameSite=Lax`
- **Role authorization** enforced at Flask decorator level (server-side)
- **No stack traces** shown to users — error templates used
- **SECRET_KEY** must be changed from the default before deployment
- **`.env` file** must never be committed to version control

---

## 18. Future Sprints Roadmap

| Sprint | Feature |
|--------|---------|
| Sprint 3 | Classes, Sections, Teacher Assignments, Video Upload |
| Sprint 4 | YOLOv8 Face Detection, MediaPipe Facial Features, Engagement Analysis |
| Sprint 5 | Engagement Percentages, High/Medium/Low scoring, Dashboard Analytics |
| Sprint 6 | PDF Reports, Final Testing, Security Audit, Deployment |

The database schema already includes tables for all future sprints:
- `classes`, `sections`, `teacher_assignments` — Sprint 3
- `monitoring_sessions`, `engagement_reports`, `engagement_scores` — Sprint 4+5
- `reports` — Sprint 6

---

*ENGAGEVISION — AI-Based Student Engagement Monitoring System*
*Built with Flask + MySQL + Vanilla CSS*
