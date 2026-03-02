import os
import shutil
import json
import sys
import time
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, \
    current_app, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db
from routes.auth import admin_required, log_event

admin_bp = Blueprint('admin', __name__)


@admin_bp.before_request
def load_pending_reset_count():
    if 'admin_id' in session:
        db = get_db()
        g.pending_reset_count = db.execute(
            "SELECT COUNT(*) FROM password_resets WHERE status = 'pending'"
        ).fetchone()[0]


@admin_bp.route('/')
def index():
    if 'admin_id' not in session:
        return redirect(url_for('admin.login'))
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'admin_id' in session:
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        db = get_db()
        admin = db.execute(
            "SELECT * FROM admin_users WHERE username = ?", (username,)
        ).fetchone()

        if admin and check_password_hash(admin['password_hash'], password):
            session['admin_id'] = admin['id']
            session['admin_username'] = admin['username']
            log_event('admin_login', details={'admin_username': username})
            return redirect(url_for('admin.dashboard'))

        flash('Invalid admin credentials.')
        log_event('admin_login_failed', details={'admin_username': username})

    return render_template('admin/login.html')


@admin_bp.route('/logout')
def logout():
    log_event('admin_logout', details={'admin_username': session.get('admin_username')})
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    return redirect(url_for('admin.login'))


@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    db = get_db()
    stats = {
        'total_users': db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        'active_users': db.execute("SELECT COUNT(*) FROM users WHERE is_active = 1").fetchone()[0],
        'total_messages': db.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
        'total_files': db.execute("SELECT COUNT(*) FROM files").fetchone()[0],
        'total_channels': db.execute("SELECT COUNT(*) FROM channels").fetchone()[0],
    }

    pending_resets = db.execute(
        """SELECT pr.id, pr.created_at, u.username, u.id as user_id
           FROM password_resets pr
           JOIN users u ON pr.user_id = u.id
           WHERE pr.status = 'pending'
           ORDER BY pr.created_at ASC"""
    ).fetchall()

    recent_logs = db.execute(
        """SELECT al.*, u.username
           FROM audit_log al
           LEFT JOIN users u ON al.user_id = u.id
           ORDER BY al.created_at DESC
           LIMIT 20"""
    ).fetchall()

    return render_template('admin/dashboard.html',
                           stats=stats,
                           recent_logs=recent_logs,
                           pending_resets=pending_resets)


@admin_bp.route('/users')
@admin_required
def users():
    db = get_db()
    all_users = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    return render_template('admin/users.html', users=all_users)


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_user(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user:
        new_status = 0 if user['is_active'] else 1
        db.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, user_id))
        db.commit()
        action = 'enabled' if new_status else 'disabled'
        log_event('admin_action', details={
            'action': f'user_{action}',
            'target_user_id': user_id,
            'admin': session.get('admin_username')
        })
        flash(f'User {user["username"]} has been {action}.')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/set-role', methods=['POST'])
@admin_required
def set_user_role(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user:
        new_role = request.form.get('role', 'user')
        if new_role not in ('user', 'admin'):
            new_role = 'user'
        db.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
        db.commit()
        log_event('admin_action', details={
            'action': 'role_changed',
            'target_user_id': user_id,
            'new_role': new_role,
            'admin': session.get('admin_username')
        })
        flash(f'Role for {user["username"]} set to {new_role}.')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def reset_user_password(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user:
        temp_password = uuid.uuid4().hex[:12]
        db.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
            (generate_password_hash(temp_password), user_id)
        )
        db.commit()
        log_event('admin_action', details={
            'action': 'force_password_change',
            'target_user_id': user_id,
            'admin': session.get('admin_username')
        })
        flash(f'Temporary password for {user["username"]}: {temp_password} — they must change it on next login.')
    return redirect(url_for('admin.users'))


@admin_bp.route('/reset-requests/<int:request_id>/approve', methods=['POST'])
@admin_required
def approve_reset(request_id):
    db = get_db()
    reset_req = db.execute(
        """SELECT pr.*, u.username FROM password_resets pr
           JOIN users u ON pr.user_id = u.id
           WHERE pr.id = ? AND pr.status = 'pending'""",
        (request_id,)
    ).fetchone()

    if reset_req:
        temp_password = uuid.uuid4().hex[:12]
        db.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
            (generate_password_hash(temp_password), reset_req['user_id'])
        )
        db.execute(
            "UPDATE password_resets SET status = 'approved', reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session.get('admin_username'), request_id)
        )
        db.commit()
        log_event('admin_action', details={
            'action': 'password_reset_approved',
            'target_user_id': reset_req['user_id'],
            'admin': session.get('admin_username')
        })
        flash(f'Password reset approved for {reset_req["username"]}. Temporary password: {temp_password}')
    else:
        flash('Reset request not found or already processed.')

    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/reset-requests/<int:request_id>/deny', methods=['POST'])
