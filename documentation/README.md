# PwnBox Documentation

This directory contains technical documentation for the PwnBox CTF platform.

---

## Table of Contents

### Setup and Operation
- [Getting Started](getting-started.md) — Host setup, configuration, and launching all components.
- [Infrastructure](infrastructure.md) — Portal, scaler, instance manager, and NetBird integration.

### Application Reference
- [Architecture Overview](architecture.md) — System design, project structure, and request lifecycle.
- [Configuration and Deployment](configuration.md) — Configuration classes, environment variables, Docker image build, and docker-compose stack.
- [XSS Bot](xss-bot.md) — Puppeteer bot design, cookie encryption, XSS exploitation, and Docker Compose integration.

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

### CTF Challenges
- [CTF Challenges](ctf-challenges.md) — Overview of all five flags, categories, and intended attack paths.
- [Full Walkthrough](writeup/ctf-walkthrough.md) — Step-by-step solution for every flag.
- [Git Challenge Writeup](writeup/git-challenge-writeup.md) — Exposed `.git` repository (Flag 1).
- [IDOR / Token Bypass Writeup](writeup/idor-challenge-writeup.md) — SQL injection, IDOR, and DM access (Flag 2).
- [Crypto Challenge Writeup](writeup/crypto-challenge-writeup.md) — MD5(base64) hash cracking (Flag 3).
- [Reverse Engineering Writeup](writeup/re-challenge-writeup.md) — XOR-encoded binary backdoor (Flag 4).
- [Privilege Escalation Writeup](writeup/privesc-challenge-writeup.md) — Wildcard tar cron exploit (Flag 5).

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

| Role | Username | Password | Notes |
|------|----------|----------|-------|
| Regular user | `demo` | `demo123` | General-purpose test account |
| Administrator | `admin` | `admin2026!` | Admin panel at `/admin` |
| XSS bot | `compliancebot` | `C0mpl1anceB0t2026` | Puppeteer bot; carries flag cookie |
| SSH service account | `svc_backup` | `netterFeger69#` | Discoverable via binary reversing |

### Run Script Commands

| Command | Purpose |
|---------|---------|
| `./setup-host.sh` | One-time host environment setup |
| `./run.sh portal` | Start the CTF player portal |
| `./run.sh scale` | Start the operator scaler |
| `./run.sh app` | Run CorpChat standalone in Docker |
| `./run.sh app --netbird` | Run standalone with NetBird VPN |
| `./run.sh compose` | Run via Docker Compose (includes XSS bot) |
| `./run.sh build` | Build or rebuild the Docker image |

---

## Project Structure

```
pwnbox/
├── app.py                       # Flask application factory
├── config.py                    # Configuration classes
├── database.py                  # Database initialisation, migrations, and seed data
├── schema.sql                   # SQLite table definitions
├── requirements.txt             # Python dependencies
├── entrypoint.py                # Container startup: NetBird, SSH, cron, challenge setup
├── run.sh                       # Unified runner for all components
├── setup-host.sh                # One-time host environment setup
├── ctfrepo.sh                   # Builds the fake exposed git repository for Flag 1
├── docker/
│   ├── Dockerfile               # Container image definition (compiles corpchat-admin)
│   └── docker-compose.yml       # Single-instance development stack with XSS bot
├── infra/
│   ├── config.ini               # Infrastructure configuration
│   ├── portal.py                # CTF self-service portal
│   ├── scaler.py                # Operator instance scaler
│   ├── pwnbox-manager.py        # Instance lifecycle CLI
│   ├── flags.json               # Flag strings (5 total)
│   └── templates/               # Portal and scaler HTML templates
├── bot/
│   ├── bot.js                   # Puppeteer XSS bot (logs in as compliancebot, visits all DMs)
│   ├── dockerfile               # Node.js + Chromium image for the bot
│   └── package.json             # Bot dependencies
├── reversing-challenge/
│   ├── admin-tools.c            # Source for the compiled challenge binary
│   ├── corpchat-admin           # Compiled binary (seeded into /data/uploads/tools/)
│   └── xor_encode.c             # XOR encoding utility used to produce the encoded arrays
├── routes/                      # Flask route blueprints
├── templates/                   # Jinja2 application templates
├── static/
│   ├── css/                     # Stylesheets
│   ├── js/                      # JavaScript (chat.js, dm.js, admin.js)
│   └── challenge/               # Exposed git repository for Flag 1 (.git directory inside)
└── documentation/               # This documentation directory
    └── writeup/                 # Per-challenge writeups and the full walkthrough
```

---

## Navigation Guide

- **New to the project?** Begin with [Getting Started](getting-started.md), then [Infrastructure](infrastructure.md).
- **Running a CTF event?** See [Infrastructure](infrastructure.md) for portal and scaler operation.
- **Working on the application backend?** Read [Authentication](authentication.md) first, then the relevant route module.
- **Working on the frontend?** See [Frontend JavaScript](frontend.md) and [Templates](templates.md).
- **Integrating with the API?** The [REST API Reference](api-reference.md) covers all endpoints.
- **Database questions?** See [Database Schema](database-schema.md).
- **Understanding Docker / the image build?** See [Configuration and Deployment](configuration.md).
- **Understanding the XSS bot?** See [XSS Bot](xss-bot.md).
- **Solving the CTF?** See [CTF Challenges](ctf-challenges.md) for an overview, or jump straight to the [Full Walkthrough](writeup/ctf-walkthrough.md).
- **Setting challenge flags or editing challenge content?** See `infra/flags.json`, `database.py` (`_seed_data`), and `entrypoint.py` (`setup_challenge`).
