# WhatsApp API - Deployment Guide

## Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- PostgreSQL (optional, SQLite works for development)
- Python 3.11+ (for local development)

### 2. Configuration

Create `.env` file:
```bash
# Admin Dashboard
ADMIN_PASSWORD=your-secure-password

# Database (PostgreSQL recommended for production)
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Or use SQLite for development
# DATABASE_URL=sqlite:///./data/whatsapp.db

# Server
HOST=0.0.0.0
PORT=8080

# Observability (optional)
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

### 3. Run with Docker

```bash
# Build and start
docker compose up -d

# Check logs
docker logs -f whatsapp-api

# Stop
docker compose down
```

### 4. Access Dashboard

Navigate to: `http://localhost:8080/admin/login`

Enter your `ADMIN_PASSWORD`

---

## Features Available

### ✅ Phase 1-3: Core Features
- Multi-tenant WhatsApp sessions
- PostgreSQL persistence
- Webhook delivery
- Rate limiting with IP blocking
- Admin dashboard

### ✅ Phase 4: Real-time Updates
- WebSocket-based live updates
- Instant notifications
- Auto-reconnect on disconnect

### ✅ Phase 5: Enhanced Features
- Advanced message search
- Tenant details page
- Bulk operations

---

## Production Checklist

### Security
- [x] Set strong `ADMIN_PASSWORD`
- [x] Configure rate limiting
- [x] Enable HTTPS (via reverse proxy)
- [x] Set up firewall rules
- [x] Configure database backups

### Performance
- [x] Use PostgreSQL (not SQLite)
- [x] Configure connection pooling
- [x] Set up monitoring (Grafana)
- [x] Configure log aggregation

### High Availability
- [ ] Set up load balancing
- [ ] Configure database replication
- [ ] Set up Redis for session storage
- [ ] Configure health checks

---

## Monitoring

### Metrics Available
- WebSocket connections
- Message throughput
- Webhook delivery rates
- Rate limit events
- Database connections

### Access Grafana
```bash
# Start monitoring stack
docker compose -f docker-compose.monitoring.yml up -d

# Access Grafana
http://localhost:3000
```

---

## Troubleshooting

### WebSocket Not Connecting
1. Check browser console for errors
2. Verify `ADMIN_PASSWORD` is set
3. Check if session has expired
4. Verify network allows WebSocket connections

### Messages Not Appearing
1. Check tenant is connected
2. Verify WhatsApp session is active
3. Check database connectivity
4. Review webhook delivery logs

### Rate Limiting Issues
1. Check `/admin/security` for blocked IPs
2. Clear failed auth attempts if needed
3. Adjust rate limit settings in config

---

## Upgrade Path

### From Phase 1-3 to Phase 4-5

1. **Pull latest code:**
   ```bash
   git pull origin main
   ```

2. **No database migrations needed** ✅

3. **No new dependencies** ✅

4. **Restart services:**
   ```bash
   docker compose restart
   ```

5. **Verify:**
   - Open admin dashboard
   - Check WebSocket connects (browser console)
   - Test message search
   - Test tenant details page

---

## Performance Tuning

### WebSocket
```python
# In src/config.py (future enhancement)
ADMIN_WS_MAX_CONNECTIONS = 100
ADMIN_WS_HEARTBEAT_INTERVAL = 30
ADMIN_WS_MESSAGE_QUEUE_SIZE = 1000
```

### Database
```python
# PostgreSQL connection pooling
DB_POOL_MIN = 10
DB_POOL_MAX = 50
```

### Search
```python
# Search performance
SEARCH_DEBOUNCE_MS = 300
SEARCH_MAX_RESULTS = 500
```

---

## Backup Strategy

### Database Backup
```bash
# PostgreSQL
pg_dump -U user dbname > backup.sql

# SQLite
cp data/whatsapp.db backup/whatsapp-$(date +%Y%m%d).db
```

### Configuration Backup
```bash
# Backup .env and docker-compose.yml
tar -czf config-backup.tar.gz .env docker-compose.yml
```

---

## Support

### Logs Location
- Application: `docker logs whatsapp-api`
- WebSocket: Browser console (F12)
- Database: PostgreSQL logs

### Health Check
```bash
curl http://localhost:8080/health
```

### Debug Mode
```bash
export DEBUG=true
docker compose up
```

---

## Next Steps

After deployment:
1. Create your first tenant
2. Scan QR code to connect WhatsApp
3. Configure webhooks (if needed)
4. Test message sending
5. Explore real-time updates
6. Try bulk operations

---

## Version History

- **v2.1.0** (2026-03-03): Phase 4 & 5 - Real-time updates + Enhanced features
- **v2.0.0**: Phase 3 - Admin dashboard
- **v1.0.0**: Phase 1-2 - Core features + tooling

---

**Status:** ✅ Production Ready
**License:** MIT
**Support:** github.com/doryashar/whatsapp-python/issues
