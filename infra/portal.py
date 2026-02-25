#!/usr/bin/env python3
"""PwnBox CTF Self-Service Portal

King of the Hill CTF platform with user accounts, teams, flag submission,
and a leaderboard. Run on the host machine.

Usage: python3 portal.py
"""

import configparser
import json
import os
import string
import subprocess
import sys
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import bcrypt
from flask import Flask, render_template, request, jsonify, session

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.ini"
MANAGER = SCRIPT_DIR / "pwnbox-manager.py"

app = Flask(__name__, template_folder=str(SCRIPT_DIR / "templates"))


# --- Config & State helpers ---

def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    return cfg


def state_dir():
    cfg = load_config()
    p = Path(cfg.get("paths", "state_dir"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_json(filename, default=None):
    path = state_dir() / filename
    if not path.exists():
        return default if default is not None else {}
    with open(path) as f:
        return json.load(f)


def _save_json(filename, data):
    path = state_dir() / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_users():
    return _load_json("users.json", {})


def save_users(users):
    _save_json("users.json", users)


def load_teams():
    return _load_json("teams.json", {})


def save_teams(teams):
    _save_json("teams.json", teams)


def load_instances():
    return _load_json("instances.json", {})


def load_submissions():
    return _load_json("submissions.json", {})


def save_submissions(subs):
    _save_json("submissions.json", subs)


def load_flags():
    path = SCRIPT_DIR / "flags.json"
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def run_manager(command, team=None):
    cmd = [sys.executable, str(MANAGER), command]
    if team:
        cmd.append(team)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def generate_join_code():
    return os.urandom(4).hex()


# --- Auth decorators ---

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return jsonify({"error": "Not authenticated"}), 401
        return f(*args, **kwargs)
    return decorated


def captain_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return jsonify({"error": "Not authenticated"}), 401
        if not session.get("is_captain"):
            return jsonify({"error": "Only the team captain can do this"}), 403
        if not session.get("team"):
            return jsonify({"error": "You are not on a team"}), 403
        return f(*args, **kwargs)
    return decorated


# --- Routes ---

@app.route("/")
def index():
    cfg = load_config()
    ttl = cfg.getint("general", "instance_ttl_hours")
    return render_template("portal.html", ttl_hours=ttl)


# --- Auth API ---

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json()
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    event_password = data.get("event_password", "")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    if len(username) < 3 or len(username) > 32:
        return jsonify({"error": "Username must be 3-32 characters"}), 400

    allowed = set(string.ascii_lowercase + string.digits + "_-")
    if not all(c in allowed for c in username):
        return jsonify({"error": "Username: letters, numbers, hyphens, underscores only"}), 400

    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters"}), 400

    cfg = load_config()
    expected_event_pw = cfg.get("portal", "event_password", fallback="")
    if not expected_event_pw or event_password != expected_event_pw:
        return jsonify({"error": "Invalid event password"}), 403

    users = load_users()
    if username in users:
        return jsonify({"error": "Username already taken"}), 409

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    users[username] = {
        "password_hash": pw_hash,
        "team": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_users(users)

    session["username"] = username
    session["team"] = None
    session["is_captain"] = False

    return jsonify({"status": "ok", "username": username})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")

    users = load_users()
    user = users.get(username)
    if not user:
        return jsonify({"error": "Invalid username or password"}), 401

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "Invalid username or password"}), 401

    team_name = user.get("team")
    is_captain = False
    if team_name:
        teams = load_teams()
        team_data = teams.get(team_name)
        if team_data:
            is_captain = team_data["captain"] == username

    session["username"] = username
    session["team"] = team_name
    session["is_captain"] = is_captain

    return jsonify({"status": "ok", "username": username})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"status": "ok"})


# --- User info ---

@app.route("/api/me")
@login_required
def api_me():
    username = session["username"]
    users = load_users()
    user = users.get(username)
    if not user:
        session.clear()
        return jsonify({"error": "User not found"}), 401

    # Refresh session state from stored data
    team_name = user.get("team")
    is_captain = False
    if team_name:
        teams = load_teams()
        team_data = teams.get(team_name)
        if team_data:
            is_captain = team_data["captain"] == username
        else:
            team_name = None

    session["team"] = team_name
    session["is_captain"] = is_captain

    return jsonify({
        "username": username,
        "team": team_name,
        "is_captain": is_captain,
    })


