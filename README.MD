# PwnBox

PwnBox is a Capture The Flag (CTF) platform built on top of CorpChat, a deliberately vulnerable corporate messaging application. It provides a complete event infrastructure: containerised challenge instances, a self-service player portal, and an operator scaler for managing instances at scale.

---

## Overview

| Component | Purpose |
|-----------|---------|
| CorpChat | Intentionally vulnerable Flask web application (the challenge target) |
| Docker image | Packages CorpChat with NetBird VPN, SSH, and cron |
| Portal | Web interface for team registration, instance management, and scoring |
| Scaler | Token-authenticated operator interface for spinning instances up and down |
| Manager | CLI tool (`pwnbox-manager.py`) called by the portal and scaler |

---

## Prerequisites

- Docker
- Python 3.11 or later with `pip`
- A NetBird self-hosted or cloud management server

---

## Quick Start

### 1. Host Setup

Run the setup script once on the host machine. It creates the Docker network, initialises the state directory, and builds the image.

```bash
./setup-host.sh
```

### 2. Start the Portal

```bash
./run.sh portal
```

The portal is available at `http://localhost:8888`.

### 3. Start the Scaler (Optional)

```bash
./run.sh scale
```

The scaler is available at `http://localhost:8889`.

---

## Running the Application Standalone

To run CorpChat directly (without CTF infrastructure), use Docker Compose:

```bash
./run.sh compose
```

Or run locally without Docker:

```bash
pip install -r requirements.txt
python3 app.py
```

The application starts on `http://localhost:5000`.

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
│   └── admin-tools.c            # Compiled into the challenge binary
├── routes/                      # Flask route blueprints
├── templates/                   # Jinja2 application templates
├── static/                      # CSS and JavaScript assets
└── documentation/               # Full documentation wiki
```

---

## Configuration

All infrastructure settings are in `infra/config.ini`. Key sections:

| Section | Purpose |
|---------|---------|
| `[general]` | Docker image name, network, TTL, instance limits |
| `[netbird]` | Management URL, machine and player setup keys |
| `[portal]` | Host, port, secret key, event password |
| `[scaler]` | Host, port, event token |
| `[paths]` | State directory, log directory |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Application | Python 3.11, Flask 3.0 |
| Database | SQLite 3 |
| Frontend | HTML5, Jinja2, Vanilla JavaScript |
| Containerisation | Docker |
| Networking | NetBird (WireGuard-based overlay VPN) |

---

## Documentation

Full documentation is in the [documentation/](documentation/README.md) directory.
The entire documentation is autonomously managed and updated by Claude Code to ensure we can serve a detailed and always up-to-date documentation.
