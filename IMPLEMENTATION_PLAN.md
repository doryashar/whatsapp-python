# Implementation Plan for Code Review Fixes

## Issue 1: Duplicate session state update in `handle_bridge_crash`

**File:** `src/main.py`
**Lines:** 110-114

### Current Code
```python
async def handle_bridge_crash(tenant):
    await tenant_manager.update_session_state(tenant, "connecting")
    success = await _restart_bridge(tenant, "process_crash")
    if success:
        await tenant_manager.update_session_state(tenant, "connecting")
    else:
        await tenant_manager.update_session_state(tenant, "disconnected")
```

### Fix
```python
async def handle_bridge_crash(tenant):
    success = await _restart_bridge(tenant, "process_crash")
    if not success:
        await tenant_manager.update_session_state(tenant, "disconnected")
```

### Steps
1. Remove line 110 (redundant initial state update)
2. Line 114 already sets "connecting" when successful, so remove the duplicate

---

## Issue 2: Edited message formatting bug

**File:** `src/chatwoot/integration.py`
**Lines:** 370-372

### Current Code
```python
if is_edited and content:
    edited_text = event_data.get("edited_text", content)
    content = f"\n\n*Edited:*\n{edited_text}"
```

### Fix
```python
if is_edited and content:
    edited_text = event_data.get("edited_text")
    if edited_text and edited_text != content:
        content = f"{content}\n\n*Edited to:*\n{edited_text}"
```

### Steps
1. Check if `edited_text` exists and differs from current content
2. Append the edited version instead of replacing the original
3. Change format from "*Edited:*" to "*Edited to:*" for clarity

---

## Issue 3: Missing status handling in `find_bot_conversation`

**File:** `src/chatwoot/client.py`
**Lines:** 458-462

### Current Code
```python
async def find_bot_conversation(
    self,
    bot_contact: ChatwootContact,
) -> Optional[ChatwootConversation]:
    return await self.find_conversation_by_contact(bot_contact.id)
```

### Fix
```python
async def find_bot_conversation(
    self,
    bot_contact: ChatwootContact,
) -> Optional[ChatwootConversation]:
    existing = await self.find_conversation_by_contact(bot_contact.id)
    if existing:
        if existing.status in ("resolved", "closed"):
            await self.toggle_conversation_status(existing.id, "open")
        return existing
    return None
```

### Steps
1. Check if existing conversation has resolved/closed status
2. Reopen if needed (matching behavior of `get_or_create_bot_conversation`)
3. Return the conversation

---

## Issue 4: Race condition in conversation cache

**File:** `src/chatwoot/client.py`
**Lines:** 373-382

### Current Code
```python
def _get_cached_conversation(
    self, contact_id: int
) -> Optional[ChatwootConversation]:
    if contact_id in self._conversation_cache:
        conv, timestamp = self._conversation_cache[contact_id]
        if time.time() - timestamp < self.CACHE_TTL:
            return conv
        else:
            del self._conversation_cache[contact_id]
    return None
```

### Fix
Add a lock to prevent concurrent cache access issues:

```python
def __init__(self, config: ChatwootConfig, timeout: int = 30):
    # ... existing init code ...
    self._cache_lock = asyncio.Lock()

async def _get_cached_conversation(
    self, contact_id: int
) -> Optional[ChatwootConversation]:
    async with self._cache_lock:
        if contact_id in self._conversation_cache:
            conv, timestamp = self._conversation_cache[contact_id]
            if time.time() - timestamp < self.CACHE_TTL:
                return conv
            else:
                del self._conversation_cache[contact_id]
    return None

async def _cache_conversation(self, contact_id: int, conv: ChatwootConversation) -> None:
    async with self._cache_lock:
        self._conversation_cache[contact_id] = (conv, time.time())

async def clear_cache(self) -> None:
    async with self._cache_lock:
        self._conversation_cache.clear()
```

