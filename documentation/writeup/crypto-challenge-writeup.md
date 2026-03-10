# Crypto Challenge Writeup — Legacy Hash Cracking

**Category:** Cryptography
**Difficulty:** Medium
**Flag:** `CTF{md5_b64_l3g4cy_p4ss_cr4ck3d}`
**Responsible:** Laura

---

## Overview

Every user account in the CorpChat database has a `legacy_password_hash` column. This column contains an MD5 hash of the base64-encoding of the user's password — written as `MD5(base64(plaintext))`. For all normal users the plaintext is their regular password. For the compliance bot account `compliancebot`, the plaintext stored in this scheme is the flag itself.

Players discover the database, recognise the MD5 hash format, reverse-engineer the two-step scheme, and crack `compliancebot`'s hash to reveal the flag.

---

## Background: The Hashing Scheme

The scheme is seeded in `database.py`:

```python
def _legacy_hash(plaintext):
    b64 = base64.b64encode(plaintext.encode()).decode()
    return hashlib.md5(b64.encode()).hexdigest()

legacy_passwords = {
    'demo':        ('demo123',                             None),
    'chatbot':     ('bot12345',                            None),
    'sarah_chen':  ('sarah2024!',                          None),
    'manager_bob': ('b0bM@nager2024!',                     None),
    'compliancebot':   ('CTF{md5_b64_l3g4cy_p4ss_cr4ck3d}',   None),  # ← flag
}
```

### Why This Scheme Is Weak

| Problem | Explanation |
|---------|-------------|
| MD5 is broken | MD5 was deprecated for security use in 2004. It is extremely fast (billions of hashes/second on a GPU) |
| No salt | The same plaintext always produces the same hash. Precomputed rainbow tables can crack common passwords instantly |
| Base64 is reversible | Base64 adds no cryptographic value — it only changes the character set and length of the input |
| Single-byte XOR per character | Not applicable here, but the scheme is equivalent in weakness to MD5 of the raw plaintext |

The correct scheme for password storage is bcrypt, scrypt, or Argon2 — all of which are deliberately slow, salted, and memory-hard.

---

## Step 1 — Obtain the Database

### Path A: SSH with Stage 4 Credentials

Completing Stage 4 (reverse engineering) gives you SSH credentials:

```bash
ssh svc_backup@<ip>
# Password: netterFeger69#
```

The database file is at `/data/corpchat.db` and readable by `svc_backup` (the file is owned by the `corpchat` service account, but the group is readable):

```bash
# Check permissions
ls -la /data/corpchat.db

# Copy it to your attacker machine
exit
scp svc_backup@<ip>:/data/corpchat.db ./corpchat.db
```

### Path B: Admin Panel Backup

If you have admin panel access (`admin` / `admin2026!` at `/admin`):

1. Log in to the admin panel at `/admin`.
2. Click **Create Backup** in the top navigation bar.
3. The backup is stored at `/data/backups/corpchat_backup_YYYYMMDD_HHMMSS.db`.
4. Download it via the Files section or directly via SSH.

### Path C: SQL Injection

The Stage 2 SQL injection lets you dump the `users` table directly from the web:

```
/search?q=' UNION SELECT id, username, legacy_password_hash FROM users --
```

This extracts all five legacy hashes through the browser without needing file access.

---

## Step 2 — Inspect the Database

```bash
sqlite3 corpchat.db ".mode column" ".headers on" \
  "SELECT id, username, legacy_password_hash FROM users"
```

Output:

```
id  username     legacy_password_hash
--  -----------  --------------------------------
1   demo         <32-char hex>
2   chatbot      <32-char hex>
3   sarah_chen   <32-char hex>
4   manager_bob  <32-char hex>
5   compliancebot    <32-char hex>
```

All five values are 32-character hexadecimal strings — the exact length of an MD5 digest. Compare with bcrypt (which starts with `$2b$` and is 60 characters) — this confirms we are looking at raw MD5.

---

## Step 3 — Understand and Verify the Scheme

Before attacking the unknown hash, verify the scheme against an account whose password you know. `demo`'s password is `demo123`:

```python
import hashlib, base64

plaintext = 'demo123'
step1 = base64.b64encode(plaintext.encode()).decode()  # 'ZGVtbzEyMw=='
step2 = hashlib.md5(step1.encode()).hexdigest()
print(f"base64: {step1}")
print(f"md5:    {step2}")
```

Confirm the output matches what the database has for `demo`. You now have a verified understanding of the scheme.

---

## Step 4 — Extract the Target Hash

```bash
sqlite3 corpchat.db \
  "SELECT legacy_password_hash FROM users WHERE username='compliancebot'"
```

Save the hash:

```bash
sqlite3 corpchat.db \
  "SELECT legacy_password_hash FROM users WHERE username='compliancebot'" \
  > compliancebot.hash

cat compliancebot.hash
```

---

## Step 5 — Crack the Hash

### Method A — Hashcat (Standard MD5)

The `legacy_password_hash` column is MD5 of the base64 string — meaning the direct input to MD5 is the base64 of the plaintext. Hashcat mode `0` is raw MD5.

```bash
# Try rockyou wordlist — won't find it (flag is not a dictionary word)
hashcat -m 0 compliancebot.hash /usr/share/wordlists/rockyou.txt

# Hashcat can apply rules to transform words
# e.g., prepend CTF{, append }
hashcat -m 0 compliancebot.hash /usr/share/wordlists/rockyou.txt -r /usr/share/hashcat/rules/best64.rule
```

