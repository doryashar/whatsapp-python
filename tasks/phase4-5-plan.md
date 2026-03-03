# Phase 4 & 5 Implementation Plan

## Overview

This plan outlines the implementation of real-time WebSocket updates (Phase 4) and enhanced features (Phase 5) for the WhatsApp API admin dashboard.

## Current Status

✅ Phase 1-3 Complete:
- Multi-tenant support with PostgreSQL
- Webhook and WebSocket event delivery
- OpenTelemetry observability
- Rate limiting with IP blocking
- Admin dashboard with HTMX-based UI

## Phase 4: Real-time WebSocket Updates

### Architecture: Separate Admin WebSocket

**Decision:** Create dedicated `/admin/ws` endpoint with `AdminConnectionManager`

### Components

#### 1. Backend Infrastructure (`src/admin/websocket.py`)

**AdminConnectionManager Class:**
```python
class AdminConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket, session_id: str)
    def disconnect(self, websocket: WebSocket)
    async def broadcast(self, event_type: str, data: dict)
    async def broadcast_to_all(self, message: dict)
```

**WebSocket Endpoint (`/admin/ws`):**
- Validates admin session cookie
- Handles connection lifecycle
- Implements heartbeat (ping/pong every 30s)
- Auto-reconnect on disconnect

**Event Types:**
- `tenant_state_changed` - Connection state updates
- `new_message` - New inbound/outbound messages
- `webhook_attempt` - Webhook delivery results
- `security_event` - IP blocks, failed auth
- `stats_updated` - Dashboard statistics changes

#### 2. Event Broadcasting Integration

**Hook Points:**
- `tenant_manager.update_session_state()` → broadcast `tenant_state_changed`
- `handle_bridge_event()` in main.py → broadcast `new_message`
- `WebhookSender.send()` → broadcast `webhook_attempt`
- `rate_limiter.block_ip()` → broadcast `security_event`

#### 3. Frontend WebSocket Client

**JavaScript Class:**
```javascript
class AdminWebSocket {
  constructor() {
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.heartbeatInterval = null;
  }
  
  connect() {
    this.ws = new WebSocket('wss://localhost:8080/admin/ws');
    this.ws.onopen = () => this.onOpen();
    this.ws.onmessage = (e) => this.onMessage(JSON.parse(e.data));
    this.ws.onclose = () => this.onClose();
    this.startHeartbeat();
  }
  
  onMessage(event) {
    switch(event.type) {
      case 'tenant_state_changed':
        htmx.trigger('#tenants-list', 'load');
        break;
      case 'new_message':
        htmx.trigger('#messages-list', 'load');
        break;
      // ... other event types
    }
  }
}
```

**Page Integration:**
- Dashboard: Listen for `stats_updated`, refresh cards
- Tenants: Listen for `tenant_state_changed`, update badges
- Messages: Listen for `new_message`, refresh list
- Security: Listen for `security_event`, update lists

### Testing

**File:** `tests/test_admin_websocket.py`

**Test Cases:**
- ✅ Connection requires valid session
- ✅ Events broadcast to all connected clients
- ✅ Tenant state changes trigger broadcasts
- ✅ New messages trigger broadcasts
- ✅ Webhook attempts trigger broadcasts
- ✅ Heartbeat maintains connection
- ✅ Auto-reconnect on disconnect

---

## Phase 5: Enhanced Features

### 5.1 Enhanced Message Search

**Current State:** ✅ Backend supports search/filters
**What's Missing:** UI components

#### Frontend Components

