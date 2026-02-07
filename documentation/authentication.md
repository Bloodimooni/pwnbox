# Authentication & Authorization

[Back to Index](README.md)

---

## Overview

PwnBox has **two independent authentication systems**:

1. **Regular User Auth** -- cookie-based sessions for the main application
2. **Admin Auth** -- separate cookie-based sessions for the admin portal
3. **API Token Auth** -- header-based authentication for REST API endpoints

All authentication logic lives in `routes/auth.py` (user auth) and `routes/admin.py` (admin auth), with API token auth in `routes/api.py`.

---

## Source File: `routes/auth.py`

This file defines the `auth_bp` blueprint (no URL prefix) and contains:
- Login/logout routes
- Registration route
- Password reset flow
- Two decorator functions (`login_required`, `admin_required`)
- The `log_event()` utility function

---

## Decorators

### `@login_required` (lines 11-19)

Protects routes that require a logged-in regular user.

```python
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if session.get('must_change_password'):
            return redirect(url_for('auth.force_change_password'))
        return f(*args, **kwargs)
    return decorated
```

**Behavior:**
1. Checks if `session['user_id']` exists
2. If not present: redirects to `/login`
3. If present but `session['must_change_password']` is set: redirects to `/change-password`
4. Otherwise: allows the request to proceed

**Used by:** All routes in `chat_bp`, `dm_bp`, `profile_bp`, `files_bp`, `search_bp`

### `@admin_required` (lines 22-28)

Protects routes that require an authenticated admin.

```python
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated
```

**Behavior:**
1. Checks if `session['admin_id']` exists
2. If not present: redirects to `/admin/login`
3. Otherwise: allows the request to proceed

**Used by:** All routes in `admin_bp` except `/admin/login`

### `@api_auth_required` (in `routes/api.py`, lines 23-44)

Protects REST API endpoints. Supports two authentication methods:

```python
def api_auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # 1. Check X-API-Token header first
        token = request.headers.get('X-API-Token')
        if token:
            user = db.execute("SELECT * FROM users WHERE api_token = ?", (token,)).fetchone()
            if user and user['is_active']:
                g.api_user = user
                return f(*args, **kwargs)

        # 2. Fall back to session-based auth
        if 'user_id' in session:
            user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
            if user and user['is_active']:
                g.api_user = user
                return f(*args, **kwargs)

        return jsonify({"error": "Authentication required"}), 401
    return decorated
```

**Authentication priority:**
1. `X-API-Token` header -- looks up user by `api_token` column
2. Session cookie -- falls back to `session['user_id']`
3. If neither works: returns 401 JSON error

**Key detail:** Both methods also check `user['is_active']` -- disabled accounts are rejected even with valid tokens.

The authenticated user is stored in `g.api_user` for access by the route handler.

---

## Login Flow (`/login`)

**Route:** `GET /login` and `POST /login` (lines 40-77)

### GET Request
- If already logged in (`session['user_id']` exists):
  - If `must_change_password`: redirect to `/change-password`
  - Otherwise: redirect to `/chat`
- Renders `templates/auth/login.html`

### POST Request
1. Extracts `username` and `password` from form data
2. Queries `SELECT * FROM users WHERE username = ?`
3. Verifies password with `check_password_hash(user['password_hash'], password)`
4. **If credentials valid:**
   - Checks `user['is_active']` -- if disabled, shows error and stops
   - Sets session values: `user_id`, `username`, `display_name`
   - Updates `last_login` timestamp in database
   - Logs a `login` event to `audit_log`
   - If `user['must_change_password']`: sets `session['must_change_password'] = True` and redirects to `/change-password`
   - Otherwise: redirects to `/chat`
5. **If credentials invalid:**
   - Flashes "Invalid username or password."
   - Logs a `login_failed` event (with username in details, no user_id)

---

## Registration Flow (`/register`)

**Route:** `GET /register` and `POST /register` (lines 80-129)

### POST Request Validation
1. **Username:** Must be at least 3 characters (after stripping whitespace)
2. **Email:** Must contain `@`
3. **Password:** Must be at least 6 characters
4. **Confirm Password:** Must match password
5. **Uniqueness:** Checks `SELECT id FROM users WHERE username = ? OR email = ?`

### On Successful Registration
1. Generates an API token: `str(uuid.uuid4())`
2. Hashes password with `generate_password_hash(password)`
3. Inserts into `users` table with `display_name` defaulting to username if not provided
4. Logs a `register` event
5. Flashes success message and redirects to `/login`

---

## Logout (`/logout`)

**Route:** `GET /logout` (lines 132-141)

