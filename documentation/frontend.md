# Frontend JavaScript & CSS

[Back to Index](README.md)

---

## Overview

PwnBox's frontend consists of vanilla JavaScript (no frameworks) and custom CSS. The JavaScript handles real-time features via AJAX polling, while the CSS provides a Discord/Slack-inspired dark theme.

**JavaScript files:**
- `static/js/chat.js` (284 lines) -- channel chat functionality
- `static/js/dm.js` (268 lines) -- direct message functionality
- `static/js/admin.js` (11 lines) -- admin panel placeholder
- Inline script in `templates/base.html` (~150 lines) -- global features

**CSS files:**
- `static/css/main.css` (1088 lines) -- all application styling
- `static/css/admin.css` (35 lines) -- admin panel overrides

---

## JavaScript Architecture

### Base Template Inline Script (`base.html`, lines 87-239)

This IIFE runs on **every page** that extends `base.html` (all authenticated pages). It handles:

#### 1. Mute Management (lines 90-105, 197-232)

**Global state:**
```javascript
var mutedChannels = [];
var mutedDms = [];
var mutedUsers = [];
```

**`fetchMutes()`** -- calls `GET /api/v1/mutes`, updates the three arrays. Refreshes every 30 seconds.

**`updateMuteButtons()`** -- iterates over all `.btn-mute` elements, reads `data-mute-type` and `data-mute-id` attributes, and toggles:
- `.is-muted` class on the button and sibling channel/DM item
- Speaker icon (muted vs unmuted)
- Button title text

**Click handler** (lines 214-232) -- on any `.btn-mute` click:
1. Determines current mute state
2. POSTs to `/api/v1/mute` or `/api/v1/unmute`
3. Refreshes mute state and updates UI

**Global export:** `window._PwnBoxMutes` exposes mute state for `chat.js` and `dm.js`:
```javascript
window._PwnBoxMutes = {
    channels: function() { return mutedChannels; },
    dms: function() { return mutedDms; },
    users: function() { return mutedUsers; }
};
```

#### 2. Online Users (lines 107-126)

**`fetchOnlineUsers()`** -- calls `GET /api/v1/users/online`, renders the sidebar list.

For each user:
```javascript
var li = document.createElement('li');
li.className = 'online-user-item';
var name = u.display_name || u.username;
li.innerHTML = '<span class="online-dot"></span> ' + name.replace(/</g, '&lt;');
```

Note: HTML escaping is done with a simple regex replacement of `<` characters.

Refreshes every **10 seconds**.

#### 3. Navigation Badges (lines 128-188)

**`fetchNavBadges()`** -- determines unread counts for Chat and DM badges.

**Chat badge logic:**
1. Fetches `GET /api/v1/channels/activity` (latest message IDs per channel)
2. Reads `corpchat_last_seen` from localStorage
3. For each channel: if `latest > lastRead` and channel is not muted → count as unread
4. Updates `#chat-badge` element: shows count or hides

**DM badge logic:** Same pattern using `GET /api/v1/dm/activity` and `corpchat_dm_last_seen`.

Refreshes every **5 seconds**.

#### 4. Initialization (lines 234-238)

```javascript
fetchMutes().then(function() { updateMuteButtons(); fetchNavBadges(); });
fetchOnlineUsers();
setInterval(fetchOnlineUsers, 10000);
setInterval(fetchMutes, 30000);
setInterval(fetchNavBadges, 5000);
```

---

### `static/js/chat.js` (284 lines)

An IIFE that handles channel chat real-time features. Only runs when a `#chat-container` element with a `data-channel-id` attribute is present.

#### Initialization
1. Reads channel ID from `data-channel-id`
2. Gets DOM references for: messages container, input, file input, preview elements, typing indicator
3. Scans existing server-rendered `.message` elements to find `lastMessageId`
4. Marks channel as read in localStorage
5. Scrolls to bottom

#### Polling Setup

| Function | Interval | Purpose |
|----------|----------|---------|
| `fetchNewMessages()` | 3s | Polls `/api/v1/channels/{id}/messages?since={lastId}` |
| `fetchChannelActivity()` | 5s | Polls `/api/v1/channels/activity` for unread badges |
| `fetchTypingStatus()` | 1.5s | Polls `/api/v1/channels/{id}/typing` |

#### Key Functions

**`fetchNewMessages()` (lines 130-148)**
- Fetches messages newer than `lastMessageId`
- For each new message: checks for duplicates, calls `appendMessage()`, updates `lastMessageId`
- Marks channel as read and scrolls to bottom

