
## Quick Start

```bash
docker-compose up --build
```

Open http://localhost:5000

Or run locally without Docker:

```bash
pip install -r requirements.txt
python3 app.py
```

## Default Accounts

| Role | Username | Password |
|------|----------|----------|
| User | demo | demo123 |
| Admin | admin | admin2026! |

Admin portal lives at `/admin`.

## What the App Does

- **Chat** with channels, real-time message polling, channel creation
- **User profiles** with bio and avatar
- **File sharing** with upload/download
- **Search** across messages and users
- **Admin dashboard** with user management, settings, logs, backups
- **REST API** at `/api/v1` with token auth and crypto endpoints

## Project Structure

```
app.py              Main app (Flask application factory)
config.py           App configuration
database.py         SQLite setup and seed data
schema.sql          Database tables
routes/
  auth.py           Login, register, logout, password reset
  chat.py           Channels and chat page
  profile.py        User profiles
  files.py          File upload/download
  search.py         Search
  admin.py          Admin panel
  api.py            REST API + crypto stubs
templates/          Jinja2 HTML templates
static/             CSS and JS
Dockerfile          Container build
docker-compose.yml  One-command deployment
```

## Vulnerability Areas

Each team member owns one category and works in the corresponding files.

| Category | Files to Modify |
|----------|----------------|
| Misconfiguration | `config.py`, `routes/admin.py`, `docker-compose.yml` |
| Authentication | `routes/auth.py` |
| Web Security (XSS) | `templates/chat/chat.html`, profile/search templates |
| Weak Crypto | `routes/api.py` (crypto endpoints, tokens) |
| API / Binary | `routes/api.py`, add helper binary |
| Networking / RE | `docker-compose.yml`, add services/binaries |

Flags follow the format `CTF{...}`.

## Tech Stack

- Python 3.11 + Flask
- SQLite
- Vanilla JS (AJAX polling for chat)
- Docker Compose
