# PwnBox Documentation

This directory contains technical documentation for the PwnBox CTF platform.

---

## Table of Contents

### Setup and Operation
- [Getting Started](getting-started.md) — Host setup, configuration, and launching all components.
- [Infrastructure](infrastructure.md) — Portal, scaler, instance manager, and NetBird integration.

### Application Reference
- [Architecture Overview](architecture.md) — System design, project structure, and request lifecycle.
- [Configuration and Deployment](configuration.md) — Configuration classes, environment variables, and Docker setup.

### Core Systems
- [Authentication and Authorization](authentication.md) — Login, registration, sessions, and audit logging.
- [Chat System](chat-system.md) — Channel messaging, real-time polling, and channel management.
- [Direct Messaging](direct-messaging.md) — One-to-one conversations and conversation lifecycle.
- [File Management](file-management.md) — Upload, download, storage, and allowed file types.
- [Search and Profiles](search-and-profiles.md) — Global search and user profile management.
- [Admin Panel](admin-panel.md) — User management, settings, logs, and backups.

### API and Frontend
- [REST API Reference](api-reference.md) — All `/api/v1` endpoints with request and response examples.
- [Frontend JavaScript](frontend.md) — Breakdown of `chat.js`, `dm.js`, `admin.js`, and inline scripts.
- [Templates](templates.md) — Jinja2 template hierarchy and page-specific behaviour.

### Data Layer
- [Database Schema](database-schema.md) — Tables, columns, constraints, relationships, and migrations.

---

## Quick Reference

### Service URLs

| Service | Default URL |
|---------|-------------|
| CorpChat application | `http://localhost:8080` |
| CTF player portal | `http://localhost:8888` |
| Operator scaler | `http://localhost:8889` |
| CorpChat admin panel | `http://<instance-ip>:8080/admin` |
| CorpChat REST API | `http://<instance-ip>:8080/api/v1` |

### Default Accounts

| Role | Username | Password |
|------|----------|----------|
| Regular user | `demo` | `demo123` |
| Administrator | `admin` | `admin2026!` |
| Bot | `chatbot` | `bot12345` |

### Run Script Commands

| Command | Purpose |
|---------|---------|
| `./setup-host.sh` | One-time host environment setup |
| `./run.sh portal` | Start the CTF player portal |
| `./run.sh scale` | Start the operator scaler |
| `./run.sh app` | Run CorpChat standalone in Docker |
| `./run.sh compose` | Run via Docker Compose |
| `./run.sh build` | Build or rebuild the Docker image |

---

## Project Structure

```
pwnbox/
├── app.py                       # Flask application factory
├── config.py                    # Configuration classes
├── database.py                  # Database initialisation and migrations
├── schema.sql                   # SQLite table definitions
├── requirements.txt             # Python dependencies
├── entrypoint.py                # Container startup script
├── run.sh                       # Unified runner for all components
├── setup-host.sh                # One-time host environment setup
├── docker/
│   ├── Dockerfile               # Container image definition
│   └── docker-compose.yml       # Single-instance development stack
├── infra/
│   ├── config.ini               # Infrastructure configuration
│   ├── portal.py                # CTF self-service portal
│   ├── scaler.py                # Operator instance scaler
│   ├── pwnbox-manager.py        # Instance lifecycle CLI
│   ├── flags.json               # Flag definitions
│   └── templates/               # Portal and scaler HTML templates
├── reversing-challenge/
│   └── admin-tools.c            # Source for the compiled challenge binary
├── routes/                      # Flask route blueprints
├── templates/                   # Jinja2 application templates
├── static/                      # CSS and JavaScript assets
└── documentation/               # This documentation directory
```

---

## Navigation Guide

- **New to the project?** Begin with [Getting Started](getting-started.md), then [Infrastructure](infrastructure.md).
- **Running a CTF event?** See [Infrastructure](infrastructure.md) for portal and scaler operation.
- **Working on the application backend?** Read [Authentication](authentication.md) first, then the relevant route module.
- **Working on the frontend?** See [Frontend JavaScript](frontend.md) and [Templates](templates.md).
- **Integrating with the API?** The [REST API Reference](api-reference.md) covers all endpoints.
- **Database questions?** See [Database Schema](database-schema.md).
