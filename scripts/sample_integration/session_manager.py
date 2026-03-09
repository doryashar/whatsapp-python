#!/usr/bin/env python3
"""
Session manager for opencode WhatsApp integration.
Manages mappings between WhatsApp chat IDs and opencode session IDs using SQLite.
"""

import aiosqlite
import logging
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages opencode sessions for WhatsApp chats."""

    def __init__(self, db_path: str = "./data/sessions.db"):
        self.db_path = db_path
        self.db: Optional[aiosqlite.Connection] = None

    async def init_db(self) -> None:
        """Initialize SQLite database and create tables."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db = await aiosqlite.connect(self.db_path)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_jid TEXT UNIQUE NOT NULL,
                opencode_session_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_jid ON sessions(chat_jid)
        """)
        await self.db.commit()
        logger.info(f"Database initialized at {self.db_path}")

    async def close(self) -> None:
        """Close database connection."""
        if self.db:
            await self.db.close()
            logger.info("Database connection closed")

    async def get_session(self, chat_jid: str) -> Optional[str]:
        """
        Get opencode session ID for a WhatsApp chat.

        Args:
            chat_jid: WhatsApp chat JID (e.g., "1234567890@s.whatsapp.net")

        Returns:
            OpenCode session ID if exists, None otherwise
        """
        if not self.db:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        async with self.db.execute(
            "SELECT opencode_session_id FROM sessions WHERE chat_jid = ?", (chat_jid,)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            session_id = row[0]
            await self.update_last_used(chat_jid)
            logger.debug(f"Found session for {chat_jid}: {session_id}")
            return session_id

        logger.debug(f"No session found for {chat_jid}")
        return None

    async def create_session(self, chat_jid: str, opencode_session_id: str) -> None:
        """
        Create a new session mapping.

        Args:
            chat_jid: WhatsApp chat JID
            opencode_session_id: OpenCode session ID
        """
        if not self.db:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        await self.db.execute(
            """INSERT OR REPLACE INTO sessions 
               (chat_jid, opencode_session_id, created_at, last_used_at)
               VALUES (?, ?, ?, ?)""",
            (chat_jid, opencode_session_id, datetime.now(UTC), datetime.now(UTC)),
        )
        await self.db.commit()
        logger.info(f"Created session mapping: {chat_jid} -> {opencode_session_id}")

    async def update_last_used(self, chat_jid: str) -> None:
        """Update last_used_at timestamp for a chat."""
        if not self.db:
            return

        await self.db.execute(
            "UPDATE sessions SET last_used_at = ? WHERE chat_jid = ?",
            (datetime.now(UTC), chat_jid),
        )
        await self.db.commit()

    async def delete_session(self, chat_jid: str) -> bool:
        """
        Delete a session mapping.

        Args:
            chat_jid: WhatsApp chat JID

        Returns:
            True if session was deleted, False if not found
        """
        if not self.db:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        cursor = await self.db.execute(
            "DELETE FROM sessions WHERE chat_jid = ?", (chat_jid,)
        )
        await self.db.commit()

        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Deleted session for {chat_jid}")
        return deleted

    async def list_sessions(self) -> list[dict]:
        """
        List all active sessions.

        Returns:
            List of session dictionaries
        """
        if not self.db:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        sessions = []
        async with self.db.execute(
            """SELECT chat_jid, opencode_session_id, created_at, last_used_at 
               FROM sessions ORDER BY last_used_at DESC"""
        ) as cursor:
            async for row in cursor:
                sessions.append(
                    {
                        "chat_jid": row[0],
                        "opencode_session_id": row[1],
                        "created_at": row[2],
                        "last_used_at": row[3],
                    }
                )

        logger.debug(f"Listed {len(sessions)} sessions")
        return sessions

    async def cleanup_old_sessions(self, days_old: int = 30) -> int:
        """
        Remove sessions older than specified days.

        Args:
            days_old: Number of days after which to delete sessions

        Returns:
            Number of sessions deleted
        """
        if not self.db:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        cutoff = datetime.now(UTC) - timedelta(days=days_old)
        cursor = await self.db.execute(
            "DELETE FROM sessions WHERE last_used_at < ?", (cutoff,)
        )
        await self.db.commit()

        deleted_count = cursor.rowcount
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old sessions")
        return deleted_count
