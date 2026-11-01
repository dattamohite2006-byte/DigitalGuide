# Digital Guide for Social and Welfare Schemes

A final-year web application that helps citizens discover government social
welfare schemes, check their eligibility, and lets an admin manage the
scheme catalog.

**Stack:** HTML5, CSS3, Bootstrap 5, JavaScript (frontend) · Python Flask (backend)
· MySQL via XAMPP (database) · VS Code (IDE)

---

## 1. Features

- Public scheme catalog with search & category filters
- Scheme detail pages (benefits, documents, how to apply, official link)
- Eligibility checker (age, income, gender, category, state → matching schemes)
- User registration & login (password hashing with Werkzeug)
- Logged-in users can save/bookmark schemes
- Contact-us form (stored in the database)
- Admin panel: dashboard stats, add/edit/delete schemes (with image upload),
  view registered users

## 2. Project Structure

```
digital_guide/
├── app.py                 # Flask app: all routes
├── config.py               # App + MySQL configuration
├── requirements.txt
├── .env.example             # Copy to .env and edit for your setup
├── database/
│   └── schema.sql           # Full schema + seed data (import into MySQL)
├── static/
│   ├── css/style.css
│   ├── js/script.js
│   └── images/
└── templates/
    ├── base.html, index.html, login.html, register.html,
    ├── schemes.html, scheme_details.html, eligibility.html, contact.html
    └── admin/
        ├── admin_base.html (shared sidebar layout)
        ├── dashboard.html, schemes.html, add_scheme.html,
        └── edit_scheme.html, users.html
```

## 3. Setup Instructions (Windows + XAMPP + VS Code)

### Step 1 — Start MySQL via XAMPP
1. Open the **XAMPP Control Panel** and click **Start** next to `MySQL`.
2. Open `http://localhost/phpmyadmin`.

### Step 2 — Create the database
1. In phpMyAdmin, go to **Import**.
2. Choose the file `database/schema.sql` from this project and click **Go**.
   This creates the `digital_guide` database, all tables, and seed data
   (including sample schemes and a demo admin account).

### Step 3 — Set up the Python environment
Open this project folder in VS Code, then in the integrated terminal:

```bash
# create & activate a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# install dependencies
pip install -r requirements.txt
```

### Step 4 — Configure environment variables
Copy `.env.example` to `.env` and edit if your MySQL credentials differ from
the XAMPP defaults (`root` user, empty password):

```bash
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux
```

### Step 5 — Run the app
```bash
python app.py
```
Visit **http://127.0.0.1:5000** in your browser.

### Demo Admin Login
```
Email:    admin@digitalguide.gov
Password: Admin@123
```
Log in with these credentials, then open the **Admin Panel** link in the
navbar to manage schemes and view users.

## 4. Notes for the Report / Viva

- Passwords are never stored in plain text — `werkzeug.security` hashes
  them with `scrypt` before saving to MySQL.
- All database access goes through parameterized queries (`%s` placeholders)
  to prevent SQL injection.
- `PyMySQL` is used as the DB driver (pure Python) so it installs without
  needing a C compiler — convenient for a typical student Windows setup.
- The eligibility checker is a simple rule-based match: it filters the
  `schemes` table on age range, income ceiling, gender, category and state
  columns based on the form the citizen fills in.
- Sessions (`flask.session`) are used for authentication; an `admin_required`
  decorator protects every `/admin/*` route.

## 5. Possible Extensions

- Multi-language support (Hindi/regional languages) for wider accessibility
- SMS/email notification when a new matching scheme is added
- Document upload for users to track their own applications
- REST API endpoints for a companion mobile app
