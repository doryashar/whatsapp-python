# WhatsApp Python API — Architecture Review

## Architecture Overview

```
┌──────────────┐     REST/WS     ┌──────────────────┐   JSON-RPC/stdio   ┌──────────────────┐
│   Clients    │ ◄─────────────► │  FastAPI (Python) │ ◄────────────────► │  Baileys Bridge  │
│  (HTTP/WS)   │                 │  src/main.py      │   stdin/stdout     │  bridge/index.mjs│
└──────────────┘                 └──────────────────┘                     └────────┬─────────┘
                                        │                                        │
                                   ┌────┴────┐                              WebSocket
                                   │ SQLite/ │                                  │
                                   │Postgres │                                  ▼
                                   └─────────┘                            WhatsApp Servers
```

A **hybrid Python/Node.js** multi-tenant WhatsApp Web API. Python handles the API surface; Node.js (Baileys) handles the WhatsApp protocol. Communication between them uses **JSON-RPC over stdio pipes**.

---

## Core Layers

### 1. Entry Point (`src/main.py` — 1054 lines)

- **Lifespan manager**: initializes DB, restores tenant sessions on startup, starts health check loop
- **Event dispatch table** (`EVENT_HANDLERS`): maps bridge event types to handler functions
- **Event pipeline** (per event, in order): handler → store message → broadcast WebSocket → send webhook → Chatwoot integration → log buffer
- **Two WebSocket endpoints**: `/ws/events` (tenant) and `/admin/ws` (admin dashboard)
- **Bridge lifecycle**: auto-restart with rate limiting (`_restart_bridge`), crash handling (`handle_bridge_crash`), health check loop (`connection_health_check`)

Key functions:

| Function | Line | Purpose |
|----------|------|---------|
| `create_task_with_logging` | 58 | Creates asyncio tasks with exception logging via done callbacks |
| `_restart_bridge` | 82 | Rate-limited bridge restart with cooldown, lock guard, and auth validation |
| `handle_bridge_crash` | 159 | Crash handler that attempts auto-restart, marks offline on failure |
| `connection_health_check` | 183 | Background loop checking all tenant bridges every N seconds |
| `handle_bridge_event` | 879 | Central event dispatcher — routes events through the handler pipeline |
| `lifespan` | 274 | FastAPI context manager for startup/shutdown lifecycle |

Event handler pipeline for each bridge event:

1. Look up handler in `EVENT_HANDLERS` dict and invoke it
2. If event is `message` or `sent`, call `_store_message()` to persist
3. `_broadcast_to_websockets()` — push to tenant WS and admin WS
4. `_send_webhook()` — fire-and-forget to registered webhook URLs
5. `_handle_chatwoot_integration()` — if Chatwoot is enabled for the tenant
6. `_capture_event_to_log_buffer()` — record in in-memory log buffer

---

### 2. Bridge Layer (`src/bridge/`)

#### `client.py` (613 lines)

`BaileysBridge` — Python async client that manages a Node.js child process.

- Spawns `node bridge/index.mjs` with `stdin=PIPE, stdout=PIPE, stderr=PIPE`
- Communicates via newline-delimited JSON-RPC 2.0 messages
- **Request-response pattern**: Each call gets an incrementing ID, stored in `_pending` dict as `asyncio.Future` objects
- **Event pattern**: Incoming messages without an `id` field (only `method` + `params`) are dispatched to registered event handler callbacks
- Exposes 50+ async methods organized by domain:

| Domain | Methods |
|--------|---------|
| Auth | `login`, `logout`, `auth_exists`, `auth_age`, `self_id` |
| Messaging | `send_message`, `send_reaction`, `send_poll`, `send_typing`, `send_location`, `send_contact`, `send_sticker`, `send_buttons`, `send_list`, `send_status`, `edit_message`, `delete_message`, `mark_read` |
| Groups | `group_create`, `group_update_subject`, `group_update_description`, `group_update_picture`, `group_get_info`, `group_get_all`, `group_get_participants`, `group_get_invite_code`, `group_revoke_invite`, `group_accept_invite`, `group_get_invite_info`, `group_update_participant`, `group_update_setting`, `group_toggle_ephemeral`, `group_leave` |
| Chat | `archive_chat`, `block_user`, `check_whatsapp`, `get_contacts`, `get_chats_with_messages`, `get_profile_picture` |
| Profile | `update_profile_name`, `update_profile_status`, `update_profile_picture`, `remove_profile_picture`, `get_profile` |
| Privacy | `fetch_privacy_settings`, `update_privacy_settings` |
| Settings | `get_settings`, `update_settings` |

