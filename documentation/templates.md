# Templates

[Back to Index](README.md)

---

## Overview

PwnBox uses **Jinja2** templates (Flask's default template engine) for server-side HTML rendering. Templates are organized in subdirectories by feature area.

```
templates/
├── base.html                    # Main layout (sidebar + topbar)
├── auth/
│   ├── login.html               # User login page
│   ├── register.html            # User registration page
│   ├── change_password.html     # Forced password change
│   └── reset_password.html      # Password reset request
├── chat/
│   └── chat.html                # Channel chat interface
├── dm/
│   └── dm.html                  # Direct messages interface
├── profile/
│   ├── view.html                # User profile view
│   └── edit.html                # Profile editing form
├── files/
│   └── list.html                # File listing and upload
├── search/
│   └── results.html             # Search results page
└── admin/
    ├── base_admin.html          # Admin layout (admin sidebar)
    ├── login.html               # Admin login page
    ├── dashboard.html           # Admin dashboard
    ├── users.html               # User management
    ├── settings.html            # System settings
    └── logs.html                # Audit logs viewer
```

---

## Template Hierarchy

```
base.html
├── chat/chat.html
├── dm/dm.html
├── profile/view.html
├── profile/edit.html
├── files/list.html
└── search/results.html

admin/base_admin.html
├── admin/dashboard.html
├── admin/users.html
├── admin/settings.html
└── admin/logs.html

(Standalone - no parent)
├── auth/login.html
├── auth/register.html
├── auth/change_password.html
├── auth/reset_password.html
└── admin/login.html
```

---

## Base Template: `base.html` (244 lines)

The main layout template used by all authenticated pages. Provides a two-column layout with sidebar and main content area.

### Structure

```html
<!DOCTYPE html>
<html>
<head>
    <title>{% block title %}PwnBox{% endblock %}</title>
    <link rel="stylesheet" href="main.css">
    {% block extra_head %}{% endblock %}
</head>
<body>
    <div class="app-layout">
        <aside class="sidebar">
            <!-- Logo -->
            <!-- Navigation (Chat, Messages, Files, Search) -->
            {% block sidebar_extra %}{% endblock %}
            <!-- Online Users section -->
            <!-- User info footer -->
        </aside>
        <main class="main-content">
            <header class="topbar">
                {% block page_header %}PwnBox{% endblock %}
                <!-- Search form -->
            </header>
            <div class="content-area">
                <!-- Flash messages -->
                {% block content %}{% endblock %}
            </div>
        </main>
    </div>
    <script>/* inline mutes, online users, badges */</script>
    {% block extra_scripts %}{% endblock %}
</body>
</html>
```

### Blocks Available

| Block | Purpose | Location |
|-------|---------|----------|
| `title` | Page title in `<title>` tag | `<head>` |
| `extra_head` | Additional `<head>` content (CSS, meta) | `<head>` |
| `page_header` | Text in the topbar | `<header>` |
| `sidebar_extra` | Additional sidebar content (channel list, DM list) | `<aside>` |
| `content` | Main page content | `<main>` |
| `extra_scripts` | Additional `<script>` tags | End of `<body>` |

### Sidebar Navigation

4 navigation items, each with active state detection:

| Item | URL | Active when |
|------|-----|-------------|
| Chat | `/chat` | `request.path.startswith('/chat')` |
| Messages | `/dm` | `request.path.startswith('/dm')` |
| Files | `/files` | `request.path.startswith('/files')` |
| Search | `/search` | `request.path.startswith('/search')` |

Each nav item has an icon (Unicode character) and an optional badge element for unread counts.

### Sidebar Footer

Shows the current user's:
- Avatar (first letter of display name in a colored circle)
- Display name
- Link to profile (`/profile/<user_id>`)
- Logout button (right arrow icon linking to `/logout`)

### Flash Messages

```jinja2
{% with messages = get_flashed_messages() %}
    {% if messages %}
        <div class="flash-messages">
            {% for msg in messages %}
                <div class="flash-msg">{{ msg }}</div>
            {% endfor %}
        </div>
    {% endif %}
{% endwith %}
```

Flash messages appear at the top of the content area with an amber/gold theme.

---

## Auth Templates (Standalone)

These templates do **not** extend `base.html`. They are standalone pages with a centered card layout.

### `auth/login.html` (47 lines)

Centered login card with:
- PwnBox logo
- "Sign In" heading
- Flash messages (with category support -- `with_categories=true`)
- Username input (autofocus)
- Password input
- "Sign In" button
- Links to register and forgot password

### `auth/register.html` (57 lines)

Registration form with:
- Username (min 3 chars)
- Email (email type)
- Display name (optional)
- Password (min 6 chars)
- Confirm password
- "Create Account" button
- Link to login

### `auth/change_password.html` (45 lines)

Forced password change form:
- Explanatory text: "An administrator has approved your password reset."
- New password (min 6 chars, autofocus)
- Confirm password
- "Change Password" button

### `auth/reset_password.html` (56 lines)

Two-step template controlled by a `step` variable:

**`step = 'request'`:**
- Username input
- "Request Password Reset" button

**`step = 'requested'`:**
- Success flash message
- Explanatory text: "Your request has been sent to an administrator for review."

Both steps have a "Back to login" link.

---

## Chat Template: `chat/chat.html` (115 lines)

Extends `base.html`.

### `sidebar_extra` Block
Channel list section:
- Section header: "Channels"
- List of channels with links and mute buttons
- Active channel highlighted
- "+ New Channel" button

### `content` Block
Chat interface:
- **Message container** (`#chat-messages`): Server-rendered messages, each with avatar, author, time, content, and optional attachment image
- **Typing indicator** (hidden by default)
- **Attachment preview** (hidden by default)
- **Chat input area**: Attach button (SVG icon), text input, Send button

### Create Channel Modal
Overlay with:
- Channel name input (placeholder: "e.g. project-alpha")
- Description input (optional)
- Cancel and Create buttons
- Form POSTs to `/chat/channel/create`

### `extra_scripts` Block
Includes `chat.js`.

---

## DM Template: `dm/dm.html` (129 lines)

Extends `base.html`. Very similar to `chat.html`.

### `sidebar_extra` Block
- DM conversation list with other user's name
- Mute buttons for each conversation
- "+ New Message" button

### `content` Block
Three states:
1. **No conversations:** Empty state with envelope icon
2. **No active conversation:** "Select a conversation" prompt with arrow icon
3. **Active conversation:** Messages, typing indicator, attachment preview, input

### New DM Modal
- User picker dropdown (`<select>`)
- Cancel and "Start Conversation" buttons
- Form POSTs to `/dm/new`

### `extra_scripts` Block
Includes `dm.js`.

---

## Profile Templates

### `profile/view.html` (27 lines)

Extends `base.html`.

Displays:
- Large avatar circle
- Display name heading
- `@username`
- Bio text
- Metadata row: join date, message count, email
- "Edit Profile" button (only for own profile)

### `profile/edit.html` (37 lines)

Extends `base.html`.

Form with `enctype="multipart/form-data"`:
- Display name text input
- Bio textarea (4 rows)
- Avatar file input (accepts `image/*`)
- Email (disabled, read-only)
- API token (disabled, read-only, monospace)
- Save and Cancel buttons

---

## Files Template: `files/list.html` (63 lines)

Extends `base.html`.

### File List
Each file displayed with:
- Filename
- Uploader name, date, size in KB
- "Encrypted" badge if `is_encrypted`
- Download button
- Delete button (only for own files, with confirm dialog)

### Upload Modal
- File input
- Allowed types help text
- Cancel and Upload buttons
- Form POSTs to `/files/upload` with `enctype="multipart/form-data"`

---

## Search Template: `search/results.html` (58 lines)

Extends `base.html`.

- Search form (text input + button)
- Messages section with count, author, channel, time, content
- Users section with avatar, name (linked to profile), username
- "No results" message
- Empty state when no query

---

## Admin Templates

### `admin/base_admin.html` (82 lines)

Admin layout template (equivalent to `base.html` for admin pages).

**Differences from `base.html`:**
- Includes both `main.css` and `admin.css`
- Red admin logo icon ("A" instead of "C")
- Admin-specific navigation: Dashboard, Users, Settings, Logs
- Dashboard nav shows pending reset count badge via `g.pending_reset_count`
- "Create Backup" button in topbar
- Footer shows "Back to PwnBox" link instead of profile link
- No inline JavaScript (no mutes, online users, or badges)

### `admin/login.html` (48 lines)

Standalone admin login page (does not extend any base):
- Navy/purple dark theme (`#1a1a2e` background)
- Red accent color for branding
- Username and password fields with matching dark input styling
- "Back to PwnBox" link

### `admin/dashboard.html` (95 lines)

Extends `admin/base_admin.html`.

Sections:
1. **Stats grid** -- 5 cards: Total Users, Active Users, Messages, Files, Channels
2. **Pending Password Resets** -- bordered table (only shown if pending requests exist), with Approve/Deny buttons per request
3. **Recent Activity** -- table with Time, Event (badge), User, Details, IP columns

### `admin/users.html` (61 lines)

Extends `admin/base_admin.html`.

Full user table with columns: ID, Username, Display Name, Email, Role, Status (Active/Disabled badges, PW Reset badge), Created, Last Login, Actions (Disable/Enable toggle, Force PW Change button).

### `admin/settings.html` (20 lines)

Extends `admin/base_admin.html`.

Dynamic form: iterates over all `system_settings` rows, creates a text input for each with the key as label and `setting_{key}` as the input name. Shows last update timestamp.

### `admin/logs.html` (66 lines)

Extends `admin/base_admin.html`.

- Event type filter dropdown (populated from distinct event types in the database)
- Table with columns: ID, Time, Event (badge), User, Details (monospace, truncated), IP Address
- Previous/Next pagination (50 entries per page)

---

## Jinja2 Features Used

| Feature | Example | Where |
|---------|---------|-------|
| Template inheritance | `{% extends "base.html" %}` | All child templates |
| Blocks | `{% block content %}...{% endblock %}` | Layout system |
| Variables | `{{ msg.content }}` | Data display |
| Filters | `{{ (file.file_size / 1024)\|round(1) }}` | File size formatting |
| Filters | `{{ name[0]\|upper }}` | Avatar initials |
| Conditionals | `{% if user.is_active %}` | Status badges |
| Loops | `{% for msg in messages %}` | Lists and tables |
| Flash messages | `{% with messages = get_flashed_messages() %}` | Notification display |
| URL generation | `{{ url_for('chat.index', channel=1) }}` | All links |
| Session access | `{{ session.get('display_name') }}` | User info display |
| Request access | `{{ request.path }}` | Active nav detection |
| Global `g` | `{{ g.pending_reset_count }}` | Admin badge |
