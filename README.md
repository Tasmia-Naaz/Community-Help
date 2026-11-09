# Community Help Connect

> **A Centralized Hyperlocal Peer-to-Peer Community Support & Emergency Coordination Web Application**  
> *Developed with Python Flask, PostgreSQL, Flask-SQLAlchemy, and Bootstrap 5 for academic evaluation  demonstration.*

---

## 1. Project Overview & Problem Statement

In many neighborhoods, individuals and vulnerable residents often struggle to obtain timely local assistance for everyday difficulties (e.g., pharmacy pickups, temporary mobility transit, emergency food staples, or lost pets). Simultaneously, willing neighborhood volunteers and community members with surplus resources remain disconnected across fragmented chat groups and isolated platforms.

**Community Help Connect** solves this problem by providing a centralized, transparent, and secure web application that connects help seekers directly with nearby volunteers and resource donors.

### Key Architectural Highlights:
- **No Paid APIs or Machine Learning required:** Employs deterministic, transparent **Rule-Based Proximity Matching**.
- **Concurrency-Safe Operations:** Database row-locking (`with_for_update()`) prevents duplicate task acceptance by multiple volunteers.
- **Role-Based Access Control (RBAC):** Strict server-side verification using custom Python decorators; URL manipulation and ID tampering are rejected.
- **Audit Logging:** Every status transition across the lifecycle is permanently recorded in a `status_history` audit trail with timestamps and acting user IDs.
- **Crisis Response:** Administrator-managed **Emergency Mode** that broadcasts in-app notifications and prioritizes relief requests in affected zones.

---

## 2. Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend** | Python 3.10+ / Flask 3.x | Lightweight, modular WSGI application |
| **Database** | MySQL 8.0+ | Relational data persistence with foreign keys and ACID transactions |
| **Database Driver** | PyMySQL | Pure-Python MySQL client driver |
| **ORM** | Flask-SQLAlchemy | Object-relational mapping and transaction handling |
| **Frontend** | HTML5, CSS3, JavaScript | Semantic structure and responsive micro-interactions |
| **UI Framework** | Bootstrap 5.3 & Bootstrap Icons | Modern, mobile-responsive layout without npm build pipelines |
| **Templating** | Jinja2 | Dynamic server-side rendering and reusable component layouts |
| **Forms & Security** | Flask-WTF / WTForms | Server-side validation and CSRF token protection |
| **Password Security**| Werkzeug Security | Industry-standard salted password hashing (`generate_password_hash`) |
| **Environment** | python-dotenv | Secure secret and credential configuration from `.env` |
| **Test Suite** | Pytest | Automated verification of auth, concurrency, and workflows |

---

## 3. The Six Service Categories

All requests and resource offers are organized into six distinct service categories:
1. **Essential Items Assistance:** Clothes, warm blankets, school stationery kits, hygiene packs, and non-perishable staples.
2. **Surplus Food Sharing:** Manual reporting of excess edible meals and groceries from restaurants, caterers, or households with strict expiry dates.
3. **Medical Assistance:** Pharmacy prescription pickups, voluntary blood donor connections, and medical equipment lending (wheelchairs, crutches).
4. **Transportation Assistance:** Volunteer rides for elderly or disabled neighbors to scheduled hospital or therapy visits.
5. **Emergency Relief:** Potable water delivery, sandbags, and emergency supplies during flash floods or severe storms.
6. **Lost and Found Assistance:** Notices for missing pets and lost personal community possessions.

---

## 4. Temporary Demo Credentials (For Testing)

These accounts are seeded into the database using `python seed.py --demo`:

| Role | Email Address | Password | Intended Workflow |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin@communityhelp.org` | `Admin@12345` | Moderation, metrics, emergency mode, account verification |
| **Help Seeker** | `seeker@example.com` | `Seeker@123` | Posting help requests, tracking status, cancelling requests |
| **Volunteer** | `volunteer@example.com` | `Volunteer@123` | Browsing open tasks, accepting tasks, updating progress |
| **Resource Donor** | `donor@example.com` | `Donor@123` | Listing supplies/meals, monitoring status, withdrawing items |

---

## 5. Windows PowerShell Setup Instructions

Follow these exact step-by-step instructions in **VS Code on Windows**:

### Step 1: Open Project in VS Code
1. Open VS Code.
2. Click **File &rarr; Open Folder...** and select `f:\Community help\community_help_connect` (or the folder where you extracted this project).
3. Open a new PowerShell terminal in VS Code: **Terminal &rarr; New Terminal** (`Ctrl + ` `~`).

### Step 2: Create and Activate Python Virtual Environment
Run the following PowerShell commands:
```powershell
# Verify Python is installed (Python 3.10 or higher recommended)
python --version

