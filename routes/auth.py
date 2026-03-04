import uuid
import json
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db

auth_bp = Blueprint('auth', __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if session.get('must_change_password'):
            return redirect(url_for('auth.force_change_password'))
        return f(*args, **kwargs)
    return decorated


def full_access_required(f):
    """Requires login AND that the account is not a restricted new_user."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if session.get('must_change_password'):
            return redirect(url_for('auth.force_change_password'))
        role = session.get('role')
        if role is None:
            db = get_db()
            user = db.execute("SELECT role FROM users WHERE id = ?", (session['user_id'],)).fetchone()
            role = user['role'] if user else 'user'
            session['role'] = role
        if role == 'new_user':
            flash('Your account has limited access. Contact an administrator to upgrade your permissions.')
            return redirect(url_for('chat.index'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated


def log_event(event_type, user_id=None, details=None):
    db = get_db()
    db.execute(
        "INSERT INTO audit_log (event_type, user_id, details, ip_address) VALUES (?, ?, ?, ?)",
        (event_type, user_id, json.dumps(details) if details else None, request.remote_addr)
    )
    db.commit()


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        if session.get('must_change_password'):
            return redirect(url_for('auth.force_change_password'))
        return redirect(url_for('chat.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            if not user['is_active']:
                flash('Your account has been disabled. Contact an administrator.')
                return render_template('auth/login.html')

            session['user_id'] = user['id']
            session['username'] = user['username']
            session['display_name'] = user['display_name'] or user['username']
            session['avatar_filename'] = user['avatar_filename']
            session['role'] = user['role']

            db.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user['id'],))
            db.commit()

            log_event('login', user['id'], {'username': username})

            if user['must_change_password']:
                session['must_change_password'] = True
                return redirect(url_for('auth.force_change_password'))

            return redirect(url_for('chat.index'))

        flash('Invalid username or password.')
        log_event('login_failed', details={'username': username})

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('chat.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        display_name = request.form.get('display_name', '').strip()

        errors = []
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters.')
        if not email or '@' not in email:
            errors.append('Please enter a valid email address.')
        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm:
            errors.append('Passwords do not match.')

        if not errors:
            db = get_db()
            existing = db.execute(
                "SELECT id FROM users WHERE username = ? OR email = ?",
                (username, email)
            ).fetchone()

            if existing:
                errors.append('Username or email already taken.')

        if errors:
            for error in errors:
                flash(error)
            return render_template('auth/register.html')

        api_token = str(uuid.uuid4())
        db = get_db()
        db.execute(
            "INSERT INTO users (username, email, password_hash, display_name, api_token, role) VALUES (?, ?, ?, ?, ?, ?)",
            (username, email, generate_password_hash(password), display_name or username, api_token, 'new_user')
        )
        db.commit()

        # Auto-post a welcome message in #general on behalf of the new user
        new_user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        general = db.execute("SELECT id FROM channels WHERE name = 'general'").fetchone()
        if new_user and general:
            db.execute(
                "INSERT INTO messages (channel_id, user_id, content) VALUES (?, ?, ?)",
                (general['id'], new_user['id'],
                 f"Hey everyone! Just joined CorpChat. Looking forward to working with you all! 👋")
            )
            db.commit()

        log_event('register', details={'username': username})
        flash('Account created successfully. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/logout')
def logout():
    user_id = session.get('user_id')
    if user_id:
        log_event('logout', user_id)
    session.clear()
    return redirect(url_for('auth.login'))


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password_request():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if user:
            # Don't create duplicate pending requests
            existing = db.execute(
                "SELECT id FROM password_resets WHERE user_id = ? AND status = 'pending'",
                (user['id'],)
            ).fetchone()

            if not existing:
                db.execute(
                    "INSERT INTO password_resets (user_id, token, status) VALUES (?, ?, 'pending')",
                    (user['id'], str(uuid.uuid4()).replace('-', ''))
                )
                db.commit()
                log_event('password_reset_request', user['id'])

        # Always show the same message regardless of whether user exists
        flash('If that account exists, your request has been submitted. An administrator will review it and send you a reset link.', 'success')
        return render_template('auth/reset_password.html', step='requested')

    return render_template('auth/reset_password.html', step='request')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password_confirm(token):
    db = get_db()
    reset = db.execute(
        """SELECT pr.*, u.username FROM password_resets pr
           JOIN users u ON pr.user_id = u.id
           WHERE pr.token = ? AND pr.used = 0 AND pr.status = 'approved'""",
        (token,)
    ).fetchone()

    if not reset:
        flash('Invalid or expired password reset token.')
        return redirect(url_for('auth.reset_password_request'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if len(password) < 6:
            flash('Password must be at least 6 characters.')
            return render_template('auth/reset_confirm.html', token=token, username=reset['username'])
        if password != confirm:
            flash('Passwords do not match.')
            return render_template('auth/reset_confirm.html', token=token, username=reset['username'])

        db.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
            (generate_password_hash(password), reset['user_id'])
        )
        db.execute(
            "UPDATE password_resets SET used = 1, status = 'used' WHERE token = ?",
            (token,)
        )
        db.commit()

        log_event('password_reset_confirmed', reset['user_id'])
        flash('Password reset successfully. You can now log in with your new password.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_confirm.html', token=token, username=reset['username'])


@auth_bp.route('/token-login')
def token_login():
    """Developer convenience endpoint: exchange an API token for a web session.
    NOTE: This endpoint is intentionally left in for debugging purposes.
    """
    token = request.args.get('token', '').strip()
    if not token:
        flash('Token required.')
        return redirect(url_for('auth.login'))

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE api_token = ? AND is_active = 1", (token,)).fetchone()

    if not user:
        flash('Invalid or expired token.')
        return redirect(url_for('auth.login'))

    session['user_id'] = user['id']
    session['username'] = user['username']
    session['display_name'] = user['display_name'] or user['username']
    session['avatar_filename'] = user['avatar_filename']
    session['role'] = user['role']

    db.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user['id'],))
    db.commit()

    log_event('token_login', user['id'], {'username': user['username']})
    return redirect(url_for('chat.index'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
def force_change_password():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    if not session.get('must_change_password'):
        return redirect(url_for('chat.index'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if len(password) < 6:
            flash('Password must be at least 6 characters.')
            return render_template('auth/change_password.html')
        if password != confirm:
            flash('Passwords do not match.')
            return render_template('auth/change_password.html')

        db = get_db()
        db.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
            (generate_password_hash(password), session['user_id'])
        )
        db.commit()

        session.pop('must_change_password', None)
        log_event('password_changed', session['user_id'])
        flash('Password changed successfully.', 'success')
        return redirect(url_for('chat.index'))

    return render_template('auth/change_password.html')
