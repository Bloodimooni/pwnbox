
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

## WIKI

[Full Documentation](documentation/README.md)

## Vulnerability Areas

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
