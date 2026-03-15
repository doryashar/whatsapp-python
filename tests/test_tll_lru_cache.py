import pytest
import time

from src.chatwoot.integration import TTLLRUCache


class TestTTLLRUCache:
    def test_set_and_get(self):
        cache = TTLLRUCache(max_size=3, ttl_seconds=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self):
        cache = TTLLRUCache(max_size=3, ttl_seconds=60)
        assert cache.get("nonexistent") is None

    def test_lru_eviction(self):
        cache = TTLLRUCache(max_size=3, ttl_seconds=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_update_existing_key_moves_to_end(self):
        cache = TTLLRUCache(max_size=3, ttl_seconds=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key1", "updated1")
        cache.set("key4", "value4")
        assert cache.get("key1") == "updated1"
        assert cache.get("key2") is None

    def test_clear(self):
        cache = TTLLRUCache(max_size=3, ttl_seconds=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_ttl_expiration(self):
        cache = TTLLRUCache(max_size=3, ttl_seconds=0.1)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        time.sleep(0.15)
        assert cache.get("key1") is None

    def test_ttl_not_expired(self):
        cache = TTLLRUCache(max_size=3, ttl_seconds=1.0)
        cache.set("key1", "value1")
        time.sleep(0.1)
        assert cache.get("key1") == "value1"

    def test_int_key(self):
        cache = TTLLRUCache(max_size=3, ttl_seconds=60)
        cache.set(123, "int_value")
        assert cache.get(123) == "int_value"

    def test_mixed_key_types(self):
        cache = TTLLRUCache(max_size=10, ttl_seconds=60)
        cache.set("str_key", "str_value")
        cache.set(123, "int_value")
        assert cache.get("str_key") == "str_value"
        assert cache.get(123) == "int_value"

    def test_access_moves_to_end(self):
        cache = TTLLRUCache(max_size=3, ttl_seconds=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.get("key1")
        cache.set("key4", "value4")
        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None
