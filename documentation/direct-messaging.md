# Direct Messaging

[Back to Index](README.md)

---

## Overview

The direct messaging (DM) system provides **1-to-1 private conversations** between users. It mirrors the channel chat system in structure but operates on separate database tables (`dm_conversations`, `dm_messages`) and has its own set of API endpoints.

- **Backend:** `routes/dm.py` (server-rendered pages) and `routes/api.py` (JSON API for polling)
- **Frontend:** `templates/dm/dm.html` (Jinja2 template) and `static/js/dm.js` (AJAX polling)

---

## Source File: `routes/dm.py`

This file defines the `dm_bp` blueprint with URL prefix `/dm`.

### Helper: `get_or_create_conversation()` (lines 8-24)

This function ensures exactly one conversation record exists between any two users.

```python
def get_or_create_conversation(user1_id, user2_id):
    low, high = sorted([user1_id, user2_id])
    db = get_db()
    conv = db.execute(
        "SELECT * FROM dm_conversations WHERE user1_id = ? AND user2_id = ?",
        (low, high)
    ).fetchone()
    if conv:
        return conv['id']
    cursor = db.execute(
        "INSERT INTO dm_conversations (user1_id, user2_id) VALUES (?, ?)",
        (low, high)
    )
    db.commit()
    return cursor.lastrowid
```

**Key design:** The lower user ID is always stored as `user1_id` and the higher as `user2_id`. Combined with the `UNIQUE(user1_id, user2_id)` constraint, this guarantees exactly one conversation per user pair regardless of who initiates.

### Route: `GET /dm/` -- DM Index

**Function:** `index()` (lines 27-30)
**Decorator:** `@login_required`

Calls `dm_view(None)` -- renders the DM page with no active conversation.

### Route: `GET /dm/<int:conversation_id>` -- View Conversation

**Function:** `conversation()` (lines 33-36)
**Decorator:** `@login_required`

Calls `dm_view(conversation_id)` -- renders the DM page with the specified conversation active.

### Route: `GET /dm/user/<int:user_id>` -- Start DM with User

**Function:** `start_with_user()` (lines 39-55)
**Decorator:** `@login_required`

Creates or retrieves a conversation with the specified user and redirects to it.

**Validation:**
- Cannot DM yourself (shows error flash)
- Target user must exist and be active

### Route: `POST /dm/new` -- New Conversation from Picker

**Function:** `new_conversation()` (lines 58-66)
**Decorator:** `@login_required`

Handles the "New Message" modal form submission. Reads `user_id` from form data and redirects to `start_with_user`.

### Shared View: `dm_view()` (lines 69-133)

This is the main rendering function used by both `index()` and `conversation()`.

**Logic flow:**

1. **Fetch conversations list:**
   ```sql
   SELECT dc.id, dc.created_at,
          CASE WHEN dc.user1_id = ? THEN dc.user2_id ELSE dc.user1_id END as other_user_id,
          CASE WHEN dc.user1_id = ? THEN u2.username ELSE u1.username END as other_username,
          CASE WHEN dc.user1_id = ? THEN u2.display_name ELSE u1.display_name END as other_display_name
   FROM dm_conversations dc
   JOIN users u1 ON dc.user1_id = u1.id
   JOIN users u2 ON dc.user2_id = u2.id
   WHERE dc.user1_id = ? OR dc.user2_id = ?
   ORDER BY dc.created_at DESC
   ```
   This query uses `CASE` expressions to always return the **other** user's info regardless of which position the current user is in.

2. **If conversation_id is provided:**
   - Verify the current user is a participant (access control)
   - Fetch all messages with user and attachment info:
     ```sql
     SELECT dm.*, u.username, u.display_name, u.avatar_filename,
            f.filename as attachment_filename, f.mime_type as attachment_mime_type
     FROM dm_messages dm
     JOIN users u ON dm.sender_id = u.id
     LEFT JOIN files f ON dm.attachment_id = f.id
     WHERE dm.conversation_id = ?
     ORDER BY dm.created_at ASC
     ```
   - Get the other user's info for the page header

3. **Fetch all active users** (excluding self) for the "New Message" user picker

4. **Render** `dm/dm.html` with: `conversations`, `active_conv`, `other_user`, `messages`, `all_users`

---

## API Endpoints for DM

These endpoints in `routes/api.py` power the real-time DM features.

### `GET /api/v1/dm/activity` -- DM Activity

**Function:** `dm_activity()` (lines 415-430)
**Auth:** `@api_auth_required`

