# Chatwoot Integration Parity Checklist - COMPLETE

Last updated: 2026-03-04

## Configuration Options

| Option | Evolution | whatsapp-python | Status |
|--------|-----------|-----------------|--------|
| enabled | ✅ | ✅ | [x] |
| accountId | ✅ | ✅ (account_id) | [x] |
| token | ✅ | ✅ | [x] |
| url | ✅ | ✅ | [x] |
| nameInbox | ✅ | ✅ (inbox_name) | [x] |
| signMsg | ✅ | ✅ (sign_messages) | [x] |
| signDelimiter | ✅ | ✅ (sign_delimiter) | [x] |
| number | ✅ | ✅ | [x] |
| reopenConversation | ✅ | ✅ (reopen_conversation) | [x] |
| conversationPending | ✅ | ✅ (conversation_pending) | [x] |
| mergeBrazilContacts | ✅ | ✅ (merge_brazil_contacts) | [x] |
| importContacts | ✅ | ✅ (import_contacts) | [x] |
| importMessages | ✅ | ✅ (import_messages) | [x] |
| daysLimitImportMessages | ✅ | ✅ (days_limit_import) | [x] |
| autoCreate | ✅ | ✅ (auto_create) | [x] |
| organization | ✅ | ✅ | [x] |
| logo | ✅ | ✅ | [x] |
| ignoreJids | ✅ | ✅ (ignore_jids) | [x] |
| message_delete_enabled | N/A | ✅ | [x] |
| mark_read_on_reply | N/A | ✅ | [x] |
| bot_contact_enabled | N/A | ✅ | [x] |
| bot_name | N/A | ✅ | [x] |
| bot_avatar_url | N/A | ✅ | [x] |
| group_messages_enabled | N/A | ✅ | [x] |

## Public Methods

### Setup
| Method | Evolution | whatsapp-python | Status |
|--------|-----------|-----------------|--------|
| create | ✅ | ✅ | [x] |
| find | ✅ | ✅ | [x] |
| initInstanceChatwoot | ✅ | ✅ (setup_inbox) | [x] |

### Contacts
| Method | Evolution | whatsapp-python | Status |
|--------|-----------|-----------------|--------|
| getContact | ✅ | ✅ (find_contact_by_phone) | [x] |
| createContact | ✅ | ✅ | [x] |
| updateContact | ✅ | ✅ | [x] |
| findContact | ✅ | ✅ | [x] |
| findContactByIdentifier | ✅ | ✅ | [x] |
| mergeBrazilianContacts | ✅ | ✅ (_try_brazil_number_variants) | [x] |

### Conversations
| Method | Evolution | whatsapp-python | Status |
|--------|-----------|-----------------|--------|
| createConversation | ✅ | ✅ | [x] |
| getInbox | ✅ | ✅ (list_inboxes) | [x] |
| getOpenConversationByContact | ✅ | ✅ (find_conversation_by_contact) | [x] |

### Messages
| Method | Evolution | whatsapp-python | Status |
|--------|-----------|-----------------|--------|
| createMessage | ✅ | ✅ | [x] |
| createBotMessage | ✅ | ✅ | [x] |
| createBotQr | ✅ | ✅ (handle_qr) | [x] |
| sendData | ✅ | ✅ (send_message) | [x] |
| sendAttachment | ✅ | ✅ | [x] |

### Events
| Method | Evolution | whatsapp-python | Status |
|--------|-----------|-----------------|--------|
| receiveWebhook | ✅ | ✅ (handle_webhook) | [x] |
| eventWhatsapp | ✅ | ✅ (handle_message) | [x] |

### History Import
| Method | Evolution | whatsapp-python | Status |
|--------|-----------|-----------------|--------|
| sync_message_history | ✅ | ✅ | [x] |

## WhatsApp Events Handled

| Event | Evolution | whatsapp-python | Status |
|-------|-----------|-----------------|--------|
| messages.upsert | ✅ | ✅ (handle_message) | [x] |
| send.message | ✅ | ✅ | [x] |
| MESSAGES_DELETE | ✅ | ✅ | [x] |
| connection.update | ✅ | ✅ | [x] |
| qrcode.updated | ✅ | ✅ (handle_qr) | [x] |