1. If logged in, logs a `logout` event
2. Removes all session keys: `user_id`, `username`, `display_name`, `must_change_password`
3. Redirects to `/login`

---

## Password Reset Flow

The password reset system is a **multi-step admin-approved process**:

### Step 1: User Requests Reset (`/reset-password`)

**Route:** `GET /reset-password` and `POST /reset-password` (lines 144-172)

1. User submits their username
2. Application looks up the user (but **always shows the same message** regardless of whether the user exists -- prevents username enumeration)
3. If user exists and no pending request already:
   - Creates a `password_resets` record with `status='pending'` and a UUID token
   - Logs `password_reset_request` event
4. Shows: "If that account exists, a password reset request has been submitted."

### Step 2: Admin Reviews Request

In the admin dashboard (`/admin/dashboard`), pending reset requests are displayed. The admin can:

- **Approve** (`POST /admin/reset-requests/{id}/approve`):
  1. Generates a temporary password: `uuid.uuid4().hex[:12]`
  2. Updates the user's `password_hash` and sets `must_change_password = 1`
  3. Updates the reset request `status` to `'approved'`
  4. Flashes the temporary password to the admin
  5. Logs `admin_action` with `action: 'password_reset_approved'`

- **Deny** (`POST /admin/reset-requests/{id}/deny`):
  1. Updates the reset request `status` to `'denied'`
  2. Logs `admin_action` with `action: 'password_reset_denied'`

### Step 3: User Changes Password (`/change-password`)

**Route:** `GET /change-password` and `POST /change-password` (lines 181-211)

This route is accessible **only** when `session['must_change_password']` is True.

1. User enters new password (min 6 chars) and confirms it
2. Password is hashed and updated in the database
3. `must_change_password` flag is cleared (both in DB and session)
4. Logs `password_changed` event
5. Redirects to `/chat`

### Deprecated Token-Based Reset (`/reset-password/<token>`)

**Route:** `GET /reset-password/<token>` (lines 175-178)

This old flow is deprecated. It simply flashes a message saying "The password reset process has changed" and redirects back to `/reset-password`.

---

## Session Data

### Regular User Session Keys

| Key | Type | Set When | Description |
|-----|------|----------|-------------|
| `user_id` | int | Login | User's database ID |
| `username` | str | Login | User's username |
| `display_name` | str | Login | User's display name (or username) |
| `must_change_password` | bool | Login (if flag set) | Forces redirect to password change |

### Admin Session Keys

| Key | Type | Set When | Description |
|-----|------|----------|-------------|
| `admin_id` | int | Admin login | Admin's database ID |
| `admin_username` | str | Admin login | Admin's username |

**Important:** Both session types can coexist. A single browser session can be authenticated as both a regular user and an admin simultaneously.

---

## Audit Logging

The `log_event()` function (`routes/auth.py:31-37`) is used throughout the application:

```python
def log_event(event_type, user_id=None, details=None):
    db = get_db()
    db.execute(
        "INSERT INTO audit_log (event_type, user_id, details, ip_address) VALUES (?, ?, ?, ?)",
        (event_type, user_id, json.dumps(details) if details else None, request.remote_addr)
    )
    db.commit()
```

**Parameters:**
- `event_type` -- string category of the event
- `user_id` -- optional user associated with the event
- `details` -- optional dict that gets JSON-serialized
- `ip_address` -- automatically captured from `request.remote_addr`

This function is imported and used by `chat.py`, `profile.py`, `files.py`, `admin.py`, and `api.py`.

---

## User Activity Tracking

The `before_request` hook in `app.py:54-65` updates `last_activity` on every request:

```python
@app.before_request
def update_user_activity():
    if 'user_id' in session and not session.get('must_change_password'):
        try:
            db = get_db()
            db.execute(
                "UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE id = ?",
                (session['user_id'],)
            )
            db.commit()
        except Exception:
            pass
```

This is used by the "Online Users" feature -- users with `last_activity` within the last 5 minutes are considered online (`routes/api.py:310-324`).

---

## API Token Authentication

Each user has an `api_token` (UUID) generated at registration. This token can be used to authenticate API requests:

```bash
curl -H "X-API-Token: <your-token>" http://localhost:5000/api/v1/users/me
```

To obtain a token programmatically:

```bash
curl -X POST http://localhost:5000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "demo123"}'
```

**Response:**
```json
{
  "data": {
    "token": "a1b2c3d4-...",
    "user_id": 1,
    "username": "demo"
  }
}
```

The token is displayed on the user's profile edit page (`/profile/edit`) in a read-only field.
