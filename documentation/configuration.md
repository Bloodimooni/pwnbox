# Configuration & Deployment

[Back to Index](README.md)

---

## Overview

PwnBox uses a class-based configuration system (`config.py`) with environment variable overrides. It can be deployed locally for development or via Docker for production.

---

## Source File: `config.py` (34 lines)

### `BaseConfig` (lines 6-11)

The base configuration class inherited by both development and production configs.

| Setting | Default | Source | Description |
|---------|---------|--------|-------------|
| `SECRET_KEY` | `'corpchat-secret-key-change-me'` | `os.environ.get('SECRET_KEY', ...)` | Flask session signing key. Used to cryptographically sign session cookies. |
| `MAX_CONTENT_LENGTH` | `10485760` (10 MB) | Hardcoded | Maximum request body size. Flask rejects larger uploads with 413 error. |
| `ALLOWED_EXTENSIONS` | `{'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'doc', 'docx'}` | Hardcoded | File extensions permitted for upload. |
| `CRYPTO_SIGNING_KEY` | `'hmac-signing-key-placeholder'` | `os.environ.get('CRYPTO_KEY', ...)` | HMAC key used by the `/api/v1/crypto/sign` and `/api/v1/crypto/verify` endpoints. |
| `APP_VERSION` | `'1.0.0'` | Hardcoded | Application version string, returned by health check and debug endpoints. |

### `DevelopmentConfig` (lines 14-22)

Inherits `BaseConfig`. Used when running locally.

| Setting | Value | Source |
|---------|-------|--------|
| `DEBUG` | `True` | Hardcoded |
| `DATABASE_DIR` | `./data` | `os.environ.get('DATABASE_DIR', ...)` |
| `DATABASE_PATH` | `./data/corpchat.db` | Computed from `DATABASE_DIR` |
| `UPLOAD_FOLDER` | `./uploads` | `os.environ.get('UPLOAD_FOLDER', ...)` |
| `LOG_DIR` | `./logs` | `os.environ.get('LOG_DIR', ...)` |
| `BACKUP_DIR` | `./data/backups` | `os.environ.get('BACKUP_DIR', ...)` |

### `ProductionConfig` (lines 25-33)

Inherits `BaseConfig`. Used in Docker.

| Setting | Value | Source |
|---------|-------|--------|
| `DEBUG` | `False` | Hardcoded |
| `DATABASE_DIR` | `/data` | `os.environ.get('DATABASE_DIR', ...)` |
| `DATABASE_PATH` | `/data/corpchat.db` | Computed from `DATABASE_DIR` |
| `UPLOAD_FOLDER` | `/data/uploads` | `os.environ.get('UPLOAD_FOLDER', ...)` |
| `LOG_DIR` | `/data/logs` | `os.environ.get('LOG_DIR', ...)` |
| `BACKUP_DIR` | `/data/backups` | `os.environ.get('BACKUP_DIR', ...)` |

### Config Selection

In `app.py:10`:
```python
config_class = os.environ.get('FLASK_CONFIG', 'config.DevelopmentConfig')
app.config.from_object(config_class)
```

The `FLASK_CONFIG` environment variable determines which config class is loaded. Defaults to `DevelopmentConfig` for local development.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FLASK_CONFIG` | No | `config.DevelopmentConfig` | Config class to load |
| `SECRET_KEY` | No | `corpchat-secret-key-change-me` | Session signing secret |
| `DATABASE_DIR` | No | `./data` (dev) or `/data` (prod) | Directory containing the SQLite database |
| `UPLOAD_FOLDER` | No | `./uploads` (dev) or `/data/uploads` (prod) | File upload storage directory |
| `LOG_DIR` | No | `./logs` (dev) or `/data/logs` (prod) | Application log directory |
| `BACKUP_DIR` | No | `./data/backups` (dev) or `/data/backups` (prod) | Database backup directory |
| `CRYPTO_KEY` | No | `hmac-signing-key-placeholder` | HMAC signing key for crypto endpoints |

---

## Directory Auto-Creation

On startup, `app.py:19-26` ensures all required directories exist:

```python
for dir_key in ('DATABASE_DIR', 'UPLOAD_FOLDER', 'LOG_DIR'):
    dir_path = app.config.get(dir_key)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

backup_dir = app.config.get('BACKUP_DIR')
if backup_dir:
    os.makedirs(backup_dir, exist_ok=True)
```

This means you never need to manually create the `data/`, `uploads/`, `logs/`, or `data/backups/` directories.

---

## Docker Deployment

### Dockerfile (21 lines)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/uploads /data/backups /data/logs

EXPOSE 5000

ENV FLASK_CONFIG=config.ProductionConfig
ENV SECRET_KEY=corpchat-default-secret
ENV DATABASE_DIR=/data
ENV UPLOAD_FOLDER=/data/uploads
ENV LOG_DIR=/data/logs

CMD ["python", "app.py"]
```

**Build process:**
1. Uses `python:3.11-slim` as the base image (minimal Debian with Python)
2. Copies and installs Python dependencies first (for Docker layer caching)
3. Copies the entire application
4. Creates data directories under `/data`
5. Sets production environment variables
6. Exposes port 5000
7. Runs the Flask development server via `python app.py`