### Steps
1. Add `_cache_lock: asyncio.Lock` to `__init__`
2. Make `_get_cached_conversation` async
3. Wrap cache operations in `async with self._cache_lock`
4. Update `_cache_conversation` to be async with lock
5. Update `clear_cache` to be async with lock
6. Update all callers to await these methods

---

## Issue 5: Unused constant

**File:** `src/chatwoot/integration.py`
**Line:** 27

### Current Code
```python
class ChatwootIntegration:
    LOCK_TIMEOUT = 5.0
    LOCK_POLL_DELAY = 0.0
    CONNECTION_NOTIFICATION_COOLDOWN = 300.0
```

### Fix
```python
class ChatwootIntegration:
    LOCK_TIMEOUT = 5.0
    CONNECTION_NOTIFICATION_COOLDOWN = 300.0
```

### Steps
1. Remove line 27 (`LOCK_POLL_DELAY = 0.0`)

---

## Issue 6: Memory leak in restart history

**File:** `src/tenant/__init__.py`

### Current Code
```python
class TenantManager:
    def __init__(...):
        # ...
        self._restart_history: dict[str, list[datetime]] = {}
```

### Fix
Add a cleanup method and call it periodically:

```python
class TenantManager:
    # ... existing constants ...
    RESTART_HISTORY_CLEANUP_INTERVAL = 3600  # 1 hour

    def __init__(self, ...):
        # ... existing init ...
        self._restart_history: dict[str, list[datetime]] = {}
        self._last_cleanup: datetime = datetime.now(UTC)

    def _cleanup_restart_history(self) -> None:
        """Remove entries for deleted tenants and expired timestamps."""
        now = datetime.now(UTC)
        if (now - self._last_cleanup).total_seconds() < self.RESTART_HISTORY_CLEANUP_INTERVAL:
            return
        
        cutoff = now - timedelta(seconds=settings.restart_window_seconds)
        active_tenant_hashes = set(self._tenants.keys())
        
        # Remove deleted tenants
        for tenant_hash in list(self._restart_history.keys()):
            if tenant_hash not in active_tenant_hashes:
                del self._restart_history[tenant_hash]
            else:
                # Filter out old timestamps
                self._restart_history[tenant_hash] = [
                    ts for ts in self._restart_history[tenant_hash] if ts > cutoff
                ]
                # Remove empty entries
                if not self._restart_history[tenant_hash]:
                    del self._restart_history[tenant_hash]
        
        self._last_cleanup = now
        logger.debug(f"Restart history cleanup completed, {len(self._restart_history)} tenants tracked")

    def can_restart(self, tenant: Tenant) -> bool:
        self._cleanup_restart_history()  # Add this line
        # ... rest of existing code ...
```

### Steps
1. Add `RESTART_HISTORY_CLEANUP_INTERVAL` constant
2. Add `_last_cleanup` field to `__init__`
3. Add `_cleanup_restart_history()` method
4. Call cleanup at the start of `can_restart()`

---

## Issue 7: Duplicate WebhookSender instantiation

**File:** `src/webhooks/__init__.py:247-252` and `src/main.py:656-664`

### Current Code

In `src/webhooks/__init__.py`:
```python
webhook_sender = WebhookSender(
    urls=settings.webhook_urls,
    secret=settings.webhook_secret,
    timeout=settings.webhook_timeout,
    max_retries=settings.webhook_retries,
)
```

In `src/main.py`:
```python
sender = WebhookSender(
    urls=tenant.webhook_urls,
    secret=settings.webhook_secret,
    timeout=settings.webhook_timeout,
    max_retries=settings.webhook_retries,
    tenant_hash=tenant.api_key_hash,
    db=tenant_manager._db,
)
asyncio.create_task(sender.send(event_type, params))
```

### Fix
Remove the module-level instance since per-tenant instances are needed:

In `src/webhooks/__init__.py`, remove lines 247-252:
```python
# Remove this unused instance
# webhook_sender = WebhookSender(...)
```

