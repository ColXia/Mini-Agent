"""High-performance caching layer with LRU eviction and TTL support."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable, Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class CacheEntry(Generic[V]):
    """Cache entry with TTL support."""

    value: V
    created_at: float
    expires_at: float | None = None
    access_count: int = 0
    last_accessed_at: float = 0.0

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def touch(self) -> None:
        self.access_count += 1
        self.last_accessed_at = time.time()


@dataclass
class CacheStats:
    """Cache statistics."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expired_removals: int = 0
    size: int = 0
    max_size: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


class LRUCache(Generic[K, V]):
    """Thread-safe LRU cache with TTL support."""

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl_seconds: float | None = None,
    ) -> None:
        self.max_size = max(1, int(max_size))
        self.default_ttl_seconds = default_ttl_seconds
        self._cache: OrderedDict[K, CacheEntry[V]] = OrderedDict()
        self._lock = RLock()
        self._stats = CacheStats(max_size=self.max_size)

    def get(self, key: K) -> V | None:
        """Get a value from cache, returning None if not found or expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats.misses += 1
                return None

            if entry.is_expired():
                del self._cache[key]
                self._stats.expired_removals += 1
                self._stats.misses += 1
                self._stats.size = len(self._cache)
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.touch()
            self._stats.hits += 1
            return entry.value

    def set(
        self,
        key: K,
        value: V,
        ttl_seconds: float | None = None,
    ) -> None:
        """Set a value in cache with optional TTL."""
        effective_ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds

        now = time.time()
        expires_at = now + effective_ttl if effective_ttl is not None else None

        entry = CacheEntry(
            value=value,
            created_at=now,
            expires_at=expires_at,
            last_accessed_at=now,
        )

        with self._lock:
            # Remove if exists (to update position)
            if key in self._cache:
                del self._cache[key]

            # Evict oldest if at capacity
            while len(self._cache) >= self.max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                self._stats.evictions += 1

            self._cache[key] = entry
            self._stats.size = len(self._cache)

    def delete(self, key: K) -> bool:
        """Delete a key from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats.size = len(self._cache)
                return True
            return False

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._cache.clear()
            self._stats.size = 0

    def cleanup_expired(self) -> int:
        """Remove all expired entries, return count removed."""
        removed = 0
        with self._lock:
            expired_keys = [
                k for k, v in self._cache.items() if v.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
                removed += 1
            self._stats.expired_removals += removed
            self._stats.size = len(self._cache)
        return removed

    def stats(self) -> CacheStats:
        """Get cache statistics."""
        with self._lock:
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                evictions=self._stats.evictions,
                expired_removals=self._stats.expired_removals,
                size=len(self._cache),
                max_size=self.max_size,
            )


class AsyncLRUCache(Generic[K, V]):
    """Async-compatible LRU cache with TTL support."""

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl_seconds: float | None = None,
    ) -> None:
        self.max_size = max(1, int(max_size))
        self.default_ttl_seconds = default_ttl_seconds
        self._cache: OrderedDict[K, CacheEntry[V]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._stats = CacheStats(max_size=self.max_size)

    async def get(self, key: K) -> V | None:
        """Get a value from cache."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats.misses += 1
                return None

            if entry.is_expired():
                del self._cache[key]
                self._stats.expired_removals += 1
                self._stats.misses += 1
                self._stats.size = len(self._cache)
                return None

            self._cache.move_to_end(key)
            entry.touch()
            self._stats.hits += 1
            return entry.value

    async def set(
        self,
        key: K,
        value: V,
        ttl_seconds: float | None = None,
    ) -> None:
        """Set a value in cache."""
        effective_ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds

        now = time.time()
        expires_at = now + effective_ttl if effective_ttl is not None else None

        entry = CacheEntry(
            value=value,
            created_at=now,
            expires_at=expires_at,
            last_accessed_at=now,
        )

        async with self._lock:
            if key in self._cache:
                del self._cache[key]

            while len(self._cache) >= self.max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                self._stats.evictions += 1

            self._cache[key] = entry
            self._stats.size = len(self._cache)

    async def delete(self, key: K) -> bool:
        """Delete a key from cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats.size = len(self._cache)
                return True
            return False

    async def clear(self) -> None:
        """Clear all entries."""
        async with self._lock:
            self._cache.clear()
            self._stats.size = 0

    async def cleanup_expired(self) -> int:
        """Remove all expired entries."""
        removed = 0
        async with self._lock:
            expired_keys = [
                k for k, v in self._cache.items() if v.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
                removed += 1
            self._stats.expired_removals += removed
            self._stats.size = len(self._cache)
        return removed

    async def stats(self) -> CacheStats:
        """Get cache statistics."""
        async with self._lock:
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                evictions=self._stats.evictions,
                expired_removals=self._stats.expired_removals,
                size=len(self._cache),
                max_size=self.max_size,
            )


def cache_key(*args: Any, **kwargs: Any) -> str:
    """Generate a cache key from arguments."""
    key_data = {"args": args, "kwargs": kwargs}
    key_json = json.dumps(key_data, sort_keys=True, default=str)
    return hashlib.sha256(key_json.encode()).hexdigest()[:32]


def cached(
    cache: LRUCache[str, Any] | AsyncLRUCache[str, Any],
    ttl_seconds: float | None = None,
    key_func: Callable[..., str] | None = None,
) -> Callable:
    """Decorator for caching function results."""
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                key = key_func(*args, **kwargs) if key_func else cache_key(*args, **kwargs)
                if isinstance(cache, AsyncLRUCache):
                    cached_value = await cache.get(key)
                    if cached_value is not None:
                        return cached_value
                    result = await func(*args, **kwargs)
                    await cache.set(key, result, ttl_seconds)
                    return result
                else:
                    cached_value = cache.get(key)
                    if cached_value is not None:
                        return cached_value
                    result = await func(*args, **kwargs)
                    cache.set(key, result, ttl_seconds)
                    return result
            return async_wrapper
        else:
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                key = key_func(*args, **kwargs) if key_func else cache_key(*args, **kwargs)
                if isinstance(cache, AsyncLRUCache):
                    raise RuntimeError("Cannot use async cache with sync function")
                cached_value = cache.get(key)
                if cached_value is not None:
                    return cached_value
                result = func(*args, **kwargs)
                cache.set(key, result, ttl_seconds)
                return result
            return sync_wrapper
    return decorator


class CacheWarmup:
    """Cache warmup utilities."""

    @staticmethod
    async def warmup_from_func(
        cache: AsyncLRUCache[K, V],
        loader: Callable[[], list[tuple[K, V]]],
        ttl_seconds: float | None = None,
    ) -> int:
        """Warmup cache from a loader function."""
        items = loader()
        for key, value in items:
            await cache.set(key, value, ttl_seconds)
        return len(items)

    @staticmethod
    async def warmup_from_dict(
        cache: AsyncLRUCache[K, V],
        data: dict[K, V],
        ttl_seconds: float | None = None,
    ) -> int:
        """Warmup cache from a dictionary."""
        for key, value in data.items():
            await cache.set(key, value, ttl_seconds)
        return len(data)