@admin_required
def deny_reset(request_id):
    db = get_db()
    reset_req = db.execute(
        """SELECT pr.*, u.username FROM password_resets pr
           JOIN users u ON pr.user_id = u.id
           WHERE pr.id = ? AND pr.status = 'pending'""",
        (request_id,)
    ).fetchone()

    if reset_req:
        db.execute(
            "UPDATE password_resets SET status = 'denied', reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session.get('admin_username'), request_id)
        )
        db.commit()
        log_event('admin_action', details={
            'action': 'password_reset_denied',
            'target_user_id': reset_req['user_id'],
            'admin': session.get('admin_username')
        })
        flash(f'Password reset denied for {reset_req["username"]}.')
    else:
        flash('Reset request not found or already processed.')

    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    db = get_db()

    if request.method == 'POST':
        for key in request.form:
            if key.startswith('setting_'):
                setting_key = key[8:]
                value = request.form[key]
                db.execute(
                    "UPDATE system_settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
                    (value, setting_key)
                )
        db.commit()
        log_event('settings_change', details={'admin': session.get('admin_username')})
        flash('Settings updated successfully.')

    all_settings = db.execute("SELECT * FROM system_settings ORDER BY key").fetchall()
    return render_template('admin/settings.html', settings=all_settings)


@admin_bp.route('/logs')
@admin_required
def logs():
    db = get_db()
    event_type = request.args.get('event_type', '')
    page = int(request.args.get('page', 1))
    per_page = 50

    query = "SELECT al.*, u.username FROM audit_log al LEFT JOIN users u ON al.user_id = u.id"
    params = []

    if event_type:
        query += " WHERE al.event_type = ?"
        params.append(event_type)

    query += " ORDER BY al.created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    log_entries = db.execute(query, params).fetchall()

    event_types = db.execute("SELECT DISTINCT event_type FROM audit_log ORDER BY event_type").fetchall()

    return render_template('admin/logs.html',
                           logs=log_entries,
                           event_types=event_types,
                           current_filter=event_type,
                           page=page)


@admin_bp.route('/backup', methods=['POST'])
@admin_required
def backup():
    backup_dir = current_app.config.get('BACKUP_DIR',
                                         os.path.join(current_app.config['DATABASE_DIR'], 'backups'))
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'corpchat_backup_{timestamp}.db'
    backup_path = os.path.join(backup_dir, backup_name)

    shutil.copy2(current_app.config['DATABASE_PATH'], backup_path)

    log_event('backup_created', details={
        'backup_file': backup_name,
        'admin': session.get('admin_username')
    })
    flash(f'Backup created: {backup_name}')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/debug')
@admin_required
def debug():
    return jsonify({
        'app_version': current_app.config.get('APP_VERSION', 'unknown'),
        'python_version': sys.version,
        'debug_mode': current_app.debug,
        'database_path': current_app.config['DATABASE_PATH'],
        'upload_folder': current_app.config['UPLOAD_FOLDER'],
        'max_upload_size': current_app.config['MAX_CONTENT_LENGTH'],
        'server_time': datetime.now().isoformat(),
    })
