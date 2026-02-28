#!/usr/bin/env python3

import argparse
import configparser
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from filelock import FileLock

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.ini"


def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    return cfg


def _resolve_state_dir(cfg):
    p = Path(cfg.get("paths", "state_dir"))
    if not p.is_absolute():
        p = SCRIPT_DIR / p
    return p


def get_state_path(cfg):
    return _resolve_state_dir(cfg) / "instances.json"


def get_lock_path(cfg):
    return _resolve_state_dir(cfg) / "instances.lock"


def load_instances(cfg):
    path = get_state_path(cfg)
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def save_instances(cfg, instances):
    path = get_state_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(instances, f, indent=2, default=str)


def validate_team_name(name):
    if not re.match(r'^[a-zA-Z0-9_-]{1,32}$', name):
        print(f"Error: Invalid team name '{name}'. Use only letters, numbers, hyphens, underscores (max 32 chars).")
        sys.exit(1)


def run(cmd, check=True, capture=True):
    """Run a shell command."""
    result = subprocess.run(
        cmd, shell=isinstance(cmd, str),
        capture_output=capture, text=True
    )
    if check and result.returncode != 0:
        stderr = result.stderr if capture else ""
        raise RuntimeError(f"Command failed: {cmd}\n{stderr}")
    return result


def next_available_ip(cfg, instances):
    #Find the next available Docker container IP.

    start = cfg.getint("general", "container_ip_start")
    max_inst = cfg.getint("general", "max_instances")
    network = cfg.get("general", "docker_network")
    docker_prefix = cfg.get("general", "docker_subnet").rsplit(".", 2)[0]

    used_offsets = set()

    # From state file
    for inst in instances.values():
        try:
            last_octet = int(inst["container_ip"].rsplit(".", 1)[1])
            used_offsets.add(last_octet)
        except (KeyError, ValueError):
            pass

    # From Docker network
    result = subprocess.run(
        ["docker", "network", "inspect", network, "--format", "{{json .Containers}}"],
        capture_output=True, text=True
    )
    if result.returncode == 0 and result.stdout.strip() not in ("", "null"):
        try:
            containers = json.loads(result.stdout.strip())
            for c in containers.values():
                ip = c.get("IPv4Address", "").split("/")[0]
                if ip:
                    last_octet = int(ip.rsplit(".", 1)[1])
                    used_offsets.add(last_octet)
        except (json.JSONDecodeError, ValueError):
            pass

    for offset in range(start, start + max_inst):
        if offset not in used_offsets:
            return f"{docker_prefix}.0.{offset}"

    return None


def start_container(cfg, team, container_ip):

    image = cfg.get("general", "image_name")
    network = cfg.get("general", "docker_network")
    container_name = f"pwnbox-{team}"
    mgmt_url = cfg.get("netbird", "management_url")
    machine_key = cfg.get("netbird", "machine_setup_key")

    run(f"docker run -d "
        f"--name {container_name} "
        f"--network {network} "
        f"--ip {container_ip} "
        f"--hostname pwnbox-{team} "
        f"--cap-add NET_ADMIN "
        f"-e NETBIRD_SETUP_KEY={machine_key} "
        f"-e NETBIRD_MGMT_URL={mgmt_url} "
        f"-e SECRET_KEY=ctf-{team}-{os.urandom(4).hex()} "
        f"-e FLASK_CONFIG=config.ProductionConfig "
        f"-e DATABASE_DIR=/data "
        f"-e UPLOAD_FOLDER=/data/uploads "
        f"-e LOG_DIR=/data/logs "
        f"--restart unless-stopped "
        f"{image}")


def get_netbird_ip(team, retries=10, delay=3):

    container_name = f"pwnbox-{team}"
    for i in range(retries):
        result = run(
            f"docker exec {container_name} netbird status",
            check=False, capture=True
        )
        if result.returncode == 0 and result.stdout:
            match = re.search(r'NetBird IP:\s*([0-9.]+)', result.stdout)
            if match:
                return match.group(1)
        if i < retries - 1:
            time.sleep(delay)
    return None


def stop_container(team):

    container_name = f"pwnbox-{team}"
    run(f"docker rm -f {container_name}", check=False)


# --- Commands ---

