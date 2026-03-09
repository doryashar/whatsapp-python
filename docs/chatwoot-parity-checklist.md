# Chatwoot Integration Parity Checklist

Quick reference for verifying whatsapp-python has complete parity with Evolution API.

## Configuration Options

| Option | Evolution | whatsapp-python | Status |
|--------|-----------|-----------------|--------|
| enabled | ✅ | | [ ] |
| accountId | ✅ | | [ ] |
| token | ✅ | | [ ] |
| url | ✅ | | [ ] |
| nameInbox | ✅ | | [ ] |
| signMsg | ✅ | | [ ] |
| signDelimiter | ✅ | | [ ] |
| number | ✅ | | [ ] |
| reopenConversation | ✅ | | [ ] |
| conversationPending | ✅ | | [ ] |
| mergeBrazilContacts | ✅ | | [ ] |
| importContacts | ✅ | | [ ] |
| importMessages | ✅ | | [ ] |
| daysLimitImportMessages | ✅ | | [ ] |
| autoCreate | ✅ | | [ ] |
| organization | ✅ | | [ ] |
| logo | ✅ | | [ ] |
| ignoreJids | ✅ | | [ ] |

## Public Methods

### Setup
| Method | Evolution | whatsapp-python | Status |
|--------|-----------|-----------------|--------|
| create | ✅ | | [ ] |
| find | ✅ | | [ ] |
| initInstanceChatwoot | ✅ | | [ ] |

### Contacts
| Method | Evolution | whatsapp-python | Status |
|--------|-----------|-----------------|--------|
| getContact | ✅ | | [ ] |
| createContact | ✅ | | [ ] |
| updateContact | ✅ | | [ ] |
| findContact | ✅ | | [ ] |
| findContactByIdentifier | ✅ | | [ ] |
| addLabelToContact | ✅ | | [ ] |
| mergeContacts | ✅ | | [ ] |
| mergeBrazilianContacts | ✅ | | [ ] |

### Conversations
| Method | Evolution | whatsapp-python | Status |
|--------|-----------|-----------------|--------|
| createConversation | ✅ | | [ ] |
| getInbox | ✅ | | [ ] |
| getOpenConversationByContact | ✅ | | [ ] |

### Messages
| Method | Evolution | whatsapp-python | Status |
|--------|-----------|-----------------|--------|
| createMessage | ✅ | | [ ] |
| createBotMessage | ✅ | | [ ] |
| createBotQr | ✅ | | [ ] |
| sendData | ✅ | | [ ] |
| sendAttachment | ✅ | | [ ] |
| getConversationMessage | ✅ | | [ ] |

### Events
| Method | Evolution | whatsapp-python | Status |
|--------|-----------|-----------------|--------|
| receiveWebhook | ✅ | | [ ] |
| eventWhatsapp | ✅ | | [ ] |

### History Import
| Method | Evolution | whatsapp-python | Status |
|--------|-----------|-----------------|--------|
| isImportHistoryAvailable | ✅ | | [ ] |
| startImportHistoryMessages | ✅ | | [ ] |
| addHistoryMessages | ✅ | | [ ] |
| addHistoryContacts | ✅ | | [ ] |
| importHistoryMessages | ✅ | | [ ] |
| updateContactAvatarInRecentConversations | ✅ | | [ ] |
| syncLostMessages | ✅ | | [ ] |

## WhatsApp Events Handled

| Event | Evolution | whatsapp-python | Status |
|-------|-----------|-----------------|--------|
| messages.upsert | ✅ | | [ ] |
| send.message | ✅ | | [ ] |
| MESSAGES_DELETE | ✅ | | [ ] |
| messages.edit | ✅ | | [ ] |
| send.message.update | ✅ | | [ ] |
| messages.read | ✅ | | [ ] |
| status.instance | ✅ | | [ ] |
| connection.update | ✅ | | [ ] |
| qrcode.updated | ✅ | | [ ] |

## Chatwoot Webhook Events

| Event | Evolution | whatsapp-python | Status |
|-------|-----------|-----------------|--------|
| message_created (outgoing) | ✅ | | [ ] |
| message_created (template) | ✅ | | [ ] |
| message_updated (deleted) | ✅ | | [ ] |
| conversation_status_changed | ✅ | | [ ] |

## Message Types (Incoming)

