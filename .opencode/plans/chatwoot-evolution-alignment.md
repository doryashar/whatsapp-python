# Chatwoot Integration Alignment with Evolution API

## Overview

This plan outlines the changes needed to align whatsapp-python's Chatwoot integration with [Evolution API](https://github.com/EvolutionAPI/evolution-api)'s implementation for feature parity.

---

## Current State Comparison

### API Endpoints

| Feature | Evolution API | whatsapp-python | Status |
|---------|--------------|-----------------|--------|
| Set config | `POST /chatwoot/set/{instance}` | `POST /api/chatwoot/config` | Different path |
| Get config | `GET /chatwoot/find/{instance}` | `GET /api/chatwoot/config` | Different path |
| Webhook | `POST /chatwoot/webhook/{instance}` | `POST /webhooks/chatwoot/{tenant_hash}/outgoing` | Different path |
| Status check | Via `/chatwoot/find/{instance}` | `GET /api/chatwoot/status` | whatsapp-python has dedicated endpoint |
| Auto-setup | Built into `/chatwoot/set` | `POST /api/chatwoot/setup` | Separate endpoint |
| Admin sync | N/A | `POST /admin/api/tenants/{hash}/chatwoot/sync-*` | whatsapp-python has extra endpoints |

### Configuration Fields

| Field | Evolution API | whatsapp-python | Status |
|-------|--------------|-----------------|--------|
| `enabled` | bool | bool | Match |
| `url` | string | string | Match |
| `token` | string | string | Match |
| `accountId` / `account_id` | string | string | Different naming (snake_case vs camelCase) |
| `nameInbox` / `inbox_name` | string | string | Different naming |
| `signMsg` / `sign_messages` | bool | bool | Different naming |
| `signDelimiter` / `sign_delimiter` | string | string | Different naming |
| `reopenConversation` / `reopen_conversation` | bool | bool | Different naming |
| `conversationPending` / `conversation_pending` | bool | bool | Different naming |
| `mergeBrazilContacts` / `merge_brazil_contacts` | bool | bool | Different naming |
| `importContacts` / `import_contacts` | bool | bool | Different naming |
| `importMessages` / `import_messages` | bool | bool | Different naming |
| `daysLimitImportMessages` / `days_limit_import` | number | number | Different naming |
| `ignoreJids` / `ignore_jids` | string[] | string[] | Different naming |
| `number` | string | **Missing** | Need to add |
| `autoCreate` | bool | **Missing** | Need to add |
| `organization` | string | **Missing** | Need to add |
| `logo` | string | **Missing** | Need to add |
| `bot_contact_enabled` | **Missing** | bool | Evolution doesn't expose this |
| `bot_name` | **Missing** | string | Evolution doesn't expose this |
| `bot_avatar_url` | **Missing** | string | Evolution doesn't expose this |

### Environment Variables

| Variable | Evolution API | whatsapp-python |
|----------|--------------|-----------------|
| `CHATWOOT_ENABLED` | bool | Not configurable |
| `CHATWOOT_MESSAGE_READ` | bool | Not configurable |
| `CHATWOOT_MESSAGE_DELETE` | bool | Not configurable |
| `CHATWOOT_BOT_CONTACT` | bool | Per-tenant config |

---

## Missing Features (Need to Add)

### 1. Message Formatting Conversion (HIGH PRIORITY)

Evolution API converts markdown formatting between Chatwoot and WhatsApp:

**Current whatsapp-python**: No formatting conversion

**Evolution API behavior**:
- Chatwoot `*text*` (bold) → WhatsApp `_text_` (italic)
- Chatwoot `**text**` → WhatsApp `*text*` (bold)
- Chatwoot `~~text~~` → WhatsApp `~text~` (strikethrough)
- Chatwoot `` `text` `` → WhatsApp `` ```text``` `` (monospace)

**Implementation**:
- Add `_convert_markdown_formatting()` method in `webhook_handler.py`
- Apply conversion before sending to WhatsApp
- Add tests for formatting conversion

### 2. Message Deletion Support (HIGH PRIORITY)

**Evolution API**: 
- Handles `message_updated` webhook event
- Deletes message in Chatwoot when deleted in WhatsApp (configurable via `CHATWOOT_MESSAGE_DELETE`)
- Deletes message in WhatsApp when deleted in Chatwoot

**Current whatsapp-python**: No message deletion support

**Implementation**:
1. Add `message_updated` event handler in `webhook_handler.py`
2. Check if content is empty (indicates deletion)
3. Call bridge to delete message in WhatsApp
4. Add config option `message_delete_enabled` (default: true)
5. Add tests

### 3. Message Read Status Sync (MEDIUM PRIORITY)

**Evolution API**:
- Marks WhatsApp messages as read when agent replies (configurable via `CHATWOOT_MESSAGE_READ`)

**Current whatsapp-python**: No read status sync

**Implementation**:
1. Add config option `mark_read_on_reply` (default: true)
2. After sending message to WhatsApp, call `mark_read` on the conversation
3. Add tests

### 4. Additional Configuration Fields (MEDIUM PRIORITY)

Add missing fields to match Evolution API:

```python
# In models.py ChatwootConfig
number: Optional[str] = None  # WhatsApp number for instance
auto_create: bool = True  # Auto-create inbox/contact
organization: Optional[str] = None  # Organization name for bot contact
logo: Optional[str] = None  # Logo URL for bot contact
```

### 5. Webhook Event: message_updated (HIGH PRIORITY)

