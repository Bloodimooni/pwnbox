// CorpChat - Chat JavaScript (AJAX polling + message send + image attachments + unread notifications)

(function () {
    const container = document.getElementById('chat-container');
    if (!container) return;

    const channelId = container.dataset.channelId;
    if (!channelId) return;

    const messagesDiv = document.getElementById('chat-messages');
    const input = document.getElementById('message-input');
    const fileInput = document.getElementById('file-input');
    const preview = document.getElementById('attachment-preview');
    const previewImg = document.getElementById('attachment-preview-img');
    const previewName = document.getElementById('attachment-preview-name');
    const typingIndicator = document.getElementById('typing-indicator');
    const typingText = document.getElementById('typing-text');
    let lastMessageId = 0;
    let pendingAttachmentId = null;
    let typingTimeout = null;

    // --- Unread tracking via localStorage ---
    const STORAGE_KEY = 'corpchat_last_seen';

    function getLastSeen() {
        try {
            return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
        } catch (_) {
            return {};
        }
    }

    function setLastSeen(chId, msgId) {
        const seen = getLastSeen();
        seen[chId] = Math.max(seen[chId] || 0, msgId);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(seen));
    }

    // Determine the last message ID from existing messages
    const existingMessages = messagesDiv.querySelectorAll('.message');
    if (existingMessages.length > 0) {
        const lastMsg = existingMessages[existingMessages.length - 1];
        lastMessageId = parseInt(lastMsg.dataset.messageId) || 0;
    }

    // Mark current channel as read
    if (lastMessageId > 0) {
        setLastSeen(channelId, lastMessageId);
    }

    // Scroll to bottom on load
    scrollToBottom();

    // Poll for new messages every 3 seconds
    setInterval(fetchNewMessages, 3000);

    // Poll for channel activity every 5 seconds
    fetchChannelActivity();
    setInterval(fetchChannelActivity, 5000);

    // Send on Enter key + typing indicator
    if (input) {
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
                return;
            }
            // Send typing signal (debounced: at most once per 2 seconds)
            if (!typingTimeout) {
                sendTypingSignal();
                typingTimeout = setTimeout(function () {
                    typingTimeout = null;
                }, 2000);
            }
        });
    }

    // Poll for typing indicators every 1.5 seconds
    setInterval(fetchTypingStatus, 1500);

    // Handle file selection
    if (fileInput) {
        fileInput.addEventListener('change', function () {
            const file = fileInput.files[0];
            if (!file) return;

            // Show local preview
            const reader = new FileReader();
            reader.onload = function (e) {
                previewImg.src = e.target.result;
                previewName.textContent = file.name;
                preview.style.display = 'flex';
            };
            reader.readAsDataURL(file);

            // Upload the file
            const formData = new FormData();
            formData.append('file', file);

            fetch(`/api/v1/channels/${channelId}/upload`, {
                method: 'POST',
                body: formData
            })
                .then(r => r.json())
                .then(data => {
                    if (data.data) {
                        pendingAttachmentId = data.data.id;
                    } else {
                        alert(data.error || 'Upload failed');
                        removeAttachment();
                    }
                })
                .catch(() => {
                    alert('Upload failed');
                    removeAttachment();
                });
        });
    }

    // Remove attachment (exposed globally for onclick)
    window.removeAttachment = function () {
        pendingAttachmentId = null;
        if (fileInput) fileInput.value = '';
        if (preview) preview.style.display = 'none';
        if (previewImg) previewImg.src = '';
        if (previewName) previewName.textContent = '';
    };

    function fetchNewMessages() {
        fetch(`/api/v1/channels/${channelId}/messages?since=${lastMessageId}`)
            .then(r => r.json())
            .then(data => {
                if (data.data && data.data.length > 0) {
                    data.data.forEach(msg => {
                        // Don't add duplicates
                        if (!messagesDiv.querySelector(`[data-message-id="${msg.id}"]`)) {
                            appendMessage(msg);
                        }
                        lastMessageId = Math.max(lastMessageId, msg.id);
                    });
                    // Mark current channel as read
                    setLastSeen(channelId, lastMessageId);
                    scrollToBottom();
                }
            })
            .catch(() => { /* silently ignore polling errors */ });
    }

    function fetchChannelActivity() {
        fetch('/api/v1/channels/activity')
            .then(r => r.json())
            .then(data => {
                if (!data.data) return;
                const seen = getLastSeen();
                const muted = window._PwnBoxMutes ? window._PwnBoxMutes.channels() : [];
                const channelLinks = document.querySelectorAll('.channel-item[data-channel-id]');
                channelLinks.forEach(link => {
                    const chId = link.dataset.channelId;
                    const latest = data.data[chId] || 0;
                    const lastRead = seen[chId] || 0;
                    if (latest > lastRead && chId !== channelId && muted.indexOf(parseInt(chId)) === -1) {
                        link.classList.add('has-unread');
                    } else {
                        link.classList.remove('has-unread');
                    }
                });
            })
            .catch(() => { /* silently ignore */ });
    }

    window.sendMessage = function () {
        if (!input) return;
        const content = input.value.trim();
        if (!content && !pendingAttachmentId) return;

        input.disabled = true;
        const sendBtn = document.getElementById('send-btn');
        if (sendBtn) sendBtn.disabled = true;

        const body = { content: content };
        if (pendingAttachmentId) {
            body.attachment_id = pendingAttachmentId;
        }

        fetch(`/api/v1/channels/${channelId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        })
            .then(r => r.json())
            .then(data => {
                if (data.data) {
                    if (!messagesDiv.querySelector(`[data-message-id="${data.data.id}"]`)) {
                        appendMessage(data.data);
                    }
                    lastMessageId = Math.max(lastMessageId, data.data.id);
                    setLastSeen(channelId, lastMessageId);
                    input.value = '';
                    removeAttachment();
                    scrollToBottom();
                }
            })
            .catch(() => { /* handle error silently */ })
            .finally(() => {
                input.disabled = false;
                if (sendBtn) sendBtn.disabled = false;
                input.focus();
            });
    };

    function sendTypingSignal() {
        fetch(`/api/v1/channels/${channelId}/typing`, { method: 'POST' })
            .catch(function () {});
    }

    function fetchTypingStatus() {
        fetch(`/api/v1/channels/${channelId}/typing`)
            .then(r => r.json())
            .then(data => {
                if (!typingIndicator || !typingText) return;
                if (data.data && data.data.length > 0) {
                    var names = data.data;
                    var text;
                    if (names.length === 1) {
                        text = names[0] + ' is typing';
                    } else if (names.length === 2) {
                        text = names[0] + ' and ' + names[1] + ' are typing';
                    } else {
                        text = 'Several people are typing';
                    }
                    typingText.textContent = text;
                    typingIndicator.style.display = 'flex';
                } else {
                    typingIndicator.style.display = 'none';
                }
            })
            .catch(function () {});
    }

    function appendMessage(msg) {
        const div = document.createElement('div');
        div.className = 'message';
        div.dataset.messageId = msg.id;

        const displayName = msg.display_name || msg.username || 'Unknown';
        const initial = displayName.charAt(0).toUpperCase();

        let contentHtml = '';
        if (msg.content) {
            contentHtml = `<div class="message-content">${escapeHtml(msg.content)}</div>`;
        }

        let attachmentHtml = '';
        if (msg.attachment_id) {
            attachmentHtml = `<div class="message-attachment"><img src="/files/view/${msg.attachment_id}" alt="attachment" loading="lazy"></div>`;
        }

        let avatarHtml;
        if (msg.avatar_filename && msg.avatar_filename !== 'default_avatar.png') {
            avatarHtml = `<div class="message-avatar"><img src="/profile/avatar/${encodeURIComponent(msg.avatar_filename)}" alt="Avatar"></div>`;
        } else {
            avatarHtml = `<div class="message-avatar">${escapeHtml(initial)}</div>`;
        }

        div.innerHTML = `
            ${avatarHtml}
            <div class="message-body">
                <div class="message-header">
                    <span class="message-author">${escapeHtml(displayName)}</span>
                    <span class="message-time">${escapeHtml(msg.created_at || '')}</span>
                </div>
                ${contentHtml}
                ${attachmentHtml}
            </div>
        `;

        messagesDiv.appendChild(div);
    }

    function scrollToBottom() {
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
})();
