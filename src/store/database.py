import json
from datetime import datetime
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
                creds_json TEXT
            )
        """)
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
                              last_connected_at, last_disconnected_at, has_auth, creds_json
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
                        "creds_json": row["creds_json"],
                    }
                    for row in rows
                ]
        else:
            async with self._pool.execute(
                """SELECT api_key_hash, name, created_at, webhook_urls,
                          connection_state, self_jid, self_phone, self_name,
                          last_connected_at, last_disconnected_at, has_auth, creds_json
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
        now = datetime.utcnow()

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
