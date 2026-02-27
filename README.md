# WhatsApp Python API

A FastAPI-based WhatsApp Web API that wraps Baileys (Node.js) for reliable WhatsApp messaging.

## Architecture

```
FastAPI (Python) <--JSON-RPC/stdio--> Baileys Bridge (Node.js) <--WebSocket--> WhatsApp
```

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

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
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
| WS | `/ws/events` | Real-time events |

## Usage Examples

### Login

```bash
# Start login flow
curl -X POST http://localhost:8080/api/login

# Response includes qr_data_url for displaying QR code
```

### Send Message

```bash
curl -X POST http://localhost:8080/api/send \
  -H "Content-Type: application/json" \
  -d '{"to": "+15551234567", "text": "Hello from API!"}'
```

### WebSocket Events

```javascript
const ws = new WebSocket("ws://localhost:8080/ws/events");

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
| `AUTO_LOGIN` | `false` | Auto-start login on boot |
| `MAX_MESSAGES` | `1000` | Max messages to store |
| `WHATSAPP_AUTH_DIR` | `./data/auth` | Auth credentials directory |
| `BRIDGE_PATH` | `./bridge/index.mjs` | Path to Node.js bridge |
| `WEBHOOK_URLS` | `[]` | Comma-separated list of webhook URLs |
| `WEBHOOK_SECRET` | `""` | Secret for HMAC signature |
| `WEBHOOK_TIMEOUT` | `30` | Webhook request timeout (seconds) |
| `WEBHOOK_RETRIES` | `3` | Max retries for failed webhooks |

## Docker Compose

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

All events are also sent to registered webhook URLs via HTTP POST requests.

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
curl http://localhost:8080/api/webhooks

# Add a webhook
curl -X POST http://localhost:8080/api/webhooks \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-server.com/webhook"}'

# Remove a webhook
curl -X DELETE "http://localhost:8080/api/webhooks?url=https://your-server.com/webhook"
```

### Retry Behavior

Failed webhooks are retried up to `WEBHOOK_RETRIES` times with exponential backoff (0.5s, 1s, 2s, ...).
