#!/usr/bin/env python3

import argparse
import configparser
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from filelock import FileLock

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.ini"


def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    return cfg


def get_state_path(cfg):
    return Path(cfg.get("paths", "state_dir")) / "instances.json"


def get_lock_path(cfg):
    return Path(cfg.get("paths", "state_dir")) / "instances.lock"


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


def wg_genkey():
    """Generate a WireGuard private key and derive the public key."""
    priv = run("wg genkey").stdout.strip()
    pub = run(f"echo {priv} | wg pubkey").stdout.strip()
    return priv, pub


def next_available_ip(cfg, instances):
    """Find the next available IP pair (WireGuard + Docker)."""
    start = cfg.getint("general", "container_ip_start")
    max_inst = cfg.getint("general", "max_instances")
    used_offsets = set()
    for inst in instances.values():
        # Extract the last octet from container_ip
        last_octet = int(inst["container_ip"].rsplit(".", 1)[1])
        used_offsets.add(last_octet)

    for offset in range(start, start + max_inst):
        if offset not in used_offsets:
            # Docker: 172.20.0.{offset}
            docker_prefix = cfg.get("general", "docker_subnet").rsplit(".", 2)[0]
            container_ip = f"{docker_prefix}.0.{offset}"
            # WireGuard: 10.13.37.{offset}
            wg_prefix = cfg.get("wireguard", "subnet").rsplit(".", 1)[0]
            wg_ip = f"{wg_prefix}.{offset}"
            return container_ip, wg_ip

    return None, None


def add_wg_peer(cfg, wg_ip, pub_key, container_ip):
    """Add a WireGuard peer to the server config and reload."""
    iface = cfg.get("wireguard", "interface")
    wg_dir = cfg.get("paths", "wireguard_dir")

    peer_block = f"""
# PWNBOX_PEER:{wg_ip}
[Peer]
PublicKey = {pub_key}
AllowedIPs = {wg_ip}/32
# END_PWNBOX_PEER:{wg_ip}
"""
    conf_path = Path(wg_dir) / f"{iface}.conf"
    with open(conf_path, "a") as f:
        f.write(peer_block)

    # Reload WireGuard without disrupting existing connections
    run(f"wg syncconf {iface} <(wg-quick strip {iface})", check=False)


def remove_wg_peer(cfg, wg_ip):
    """Remove a WireGuard peer from config and reload."""
    iface = cfg.get("wireguard", "interface")
    wg_dir = cfg.get("paths", "wireguard_dir")
    conf_path = Path(wg_dir) / f"{iface}.conf"

    with open(conf_path) as f:
        content = f.read()

    # Remove the peer block between markers
    pattern = rf'\n# PWNBOX_PEER:{re.escape(wg_ip)}.*?# END_PWNBOX_PEER:{re.escape(wg_ip)}\n'
    content = re.sub(pattern, '', content, flags=re.DOTALL)

    with open(conf_path, "w") as f:
        f.write(content)

    run(f"wg syncconf {iface} <(wg-quick strip {iface})", check=False)


def gen_client_config(cfg, priv_key, wg_ip, container_ip):
    """Generate the client WireGuard config file content."""
    wg_dir = cfg.get("paths", "wireguard_dir")
    server_pub = Path(wg_dir) / "server_public.key"
    server_pubkey = server_pub.read_text().strip()
    endpoint = cfg.get("wireguard", "endpoint")
    port = cfg.get("wireguard", "port")
    dns = cfg.get("wireguard", "dns")

    # Route the specific container IP through the tunnel
    docker_subnet = cfg.get("general", "docker_subnet")

    return f"""[Interface]
PrivateKey = {priv_key}
Address = {wg_ip}/32
DNS = {dns}

[Peer]
PublicKey = {server_pubkey}
Endpoint = {endpoint}:{port}
AllowedIPs = {docker_subnet}
PersistentKeepalive = 25
"""


def start_container(cfg, team, container_ip):
    """Start a Docker container for the team."""
    image = cfg.get("general", "image_name")
    network = cfg.get("general", "docker_network")
    container_name = f"pwnbox-{team}"

    run(f"docker run -d "
        f"--name {container_name} "
        f"--network {network} "
        f"--ip {container_ip} "
        f"--hostname corpchat "
        f"-e SECRET_KEY=ctf-{team}-{os.urandom(4).hex()} "
        f"-e FLASK_CONFIG=config.ProductionConfig "
        f"-e DATABASE_DIR=/data "
        f"-e UPLOAD_FOLDER=/data/uploads "
        f"-e LOG_DIR=/data/logs "
        f"--restart unless-stopped "
        f"{image}")


