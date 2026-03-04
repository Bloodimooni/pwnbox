from flask import Blueprint, render_template, request, session
from database import get_db
from routes.auth import login_required

search_bp = Blueprint('search', __name__)


@search_bp.route('/')
@login_required
def index():
    query = request.args.get('q', '').strip()
    messages = []
    users = []
    token_results = []

    if query:
        db = get_db()

        user = db.execute("SELECT role FROM users WHERE id = ?", (session['user_id'],)).fetchone()
        user_role = user['role'] if user else 'user'

        # Message search (parameterized - safe)
        # New users are restricted to #general only
        if user_role == 'new_user':
            messages = db.execute(
                """SELECT m.*, u.username, u.display_name, c.name as channel_name
                   FROM messages m
                   JOIN users u ON m.user_id = u.id
                   JOIN channels c ON m.channel_id = c.id
                   WHERE m.content LIKE ? AND c.name = 'general' AND m.is_deleted = 0
                   ORDER BY m.created_at DESC
                   LIMIT 20""",
                (f'%{query}%',)
            ).fetchall()
        else:
            messages = db.execute(
                """SELECT m.*, u.username, u.display_name, c.name as channel_name
                   FROM messages m
                   JOIN users u ON m.user_id = u.id
                   JOIN channels c ON m.channel_id = c.id
                   WHERE m.content LIKE ? AND m.is_deleted = 0
                   ORDER BY m.created_at DESC
                   LIMIT 50""",
                (f'%{query}%',)
            ).fetchall()

        # User search (parameterized - safe)
        users = db.execute(
            """SELECT id, username, display_name
               FROM users
               WHERE username LIKE ? OR display_name LIKE ?
               ORDER BY username
               LIMIT 20""",
            (f'%{query}%', f'%{query}%')
        ).fetchall()

        # --- SQL injection — Svenja ---
        # ===== VULNERABLE QUERY - SQL INJECTION =====
        # Internal token lookup: looks up a user by their exact API token string.
        # Returns nothing for any normal search term (tokens are UUIDs, not guessable).
        # VULNERABILITY: Direct string interpolation - injectable via UNION attack.
        # Intended payload: ' UNION SELECT id, user_id, token FROM password_resets --
        cursor = db.cursor()
        sql = f"SELECT id, username, api_token FROM users WHERE api_token = '{query}'"
        try:
            cursor.execute(sql)
            token_results = cursor.fetchall()
        except Exception as e:
            token_results = []
            print("Token lookup error:", e)

    return render_template('search/results.html',
                           query=query,
                           messages=messages,
                           users=users,
                           token_results=token_results)
