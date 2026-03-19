// Frontend Error Reporting
(function() {
    var _lastErrorKey = '';
    var _lastErrorTime = 0;
    var _dedupWindow = 5000;

    function _errorKey(message, source, lineno) {
        return (message || '') + '|' + (source || '') + '|' + (lineno || 0);
    }

    window.reportFrontendError = function(errorInfo) {
        var key = _errorKey(errorInfo.message, errorInfo.source, errorInfo.lineno);
        var now = Date.now();
        if (key === _lastErrorKey && (now - _lastErrorTime) < _dedupWindow) {
            return;
        }
        _lastErrorKey = key;
        _lastErrorTime = now;

        var payload = {
            type: 'frontend_error',
            data: {
                message: errorInfo.message || 'Unknown error',
                source: errorInfo.source || null,
                lineno: errorInfo.lineno || null,
                colno: errorInfo.colno || null,
                stack: errorInfo.stack || null,
                error_type: errorInfo.error_type || null,
                url: window.location.href,
                user_agent: navigator.userAgent,
            }
        };

        if (window.adminWS && window.adminWS.connected) {
            try {
                window.adminWS.ws.send(JSON.stringify(payload));
                return;
            } catch (e) {
                // fall through to fetch
            }
        }

        if (navigator.sendBeacon) {
            try {
                navigator.sendBeacon(
                    '/admin/api/frontend-errors',
                    new Blob([JSON.stringify(payload.data)], {type: 'application/json'})
                );
                return;
            } catch (e) {
                // fall through to fetch
            }
        }

        try {
            fetch('/admin/api/frontend-errors', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload.data),
                keepalive: true,
            }).catch(function() {});
        } catch (e) {}
    };

    window.addEventListener('error', function(event) {
        window.reportFrontendError({
            message: event.message,
            source: event.filename || event.sourceURL,
            lineno: event.lineno,
            colno: event.colno,
            stack: event.error && event.error.stack ? event.error.stack : null,
            error_type: 'Error',
        });
    });

    window.addEventListener('unhandledrejection', function(event) {
        var reason = event.reason;
        var message = reason instanceof Error ? reason.message : String(reason);
        var stack = reason instanceof Error ? reason.stack : null;
        window.reportFrontendError({
            message: 'Unhandled Promise Rejection: ' + message,
            stack: stack,
            error_type: 'UnhandledRejection',
        });
    });
})();

// Admin WebSocket Client for Real-time Updates

class AdminWebSocket {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = Infinity;
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
                if (message.data.event === 'connected') {
                    const qrModal = document.getElementById('qr-modal');
                    if (qrModal) {
                        qrModal.classList.add('hidden');
                        console.log('QR modal closed - tenant connected');
                    }
                }
                
                if (typeof htmx !== 'undefined') {
                    const tenantsList = document.querySelector('#tenants-list');
                    if (tenantsList) htmx.trigger(tenantsList, 'load');
                    const statsGrid = document.querySelector('.grid');
                    if (statsGrid) htmx.trigger(statsGrid, 'load');
                }
                this.showNotification(
                    `Tenant ${message.data.tenant_name}: ${message.data.event}`,
                    'info'
                );
                break;

            case 'tenant_list_changed':
                if (typeof htmx !== 'undefined') {
                    const tenantsList = document.querySelector('#tenants-list');
                    if (tenantsList) htmx.trigger(tenantsList, 'load');
                    const statsGrid = document.querySelector('.grid');
                    if (statsGrid) htmx.trigger(statsGrid, 'load');
                }
                break;

            case 'new_message':
                if (typeof htmx !== 'undefined') {
                    const messagesList = document.querySelector('#messages-list');
                    if (messagesList) htmx.trigger(messagesList, 'load');
                    const statsGrid = document.querySelector('.grid');
                    if (statsGrid) htmx.trigger(statsGrid, 'load');
                    const tabsContainer = document.querySelector('#messages-tabs-container');
                    if (tabsContainer) htmx.trigger(tabsContainer, 'load');
                }
                const preview = message.data.message.text ?
                    message.data.message.text.substring(0, 50) :
                    'Media message';
                const senderName = message.data.sender_name || 'Unknown';
                this.showNotification(
                    `New message from ${senderName} to ${message.data.tenant_name}: ${preview}`,
                    'success'
                );
                break;

            case 'webhook_attempt':
                if (typeof htmx !== 'undefined') {
                    const webhookHistory = document.querySelector('#webhook-history');
                    if (webhookHistory) htmx.trigger(webhookHistory, 'load');
                }
                if (!message.data.success) {
                    this.showNotification(
                        `Webhook failed: ${message.data.url}`,
                        'error'
                    );
                }
                break;

            case 'security_event':
                if (typeof htmx !== 'undefined') {
                    const blockedIps = document.querySelector('#blocked-ips');
                    if (blockedIps) htmx.trigger(blockedIps, 'load');
                    const failedAuth = document.querySelector('#failed-auth');
                    if (failedAuth) htmx.trigger(failedAuth, 'load');
                }
                this.showNotification(
                    `Security event: ${message.data.event} - ${message.data.ip}`,
                    'warning'
                );
                break;

            case 'qr_generated':
                console.log('QR event received:', message.data);
                this.showQRCode(message.data);
                break;

            case 'log_entry':
            case 'app_event':
                if (typeof appendLogEntry === 'function') {
                    appendLogEntry(message.data);
                }
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
        const maxBackoff = Math.min(this.reconnectAttempts, 10);
        const delay = Math.min(
            this.reconnectDelay * Math.pow(2, maxBackoff - 1),
            this.maxReconnectDelay
        );

        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

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

    showQRCode(data) {
        console.log('showQRCode called with:', data);
        let modal = document.getElementById('qr-modal');
        if (!modal) {
            console.log('Creating new QR modal');
            modal = document.createElement('div');
            modal.id = 'qr-modal';
            modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
            modal.innerHTML = `
                <div class="bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
                    <div class="flex justify-between items-center mb-4">
                        <h3 class="text-xl font-semibold text-white">Scan QR Code</h3>
                        <button onclick="this.closest('#qr-modal').classList.add('hidden')" class="text-gray-400 hover:text-white">
                            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                            </svg>
                        </button>
                    </div>
                    <p class="text-gray-300 mb-4">Tenant: <span id="qr-tenant-name" class="font-medium"></span></p>
                    <div class="bg-white p-4 rounded-lg flex justify-center">
                        <img id="qr-image" src="" alt="QR Code" class="max-w-full" />
                    </div>
                    <p class="text-gray-400 text-sm mt-4 text-center">Open WhatsApp on your phone and scan this QR code</p>
                </div>
            `;
            document.body.appendChild(modal);
            console.log('QR modal added to DOM');
        }
        
        modal.classList.remove('hidden');
        console.log('Modal shown, setting tenant name and QR image');
        document.getElementById('qr-tenant-name').textContent = data.tenant_name || 'Unknown';
        document.getElementById('qr-image').src = data.qr_data_url || '';
        console.log('QR image src set to:', data.qr_data_url ? 'data URL present' : 'empty');
        
        this.showNotification(`QR code generated for ${data.tenant_name}`, 'info');
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
var adminWS = null;

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
