import sqlite3 as _sqlite3

from flask import Blueprint, render_template, request, session
from database import get_db
from routes.auth import login_required

search_bp = Blueprint('search', __name__)

# Joshua's fix to keep players on the intended CTF path:
# Tables and columns that must not be readable via the intentionally vulnerable
# token-lookup query. Applied via SQLite's authorizer callback so it holds even
# against UNION-based injection — no SQL trick can bypass an authorizer decision.
#
# SQLITE_DENY  — raises an error (used for DM tables: blocks access visibly)
# SQLITE_IGNORE — returns NULL instead of the real value, no error raised.
#   Used for sensitive columns that also appear in the WHERE clause (api_token):
#   DENY would break the WHERE evaluation itself, IGNORE silently nulls them out.
_SQLI_BLOCKED_TABLES  = frozenset({'dm_messages', 'dm_conversations'})
_SQLI_IGNORE_COLUMNS  = frozenset({('users', 'api_token'), ('users', 'password_hash')})

def _sqli_authorizer(action, arg1, arg2, _dbname, _trigger):  # noqa: ARG001
    if action == _sqlite3.SQLITE_READ:
        if arg1 in _SQLI_BLOCKED_TABLES:
            return _sqlite3.SQLITE_DENY
        if (arg1, arg2) in _SQLI_IGNORE_COLUMNS:
            return _sqlite3.SQLITE_IGNORE
    return _sqlite3.SQLITE_OK


@search_bp.route('/')
@login_required
def index():
    query = request.args.get('q', '').strip()
    messages = []
    users = []
    token_results = []
    sql_error = None
    sql_query = None

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
        # NOTE: SELECT uses display_name (not api_token) so a trivial OR 1=1 dump
        #       only reveals boring display names, not sensitive tokens.
        cursor = db.cursor()
        sql = f"SELECT id, username, display_name FROM users WHERE api_token = '{query}'"
        db.set_authorizer(_sqli_authorizer)
        try:
            cursor.execute(sql)
            token_results = cursor.fetchall()
        except Exception as e:
            token_results = []
            sql_error = str(e)
            sql_query = sql
            print("Token lookup error:", e)
        finally:
            db.set_authorizer(None)

    return render_template('search/results.html',
                           query=query,
                           messages=messages,
                           users=users,
                           token_results=token_results,
                           sql_error=sql_error,
                           sql_query=sql_query)
