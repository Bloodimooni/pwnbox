# Configuration & Deployment

[Back to Index](README.md)

---

## Overview

PwnBox uses a class-based Python configuration system (`config.py`) with environment variable overrides. The Docker image is built from `docker/Dockerfile` and can be run standalone via `run.sh app` or as a full development stack (application + XSS bot) via `docker-compose.yml`.

---

## Python Configuration (`config.py`)

### Class Hierarchy

```
BaseConfig
├── DevelopmentConfig   (used for local development, DEBUG=True)
└── ProductionConfig    (used in Docker, DEBUG=False)
```

The active config class is selected by the `FLASK_CONFIG` environment variable:

```python
# app.py
config_class = os.environ.get('FLASK_CONFIG', 'config.DevelopmentConfig')
app.config.from_object(config_class)
```

---

### `BaseConfig`

Inherited by both Development and Production configs.

| Setting | Value | Source | Description |
|---------|-------|--------|-------------|
| `SECRET_KEY` | `rSJhjbPT3zuVzffVtb3XuvnrCv39CZq8` | `os.environ.get('SECRET_KEY', ...)` | Flask session signing key. Signs and verifies session cookies. Must be changed in production. |
| `MAX_CONTENT_LENGTH` | `10485760` (10 MB) | Hardcoded | Maximum request body size. Flask returns 413 for larger uploads. |
| `ALLOWED_EXTENSIONS` | See below | Hardcoded set | File extensions permitted for upload. |
| `CRYPTO_SIGNING_KEY` | `rSJhjbPT3zuVzffVtb3XuvnrCv39CZq8` | `os.environ.get('CRYPTO_KEY', ...)` | Key used by the `/api/v1/crypto/sign` and `/api/v1/crypto/verify` endpoints. |
| `APP_VERSION` | `'1.0.0'` | Hardcoded | Version string returned by health check and debug endpoints. |

**Allowed Extensions:**

```python
{
    'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'doc', 'docx',
    'mp4', 'mp3', 'webm', 'ogg', 'wav', 'mov', 'avi',
    'svg', 'webp', 'csv', 'json', 'xml', 'pptx', 'xlsx', 'sh', 'py'
}
```

Note that `sh` and `py` are intentionally allowed — players need to upload shell scripts for the privilege escalation stage.

---

### `DevelopmentConfig`

Used for local development (`python3 app.py`).

| Setting | Value | Source |
|---------|-------|--------|
| `DEBUG` | `True` | Hardcoded |
| `DATABASE_DIR` | `./data` | `os.environ.get('DATABASE_DIR', ...)` |
| `DATABASE_PATH` | `./data/corpchat.db` | Computed from `DATABASE_DIR` |
| `UPLOAD_FOLDER` | `./uploads` | `os.environ.get('UPLOAD_FOLDER', ...)` |
| `LOG_DIR` | `./logs` | `os.environ.get('LOG_DIR', ...)` |
| `BACKUP_DIR` | `./data/backups` | `os.environ.get('BACKUP_DIR', ...)` |

---

### `ProductionConfig`

Used inside Docker containers (`FLASK_CONFIG=config.ProductionConfig`).

| Setting | Value | Source |
|---------|-------|--------|
| `DEBUG` | `False` | Hardcoded |
| `DATABASE_DIR` | `/data` | `os.environ.get('DATABASE_DIR', ...)` |
| `DATABASE_PATH` | `/data/corpchat.db` | Computed from `DATABASE_DIR` |
| `UPLOAD_FOLDER` | `/data/uploads` | `os.environ.get('UPLOAD_FOLDER', ...)` |
| `LOG_DIR` | `/data/logs` | `os.environ.get('LOG_DIR', ...)` |
| `BACKUP_DIR` | `/data/backups` | `os.environ.get('BACKUP_DIR', ...)` |

---

## Environment Variables

All container environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FLASK_CONFIG` | No | `config.DevelopmentConfig` | Config class to load |
| `SECRET_KEY` | **Yes (prod)** | `corpchat-default-secret` | Session signing key; generate a unique value per instance |
| `DATABASE_DIR` | No | `/data` (prod) | Directory containing the SQLite database file |
| `UPLOAD_FOLDER` | No | `/data/uploads` (prod) | File upload storage |
| `LOG_DIR` | No | `/data/logs` (prod) | Application log directory |
| `NETBIRD_SETUP_KEY` | No | — | Setup key for NetBird VPN registration (set by pwnbox-manager) |
| `NETBIRD_MGMT_URL` | No | — | NetBird management server URL (set by pwnbox-manager) |

---

## Docker Image (`docker/Dockerfile`)

### Full Dockerfile

```dockerfile
FROM python:3.11-slim