- `stop()` method: Cancels pending futures, closes stdin, terminates process with 5s timeout before SIGKILL
- `is_alive()` checks `process.returncode is None`

#### `protocol.py` (37 lines)

Minimal JSON-RPC 2.0 encoder/decoder with three Pydantic models:

- `JsonRpcRequest`: `{jsonrpc: "2.0", method, params?, id?}`
- `JsonRpcResponse`: `{jsonrpc: "2.0", result?, error?, id}`
- `JsonRpcEvent`: `{jsonrpc: "2.0", method, params}` (no `id`)

`decode_response()` distinguishes responses from events by checking for `id` + (`result` or `error`) fields.

---

### 3. Node.js Bridge (`bridge/index.mjs` — 1852 lines)

The only Node.js file. Wraps `@whiskeysockets/baileys` with full lifecycle management.

#### Socket Configuration

```javascript
sock = makeWASocket({
    auth: { creds, keys: makeCacheableSignalKeyStore(state.keys, logger) },
    version, // fetched from fetchLatestBaileysVersion()
    browser: ["Chrome (Linux)", "Chrome", "120.0.0"],
    syncFullHistory: false,
    markOnlineOnConnect: true,
    connectTimeoutMs: 60_000,
    keepAliveIntervalMs: 25_000,
    retryRequestDelayMs: 250,
    maxMsgRetryCount: 5,
    fireInitQueries: true,
});
```

JID filter ignores broadcast and status channels.

#### Disconnect Reason Mapping

Maps ~30 Baileys status codes to human-readable reasons:

| Code | Reason |
|------|--------|
| 401 | loggedOut |
| 403 | banned |
| 405 | invalidSession |
| 408-418 | restartRequired / timedOut / connectionReplaced |
| 428-436 | connectionClosed / connectionLost |
| 440-442 | serviceUnavailable |
| 500-504 | unknown / unavailable / timedOut |

#### Message Extraction (`extractMessageContent`)

Handles all Baileys message types and returns a normalized dict with: `text`, `type`, `mimetype`, `url`, `mediaKey`, `fileEncSha256`, `fileSha256`, `contextInfo`. Supported types: text, extendedText, image, video, audio, document, sticker, location, contact.

#### Post-Connect Sync Sequence

```
connection === "open"
  └─ 2s delay → fetch contacts from store → emit "contacts" event
       └─ 3s delay → fetch chats with last 50 messages each → emit "chats_history" event
```

#### Event Listeners

| Baileys Event | Handler Action |
|---------------|----------------|
| `creds.update` | Save credentials, export auth state to Python |
| `connection.update` | Handle QR, connecting, close, open states |
| `messages.upsert` | Extract content, emit "message" event, auto-mark-read |
| `messages.delete` | Emit "message_deleted" event |
| `messages.read` | Emit "message_read" event |

#### Stdin/Stdout Protocol

```javascript
process.stdin.on("data", (chunk) => {
    buffer += chunk;
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
        if (line.trim()) handleRequest(line.trim());
    }
});
```

Request handler looks up method in the `methods` dict, calls it, and sends response or error back via stdout.

#### Signal Handling

Graceful shutdown on `SIGTERM`, `SIGINT`, and stdin `end` — closes WebSocket and exits.

#### Auto-Login

If `AUTO_LOGIN=true` env var is set, `createSocket()` is called immediately on process start.

---

### 4. Tenant Manager (`src/tenant/__init__.py` — 486 lines)

#### Tenant Dataclass

```python
@dataclass
class Tenant:
    api_key_hash: str
    name: str
    bridge: Optional[BaileysBridge]      # per-tenant Node.js process
    message_store: Optional[MessageStore] # per-tenant message buffer + DB
    webhook_urls: list[str]
    connection_state: str                 # "disconnected" | "connecting" | "connected"
    self_jid, self_phone, self_name       # WhatsApp identity
    has_auth: bool
    creds_json: Optional[dict]            # serialized auth state for persistence
    chatwoot_config: Optional[dict]       # Chatwoot integration settings
    health_check_failures: int
    total_restarts: int
    _restart_lock: asyncio.Lock           # prevents concurrent restarts
    _restarting: bool                     # double-check flag inside lock
```

Auth directory per tenant: `data/auth/<first 16 chars of sha256(api_key_hash)>/`

#### TenantManager

