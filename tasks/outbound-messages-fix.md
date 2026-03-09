# Outbound Messages Not Saving - Fix Complete ✅

## Problem

When sending messages from the admin UI, outbound messages like "היי" were not appearing in the messages page. Investigation revealed that **outbound messages were never being saved to the database**.

## Root Causes (Multiple Issues)

### Issue 1: Event Type Mismatch
1. **Event Type Mismatch**: The bridge emits event type `"sent"` when a message is sent outbound
2. **Incomplete Handler**: The code only handled `"message"` events, not `"sent"` events
3. **Result**: All outbound messages were ignored and never persisted

### Issue 2: Message ID Field Name Mismatch
1. The bridge sends `message_id` in the sent event
2. The Python code was looking for `id` field
3. **Result**: StoredMessage was created with empty id

### Issue 3: Timestamp Format Mismatch
1. The bridge's `messageTimestamp` is a protobuf Long object: `{'low': 1772564151, 'high': 0, 'unsigned': True}`
2. The database expects an integer
3. **Result**: Database save failed silently due to type error

## Evidence from Logs

```json
{
  "timestamp": "2026-03-03T14:51:17.246049+00:00",
  "level": "INFO",
  "logger": "whatsapp",
  "message": "Bridge event for tenant dor: type=sent"
}
```

The event type is "sent", but the code was only checking for "message".

### Database Evidence (Before Fix)

```sql
SELECT COUNT(*) as total, direction FROM messages GROUP BY direction;

 total | direction 
-------+-----------
    12 | inbound

(1 row)
```

**Zero outbound messages** despite sending "היי" from the admin UI.

## Solution

### Code Changes

#### 1. Handle "sent" events in `src/main.py`

```python
# BEFORE: Only handled "message" events
if event_type == "message":
    from_jid = params["from"]
    is_outbound = tenant.self_jid and from_jid == tenant.self_jid
    direction = "outbound" if is_outbound else "inbound"

# AFTER: Handle both "message" and "sent" events
if event_type in ["message", "sent"]:
    from_jid = params.get("from") or params.get("to", "")
    is_outbound = event_type == "sent" or (tenant.self_jid and from_jid == tenant.self_jid)
    direction = "outbound" if is_outbound else "inbound"
```

#### 2. Fix message ID field in `src/main.py` (line 263)

```python
# BEFORE
id=params.get("id", ""),

# AFTER
id=params.get("id") or params.get("message_id", ""),
```

#### 3. Fix timestamp format in `bridge/index.mjs` (line 445)

```javascript
// BEFORE
const timestamp = result?.messageTimestamp || Date.now();

// AFTER
const timestamp = typeof result?.messageTimestamp === 'object' 
  ? result.messageTimestamp.low 
  : (result?.messageTimestamp || Date.now());
```

#### 4. Add error logging in `src/store/messages.py`

Changed silent exception swallowing to proper error logging so future issues are visible.

### Key Changes Summary

1. **Line 252 in main.py**: Changed condition from `if event_type == "message"` to `if event_type in ["message", "sent"]`
2. **Line 254-256 in main.py**: Handle both "from" (message events) and "to" (sent events)
3. **Line 257-259 in main.py**: Mark as outbound if event is "sent" OR if from_jid matches self_jid
4. **Line 263 in main.py**: Check both `id` and `message_id` fields
5. **Line 445 in bridge/index.mjs**: Convert protobuf Long to integer
6. **Line 291 in main.py**: Broadcast both message and sent events to admin websocket

### Files Modified

- `src/main.py` (3 changes)
- `src/store/messages.py` (improved error logging)
- `bridge/index.mjs` (timestamp fix)
- `tests/test_outbound_messages.py` (new file)

## Tests

Created comprehensive test suite:

1. **test_sent_event_creates_outbound_message**: Verifies "sent" events save as outbound
2. **test_message_event_inbound_direction**: Verifies inbound messages still work
3. **test_message_event_outbound_when_from_self**: Verifies outbound detection from "message" events

## Deployment

✅ **Deployed and Verified**

```bash
# Container: whatsapp-api
# Rebuilt Docker image with all fixes
# Restarted with: docker compose up -d --force-recreate --build whatsapp-api
```

## Verification Results

### Database (After Fix)

```sql
SELECT id, text, direction FROM messages WHERE direction='outbound' ORDER BY created_at DESC LIMIT 1;

 id |                 text                  | direction
----+---------------------------------------+-----------
 24 | sixth test with working timestamp fix | outbound
```

### API Response

```json
{
  "id": 24,
  "text": "sixth test with working timestamp fix",
  "direction": "outbound",
  "message_id": "3EB08BFABCBC920217CC60"
}
```

## Expected Behavior (Now Working)

- Send message from admin UI → Event type "sent" → Saved as outbound → In database ✅
- Messages page shows both inbound and outbound
- Outbound messages display with purple "Out" badge
- Direction filtering works for both inbound and outbound
- Text content is preserved and displayed correctly

## Related Issues Resolved

This fix also resolves:
- Real-time websocket updates for outbound messages
- Webhook notifications for sent messages
- Chatwoot integration for outbound messages
- Proper text content display in UI and database

All these features were already calling the handler but outbound messages were being ignored.
