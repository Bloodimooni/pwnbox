# Architecture Overview

[Back to Index](README.md)

---

## High-Level Architecture

PwnBox follows a classic **server-rendered monolith** architecture with **AJAX-powered real-time features**. It is a Flask web application that uses SQLite for persistence and vanilla JavaScript for client-side interactivity.

```
┌─────────────────────────────────────────────────────────┐
│                      Browser Client                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Jinja2 HTML │  │  chat.js     │  │  dm.js       │  │
│  │  (SSR pages) │  │  (AJAX poll) │  │  (AJAX poll) │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
└─────────┼─────────────────┼─────────────────┼───────────┘
          │ Page requests   │ JSON API        │ JSON API
          │ (GET/POST)      │ polling         │ polling
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────┐
│                    Flask Application                     │
│                                                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────────┐ │
│  │ auth_bp │ │ chat_bp │ │ dm_bp   │ │  api_bp      │ │
│  │ /login  │ │ /chat   │ │ /dm     │ │  /api/v1     │ │
│  │ /register│ │         │ │         │ │  (JSON API)  │ │
│  └────┬────┘ └────┬────┘ └────┬────┘ └──────┬───────┘ │
│       │           │           │              │         │
│  ┌────┴───────────┴───────────┴──────────────┴───────┐ │
│  │              SQLite Database (corpchat.db)          │ │
│  └────────────────────────────────────────────────────┘ │
│                                                         │
│  ┌────────────────┐  ┌────────────────────────────────┐ │
│  │  files_bp      │  │  admin_bp                      │ │
│  │  /files        │  │  /admin (separate auth system) │ │
│  └────────────────┘  └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Application Factory Pattern

The application uses Flask's **application factory pattern** (`app.py:6-73`). The `create_app()` function:

1. **Creates the Flask instance** and loads config based on the `FLASK_CONFIG` environment variable (defaults to `config.DevelopmentConfig`).
2. **Ensures runtime directories exist** -- iterates over `DATABASE_DIR`, `UPLOAD_FOLDER`, `LOG_DIR`, and `BACKUP_DIR`, creating them with `os.makedirs(exist_ok=True)`.
3. **Registers the database teardown** via `app.teardown_appcontext(close_db)` so connections are closed after each request.
4. **Initializes the database** by calling `init_db()` within an app context, which runs `schema.sql`, applies migrations, and seeds default data.
5. **Registers all 8 blueprints** with their URL prefixes.
6. **Registers a `before_request` hook** (`update_user_activity`) that updates the `last_activity` timestamp for logged-in users on every request.
7. **Defines the root route** (`/`) which redirects to `/chat` if logged in, or `/login` if not.

### Blueprint Registration

| Blueprint | Variable | URL Prefix | Source File |
|-----------|----------|------------|-------------|
| Authentication | `auth_bp` | `/` (no prefix) | `routes/auth.py` |
| Chat | `chat_bp` | `/chat` | `routes/chat.py` |
| Direct Messages | `dm_bp` | `/dm` | `routes/dm.py` |
| Profile | `profile_bp` | `/profile` | `routes/profile.py` |
| Files | `files_bp` | `/files` | `routes/files.py` |
| Search | `search_bp` | `/search` | `routes/search.py` |
| Admin | `admin_bp` | `/admin` | `routes/admin.py` |
| REST API | `api_bp` | `/api/v1` | `routes/api.py` |

---

## Request Lifecycle

### 1. Standard Page Request (e.g., visiting `/chat`)

```
Browser GET /chat
    │
    ▼
Flask Router → chat_bp.index()
    │
    ├── @login_required checks session['user_id']
    │       └── If missing → redirect to /login
    │
    ├── before_request: update_user_activity()
    │       └── UPDATE users SET last_activity = NOW
    │
    ├── Handler queries DB for channels and messages
    │
    ├── render_template('chat/chat.html', ...)
    │       └── Extends base.html (sidebar, topbar, flash messages)
    │
    └── Returns HTML response
```

### 2. AJAX Polling Request (e.g., fetching new messages)

```
chat.js → fetch('/api/v1/channels/1/messages?since=42')
    │
    ▼
Flask Router → api_bp.get_messages(channel_id=1)
    │
    ├── @api_auth_required checks:
    │       1. X-API-Token header → looks up user by api_token
    │       2. Fallback: session['user_id'] → looks up user by ID
    │       └── If neither → return 401 JSON
    │
    ├── Queries messages WHERE id > 42 AND channel_id = 1
    │
    └── Returns JSON: {"data": [...messages...]}