- In-memory registry: `dict[str, Tenant]` keyed by `api_key_hash`
- **Tenant creation**: Generates `wa_<token_urlsafe(32)>` API key, SHA-256 hashes it for storage (raw key returned once at creation)
- **Session restoration**: On startup, for each tenant with `creds_json`, writes auth to filesystem and calls `bridge.login()`
- **Bridge lifecycle**: `get_or_create_bridge()` lazily creates and starts bridge processes, registers event handler
- **Webhook management**: Add/remove with DB persistence
- **Auto-restart governance**:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `max_restart_attempts` | 3 | Max restarts per window |
| `restart_window_seconds` | 300 | Sliding window for rate limiting |
| `restart_cooldown_seconds` | 10 | Minimum time between restarts |
| History cleanup interval | 3600s | Periodic purge of stale restart records |

---

### 5. Database Layer (`src/store/`)

#### `database.py` (~1200+ lines)

Dual-backend database abstraction.

| Backend | Library | Connection |
|---------|---------|------------|
| PostgreSQL | `asyncpg` | Connection pool |
| SQLite | `aiosqlite` | Single connection with WAL mode |

**Schema** — 6 tables:

| Table | Primary Key | Notable Columns |
|-------|-------------|-----------------|
| `tenants` | `api_key_hash TEXT` | name, webhook_urls (JSON), connection_state, self_jid/phone/name, has_auth, creds_json (JSON), chatwoot_config (JSON), settings (JSON), enabled |
| `messages` | `id SERIAL/AUTOINCREMENT` | tenant_hash (FK), message_id, from_jid, chat_jid, is_group, text, msg_type, timestamp, direction, media fields, Chatwoot sync fields |
| `webhook_attempts` | `id SERIAL/AUTOINCREMENT` | tenant_hash (FK), url, event_type, success, status_code, error_message, attempt_number, latency_ms |
| `admin_sessions` | `id TEXT` | created_at, expires_at, user_agent, ip_address |
| `global_config` | `key TEXT` | value (JSON), updated_at |
| `contacts` | `id SERIAL/AUTOINCREMENT` | tenant_hash (FK), phone, name, chat_jid, is_group, message_count, UNIQUE(tenant_hash, phone) |

**Indexes**: tenant+created_at, chat+created_at, unique tenant+message_id, webhook tenant+created_at, contacts tenant+last_message_at, phone.

**Inline migrations**: Both backends use `ALTER TABLE ADD COLUMN IF NOT EXISTS` (Postgres) / `PRAGMA table_info` check + `ALTER TABLE ADD COLUMN` (SQLite). The PostgreSQL section also migrates `TIMESTAMP` → `TIMESTAMPTZ` for timezone-aware datetime support.

**Retry logic**: `_with_retry()` wraps operations with 3 attempts and exponential backoff (0.1s, 0.2s, 0.4s) for transient errors (connection, timeout, deadlock, locked, busy).

**Key methods**:

| Method | Purpose |
|--------|---------|
| `save_tenant` / `load_tenants` / `delete_tenant` | CRUD with cascading message/contact/webhook deletion |
| `save_creds` / `load_creds` / `clear_creds` | Auth credential persistence |
| `save_message` / `list_messages` | Message storage with optional search and chat filtering |
| `save_webhook_attempt` | Webhook delivery audit trail |
| `upsert_contact` | Contact deduplication with last-message tracking |
| `save_global_config` / `get_global_config` | Key-value config store |

#### `messages.py` (157 lines)

Dual-layer message storage:

1. **In-memory deque**: `deque[StoredMessage]` bounded by `max_messages` (default 1000) — O(1) append, automatic eviction
2. **Database persistence**: `add_with_persist()` writes to both layers, stores `db_id` on the `StoredMessage` for cross-referencing

`StoredMessage` class: Plain Python object (not Pydantic) with `to_dict()` serialization.

`MessageStore.list()` returns in-memory messages with pagination. `list_from_db()` delegates to DB with filtering.

---

### 6. API Layer (`src/api/routes.py` — 1348 lines)

50+ REST endpoints under `/api/` prefix, organized by domain.

