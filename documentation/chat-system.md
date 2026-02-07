# Chat System

[Back to Index](README.md)

---

## Overview

The chat system provides **channel-based group messaging** similar to Slack or Discord. It consists of:

- **Backend:** `routes/chat.py` (server-rendered pages) and `routes/api.py` (JSON API for real-time features)
- **Frontend:** `templates/chat/chat.html` (Jinja2 template) and `static/js/chat.js` (AJAX polling)
- **Database tables:** `channels`, `messages`, `files`

---

## Source File: `routes/chat.py`

This file defines the `chat_bp` blueprint with URL prefix `/chat`. It contains 3 routes that handle page rendering and channel creation.

### Route: `GET /chat/` -- Chat Index

**Function:** `index()` (lines 8-39)
**Decorator:** `@login_required`

This is the main chat page. It renders the channel list and messages for the active channel.

**Logic flow:**
1. Queries all channels: `SELECT * FROM channels ORDER BY name`
2. Determines the active channel:
   - If `?channel=<id>` query parameter is present: uses that channel
   - Otherwise: defaults to the channel named `'general'`
   - If neither exists: falls back to the first channel in the list
3. Fetches messages for the active channel with a multi-table JOIN:
   ```sql
   SELECT m.*, u.username, u.display_name, u.avatar_filename,
          f.filename as attachment_filename, f.mime_type as attachment_mime_type
   FROM messages m
   JOIN users u ON m.user_id = u.id
   LEFT JOIN files f ON m.attachment_id = f.id
   WHERE m.channel_id = ?
   ORDER BY m.created_at ASC
   ```
4. Renders `chat/chat.html` with `channels`, `active_channel`, and `messages`

### Route: `GET /chat/channel/<int:channel_id>` -- Channel Redirect

**Function:** `channel()` (lines 42-45)
**Decorator:** `@login_required`

Simply redirects to `GET /chat/?channel=<channel_id>`. This provides a clean URL for channel links.

### Route: `POST /chat/channel/create` -- Create Channel

**Function:** `create_channel()` (lines 48-73)
**Decorator:** `@login_required`

Creates a new chat channel.

**Logic flow:**
1. Extracts and normalizes the channel name: `strip().lower().replace(' ', '-')`
2. Validates: name must be at least 2 characters
3. Checks for duplicate names: `SELECT id FROM channels WHERE name = ?`
4. Inserts: `INSERT INTO channels (name, description, created_by) VALUES (?, ?, ?)`
5. Logs a `channel_create` event
6. Redirects to the newly created channel

---

## API Endpoints for Chat

These endpoints in `routes/api.py` power the real-time chat functionality via AJAX polling from `chat.js`.

### `GET /api/v1/channels` -- List All Channels

**Function:** `list_channels()` (lines 82-89)
**Auth:** `@api_auth_required`

Returns all channels with basic info:
```json
{
  "data": [
    {"id": 1, "name": "general", "description": "...", "created_at": "..."},
    {"id": 2, "name": "announcements", "description": "...", "created_at": "..."}
  ]
}
```

### `GET /api/v1/channels/activity` -- Channel Activity

**Function:** `channel_activity()` (lines 92-102)
**Auth:** `@api_auth_required`

Returns the latest message ID for each channel. Used by the frontend to detect unread messages.

```json
{
  "data": {
    "1": 42,
    "2": 15,
    "3": 7
  }
}
```

The query: `SELECT channel_id, MAX(id) as latest_message_id FROM messages GROUP BY channel_id`

### `GET /api/v1/channels/<channel_id>/messages` -- Get Messages

**Function:** `get_messages()` (lines 105-131)
**Auth:** `@api_auth_required`
**Query params:** `since` (int, default 0) -- only return messages with `id > since`

Returns messages for a channel, optionally filtering by the `since` parameter for incremental polling.

```json
{
  "data": [
    {
      "id": 43,
      "content": "Hello!",
      "created_at": "2026-02-07 12:00:00",
      "is_encrypted": 0,
      "signature": null,
      "attachment_id": null,
      "user_id": 1,
      "username": "demo",
      "display_name": "Demo User",
      "avatar_filename": "default_avatar.png",
      "attachment_filename": null,
      "attachment_mime_type": null
    }
  ]
}
```

Returns 404 if the channel doesn't exist.

### `POST /api/v1/channels/<channel_id>/messages` -- Send Message

**Function:** `send_message()` (lines 134-176)
**Auth:** `@api_auth_required`
**Body:** `{"content": "text", "attachment_id": null}`

Sends a message to a channel.

**Validation:**
- Channel must exist (404 if not)
- Either `content` or `attachment_id` must be present (400 if neither)
- If `attachment_id` provided, the file must exist (400 if not)

**On success:** Returns 201 with the created message (same format as GET).

### `POST /api/v1/channels/<channel_id>/upload` -- Upload Attachment

**Function:** `upload_attachment()` (lines 179-222)
**Auth:** `@api_auth_required`
**Body:** Multipart form data with `file` field

Uploads a file attachment for use in chat messages.