### Steps
1. Delete lines 247-252 in `src/webhooks/__init__.py`
2. The code in `main.py` correctly creates per-tenant instances

---

## Issue 8: Binary key file handling

**File:** `src/tenant/__init__.py`
**Lines:** 140-148

### Current Code
```python
if "keys" in auth_data and isinstance(auth_data["keys"], dict):
    keys_dir = auth_dir / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in auth_data["keys"].items():
        key_file = keys_dir / filename
        with open(key_file, "w") as f:
            f.write(content)
```

### Fix
```python
if "keys" in auth_data and isinstance(auth_data["keys"], dict):
    keys_dir = auth_dir / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in auth_data["keys"].items():
        key_file = keys_dir / filename
        if isinstance(content, bytes):
            with open(key_file, "wb") as f:
                f.write(content)
        else:
            with open(key_file, "w") as f:
                f.write(content)
```

### Steps
1. Add type check for `content`
2. Use binary mode (`"wb"`) for bytes content
3. Keep text mode (`"w"`) for string content

---

## Issue 9: Fire-and-forget asyncio tasks without error handling

**File:** `src/main.py`
**Lines:** Multiple locations (489, 502, 508, 521, 526, etc.)

### Current Code
```python
asyncio.create_task(admin_ws_manager.broadcast(...))
asyncio.create_task(handle_chatwoot_event(tenant, "qr", params))
asyncio.create_task(tenant_manager.update_session_state(...))
# ... and many more
```

### Fix
Create a helper function for safer task creation:

```python
def create_task_with_logging(coro, name: str = "unnamed") -> asyncio.Task:
    """Create an asyncio task with exception logging."""
    task = asyncio.create_task(coro)
    
    def _handle_task_exception(t: asyncio.Task) -> None:
        try:
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(
                    f"Background task '{name}' failed: {exc}",
                    exc_info=exc,
                    extra={"task_name": name},
                )
        except asyncio.CancelledError:
            pass
        except asyncio.InvalidStateError:
            pass
    
    task.add_done_callback(_handle_task_exception)
    return task
```

Update all `asyncio.create_task()` calls:

```python
# Before
asyncio.create_task(admin_ws_manager.broadcast(...))

# After
create_task_with_logging(
    admin_ws_manager.broadcast(...),
    name="broadcast_qr"
)
```

### Steps
1. Add `create_task_with_logging` helper function after line 38
2. Update all ~15 `asyncio.create_task()` calls to use the helper
3. Add meaningful task names for debugging

---

## Issue 10: Missing validation for `send_status` endpoint

**File:** `src/api/routes.py`
**Lines:** 1265-1289

### Current Code
```python
@router.post("/status", response_model=SendStatusResponse)
async def send_status(
    request: SendStatusRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Send status: tenant={tenant.name}, type={request.type}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_status(
            type=request.type,
            content=request.content,
            # ... all params passed through
        )
```

### Fix
Add validation in the model and endpoint:

In `src/models/__init__.py` (or wherever `SendStatusRequest` is defined):
```python
from pydantic import model_validator

class SendStatusRequest(BaseModel):
    type: str
    content: str
    caption: Optional[str] = None
    background_color: Optional[str] = None
    font: Optional[int] = None
    status_jid_list: Optional[list[str]] = None
    all_contacts: bool = False

    @model_validator(mode="after")
    def validate_recipients(self):
        if self.all_contacts and self.status_jid_list:
            raise ValueError(
                "Cannot specify both all_contacts=True and status_jid_list. "
                "Choose one recipient selection method."
            )
        if not self.all_contacts and not self.status_jid_list:
            raise ValueError(
                "Must specify either all_contacts=True or provide status_jid_list."
            )
        return self
```