**Search Bar (add to `/admin/messages`):**
```html
<div class="bg-gray-800 p-4 rounded-lg mb-4">
  <div class="flex gap-4">
    <input type="text" 
           id="message-search" 
           placeholder="Search messages..."
           class="flex-1 px-4 py-2 bg-gray-700 rounded-lg"
           onkeyup="debounce(searchMessages, 300)">
    
    <select id="tenant-filter" class="px-4 py-2 bg-gray-700 rounded-lg">
      <option value="">All Tenants</option>
    </select>
    
    <select id="direction-filter" class="px-4 py-2 bg-gray-700 rounded-lg">
      <option value="">All Directions</option>
      <option value="in">Inbound</option>
      <option value="out">Outbound</option>
    </select>
    
    <button onclick="searchMessages()" class="px-4 py-2 bg-whatsapp rounded-lg">
      Search
    </button>
  </div>
</div>
```

**Features:**
- Debounced search (300ms delay)
- Real-time HTMX updates
- Text highlighting in results
- Pagination with "Load More"
- Total count display

**Backend Support:** ✅ Already exists
- `db.list_messages()` supports all filters
- `/admin/api/messages` endpoint ready
- `/admin/fragments/messages` fragment ready

### 5.2 Tenant Details Page

**New Route:** `/admin/tenants/{hash}`

#### Page Layout

**Header Section:**
- Tenant name, status badge, phone
- Created date, last connected
- Quick stats (message count, webhook count)

**Tabs:**
1. **Messages** - Real-time chat view
2. **Webhooks** - Configuration & history
3. **Settings** - Edit tenant, danger zone

#### Messages Tab (Live Chat)

**Features:**
- WebSocket connection for real-time updates
- Chat bubble interface (inbound left, outbound right)
- Auto-scroll to latest messages
- Send message form at bottom

**Implementation:**
```python
@router.get("/tenants/{tenant_hash}", response_class=HTMLResponse)
async def tenant_details_page(
    tenant_hash: str,
    session_id: str = Depends(require_admin_session)
):
    # Render tenant details page with tabs
    pass

@fragments_router.websocket("/tenants/{tenant_hash}/messages-live")
async def tenant_messages_live(
    websocket: WebSocket,
    tenant_hash: str,
    session_id: str = Depends(require_admin_session)
):
    # WebSocket endpoint for live message stream
    pass
```

#### Webhooks Tab
- List configured webhooks
- Recent delivery attempts
- Add/remove webhooks inline
- Test webhook button

#### Settings Tab
- Edit tenant name
- Chatwoot configuration
- Clear credentials button
- Delete tenant button (with confirmation)

### 5.3 Bulk Operations

**Maximum Items:** 50 per operation

#### Backend Endpoints

**Bulk Tenant Operations:**
```python
@api_router.post("/tenants/bulk/reconnect")
async def bulk_reconnect_tenants(
    tenant_hashes: list[str] = Body(..., max_items=50),
    session_id: str = Depends(require_admin_session)
):
    results = []
    for hash in tenant_hashes:
        try:
            tenant = tenant_manager._tenants.get(hash)
            if tenant:
                await tenant_manager.get_or_create_bridge(tenant)
                await tenant.bridge.login()
                results.append({"hash": hash, "status": "success"})
            else:
                results.append({"hash": hash, "status": "not_found"})
        except Exception as e:
            results.append({"hash": hash, "status": "error", "error": str(e)})
    
    return {"processed": len(results), "results": results}

@api_router.delete("/tenants/bulk")
async def bulk_delete_tenants(
    tenant_hashes: list[str] = Body(..., max_items=50),
    session_id: str = Depends(require_admin_session)
):
    # Similar pattern with confirmation requirement
    pass
```

**Bulk Message Operations:**
```python
@api_router.delete("/messages/bulk")
async def bulk_delete_messages(
    message_ids: list[int] = Body(..., max_items=50),
    session_id: str = Depends(require_admin_session)
):
    deleted = []
    for msg_id in message_ids:
        if await db.delete_message(msg_id):
            deleted.append(msg_id)
    
    return {
        "requested": len(message_ids),
        "deleted": len(deleted),
        "message_ids": deleted
    }
```