**Process:**
1. Validates channel exists
2. Validates file is present and has allowed extension
3. Generates UUID-based filename: `{uuid.uuid4().hex}.{ext}`
4. Saves file to `UPLOAD_FOLDER`
5. Detects MIME type via `mimetypes.guess_type()`
6. Inserts record into `files` table
7. Returns 201 with file metadata including the `id` (used as `attachment_id` in messages)

### `POST /api/v1/channels/<channel_id>/typing` -- Post Typing Status

**Function:** `post_typing()` (lines 381-392)
**Auth:** `@api_auth_required`

Records that the current user is typing in the specified channel. Stores in an in-memory dictionary:

```python
_typing_status[channel_id][user_id] = {
    'username': display_name or username,
    'timestamp': time.time()
}
```

### `GET /api/v1/channels/<channel_id>/typing` -- Get Typing Users

**Function:** `get_typing()` (lines 395-410)
**Auth:** `@api_auth_required`

Returns a list of usernames currently typing in the channel. Entries older than **4 seconds** are automatically cleaned up. The current user is excluded from the results.

```json
{
  "data": ["Alice", "Bob"]
}
```

---

## Frontend: `static/js/chat.js`

This 284-line IIFE (Immediately Invoked Function Expression) handles all client-side chat functionality.

### Initialization (lines 3-51)

On page load, the script:
1. Reads `data-channel-id` from the `#chat-container` element
2. Gets references to DOM elements: messages container, input field, file input, preview area, typing indicator
3. Initializes tracking variables: `lastMessageId`, `pendingAttachmentId`, `typingTimeout`
4. Scans existing server-rendered messages to determine the last message ID
5. Marks the current channel as "read" in localStorage
6. Scrolls the message container to the bottom

### Polling Intervals

| What | Interval | Function |
|------|----------|----------|
| New messages | 3 seconds | `fetchNewMessages()` |
| Channel activity (unread badges) | 5 seconds | `fetchChannelActivity()` |
| Typing indicators | 1.5 seconds | `fetchTypingStatus()` |

### Unread Tracking (lines 23-48)

Uses `localStorage` key `corpchat_last_seen` to store:
```json
{
  "1": 42,    // channel 1: last seen message ID 42
  "2": 15     // channel 2: last seen message ID 15
}
```

- `getLastSeen()` reads from localStorage
- `setLastSeen(chId, msgId)` updates with the max of current and new value
- On each poll, compares latest channel activity against last seen to determine unread state

### Message Sending (`sendMessage()`, lines 172-210)

Exposed globally via `window.sendMessage` (called from the Send button and Enter key).

1. Gets content from input field
2. If neither content nor `pendingAttachmentId` exists: returns early
3. Disables input and send button
4. POSTs to `/api/v1/channels/{id}/messages` with JSON body
5. On success: appends message, updates lastMessageId, clears input, removes attachment preview
6. Finally: re-enables input and send button, focuses input

### File Attachment (lines 82-128)

When a file is selected via the file input:
1. Shows a local preview using `FileReader.readAsDataURL()`
2. Uploads the file via `POST /api/v1/channels/{id}/upload` (FormData)
3. On success: stores the returned file ID in `pendingAttachmentId`
4. On error: alerts and removes the preview

`window.removeAttachment()` clears the pending attachment state and hides the preview.

### Message Rendering (`appendMessage()`, lines 241-272)

Creates a DOM element for a new message:
- Avatar circle with the first letter of the display name
- Author name and timestamp
- Message content (HTML-escaped via `escapeHtml()`)
- Optional attachment image (`<img src="/files/view/{id}">`)

### HTML Escaping (`escapeHtml()`, lines 278-282)

```javascript
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
```

Uses the browser's built-in text-to-HTML conversion to prevent XSS in dynamically appended messages.

### Typing Indicators (lines 62-76, 212-239)

**Sending:** When the user types, a typing signal is sent via `POST /api/v1/channels/{id}/typing`, debounced to at most once every 2 seconds.

**Receiving:** Every 1.5 seconds, `GET /api/v1/channels/{id}/typing` is polled. The response is displayed as:
- 1 person: "Alice is typing"
- 2 people: "Alice and Bob are typing"
- 3+ people: "Several people are typing"

---

## Template: `templates/chat/chat.html`

Extends `base.html` and defines these blocks:

### `sidebar_extra` Block
Renders the channel list in the sidebar:
- Each channel as a clickable link with `data-channel-id` attribute
- Mute button next to each channel
- "has-unread" CSS class applied by JavaScript
- "+ New Channel" button that opens the create channel modal

### `content` Block
The main chat area:
- **Message list:** Server-rendered messages (initial load), then JavaScript appends new ones
- **Typing indicator:** Hidden by default, shown by `chat.js`
- **Attachment preview:** Hidden by default, shown when a file is selected
- **Chat input area:** File attach button, text input, Send button
- **Create Channel Modal:** Form with name and description fields

### `extra_scripts` Block
Includes `chat.js`.

---

## Channel Name Normalization

When creating a channel, the name is normalized (`routes/chat.py:51`):

```python
name = request.form.get('name', '').strip().lower().replace(' ', '-')
```

Examples:
- `"Project Alpha"` becomes `"project-alpha"`
- `"  GENERAL  "` becomes `"general"`
- `"My Channel"` becomes `"my-channel"`
