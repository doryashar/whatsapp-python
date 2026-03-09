#!/usr/bin/env python3
"""
Unit tests for session manager.
"""

import asyncio
import os
import tempfile
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.sample_integration.session_manager import SessionManager


@pytest.fixture
async def session_manager():
    """Create a session manager with temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_sessions.db")
        manager = SessionManager(db_path)
        await manager.init_db()
        yield manager
        await manager.close()


@pytest.mark.asyncio
async def test_init_db(session_manager):
    """Test database initialization."""
    assert session_manager.db is not None

    sessions = await session_manager.list_sessions()
    assert sessions == []


@pytest.mark.asyncio
async def test_create_and_get_session(session_manager):
    """Test creating and retrieving a session."""
    chat_jid = "1234567890@s.whatsapp.net"
    opencode_session_id = "test_session_123"

    await session_manager.create_session(chat_jid, opencode_session_id)

    retrieved_id = await session_manager.get_session(chat_jid)
    assert retrieved_id == opencode_session_id


@pytest.mark.asyncio
async def test_get_nonexistent_session(session_manager):
    """Test retrieving a non-existent session."""
    chat_jid = "nonexistent@s.whatsapp.net"

    retrieved_id = await session_manager.get_session(chat_jid)
    assert retrieved_id is None


@pytest.mark.asyncio
async def test_update_session(session_manager):
    """Test updating an existing session."""
    chat_jid = "1234567890@s.whatsapp.net"
    old_session_id = "old_session"
    new_session_id = "new_session"

    await session_manager.create_session(chat_jid, old_session_id)

    await session_manager.create_session(chat_jid, new_session_id)

    retrieved_id = await session_manager.get_session(chat_jid)
    assert retrieved_id == new_session_id


@pytest.mark.asyncio
async def test_delete_session(session_manager):
    """Test deleting a session."""
    chat_jid = "1234567890@s.whatsapp.net"
    opencode_session_id = "test_session_123"

    await session_manager.create_session(chat_jid, opencode_session_id)

    deleted = await session_manager.delete_session(chat_jid)
    assert deleted is True

    retrieved_id = await session_manager.get_session(chat_jid)
    assert retrieved_id is None


@pytest.mark.asyncio
async def test_delete_nonexistent_session(session_manager):
    """Test deleting a non-existent session."""
    chat_jid = "nonexistent@s.whatsapp.net"

    deleted = await session_manager.delete_session(chat_jid)
    assert deleted is False


@pytest.mark.asyncio
async def test_list_sessions(session_manager):
    """Test listing all sessions."""
    sessions_data = [
        ("1234567890@s.whatsapp.net", "session_1"),
        ("9876543210@s.whatsapp.net", "session_2"),
        ("5555555555@s.whatsapp.net", "session_3"),
    ]

    for chat_jid, session_id in sessions_data:
        await session_manager.create_session(chat_jid, session_id)

    sessions = await session_manager.list_sessions()
    assert len(sessions) == 3

    chat_jids = [s["chat_jid"] for s in sessions]
    assert "1234567890@s.whatsapp.net" in chat_jids
    assert "9876543210@s.whatsapp.net" in chat_jids
    assert "5555555555@s.whatsapp.net" in chat_jids


@pytest.mark.asyncio
async def test_update_last_used(session_manager):
    """Test updating last_used_at timestamp."""
    chat_jid = "1234567890@s.whatsapp.net"
    opencode_session_id = "test_session_123"

    await session_manager.create_session(chat_jid, opencode_session_id)

    sessions_before = await session_manager.list_sessions()
    last_used_before = sessions_before[0]["last_used_at"]

    await asyncio.sleep(0.1)

    await session_manager.get_session(chat_jid)

    sessions_after = await session_manager.list_sessions()
    last_used_after = sessions_after[0]["last_used_at"]

    assert last_used_after >= last_used_before


@pytest.mark.asyncio
async def test_cleanup_old_sessions(session_manager):
    """Test cleaning up old sessions."""
    from datetime import datetime, timedelta, UTC

    chat_jid = "1234567890@s.whatsapp.net"
    opencode_session_id = "test_session_123"

    await session_manager.create_session(chat_jid, opencode_session_id)

    old_date = datetime.now(UTC) - timedelta(days=40)
    await session_manager.db.execute(
        "UPDATE sessions SET last_used_at = ? WHERE chat_jid = ?", (old_date, chat_jid)
    )
    await session_manager.db.commit()

    deleted_count = await session_manager.cleanup_old_sessions(days_old=30)
    assert deleted_count == 1

    retrieved_id = await session_manager.get_session(chat_jid)
    assert retrieved_id is None


@pytest.mark.asyncio
async def test_cleanup_keeps_recent_sessions(session_manager):
    """Test that cleanup doesn't delete recent sessions."""
    chat_jid = "1234567890@s.whatsapp.net"
    opencode_session_id = "test_session_123"

    await session_manager.create_session(chat_jid, opencode_session_id)

    deleted_count = await session_manager.cleanup_old_sessions(days_old=30)
    assert deleted_count == 0

    retrieved_id = await session_manager.get_session(chat_jid)
    assert retrieved_id == opencode_session_id


@pytest.mark.asyncio
async def test_database_not_initialized_error():
    """Test that operations fail if database not initialized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        manager = SessionManager(db_path)

        with pytest.raises(RuntimeError, match="Database not initialized"):
            await manager.get_session("test@s.whatsapp.net")

        with pytest.raises(RuntimeError, match="Database not initialized"):
            await manager.create_session("test@s.whatsapp.net", "session_id")

        with pytest.raises(RuntimeError, match="Database not initialized"):
            await manager.list_sessions()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
