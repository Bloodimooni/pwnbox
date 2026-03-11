# CTF Challenges

[Back to Index](README.md)

---

## Overview

CorpChat contains **five hidden flags** spread across escalating difficulty levels. Each flag is embedded in a realistic vulnerability or misconfigurations scenario. Players interact with the same CorpChat instance throughout: every flag leads deeper into the system.

| # | Flag | Category | Difficulty | Responsible |
|---|------|----------|------------|-------------|
| 1 | `CTF{exposed_git_repository_secret}` | Misconfiguration / OSINT | Easy | Svenja |
| 2 | `CTF{idor_token_auth_bypass_privesc_complete}` | IDOR / SQLi / API Abuse | Medium | Svenja |
| 3 | `ufoundit` | Cryptography / Hash Cracking | Medium | Laura |
| 4 | `CTF{r3v_3ng_b4ackd00r_4cc3ss!}` | Reverse Engineering | Medium-Hard | Joshua |
| 5 | `CTF{w1ldcard_t4r_g0t_r00t!}` | Privilege Escalation | Hard | Joshua |

For a complete step-by-step walkthrough of every flag see [CTF Walkthrough](writeup/ctf-walkthrough.md).

---

## Flag 1 — Exposed Git Repository

**Category:** Misconfiguration / OSINT
**Flag:** `CTF{exposed_git_repository_secret}`

### What Was Added

A fake git repository is pre-seeded under `/static/challenge/`. The `.git` directory is fully intact and accessible over HTTP. The repository contains a real commit history with a secret embedded in an early commit.

The repository is built by `ctfrepo.sh`, a Python-based script that creates raw git objects (blobs, trees, commits) without ever calling `git init`. This produces an authentic git object store that the `git` CLI can clone and traverse.

**Entry point:** Navigate to `http://<instance-ip>/challenge/` in a browser. The directory listing reveals `.git/`.

### How It Works

The Flask application (`app.py`) serves the `/static/challenge/` directory as-is. When the `.git` directory is accessible over HTTP, an attacker can:

1. Fetch `/.git/HEAD` to find the current branch reference.
2. Walk `/.git/refs/` to enumerate commits.
3. Fetch commit, tree, and blob objects from `/.git/objects/` to reconstruct the repository.

Tools like `git-dumper` automate this entirely.

**See:** [Git Challenge Writeup](writeup/git-challenge-writeup.md)

---

## Flag 2 — IDOR / Token Auth Bypass

**Category:** IDOR / SQL Injection / API Abuse
**Flag:** `CTF{idor_token_auth_bypass_privesc_complete}`

### What Was Added

The flag is hidden in a DM conversation between `chatbot` (user id=2) and `manager_bob` (user id=4). `manager_bob`'s API token is hard-coded to a fixed UUID (`7f3d9e2a-1b4c-4f8e-a3d7-5c9b0e6f2a1d`) to make it reachable after the IDOR step.

The search endpoint (`routes/search2.py`) contains an intentional SQL injection in the token lookup query, allowing players to extract the `password_resets` table and recover `sarah_chen`'s pre-approved reset token. After using the token to log in as `sarah_chen`, players can discover and enumerate the API to find `manager_bob`'s hard-coded token.

### How It Works

1. SQL injection in `/search?q=` exposes the `password_resets` table.
2. Sarah's pre-approved token allows login without knowing her password.
3. From Sarah's perspective, `manager_bob`'s user id (4) is visible via the user list or profile pages.
4. Fetching `/api/v1/users/4` while authenticated reveals `manager_bob`'s hard-coded `api_token`.
5. Using that token to call `/api/v1/dm/conversations` as `manager_bob` reveals the conversation with `chatbot`.
6. Reading the DM reveals the flag.

**See:** [IDOR Challenge Writeup](writeup/idor-challenge-writeup.md)

---

## Flag 3 — Weak Cryptography / Hash Cracking

**Category:** Cryptography
**Flag:** `ufoundit`

### What Was Added

Every user row in the database has a `legacy_password_hash` column containing the base64-encoding of the raw MD5 digest (`base64(MD5(password))`). This is a deliberately weak "legacy" hashing scheme.

For all normal users the legacy plaintext is just their regular password. For the bot account `compliancebot`, the legacy plaintext is the flag:

```python
'compliancebot': ('ufoundit', None)
```