#### Tenant Endpoints (`/api/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Connection status with self info |
| `/api/login` | POST | Initiate login, returns QR code |
| `/api/logout` | POST | Disconnect and clear auth |
| `/api/messages` | GET/DELETE | List/clear messages |
| `/api/send` | POST | Send text/media message |
| `/api/react` | POST | Send emoji reaction |
| `/api/poll` | POST | Create and send poll |
| `/api/typing` | POST | Send typing indicator |
| `/api/webhooks` | GET/POST/DELETE | Webhook management |
| `/api/auth/*` | GET | Auth state queries |
| `/api/contacts` | GET | Fetch contacts |
| `/api/sync-history` | POST | Manual chat history sync |
| `/api/group/*` | Various | Full group management |
| `/api/message/*` | POST/DELETE | Delete, send location, contact |
| `/api/chat/*` | POST/GET/DELETE | Archive, block, edit, mark read, profile, privacy, settings |
| `/api/sticker` | POST | Send sticker |
| `/api/buttons` | POST | Send interactive buttons |
| `/api/list` | POST | Send interactive list |
| `/api/status` | POST | Send WhatsApp status |
| `/api/privacy` | GET/POST | Privacy settings |
| `/api/settings` | GET/POST | Instance settings |

#### Admin Endpoints (`/admin/v1/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/v1/tenants` | POST/GET/DELETE | Tenant CRUD |
| `/admin/v1/rate-limit/blocked` | GET | List blocked IPs |
| `/admin/v1/rate-limit/block` | POST/DELETE | Block/unblock IP |
| `/admin/v1/rate-limit/stats` | GET | Rate limit statistics |
| `/admin/v1/rate-limit/failed-auth` | GET/DELETE | Failed auth tracking |

#### Authentication (`src/api/auth.py`)

- **Tenant auth**: `X-API-Key` header or `Bearer` token → SHA-256 hash → tenant lookup
- **Admin auth**: Same header → `hmac.compare_digest` against `ADMIN_API_KEY`
- **Rate limit integration**: Failed auth attempts tracked per IP; auto-blocks after N failures

#### Request/Response Models

All endpoints use Pydantic v2 response models (defined in `src/models/`). The routes file imports ~100 model classes.

---

### 7. Webhooks (`src/webhooks/__init__.py` — 244 lines)

#### WebhookSender

- Sends events to tenant-registered URLs via `httpx.AsyncClient`
- **Payload format**: `{"type": "<event_type>", "data": {...}, "timestamp": <unix>}`
- **HMAC-SHA256 signing**: When `WEBHOOK_SECRET` is set, adds `X-Webhook-Signature: sha256=<hex>` header
- **Retry strategy**: Exponential backoff — 0.5s × 2^attempt (0.5s, 1s, 2s, ...) up to `WEBHOOK_RETRIES` (default 3)
- **Parallel delivery**: All webhook URLs dispatched concurrently via `asyncio.gather()`
- **Attempt audit**: Each delivery attempt (success or failure) saved to `webhook_attempts` table with latency, status code, error message
- **Admin broadcast**: Webhook results forwarded to admin WebSocket for dashboard visibility

#### SSRF Protection

`is_safe_webhook_url()` validates webhook and media URLs against:
- Private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, etc.)
- Cloud metadata endpoints (169.254.169.254)
- IPv6 link-local addresses

---

### 8. Middleware (`src/middleware/ratelimit.py` — 303 lines)

#### RateLimiter

In-memory sliding window rate limiter using `deque` of timestamps per IP.

| Dimension | Default Limit |
|-----------|---------------|
| Requests per minute | 60 |
| Requests per hour | 1000 |
| Failed auth before block | 5 |
| Block duration | 15 minutes |

**Features**:
- Separate deques for per-minute and per-hour tracking
- Auto-block on rate limit exceeded or failed auth threshold
- Manual block/unblock via admin API
- Periodic cleanup of stale IP data (every 100 requests, removes entries older than 1 hour)
- Security event broadcast to admin dashboard on IP block

#### RateLimitMiddleware

`BaseHTTPMiddleware` that:
1. Skips `/health`, `/ready`, `/admin/*`, `/webhooks/*` paths
2. Checks if IP is blocked → returns 429
3. Checks rate limits → returns 429 with `Retry-After: 60` header
4. Records request timestamp in both minute and hour deques

---

### 9. Admin Dashboard (`src/admin/`)

#### Authentication (`auth.py`)

Session-based auth with database-backed sessions:
- Login validates `ADMIN_PASSWORD` (bcrypt-comparable)
- Session token is a random UUID stored in `admin_sessions` table with expiration (24h default)
- Sessions validated on every request and WebSocket handshake

#### WebSocket Manager (`websocket.py`)

`AdminConnectionManager` — manages multiple admin WebSocket connections:
- Connection tracking with session IDs and timestamps
- Async lock for thread-safe connection management
- Broadcast sends to all connected sessions, auto-disconnects on send failure
- `close_all()` for graceful shutdown

#### Log Buffer (`log_buffer.py`)

