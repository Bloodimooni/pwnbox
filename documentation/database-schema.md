# Database Schema

[Back to Index](README.md)

---

## Overview

PwnBox uses **SQLite3** as its database engine. The database file is located at `data/corpchat.db` (development) or `/data/corpchat.db` (production/Docker).

The schema is defined in `schema.sql` and consists of **12 tables**. Foreign keys are enforced at runtime via `PRAGMA foreign_keys = ON` (set in `database.py:12` every time a connection is opened).

---

## Entity Relationship Diagram

```
┌──────────────┐     ┌───────────────┐     ┌───────────────┐
│   users      │────<│   messages    │>────│   channels    │
│              │     │               │     │               │
│ id (PK)      │     │ id (PK)       │     │ id (PK)       │
│ username     │     │ channel_id(FK)│     │ name          │
│ email        │     │ user_id (FK)  │     │ description   │
│ password_hash│     │ content       │     │ is_private    │
│ display_name │     │ attachment_id │──>─┐│ created_by(FK)│
│ bio          │     │ is_encrypted  │    ││ created_at    │
│ avatar       │     │ signature     │    │└───────────────┘
│ role         │     │ created_at    │    │
│ api_token    │     └───────────────┘    │
│ is_active    │                          │
│ must_change  │     ┌──────────────┐     │
│ last_activity│     │    files     │<────┘
│ created_at   │────<│              │
│ last_login   │     │ id (PK)      │
└──────┬───────┘     │ filename     │
       │             │ stored_name  │
       │             │ file_size    │
       │             │ mime_type    │
       │             │ uploaded_by  │
       │             │ channel_id   │
       │             │ is_encrypted │
       │             └──────────────┘
       │
       │     ┌──────────────────┐     ┌──────────────────┐
       ├────<│ dm_conversations │>────│   dm_messages    │
       │     │                  │     │                  │
       │     │ id (PK)          │     │ id (PK)          │
       │     │ user1_id (FK)    │     │ conversation_id  │
       │     │ user2_id (FK)    │     │ sender_id (FK)   │
       │     │ created_at       │     │ content          │
       │     └──────────────────┘     │ attachment_id    │
       │                              │ created_at       │
       │                              └──────────────────┘
       │     ┌───────────────────┐
       ├────<│ sessions          │    ┌──────────────────┐
       │     │ session_token     │    │  admin_users     │
       │     │ user_id (FK)      │    │                  │
       │     │ ip_address        │    │ id (PK)          │
       │     │ user_agent        │    │ username         │
       │     │ expires_at        │    │ password_hash    │
       │     └───────────────────┘    │ privilege_level  │
       │     ┌───────────────────┐    │ created_at       │
       ├────<│ password_resets   │    └──────────────────┘
       │     │ token             │
       │     │ status            │    ┌──────────────────┐
       │     │ reviewed_by       │    │ system_settings  │
       │     └───────────────────┘    │                  │
       │     ┌───────────────────┐    │ key (PK)         │
       ├────<│ audit_log         │    │ value            │
       │     │ event_type        │    │ updated_at       │
       │     │ details (JSON)    │    └──────────────────┘
       │     │ ip_address        │
       │     └───────────────────┘
       │     ┌───────────────────┐
       └────<│ mutes             │
             │ mute_type         │
             │ target_id         │
             └───────────────────┘
```

---

## Table Definitions

### `users`
**Purpose:** Stores all regular user accounts.

