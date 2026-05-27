/**
 * Imdepa SDR Agent - Fernanda
 * Chat Interface JavaScript
 */

(function () {
    'use strict';

    // ============================================================
    // DOM Elements
    // ============================================================
    const chatMessages = document.getElementById('chatMessages');
    const messageInput = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');
    const quickReplies = document.getElementById('quickReplies');
    const welcomeCard = document.getElementById('welcomeCard');

    // ============================================================
    // State
    // ============================================================
    let sessionId = null;
    let isLoading = false;

    // ============================================================
    // Initialize
    // ============================================================
    async function init() {
        try {
            const res = await fetch('/api/chat/start', { method: 'POST' });
            const data = await res.json();
            sessionId = data.session_id;

            // Remove welcome card and show initial message
            if (welcomeCard) {
                welcomeCard.style.display = 'none';
            }
            appendMessage('bot', data.response);
        } catch (err) {
            console.error('Erro ao iniciar conversa:', err);
            appendMessage('bot', 'Ola! Eu sou a Fernanda, assistente comercial da Imdepa. Estamos com uma instabilidade momentanea no atendimento. Tente novamente em alguns instantes.');
        }
    }

    // ============================================================
    // Message Rendering
    // ============================================================
    function formatMessage(text) {
        // Convert markdown-like formatting to HTML
        let html = text
            // Bold
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            // Italic
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            // Line breaks to paragraphs
            .split('\n\n')
            .map(p => p.trim())
            .filter(p => p)
            .map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`)
            .join('');

        return html;
    }

    function getTimeString() {
        const now = new Date();
        return now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    }

    function appendMessage(role, text) {
        const row = document.createElement('div');
        row.className = `message-row ${role}`;

        const avatarHtml = role === 'bot'
            ? '<img src="/static/img/fernanda_icon.png" alt="Fernanda" class="msg-avatar-img">'
            : 'V';

        row.innerHTML = `
            <div class="msg-avatar">${avatarHtml}</div>
            <div>
                <div class="msg-bubble">${formatMessage(text)}</div>
                <div class="msg-time">${getTimeString()}</div>
            </div>
        `;

        chatMessages.appendChild(row);
        scrollToBottom();
    }

    function showTyping() {
        const typing = document.createElement('div');
        typing.className = 'typing-indicator';
        typing.id = 'typingIndicator';
        typing.innerHTML = `
            <div class="msg-avatar"><img src="/static/img/fernanda_icon.png" alt="Fernanda" class="msg-avatar-img"></div>
            <div class="typing-dots">
                <span></span><span></span><span></span>
            </div>
        `;
        chatMessages.appendChild(typing);
        scrollToBottom();
    }

    function hideTyping() {
        const typing = document.getElementById('typingIndicator');
        if (typing) typing.remove();
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        });
    }

    // ============================================================
    // Send Message
    // ============================================================
    async function sendMessage(text) {
        if (!text || !text.trim() || isLoading) return;

        const message = text.trim();
        isLoading = true;
        sendBtn.disabled = true;
        messageInput.value = '';
        messageInput.style.height = 'auto';

        // Hide quick replies after first user message
        if (quickReplies) {
            quickReplies.classList.add('hidden');
        }

        // Hide welcome card
        if (welcomeCard) {
            welcomeCard.style.display = 'none';
        }

        // Append user message
        appendMessage('user', message);

        // Show typing indicator
        showTyping();

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    message: message
                })
            });

            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`);
            }

            const data = await res.json();
            sessionId = data.session_id;

            hideTyping();
            appendMessage('bot', data.response);

        } catch (err) {
            console.error('Erro ao enviar mensagem:', err);
            hideTyping();
            appendMessage('bot', 'Desculpe, tive um problema ao processar sua mensagem. Pode tentar novamente?');
        } finally {
            isLoading = false;
            updateSendButton();
        }
    }

    // ============================================================
    // Input Handling
    // ============================================================
    function updateSendButton() {
        sendBtn.disabled = !messageInput.value.trim() || isLoading;
    }

    function autoResize() {
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
    }

    messageInput.addEventListener('input', () => {
        updateSendButton();
        autoResize();
    });

    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!sendBtn.disabled) {
                sendMessage(messageInput.value);
            }
        }
    });

    sendBtn.addEventListener('click', () => {
        sendMessage(messageInput.value);
    });

    // ============================================================
    // Quick Reply Chips
    // ============================================================
    document.querySelectorAll('.chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const msg = chip.getAttribute('data-message');
            if (msg) {
                sendMessage(msg);
            }
        });
    });

    // ============================================================
    // Start
    // ============================================================
    init();

})();


