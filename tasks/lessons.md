# Lessons Learned

## Silent Exception Handling

**Date**: 2026-03-03  
**Issue**: Outbound messages failing to save with no error visibility  
**File**: `src/store/messages.py:85-86`

### Problem
The `add_with_persist` method had a bare `except Exception: pass` that silently swallowed all database errors. This made debugging extremely difficult because:
- No error logs were generated
- The message appeared to be stored in memory successfully
- Only database persistence failed silently

### Solution
Replace silent exception handling with proper error logging:
```python
except Exception as e:
    logger.error(f"Failed to persist message to DB: {e}", exc_info=True)
```

### Lesson
**Never use bare `except: pass` or `except Exception: pass`** - always log the error. Silent failures are a debugging nightmare. Even if you want to continue execution, log the error so it's visible during troubleshooting.

---

## Docker Layer Caching with Multi-Stage Builds

**Date**: 2026-03-03  
**Issue**: Bridge code changes not appearing in running container  
**File**: `Dockerfile`

### Problem
After modifying `bridge/index.mjs`, running `docker build -t whatsapp-api:latest .` followed by `docker compose restart` didn't apply the changes. The container still had old code.

### Root Cause
1. Docker compose was using a cached image from a previous build
2. Multi-stage builds with `COPY --from=bridge-builder` require complete rebuild
3. Simple restart doesn't reload the image

### Solution
Force complete rebuild and container recreation:
```bash
docker compose up -d --force-recreate --build whatsapp-api
```

Or with manual steps:
```bash
docker build --no-cache -t whatsapp-api:latest .
docker compose down whatsapp-api
docker compose up -d whatsapp-api
```

### Lesson
When dealing with multi-stage Docker builds and code changes, always:
1. Use `--no-cache` to ensure fresh build, OR
2. Use `--force-recreate --build` with docker compose
3. Verify the changes are actually in the container with `docker exec`

---

## Protobuf Long Objects in JavaScript/Python Bridge

**Date**: 2026-03-03  
**Issue**: Timestamp field causing database errors  
**Files**: `bridge/index.mjs:445`, `src/main.py:263`

### Problem
The WhatsApp library returns timestamps as protobuf Long objects:
```javascript
{ low: 1772564151, high: 0, unsigned: true }
```

This gets serialized as-is when passed from Node.js bridge to Python, causing type errors:
```
TypeError: 'dict' object cannot be interpreted as an integer
```

### Solution
Convert Long objects to integers in the bridge before sending to Python:
```javascript
const timestamp = typeof result?.messageTimestamp === 'object' 
  ? result.messageTimestamp.low 
  : (result?.messageTimestamp || Date.now());
```

### Lesson
When passing data between Node.js and Python (or any cross-language boundary):
1. Be aware of library-specific types (like protobuf Long)
2. Serialize to primitive types (number, string, boolean) at the boundary
3. Don't assume all "numbers" are actual JavaScript/Python numbers

---

## Field Name Inconsistencies Between Event Types

**Date**: 2026-03-03  
**Issue**: Outbound messages saved with empty ID  
**File**: `src/main.py:263`

### Problem
Different event types used different field names:
- "message" events have `id` field
- "sent" events have `message_id` field

The code only checked for `id`, so sent events created messages with empty IDs.

### Solution
Check both fields with fallback:
```python
id=params.get("id") or params.get("message_id", ""),
```

### Lesson
When handling multiple event types or API responses:
1. Document field name differences explicitly
2. Use defensive coding with fallbacks for optional/alternative fields
3. Add logging to see actual field names during development

---

## Debug Logging Strategy

**Date**: 2026-03-03  
**Issue**: Hard to debug issues without visibility  
**Pattern**: Used throughout debugging session

### What Worked Well
Adding temporary INFO-level logs at critical points:
```python
logger.info(f"Storing message: id={msg.id}, direction={direction}, text={msg.text[:50]}")
logger.info(f"Persisting message to DB: id={msg.id}, text={msg.text[:50]}")
```

This immediately revealed:
- What data was being received
- Where the flow was breaking
- What actual values were in the fields

### Lesson
During debugging complex flows:
1. Add INFO-level (not DEBUG) logs temporarily to see what's happening
2. Log at key transition points (event receipt, object creation, database save)
3. Remove or downgrade to DEBUG after fixing the issue
4. Always include key identifiers (id, direction, truncated content) in logs