# Create virtual environment named 'venv'
python -m venv venv

# If PowerShell script execution is restricted on your system, allow local scripts:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# Activate the virtual environment
.\venv\Scripts\Activate.ps1
```
*(You will see `(venv)` appear at the beginning of your PowerShell terminal prompt).*

### Step 3: Install Required Dependencies
```powershell
pip install -r requirements-dev.txt
```

### Step 4: Create a Supabase project and get its database URL

1. Sign in at [supabase.com/dashboard](https://supabase.com/dashboard) and create a project. Choose a region near your users and set a strong **Database Password**. Save that password securely; it is separate from your Supabase account password.
2. Open the project and choose **Connect** (or **Project Settings → Database → Connection string**).
3. Select the **URI** format and copy the connection string. Use the **Session pooler** connection if a direct connection is unavailable from your network (for example, IPv4-only networks). Use the exact host, port, username, and database name Supabase displays; they vary per project.
   - Direct connection URLs typically resemble `postgresql://postgres:<DB_PASSWORD>@db.<PROJECT_REF>.supabase.co:5432/postgres?sslmode=require`.
   - Session pooler URLs typically resemble `postgresql://postgres.<PROJECT_REF>:<DB_PASSWORD>@<POOLER_HOST>:5432/postgres?sslmode=require`.
   - These are examples only. Prefer the URI copied from the dashboard rather than constructing one yourself.
4. If your database password contains reserved URL characters (such as `@`, `:`, `/`, `#`, or `%`), URL-encode the password portion before placing it in the URI. You can encode it locally without sending it to a website:

```powershell
python -c "from getpass import getpass; from urllib.parse import quote; print(quote(getpass('Database password: '), safe=''))"
```

Replace only `<DB_PASSWORD>` in the copied URI with the encoded value. Keep `?sslmode=require` if it is included in the dashboard URI.

### Step 5: Configure `.env` for Supabase

Copy the example configuration if you have not done so already:

```powershell
Copy-Item .env.example .env
```

In the project-root `.env` file, set these values. `DATABASE_URL` is the PostgreSQL URI from Step 4. In Supabase, find the project API URL and the server-side `service_role` key under **Project Settings → API** (the exact API Keys page label can vary). Use the `service_role` key, not the publishable/anon key, for private server-side document storage.

```ini
SECRET_KEY=replace-with-a-long-random-secret
DATABASE_URL=postgresql://postgres:ENCODED_PASSWORD@HOST:PORT/postgres?sslmode=require
USE_SQLITE_FALLBACK=0

SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVER_ONLY_SERVICE_ROLE_KEY
SUPABASE_STORAGE_BUCKET=volunteer-verification-documents
```

Generate a `SECRET_KEY` locally with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Do not add quotes around values unless required by your `.env` parser, do not commit `.env`, and never paste the `service_role` key into frontend code, chat, source control, or a public issue. It grants privileged access to your Supabase project. A placeholder `SECRET_KEY` is not suitable for production; keep your generated value outside source control.

The app uses SQLAlchemy with Supabase PostgreSQL for application data and the Supabase Storage API for private volunteer documents. No Supabase JavaScript client is required in the browser.

### Step 6: Initialize the database and private Storage bucket

When you first create a Supabase project, it has a PostgreSQL database but **does not yet have this application's tables**. That is expected. The app tables are created by the initialization command below; they do not appear just because the Supabase project/database exists.

For a **new/empty Supabase project**, first create the application's tables and initial admin account from the activated virtual environment:

```powershell
python seed.py --admin-only
```

This command uses the configured `DATABASE_URL`, creates any missing ORM tables, and creates `admin@communityhelp.org` with the development password shown in `seed.py`. This fixed seed credential is for local setup only: never expose it on a public deployment. Provision a separately secured administrator account before going live.

