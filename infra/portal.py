#!/usr/bin/env python3
"""PwnBox CTF Self-Service Portal

Lightweight web UI where teams can request/destroy their own instances
and download WireGuard configs. Run on the host machine.

Usage: python3 portal.py
"""

import configparser
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.ini"
MANAGER = SCRIPT_DIR / "pwnbox-manager.py"

app = Flask(__name__, template_folder=str(SCRIPT_DIR / "templates"))


def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    return cfg


def load_instances():
    cfg = load_config()
    state_path = Path(cfg.get("paths", "state_dir")) / "instances.json"
    if not state_path.exists():
        return {}
    with open(state_path) as f:
        return json.load(f)


def run_manager(command, team=None):
    """Run pwnbox-manager.py as a subprocess and capture output."""
    cmd = [sys.executable, str(MANAGER), command]
    if team:
        cmd.append(team)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


@app.route("/")
def index():
    cfg = load_config()
    instances = load_instances()
    max_instances = cfg.getint("general", "max_instances")
    ttl = cfg.getint("general", "instance_ttl_hours")
    return render_template("portal.html",
                           instances=instances,
                           max_instances=max_instances,
                           ttl_hours=ttl,
                           current_count=len(instances))


@app.route("/api/create", methods=["POST"])
def api_create():
    data = request.get_json()
    team = data.get("team", "").strip()
    if not team:
        return jsonify({"error": "Team name required"}), 400

    code, stdout, stderr = run_manager("create", team)
    if code != 0:
        # Extract error message
        error = stderr.strip() or stdout.strip()
        return jsonify({"error": error}), 400

    # Load the generated config
    cfg = load_config()
    conf_path = Path(cfg.get("paths", "state_dir")) / "configs" / f"{team}.conf"
    wg_config = conf_path.read_text() if conf_path.exists() else ""

    instances = load_instances()
    inst = instances.get(team, {})

    return jsonify({
        "status": "ok",
        "team": team,
        "container_ip": inst.get("container_ip", ""),
        "wg_ip": inst.get("wg_ip", ""),
        "expires_at": inst.get("expires_at", ""),
        "wg_config": wg_config,
        "app_port": cfg.get("general", "container_app_port"),
    })


@app.route("/api/destroy", methods=["POST"])
def api_destroy():
    data = request.get_json()
    team = data.get("team", "").strip()
    if not team:
        return jsonify({"error": "Team name required"}), 400

    code, stdout, stderr = run_manager("destroy", team)
    if code != 0:
        error = stderr.strip() or stdout.strip()
        return jsonify({"error": error}), 400

    return jsonify({"status": "ok"})


@app.route("/api/status")
def api_status():
    instances = load_instances()
    cfg = load_config()
    now = datetime.now(timezone.utc)
    result = {}

    for team, inst in instances.items():
        expires = datetime.fromisoformat(inst["expires_at"])
        remaining = (expires - now).total_seconds()
        result[team] = {
            "container_ip": inst["container_ip"],
            "expires_at": inst["expires_at"],
            "expired": remaining <= 0,
            "remaining_minutes": max(0, int(remaining / 60)),
        }

    return jsonify({
        "instances": result,
        "total": len(result),
        "max": cfg.getint("general", "max_instances"),
    })


@app.route("/api/config/<team>")
def api_download_config(team):
    cfg = load_config()
    conf_path = Path(cfg.get("paths", "state_dir")) / "configs" / f"{team}.conf"
    if not conf_path.exists():
        return jsonify({"error": "Config not found"}), 404
    return send_file(conf_path, as_attachment=True, download_name=f"pwnbox-{team}.conf")


if __name__ == "__main__":
    cfg = load_config()
    host = cfg.get("portal", "host", fallback="0.0.0.0")
    port = cfg.getint("portal", "port", fallback=8888)
    secret = cfg.get("portal", "secret_key", fallback="change-me")
    app.secret_key = secret
    print(f"PwnBox Portal running on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
