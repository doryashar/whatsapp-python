# OpenCode WhatsApp Integration

This integration allows you to connect WhatsApp messages to OpenCode AI assistant, enabling automated responses and intelligent conversation handling through WhatsApp.

## Overview

The integration consists of:

1. **OpenCode Webhook Handler** - A FastAPI service that receives WhatsApp webhook events
2. **Session Manager** - SQLite-based session tracking for per-chat conversation context
3. **OpenCode CLI Integration** - Executes OpenCode commands for message processing
4. **WhatsApp API Bridge** - Sends responses back to WhatsApp users

## Architecture

```
┌─────────────┐       ┌──────────────────┐       ┌─────────────────┐
│  WhatsApp   │──────▶│  WhatsApp API    │──────▶│  Webhook        │
│   Message   │       │  (FastAPI)       │       │  Handler        │
└─────────────┘       └──────────────────┘       └─────────────────┘
                                                           │
                                                           ▼
                                                      ┌─────────────┐
                                                      │  Session    │
                                                      │  Manager    │
                                                      │  (SQLite)   │
                                                      └─────────────┘
                                                           │
                                                           ▼
                                                      ┌─────────────┐
                                                      │  OpenCode   │
                                                      │  CLI        │
                                                      └─────────────┘
```

## Features

- **Per-Chat Sessions**: Each WhatsApp conversation maintains its own OpenCode session
- **Media Support**: Handles images, videos, audio, and documents
- **Session Persistence**: SQLite database stores session mappings
- **Docker Ready**: Fully containerized with Docker Compose
- **Health Checks**: Built-in health monitoring endpoints
- **Admin API**: Manage sessions via REST endpoints
- **Structured Logging**: JSON logs with configurable levels

## Quick Start

### Prerequisites

- Docker and Docker Compose
- OpenCode CLI installed (automatically installed in Docker)
- WhatsApp API credentials

### 1. Environment Setup

Create a `.env` file:

```bash
# Admin API Key for WhatsApp API
ADMIN_API_KEY=your_secure_admin_key

# WhatsApp Tenant API Key (get this from creating a tenant)
WHATSAPP_API_KEY=wa_your_tenant_key

# External webhook URL (for webhook registration)
WEBHOOK_EXTERNAL_URL=http://your-server.com:5556

# Optional: Logging level
LOG_LEVEL=INFO
```

### 2. Deploy with Docker Compose

```bash
# Build and start services
docker-compose -f docker-compose.webhook.yml up -d

# View logs
docker-compose -f docker-compose.webhook.yml logs -f opencode-webhook

# Stop services
docker-compose -f docker-compose.webhook.yml down
```

### 3. Register Webhook

The webhook handler runs on port 5556 by default. Register it with the WhatsApp API:

```bash
curl -X POST http://localhost:8080/api/webhooks \
  -H "X-API-Key: $WHATSAPP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "http://opencode-webhook:5556/webhook"}'
```

### 4. Test Integration

Send a WhatsApp message to your connected number. The assistant will:
1. Receive the message via webhook
2. Create or continue an OpenCode session
3. Process the message with AI
4. Send the response back to WhatsApp

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `WHATSAPP_API_URL` | WhatsApp API endpoint | `http://localhost:8080` |
| `WHATSAPP_API_KEY` | WhatsApp tenant API key | Required |
| `ADMIN_API_KEY` | Admin key for session management | `admin123` |
| `WEBHOOK_HOST` | Host to bind webhook handler | `0.0.0.0` |
| `WEBHOOK_PORT` | Port for webhook handler | `5556` |
| `WEBHOOK_EXTERNAL_URL` | External URL for webhook registration | Required |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARN, ERROR) | `INFO` |
| `OPENCODE_TIMEOUT` | Timeout for OpenCode commands (seconds) | `120` |
| `SESSION_DB_PATH` | Path to SQLite database | `./data/sessions.db` |

### Customizing the System Prompt

Edit `PROMPT.md` to customize the AI assistant's behavior:

```markdown
# WhatsApp AI Assistant

You are a helpful AI assistant accessible via WhatsApp messaging...

[Customize the prompt as needed]
```

## API Endpoints

### Webhook Endpoints

#### `POST /webhook`
Receives WhatsApp webhook events. Called automatically by WhatsApp API.

#### `GET /health`
Health check endpoint for monitoring.

**Response:**
```json
{
  "status": "healthy",
  "service": "opencode-webhook"
}
```

### Admin Endpoints

All admin endpoints require the `X-API-Key` header with the `ADMIN_API_KEY`.

#### `GET /sessions`
List all active sessions.

