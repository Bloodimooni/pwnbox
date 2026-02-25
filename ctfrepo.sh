#!/bin/bash
set -e

REPO_PATH="."
CHALLENGE_DIR="static/challenge"
FLAG="FLAG{exposed_git_repository_secret}"

cd "$REPO_PATH"

# Create browseable .git directory with custom Git history 
if [ ! -d "$CHALLENGE_DIR/.git" ]; then
    echo "[*] Building CTF Git repository with exposed history..."
    
    python3 - << 'PYTHON_SCRIPT'
import os
import hashlib
import zlib
import struct

FLAG = "FLAG{exposed_git_repository_secret}"
REPO_PATH = "."
CHALLENGE_DIR = "static/challenge"

def create_git_objects():
    """Create a full .git directory with malicious commit history"""
    
    git_dir = os.path.join(REPO_PATH, CHALLENGE_DIR, ".git")
    
    # Create directory structure
    os.makedirs(os.path.join(git_dir, "objects", "info"), exist_ok=True)
    os.makedirs(os.path.join(git_dir, "objects", "pack"), exist_ok=True)
    os.makedirs(os.path.join(git_dir, "refs", "heads"), exist_ok=True)
    os.makedirs(os.path.join(git_dir, "refs", "tags"), exist_ok=True)
    os.makedirs(os.path.join(git_dir, "hooks"), exist_ok=True)
    os.makedirs(os.path.join(git_dir, "info"), exist_ok=True)
    
    # Create git config
    config_content = """[core]
\trepositoryformatversion = 0
\tfilemode = true
\tlogallrefupdates = true
\tbareRepository = false
[user]
\temail = ctf@example.com
\tname = CTF Player
"""
    with open(os.path.join(git_dir, "config"), "w") as f:
        f.write(config_content)
    
    # Create description file
    with open(os.path.join(git_dir, "description"), "w") as f:
        f.write("Unnamed repository; edit this file 'description' to name the repository.\n")
    
    # === Commit 1: Initial commit WITH FLAG ===
    config_v1_content = f'''import os
from datetime import timedelta

class Config:
    SECRET_KEY = "SUPER_SECRET_KEY_PRODUCTION"
    FLAG = "{FLAG}"
    SESSION_COOKIE_SECURE = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY = "dev-secret-key"

class ProductionConfig(Config):
    DEBUG = False
'''
    
    # === Commit 2: Removed FLAG ===
    config_v2_content = '''import os
from datetime import timedelta

class Config:
    SECRET_KEY = "SUPER_SECRET_KEY_PRODUCTION"
    SESSION_COOKIE_SECURE = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY = "dev-secret-key"

class ProductionConfig(Config):
    DEBUG = False
'''
    
    def create_blob(content):
        """Create a git blob object (file content)"""
        if isinstance(content, str):
            content = content.encode()
        blob_header = b"blob " + str(len(content)).encode() + b"\x00"
        full_content = blob_header + content
        obj_hash = hashlib.sha1(full_content).hexdigest()
        compressed = zlib.compress(full_content)
        
        obj_dir = os.path.join(git_dir, "objects", obj_hash[:2])
        os.makedirs(obj_dir, exist_ok=True)
        with open(os.path.join(obj_dir, obj_hash[2:]), "wb") as f:
            f.write(compressed)
        
        return obj_hash, len(content)
    
    def create_tree(entries):
        """Create a git tree object (directory listing)
        entries: list of (mode, name, sha1_hex)
        """
        tree_content = b""
        for mode, name, sha1_hex in entries:
            mode_str = f"{int(mode):o}".encode()  # Convert to octal
            tree_content += mode_str + b" " + name.encode() + b"\x00" + bytes.fromhex(sha1_hex)
        
        tree_header = b"tree " + str(len(tree_content)).encode() + b"\x00"
        full_content = tree_header + tree_content
        obj_hash = hashlib.sha1(full_content).hexdigest()
        compressed = zlib.compress(full_content)
        
        obj_dir = os.path.join(git_dir, "objects", obj_hash[:2])
        os.makedirs(obj_dir, exist_ok=True)
        with open(os.path.join(obj_dir, obj_hash[2:]), "wb") as f:
            f.write(compressed)
        
        return obj_hash
    
    def create_commit(tree_hash, message, author_name="CTF Player", author_email="ctf@example.com", 
                     timestamp="1640000000", parent_hash=None):
        """Create a git commit object"""
        commit_lines = [f"tree {tree_hash}"]
        
        if parent_hash:
            commit_lines.append(f"parent {parent_hash}")
        
        timestamp_tz = f"{timestamp} +0000"
        commit_lines.append(f"author {author_name} <{author_email}> {timestamp_tz}")
        commit_lines.append(f"committer {author_name} <{author_email}> {timestamp_tz}")
        commit_lines.append("")
        commit_lines.append(message)
        
        commit_content = "\n".join(commit_lines).encode()
        commit_header = b"commit " + str(len(commit_content)).encode() + b"\x00"
        full_content = commit_header + commit_content
        obj_hash = hashlib.sha1(full_content).hexdigest()
        compressed = zlib.compress(full_content)
        
        obj_dir = os.path.join(git_dir, "objects", obj_hash[:2])
        os.makedirs(obj_dir, exist_ok=True)
        with open(os.path.join(obj_dir, obj_hash[2:]), "wb") as f:
            f.write(compressed)
        
        return obj_hash
    
    # === Create blob for config with FLAG ===
    print("[*] Creating blob (config with FLAG)...")
    blob1_hash, _ = create_blob(config_v1_content)
    print(f"    Blob 1 (with FLAG): {blob1_hash}")
    
    # === Create blob for config without FLAG ===
    print("[*] Creating blob (config without FLAG)...")
    blob2_hash, _ = create_blob(config_v2_content)
    print(f"    Blob 2 (clean): {blob2_hash}")
    
    # === Create tree for commit 1 ===
    print("[*] Creating tree objects...")
    tree1_hash = create_tree([("100644", "config.py", blob1_hash)])
    print(f"    Tree 1: {tree1_hash}")
    
    # === Create tree for commit 2 ===
    tree2_hash = create_tree([("100644", "config.py", blob2_hash)])
    print(f"    Tree 2: {tree2_hash}")
    
    # === Create commit 1 (with FLAG) ===
    print("[*] Creating commits...")
    commit1_hash = create_commit(
        tree1_hash,
        "Initial commit: Add configuration with secrets",
        timestamp="1640000000"
    )
    print(f"    Commit 1 (with FLAG): {commit1_hash}")
    
    # === Create commit 2 (cleaned, parent=commit1) ===
    commit2_hash = create_commit(
        tree2_hash,
        "Remove sensitive data from config",
        timestamp="1640000100",
        parent_hash=commit1_hash
    )
    print(f"    Commit 2 (clean): {commit2_hash}")
    
    # === Create HEAD reference ===
    head_path = os.path.join(git_dir, "HEAD")
    with open(head_path, "w") as f:
        f.write("ref: refs/heads/master\n")
    print("[*] Created HEAD reference")
    
    # === Create master branch reference ===
    master_path = os.path.join(git_dir, "refs", "heads", "master")
    with open(master_path, "w") as f:
        f.write(commit2_hash + "\n")
    print("[*] Created master branch (pointing to latest commit)")
    
    # === Create packed-refs (for reference integrity) ===
    packed_refs_path = os.path.join(git_dir, "packed-refs")
    with open(packed_refs_path, "w") as f:
        f.write("# pack-refs with: peeled fully-peeled\n")
        f.write(f"{commit2_hash} refs/heads/master\n")
    
    print("\n[+] Git repository structure created successfully!")
    print(f"[+] Challenge repository at: {CHALLENGE_DIR}")
    print(f"[+] Download URL: http://target/challenge/")
    print(f"[+] Git log will show:")
    print(f"    - Commit 2 (HEAD): Remove sensitive data")
    print(f"    - Commit 1 (history): Initial commit with FLAG")

create_git_objects()
PYTHON_SCRIPT

    # Create README for attackers
    mkdir -p "$CHALLENGE_DIR"
    cat > "$CHALLENGE_DIR/README.md" <<'READMEEOF'
# CTF Challenge - Exposed Git Repository

## Description
This is an exposed Git repository that was accidentally published to the web server. 
The repository contains sensitive information in its commit history.

## Challenge
Find the hidden flag in the Git commit history!

## How to solve

### Option 1: Download and examine locally
```bash
wget -r http://target/challenge/
cd challenge
git log --oneline
git show <commit-hash>
```

### Option 2: Clone the repository
```bash
git clone http://target/challenge/ ctf-challenge
cd ctf-challenge
git log
git show HEAD~1
```

### Option 3: Examine online
```bash
git ls-remote http://target/challenge/
```

## Hints
- Use `git log` to see commit messages
- Use `git show` to view file contents at specific commits
- The flag is hidden in an earlier commit that was "removed"
- Try examining the parent commits

## Flag Format
The flag is in the format: `FLAG{...}`

READMEEOF

    echo ""
    echo "[✓] CTF challenge created successfully!"
    echo "[✓] Repository is browseable and downloadable at /challenge/"
fi