**Evolution API handles**:
```json
{
  "event": "message_updated",
  "message": {
    "id": 123,
    "content": "",  // Empty content = deleted
    ...
  }
}
```

**Implementation**:
```python
async def _handle_message_updated(self, payload: dict) -> dict:
    message_data = payload.get("message", {})
    content = message_data.get("content", "")
    
    if not content:  # Message deleted
        if self._config.message_delete_enabled:
            # Delete in WhatsApp
            message_id = message_data.get("source_id")
            if message_id:
                await self._bridge.delete_message(message_id)
    
    return {"status": "acknowledged"}
```

---

## Implementation Plan

### Phase 1: Core Feature Parity

1. **Message Formatting Conversion** (`src/chatwoot/webhook_handler.py`)
   - [ ] Add `_convert_markdown_formatting()` method
   - [ ] Apply in `_format_message()`
   - [ ] Add tests in `tests/test_chatwoot.py`

2. **Message Deletion Support** (`src/chatwoot/webhook_handler.py`)
   - [ ] Add `message_updated` event handler
   - [ ] Add `message_delete_enabled` config option
   - [ ] Implement message deletion via bridge
   - [ ] Add tests

3. **Message Read Sync** (`src/chatwoot/webhook_handler.py`)
   - [ ] Add `mark_read_on_reply` config option
   - [ ] Mark conversation as read after sending
   - [ ] Add tests

### Phase 2: Configuration Alignment

4. **Add Missing Config Fields** (`src/chatwoot/models.py`, `src/api/chatwoot_routes.py`)
   - [ ] Add `number`, `auto_create`, `organization`, `logo`
   - [ ] Update request/response models
   - [ ] Update documentation

### Phase 3: Documentation

5. **Update Documentation** (`docs/chatwoot-integration.md`)
   - [ ] Document new configuration options
   - [ ] Document message formatting conversion
   - [ ] Document message deletion behavior
   - [ ] Update comparison table

---

## Code Changes Required

### 1. `src/chatwoot/models.py`

```python
class ChatwootConfig(BaseModel):
    # ... existing fields ...
    
    # New fields for Evolution API parity
    number: Optional[str] = None
    auto_create: bool = True
    organization: Optional[str] = None
    logo: Optional[str] = None
    message_delete_enabled: bool = True
    mark_read_on_reply: bool = True
```

### 2. `src/chatwoot/webhook_handler.py`

```python
def _convert_markdown_formatting(self, content: str) -> str:
    """Convert Chatwoot markdown to WhatsApp markdown."""
    # Bold: **text** -> *text*
    content = re.sub(r'\*\*([^*]+)\*\*', r'*\1*', content)
    # Italic: *text* -> _text_
    content = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'_\1_', content)
    # Strikethrough: ~~text~~ -> ~text~
    content = re.sub(r'~~([^~]+)~~', r'~\1~', content)
    # Code: `text` -> ```text```
    content = re.sub(r'`([^`]+)`', r'```\1```', content)
    return content

async def _handle_message_updated(self, payload: dict) -> dict:
    """Handle message update (deletion)."""
    if not self._config.message_delete_enabled:
        return {"status": "ignored", "reason": "deletion disabled"}
    
    message_data = payload.get("message", {})
    content = message_data.get("content", "")
    
    if not content:
        # Message was deleted in Chatwoot
        source_id = message_data.get("source_id")
        if source_id and source_id.startswith("WAID:"):
            wa_message_id = source_id.replace("WAID:", "")
            await self._bridge.delete_message(wa_message_id)
            return {"status": "deleted"}
    
    return {"status": "acknowledged"}
```

### 3. `src/api/chatwoot_routes.py`

```python
class ChatwootConfigRequest(BaseModel):
    # ... existing fields ...
    
    # New fields
    number: Optional[str] = None
    auto_create: bool = True
    organization: Optional[str] = None
    logo: Optional[str] = None
    message_delete_enabled: bool = True
    mark_read_on_reply: bool = True
```

---

## Testing Plan

1. **Unit Tests** (`tests/test_chatwoot.py`)
   - [ ] Test markdown conversion (all 4 types)
   - [ ] Test message deletion handling
   - [ ] Test read status marking
   - [ ] Test new config fields

2. **Integration Tests**
   - [ ] Test end-to-end message formatting
   - [ ] Test deletion flow (Chatwoot -> WhatsApp)
   - [ ] Test read status flow

---

## Summary of Changes

| Component | Changes |
|-----------|---------|
| `models.py` | Add 6 new config fields |
| `webhook_handler.py` | Add markdown conversion, message_updated handler, read marking |
| `chatwoot_routes.py` | Add new config fields to request model |
| `docs/chatwoot-integration.md` | Document new features |
| `tests/test_chatwoot.py` | Add tests for new functionality |

---

## Open Questions

1. **Naming Convention**: Keep snake_case (Python style) or add camelCase aliases for Evolution API compatibility?
2. **Backward Compatibility**: Should new config fields have defaults that maintain current behavior?
3. **Bridge Support**: Does the current bridge support `delete_message` and `mark_read`? Need to verify.

---

## References

- [Evolution API Chatwoot Source](https://github.com/EvolutionAPI/evolution-api/tree/main/src/api/integrations/chatbot/chatwoot)
- [Evolution API Chatwoot Service](https://github.com/EvolutionAPI/evolution-api/blob/main/src/api/integrations/chatbot/chatwoot/services/chatwoot.service.ts)
