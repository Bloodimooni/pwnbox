from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database import get_db
from routes.auth import login_required, full_access_required, log_event

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/')
@login_required
def index():
    db = get_db()

    user = db.execute("SELECT role FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    user_role = user['role'] if user else 'user'

    # New users are restricted to the #general channel only
    if user_role == 'new_user':
        channels = db.execute("SELECT * FROM channels WHERE name = 'general'").fetchall()
    else:
        channels = db.execute("SELECT * FROM channels ORDER BY name").fetchall()

    active_channel_id = request.args.get('channel', None)

    if active_channel_id:
        active_channel = db.execute("SELECT * FROM channels WHERE id = ?", (active_channel_id,)).fetchone()
        # Restrict new_user to general only - bounce them back if they try to access other channels
        if active_channel and user_role == 'new_user' and active_channel['name'] != 'general':
            active_channel = db.execute("SELECT * FROM channels WHERE name = 'general'").fetchone()
    else:
        active_channel = db.execute("SELECT * FROM channels WHERE name = 'general'").fetchone()

    if not active_channel and channels:
        active_channel = channels[0]

    messages = []
    if active_channel:
        messages = db.execute(
            """SELECT m.*, u.username, u.display_name, u.avatar_filename,
                      f.filename as attachment_filename, f.mime_type as attachment_mime_type
               FROM messages m
               JOIN users u ON m.user_id = u.id
               LEFT JOIN files f ON m.attachment_id = f.id
               WHERE m.channel_id = ?
               ORDER BY m.created_at ASC""",
            (active_channel['id'],)
        ).fetchall()

    return render_template('chat/chat.html',
                           channels=channels,
                           active_channel=active_channel,
                           messages=messages,
                           user_role=user_role)


@chat_bp.route('/channel/<int:channel_id>')
@login_required
def channel(channel_id):
    return redirect(url_for('chat.index', channel=channel_id))


@chat_bp.route('/channel/create', methods=['POST'])
@full_access_required
def create_channel():
    name = request.form.get('name', '').strip().lower().replace(' ', '-')
    description = request.form.get('description', '').strip()

    if not name or len(name) < 2:
        flash('Channel name must be at least 2 characters.')
        return redirect(url_for('chat.index'))

    db = get_db()
    existing = db.execute("SELECT id FROM channels WHERE name = ?", (name,)).fetchone()
    if existing:
        flash('A channel with that name already exists.')
        return redirect(url_for('chat.index'))

    db.execute(
        "INSERT INTO channels (name, description, created_by) VALUES (?, ?, ?)",
        (name, description, session['user_id'])
    )
    db.commit()

    new_channel = db.execute("SELECT id FROM channels WHERE name = ?", (name,)).fetchone()
    log_event('channel_create', session['user_id'], {'channel': name})

    return redirect(url_for('chat.index', channel=new_channel['id']))
