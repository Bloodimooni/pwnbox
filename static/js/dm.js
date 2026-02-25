// PwnBox - DM JavaScript (AJAX polling + message send + image attachments + typing + unread)

(function () {
    const container = document.getElementById('dm-container');
    if (!container) return;

    const conversationId = container.dataset.conversationId;
    if (!conversationId) return;

    const currentUserId = parseInt(container.dataset.userId) || 0;
    const userRole = container.dataset.userRole || 'user';

    const messagesDiv = document.getElementById('dm-messages');
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
    const STORAGE_KEY = 'corpchat_dm_last_seen';

    function getLastSeen() {
        try {
            return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
        } catch (_) {
            return {};
        }
    }

    function setLastSeen(convId, msgId) {
        const seen = getLastSeen();
        seen[convId] = Math.max(seen[convId] || 0, msgId);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(seen));
    }

    // Determine the last message ID from existing messages
    const existingMessages = messagesDiv.querySelectorAll('.message');
    if (existingMessages.length > 0) {
        const lastMsg = existingMessages[existingMessages.length - 1];
        lastMessageId = parseInt(lastMsg.dataset.messageId) || 0;
    }

    // Mark current conversation as read
    if (lastMessageId > 0) {
        setLastSeen(conversationId, lastMessageId);
    }

    // Scroll to bottom on load
    scrollToBottom();

    // Poll for new messages every 3 seconds
    setInterval(fetchNewMessages, 3000);

    // Poll for DM activity every 5 seconds
    fetchDmActivity();
    setInterval(fetchDmActivity, 5000);

    // Poll for typing indicators every 1.5 seconds
    setInterval(fetchTypingStatus, 1500);

    // Send on Enter key + typing indicator
    if (input) {
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendDmMessage();
                return;
            }
            if (!typingTimeout) {
                sendTypingSignal();
                typingTimeout = setTimeout(function () {
                    typingTimeout = null;
                }, 2000);
            }
        });
    }

    // Handle file selection
    if (fileInput) {
        fileInput.addEventListener('change', function () {
            var file = fileInput.files[0];
            if (!file) return;

            var reader = new FileReader();
            reader.onload = function (e) {
                previewImg.src = e.target.result;
                previewName.textContent = file.name;
                preview.style.display = 'flex';
            };
            reader.readAsDataURL(file);

            var formData = new FormData();
            formData.append('file', file);

            fetch('/api/v1/dm/' + conversationId + '/upload', {
                method: 'POST',
                body: formData
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.data) {
                        pendingAttachmentId = data.data.id;
                    } else {
                        alert(data.error || 'Upload failed');
                        removeAttachment();
                    }
                })
                .catch(function () {
                    alert('Upload failed');
                    removeAttachment();
                });
        });
    }

    window.removeAttachment = function () {
        pendingAttachmentId = null;
        if (fileInput) fileInput.value = '';
        if (preview) preview.style.display = 'none';
        if (previewImg) previewImg.src = '';
        if (previewName) previewName.textContent = '';
    };

    // Delete a DM message
    window.deleteDmMessage = function (messageId) {
        if (!confirm('Delete this message?')) return;
        fetch('/api/v1/dm/' + conversationId + '/messages/' + messageId, { method: 'DELETE' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status === 'ok') {
                    var msgEl = messagesDiv.querySelector('[data-message-id="' + messageId + '"]');
                    if (msgEl) {
                        msgEl.classList.add('message-is-deleted');
                        var body = msgEl.querySelector('.message-body');
                        var header = body.querySelector('.message-header');
                        var delBtn = header.querySelector('.btn-delete-msg');
                        if (delBtn) delBtn.remove();
                        var content = body.querySelector('.message-content');
                        var attachment = body.querySelector('.message-attachment');
                        if (content) content.remove();
                        if (attachment) attachment.remove();
                        var deleted = document.createElement('div');
                        deleted.className = 'message-content message-deleted';
                        deleted.textContent = '[message deleted]';
                        body.appendChild(deleted);
                    }
                } else {
                    alert(data.error || 'Failed to delete message');
                }
            })
            .catch(function () { alert('Failed to delete message'); });
    };

    // Request conversation deletion
    window.requestDeleteConversation = function () {
        if (!confirm('Request deletion of this entire conversation? Both users must agree for it to be deleted.')) return;
        fetch('/api/v1/dm/' + conversationId + '/request-delete', { method: 'POST' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status === 'ok') {
                    if (data.deleted) {
                        window.location.href = '/dm/';
                    } else {
                        window.location.reload();
                    }
                } else {
                    alert(data.error || 'Failed to request deletion');
                }
            })
            .catch(function () { alert('Failed to request deletion'); });
    };

    // Cancel conversation deletion request
    window.cancelDeleteConversation = function () {
        fetch('/api/v1/dm/' + conversationId + '/cancel-delete', { method: 'POST' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status === 'ok') {
                    window.location.reload();
                } else {
                    alert(data.error || 'Failed to cancel deletion');
                }
            })
            .catch(function () { alert('Failed to cancel deletion'); });
    };

    function fetchNewMessages() {
        fetch('/api/v1/dm/' + conversationId + '/messages?since=' + lastMessageId)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.data && data.data.length > 0) {
                    data.data.forEach(function (msg) {
                        if (!messagesDiv.querySelector('[data-message-id="' + msg.id + '"]')) {
                            appendMessage(msg);
                        }
                        lastMessageId = Math.max(lastMessageId, msg.id);
                    });
                    setLastSeen(conversationId, lastMessageId);
                    scrollToBottom();
                }
            })
            .catch(function () {});
    }

    function fetchDmActivity() {
        fetch('/api/v1/dm/activity')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.data) return;
                var seen = getLastSeen();
                var muted = window._PwnBoxMutes ? window._PwnBoxMutes.dms() : [];
                var convLinks = document.querySelectorAll('.dm-item[data-conv-id]');
                convLinks.forEach(function (link) {
                    var convId = link.dataset.convId;
                    var latest = data.data[convId] || 0;
                    var lastRead = seen[convId] || 0;
                    if (latest > lastRead && convId !== conversationId && muted.indexOf(parseInt(convId)) === -1) {
                        link.classList.add('has-unread');
                    } else {
                        link.classList.remove('has-unread');
                    }
                });
            })
            .catch(function () {});
    }

    window.sendDmMessage = function () {
        if (!input) return;
        var content = input.value.trim();
        if (!content && !pendingAttachmentId) return;

        input.disabled = true;
        var sendBtn = document.getElementById('send-btn');
        if (sendBtn) sendBtn.disabled = true;

        var body = { content: content };
        if (pendingAttachmentId) {
            body.attachment_id = pendingAttachmentId;
        }

        fetch('/api/v1/dm/' + conversationId + '/messages', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.data) {
                    if (!messagesDiv.querySelector('[data-message-id="' + data.data.id + '"]')) {
                        appendMessage(data.data);
                    }
                    lastMessageId = Math.max(lastMessageId, data.data.id);
                    setLastSeen(conversationId, lastMessageId);
                    input.value = '';
                    removeAttachment();
                    scrollToBottom();
                }
            })
            .catch(function () {})
            .finally(function () {
                input.disabled = false;
                if (sendBtn) sendBtn.disabled = false;
                input.focus();
            });
    };

    function sendTypingSignal() {
        fetch('/api/v1/dm/' + conversationId + '/typing', { method: 'POST' })
            .catch(function () {});
    }

    function fetchTypingStatus() {
        fetch('/api/v1/dm/' + conversationId + '/typing')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!typingIndicator || !typingText) return;
                if (data.data && data.data.length > 0) {
                    typingText.textContent = data.data[0] + ' is typing';
                    typingIndicator.style.display = 'flex';
                } else {
                    typingIndicator.style.display = 'none';
                }
            })
            .catch(function () {});
    }

    function appendMessage(msg) {
        var div = document.createElement('div');
        div.className = 'message' + (msg.is_deleted ? ' message-is-deleted' : '');
        div.dataset.messageId = msg.id;
        div.dataset.userId = msg.sender_id || '';

        var displayName = msg.display_name || msg.username || 'Unknown';
        var initial = displayName.charAt(0).toUpperCase();

        var contentHtml = '';
        var attachmentHtml = '';
        var deleteBtnHtml = '';

        if (msg.is_deleted) {
            contentHtml = '<div class="message-content message-deleted">[message deleted]</div>';
        } else {
            if (msg.content) {
                contentHtml = '<div class="message-content">' + escapeHtml(msg.content) + '</div>';
            }
            if (msg.attachment_id) {
                attachmentHtml = '<div class="message-attachment"><img src="/files/view/' + msg.attachment_id + '" alt="attachment" loading="lazy"></div>';
            }
            deleteBtnHtml = '<button class="btn-delete-msg" onclick="deleteDmMessage(' + msg.id + ')" title="Delete message">&#128465;</button>';
        }

        var avatarHtml;
        if (msg.avatar_filename && msg.avatar_filename !== 'default_avatar.png') {
            avatarHtml = '<div class="message-avatar"><img src="/profile/avatar/' + encodeURIComponent(msg.avatar_filename) + '" alt="Avatar"></div>';
        } else {
            avatarHtml = '<div class="message-avatar">' + escapeHtml(initial) + '</div>';
        }

        div.innerHTML =
            avatarHtml +
            '<div class="message-body">' +
                '<div class="message-header">' +
                    '<span class="message-author">' + escapeHtml(displayName) + '</span>' +
                    '<span class="message-time">' + escapeHtml(msg.created_at || '') + '</span>' +
                    deleteBtnHtml +
                '</div>' +
                contentHtml +
                attachmentHtml +
            '</div>';

        messagesDiv.appendChild(div);
    }

    function scrollToBottom() {
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
})();
