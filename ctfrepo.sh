#!/bin/bash
# --- .git exposure challenge — Svenja ---
set -e

# Resolve the script's own directory so it works from anywhere
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHALLENGE_DIR="$SCRIPT_DIR/static/challenge"
FLAG="CTF{exposed_git_repository_secret}"

# Only build if .git doesn't exist yet (idempotent)
if [ -d "$CHALLENGE_DIR/.git" ]; then
    echo "[i] Challenge directory already exists at $CHALLENGE_DIR"
    echo "[i] Delete $CHALLENGE_DIR/.git to rebuild."
    exit 0
fi

echo "[*] Building CTF Git repository challenge..."

python3 - "$CHALLENGE_DIR" "$FLAG" << 'PYTHON_SCRIPT'
import os
import sys
import hashlib
import zlib

CHALLENGE_DIR = sys.argv[1]
FLAG = sys.argv[2]

def create_blob(git_dir, content):
    """Create and store a git blob object. Returns sha1 hex string."""
    if isinstance(content, str):
        content = content.encode()
    header = b"blob " + str(len(content)).encode() + b"\x00"
    full = header + content
    sha1 = hashlib.sha1(full).hexdigest()
    obj_dir = os.path.join(git_dir, "objects", sha1[:2])
    obj_path = os.path.join(obj_dir, sha1[2:])
    os.makedirs(obj_dir, exist_ok=True)
    if not os.path.exists(obj_path):
        with open(obj_path, "wb") as f:
            f.write(zlib.compress(full))
    return sha1


def create_tree(git_dir, entries):
    """Create and store a git tree object.
    entries: list of (mode_str, name, sha1_hex)
    mode_str should be the literal git mode string e.g. '100644' or '40000'
    """
    tree_data = b""
    for mode_str, name, sha1_hex in entries:
        # Git tree format: "<mode> <name>\0<20-byte-sha1>"
        # mode_str is already the correct ASCII octal string (e.g. "100644")
        tree_data += mode_str.encode() + b" " + name.encode() + b"\x00" + bytes.fromhex(sha1_hex)

    header = b"tree " + str(len(tree_data)).encode() + b"\x00"
    full = header + tree_data
    sha1 = hashlib.sha1(full).hexdigest()
    obj_dir = os.path.join(git_dir, "objects", sha1[:2])
    obj_path = os.path.join(obj_dir, sha1[2:])
    os.makedirs(obj_dir, exist_ok=True)
    if not os.path.exists(obj_path):
        with open(obj_path, "wb") as f:
            f.write(zlib.compress(full))
    return sha1


def create_commit(git_dir, tree_hash, message, author="Dev Bot",
                  email="devbot@corpchat.internal", timestamp="1704067200",
                  parent_hash=None):
    """Create and store a git commit object. Returns sha1 hex string."""
    lines = [f"tree {tree_hash}"]
    if parent_hash:
        lines.append(f"parent {parent_hash}")
    ts = f"{timestamp} +0000"
    lines.append(f"author {author} <{email}> {ts}")
    lines.append(f"committer {author} <{email}> {ts}")
    lines.append("")
    lines.append(message)

    content = "\n".join(lines).encode()
    header = b"commit " + str(len(content)).encode() + b"\x00"
    full = header + content
    sha1 = hashlib.sha1(full).hexdigest()
    obj_dir = os.path.join(git_dir, "objects", sha1[:2])
    obj_path = os.path.join(obj_dir, sha1[2:])
    os.makedirs(obj_dir, exist_ok=True)
    if not os.path.exists(obj_path):
        with open(obj_path, "wb") as f:
            f.write(zlib.compress(full))
    return sha1


