# Connection Health Management Design

## Problem Statement
The app UI shows disconnected state when the mobile WhatsApp app is still connected. This is caused by:
1. False positives from process-only health checks
2. No retry logic for transient failures
3. Lack of actual connection status verification
4. No automatic recovery from bridge process crashes

## Solution Overview

### 1. Query Actual WhatsApp Connection Status

**Current Behavior:**
```python
if not tenant.bridge.is_alive():
    # Immediately mark as disconnected
    await tenant_manager.update_session_state(tenant, "disconnected")
```

**New Behavior:**
```python
if not tenant.bridge.is_alive():
    # Bridge process died - this is a real disconnection
    await handle_bridge_death(tenant)
else:
    # Process is alive, but check actual WhatsApp connection
    actual_status = await tenant.bridge.get_status()
    if actual_status["connected"]:
        # WhatsApp is connected, we're good
        reset_failure_count(tenant)
    else:
        # WhatsApp reports disconnected
        increment_failure_count(tenant)
        if should_mark_offline(tenant):
            await tenant_manager.update_session_state(tenant, "disconnected")
```

**Implementation Details:**
- Call bridge's `get_status()` RPC method
- Bridge returns: `{ connected: bool, jid: string|null, phone: string|null }`
- Only trust actual WhatsApp state, not just process state
- Handle timeout gracefully (count as failure)

### 2. Retry Logic with Configurable Threshold

**Track Health Check Failures Per Tenant:**
```python
class Tenant:
    # ... existing fields ...
    health_check_failures: int = 0
    last_health_check: Optional[datetime] = None

class TenantManager:
    def __init__(self):
        self._health_check_failures: dict[str, int] = {}  # tenant_hash -> count
```

**Configurable Threshold:**
```python
# In config.py
health_check_interval: int = 30  # seconds
health_check_timeout: int = 10   # seconds for get_status call
max_health_failures: int = 3     # failures before marking offline
```

**Health Check Logic:**
```python
async def connection_health_check():
    while True:
        await asyncio.sleep(settings.health_check_interval)
        
        for tenant in tenant_manager.list_tenants():
            if not tenant.bridge or tenant.connection_state != "connected":
                continue
            
            try:
                # Check if process is alive
                if not tenant.bridge.is_alive():
                    logger.warning(f"Bridge process died for {tenant.name}")
                    await handle_bridge_crash(tenant)
                    continue
                
                # Query actual WhatsApp status with timeout
                status = await asyncio.wait_for(
                    tenant.bridge.get_status(),
                    timeout=settings.health_check_timeout
                )
                
                if status.get("connected"):
                    # Success - reset failure count
                    tenant_manager.reset_health_failures(tenant)
                    logger.debug(f"Health check passed for {tenant.name}")
                else:
                    # WhatsApp reports disconnected
                    failures = tenant_manager.increment_health_failures(tenant)
                    logger.warning(
                        f"Health check failed for {tenant.name} "
                        f"({failures}/{settings.max_health_failures})"
                    )
                    
                    if failures >= settings.max_health_failures:
                        logger.error(
                            f"Max failures reached for {tenant.name}, "
                            "marking as disconnected"
                        )
                        await tenant_manager.update_session_state(
                            tenant, "disconnected"
                        )
                        
            except asyncio.TimeoutError:
                failures = tenant_manager.increment_health_failures(tenant)
                logger.warning(
                    f"Health check timeout for {tenant.name} "
                    f"({failures}/{settings.max_health_failures})"
                )
                
            except Exception as e:
                logger.error(f"Health check error for {tenant.name}: {e}")
                failures = tenant_manager.increment_health_failures(tenant)
```

### 3. Process Monitoring and Metrics

