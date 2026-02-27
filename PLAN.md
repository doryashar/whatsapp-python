# Python WhatsApp API - Implementation Plan

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                       │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │  REST API    │  │  WebSocket   │  │   Background Task     │  │
│  │  /api/send   │  │  /ws/events  │  │   (IPC listener)      │  │
│  │  /api/status │  │              │  │                       │  │
│  │  /api/login  │  │              │  │                       │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬───────────┘  │
│         │                 │                      │               │
│         └─────────────────┴──────────────────────┘               │
│                           │                                      │
│                    IPC Bridge (JSON-RPC over stdio)             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────────┐
│                    Node.js Baileys Bridge                        │
│  - Creates WhatsApp socket                                       │
│  - Handles QR, auth, reconnection                               │
│  - Forwards events to Python via stdout                         │
│  - Receives commands from Python via stdin                      │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

```
whatsapp-python/
├── PLAN.md                    # This file
├── STATUS.md                  # Implementation status
├── pyproject.toml             # Python deps
├── requirements.txt           # Pip compat
├── Dockerfile                 # Container image
├── docker-compose.yml         # Orchestration
├── src/
│   ├── __init__.py
│   ├── main.py                # FastAPI entrypoint
│   ├── config.py              # Settings
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py          # REST endpoints
│   │   └── websocket.py       # WebSocket handler
│   ├── bridge/
│   │   ├── __init__.py
│   │   ├── client.py          # IPC client
│   │   └── protocol.py        # JSON-RPC protocol
│   ├── models/
│   │   ├── __init__.py
│   │   ├── message.py         # Message models
│   │   └── events.py          # Event types
│   └── store/
│       ├── __init__.py
│       └── messages.py        # Message storage
├── bridge/
│   ├── package.json           # Node deps
│   └── index.mjs              # Node bridge
└── tests/
    ├── __init__.py
    ├── test_api.py
    └── test_bridge.py
```

## Protocol

### JSON-RPC Methods (Python → Node)

| Method | Params | Description |
|--------|--------|-------------|
| `login` | `{}` | Start QR login, returns QR data URL |
| `logout` | `{}` | Clear credentials |
| `send_message` | `{to, text, media_url?}` | Send message |
| `send_reaction` | `{chat, message_id, emoji}` | Send reaction |
| `get_status` | `{}` | Get connection status |

### Events (Node → Python)

| Event | Data | Description |
|-------|------|-------------|
| `qr` | `{qr, qr_data_url}` | QR code ready |
| `connected` | `{phone, jid}` | Connected to WhatsApp |
| `disconnected` | `{reason, should_reconnect}` | Disconnected |
| `message` | `{id, from, body, ...}` | Incoming message |
| `sent` | `{message_id, to}` | Message sent |

## REST API

| Endpoint | Method | Body | Description |
|----------|--------|------|-------------|
| `/api/status` | GET | - | Connection status |
| `/api/login` | POST | - | Start login, returns QR |
| `/api/logout` | POST | - | Logout |
| `/api/messages` | GET | - | List messages (query: limit, offset) |
| `/api/send` | POST | `{to, text, media_url?}` | Send message |
| `/api/react` | POST | `{chat, message_id, emoji}` | Send reaction |
| `/health` | GET | - | Health check |

## WebSocket

Connect to `/ws/events` to receive real-time events:

```json
{"type": "qr", "data": {"qr_data_url": "data:image/png;base64,..."}}
{"type": "connected", "data": {"phone": "+1234567890"}}
{"type": "message", "data": {"id": "...", "from": "...", "body": "..."}}
```

## Docker

```bash
# Build
docker compose build

# Run
docker compose up -d

# View logs
docker compose logs -f

# Login (get QR)
curl -X POST http://localhost:8080/api/login
```
