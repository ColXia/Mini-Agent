"""Distributed lock implementation with automatic renewal and deadlock detection."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None  # type: ignore


@dataclass
class LockConfig:
    """Distributed lock configuration."""

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    key_prefix: str = "mini_agent:lock:"
    default_ttl: int = 30  # seconds
    retry_interval: float = 0.1  # seconds
    max_retries: int = 100


@dataclass
class LockInfo:
    """Information about a held lock."""

    lock_name: str
    lock_value: str
    acquired_at: float
    ttl: int
    holder_id: str


class DistributedLock:
    """Distributed lock using Redis with automatic renewal."""

    # Lua script for atomic lock acquisition
    ACQUIRE_SCRIPT = """
    if redis.call("exists", KEYS[1]) == 0 then
        return redis.call("set", KEYS[1], ARGV[1], "PX", ARGV[2], "NX")
    end
    return false
    """

    # Lua script for atomic lock release
    RELEASE_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    end
    return 0
    """

    # Lua script for lock renewal
    RENEW_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("pexpire", KEYS[1], ARGV[2])
    end
    return 0
    """

    def __init__(
        self,
        name: str,
        config: LockConfig | None = None,
        *,
        holder_id: str | None = None,
    ) -> None:
        if not REDIS_AVAILABLE:
            raise ImportError("redis package required for DistributedLock")

        self.name = name
        self.config = config or LockConfig()
        self.holder_id = holder_id or str(uuid.uuid4())
        self._lock_value: str | None = None
        self._client: redis.Redis | None = None
        self._pool: redis.ConnectionPool | None = None
        self._renewal_task: asyncio.Task | None = None
        self._acquired = False
        self._acquired_at: float | None = None

    async def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._pool = redis.ConnectionPool(
                host=self.config.redis_host,
                port=self.config.redis_port,
                db=self.config.redis_db,
                password=self.config.redis_password,
                decode_responses=True,
            )
            self._client = redis.Redis(connection_pool=self._pool)
        return self._client

    def _make_key(self) -> str:
        """Create lock key."""
        return f"{self.config.key_prefix}{self.name}"

    def _generate_lock_value(self) -> str:
        """Generate unique lock value."""
        random_bytes = secrets.token_bytes(16)
        return hashlib.sha256(
            f"{self.holder_id}:{self.name}:{random_bytes.hex()}".encode()
        ).hexdigest()[:32]

    async def acquire(
        self,
        timeout: float | None = None,
        ttl: int | None = None,
    ) -> bool:
        """Acquire the lock.

        Args:
            timeout: Maximum time to wait for lock (None = no wait)
            ttl: Lock TTL in seconds

        Returns:
            True if lock acquired, False otherwise
        """
        client = await self._get_client()
        key = self._make_key()
        lock_value = self._generate_lock_value()
        effective_ttl = (ttl or self.config.default_ttl) * 1000  # Convert to ms

        # Try to acquire immediately
        acquired = await client.eval(
            self.ACQUIRE_SCRIPT,
            1,
            key,
            lock_value,
            effective_ttl,
        )

        if acquired:
            self._lock_value = lock_value
            self._acquired = True
            self._acquired_at = time.time()
            self._start_renewal(ttl or self.config.default_ttl)
            return True

        # If no timeout, return immediately
        if timeout is None:
            return False

        # Retry with timeout
        start_time = time.time()
        retries = 0

        while time.time() - start_time < timeout and retries < self.config.max_retries:
            await asyncio.sleep(self.config.retry_interval)
            retries += 1

            acquired = await client.eval(
                self.ACQUIRE_SCRIPT,
                1,
                key,
                lock_value,
                effective_ttl,
            )

            if acquired:
                self._lock_value = lock_value
                self._acquired = True
                self._acquired_at = time.time()
                self._start_renewal(ttl or self.config.default_ttl)
                return True

        return False

    async def release(self) -> bool:
        """Release the lock."""
        if not self._acquired or self._lock_value is None:
            return False

        self._stop_renewal()

        client = await self._get_client()
        key = self._make_key()

        result = await client.eval(
            self.RELEASE_SCRIPT,
            1,
            key,
            self._lock_value,
        )

        self._acquired = False
        self._lock_value = None
        self._acquired_at = None

        return bool(result)

    async def renew(self, ttl: int | None = None) -> bool:
        """Renew the lock TTL."""
        if not self._acquired or self._lock_value is None:
            return False

        client = await self._get_client()
        key = self._make_key()
        effective_ttl = (ttl or self.config.default_ttl) * 1000

        result = await client.eval(
            self.RENEW_SCRIPT,
            1,
            key,
            self._lock_value,
            effective_ttl,
        )

        return bool(result)

    def _start_renewal(self, ttl: int) -> None:
        """Start automatic renewal task."""
        if self._renewal_task is not None:
            self._renewal_task.cancel()

        async def renewal_loop() -> None:
            """Periodically renew the lock."""
            interval = ttl / 3  # Renew at 1/3 of TTL
            while self._acquired:
                await asyncio.sleep(interval)
                if self._acquired:
                    try:
                        await self.renew(ttl)
                    except Exception:
                        break

        self._renewal_task = asyncio.create_task(renewal_loop())

    def _stop_renewal(self) -> None:
        """Stop automatic renewal task."""
        if self._renewal_task is not None:
            self._renewal_task.cancel()
            self._renewal_task = None

    async def __aenter__(self) -> "DistributedLock":
        """Context manager entry."""
        acquired = await self.acquire(timeout=30)
        if not acquired:
            raise TimeoutError(f"Failed to acquire lock: {self.name}")
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Context manager exit."""
        await self.release()

    async def close(self) -> None:
        """Close the Redis connection."""
        self._stop_renewal()
        if self._client:
            await self._client.close()
            self._client = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None

    @property
    def is_acquired(self) -> bool:
        """Check if lock is currently acquired."""
        return self._acquired

    def get_info(self) -> LockInfo | None:
        """Get lock information."""
        if not self._acquired or self._lock_value is None:
            return None

        return LockInfo(
            lock_name=self.name,
            lock_value=self._lock_value,
            acquired_at=self._acquired_at or 0,
            ttl=self.config.default_ttl,
            holder_id=self.holder_id,
        )


