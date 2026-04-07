"""Distributed cache with Redis backend for multi-instance deployments."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Callable

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None  # type: ignore


@dataclass
class RedisCacheConfig:
    """Redis cache configuration."""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    username: str | None = None
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    max_connections: int = 10
    decode_responses: bool = True
    key_prefix: str = "mini_agent:"
    default_ttl: int = 3600  # 1 hour


class RedisCache:
    """Distributed cache using Redis."""

    def __init__(self, config: RedisCacheConfig | None = None) -> None:
        if not REDIS_AVAILABLE:
            raise ImportError("redis package required for RedisCache")

        self.config = config or RedisCacheConfig()
        self._client: redis.Redis | None = None
        self._pool: redis.ConnectionPool | None = None

    async def connect(self) -> None:
        """Establish connection to Redis."""
        if self._client is not None:
            return

        self._pool = redis.ConnectionPool(
            host=self.config.host,
            port=self.config.port,
            db=self.config.db,
            password=self.config.password,
            username=self.config.username,
            socket_timeout=self.config.socket_timeout,
            socket_connect_timeout=self.config.socket_connect_timeout,
            max_connections=self.config.max_connections,
            decode_responses=self.config.decode_responses,
        )
        self._client = redis.Redis(connection_pool=self._pool)

    async def disconnect(self) -> None:
        """Close connection to Redis."""
        if self._client:
            await self._client.close()
            self._client = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None

    def _make_key(self, key: str) -> str:
        """Create prefixed key."""
        return f"{self.config.key_prefix}{key}"

    async def get(self, key: str) -> Any | None:
        """Get a value from cache."""
        if not self._client:
            await self.connect()

        full_key = self._make_key(key)
        value = await self._client.get(full_key)  # type: ignore

        if value is None:
            return None

        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Set a value in cache."""
        if not self._client:
            await self.connect()

        full_key = self._make_key(key)
        effective_ttl = ttl if ttl is not None else self.config.default_ttl

        if isinstance(value, (dict, list)):
            serialized = json.dumps(value)
        else:
            serialized = str(value)

        return await self._client.set(full_key, serialized, ex=effective_ttl)  # type: ignore

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        if not self._client:
            await self.connect()

        full_key = self._make_key(key)
        result = await self._client.delete(full_key)  # type: ignore
        return result > 0

    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        if not self._client:
            await self.connect()

        full_key = self._make_key(key)
        return await self._client.exists(full_key) > 0  # type: ignore

    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on a key."""
        if not self._client:
            await self.connect()

        full_key = self._make_key(key)
        return await self._client.expire(full_key, ttl)  # type: ignore

    async def ttl(self, key: str) -> int:
        """Get remaining TTL of a key."""
        if not self._client:
            await self.connect()

        full_key = self._make_key(key)
        return await self._client.ttl(full_key)  # type: ignore

    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment a counter."""
        if not self._client:
            await self.connect()

        full_key = self._make_key(key)
        return await self._client.incrby(full_key, amount)  # type: ignore

    async def decr(self, key: str, amount: int = 1) -> int:
        """Decrement a counter."""
        return await self.incr(key, -amount)

    async def mget(self, keys: list[str]) -> list[Any | None]:
        """Get multiple values."""
        if not self._client:
            await self.connect()

        full_keys = [self._make_key(k) for k in keys]
        values = await self._client.mget(full_keys)  # type: ignore

        results = []
        for value in values:
            if value is None:
                results.append(None)
            else:
                try:
                    results.append(json.loads(value))
                except (json.JSONDecodeError, TypeError):
                    results.append(value)
        return results

    async def mset(self, mapping: dict[str, Any], ttl: int | None = None) -> bool:
        """Set multiple values."""
        if not self._client:
            await self.connect()

        pipe = self._client.pipeline()  # type: ignore
        for key, value in mapping.items():
            full_key = self._make_key(key)
            if isinstance(value, (dict, list)):
                serialized = json.dumps(value)
            else:
                serialized = str(value)

            if ttl is not None:
                pipe.set(full_key, serialized, ex=ttl)
            else:
                pipe.set(full_key, serialized, ex=self.config.default_ttl)

        await pipe.execute()
        return True

    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching a pattern."""
        if not self._client:
            await self.connect()

        full_pattern = self._make_key(pattern)
        keys = []
        async for key in self._client.scan_iter(match=full_pattern):  # type: ignore
            keys.append(key)

        if keys:
            return await self._client.delete(*keys)  # type: ignore
        return 0

    async def ping(self) -> bool:
        """Check if Redis is available."""
        if not self._client:
            await self.connect()

        try:
            return await self._client.ping()  # type: ignore
        except Exception:
            return False

    async def info(self) -> dict[str, Any]:
        """Get Redis server info."""
        if not self._client:
            await self.connect()

        info = await self._client.info()  # type: ignore
        return dict(info) if info else {}


class DistributedCache:
    """High-level distributed cache with fallback to local cache."""

    def __init__(
        self,
        redis_config: RedisCacheConfig | None = None,
        local_cache_size: int = 1000,
        local_cache_ttl: int = 60,
    ) -> None:
        from mini_agent.utils.cache import AsyncLRUCache

        self._redis: RedisCache | None = None
        self._local = AsyncLRUCache[str, Any](
            max_size=local_cache_size,
            default_ttl_seconds=local_cache_ttl,
        )
        self._redis_config = redis_config
        self._use_redis = redis_config is not None and REDIS_AVAILABLE

    async def _get_redis(self) -> RedisCache | None:
        """Get Redis client, initializing if needed."""
        if not self._use_redis:
            return None

        if self._redis is None:
            try:
                self._redis = RedisCache(self._redis_config)
                await self._redis.connect()
            except Exception:
                self._use_redis = False
                return None

        return self._redis

    async def get(self, key: str) -> Any | None:
        """Get value, checking local cache first, then Redis."""
        # Check local cache first
        local_value = await self._local.get(key)
        if local_value is not None:
            return local_value

        # Check Redis
        redis_client = await self._get_redis()
        if redis_client:
            value = await redis_client.get(key)
            if value is not None:
                # Cache in local for faster access
                await self._local.set(key, value)
            return value

        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Set value in both local and Redis."""
        # Set in local cache
        await self._local.set(key, value, ttl)

        # Set in Redis
        redis_client = await self._get_redis()
        if redis_client:
            return await redis_client.set(key, value, ttl)

        return True

    async def delete(self, key: str) -> bool:
        """Delete from both caches."""
        await self._local.delete(key)

        redis_client = await self._get_redis()
        if redis_client:
            return await redis_client.delete(key)

        return True

    async def invalidate(self, key: str) -> None:
        """Invalidate a key from all cache layers."""
        await self.delete(key)

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern."""
        count = 0

        # Clear from Redis
        redis_client = await self._get_redis()
        if redis_client:
            count = await redis_client.clear_pattern(pattern)

        # Note: Local cache doesn't support pattern clearing efficiently
        # In production, you might want to track keys or use a different approach

        return count