**Headers:**
- `X-API-Key`: Admin API key

**Response:**
```json
{
  "sessions": [
    {
      "chat_jid": "1234567890@s.whatsapp.net",
      "opencode_session_id": "abc123...",
      "created_at": "2024-01-01 12:00:00",
      "last_used_at": "2024-01-01 14:30:00"
    }
  ],
  "count": 1
}
```

#### `DELETE /sessions/{chat_jid}`
Delete a specific session.

**Headers:**
- `X-API-Key`: Admin API key

**Response:**
```json
{
  "status": "deleted",
  "chat_jid": "1234567890@s.whatsapp.net"
}
```

#### `POST /cleanup?days_old=30`
Cleanup old sessions.

**Headers:**
- `X-API-Key`: Admin API key

**Query Parameters:**
- `days_old`: Delete sessions not used in X days (default: 30)

**Response:**
```json
{
  "deleted_count": 5
}
```

## Local Development

### Without Docker

```bash
# Install dependencies
pip install -r requirements-webhook.txt

# Set environment variables
export WHATSAPP_API_URL=http://localhost:8080
export WHATSAPP_API_KEY=wa_your_tenant_key
export LOG_LEVEL=DEBUG

# Run webhook handler
python scripts/opencode_webhook_handler.py
```

### Running Tests

```bash
# Run session manager tests
pytest tests/test_session_manager.py -v

# Run webhook handler tests
pytest tests/test_opencode_webhook_handler.py -v

# Run all tests
pytest tests/ -v
```

## Monitoring

### Logs

The webhook handler outputs structured JSON logs:

```json
{
  "timestamp": "2024-01-01 12:00:00",
  "level": "INFO",
  "logger": "opencode_webhook",
  "message": "Processing text message from 1234567890@s.whatsapp.net"
}
```

### Health Checks

Docker includes automatic health checks. Check status:

```bash
docker inspect --format='{{.State.Health.Status}}' opencode-webhook
```

### Session Management

Monitor active sessions:

```bash
curl -H "X-API-Key: $ADMIN_API_KEY" \
  http://localhost:5556/sessions
```

## Troubleshooting

### Webhook Not Receiving Events

1. Check webhook is registered:
   ```bash
   curl -H "X-API-Key: $WHATSAPP_API_KEY" \
     http://localhost:8080/api/webhooks
   ```

2. Verify webhook handler is running:
   ```bash
   curl http://localhost:5556/health
   ```

3. Check Docker logs:
   ```bash
   docker-compose -f docker-compose.webhook.yml logs opencode-webhook
   ```

### OpenCode Not Responding

1. Verify OpenCode is installed:
   ```bash
   opencode --version
   ```

2. Test OpenCode manually:
   ```bash
   opencode run "Hello, test message"
   ```

3. Check timeout settings:
   ```bash
   # Increase timeout in .env
   OPENCODE_TIMEOUT=180
   ```

### Session Issues

1. List all sessions:
   ```bash
   curl -H "X-API-Key: $ADMIN_API_KEY" \
     http://localhost:5556/sessions
   ```

2. Delete problematic session:
   ```bash
   curl -X DELETE \
     -H "X-API-Key: $ADMIN_API_KEY" \
     http://localhost:5556/sessions/1234567890@s.whatsapp.net
   ```

3. Check database:
   ```bash
   sqlite3 ./data/sessions.db "SELECT * FROM sessions;"
   ```

## Security Considerations

1. **API Keys**: Store all API keys in environment variables or secure secret management
2. **Network Security**: Use HTTPS for external webhook URLs
3. **Admin Access**: Keep `ADMIN_API_KEY` secure and rotate regularly
4. **Rate Limiting**: Consider adding rate limiting for production use
5. **Input Validation**: All inputs are validated through Pydantic models

## Performance Tuning

### High Volume Deployments

For production or high-volume deployments:

1. **Increase Timeout**: Set `OPENCODE_TIMEOUT=180` or higher
2. **Use PostgreSQL**: Replace SQLite with PostgreSQL for sessions
3. **Load Balancing**: Run multiple webhook handler instances
4. **Message Queue**: Consider adding Redis/RabbitMQ for message queuing

### Resource Limits

Docker Compose configuration can be adjusted:

```yaml
services:
  opencode-webhook:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

## Future Enhancements

- [ ] Session expiration and auto-cleanup
- [ ] Message queue for high volume
- [ ] Rich message responses (buttons, lists)
- [ ] Multi-language support
- [ ] Analytics dashboard
- [ ] Webhook signature verification

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review logs for error messages
3. Open an issue on GitHub

## License

This integration is part of the WhatsApp Python API project.