def build_repo():
    git_dir = os.path.join(CHALLENGE_DIR, ".git")

    # --- Create .git directory structure ---
    for sub in ["objects/info", "objects/pack", "refs/heads", "refs/tags", "hooks", "info"]:
        os.makedirs(os.path.join(git_dir, sub), exist_ok=True)

    # git config
    with open(os.path.join(git_dir, "config"), "w") as f:
        f.write("[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n"
                "\tlogallrefupdates = true\n[user]\n\tname = Dev Bot\n"
                "\temail = devbot@corpchat.internal\n"
                "[remote \"origin\"]\n\turl = git@git.corpchat.internal:platform/backend.git\n"
                "\tfetch = +refs/heads/*:refs/remotes/origin/*\n")

    with open(os.path.join(git_dir, "description"), "w") as f:
        f.write("CorpChat backend platform repository.\n")

    with open(os.path.join(git_dir, "info", "exclude"), "w") as f:
        f.write("# Git ignore patterns specific to this machine\n*.pyc\n__pycache__/\n.env\n")

    # =========================================================
    # COMMIT 1 — initial commit, contains the flag in config.py
    # =========================================================
    config_v1 = f"""\
import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'CHANGEME_BEFORE_DEPLOY')
    # Internal flag token used for audit trail verification
    FLAG = "{FLAG}"
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///app.db')


class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY = "dev-secret-only"
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
"""

    requirements_v1 = """\
Flask==3.0.0
Werkzeug==3.0.1
SQLAlchemy==2.0.23
python-dotenv==1.0.0
gunicorn==21.2.0
"""

    readme_v1 = """\
# CorpChat Backend

Internal messaging platform backend.

## Setup

```
pip install -r requirements.txt
flask run
```

## Notes

- See config.py for configuration options.
- Do NOT commit secrets to this repository.
"""

    print("[*] Creating commit 1 (with flag)...")
    blob_config_v1 = create_blob(git_dir, config_v1)
    blob_req_v1    = create_blob(git_dir, requirements_v1)
    blob_readme_v1 = create_blob(git_dir, readme_v1)

    tree1 = create_tree(git_dir, [
        ("100644", "README.md",       blob_readme_v1),
        ("100644", "config.py",       blob_config_v1),
        ("100644", "requirements.txt", blob_req_v1),
    ])
    commit1 = create_commit(
        git_dir, tree1,
        "Initial commit: project bootstrap with config",
        timestamp="1704067200"   # 2024-01-01 00:00:00 UTC
    )
    print(f"    Commit 1 SHA: {commit1}")

    # =========================================================
    # COMMIT 2 — flag removed from config.py ("oops")
    # =========================================================
    config_v2 = """\
import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'CHANGEME_BEFORE_DEPLOY')
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///app.db')


class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY = "dev-secret-only"
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
"""

    print("[*] Creating commit 2 (flag removed)...")
    blob_config_v2 = create_blob(git_dir, config_v2)

    tree2 = create_tree(git_dir, [
        ("100644", "README.md",       blob_readme_v1),
        ("100644", "config.py",       blob_config_v2),
        ("100644", "requirements.txt", blob_req_v1),
    ])
    commit2 = create_commit(
        git_dir, tree2,
        "Remove internal audit token from config (not for VCS)",
        timestamp="1704153600",   # 2024-01-02 00:00:00 UTC
        parent_hash=commit1
    )
    print(f"    Commit 2 SHA: {commit2}")

    # =========================================================
    # COMMIT 3 — routine update (HEAD)
    # =========================================================
    requirements_v3 = """\
Flask==3.0.0
Werkzeug==3.0.1
SQLAlchemy==2.0.23
python-dotenv==1.0.0
gunicorn==21.2.0
requests==2.31.0
"""

    print("[*] Creating commit 3 (HEAD, routine update)...")
    blob_req_v3 = create_blob(git_dir, requirements_v3)

    tree3 = create_tree(git_dir, [
        ("100644", "README.md",       blob_readme_v1),
        ("100644", "config.py",       blob_config_v2),
        ("100644", "requirements.txt", blob_req_v3),
    ])
    commit3 = create_commit(
        git_dir, tree3,
        "chore: bump requests dependency",
        timestamp="1704240000",   # 2024-01-03 00:00:00 UTC
        parent_hash=commit2
    )
    print(f"    Commit 3 SHA: {commit3}")

    # --- Write refs ---
    with open(os.path.join(git_dir, "HEAD"), "w") as f:
        f.write("ref: refs/heads/master\n")

    with open(os.path.join(git_dir, "refs", "heads", "master"), "w") as f:
        f.write(commit3 + "\n")

    # ORIG_HEAD points to commit before last push (makes it look like a real repo)
    with open(os.path.join(git_dir, "ORIG_HEAD"), "w") as f:
        f.write(commit2 + "\n")

    # COMMIT_EDITMSG (last commit message)
    with open(os.path.join(git_dir, "COMMIT_EDITMSG"), "w") as f:
        f.write("chore: bump requests dependency\n")

    # packed-refs
    with open(os.path.join(git_dir, "packed-refs"), "w") as f:
        f.write("# pack-refs with: peeled fully-peeled\n")
        f.write(f"{commit3} refs/heads/master\n")
        f.write(f"{commit3} refs/remotes/origin/master\n")

    print("\n[+] Git repository built successfully!")
    print(f"[+] Challenge dir : {CHALLENGE_DIR}")
    print(f"[+] HEAD          : {commit3[:12]}... (clean)")
    print(f"[+] Flag commit   : {commit1[:12]}... (commit 1 - initial)")
    print(f"[+] Accessible at : /challenge/")


build_repo()
PYTHON_SCRIPT

# Create a plain README at the challenge root (not inside .git)
mkdir -p "$CHALLENGE_DIR"
cat > "$CHALLENGE_DIR/README.md" << 'READMEEOF'
# CorpChat Backend — Source Mirror

This is a read-only mirror of the CorpChat backend repository,
exposed here for internal development reference.

## Hints

- The `.git/` directory is browseable.
- Try reconstructing the full commit history.
- Flag format: `CTF{...}`
READMEEOF

echo ""
echo "[✓] CTF git challenge created at $CHALLENGE_DIR"
echo "[✓] Browseable at /challenge/ (requires login)"
