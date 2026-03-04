import os
import sqlite3
import uuid
import json
import base64
import hashlib
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
    # Legacy MD5(base64) password hash — weak scheme discoverable after SSH + binary reversing
    if 'legacy_password_hash' not in user_columns:
        db.execute("ALTER TABLE users ADD COLUMN legacy_password_hash TEXT")

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

    # Add soft-delete support for messages
    msg_columns2 = [row[1] for row in db.execute("PRAGMA table_info(messages)").fetchall()]
    if 'is_deleted' not in msg_columns2:
        db.execute("ALTER TABLE messages ADD COLUMN is_deleted INTEGER DEFAULT 0")

    # Add soft-delete support for DM messages
    dm_msg_columns = [row[1] for row in db.execute("PRAGMA table_info(dm_messages)").fetchall()]
    if 'is_deleted' not in dm_msg_columns:
        db.execute("ALTER TABLE dm_messages ADD COLUMN is_deleted INTEGER DEFAULT 0")

    # Add mutual-consent deletion flags for DM conversations
    dm_conv_columns = [row[1] for row in db.execute("PRAGMA table_info(dm_conversations)").fetchall()]
    if 'user1_delete_requested' not in dm_conv_columns:
        db.execute("ALTER TABLE dm_conversations ADD COLUMN user1_delete_requested INTEGER DEFAULT 0")
    if 'user2_delete_requested' not in dm_conv_columns:
        db.execute("ALTER TABLE dm_conversations ADD COLUMN user2_delete_requested INTEGER DEFAULT 0")

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

    # Demo regular user (id=1)
    demo_token = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (username, email, password_hash, display_name, bio, api_token) VALUES (?, ?, ?, ?, ?, ?)",
        ('demo', 'demo@corpchat.local', generate_password_hash('demo123'),
         'Demo User', 'Just a demo account for testing.', demo_token)
    )

    # CorpChat bot account (id=2)
    bot_token = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (username, email, password_hash, display_name, bio, api_token) VALUES (?, ?, ?, ?, ?, ?)",
        ('chatbot', 'bot@corpchat.local', generate_password_hash('bot12345'),
         'CorpChat Bot', 'Automated assistant for CorpChat.', bot_token)
    )

    # Worker account - sarah_chen (id=3) - her reset token is pre-seeded and discoverable via SQLi
    sarah_token = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (username, email, password_hash, display_name, bio, api_token, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ('sarah_chen', 'sarah.chen@corpchat.local', generate_password_hash('sarah2024!'),
         'Sarah Chen', 'Product Manager. Been here 3 years!', sarah_token, 'user')
    )

    # Manager account - manager_bob (id=4) - has admin role, api_token discoverable via IDOR
    bob_token = '7f3d9e2a-1b4c-4f8e-a3d7-5c9b0e6f2a1d'
    db.execute(
        "INSERT INTO users (username, email, password_hash, display_name, bio, api_token, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ('manager_bob', 'bob.manager@corpchat.local', generate_password_hash('b0bM@nager2024!'),
         'Bob Manager', 'Senior Manager. Admin access for platform oversight.', bob_token, 'admin')
    )

    # Compliance bot account - compliancebot (id=5)
    # Puppeteer bot that logs in and reads all DMs every 60s.
    # Its browser session carries the XSS flag cookie (httpOnly=false).
    compliancebot_token = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (username, email, password_hash, display_name, bio, api_token, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ('compliancebot', 'compliancebot@corpchat.local', generate_password_hash('C0mpl1anceB0t2026'),
         'Compliance Bot', 'Automated compliance monitoring bot. Reads all DM conversations.', compliancebot_token, 'user')
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
        (1, 2, 'Hello everyone! The new chat system is live. Feel free to explore the channels.')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content) VALUES (?, ?, ?)",
        (1, 3, "Hey team! Quick heads-up - I'm locked out of my account and had to submit a password reset. Waiting for the token to come through to my email. Anyone know how long IT usually takes?")
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content) VALUES (?, ?, ?)",
        (1, 4, "Hi Sarah! IT is a bit slow this week. Shouldn't be more than a day. Hang tight!")
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content) VALUES (?, ?, ?)",
        (1, 3, "Thanks Bob! I'll keep checking my inbox. Really need to get back in, I have reports due 😅")
    )

    # Seed message in #announcements
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content) VALUES (?, ?, ?)",
        (2, 2, 'System maintenance scheduled for this weekend. Please save your work.')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content) VALUES (?, ?, ?)",
        (2, 4, 'Reminder: Q4 security audit is coming up. All managers please review access logs.')
    )

    # Seed message in #random
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content) VALUES (?, ?, ?)",
        (3, 1, 'Anyone else think the coffee machine on floor 3 is broken? It keeps making espresso instead of regular.')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content) VALUES (?, ?, ?)",
        (3, 3, 'Haha yes! I reported it. Facilities said they\'d look at it next week.')
    )

    # Pre-seed sarah_chen's password reset token (id=3 is sarah_chen)
    # This token is discoverable via SQL injection on the search endpoint
    sarah_reset_token = 'a3f8c2e1b4d7f9a0c5e2b8d4f1a6c3e7'
    db.execute(
        "INSERT INTO password_resets (user_id, token, status) VALUES (?, ?, 'approved')",
        (3, sarah_reset_token)
    )

    # Seed DM conversation between chatbot (id=2) and manager_bob (id=4)
    # The Stage 3 flag is in this conversation - only accessible after IDOR + token-login escalation
    db.execute(
        "INSERT INTO dm_conversations (user1_id, user2_id) VALUES (?, ?)",
        (2, 4)
    )
    # conversation id=1
    db.execute(
        "INSERT INTO dm_messages (conversation_id, sender_id, content) VALUES (?, ?, ?)",
        (1, 2, "Hi Bob, automated security report for Q4. Confidential access key for the audit portal: FLAG{idor_token_auth_bypass_privesc_complete}")
    )
    db.execute(
        "INSERT INTO dm_messages (conversation_id, sender_id, content) VALUES (?, ?, ?)",
        (1, 4, "Thanks! I'll review this. Make sure this stays between us - this is sensitive.")
    )
    db.execute(
        "INSERT INTO dm_messages (conversation_id, sender_id, content) VALUES (?, ?, ?)",
        (1, 2, "One more thing: the compliance monitoring bot (username: compliancebot) went live this week. "
               "It automatically reads every DM conversation every 60 seconds to check for policy violations. "
               "Heads up: I flagged a potential issue to the dev team - the DM renderer passes message content "
               "directly to the browser without sanitization. Could be worth looking at before the audit.")
    )

    # Seed legacy MD5(base64(password)) hashes for all users.
    # This is the "weak crypto" scheme players discover after SSH access + DB dump via the binary.
    # compliancebot's legacy "password" is the flag itself — cracking it reveals the next step.
    def _legacy_hash(plaintext):
        b64 = base64.b64encode(plaintext.encode()).decode()
        return hashlib.md5(b64.encode()).hexdigest()

    legacy_passwords = {
        'demo':        ('demo123',                              None),
        'chatbot':     ('bot12345',                             None),
        'sarah_chen':  ('sarah2024!',                           None),
        'manager_bob': ('b0bM@nager2024!',                      None),
        # compliancebot's "password" in the legacy system is the flag
        'compliancebot':   ('FLAG{md5_b64_l3g4cy_p4ss_cr4ck3d}',   None),
    }
    for username, (plaintext, _) in legacy_passwords.items():
        db.execute(
            "UPDATE users SET legacy_password_hash = ? WHERE username = ?",
            (_legacy_hash(plaintext), username)
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
