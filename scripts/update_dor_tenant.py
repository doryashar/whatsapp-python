import asyncio
import asyncpg
import aiosqlite
from pathlib import Path
import os


async def update_dor_tenant():
    database_url = os.getenv("DATABASE_URL", "")
    data_dir = Path("data")

    if database_url.startswith(("postgresql://", "postgres://")):
        conn = await asyncpg.connect(database_url)
        try:
            result = await conn.execute(
                "UPDATE tenants SET connection_state = 'connected' WHERE name = 'dor'"
            )
            print(f"Updated 'dor' tenant in PostgreSQL: {result}")

            row = await conn.fetchrow(
                "SELECT name, connection_state FROM tenants WHERE name = 'dor'"
            )
            if row:
                print(f"Verified: {row['name']} - {row['connection_state']}")
            else:
                print("No tenant named 'dor' found")
        finally:
            await conn.close()
    else:
        db_path = data_dir / "sessions.db"
        if not db_path.exists():
            print(f"Database not found at {db_path}")
            return

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "UPDATE tenants SET connection_state = 'connected' WHERE name = 'dor'"
            )
            await db.commit()
            print(f"Updated 'dor' tenant in SQLite: {cursor.rowcount} row(s)")

            cursor = await db.execute(
                "SELECT name, connection_state FROM tenants WHERE name = 'dor'"
            )
            row = await cursor.fetchone()
            if row:
                print(f"Verified: {row[0]} - {row[1]}")
            else:
                print("No tenant named 'dor' found")


if __name__ == "__main__":
    asyncio.run(update_dor_tenant())