In-memory circular buffer (`LogBuffer`) of application events:
- Configurable max size (default 2000 entries)
- `LogEntry` dataclass: id, timestamp, type, level, source, message, tenant, details
- `LogBufferHandler` integrates with Python's `logging` module
- WebSocket broadcasting queued via `queue_broadcast()` for async delivery

#### UI Routes (`routes.py`)

Server-side rendered HTML with HTMX for dynamic updates:
- Dashboard with real-time tenant status, message counts, system health
- Message search with debouncing (300ms), tenant/direction filters, text highlighting
- Tenant details page with Messages, Webhooks, Settings tabs
- Log viewer with real-time event streaming

#### Static Assets

`src/admin/static/` — JavaScript files:
- `websocket.js` — Auto-reconnecting WebSocket client with exponential backoff (1s→30s, 5 attempts), toast notifications for events

---

### 10. Telemetry (`src/telemetry/__init__.py` — 144 lines)

#### OpenTelemetry Integration

- `TracerProvider` with resource attributes (service name, version, namespace)
- Optional OTLP gRPC span exporter (enabled when `OTEL_EXPORTER_OTLP_ENDPOINT` is set)
- Auto-instrumentation: `FastAPIInstrumentor` and `HTTPXClientInstrumentor`

#### Structured Logging

`JSONFormatter` — custom Python logging formatter outputting JSON with:

| Field | Source |
|-------|--------|
| `timestamp` | Current UTC time |
| `level` | Log level name |
| `logger` | Logger name |
| `message` | Log message |
| `module`, `function`, `line` | Call site |
| `exception` | Formatted traceback (if any) |
| `tenant` | From `extra={"tenant": ...}` |
| `event_type` | From `extra={"event_type": ...}` |
| `trace_id`, `span_id` | From OpenTelemetry context (if active) |
| `extra` | Any additional fields from `record.__dict__` |

All logs go to stdout as JSON. Uvicorn's logger is also reconfigured to use the same formatter.

---

### 11. Utilities (`src/utils/`)

#### `phone.py`

| Function | Purpose |
|----------|---------|
| `normalize_phone` | Strip non-digits, validate length, format with country code |
| `extract_phone_from_jid` | Extract phone number from WhatsApp JID |
| `is_group_jid` | Check if JID ends with `@g.us` |
| `format_phone_display` | Human-readable phone format |
| `format_phone_with_plus` | Add `+` prefix |
| `extract_and_validate_phone_from_jid` | Combined extraction + validation |

#### `network.py`

| Function | Purpose |
|----------|---------|
| `get_client_ip` | Extract client IP from `X-Forwarded-For` / `X-Real-IP` / direct connection |
| `is_ip_in_cidr` | Check if IP falls within a CIDR range |
| `is_trusted_proxy` | Validate proxy IPs against configured trusted proxy list |
| `is_safe_webhook_url` | SSRF protection — validate URLs against private ranges |

#### `history.py`

`store_chat_messages()` — bulk chat history sync:
- Iterates chats and their messages from bridge response
- Stores each message via `Database.save_message()`
- Returns stats: stored count, duplicates, errors

---

### 12. Chatwoot Integration (`src/chatwoot/`)

Optional per-tenant integration with Chatwoot (open-source customer engagement platform).

| File | Purpose |
|------|---------|
| `models.py` | `ChatwootConfig` — Pydantic model for Chatwoot connection settings |
| `client.py` | HTTP client for Chatwoot API v1 (conversations, messages, contacts) |
| `integration.py` | `ChatwootIntegration` — orchestrates message sync, creates conversations, handles inbound/outbound |
| `sync.py` | Historical message sync to Chatwoot |
| `webhook_handler.py` | Handles incoming Chatwoot webhook events (e.g., agent replies) |

Integration is event-driven — activated when a tenant has `chatwoot_config.enabled = true`. Each bridge event (message, sent, connected, disconnected, etc.) can trigger Chatwoot operations. Global config can be merged with per-tenant config.

---

## Data Flow

### Message Reception Flow

```
WhatsApp Server
    │
    ▼ (WebSocket)
Baileys (Node.js bridge/index.mjs)
    │ sock.ev.on("messages.upsert")
    ▼ extractMessageContent()
JSON-RPC event via stdout
    │ {jsonrpc: "2.0", method: "message", params: {...}}
    ▼
Python _read_loop (src/bridge/client.py)
    │ decode_response() → JsonRpcEvent
    ▼ _handle_event() → registered callbacks
    │
    ▼
handle_bridge_event (src/main.py:879)
    ├── _handle_message_log_event()      → debug log
    ├── _store_message()                 → in-memory deque + DB
    ├── _broadcast_to_websockets()       → tenant WS + admin WS
    ├── _send_webhook()                  → external webhook URLs
    ├── _handle_chatwoot_integration()   → Chatwoot (if enabled)
    └── _capture_event_to_log_buffer()   → admin log buffer
```

