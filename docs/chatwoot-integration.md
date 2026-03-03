# Chatwoot Integration

This document explains how to integrate whatsapp-python with [Chatwoot](https://www.chatwoot.com/), a customer support platform.

## Overview

The Chatwoot integration allows you to:
- Receive WhatsApp messages in Chatwoot as customer conversations
- Send messages from Chatwoot to WhatsApp
- Sync contacts between WhatsApp and Chatwoot
- Handle media attachments (images, videos, documents)

## Architecture

```
WhatsApp ←→ whatsapp-python ←→ Chatwoot (API Channel)
```

Unlike Chatwoot's native WhatsApp Cloud API integration, this uses Chatwoot's **API Channel** inbox. whatsapp-python handles all WhatsApp connectivity via Baileys (WhatsApp Web protocol), and syncs messages with Chatwoot via HTTP API.

## Configuration

### 1. Create a Chatwoot API Channel Inbox

First, create an API channel inbox in Chatwoot:

1. Go to Settings → Inboxes → Add Inbox
2. Select "API" as the channel type
3. Name it (e.g., "WhatsApp")
4. Copy the `inbox_id` and `webhook_url`

### 2. Get Chatwoot API Token

1. Go to Profile Settings → Access Tokens
2. Create a new token with appropriate permissions
3. Copy the token

### 3. Configure whatsapp-python

Use the API to configure Chatwoot:

```bash
# Set Chatwoot configuration
curl -X POST http://localhost:8080/api/chatwoot/config \
  -H "X-API-Key: YOUR_TENANT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "url": "https://chatwoot.example.com",
    "token": "YOUR_CHATWOOT_API_TOKEN",
    "account_id": "1",
    "inbox_name": "WhatsApp",
    "sign_messages": true,
    "reopen_conversation": true,
    "import_contacts": true
  }'
```

### 4. Auto-Setup (Optional)

Alternatively, use auto-setup to create the inbox automatically:

```bash
curl -X POST http://localhost:8080/api/chatwoot/setup \
  -H "X-API-Key: YOUR_TENANT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"inbox_name": "WhatsApp"}'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chatwoot/config` | GET | Get current configuration |
| `/api/chatwoot/config` | POST | Set configuration |
| `/api/chatwoot/config` | DELETE | Disable integration |
| `/api/chatwoot/setup` | POST | Auto-create inbox |
| `/api/chatwoot/status` | GET | Check connection status |
| `/webhooks/chatwoot/{tenant}/outgoing` | POST | Receive from Chatwoot |

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | false | Enable/disable integration |
| `url` | string | - | Chatwoot base URL (no trailing /) |
| `token` | string | - | Chatwoot API token |
| `account_id` | string | - | Chatwoot account ID |
| `inbox_id` | string | - | API inbox ID (auto-created on setup) |
| `inbox_name` | string | "WhatsApp" | Custom inbox name |
| `sign_messages` | bool | true | Add agent signature to messages |
| `reopen_conversation` | bool | true | Reopen existing conversations |
| `conversation_pending` | bool | false | Start conversations as pending |
| `import_contacts` | bool | true | Sync WhatsApp contacts to Chatwoot |
| `import_messages` | bool | false | Import message history |
| `days_limit_import` | int | 3 | Days of history to import |
| `merge_brazil_contacts` | bool | true | Handle +55 9-digit numbers |

## How It Works

### Incoming Messages (WhatsApp → Chatwoot)

1. Message received from WhatsApp via Baileys
2. whatsapp-python extracts sender phone number
3. Find or create contact in Chatwoot
4. Find or create conversation for contact
5. Send message to Chatwoot conversation

### Outgoing Messages (Chatwoot → WhatsApp)

1. Agent sends message in Chatwoot
2. Chatwoot posts to whatsapp-python webhook
3. Webhook signature verified
4. Message sent via whatsapp-python to WhatsApp

## Webhook Format

Chatwoot sends webhooks to whatsapp-python in this format:

```json
{
  "event": "message_created",
  "message": {
    "id": 1,
    "content": "Hello!",
    "message_type": "outgoing",
    "private": false,
    "attachments": []
  },
  "conversation": {
    "id": 1,
    "status": "open"
  },
  "sender": {
    "id": 1,
    "phone_number": "+1234567890"
  }
}
```

## Media Support

### Incoming Media

When a WhatsApp message contains media:
- Images, videos, audio, documents are supported
- Media is forwarded to Chatwoot as attachments
- Chatwoot displays media inline when possible

### Outgoing Media

When an agent attaches a file in Chatwoot:
- Chatwoot sends attachment URL in webhook
- whatsapp-python downloads and sends to WhatsApp

## Comparison with Evolution API

This integration is similar to [Evolution API](https://github.com/EvolutionAPI/evolution-api)'s Chatwoot integration:

| Feature | Evolution API | whatsapp-python |
|---------|--------------|-----------------|
| Contact sync | ✅ | ✅ |
| Message sync | ✅ | ✅ |
| Media support | ✅ | ✅ |
| Auto-create inbox | ✅ | ✅ |
| Signature on messages | ✅ | ✅ |
| Reopen conversation | ✅ | ✅ |
| Import message history | ✅ | ✅ |
| Brazilian number merge | ✅ | ✅ |

## Troubleshooting

### Messages not appearing in Chatwoot

1. Check if Chatwoot integration is enabled: `GET /api/chatwoot/status`
2. Verify API token has correct permissions
3. Check whatsapp-python logs for errors

### Outgoing messages not sending

1. Verify webhook URL is accessible from Chatwoot
2. Check webhook signature verification
3. Verify tenant has active WhatsApp session

### Contact not syncing

1. Ensure `import_contacts` is enabled
2. Check if phone number format is correct
3. For Brazilian numbers, enable `merge_brazil_contacts`

## Security

- All API calls use Bearer token authentication
- Webhook signature verification (HMAC-SHA256)
- Tenant isolation via API keys

## Rate Limits

Chatwoot may have its own rate limits. whatsapp-python does not add additional rate limiting for Chatwoot API calls.
