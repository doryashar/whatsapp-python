# Chatwoot Integration

This document explains how to integrate whatsapp-python with [Chatwoot](https://www.chatwoot.com/), a customer support platform.

## Overview

The Chatwoot integration allows you to:
- Receive WhatsApp messages in Chatwoot as customer conversations
- Send messages from Chatwoot to WhatsApp
- Sync contacts between WhatsApp and Chatwoot
- Handle media attachments (images, videos, documents)
- **Control WhatsApp from Chatwoot via bot commands**
- **Sync profile pictures from WhatsApp to Chatwoot**
- **Preserve reply/quoted message context**
- **Exclude specific contacts from syncing**
- **Message deletion sync (WhatsApp ↔ Chatwoot)**
- **Automatic read status sync**
- **Markdown formatting conversion**

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
    "sign_delimiter": "\n",
    "reopen_conversation": true,
    "import_contacts": true,
    "bot_contact_enabled": true,
    "bot_name": "WhatsApp Bot",
    "ignore_jids": ["status@broadcast"]
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
| `/admin/api/tenants/{hash}/chatwoot/sync-contacts` | POST | Sync contacts to Chatwoot |
| `/admin/api/tenants/{hash}/chatwoot/sync-messages` | POST | Sync message history to Chatwoot |

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | false | Enable/disable integration |
| `url` | string | - | Chatwoot base URL (no trailing /) |
| `token` | string | - | Chatwoot API token |
| `account_id` | string | - | Chatwoot account ID |
| `inbox_id` | int | - | API inbox ID (auto-created on setup) |
| `inbox_name` | string | "WhatsApp" | Custom inbox name |
| `sign_messages` | bool | true | Add agent signature to messages |
| `sign_delimiter` | string | "\n" | Delimiter between signature and message |
| `reopen_conversation` | bool | true | Reopen existing conversations |
| `conversation_pending` | bool | false | Start conversations as pending |
| `import_contacts` | bool | true | Sync WhatsApp contacts to Chatwoot |
| `import_messages` | bool | false | Import message history |
| `days_limit_import` | int | 3 | Days of history to import |
| `merge_brazil_contacts` | bool | true | Handle +55 9-digit numbers |
| `bot_contact_enabled` | bool | true | Enable bot contact commands |
| `bot_name` | string | "Bot" | Name for bot contact |
| `bot_avatar_url` | string | - | Avatar URL for bot contact |
| `ignore_jids` | array | [] | JIDs to exclude from Chatwoot |
| `number` | string | - | WhatsApp number for this instance |
| `auto_create` | bool | true | Auto-create inbox and contact |
| `organization` | string | - | Organization name for bot contact |
| `logo` | string | - | Logo URL for bot contact |
| `message_delete_enabled` | bool | true | Sync message deletions |
| `mark_read_on_reply` | bool | true | Mark WhatsApp messages as read when agent replies |

## Bot Contact Commands

When enabled, a special bot contact (phone: `123456`) is created in Chatwoot. Send messages to this contact to control WhatsApp:

| Command | Description |
|---------|-------------|
| `init` or `iniciar` | Connect WhatsApp instance |
| `init:NUMBER` | Connect with pairing code for specific number |
| `disconnect` or `desconectar` | Disconnect WhatsApp session |
| `status` | Show current connection status |
| `clearcache` | Clear Chatwoot contact/conversation cache |

### Example Usage

1. In Chatwoot, find the contact with phone `123456` (named "WhatsApp Bot" by default)
2. Send `status` to check connection
3. Send `disconnect` to log out
4. Send `init` to reconnect

## Profile Picture Sync

Profile pictures are automatically synced from WhatsApp to Chatwoot:
- When a message is received, the sender's profile picture is fetched
- If the picture has changed, the Chatwoot contact is updated
- Pictures are cached to avoid repeated fetches

## Reply/Quoted Message Support

When a WhatsApp message is a reply to another message:
- The message is created in Chatwoot with `source_id` set to `WAID:{message_id}`
- If replying to another message, `source_reply_id` is set to the quoted message ID
- The quoted text is included in `content_attributes.in_reply_to`

## Ignoring Specific Contacts

To exclude certain contacts from Chatwoot syncing:

```bash
curl -X POST http://localhost:8080/api/chatwoot/config \
  -H "X-API-Key: YOUR_TENANT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "url": "https://chatwoot.example.com",
    "token": "YOUR_TOKEN",
    "account_id": "1",
    "ignore_jids": [
      "status@broadcast",
      "1234567890@s.whatsapp.net"
    ]
  }'
```

Messages from these JIDs will be skipped and not create conversations in Chatwoot.

## Message Deletion Sync

When `message_delete_enabled` is `true` (default):

- When a message is deleted in Chatwoot, it's also deleted in WhatsApp
- Deletions are triggered by the `message_updated` webhook event with empty content

To disable:
```json
{
  "message_delete_enabled": false
}
```

## Read Status Sync

When `mark_read_on_reply` is `true` (default):

- When an agent replies in Chatwoot, the customer's last messages in WhatsApp are marked as read
- This provides a better customer experience by showing the blue checkmarks

To disable:
```json
{
  "mark_read_on_reply": false
}
```

## Markdown Formatting Conversion

Messages sent from Chatwoot have their markdown formatting automatically converted to WhatsApp formatting:

| Chatwoot | WhatsApp |
|----------|----------|
| `**bold**` | `*bold*` |
| `*italic*` | `_italic_` |
| `~~strikethrough~~` | `~strikethrough~` |
| `` `code` `` | `` ```code``` `` |

This conversion happens automatically before sending to WhatsApp.

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

## Message History Sync

### Overview

The message history sync feature allows you to import existing WhatsApp messages stored in whatsapp-python's database into Chatwoot conversations. This is useful when:
- Setting up Chatwoot for the first time with existing message history
- Re-syncing messages after a configuration change
- Recovering conversations after issues

### How to Use

1. **Enable Message Import**: Set `import_messages: true` in your Chatwoot configuration
2. **Configure Days Limit**: Set `days_limit_import` to control how many days of history to sync (default: 3)
3. **Trigger Sync**: Use the admin UI "Sync Messages" button or call the API endpoint manually

### Admin UI

1. Go to Admin Dashboard → Chatwoot
2. Find the tenant you want to sync
3. Click "Sync Messages" button (only visible when `import_messages` is enabled)
4. Wait for sync to complete (progress shown)
5. Review results: synced, skipped, errors

### API Endpoint

```bash
# Sync message history
curl -X POST http://localhost:8080/admin/api/tenants/{tenant_hash}/chatwoot/sync-messages \
  -H "Cookie: admin_session=YOUR_SESSION_ID"

# Response
{
  "synced": 50,
  "skipped": 10,
  "errors": 2,
  "error_details": ["Message 123: API error", "Message 456: Timeout"]
}
```

### How It Works

1. **Retrieve Messages**: Fetches unsynced messages from database within date range
2. **Group by Contact**: Groups messages by chat_jid for efficient processing
3. **Create Contacts/Conversations**: For each contact:
   - Find or create contact in Chatwoot
   - Find or create conversation
4. **Sync Messages**: For each message:
   - Create message in Chatwoot (incoming or outgoing based on direction)
   - Handle media attachments when available
   - Mark as synced to avoid duplicates
5. **Return Stats**: Returns count of synced, skipped, and errors

### Features

- **Skip Duplicates**: Messages already synced are skipped (tracked via `chatwoot_synced_at` timestamp)
- **Both Directions**: Syncs both inbound (from contacts) and outbound (from agents) messages
- **Media Support**: Includes media attachments when URLs are still valid
- **Error Resilient**: Individual message errors don't stop the sync
- **Idempotent**: Safe to run multiple times

### Limitations

- **Media URLs**: WhatsApp media URLs expire after some time. Old media may not sync successfully.
- **Rate Limits**: Chatwoot may have API rate limits. Large syncs may take time.
- **Batch Size**: Limited to 1000 messages per sync to prevent timeouts.
- **Group Messages**: Group messages are skipped (same as live handling)

### Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `import_messages` | bool | false | Enable/disable message sync feature |
| `days_limit_import` | int | 3 | Number of days of history to sync |

### Best Practices

1. **Start Small**: Begin with a small `days_limit_import` (1-3 days) to test
2. **Check Logs**: Review logs for any sync errors
3. **Verify Results**: Check Chatwoot to confirm messages appear correctly
4. **Increment Gradually**: Increase days limit for larger historical imports
5. **Off-Peak**: Run large syncs during off-peak hours

### Troubleshooting

**No messages synced:**
- Check `import_messages` is enabled in config
- Verify database has messages within date range
- Check if messages were already synced (duplicates skipped)

**Media not syncing:**
- Media URLs may have expired
- Check if media_url is stored in database
- Review logs for attachment errors

**Sync taking too long:**
- Reduce `days_limit_import`
- Check Chatwoot API response times
- Consider network latency

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
| Message deletion sync | ✅ | ✅ |
| Read status sync | ✅ | ✅ |
| Markdown conversion | ✅ | ✅ |
| Bot commands | ✅ | ✅ |
| Profile picture sync | ✅ | ✅ |
| Reply context | ✅ | ✅ |
| Ignore JIDs | ✅ | ✅ |

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
