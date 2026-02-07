# Search & Profiles

[Back to Index](README.md)

---

## Search System

### Overview

The search feature allows users to find messages and other users across the entire application. It's available both as a web page and an API endpoint.

- **Backend:** `routes/search.py` (web UI) and `routes/api.py` (JSON API)
- **Template:** `templates/search/results.html`

### Source File: `routes/search.py`

This file defines the `search_bp` blueprint with URL prefix `/search`. It contains a single route.

#### Route: `GET /search/` -- Search Page

**Function:** `index()` (lines 8-36)
**Decorator:** `@login_required`

**Query Parameter:** `q` (search term)

**Behavior:**
1. If `q` is empty: renders the search page with no results
2. If `q` is provided, executes two queries:

**Message search:**
```sql
SELECT m.*, u.username, u.display_name, c.name as channel_name
FROM messages m
JOIN users u ON m.user_id = u.id
JOIN channels c ON m.channel_id = c.id
WHERE m.content LIKE ?
ORDER BY m.created_at DESC
LIMIT 50
```
The `?` parameter is `f'%{query}%'` -- matches messages containing the search term anywhere.

**User search:**
```sql
SELECT * FROM users
WHERE username LIKE ? OR display_name LIKE ?
ORDER BY username
LIMIT 20
```
Searches both `username` and `display_name` columns.

### Template: `templates/search/results.html`

Extends `base.html`.

**Sections:**
1. **Search form** -- text input pre-filled with the current query, plus Search button
2. **Messages section** (if results found):
   - Count header: "Messages (N)"
   - Each result shows: author name, channel name (e.g., "in #general"), timestamp, and message content
3. **Users section** (if results found):
   - Count header: "Users (N)"
   - Each result shows: avatar initial, display name (linked to profile), and @username
4. **No results** -- shown if query was provided but neither search returned results
5. **Empty state** -- "Enter a search term to find messages and users." when no query

### API Search Endpoint

`GET /api/v1/search?q=<query>&type=<all|messages|users>`

See [REST API Reference](api-reference.md) for full details. Returns the same data as the web search but in JSON format, with an additional `type` filter parameter.

### Search Accessibility

The search function is accessible from two places:
1. **Search page** (`/search/`) -- the dedicated search page with full results
2. **Topbar search bar** (in `base.html`) -- a form in the top navigation bar that submits to `/search/`

---

## User Profiles

### Overview

Each user has a profile page showing their information. Users can edit their own profile (display name, bio, avatar).

- **Backend:** `routes/profile.py`
- **Templates:** `templates/profile/view.html` and `templates/profile/edit.html`

### Source File: `routes/profile.py`

This file defines the `profile_bp` blueprint with URL prefix `/profile`.

#### Route: `GET /profile/<int:user_id>` -- View Profile

**Function:** `view()` (lines 10-23)
**Decorator:** `@login_required`

Displays a user's public profile.

**Data fetched:**
1. User record: `SELECT * FROM users WHERE id = ?`
2. Message count: `SELECT COUNT(*) FROM messages WHERE user_id = ?`

**If user not found:** Flashes "User not found." and redirects to `/chat`.

**Template (`profile/view.html`) displays:**
- **Avatar** -- large circle with first letter of display name
- **Display name** -- or username if no display name
- **Username** -- shown as `@username`
- **Bio** -- or "No bio set."
- **Profile meta:**
  - Join date (`created_at`)
  - Message count
  - Email address
- **Edit Profile button** -- only shown if viewing your own profile (`profile_user.id == session.get('user_id')`)

#### Route: `GET/POST /profile/edit` -- Edit Profile

**Function:** `edit()` (lines 26-59)
**Decorator:** `@login_required`

Allows users to edit their own profile.

**GET:** Renders the edit form pre-filled with current values.

**POST:** Processes the form submission:

1. **Display name:** Read from form, falls back to username if empty
2. **Bio:** Read from form (can be empty)
3. **Avatar:** Optional file upload
   - Validates extension: `png`, `jpg`, `jpeg`, `gif`
   - Generates UUID filename: `{uuid.uuid4().hex}.{ext}`
   - Saves to `UPLOAD_FOLDER`
   - If invalid format: flashes "Invalid image format. Use PNG, JPG, or GIF."
4. **Database update:**
   ```sql
   UPDATE users SET display_name = ?, bio = ?, avatar_filename = ? WHERE id = ?
   ```
5. Updates `session['display_name']`
6. Logs `profile_update` event
7. Redirects to profile view page

**Template (`profile/edit.html`) contains:**
- **Display Name** input (text)
- **Bio** textarea (4 rows)
- **Avatar** file input (accepts `image/*`, help text: "PNG, JPG, or GIF. Max 10MB.")
- **Email** input (disabled/read-only)
- **API Token** input (disabled/read-only, monospace font)
- **Save Changes** and **Cancel** buttons

### Profile-Related API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/users/<id>` | Public profile info (id, username, display_name, bio, avatar, created_at) |
| `GET /api/v1/users/me` | Full profile including email, role, and API token |

See [REST API Reference](api-reference.md) for details.

---

## Online Users

The sidebar in `base.html` displays a list of currently online users, powered by the inline JavaScript.

### How It Works

1. **Tracking:** The `before_request` hook in `app.py` updates `users.last_activity` on every authenticated request
2. **API:** `GET /api/v1/users/online` returns users where `last_activity >= datetime('now', '-5 minutes')`
3. **Display:** The base template's JavaScript fetches this endpoint every 10 seconds and renders the list:
   ```javascript
   fetchOnlineUsers();
   setInterval(fetchOnlineUsers, 10000);
   ```
4. **Rendering:** Each online user is shown with a green dot and their display name (HTML-escaped)

### Online User Section (in sidebar)
```html
<div class="online-users-section">
    <div class="channel-section-header">
        <span>Online -- <span id="online-count">0</span></span>
    </div>
    <ul class="online-users-list" id="online-users-list">
        <!-- Populated by JavaScript -->
    </ul>
</div>
```

---

## Muting

Users can mute channels, DM conversations, and individual users. Muted items don't generate unread badges.

### How Muting Works

1. **Toggle button** -- each channel/DM in the sidebar has a mute button (speaker icon)
2. **Click handler** (in `base.html` JavaScript) sends `POST /api/v1/mute` or `POST /api/v1/unmute`
3. **Mute state** is fetched via `GET /api/v1/mutes` and cached globally in `window._PwnBoxMutes`
4. **UI updates:**
   - Muted items get `opacity: 0.4` CSS
   - Mute button shows speaker-off icon with red color
   - Unread badges are suppressed for muted items

### Mute Types

| Type | Target | Effect |
|------|--------|--------|
| `channel` | Channel ID | Suppresses unread badge for that channel |
| `dm` | Conversation ID | Suppresses unread badge for that DM |
| `user` | User ID | Available in the API but no UI toggle exists |

### Refresh Intervals

| Data | Interval |
|------|----------|
| Mute state | 30 seconds |
| Unread badges (using mute data) | 5 seconds |
| Online users | 10 seconds |