**Note:** The Dockerfile sets `SECRET_KEY=corpchat-default-secret`, but the `docker-compose.yml` overrides this.

### docker-compose.yml (21 lines)

```yaml
version: '3.8'

services:
  corpchat:
    build: .
    container_name: corpchat-app
    ports:
      - "5000:5000"
    volumes:
      - corpchat-data:/data
    environment:
      - SECRET_KEY=corpchat-ctf-secret-key-2026
      - FLASK_CONFIG=config.ProductionConfig
      - DATABASE_DIR=/data
      - UPLOAD_FOLDER=/data/uploads
      - LOG_DIR=/data/logs
    restart: unless-stopped

volumes:
  corpchat-data:
```

**Key details:**

| Aspect | Value |
|--------|-------|
| Service name | `corpchat` |
| Container name | `corpchat-app` |
| Port mapping | `5000:5000` (host:container) |
| Data volume | Named volume `corpchat-data` mounted at `/data` |
| Secret key | `corpchat-ctf-secret-key-2026` |
| Config class | `config.ProductionConfig` |
| Restart policy | `unless-stopped` (auto-restart on crash, not on manual stop) |

**Volume persistence:** The `corpchat-data` named volume persists across container restarts and rebuilds. It stores:
- `corpchat.db` -- the SQLite database
- `uploads/` -- uploaded files
- `backups/` -- database backups
- `logs/` -- application logs

---

## Local Development

### Running Locally

```bash
pip install -r requirements.txt
python3 app.py
```

The server starts at `http://0.0.0.0:5000` with:
- `DevelopmentConfig` (debug mode enabled)
- Database at `./data/corpchat.db`
- Uploads at `./uploads/`
- Logs at `./logs/`

### Debug Mode

When `DEBUG = True` (development):
- Flask auto-reloads on code changes
- Detailed error pages are shown in the browser
- The debug endpoint at `/admin/debug` reports `"debug_mode": true`

When `DEBUG = False` (production):
- No auto-reload
- Generic error pages
- Better performance

---

## Application Entry Point: `app.py`

### `create_app()` (lines 6-73)

The Flask application factory. Called once at startup.

**Steps:**
1. Create Flask instance
2. Load configuration from `FLASK_CONFIG` env var
3. Ensure `DATABASE_PATH` is set (fallback logic for when `from_object` doesn't capture it)
4. Create runtime directories
5. Register `close_db` teardown
6. Initialize database (within app context)
7. Register all 8 blueprints
8. Register `before_request` hook for user activity tracking
9. Register root route (`/` → redirect to `/chat` or `/login`)

### `if __name__ == '__main__'` (lines 76-78)

```python
if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000)
```

Runs the Flask development server on all interfaces, port 5000.

**Note:** This uses Flask's built-in development server. For production, a WSGI server like Gunicorn would be recommended, but the current setup uses the dev server even in the Docker container.

---

## Dependencies

### `requirements.txt`

```
Flask==3.0.0
Werkzeug==3.0.1
```

**Flask 3.0.0** provides:
- Request routing and blueprints
- Jinja2 template engine
- Session management (signed cookies)
- Flash messages
- Static file serving
- `send_from_directory()` for file downloads

**Werkzeug 3.0.1** provides:
- `generate_password_hash()` -- creates bcrypt-style password hashes
- `check_password_hash()` -- verifies passwords against hashes
- WSGI utilities used internally by Flask

**Standard library modules used:**
| Module | Used For |
|--------|----------|
| `sqlite3` | Database connections and queries |
| `uuid` | API token generation, file naming |
| `json` | Audit log details serialization |
| `os` | File path operations, environment variables |
| `sys` | Python version info (debug endpoint) |
| `time` | Typing indicator timestamps |
| `shutil` | Database backup (file copy) |
| `mimetypes` | MIME type detection for uploads |
| `hashlib` | HMAC-SHA256 for crypto endpoints |
| `hmac` | Message signing/verification |
| `base64` | Crypto encrypt placeholder |
| `functools` | `@wraps` for decorators |
| `datetime` | Backup filename timestamps |

---

## System Settings vs. Config

The application has two configuration layers:

### 1. Python Config (`config.py`)
- Loaded at startup via `app.config.from_object()`
- Controls actual application behavior
- Changed via environment variables or code

### 2. Database Settings (`system_settings` table)
- Managed via the admin panel UI (`/admin/settings`)
- Stored in the database
- **Not read by the application at runtime** -- they exist as a UI feature but don't control behavior
- Default values: `site_name`, `allow_registration`, `max_upload_size_mb`, `debug_mode`, `backup_enabled`, `backup_path`, `session_timeout_minutes`, `motd`

This means changing settings in the admin panel does not affect how the application actually runs. The settings are a placeholder for potential future functionality.

---

## Backup System

Database backups are created via the admin panel:

1. Admin clicks "Create Backup" in the topbar
2. `POST /admin/backup` handler runs
3. `shutil.copy2()` copies the SQLite database file
4. Backup is named `corpchat_backup_{YYYYMMDD_HHMMSS}.db`
5. Stored in `BACKUP_DIR`

Backups are full copies of the SQLite database and can be restored by replacing the active database file.
