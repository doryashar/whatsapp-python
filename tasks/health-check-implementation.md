# Connection Health Management - Implementation Summary

## Problem Solved

The app UI was showing disconnected state for users when the mobile WhatsApp app was still connected. This was caused by:
1. Health checks only verified if the bridge process was alive, not actual WhatsApp connection
2. No retry logic - single failure immediately marked tenant as disconnected
3. No automatic recovery from bridge process crashes
4. Lack of visibility into health check failures and restart attempts

## Solution Implemented

### 1. Query Actual WhatsApp Connection Status ✅

**Before:**
```python
if not tenant.bridge.is_alive():
    # Immediately mark as disconnected
    await tenant_manager.update_session_state(tenant, "disconnected")
```

**After:**
```python
if not tenant.bridge.is_alive():
    # Bridge process died - handle with auto-restart
    await handle_bridge_crash(tenant)
else:
    # Process alive, check actual WhatsApp connection
    status = await asyncio.wait_for(
        tenant.bridge.get_status(),
        timeout=settings.health_check_timeout_seconds
    )
    if status.get("connected"):
        tenant_manager.reset_health_failures(tenant)
    else:
        failures = tenant_manager.increment_health_failures(tenant)
        if failures >= settings.max_health_check_failures:
            await tenant_manager.update_session_state(tenant, "disconnected")
```

**Implementation Details:**
- Calls bridge's `get_status()` RPC method
- Handles timeouts gracefully (counts as failure)
- Only trusts actual WhatsApp state, not just process state

### 2. Retry Logic with Configurable Threshold ✅

**New Configuration:**
```python
health_check_interval_seconds: int = 30    # How often to check
health_check_timeout_seconds: int = 10     # Timeout for status query
max_health_check_failures: int = 3         # Failures before marking offline
```

**Tracking Per Tenant:**
```python
class Tenant:
    health_check_failures: int = 0
    last_health_check: Optional[datetime] = None
    last_successful_health_check: Optional[datetime] = None
```

**TenantManager Methods:**
- `reset_health_failures(tenant)` - Reset on successful check
- `increment_health_failures(tenant)` - Increment on failure

### 3. Process Monitoring and Metrics ✅

**New Tenant Fields:**
```python
class Tenant:
    total_restarts: int = 0
    last_restart_at: Optional[datetime] = None
    last_restart_reason: Optional[str] = None
```

**Enhanced Logging:**
- Health check success with PID, JID, and uptime
- Health check failures with count and threshold
- Bridge crashes with exit code
- Auto-restart attempts with new PID
- Rate limit exceeded warnings

### 4. Auto-Restart Mechanism ✅

**Level 1: Bridge Process Crash Recovery**
When Node.js bridge process crashes/exits:

```python
async def handle_bridge_crash(tenant: Tenant):
    # 1. Mark as connecting (temporary state)
    await tenant_manager.update_session_state(tenant, "connecting")
    
    # 2. Stop old bridge
    await tenant.bridge.stop()
    
    # 3. Check if can restart (has auth + rate limit)
    if not tenant.has_valid_auth():
        # No credentials - mark disconnected
        return
    
    if not tenant_manager.can_restart(tenant):
        # Rate limit exceeded - mark disconnected
        return
    
    # 4. Create new bridge with auto_login=True
    new_bridge = BaileysBridge(
        auth_dir=auth_dir,
        auto_login=True,
        tenant_id=tenant.api_key_hash,
    )
    
    # 5. Start new bridge
    await new_bridge.start()
    
    # 6. Update tenant with new bridge
    tenant.bridge = new_bridge
    tenant_manager.record_restart(tenant, "process_crash")
    
    # 7. Will become connected via event
```

**Level 2: WhatsApp Connection Loss**
When bridge is alive but WhatsApp disconnected:
- Bridge already has auto-reconnect logic (index.mjs lines 271-289)
- Sends "reconnecting" event to Python
- Python updates state to "connecting"

**Rate Limiting:**
```python
auto_restart_bridge: bool = True           # Enable/disable
max_restart_attempts: int = 3              # Max attempts in window
restart_window_seconds: int = 300          # 5 minute window
restart_cooldown_seconds: int = 10         # Wait between attempts
```

## Files Modified

1. **src/config.py** - Added health check and restart configuration
2. **src/tenant/__init__.py** - Added health tracking fields and methods to Tenant and TenantManager
3. **src/main.py** - Completely rewrote `connection_health_check()` and added `handle_bridge_crash()`
4. **tests/test_health_check.py** - Added 20 comprehensive tests
5. **docs/connection-health-design.md** - Detailed design document
6. **.env.example** - Added all new configuration options with documentation
7. **README.md** - Updated environment variables table with new settings

## Tests Added

Created `tests/test_health_check.py` with 20 tests covering:
- Health check failure tracking
- Restart rate limiting
- Bridge health check success/failure/timeout
- Auto-restart with/without auth
- Auto-restart rate limiting
- Tenant metrics
- Full integration scenarios

**Test Results:**
```
20 passed, 55 warnings in 20.59s
```

## Configuration

All settings are configurable via environment variables:

```bash
# Health Check Settings
HEALTH_CHECK_INTERVAL_SECONDS=30    # How often to check connections
HEALTH_CHECK_TIMEOUT_SECONDS=10     # Timeout for get_status() calls
MAX_HEALTH_CHECK_FAILURES=3         # Failures before marking offline

# Auto-Restart Settings
AUTO_RESTART_BRIDGE=true            # Enable/disable auto-restart
MAX_RESTART_ATTEMPTS=3              # Max restarts in window
RESTART_WINDOW_SECONDS=300          # Time window for rate limiting
RESTART_COOLDOWN_SECONDS=10         # Wait between restarts
```

## Benefits

1. **No False Positives**: Checks actual WhatsApp connection, not just process state
2. **Resilient**: Tolerates transient failures (3 failures required)
3. **Self-Healing**: Automatically recovers from process crashes
4. **Observable**: Detailed logging and metrics for debugging
5. **Configurable**: All thresholds can be tuned per deployment
6. **Safe**: Rate limiting prevents restart loops
7. **Tested**: 20 comprehensive tests ensure reliability

## Monitoring

Track these metrics in production:

```python
# Per tenant
tenant.health_check_failures      # Current failure count
tenant.total_restarts             # Total restart attempts
tenant.last_health_check          # Last check timestamp
tenant.last_restart_reason        # Why last restart occurred

# Check for issues
if tenant.health_check_failures > 0:
    # Warning - health checks failing
    
if tenant.total_restarts > 0 in last hour:
    # Critical - bridge keeps crashing
```

## Next Steps

Optional enhancements:
1. Add admin API endpoint to expose tenant health metrics
2. Add Prometheus metrics for monitoring
3. Add alerts when restart rate limits are hit
4. Add webhook notifications for health events
5. Add dashboard visualization for health trends

## Backwards Compatibility

✅ All changes are backwards compatible:
- New fields have default values
- New configuration uses defaults if not set
- Existing functionality unchanged
- Tests pass for all features
