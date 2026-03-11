# Crypto Challenge Writeup — Legacy Hash Cracking

**Category:** Cryptography
**Difficulty:** Medium
**Flag:** `ufoundit`
**Responsible:** Laura

---

## Overview

Every user account in the CorpChat database has a `legacy_password_hash` column. This column contains the base64-encoding of the raw MD5 digest of the user's password — written as `base64(MD5(plaintext))`. For all normal users the plaintext is their regular password. For the compliance bot account `compliancebot`, the plaintext is the flag itself.

Players discover the database, recognise the base64-encoded format, decode it to get the raw MD5 bytes, and crack `compliancebot`'s hash with RockYou.txt to reveal the flag.

---

## Background: The Hashing Scheme

The scheme is seeded in `database.py`:

```python
def _legacy_hash(plaintext):
    md5_bytes = hashlib.md5(plaintext.encode()).digest()  # raw bytes, not hexdigest
    return base64.b64encode(md5_bytes).decode()

legacy_passwords = {
    'chatbot':     ('bot12345',     None),
    'sarah_chen':  ('sarah2024!',   None),
    'manager_bob': ('b0bM@nager2024!', None),
    'compliancebot':   ('ufoundit',     None),  # ← flag
}
```

The stored value is a 24-character base64 string (ends in `==`), not the familiar 32-character MD5 hex string.

### Why This Scheme Is Weak

| Problem | Explanation |
|---------|-------------|
| MD5 is broken | MD5 was deprecated for security use in 2004. Billions of hashes/second on a GPU |
| No salt | Same plaintext always produces the same hash — directly crackable with RockYou.txt |
| Base64 is encoding, not encryption | Base64 adds zero cryptographic strength; it only changes the representation of the hash |
| Password in RockYou.txt | `ufoundit` is a dictionary word, cracked instantly by any wordlist attack |

The correct scheme for password storage is bcrypt, scrypt, or Argon2 — deliberately slow, salted, and memory-hard.

---

## Step 1 — Obtain the Database

### Path A: SSH with Stage 4 Credentials

Completing Stage 4 (reverse engineering) gives you SSH credentials:

```bash
ssh svc_backup@<ip>
# Password: netterFeger69#
```

The database file is at `/data/corpchat.db` and readable by `svc_backup`:

```bash
ls -la /data/corpchat.db
scp svc_backup@<ip>:/data/corpchat.db ./corpchat.db
```

### Path B: Admin Panel Backup

If you have admin panel access at `/admin`:

1. Log in and click **Create Backup**.
2. The backup lands at `/data/backups/corpchat_backup_YYYYMMDD_HHMMSS.db`.
3. Download via SSH or the Files section.

### Path C: SQL Injection

The Stage 2 SQL injection lets you dump the `users` table directly from the browser:

```
/search?q=' UNION SELECT id, username, legacy_password_hash FROM users --
```

This extracts all legacy hashes through the browser without needing file access.

---

## Step 2 — Inspect the Database

```bash
sqlite3 corpchat.db ".mode column" ".headers on" \
  "SELECT id, username, legacy_password_hash FROM users"
```

Output:

```
id  username     legacy_password_hash
--  -----------  ------------------------
1   chatbot      QZ8CEw7b24IwMNeE5RFdfA==
2   sarah_chen   6CPT/2IqwIs/EUQw68KdIw==
3   manager_bob  eLuHkGGwhLLDfQx7NXiDNw==
4   compliancebot    axiZUD8XHIwuAnDt4tidow==
```

All values are 24-character strings ending in `==` — this is the base64 encoding of 16 raw bytes, which is exactly the size of an MD5 digest. Compare with bcrypt (starts with `$2b$`, 60 characters) — this confirms we are looking at base64-encoded MD5.

---

## Step 3 — Understand and Verify the Scheme

Before attacking the unknown hash, verify the scheme against an account whose password you know. `chatbot`'s password is `bot12345`:

```python
import hashlib, base64

plaintext = 'bot12345'
md5_bytes = hashlib.md5(plaintext.encode()).digest()
stored = base64.b64encode(md5_bytes).decode()
print(f"MD5 (hex): {md5_bytes.hex()}")
print(f"base64:    {stored}")
# base64: QZ8CEw7b24IwMNeE5RFdfA==
```

Confirm the output matches what the database has for `chatbot`. You now have a verified understanding of the scheme:

1. Take the raw password bytes
2. Run MD5 → get 16 raw bytes
3. Base64-encode those bytes → store the result

---

## Step 4 — Extract the Target Hash

