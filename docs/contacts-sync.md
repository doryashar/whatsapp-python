# Contacts Synchronization

## Overview

The WhatsApp API automatically synchronizes contacts when a tenant connects via QR code. This ensures that the contacts database is populated with all available contacts from the WhatsApp account.

## How It Works

### 1. QR Code Connection Flow

When a tenant scans a QR code and connects to WhatsApp:

1. The bridge (Baileys) establishes a connection to WhatsApp
2. After successful connection, the bridge waits 2 seconds for contacts to sync
3. The bridge fetches all contacts from the WhatsApp store
4. Contacts are sent to the Python backend via a `contacts` event

### 2. Contact Storage

Contacts are stored in the `contacts` table with the following information:

- `phone`: Normalized phone number (e.g., "1234567890")
- `name`: Contact name from WhatsApp
- `chat_jid`: WhatsApp JID (e.g., "1234567890@s.whatsapp.net")
- `is_group`: Boolean indicating if it's a group chat
- `message_count`: Number of messages exchanged with this contact
- `last_message_at`: Timestamp of the last message

### 3. Contact Deduplication

Contacts are deduplicated by normalized phone number. If a contact already exists:
- The name is updated only if the new name is not empty
- The message count is incremented
- The last message timestamp is updated

## Implementation Details

### Bridge Side (JavaScript)

The bridge automatically fetches contacts when connection is established:

```javascript
// In bridge/index.mjs
if (connection === "open") {
  // ... connection established ...
  
  // Fetch contacts after 2 seconds
  setTimeout(async () => {
    const contacts = [];
    if (sock.store && sock.store.contacts) {
      for (const [jid, contact] of sock.store.contacts) {
        // Filter out broadcast and status
        if (jid && !jid.endsWith('@broadcast') && jid !== 'status@broadcast') {
          const isGroup = isJidGroup(jid);
          contacts.push({
            jid: jid,
            name: contact.name || contact.notify || null,
            phone: isGroup ? null : jid.split('@')[0].split(':')[0],
            is_group: isGroup,
          });
        }
      }
    }
    sendEvent("contacts", { contacts });
  }, 2000);
}
```

### Python Side

The backend handles the `contacts` event:

```python
# In src/main.py
elif event_type == "contacts":
    logger.info(
        f"Received contacts for tenant {tenant.name}: count={len(params.get('contacts', []))}"
    )
    asyncio.create_task(handle_contacts_sync(tenant, params.get("contacts", [])))
```

The `handle_contacts_sync` function processes and stores each contact:

```python
async def handle_contacts_sync(tenant: "Tenant", contacts: list[dict]):
    """Sync contacts from WhatsApp to database"""
    for contact in contacts:
        phone = contact.get("phone")
        jid = contact.get("jid")
        if not phone or not jid:
            continue

        normalized_phone = normalize_phone(phone)
        if not normalized_phone:
            continue

        await tenant_manager._db.upsert_contact(
            tenant_hash=tenant.api_key_hash,
            phone=normalized_phone,
            name=contact.get("name"),
            chat_jid=jid,
            is_group=contact.get("is_group", False),
        )
```

## API Endpoints

### Get Contacts

**Endpoint:** `GET /api/tenants/{tenant_hash}/contacts`

Returns the list of contacts for a specific tenant.

**Response:**
```json
{
  "contacts": [
    {
      "phone": "1234567890",
      "name": "John Doe",
      "chat_jid": "1234567890@s.whatsapp.net",
      "is_group": false,
      "message_count": 5,
      "last_message_at": "2024-01-15T10:30:00"
    }
  ]
}
```

## Manual Contact Fetching

If you need to manually fetch contacts after connection, you can call the bridge method:

```python
# Using the bridge client
contacts = await tenant.bridge.get_contacts()
```

## Testing

The contact synchronization is tested in `tests/test_contacts.py`. The test suite includes:

- `test_contacts_sync_on_connection`: Verifies that contacts are properly synced when received from WhatsApp

Run the tests:
```bash
python -m pytest tests/test_contacts.py -v
```

## Important Notes

1. **Timing**: Contacts are fetched 2 seconds after connection to ensure they have synced from WhatsApp servers
2. **Filtering**: Broadcast lists and status updates are filtered out
3. **Groups**: Group chats are included but don't have phone numbers (phone is null)
4. **Normalization**: Phone numbers are normalized using the `normalize_phone` utility
5. **Privacy**: Contact names are preserved unless a newer non-empty name is provided

## Future Improvements

- Add periodic contact refresh during active sessions
- Implement contact change detection and delta updates
- Add contact photo synchronization
- Support for contact labels and tags