| Column | Type | Default | Constraints | Description |
|--------|------|---------|-------------|-------------|
| `id` | INTEGER | Auto | PRIMARY KEY AUTOINCREMENT | Unique user identifier |
| `username` | TEXT | -- | UNIQUE NOT NULL | Login username (min 3 chars enforced in app) |
| `email` | TEXT | -- | UNIQUE NOT NULL | User email address |
| `password_hash` | TEXT | -- | NOT NULL | Werkzeug-generated password hash |
| `display_name` | TEXT | `''` | -- | Display name shown in UI |
| `bio` | TEXT | `''` | -- | User biography/description |
| `avatar_filename` | TEXT | `'default_avatar.png'` | -- | Filename of avatar in uploads folder |
| `role` | TEXT | `'user'` | -- | User role (currently only 'user') |
| `api_token` | TEXT | NULL | -- | UUID-based API authentication token |
| `is_active` | INTEGER | `1` | -- | Whether the account is enabled (1) or disabled (0) |
| `must_change_password` | INTEGER | `0` | -- | Forces password change on next login (1=yes) |
| `last_activity` | TIMESTAMP | NULL | -- | Updated on every request via `before_request` hook |
| `legacy_password_hash` | TEXT | NULL | -- | `MD5(base64(password))` — intentionally weak legacy scheme for the crypto CTF challenge |
| `created_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | -- | Account creation time |
| `last_login` | TIMESTAMP | NULL | -- | Updated on each successful login |

**Key behaviors:**
- `api_token` is generated as `str(uuid.uuid4())` during registration
- `is_active = 0` blocks login and API access
- `last_activity` is used to determine online status (active within last 5 minutes)
- `must_change_password` redirects user to `/change-password` on every request
- `legacy_password_hash` is seeded for every user; for `compliancebot` the plaintext is the Flag 3 string (see [Crypto Challenge Writeup](writeup/crypto-challenge-writeup.md))

---

### `admin_users`
**Purpose:** Stores admin portal accounts, completely separate from regular users.

| Column | Type | Default | Constraints | Description |
|--------|------|---------|-------------|-------------|
| `id` | INTEGER | Auto | PRIMARY KEY AUTOINCREMENT | Unique admin identifier |
| `username` | TEXT | -- | UNIQUE NOT NULL | Admin login username |
| `password_hash` | TEXT | -- | NOT NULL | Werkzeug-generated password hash |
| `privilege_level` | TEXT | `'admin'` | -- | Privilege tier (e.g., 'superadmin', 'admin') |
| `created_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | -- | Account creation time |

**Key behaviors:**
- Authenticated via `session['admin_id']` (separate from user sessions)
- Default seeded admin: username=`admin`, password=`admin2026!`, level=`superadmin`

---

### `channels`
**Purpose:** Chat channels that users can post messages to.

| Column | Type | Default | Constraints | Description |
|--------|------|---------|-------------|-------------|
| `id` | INTEGER | Auto | PRIMARY KEY AUTOINCREMENT | Unique channel identifier |
| `name` | TEXT | -- | UNIQUE NOT NULL | Channel name (lowercase, hyphens for spaces) |
| `description` | TEXT | `''` | -- | Channel description shown in header |
| `is_private` | INTEGER | `0` | -- | Whether channel is private (not used in current code) |
| `created_by` | INTEGER | -- | REFERENCES users(id) | User who created the channel |
| `created_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | -- | Channel creation time |

**Key behaviors:**
- Channel names are normalized: `strip().lower().replace(' ', '-')` in `routes/chat.py:51`
- Three default channels seeded: `general`, `announcements`, `random`
- The `is_private` field exists in the schema but is not currently used by any route

---

### `messages`
**Purpose:** Chat messages within channels.

| Column | Type | Default | Constraints | Description |
|--------|------|---------|-------------|-------------|
| `id` | INTEGER | Auto | PRIMARY KEY AUTOINCREMENT | Unique message identifier |
| `channel_id` | INTEGER | -- | NOT NULL, REFERENCES channels(id) | Channel this message belongs to |
| `user_id` | INTEGER | -- | NOT NULL, REFERENCES users(id) | User who sent the message |
| `content` | TEXT | `''` | NOT NULL | Message text content |
| `attachment_id` | INTEGER | NULL | REFERENCES files(id) | Optional file attachment |
| `is_encrypted` | INTEGER | `0` | -- | Whether message is encrypted (placeholder) |
| `signature` | TEXT | NULL | -- | Cryptographic signature (placeholder) |
| `is_deleted` | INTEGER | `0` | -- | Soft-delete flag; deleted messages are hidden from the UI but kept in the DB |
| `created_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | -- | When the message was sent |