| Type | Evolution | whatsapp-python | Status |
|------|-----------|-----------------|--------|
| conversation (text) | ✅ | | [ ] |
| imageMessage | ✅ | | [ ] |
| videoMessage | ✅ | | [ ] |
| audioMessage | ✅ | | [ ] |
| documentMessage | ✅ | | [ ] |
| stickerMessage | ✅ | | [ ] |
| contactMessage (vCard) | ✅ | | [ ] |
| contactsArrayMessage | ✅ | | [ ] |
| locationMessage | ✅ | | [ ] |
| liveLocationMessage | ✅ | | [ ] |
| listMessage | ✅ | | [ ] |
| listResponseMessage | ✅ | | [ ] |
| reactionMessage | ✅ | | [ ] |
| viewOnceMessageV2 | ✅ | | [ ] |
| ephemeralMessage | ✅ | | [ ] |
| extendedTextMessage (ads) | ✅ | | [ ] |
| interactiveMessage (buttons) | ✅ | | [ ] |

## Bot Commands

| Command | Evolution | whatsapp-python | Status |
|---------|-----------|-----------------|--------|
| init | ✅ | | [ ] |
| iniciar | ✅ | | [ ] |
| init:NUMBER | ✅ | | [ ] |
| disconnect | ✅ | | [ ] |
| desconectar | ✅ | | [ ] |
| status | ✅ | | [ ] |
| clearcache | ✅ | | [ ] |

## Special Features

| Feature | Evolution | whatsapp-python | Status |
|---------|-----------|-----------------|--------|
| Markdown conversion (CW→WA) | ✅ | | [ ] |
| Markdown conversion (WA→CW) | ✅ | | [ ] |
| Agent signature | ✅ | | [ ] |
| Custom signature delimiter | ✅ | | [ ] |
| Group message formatting | ✅ | | [ ] |
| Participant contact creation | ✅ | | [ ] |
| Profile picture sync | ✅ | | [ ] |
| Reply/quoted message support | ✅ | | [ ] |
| Brazilian number merge | ✅ | | [ ] |
| LID addressing mode | ✅ | | [ ] |
| Ignore JIDs filter | ✅ | | [ ] |
| QR code image to Chatwoot | ✅ | | [ ] |
| Pairing code display | ✅ | | [ ] |
| Connection notification throttling | ✅ | | [ ] |
| Edited message handling | ✅ | | [ ] |
| Message deletion sync | ✅ | | [ ] |
| Read status sync | ✅ | | [ ] |
| Error private notes | ✅ | | [ ] |
| Conversation caching | ✅ | | [ ] |
| Race condition locking | ✅ | | [ ] |

## History Import Features

| Feature | Evolution | whatsapp-python | Status |
|---------|-----------|-----------------|--------|
| Direct DB connection | ✅ | | [ ] |
| Contact batch import | ✅ | | [ ] |
| Message batch import | ✅ | | [ ] |
| Duplicate detection | ✅ | | [ ] |
| Label assignment | ✅ | | [ ] |
| Avatar sync after import | ✅ | | [ ] |
| Lost message sync | ✅ | | [ ] |

## API Endpoints

| Endpoint | Evolution | whatsapp-python | Status |
|----------|-----------|-----------------|--------|
| POST /chatwoot/set | ✅ | | [ ] |
| GET /chatwoot/find | ✅ | | [ ] |
| POST /chatwoot/webhook | ✅ | | [ ] |

## Notes for Implementation

### Critical Features (Must Have)
1. Message sync (bidirectional)
2. Contact sync
3. Media support
4. Conversation management
5. Bot commands for QR/connection control

### Important Features (Should Have)
1. Profile picture sync
2. Reply/quoted message support
3. Group message formatting
4. Message deletion sync
5. Read status sync

### Nice to Have
1. History import (direct DB)
2. Brazilian number merge
3. LID addressing mode
4. Connection notification throttling
5. Lost message sync

### Key Implementation Details

1. **Source ID Format**: Use `WAID:{messageId}` for messages sent to Chatwoot
2. **Bot Contact Phone**: Always `123456`
3. **Group Suffix**: Add "(GROUP)" to group contact names
4. **Cache TTL**: 1800 seconds (30 minutes) for conversations
5. **Lock Timeout**: 30 seconds for conversation creation lock
6. **QR Code**: Send as image attachment + text with pairing code
7. **Edited Messages**: Create new message with "Edited:" prefix
8. **Error Handling**: Create private note in Chatwoot for send failures
