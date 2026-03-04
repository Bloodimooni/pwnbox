import os
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, send_from_directory
from database import get_db
from routes.auth import login_required, full_access_required, log_event

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/<int:user_id>')
@login_required
def view(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        flash('User not found.')
        return redirect(url_for('chat.index'))

    message_count = db.execute(
        "SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,)
    ).fetchone()[0]

    return render_template('profile/view.html', profile_user=user, message_count=message_count)


@profile_bp.route('/edit', methods=['GET', 'POST'])
@full_access_required
def edit():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()

    if request.method == 'POST':
        display_name = request.form.get('display_name', '').strip()
        bio = request.form.get('bio', '').strip()

        avatar_filename = user['avatar_filename']
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename:
                ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
                if ext in ('png', 'jpg', 'jpeg', 'gif'):
                    avatar_filename = f"{uuid.uuid4().hex}.{ext}"
                    upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], avatar_filename)
                    file.save(upload_path)
                else:
                    flash('Invalid image format. Use PNG, JPG, or GIF.')

        db.execute(
            "UPDATE users SET display_name = ?, bio = ?, avatar_filename = ? WHERE id = ?",
            (display_name or user['username'], bio, avatar_filename, session['user_id'])
        )
        db.commit()

        session['display_name'] = display_name or user['username']
        session['avatar_filename'] = avatar_filename
        log_event('profile_update', session['user_id'])
        flash('Profile updated successfully.')
        return redirect(url_for('profile.view', user_id=session['user_id']))

    return render_template('profile/edit.html', user=user)


@profile_bp.route('/avatar/<filename>')
@login_required
def avatar(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)
