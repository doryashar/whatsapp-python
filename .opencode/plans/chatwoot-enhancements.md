# Chatwoot Integration Enhancements Plan

## Goal

Bring whatsapp-python's Chatwoot integration to feature parity with Evolution API by implementing:
1. Bot contact commands (init/disconnect/status/clearcache)
2. Profile picture sync (WhatsApp → Chatwoot)
3. Reply/quoted message support
4. ignoreJids configuration

## Feature 1: Bot Contact Commands

### Overview
Create a special "bot" contact (phone: `123456`) that handles commands sent from Chatwoot.

### Commands
| Command | Description |
|---------|-------------|
| `init` or `iniciar` | Connect WhatsApp instance (optionally with number for pairing code) |
| `init:NUMBER` | Connect with specific number for pairing code |
| `disconnect` or `desconectar` | Disconnect WhatsApp session |
| `status` | Show connection status |
| `clearcache` | Clear Chatwoot contact/conversation cache |

### Files to Modify

#### 1. `src/chatwoot/models.py`
Add to ChatwootConfig:
- bot_contact_enabled: bool = True
- bot_name: str = "Bot"
- bot_avatar_url: Optional[str] = None

#### 2. `src/chatwoot/webhook_handler.py`
- Add `_handle_bot_command()` method
- Check if message is to bot contact (phone: `123456`)
- Parse and execute commands
- Send responses via `create_message()` to bot conversation

#### 3. `src/chatwoot/client.py`
- Add `find_bot_contact()` - find or create bot contact (phone: 123456)
- Add `find_bot_conversation()` - find or create bot conversation
- Add `send_bot_message()` - send message from bot

#### 4. `src/api/chatwoot_routes.py`
- Add `bot_contact_enabled` to config request model

### Implementation Steps
- [ ] Add config options for bot contact
- [ ] Create bot contact on Chatwoot integration setup
- [ ] Add command detection in webhook handler
- [ ] Implement each command handler
- [ ] Add response messages
- [ ] Test all commands

---

## Feature 2: Profile Picture Sync

### Overview
Sync WhatsApp profile pictures to Chatwoot contacts when receiving messages.

### Files to Modify

#### 1. `bridge/index.mjs`
Add new method `get_profile_picture(params)`:
- Use `sock.profilePictureUrl(jid, "image")`
- Return `{ url }` or `{ url: null }`

#### 2. `src/bridge/client.py`
```python
async def get_profile_picture(self, jid: str) -> dict:
    return await self.call("get_profile_picture", {"jid": jid})
```

#### 3. `src/chatwoot/integration.py`
- In `handle_message()`, after getting contact:
  - Fetch profile picture from WhatsApp
  - Compare with Chatwoot contact thumbnail (filename comparison)
  - Update if different via `update_contact()`

#### 4. `src/chatwoot/client.py`
- Modify `update_contact()` to accept `avatar_url` parameter

### Implementation Steps
- [ ] Add `get_profile_picture` to bridge
- [ ] Add Python bridge client method
- [ ] Add profile picture fetch in integration
- [ ] Add comparison logic (URL filename comparison)
- [ ] Update contact with new avatar
- [ ] Cache to avoid repeated fetches
- [ ] Test with various contacts

---

## Feature 3: Reply/Quoted Message Support

### Overview
Preserve reply context when syncing messages between WhatsApp and Chatwoot.

### Files to Modify

#### 1. `bridge/index.mjs`
- In `extractMessageContent()`, extract `contextInfo`:
  - `quoted_message_id`: `contextInfo.stanzaId`
  - `quoted_participant`: `contextInfo.participant`

#### 2. `src/bridge/protocol.py`
- Add `context_info` field to message event params

#### 3. `src/chatwoot/client.py`
- Modify `create_message()` to accept `source_id` and `source_reply_id`
- Add `content_attributes` with `in_reply_to`

#### 4. `src/store/database.py`
- Add tracking for WhatsApp message ID to Chatwoot message ID mapping

