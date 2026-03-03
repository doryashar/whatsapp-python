# WhatsApp Python API

A FastAPI-based WhatsApp Web API that wraps Baileys (Node.js) for reliable WhatsApp messaging with multi-tenant support.

## Architecture

```
FastAPI (Python) <--JSON-RPC/stdio--> Baileys Bridge (Node.js) <--WebSocket--> WhatsApp
```

## Multi-Tenant Architecture

This API supports multiple WhatsApp accounts, each with its own API key. Each tenant has:
- Isolated WhatsApp session/auth
- Separate message store
- Independent webhooks
- Own WebSocket connection

## Quick Start

### With Docker (Recommended)

```bash
# Build and run
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

### Without Docker

```bash
# Install Node.js bridge dependencies
cd bridge && npm install

# Install Python dependencies
pip install -r requirements.txt

# Run
python -m uvicorn src.main:app --reload
```

## Authentication

All API endpoints require an API key via the `X-API-Key` header or `Bearer` token.

### Admin Endpoints

Admin endpoints require the `ADMIN_API_KEY` environment variable to be set.

```bash
# Create a new tenant (returns API key)
curl -X POST "http://localhost:8080/admin/tenants?name=my_app" \
  -H "X-API-Key: YOUR_ADMIN_KEY"

# Response:
# {"name": "my_app", "api_key": "wa_xxx...", "created_at": "2024-01-01T00:00:00"}
```

## API Endpoints

### Admin Endpoints (require ADMIN_API_KEY)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/admin/tenants?name=<name>` | Create tenant (returns API key) |
| GET | `/admin/tenants` | List all tenants |
| DELETE | `/admin/tenants?api_key=<key>` | Delete a tenant |

### Tenant Endpoints (require tenant API key)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Connection status |
| POST | `/api/login` | Start login (returns QR) |
| POST | `/api/logout` | Logout |
| GET | `/api/messages` | List received messages |
| DELETE | `/api/messages` | Clear message store |
| POST | `/api/send` | Send message |
| POST | `/api/react` | Send reaction |
| GET | `/api/webhooks` | List registered webhooks |
| POST | `/api/webhooks` | Add a webhook URL |
| DELETE | `/api/webhooks` | Remove a webhook URL |
| WS | `/ws/events?api_key=<key>` | Real-time events |

| GET | `/health` | Health check (no auth required) |

## Usage Examples

### Create a Tenant

```bash
# First, create a tenant using admin key
curl -X POST "http://localhost:8080/admin/tenants?name=my_bot" \
  -H "X-API-Key: your_admin_key"

# Save the returned api_key for subsequent requests
```

### Login

```bash
# Start login flow with your tenant API key
curl -X POST http://localhost:8080/api/login \
  -H "X-API-Key: wa_your_tenant_key"

# Response includes qr_data_url for displaying QR code
```

### Send Message

```bash
curl -X POST http://localhost:8080/api/send \
  -H "Content-Type: application/json" \
  -H "X-API-Key: wa_your_tenant_key" \
  -d '{"to": "+15551234567", "text": "Hello from API!"}'
```

### WebSocket Events

```javascript
// Connect with API key as query parameter
const ws = new WebSocket("ws://localhost:8080/ws/events?api_key=wa_your_tenant_key");

ws.onmessage = (event) => {
  const { type, data } = JSON.parse(event.data);
  
  switch (type) {
    case "qr":
      console.log("Scan QR:", data.qr_data_url);
      break;
    case "connected":
      console.log("Connected as:", data.phone);
      break;
    case "message":
      console.log("New message:", data);
      break;
  }
};
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8080` | Server port |
| `DEBUG` | `false` | Enable debug mode |
| `MAX_MESSAGES` | `1000` | Max messages to store per tenant |
| `WHATSAPP_AUTH_DIR` | `./data/auth` | Auth credentials directory |
| `DATA_DIR` | `./data` | Data directory (for SQLite) |
| `BRIDGE_PATH` | `./bridge/index.mjs` | Path to Node.js bridge |
| `WEBHOOK_SECRET` | `""` | Secret for HMAC signature |
| `WEBHOOK_TIMEOUT` | `30` | Webhook request timeout (seconds) |
| `WEBHOOK_RETRIES` | `3` | Max retries for failed webhooks |
| `ADMIN_API_KEY` | `""` | Admin API key for tenant management |
| `DATABASE_URL` | `""` | PostgreSQL URL (empty = SQLite) |

