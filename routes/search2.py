from flask import Blueprint, render_template, request
from database import get_db
from routes.admin import users
from routes.auth import login_required

search_bp = Blueprint('search', __name__)

@search_bp.route('/')
@login_required
def index():
    query = request.args.get('q', '').strip()
    messages = []
    users = []
    tokens = []

    if query:
        db = get_db()
        # Normale Suche
        messages = db.execute(
            """SELECT m.*, u.username, u.display_name, c.name as channel_name
               FROM messages m
               JOIN users u ON m.user_id = u.id
               JOIN channels c ON m.channel_id = c.id
               WHERE m.content LIKE ?
               ORDER BY m.created_at DESC
               LIMIT 50""",
            (f'%{query}%',)
        ).fetchall()

        users = db.execute(
            """SELECT id, username, display_name
               FROM users
               WHERE username LIKE ? OR display_name LIKE ?
               ORDER BY username
               LIMIT 20""",
            (f'%{query}%', f'%{query}%')
        ).fetchall()

        cursor = db.cursor()
        sql = f"SELECT id, username, token FROM users WHERE token LIKE '%{query}%'"
        print("Ausgeführte Query (Token):", sql)
        try:
            cursor.execute(sql)
            tokens = cursor.fetchall()
        except Exception as e:
            tokens = []
            print("Token-Suche Fehler:", e)

    return render_template('search/results.html', query=query, messages=messages, users=users, tokens=tokens)