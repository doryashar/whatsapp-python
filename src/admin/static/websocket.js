// Admin WebSocket Client for Real-time Updates

class AdminWebSocket {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000; // Start with 1 second
        this.maxReconnectDelay = 30000; // Max 30 seconds
        this.heartbeatInterval = null;
        this.sessionId = null;
        this.connected = false;
    }

    async connect() {
        try {
            // Get session ID from API
            const response = await fetch('/admin/api/session-id');
            if (!response.ok) {
                console.error('Failed to get session ID');
                return;
            }
            const data = await response.json();
            this.sessionId = data.session_id;

            // Connect to WebSocket
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/admin/ws?session_id=${this.sessionId}`;
            
            console.log('Connecting to admin WebSocket:', wsUrl);
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                console.log('Admin WebSocket connected');
                this.connected = true;
                this.reconnectAttempts = 0;
                this.reconnectDelay = 1000;
                this.startHeartbeat();
            };

            this.ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this.onMessage(message);
                } catch (e) {
                    console.error('Failed to parse WebSocket message:', e);
                }
            };

            this.ws.onclose = (event) => {
                console.log('Admin WebSocket disconnected:', event.code, event.reason);
                this.connected = false;
                this.stopHeartbeat();
                this.onClose(event);
            };

            this.ws.onerror = (error) => {
                console.error('Admin WebSocket error:', error);
                this.connected = false;
            };

        } catch (error) {
            console.error('Failed to connect to admin WebSocket:', error);
            this.scheduleReconnect();
        }
    }

    onMessage(message) {
        console.log('Admin WebSocket message:', message.type, message.data);

        switch (message.type) {
            case 'tenant_state_changed':
                // Refresh tenant list
                if (typeof htmx !== 'undefined') {
                    htmx.trigger('#tenants-list', 'load');
                    // Also refresh stats if on dashboard
                    htmx.trigger('.grid', 'load');
                }
                // Show notification
                this.showNotification(
                    `Tenant ${message.data.tenant_name}: ${message.data.event}`,
                    'info'
                );
                break;

            case 'new_message':
                // Refresh message list
                if (typeof htmx !== 'undefined') {
                    htmx.trigger('#messages-list', 'load');
                    // Also refresh stats
                    htmx.trigger('.grid', 'load');
                }
                // Show notification with message preview
                const preview = message.data.message.text ?
                    message.data.message.text.substring(0, 50) :
                    'Media message';
                this.showNotification(
                    `New message from ${message.data.tenant_name}: ${preview}`,
                    'success'
                );
                break;

            case 'webhook_attempt':
                // Refresh webhook history
                if (typeof htmx !== 'undefined') {
                    htmx.trigger('#webhook-history', 'load');
                }
                // Show notification for failed webhooks
                if (!message.data.success) {
                    this.showNotification(
                        `Webhook failed: ${message.data.url}`,
                        'error'
                    );
                }
                break;

            case 'security_event':
                // Refresh security lists
                if (typeof htmx !== 'undefined') {
                    htmx.trigger('#blocked-ips', 'load');
                    htmx.trigger('#failed-auth', 'load');
                }
                // Show security alert
                this.showNotification(
                    `Security event: ${message.data.event} - ${message.data.ip}`,
                    'warning'
                );
                break;

            case 'pong':
                // Heartbeat response, do nothing
                break;

            default:
                console.log('Unknown WebSocket message type:', message.type);
        }
    }

    onClose(event) {
        // Attempt to reconnect unless explicitly closed
        if (event.code !== 1000) {
            this.scheduleReconnect();
        }
    }

    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnect attempts reached');
            this.showNotification(
                'Lost connection to server. Please refresh the page.',
                'error'
            );
            return;
        }

        this.reconnectAttempts++;
        const delay = Math.min(
            this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
            this.maxReconnectDelay
        );

        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

        setTimeout(() => {
            this.connect();
        }, delay);
    }

    startHeartbeat() {
        this.heartbeatInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 30000); // Send ping every 30 seconds
    }

    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 px-6 py-3 rounded-lg shadow-lg z-50 transition-all transform translate-x-full`;
        
        // Set color based on type
        const colors = {
            'info': 'bg-blue-600',
            'success': 'bg-green-600',
            'warning': 'bg-yellow-600',
            'error': 'bg-red-600'
        };
        notification.classList.add(colors[type] || colors.info);
        
        notification.innerHTML = `
            <div class="flex items-center space-x-2">
                <span class="text-white font-medium">${message}</span>
                <button onclick="this.parentElement.parentElement.remove()" class="text-white hover:text-gray-200">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
        `;

        document.body.appendChild(notification);

        // Animate in
        setTimeout(() => {
            notification.classList.remove('translate-x-full');
        }, 10);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            notification.classList.add('translate-x-full');
            setTimeout(() => {
                notification.remove();
            }, 300);
        }, 5000);
    }

    disconnect() {
        this.stopHeartbeat();
        if (this.ws) {
            this.ws.close(1000, 'User disconnect');
            this.ws = null;
        }
        this.connected = false;
    }
}

// Global instance
let adminWS = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize on admin pages
    if (window.location.pathname.startsWith('/admin')) {
        adminWS = new AdminWebSocket();
        adminWS.connect();
        console.log('Admin WebSocket initialized');
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (adminWS) {
        adminWS.disconnect();
    }
});