**Track Per-Tenant Metrics:**
```python
class TenantMetrics:
    tenant_name: str
    bridge_pid: Optional[int]
    bridge_uptime: Optional[timedelta]
    health_check_failures: int
    last_health_check: Optional[datetime]
    last_successful_health_check: Optional[datetime]
    total_restarts: int
    last_restart_reason: Optional[str]
    process_memory_mb: Optional[float]
    
def get_tenant_metrics(tenant: Tenant) -> TenantMetrics:
    """Collect comprehensive metrics for a tenant"""
    metrics = TenantMetrics(tenant_name=tenant.name)
    
    if tenant.bridge and tenant.bridge._process:
        process = tenant.bridge._process
        metrics.bridge_pid = process.pid
        
        # Process memory usage (Linux/Unix only)
        try:
            import psutil
            p = psutil.Process(process.pid)
            metrics.process_memory_mb = p.memory_info().rss / 1024 / 1024
        except:
            pass
    
    metrics.health_check_failures = tenant_manager.get_health_failures(tenant)
    metrics.last_health_check = tenant.last_health_check
    
    return metrics
```

**Logging Strategy:**
```python
# Health check success
logger.info(
    f"Health check passed for {tenant.name}",
    extra={
        "tenant": tenant.name,
        "pid": tenant.bridge._process.pid if tenant.bridge else None,
        "whatsapp_jid": tenant.self_jid,
        "uptime_seconds": get_uptime(tenant),
    }
)

# Health check failure
logger.warning(
    f"Health check failed for {tenant.name}",
    extra={
        "tenant": tenant.name,
        "failure_count": failures,
        "max_failures": settings.max_health_failures,
        "reason": str(e),
    }
)

# Bridge process death
logger.error(
    f"Bridge process died for {tenant.name}",
    extra={
        "tenant": tenant.name,
        "pid": tenant.bridge._process.pid if tenant.bridge else None,
        "exit_code": tenant.bridge._process.returncode,
        "action": "auto_restarting",
    }
)
```

**Admin Dashboard Endpoint:**
```python
@router.get("/api/admin/tenants/{tenant_name}/metrics")
async def get_tenant_health_metrics(tenant_name: str):
    tenant = tenant_manager.get_tenant_by_name(tenant_name)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    
    return {
        "tenant_name": tenant.name,
        "connection_state": tenant.connection_state,
        "metrics": get_tenant_metrics(tenant),
        "health_history": get_recent_health_checks(tenant, limit=10),
    }
```

### 4. Auto-Restart Mechanism (Detailed)

**Two Levels of Recovery:**

#### Level 1: Bridge Process Crash Recovery
When the Node.js bridge process itself crashes/exits:

```python
async def handle_bridge_crash(tenant: Tenant):
    """
    Handle complete bridge process death.
    This means the Node.js process exited/crashed.
    """
    logger.error(
        f"Bridge process crashed for {tenant.name}",
        extra={
            "tenant": tenant.name,
            "exit_code": tenant.bridge._process.returncode if tenant.bridge else None,
        }
    )
    
    # Step 1: Mark as disconnected temporarily
    await tenant_manager.update_session_state(tenant, "connecting")
    
    # Step 2: Clean up old bridge
    if tenant.bridge:
        try:
            await tenant.bridge.stop()
        except Exception as e:
            logger.debug(f"Error stopping dead bridge: {e}")
    
    # Step 3: Check if tenant has valid credentials
    if not tenant.has_valid_auth():
        logger.warning(
            f"No valid auth for {tenant.name}, cannot auto-restart",
            extra={"tenant": tenant.name}
        )
        await tenant_manager.update_session_state(
            tenant, "disconnected", has_auth=False
        )
        return
    
    # Step 4: Create new bridge instance
    try:
        logger.info(f"Auto-restarting bridge for {tenant.name}")
        
        auth_dir = tenant.get_auth_dir(settings.auth_dir)
        new_bridge = BaileysBridge(
            auth_dir=auth_dir,
            auto_login=True,  # Auto-login using saved credentials
            tenant_id=tenant.api_key_hash,
        )
        
        # Step 5: Register event handler
        if tenant_manager._event_handler:
            new_bridge.on_event(tenant_manager._event_handler)
        
        # Step 6: Start the bridge
        await new_bridge.start()
        
        # Step 7: Update tenant with new bridge
        tenant.bridge = new_bridge
        tenant_manager._track_metrics(tenant, "restart", reason="process_crash")
        
        logger.info(
            f"Bridge auto-restarted successfully for {tenant.name}",
            extra={"tenant": tenant.name, "new_pid": new_bridge._process.pid}
        )
        
        # Step 8: Update state to connecting (will become connected via event)
        await tenant_manager.update_session_state(tenant, "connecting")
        
    except Exception as e:
        logger.error(
            f"Failed to auto-restart bridge for {tenant.name}: {e}",
            extra={"tenant": tenant.name},
            exc_info=True
        )
        await tenant_manager.update_session_state(tenant, "disconnected")
```