def cmd_create(cfg, team):
    validate_team_name(team)
    lock = FileLock(str(get_lock_path(cfg)))

    with lock:
        instances = load_instances(cfg)

        if team in instances:
            print(f"Error: Instance for '{team}' already exists.")
            print(f"  Use 'destroy {team}' first, or 'info {team}' to see details.")
            sys.exit(1)

        max_inst = cfg.getint("general", "max_instances")
        if len(instances) >= max_inst:
            print(f"Error: Maximum amount of instances ({max_inst}) reached.")
            sys.exit(1)

        container_ip = next_available_ip(cfg, instances)
        if not container_ip:
            print("Error: No available IPs.")
            sys.exit(1)

        ttl = cfg.getint("general", "instance_ttl_hours")
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=ttl)

        print(f"Creating instance for team '{team}'...")
        print(f"  Container IP: {container_ip}")

        # Remove any orphaned container with this name before starting
        container_name = f"pwnbox-{team}"
        r = subprocess.run(["docker", "inspect", container_name], capture_output=True)
        if r.returncode == 0:
            print(f"  Removing orphaned container '{container_name}'...")
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

        # Start container (NetBird starts inside automatically)
        start_container(cfg, team, container_ip)

        # Wait for NetBird to register and get its IP
        print(f"  Waiting for NetBird registration...")
        netbird_ip = get_netbird_ip(team)
        if netbird_ip:
            print(f"  NetBird IP:   {netbird_ip}")
        else:
            print(f"  Warning: Could not retrieve NetBird IP yet. Check 'info {team}' later.")

        # Save state
        instances[team] = {
            "container_ip": container_ip,
            "netbird_ip": netbird_ip or "",
            "container_name": f"pwnbox-{team}",
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }
        save_instances(cfg, instances)

    app_port = cfg.get("general", "container_app_port")
    mgmt_url = cfg.get("netbird", "management_url")
    player_key = cfg.get("netbird", "player_setup_key")

    print(f"  Expires:      {expires.strftime('%Y-%m-%d %H:%M UTC')}")
    print()
    print("=== NetBird Connection ===")
    print(f"  1. Install NetBird: https://docs.netbird.io/how-to/installation")
    print(f"  2. Connect: netbird up --setup-key {player_key} --management-url {mgmt_url}")
    if netbird_ip:
        print(f"  3. Access PwnBox at: http://{netbird_ip}:{app_port}")
    else:
        print(f"  3. Access PwnBox at the NetBird IP shown in 'info {team}'")
    print(f"  4. Instance auto-destroys in {ttl} hours")


def cmd_destroy(cfg, team):
    validate_team_name(team)
    lock = FileLock(str(get_lock_path(cfg)))

    with lock:
        instances = load_instances(cfg)

        if team not in instances:
            print(f"Error: No instance found for '{team}'.")
            sys.exit(1)

        inst = instances[team]
        print(f"Destroying instance for team '{team}'...")

        # Stop container (also removes NetBird peer when container dies)
        print(f"  Stopping container: {inst['container_name']}")
        stop_container(team)

        del instances[team]
        save_instances(cfg, instances)

    print("  Done.")


