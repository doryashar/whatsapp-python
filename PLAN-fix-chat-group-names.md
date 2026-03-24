# Plan: Fix Chat Names + Image Display (IMPLEMENTED)

## Status: Done

All three issues have been fixed. See the implementation summary below.

## Problems Fixed

1. Messages page shows "Chat: group" instead of actual group names
2. Group tabs show numeric IDs (e.g., `120363111222`) instead of group names
3. Images show "[Image message]" placeholder instead of inline images
4. Image URLs expire after WhatsApp's temporary URL expires

## Root Cause

**`sock.store` was never populated.** The WhiskeySockets fork (`@whiskeysockets/baileys ^6.6.0`) does NOT export `makeInMemoryStore`, so the bridge never created an in-memory store. All references to `sock.store` returned `undefined`. The `messaging-history.set` event provided chat/contact/message data but it was discarded.

## Implementation Summary

### Phase 1: In-memory stores in `bridge/index.mjs`

- Added `chatStore`, `contactStore`, `messageStore` Map-based stores at module level
- Added `_upsertChat()`, `_upsertContact()`, `_upsertMessage()`, `_getChatName()` helpers
- `messaging-history.set` event now populates all three stores from the arrays it receives
- Added incremental event listeners: `chats.upsert`, `chats.update`, `contacts.upsert`, `contacts.update`, `groups.upsert`, `groups.update`, `messages.upsert`
- Added `sock.groupFetchAllParticipating()` call on connect to fetch all group metadata
- Replaced ALL 9 `sock.store` references with the new Map stores

### Phase 2: Fix contact sync for groups (`src/main.py`)

- `handle_contacts_sync()` now accepts contacts without a `phone` field (groups)
- For groups, uses the JID prefix as the phone key for the DB unique constraint
- Skips phone normalization for group contacts

### Phase 3: Inline media on global Messages page (`src/admin/routes.py`)

- Added `render_compact_media()` function for the global messages list
- Renders: image thumbnails (click to expand), video/audio/document cards, location links, stickers
- Added `toggleMediaExpand()` JS for image click-to-enlarge
- Changed "[Image message]" fallback to only show when no media_url exists

### Phase 4: Media caching to local disk

- Added `_download_and_cache_media()` in `src/main.py` — downloads media from WhatsApp URL after message storage
- Added `update_message_media_url()` in `src/store/database.py` — updates DB with local file path
- Added `GET /admin/media/{tenant_hash}/{message_id}` endpoint in `src/admin/routes.py` — serves cached media files
- Added `_resolve_media_url()` helper — converts local file paths to the media serving endpoint URL
- Both `render_compact_media()` and `render_media_content()` use `_resolve_media_url()` for proper URL routing
- Media saved to `data/media/{tenant_hash}/{message_id}.{ext}`

## Files Modified

| File | Changes |
|------|---------|
| `bridge/index.mjs` | Added 3 Map stores, 4 helper functions, 7 event listeners, group fetch on connect, replaced 9 `sock.store` references |
| `src/main.py` | Fixed contact sync for groups, added media download/cache system, added `_download_and_cache_media()`, `_update_media_url_in_db()` |
| `src/store/database.py` | Added `update_message_media_url()` method |
| `src/admin/routes.py` | Added `render_compact_media()`, `_resolve_media_url()`, `toggleMediaExpand()`, media serving endpoint, updated `render_media_content()` |
| `PLAN-fix-chat-group-names.md` | Updated (this file) |
