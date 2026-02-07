# Admin Panel

[Back to Index](README.md)

---

## Overview

The admin panel is a separate section of the application accessible at `/admin`. It has its own authentication system (using the `admin_users` table), its own base template, and provides tools for user management, system configuration, audit logging, and database backups.

- **Backend:** `routes/admin.py`
- **Templates:** `templates/admin/` (6 templates)
- **CSS:** `static/css/admin.css`
- **JS:** `static/js/admin.js`

---

## Source File: `routes/admin.py`

This file defines the `admin_bp` blueprint with URL prefix `/admin`.

### `before_request` Hook: `load_pending_reset_count()` (lines 17-23)

Runs before every admin route. If an admin is logged in, it counts pending password reset requests and stores the count in `g.pending_reset_count`. This is displayed as a badge on the Dashboard nav item.

```python
@admin_bp.before_request
def load_pending_reset_count():
    if 'admin_id' in session:
        db = get_db()
        g.pending_reset_count = db.execute(
            "SELECT COUNT(*) FROM password_resets WHERE status = 'pending'"
        ).fetchone()[0]
```

---

### Route: `GET /admin/` -- Index Redirect

**Function:** `index()` (lines 26-30)

If logged in, redirects to `/admin/dashboard`. Otherwise, redirects to `/admin/login`.

---

### Route: `GET/POST /admin/login` -- Admin Authentication

**Function:** `login()` (lines 33-56)

**GET:** Renders the admin login page (`admin/login.html`). If already logged in, redirects to dashboard.

**POST:**
1. Extracts `username` and `password` from form
2. Queries `admin_users` table: `SELECT * FROM admin_users WHERE username = ?`
3. Verifies password with `check_password_hash()`
4. On success:
   - Sets `session['admin_id']` and `session['admin_username']`
   - Logs `admin_login` event
   - Redirects to dashboard
5. On failure:
   - Flashes "Invalid admin credentials."
   - Logs `admin_login_failed` event

---

### Route: `GET /admin/logout` -- Admin Logout

**Function:** `logout()` (lines 59-64)

1. Logs `admin_logout` event
2. Removes `admin_id` and `admin_username` from session
3. Redirects to admin login

---

### Route: `GET /admin/dashboard` -- Dashboard

**Function:** `dashboard()` (lines 67-98)
**Decorator:** `@admin_required`

The main admin landing page displaying statistics, pending actions, and recent activity.

**Data gathered:**
1. **Statistics:**
   ```python
   stats = {
       'total_users': ...,
       'active_users': ...,      # WHERE is_active = 1
       'total_messages': ...,
       'total_files': ...,
       'total_channels': ...,
   }
   ```

2. **Pending password resets:**
   ```sql
   SELECT pr.id, pr.created_at, u.username, u.id as user_id
   FROM password_resets pr
   JOIN users u ON pr.user_id = u.id
   WHERE pr.status = 'pending'
   ORDER BY pr.created_at ASC
   ```

3. **Recent audit logs** (last 20 entries):
   ```sql
   SELECT al.*, u.username
   FROM audit_log al
   LEFT JOIN users u ON al.user_id = u.id
   ORDER BY al.created_at DESC
   LIMIT 20
   ```

**Template sections:**
- **Stats grid** -- 5 cards showing counts (Total Users, Active Users, Messages, Files, Channels)
- **Pending Password Resets** -- table with Approve/Deny buttons (only shown if there are pending requests)
- **Recent Activity** -- table of audit log entries with timestamp, event type, user, details, and IP

---

### Route: `GET /admin/users` -- User Management

**Function:** `users()` (lines 101-106)
**Decorator:** `@admin_required`

Lists all users from the `users` table ordered by ID.

**Template (`admin/users.html`) displays:**

| Column | Source |
|--------|--------|
| ID | `user.id` |
| Username | `user.username` (bold) |
| Display Name | `user.display_name` |
| Email | `user.email` |
| Role | `user.role` |
| Status | "Active" (green) or "Disabled" (red) badge, plus "PW Reset" badge if `must_change_password` |
| Created | `user.created_at` |
| Last Login | `user.last_login` or "Never" |
| Actions | Enable/Disable toggle + Force PW Change button |

---

### Route: `POST /admin/users/<int:user_id>/toggle` -- Toggle User Active Status

**Function:** `toggle_user()` (lines 109-125)
**Decorator:** `@admin_required`

Toggles a user's `is_active` flag between 0 and 1.

```python
new_status = 0 if user['is_active'] else 1
db.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, user_id))
```

- Disabled users cannot log in or use the API
- Logs `admin_action` with `action: 'user_enabled'` or `'user_disabled'`

---

### Route: `POST /admin/users/<int:user_id>/reset-password` -- Force Password Reset

**Function:** `reset_user_password()` (lines 128-146)
**Decorator:** `@admin_required`

Generates a temporary password and forces the user to change it on next login.

1. Generates temp password: `uuid.uuid4().hex[:12]` (12 random hex characters)
2. Hashes it with `generate_password_hash()`
3. Updates user: sets new `password_hash` and `must_change_password = 1`
4. Flashes the temp password to the admin: "Temporary password for {username}: {password}"
5. Logs `admin_action` with `action: 'force_password_change'`

---

### Route: `POST /admin/reset-requests/<int:request_id>/approve` -- Approve Password Reset

**Function:** `approve_reset()` (lines 149-180)
**Decorator:** `@admin_required`

