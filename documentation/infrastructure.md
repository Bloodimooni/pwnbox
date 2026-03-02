# Infrastructure

[Back to Index](README.md)

---

## Overview

The PwnBox infrastructure layer sits between the CorpChat application and the event operator. It consists of four components:

| Component | File | Purpose |
|-----------|------|---------|
| Player portal | `infra/portal.py` | Team registration, self-service instance management, flag submission, leaderboard |
| Operator scaler | `infra/scaler.py` | Token-authenticated operator tool for spinning instances up and down |
| Instance manager | `infra/pwnbox-manager.py` | CLI tool that creates and destroys Docker containers |
| Configuration | `infra/config.ini` | Central configuration for all infrastructure components |

All components read from the same `infra/config.ini` file and share the same instance state directory.

---

## Configuration Reference (`infra/config.ini`)

### `[general]`

| Key | Default | Description |
|-----|---------|-------------|
| `image_name` | `pwnbox-ctf` | Docker image name used for all challenge containers |
| `max_instances` | `16` | Maximum number of concurrent instances (portal and manager enforce this) |
| `instance_ttl_hours` | `8` | Lifetime of each instance in hours; after expiry it will not be auto-destroyed but is marked expired |
| `docker_network` | `pwnbox-net` | Name of the Docker bridge network |
| `docker_subnet` | `172.20.0.0/16` | Subnet assigned to the Docker network |
| `container_ip_start` | `2` | Last-octet offset for the first assigned container IP |
| `container_app_port` | `8080` | Port the CorpChat Flask application listens on inside the container |

### `[netbird]`

| Key | Description |
|-----|-------------|
| `management_url` | Full URL of the NetBird management server, including port |
| `machine_setup_key` | Setup key used when registering each challenge container as a NetBird peer |
| `player_setup_key` | Setup key distributed to players so they can join the same NetBird network |

### `[portal]`

| Key | Default | Description |
|-----|---------|-------------|
| `host` | `0.0.0.0` | Interface the portal Flask application binds to |
| `port` | `8888` | Port the portal listens on |
| `secret_key` | — | Flask session signing key; must be changed before deployment |
| `event_password` | — | Password players enter during team registration |

### `[scaler]`

| Key | Default | Description |
|-----|---------|-------------|
| `host` | `0.0.0.0` | Interface the scaler Flask application binds to |
| `port` | `8889` | Port the scaler listens on |
| `event_token` | — | Bearer token required for all scaler API requests |

### `[paths]`

| Key | Default | Description |
|-----|---------|-------------|
| `state_dir` | `./pwnbox-machines` | Directory where instance state is stored; relative paths are resolved against `infra/` |
| `log_dir` | `./logs` | Directory for portal HTTP access logs |

Relative paths in `[paths]` are resolved relative to the `infra/` directory, regardless of the working directory from which the process is launched.

---

## Player Portal (`infra/portal.py`)

The portal is the primary interface for CTF participants. It runs as a Flask application on the host.

### Features

- Team registration with event password verification
- Role-based access: one captain per team, multiple members
- Self-service instance launch, pause, resume, and destroy
- Instance TTL display with live countdown
- Cooldown enforcement after instance destruction (prevents rapid relaunching)
- Flag submission with per-flag scoring
- Leaderboard showing team scores and solve times
- Operator admin panel for managing teams and overriding instance state

### Team and Instance Lifecycle

1. A player registers using the event password and creates or joins a team.
2. The team captain launches an instance from the dashboard.
3. The portal calls `pwnbox-manager.py create <team>` as a subprocess.
4. The manager starts a Docker container and waits for the NetBird IP to be assigned.
5. The dashboard displays the NetBird IP, TTL countdown, and connection instructions.
6. The captain can pause, resume, or destroy the instance at any time.
7. After destruction, a cooldown period prevents the team from launching a new instance immediately.

### API Endpoints (Portal)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/team` | Returns the current team's state, instance info, and cooldown status |
| `GET` | `/api/admin/overview` | Operator view of all teams and instances (requires admin session) |
| `POST` | `/api/instance/launch` | Launch an instance for the current team (captain only) |
| `POST` | `/api/instance/destroy` | Destroy the current team's instance (captain only) |
| `POST` | `/api/instance/pause` | Pause the current team's instance (captain only) |
| `POST` | `/api/instance/resume` | Resume the current team's instance (captain only) |
| `POST` | `/api/flags/submit` | Submit a flag for the current team |

### State Storage

The portal stores team and flag data in a JSON file within `state_dir`. Instance state is shared with the manager via `instances.json`. File locking (`filelock`) prevents race conditions when multiple requests modify state simultaneously.

---

## Operator Scaler (`infra/scaler.py`)

The scaler is a lightweight operator tool that does not require player accounts or a team system. All requests are authenticated with a static bearer token configured in `[scaler]`.

### Intended Use

The scaler is intended for events where the operator manages instances directly, rather than delegating instance management to players. It provides a simple web interface and a JSON API.

### Authentication

All API requests must include the token in the `Authorization` header:

```
Authorization: Bearer <event_token>
```

The web interface prompts for the token on first load and stores it in `localStorage`.

### API Endpoints (Scaler)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/instances` | List all active instances with NetBird IP, status, and TTL |
| `POST` | `/api/instances` | Create a new instance; body: `{"name": "<name>"}` |
| `DELETE` | `/api/instances/<name>` | Destroy a specific instance |
| `DELETE` | `/api/instances` | Destroy all instances |
| `GET` | `/api/config` | Return player-facing connection details (setup key, management URL) |

### Limits

- Maximum of 20 instances can be active at once. Attempts to exceed this return HTTP 429.
- Instance names follow the same validation rules as team names: alphanumeric, hyphens, and underscores only, maximum 32 characters.

