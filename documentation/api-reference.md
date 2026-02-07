# REST API Reference

[Back to Index](README.md)

---

## Overview

PwnBox exposes a REST API at `/api/v1` for programmatic access. The API is defined in `routes/api.py` as the `api_bp` blueprint.

**Base URL:** `http://localhost:5000/api/v1`

**Content Type:** All request/response bodies are JSON (`application/json`) unless uploading files (which use `multipart/form-data`).

**Response Format:** All successful responses wrap data in a `"data"` key. Errors use an `"error"` key.

---

## Authentication

### Methods

The API supports two authentication methods, checked in order:

#### 1. API Token (Header)
Include the `X-API-Token` header with a valid user API token:
```
X-API-Token: a1b2c3d4-e5f6-7890-abcd-ef0123456789
```

#### 2. Session Cookie
If no API token header is present, the API falls back to the Flask session cookie (same as the web UI uses). This is how the JavaScript frontend authenticates.

### Getting a Token

**Endpoint:** `POST /api/v1/auth/token`
**Auth:** None required

**Request:**
```json
{
  "username": "demo",
  "password": "demo123"
}
```

**Success Response (200):**
```json
{
  "data": {
    "token": "a1b2c3d4-e5f6-7890-abcd-ef0123456789",
    "user_id": 1,
    "username": "demo"
  }
}
```

**Error Responses:**
- `400` -- `{"error": "JSON body required"}` (no JSON body sent)
- `401` -- `{"error": "Invalid credentials"}`
- `403` -- `{"error": "Account disabled"}`

### Authentication Errors

All `@api_auth_required` endpoints return:
```json
{"error": "Authentication required"}
```
with status `401` if authentication fails.

---

## Health Check

### `GET /api/v1/health`
**Auth:** None required

Returns application health status.

