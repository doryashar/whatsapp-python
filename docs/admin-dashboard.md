# Admin Dashboard

Modern web UI for managing the WhatsApp API.

## Access

**URL:** http://localhost:8080/admin/login  
**Password:** Set via `ADMIN_PASSWORD` environment variable

## Configuration

Add to your `.env` file or docker-compose.yml:

```bash
ADMIN_PASSWORD=your-secure-password
```

## Features

### Dashboard (`/admin/dashboard`)
- System overview with live stats
- Connected/disconnected tenant counts  
- Message statistics
- Webhook success rates
- Quick action buttons

### Tenants (`/admin/tenants`)
- List all tenants
- Create new tenants
- View connection status
- Delete tenants
- Reconnect tenants
- Clear stored credentials

### Messages (`/admin/messages`)
- View all messages across tenants
- Filter by tenant
- Search message content
- View message metadata (sender, timestamp, direction)

### Webhooks (`/admin/webhooks`)
- List all registered webhooks
- View delivery history
- See success/failure rates
- View latency metrics
- Error messages for failed deliveries

### Security (`/admin/security`)
- View blocked IPs
- Block/unblock IP addresses
- View failed authentication attempts
- Clear failed attempt counters
- Rate limit statistics

## API Endpoints

All API endpoints require session authentication (login first):

```bash
# Login and save session cookie
curl -c cookies.txt -X POST http://localhost:8080/admin/login \
  -d "password=your-password"

# Use session for subsequent requests
curl -b cookies.txt http://localhost:8080/admin/api/stats
```

### Available Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/admin/login` | Login with password |
| POST | `/admin/logout` | End session |
| GET | `/admin/api/stats` | System statistics |
| GET | `/admin/api/tenants` | List tenants |
| POST | `/admin/api/tenants` | Create tenant |
| GET | `/admin/api/tenants/:hash` | Get tenant details |
| DELETE | `/admin/api/tenants/:hash` | Delete tenant |
| POST | `/admin/api/tenants/:hash/reconnect` | Force reconnect |
| DELETE | `/admin/api/tenants/:hash/credentials` | Clear credentials |
| GET | `/admin/api/messages` | List messages |
| GET | `/admin/api/webhooks` | List webhooks |
| GET | `/admin/api/webhooks/history` | Delivery history |
| GET | `/admin/api/webhooks/stats` | Webhook statistics |
| POST | `/admin/api/tenants/:hash/webhooks` | Add webhook |
| DELETE | `/admin/api/tenants/:hash/webhooks` | Remove webhook |
| GET | `/admin/api/rate-limit/blocked` | List blocked IPs |
| POST | `/admin/api/rate-limit/block` | Block IP |
| DELETE | `/admin/api/rate-limit/block` | Unblock IP |
| GET | `/admin/api/rate-limit/failed-auth` | Failed auth attempts |
| DELETE | `/admin/api/rate-limit/failed-auth` | Clear failed attempts |

## Technology Stack

- **Frontend:** Tailwind CSS, HTMX
- **Icons:** Heroicons
- **Authentication:** Session-based with HTTP-only cookies
- **Real-time:** HTMX polling (30s intervals)
- **Architecture:** HTML fragment endpoints for dynamic content loading

## HTML Fragment Endpoints

The dashboard uses HTMX to load HTML fragments from these endpoints:

| Endpoint | Description |
|----------|-------------|
| `/admin/fragments/stats` | Stats cards HTML |
| `/admin/fragments/tenants` | Tenants list HTML |
| `/admin/fragments/messages` | Messages list HTML |
| `/admin/fragments/webhooks` | Webhooks list HTML |
| `/admin/fragments/webhook-history` | Webhook attempts HTML |
| `/admin/fragments/blocked-ips` | Blocked IPs list HTML |
| `/admin/fragments/failed-auth` | Failed auth attempts HTML |

These endpoints return rendered HTML fragments that HTMX inserts into the page, providing a smooth user experience without full page reloads.

## Testing

```bash
# Start services with admin password
ADMIN_PASSWORD='your-password' docker compose up -d

# Test login
python3 << 'EOF'
import requests
session = requests.Session()
login = session.post(
    "http://localhost:8080/admin/login",
    data={"password": "your-password"}
)
print(f"Login: {login.status_code}")

# Test dashboard
dashboard = session.get("http://localhost:8080/admin/dashboard")
print(f"Dashboard: {dashboard.status_code}")
print(f"Has content: {'WhatsApp Admin' in dashboard.text}")
EOF
```

## Database Tables

The admin dashboard uses three database tables:

### messages
Stores all messages for persistence and viewing:
```sql
- id (auto-increment)
- tenant_hash (foreign key)
- message_id (WhatsApp ID)
- from_jid, chat_jid (sender/chat)
- text, msg_type, timestamp
- direction (inbound/outbound)
- created_at
```

### webhook_attempts  
Tracks all webhook delivery attempts:
```sql
- id (auto-increment)
- tenant_hash (foreign key)
- url (webhook endpoint)
- event_type (message, connected, etc)
- success (boolean)
- status_code, error_message
- latency_ms, attempt_number
- payload_preview (first 500 chars)
- created_at
```

### admin_sessions
Manages login sessions:
```sql
- id (session ID)
- created_at, expires_at
- user_agent, ip_address
```

## Security

- Sessions expire after 24 hours
- HTTP-only cookies prevent XSS
- CSRF protection via SameSite cookies
- Password hashed with SHA256
- Rate limiting applies to all endpoints
- Failed login attempts are tracked

## Troubleshooting

**Can't access admin pages:**
1. Check `ADMIN_PASSWORD` is set
2. Clear browser cookies
3. Check container logs: `docker logs whatsapp-api`

**Login redirects but shows 401:**
- Session cookie not being saved
- Check browser cookie settings
- Verify password is correct

**Pages not updating:**
- HTMX polls every 30 seconds
- Manually refresh the page
- Check browser console for errors