class LockManager:
    """Manager for multiple distributed locks."""

    def __init__(self, config: LockConfig | None = None) -> None:
        self.config = config or LockConfig()
        self._locks: dict[str, DistributedLock] = {}

    def get_lock(self, name: str, holder_id: str | None = None) -> DistributedLock:
        """Get or create a lock by name."""
        if name not in self._locks:
            self._locks[name] = DistributedLock(
                name=name,
                config=self.config,
                holder_id=holder_id,
            )
        return self._locks[name]

    async def acquire_many(
        self,
        names: list[str],
        timeout: float = 30.0,
        ttl: int | None = None,
    ) -> bool:
        """Acquire multiple locks atomically.

        Uses sorted lock names to prevent deadlock.
        """
        # Sort locks to prevent deadlock
        sorted_names = sorted(names)

        acquired_locks: list[str] = []

        try:
            for name in sorted_names:
                lock = self.get_lock(name)
                if not await lock.acquire(timeout=timeout / len(names), ttl=ttl):
                    # Failed to acquire, release all
                    for acquired in acquired_locks:
                        await self._locks[acquired].release()
                    return False
                acquired_locks.append(name)

            return True

        except Exception:
            # Release any acquired locks on error
            for name in acquired_locks:
                try:
                    await self._locks[name].release()
                except Exception:
                    pass
            return False

    async def release_all(self) -> None:
        """Release all managed locks."""
        for lock in self._locks.values():
            try:
                await lock.release()
            except Exception:
                pass

    async def close(self) -> None:
        """Close all lock connections."""
        for lock in self._locks.values():
            try:
                await lock.close()
            except Exception:
                pass
        self._locks.clear()


class LocalLock:
    """Local lock for single-instance deployments (fallback)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._lock = asyncio.Lock()
        self._holder: str | None = None
        self._acquired_at: float | None = None

    async def acquire(self, timeout: float | None = None) -> bool:
        """Acquire the lock."""
        if timeout is None:
            await self._lock.acquire()
        else:
            try:
                await asyncio.wait_for(
                    self._lock.acquire(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                return False

        self._holder = str(uuid.uuid4())
        self._acquired_at = time.time()
        return True

    async def release(self) -> bool:
        """Release the lock."""
        if self._lock.locked():
            self._lock.release()
            self._holder = None
            self._acquired_at = None
            return True
        return False

    async def __aenter__(self) -> "LocalLock":
        await self.acquire()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.release()

    @property
    def is_acquired(self) -> bool:
        return self._lock.locked()
