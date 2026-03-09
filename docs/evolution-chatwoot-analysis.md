# Evolution API Chatwoot Integration - Complete Feature Analysis

This document provides a comprehensive analysis of Evolution API's Chatwoot integration for parity verification.

## Files Analyzed

| File | Size | Purpose |
|------|------|---------|
| `chatwoot.service.ts` | ~86KB | Main service with all business logic |
| `chatwoot.controller.ts` | ~2.7KB | HTTP request handling |
| `chatwoot.dto.ts` | ~1.2KB | Data transfer objects |
| `chatwoot.router.ts` | ~1.8KB | Route definitions |
| `chatwoot.schema.ts` | ~1.6KB | JSON schema validation |
| `chatwoot-import-helper.ts` | ~23KB | History import functionality |
| `postgres.client.ts` | ~1KB | PostgreSQL connection for direct DB access |

---

## 1. Configuration Options (DTO)

```typescript
class ChatwootDto {
  enabled?: boolean;
  accountId?: string;
  token?: string;
  url?: string;
  nameInbox?: string;
  signMsg?: boolean;
  signDelimiter?: string;
  number?: string;
  reopenConversation?: boolean;
  conversationPending?: boolean;
  mergeBrazilContacts?: boolean;
  importContacts?: boolean;
  importMessages?: boolean;
  daysLimitImportMessages?: number;
  autoCreate?: boolean;
  organization?: string;
  logo?: string;
  ignoreJids?: string[];
}
```

### Database Model (Prisma)

```prisma
model Chatwoot {
  id                      String    @id @default(cuid())
  enabled                 Boolean?  @default(true)
  accountId               String?
  token                   String?
  url                     String?
  nameInbox               String?
  signMsg                 Boolean?  @default(false)
  signDelimiter           String?
  number                  String?
  reopenConversation      Boolean?  @default(false)
  conversationPending     Boolean?  @default(false)
  mergeBrazilContacts     Boolean?  @default(false)
  importContacts          Boolean?  @default(false)
  importMessages          Boolean?  @default(false)
  daysLimitImportMessages Int?
  organization            String?
  logo                    String?
  ignoreJids              Json?
  createdAt               DateTime?
  updatedAt               DateTime  @updatedAt
  instanceId              String    @unique
}
```

### Environment Configuration

```typescript
CHATWOOT: {
  ENABLED: boolean;
  BOT_CONTACT: boolean;
  MESSAGE_READ: boolean;
  MESSAGE_DELETE: boolean;
  IMPORT: {
    DATABASE: {
      CONNECTION: {
        URI: string;  // Direct PostgreSQL connection to Chatwoot DB
      };
    };
    PLACEHOLDER_MEDIA_MESSAGE: boolean;
  };
}
```

---

## 2. Public Methods (Service)

### Core Setup Methods

| Method | Description |
|--------|-------------|
| `create(instance, data)` | Create/update Chatwoot configuration |
| `find(instance)` | Find Chatwoot configuration for instance |
| `initInstanceChatwoot(instance, inboxName, webhookUrl, qrcode, number, organization?, logo?)` | Initialize inbox, bot contact, conversation |

### Contact Management

| Method | Description |
|--------|-------------|
| `getContact(instance, id)` | Get contact by Chatwoot ID |
| `createContact(instance, phoneNumber, inboxId, isGroup, name?, avatar_url?, jid?)` | Create contact in Chatwoot |
| `updateContact(instance, id, data)` | Update contact in Chatwoot |
| `findContact(instance, phoneNumber)` | Find contact by phone number |
| `findContactByIdentifier(instance, identifier)` | Find contact by identifier/JID |
| `addLabelToContact(nameInbox, contactId)` | Add label to contact (direct DB) |
| `mergeContacts(baseId, mergeId)` | Merge two contacts |
| `mergeBrazilianContacts(contacts)` | Merge Brazilian +55 contacts |

### Conversation Management