---

## Instance Manager (`infra/pwnbox-manager.py`)

The manager is a CLI tool called by both the portal and the scaler to perform the actual Docker operations. It can also be used directly by operators.

### Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `create` | `pwnbox-manager.py create <team>` | Start a new container, wait for NetBird registration, save state |
| `destroy` | `pwnbox-manager.py destroy <team>` | Remove the container and delete the state entry |
| `list` | `pwnbox-manager.py list` | Print a table of all active instances with IP, TTL, and status |
| `info` | `pwnbox-manager.py info <team>` | Print detailed info for one instance, refreshing the NetBird IP if missing |
| `pause` | `pwnbox-manager.py pause <team>` | Stop the container without removing it |
| `resume` | `pwnbox-manager.py resume <team>` | Start a previously paused container |
| `cleanup` | `pwnbox-manager.py cleanup` | Destroy all instances whose TTL has expired |
| `rebuild` | `pwnbox-manager.py rebuild` | Rebuild the Docker image with NetBird enabled |

### Instance Creation Process

1. Acquires a file lock on `instances.lock`.
2. Validates the team name against the pattern `[a-zA-Z0-9_-]{1,32}`.
3. Checks that the total instance count is below `max_instances`.
4. Allocates the next available IP from the Docker subnet.
5. Removes any orphaned container with the same name.
6. Starts the container with the required environment variables.
7. Polls `docker exec <container> netbird status` up to 10 times (3-second intervals) until the NetBird IP is visible.
8. Writes the instance record to `instances.json`.

### State File Format

Each entry in `instances.json` is keyed by team name:

```json
{
  "teamname": {
    "container_ip": "172.20.0.2",
    "netbird_ip": "100.x.x.x",
    "container_name": "pwnbox-teamname",
    "created_at": "2026-01-01T12:00:00+00:00",
    "expires_at": "2026-01-01T20:00:00+00:00",
    "paused": false
  }
}
```

### IP Allocation

The manager allocates IPs from the configured Docker subnet. It checks both the state file and the live Docker network (`docker network inspect`) to avoid conflicts with containers not tracked in the state file. IPs are assigned by incrementing the last octet starting from `container_ip_start`.

---

## NetBird Integration

NetBird provides the WireGuard-based overlay network that players use to reach their challenge containers. The containers are not directly accessible from the internet.

### How It Works

1. During image build, NetBird is optionally installed via the official install script.
2. When a container starts, `entrypoint.py` wipes the NetBird state directories (`/var/lib/netbird`, `/etc/netbird`) to ensure each container generates a fresh WireGuard identity.
3. The container calls `netbird up` with the `NETBIRD_SETUP_KEY` and `NETBIRD_MGMT_URL` environment variables.
4. NetBird registers the container as a new peer with a unique IP on the overlay network.
5. Players connect to the same NetBird network using the `player_setup_key` and can then access the container at its NetBird IP.

### Why State Must Be Wiped

The Docker image bakes in all files present during the build, including any NetBird identity files. If the state directories are not cleared at startup, every container started from the same image would present the same WireGuard private key to the management server, resulting in all containers being assigned the same peer identity and the same IP address.

### Player Connection

Players connect using the NetBird CLI:

```bash
netbird up --setup-key <player_setup_key> --management-url <management_url>
```

Once connected, the challenge instance is accessible at `http://<netbird-ip>:8080` and via SSH on port 22.

---

## Container Environment

Each challenge container is started with the following environment variables:

| Variable | Source | Description |
|----------|--------|-------------|
| `NETBIRD_SETUP_KEY` | `config.ini [netbird]` | Registers the container as a NetBird peer |
| `NETBIRD_MGMT_URL` | `config.ini [netbird]` | NetBird management server URL |
| `SECRET_KEY` | Generated per instance | Unique Flask session signing key |
| `FLASK_CONFIG` | Hardcoded | `config.ProductionConfig` |
| `DATABASE_DIR` | Hardcoded | `/data` |
| `UPLOAD_FOLDER` | Hardcoded | `/data/uploads` |
| `LOG_DIR` | Hardcoded | `/data/logs` |

The container is started with `--cap-add NET_ADMIN` to allow NetBird to configure the WireGuard interface, and with `--restart unless-stopped` so it survives host reboots.

---

## Flags

Flag definitions are stored in `infra/flags.json`. Each flag entry includes an identifier, a point value, and the flag string itself. The portal validates submitted flags against this file and records the first-correct-submission time for each team.

---

## Operator Workflows

### Running an Event with the Portal

1. Configure `infra/config.ini` with your NetBird credentials and event password.
2. Run `./setup-host.sh` to prepare the host.
3. Run `./run.sh portal` to start the player portal.
4. Share the portal URL and event password with participants.
5. Monitor the operator admin panel for team and instance status.

### Running an Event with the Scaler

1. Configure `infra/config.ini` with your NetBird credentials and a strong `event_token`.
2. Run `./setup-host.sh` to prepare the host.
3. Run `./run.sh scale` to start the scaler.
4. Use the scaler web interface (or its API) to create instances manually.
5. Share NetBird connection details with participants using the `/api/config` response.

### Direct CLI Management

```bash
cd infra

# Create an instance
python3 pwnbox-manager.py create teamname

# List all instances
python3 pwnbox-manager.py list

# Show details for one instance
python3 pwnbox-manager.py info teamname

# Pause and resume
python3 pwnbox-manager.py pause teamname
python3 pwnbox-manager.py resume teamname

# Destroy one instance
python3 pwnbox-manager.py destroy teamname

# Clean up all expired instances
python3 pwnbox-manager.py cleanup
```