**Bulk Webhook Operations:**
```python
@api_router.post("/webhooks/bulk/test")
async def bulk_test_webhooks(
    webhook_urls: list[str] = Body(..., max_items=50),
    session_id: str = Depends(require_admin_session)
):
    # Test all webhooks in parallel
    pass
```

#### Frontend Components

**1. Selection UI:**
```html
<!-- Add to tenant/message rows -->
<input type="checkbox" 
       class="tenant-checkbox" 
       data-hash="abc123"
       onchange="updateBulkSelection()">

<!-- Select all checkbox -->
<input type="checkbox" 
       id="select-all-tenants"
       onchange="toggleSelectAll()">
```

**2. Bulk Action Bar:**
```html
<div id="bulk-action-bar" class="fixed bottom-0 left-0 right-0 bg-gray-800 p-4 hidden">
  <div class="flex items-center justify-between">
    <span id="selected-count">0 selected</span>
    <div class="flex gap-2">
      <button onclick="bulkReconnect()" class="btn-primary">Reconnect</button>
      <button onclick="bulkDelete()" class="btn-danger">Delete</button>
      <button onclick="clearSelection()" class="btn-secondary">Cancel</button>
    </div>
  </div>
</div>
```

**3. Confirmation Dialogs:**
```javascript
async function bulkDelete() {
  const selected = getSelectedTenants();
  const confirmed = confirm(
    `Are you sure you want to delete ${selected.length} tenants?\n\n` +
    `This action cannot be undone.`
  );
  
  if (!confirmed) return;
  
  // For destructive ops, require typing confirmation
  const typed = prompt(
    `Type "DELETE ${selected.length} TENANTS" to confirm:`
  );
  
  if (typed !== `DELETE ${selected.length} TENANTS`) {
    alert('Confirmation text did not match');
    return;
  }
  
  // Proceed with deletion
  const result = await fetch('/admin/api/tenants/bulk', {
    method: 'DELETE',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(selected)
  });
  
  // Show results
  showBulkResult(await result.json());
}
```

**4. Progress Indicator:**
```javascript
function showBulkProgress(current, total) {
  document.getElementById('bulk-progress').textContent = 
    `Processing ${current}/${total}...`;
}

function showBulkResult(result) {
  const summary = `
    ✅ Successful: ${result.results.filter(r => r.status === 'success').length}
    ❌ Failed: ${result.results.filter(r => r.status === 'error').length}
  `;
  alert(summary);
}
```

---

## Database Changes

**Required:** None ✅

All necessary tables and indexes already exist:
- ✅ `messages` table with full-text search
- ✅ `tenants` table with metadata
- ✅ `webhook_attempts` table
- ✅ Indexes for performance

---

## Implementation Timeline

### Week 1: Phase 4 (Real-time Updates)

**Day 1-2: Backend WebSocket**
- [ ] Create `src/admin/websocket.py`
- [ ] Implement `AdminConnectionManager`
- [ ] Add `/admin/ws` endpoint to main.py
- [ ] Integrate event broadcasting hooks

**Day 3: Frontend WebSocket**
- [ ] Create `AdminWebSocket` JavaScript class
- [ ] Add WebSocket connection to all admin pages
- [ ] Implement event handlers for each page

**Day 4-5: Testing & Docs**
- [ ] Write `tests/test_admin_websocket.py`
- [ ] Test multi-client scenarios
- [ ] Test reconnection logic
- [ ] Update `docs/admin-websocket.md`
- [ ] Update `docs/admin-dashboard.md`

### Week 2: Phase 5 (Enhanced Features)

**Day 1-2: Message Search**
- [ ] Add search UI to messages page
- [ ] Implement debounced search
- [ ] Add text highlighting
- [ ] Add pagination controls

**Day 3-4: Tenant Details Page**
- [ ] Create tenant details route
- [ ] Build tabbed interface
- [ ] Add real-time message stream
- [ ] Add settings/webhook tabs

