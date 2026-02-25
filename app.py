import os
from flask import Flask, redirect, url_for, session, g, send_from_directory, render_template_string
from database import init_db, close_db, get_db


def create_app():
    app = Flask(__name__)

    # Load configuration
    config_class = os.environ.get('FLASK_CONFIG', 'config.DevelopmentConfig')
    app.config.from_object(config_class)

    # Ensure DATABASE_PATH is set (property doesn't work with from_object)
    if 'DATABASE_PATH' not in app.config or not app.config['DATABASE_PATH']:
        db_dir = app.config.get('DATABASE_DIR', os.path.join(os.path.dirname(__file__), 'data'))
        app.config['DATABASE_PATH'] = os.path.join(db_dir, 'corpchat.db')

    # Ensure runtime directories exist
    for dir_key in ('DATABASE_DIR', 'UPLOAD_FOLDER', 'LOG_DIR'):
        dir_path = app.config.get(dir_key)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

    backup_dir = app.config.get('BACKUP_DIR')
    if backup_dir:
        os.makedirs(backup_dir, exist_ok=True)

    # Database teardown
    app.teardown_appcontext(close_db)

    # Initialize database
    with app.app_context():
        init_db()

    # Register blueprints
    from routes.auth import auth_bp
    from routes.chat import chat_bp
    from routes.profile import profile_bp
    from routes.files import files_bp
    from routes.search import search_bp
    from routes.admin import admin_bp
    from routes.api import api_bp
    from routes.dm import dm_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp, url_prefix='/chat')
    app.register_blueprint(dm_bp, url_prefix='/dm')
    app.register_blueprint(profile_bp, url_prefix='/profile')
    app.register_blueprint(files_bp, url_prefix='/files')
    app.register_blueprint(search_bp, url_prefix='/search')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api/v1')

    @app.before_request
    def update_user_activity():
        if 'user_id' in session and not session.get('must_change_password'):
            try:
                db = get_db()
                db.execute(
                    "UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE id = ?",
                    (session['user_id'],)
                )
                db.commit()
            except Exception:
                pass

    @app.route('/')
    def index():
        if 'user_id' in session:
            return redirect(url_for('chat.index'))
        return redirect(url_for('auth.login'))

    # CTF Challenge: Serve challenge directory with exposed git and directory listing
    @app.route('/challenge/')
    @app.route('/challenge/<path:filepath>')
    def serve_challenge(filepath=''):
        """Serve CTF challenge files including .git directory with directory listing"""
        challenge_dir = os.path.join(os.path.dirname(__file__), 'static', 'challenge')
        
        # Security: prevent directory traversal
        if '..' in filepath:
            return 'Not Found', 404
        
        full_path = os.path.join(challenge_dir, filepath)
        
        # Check if path exists
        if not os.path.exists(full_path):
            return 'Not Found', 404
        
        # If it's a file, serve it
        if os.path.isfile(full_path):
            return send_from_directory(challenge_dir, filepath)
        
        # If it's a directory, generate HTML listing with wget-compatible directory listing
        if os.path.isdir(full_path):
            try:
                items = os.listdir(full_path)
                
                # Sort: directories first, then files
                dirs = sorted([f for f in items if os.path.isdir(os.path.join(full_path, f))])
                files = sorted([f for f in items if os.path.isfile(os.path.join(full_path, f))])
                
                # Build parent directory link if not root
                parent_link = ''
                if filepath and filepath != '/':
                    parent_path = '/'.join(filepath.split('/')[:-1])
                    parent_link = f'<li><a href="/challenge/{parent_path}/">..</a></li>'
                
                # Build directory links
                dir_links = ''
                for d in dirs:
                    new_path = filepath + '/' + d if filepath else d
                    dir_links += f'<li><a href="/challenge/{new_path}/">{d}/</a></li>\n'
                
                # Build file links
                file_links = ''
                for f in files:
                    new_path = filepath + '/' + f if filepath else f
                    file_links += f'<li><a href="/challenge/{new_path}">{f}</a></li>\n'
                
                # Generate HTML (wget-compatible directory listing)
                html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Index of /challenge/{filepath}</title>
</head>
<body>
    <h1>Index of /challenge/{filepath}</h1>
    <ul>
        {parent_link}
        {dir_links}
        {file_links}
    </ul>
</body>
</html>'''
                
                return html, 200, {'Content-Type': 'text/html'}
            except Exception as e:
                return f'Error listing directory: {str(e)}', 500

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=7000)
