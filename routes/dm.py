from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database import get_db
from routes.auth import login_required, full_access_required
import re

dm_bp = Blueprint('dm', __name__)


def get_or_create_conversation(user1_id, user2_id):
    """Get existing conversation between two users, or create one.
    Always stores the lower user_id as user1_id for uniqueness."""
    low, high = sorted([user1_id, user2_id])
    db = get_db()
    conv = db.execute(
        "SELECT * FROM dm_conversations WHERE user1_id = ? AND user2_id = ?",
        (low, high)
    ).fetchone()
    if conv:
        return conv['id']
    cursor = db.execute(
        "INSERT INTO dm_conversations (user1_id, user2_id) VALUES (?, ?)",
        (low, high)
    )
    db.commit()
    return cursor.lastrowid


@dm_bp.route('/')
@full_access_required
def index():
    return dm_view(None)


@dm_bp.route('/<int:conversation_id>')
@full_access_required
def conversation(conversation_id):
    return dm_view(conversation_id)


@dm_bp.route('/user/<int:user_id>')
@full_access_required
def start_with_user(user_id):
    """Start or open a DM with a specific user."""
    current_user_id = session['user_id']
    if user_id == current_user_id:
        flash('You cannot DM yourself.')
        return redirect(url_for('dm.index'))

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)).fetchone()
    if not user:
        flash('User not found.')
        return redirect(url_for('dm.index'))

    conv_id = get_or_create_conversation(current_user_id, user_id)
    return redirect(url_for('dm.conversation', conversation_id=conv_id))


@dm_bp.route('/new', methods=['POST'])
@full_access_required
def new_conversation():
    """Start a new DM from the user picker."""
    target_user_id = request.form.get('user_id', type=int)
    if not target_user_id:
        flash('Please select a user.')
        return redirect(url_for('dm.index'))
    return redirect(url_for('dm.start_with_user', user_id=target_user_id))


def dm_view(conversation_id):
    db = get_db()
    current_user_id = session['user_id']

    # Get all conversations for this user with the other user's info
    conversations = db.execute(
        """SELECT dc.id, dc.created_at,
                  CASE WHEN dc.user1_id = ? THEN dc.user2_id ELSE dc.user1_id END as other_user_id,
                  CASE WHEN dc.user1_id = ? THEN u2.username ELSE u1.username END as other_username,
                  CASE WHEN dc.user1_id = ? THEN u2.display_name ELSE u1.display_name END as other_display_name
           FROM dm_conversations dc
           JOIN users u1 ON dc.user1_id = u1.id
           JOIN users u2 ON dc.user2_id = u2.id
           WHERE dc.user1_id = ? OR dc.user2_id = ?
           ORDER BY dc.created_at DESC""",
        (current_user_id, current_user_id, current_user_id,
         current_user_id, current_user_id)
    ).fetchall()

    active_conv = None
    messages = []

    if conversation_id:
        active_conv = db.execute(
            "SELECT * FROM dm_conversations WHERE id = ? AND (user1_id = ? OR user2_id = ?)",
            (conversation_id, current_user_id, current_user_id)
        ).fetchone()

        if not active_conv:
            flash('Conversation not found.')
            return redirect(url_for('dm.index'))

        messages = db.execute(
            """SELECT dm.id, dm.content, dm.created_at, dm.attachment_id, dm.sender_id,
                      u.username, u.display_name, u.avatar_filename,
                      f.filename as attachment_filename, f.mime_type as attachment_mime_type
               FROM dm_messages dm
               JOIN users u ON dm.sender_id = u.id
               LEFT JOIN files f ON dm.attachment_id = f.id
               WHERE dm.conversation_id = ?
               ORDER BY dm.created_at ASC""",
            (conversation_id,)
        ).fetchall()

        # --- XSS — Leon ---
        messages = [dict(m) for m in messages]
        for m in messages:
            if m['content']:
                m['content'] = re.sub(
                    r"<script.*?>.*?</script>",
                    "",
                    m['content'],
                    flags=re.IGNORECASE | re.DOTALL
                )


    # Get other user info for active conversation header
    other_user = None
    my_delete_requested = 0
    other_delete_requested = 0
    if active_conv:
        other_user_id = active_conv['user2_id'] if active_conv['user1_id'] == current_user_id else active_conv['user1_id']
        other_user = db.execute(
            "SELECT id, username, display_name FROM users WHERE id = ?",
            (other_user_id,)
        ).fetchone()

        # Determine deletion request state
        if active_conv['user1_id'] == current_user_id:
            my_delete_requested = active_conv['user1_delete_requested'] if 'user1_delete_requested' in active_conv.keys() else 0
            other_delete_requested = active_conv['user2_delete_requested'] if 'user2_delete_requested' in active_conv.keys() else 0
        else:
            my_delete_requested = active_conv['user2_delete_requested'] if 'user2_delete_requested' in active_conv.keys() else 0
            other_delete_requested = active_conv['user1_delete_requested'] if 'user1_delete_requested' in active_conv.keys() else 0

    # Get user role
    user = db.execute("SELECT role FROM users WHERE id = ?", (current_user_id,)).fetchone()
    user_role = user['role'] if user else 'user'

    # Get all users for "new DM" picker (exclude self)
    all_users = db.execute(
        "SELECT id, username, display_name FROM users WHERE id != ? AND is_active = 1 ORDER BY username",
        (current_user_id,)
    ).fetchall()

    return render_template('dm/dm.html',
                           conversations=conversations,
                           active_conv=active_conv,
                           other_user=other_user,
                           messages=messages,
                           all_users=all_users,
                           user_role=user_role,
                           my_delete_requested=my_delete_requested,
                           other_delete_requested=other_delete_requested)