**Day 5: Bulk Operations**
- [ ] Implement bulk operation endpoints
- [ ] Add selection UI components
- [ ] Add confirmation dialogs
- [ ] Test edge cases

**Day 6-7: Testing & Finalization**
- [ ] Write comprehensive tests
- [ ] Manual testing
- [ ] Update all documentation
- [ ] Update `tasks/todo.md`

---

## Testing Strategy

### Unit Tests

**New Test Files:**
1. `tests/test_admin_websocket.py`
   - WebSocket connection/disconnection
   - Event broadcasting
   - Session validation
   - Heartbeat mechanism

2. `tests/test_bulk_operations.py`
   - Bulk tenant operations
   - Bulk message operations
   - Bulk webhook operations
   - Edge cases (partial failures)

3. `tests/test_tenant_details.py`
   - Tenant details page load
   - Tab navigation
   - Real-time message updates

### Integration Tests

**WebSocket Integration:**
- Multiple clients receive same events
- Events trigger correct HTMX updates
- Connection survives server restart

**Bulk Operations:**
- Process 50 items successfully
- Handle partial failures gracefully
- Confirmation flow works correctly

### Manual Testing Checklist

**WebSocket:**
- [ ] Open 3 browser tabs, verify all receive updates
- [ ] Kill WebSocket server, verify auto-reconnect
- [ ] Check browser console for errors
- [ ] Verify heartbeat keeps connection alive

**Search:**
- [ ] Search returns correct results
- [ ] Filters work independently and combined
- [ ] Pagination works correctly
- [ ] Performance with 10k+ messages

**Tenant Details:**
- [ ] Real-time messages appear immediately
- [ ] Send message from details page works
- [ ] Webhooks tab shows correct data
- [ ] Settings changes persist correctly

**Bulk Operations:**
- [ ] Select all/deselect all works
- [ ] Bulk reconnect handles failures
- [ ] Confirmation dialogs prevent accidents
- [ ] Progress indicator shows correctly

---

## Documentation Updates

### Files to Update

1. **`docs/admin-dashboard.md`**
   - Add WebSocket section
   - Document real-time features
   - Add search/filter documentation
   - Document tenant details page
   - Add bulk operations guide

2. **`docs/admin-websocket.md`** (NEW)
   - WebSocket API reference
   - Event types and payloads
   - Client implementation guide
   - Troubleshooting section

3. **`README.md`**
   - Update features list
   - Mention real-time capabilities
   - Add screenshots of new features

4. **`tasks/todo.md`**
   - Mark Phase 4 complete
   - Mark Phase 5 complete
   - Update current status

5. **`PLAN.md`** or **`plan.md`**
   - Update project roadmap
   - Document completed phases

---

## Configuration

### Environment Variables

No new environment variables required. WebSocket uses existing:
- `ADMIN_PASSWORD` - Already configured
- `DATABASE_URL` - Already configured
- `HOST` / `PORT` - Already configured

### WebSocket Settings

Add to `src/config.py`:
```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # WebSocket settings
    admin_ws_heartbeat_interval: int = 30  # seconds
    admin_ws_max_connections: int = 10
    admin_ws_message_queue_size: int = 100
```

---

## Security Considerations

### WebSocket Security

1. **Authentication:**
   - Validate admin session on connect
   - Re-validate session periodically
   - Disconnect on session expiry

2. **Authorization:**
   - All connected admins see all events (multi-tenant admin)
   - Future: Role-based access control

3. **Rate Limiting:**
   - Limit WebSocket connections per IP
   - Limit message broadcast rate
   - Protect against flood attacks

4. **Input Validation:**
   - Validate all incoming WebSocket messages
   - Sanitize event data before broadcast
   - Prevent injection attacks

### Bulk Operations Security

1. **Confirmation Required:**
   - Destructive ops require typed confirmation
   - Show affected items before execution
   - Log all bulk operations

2. **Rate Limiting:**
   - Limit bulk operations per minute
   - Maximum 50 items per request
   - Prevent abuse