ARG INSTALL_NETBIRD=false

WORKDIR /app

# System tools: GCC (to compile corpchat-admin), SQLite dev libs,
# sudo, curl (NetBird install), SSH server, cron
RUN apt-get update && \
    apt-get install -y gcc libsqlite3-dev sudo curl iproute2 openssh-server cron && \
    rm -rf /var/lib/apt/lists/*

# Optionally install NetBird VPN (needed for multi-instance CTF deployments)
RUN if [ "$INSTALL_NETBIRD" = "true" ]; then \
        curl -fsSL https://pkgs.netbird.io/install.sh | sh; \
    fi

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application source
COPY . .

# Compile the corpchat-admin binary (Stage 4 — reversing challenge)
# The sed command rewrites the hardcoded ./data/ path to /data/ for container use.
RUN mkdir -p /opt/corpchat && \
    sed 's|"./data/|"/data/|g' reversing-challenge/admin-tools.c | \
    gcc -x c - -o /opt/corpchat/corpchat-admin -lsqlite3 -O0 -no-pie && \
    chmod 755 /opt/corpchat/corpchat-admin

# Create runtime directories
RUN mkdir -p /data/uploads /data/uploads/tools /data/backups /data/logs /app/scripts

# Service account and permissions
# - corpchat: low-privilege account the Flask app runs as after privilege drop
# - /app: root-owned, group-readable by corpchat (read-only at runtime)
# - /data: fully owned by corpchat (app must write DB, logs, uploads)
# - /data/uploads and /data/uploads/tools: 777 (world-writable — intentional for CTF Stage 5)
RUN useradd -r -s /bin/false -M corpchat && \
    chown -R root:corpchat /app && \
    chmod -R g+rX,o-rwx /app && \
    chown -R corpchat:corpchat /data && \
    chmod 755 /data && \
    chmod 777 /data/uploads /data/uploads/tools

# SSH configuration — replaced with a clean authoritative config
# to prevent Debian package defaults from silently disabling password auth
RUN mkdir -p /var/run/sshd && \
    printf 'Port 22\nPasswordAuthentication yes\nPermitRootLogin no\nUsePAM yes\nLogLevel VERBOSE\nAcceptEnv LANG LC_*\nSubsystem sftp /usr/lib/openssh/sftp-server\n' \
        > /etc/ssh/sshd_config

EXPOSE 8080 22

ENV FLASK_CONFIG=config.ProductionConfig
ENV SECRET_KEY=corpchat-default-secret
ENV DATABASE_DIR=/data
ENV UPLOAD_FOLDER=/data/uploads
ENV LOG_DIR=/data/logs

CMD ["python", "/app/entrypoint.py"]
```

---

### Build Stages

The image is built in one stage but performs several distinct setup steps:

#### 1. System Packages

```
gcc libsqlite3-dev    → compiling corpchat-admin (C with SQLite)
sudo curl iproute2    → NetBird VPN tooling
openssh-server        → SSH daemon for player access (Stage 4 credentials)
cron                  → cron daemon for the backup job (Stage 5)
```

#### 2. NetBird (Conditional)

```dockerfile
ARG INSTALL_NETBIRD=false
RUN if [ "$INSTALL_NETBIRD" = "true" ]; then \
        curl -fsSL https://pkgs.netbird.io/install.sh | sh; \
    fi
```

NetBird is only installed when the build arg `INSTALL_NETBIRD=true` is passed. This keeps the development image smaller. The production multi-instance deployment always builds with NetBird:

```bash
./run.sh app --netbird     # passes --build-arg INSTALL_NETBIRD=true
./run.sh portal            # always builds with NetBird
```

#### 3. corpchat-admin Compilation

```dockerfile
RUN mkdir -p /opt/corpchat && \
    sed 's|"./data/|"/data/|g' reversing-challenge/admin-tools.c | \
    gcc -x c - -o /opt/corpchat/corpchat-admin -lsqlite3 -O0 -no-pie && \
    chmod 755 /opt/corpchat/corpchat-admin
```

The source `admin-tools.c` uses relative paths (`./data/`) which work for local development. The `sed` command rewrites them to `/data/` before compilation so the binary works inside the container. Key compiler flags:

| Flag | Effect |
|------|--------|
| `-O0` | Disable optimisations — preserves readable decompiled output in Ghidra |
| `-no-pie` | Disable position-independent executable — static addresses, easier to reverse |
| `-lsqlite3` | Link against the SQLite library (the binary can query the CorpChat database) |

The compiled binary is placed at `/opt/corpchat/corpchat-admin`. The `entrypoint.py` copies it to `/data/uploads/tools/corpchat-admin` at runtime so players can find and download it.

#### 4. Service Account and Permissions

```
corpchat (system account, no shell, no home dir)
├── /app/           → root:corpchat  chmod g+rX,o-rwx
│                     (group-readable, no world access — corpchat can read code)
└── /data/          → corpchat:corpchat  chmod 755
    ├── uploads/    → chmod 777  (world-writable — intentional CTF vector)
    └── uploads/tools/ → chmod 777
```

This permission model means:
- Flask (running as `corpchat`) can read `/app` and write `/data`.
- A CTF player who gets RCE via web exploits gets a shell as `corpchat`.
- `corpchat` can write to `/data/uploads` — enabling the wildcard tar exploit.
- `corpchat` cannot read `/root/flag.txt` (which is `chmod 600` owned by root).

#### 5. SSH Configuration

The default Debian/Ubuntu `sshd_config` often has `PasswordAuthentication` commented out or set by an `/etc/ssh/sshd_config.d/*.conf` file. The Dockerfile replaces the entire config to guarantee `PasswordAuthentication yes` is active:

```
Port 22
PasswordAuthentication yes
PermitRootLogin no         ← root SSH is blocked; root flag requires local privesc
UsePAM yes
LogLevel VERBOSE
```

`PermitRootLogin no` is important: even after escalating to root via the wildcard tar exploit, players cannot SSH in as root. The flag must be read from inside the container.

---

### Build Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `INSTALL_NETBIRD` | `false` | Set to `true` to include the NetBird VPN client in the image |

Build with NetBird:

```bash
docker build \
  --build-arg INSTALL_NETBIRD=true \
  -t pwnbox-ctf \
  -f docker/Dockerfile \
  .
```

---

### Exposed Ports

| Port | Service |
|------|---------|
| `8080` | Flask application (CorpChat) |
| `22` | OpenSSH daemon |

---

## Docker Compose Stack (`docker/docker-compose.yml`)

The Compose file runs the full development stack: the CorpChat application and the XSS bot.

```yaml
services:
  corpchat:
    build:
      context: ..
      dockerfile: docker/Dockerfile
      args:
        INSTALL_NETBIRD: "false"
    image: pwnbox-ctf
    container_name: corpchat-dev
    ports:
      - "8080:8080"    # CorpChat web UI
      - "2222:22"      # SSH (host port 2222 → container port 22)
    volumes:
      - corpchat_data:/data
    environment:
      - FLASK_CONFIG=config.ProductionConfig
      - SECRET_KEY=corpchat-dev-secret
      - DATABASE_DIR=/data
      - UPLOAD_FOLDER=/data/uploads
      - LOG_DIR=/data/logs
    restart: unless-stopped

  xss-bot:
    build:
      context: ../bot
      dockerfile: dockerfile
    container_name: xss-bot
    depends_on:
      - corpchat
    environment:
      - TARGET_URL=http://corpchat:8080
      - BOT_USER=compliancebot
      - BOT_PASS=C0mpl1anceB0t2026
      - DEBUG_TOKEN=b3b46de0-86e1-4a98-885d-1a85d2bef561
      - POLL_MS=60000
      - CHROMIUM_PATH=/usr/bin/chromium
    restart: unless-stopped

volumes:
  corpchat_data:
```

### Service: `corpchat`

| Aspect | Value | Notes |
|--------|-------|-------|
| Image tag | `pwnbox-ctf` | Used by the manager to create instances |
| Build context | `..` (project root) | Allows the Dockerfile to access the full source tree |
| Dockerfile | `docker/Dockerfile` | Relative to the project root |
| NetBird | Disabled | Dev stack doesn't need VPN; instances use it |
| Port 8080 | `0.0.0.0:8080:8080` | Web app accessible at `http://localhost:8080` |
| Port 2222 | `0.0.0.0:2222:22` | SSH accessible at `ssh user@localhost -p 2222` |
| Volume | `corpchat_data:/data` | Named volume persists DB and uploads across restarts |
| Restart | `unless-stopped` | Auto-restarts on crash; stays stopped if manually stopped |

### Service: `xss-bot`

| Aspect | Value | Notes |
|--------|-------|-------|
| Build context | `../bot` | Bot directory relative to `docker/` |
| `depends_on` | `corpchat` | Ensures corpchat starts first (but doesn't wait for readiness) |
| `TARGET_URL` | `http://corpchat:8080` | Uses Docker internal DNS — resolves to corpchat's container IP |
| `restart` | `unless-stopped` | If Chromium crashes, the container restarts and re-logs in |

See [XSS Bot](xss-bot.md) for full details on bot behaviour.

### Named Volume: `corpchat_data`

The `corpchat_data` volume persists:

```
/data/
├── corpchat.db          ← SQLite database (all users, messages, channels)
├── uploads/             ← Uploaded files (including tools/corpchat-admin)
│   └── tools/
│       └── corpchat-admin
├── backups/             ← Admin panel database backups
└── logs/                ← Application logs
```

Volume persists across `docker compose down && docker compose up`. To reset to a clean state (new database, no uploads):

```bash
docker compose down -v    # -v removes the named volume
docker compose up --build
```

---

## Container Networking

### Docker Compose Network

Compose automatically creates a bridge network (default name: `pwnbox_default`) connecting `corpchat` and `xss-bot`. The two containers can reach each other by service name:

```
xss-bot  →  http://corpchat:8080   (internal)
host     →  http://localhost:8080   (via port mapping)
```

### Multi-Instance Network (`pwnbox-net`)

For CTF events using the portal or scaler, `setup-host.sh` creates a dedicated Docker bridge network:

```bash
docker network create \
  --driver bridge \
  --subnet 172.20.0.0/16 \
  pwnbox-net
```

Each challenge instance is attached to this network with a statically assigned IP in the `172.20.x.x` range. NetBird provides an additional overlay network so players can reach their container from outside.

---

## Directory Auto-Creation

On startup, `app.py` ensures all required directories exist:

```python
for dir_key in ('DATABASE_DIR', 'UPLOAD_FOLDER', 'LOG_DIR'):
    dir_path = app.config.get(dir_key)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

backup_dir = app.config.get('BACKUP_DIR')
if backup_dir:
    os.makedirs(backup_dir, exist_ok=True)
```

In practice, the Dockerfile creates these directories during the build, and `entrypoint.py` also ensures they exist and have correct ownership before handing off to Flask.

---

## Running Commands

### Development Stack (Compose)

```bash
./run.sh compose           # Start both services (builds if needed)
./run.sh compose down      # Stop and remove containers
./run.sh compose logs      # Follow combined logs
docker compose logs corpchat   # Only app logs
docker compose logs xss-bot    # Only bot logs
```

### Standalone (No Bot)

```bash
./run.sh app               # Build + run without NetBird
./run.sh app --netbird     # Build + run with NetBird
```

### Explicit Build

```bash
./run.sh build             # Build if image is missing or stale
./run.sh build --force     # Force rebuild
./run.sh build --netbird   # Build with NetBird
```

The image staleness check in `run.sh` compares the image creation timestamp against the modification time of `docker/Dockerfile`, `requirements.txt`, and `entrypoint.py`. If any source file is newer than the image, a rebuild is triggered automatically.

---

## Local Development (No Docker)

For working on the Flask application without Docker:

```bash
pip install -r requirements.txt
python3 app.py
```

The server starts at `http://0.0.0.0:5000` using `DevelopmentConfig` (debug mode, local `./data/` directory). The SSH daemon and cron jobs are not available in this mode.

---

## Dependencies

### `requirements.txt`

```
Flask==3.0.0
Werkzeug==3.0.1
```

| Package | Provides |
|---------|---------|
| Flask 3.0.0 | Request routing, blueprints, Jinja2 templates, sessions, static files |
| Werkzeug 3.0.1 | `generate_password_hash`, `check_password_hash`, WSGI utilities |

Everything else (SQLite, uuid, hashlib, base64, etc.) is from the Python standard library.

### Bot (`bot/package.json`)

```json
{ "dependencies": { "puppeteer": "^21.0.0" } }
```

Puppeteer provides the browser automation API over the DevTools protocol. The bot uses system Chromium rather than Puppeteer's bundled Chromium.

---

## System Settings vs. Config

Two distinct layers control application behaviour:

### 1. Python Config (`config.py`)

- Loaded once at startup via `app.config.from_object()`.
- Controls actual application behaviour (DB path, upload limits, debug mode).
- Changed via environment variables or code changes.

### 2. Database Settings (`system_settings` table)

Managed via the admin panel at `/admin/settings`. Stored in the SQLite database. **The application does not read these at runtime** — they exist as a UI convenience feature but do not affect application behaviour.

Default seeded values:

| Key | Default Value |
|-----|---------------|
| `site_name` | `CorpChat` |
| `allow_registration` | `true` |
| `max_upload_size_mb` | `10` |
| `debug_mode` | `false` |
| `backup_enabled` | `true` |
| `backup_path` | `/data/backups` |
| `session_timeout_minutes` | `60` |
| `motd` | `Welcome to CorpChat - Your secure corporate messaging platform` |
