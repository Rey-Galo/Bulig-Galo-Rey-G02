# Bulig

Anonymous student reporting and guidance case management for Philippine basic education schools.
Bulig is Cebuano for "help".

Built with Django 6.1 and PostgreSQL on Supabase (CSIT327 Information Management 2).

## Features

### Standard features (Project Development 1)

- **Registration.** Public sign-up always creates a school `STAFF` account. Passwords are hashed with Argon2.
- **Login and logout.** Email-based login. Logout is POST-only.
- **Role-based dashboards.** Staff, division admin and platform admin each get their own dashboard.
- **Profile.** View and edit your own name and email.

### Core feature (Project Development 2): anonymous intake and case workflow

A student sends a concern to a trusted adult without an account. That adult, or the school head,
then carries the case from review to closure.

1. **Anonymous intake** (`/report/`, no login). The student:
   - picks a school;
   - picks a trusted adult who opted in to receive reports;
   - picks a language (Bisaya, Tagalog or English) and an optional category;
   - writes 20–5000 characters.

   The report and its case are saved together. If the same form is submitted twice, only one report is
   stored. No name, IP address or student account is ever recorded.
2. **Case queue** (`/cases/`, staff only). Staff see a case if they are its current owner, the adult the
   student chose, or the head of that school. The queue can be filtered by status and severity.
3. **Case workflow:**
   - **Review.** One human severity decision (high, moderate or low) with a required reason. It starts the
     acknowledgement deadline, which is taken from the school's settings.
   - **Acknowledge.** The owner or the school head accepts responsibility for the case.
   - **In progress, then referred, then closed.** Referring needs a destination, and closing needs a
     resolution. A closed case never reopens.
   - **Reassign.** School heads only, and only to staff in the same school.
4. **School memberships** (`/schools/memberships/`, staff only):
   - Join a school as a teacher or guidance counselor.
   - Turn "Receive student reports" on or off.
   - Leave a school. You cannot leave while you still own an open case. If you have case history at the
     school, your membership is switched off instead of deleted.
5. **Dashboards:**
   - Staff see counts of their cases waiting for review, waiting for acknowledgement and being handled.
   - Division admins see per-school counts only, never report text or case numbers.
   - Platform admins see school totals and manage schools and school heads in the Django admin.

Every rule is enforced on the server in `cases/services.py`, and many are also enforced by database
constraints.

## Setup

Requirements: Python 3.12+ and a PostgreSQL database (the project uses the Supabase session pooler).

```powershell
git clone https://github.com/Rey-Galo/Bulig-Galo-Rey-G02.git
cd Bulig-Galo-Rey-G02
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file in the project root. It is gitignored, so never commit it.

```
SECRET_KEY=change-me
DEBUG=True
DB_NAME=postgres
DB_USER=postgres.<project-ref>
DB_PASSWORD=<your-db-password>
DB_HOST=<region>.pooler.supabase.com
DB_PORT=5432
```

Then run:

```powershell
python manage.py migrate
python manage.py seed_demo --password "<choose-a-demo-password>"   # demo school and test accounts
python manage.py runserver
```

Open http://127.0.0.1:8000/.

- Students go to http://127.0.0.1:8000/report/.
- Staff log in at http://127.0.0.1:8000/login/.

### Demo accounts created by `seed_demo`

| Email | Role |
|---|---|
| `head@bulig.test` | Staff, school head of Demo National High School |
| `teacher@bulig.test` | Staff, teacher (receives reports) |
| `guidance@bulig.test` | Staff, guidance counselor (receives reports) |
| `division@bulig.test` | Division admin (Demo Cebu Division) |
| `platform@bulig.test` | Platform admin (also has Django admin access) |

All of them use the password you passed to `--password`.

## Tests

The Supabase pooler keeps sessions open, so always pass `--keepdb`:

```powershell
python manage.py test accounts schools cases --keepdb
```

## Project layout

| Path | What it holds |
|---|---|
| `accounts/` | Staff accounts, divisions, auth, dashboards and profile |
| `schools/` | Schools, staff memberships and the `seed_demo` command |
| `cases/` | Reports, cases, reviews, acknowledgements and the workflow rules (`services.py`) |
| `templates/` | All page templates |
| `static/` | `bulig.css` design tokens and the small `bulig.js` |

## Not built yet

These come later: AI triage drafts, the anonymous follow-up code and messages, automatic escalation,
in-app notifications, the audit log, and encryption of report text at rest.