Then run the complete [`supabase_migration.sql`](./supabase_migration.sql) script in **Supabase Dashboard → SQL Editor → New query**. Paste the file's contents, review the target project, and select **Run**. This creates/initializes the feature tables, sends existing volunteers to pending review, creates the private `volunteer-verification-documents` bucket, and installs its Storage policies. It does not erase existing application records.

After both steps, open **Table Editor** in the same Supabase project. You should see application tables such as `users`, `help_requests`, `resource_listings`, `notifications`, `volunteer_verifications`, `conversations`, and `messages`. The Supabase internal `auth` and `storage` schemas are separate; the app's tables are in the `public` schema.

If Table Editor still shows no `public` application tables:

1. Confirm the terminal is open in the repository folder containing `.env`, and that `.env` has the connection URI for this exact Supabase project.
2. Verify the app can connect to the configured database. This prints only the connected database/schema (not the password or full URI):

```powershell
python -c "from app import create_app; from sqlalchemy import text; from extensions import db; app=create_app(); ctx=app.app_context(); ctx.push(); print(db.session.execute(text('select current_database(), current_schema()')).one()); ctx.pop()"
```

3. If the connection succeeds, run `python seed.py --admin-only` again and check its output for errors. Then refresh Table Editor and make sure its schema selector is set to `public`.
4. If that works, run `supabase_migration.sql` in the SQL Editor for verification and Storage setup. Do not run `schema.sql` on Supabase: it is a MySQL script and drops tables.

For an **existing Supabase app database**, back it up first, then run `supabase_migration.sql` in the SQL Editor. Its `IF NOT EXISTS`/conflict-safe statements are intended to preserve existing tables and records. Do not run `schema.sql` on Supabase: it is a MySQL schema script that drops existing tables.

The bucket must remain **private**. Flask checks the signed-in application user's role before using the server-side Storage service key; admins receive short-lived (60-second) signed preview links. Keep the key server-only. The SQL policies also document the folder-based rules for direct Supabase Auth access; that separate access path requires trusted `app_metadata` claims and must not use user-editable metadata.

### Step 7: (Optional) Add demo accounts and sample data

For local evaluation only, run:

```powershell
python seed.py --demo
```

This adds demo Help Seeker, Volunteer, and Donor accounts and sample listings/requests without deleting existing rows. If a demo account already exists, this explicit demo command restores its published password and role access; use it only on a development/demo database. It includes a pre-approved demo volunteer with no identity document, so use it only for demonstration. Real public volunteer registrations must upload an ID and wait for admin approval. Do not seed demo credentials into a production database.

If upgrading a non-Supabase existing MySQL/SQLite installation, the legacy resource-request migration is still available:

```powershell
python migrate_resource_requests.py
```

### Step 8: Run the Web Application

From the activated virtual environment and repository root:

```powershell
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). Register a Help Seeker or Donor to exercise messaging. Register a Volunteer with an ID document, then log in as an admin to review the application.

### Use MySQL or SQLite instead (optional)

Supabase is the recommended setup for the private document-storage feature. The app also supports its existing MySQL database or a local SQLite fallback:

- **MySQL:** Create `community_help_db` with MySQL 8+, set `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, and `DB_NAME` in `.env`, and leave `DATABASE_URL` blank. On an existing installation, back up your database and run `python migrate_community_features.py` to add the new app tables.
- **SQLite:** Set `USE_SQLITE_FALLBACK=1` and leave `DATABASE_URL` blank. Then run `python seed.py --admin-only` to initialize the database. SQLite is useful for local work, but volunteer document uploads still require a configured Supabase Storage project.

For MySQL/SQLite document uploads, configure the same three `SUPABASE_*` Storage values above. If they are missing, volunteer registration will return a clear storage configuration error rather than saving sensitive documents locally or publicly.

---

## 6. Step-by-Step Manual Testing &  Demonstration Guide

Follow this sequence to demonstrate all 8 pages and all workflows during your :

### Test 1: Public Registration & Login Throttling (Workflows A & H)
1. Go to `http://127.0.0.1:5000/auth/register`.
2. Notice the role selector: Only **Help Seeker**, **Volunteer**, and **Donor** are available. **Administrator is never selectable publicly.**
3. Register a new user (e.g. `testseeker@example.com`).
4. Attempt to register again with the same email &rarr; verified duplicate email error is shown.
5. Log in with the registered user &rarr; automatically redirects to the Help Seeker dashboard.

