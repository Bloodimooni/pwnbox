import hmac
import hashlib
import base64
import json
import os
import uuid
import time
import mimetypes
from functools import wraps
from flask import Blueprint, request, jsonify, session, g, current_app
from werkzeug.security import check_password_hash
from database import get_db

api_bp = Blueprint('api', __name__)

# In-memory typing status: {channel_id: {user_id: {'username': str, 'timestamp': float}}}
_typing_status = {}

# In-memory DM typing status: {conversation_id: {user_id: {'username': str, 'timestamp': float}}}
_dm_typing_status = {}


def api_auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check X-API-Token header first
        token = request.headers.get('X-API-Token')
        if token:
            db = get_db()
            user = db.execute("SELECT * FROM users WHERE api_token = ?", (token,)).fetchone()
            if user and user['is_active']:
                g.api_user = user
                return f(*args, **kwargs)

        # Fall back to session-based auth
        if 'user_id' in session:
            db = get_db()
            user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
            if user and user['is_active']:
                g.api_user = user
                return f(*args, **kwargs)

        return jsonify({"error": "Authentication required"}), 401
    return decorated


@api_bp.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "version": current_app.config.get('APP_VERSION', '1.0.0'),
        "service": "CorpChat"
    })


@api_bp.route('/auth/token', methods=['POST'])
def get_token():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    username = data.get('username', '')
    password = data.get('password', '')

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

    if user and check_password_hash(user['password_hash'], password):
        if not user['is_active']:
            return jsonify({"error": "Account disabled"}), 403
        return jsonify({
            "data": {
                "token": user['api_token'],
                "user_id": user['id'],
                "username": user['username']
            }
        })

    return jsonify({"error": "Invalid credentials"}), 401


@api_bp.route('/channels')
@api_auth_required
def list_channels():
    db = get_db()
    channels = db.execute("SELECT id, name, description, created_at FROM channels ORDER BY name").fetchall()
    return jsonify({
        "data": [dict(ch) for ch in channels]
    })


@api_bp.route('/channels/activity')
@api_auth_required
def channel_activity():
    db = get_db()
    rows = db.execute(
        """SELECT channel_id, MAX(id) as latest_message_id
           FROM messages GROUP BY channel_id"""
    ).fetchall()
    return jsonify({
        "data": {str(row['channel_id']): row['latest_message_id'] for row in rows}
    })


@api_bp.route('/channels/<int:channel_id>/messages')
@api_auth_required
def get_messages(channel_id):
    db = get_db()

    channel = db.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if not channel:
        return jsonify({"error": "Channel not found"}), 404

    since = request.args.get('since', 0, type=int)

    messages = db.execute(
        """SELECT m.id, m.content, m.created_at, m.is_encrypted, m.signature,
                  m.attachment_id,
                  u.id as user_id, u.username, u.display_name, u.avatar_filename,
                  f.filename as attachment_filename, f.mime_type as attachment_mime_type
           FROM messages m
           JOIN users u ON m.user_id = u.id
           LEFT JOIN files f ON m.attachment_id = f.id
           WHERE m.channel_id = ? AND m.id > ?
           ORDER BY m.created_at ASC""",
        (channel_id, since)
    ).fetchall()

    return jsonify({
        "data": [dict(msg) for msg in messages]
    })


