# PwnBox Documentation Wiki

Welcome to the comprehensive documentation for **PwnBox** (internally codenamed **CorpChat**) -- a Capture The Flag (CTF) web application built as a corporate messaging platform. This wiki explains every aspect of the codebase in detail.

---

## Table of Contents

### Getting Started
- [Getting Started](getting-started.md) -- How to install, configure, and run the application locally or with Docker.

### Architecture & Design
- [Architecture Overview](architecture.md) -- High-level system design, project structure, tech stack, and request lifecycle.
- [Configuration & Deployment](configuration.md) -- All configuration classes, environment variables, Docker setup, and deployment details.

### Core Systems
- [Authentication & Authorization](authentication.md) -- Login, registration, sessions, password resets, decorators, and audit logging.
- [Chat System](chat-system.md) -- Channel-based messaging, real-time polling, message creation, and channel management.
- [Direct Messaging](direct-messaging.md) -- 1-to-1 conversations, conversation lifecycle, and DM-specific behavior.
- [File Management](file-management.md) -- File uploads, downloads, viewing, deletion, storage strategy, and allowed types.
- [Search & Profiles](search-and-profiles.md) -- Global search functionality and user profile viewing/editing.
- [Admin Panel](admin-panel.md) -- Admin dashboard, user management, password reset approval, settings, logs, backups, and debug endpoint.

### API & Frontend
- [REST API Reference](api-reference.md) -- Complete documentation of every `/api/v1` endpoint with request/response examples.
- [Frontend JavaScript](frontend.md) -- Detailed breakdown of `chat.js`, `dm.js`, `admin.js`, and the base template's inline JavaScript.
- [Templates](templates.md) -- Every Jinja2 template explained: layout hierarchy, blocks, and page-specific behavior.

### Data Layer
- [Database Schema](database-schema.md) -- Every table, column, type, constraint, relationship, migration logic, and seed data.

---

## Quick Reference

| Resource | URL |
|----------|-----|
| Application | `http://localhost:5000` |
| Admin Panel | `http://localhost:5000/admin` |
| REST API Base | `http://localhost:5000/api/v1` |
| Health Check | `http://localhost:5000/api/v1/health` |

### Default Accounts

| Role | Username | Password | Purpose |
|------|----------|----------|---------|
| Regular User | `demo` | `demo123` | Demo/testing account |
| Admin | `admin` | `admin2026!` | Admin portal access |
| Bot | `chatbot` | `bot12345` | Automated assistant account |

### Tech Stack Summary

| Component | Technology |
|-----------|------------|
| Backend | Python 3.11 + Flask 3.0.0 |
| Database | SQLite3 (via `sqlite3` stdlib) |
| Passwords | Werkzeug 3.0.1 (`generate_password_hash` / `check_password_hash`) |
| Frontend | Vanilla JavaScript, HTML5, Jinja2 templates |
| Styling | Custom CSS (Discord/Slack-inspired dark theme) |
| Containerization | Docker + Docker Compose |

---

## Project Structure at a Glance

```
pwnbox/
├── app.py                    # Flask application factory
├── config.py                 # Configuration classes (Dev/Prod)
├── database.py               # SQLite init, migrations, seed data
├── schema.sql                # Database table definitions
├── requirements.txt          # Python dependencies
├── Dockerfile                # Container build instructions
├── docker-compose.yml        # One-command deployment
├── routes/                   # All route blueprints
│   ├── __init__.py
│   ├── auth.py               # Authentication & authorization
│   ├── chat.py               # Channel chat
│   ├── dm.py                 # Direct messaging
│   ├── profile.py            # User profiles
│   ├── files.py              # File upload/download
│   ├── search.py             # Search
│   ├── admin.py              # Admin panel
│   └── api.py                # REST API v1
├── templates/                # Jinja2 HTML templates
│   ├── base.html
│   ├── auth/
│   ├── chat/
│   ├── dm/
│   ├── profile/
│   ├── files/
│   ├── search/
│   └── admin/
├── static/                   # Static assets
│   ├── css/
│   │   ├── main.css
│   │   └── admin.css
│   └── js/
│       ├── chat.js
│       ├── dm.js
│       └── admin.js
├── data/                     # Runtime data
│   ├── corpchat.db
│   └── backups/
├── uploads/                  # User-uploaded files
└── logs/                     # Application logs
```

---

## How to Navigate This Wiki

- **New to the project?** Start with [Getting Started](getting-started.md) and then [Architecture Overview](architecture.md).
- **Working on the backend?** Read [Authentication](authentication.md) first, then the specific route module you need.
- **Working on the frontend?** See [Frontend JavaScript](frontend.md) and [Templates](templates.md).
- **Building an integration?** The [REST API Reference](api-reference.md) has everything you need.
- **Database questions?** See [Database Schema](database-schema.md).