In `src/api/routes.py`:
```python
@router.post("/status", response_model=SendStatusResponse)
async def send_status(
    request: SendStatusRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Send status: tenant={tenant.name}, type={request.type}")
    
    # Additional validation
    if request.type not in ("text", "image", "video"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status type '{request.type}'. Must be 'text', 'image', or 'video'."
        )
    
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_status(
            type=request.type,
            content=request.content,
            caption=request.caption,
            background_color=request.background_color,
            font=request.font,
            status_jid_list=request.status_jid_list,
            all_contacts=request.all_contacts,
        )
        return SendStatusResponse(
            message_id=result.get("message_id"),
            to=result.get("to"),
            recipient_count=result.get("recipient_count"),
        )
    except BridgeError as e:
        logger.error(f"Send status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### Steps
1. Find `SendStatusRequest` model definition
2. Add `model_validator` for recipient validation
3. Add type validation in the endpoint

---

## Issue 11: Admin session not refreshed on activity

**File:** `src/admin/auth.py`

### Current Code
```python
async def validate_session(
    self,
    session_id: Optional[str],
) -> bool:
    if not session_id:
        return False
    session = await self._db.get_admin_session(session_id)
    return session is not None
```

### Fix
Add session refresh logic:

```python
class AdminSession:
    SESSION_DURATION_HOURS = 24

    async def validate_session(
        self,
        session_id: Optional[str],
    ) -> bool:
        if not session_id:
            return False
        session = await self._db.get_admin_session(session_id)
        if session:
            # Refresh session on activity (sliding expiration)
            await self._refresh_session(session_id)
            return True
        return False

    async def _refresh_session(self, session_id: str) -> None:
        """Extend session expiration on activity."""
        new_expires = datetime.now() + timedelta(hours=self.SESSION_DURATION_HOURS)
        await self._db.update_admin_session_expiry(session_id, new_expires)
```

Add new method to `Database` class in `src/store/database.py`:

```python
async def update_admin_session_expiry(
    self, session_id: str, expires_at: datetime
) -> None:
    """Update admin session expiration time."""
    if self._is_postgres:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE admin_sessions SET expires_at = $1 WHERE id = $2",
                expires_at,
                session_id,
            )
    else:
        await self._pool.execute(
            "UPDATE admin_sessions SET expires_at = ? WHERE id = ?",
            (expires_at.isoformat(), session_id),
        )
        await self._pool.commit()
```

### Steps
1. Add `SESSION_DURATION_HOURS` constant
2. Add `_refresh_session()` method to `AdminSession`
3. Call refresh in `validate_session()` when session is valid
4. Add `update_admin_session_expiry()` method to `Database` class
5. Add PostgreSQL and SQLite implementations

---

## Issue 12: Silent exception swallowing in stderr loop

**File:** `src/bridge/client.py`
**Lines:** 152-164

### Current Code
```python
async def _stderr_loop(self) -> None:
    if not self._process or not self._process.stderr:
        return

    reader = self._process.stderr
    while self._running:
        try:
            line = await reader.readline()
            if not line:
                break
            logger.debug(f"Bridge stderr: {line.decode('utf-8').strip()}")
        except Exception:
            break
```

### Fix
```python
async def _stderr_loop(self) -> None:
    if not self._process or not self._process.stderr:
        return

    reader = self._process.stderr
    while self._running:
        try:
            line = await reader.readline()
            if not line:
                break
            logger.debug(f"Bridge stderr: {line.decode('utf-8').strip()}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Bridge stderr loop error: {e}")
            break
```

### Steps
1. Add explicit `asyncio.CancelledError` handling
2. Log other exceptions at WARNING level before breaking

---

## Issue 13: Duplicate message storage logic

**File:** `src/api/routes.py:1074-1147` and `src/main.py:313-391`

### Current Code
Both files contain similar message storage logic for syncing chat history.

### Fix
Extract to a shared utility function:

Create `src/utils/history.py`:
```python
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..tenant import Tenant
    from ..store.database import Database

from ..store.messages import StoredMessage
from ..telemetry import get_logger

logger = get_logger("whatsapp.history")