```

### 3. Admin Request (e.g., visiting `/admin/dashboard`)

```
Browser GET /admin/dashboard
    │
    ▼
Flask Router → admin_bp.dashboard()
    │
    ├── @admin_required checks session['admin_id']
    │       └── If missing → redirect to /admin/login
    │
    ├── before_request: load_pending_reset_count()
    │       └── Counts pending password reset requests → g.pending_reset_count
    │
    ├── Queries stats, pending resets, recent logs
    │
    └── render_template('admin/dashboard.html', ...)
            └── Extends admin/base_admin.html (admin sidebar)
```

---

## Dual Authentication System

The application maintains **two completely separate authentication systems**:

### Regular Users
- Stored in the `users` table
- Authenticated via `session['user_id']`
- Protected by the `@login_required` decorator (`routes/auth.py:11-19`)
- Sessions contain: `user_id`, `username`, `display_name`, `must_change_password`

### Admin Users
- Stored in the `admin_users` table (completely separate table)
- Authenticated via `session['admin_id']`
- Protected by the `@admin_required` decorator (`routes/auth.py:22-28`)
- Sessions contain: `admin_id`, `admin_username`
- Have their own login page at `/admin/login`

Both session types can coexist -- a user can be logged in as both a regular user and an admin simultaneously.

---

## Data Flow: Chat Messages

This diagram shows how a message flows through the system:

```
1. User types message + presses Enter
       │
       ▼
2. chat.js sendMessage()
   POST /api/v1/channels/{id}/messages
   Body: {"content": "Hello!", "attachment_id": null}
       │
       ▼
3. api_bp.send_message()
   ├── Validates channel exists
   ├── Validates content or attachment present
   ├── INSERT INTO messages (channel_id, user_id, content, attachment_id)
   ├── SELECT the new message with user + file JOINs
   └── Return JSON: {"data": {id, content, user_id, username, ...}}
       │
       ▼
4. chat.js receives response
   ├── Calls appendMessage(msg) → creates DOM element
   ├── Updates lastMessageId
   ├── Updates localStorage (unread tracking)
   └── Scrolls to bottom

5. Other users' browsers (every 3 seconds):
   GET /api/v1/channels/{id}/messages?since={lastId}
       │
       ▼
   Returns new messages → appendMessage() for each
```

---

## Data Flow: File Attachments

```
1. User clicks attach button → selects image
       │
       ▼
2. chat.js file input change handler
   ├── Shows local preview (FileReader → data URL)
   ├── POST /api/v1/channels/{id}/upload (FormData with file)
       │
       ▼
3. api_bp.upload_attachment()
   ├── Validates file extension against ALLOWED_EXTENSIONS
   ├── Generates UUID-based stored_filename
   ├── Saves to UPLOAD_FOLDER
   ├── INSERT INTO files (filename, stored_filename, ...)
   └── Returns: {"data": {"id": 7, "filename": "photo.png", ...}}
       │
       ▼
4. chat.js sets pendingAttachmentId = 7
5. User sends message → POST includes attachment_id: 7
6. Message rendered with <img src="/files/view/7">
```

---

## In-Memory State

The application maintains two pieces of **in-memory state** (not persisted to the database):

### Typing Indicators (`routes/api.py:17-20`)

```python
_typing_status = {}       # {channel_id: {user_id: {'username': str, 'timestamp': float}}}
_dm_typing_status = {}    # {conversation_id: {user_id: {'username': str, 'timestamp': float}}}
```

- **Set** when a user sends a `POST /api/v1/channels/{id}/typing` request
- **Expired** when entries are older than 4 seconds (cleaned up on read)
- **Lost** on server restart (ephemeral by design)

---

## Key Design Decisions

1. **AJAX Polling over WebSockets**: The app uses 3-second interval polling (`setInterval`) rather than WebSockets for real-time messaging. This simplifies the server but adds latency.

2. **Separate Admin Auth**: Admin users have their own table and session keys, allowing a clean separation from regular user authentication.

3. **UUID File Storage**: Uploaded files are renamed to `{uuid}.{ext}` on disk, preventing filename collisions and path traversal.

4. **localStorage for Unread Tracking**: Unread message state is tracked entirely client-side using `localStorage`, avoiding additional server-side state.

5. **Server-Side Rendering + API**: Pages are server-rendered with Jinja2 for initial load, then JavaScript takes over for real-time updates via the JSON API.

6. **Single-File SQLite**: The entire database is a single `.db` file, making backups trivial (just copy the file).