Processes a user-initiated password reset request.

1. Looks up the request (must be `status = 'pending'`)
2. Generates temp password: `uuid.uuid4().hex[:12]`
3. Updates user: new hash + `must_change_password = 1`
4. Updates request: `status = 'approved'`, sets `reviewed_by` and `reviewed_at`
5. Flashes temp password to admin
6. Logs `admin_action` with `action: 'password_reset_approved'`
7. Redirects to dashboard

---

### Route: `POST /admin/reset-requests/<int:request_id>/deny` -- Deny Password Reset

**Function:** `deny_reset()` (lines 183-209)
**Decorator:** `@admin_required`

1. Looks up the request (must be `status = 'pending'`)
2. Updates request: `status = 'denied'`, sets `reviewed_by` and `reviewed_at`
3. Logs `admin_action` with `action: 'password_reset_denied'`
4. Redirects to dashboard

---

### Route: `GET/POST /admin/settings` -- System Settings

**Function:** `settings()` (lines 212-231)
**Decorator:** `@admin_required`

Manages the `system_settings` key-value store.

**GET:** Fetches all settings and renders the form:
```sql
SELECT * FROM system_settings ORDER BY key
```

**POST:** Iterates over form fields whose names start with `setting_`:
```python
for key in request.form:
    if key.startswith('setting_'):
        setting_key = key[8:]  # Strip "setting_" prefix
        value = request.form[key]
        db.execute(
            "UPDATE system_settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
            (value, setting_key)
        )
```

Logs `settings_change` event.

**Template (`admin/settings.html`):** Renders each setting as a text input labeled with the setting key, showing the last update timestamp.

---

### Route: `GET /admin/logs` -- Audit Logs

**Function:** `logs()` (lines 234-260)
**Decorator:** `@admin_required`

Displays the audit log with filtering and pagination.

**Parameters:**
- `event_type` (query string) -- filter by event type
- `page` (query string, default 1) -- page number

**Pagination:** 50 entries per page.

**Query construction:**
```python
query = "SELECT al.*, u.username FROM audit_log al LEFT JOIN users u ON al.user_id = u.id"
if event_type:
    query += " WHERE al.event_type = ?"
query += " ORDER BY al.created_at DESC LIMIT ? OFFSET ?"
```

**Template (`admin/logs.html`) features:**
- Dropdown filter for event type (populated from `SELECT DISTINCT event_type`)
- Table with columns: ID, Time, Event (badge), User, Details (monospace, truncated), IP Address
- Previous/Next pagination links

---

### Route: `POST /admin/backup` -- Create Database Backup

**Function:** `backup()` (lines 263-281)
**Decorator:** `@admin_required`

Creates a timestamped copy of the SQLite database.

```python
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup_name = f'corpchat_backup_{timestamp}.db'
backup_path = os.path.join(backup_dir, backup_name)
shutil.copy2(current_app.config['DATABASE_PATH'], backup_path)
```

Example filename: `corpchat_backup_20260207_143022.db`

The button is in the admin topbar (defined in `admin/base_admin.html`).

Logs `backup_created` event with backup filename.

---

### Route: `GET /admin/debug` -- Debug Information

**Function:** `debug()` (lines 284-295)
**Decorator:** `@admin_required`

Returns system information as JSON:

```json
{
  "app_version": "1.0.0",
  "python_version": "3.11.x ...",
  "debug_mode": true,
  "database_path": "./data/corpchat.db",
  "upload_folder": "./uploads",
  "max_upload_size": 10485760,
  "server_time": "2026-02-07T14:30:22.123456"
}
```

This endpoint has no corresponding template -- it returns raw JSON.

---

## Admin Templates

### `admin/base_admin.html`
Base layout for all admin pages. Similar to `base.html` but with:
- Admin-specific sidebar (dark blue theme, red accent icon "A")
- Navigation: Dashboard (with pending count badge), Users, Settings, Logs
- Topbar with "Create Backup" button
- "Back to PwnBox" link in the sidebar footer
- Includes both `main.css` and `admin.css`

### `admin/login.html`
Standalone login page (does not extend base_admin.html). Features:
- Dark navy/purple color scheme
- Red accent color for the admin brand
- "Back to PwnBox" link

### `admin/dashboard.html`
Dashboard with stats cards, pending reset requests table, and recent activity table.

### `admin/users.html`
User management table with action buttons for each user.

### `admin/settings.html`
Dynamic form generated from `system_settings` rows.

### `admin/logs.html`
Audit log viewer with event type filter dropdown and pagination.

---

## Admin CSS (`static/css/admin.css`)

Overrides for the admin panel theme (35 lines):

- **Sidebar:** Darker navy background (`#1a1a2e`) instead of the standard dark gray
- **Nav hover:** Purple-tinted hover (`#262640`)
- **Active nav:** Deeper purple (`#2a2a4a`)
- **Logo icon:** Red background (`#d94a4a`)
- **Stat values:** Red accent instead of blue

---

## Admin JavaScript (`static/js/admin.js`)

Minimal placeholder (11 lines):

```javascript
(function () {
    const logsTable = document.querySelector('[data-auto-refresh]');
    if (logsTable) {
        setInterval(function () {
            window.location.reload();
        }, 30000);
    }
})();
```

Auto-refreshes the page every 30 seconds if a `[data-auto-refresh]` element exists (currently not used by any template).