async def store_chat_messages(
    tenant: "Tenant",
    chats_data: dict[str, Any],
    db: "Database",
) -> dict[str, int]:
    """
    Store chat messages from WhatsApp history sync.
    
    Returns:
        dict with 'stored', 'duplicates', 'errors' counts
    """
    chats = chats_data.get("chats", [])
    stats = {"stored": 0, "duplicates": 0, "errors": 0}

    for chat in chats:
        chat_jid = chat.get("jid", "")
        is_group = chat.get("is_group", False)
        messages = chat.get("messages", [])

        for msg in messages:
            try:
                msg_id = msg.get("id", "")
                if not msg_id:
                    continue

                from_me = msg.get("from_me", False)
                from_jid = msg.get("from", "")
                text = msg.get("text", "")
                msg_type = msg.get("type", "text")
                timestamp = msg.get("timestamp", 0)
                push_name = msg.get("push_name")

                direction = "outbound" if from_me else "inbound"

                stored_msg = StoredMessage(
                    id=msg_id,
                    from_jid=from_jid,
                    chat_jid=chat_jid,
                    is_group=is_group,
                    push_name=push_name,
                    text=text,
                    msg_type=msg_type,
                    timestamp=timestamp,
                    direction=direction,
                )

                if hasattr(tenant.message_store, "add_with_persist"):
                    db_id = await tenant.message_store.add_with_persist(stored_msg)
                    if db_id:
                        stats["stored"] += 1
                    else:
                        stats["duplicates"] += 1
                else:
                    tenant.message_store.add(stored_msg)
                    stats["stored"] += 1

            except Exception as e:
                stats["errors"] += 1
                logger.error(
                    f"Failed to sync message for tenant {tenant.name}: {e}",
                    exc_info=True,
                )

    return stats
```

Update `src/main.py`:
```python
from .utils.history import store_chat_messages

async def handle_history_sync(tenant: "Tenant", chats_data: dict[str, Any]):
    """Sync chat history from WhatsApp to database"""
    if not tenant_manager._db:
        logger.debug(f"No database available for history sync: tenant={tenant.name}")
        return

    if not tenant.message_store:
        logger.warning(f"No message store for tenant {tenant.name}")
        return

    total_messages = chats_data.get("total_messages", 0)
    logger.info(
        f"Starting history sync for tenant {tenant.name}: "
        f"{len(chats_data.get('chats', []))} chats, {total_messages} messages"
    )

    stats = await store_chat_messages(tenant, chats_data, tenant_manager._db)

    logger.info(
        f"History sync complete for tenant {tenant.name}: "
        f"stored={stats['stored']}, duplicates={stats['duplicates']}, errors={stats['errors']}",
        extra={
            "tenant": tenant.name,
            **stats,
        },
    )
```

Update `src/api/routes.py`:
```python
from ..utils.history import store_chat_messages

