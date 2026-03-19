import asyncio
import pytest
import time
from unittest.mock import Mock, AsyncMock

from src.chatwoot import ChatwootConfig
from src.chatwoot.client import ChatwootClient
from src.chatwoot.models import ChatwootConversation


@pytest.fixture
def config():
    return ChatwootConfig(
        enabled=True,
        url="https://chatwoot.example.com",
        token="test_token",
        account_id="1",
        inbox_id=1,
    )


class TestCacheRaceCondition:
    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self, config):
        client = ChatwootClient(config)
        conv = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        async def cache_many():
            for i in range(100):
                await client._cache_conversation(i, conv)

        async def read_many():
            for i in range(100):
                await client._get_cached_conversation(i)

        await asyncio.gather(cache_many(), read_many())

    @pytest.mark.asyncio
    async def test_concurrent_cache_and_clear(self, config):
        client = ChatwootClient(config)
        conv = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        for i in range(50):
            await client._cache_conversation(i, conv)

        async def clear_loop():
            for _ in range(10):
                await client.clear_cache()

        async def read_loop():
            for _ in range(10):
                await client._get_cached_conversation(25)

        await asyncio.gather(clear_loop(), read_loop())

    @pytest.mark.asyncio
    async def test_cache_lock_prevents_corruption(self, config):
        client = ChatwootClient(config)
        assert isinstance(client._cache_lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_cache_expiry_during_concurrent_read(self, config):
        client = ChatwootClient(config)
        conv = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        client._conversation_cache[1] = (conv, time.time() - 2000)

        async def read_expired():
            return await client._get_cached_conversation(1)

        results = await asyncio.gather(read_expired(), read_expired())
        assert results[0] is None
        assert results[1] is None
        assert 1 not in client._conversation_cache

    @pytest.mark.asyncio
    async def test_multiple_writers_same_key(self, config):
        client = ChatwootClient(config)
        conv1 = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )
        conv2 = ChatwootConversation(
            id=2, account_id=1, inbox_id=1, contact_id=1, status="pending"
        )

        async def write1():
            await client._cache_conversation(1, conv1)

        async def write2():
            await client._cache_conversation(1, conv2)

        await asyncio.gather(write1(), write2())

        cached = await client._get_cached_conversation(1)
        assert cached is not None
        assert cached.id in (1, 2)

    @pytest.mark.asyncio
    async def test_stale_entry_removed_on_read(self, config):
        client = ChatwootClient(config)
        conv = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        client._conversation_cache[99] = (conv, time.time() - 9999)
        assert 99 in client._conversation_cache

        result = await client._get_cached_conversation(99)
        assert result is None
        assert 99 not in client._conversation_cache

    @pytest.mark.asyncio
    async def test_cache_conversation_is_async(self, config):
        client = ChatwootClient(config)
        conv = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        result = await client._cache_conversation(1, conv)
        assert 1 in client._conversation_cache

    @pytest.mark.asyncio
    async def test_clear_cache_is_async(self, config):
        client = ChatwootClient(config)
        conv = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        await client._cache_conversation(1, conv)
        await client.clear_cache()
        assert client._conversation_cache == {}