| Method | Description |
|--------|-------------|
| `createConversation(instance, body)` | Create or find conversation |
| `getInbox(instance)` | Get inbox by name |
| `getOpenConversationByContact(instance, inbox, contact)` | Get open conversation for contact |

### Message Handling

| Method | Description |
|--------|-------------|
| `createMessage(instance, conversationId, content, messageType, privateMessage?, attachments?, messageBody?, sourceId?, quotedMsg?)` | Create message in Chatwoot |
| `createBotMessage(instance, content, messageType, attachments?)` | Send message to bot conversation |
| `createBotQr(instance, content, messageType, fileStream?, fileName?)` | Send QR code image to bot |
| `sendData(conversationId, fileStream, fileName, messageType, content?, instance?, messageBody?, sourceId?, quotedMsg?)` | Send media attachment |
| `sendAttachment(waInstance, number, media, caption?, options?)` | Send attachment to WhatsApp |
| `getConversationMessage(msg)` | Extract text content from WhatsApp message |

### Webhook & Event Handling

| Method | Description |
|--------|-------------|
| `receiveWebhook(instance, body)` | Handle incoming Chatwoot webhook |
| `eventWhatsapp(event, instance, body)` | Handle WhatsApp events |

### Utility Methods

| Method | Description |
|--------|-------------|
| `getClientCwConfig()` | Get Chatwoot client configuration |
| `getCache()` | Access cache service |
| `onSendMessageError(instance, conversation, error)` | Handle send errors (create private note) |
| `updateChatwootMessageId(message, chatwootMessageIds, instance)` | Update message with Chatwoot IDs |
| `normalizeJidIdentifier(remoteJid)` | Normalize JID for identifier |

### History Import Methods

| Method | Description |
|--------|-------------|
| `isImportHistoryAvailable()` | Check if import DB connection configured |
| `startImportHistoryMessages(instance)` | Start import notification |
| `addHistoryMessages(instance, messagesRaw)` | Add messages to import queue |
| `addHistoryContacts(instance, contactsRaw)` | Add contacts to import queue |
| `importHistoryMessages(instance)` | Execute history import |
| `updateContactAvatarInRecentConversations(instance, limitContacts?)` | Update avatars for recent contacts |
| `syncLostMessages(instance, chatwootConfig, prepareMessage)` | Sync messages missed during downtime |

---

## 3. Webhook Events Handled (receiveWebhook)

| Event | Condition | Action |
|-------|-----------|--------|
| `conversation_status_changed` | `status === 'resolved'` & `reopenConversation === false` | Delete conversation from cache |
| `message_updated` | `content_attributes.deleted === true` | Delete message from WhatsApp |
| `message_created` | `message_type === 'outgoing'` | Send message to WhatsApp |
| `message_created` | `message_type === 'template'` | Send template message |
| Any | `chatId === '123456'` | Handle bot commands |
| Any | `body.private === true` | Skip (private notes) |
| Any | `source_id.startsWith('WAID:')` | Skip (already synced) |

---

## 4. WhatsApp Events Handled (eventWhatsapp)

| Event | Description |
|-------|-------------|
| `messages.upsert` | New incoming/outgoing message |
| `send.message` | Message sent from API |
| `MESSAGES_DELETE` | Message deleted in WhatsApp |
| `messages.edit` | Message edited in WhatsApp |
| `send.message.update` | Message edit from API |
| `messages.read` | Messages marked as read |
| `status.instance` | Instance status change |
| `connection.update` | Connection status (open) |
| `qrcode.updated` | QR code generated/limit reached |

---

## 5. Message Types Supported

### Incoming (WhatsApp → Chatwoot)