**Response (200):**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "service": "CorpChat"
}
```

---

## Channels

### `GET /api/v1/channels` -- List Channels
**Auth:** Required

**Response (200):**
```json
{
  "data": [
    {
      "id": 1,
      "name": "general",
      "description": "General discussion for the team",
      "created_at": "2026-02-07 10:00:00"
    },
    {
      "id": 2,
      "name": "announcements",
      "description": "Important announcements",
      "created_at": "2026-02-07 10:00:00"
    }
  ]
}
```

### `GET /api/v1/channels/activity` -- Channel Activity
**Auth:** Required

Returns the highest message ID per channel. Used to detect new/unread messages.

**Response (200):**
```json
{
  "data": {
    "1": 42,
    "2": 15,
    "3": 7
  }
}
```
Keys are channel IDs (as strings), values are the latest message IDs.

### `GET /api/v1/channels/<channel_id>/messages` -- Get Messages
**Auth:** Required

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `since` | int | `0` | Only return messages with `id > since` |

**Response (200):**
```json
{
  "data": [
    {
      "id": 43,
      "content": "Hello everyone!",
      "created_at": "2026-02-07 12:30:00",
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

**Error:** `404` if channel doesn't exist.

### `POST /api/v1/channels/<channel_id>/messages` -- Send Message
**Auth:** Required

**Request Body:**
```json
{
  "content": "Hello!",
  "attachment_id": null
}
```

At least one of `content` or `attachment_id` must be provided.

**Success Response (201):** Returns the created message in the same format as GET.

**Errors:**
- `404` -- Channel not found
- `400` -- No JSON body / no content or attachment / attachment not found

### `POST /api/v1/channels/<channel_id>/upload` -- Upload Attachment
**Auth:** Required

**Request:** `multipart/form-data` with a `file` field.

**Success Response (201):**
```json
{
  "data": {
    "id": 7,
    "filename": "screenshot.png",
    "mime_type": "image/png",
    "file_size": 245760
  }
}
```

**Errors:**
- `404` -- Channel not found
- `400` -- No file provided / no file selected / file type not allowed

### `POST /api/v1/channels/<channel_id>/typing` -- Post Typing Indicator
**Auth:** Required

Records that the authenticated user is currently typing in this channel.

**Response (200):**
```json
{"status": "ok"}
```

### `GET /api/v1/channels/<channel_id>/typing` -- Get Typing Users
**Auth:** Required

Returns usernames of users currently typing (excludes the requesting user). Entries expire after 4 seconds.

**Response (200):**
```json
{
  "data": ["Alice", "Bob"]
}
```

---

## Direct Messages

### `GET /api/v1/dm/activity` -- DM Activity
**Auth:** Required

Returns the highest message ID per conversation for the authenticated user.

**Response (200):**
```json
{
  "data": {
    "1": 28,
    "3": 42
  }
}
```

### `GET /api/v1/dm/<conversation_id>/messages` -- Get DM Messages
**Auth:** Required

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `since` | int | `0` | Only return messages with `id > since` |

**Response (200):**
```json
{
  "data": [
    {
      "id": 29,
      "content": "Hey, how are you?",
      "created_at": "2026-02-07 14:00:00",
      "attachment_id": null,
      "sender_id": 1,
      "username": "demo",
      "display_name": "Demo User",
      "avatar_filename": "default_avatar.png",
      "attachment_filename": null,
      "attachment_mime_type": null
    }
  ]
}
```

**Error:** `404` if conversation doesn't exist or user is not a participant.

### `POST /api/v1/dm/<conversation_id>/messages` -- Send DM
**Auth:** Required

**Request Body:**
```json
{
  "content": "Hey!",
  "attachment_id": null
}
```

**Success Response (201):** Returns the created message.

**Errors:**
- `404` -- Conversation not found / not a participant
- `400` -- No JSON body / no content or attachment / attachment not found

### `POST /api/v1/dm/<conversation_id>/upload` -- Upload DM Attachment
**Auth:** Required

**Request:** `multipart/form-data` with a `file` field.

**Success Response (201):** Same format as channel upload.

**Errors:** Same as channel upload, plus `404` for invalid conversation.

### `POST /api/v1/dm/<conversation_id>/typing` -- Post DM Typing
**Auth:** Required

**Response (200):** `{"status": "ok"}`

### `GET /api/v1/dm/<conversation_id>/typing` -- Get DM Typing
**Auth:** Required

**Response (200):**
```json
{
  "data": ["Alice"]
}
```

---

## Users

### `GET /api/v1/users/<user_id>` -- Get User Info
**Auth:** Required

Returns public profile information for a user.

**Response (200):**
```json
{
  "data": {
    "id": 1,
    "username": "demo",
    "display_name": "Demo User",
    "bio": "Just a demo account for testing.",
    "avatar_filename": "default_avatar.png",
    "created_at": "2026-02-07 10:00:00"
  }
}
```

**Error:** `404` if user not found.

### `GET /api/v1/users/me` -- Get Current User
**Auth:** Required

Returns full profile info for the authenticated user (includes sensitive fields).

**Response (200):**
```json
{
  "data": {
    "id": 1,
    "username": "demo",
    "email": "demo@corpchat.local",
    "display_name": "Demo User",
    "bio": "Just a demo account for testing.",
    "avatar_filename": "default_avatar.png",
    "role": "user",
    "api_token": "a1b2c3d4-...",
    "created_at": "2026-02-07 10:00:00"
  }
}
```

Note: This endpoint returns `email`, `role`, and `api_token` which are not included in the public user endpoint.

### `GET /api/v1/users/online` -- Online Users
**Auth:** Required

Returns users active within the last 5 minutes.

**Response (200):**
```json
{
  "data": [
    {
      "id": 1,
      "username": "demo",
      "display_name": "Demo User",
      "avatar_filename": "default_avatar.png"
    }
  ]
}
```

**Query:**
```sql
SELECT id, username, display_name, avatar_filename
FROM users
WHERE is_active = 1
  AND last_activity IS NOT NULL
  AND last_activity >= datetime('now', '-5 minutes')
ORDER BY username
```

---

## Files

### `GET /api/v1/files` -- List All Files
**Auth:** Required

**Response (200):**
```json
{
  "data": [
    {
      "id": 1,
      "filename": "report.pdf",
      "file_size": 1048576,
      "mime_type": "application/pdf",
      "created_at": "2026-02-07 11:00:00",
      "is_encrypted": 0,
      "uploaded_by_name": "demo"
    }
  ]
}
```

---

## Search

### `GET /api/v1/search` -- Search Messages and Users
**Auth:** Required

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | string | (required) | Search query |
| `type` | string | `"all"` | `"all"`, `"messages"`, or `"users"` |

**Response (200):**
```json
{
  "data": {
    "messages": [
      {
        "id": 5,
        "content": "Hello everyone!",
        "created_at": "2026-02-07 12:00:00",
        "username": "demo",
        "channel_name": "general"
      }
    ],
    "users": [
      {
        "id": 1,
        "username": "demo",
        "display_name": "Demo User",
        "bio": "Just a demo account.",
        "avatar_filename": "default_avatar.png"
      }
    ]
  }
}
```

**Limits:** 50 messages, 20 users.

**Error:** `400` if `q` is empty.

---

## Mutes

### `GET /api/v1/mutes` -- Get User's Mutes
**Auth:** Required

**Response (200):**
```json
{
  "data": {
    "channel": [2, 3],
    "dm": [1],
    "user": []
  }
}
```

Each array contains the IDs of muted targets.

### `POST /api/v1/mute` -- Mute a Target
**Auth:** Required

**Request Body:**
```json
{
  "type": "channel",
  "target_id": 2
}
```

Valid types: `"channel"`, `"dm"`, `"user"`

**Response (200):** `{"status": "ok"}`

Uses `INSERT OR IGNORE` so muting an already-muted target is a no-op.

### `POST /api/v1/unmute` -- Unmute a Target
**Auth:** Required

**Request Body:**
```json
{
  "type": "channel",
  "target_id": 2
}
```

**Response (200):** `{"status": "ok"}`

---

## Cryptography (Stub Endpoints)

These endpoints are placeholder implementations intended for the CTF crypto challenges.

### `POST /api/v1/crypto/sign` -- Sign Message
**Auth:** Required

Signs a message using HMAC-SHA256 with the configured `CRYPTO_SIGNING_KEY`.

**Request:**
```json
{"message": "Hello"}
```

**Response (200):**
```json
{
  "data": {
    "message": "Hello",
    "signature": "a1b2c3d4e5f6...",
    "algorithm": "HMAC-SHA256"
  }
}
```

**Implementation:**
```python
key = current_app.config.get('CRYPTO_SIGNING_KEY', 'default-key')
signature = hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()
```

### `POST /api/v1/crypto/verify` -- Verify Signature
**Auth:** Required

Verifies an HMAC-SHA256 signature.

**Request:**
```json
{
  "message": "Hello",
  "signature": "a1b2c3d4e5f6..."
}
```

**Response (200):**
```json
{
  "data": {
    "valid": true,
    "algorithm": "HMAC-SHA256"
  }
}
```

Uses `hmac.compare_digest()` for constant-time comparison.

### `POST /api/v1/crypto/encrypt` -- Encrypt Data
**Auth:** Required

**Warning:** This is a **placeholder** that only performs base64 encoding (not real encryption).

**Request:**
```json
{"data": "secret message"}
```

**Response (200):**
```json
{
  "data": {
    "encrypted": "c2VjcmV0IG1lc3NhZ2U=",
    "algorithm": "base64-placeholder"
  }
}
```

---

## Complete Endpoint Summary

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | No | Health check |
| POST | `/auth/token` | No | Get API token |
| GET | `/channels` | Yes | List channels |
| GET | `/channels/activity` | Yes | Channel latest message IDs |
| GET | `/channels/<id>/messages` | Yes | Get channel messages |
| POST | `/channels/<id>/messages` | Yes | Send channel message |
| POST | `/channels/<id>/upload` | Yes | Upload channel attachment |
| POST | `/channels/<id>/typing` | Yes | Post typing indicator |
| GET | `/channels/<id>/typing` | Yes | Get typing users |
| GET | `/users/<id>` | Yes | Get user profile |
| GET | `/users/me` | Yes | Get current user |
| GET | `/users/online` | Yes | Get online users |
| GET | `/files` | Yes | List all files |
| GET | `/search` | Yes | Search messages/users |
| GET | `/mutes` | Yes | Get muted targets |
| POST | `/mute` | Yes | Mute a target |
| POST | `/unmute` | Yes | Unmute a target |
| GET | `/dm/activity` | Yes | DM latest message IDs |
| GET | `/dm/<id>/messages` | Yes | Get DM messages |
| POST | `/dm/<id>/messages` | Yes | Send DM message |
| POST | `/dm/<id>/upload` | Yes | Upload DM attachment |
| POST | `/dm/<id>/typing` | Yes | Post DM typing |
| GET | `/dm/<id>/typing` | Yes | Get DM typing |
| POST | `/crypto/sign` | Yes | Sign message (HMAC) |
| POST | `/crypto/verify` | Yes | Verify signature |
| POST | `/crypto/encrypt` | Yes | "Encrypt" data (base64) |
