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

     if query:
         db = get_db()
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
             """SELECT * FROM users
                WHERE username LIKE ? OR display_name LIKE ?
                ORDER BY username
                LIMIT 20""",
             (f'%{query}%', f'%{query}%')
         ).fetchall()

     return render_template('search/results.html', query=query, messages=messages, users=users)

# Absichtlich verwundbare Route
@search_bp.route('/')
@login_required
def vulnerable_search():
    query_param = request.args.get("q", "")

    db = get_db()
    cursor = db.cursor()

    # VULNERABLE: direkte Einbettung der User-Input
    sql = f"SELECT id, username, email, password_hash FROM users WHERE username LIKE '%{query_param}%'"
    print("Ausgeführte Query:", sql)

    cursor.execute(sql)
    results = cursor.fetchall()

    return render_template('search/results.html', query=query_param, messages=[], users=results)

