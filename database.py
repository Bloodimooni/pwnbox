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
        ('admin', generate_password_hash('K9#mPx2@vL7qRt4!'), 'superadmin')
    )

    # CorpChat bot account (id=1)
    bot_token = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (username, email, password_hash, display_name, bio, api_token) VALUES (?, ?, ?, ?, ?, ?)",
        ('chatbot', 'bot@corpchat.local', generate_password_hash('bot12345'),
         'CorpChat Bot', 'Automated assistant for CorpChat.', bot_token)
    )

    # Worker account - sarah_chen (id=2) - her reset token is pre-seeded and discoverable via SQLi
    sarah_token = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (username, email, password_hash, display_name, bio, api_token, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ('sarah_chen', 'sarah.chen@corpchat.local', generate_password_hash('sarah2024!'),
         'Sarah Chen', 'Product Manager. Been here 3 years!', sarah_token, 'user')
    )

    # Manager account - manager_bob (id=3) - has admin role, api_token discoverable via IDOR
    bob_token = '7f3d9e2a-1b4c-4f8e-a3d7-5c9b0e6f2a1d'
    db.execute(
        "INSERT INTO users (username, email, password_hash, display_name, bio, api_token, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ('manager_bob', 'bob.manager@corpchat.local', generate_password_hash('b0bM@nager2024!'),
         'Bob Manager', 'Senior Manager. Admin access for platform oversight.', bob_token, 'admin')
    )

    # Compliance bot account - compliancebot (id=4)
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

    # Historical messages — Day -14 (Monday morning)
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 1, 'Good morning everyone! New week starts now. Reminder: Q4 planning season is officially open.', '-14 days -118 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, 'Morning \U0001f634 VPN is down for me again, anyone else?', '-14 days -112 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 3, 'Works fine on my end. Try restarting the NetBird client.', '-14 days -109 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, 'Nope still nothing. IT ticket submitted. Classic Monday.', '-14 days -104 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, 'Okay who used the last of the ground coffee and put the empty bag BACK in the cupboard. I will find you.', '-14 days -97 minutes')
    )

    # Historical messages — Day -13 (Tuesday)
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (2, 1, 'Q4 security audit begins in two weeks. All managers: please review team access permissions and submit the compliance checklist.', '-13 days -115 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 3, 'Team standup moved to 9:30 today. Updated invite sent.', '-13 days -108 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, 'ty, i was already in the old slot staring at an empty room', '-13 days -103 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 3, 'Fun fact: CorpChat as a platform is now 5 years old this month \U0001f382', '-13 days -82 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, "Fun fact: I've filed 52 bug reports in those 5 years and exactly 4 have been closed.", '-13 days -76 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 3, 'Some of those were duplicates, Sarah.', '-13 days -71 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, 'they were not bob', '-13 days -68 minutes')
    )

    # Historical messages — Day -12 (Wednesday)
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, 'Anyone else getting 403 on the old reporting portal? Need Q3 exports.', '-12 days -110 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 3, 'That portal was deprecated last quarter. Use the new dashboard \u2014 sending link now.', '-12 days -105 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, 'the link you sent is also a 403, bob', '-12 days -101 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 1, 'Automated notice: scheduled maintenance on the backup server tonight 22:00\u2013midnight. Expect brief downtime.', '-12 days -88 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, "'Brief' downtime. Last time 'brief' was 4 hours. I am logging this.", '-12 days -84 minutes')
    )

    # Historical messages — Day -11 (Thursday)
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, "bob just sent me a calendar invite titled 'Quick 15-min sync'. it is 90 minutes long.", '-11 days -107 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 3, "There's a lot to cover.", '-11 days -102 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, "there's always a lot to cover, bob", '-11 days -98 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 1, 'Maintenance complete. All systems operational.', '-11 days -79 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, 'oh NOW it works. beautiful timing.', '-11 days -74 minutes')
    )

    # Historical messages — Day -10 (Friday)
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, 'TGIF \U0001f389 running on caffeine and spite', '-10 days -116 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 3, 'Great week team. Q4 goal-setting forms are due Monday. Links in your inboxes.', '-10 days -62 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, 'bob it is 4:58pm on a friday', '-10 days -58 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 3, 'Just a friendly reminder!', '-10 days -55 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, 'this is fine \U0001f525 everything is fine \U0001f525\U0001f525', '-10 days -52 minutes')
    )

    # Historical messages — Day -7 (Monday)
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, 'Good morning! New week, new me, same backlog \U0001f4aa', '-7 days -118 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 3, "Morning all! Q4 audit prep kick-off meeting is on your calendars for 2pm. It'll be 3 hours but there's a lot of ground to cover.", '-7 days -112 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, 'bob. 3 hours.', '-7 days -107 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 3, 'We can split it into two sessions if needed.', '-7 days -103 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, '...or we could just send a document', '-7 days -99 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (2, 3, 'All staff: please ensure access logs are up to date before the security review. See the Q4 checklist in the admin portal.', '-7 days -76 minutes')
    )

    # Historical messages — Day -6 (Tuesday)
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, 'hot take: standups should be 10 minutes max. not 45. just 10.', '-6 days -113 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 3, 'Complex blockers sometimes need more discussion time.', '-6 days -108 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, 'then SCHEDULE A SEPARATE MEETING BOB', '-6 days -103 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, "side note \u2014 has anyone else noticed the search returning weird results? like extra rows that feel off", '-6 days -88 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 3, 'What do you mean? What are you searching for?', '-6 days -83 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, "doesn't matter, probably a display bug. logging a ticket.", '-6 days -79 minutes')
    )

    # Historical messages — Day -5 (Wednesday)
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (2, 1, 'System update: the automated compliance monitoring bot (username: compliancebot) is now active. It reviews all DM conversations for policy compliance. Any issues, contact your line manager.', '-5 days -109 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, 'hold on. a bot is reading all our DMs?', '-5 days -103 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 3, "It's standard compliance practice. It's automated.", '-5 days -98 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, "totally normal. 100% fine. I'm fine.", '-5 days -93 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, "need a meme break. someone describe the funniest thing that happened to them this week. I'll start: I sent a P1 incident alert to the wrong Slack. the other company's ops team responded faster than ours.", '-5 days -77 minutes')
    )

    # Historical messages — Day -4 (Thursday)
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, "IT just remote-desktopped into my machine without telling me. I watched my mouse wander around for 10 minutes while I was on a call.", '-4 days -106 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 3, 'Standard support procedure.', '-4 days -101 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, "it opened Notepad, typed nothing, and closed it. what was it doing.", '-4 days -97 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 3, 'Diagnostics.', '-4 days -93 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, "bob that's not what diagnostics means", '-4 days -89 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 1, 'Reminder: the corpchat-admin binary has been placed in the uploads/tools directory for the ops team evaluation. Internal use only.', '-4 days -74 minutes')
    )

    # Historical messages — Day -3 (Monday)
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 3, "Team \u2014 heads-up that I need to submit a password reset request. Having some login issues. Waiting on the token.", '-3 days -112 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, "IT is a bit backed up this week. Hang tight, shouldn't be more than a day or two.", '-3 days -106 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 3, "Thanks! I'll keep checking. Have a presentation at 10, really need access back.", '-3 days -102 minutes')
    )

    # Historical messages — Day -2 (Tuesday)
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, 'okay current status: 3 PRs open, 2 meetings conflicting, 1 coffee spilled on keyboard, 0 regrets', '-2 days -108 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 3, 'Are you okay?', '-2 days -103 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, 'I am THRIVING bob', '-2 days -99 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 1, 'Automated: weekly backup completed. 847 files archived.', '-2 days -84 minutes')
    )

    # Historical messages — Day -1 (Wednesday, yesterday)
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 3, "Morning all! Quick reminder about the security audit \u2014 it includes a review of API access tokens. Please check your tokens haven't been shared anywhere.", '-1 days -118 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (1, 2, 'noted! btw is anyone else finding the search results page a bit... chatty? might be worth a look', '-1 days -112 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, 'anyway. coffee machine on floor 3 is making espresso when you ask for americano. this is either a bug or a feature.', '-1 days -97 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 3, 'Facilities has been notified.', '-1 days -92 minutes')
    )
    db.execute(
        "INSERT INTO messages (channel_id, user_id, content, created_at) VALUES (?, ?, ?, datetime('now', ?))",
        (3, 2, "it's been 'notified' for 2 weeks bob", '-1 days -88 minutes')
    )

    # Pre-seed sarah_chen's password reset token (id=2 is sarah_chen)
    # This token is discoverable via SQL injection on the search endpoint
    sarah_reset_token = 'a3f8c2e1b4d7f9a0c5e2b8d4f1a6c3e7'
    db.execute(
        "INSERT INTO password_resets (user_id, token, status) VALUES (?, ?, 'approved')",
        (2, sarah_reset_token)
    )

    # Seed DM conversation between chatbot (id=1) and manager_bob (id=3)
    # The Stage 3 flag is in this conversation - only accessible after IDOR + token-login escalation
    db.execute(
        "INSERT INTO dm_conversations (user1_id, user2_id) VALUES (?, ?)",
        (1, 3)
    )
    # conversation id=1
    db.execute(
        "INSERT INTO dm_messages (conversation_id, sender_id, content) VALUES (?, ?, ?)",
        (1, 1, "Hi Bob, automated security report for Q4. Confidential access key for the audit portal: CTF{idor_token_auth_bypass_privesc_complete}")
    )
    db.execute(
        "INSERT INTO dm_messages (conversation_id, sender_id, content) VALUES (?, ?, ?)",
        (1, 3, "Thanks! I'll review this. Make sure this stays between us - this is sensitive.")
    )
    db.execute(
        "INSERT INTO dm_messages (conversation_id, sender_id, content) VALUES (?, ?, ?)",
        (1, 1, "One more thing: the compliance monitoring bot (username: compliancebot) went live this week. "
               "It automatically reads every DM conversation every 60 seconds to check for policy violations. "
               "Heads up: I flagged a potential issue to the dev team - the DM renderer passes message content "
               "directly to the browser without sanitization. Could be worth looking at before the audit.")
    )
    db.execute(
        "INSERT INTO dm_messages (conversation_id, sender_id, content) VALUES (?, ?, ?)",
        (1, 1, "Also: Jamie left the internal debug API endpoint live on /api/v1/debug — it accepts a POST "
               "with a 'script' field and runs it from the scripts/ directory. It's gated behind a separate "
               "debug token (not your normal API token) so it should be safe, but it's worth auditing before "
               "the security review.")
    )
    db.execute(
        "INSERT INTO dm_messages (conversation_id, sender_id, content) VALUES (?, ?, ?)",
        (1, 1, "One more housekeeping note: the corpchat-admin binary was copied to "
               "/data/uploads/tools/corpchat-admin for the ops team to test. It's not linked from the UI "
               "but it's sitting there on the filesystem.")
    )

    # --- Crypto — Laura ---
    # Seed legacy MD5(base64(password)) hashes for all users.
    # This is the "weak crypto" scheme players discover after SSH access + DB dump via the binary.
    # compliancebot's legacy "password" is the flag itself — cracking it reveals the next step.
    def _legacy_hash(plaintext):
        b64 = base64.b64encode(plaintext.encode()).decode()
        return hashlib.md5(b64.encode()).hexdigest()

    legacy_passwords = {
        'chatbot':     ('bot12345',                             None),
        'sarah_chen':  ('sarah2024!',                           None),
        'manager_bob': ('b0bM@nager2024!',                      None),
        # compliancebot's "password" in the legacy system is the flag
        'compliancebot':   ('CTF{md5_b64_l3g4cy_p4ss_cr4ck3d}',    None),
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