## Chatwoot Webhook Events

| Event | Evolution | whatsapp-python | Status |
|-------|-----------|-----------------|--------|
| message_created (outgoing) | ✅ | ✅ | [x] |
| message_updated (deleted) | ✅ | ✅ | [x] |
| conversation_status_changed | ✅ | ✅ | [x] |

## Message Types (Incoming to Chatwoot)

| Type | Evolution | whatsapp-python | Status |
|------|-----------|-----------------|--------|
| conversation (text) | ✅ | ✅ | [x] |
| imageMessage | ✅ | ✅ | [x] |
| videoMessage | ✅ | ✅ | [x] |
| audioMessage | ✅ | ✅ | [x] |
| documentMessage | ✅ | ✅ | [x] |
| stickerMessage | ✅ | ✅ | [x] |
| locationMessage | ✅ | ✅ | [x] |
| liveLocationMessage | ✅ | ✅ | [x] |
| contactMessage (vCard) | ✅ | ✅ | [x] |
| listMessage | ✅ | ✅ | [x] |
| listResponseMessage | ✅ | ✅ | [x] |
| viewOnceMessageV2 | ✅ | ✅ | [x] |

## Bot Commands

| Command | Evolution | whatsapp-python | Status |
|---------|-----------|-----------------|--------|
| init | ✅ | ✅ | [x] |
| iniciar | ✅ | ✅ | [x] |
| init:NUMBER | ✅ | ✅ | [x] |
| disconnect | ✅ | ✅ | [x] |
| desconectar | ✅ | ✅ | [x] |
| status | ✅ | ✅ | [x] |
| clearcache | ✅ | ✅ | [x] |

## Special Features

| Feature | Evolution | whatsapp-python | Status |
|---------|-----------|-----------------|--------|
| Markdown conversion (CW→WA) | ✅ | ✅ | [x] |
| Markdown conversion (WA→CW) | ✅ | ✅ | [x] |
| Agent signature | ✅ | ✅ | [x] |
| Custom signature delimiter | ✅ | ✅ | [x] |
| Group message formatting | ✅ | ✅ | [x] |
| Participant contact creation | ✅ | ✅ | [x] |
| Profile picture sync | ✅ | ✅ | [x] |
| Reply/quoted message support | ✅ | ✅ | [x] |
| Brazilian number merge | ✅ | ✅ | [x] |
| Ignore JIDs filter | ✅ | ✅ | [x] |
| QR code image to Chatwoot | ✅ | ✅ | [x] |
| Message deletion sync | ✅ | ✅ | [x] |
| Read status sync | ✅ | ✅ | [x] |
| Error private notes | ✅ | ✅ | [x] |
| Conversation caching with TTL | ✅ | ✅ | [x] |
| Message edit handling | ✅ | ✅ | [x] |

## API Endpoints

| Endpoint | Evolution | whatsapp-python | Status |
|----------|-----------|-----------------|--------|
| POST /chatwoot/set | ✅ | ✅ (POST /api/chatwoot/config) | [x] |
| GET /chatwoot/find | ✅ | ✅ (GET /api/chatwoot/config) | [x] |
| POST /chatwoot/webhook | ✅ | ✅ (POST /webhooks/chatwoot/{hash}/outgoing) | [x] |

## Summary

**All features implemented and tested!**

- Total tests: 77
- All passing: ✅
- Test files:
  - `tests/test_chatwoot.py` (62 tests)
  - `tests/test_chatwoot_sync.py` (15 tests)

## Files Modified

1. `src/chatwoot/models.py` - Added `group_messages_enabled` field
2. `src/chatwoot/integration.py` - Added group messages, WA→CW markdown, message types, edit handling
3. `src/chatwoot/client.py` - Added TTL-based conversation caching
4. `src/chatwoot/webhook_handler.py` - Added error private notes
5. `src/api/chatwoot_routes.py` - Added `group_messages_enabled` to config request
6. `tests/test_chatwoot.py` - Added 24 new tests

## Completion Date

**2026-03-04** - Full Chatwoot parity achieved with EvolutionAPI
