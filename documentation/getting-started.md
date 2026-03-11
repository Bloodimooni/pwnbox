# Getting Started

[Back to Index](README.md)

---

## Overview

PwnBox is a CTF platform consisting of several components that work together. The typical setup sequence is:

1. Run `setup-host.sh` once to prepare the host environment.
2. Configure `infra/config.ini` for your event.
3. Start the player portal and/or the operator scaler.

This guide covers all deployment modes.

---

## Prerequisites

| Requirement | Purpose |
|-------------|---------|
| Docker | Building and running challenge containers |
| Python 3.11+ | Running the portal and scaler on the host |
| pip | Installing Python dependencies |
| NetBird account or self-hosted instance | VPN connectivity for player instances |

---

## Step 1: Host Setup

Run the setup script once from the project root. It must be executed with sufficient privileges to modify network settings and create Docker networks.

```bash
./setup-host.sh
```

This script performs the following actions:

1. **Enables IP forwarding** — Writes `net.ipv4.ip_forward = 1` to `/etc/sysctl.d/99-pwnbox.conf` and applies it.
2. **Creates the Docker network** — Creates a dedicated bridge network (default: `pwnbox-net`) with the configured subnet.
3. **Initialises the state directory** — Creates the state directory and an empty `instances.json` file if they do not already exist.
4. **Builds the Docker image** — Builds the `pwnbox-ctf` image from `docker/Dockerfile` using the project root as the build context.

The script reads all configuration from `infra/config.ini`. If the Docker network or state directory already exist, they are left unchanged.

---

## Step 2: Configuration

All infrastructure settings are in `infra/config.ini`. Edit this file before starting any components.

### Required Settings

| Section | Key | Description |
|---------|-----|-------------|
| `[netbird]` | `management_url` | URL of your NetBird management server |
| `[netbird]` | `machine_setup_key` | Setup key used by the host machine |
| `[netbird]` | `player_setup_key` | Setup key distributed to players for VPN access |
| `[portal]` | `secret_key` | Flask session signing key — change before deployment |
| `[portal]` | `event_password` | Password players enter to register for the event |
| `[scaler]` | `event_token` | Bearer token required to access the scaler API |

See [Infrastructure](infrastructure.md) for a complete reference of all configuration options.

---

## Step 3: Start the Components

Use the unified `run.sh` script to start each component.

### Player Portal

The portal provides team registration, instance management, flag submission, and a leaderboard.

```bash
./run.sh portal
```

The portal starts on `http://localhost:8080:8888` by default (configurable in `config.ini`).

On first launch, the script checks whether Python dependencies (`flask`, `bcrypt`, `filelock`) are installed and installs them if not.

### Operator Scaler

The scaler is a lightweight operator tool for spinning instances up and down without a team system. It uses token authentication and has no player-facing features.

```bash
./run.sh scale
```

The scaler starts on `http://localhost:8080:8889` by default (configurable in `config.ini`).

### CorpChat Standalone (Development)

To run CorpChat in a Docker container without the CTF infrastructure:

```bash
./run.sh app
```

The application is available at `http://localhost:8080`. SSH is available on port `2222`.

To include NetBird VPN in the standalone image:

```bash
./run.sh app --netbird
```

### Docker Compose (Single-Instance Development)

```bash
./run.sh compose        # Start (equivalent to docker compose up --build)
./run.sh compose down   # Stop
./run.sh compose logs   # Follow logs
```

---

## Image Management

The `run.sh` script automatically builds or rebuilds the Docker image when needed. You can also manage the image explicitly.

```bash
./run.sh build              # Build if missing or source files are newer than the image
./run.sh build --force      # Force rebuild regardless of image age
./run.sh build --netbird    # Build with NetBird included
```

The image staleness check compares the image creation timestamp against the modification time of `docker/Dockerfile`, `requirements.txt`, and `entrypoint.py`.

The portal and scaler commands always build with NetBird enabled, since challenge instances require VPN connectivity.

---

## First-Run Behaviour

When a challenge container starts for the first time, `entrypoint.py` performs the following:

1. **Clears NetBird state** — Wipes `/var/lib/netbird` and `/etc/netbird` to ensure each container generates a unique WireGuard identity, then registers with the NetBird management server using the configured setup key.
2. **Configures SSH** — Creates the `svc_backup` user account and sets the password from the `SSH_PASSWORD` environment variable.
3. **Seeds the database** — Initialises SQLite tables, runs migrations, and inserts default accounts, channels, and messages.
4. **Starts services** — Launches cron, SSH daemon, and the Flask application.

---

## Accessing the Application

### Player Portal
1. Navigate to `http://<host>:8888`.
2. Register a team using the event password provided by the operator.
3. The team captain can launch a challenge instance from the dashboard.

### CorpChat Application (via instance)
1. Connect to NetBird using the player setup key and management URL.
2. Access the application at `http://<netbird-ip>`.
3. Log in with `demo` / `demo123`.

### CorpChat Admin Panel
- Navigate to `/admin` on the CorpChat instance.
- Log in with `admin` / `admin2026!`.

### SSH Access
```bash
ssh svc_backup@<netbird-ip> -p 22
```

---

## Running CorpChat Without Docker

For local development of the CorpChat application only:

```bash
pip install -r requirements.txt
python3 app.py
```

The application starts on `http://0.0.0.0:5000` in development mode.

---

## Environment Variables

The CorpChat container is configured via the following environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_CONFIG` | `config.ProductionConfig` | Configuration class to load |
| `SECRET_KEY` | `corpchat-default-secret` | Flask session signing key |
| `DATABASE_DIR` | `/data` | Directory for the SQLite database |
| `UPLOAD_FOLDER` | `/data/uploads` | Directory for uploaded files |
| `LOG_DIR` | `/data/logs` | Directory for application logs |
| `SSH_PASSWORD` | (set by manager) | Password for the `svc_backup` SSH account |
| `NETBIRD_SETUP_KEY` | (set by manager) | NetBird setup key for VPN registration |
| `NETBIRD_MANAGEMENT_URL` | (set by manager) | NetBird management server URL |

See [Configuration and Deployment](configuration.md) for the full reference.