| Type | Handling |
|------|----------|
| Text (conversation) | Direct text |
| Image | Attachment + caption |
| Video | Attachment + caption |
| Audio | Attachment |
| Document | Attachment + caption |
| Sticker | Attachment |
| Contact (vCard) | Formatted text with phone numbers |
| Contacts Array | Formatted text for multiple contacts |
| Location | Formatted text with Google Maps link |
| Live Location | Formatted text with coordinates |
| List Message | Formatted text with sections/rows |
| List Response | Formatted text with selection |
| Reaction | Text message with emoji |
| View Once | Attachment |
| Ephemeral | Unwrap and process inner message |
| Extended Text (with context) | Text + reply reference |
| Ads Message | Thumbnail + formatted text |
| Interactive Buttons (Payment/PIX) | Formatted text with payment info |
| Template Message | Text content |

### Outgoing (Chatwoot → WhatsApp)

| Type | Handling |
|------|----------|
| Text | Send via textMessage API |
| Image | Send via mediaMessage API |
| Video | Send via mediaMessage API |
| Audio | Send via audioWhatsapp API |
| Document | Send via mediaMessage API |

---

## 6. Special Handling

### Markdown Conversion (Chatwoot → WhatsApp)

```javascript
// Chatwoot format → WhatsApp format
*italic* → _italic_
**bold** → *bold*
~~strikethrough~~ → ~strikethrough~
`code` → ```code```
```

### Markdown Conversion (WhatsApp → Chatwoot)

```javascript
// WhatsApp format → Chatwoot format
*bold* → **bold**
_italic_ → *italic*
~strikethrough~ → ~~strikethrough~~
```code``` → `code`
```

### Brazilian Number Merge

When `mergeBrazilContacts` is enabled:
- Handles +55 numbers with/without 9 digit
- Merges duplicate contacts automatically
- Searches both formats when finding contacts

### Group Message Handling

For groups (@g.us):
- Creates group as contact with "(GROUP)" suffix
- Creates participant as separate contact
- Formats message with participant name and phone
- Example: `**+55 11 99999-9999 - John Doe:**\n\nMessage content`

### Reply/Quoted Message Support

- Extracts `stanzaId` from `contextInfo`
- Finds original message in database
- Sets `in_reply_to` to Chatwoot message ID
- Sets `source_reply_id` for threading

### Contact Labeling

- Automatically adds label to contacts (direct DB operation)
- Label name = inbox name
- Creates tag if not exists
- Creates tagging record

### Profile Picture Sync

- Fetches profile picture on first message
- Compares filename to detect changes
- Updates Chatwoot contact avatar_url when changed
- Clears avatar when WhatsApp picture removed

### LID (Addressing Mode) Support

Handles WhatsApp's LID addressing mode:
- Uses `remoteJidAlt` when `addressingMode === 'lid'`
- Updates contact identifier when LID changes
- Merges contacts when duplicates detected

---

## 7. Caching Mechanisms

### Cache Keys

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| `{instance}:getProvider` | Default | Store provider config |
| `{instance}:getInbox` | Default | Store inbox object |
| `{instance}:createConversation-{remoteJid}` | 1800s (30min) | Store conversation ID |
| `{instance}:lock:createConversation-{remoteJid}` | 30s | Lock for race condition prevention |

### Locking Strategy

```typescript
LOCK_POLLING_DELAY_MS = 300;  // 300ms between checks
maxWaitTime = 5000;           // 5 second timeout
```

### Cache Invalidation

- Conversation cache cleared on `conversation_status_changed` (resolved)
- Cache cleared via `clearcache` bot command
- Lock auto-expires after 30 seconds

---

## 8. Database Operations

### Message Table Updates

```sql
UPDATE "Message" 
SET 
  "chatwootMessageId" = ?,
  "chatwootConversationId" = ?,
  "chatwootInboxId" = ?,
  "chatwootContactInboxSourceId" = ?,
  "chatwootIsRead" = ?
WHERE "instanceId" = ? AND "key"->>'id' = ?
```

### Direct Chatwoot DB Operations

Via PostgreSQL connection to Chatwoot database:

```sql
-- Tags
INSERT INTO tags (name, taggings_count) VALUES (?, ?)
ON CONFLICT (name) DO UPDATE SET taggings_count = tags.taggings_count + 1

-- Taggings (labels)
INSERT INTO taggings (tag_id, taggable_type, taggable_id, context, created_at)
VALUES (?, 'Contact', ?, 'labels', NOW())

-- Messages (history import)
INSERT INTO messages (content, processed_message_content, account_id, inbox_id, 
  conversation_id, message_type, private, content_type, sender_type, sender_id, 
  source_id, created_at, updated_at)
VALUES (...)

-- Contacts (history import)
INSERT INTO contacts (name, phone_number, account_id, identifier, created_at, updated_at)
VALUES (...) ON CONFLICT (identifier, account_id) DO UPDATE SET ...

-- Contact Inboxes (history import)
INSERT INTO contact_inboxes (contact_id, inbox_id, source_id, created_at, updated_at)
VALUES (...)

-- Conversations (history import)
INSERT INTO conversations (account_id, inbox_id, status, contact_id, 
  contact_inbox_id, uuid, last_activity_at, created_at, updated_at)
VALUES (...)
```

---

## 9. API Endpoints

### Router Definition

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chatwoot/set` | POST | Create/update Chatwoot config |
| `/chatwoot/find` | GET | Get Chatwoot config |
| `/chatwoot/webhook` | POST | Receive webhooks from Chatwoot |

### Request/Response Formats

#### POST /chatwoot/set

```json
{
  "enabled": true,
  "accountId": "1",
  "token": "xxx",
  "url": "https://chatwoot.example.com",
  "nameInbox": "WhatsApp",
  "signMsg": true,
  "signDelimiter": "\n",
  "reopenConversation": true,
  "conversationPending": false,
  "mergeBrazilContacts": true,
  "importContacts": true,
  "importMessages": false,
  "daysLimitImportMessages": 3,
  "autoCreate": true,
  "number": "5511999999999",
  "organization": "My Company",
  "logo": "https://example.com/logo.png",
  "ignoreJids": ["status@broadcast", "@g.us"]
}
```

Response includes `webhook_url`:
```json
{
  "enabled": true,
  "webhook_url": "https://evolution.example.com/chatwoot/webhook/instanceName"
}
```

#### POST /chatwoot/webhook

Receives Chatwoot webhook events. Returns `{ message: 'bot' }` for processed events.

---

## 10. Bot Commands

Commands sent to contact with phone `123456`:

| Command | Aliases | Action |
|---------|---------|--------|
| `init` | `iniciar` | Connect WhatsApp |
| `init:NUMBER` | - | Connect with specific number |
| `disconnect` | `desconectar` | Logout WhatsApp |
| `status` | - | Show connection status |
| `clearcache` | - | Clear Chatwoot cache |

---

## 11. Error Handling

### Message Send Errors

Creates private note in Chatwoot conversation:
- Number not on WhatsApp: "Number not on WhatsApp"
- Other errors: "Message not sent: {error}"

### Contact Creation Errors

- 422 (duplicate): Find existing contact and return it
- Other errors: Log and return null

### Conversation Creation Errors

- Logs error and returns null
- Releases lock on failure

---

## 12. History Import (chatwoot-import-helper.ts)

### Features

- Batch processing (3000 contacts, 4000 messages per batch)
- Duplicate detection via source_id
- Progress tracking
- Error resilience
- Contact label assignment
- Avatar sync for recent conversations

### Import Process

1. Collect messages/contacts from Evolution DB
2. Order messages by phone number and timestamp
3. Create contacts (if not exist)
4. Create contact_inboxes
5. Create conversations
6. Create messages with source_id = 'WAID:{id}'
7. Update avatars for recent contacts

---

## 13. Feature Parity Checklist

Use this checklist to verify whatsapp-python implementation:

### Core Features

- [ ] Create/update Chatwoot configuration
- [ ] Find Chatwoot configuration
- [ ] Auto-create inbox on setup
- [ ] Auto-create bot contact
- [ ] Webhook endpoint for Chatwoot

### Contact Management

- [ ] Create contact in Chatwoot
- [ ] Update contact in Chatwoot
- [ ] Find contact by phone number
- [ ] Find contact by identifier
- [ ] Merge Brazilian contacts (+55)
- [ ] Add labels to contacts
- [ ] Sync profile pictures

### Conversation Management

- [ ] Create conversation
- [ ] Find existing conversation
- [ ] Reopen resolved conversations
- [ ] Set conversation as pending
- [ ] Handle group conversations

### Message Handling

- [ ] Send text message to Chatwoot
- [ ] Send media attachment to Chatwoot
- [ ] Send message to WhatsApp
- [ ] Send media to WhatsApp
- [ ] Handle reply/quoted messages
- [ ] Mark messages as read

### Event Processing

- [ ] Handle messages.upsert
- [ ] Handle messages.delete
- [ ] Handle messages.edit
- [ ] Handle messages.read
- [ ] Handle connection.update
- [ ] Handle qrcode.updated
- [ ] Handle status.instance

### Message Types

- [ ] Text messages
- [ ] Image messages
- [ ] Video messages
- [ ] Audio messages
- [ ] Document messages
- [ ] Sticker messages
- [ ] Contact messages (vCard)
- [ ] Location messages
- [ ] Live location messages
- [ ] List messages
- [ ] Reaction messages
- [ ] View once messages
- [ ] Ads/extended messages
- [ ] Interactive button messages
- [ ] Template messages

### Bot Commands

- [ ] init/iniciar command
- [ ] init:NUMBER command
- [ ] disconnect/desconectar command
- [ ] status command
- [ ] clearcache command

### Special Features

- [ ] Markdown conversion (Chatwoot → WhatsApp)
- [ ] Markdown conversion (WhatsApp → Chatwoot)
- [ ] Agent signature on messages
- [ ] Custom signature delimiter
- [ ] Group message formatting
- [ ] Participant contact creation
- [ ] LID addressing mode support
- [ ] Ignore JIDs filter
- [ ] Conversation caching
- [ ] Lock mechanism for race conditions

### History Import

- [ ] Import contacts to Chatwoot DB
- [ ] Import messages to Chatwoot DB
- [ ] Batch processing
- [ ] Duplicate detection
- [ ] Avatar sync after import
- [ ] Lost message sync

### Error Handling

- [ ] Send error private notes
- [ ] Handle contact creation errors
- [ ] Handle message send errors
- [ ] Handle number not on WhatsApp

### Configuration Options

- [ ] enabled
- [ ] accountId
- [ ] token
- [ ] url
- [ ] nameInbox
- [ ] signMsg
- [ ] signDelimiter
- [ ] number
- [ ] reopenConversation
- [ ] conversationPending
- [ ] mergeBrazilContacts
- [ ] importContacts
- [ ] importMessages
- [ ] daysLimitImportMessages
- [ ] autoCreate
- [ ] organization
- [ ] logo
- [ ] ignoreJids

---

## 14. Key Differences to Note

1. **Direct DB Access**: Evolution can write directly to Chatwoot's PostgreSQL database for history import. This requires database connection configuration.

2. **Cache Service**: Uses internal cache service with Redis-like interface for conversation caching.

3. **Chatwoot SDK**: Uses `@figuro/chatwoot-sdk` for API calls.

4. **Message Source ID**: Uses `WAID:{messageId}` prefix for source_id to identify WhatsApp-originated messages.

5. **i18n Support**: Uses i18next for internationalized messages.

6. **Telemetry**: Sends telemetry events for message operations.

7. **QR Code Delivery**: Sends QR code as image attachment + text with pairing code to bot conversation.

8. **Connection Notifications**: Throttles connection notifications (30s minimum between notifications).

9. **Edited Messages**: Creates new message with "Edited:" prefix rather than updating existing.

10. **Message Read Sync**: Uses Chatwoot's public API endpoint for marking conversations as read.