@router.post("/sync-history")
async def sync_history(
    tenant: Tenant = Depends(get_tenant),
    limit: int = Query(default=50, ge=1, le=200, description="Messages per chat"),
):
    logger.info(f"Manual history sync: tenant={tenant.name}, limit={limit}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.get_chats_with_messages(limit_per_chat=limit)
        
        chats = result.get("chats", [])
        total_messages = result.get("total_messages", 0)

        stats = {"stored": 0, "duplicates": 0, "errors": 0}
        
        if tenant.message_store and tenant_manager._db:
            stats = await store_chat_messages(tenant, result, tenant_manager._db)

        logger.info(
            f"History sync complete for tenant {tenant.name}: "
            f"stored={stats['stored']}, duplicates={stats['duplicates']}"
        )

        return {
            "status": "synced",
            "chats_count": len(chats),
            "total_messages": total_messages,
            "stored": stats["stored"],
            "duplicates": stats["duplicates"],
            "errors": stats["errors"],
        }
    except BridgeError as e:
        logger.error(f"History sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### Steps
1. Create `src/utils/history.py` with `store_chat_messages` function
2. Export from `src/utils/__init__.py`
3. Refactor `handle_history_sync` in `main.py` to use shared function
4. Refactor `sync_history` endpoint in `routes.py` to use shared function

---

## Issue 14: Missing transaction in SQLite tenant save

**File:** `src/store/database.py`
**Lines:** 377-404

### Current Code
```python
await self._pool.execute(
    """
    INSERT OR REPLACE INTO tenants ...
    """,
    (...),
)
await self._pool.commit()
```

### Fix
Wrap in explicit transaction:

```python
async def save_tenant(
    self,
    api_key_hash: str,
    name: str,
    created_at: datetime,
    webhook_urls: list[str],
) -> None:
    logger.debug(f"Saving tenant: name={name}, hash={api_key_hash[:16]}...")
    if self._is_postgres:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tenants (api_key_hash, name, created_at, webhook_urls)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (api_key_hash) DO UPDATE SET
                    name = EXCLUDED.name,
                    webhook_urls = EXCLUDED.webhook_urls
                """,
                api_key_hash,
                name,
                created_at,
                json.dumps(webhook_urls),
            )
    else:
        try:
            await self._pool.execute("BEGIN IMMEDIATE TRANSACTION")
            await self._pool.execute(
                """
                INSERT OR REPLACE INTO tenants (api_key_hash, name, created_at, webhook_urls, connection_state, self_jid, self_phone, self_name, last_connected_at, last_disconnected_at, has_auth)
                VALUES (?, ?, ?, ?, 
                    COALESCE((SELECT connection_state FROM tenants WHERE api_key_hash = ?), 'disconnected'),
                    COALESCE((SELECT self_jid FROM tenants WHERE api_key_hash = ?), NULL),
                    COALESCE((SELECT self_phone FROM tenants WHERE api_key_hash = ?), NULL),
                    COALESCE((SELECT self_name FROM tenants WHERE api_key_hash = ?), NULL),
                    COALESCE((SELECT last_connected_at FROM tenants WHERE api_key_hash = ?), NULL),
                    COALESCE((SELECT last_disconnected_at FROM tenants WHERE api_key_hash = ?), NULL),
                    COALESCE((SELECT has_auth FROM tenants WHERE api_key_hash = ?), 0)
                )
                """,
                (
                    api_key_hash,
                    name,
                    created_at.isoformat(),
                    json.dumps(webhook_urls),
                    api_key_hash,
                    api_key_hash,
                    api_key_hash,
                    api_key_hash,
                    api_key_hash,
                    api_key_hash,
                    api_key_hash,
                ),
            )
            await self._pool.commit()
        except Exception as e:
            await self._pool.execute("ROLLBACK")
            raise
    logger.debug(f"Tenant saved: {name}")
```

### Steps
1. Add `BEGIN IMMEDIATE TRANSACTION` before the SQLite insert
2. Add try/except with ROLLBACK on error
3. Ensure commit only happens on success

---

# Implementation Order

Recommended order of implementation (by priority and dependencies):

1. **Issue 9** - Fire-and-forget tasks (critical for debugging)
2. **Issue 1** - Duplicate state update (simple fix)
3. **Issue 2** - Edited message formatting (affects user-facing feature)
4. **Issue 5** - Unused constant (quick cleanup)
5. **Issue 12** - Silent stderr exception (improves debugging)
6. **Issue 3** - Bot conversation status (feature consistency)
7. **Issue 8** - Binary key handling (prevents potential data corruption)
8. **Issue 4** - Race condition fix (requires updating callers)
9. **Issue 13** - Duplicate message storage (refactoring)
10. **Issue 6** - Memory leak (adds periodic cleanup)
11. **Issue 7** - Remove unused webhook sender (cleanup)
12. **Issue 10** - Status validation (input validation)
13. **Issue 14** - SQLite transaction (data integrity)
14. **Issue 11** - Session refresh (UX improvement)