### Message Sending Flow

```
Client HTTP POST /api/send
    │
    ▼
get_tenant auth dependency (src/api/auth.py)
    │
    ▼
send_message endpoint (src/api/routes.py:193)
    │ SSRF check on media_url
    ▼
tenant_manager.get_or_create_bridge(tenant)
    │ lazily creates bridge if needed
    ▼
bridge.send_message(to, text, media_url)
    │
    ▼
BaileysBridge.call("send_message", params)
    │ encode_request() → JSON-RPC
    ▼
process.stdin.write(json + "\n")
    │
    ▼
Node.js handleRequest() → methods.send_message()
    │ sock.sendMessage(jid, content)
    ▼
WhatsApp Server → delivered
    │
    ▼
Node.js emits "sent" event via stdout
    │
    ▼
Python event pipeline (same as reception)
```

### Health Check Flow

```
connection_health_check() (every 30s)
    │
    ▼ for each tenant with bridge and connection_state == "connected"
    ├── bridge.is_alive()         → check process.returncode
    │   └── if dead → handle_bridge_crash()
    └── bridge.get_status()       → JSON-RPC call with 10s timeout
        ├── connection_state == "connected" → reset failures
        └── otherwise → increment failures
            └── failures >= MAX → mark disconnected
```

---

## Configuration

All settings via environment variables, defined in `src/config.py`:

| Variable | Default | Category |
|----------|---------|----------|
| `HOST` | `0.0.0.0` | Server |
| `PORT` | `8080` | Server |
| `DEBUG` | `false` | Server |
| `ADMIN_API_KEY` | `""` | Auth |
| `ADMIN_PASSWORD` | `""` | Auth |
| `DATABASE_URL` | `""` | Storage |
| `DATA_DIR` | `./data` | Storage |
| `WHATSAPP_AUTH_DIR` | `./data/auth` | Storage |
| `MAX_MESSAGES` | `1000` | Storage |
| `BRIDGE_PATH` | `./bridge/index.mjs` | Bridge |
| `BRIDGE_TIMEOUT_SECONDS` | `60` | Bridge |
| `AUTO_RESTART_BRIDGE` | `true` | Bridge |
| `MAX_RESTART_ATTEMPTS` | `3` | Bridge |
| `RESTART_WINDOW_SECONDS` | `300` | Bridge |
| `RESTART_COOLDOWN_SECONDS` | `10` | Bridge |
| `WEBHOOK_SECRET` | `""` | Webhooks |
| `WEBHOOK_TIMEOUT` | `30` | Webhooks |
| `WEBHOOK_RETRIES` | `3` | Webhooks |
| `RATE_LIMIT_PER_MINUTE` | `60` | Security |
| `RATE_LIMIT_PER_HOUR` | `1000` | Security |
| `MAX_FAILED_AUTH_ATTEMPTS` | `5` | Security |
| `HEALTH_CHECK_INTERVAL_SECONDS` | `30` | Reliability |
| `HEALTH_CHECK_TIMEOUT_SECONDS` | `10` | Reliability |
| `MAX_HEALTH_CHECK_FAILURES` | `3` | Reliability |
| `CORS_ORIGINS` | `[]` | Network |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `""` | Telemetry |
| `OTEL_SERVICE_NAME` | `whatsapp-api` | Telemetry |

**Production validator**: Raises `ValueError` if `DATABASE_URL` is empty in production/staging environment. Warns on empty `ADMIN_PASSWORD` and `CORS_ORIGINS`.

---

## Dependencies

### Python (`pyproject.toml`)

| Package | Purpose |
|---------|---------|
| `fastapi >= 0.109` | Web framework |
| `uvicorn[standard] >= 0.27` | ASGI server |
| `pydantic >= 2.5` | Data validation |
| `pydantic-settings >= 2.1` | Settings management |
| `python-multipart >= 0.0.6` | Form data parsing |
| `opentelemetry-*` | Distributed tracing |
| `httpx` | Async HTTP client (webhooks) |
| `asyncpg` | PostgreSQL driver (optional) |
| `aiosqlite` | SQLite driver (default) |

### Node.js (`bridge/package.json`)

| Package | Purpose |
|---------|---------|
| `@whiskeysockets/baileys` | WhatsApp Web protocol |
| `pino` | JSON logger |
| `qrcode` | QR code generation (for login) |

