import os
from flask import Flask, redirect, url_for, session, g
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

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=8080)
    # changed port so we can all work on it together without interference
    