# --- Team API ---

@app.route("/api/team/create", methods=["POST"])
@login_required
def api_team_create():
    data = request.get_json()
    team_name = data.get("team_name", "").strip().lower()

    if not team_name or len(team_name) < 2 or len(team_name) > 32:
        return jsonify({"error": "Team name must be 2-32 characters"}), 400

    allowed = set(string.ascii_lowercase + string.digits + "_-")
    if not all(c in allowed for c in team_name):
        return jsonify({"error": "Team name: letters, numbers, hyphens, underscores only"}), 400

    username = session["username"]
    users = load_users()
    if users[username].get("team"):
        return jsonify({"error": "You are already on a team"}), 400

    teams = load_teams()
    if team_name in teams:
        return jsonify({"error": "Team name already taken"}), 409

    cfg = load_config()
    max_teams = cfg.getint("general", "max_instances")
    if len(teams) >= max_teams:
        return jsonify({"error": f"Maximum number of teams ({max_teams}) reached"}), 400

    join_code = generate_join_code()
    teams[team_name] = {
        "captain": username,
        "join_code": join_code,
        "members": [username],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_teams(teams)

    users[username]["team"] = team_name
    save_users(users)

    session["team"] = team_name
    session["is_captain"] = True

    return jsonify({"status": "ok", "team_name": team_name, "join_code": join_code})


@app.route("/api/team/join", methods=["POST"])
@login_required
def api_team_join():
    data = request.get_json()
    join_code = data.get("join_code", "").strip()

    if not join_code:
        return jsonify({"error": "Join code required"}), 400

    username = session["username"]
    users = load_users()
    if users[username].get("team"):
        return jsonify({"error": "You are already on a team"}), 400

    teams = load_teams()
    target_team = None
    for tname, tdata in teams.items():
        if tdata["join_code"] == join_code:
            target_team = tname
            break

    if not target_team:
        return jsonify({"error": "Invalid join code"}), 404

    teams[target_team]["members"].append(username)
    save_teams(teams)

    users[username]["team"] = target_team
    save_users(users)

    session["team"] = target_team
    session["is_captain"] = False

    return jsonify({"status": "ok", "team_name": target_team})


@app.route("/api/team")
@login_required
def api_team_info():
    username = session["username"]
    team_name = session.get("team")
    if not team_name:
        return jsonify({"error": "You are not on a team"}), 404

    teams = load_teams()
    team = teams.get(team_name)
    if not team:
        return jsonify({"error": "Team not found"}), 404

    is_captain = team["captain"] == username

    # Get instance info if exists
    instances = load_instances()
    instance = instances.get(team_name)
    instance_info = None
    if instance:
        cfg = load_config()
        expires = datetime.fromisoformat(instance["expires_at"])
        now = datetime.now(timezone.utc)
        remaining = (expires - now).total_seconds()
        instance_info = {
            "container_ip": instance["container_ip"],
            "netbird_ip": instance.get("netbird_ip", ""),
            "expires_at": instance["expires_at"],
            "remaining_minutes": max(0, int(remaining / 60)),
            "expired": remaining <= 0,
            "paused": instance.get("paused", False),
            "app_port": cfg.get("general", "container_app_port"),
            "netbird_setup_key": cfg.get("netbird", "player_setup_key"),
            "netbird_management_url": cfg.get("netbird", "management_url"),
        }

    # Get team submissions
    subs = load_submissions()
    team_subs = subs.get(team_name, {})

    result = {
        "team_name": team_name,
        "captain": team["captain"],
        "members": team["members"],
        "is_captain": is_captain,
        "instance": instance_info,
        "score": team_subs.get("score", 0),
        "flags_found": len(team_subs.get("flags", [])),
    }

    if is_captain:
        result["join_code"] = team["join_code"]

    return jsonify(result)


# --- Instance API (captain only) ---

@app.route("/api/instance/launch", methods=["POST"])
@captain_required
def api_instance_launch():
    team_name = session["team"]
    code, stdout, stderr = run_manager("create", team_name)
    if code != 0:
        error = stderr.strip() or stdout.strip()
        return jsonify({"error": error}), 400

    instances = load_instances()
    inst = instances.get(team_name, {})
    cfg = load_config()

    return jsonify({
        "status": "ok",
        "container_ip": inst.get("container_ip", ""),
        "netbird_ip": inst.get("netbird_ip", ""),
        "expires_at": inst.get("expires_at", ""),
        "app_port": cfg.get("general", "container_app_port"),
        "netbird_setup_key": cfg.get("netbird", "player_setup_key"),
        "netbird_management_url": cfg.get("netbird", "management_url"),
    })


@app.route("/api/instance/destroy", methods=["POST"])
@captain_required
def api_instance_destroy():
    team_name = session["team"]
    code, stdout, stderr = run_manager("destroy", team_name)
    if code != 0:
        error = stderr.strip() or stdout.strip()
        return jsonify({"error": error}), 400

    return jsonify({"status": "ok"})


@app.route("/api/instance/pause", methods=["POST"])
@captain_required
def api_instance_pause():
    team_name = session["team"]
    code, stdout, stderr = run_manager("pause", team_name)
    if code != 0:
        error = stderr.strip() or stdout.strip()
        return jsonify({"error": error}), 400

    return jsonify({"status": "ok"})


@app.route("/api/instance/resume", methods=["POST"])
@captain_required
def api_instance_resume():
    team_name = session["team"]
    code, stdout, stderr = run_manager("resume", team_name)
    if code != 0:
        error = stderr.strip() or stdout.strip()
        return jsonify({"error": error}), 400

    return jsonify({"status": "ok"})


# --- Flag API ---

@app.route("/api/flag", methods=["POST"])
@login_required
def api_flag_submit():
    username = session["username"]
    team_name = session.get("team")
    if not team_name:
        return jsonify({"error": "You must be on a team to submit flags"}), 403

    data = request.get_json()
    flag = data.get("flag", "").strip()
    if not flag:
        return jsonify({"error": "Flag required"}), 400

    valid_flags = load_flags()
    if flag not in valid_flags:
        return jsonify({"error": "Invalid flag"}), 400

    subs = load_submissions()
    if team_name not in subs:
        subs[team_name] = {"flags": [], "score": 0, "submissions": []}

    team_subs = subs[team_name]
    if flag in team_subs["flags"]:
        return jsonify({"error": "Flag already submitted by your team"}), 409

    team_subs["flags"].append(flag)
    team_subs["score"] += 100
    team_subs["submissions"].append({
        "flag": flag,
        "by": username,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    save_submissions(subs)

    return jsonify({
        "status": "ok",
        "score": team_subs["score"],
        "total_flags": len(team_subs["flags"]),
    })


@app.route("/api/team/flags")
@login_required
def api_team_flags():
    team_name = session.get("team")
    if not team_name:
        return jsonify({"error": "You must be on a team"}), 403

    subs = load_submissions()
    team_subs = subs.get(team_name, {"flags": [], "score": 0, "submissions": []})
    total_flags = len(load_flags())

    return jsonify({
        "score": team_subs["score"],
        "flags_found": len(team_subs["flags"]),
        "total_flags": total_flags,
        "submissions": team_subs["submissions"],
    })


# --- Leaderboard ---

@app.route("/api/leaderboard")
def api_leaderboard():
    subs = load_submissions()
    teams = load_teams()
    total_flags = len(load_flags())

    board = []
    for team_name, team_subs in subs.items():
        board.append({
            "team": team_name,
            "score": team_subs.get("score", 0),
            "flags_found": len(team_subs.get("flags", [])),
            "total_flags": total_flags,
            "members": len(teams.get(team_name, {}).get("members", [])),
        })

    board.sort(key=lambda x: x["score"], reverse=True)

    # Add rank
    for i, entry in enumerate(board):
        entry["rank"] = i + 1

    return jsonify({"leaderboard": board, "total_flags": total_flags})


if __name__ == "__main__":
    cfg = load_config()
    host = cfg.get("portal", "host", fallback="0.0.0.0")
    port = cfg.getint("portal", "port", fallback=8888)
    secret = cfg.get("portal", "secret_key", fallback="NUBU4Q95W9LAH5G7GO0M4XVTBMS4EZC6")
    app.secret_key = secret
    print(f"PwnBox Portal running on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
