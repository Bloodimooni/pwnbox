import sqlite3
import uuid
import json
from flask import g, current_app
from werkzeug.security import generate_password_hash


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE_PATH'])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource('schema.sql') as f:
        db.executescript(f.read().decode('utf-8'))
    _migrate_db(db)
    _seed_data(db)
    db.commit()


def _migrate_db(db):
    # Add attachment_id to messages if it doesn't exist yet
    msg_columns = [row[1] for row in db.execute("PRAGMA table_info(messages)").fetchall()]
    if 'attachment_id' not in msg_columns:
        db.execute("ALTER TABLE messages ADD COLUMN attachment_id INTEGER REFERENCES files(id)")

    # Add must_change_password flag to users
    user_columns = [row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()]
    if 'must_change_password' not in user_columns:
        db.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0")
    if 'last_activity' not in user_columns:
        db.execute("ALTER TABLE users ADD COLUMN last_activity TIMESTAMP")

    # Add conversation_id to files for DM attachment access control
    files_columns = [row[1] for row in db.execute("PRAGMA table_info(files)").fetchall()]
    if 'conversation_id' not in files_columns:
        db.execute("ALTER TABLE files ADD COLUMN conversation_id INTEGER REFERENCES dm_conversations(id)")
        db.execute("""
            UPDATE files SET conversation_id = (
                SELECT dm.conversation_id FROM dm_messages dm
                WHERE dm.attachment_id = files.id
                LIMIT 1
            )
            WHERE id IN (SELECT attachment_id FROM dm_messages WHERE attachment_id IS NOT NULL)
        """)

    # Add status tracking to password_resets
    pr_columns = [row[1] for row in db.execute("PRAGMA table_info(password_resets)").fetchall()]
    if 'status' not in pr_columns:
        db.execute("ALTER TABLE password_resets ADD COLUMN status TEXT DEFAULT 'pending'")
        # Mark all pre-existing rows as legacy so they don't appear as pending
        db.execute("UPDATE password_resets SET status = 'legacy'")
    if 'reviewed_by' not in pr_columns:
        db.execute("ALTER TABLE password_resets ADD COLUMN reviewed_by TEXT")
    if 'reviewed_at' not in pr_columns:
        db.execute("ALTER TABLE password_resets ADD COLUMN reviewed_at TIMESTAMP")


def _seed_data(db):
    # Only seed if users table is empty
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        return

    # Default admin user for the admin portal
    db.execute(
        "INSERT INTO admin_users (username, password_hash, privilege_level) VALUES (?, ?, ?)",
        ('admin', generate_password_hash('admin2026!'), 'superadmin')
    )

    # Demo regular user
    demo_token = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (username, email, password_hash, display_name, bio, api_token) VALUES (?, ?, ?, ?, ?, ?)",
        ('demo', 'demo@corpchat.local', generate_password_hash('demo123'),
         'Demo User', 'Just a demo account for testing.', demo_token)
    )

    # Second demo user for chat
    bot_token = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (username, email, password_hash, display_name, bio, api_token) VALUES (?, ?, ?, ?, ?, ?)",
        ('chatbot', 'bot@corpchat.local', generate_password_hash('bot12345'),
         'CorpChat Bot', 'Automated assistant for CorpChat.', bot_token)
    )

    # Default channels
    db.execute(
        "INSERT INTO channels (name, description, created_by) VALUES (?, ?, ?)",
        ('general', 'General discussion for the team', 1)
    )
    db.execute(
        "INSERT INTO channels (name, description, created_by) VALUES (?, ?, ?)",
        ('announcements', 'Important announcements', 1)
    )
    db.execute(
        "INSERT INTO channels (name, description, created_by) VALUES (?, ?, ?)",
        ('random', 'Off-topic chat and fun stuff', 1)
    )

    # Seed messages in #general
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content) VALUES (?, ?, ?)",
        (1, 1, 'Welcome to CorpChat! This is the general channel.')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content) VALUES (?, ?, ?)",
        (1, 2, 'Hello everyone! The new chat system is live.')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content) VALUES (?, ?, ?)",
        (1, 1, 'Feel free to explore the channels and features.')
    )

    # Seed message in #announcements
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content) VALUES (?, ?, ?)",
        (2, 2, 'System maintenance scheduled for this weekend. Please save your work.')
    )

    # Default system settings
    settings = [
        ('site_name', 'CorpChat'),
        ('allow_registration', 'true'),
        ('max_upload_size_mb', '10'),
        ('debug_mode', 'false'),
        ('backup_enabled', 'true'),
        ('backup_path', '/data/backups'),
        ('session_timeout_minutes', '60'),
        ('motd', 'Welcome to CorpChat - Your secure corporate messaging platform'),
    ]
    for key, value in settings:
        db.execute(
            "INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)",
            (key, value)
        )