**Key behaviors:**
- Messages are queried with `ORDER BY created_at ASC` for display
- The `since` parameter in the API filters by `id > ?` for incremental polling
- `attachment_id` was added via migration (not in original schema for existing databases)
- `is_deleted` was added via migration; soft-deleted messages are excluded from all queries with `WHERE is_deleted = 0`
- `is_encrypted` and `signature` are placeholder fields

---

### `files`
**Purpose:** Metadata for all uploaded files.

| Column | Type | Default | Constraints | Description |
|--------|------|---------|-------------|-------------|
| `id` | INTEGER | Auto | PRIMARY KEY AUTOINCREMENT | Unique file identifier |
| `filename` | TEXT | -- | NOT NULL | Original filename as uploaded by user |
| `stored_filename` | TEXT | -- | NOT NULL | UUID-based filename on disk (e.g., `a1b2c3d4.png`) |
| `file_size` | INTEGER | NULL | -- | File size in bytes |
| `mime_type` | TEXT | NULL | -- | MIME type (guessed from filename) |
| `uploaded_by` | INTEGER | -- | NOT NULL, REFERENCES users(id) | User who uploaded the file |
| `channel_id` | INTEGER | NULL | REFERENCES channels(id) | Channel the file was uploaded to (NULL for DM/profile uploads) |
| `conversation_id` | INTEGER | NULL | REFERENCES dm_conversations(id) | DM conversation the file was uploaded to (NULL for channel/profile uploads) |
| `is_encrypted` | INTEGER | `0` | -- | Whether file is encrypted (placeholder) |
| `encryption_key_hint` | TEXT | NULL | -- | Hint for encryption key (placeholder) |
| `created_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | -- | Upload time |

**Key behaviors:**
- Actual files stored in `UPLOAD_FOLDER` using `stored_filename`
- Original `filename` preserved for download headers
- `conversation_id` was added via migration; used for DM attachment access control (only participants of the conversation can download the file)
- Allowed extensions: `txt, pdf, png, jpg, jpeg, gif, zip, doc, docx, mp4, mp3, webm, ogg, wav, mov, avi, svg, webp, csv, json, xml, pptx, xlsx, sh, py`
- Max size: 10 MB (enforced by Flask's `MAX_CONTENT_LENGTH`)

---

### `sessions`
**Purpose:** Tracks user login sessions.

| Column | Type | Default | Constraints | Description |
|--------|------|---------|-------------|-------------|
| `id` | INTEGER | Auto | PRIMARY KEY AUTOINCREMENT | Unique session identifier |
| `session_token` | TEXT | -- | UNIQUE NOT NULL | Session token string |
| `user_id` | INTEGER | -- | NOT NULL, REFERENCES users(id) | User this session belongs to |
| `ip_address` | TEXT | NULL | -- | Client IP address |
| `user_agent` | TEXT | NULL | -- | Client user-agent string |
| `created_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | -- | Session creation time |
| `expires_at` | TIMESTAMP | NULL | -- | Session expiration time |

**Note:** This table exists in the schema but is **not actively used** by the application. Flask's built-in session mechanism (cookie-based, signed with `SECRET_KEY`) is used instead. The table appears to be reserved for future custom session management.

---

### `password_resets`
**Purpose:** Tracks password reset requests and their approval status.

