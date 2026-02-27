import json
from datetime import datetime
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, database_url: str, data_dir: Path):
        self.database_url = database_url
        self.data_dir = data_dir
        self._pool: Any = None
        self._is_postgres = database_url.startswith(("postgresql://", "postgres://"))

    async def connect(self) -> None:
        if self._is_postgres:
            import asyncpg

            self._pool = await asyncpg.create_pool(self.database_url)
            await self._create_tables_postgres()
        else:
            import aiosqlite

            self.data_dir.mkdir(parents=True, exist_ok=True)
            db_path = self.data_dir / "whatsapp.db"
            self._pool = await aiosqlite.connect(db_path)
            await self._pool.execute("PRAGMA journal_mode=WAL")
            await self._create_tables_sqlite()

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def _create_tables_postgres(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    api_key_hash TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    webhook_urls JSONB DEFAULT '[]'
                )
            """)

    async def _create_tables_sqlite(self) -> None:
        await self._pool.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                api_key_hash TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                webhook_urls TEXT DEFAULT '[]'
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
                INSERT OR REPLACE INTO tenants (api_key_hash, name, created_at, webhook_urls)
                VALUES (?, ?, ?, ?)
                """,
                (api_key_hash, name, created_at.isoformat(), json.dumps(webhook_urls)),
            )
            await self._pool.commit()

    async def load_tenants(self) -> list[dict]:
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT api_key_hash, name, created_at, webhook_urls FROM tenants"
                )
                return [
                    {
                        "api_key_hash": row["api_key_hash"],
                        "name": row["name"],
                        "created_at": row["created_at"],
                        "webhook_urls": json.loads(row["webhook_urls"])
                        if isinstance(row["webhook_urls"], str)
                        else row["webhook_urls"],
                    }
                    for row in rows
                ]
        else:
            async with self._pool.execute(
                "SELECT api_key_hash, name, created_at, webhook_urls FROM tenants"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "api_key_hash": row[0],
                        "name": row[1],
                        "created_at": datetime.fromisoformat(row[2]),
                        "webhook_urls": json.loads(row[3]),
                    }
                    for row in rows
                ]

    async def delete_tenant(self, api_key_hash: str) -> bool:
        if self._is_postgres:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM tenants WHERE api_key_hash = $1", api_key_hash
                )
                return result.split()[-1] != "0"
        else:
            cursor = await self._pool.execute(
                "DELETE FROM tenants WHERE api_key_hash = ?",
                (api_key_hash,),
            )
            await self._pool.commit()
            return cursor.rowcount > 0

    async def update_webhooks(self, api_key_hash: str, webhook_urls: list[str]) -> None:
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