3. **Audit Trail:**
   - Log who performed operation
   - Log what was affected
   - Store in database for review

---

## Performance Considerations

### WebSocket Performance

- **Connection Pooling:** AdminConnectionManager handles multiple clients efficiently
- **Event Batching:** Consider batching rapid events (e.g., multiple messages in 1s)
- **Memory Management:** Clean up disconnected clients immediately
- **Broadcasting:** Use efficient async iteration for multiple clients

### Search Performance

- **Database Indexes:** Already exist on messages table
- **Pagination:** Always use limit/offset
- **Caching:** Consider caching tenant list for filters
- **Full-text Search:** PostgreSQL `ILIKE` is sufficient for current scale

### Bulk Operations Performance

- **Parallel Processing:** Use `asyncio.gather()` for independent operations
- **Progress Updates:** Stream progress via WebSocket
- **Timeout Protection:** Set reasonable timeout per operation
- **Resource Limits:** Enforce 50 item maximum

---

## Rollback Plan

### If Phase 4 (WebSocket) Has Issues:

1. **Immediate:** Disable WebSocket endpoint in `main.py`
2. **Fallback:** Dashboard continues with HTMX polling (current behavior)
3. **No Data Loss:** WebSocket is additive, no data migration

### If Phase 5 (Enhanced Features) Has Issues:

1. **Search:** Can disable search UI, backend already exists
2. **Tenant Details:** Can remove route, old tenant list still works
3. **Bulk Ops:** Can disable endpoints, individual operations still work

### Database Rollback

**Not Required:** No schema changes

---

## Success Metrics

### Phase 4 Success Criteria:
- ✅ WebSocket connects successfully with valid session
- ✅ Events broadcast to all connected admins within 100ms
- ✅ Auto-reconnect works within 5 seconds
- ✅ Zero increase in server memory usage
- ✅ All tests pass

### Phase 5 Success Criteria:
- ✅ Search returns results in <200ms for 10k messages
- ✅ Tenant details page loads in <300ms
- ✅ Real-time messages appear within 500ms
- ✅ Bulk operations handle 50 items in <10s
- ✅ All tests pass
- ✅ Documentation complete

---

## Future Enhancements (Out of Scope)

**Not included in this phase:**

1. **Advanced Search Filters:**
   - Date range picker
   - Message type filter (image, video, etc.)
   - Group vs individual filter

2. **Message Actions:**
   - Reply to message
   - Forward message
   - Quote message

3. **Analytics Dashboard:**
   - Message volume charts
   - Peak usage times
   - Response time metrics

4. **Role-Based Access:**
   - Super admin vs tenant admin
   - Permission management
   - Audit logs UI

5. **Export Features:**
   - Export messages to CSV/JSON
   - Export webhook logs
   - Generate reports

---

## Notes

- All code follows existing project conventions
- Tailwind CSS for styling (consistent with current UI)
- HTMX for dynamic updates (existing pattern)
- No new dependencies required
- Compatible with existing PostgreSQL/SQLite setup
- Works with current authentication system

---

## Questions & Decisions Log

**Decision 1:** Separate Admin WebSocket vs. Extend Existing
- **Chosen:** Separate `/admin/ws` endpoint
- **Reason:** Cleaner separation, easier to maintain, independent scaling

**Decision 2:** Bulk Operation Limit
- **Chosen:** 50 items maximum
- **Reason:** Balance between usability and system stability

**Decision 3:** Live Chat Streaming
- **Chosen:** Yes, with WebSocket streaming
- **Reason:** Better UX, showcases real-time capabilities

**Decision 4:** Search Filter Level
- **Chosen:** Standard (text + tenant + direction)
- **Reason:** Covers most use cases without complexity

---

## Sign-off

**Plan Created:** 2026-03-03
**Status:** Ready for Implementation
**Next Step:** Switch from Plan Mode to Implementation Mode