```bash
sqlite3 corpchat.db \
  "SELECT legacy_password_hash FROM users WHERE username='compliancebot'"
# axiZUD8XHIwuAnDt4tidow==
```

---

## Step 5 — Crack the Hash

The stored value is `base64(MD5(plaintext))`. To crack it:

1. **Decode the base64** to recover the raw MD5 bytes, then convert to hex.
2. **Crack the MD5 hex** with hashcat mode 0 (raw MD5) against RockYou.txt.

### Step 5a — Decode Base64 to MD5 Hex

```bash
python3 -c "import base64; print(base64.b64decode('axiZUD8XHIwuAnDt4tidow==').hex())"
# 6b1899503f171c8c2e0270ede2d89da3
```

Or inline with hashcat by piping:

```bash
echo "axiZUD8XHIwuAnDt4tidow==" | python3 -c "
import sys, base64
print(base64.b64decode(sys.stdin.read().strip()).hex())
" > compliancebot.hash
```

### Step 5b — Crack with Hashcat (Mode 0 — Raw MD5)

```bash
hashcat -m 0 compliancebot.hash /usr/share/wordlists/rockyou.txt
```

Output:

```
6b1899503f171c8c2e0270ede2d89da3:ufoundit
```

### Method B — John the Ripper

```bash
# Save the hex hash
echo "6b1899503f171c8c2e0270ede2d89da3" > compliancebot.hash

# Crack
john --format=raw-md5 --wordlist=/usr/share/wordlists/rockyou.txt compliancebot.hash
john --show compliancebot.hash
# ?:ufoundit
```

### Method C — Python Script

```python
import hashlib, base64, sqlite3

db = sqlite3.connect('corpchat.db')
stored_b64 = db.execute(
    "SELECT legacy_password_hash FROM users WHERE username='compliancebot'"
).fetchone()[0]
db.close()

target_bytes = base64.b64decode(stored_b64)
print(f"Target MD5 hex: {target_bytes.hex()}")

def legacy_hash(plaintext):
    return base64.b64encode(hashlib.md5(plaintext.encode()).digest()).decode()

# Verify scheme with known account
assert legacy_hash('bot12345') == 'QZ8CEw7b24IwMNeE5RFdfA=='

# Crack from RockYou wordlist
with open('/usr/share/wordlists/rockyou.txt', 'rb') as f:
    for line in f:
        word = line.rstrip(b'\n').decode('latin-1')
        if legacy_hash(word) == stored_b64:
            print(f"CRACKED: {word}")
            break
```

**Flag: `ufoundit`**

---

## What Makes This Interesting: The XSS Bot Connection

`compliancebot` is not just a database entry — it is the XSS bot's account. The Puppeteer bot logs into CorpChat as `compliancebot` every 60 seconds and visits every DM conversation.

The bot carries two cookies in its browser session:

| Cookie | Value | Notes |
|--------|-------|-------|
| `flag` | `CORP{<base64(XOR(token, hour_byte))>}` | Encrypted debug API token |
| `hint` | `This looks encrypted. Maybe the platform has a crypto endpoint you could use...` | Plaintext hint |

The flag cookie is `httpOnly: false` — JavaScript can read it. If you send `compliancebot` a DM containing a JavaScript payload, the bot will visit the DM and execute your script.

### The XOR Encryption

The bot encrypts the debug token using a single-byte XOR key equal to the current UTC hour index:

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
curl -s -X POST http://<ip>:8080/api/v1/crypto/encrypt \
  -H "Content-Type: application/json" \
  -H "X-API-Token: <any-valid-token>" \
  -d '{"plaintext": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}'
# XOR 0x41 (A) with each ciphertext byte to recover the key byte
```

---

## Connection to Other Stages

| Stage | How crypto is relevant |
|-------|----------------------|
| Stage 2 (IDOR) | The SQLi on `/search` can also dump `legacy_password_hash` for all users |
| Stage 3 (this stage) | Crack `compliancebot`'s hash to get the flag `ufoundit` |
| Stage 4 (RE) | The `entrypoint.py` also uses XOR obfuscation for the SSH password |
| XSS bonus | `compliancebot` is the bot account; the flag cookie uses the same XOR cipher as `/api/v1/crypto/encrypt` |

---

## Remediation (Real World)

| Weakness | Fix |
|----------|-----|
| MD5 for password hashing | Replace with bcrypt, scrypt, or Argon2 |
| No salting | Always generate a unique random salt per user and store it with the hash |
| Base64 post-processing | Base64 is encoding, not encryption; remove it — it adds no security |
| Weak password | Never use dictionary words as credentials, even for internal service accounts |