@api_bp.route('/channels/<int:channel_id>/messages', methods=['POST'])
@api_auth_required
def send_message(channel_id):
    db = get_db()

    channel = db.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if not channel:
        return jsonify({"error": "Channel not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    content = data.get('content', '').strip()
    attachment_id = data.get('attachment_id')

    if not content and not attachment_id:
        return jsonify({"error": "Message content or attachment required"}), 400

    if attachment_id:
        file_record = db.execute("SELECT * FROM files WHERE id = ?", (attachment_id,)).fetchone()
        if not file_record:
            return jsonify({"error": "Attachment not found"}), 400

    cursor = db.execute(
        "INSERT INTO messages (channel_id, user_id, content, attachment_id) VALUES (?, ?, ?, ?)",
        (channel_id, g.api_user['id'], content, attachment_id)
    )
    db.commit()

    message = db.execute(
        """SELECT m.id, m.content, m.created_at, m.is_encrypted, m.signature,
                  m.attachment_id,
                  u.id as user_id, u.username, u.display_name, u.avatar_filename,
                  f.filename as attachment_filename, f.mime_type as attachment_mime_type
           FROM messages m
           JOIN users u ON m.user_id = u.id
           LEFT JOIN files f ON m.attachment_id = f.id
           WHERE m.id = ?""",
        (cursor.lastrowid,)
    ).fetchone()

    return jsonify({"data": dict(message)}), 201


@api_bp.route('/channels/<int:channel_id>/upload', methods=['POST'])
@api_auth_required
def upload_attachment(channel_id):
    db = get_db()

    channel = db.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if not channel:
        return jsonify({"error": "Channel not found"}), 404

    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({"error": "No file selected"}), 400

    allowed = current_app.config.get('ALLOWED_EXTENSIONS', set())
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        return jsonify({"error": "File type not allowed"}), 400

    original_filename = file.filename
    stored_filename = f"{uuid.uuid4().hex}.{ext}"
    upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], stored_filename)
    file.save(upload_path)

    file_size = os.path.getsize(upload_path)
    mime_type = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'

    cursor = db.execute(
        """INSERT INTO files (filename, stored_filename, file_size, mime_type, uploaded_by, channel_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (original_filename, stored_filename, file_size, mime_type, g.api_user['id'], channel_id)
    )
    db.commit()

    return jsonify({
        "data": {
            "id": cursor.lastrowid,
            "filename": original_filename,
            "mime_type": mime_type,
            "file_size": file_size
        }
    }), 201


@api_bp.route('/users/<int:user_id>')
@api_auth_required
def get_user(user_id):
    db = get_db()
    user = db.execute(
        "SELECT id, username, display_name, bio, avatar_filename, created_at FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"data": dict(user)})


@api_bp.route('/users/me')
@api_auth_required
def get_me():
    user = g.api_user
    return jsonify({
        "data": {
            "id": user['id'],
            "username": user['username'],
            "email": user['email'],
            "display_name": user['display_name'],
            "bio": user['bio'],
            "avatar_filename": user['avatar_filename'],
            "role": user['role'],
            "api_token": user['api_token'],
            "created_at": user['created_at'],
        }
    })


@api_bp.route('/files')
@api_auth_required
def list_files():
    db = get_db()
    files = db.execute(
        """SELECT f.id, f.filename, f.file_size, f.mime_type, f.created_at,
                  f.is_encrypted, u.username as uploaded_by_name
           FROM files f
           JOIN users u ON f.uploaded_by = u.id
           WHERE f.channel_id IS NULL AND f.conversation_id IS NULL
           ORDER BY f.created_at DESC"""
    ).fetchall()
    return jsonify({"data": [dict(f) for f in files]})


@api_bp.route('/search')
@api_auth_required
def search():
    query = request.args.get('q', '').strip()
    search_type = request.args.get('type', 'all')

    if not query:
        return jsonify({"error": "Search query required"}), 400

    db = get_db()
    results = {"messages": [], "users": []}

    if search_type in ('all', 'messages'):
        messages = db.execute(
            """SELECT m.id, m.content, m.created_at,
                      u.username, c.name as channel_name
               FROM messages m
               JOIN users u ON m.user_id = u.id
               JOIN channels c ON m.channel_id = c.id
               WHERE m.content LIKE ?
               ORDER BY m.created_at DESC LIMIT 50""",
            (f'%{query}%',)
        ).fetchall()
        results["messages"] = [dict(m) for m in messages]

    if search_type in ('all', 'users'):
        users = db.execute(
            """SELECT id, username, display_name, bio, avatar_filename
               FROM users WHERE username LIKE ? OR display_name LIKE ?
               ORDER BY username LIMIT 20""",
            (f'%{query}%', f'%{query}%')
        ).fetchall()
        results["users"] = [dict(u) for u in users]

    return jsonify({"data": results})


@api_bp.route('/users/online')
@api_auth_required
def online_users():
    db = get_db()
    users = db.execute(
        """SELECT id, username, display_name, avatar_filename
           FROM users
           WHERE is_active = 1
             AND last_activity IS NOT NULL
             AND last_activity >= datetime('now', '-5 minutes')
           ORDER BY username"""
    ).fetchall()
    return jsonify({
        "data": [dict(u) for u in users]
    })


@api_bp.route('/mutes')
@api_auth_required
def get_mutes():
    db = get_db()
    mutes = db.execute(
        "SELECT mute_type, target_id FROM mutes WHERE user_id = ?",
        (g.api_user['id'],)
    ).fetchall()
    result = {'channel': [], 'dm': [], 'user': []}
    for m in mutes:
        mt = m['mute_type']
        if mt in result:
            result[mt].append(m['target_id'])
    return jsonify({"data": result})


@api_bp.route('/mute', methods=['POST'])
@api_auth_required
def mute_target():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400
    mute_type = data.get('type', '')
    target_id = data.get('target_id')
    if mute_type not in ('channel', 'dm', 'user') or not target_id:
        return jsonify({"error": "Invalid mute type or target"}), 400
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO mutes (user_id, mute_type, target_id) VALUES (?, ?, ?)",
        (g.api_user['id'], mute_type, target_id)
    )
    db.commit()
    return jsonify({"status": "ok"})


@api_bp.route('/unmute', methods=['POST'])
@api_auth_required
def unmute_target():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400
    mute_type = data.get('type', '')
    target_id = data.get('target_id')
    if mute_type not in ('channel', 'dm', 'user') or not target_id:
        return jsonify({"error": "Invalid mute type or target"}), 400
    db = get_db()
    db.execute(
        "DELETE FROM mutes WHERE user_id = ? AND mute_type = ? AND target_id = ?",
        (g.api_user['id'], mute_type, target_id)
    )
    db.commit()
    return jsonify({"status": "ok"})


@api_bp.route('/channels/<int:channel_id>/typing', methods=['POST'])
@api_auth_required
def post_typing(channel_id):
    user_id = g.api_user['id']
    username = g.api_user['display_name'] or g.api_user['username']
    if channel_id not in _typing_status:
        _typing_status[channel_id] = {}
    _typing_status[channel_id][user_id] = {
        'username': username,
        'timestamp': time.time()
    }
    return jsonify({"status": "ok"})


@api_bp.route('/channels/<int:channel_id>/typing')
@api_auth_required
def get_typing(channel_id):
    now = time.time()
    typers = []
    if channel_id in _typing_status:
        # Clean up stale entries (older than 4 seconds)
        stale = [uid for uid, info in _typing_status[channel_id].items()
                 if now - info['timestamp'] > 4]
        for uid in stale:
            del _typing_status[channel_id][uid]
        # Return current typers (exclude self)
        current_user_id = g.api_user['id']
        typers = [info['username'] for uid, info in _typing_status[channel_id].items()
                  if uid != current_user_id]
    return jsonify({"data": typers})


# --- DM endpoints ---

@api_bp.route('/dm/activity')
@api_auth_required
def dm_activity():
    db = get_db()
    current_user_id = g.api_user['id']
    rows = db.execute(
        """SELECT dm.conversation_id, MAX(dm.id) as latest_message_id
           FROM dm_messages dm
           JOIN dm_conversations dc ON dm.conversation_id = dc.id
           WHERE dc.user1_id = ? OR dc.user2_id = ?
           GROUP BY dm.conversation_id""",
        (current_user_id, current_user_id)
    ).fetchall()
    return jsonify({
        "data": {str(row['conversation_id']): row['latest_message_id'] for row in rows}
    })


@api_bp.route('/dm/<int:conversation_id>/messages')
@api_auth_required
def get_dm_messages(conversation_id):
    db = get_db()
    current_user_id = g.api_user['id']

    conv = db.execute(
        "SELECT * FROM dm_conversations WHERE id = ? AND (user1_id = ? OR user2_id = ?)",
        (conversation_id, current_user_id, current_user_id)
    ).fetchone()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    since = request.args.get('since', 0, type=int)

    messages = db.execute(
        """SELECT dm.id, dm.content, dm.created_at, dm.attachment_id, dm.sender_id,
                  u.username, u.display_name, u.avatar_filename,
                  f.filename as attachment_filename, f.mime_type as attachment_mime_type
           FROM dm_messages dm
           JOIN users u ON dm.sender_id = u.id
           LEFT JOIN files f ON dm.attachment_id = f.id
           WHERE dm.conversation_id = ? AND dm.id > ?
           ORDER BY dm.created_at ASC""",
        (conversation_id, since)
    ).fetchall()

    return jsonify({"data": [dict(msg) for msg in messages]})


@api_bp.route('/dm/<int:conversation_id>/messages', methods=['POST'])
@api_auth_required
def send_dm_message(conversation_id):
    db = get_db()
    current_user_id = g.api_user['id']

    conv = db.execute(
        "SELECT * FROM dm_conversations WHERE id = ? AND (user1_id = ? OR user2_id = ?)",
        (conversation_id, current_user_id, current_user_id)
    ).fetchone()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    content = data.get('content', '').strip()
    attachment_id = data.get('attachment_id')

    if not content and not attachment_id:
        return jsonify({"error": "Message content or attachment required"}), 400

    if attachment_id:
        file_record = db.execute("SELECT * FROM files WHERE id = ?", (attachment_id,)).fetchone()
        if not file_record:
            return jsonify({"error": "Attachment not found"}), 400

    cursor = db.execute(
        "INSERT INTO dm_messages (conversation_id, sender_id, content, attachment_id) VALUES (?, ?, ?, ?)",
        (conversation_id, current_user_id, content, attachment_id)
    )
    db.commit()

    message = db.execute(
        """SELECT dm.id, dm.content, dm.created_at, dm.attachment_id, dm.sender_id,
                  u.username, u.display_name, u.avatar_filename,
                  f.filename as attachment_filename, f.mime_type as attachment_mime_type
           FROM dm_messages dm
           JOIN users u ON dm.sender_id = u.id
           LEFT JOIN files f ON dm.attachment_id = f.id
           WHERE dm.id = ?""",
        (cursor.lastrowid,)
    ).fetchone()

    return jsonify({"data": dict(message)}), 201


@api_bp.route('/dm/<int:conversation_id>/upload', methods=['POST'])
@api_auth_required
def upload_dm_attachment(conversation_id):
    db = get_db()
    current_user_id = g.api_user['id']

    conv = db.execute(
        "SELECT * FROM dm_conversations WHERE id = ? AND (user1_id = ? OR user2_id = ?)",
        (conversation_id, current_user_id, current_user_id)
    ).fetchone()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({"error": "No file selected"}), 400

    allowed = current_app.config.get('ALLOWED_EXTENSIONS', set())
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        return jsonify({"error": "File type not allowed"}), 400

    original_filename = file.filename
    stored_filename = f"{uuid.uuid4().hex}.{ext}"
    upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], stored_filename)
    file.save(upload_path)

    file_size = os.path.getsize(upload_path)
    mime_type = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'

    cursor = db.execute(
        """INSERT INTO files (filename, stored_filename, file_size, mime_type, uploaded_by, conversation_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (original_filename, stored_filename, file_size, mime_type, current_user_id, conversation_id)
    )
    db.commit()

    return jsonify({
        "data": {
            "id": cursor.lastrowid,
            "filename": original_filename,
            "mime_type": mime_type,
            "file_size": file_size
        }
    }), 201


@api_bp.route('/dm/<int:conversation_id>/typing', methods=['POST'])
@api_auth_required
def post_dm_typing(conversation_id):
    user_id = g.api_user['id']
    username = g.api_user['display_name'] or g.api_user['username']
    if conversation_id not in _dm_typing_status:
        _dm_typing_status[conversation_id] = {}
    _dm_typing_status[conversation_id][user_id] = {
        'username': username,
        'timestamp': time.time()
    }
    return jsonify({"status": "ok"})


@api_bp.route('/dm/<int:conversation_id>/typing')
@api_auth_required
def get_dm_typing(conversation_id):
    now = time.time()
    typers = []
    if conversation_id in _dm_typing_status:
        stale = [uid for uid, info in _dm_typing_status[conversation_id].items()
                 if now - info['timestamp'] > 4]
        for uid in stale:
            del _dm_typing_status[conversation_id][uid]
        current_user_id = g.api_user['id']
        typers = [info['username'] for uid, info in _dm_typing_status[conversation_id].items()
                  if uid != current_user_id]
    return jsonify({"data": typers})


# --- Crypto stub endpoints ---

@api_bp.route('/crypto/sign', methods=['POST'])
@api_auth_required
def crypto_sign():
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({"error": "Message field required"}), 400

    message = data['message']
    key = current_app.config.get('CRYPTO_SIGNING_KEY', 'default-key')
    signature = hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()

    return jsonify({
        "data": {
            "message": message,
            "signature": signature,
            "algorithm": "HMAC-SHA256"
        }
    })


@api_bp.route('/crypto/verify', methods=['POST'])
@api_auth_required
def crypto_verify():
    data = request.get_json()
    if not data or 'message' not in data or 'signature' not in data:
        return jsonify({"error": "Message and signature fields required"}), 400

    message = data['message']
    provided_sig = data['signature']
    key = current_app.config.get('CRYPTO_SIGNING_KEY', 'default-key')
    expected_sig = hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()

    return jsonify({
        "data": {
            "valid": hmac.compare_digest(provided_sig, expected_sig),
            "algorithm": "HMAC-SHA256"
        }
    })


@api_bp.route('/crypto/encrypt', methods=['POST'])
@api_auth_required
def crypto_encrypt():
    data = request.get_json()
    if not data or 'data' not in data:
        return jsonify({"error": "Data field required"}), 400

    plaintext = data['data']
    # Simple base64 encoding as a placeholder -- team 4 will replace with real (weak) crypto
    encrypted = base64.b64encode(plaintext.encode()).decode()

    return jsonify({
        "data": {
            "encrypted": encrypted,
            "algorithm": "base64-placeholder"
        }
    })

@api_bp.route('/debug', methods=['POST'])
def debug_run():
    data = request.get_json()
    if not data or 'script' not in data:
        return jsonify({"error": "Script name required"}), 400

    script_name = data['script']
    base_dir = '/home/jamie/pwnbox/scripts'
    script_path = os.path.join(base_dir, script_name)

    if not os.path.isfile(script_path):
        return jsonify({"error": "Script not found"}), 404

    try:
        import subprocess
        result = subprocess.run(
            ['bash', script_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        return jsonify({
            "data": {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Script execution timed out"}), 408
    except Exception as e:
        return jsonify({"error": f"Execution failed: {str(e)}"}), 500
