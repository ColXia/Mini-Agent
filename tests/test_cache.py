"""Tests for cache layer."""

from __future__ import annotations

import asyncio
import time

import pytest

from mini_agent.utils.cache import (
    AsyncLRUCache,
    CacheStats,
    LRUCache,
    cache_key,
    cached,
)


def test_lru_cache_basic_get_set():
    cache = LRUCache[str, int](max_size=3)

    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    assert cache.get("a") == 1
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_lru_cache_eviction():
    cache = LRUCache[str, int](max_size=2)

    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)  # Should evict "a"

    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_lru_cache_lru_order():
    cache = LRUCache[str, int](max_size=2)

    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # Access "a", making it more recent
    cache.set("c", 3)  # Should evict "b" not "a"

    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3


def test_lru_cache_ttl():
    cache = LRUCache[str, int](default_ttl_seconds=0.1)

    cache.set("a", 1)
    assert cache.get("a") == 1

    time.sleep(0.15)
    assert cache.get("a") is None


def test_lru_cache_delete():
    cache = LRUCache[str, int](max_size=3)

    cache.set("a", 1)
    assert cache.delete("a") is True
    assert cache.get("a") is None
    assert cache.delete("a") is False


def test_lru_cache_clear():
    cache = LRUCache[str, int](max_size=3)

    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()

    assert cache.get("a") is None
    assert cache.get("b") is None


def test_lru_cache_stats():
    cache = LRUCache[str, int](max_size=2)

    cache.set("a", 1)
    cache.get("a")  # hit
    cache.get("b")  # miss
    cache.set("b", 2)
    cache.set("c", 3)  # eviction

    stats = cache.stats()
    assert stats.hits == 1
    assert stats.misses == 1
    assert stats.evictions == 1
    assert stats.size == 2


def test_lru_cache_cleanup_expired():
    cache = LRUCache[str, int](max_size=10)

    cache.set("a", 1, ttl_seconds=0.1)
    cache.set("b", 2, ttl_seconds=0.1)
    cache.set("c", 3)  # No TTL

    time.sleep(0.15)
    removed = cache.cleanup_expired()

    assert removed == 2
    assert cache.get("a") is None
    assert cache.get("b") is None
    assert cache.get("c") == 3


def test_cache_key_deterministic():
    key1 = cache_key("a", "b", c=1)
    key2 = cache_key("a", "b", c=1)
    assert key1 == key2


def test_cache_key_different():
    key1 = cache_key("a", "b")
    key2 = cache_key("a", "c")
    assert key1 != key2


def test_cached_decorator():
    cache = LRUCache[str, int](max_size=10)
    call_count = 0

    @cached(cache)
    def expensive_func(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x * 2

    result1 = expensive_func(5)
    result2 = expensive_func(5)

    assert result1 == 10
    assert result2 == 10
    assert call_count == 1  # Only called once due to cache


@pytest.mark.asyncio
async def test_async_lru_cache_basic():
    cache = AsyncLRUCache[str, int](max_size=3)

    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.set("c", 3)

    assert await cache.get("a") == 1
    assert await cache.get("b") == 2
    assert await cache.get("c") == 3


@pytest.mark.asyncio
async def test_async_lru_cache_eviction():
    cache = AsyncLRUCache[str, int](max_size=2)

    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.set("c", 3)  # Should evict "a"

    assert await cache.get("a") is None
    assert await cache.get("b") == 2


@pytest.mark.asyncio
async def test_async_lru_cache_ttl():
    cache = AsyncLRUCache[str, int](default_ttl_seconds=0.1)

    await cache.set("a", 1)
    assert await cache.get("a") == 1

    await asyncio.sleep(0.15)
    assert await cache.get("a") is None


@pytest.mark.asyncio
async def test_async_lru_cache_stats():
    cache = AsyncLRUCache[str, int](max_size=2)

    await cache.set("a", 1)
    await cache.get("a")  # hit
    await cache.get("b")  # miss

    stats = await cache.stats()
    assert stats.hits == 1
    assert stats.misses == 1