def stop_container(team):
    """Stop and remove a team's container."""
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
            print(f"Error: Maximum instances ({max_inst}) reached. Try again later.")
            sys.exit(1)

        container_ip, wg_ip = next_available_ip(cfg, instances)
        if not container_ip:
            print("Error: No available IPs.")
            sys.exit(1)

        ttl = cfg.getint("general", "instance_ttl_hours")
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=ttl)

        print(f"Creating instance for team '{team}'...")

        # Generate WireGuard keys
        priv_key, pub_key = wg_genkey()

        # Add WireGuard peer
        print(f"  WireGuard peer: {wg_ip}")
        add_wg_peer(cfg, wg_ip, pub_key, container_ip)

        # Start container
        print(f"  Container IP:   {container_ip}")
        start_container(cfg, team, container_ip)

        # Generate client config
        client_conf = gen_client_config(cfg, priv_key, wg_ip, container_ip)

        # Save state
        instances[team] = {
            "container_ip": container_ip,
            "wg_ip": wg_ip,
            "wg_public_key": pub_key,
            "container_name": f"pwnbox-{team}",
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }
        save_instances(cfg, instances)

    # Save client config
    conf_dir = Path(cfg.get("paths", "state_dir")) / "configs"
    conf_dir.mkdir(parents=True, exist_ok=True)
    conf_file = conf_dir / f"{team}.conf"
    conf_file.write_text(client_conf)

    app_port = cfg.get("general", "container_app_port")
    print(f"  Config saved:   {conf_file}")
    print(f"  Expires:        {expires.strftime('%Y-%m-%d %H:%M UTC')}")
    print()
    print("=== WireGuard Client Config ===")
    print(client_conf)
    print("=== Connection Info ===")
    print(f"  1. Import the config above into WireGuard client")
    print(f"  2. Connect to the VPN")
    print(f"  3. Access PwnBox at: http://{container_ip}:{app_port}")
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

        # Stop container
        print(f"  Stopping container: {inst['container_name']}")
        stop_container(team)

        # Remove WireGuard peer
        print(f"  Removing WireGuard peer: {inst['wg_ip']}")
        remove_wg_peer(cfg, inst["wg_ip"])

        # Clean up config file
        conf_file = Path(cfg.get("paths", "state_dir")) / "configs" / f"{team}.conf"
        if conf_file.exists():
            conf_file.unlink()

        del instances[team]
        save_instances(cfg, instances)

    print("  Done.")


def cmd_list(cfg):
    instances = load_instances(cfg)
    if not instances:
        print("No active instances.")
        return

    now = datetime.now(timezone.utc)
    print(f"{'Team':<20} {'Container IP':<18} {'WG IP':<16} {'Created':<20} {'Expires':<20} {'Status'}")
    print("-" * 115)

    for team, inst in sorted(instances.items()):
        expires = datetime.fromisoformat(inst["expires_at"])
        created = datetime.fromisoformat(inst["created_at"])
        expired = "EXPIRED" if now > expires else "active"
        remaining = expires - now
        if expired == "active":
            hours = int(remaining.total_seconds() // 3600)
            mins = int((remaining.total_seconds() % 3600) // 60)
            expired = f"active ({hours}h {mins}m left)"

        print(f"{team:<20} {inst['container_ip']:<18} {inst['wg_ip']:<16} "
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

    print(f"=== Instance: {team} ===")
    print(f"  Container:    {inst['container_name']}")
    print(f"  Container IP: {inst['container_ip']}")
    print(f"  WireGuard IP: {inst['wg_ip']}")
    print(f"  App URL:      http://{inst['container_ip']}:{app_port}")
    print(f"  Created:      {inst['created_at']}")
    print(f"  Expires:      {inst['expires_at']}")
    if remaining.total_seconds() > 0:
        hours = int(remaining.total_seconds() // 3600)
        mins = int((remaining.total_seconds() % 3600) // 60)
        print(f"  Remaining:    {hours}h {mins}m")
    else:
        print(f"  Status:       EXPIRED")

    # Show client config if it exists
    conf_file = Path(cfg.get("paths", "state_dir")) / "configs" / f"{team}.conf"
    if conf_file.exists():
        print(f"\n=== WireGuard Client Config ===")
        print(conf_file.read_text())


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


def cmd_rebuild(cfg):
    image = cfg.get("general", "image_name")
    pwnbox_dir = SCRIPT_DIR / ".."
    print(f"Rebuilding image '{image}'...")
    run(f"docker build -t {image} {pwnbox_dir}", capture=False)
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
    elif args.command == "cleanup":
        cmd_cleanup(cfg)
    elif args.command == "rebuild":
        cmd_rebuild(cfg)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
