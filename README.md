# Dr. Girija's NutriLife

A full-stack digital companion and coaching tracker for a 90-day holistic wellness program. Built directly from the Excel workbook requirements (`90 Day Tracker.xlsx`), digitally preserving all seven worksheets, their exact formulas, auto-calculations, and tracking rules.

---

## 🌟 Key Features

### 1. Public Website & Self-Registration
- **Welcoming Homepage:** Program overview, philosophy ("Patterns over perfection", "Waist matters more than weight"), core tracking pillars, and coach directory.
- **Participant Self-Registration:** Allows any individual to join without prior admin creation. Captures:
  - Full Name, Email, Mobile, Password.
  - Program Start Date (Day 1).
  - Assigned / Preferred Coach selection.
  - Personal 90-Day Wellness Goal & Reason for Joining (your "Why").
  - Coaching session day and time.
  - Two primary root causes or challenges.
  - Optional profile photo upload with live preview.
- **Automatic Setup:** Automatically initializes participant profile and baseline records matching the 7 worksheets (measurements, 15 clinical blood reports, 12 weeks of coach habits, weekly scoring rows).
- **Secure Authentication:** Passwords hashed with PBKDF2-SHA256 (`werkzeug.security`). Role-based access control (`participant` vs `admin`). Participants cannot escalate their privileges to admin.

### 2. Participant Dashboard
- **Dynamic Program Counter:** Computes real program day (Day 1–90), days completed, and days remaining from the participant's saved start date and the current date (no hardcoded days).
- **Daily Checklist & Score:** Displays today's task status across Food, Hydration, Movement, and Habits with a live completion percentage.
- **Interactive Visualizations (Chart.js):**
  - **Body Measurements Trajectory:** Dual-axis chart tracking Weight (kg) and Waist (cm) over time.
  - **Weekly Vitality Trend:** Multi-variable chart tracking subjective scores (Energy, Sleep, Digestion, Mood, Cravings).
- **Quick Logging:** One-click quick-adds for water and direct links to all tracking modules.
- **Empty States:** Clean, informative empty states when no data has been logged yet—never populates charts with fake/invented numbers.

### 3. Top-Right Profile Menu
- Accessible avatar / dropdown at the top right:
  - **View Profile:** Overview of baseline goals, coach, session schedule.
  - **Edit Profile:** Update full name, mobile number, coaching schedule, 90-day goal, why, and root causes.
  - **Profile Photo Management:** Upload, preview, replace, or remove profile photo with persistent storage.
  - **Password Change:** Secure password verification and update.
  - **Sign Out.**

### 4. Excel Workbook Trackers (All 7 Worksheets Implemented)

| Worksheet | Digital Implementation | Excel Formulas Preserved |
|---|---|---|
| **1. Start Here (Cover)** | Participant registration baseline, 90-day goal, Why, Session schedule, 2 root causes. | Baseline profile linkage. |
| **2. Food Tracker** | 7 Daily meal slots (*Early morning, Breakfast, Mid-morning, Lunch, Evening snack, Dinner, After dinner*), optional meal photos with preview/removal, water glasses counter, and craving trigger notes. | Pattern tracking, 90-day history log. |
| **3. Water Tracker** | Custom daily hydration goal (default 3000ml), quick-add buttons (+250ml glass, +500ml bottle, +750ml flask, +1L), timestamped intake log with delete/edit, live progress indicator. | Real-time intake sum, remaining ml. |
| **4. Movement Tracker** | Steps, Morning activity & minutes, Evening activity & minutes, Other movement & minutes, Total active minutes auto-sum, How I felt after, 90-day history table. | `=SUM(Morning, Evening, Other)`<br>`=COUNT(Steps)` (Days filled)<br>`=ROUND(AVERAGE(Steps), 0)`<br>`=ROUND(AVERAGE(Active Mins), 0)` |
| **5. Habit Tracker** | 12 Weeks of 3 coach-assigned action steps. Monday–Sunday check-in checkboxes. Days done count, % done per habit, and total week score. | `=COUNTIF(Mon:Sun, "Y")`<br>`=DaysDone / 7 * 100%`<br>`=SUM(DaysDone) / 21 * 100%`<br>*"Anything above 70% in a week is a good week."* |
| **6. Measurements** | Start (Day 1) + Weeks 1 to 12. Tracks Weight (kg), Waist (cm), Hips (cm), Chest (cm), Upper arm (cm), Thigh (cm), and Notes. | **Change so far:** `Latest minus Start`<br>`=IFERROR(IF(COUNT(col)<2,"",LOOKUP(9.99E+307,col)-D6),"")` |
| **7. Reports (Blood Tests)** | 15 preloaded clinical tests (*Vitamin D, B12, Fasting blood sugar, HbA1c, Haemoglobin, TSH, Total cholesterol, Triglycerides, HDL, LDL, SGPT/ALT, Creatinine, Uric acid, Ferritin, Fasting insulin*) + custom test rows + lab report file upload (PDF/Images). | Before vs Day 90 test dates & results with ideal reference ranges. |
| **8. Weekly Score** | Sunday self-reflection (1 to 10 scale) on Energy, Sleep, Digestion, Mood, and Cravings under control. | `=ROUND(AVERAGE(Energy, Sleep, Digestion, Mood, Cravings), 1)`<br>`Change, Week 1 to latest` |

