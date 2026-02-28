#!/usr/bin/env python3

import configparser
import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.ini"
MANAGER = SCRIPT_DIR / "pwnbox-manager.py"
TEMPLATES = SCRIPT_DIR / "templates"

app = Flask(__name__, template_folder=str(TEMPLATES))


# ── Config / state helpers ──────────────────────────────────────────────────

def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    return cfg


def get_instances_path(cfg):
    state_dir = Path(cfg.get("paths", "state_dir"))
    if not state_dir.is_absolute():
        state_dir = SCRIPT_DIR / state_dir
    return state_dir / "instances.json"


def load_instances(cfg):
    path = get_instances_path(cfg)
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def run_manager(command, name=None):
    cmd = [sys.executable, str(MANAGER), command]
    if name:
        cmd.append(name)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr, flush=True)
    return result.returncode, result.stdout, result.stderr


# ── Auth ────────────────────────────────────────────────────────────────────

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        cfg = load_config()
        expected = cfg.get("scaler", "event_token", fallback="")
        auth = request.headers.get("Authorization", "")
        if not expected or not auth.startswith("Bearer ") or auth[7:] != expected:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(TEMPLATES), "scaler.html")


@app.route("/api/instances", methods=["GET"])
@token_required
def list_instances():
    cfg = load_config()
    instances = load_instances(cfg)
    now = datetime.now(timezone.utc)
    player_key = cfg.get("netbird", "player_setup_key")
    mgmt_url = cfg.get("netbird", "management_url")
    app_port = cfg.get("general", "container_app_port")

    result = []
    for name, inst in instances.items():
        expires = datetime.fromisoformat(inst["expires_at"])
        remaining = (expires - now).total_seconds()
        netbird_ip = inst.get("netbird_ip", "")
        result.append({
            "name": name,
            "container_ip": inst.get("container_ip", ""),
            "netbird_ip": netbird_ip,
            "expires_at": inst["expires_at"],
            "remaining_minutes": max(0, int(remaining / 60)),
            "expired": remaining <= 0,
            "player_setup_key": player_key,
            "management_url": mgmt_url,
            "app_port": app_port,
            "netbird_setup_cmd": f"netbird up --setup-key {player_key} --management-url {mgmt_url}",
            "app_url": f"http://{netbird_ip}:{app_port}" if netbird_ip else None,
        })

    return jsonify(result)


@app.route("/api/instances", methods=["POST"])
@token_required
def create_instance():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not re.match(r'^[a-zA-Z0-9_-]{1,32}$', name):
        return jsonify({"error": "name must be alphanumeric / hyphens / underscores (max 32 chars)"}), 400

    cfg = load_config()
    instances = load_instances(cfg)
    if name in instances:
        return jsonify({"error": f"Instance '{name}' already exists"}), 409

    rc, out, err = run_manager("create", name)
    if rc != 0:
        return jsonify({"error": (err or out or "Failed to create instance").strip()}), 500

    instances = load_instances(cfg)
    inst = instances.get(name)
    if not inst:
        return jsonify({"error": "Instance created but state not found"}), 500

    now = datetime.now(timezone.utc)
    expires = datetime.fromisoformat(inst["expires_at"])
    remaining = (expires - now).total_seconds()
    player_key = cfg.get("netbird", "player_setup_key")
    mgmt_url = cfg.get("netbird", "management_url")
    app_port = cfg.get("general", "container_app_port")
    netbird_ip = inst.get("netbird_ip", "")

    return jsonify({
        "name": name,
        "container_ip": inst.get("container_ip", ""),
        "netbird_ip": netbird_ip,
        "expires_at": inst["expires_at"],
        "remaining_minutes": max(0, int(remaining / 60)),
        "player_setup_key": player_key,
        "management_url": mgmt_url,
        "app_port": app_port,
        "netbird_setup_cmd": f"netbird up --setup-key {player_key} --management-url {mgmt_url}",
        "app_url": f"http://{netbird_ip}:{app_port}" if netbird_ip else None,
    }), 201


@app.route("/api/instances/<name>", methods=["GET"])
@token_required
def get_instance(name):
    cfg = load_config()
    instances = load_instances(cfg)
    inst = instances.get(name)
    if not inst:
        return jsonify({"error": f"Instance '{name}' not found"}), 404

    now = datetime.now(timezone.utc)
    expires = datetime.fromisoformat(inst["expires_at"])
    remaining = (expires - now).total_seconds()
    player_key = cfg.get("netbird", "player_setup_key")
    mgmt_url = cfg.get("netbird", "management_url")
    app_port = cfg.get("general", "container_app_port")
    netbird_ip = inst.get("netbird_ip", "")

    return jsonify({
        "name": name,
        "container_ip": inst.get("container_ip", ""),
        "netbird_ip": netbird_ip,
        "expires_at": inst["expires_at"],
        "remaining_minutes": max(0, int(remaining / 60)),
        "expired": remaining <= 0,
        "player_setup_key": player_key,
        "management_url": mgmt_url,
        "app_port": app_port,
        "netbird_setup_cmd": f"netbird up --setup-key {player_key} --management-url {mgmt_url}",
        "app_url": f"http://{netbird_ip}:{app_port}" if netbird_ip else None,
    })


@app.route("/api/config", methods=["GET"])
@token_required
def get_config():
    cfg = load_config()
    player_key = cfg.get("netbird", "player_setup_key")
    mgmt_url = cfg.get("netbird", "management_url")
    app_port = cfg.get("general", "container_app_port")
    return jsonify({
        "player_setup_key": player_key,
        "management_url": mgmt_url,
        "app_port": app_port,
        "netbird_setup_cmd": f"netbird up --setup-key {player_key} --management-url {mgmt_url}",
    })


@app.route("/api/instances", methods=["DELETE"])
@token_required
def destroy_all_instances():
    cfg = load_config()
    instances = load_instances(cfg)
    errors = []
    for name in list(instances.keys()):
        rc, out, err = run_manager("destroy", name)
        if rc != 0:
            errors.append(f"{name}: {(err or out or 'failed').strip()}")
    if errors:
        return jsonify({"error": "Some instances failed to destroy", "details": errors}), 500
    return jsonify({"message": f"All instances destroyed"})


@app.route("/api/instances/<name>", methods=["DELETE"])
@token_required
def destroy_instance(name):
    cfg = load_config()
    instances = load_instances(cfg)
    if name not in instances:
        return jsonify({"error": f"Instance '{name}' not found"}), 404

    rc, out, err = run_manager("destroy", name)
    if rc != 0:
        return jsonify({"error": (err or out or "Failed to destroy instance").strip()}), 500

    return jsonify({"message": f"Instance '{name}' destroyed"})


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cfg = load_config()
    host = cfg.get("scaler", "host", fallback="0.0.0.0")
    port = cfg.getint("scaler", "port", fallback=8889)
    token = cfg.get("scaler", "event_token", fallback="(not set)")

    log_dir = Path(cfg.get("paths", "log_dir", fallback="./logs"))
    if not log_dir.is_absolute():
        log_dir = SCRIPT_DIR / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    wz = logging.getLogger("werkzeug")
    wz.setLevel(logging.INFO)
    wz.handlers = []
    wz.propagate = False
    fh = logging.FileHandler(log_dir / "autoscaler-access.log")
    fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    wz.addHandler(fh)

    print(f"[scaler] Starting on http://{host}:{port}")
    print(f"[scaler] Event token: {token}")

    app.run(host=host, port=port, debug=False)