---

## Testing

48 test files covering:

| Area | Test Files |
|------|------------|
| API | `test_api.py` |
| Bridge | `test_bridge.py`, `test_bridge_crash.py`, `test_bridge_restart_lock.py` |
| Tenant | `test_tenant.py`, `test_tenant_settings.py` |
| Database | `test_persistence.py` |
| Messages | `test_messages_direction.py`, `test_outbound_messages.py`, `test_media_*.py` |
| Webhooks | `test_webhooks.py` |
| Rate Limiting | `test_ratelimit.py` |
| Health Check | `test_health_check.py` |
| History | `test_history.py`, `test_history_sync.py` |
| Admin Dashboard | `test_admin_dashboard.py`, `test_admin_*.py` |
| Chatwoot | `test_chatwoot.py`, `test_chatwoot_sync.py` |
| Auth | `test_session_manager.py` |
| Utilities | `test_phone_utils.py` |
| E2E | `test_e2e_whatsapp_chatwoot.py` |

---

## Design Patterns & Strengths

### Process Isolation
Each tenant gets its own Node.js bridge process and auth directory. A crash in one tenant's bridge doesn't affect others.

### Full Async Stack
Python side uses `asyncio` for all I/O operations. Node.js bridge is inherently async. No blocking calls in the hot path.

### Graceful Degradation
SQLite fallback for development with zero external dependencies. PostgreSQL for production. No mandatory external services required to start.

### Comprehensive WhatsApp API Coverage
Groups, polls, stickers, buttons, lists, locations, contacts, status, privacy settings — nearly the full Baileys API surface exposed through REST.

### Security Measures
- SSRF protection on media URLs and webhook URLs
- HMAC-SHA256 webhook signature verification
- Sliding window rate limiting with auto-blocking
- Constant-time admin key comparison (`hmac.compare_digest`)
- IP-based failed auth tracking with progressive blocking
- Session-based admin auth with database-backed sessions

### Operational Visibility
- Structured JSON logging with tenant/event context
- OpenTelemetry tracing with optional OTLP export
- Real-time admin dashboard with WebSocket updates
- Webhook delivery audit trail with latency tracking
- Health check monitoring with configurable thresholds

---

## Architectural Concerns

### 1. Single-Process Bottleneck

The in-memory tenant registry (`dict[str, Tenant]`), rate limiter, WebSocket connection managers, and log buffer are all held in process memory. This prevents horizontal scaling without external state stores (Redis, etc.). If the Python process crashes, all tenant bridges die (though they can auto-restart on next boot).

### 2. No Structured Migration Tool

Inline `ALTER TABLE ADD COLUMN IF NOT EXISTS` and `PRAGMA table_info` checks work for adding columns but don't handle:
- Column type changes
- Data transformations
- Rollbacks
- Migration ordering

The PostgreSQL migration section alone spans ~180 lines of repetitive `ALTER TABLE` statements. A proper migration tool (Alembic) would be more maintainable.

### 3. Bridge Process Hang Risk

The `_read_loop` in `client.py` does `await reader.readline()` with no per-line timeout. If the Node.js bridge hangs without crashing (e.g., stuck in a Baileys internal state), `health_check_timeout_seconds` will eventually detect it, but the `_pending` futures for in-flight requests will only timeout after `bridge_timeout_seconds` (default 60s). During this window, tenant API calls will be slow or hang.

### 4. Fire-and-Forget Event Processing

`handle_bridge_event` is a synchronous function that calls `asyncio.create_task()` for each handler step. There is no backpressure mechanism. A rapid burst of events (e.g., receiving many messages simultaneously) will create many concurrent tasks with no throttling. Failed tasks are logged but not retried.

### 5. No Event-Level Deduplication

While the database has `UNIQUE(tenant_hash, message_id)` preventing duplicate storage, the in-memory deque and WebSocket broadcasts have no deduplication. If the bridge emits a duplicate event (e.g., due to a reconnect that replays events), it will appear as duplicate in the message store and WebSocket stream.

### 6. CORS Configuration Discrepancy

The README states `CORS_ORIGINS` defaults to `["*"]`, but the code defaults to an empty list `[]` with a warning. An empty `CORSMiddleware` config may block all cross-origin requests depending on the Starlette version.

### 7. Admin Path Rate Limit Bypass

The `RateLimitMiddleware` skips rate limiting for any path starting with `/admin/`. If additional API endpoints were accidentally added under this prefix, they would bypass rate limiting.