#### Level 2: WhatsApp Connection Loss Recovery
When the bridge process is alive but WhatsApp connection dropped:

```python
# The bridge (index.mjs) already has auto-reconnect logic for this:
# - Listens for connection.close events
# - Automatically reconnects for transient errors (lines 271-289)
# - Sends "reconnecting" event to Python
# - Python updates state to "connecting"

# Additional improvement: Force reconnect API
@router.post("/api/admin/tenants/{tenant_name}/reconnect")
async def force_reconnect_tenant(tenant_name: str):
    """Force a reconnection attempt"""
    tenant = tenant_manager.get_tenant_by_name(tenant_name)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    
    if not tenant.bridge or not tenant.bridge.is_alive():
        # Bridge process dead - use Level 1 recovery
        await handle_bridge_crash(tenant)
        return {"status": "reconnecting", "method": "bridge_restart"}
    
    # Bridge alive - request reconnection via RPC
    try:
        await tenant.bridge.call("reconnect", {})
        return {"status": "reconnecting", "method": "whatsapp_reconnect"}
    except Exception as e:
        logger.error(f"Reconnect failed for {tenant.name}: {e}")
        raise HTTPException(500, f"Reconnect failed: {e}")
```

**Configuration:**
```python
# In config.py
auto_restart_bridge: bool = True  # Enable/disable auto-restart
max_restart_attempts: int = 3     # Max restart attempts within restart_window
restart_window_seconds: int = 300 # Window for counting restart attempts
restart_cooldown_seconds: int = 10 # Wait between restart attempts
```

**Restart Rate Limiting:**
```python
class TenantManager:
    def __init__(self):
        self._restart_history: dict[str, list[datetime]] = {}  # tenant_hash -> [timestamps]
    
    def can_restart(self, tenant: Tenant) -> bool:
        """Check if we can restart (rate limiting)"""
        if not settings.auto_restart_bridge:
            return False
        
        history = self._restart_history.get(tenant.api_key_hash, [])
        
        # Remove old entries outside the window
        cutoff = datetime.utcnow() - timedelta(seconds=settings.restart_window_seconds)
        history = [ts for ts in history if ts > cutoff]
        self._restart_history[tenant.api_key_hash] = history
        
        # Check if we've exceeded max attempts
        if len(history) >= settings.max_restart_attempts:
            logger.warning(
                f"Restart rate limit exceeded for {tenant.name}",
                extra={
                    "tenant": tenant.name,
                    "attempts": len(history),
                    "window_seconds": settings.restart_window_seconds,
                }
            )
            return False
        
        return True
    
    def record_restart(self, tenant: Tenant):
        """Record a restart attempt"""
        if tenant.api_key_hash not in self._restart_history:
            self._restart_history[tenant.api_key_hash] = []
        self._restart_history[tenant.api_key_hash].append(datetime.utcnow())
```

## Implementation Plan

1. **Add health check tracking to Tenant model**
   - Add `health_check_failures` field
   - Add `last_health_check` field

2. **Implement get_status in bridge**
   - Already exists in index.mjs (returns connection state)
   - Ensure it returns proper format

3. **Update connection_health_check**
   - Query actual status
   - Implement retry logic
   - Call handle_bridge_crash on process death

4. **Implement handle_bridge_crash**
   - Clean up old bridge
   - Create new bridge with auto_login
   - Add rate limiting
   - Update tenant state

5. **Add process monitoring**
   - Track metrics
   - Add admin endpoints
   - Improve logging

6. **Add tests**
   - Test health check logic
   - Test auto-restart
   - Test rate limiting

## Benefits

1. **No false positives**: Actual WhatsApp status is checked
2. **Resilient to transient failures**: Multiple attempts before marking offline
3. **Self-healing**: Automatically recovers from process crashes
4. **Observable**: Detailed metrics and logging
5. **Configurable**: Thresholds can be tuned per deployment