### Test 2: Help Seeker Workflow (Workflow B)
1. Log in as `seeker@example.com` / `Seeker@123`.
2. Notice the dashboard cards: Total Requests, Awaiting Volunteer, In Progress, Completed.
3. Click **Post New Help Request**.
4. Select category (e.g. `Medical Assistance`), enter title, urgency (`Critical`), locality (`Indiranagar`), and submit.
5. Notice the new request appears with a red `Critical` badge and `Pending` status.

### Test 3: Rule-Based Matching & Duplicate Acceptance Prevention (Workflows C & D)
1. In a private/incognito browser window (or after logging out), log in as `volunteer@example.com` / `Volunteer@123`.
2. Notice the **Volunteer Coordination Hub**:
   - The critical request posted in Test 2 appears at the very top of the list because our **Rule-Based Matching Algorithm** prioritizes `Critical` urgency (+100 pts) and locality proximity (+40 pts).
3. Click **Accept Task**. The task status updates to `Accepted` and moves into **My Accepted Tasks**.
4. **Duplicate acceptance check:** If a second volunteer tries to accept this request simultaneously, the transaction rolls back and displays: *"Sorry! This request was just accepted by another volunteer."*

### Test 4: Task Lifecycle Progression & Audit Trail (Workflow F)
1. In the volunteer dashboard, on the accepted task, click **Start Task** &rarr; status updates to `In Progress`.
2. Click **Mark Completed** &rarr; status transitions to `Completed`.
3. Click **Details** on the task to open the **Request Detail Page**.
4. Scroll to the **Audit Log & Status History Timeline**:
   - Observe every step recorded: `Created -> Pending`, `Pending -> Accepted`, `Accepted -> In Progress`, `In Progress -> Completed`, along with exact timestamps and acting user names!

### Test 5: Resource Donations & Auto-Expiry Safeguards (Workflow E)
1. Log in as `donor@example.com` / `Donor@123`.
2. Click **List New Resource**.
3. Select `Surplus Food Sharing`. Notice the interactive prompt indicating that the expiry date is mandatory for perishable food.
4. Set description, quantity (e.g. `25 boxes`), and pickup instructions.
5. Submit the listing &rarr; view it in the donor dashboard.
6. If an item passes its expiry date, the application automatically flags it as expired and transitions status to `Withdrawn`.

### Test 6: Administrator Control Center & Emergency Mode (Workflow G)
1. Log in as `admin@communityhelp.org` / `Admin@12345`.
2. Explore the **Administrator Control Center**:
   - KPI metrics: Total Users, Total Requests, Open/Pending, Completed, Resources.
   - User Management table: Click **Suspend** or **Verify** to moderate user accounts.
3. Click **Declare Emergency Event**:
   - Emergency Type: `Flash Flood Waterlogging`
   - Locality: `Indiranagar, Sector 4`
   - Severity: `Severe`
   - Submit.
4. Observe:
   - A pulsing red **Emergency Alert Banner** appears across the entire site.
   - All volunteers in `Indiranagar` instantly receive an in-app emergency notification in their notification center.
   - Click **Deactivate Emergency Mode** to conclude the crisis event.

---

## 7. Volunteer Verification and Direct Messaging

### Volunteer application and approval

Public volunteer registration requires an ID document type and an ID document upload. PDF, JPG/JPEG, and PNG files are accepted, with a 5 MB per-file limit; the server checks the extension, size, and file signature. A certificate and experience are optional. Documents are uploaded from Flask to the private Supabase Storage bucket and only paths/metadata are stored in the application database. A new application starts as `pending`; volunteer-only routes (including task acceptance and resource requests) require an `approved` verification and a non-suspended account. Applicants can see their status and, after rejection or an administrator's information request, resubmit documents. Approval, rejection, requests for information, and suspension are audited and notify the volunteer.

Administrators use **Volunteer Verification** in the Admin Dashboard to inspect application details and history, create a 60-second signed document preview, and approve, reject (reason required), request additional information (message required), or suspend an approved volunteer (reason required). Suspended volunteers cannot use volunteer routes. Existing volunteers created before this migration are added as pending and must be reviewed; an administrator can request information to enable their document resubmission.