**`fetchChannelActivity()` (lines 150-170)**
- Gets latest message IDs per channel
- Compares with localStorage read state
- Adds/removes `has-unread` class on channel sidebar links
- Respects mute state via `window._PwnBoxMutes.channels()`

**`sendMessage()` (lines 172-210)** (exposed as `window.sendMessage`)
- Reads input value and pending attachment ID
- Disables input/button during send
- POSTs JSON to `/api/v1/channels/{id}/messages`
- On success: appends message, clears input, removes attachment preview
- On error: silently ignores
- Re-enables input and focuses

**`appendMessage(msg)` (lines 241-272)**
Creates a message DOM element:
```html
<div class="message" data-message-id="43">
    <div class="message-avatar">D</div>
    <div class="message-body">
        <div class="message-header">
            <span class="message-author">Demo User</span>
            <span class="message-time">2026-02-07 12:00:00</span>
        </div>
        <div class="message-content">Hello!</div>
        <!-- Optional: -->
        <div class="message-attachment">
            <img src="/files/view/7" alt="attachment" loading="lazy">
        </div>
    </div>
</div>
```

**`escapeHtml(text)` (lines 278-282)**
```javascript
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
```
Uses the browser's DOM to safely escape HTML entities.

#### File Attachment Handling (lines 82-128)

When a file is selected:
1. `FileReader.readAsDataURL()` creates a local preview
2. Shows preview bar with image thumbnail and filename
3. Uploads via `POST /api/v1/channels/{id}/upload` (FormData)
4. Stores returned file ID in `pendingAttachmentId`
5. On send, includes `attachment_id` in the message payload

`window.removeAttachment()` clears the state and hides the preview.

#### Typing Indicators (lines 62-76, 212-239)

**Sending:** On keydown (not Enter), sends `POST /api/v1/channels/{id}/typing` debounced to once per 2 seconds.

**Receiving:** Polls every 1.5s. Display text:
- 1 typer: "Alice is typing"
- 2 typers: "Alice and Bob are typing"
- 3+ typers: "Several people are typing"

#### Enter Key Handling (lines 62-77)

```javascript
input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
        return;
    }
    // ... typing indicator logic
});
```
Enter sends the message. Shift+Enter does nothing special (single-line input).

---

### `static/js/dm.js` (268 lines)

Nearly identical to `chat.js` but for DM conversations. Key differences:

| Aspect | chat.js | dm.js |
|--------|---------|-------|
| Container | `#chat-container` | `#dm-container` |
| ID attribute | `data-channel-id` | `data-conversation-id` |
| localStorage key | `corpchat_last_seen` | `corpchat_dm_last_seen` |
| API base | `/api/v1/channels/` | `/api/v1/dm/` |
| Send function | `window.sendMessage` | `window.sendDmMessage` |
| Activity endpoint | `/api/v1/channels/activity` | `/api/v1/dm/activity` |
| Unread class target | `.channel-item[data-channel-id]` | `.dm-item[data-conv-id]` |
| Mute list | `_PwnBoxMutes.channels()` | `_PwnBoxMutes.dms()` |
| Typing display | Handles 1, 2, 3+ typers | Only shows first typer |
| ES version | Uses `const`, arrow functions | Uses `var`, `function` expressions |

---

### `static/js/admin.js` (11 lines)

Minimal placeholder:
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

Would auto-refresh pages with `[data-auto-refresh]` elements every 30 seconds, but no admin templates currently use this attribute.

---

## CSS Architecture

### `static/css/main.css` (1088 lines)

The main stylesheet uses **CSS custom properties** (variables) for theming.

#### CSS Variables (`:root`, lines 3-22)

```css
:root {
    --sidebar-bg: #1e1f22;         /* Sidebar background */
    --sidebar-text: #b5bac1;       /* Sidebar text color */
    --sidebar-hover: #35373c;      /* Sidebar hover state */
    --sidebar-active: #404249;     /* Sidebar active/selected state */
    --topbar-bg: #2b2d31;          /* Top bar background */
    --topbar-text: #f2f3f5;        /* Top bar text */
    --content-bg: #313338;         /* Main content area background */
    --card-bg: #2b2d31;            /* Card/panel background */
    --message-hover: #383a40;      /* Message hover highlight */
    --accent: #5865f2;             /* Primary accent (Discord blue) */
    --accent-hover: #4752c4;       /* Accent hover state */
    --danger: #ed4245;             /* Danger/error color (red) */
    --text-primary: #f2f3f5;       /* Primary text (near-white) */
    --text-secondary: #b5bac1;     /* Secondary text (gray) */
    --text-muted: #6d6f78;         /* Muted/subtle text */
    --border-color: #3f4147;       /* Border color */
    --input-bg: #1e1f22;           /* Input field background */
    --input-border: #3f4147;       /* Input field border */
}
```