def cmd_list(cfg):
    instances = load_instances(cfg)
    if not instances:
        print("No active instances.")
        return

    now = datetime.now(timezone.utc)
    print(f"{'Team':<20} {'NetBird IP':<18} {'Created':<20} {'Expires':<20} {'Status'}")
    print("-" * 100)

    for team, inst in sorted(instances.items()):
        expires = datetime.fromisoformat(inst["expires_at"])
        created = datetime.fromisoformat(inst["created_at"])
        expired = "EXPIRED" if now > expires else "active"
        remaining = expires - now
        if expired == "active":
            hours = int(remaining.total_seconds() // 3600)
            mins = int((remaining.total_seconds() % 3600) // 60)
            expired = f"active ({hours}h {mins}m left)"

        nb_ip = inst.get("netbird_ip", "pending")
        print(f"{team:<20} {nb_ip:<18} "
              f"{created.strftime('%m-%d %H:%M UTC'):<20} {expires.strftime('%m-%d %H:%M UTC'):<20} {expired}")

    print(f"\nTotal: {len(instances)} instance(s)")


def cmd_info(cfg, team):
    validate_team_name(team)
    instances = load_instances(cfg)

    if team not in instances:
        print(f"No instance found for '{team}'.")
        sys.exit(1)

    inst = instances[team]
    app_port = cfg.get("general", "container_app_port")
    now = datetime.now(timezone.utc)
    expires = datetime.fromisoformat(inst["expires_at"])
    remaining = expires - now

    # Try to refresh NetBird IP if it was missing
    netbird_ip = inst.get("netbird_ip", "")
    if not netbird_ip:
        netbird_ip = get_netbird_ip(team, retries=1, delay=0) or ""
        if netbird_ip:
            lock = FileLock(str(get_lock_path(cfg)))
            with lock:
                instances = load_instances(cfg)
                if team in instances:
                    instances[team]["netbird_ip"] = netbird_ip
                    save_instances(cfg, instances)

    print(f"=== Instance: {team} ===")
    print(f"  Container:    {inst['container_name']}")
    print(f"  Container IP: {inst['container_ip']}")
    print(f"  NetBird IP:   {netbird_ip or 'pending'}")
    if netbird_ip:
        print(f"  App URL:      http://{netbird_ip}:{app_port}")
    print(f"  Created:      {inst['created_at']}")
    print(f"  Expires:      {inst['expires_at']}")
    if remaining.total_seconds() > 0:
        hours = int(remaining.total_seconds() // 3600)
        mins = int((remaining.total_seconds() % 3600) // 60)
        print(f"  Remaining:    {hours}h {mins}m")
    else:
        print(f"  Status:       EXPIRED")

    mgmt_url = cfg.get("netbird", "management_url")
    player_key = cfg.get("netbird", "player_setup_key")
    print(f"\n=== NetBird Connection ===")
    print(f"  netbird up --setup-key {player_key} --management-url {mgmt_url}")


def cmd_cleanup(cfg):
    lock = FileLock(str(get_lock_path(cfg)))

    with lock:
        instances = load_instances(cfg)
        now = datetime.now(timezone.utc)
        expired = []

        for team, inst in instances.items():
            expires = datetime.fromisoformat(inst["expires_at"])
            if now > expires:
                expired.append(team)

    if not expired:
        print("No expired instances.")
        return

    print(f"Found {len(expired)} expired instance(s).")
    for team in expired:
        cmd_destroy(cfg, team)


def cmd_pause(cfg, team):
    validate_team_name(team)
    lock = FileLock(str(get_lock_path(cfg)))

    with lock:
        instances = load_instances(cfg)

        if team not in instances:
            print(f"Error: No instance found for '{team}'.")
            sys.exit(1)

        inst = instances[team]
        container_name = inst["container_name"]
        print(f"Pausing instance for team '{team}'...")
        run(f"docker stop {container_name}")
        instances[team]["paused"] = True
        save_instances(cfg, instances)

    print("  Done. Container stopped.")


def cmd_resume(cfg, team):
    validate_team_name(team)
    lock = FileLock(str(get_lock_path(cfg)))

    with lock:
        instances = load_instances(cfg)

        if team not in instances:
            print(f"Error: No instance found for '{team}'.")
            sys.exit(1)

        inst = instances[team]
        container_name = inst["container_name"]
        print(f"Resuming instance for team '{team}'...")
        run(f"docker start {container_name}")
        instances[team]["paused"] = False
        save_instances(cfg, instances)

    print("  Done. Container started.")


def cmd_rebuild(cfg):
    image = cfg.get("general", "image_name")
    project_root = SCRIPT_DIR / ".."
    dockerfile = project_root / "docker" / "Dockerfile"
    print(f"Rebuilding image '{image}' (with NetBird)...")
    run(f"docker build --build-arg INSTALL_NETBIRD=true -f {dockerfile} -t {image} {project_root}", capture=False)
    print("Done. New instances will use the updated image.")
    print("Note: Existing instances still run the old image.")


def main():
    parser = argparse.ArgumentParser(description="PwnBox CTF Instance Manager")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to config.ini")
    sub = parser.add_subparsers(dest="command")

    p_create = sub.add_parser("create", help="Create a new instance")
    p_create.add_argument("team", help="Team name")

    p_destroy = sub.add_parser("destroy", help="Destroy an instance")
    p_destroy.add_argument("team", help="Team name")

    sub.add_parser("list", help="List active instances")

    p_info = sub.add_parser("info", help="Show instance info")
    p_info.add_argument("team", help="Team name")

    p_pause = sub.add_parser("pause", help="Pause (stop) an instance")
    p_pause.add_argument("team", help="Team name")

    p_resume = sub.add_parser("resume", help="Resume (start) an instance")
    p_resume.add_argument("team", help="Team name")

    sub.add_parser("cleanup", help="Destroy expired instances")
    sub.add_parser("rebuild", help="Rebuild Docker image")

    args = parser.parse_args()
    cfg = configparser.ConfigParser()
    cfg.read(args.config)

    if args.command == "create":
        cmd_create(cfg, args.team)
    elif args.command == "destroy":
        cmd_destroy(cfg, args.team)
    elif args.command == "list":
        cmd_list(cfg)
    elif args.command == "info":
        cmd_info(cfg, args.team)
    elif args.command == "pause":
        cmd_pause(cfg, args.team)
    elif args.command == "resume":
        cmd_resume(cfg, args.team)
    elif args.command == "cleanup":
        cmd_cleanup(cfg)
    elif args.command == "rebuild":
        cmd_rebuild(cfg)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
