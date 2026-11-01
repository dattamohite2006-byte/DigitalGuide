"""
Digital Guide for Social and Welfare Schemes
Final Year Project - Flask + MySQL + Bootstrap

Run:
    python app.py
Requires a MySQL server (e.g. via XAMPP) with the 'digital_guide'
database imported from database/schema.sql
"""

import os
import functools
from datetime import date

import pymysql
import pymysql.cursors
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import Config

app = Flask(__name__)
app.config.from_object(Config)

os.makedirs(os.path.join(app.root_path, app.config['UPLOAD_FOLDER']), exist_ok=True)


# ------------------------------------------------------------------
# Database helpers
# ------------------------------------------------------------------
def get_db():
    """Open a new MySQL connection (PyMySQL) using dict cursors."""
    return pymysql.connect(
        host=app.config['MYSQL_HOST'],
        port=app.config['MYSQL_PORT'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        database=app.config['MYSQL_DB'],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def query_db(sql, args=None, one=False, commit=False):
    """Run a query and return results (or lastrowid when commit=True)."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            if commit:
                conn.commit()
                return cur.lastrowid
            rows = cur.fetchall()
            return (rows[0] if rows else None) if one else rows
    finally:
        conn.close()


def execute_db(sql, args=None):
    """Run an INSERT/UPDATE/DELETE and commit."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


# ------------------------------------------------------------------
# Auth helpers / decorators
# ------------------------------------------------------------------
def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login', next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login'))
        if not session.get('is_admin'):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    return {
        'current_user_name': session.get('full_name'),
        'is_logged_in': bool(session.get('user_id')),
        'is_admin': bool(session.get('is_admin')),
    }


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def calculate_age(dob):
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# ------------------------------------------------------------------
# Public routes
# ------------------------------------------------------------------
@app.route('/')
def index():
    featured = query_db(
        "SELECT s.*, c.name AS category_name FROM schemes s "
        "LEFT JOIN scheme_categories c ON s.category_id = c.id "
        "WHERE s.status = 'Active' ORDER BY s.created_at DESC LIMIT 6"
    )
    total_schemes = query_db("SELECT COUNT(*) AS total FROM schemes WHERE status='Active'", one=True)['total']
    categories = query_db("SELECT * FROM scheme_categories ORDER BY name")
    return render_template('index.html', schemes=featured, total_schemes=total_schemes, categories=categories)


@app.route('/schemes')
def schemes():
    search = request.args.get('q', '').strip()
    category_id = request.args.get('category', '')

    sql = ("SELECT s.*, c.name AS category_name FROM schemes s "
           "LEFT JOIN scheme_categories c ON s.category_id = c.id "
           "WHERE s.status = 'Active'")
    args = []

    if search:
        sql += " AND (s.title LIKE %s OR s.short_description LIKE %s OR s.department LIKE %s)"
        like = f"%{search}%"
        args += [like, like, like]

    if category_id:
        sql += " AND s.category_id = %s"
        args.append(category_id)

    sql += " ORDER BY s.created_at DESC"
    results = query_db(sql, args)
    categories = query_db("SELECT * FROM scheme_categories ORDER BY name")

    return render_template('schemes.html', schemes=results, categories=categories,
                            search=search, selected_category=category_id)


@app.route('/scheme/<int:scheme_id>')
def scheme_details(scheme_id):
    scheme = query_db(
        "SELECT s.*, c.name AS category_name FROM schemes s "
        "LEFT JOIN scheme_categories c ON s.category_id = c.id "
        "WHERE s.id = %s", (scheme_id,), one=True
    )
    if not scheme:
        abort(404)

    is_saved = False
    if session.get('user_id'):
        saved = query_db(
            "SELECT id FROM saved_schemes WHERE user_id=%s AND scheme_id=%s",
            (session['user_id'], scheme_id), one=True
        )
        is_saved = bool(saved)

    related = query_db(
        "SELECT * FROM schemes WHERE category_id=%s AND id != %s AND status='Active' LIMIT 3",
        (scheme['category_id'], scheme_id)
    )
    return render_template('scheme_details.html', scheme=scheme, is_saved=is_saved, related=related)


@app.route('/scheme/<int:scheme_id>/save', methods=['POST'])
@login_required
def toggle_save_scheme(scheme_id):
    existing = query_db(
        "SELECT id FROM saved_schemes WHERE user_id=%s AND scheme_id=%s",
        (session['user_id'], scheme_id), one=True
    )
    if existing:
        execute_db("DELETE FROM saved_schemes WHERE id=%s", (existing['id'],))
        flash('Removed from saved schemes.', 'info')
    else:
        execute_db(
            "INSERT INTO saved_schemes (user_id, scheme_id) VALUES (%s, %s)",
            (session['user_id'], scheme_id)
        )
        flash('Scheme saved to your profile.', 'success')
    return redirect(url_for('scheme_details', scheme_id=scheme_id))