| Column | Type | Default | Constraints | Description |
|--------|------|---------|-------------|-------------|
| `id` | INTEGER | Auto | PRIMARY KEY AUTOINCREMENT | Unique request identifier |
| `user_id` | INTEGER | -- | NOT NULL, REFERENCES users(id) | User requesting the reset |
| `token` | TEXT | -- | UNIQUE NOT NULL | UUID-based reset token |
| `created_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | -- | When the request was made |
| `used` | INTEGER | `0` | -- | Whether the token has been used |
| `status` | TEXT | `'pending'` | -- | Request status: `pending`, `approved`, `denied`, `legacy` |
| `reviewed_by` | TEXT | NULL | -- | Admin username who reviewed |
| `reviewed_at` | TIMESTAMP | NULL | -- | When the review happened |

**Key behaviors:**
- Users submit reset requests via `/reset-password` (POST with username)
- Admins approve/deny requests via the admin dashboard
- On approval: a temporary password is generated, user's `must_change_password` is set to 1
- The `token` field is generated but the old token-based reset flow is deprecated
- `status`, `reviewed_by`, `reviewed_at` were added via migration

---

### `audit_log`
**Purpose:** Records security-relevant events for audit trail.

| Column | Type | Default | Constraints | Description |
|--------|------|---------|-------------|-------------|
| `id` | INTEGER | Auto | PRIMARY KEY AUTOINCREMENT | Unique log entry identifier |
| `event_type` | TEXT | -- | NOT NULL | Event category (e.g., `login`, `login_failed`, `register`) |
| `user_id` | INTEGER | NULL | -- | User associated with the event (NULL for failed logins) |
| `details` | TEXT | NULL | -- | JSON-encoded event details |
| `ip_address` | TEXT | NULL | -- | Client IP address (`request.remote_addr`) |
| `created_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | -- | When the event occurred |

**Logged event types:**
| Event Type | When Logged | Details Included |
|------------|-------------|------------------|
| `login` | Successful user login | `{"username": "..."}` |
| `login_failed` | Failed login attempt | `{"username": "..."}` |
| `register` | New user registration | `{"username": "..."}` |
| `logout` | User logout | -- |
| `password_reset_request` | User requests password reset | -- |
| `password_changed` | User changes password | -- |
| `profile_update` | Profile edited | -- |
| `file_upload` | File uploaded | `{"filename": "..."}` |
| `file_download` | File downloaded | `{"file_id": N, "filename": "..."}` |
| `file_delete` | File deleted | `{"file_id": N, "filename": "..."}` |
| `channel_create` | New channel created | `{"channel": "..."}` |
| `admin_login` | Admin portal login | `{"admin_username": "..."}` |
| `admin_login_failed` | Failed admin login | `{"admin_username": "..."}` |
| `admin_logout` | Admin portal logout | `{"admin_username": "..."}` |
| `admin_action` | Admin performs action | `{"action": "...", "target_user_id": N}` |
| `settings_change` | System settings updated | `{"admin": "..."}` |
| `backup_created` | Database backup created | `{"backup_file": "...", "admin": "..."}` |

---

### `system_settings`
**Purpose:** Key-value store for application configuration managed via the admin panel.

| Column | Type | Default | Constraints | Description |
|--------|------|---------|-------------|-------------|
| `key` | TEXT | -- | PRIMARY KEY | Setting name |
| `value` | TEXT | -- | NOT NULL | Setting value |
| `updated_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | -- | Last update time |

**Default settings** (see [Getting Started](getting-started.md) for the full list).

**Note:** These settings are stored in the database but are **not read by the application at runtime** -- they exist primarily for the admin panel UI. The actual application behavior is controlled by `config.py` classes.

---

### `dm_conversations`
**Purpose:** Tracks 1-to-1 direct message conversations between two users.

| Column | Type | Default | Constraints | Description |
|--------|------|---------|-------------|-------------|
| `id` | INTEGER | Auto | PRIMARY KEY AUTOINCREMENT | Unique conversation identifier |
| `user1_id` | INTEGER | -- | NOT NULL, REFERENCES users(id) | First user (always the lower ID) |
| `user2_id` | INTEGER | -- | NOT NULL, REFERENCES users(id) | Second user (always the higher ID) |
| `user1_delete_requested` | INTEGER | `0` | -- | Whether user1 has requested conversation deletion |
| `user2_delete_requested` | INTEGER | `0` | -- | Whether user2 has requested conversation deletion |
| `created_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | -- | When conversation was started |

**Constraints:** `UNIQUE(user1_id, user2_id)`

**Key behaviors:**
- `user1_id` is always the smaller of the two user IDs (enforced in `routes/dm.py:11`)
- This ensures only one conversation record exists per user pair
- Created on-demand via `get_or_create_conversation()` when a user initiates a DM
- Mutual-consent deletion: a conversation is fully deleted only when both `user1_delete_requested` and `user2_delete_requested` are set to `1`
- `user1_delete_requested` and `user2_delete_requested` were added via migration