Players discover the database after gaining SSH access (via Flag 4 credentials) or via the SQL injection on the search endpoint. They dump the `users` table, see base64 strings, decode each to get the raw MD5 bytes, and crack `compliancebot`'s hash with RockYou.txt to reveal the flag.

### How It Works

1. Player gains SSH or web access and dumps `corpchat.db`.
2. Runs `sqlite3 corpchat.db "SELECT username, legacy_password_hash FROM users"`.
3. Recognises the 24-character base64 strings (ending in `==`), decodes to 16 raw bytes.
4. Converts raw bytes to hex to get the MD5 digest.
5. Cracks with hashcat mode 0: `hashcat -m 0 <md5hex> /usr/share/wordlists/rockyou.txt`.
6. Cracked plaintext `ufoundit` is the flag.

**See:** [Crypto Challenge Writeup](writeup/crypto-challenge-writeup.md)

---

## Flag 4 — Reverse Engineering

**Category:** Reverse Engineering / Binary Analysis
**Flag:** `CTF{r3v_3ng_b4ackd00r_4cc3ss!}`

### What Was Added

`entrypoint.py` seeds a compiled binary `corpchat-admin` into `/data/uploads/tools/` at container startup. The binary implements a simple admin CLI tool with XOR-encoded backdoor credentials and a hidden maintenance menu reachable only via option `69`.

Source code lives in `reversing-challenge/admin-tools.c`. The binary is compiled during the Docker image build.

### How It Works

1. Player finds `/data/uploads/tools/corpchat-admin` (accessible after RCE or via file download).
2. Runs `strings` on the binary to spot `xor_decode`, `enc_backdoor_user`, `enc_backdoor_pass`, and the hidden maintenance menu strings.
3. Loads the binary in Ghidra or uses `ltrace` to extract the XOR key and encoded byte arrays.
4. Decodes the credentials: `svc_backup` / `netterFeger69#`.
5. Logs in; enters hidden option `69` to reach the maintenance menu.
6. Selects option `3` (Decrypt Master Key) to print the flag.

**See:** [Reverse Engineering Writeup](writeup/re-challenge-writeup.md)

---

## Flag 5 — Privilege Escalation (Wildcard Tar)

**Category:** Linux Privilege Escalation
**Flag:** `CTF{w1ldcard_t4r_g0t_r00t!}`

### What Was Added

`entrypoint.py` (running as root before the privilege drop) writes `/root/flag.txt` and installs a cron job at `/etc/cron.d/corpchat-backup`:

```
* * * * * root cd /data/uploads && tar -czf /tmp/uploads_backup.tar.gz *
```

The `/data/uploads` directory is world-writable (`chmod 777`). The cron job runs as root every minute and uses a wildcard `*` in the `tar` command, which is vulnerable to argument injection via specially named files.

### How It Works

1. Player gains a shell as `corpchat` (via web RCE or SSH with Flag 4 credentials).
2. Discovers the cron job by reading `/etc/cron.d/corpchat-backup`.
3. Creates exploit files in `/data/uploads`:
   - `--checkpoint=1`
   - `--checkpoint-action=exec=sh exploit.sh`
   - `exploit.sh` (the payload script)
4. When cron fires, tar expands `*` and processes the filenames as command-line flags, executing the payload as root.
5. Payload reads `/root/flag.txt` and writes it somewhere readable, or establishes a root shell.

**See:** [Privilege Escalation Writeup](writeup/privesc-challenge-writeup.md)

---

## Challenge Flow Summary

The intended attack path progresses through the five flags in order:

```
[1] Exposed .git repo   →   discover commit secrets & repo context
        ↓
[2] SQLi → IDOR → DM   →   escalate to manager_bob's DM conversation
        ↓
[3] SSH access + DB dump →  crack legacy MD5 hashes, find crypto flag
        ↓
[4] Binary on filesystem →  reverse-engineer XOR encoding, get backdoor creds
        ↓
[5] Shell as corpchat   →   exploit wildcard tar cron, read /root/flag.txt
```

Each flag unlocks context or access needed for the next stage. Players are not required to follow this order, but it is the intended path.

---

## Flag Submission

Flags are submitted through the CTF player portal at `http://<host>:8888`. Navigate to your team dashboard, enter the flag string exactly as shown (including the `CTF{...}` wrapper), and click Submit. Each flag is worth points; first-blood solves are tracked on the leaderboard.