Demo-only accounts created by `python seed.py --demo` include a pre-approved volunteer so existing smoke tests can exercise task workflows. This demo account has no ID document on file and is not an example of production onboarding; real public volunteer registrations always require an ID upload.

### Supabase setup and migrations

The app supports Supabase PostgreSQL through SQLAlchemy as well as the existing MySQL/SQLite configurations. In `.env`, set `DATABASE_URL` to the PostgreSQL connection URI from Supabase (include `?sslmode=require` for a direct connection), and install dependencies with `pip install -r requirements.txt`. Supabase pooler URIs should use the host and port provided by the project. Set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_STORAGE_BUCKET=volunteer-verification-documents`. Keep the service-role key server-side only; never commit it, expose it to browsers, or put it in user-editable metadata. Registration and resubmission fail explicitly if private storage is not configured.

For Supabase PostgreSQL, run the complete, repeatable database-and-storage migration in [`supabase_migration.sql`](./supabase_migration.sql) using the Supabase SQL Editor or `psql`. It creates only the new feature tables and indexes, preserves existing records, creates the **private** document bucket, and installs storage object policies. It also initializes pre-existing volunteers as pending. Do not mark old volunteers approved without verifying them.

For the existing Flask SQLAlchemy database (MySQL, PostgreSQL, or SQLite), configure `DATABASE_URL` as appropriate and run:

```powershell
python migrate_community_features.py
```

The script creates only the new feature tables and preserves existing application tables/data. Supabase's storage bucket and policies are provisioned by `supabase_migration.sql`; the migration SQL is also the exact schema/policy reference for those features.

### Help Seeker completion confirmation

Volunteer completion now moves a request to `awaiting_confirmation`. The assigned Help Seeker can confirm it (final status `Completed`, with an optional 1–5 star rating and feedback) or report an issue (status `disputed`). Administrators can review disputed requests and either verify completion or reopen the request for volunteers. Notifications and status-history audit entries are created for these transitions.

Before deploying this feature against an existing database, run the additive migration once against the same `DATABASE_URL` used by the app:

```powershell
python migrate_help_seeker_confirmation.py
```

The script adds only missing nullable columns to `help_requests`; it does not delete or rewrite existing requests. Run it from a deployment shell with the production database environment variables configured, or run it locally with a secure production `DATABASE_URL`. Do not add credentials to the command line or commit them. For a new database, the fields are included in the SQLAlchemy model and are created by the application's normal schema initialization.

On Render, configure the production environment variables, run `python migrate_help_seeker_confirmation.py` from the service's Shell before deploying the new application version, then deploy/restart the service. Confirm the migration output and inspect the Volunteer, Help Seeker, and Admin dashboards. The script is idempotent and can safely be run again.

The bucket must remain private. The SQL migration restricts direct authenticated object operations to a volunteer's own `volunteer/<community_user_id>/...` folder and allows admins to read. For direct Supabase Auth access, populate trusted `app_metadata` claims (`role` and `community_user_id`) from a trusted server; never accept those claims from `user_metadata`. The current Flask app uses its authenticated session and the service-role Storage API server-side, with route-level volunteer/admin checks and 60-second signed preview links. The service key bypasses Storage RLS, so do not add an unauthenticated upload endpoint or expose the key.

### Help Seeker–Donor and Volunteer–Donor conversations

Help Seekers and approved, active Volunteers can browse available donor resources and choose **Contact Donor**. Volunteers can also start a conversation from their resource dashboard without submitting an item request. Each thread is private to the donor and its one seeker/volunteer participant, is linked to the resource listing, and does not reserve stock or expose private phone numbers, email addresses, or pickup instructions. Donors can message multiple volunteers through their separate resource-request conversations. Both participants can review history, see unread counts, exchange text messages, receive notifications, and report suspicious conversations. The chat initially loads the latest 50 messages, can fetch older history on demand, sends without reloading the page, and polls for new messages every five seconds while open. Donors can close and reopen conversations; closed conversations reject new messages unless reopened. Only administrators can review reported conversation history in **Review Conversation Reports**.

### Feature verification

Run the automated feature and regression tests:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

For a fresh development environment, install test dependencies with `pip install -r requirements-dev.txt`.

The tests cover the task-confirmation and dispute workflow as well as mandatory document uploads, pending/suspended route denial, admin approval and audit history, secure preview authorization, private message exchange/read receipts, and unrelated-user/volunteer conversation denial. Supabase Storage itself requires a configured project for an end-to-end live upload/preview test; unit tests mock that external service.

### Preparing the repository for deployment

The root `.gitignore` excludes local secrets (`.env` and `.flaskenv`), virtual environments, SQLite/instance data, caches, logs, and build artifacts. Keep application source, templates, static assets, migrations, and tests in Git; they are not deployment clutter. Existing local files are not deleted by these ignore rules.

Before deploying, review `git status --short` and ensure `.env`, database files, and credentials are not staged. Configure `SECRET_KEY`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_STORAGE_BUCKET` as environment variables in the hosting provider. Apply `supabase_migration.sql` to the intended Supabase project. Do not run `seed.py --demo` or deploy with demo credentials. Use the production configuration (`FLASK_ENV=production`) and your host's supported WSGI server and start command; the exact command depends on the hosting provider.