### 5. Help & Coach Support Messaging System
- **Participant Help Desk:** Participants can create a support conversation, ask questions about nutrition or workouts, send follow-up replies, and track status (`Open`, `Replied`, `Resolved`).
- **Admin Support Inbox:** Coaches/administrators can view all open tickets, inspect participant context, reply directly, and toggle ticket statuses.
- **Strict Privacy:** Participants can only access their own support threads.

### 6. Protected Administrator Portal (`/admin`)
- Server-side role check (`@admin_required`): non-admin users cannot access any administrative routes.
- **Executive Dashboard:** Total participants, active participants, incomplete records today, pending support queries, and cohort distribution by program day.
- **Roster & Participant Inspector:** Search by name/email/phone, filter by coach, view full 360° participant history (meals, photos, measurements, lab tests, weekly scores).
- **Coach Assignment:** Re-assign coaches to participants dynamically.
- **Habit Configuration:** Configure and customize the 3 weekly action steps for any participant for any of the 12 weeks.
- **CSV Data Export:** Export the entire participant directory or individual participant movement history to CSV.

---

## 💻 Tech Stack & Architecture

- **Backend:** Python 3.15, Flask 3.1, Flask-SQLAlchemy 3.1, Werkzeug 3.1
- **Database:** SQLite (local persistent development: `wellness.db`) / PostgreSQL (production ready via `DATABASE_URL`)
- **Frontend:** Jinja2 templates, Tailwind CSS (CDN), Chart.js (CDN), Responsive HTML5 / Mobile-Friendly Design
- **Image & File Processing:** Pillow (image optimization, thumbnailing, resizing), Secure multi-part upload handling with ownership checks.

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+ installed on your machine.
- Git (optional).

### 2. Set Project Directory as Workspace
Open your terminal or IDE in the project directory:
```bash
cd "C:\Users\VIJAY\.gemini\antigravity\scratch\wellness-tracker"
```

### 3. Install Dependencies
```bash
python -m pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
copy .env.example .env
```
Local development uses SQLite by default. Production requires a hosted PostgreSQL URL in `DATABASE_URL` and a private `SECRET_KEY`.

### 5. Initialize the Database & Primary Coach
Run the explicit initialization script against the database selected by `DATABASE_URL`:
```bash
python init_db.py
```
This repeatable command will:
- Create missing database tables without dropping existing tables or data.
- Ensure Dr. Girija Pashikanti — Nutritionist (Pharmacology) is the only active coach.
- Reassign existing coach-linked participant profiles to Dr. Girija and deactivate (not delete) old coach records.

To create or update the NutriLife administrator, run this explicit command. It prompts for the account password twice without echoing it; the password is stored using the existing Werkzeug hash:
```bash
python init_db.py --configure-nutrilife-admin
```
The account username is `drgirijasnutrilife.com`. Running this command again updates the existing admin password rather than creating duplicate accounts. It refuses to elevate an existing participant account.

The existing generic admin creation option remains available for other administrator accounts:
```bash
python init_db.py --create-admin --admin-email you@example.com
```