## Docker Compose

```yaml
services:
  whatsapp-api:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - whatsapp-data:/app/data
    environment:
      - DEBUG=false
      - ADMIN_API_KEY=your_secure_admin_key
```

### With PostgreSQL

```yaml
services:
  whatsapp-api:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - whatsapp-auth:/app/data/auth
    environment:
      - DEBUG=false
      - ADMIN_API_KEY=your_secure_admin_key
      - DATABASE_URL=postgresql://user:pass@postgres:5432/whatsapp
    depends_on:
      - postgres

  postgres:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=whatsapp
    volumes:
      - postgres-data:/var/lib/postgresql/data
```

## WebSocket Event Types

| Event | Data |
|-------|------|
| `qr` | `{qr, qr_data_url}` |
| `connected` | `{jid, phone, name}` |
| `disconnected` | `{reason, should_reconnect}` |
| `message` | `{id, from, chat_jid, text, ...}` |
| `sent` | `{message_id, to}` |

## Webhooks

Each tenant can register their own webhooks. Events are sent via HTTP POST.

### Webhook Payload

```json
{
  "type": "message",
  "data": { ... },
  "timestamp": 1709012345
}
```

### Signature Verification

When `WEBHOOK_SECRET` is set, each webhook includes an `X-Webhook-Signature` header containing `sha256=<hex_signature>`. Verify by computing HMAC-SHA256 of the request body with your secret.

```python
import hmac
import hashlib

def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return signature == f"sha256={expected}"
```

### Managing Webhooks

```bash
# List webhooks
curl http://localhost:8080/api/webhooks \
  -H "X-API-Key: wa_your_tenant_key"

# Add a webhook
curl -X POST http://localhost:8080/api/webhooks \
  -H "Content-Type: application/json" \
  -H "X-API-Key: wa_your_tenant_key" \
  -d '{"url": "https://your-server.com/webhook"}'

# Remove a webhook
curl -X DELETE "http://localhost:8080/api/webhooks?url=https://your-server.com/webhook" \
  -H "X-API-Key: wa_your_tenant_key"
```

### Retry Behavior

Failed webhooks are retried up to `WEBHOOK_RETRIES` times with exponential backoff (0.5s, 1s, 2s, ...).

## OpenCode Integration

This project includes a built-in integration with OpenCode AI assistant for automated WhatsApp responses.

### Features

- **Per-Chat Sessions**: Each WhatsApp conversation maintains isolated context
- **Media Support**: Handles images, videos, audio, and documents
- **Session Persistence**: SQLite-based session management
- **Docker Ready**: Fully containerized deployment
- **Admin API**: Manage sessions via REST endpoints

### Quick Start

```bash
# Deploy with Docker Compose
docker-compose -f docker-compose.webhook.yml up -d

# Register webhook with WhatsApp API
curl -X POST http://localhost:8080/api/webhooks \
  -H "X-API-Key: $WHATSAPP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "http://opencode-webhook:5556/webhook"}'
```

### Documentation

- **[OpenCode Integration Guide](docs/opencode-integration.md)** - Setup, configuration, troubleshooting
- **[Plugin System Plan](docs/PLUGIN_SYSTEM_PLAN.md)** - Architecture for converting OpenCode into a plugin system

### Plugin System (Planned)

The OpenCode integration is being converted into a **per-tenant plugin system** with:

- Per-tenant plugin enable/disable
- Admin dashboard management
- Plugin installation from UI
- API versioning for compatibility

See [docs/PLUGIN_SYSTEM_PLAN.md](docs/PLUGIN_SYSTEM_PLAN.md) for the complete architecture and implementation plan.

### Testing

```bash
# Run integration tests
pytest tests/test_opencode_webhook_handler.py -v

# Run manual test suite
python tests/test_opencode_integration.py
```