This repository includes a `Procfile` and `wsgi.py` for Procfile-compatible platforms. Install production dependencies from `requirements.txt`; the host starts the app with Gunicorn. The WSGI entry point explicitly loads the production configuration and requires `SECRET_KEY`. Set the database and Supabase Storage variables in the host's secret/environment settings, and use the provided platform's PostgreSQL connection URI. Do not put production secrets in the repository or run demo seed commands against production.

## 8. Running Automated Tests

A comprehensive automated test suite is provided in the `tests/` directory covering authentication, duplicate acceptance prevention, lifecycle transitions, resource expiry, and emergency dispatch.

To run the automated tests:
```powershell
# Ensure virtual environment is active
pytest -v
```

All test cases run against an isolated in-memory test database without modifying your development or Supabase records.

---

## 9. Common Troubleshooting (Windows & MySQL)

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | PowerShell ExecutionPolicy default restriction | Run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` |
| `OperationalError: (2003, "Can't connect to MySQL server")` | MySQL service is not running | Start MySQL service via Windows Services (`services.msc`) or XAMPP Control Panel. |
| `OperationalError: (1045, "Access denied for user 'root'")` | Incorrect password in `.env` | Update `DB_PASSWORD` in `.env` with your actual MySQL root password. |
| `Address already in use: 5000` | Another process is using port 5000 | In `app.py`, change `app.run(..., port=5001)` or terminate the previous Python process. |
| Running without MySQL available | Demonstration machine lacks MySQL | In `.env`, set `USE_SQLITE_FALLBACK=1` to run instantly using SQLite! |

---

## 10.  Q&A Guide 

**Q1: Why did you choose Python Flask instead of Django or Node.js?**  
*Answer:* Flask provides a clean, unbloated microframework architecture that allows full transparency over every route, middleware, session check, and database transaction. It makes demonstrating modular Blueprints (`auth`, `help_requests`, `volunteers`, `donations`, `admin`) straightforward without hidden framework magic.

**Q2: How do you prevent two volunteers from accepting the same request simultaneously (Race Condition)?**  
*Answer:* We implement optimistic/pessimistic row-level locking using SQLAlchemy's `with_for_update()` inside an isolated database transaction (`volunteers/routes.py`). The query checks `status='Pending' and assigned_volunteer_id=None` while locking the row. If another volunteer commits first, the second query returns `None` and cleanly rolls back.

**Q3: How does your volunteer matching work without using AI or expensive Google Maps APIs?**  
*Answer:* We implemented a deterministic, explainable **Rule-Based Matching Algorithm** (`helpers.py:calculate_matching_score`). It scores open requests using:
1. Urgency Level (Critical: +100 pts, Urgent: +50 pts, Normal: +10 pts)
2. Locality proximity (Exact match: +40 pts, Sub-locality: +20 pts)
3. Emergency Zone Boost (+60 pts if in an active crisis locality)
4. Request Age (+1 pt per 2 hours to avoid request starvation).

**Q4: How do you enforce security and prevent unauthorized access to private contact details?**  
*Answer:* 
1. Passwords are never stored in plaintext; we use salted hashing via `werkzeug.security`.
2. All POST forms are protected by CSRF tokens via `Flask-WTF`.
3. Server-side custom decorators (`@login_required`, `@role_required`, `@admin_required`) protect every privileged route.
4. Contact information is conditionally masked: phone numbers and emails are hidden until a volunteer formally accepts a task, according to the seeker's preference.