#### Major Layout Sections

**App Layout (lines 39-43)**
```css
.app-layout {
    display: grid;
    grid-template-columns: 260px 1fr;
    height: 100vh;
}
```
Two-column layout: 260px fixed sidebar + fluid main content.

**Sidebar (lines 46-53)** -- full-height flex column with header, nav, channel list, online users, and footer.

**Main Content (lines 271-276)** -- flex column with topbar and scrollable content area.

**Chat Layout (lines 345-349)** -- flex column taking full height of the content area.

#### Component Styles

| Component | Lines | Description |
|-----------|-------|-------------|
| `.sidebar` | 46-268 | Sidebar layout, navigation, channel list, user info footer |
| `.topbar` | 278-314 | Top bar with page title and search form |
| `.content-area` | 322-327 | Scrollable main content |
| `.flash-msg` | 330-342 | Flash message alerts (amber/gold theme) |
| `.chat-layout` | 345-441 | Chat area: messages, input, buttons |
| `.message` | 357-411 | Individual message styling with avatar |
| `.btn` variants | 443-487 | Button styles: primary, danger, secondary, small |
| `.card` / `.stats-grid` | 489-529 | Card panels and statistics grid |
| `table` | 531-555 | Table styling for admin pages |
| `.form-group` | 557-595 | Form input styling |
| `.auth-page` / `.auth-card` | 597-678 | Standalone auth page centering and card |
| `.profile-*` | 680-725 | Profile page layout |
| `.file-item` | 727-758 | File listing rows |
| `.search-*` | 760-782 | Search results sections |
| `.modal-overlay` / `.modal` | 784-814 | Modal dialog overlays |
| `.online-users-*` | 868-894 | Online user list in sidebar |
| `.typing-indicator` | 896-932 | Typing indicator with bouncing dots animation |
| `.dm-item` | 934-954 | DM-specific sidebar items |
| `.attachment-preview` | 956-992 | File attachment preview bar |
| `.btn-attach` | 994-1009 | Attachment button |
| `.message-attachment` | 1011-1021 | Inline image attachments |
| `.nav-badge` | 1023-1037 | Unread count badges |
| `.btn-mute` / `.is-muted` | 1039-1088 | Mute toggle button and muted state |

#### Key Animations

**Typing indicator bounce (lines 929-932):**
```css
@keyframes typingBounce {
    0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
    30% { transform: translateY(-4px); opacity: 1; }
}
```
Three dots bounce sequentially with 0.2s delays between them.

#### Responsive Considerations

The current CSS does not include media queries or responsive breakpoints. The layout assumes a desktop viewport with at least ~800px width.

---

### `static/css/admin.css` (35 lines)

Minimal overrides for the admin panel:

```css
.admin-sidebar { background: #1a1a2e; }              /* Darker navy sidebar */
.admin-sidebar .nav-item:hover { background: #262640; }  /* Purple-tinted hover */
.admin-sidebar .nav-item.active { background: #2a2a4a; } /* Active state */
.admin-logo-icon { background: #d94a4a !important; }     /* Red logo icon */
.admin-sidebar ~ .main-content .stat-value { color: #d94a4a; } /* Red stat numbers */
```

The admin panel inherits all styles from `main.css` and only overrides colors to create a visually distinct admin experience (navy + red vs. dark gray + blue).

---

## Polling Summary

All polling intervals across the application:

| What | Interval | Source | Endpoint |
|------|----------|--------|----------|
| Online users | 10s | `base.html` | `GET /api/v1/users/online` |
| Mute state | 30s | `base.html` | `GET /api/v1/mutes` |
| Nav badges (chat) | 5s | `base.html` | `GET /api/v1/channels/activity` |
| Nav badges (DM) | 5s | `base.html` | `GET /api/v1/dm/activity` |
| Channel messages | 3s | `chat.js` | `GET /api/v1/channels/{id}/messages?since=` |
| Channel activity | 5s | `chat.js` | `GET /api/v1/channels/activity` |
| Channel typing | 1.5s | `chat.js` | `GET /api/v1/channels/{id}/typing` |
| DM messages | 3s | `dm.js` | `GET /api/v1/dm/{id}/messages?since=` |
| DM activity | 5s | `dm.js` | `GET /api/v1/dm/activity` |
| DM typing | 1.5s | `dm.js` | `GET /api/v1/dm/{id}/typing` |

**Total on a chat page:** Up to 6 concurrent polling loops.
