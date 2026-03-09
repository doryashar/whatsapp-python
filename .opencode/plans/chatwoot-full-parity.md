# Chatwoot Full Parity Implementation Plan

## Goal
Achieve complete feature parity between whatsapp-python and EvolutionAPI's Chatwoot integration.

## Reference
- EvolutionAPI Chatwoot Service: https://github.com/EvolutionAPI/evolution-api/tree/main/src/api/integrations/chatbot/chatwoot
- Local implementation: `src/chatwoot/`

---

## Current State Summary

### Already Implemented ✅
- All config fields (enabled, url, token, account_id, inbox_id, etc.)
- Evolution parity fields (number, auto_create, organization, logo, message_delete_enabled, mark_read_on_reply)
- Bot commands (init, disconnect, status, clearcache)
- QR code delivery to bot contact
- Message signing with delimiter
- Chatwoot→WhatsApp markdown conversion
- Message deletion support
- Read status sync
- Profile picture sync
- Reply/quoted message support
- Brazilian number merge
- Ignore JIDs filter
- Webhook signature verification
- Message history sync

### Missing Features to Implement

---

## Phase 1: Group Message Support (HIGH PRIORITY)

### 1.1 Enable Group Message Handling
**File:** `src/chatwoot/integration.py`

Current behavior: Groups skipped at line 85-87
```python
if is_group:
    logger.debug(f"Skipping group message for tenant {self._tenant.name}")
    return False
```

**Changes:**
1. Remove the early return for groups
2. Extract group JID and participant info
3. Create group contact with "(GROUP)" suffix
4. Create participant contacts when needed
5. Format messages with participant name

**Implementation:**
```python
async def handle_message(self, event_data: dict, is_outgoing: bool = False) -> bool:
    # ... existing code ...
    
    if is_group:
        return await self._handle_group_message(event_data, is_outgoing)
    else:
        return await self._handle_direct_message(event_data, is_outgoing)

async def _handle_group_message(self, event_data: dict, is_outgoing: bool) -> bool:
    group_jid = event_data.get("chat_jid", "")
    participant_jid = event_data.get("participant", "") or event_data.get("from", "")
    
    # Create/update group contact
    group_name = event_data.get("group_name", group_jid.split("@")[0])
    group_contact = await self._client.find_or_create_contact(
        phone_number=group_jid.split("@")[0],
        name=f"{group_name} (GROUP)",
        identifier=group_jid,
    )
    
    # Format message with participant
    participant_phone = self._extract_phone(participant_jid)
    participant_name = event_data.get("push_name", participant_phone)
    
    text = event_data.get("text", "")
    formatted_text = f"[{participant_name}]: {text}" if text else None
    
    # Create message with formatted content
    # ...
```

### 1.2 Add Group-Specific Fields to Config
**File:** `src/chatwoot/models.py`

```python
class ChatwootConfig(BaseModel):
    # ... existing fields ...
    group_messages_enabled: bool = True  # Enable/disable group handling
```

### 1.3 Tests
**File:** `tests/test_chatwoot.py`

- Test group message creates group contact with "(GROUP)" suffix
- Test participant name included in message
- Test group JID used as identifier
- Test group_messages_enabled flag

---

## Phase 2: WhatsApp→Chatwoot Markdown Conversion (MEDIUM PRIORITY)

### 2.1 Add Reverse Markdown Conversion
**File:** `src/chatwoot/integration.py`

EvolutionAPI converts WhatsApp formatting to Chatwoot:
- WhatsApp `*text*` (bold) → Chatwoot `**text**`
- WhatsApp `_text_` (italic) → Chatwoot `*text*`
- WhatsApp `~text~` (strikethrough) → Chatwoot `~~text~~`
- WhatsApp ```text``` (code) → Chatwoot `text`

**Implementation:**
```python
def _convert_wa_to_cw_markdown(self, content: str) -> str:
    """Convert WhatsApp markdown to Chatwoot markdown."""
    # Code: ```text``` -> `text`
    content = re.sub(r'```([^`]+)```', r'`\1`', content)
    # Strikethrough: ~text~ -> ~~text~~
    content = re.sub(r'(?<!~)~([^~]+)~(?!~)', r'~~\1~~', content)
    # Italic: _text_ -> *text*
    content = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'*\1*', content)
    # Bold: *text* -> **text**
    content = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'**\1**', content)
    return content
```

### 2.2 Apply in handle_message
```python
async def handle_message(self, event_data: dict, is_outgoing: bool = False) -> bool:
    # ... existing code ...
    content = self._convert_wa_to_cw_markdown(text) if text else None
```

### 2.3 Tests
- Test WhatsApp bold → Chatwoot bold
- Test WhatsApp italic → Chatwoot italic
- Test WhatsApp strikethrough → Chatwoot strikethrough
- Test WhatsApp code → Chatwoot code
- Test mixed formatting

---

## Phase 3: Message Edit Handling (MEDIUM PRIORITY)

### 3.1 Handle Edited Messages from WhatsApp
**File:** `src/chatwoot/integration.py`

EvolutionAPI creates a new message with "Edited:" prefix when WhatsApp message is edited.

**Implementation:**
```python
async def handle_message(self, event_data: dict, is_outgoing: bool = False) -> bool:
    # ... existing code ...
    
    is_edited = event_data.get("is_edited", False)
    if is_edited:
        edited_text = event_data.get("edited_text", text)
        content = f"Edited: {edited_text}"