### 6. Start the Web Application
```bash
python run.py
```
Open your browser and navigate to:
- **Public Homepage / Participant Portal:** [http://127.0.0.1:5000/](http://127.0.0.1:5000/)
- **Admin Control Center:** [http://127.0.0.1:5000/admin](http://127.0.0.1:5000/admin)

---

## 🧪 Running Automated Tests

A comprehensive test suite covering the original 16 workflows plus coach-migration and admin-authentication regressions is included in `tests/test_wellness_app.py`.

To run the test suite:
```bash
python -m unittest tests/test_wellness_app.py
```

### Verified Test Cases:
1. `test_01_participant_registration`: Public self-registration, user creation, profile creation, automatic record initialization.
2. `test_02_participant_login`: Returning participant login and dashboard redirection.
3. `test_03_profile_photo_upload`: Uploading, previewing, and updating profile photos.
4. `test_04_save_meal_without_photo`: Food tracker meal saving without image.
5. `test_05_save_meal_with_photo`: Food tracker meal saving with image upload and storage.
6. `test_06_meal_persistence_after_relogin`: Verifying meals and photos persist across logout and re-login.
7. `test_07_water_calculations`: Water intake logging, quick add, sum totals, and entry deletion.
8. `test_08_movement_totals_and_averages`: Morning + Evening + Other sum formula, steps, 90-day averages (excluding blank days).
9. `test_09_trackers_saving`: Habit check-ins (70% rule), Measurements (latest minus start difference formula), Weekly scores (1-10 average).
10. `test_10_and_11_admin_portal_review`: Admin dashboard, roster visibility, participant 360° inspector.
11. `test_12_support_ticket_and_reply`: Participant queries coach, coach replies from admin inbox, status transitions.
12. `test_13_record_privacy`: IDOR protection; participant cannot view another participant's private records or photos.
13. `test_14_admin_access_protection`: Participant attempting to access `/admin` is rejected with 403 / redirect.
14. `test_15_navigation_endpoints`: All main routes return 200 OK.
15. `test_16_program_day_calculation`: Calculates program day dynamically based on real calendar dates.

---

## 🛡️ Security & Privacy Architecture

- **Password Protection:** PBKDF2 with SHA-256 and unique salts for every user.
- **Server-Side Authorization:** Every participant endpoint strictly verifies record ownership against `g.current_user.id`.
- **Protected File Access:** Uploaded meal photos and blood reports are served through an authenticated route (`/uploads/<folder>/<filename>`) that checks ownership or admin rights before streaming the file.
- **Sanitized Uploads:** File extensions are strictly whitelisted (`.jpg`, `.jpeg`, `.png`, `.webp`, `.pdf`). Filenames are sanitized via `secure_filename` and prefixed with UUIDs to prevent directory traversal or collision attacks.
- **Role Isolation:** Roles are stored on the server model. Registration is hardcoded to assign `role='participant'`. Admin accounts can only be created via the CLI `init_db.py` script.

---

## Production Deployment

For Vercel, create a hosted PostgreSQL database with a provider of your choice. Copy its application connection URL from that provider's dashboard; do not use a locally invented URL. Keep these Vercel Environment Variables for the Production environment:

- `DATABASE_URL`: the provider's PostgreSQL connection URL. The app accepts `postgres://` or `postgresql://` and uses the Psycopg 3 driver.
- `SECRET_KEY`: a privately generated, high-entropy value. Do not commit it or use the development placeholder.
- `APP_ENV`: `production`.

No new public environment variable is required. On the first request to `/register`, the application now safely creates or reactivates the primary coach in the configured database if the record is missing. This makes the production registration page self-healing without relying on a local database or a Vercel build-time script. The operation is repeatable and does not delete or rewrite participant records.

For a planned database initialization, run `python init_db.py` from an operator environment whose `DATABASE_URL` is securely set to the hosted production database. It creates missing tables, ensures the primary coach, repoints existing coach-linked profiles, and deactivates old coaches without deleting their rows or participant data. Do not run it against the local SQLite database expecting it to update production.

To provision the administrator, run `python init_db.py --configure-nutrilife-admin` against that same hosted database and enter the requested password at the hidden prompt. Do not put the password in source code, command-line arguments, `.env.example`, or Vercel frontend variables. Administrator accounts are not created or reset at application startup. Deploy the application code, then visit `/register`; no coach-specific environment variable or schema change is required.

Vercel's function filesystem is temporary. The current upload code writes photos and reports under `UPLOAD_FOLDER`, so production uploads need external persistent object storage and corresponding storage integration in `app/utils.py` and the upload route. Setting `UPLOAD_FOLDER` to a Vercel path alone does not make uploaded files durable.

The local SQLite database is for development only. Vercel app imports do not create tables or run the initialization script; the registration request ensures the primary coach record in whichever configured database the live app uses.
#   H e a l t h - C a m p 
 
 