Standard wordlists won't crack this because the preimage (the base64 of the flag) is not a natural-language word. The preimage is:

```
Q1RGe21kNV9iNjRfbDNnNGN5X3A0c3NfY3I0Y2szZH0=
```

You would need to know this preimage in order for hashcat to find it. The more practical approach is Method B.

### Method B — Hashcat with Base64-Transformed Input

Hashcat supports rule-based attacks where it transforms the input before hashing. Using the `--rule-right` option with a base64 encode rule (if your hashcat version supports it), or creating a wordlist of pre-computed preimages:

```bash
# Generate a wordlist of CTF-format preimages
python3 -c "
import base64
candidates = [
    'CTF{md5_b64_l3g4cy_p4ss_cr4ck3d}',
]
for c in candidates:
    print(base64.b64encode(c.encode()).decode())
" > preimage_list.txt

# Crack using preimages directly as the MD5 input
hashcat -m 0 compliancebot.hash preimage_list.txt
```

### Method C — Python Script (Most Direct)

Since you know the scheme and suspect the flag format is `CTF{...}`, write a targeted cracker:

```python
import hashlib, base64, sqlite3

# Load the target hash
db = sqlite3.connect('corpchat.db')
target = db.execute(
    "SELECT legacy_password_hash FROM users WHERE username='compliancebot'"
).fetchone()[0]
db.close()

print(f"Target hash: {target}")

# Verify with known accounts first
def legacy_hash(plaintext):
    b64 = base64.b64encode(plaintext.encode()).decode()
    return hashlib.md5(b64.encode()).hexdigest()

# Sanity check
assert legacy_hash('demo123') != target, "Sanity check failed"

# Try CTF-format candidates
candidates = [
    'CTF{md5_b64_l3g4cy_p4ss_cr4ck3d}',
    # Add other guesses here based on the challenge context
]

for candidate in candidates:
    h = legacy_hash(candidate)
    if h == target:
        print(f"CRACKED: {candidate}")
        break
else:
    print("Not found in candidate list. Expand the wordlist.")
```

### Method D — Recognise the Base64 Preimage

If you crack the hash with any tool that outputs the preimage, the preimage will look like base64:

```
Q1RGe21kNV9iNjRfbDNnNGN5X3A0c3NfY3I0Y2szZH0=
```

Base64-decode it to reveal the flag:

```bash
echo "Q1RGe21kNV9iNjRfbDNnNGN5X3A0c3NfY3I0Y2szZH0=" | base64 -d
# CTF{md5_b64_l3g4cy_p4ss_cr4ck3d}
```

**Flag: `CTF{md5_b64_l3g4cy_p4ss_cr4ck3d}`**

---

## What Makes This Interesting: The XSS Bot Connection

`compliancebot` is not just a database entry — it is the XSS bot's account. The Puppeteer bot (running in a separate Docker container) logs into CorpChat as `compliancebot` every 60 seconds and visits every DM conversation.

The bot carries two cookies in its browser session:

| Cookie | Value | Notes |
|--------|-------|-------|
| `flag` | `CORP{<base64(XOR(token, hour_byte))>}` | Encrypted debug API token |
| `hint` | `This looks encrypted. Maybe the platform has a crypto endpoint you could use...` | Plaintext hint |

The flag cookie is `httpOnly: false` — JavaScript can read it. If you send `compliancebot` a DM containing a JavaScript payload, the bot will visit the DM and execute your script.

### The XOR Encryption

The bot encrypts the debug token (`b3b46de0-86e1-4a98-885d-1a85d2bef561`) using a single-byte XOR key equal to the current UTC hour index:

```javascript
function encryptToken(token) {
  const keyByte = Math.floor(Date.now() / 3_600_000) & 0xFF;
  const buf = Buffer.from(token, 'utf8');
  const enc = Buffer.from(buf.map(b => b ^ keyByte));
  return 'CORP{' + enc.toString('base64') + '}';
}
```

To decrypt the cookie, use the `/api/v1/crypto/encrypt` endpoint as a chosen-plaintext oracle:

```bash
# Encrypt a known string to discover the key byte
curl -s -X POST http://<ip>:8080/api/v1/crypto/encrypt \
  -H "Content-Type: application/json" \
  -H "X-API-Token: <any-valid-token>" \
  -d '{"plaintext": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}'

# Response: {"data": {"ciphertext": "CORP{<base64>}"}}
# XOR 0x41 (A) with each ciphertext byte to recover the key byte
# Then XOR the flag cookie bytes with the same key byte
```

---

## Connection to Other Stages

| Stage | How crypto is relevant |
|-------|----------------------|
| Stage 2 (IDOR) | The SQLi on `/search` can also dump `legacy_password_hash` for all users |
| Stage 3 (this stage) | Crack `compliancebot`'s hash to get the flag |
| Stage 4 (RE) | The `entrypoint.py` also uses XOR obfuscation for the SSH password |
| XSS bonus | `compliancebot` is the bot account; the flag cookie uses the same XOR cipher as `/api/v1/crypto/encrypt` |

---

## Remediation (Real World)

| Weakness | Fix |
|----------|-----|
| MD5 for password hashing | Replace with bcrypt, scrypt, or Argon2 |
| No salting | Always generate a unique random salt per user and store it with the hash |
| Base64 pre-processing | Base64 is encoding, not encryption; remove it — it adds no security |
| Flag stored as "password" | Never store CTF flags or system secrets in a user-facing credential field |
