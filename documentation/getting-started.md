# Getting Started

[Back to Index](README.md)

---

## Prerequisites

- **Python 3.11+** (for local development)
- **pip** (Python package manager)
- **Docker** and **Docker Compose** (for containerized deployment)

---

## Installation

### Option 1: Docker (Recommended)

The simplest way to run PwnBox is with Docker Compose:

```bash
docker-compose up --build
```

This will:
1. Build a Docker image from the `Dockerfile` (based on `python:3.11-slim`)
2. Install dependencies from `requirements.txt`
3. Create data directories at `/data/uploads`, `/data/backups`, `/data/logs`
4. Start the Flask server on port 5000
5. Mount a persistent Docker volume (`corpchat-data`) at `/data`

The application will be available at **http://localhost:5000**.

### Option 2: Local Development

```bash
# Clone the repository
git clone <repo-url>
cd pwnbox

# Install Python dependencies
pip install -r requirements.txt

# Run the application
python3 app.py
```

The app will start on **http://0.0.0.0:5000** in development mode (debug enabled).

---

## First-Run Behavior

On first startup, when the database is empty, the application automatically:

### 1. Creates Database Tables
The `init_db()` function (`database.py:22-28`) reads and executes `schema.sql`, which creates all 12 tables using `CREATE TABLE IF NOT EXISTS`.

### 2. Runs Migrations
The `_migrate_db()` function (`database.py:31-53`) checks for missing columns and adds them via `ALTER TABLE`:
- `messages.attachment_id` -- foreign key to `files`
- `users.must_change_password` -- flag for forced password change
- `users.last_activity` -- timestamp for online status
- `password_resets.status` -- request state tracking (`pending`, `approved`, `denied`)
- `password_resets.reviewed_by` -- admin who reviewed the request
- `password_resets.reviewed_at` -- timestamp of review

### 3. Seeds Default Data
The `_seed_data()` function (`database.py:56-132`) runs only when the `users` table is empty. It creates:

**Admin User** (for the admin portal at `/admin`):
| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | `admin2026!` |
| Privilege Level | `superadmin` |

**Regular Users:**

| Username | Password | Display Name | Email | Purpose |
|----------|----------|-------------|-------|---------|
| `demo` | `demo123` | Demo User | demo@corpchat.local | Testing account |
| `chatbot` | `bot12345` | CorpChat Bot | bot@corpchat.local | Automated assistant |

**Default Channels:**

| Name | Description |
|------|-------------|
| `general` | General discussion for the team |
| `announcements` | Important announcements |
| `random` | Off-topic chat and fun stuff |

**Seed Messages** (in `#general` and `#announcements`):
- "Welcome to CorpChat! This is the general channel." (demo user)
- "Hello everyone! The new chat system is live." (chatbot)
- "Feel free to explore the channels and features." (demo user)
- "System maintenance scheduled for this weekend. Please save your work." (chatbot, in #announcements)

**Default System Settings:**

| Key | Value |
|-----|-------|
| `site_name` | CorpChat |
| `allow_registration` | true |
| `max_upload_size_mb` | 10 |
| `debug_mode` | false |
| `backup_enabled` | true |
| `backup_path` | /data/backups |
| `session_timeout_minutes` | 60 |
| `motd` | Welcome to CorpChat - Your secure corporate messaging platform |

---

## Dependencies

The application has minimal dependencies, defined in `requirements.txt`:

```
Flask==3.0.0
Werkzeug==3.0.1
```

- **Flask 3.0.0** -- The web framework. Provides routing, templates (Jinja2), sessions, request handling, and blueprint support.
- **Werkzeug 3.0.1** -- Flask's underlying WSGI toolkit. Used directly for password hashing (`generate_password_hash`, `check_password_hash`) and file serving (`send_from_directory`).

All other functionality (SQLite, UUID generation, JSON, file I/O, HMAC) uses Python's standard library.

---

## Directory Structure After First Run

```
pwnbox/
├── data/
│   ├── corpchat.db          # SQLite database (created automatically)
│   └── backups/             # Database backups (created via admin panel)
├── uploads/                  # Uploaded files stored here
├── logs/                     # Application log directory
└── ... (source files)
```

---

## Accessing the Application

### Regular User Login
1. Go to `http://localhost:5000` (redirects to `/login`)
2. Log in with `demo` / `demo123`
3. You'll be taken to the `#general` channel

### Admin Panel
1. Go to `http://localhost:5000/admin`
2. Log in with `admin` / `admin2026!`
3. You'll see the admin dashboard with statistics and pending actions

### Creating a New User
1. Go to `http://localhost:5000/register`
2. Fill in username (min 3 chars), email (must contain `@`), password (min 6 chars), and optional display name
3. After registration, log in with your new credentials

---

## Environment Variables

The application can be configured via environment variables:

| Variable | Default (Dev) | Default (Prod) | Description |
|----------|---------------|----------------|-------------|
| `FLASK_CONFIG` | `config.DevelopmentConfig` | `config.ProductionConfig` | Which config class to load |
| `SECRET_KEY` | `corpchat-secret-key-change-me` | Same | Flask session signing key |
| `DATABASE_DIR` | `./data` | `/data` | Directory for the SQLite database |
| `UPLOAD_FOLDER` | `./uploads` | `/data/uploads` | Where uploaded files are stored |
| `LOG_DIR` | `./logs` | `/data/logs` | Log file directory |
| `BACKUP_DIR` | `./data/backups` | `/data/backups` | Database backup directory |
| `CRYPTO_KEY` | `hmac-signing-key-placeholder` | Same | HMAC signing key for crypto endpoints |

See [Configuration & Deployment](configuration.md) for full details.
