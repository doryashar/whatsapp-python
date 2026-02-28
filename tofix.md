# Bugs & Issues to Fix

## Status: ALL ISSUES FIXED

All identified bugs and issues have been resolved. See details below.

---

## CRITICAL BUGS (FIXED)

### 1. ~~Wrong `shouldIgnoreJid` Logic (blocks all DMs)~~
**File:** `bridge/index.mjs:174-179`
**Status:** FIXED

```javascript
// BEFORE (WRONG)
shouldIgnoreJid: (jid) => {
  return !(isGroup || isBroadcast || isStatus);  // Returns true for DMs!
}

// AFTER (FIXED)
shouldIgnoreJid: (jid) => {
  return isBroadcast || isStatus;
}
```

---

### 2. ~~Flawed JSON-RPC Response Detection~~
**File:** `src/bridge/protocol.py:33-36`
**Status:** FIXED

```python
# BEFORE (WRONG)
if "id" in parsed or "result" in parsed or "error" in parsed:

# AFTER (FIXED)
if "id" in parsed and ("result" in parsed or "error" in parsed):
```

---

## MEDIUM BUGS (FIXED)

### 3. ~~Deprecated asyncio API~~
**File:** `src/bridge/client.py:162`
**Status:** FIXED

```python
# BEFORE (DEPRECATED)
future: asyncio.Future = asyncio.get_event_loop().create_future()

# AFTER (FIXED)
future: asyncio.Future = asyncio.get_running_loop().create_future()
```

---

### 4. ~~Hardcoded `fromMe: false` in Reactions~~
**File:** `bridge/index.mjs:425-430`
**Status:** FIXED

Now supports optional `from_me` parameter for reactions to own messages.

---

### 5. ~~Incomplete Status Broadcast Check~~
**File:** `bridge/index.mjs:301`
**Status:** FIXED

```javascript
// BEFORE
if (remoteJid.endsWith("@status") || ...)

// AFTER
if (remoteJid === "status@broadcast" || ...)
```

---

## TYPE ERRORS (FIXED)

### 11. ~~Two Classes Named `InboundMessage`~~
**Files:** `src/store/messages.py` and `src/models/message.py`
**Status:** FIXED

- Renamed `src/store/messages.py` class to `StoredMessage`
- Updated `src/store/__init__.py` exports
- Updated `src/main.py` to use `StoredMessage`
- Updated test imports in `tests/test_tenant.py`

---

### 12. ~~Type Checker: `result` and `error` May Be `None`~~
**File:** `tests/test_bridge.py:28,36`
**Status:** FIXED

Added null checks before accessing `result.result` and `result.error`.

---

### 13. ~~Type Checker: Handler Result May Not Be Awaitable~~
**File:** `src/bridge/client.py:150`
**Status:** FIXED

Added `# type: ignore[arg-type]` comment for type checker.

---

## MISSING FEATURES (ADDED)

### 6. ~~No Poll Support~~
**Status:** ADDED

Added `send_poll` method to bridge and `/api/poll` endpoint.

---

### 7. ~~No Typing Indicator~~
**Status:** ADDED

Added `send_typing` method to bridge and `/api/typing` endpoint.

---

### 9. ~~No Auth Age/Exists/Self ID API~~
**Status:** ADDED

Added new endpoints:
- `/api/auth/exists` - Check if credentials exist
- `/api/auth/age` - Get credential age in milliseconds
- `/api/auth/self` - Get self identity (jid, e164, name)

---

## Summary

| Issue | Severity | Status |
|-------|----------|--------|
| #1 shouldIgnoreJid | CRITICAL | FIXED |
| #2 JSON-RPC decode | HIGH | FIXED |
| #3 Deprecated asyncio | MEDIUM | FIXED |
| #4 Reaction fromMe | MEDIUM | FIXED |
| #5 Status broadcast | LOW | FIXED |
| #6 Poll support | FEATURE | ADDED |
| #7 Typing indicator | FEATURE | ADDED |
| #9 Auth API | FEATURE | ADDED |
| #11 Duplicate classes | HIGH | FIXED |
| #12 Test type checks | LOW | FIXED |
| #13 Type annotations | LOW | FIXED |

All 38 tests pass after fixes.
