import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Optional

from ..telemetry import get_logger

logger = get_logger("whatsapp.database")


class Database:
    def __init__(self, database_url: str, data_dir: Path):
        self.database_url = database_url
        self.data_dir = data_dir
        self._pool: Any = None
        self._is_postgres = database_url.startswith(("postgresql://", "postgres://"))
        logger.debug(
            f"Database initialized: postgres={'yes' if self._is_postgres else 'no'}"
        )

    async def connect(self) -> None:
        if self._is_postgres:
            import asyncpg

            logger.info(
                f"Connecting to PostgreSQL: {self.database_url.split('@')[1] if '@' in self.database_url else 'hidden'}"
            )
            self._pool = await asyncpg.create_pool(self.database_url)
            await self._create_tables_postgres()
            logger.info("PostgreSQL connection established")
        else:
            import aiosqlite

            self.data_dir.mkdir(parents=True, exist_ok=True)
            db_path = self.data_dir / "whatsapp.db"
            logger.info(f"Connecting to SQLite: {db_path}")
            self._pool = await aiosqlite.connect(db_path)
            await self._pool.execute("PRAGMA journal_mode=WAL")
            await self._create_tables_sqlite()
            logger.info("SQLite connection established")

    async def close(self) -> None:
        if self._pool:
            logger.debug("Closing database connection")
            await self._pool.close()

    async def _create_tables_postgres(self) -> None:
        logger.debug("Creating PostgreSQL tables if not exist")
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    api_key_hash TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    webhook_urls JSONB DEFAULT '[]',
                    connection_state TEXT DEFAULT 'disconnected',
                    self_jid TEXT,
                    self_phone TEXT,
                    self_name TEXT,
                    last_connected_at TIMESTAMP,
                    last_disconnected_at TIMESTAMP,
                    has_auth BOOLEAN DEFAULT FALSE,
                    creds_json JSONB
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    tenant_hash TEXT NOT NULL REFERENCES tenants(api_key_hash) ON DELETE CASCADE,
                    message_id TEXT NOT NULL,
                    from_jid TEXT NOT NULL,
                    chat_jid TEXT NOT NULL,
                    is_group BOOLEAN DEFAULT FALSE,
                    push_name TEXT,
                    text TEXT,
                    msg_type TEXT DEFAULT 'text',
                    timestamp BIGINT NOT NULL,
                    direction TEXT DEFAULT 'inbound',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_tenant ON messages(tenant_hash, created_at DESC)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_jid, created_at DESC)"
            )
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS webhook_attempts (
                    id SERIAL PRIMARY KEY,
                    tenant_hash TEXT NOT NULL REFERENCES tenants(api_key_hash) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    status_code INTEGER,
                    error_message TEXT,
                    attempt_number INTEGER DEFAULT 1,
                    latency_ms INTEGER,
                    payload_preview TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_webhook_tenant ON webhook_attempts(tenant_hash, created_at DESC)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_webhook_url ON webhook_attempts(url, created_at DESC)"
            )
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT NOW(),
                    expires_at TIMESTAMP NOT NULL,
                    user_agent TEXT,
                    ip_address TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS global_config (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            await conn.execute("""
                ALTER TABLE tenants ADD COLUMN IF NOT EXISTS connection_state TEXT DEFAULT 'disconnected'
            """)
            await conn.execute("""
                ALTER TABLE tenants ADD COLUMN IF NOT EXISTS self_jid TEXT
            """)
            await conn.execute("""
                ALTER TABLE tenants ADD COLUMN IF NOT EXISTS self_phone TEXT
            """)
            await conn.execute("""
                ALTER TABLE tenants ADD COLUMN IF NOT EXISTS self_name TEXT
            """)
            await conn.execute("""
                ALTER TABLE tenants ADD COLUMN IF NOT EXISTS last_connected_at TIMESTAMP
            """)
            await conn.execute("""
                ALTER TABLE tenants ADD COLUMN IF NOT EXISTS last_disconnected_at TIMESTAMP
            """)
            await conn.execute("""
                ALTER TABLE tenants ADD COLUMN IF NOT EXISTS has_auth BOOLEAN DEFAULT FALSE
            """)
            await conn.execute("""
                ALTER TABLE tenants ADD COLUMN IF NOT EXISTS creds_json JSONB
            """)
            await conn.execute("""
                ALTER TABLE tenants ADD COLUMN IF NOT EXISTS chatwoot_config JSONB
            """)
            await conn.execute("""
                ALTER TABLE tenants ADD COLUMN IF NOT EXISTS enabled BOOLEAN DEFAULT TRUE
            """)
            await conn.execute("""
                ALTER TABLE messages ADD COLUMN IF NOT EXISTS chatwoot_synced_at TIMESTAMP
            """)
            await conn.execute("""
                ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_url TEXT
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_chatwoot_sync ON messages(tenant_hash, chatwoot_synced_at, created_at DESC)"
            )
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id SERIAL PRIMARY KEY,
                    tenant_hash TEXT NOT NULL REFERENCES tenants(api_key_hash) ON DELETE CASCADE,
                    phone TEXT NOT NULL,
                    name TEXT,
                    chat_jid TEXT NOT NULL,
                    is_group BOOLEAN DEFAULT FALSE,
                    last_message_at TIMESTAMP,
                    message_count INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(tenant_hash, phone)
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_contacts_tenant ON contacts(tenant_hash, last_message_at DESC)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone)"
            )

    async def _create_tables_sqlite(self) -> None:
        logger.debug("Creating SQLite tables if not exist")
        await self._pool.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                api_key_hash TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                webhook_urls TEXT DEFAULT '[]',
                connection_state TEXT DEFAULT 'disconnected',
                self_jid TEXT,
                self_phone TEXT,
                self_name TEXT,
                last_connected_at TEXT,
                last_disconnected_at TEXT,
                has_auth INTEGER DEFAULT 0,
                creds_json TEXT,
                chatwoot_config TEXT
            )
        """)
        await self._pool.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_hash TEXT NOT NULL REFERENCES tenants(api_key_hash) ON DELETE CASCADE,
                message_id TEXT NOT NULL,
                from_jid TEXT NOT NULL,
                chat_jid TEXT NOT NULL,
                is_group INTEGER DEFAULT 0,
                push_name TEXT,
                text TEXT,
                msg_type TEXT DEFAULT 'text',
                timestamp INTEGER NOT NULL,
                direction TEXT DEFAULT 'inbound',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_tenant ON messages(tenant_hash, created_at DESC)"
        )
        await self._pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_jid, created_at DESC)"
        )
        await self._pool.execute("""
            CREATE TABLE IF NOT EXISTS webhook_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_hash TEXT NOT NULL REFERENCES tenants(api_key_hash) ON DELETE CASCADE,
                url TEXT NOT NULL,
                event_type TEXT NOT NULL,
                success INTEGER NOT NULL,
                status_code INTEGER,
                error_message TEXT,
                attempt_number INTEGER DEFAULT 1,
                latency_ms INTEGER,
                payload_preview TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_webhook_tenant ON webhook_attempts(tenant_hash, created_at DESC)"
        )
        await self._pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_webhook_url ON webhook_attempts(url, created_at DESC)"
        )
        await self._pool.execute("""
            CREATE TABLE IF NOT EXISTS admin_sessions (
                id TEXT PRIMARY KEY,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL,
                user_agent TEXT,
                ip_address TEXT
            )
        """)
        await self._pool.execute("""
            CREATE TABLE IF NOT EXISTS global_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor = await self._pool.execute("PRAGMA table_info(tenants)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "chatwoot_config" not in columns:
            logger.info("Adding chatwoot_config column to tenants table")
            await self._pool.execute(
                "ALTER TABLE tenants ADD COLUMN chatwoot_config TEXT"
            )
        if "enabled" not in columns:
            logger.info("Adding enabled column to tenants table")
            await self._pool.execute(
                "ALTER TABLE tenants ADD COLUMN enabled INTEGER DEFAULT 1"
            )
        cursor = await self._pool.execute("PRAGMA table_info(messages)")
        msg_columns = [row[1] for row in await cursor.fetchall()]
        if "chatwoot_synced_at" not in msg_columns:
            logger.info("Adding chatwoot_synced_at column to messages table")
            await self._pool.execute(
                "ALTER TABLE messages ADD COLUMN chatwoot_synced_at TEXT"
            )
            await self._pool.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_chatwoot_sync ON messages(tenant_hash, chatwoot_synced_at, created_at DESC)"
            )
        if "media_url" not in msg_columns:
            logger.info("Adding media_url column to messages table")
            await self._pool.execute("ALTER TABLE messages ADD COLUMN media_url TEXT")
        await self._pool.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_hash TEXT NOT NULL REFERENCES tenants(api_key_hash) ON DELETE CASCADE,
                phone TEXT NOT NULL,
                name TEXT,
                chat_jid TEXT NOT NULL,
                is_group INTEGER DEFAULT 0,
                last_message_at TEXT,
                message_count INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_hash, phone)
            )
        """)
        await self._pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_contacts_tenant ON contacts(tenant_hash, last_message_at DESC)"
        )
        await self._pool.execute(
            "CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone)"
        )
        await self._pool.commit()

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
        logger.debug(f"Tenant saved: {name}")

    async def load_tenants(self) -> list[dict]:
        logger.debug("Loading all tenants from database")
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT api_key_hash, name, created_at, webhook_urls, 
                              connection_state, self_jid, self_phone, self_name,
                              last_connected_at, last_disconnected_at, has_auth, creds_json,
                              chatwoot_config, enabled
                       FROM tenants"""
                )
                tenants = [
                    {
                        "api_key_hash": row["api_key_hash"],
                        "name": row["name"],
                        "created_at": row["created_at"],
                        "webhook_urls": json.loads(row["webhook_urls"])
                        if isinstance(row["webhook_urls"], str)
                        else row["webhook_urls"],
                        "connection_state": row["connection_state"] or "disconnected",
                        "self_jid": row["self_jid"],
                        "self_phone": row["self_phone"],
                        "self_name": row["self_name"],
                        "last_connected_at": row["last_connected_at"],
                        "last_disconnected_at": row["last_disconnected_at"],
                        "has_auth": bool(row["has_auth"]),
                        "creds_json": json.loads(row["creds_json"])
                        if isinstance(row["creds_json"], str)
                        else row["creds_json"],
                        "chatwoot_config": json.loads(row["chatwoot_config"])
                        if row["chatwoot_config"]
                        and isinstance(row["chatwoot_config"], str)
                        else row["chatwoot_config"],
                        "enabled": bool(row["enabled"])
                        if row["enabled"] is not None
                        else True,
                    }
                    for row in rows
                ]
        else:
            async with self._pool.execute(
                """SELECT api_key_hash, name, created_at, webhook_urls,
                          connection_state, self_jid, self_phone, self_name,
                          last_connected_at, last_disconnected_at, has_auth, creds_json,
                          chatwoot_config, enabled
                   FROM tenants"""
            ) as cursor:
                rows = await cursor.fetchall()
                tenants = [
                    {
                        "api_key_hash": row[0],
                        "name": row[1],
                        "created_at": datetime.fromisoformat(row[2]),
                        "webhook_urls": json.loads(row[3]),
                        "connection_state": row[4] or "disconnected",
                        "self_jid": row[5],
                        "self_phone": row[6],
                        "self_name": row[7],
                        "last_connected_at": datetime.fromisoformat(row[8])
                        if row[8]
                        else None,
                        "last_disconnected_at": datetime.fromisoformat(row[9])
                        if row[9]
                        else None,
                        "has_auth": bool(row[10]),
                        "creds_json": json.loads(row[11]) if row[11] else None,
                        "chatwoot_config": json.loads(row[12]) if row[12] else None,
                        "enabled": bool(row[13]) if row[13] is not None else True,
                    }
                    for row in rows
                ]
        logger.debug(f"Loaded {len(tenants)} tenants")
        return tenants

    async def delete_tenant(self, api_key_hash: str) -> bool:
        logger.debug(f"Deleting tenant: hash={api_key_hash[:16]}...")
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM tenants WHERE api_key_hash = $1", api_key_hash
                )
                deleted = result.split()[-1] != "0"
        else:
            cursor = await self._pool.execute(
                "DELETE FROM tenants WHERE api_key_hash = ?",
                (api_key_hash,),
            )
            await self._pool.commit()
            deleted = cursor.rowcount > 0
        logger.debug(f"Tenant deleted: {deleted}")
        return deleted

    async def update_webhooks(self, api_key_hash: str, webhook_urls: list[str]) -> None:
        logger.debug(
            f"Updating webhooks for tenant: hash={api_key_hash[:16]}..., count={len(webhook_urls)}"
        )
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE tenants SET webhook_urls = $1 WHERE api_key_hash = $2",
                    json.dumps(webhook_urls),
                    api_key_hash,
                )
        else:
            await self._pool.execute(
                "UPDATE tenants SET webhook_urls = ? WHERE api_key_hash = ?",
                (json.dumps(webhook_urls), api_key_hash),
            )
            await self._pool.commit()
        logger.debug("Webhooks updated")

    async def update_tenant_enabled(self, api_key_hash: str, enabled: bool) -> None:
        logger.debug(
            f"Updating enabled status for tenant: hash={api_key_hash[:16]}..., enabled={enabled}"
        )
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE tenants SET enabled = $1 WHERE api_key_hash = $2",
                    enabled,
                    api_key_hash,
                )
        else:
            await self._pool.execute(
                "UPDATE tenants SET enabled = ? WHERE api_key_hash = ?",
                (1 if enabled else 0, api_key_hash),
            )
            await self._pool.commit()
        logger.debug(f"Tenant enabled status updated to {enabled}")

    async def update_session_state(
        self,
        api_key_hash: str,
        connection_state: str,
        self_jid: Optional[str] = None,
        self_phone: Optional[str] = None,
        self_name: Optional[str] = None,
        has_auth: Optional[bool] = None,
    ) -> None:
        logger.debug(
            f"Updating session state for tenant: hash={api_key_hash[:16]}..., state={connection_state}"
        )
        now = datetime.now(UTC)

        if self._is_postgres:
            async with self._pool.acquire() as conn:
                if connection_state == "connected":
                    await conn.execute(
                        """
                        UPDATE tenants SET 
                            connection_state = $1,
                            self_jid = COALESCE($2, self_jid),
                            self_phone = COALESCE($3, self_phone),
                            self_name = COALESCE($4, self_name),
                            last_connected_at = $5,
                            has_auth = COALESCE($6, has_auth)
                        WHERE api_key_hash = $7
                        """,
                        connection_state,
                        self_jid,
                        self_phone,
                        self_name,
                        now,
                        has_auth,
                        api_key_hash,
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE tenants SET 
                            connection_state = $1,
                            self_jid = COALESCE($2, self_jid),
                            self_phone = COALESCE($3, self_phone),
                            self_name = COALESCE($4, self_name),
                            last_disconnected_at = $5,
                            has_auth = COALESCE($6, has_auth)
                        WHERE api_key_hash = $7
                        """,
                        connection_state,
                        self_jid,
                        self_phone,
                        self_name,
                        now,
                        has_auth,
                        api_key_hash,
                    )
        else:
            if connection_state == "connected":
                await self._pool.execute(
                    """
                    UPDATE tenants SET 
                        connection_state = ?,
                        self_jid = COALESCE(?, self_jid),
                        self_phone = COALESCE(?, self_phone),
                        self_name = COALESCE(?, self_name),
                        last_connected_at = ?,
                        has_auth = COALESCE(?, has_auth)
                    WHERE api_key_hash = ?
                    """,
                    (
                        connection_state,
                        self_jid,
                        self_phone,
                        self_name,
                        now.isoformat(),
                        1 if has_auth else None,
                        api_key_hash,
                    ),
                )
            else:
                await self._pool.execute(
                    """
                    UPDATE tenants SET 
                        connection_state = ?,
                        self_jid = COALESCE(?, self_jid),
                        self_phone = COALESCE(?, self_phone),
                        self_name = COALESCE(?, self_name),
                        last_disconnected_at = ?,
                        has_auth = COALESCE(?, has_auth)
                    WHERE api_key_hash = ?
                    """,
                    (
                        connection_state,
                        self_jid,
                        self_phone,
                        self_name,
                        now.isoformat(),
                        1 if has_auth else None,
                        api_key_hash,
                    ),
                )
            await self._pool.commit()
        logger.debug("Session state updated")

    async def save_creds(self, api_key_hash: str, creds_json: dict) -> None:
        logger.debug(f"Saving credentials for tenant: hash={api_key_hash[:16]}...")
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE tenants SET creds_json = $1, has_auth = TRUE
                    WHERE api_key_hash = $2
                    """,
                    json.dumps(creds_json),
                    api_key_hash,
                )
        else:
            await self._pool.execute(
                """
                UPDATE tenants SET creds_json = ?, has_auth = 1
                WHERE api_key_hash = ?
                """,
                (json.dumps(creds_json), api_key_hash),
            )
            await self._pool.commit()
        logger.debug("Credentials saved")

    async def load_creds(self, api_key_hash: str) -> Optional[dict]:
        logger.debug(f"Loading credentials for tenant: hash={api_key_hash[:16]}...")
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT creds_json FROM tenants WHERE api_key_hash = $1",
                    api_key_hash,
                )
                if row and row["creds_json"]:
                    creds = row["creds_json"]
                    return json.loads(creds) if isinstance(creds, str) else creds
        else:
            async with self._pool.execute(
                "SELECT creds_json FROM tenants WHERE api_key_hash = ?",
                (api_key_hash,),
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    return json.loads(row[0])
        return None

    async def clear_creds(self, api_key_hash: str) -> None:
        logger.debug(f"Clearing credentials for tenant: hash={api_key_hash[:16]}...")
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE tenants SET creds_json = NULL, has_auth = FALSE
                    WHERE api_key_hash = $1
                    """,
                    api_key_hash,
                )
        else:
            await self._pool.execute(
                """
                UPDATE tenants SET creds_json = NULL, has_auth = 0
                WHERE api_key_hash = ?
                """,
                (api_key_hash,),
            )
            await self._pool.commit()
        logger.debug("Credentials cleared")

    async def save_chatwoot_config(
        self, api_key_hash: str, config: Optional[dict]
    ) -> None:
        logger.debug(f"Saving Chatwoot config for tenant: hash={api_key_hash[:16]}...")
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE tenants SET chatwoot_config = $1 WHERE api_key_hash = $2",
                    json.dumps(config) if config else None,
                    api_key_hash,
                )
        else:
            await self._pool.execute(
                "UPDATE tenants SET chatwoot_config = ? WHERE api_key_hash = ?",
                (json.dumps(config) if config else None, api_key_hash),
            )
            await self._pool.commit()
        logger.debug("Chatwoot config saved")

    async def save_global_config(self, key: str, value: dict) -> None:
        logger.debug(f"Saving global config: key={key}")
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO global_config (key, value, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()
                    """,
                    key,
                    json.dumps(value),
                )
        else:
            await self._pool.execute(
                """
                INSERT OR REPLACE INTO global_config (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
                """,
                (key, json.dumps(value)),
            )
            await self._pool.commit()
        logger.debug(f"Global config saved: key={key}")

    async def get_global_config(self, key: str) -> Optional[dict]:
        logger.debug(f"Getting global config: key={key}")
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT value FROM global_config WHERE key = $1", key
                )
                if row:
                    value = row["value"]
                    if isinstance(value, str):
                        return json.loads(value)
                    return value
        else:
            cursor = await self._pool.execute(
                "SELECT value FROM global_config WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            if row:
                return json.loads(row[0])
        return None

    async def save_message(
        self,
        tenant_hash: str,
        message_id: str,
        from_jid: str,
        chat_jid: str,
        is_group: bool = False,
        push_name: Optional[str] = None,
        text: str = "",
        msg_type: str = "text",
        timestamp: int = 0,
        direction: str = "inbound",
        media_url: Optional[str] = None,
    ) -> int:
        from ..utils.phone import normalize_phone, extract_phone_from_jid

        if self._is_postgres:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO messages (tenant_hash, message_id, from_jid, chat_jid, is_group, push_name, text, msg_type, timestamp, direction, media_url)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    RETURNING id
                    """,
                    tenant_hash,
                    message_id,
                    from_jid,
                    chat_jid,
                    is_group,
                    push_name,
                    text,
                    msg_type,
                    timestamp,
                    direction,
                    media_url,
                )
                msg_id = row["id"]
        else:
            cursor = await self._pool.execute(
                """
                INSERT INTO messages (tenant_hash, message_id, from_jid, chat_jid, is_group, push_name, text, msg_type, timestamp, direction, media_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_hash,
                    message_id,
                    from_jid,
                    chat_jid,
                    1 if is_group else 0,
                    push_name,
                    text,
                    msg_type,
                    timestamp,
                    direction,
                    media_url,
                ),
            )
            await self._pool.commit()
            msg_id = cursor.lastrowid

        phone = extract_phone_from_jid(chat_jid)
        normalized_phone = normalize_phone(phone)
        if normalized_phone:
            await self.upsert_contact(
                tenant_hash=tenant_hash,
                phone=normalized_phone,
                name=push_name,
                chat_jid=chat_jid,
                is_group=is_group,
            )

        return msg_id

    async def list_messages(
        self,
        tenant_hash: Optional[str] = None,
        chat_jid: Optional[str] = None,
        direction: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                conditions = []
                params = []
                param_idx = 1

                if tenant_hash:
                    conditions.append(f"tenant_hash = ${param_idx}")
                    params.append(tenant_hash)
                    param_idx += 1
                if chat_jid:
                    conditions.append(f"chat_jid = ${param_idx}")
                    params.append(chat_jid)
                    param_idx += 1
                if direction:
                    conditions.append(f"direction = ${param_idx}")
                    params.append(direction)
                    param_idx += 1
                if search:
                    conditions.append(f"text ILIKE ${param_idx}")
                    params.append(f"%{search}%")
                    param_idx += 1

                where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

                count_row = await conn.fetchrow(
                    f"SELECT COUNT(*) as count FROM messages {where_clause}", *params
                )
                total = count_row["count"]

                params.extend([limit, offset])
                rows = await conn.fetch(
                    f"""
                    SELECT id, tenant_hash, message_id, from_jid, chat_jid, is_group, push_name, text, msg_type, timestamp, direction, created_at
                    FROM messages {where_clause}
                    ORDER BY created_at DESC
                    LIMIT ${param_idx} OFFSET ${param_idx + 1}
                    """,
                    *params,
                )
                messages = [dict(row) for row in rows]
                return messages, total
        else:
            conditions = []
            params = []

            if tenant_hash:
                conditions.append("tenant_hash = ?")
                params.append(tenant_hash)
            if chat_jid:
                conditions.append("chat_jid = ?")
                params.append(chat_jid)
            if direction:
                conditions.append("direction = ?")
                params.append(direction)
            if search:
                conditions.append("text LIKE ?")
                params.append(f"%{search}%")

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            async with self._pool.execute(
                f"SELECT COUNT(*) FROM messages {where_clause}",
                params,
            ) as cursor:
                count_row = await cursor.fetchone()
                total = count_row[0] if count_row else 0

            params.extend([limit, offset])
            async with self._pool.execute(
                f"""
                SELECT id, tenant_hash, message_id, from_jid, chat_jid, is_group, push_name, text, msg_type, timestamp, direction, created_at
                FROM messages {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ) as cursor:
                rows = await cursor.fetchall()
                messages = [
                    {
                        "id": row[0],
                        "tenant_hash": row[1],
                        "message_id": row[2],
                        "from_jid": row[3],
                        "chat_jid": row[4],
                        "is_group": bool(row[5]),
                        "push_name": row[6],
                        "text": row[7],
                        "msg_type": row[8],
                        "timestamp": row[9],
                        "direction": row[10],
                        "created_at": row[11],
                    }
                    for row in rows
                ]
                return messages, total

    async def delete_message(self, message_id: int) -> bool:
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM messages WHERE id = $1", message_id
                )
                return result.split()[-1] != "0"
        else:
            cursor = await self._pool.execute(
                "DELETE FROM messages WHERE id = ?", (message_id,)
            )
            await self._pool.commit()
            return cursor.rowcount > 0

    async def upsert_contact(
        self,
        tenant_hash: str,
        phone: str,
        name: Optional[str],
        chat_jid: str,
        is_group: bool = False,
        message_time: Optional[datetime] = None,
    ) -> None:
        """
        Insert or update a contact.
        Updates name only if the new name is not empty/None.
        """
        if message_time is None:
            message_time = datetime.now(UTC)

        if self._is_postgres:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO contacts (tenant_hash, phone, name, chat_jid, is_group, last_message_at, message_count, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, 1, NOW(), NOW())
                    ON CONFLICT (tenant_hash, phone) DO UPDATE SET
                        name = CASE WHEN EXCLUDED.name IS NOT NULL AND EXCLUDED.name != '' THEN EXCLUDED.name ELSE contacts.name END,
                        chat_jid = EXCLUDED.chat_jid,
                        is_group = EXCLUDED.is_group,
                        last_message_at = EXCLUDED.last_message_at,
                        message_count = contacts.message_count + 1,
                        updated_at = NOW()
                    """,
                    tenant_hash,
                    phone,
                    name,
                    chat_jid,
                    is_group,
                    message_time,
                )
        else:
            await self._pool.execute(
                """
                INSERT INTO contacts (tenant_hash, phone, name, chat_jid, is_group, last_message_at, message_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(tenant_hash, phone) DO UPDATE SET
                    name = CASE WHEN excluded.name IS NOT NULL AND excluded.name != '' THEN excluded.name ELSE contacts.name END,
                    chat_jid = excluded.chat_jid,
                    is_group = excluded.is_group,
                    last_message_at = excluded.last_message_at,
                    message_count = contacts.message_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    tenant_hash,
                    phone,
                    name,
                    chat_jid,
                    1 if is_group else 0,
                    message_time.isoformat(),
                ),
            )
            await self._pool.commit()

    async def get_contact_by_phone(
        self, tenant_hash: str, phone: str
    ) -> Optional[dict]:
        """Get a contact by normalized phone number."""
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT id, tenant_hash, phone, name, chat_jid, is_group, 
                           last_message_at, message_count, created_at, updated_at
                    FROM contacts
                    WHERE tenant_hash = $1 AND phone = $2
                    """,
                    tenant_hash,
                    phone,
                )
                if row:
                    return {
                        "id": row["id"],
                        "tenant_hash": row["tenant_hash"],
                        "phone": row["phone"],
                        "name": row["name"],
                        "chat_jid": row["chat_jid"],
                        "is_group": row["is_group"],
                        "last_message_at": row["last_message_at"],
                        "message_count": row["message_count"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
                return None
        else:
            async with self._pool.execute(
                """
                SELECT id, tenant_hash, phone, name, chat_jid, is_group, 
                       last_message_at, message_count, created_at, updated_at
                FROM contacts
                WHERE tenant_hash = ? AND phone = ?
                """,
                (tenant_hash, phone),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "tenant_hash": row[1],
                        "phone": row[2],
                        "name": row[3],
                        "chat_jid": row[4],
                        "is_group": bool(row[5]),
                        "last_message_at": row[6],
                        "message_count": row[7],
                        "created_at": row[8],
                        "updated_at": row[9],
                    }
                return None

    async def populate_contacts_from_messages(
        self, tenant_hash: Optional[str] = None
    ) -> int:
        """
        Populate contacts table from existing messages.
        If tenant_hash is provided, only populate for that tenant.
        Returns the number of contacts created/updated.
        """
        from ..utils.phone import normalize_phone, extract_phone_from_jid

        count = 0
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                if tenant_hash:
                    rows = await conn.fetch(
                        """
                        SELECT DISTINCT tenant_hash, chat_jid, push_name, is_group, MAX(created_at) as last_msg
                        FROM messages
                        WHERE tenant_hash = $1 AND chat_jid IS NOT NULL AND chat_jid != ''
                        GROUP BY tenant_hash, chat_jid, push_name, is_group
                        """,
                        tenant_hash,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT DISTINCT tenant_hash, chat_jid, push_name, is_group, MAX(created_at) as last_msg
                        FROM messages
                        WHERE chat_jid IS NOT NULL AND chat_jid != ''
                        GROUP BY tenant_hash, chat_jid, push_name, is_group
                        """
                    )

                for row in rows:
                    phone = extract_phone_from_jid(row["chat_jid"])
                    if not phone:
                        continue
                    normalized = normalize_phone(phone)
                    if not normalized:
                        continue

                    await conn.execute(
                        """
                        INSERT INTO contacts (tenant_hash, phone, name, chat_jid, is_group, last_message_at, message_count, created_at, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, 1, NOW(), NOW())
                        ON CONFLICT (tenant_hash, phone) DO UPDATE SET
                            name = CASE WHEN EXCLUDED.name IS NOT NULL AND EXCLUDED.name != '' THEN EXCLUDED.name ELSE contacts.name END,
                            chat_jid = EXCLUDED.chat_jid,
                            last_message_at = GREATEST(contacts.last_message_at, EXCLUDED.last_message_at),
                            message_count = contacts.message_count + 1,
                            updated_at = NOW()
                        """,
                        row["tenant_hash"],
                        normalized,
                        row["push_name"],
                        row["chat_jid"],
                        row["is_group"],
                        row["last_msg"],
                    )
                    count += 1
        else:
            if tenant_hash:
                cursor = await self._pool.execute(
                    """
                    SELECT DISTINCT tenant_hash, chat_jid, push_name, is_group, MAX(created_at) as last_msg
                    FROM messages
                    WHERE tenant_hash = ? AND chat_jid IS NOT NULL AND chat_jid != ''
                    GROUP BY tenant_hash, chat_jid, push_name, is_group
                    """,
                    (tenant_hash,),
                )
            else:
                cursor = await self._pool.execute(
                    """
                    SELECT DISTINCT tenant_hash, chat_jid, push_name, is_group, MAX(created_at) as last_msg
                    FROM messages
                    WHERE chat_jid IS NOT NULL AND chat_jid != ''
                    GROUP BY tenant_hash, chat_jid, push_name, is_group
                    """
                )
            rows = await cursor.fetchall()

            for row in rows:
                phone = extract_phone_from_jid(row[1])
                if not phone:
                    continue
                normalized = normalize_phone(phone)
                if not normalized:
                    continue

                await self._pool.execute(
                    """
                    INSERT INTO contacts (tenant_hash, phone, name, chat_jid, is_group, last_message_at, message_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(tenant_hash, phone) DO UPDATE SET
                        name = CASE WHEN excluded.name IS NOT NULL AND excluded.name != '' THEN excluded.name ELSE contacts.name END,
                        chat_jid = excluded.chat_jid,
                        last_message_at = CASE 
                            WHEN contacts.last_message_at IS NULL THEN excluded.last_message_at
                            WHEN excluded.last_message_at IS NULL THEN contacts.last_message_at
                            WHEN excluded.last_message_at > contacts.last_message_at THEN excluded.last_message_at
                            ELSE contacts.last_message_at
                        END,
                        message_count = contacts.message_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        row[0],
                        normalized,
                        row[2],
                        row[1],
                        1 if row[3] else 0,
                        row[4],
                    ),
                )
                count += 1
            await self._pool.commit()

        logger.info(f"Populated {count} contacts from messages")
        return count

    async def get_recent_chats(
        self,
        tenant_hash: str,
        limit: int = 50,
    ) -> list[dict]:
        """
        Get recent chats from the contacts table (deduplicated by normalized phone).
        Returns contacts with their name, phone, chat_jid, and metadata.
        """
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT 
                        phone,
                        name,
                        chat_jid,
                        is_group,
                        last_message_at,
                        message_count
                    FROM contacts
                    WHERE tenant_hash = $1 AND phone IS NOT NULL AND phone != ''
                    ORDER BY last_message_at DESC NULLS LAST
                    LIMIT $2
                    """,
                    tenant_hash,
                    limit,
                )
                return [
                    {
                        "phone": row["phone"],
                        "push_name": row["name"],
                        "chat_jid": row["chat_jid"],
                        "is_group": row["is_group"],
                        "last_message_at": row["last_message_at"],
                        "message_count": row["message_count"],
                    }
                    for row in rows
                ]
        else:
            async with self._pool.execute(
                """
                SELECT 
                    phone,
                    name,
                    chat_jid,
                    is_group,
                    last_message_at,
                    message_count
                FROM contacts
                WHERE tenant_hash = ? AND phone IS NOT NULL AND phone != ''
                ORDER BY last_message_at DESC
                LIMIT ?
                """,
                (tenant_hash, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "phone": row[0],
                        "push_name": row[1],
                        "chat_jid": row[2],
                        "is_group": bool(row[3]),
                        "last_message_at": row[4],
                        "message_count": row[5],
                    }
                    for row in rows
                ]

    async def save_webhook_attempt(
        self,
        tenant_hash: str,
        url: str,
        event_type: str,
        success: bool,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None,
        attempt_number: int = 1,
        latency_ms: Optional[int] = None,
        payload_preview: Optional[str] = None,
    ) -> int:
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO webhook_attempts (tenant_hash, url, event_type, success, status_code, error_message, attempt_number, latency_ms, payload_preview)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING id
                    """,
                    tenant_hash,
                    url,
                    event_type,
                    success,
                    status_code,
                    error_message,
                    attempt_number,
                    latency_ms,
                    payload_preview,
                )
                return row["id"]
        else:
            cursor = await self._pool.execute(
                """
                INSERT INTO webhook_attempts (tenant_hash, url, event_type, success, status_code, error_message, attempt_number, latency_ms, payload_preview)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_hash,
                    url,
                    event_type,
                    1 if success else 0,
                    status_code,
                    error_message,
                    attempt_number,
                    latency_ms,
                    payload_preview,
                ),
            )
            await self._pool.commit()
            return cursor.lastrowid

    async def list_webhook_attempts(
        self,
        tenant_hash: Optional[str] = None,
        url: Optional[str] = None,
        success: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                conditions = []
                params = []
                param_idx = 1

                if tenant_hash:
                    conditions.append(f"tenant_hash = ${param_idx}")
                    params.append(tenant_hash)
                    param_idx += 1
                if url:
                    conditions.append(f"url = ${param_idx}")
                    params.append(url)
                    param_idx += 1
                if success is not None:
                    conditions.append(f"success = ${param_idx}")
                    params.append(success)
                    param_idx += 1

                where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

                count_row = await conn.fetchrow(
                    f"SELECT COUNT(*) as count FROM webhook_attempts {where_clause}",
                    *params,
                )
                total = count_row["count"]

                params.extend([limit, offset])
                rows = await conn.fetch(
                    f"""
                    SELECT id, tenant_hash, url, event_type, success, status_code, error_message, attempt_number, latency_ms, payload_preview, created_at
                    FROM webhook_attempts {where_clause}
                    ORDER BY created_at DESC
                    LIMIT ${param_idx} OFFSET ${param_idx + 1}
                    """,
                    *params,
                )
                attempts = [dict(row) for row in rows]
                return attempts, total
        else:
            conditions = []
            params = []

            if tenant_hash:
                conditions.append("tenant_hash = ?")
                params.append(tenant_hash)
            if url:
                conditions.append("url = ?")
                params.append(url)
            if success is not None:
                conditions.append("success = ?")
                params.append(1 if success else 0)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            async with self._pool.execute(
                f"SELECT COUNT(*) FROM webhook_attempts {where_clause}",
                params,
            ) as cursor:
                count_row = await cursor.fetchone()
                total = count_row[0] if count_row else 0

            params.extend([limit, offset])
            async with self._pool.execute(
                f"""
                SELECT id, tenant_hash, url, event_type, success, status_code, error_message, attempt_number, latency_ms, payload_preview, created_at
                FROM webhook_attempts {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ) as cursor:
                rows = await cursor.fetchall()
                attempts = [
                    {
                        "id": row[0],
                        "tenant_hash": row[1],
                        "url": row[2],
                        "event_type": row[3],
                        "success": bool(row[4]),
                        "status_code": row[5],
                        "error_message": row[6],
                        "attempt_number": row[7],
                        "latency_ms": row[8],
                        "payload_preview": row[9],
                        "created_at": row[10],
                    }
                    for row in rows
                ]
                return attempts, total

    async def get_webhook_stats(self, url: Optional[str] = None) -> dict:
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                if url:
                    row = await conn.fetchrow(
                        """
                        SELECT 
                            COUNT(*) as total,
                            COUNT(*) FILTER (WHERE success) as success_count,
                            COUNT(*) FILTER (WHERE NOT success) as fail_count,
                            AVG(latency_ms) FILTER (WHERE latency_ms IS NOT NULL) as avg_latency,
                            MAX(created_at) FILTER (WHERE success) as last_success,
                            MAX(created_at) FILTER (WHERE NOT success) as last_failure
                        FROM webhook_attempts WHERE url = $1
                        """,
                        url,
                    )
                else:
                    row = await conn.fetchrow(
                        """
                        SELECT 
                            COUNT(*) as total,
                            COUNT(*) FILTER (WHERE success) as success_count,
                            COUNT(*) FILTER (WHERE NOT success) as fail_count,
                            AVG(latency_ms) FILTER (WHERE latency_ms IS NOT NULL) as avg_latency
                        FROM webhook_attempts
                        """
                    )
                return dict(row) if row else {}
        else:
            async with self._pool.execute(
                "SELECT COUNT(*), SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END), AVG(latency_ms) FROM webhook_attempts"
            ) as cursor:
                row = await cursor.fetchone()
                return {
                    "total": row[0] or 0,
                    "success_count": row[1] or 0,
                    "fail_count": (row[0] or 0) - (row[1] or 0),
                    "avg_latency": row[2],
                }

    async def create_admin_session(
        self,
        session_id: str,
        expires_at: datetime,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO admin_sessions (id, expires_at, user_agent, ip_address)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (id) DO UPDATE SET expires_at = $2, user_agent = $3, ip_address = $4
                    """,
                    session_id,
                    expires_at,
                    user_agent,
                    ip_address,
                )
        else:
            await self._pool.execute(
                """
                INSERT OR REPLACE INTO admin_sessions (id, expires_at, user_agent, ip_address)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, expires_at.isoformat(), user_agent, ip_address),
            )
            await self._pool.commit()

    async def get_admin_session(self, session_id: str) -> Optional[dict]:
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, created_at, expires_at, user_agent, ip_address FROM admin_sessions WHERE id = $1 AND expires_at > NOW()",
                    session_id,
                )
                return dict(row) if row else None
        else:
            async with self._pool.execute(
                "SELECT id, created_at, expires_at, user_agent, ip_address FROM admin_sessions WHERE id = ? AND expires_at > datetime('now')",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "created_at": row[1],
                        "expires_at": row[2],
                        "user_agent": row[3],
                        "ip_address": row[4],
                    }
                return None

    async def delete_admin_session(self, session_id: str) -> None:
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM admin_sessions WHERE id = $1", session_id
                )
        else:
            await self._pool.execute(
                "DELETE FROM admin_sessions WHERE id = ?", (session_id,)
            )
            await self._pool.commit()

    async def cleanup_old_data(self, days: int = 7) -> dict:
        cleaned = {}
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM webhook_attempts WHERE created_at < NOW() - INTERVAL '1 day' * $1",
                    days,
                )
                cleaned["webhook_attempts"] = int(result.split()[-1])
                result = await conn.execute(
                    "DELETE FROM messages WHERE created_at < NOW() - INTERVAL '1 day' * $1",
                    days,
                )
                cleaned["messages"] = int(result.split()[-1])
                result = await conn.execute(
                    "DELETE FROM admin_sessions WHERE expires_at < NOW()"
                )
                cleaned["admin_sessions"] = int(result.split()[-1])
        else:
            cursor = await self._pool.execute(
                "DELETE FROM webhook_attempts WHERE datetime(created_at) < datetime('now', ?)",
                (f"-{days} days",),
            )
            cleaned["webhook_attempts"] = cursor.rowcount
            cursor = await self._pool.execute(
                "DELETE FROM messages WHERE datetime(created_at) < datetime('now', ?)",
                (f"-{days} days",),
            )
            cleaned["messages"] = cursor.rowcount
            cursor = await self._pool.execute(
                "DELETE FROM admin_sessions WHERE datetime(expires_at) < datetime('now')"
            )
            cleaned["admin_sessions"] = cursor.rowcount
            await self._pool.commit()
        logger.info(f"Cleaned up old data: {cleaned}")
        return cleaned

    async def mark_message_chatwoot_synced(self, message_id: int) -> None:
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE messages SET chatwoot_synced_at = NOW() WHERE id = $1",
                    message_id,
                )
        else:
            await self._pool.execute(
                "UPDATE messages SET chatwoot_synced_at = datetime('now') WHERE id = ?",
                (message_id,),
            )
            await self._pool.commit()

    async def get_unsynced_messages_for_chatwoot(
        self,
        tenant_hash: str,
        days_limit: int = 3,
        limit: int = 1000,
    ) -> list[dict]:
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, tenant_hash, message_id, from_jid, chat_jid, is_group, push_name, 
                           text, msg_type, timestamp, direction, created_at, media_url
                    FROM messages
                    WHERE tenant_hash = $1 
                      AND chatwoot_synced_at IS NULL
                      AND is_group = FALSE
                      AND created_at >= NOW() - INTERVAL '%s days'
                    ORDER BY created_at ASC
                    LIMIT $2
                    """
                    % days_limit,
                    tenant_hash,
                    limit,
                )
                return [dict(row) for row in rows]
        else:
            async with self._pool.execute(
                """
                SELECT id, tenant_hash, message_id, from_jid, chat_jid, is_group, push_name, 
                       text, msg_type, timestamp, direction, created_at, media_url
                FROM messages
                WHERE tenant_hash = ? 
                  AND chatwoot_synced_at IS NULL
                  AND is_group = 0
                  AND datetime(created_at) >= datetime('now', ?)
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (tenant_hash, f"-{days_limit} days", limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "id": row[0],
                        "tenant_hash": row[1],
                        "message_id": row[2],
                        "from_jid": row[3],
                        "chat_jid": row[4],
                        "is_group": bool(row[5]),
                        "push_name": row[6],
                        "text": row[7],
                        "msg_type": row[8],
                        "timestamp": row[9],
                        "direction": row[10],
                        "created_at": row[11],
                        "media_url": row[12] if len(row) > 12 else None,
                    }
                    for row in rows
                ]