@app.route('/eligibility', methods=['GET', 'POST'])
def eligibility():
    matched = None
    form_data = {}

    if request.method == 'POST':
        form_data = request.form.to_dict()
        age = request.form.get('age', type=int)
        income = request.form.get('income', type=float)
        gender = request.form.get('gender', 'All')
        category = request.form.get('category', 'All')
        state = request.form.get('state', 'All')

        sql = ("SELECT s.*, c.name AS category_name FROM schemes s "
               "LEFT JOIN scheme_categories c ON s.category_id = c.id "
               "WHERE s.status='Active' AND %s BETWEEN s.min_age AND s.max_age "
               "AND (s.max_income IS NULL OR %s <= s.max_income) "
               "AND (s.applicable_gender = 'All' OR s.applicable_gender = %s) "
               "AND (s.applicable_category = 'All' OR s.applicable_category = %s) "
               "AND (s.applicable_state = 'All' OR s.applicable_state = %s) "
               "ORDER BY s.title")
        matched = query_db(sql, (age, income if income is not None else 0, gender, category, state))

    categories = query_db("SELECT * FROM scheme_categories ORDER BY name")
    return render_template('eligibility.html', matched=matched, form_data=form_data, categories=categories)


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()

        if not name or not email or not message:
            flash('Please fill in all required fields.', 'danger')
        else:
            execute_db(
                "INSERT INTO contact_messages (name, email, subject, message) VALUES (%s,%s,%s,%s)",
                (name, email, subject, message)
            )
            flash('Thank you! Your message has been sent.', 'success')
            return redirect(url_for('contact'))

    return render_template('contact.html')