### 8. Module-Level Side Effects

`src/store/messages.py` creates a module-level `message_store` instance at import time. Similarly, `src/tenant/__init__.py` creates a module-level `tenant_manager` instance, and `src/middleware/__init__.py` creates a module-level `rate_limiter`. These global singletons can cause issues with test isolation and make the import graph harder to reason about.

### 9. WebSocket Auth Via Query Parameter

Both `/ws/events` and `/admin/ws` use query parameters for authentication (`api_key` and `session_id` respectively). This is a documented limitation — cookies are not available during WebSocket handshake in browsers. Query params can appear in server logs, proxy logs, and browser history.

### 10. No Event Batching

The admin WebSocket broadcasts events individually. In high-throughput scenarios with many tenants, this could generate significant WebSocket traffic. A batching mechanism (e.g., collecting events over a short window and sending them as an array) would be more efficient.

### 11. Synchronous JSON-RPC Event Dispatch

In `BaileysBridge._handle_event()`, event handlers are called synchronously. If a handler is an async coroutine, it's awaited. But the outer `_read_loop` processes events sequentially — a slow handler blocks processing of subsequent events from the bridge's stdout. Events are queued by the OS pipe buffer, but if the buffer fills, the bridge process could block on stdout writes.

---

## File Structure Map

```
whatsapp-python/
├── bridge/
│   ├── index.mjs              # Node.js bridge (1852 lines) — Baileys wrapper, JSON-RPC server
│   └── package.json           # Node.js dependencies (baileys, pino, qrcode)
├── src/
│   ├── main.py                # FastAPI app, event pipeline, WebSocket endpoints (1054 lines)
│   ├── config.py              # Pydantic settings from env vars (108 lines)
│   ├── admin/
│   │   ├── __init__.py        # Exports admin_ws_manager, routers
│   │   ├── auth.py            # Session-based admin authentication
│   │   ├── routes.py          # Admin dashboard HTML routes (HTMX)
│   │   ├── websocket.py       # AdminConnectionManager for real-time updates (120 lines)
│   │   ├── log_buffer.py      # In-memory circular log buffer
│   │   └── static/            # JavaScript, CSS for admin dashboard
│   ├── api/
│   │   ├── __init__.py        # Exports router, admin_router
│   │   ├── auth.py            # Tenant + admin key auth dependencies (98 lines)
│   │   ├── routes.py          # 50+ REST endpoints (1348 lines)
│   │   └── chatwoot_routes.py # Chatwoot-specific API routes
│   ├── bridge/
│   │   ├── __init__.py        # Exports BaileysBridge
│   │   ├── client.py          # BaileysBridge — process management, RPC client (613 lines)
│   │   └── protocol.py        # JSON-RPC 2.0 encoder/decoder (37 lines)
│   ├── chatwoot/
│   │   ├── __init__.py        # Exports
│   │   ├── client.py          # Chatwoot API HTTP client
│   │   ├── integration.py     # ChatwootIntegration orchestrator
│   │   ├── models.py          # ChatwootConfig Pydantic model
│   │   ├── sync.py            # Historical message sync
│   │   └── webhook_handler.py # Incoming Chatwoot webhook handler
│   ├── middleware/
│   │   ├── __init__.py        # Exports rate_limiter singleton
│   │   └── ratelimit.py       # RateLimiter + RateLimitMiddleware (303 lines)
│   ├── models/
│   │   ├── __init__.py        # Exports all Pydantic request/response models
│   │   ├── message.py         # Message-related models
│   │   ├── events.py          # Event-related models
│   │   └── group.py           # Group-related models
│   ├── store/
│   │   ├── __init__.py        # Exports
│   │   ├── database.py        # Dual-backend DB (SQLite/Postgres) (~1200 lines)
│   │   └── messages.py        # MessageStore — deque + DB dual storage (157 lines)
│   ├── tenant/
│   │   └── __init__.py        # Tenant dataclass + TenantManager (486 lines)
│   ├── telemetry/
│   │   └── __init__.py        # OpenTelemetry setup, JSON logging (144 lines)
│   └── utils/
│       ├── __init__.py        # Exports all utility functions
│       ├── phone.py           # Phone number parsing and validation
│       ├── network.py         # IP utilities, SSRF protection
│       └── history.py         # Chat history sync utilities
├── tests/                     # 48 test files
├── docs/                      # Integration guides
├── Dockerfile                 # Production Docker build
├── docker-compose.webhook.yml # OpenCode integration deployment
├── pyproject.toml             # Python project config
└── requirements.txt           # Python dependencies
```