### Implementation Steps
- [ ] Extract context info from WhatsApp messages
- [ ] Pass context info through bridge protocol
- [ ] Store source_id mapping in database
- [ ] Add reply fields to Chatwoot message creation
- [ ] Test reply chains

---

## Feature 4: ignoreJids Configuration

### Overview
Allow excluding certain JIDs from Chatwoot syncing.

### Files to Modify

#### 1. `src/chatwoot/models.py`
```python
ignore_jids: list[str] = Field(default_factory=list)
```

#### 2. `src/api/chatwoot_routes.py`
- Add `ignore_jids` to `ChatwootConfigRequest`

#### 3. `src/chatwoot/integration.py`
- In `handle_message()`, check if JID is in ignore list

### Implementation Steps
- [ ] Add config field
- [ ] Add API endpoint support
- [ ] Add filter logic in integration
- [ ] Test with various JIDs

---

## Implementation Order

| Phase | Feature | Complexity | Time |
|-------|---------|------------|------|
| 1 | ignoreJids | Low | 1h |
| 2 | Bot Commands | Medium | 3h |
| 3 | Profile Pictures | Medium | 2h |
| 4 | Reply Support | High | 4h |
| - | Testing | - | 2h |
| **Total** | | | **12h** |

---

## Configuration Example

```json
{
  "enabled": true,
  "url": "https://chatwoot.example.com",
  "token": "your-token",
  "account_id": "1",
  "inbox_name": "WhatsApp",
  "sign_messages": true,
  "sign_delimiter": "\n",
  "reopen_conversation": true,
  "conversation_pending": false,
  "merge_brazil_contacts": true,
  "import_contacts": true,
  "import_messages": false,
  "days_limit_import": 3,
  "bot_name": "WhatsApp Bot",
  "bot_avatar_url": "https://example.com/bot.png",
  "ignore_jids": ["status@broadcast", "1234567890@s.whatsapp.net"]
}
```

---

## Summary

This plan brings whatsapp-python's Chatwoot integration to feature parity with Evolution API. The four features are:

1. **ignoreJids** - Simple config to exclude JIDs (easiest, start here)
2. **Bot Commands** - Control WhatsApp from Chatwoot (high value)
3. **Profile Pictures** - Visual enhancement (medium complexity)
4. **Reply Support** - Full message context (most complex)

---

## Implementation Status: ✅ COMPLETE

All features have been implemented and tested.

### Files Modified

| File | Changes |
|------|---------|
| `src/chatwoot/models.py` | Added `ignore_jids`, `bot_contact_enabled`, `sign_delimiter`, reply fields |
| `src/chatwoot/client.py` | Added `avatar_url` param, `source_id`/`source_reply_id`, bot contact methods |
| `src/chatwoot/webhook_handler.py` | Added bot commands, signature formatting, `_is_bot_contact()` |
| `src/chatwoot/integration.py` | Added `_is_ignored()`, `_sync_profile_picture()`, reply support |
| `src/api/chatwoot_routes.py` | Added new config fields to request model |
| `src/bridge/client.py` | Added `get_profile_picture()` method |
| `bridge/index.mjs` | Added `get_profile_picture`, context info extraction |
| `docs/chatwoot-integration.md` | Updated documentation |
| `tests/test_chatwoot.py` | Added 26 tests for all features |

### Tests

All 26 tests pass:
```
tests/test_chatwoot.py::TestChatwootConfig - 2 tests
tests/test_chatwoot.py::TestChatwootContact - 1 test
tests/test_chatwoot.py::TestChatwootConversation - 1 test
tests/test_chatwoot.py::TestChatwootMessage - 1 test
tests/test_chatwoot.py::TestChatwootClient - 2 tests
tests/test_chatwoot.py::TestChatwootIntegration - 4 tests
tests/test_chatwoot.py::TestChatwootWebhookHandler - 9 tests
tests/test_chatwoot.py::TestBotCommands - 2 tests
tests/test_chatwoot.py::TestChatwootConfigNewFields - 4 tests
```

### Date Completed: 2026-03-04