```

### 3.2 Tests
- Test edited message has "Edited:" prefix

---

## Phase 4: Additional Message Types (MEDIUM PRIORITY)

### 4.1 Location Messages
**File:** `src/chatwoot/integration.py`

```python
async def _prepare_location_content(self, event_data: dict) -> str:
    lat = event_data.get("latitude")
    lon = event_data.get("longitude")
    name = event_data.get("location_name", "")
    address = event_data.get("location_address", "")
    
    if lat and lon:
        parts = [f"📍 Location: https://maps.google.com/?q={lat},{lon}"]
        if name:
            parts.append(f"Name: {name}")
        if address:
            parts.append(f"Address: {address}")
        return "\n".join(parts)
    return "[Location]"
```

### 4.2 Contact/VCard Messages
```python
async def _prepare_contact_content(self, event_data: dict) -> str:
    contacts = event_data.get("contacts", [])
    if not contacts:
        return "[Contact]"
    
    parts = ["📱 Contact(s):"]
    for contact in contacts:
        name = contact.get("name", "Unknown")
        phones = contact.get("phones", [])
        for phone in phones:
            parts.append(f"  {name}: {phone}")
    return "\n".join(parts)
```

### 4.3 List/Interactive Messages
```python
async def _prepare_list_content(self, event_data: dict) -> str:
    title = event_data.get("list_title", "")
    description = event_data.get("list_description", "")
    button_text = event_data.get("button_text", "")
    
    parts = [f"📋 {title}" if title else "📋 List Message"]
    if description:
        parts.append(description)
    if button_text:
        parts.append(f"Button: {button_text}")
    return "\n".join(parts)
```

### 4.4 View Once Messages
```python
async def _prepare_view_once_content(self, event_data: dict) -> str:
    media_type = event_data.get("media_type", "media")
    return f"🔒 View Once {media_type.title()} (cannot be displayed)"
```

### 4.5 Tests
- Test location message formatting
- Test contact message formatting
- Test list message formatting
- Test view once message handling

---

## Phase 5: Conversation Caching with TTL (LOW PRIORITY)

### 5.1 Add TTL-Based Cache
**File:** `src/chatwoot/client.py`

```python
import time
from typing import Optional, Tuple

class ChatwootClient:
    CACHE_TTL = 1800  # 30 minutes
    
    def __init__(self, config: ChatwootConfig, timeout: int = 30):
        # ... existing code ...
        self._conversation_cache: dict[int, Tuple[ChatwootConversation, float]] = {}
    
    def _get_cached_conversation(self, contact_id: int) -> Optional[ChatwootConversation]:
        if contact_id in self._conversation_cache:
            conv, timestamp = self._conversation_cache[contact_id]
            if time.time() - timestamp < self.CACHE_TTL:
                return conv
            else:
                del self._conversation_cache[contact_id]
        return None
    
    def _cache_conversation(self, contact_id: int, conv: ChatwootConversation) -> None:
        self._conversation_cache[contact_id] = (conv, time.time())
```

### 5.2 Tests
- Test cache hit within TTL
- Test cache miss after TTL
- Test cache invalidation

---

## Phase 6: Error Private Notes (LOW PRIORITY)

### 6.1 Create Private Note on Send Failure
**File:** `src/chatwoot/webhook_handler.py`

```python
async def _handle_message_created(self, payload: dict) -> dict:
    # ... existing code ...
    
    try:
        # ... send message logic ...
    except Exception as e:
        logger.error(f"Failed to send message from Chatwoot webhook: {e}")
        
        # Create private note about failure
        if self._chatwoot_client and conversation_data:
            conversation_id = conversation_data.get("id")
            if conversation_id:
                try:
                    await self._chatwoot_client.create_message(
                        conversation_id=conversation_id,
                        content=f"⚠️ Failed to send to WhatsApp: {str(e)}",
                        private=True,
                    )
                except Exception:
                    pass
        
        return {"status": "error", "reason": str(e)}
```

### 6.2 Tests
- Test private note created on send failure
- Test private note not created on success

---

## Phase 7: Direct DB Connection for Bulk Imports (LOW PRIORITY)

### 7.1 Add Optional Direct DB Support
**File:** `src/chatwoot/sync.py`

**Config:**
```python
class ChatwootConfig(BaseModel):
    # ... existing fields ...
    import_db_uri: Optional[str] = None  # Direct Chatwoot DB connection
```

**Implementation:**
```python
import asyncpg

class ChatwootSyncService:
    async def _bulk_insert_contacts(self, contacts: list[dict]) -> int:
        db = await self._get_chatwoot_db()
        if not db:
            return 0
        # Direct INSERT into Chatwoot's contacts table
```

### 7.2 Tests
- Test bulk contact import with DB
- Test fallback to API when DB not available

---

## Implementation Order

### Week 1: Core Features
1. Phase 1: Group Message Support
2. Phase 2: WA→CW Markdown Conversion
3. Phase 3: Message Edit Handling

### Week 2: Enhanced Features
4. Phase 4: Additional Message Types
5. Phase 5: Conversation Caching with TTL
6. Phase 6: Error Private Notes

### Week 3: Advanced Features
7. Phase 7: Direct DB Connection for Bulk Imports

---

## Testing Strategy

```bash
# Run all Chatwoot tests
pytest tests/test_chatwoot*.py -v

# Run with coverage
pytest tests/test_chatwoot*.py --cov=src/chatwoot -v
```

---

## Success Criteria

- [ ] All tests passing
- [ ] Group messages working end-to-end
- [ ] Markdown conversion working bidirectionally
- [ ] All message types supported
- [ ] Error handling with private notes
- [ ] Documentation updated
- [ ] Parity checklist updated