# ------------------------------------------------------------------
# Auth routes
# ------------------------------------------------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('index'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        phone = request.form.get('phone', '').strip()
        gender = request.form.get('gender') or None
        dob = request.form.get('dob') or None
        income = request.form.get('income') or None
        category = request.form.get('category') or 'General'
        state = request.form.get('state', '').strip()

        errors = []
        if not full_name or not email or not password:
            errors.append('Name, email and password are required.')
        if password != confirm_password:
            errors.append('Passwords do not match.')
        if len(password) < 6:
            errors.append('Password must be at least 6 characters.')

        existing = query_db("SELECT id FROM users WHERE email=%s", (email,), one=True)
        if existing:
            errors.append('An account with this email already exists.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('register.html', form_data=request.form)

        hashed = generate_password_hash(password)
        execute_db(
            "INSERT INTO users (full_name, email, password, phone, gender, dob, annual_income, category, state) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (full_name, email, hashed, phone, gender, dob, income, category, state)
        )
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', form_data={})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = query_db("SELECT * FROM users WHERE email=%s", (email,), one=True)
        if user and check_password_hash(user['password'], password):
            session.clear()
            session['user_id'] = user['id']
            session['full_name'] = user['full_name']
            session['is_admin'] = bool(user['is_admin'])
            flash(f"Welcome back, {user['full_name']}!", 'success')

            next_page = request.args.get('next')
            if user['is_admin']:
                return redirect(next_page or url_for('admin_dashboard'))
            return redirect(next_page or url_for('index'))

        flash('Invalid email or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# ------------------------------------------------------------------
# Admin routes
# ------------------------------------------------------------------
@app.route('/admin')
@admin_required
def admin_dashboard():
    stats = {
        'total_schemes': query_db("SELECT COUNT(*) c FROM schemes", one=True)['c'],
        'active_schemes': query_db("SELECT COUNT(*) c FROM schemes WHERE status='Active'", one=True)['c'],
        'total_users': query_db("SELECT COUNT(*) c FROM users WHERE is_admin=0", one=True)['c'],
        'total_messages': query_db("SELECT COUNT(*) c FROM contact_messages", one=True)['c'],
    }
    recent_schemes = query_db("SELECT * FROM schemes ORDER BY created_at DESC LIMIT 5")
    recent_users = query_db("SELECT id, full_name, email, created_at FROM users WHERE is_admin=0 ORDER BY created_at DESC LIMIT 5")
    recent_messages = query_db("SELECT * FROM contact_messages ORDER BY created_at DESC LIMIT 5")
    return render_template('admin/dashboard.html', stats=stats, recent_schemes=recent_schemes,
                            recent_users=recent_users, recent_messages=recent_messages)


@app.route('/admin/schemes')
@admin_required
def admin_schemes():
    all_schemes = query_db(
        "SELECT s.*, c.name AS category_name FROM schemes s "
        "LEFT JOIN scheme_categories c ON s.category_id = c.id "
        "ORDER BY s.created_at DESC"
    )
    return render_template('admin/schemes.html', schemes=all_schemes)


@app.route('/admin/schemes/add', methods=['GET', 'POST'])
@admin_required
def add_scheme():
    categories = query_db("SELECT * FROM scheme_categories ORDER BY name")

    if request.method == 'POST':
        f = request.form
        image_filename = 'default_scheme.jpg'

        file = request.files.get('image')
        if file and file.filename and allowed_file(file.filename):
            image_filename = secure_filename(file.filename)
            file.save(os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], image_filename))

        execute_db(
            """INSERT INTO schemes
               (title, category_id, department, short_description, description, benefits,
                documents_required, how_to_apply, official_link, image,
                min_age, max_age, max_income, applicable_gender, applicable_category,
                applicable_state, status, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (f.get('title'), f.get('category_id') or None, f.get('department'),
             f.get('short_description'), f.get('description'), f.get('benefits'),
             f.get('documents_required'), f.get('how_to_apply'), f.get('official_link'),
             image_filename, f.get('min_age', 0), f.get('max_age', 120),
             f.get('max_income') or None, f.get('applicable_gender', 'All'),
             f.get('applicable_category', 'All'), f.get('applicable_state', 'All'),
             f.get('status', 'Active'), session['user_id'])
        )
        flash('Scheme added successfully.', 'success')
        return redirect(url_for('admin_schemes'))

    return render_template('admin/add_scheme.html', categories=categories)


@app.route('/admin/schemes/edit/<int:scheme_id>', methods=['GET', 'POST'])
@admin_required
def edit_scheme(scheme_id):
    scheme = query_db("SELECT * FROM schemes WHERE id=%s", (scheme_id,), one=True)
    if not scheme:
        abort(404)
    categories = query_db("SELECT * FROM scheme_categories ORDER BY name")

    if request.method == 'POST':
        f = request.form
        image_filename = scheme['image']

        file = request.files.get('image')
        if file and file.filename and allowed_file(file.filename):
            image_filename = secure_filename(file.filename)
            file.save(os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], image_filename))

        execute_db(
            """UPDATE schemes SET title=%s, category_id=%s, department=%s, short_description=%s,
               description=%s, benefits=%s, documents_required=%s, how_to_apply=%s,
               official_link=%s, image=%s, min_age=%s, max_age=%s, max_income=%s,
               applicable_gender=%s, applicable_category=%s, applicable_state=%s, status=%s
               WHERE id=%s""",
            (f.get('title'), f.get('category_id') or None, f.get('department'),
             f.get('short_description'), f.get('description'), f.get('benefits'),
             f.get('documents_required'), f.get('how_to_apply'), f.get('official_link'),
             image_filename, f.get('min_age', 0), f.get('max_age', 120),
             f.get('max_income') or None, f.get('applicable_gender', 'All'),
             f.get('applicable_category', 'All'), f.get('applicable_state', 'All'),
             f.get('status', 'Active'), scheme_id)
        )
        flash('Scheme updated successfully.', 'success')
        return redirect(url_for('admin_schemes'))

    return render_template('admin/edit_scheme.html', scheme=scheme, categories=categories)


@app.route('/admin/schemes/delete/<int:scheme_id>', methods=['POST'])
@admin_required
def delete_scheme(scheme_id):
    execute_db("DELETE FROM schemes WHERE id=%s", (scheme_id,))
    flash('Scheme deleted.', 'info')
    return redirect(url_for('admin_schemes'))


@app.route('/admin/users')
@admin_required
def admin_users():
    all_users = query_db(
        "SELECT id, full_name, email, phone, gender, category, state, created_at "
        "FROM users WHERE is_admin=0 ORDER BY created_at DESC"
    )
    return render_template('admin/users.html', users=all_users)


@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    execute_db("DELETE FROM users WHERE id=%s AND is_admin=0", (user_id,))
    flash('User removed.', 'info')
    return redirect(url_for('admin_users'))


# ------------------------------------------------------------------
# Error handlers
# ------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403


if __name__ == '__main__':
    app.run(debug=True, port=5000)