Returns the latest message ID for each conversation the current user is part of.

```json
{
  "data": {
    "1": 28,
    "3": 42
  }
}
```

### `GET /api/v1/dm/<conversation_id>/messages` -- Get DM Messages

**Function:** `get_dm_messages()` (lines 433-460)
**Auth:** `@api_auth_required`
**Query params:** `since` (int, default 0)

Returns messages for a conversation, filtered by `id > since` for incremental polling.

**Access control:** Verifies the current user is a participant:
```sql
SELECT * FROM dm_conversations WHERE id = ? AND (user1_id = ? OR user2_id = ?)
```
Returns 404 if the user is not a participant.

### `POST /api/v1/dm/<conversation_id>/messages` -- Send DM

**Function:** `send_dm_message()` (lines 463-508)
**Auth:** `@api_auth_required`
**Body:** `{"content": "text", "attachment_id": null}`

Sends a message in a DM conversation.

**Validation:**
- Conversation must exist and current user must be a participant
- Either `content` or `attachment_id` must be present
- If `attachment_id`, the file record must exist

**Returns:** 201 with the created message.

### `POST /api/v1/dm/<conversation_id>/upload` -- Upload DM Attachment

**Function:** `upload_dm_attachment()` (lines 511-558)
**Auth:** `@api_auth_required`

Identical to channel upload but:
- Verifies conversation access
- Does **not** set `channel_id` on the file record (it's a DM upload)

### `POST /api/v1/dm/<conversation_id>/typing` -- Post DM Typing

**Function:** `post_dm_typing()` (lines 561-572)
**Auth:** `@api_auth_required`

Records typing status in `_dm_typing_status` (separate from channel typing).

### `GET /api/v1/dm/<conversation_id>/typing` -- Get DM Typing

**Function:** `get_dm_typing()` (lines 575-588)
**Auth:** `@api_auth_required`

Returns typing users for the conversation. Same 4-second expiry as channel typing.

---

## Frontend: `static/js/dm.js`

This 268-line IIFE mirrors `chat.js` but operates on DM conversations.

### Key Differences from `chat.js`

| Feature | chat.js | dm.js |
|---------|---------|-------|
| Container ID | `#chat-container` | `#dm-container` |
| Data attribute | `data-channel-id` | `data-conversation-id` |
| localStorage key | `corpchat_last_seen` | `corpchat_dm_last_seen` |
| Messages endpoint | `/api/v1/channels/{id}/messages` | `/api/v1/dm/{id}/messages` |
| Upload endpoint | `/api/v1/channels/{id}/upload` | `/api/v1/dm/{id}/upload` |
| Send function | `window.sendMessage()` | `window.sendDmMessage()` |
| Typing endpoint | `/api/v1/channels/{id}/typing` | `/api/v1/dm/{id}/typing` |
| Activity endpoint | `/api/v1/channels/activity` | `/api/v1/dm/activity` |
| Unread selector | `.channel-item[data-channel-id]` | `.dm-item[data-conv-id]` |
| Mutes check | `_PwnBoxMutes.channels()` | `_PwnBoxMutes.dms()` |

### Polling Intervals (same as chat.js)

| What | Interval |
|------|----------|
| New messages | 3 seconds |
| DM activity (unread badges) | 5 seconds |
| Typing indicators | 1.5 seconds |

### Typing Display

DM typing is simpler than channel typing -- it only shows one person's name:
```javascript
typingText.textContent = data.data[0] + ' is typing';
```

---

## Template: `templates/dm/dm.html`

Extends `base.html`.

### `sidebar_extra` Block
- Lists all DM conversations with the other user's name
- Each conversation has a mute button
- "dm-item" CSS class (shows `@` prefix instead of `#`)
- "+ New Message" button opens the user picker modal

### `content` Block
Three possible states:
1. **No conversations and none active:** Shows "No conversations yet" empty state
2. **Conversations exist but none selected:** Shows "Select a conversation" prompt
3. **Active conversation:** Shows messages, typing indicator, attachment preview, and input area

### New DM Modal
A `<select>` dropdown listing all active users (excluding self), submitted to `POST /dm/new`.

---

## Access Control

DM conversations have strict access control:
- Only the two participants can view messages
- Only participants can send messages
- Only participants can upload attachments
- Conversation existence is verified on every API call

This is enforced by checking:
```sql
WHERE id = ? AND (user1_id = ? OR user2_id = ?)
```