---

### `mutes`
**Purpose:** Allows users to mute channels, conversations, or other users.

| Column | Type | Default | Constraints | Description |
|--------|------|---------|-------------|-------------|
| `id` | INTEGER | Auto | PRIMARY KEY AUTOINCREMENT | Unique mute record identifier |
| `user_id` | INTEGER | -- | NOT NULL, REFERENCES users(id) | User who created the mute |
| `mute_type` | TEXT | -- | NOT NULL | Type of mute: `channel`, `dm`, or `user` |
| `target_id` | INTEGER | -- | NOT NULL | ID of the muted target (channel ID, conversation ID, or user ID) |
| `created_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | -- | When the mute was created |

**Constraints:** `UNIQUE(user_id, mute_type, target_id)`

**Key behaviors:**
- Muted channels/DMs don't trigger unread badges in the sidebar
- Mute state is fetched via `GET /api/v1/mutes` and cached client-side
- Toggle is handled via `POST /api/v1/mute` and `POST /api/v1/unmute`

---

### `dm_messages`
**Purpose:** Messages within direct message conversations.

| Column | Type | Default | Constraints | Description |
|--------|------|---------|-------------|-------------|
| `id` | INTEGER | Auto | PRIMARY KEY AUTOINCREMENT | Unique message identifier |
| `conversation_id` | INTEGER | -- | NOT NULL, REFERENCES dm_conversations(id) | Conversation this message belongs to |
| `sender_id` | INTEGER | -- | NOT NULL, REFERENCES users(id) | User who sent the message |
| `content` | TEXT | `''` | NOT NULL | Message text content |
| `attachment_id` | INTEGER | NULL | REFERENCES files(id) | Optional file attachment |
| `is_deleted` | INTEGER | `0` | -- | Soft-delete flag; deleted messages are hidden but kept in the DB |
| `created_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | -- | When the message was sent |

**Key behaviors:**
- Structured identically to channel messages but without encryption/signature fields
- Queried with `ORDER BY created_at ASC`
- Access controlled: only participants of the conversation can read/write messages
- `is_deleted` was added via migration; soft-deleted messages are excluded with `WHERE is_deleted = 0`

---

## Migrations

The `_migrate_db()` function in `database.py:31-53` handles schema evolution. It uses `PRAGMA table_info()` to check for missing columns and adds them via `ALTER TABLE`.

This approach runs on every startup, making it safe to run the application against an older database file.

| Migration | Column Added | To Table | Default |
|-----------|-------------|----------|---------|
| 1 | `attachment_id` | `messages` | NULL |
| 2 | `must_change_password` | `users` | 0 |
| 3 | `last_activity` | `users` | NULL |
| 4 | `legacy_password_hash` | `users` | NULL |
| 5 | `conversation_id` | `files` | NULL |
| 6 | `is_deleted` | `messages` | 0 |
| 7 | `is_deleted` | `dm_messages` | 0 |
| 8 | `user1_delete_requested` | `dm_conversations` | 0 |
| 9 | `user2_delete_requested` | `dm_conversations` | 0 |
| 10 | `status` | `password_resets` | 'pending' |
| 11 | `reviewed_by` | `password_resets` | NULL |
| 12 | `reviewed_at` | `password_resets` | NULL |

**Special migration behavior:** When `status` is added to `password_resets`, all existing rows are marked as `'legacy'` to prevent them from appearing as pending requests. When `conversation_id` is added to `files`, the migration backfills values by joining against `dm_messages`.

---

## Database Connection Management

Connections are managed per-request using Flask's `g` object (`database.py:8-19`):

```python
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE_PATH'])
        g.db.row_factory = sqlite3.Row    # Enables dict-like access
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()
```

- `get_db()` creates a connection lazily on first call per request
- `sqlite3.Row` row factory enables accessing columns by name (e.g., `row['username']`)
- Foreign keys are enabled per-connection (SQLite requires this)
- `close_db()` is registered as a teardown function via `app.teardown_appcontext(close_db)`
