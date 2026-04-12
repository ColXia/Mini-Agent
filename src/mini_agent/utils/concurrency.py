"""Connection pool and request batching for high-concurrency scenarios."""

from __future__ import annotations

import asyncio
import inspect
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Generic, TypeVar

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class PoolStats:
    """Connection pool statistics."""

    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    waiters: int = 0
    created_count: int = 0
    reused_count: int = 0


@dataclass
class PooledConnection(Generic[T]):
    """Wrapper for a pooled connection."""

    connection: T
    created_at: float
    last_used_at: float
    use_count: int = 0
    is_active: bool = False


class AsyncConnectionPool(Generic[T]):
    """Generic async connection pool."""

    def __init__(
        self,
        factory: Callable[[], T],
        *,
        max_size: int = 10,
        min_size: int = 1,
        max_idle_time: float = 300.0,
        acquire_timeout: float = 30.0,
    ) -> None:
        self.factory = factory
        self.max_size = max(1, int(max_size))
        self.min_size = max(0, min(int(min_size), self.max_size))
        self.max_idle_time = max_idle_time
        self.acquire_timeout = acquire_timeout

        self._pool: list[PooledConnection[T]] = []
        self._semaphore = asyncio.Semaphore(self.max_size)
        self._lock = asyncio.Lock()
        self._stats = PoolStats()

    async def _create_connection(self) -> PooledConnection[T]:
        """Create a new connection."""
        now = time.time()
        created = self.factory()
        conn = await created if inspect.isawaitable(created) else created
        pooled = PooledConnection(
            connection=conn,
            created_at=now,
            last_used_at=now,
        )
        self._stats.created_count += 1
        return pooled

    async def acquire(self) -> PooledConnection[T]:
        """Acquire a connection from the pool."""
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self.acquire_timeout,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Failed to acquire connection within {self.acquire_timeout}s")

        async with self._lock:
            # Try to find an idle connection
            for pooled in self._pool:
                if not pooled.is_active:
                    if time.time() - pooled.last_used_at > self.max_idle_time:
                        # Connection too old, remove and create new
                        self._pool.remove(pooled)
                        break
                    pooled.is_active = True
                    pooled.last_used_at = time.time()
                    pooled.use_count += 1
                    self._stats.reused_count += 1
                    self._update_stats()
                    return pooled

            # Create new connection
            pooled = await self._create_connection()
            pooled.is_active = True
            pooled.use_count += 1
            self._pool.append(pooled)
            self._update_stats()
            return pooled

    async def release(self, pooled: PooledConnection[T]) -> None:
        """Release a connection back to the pool."""
        async with self._lock:
            pooled.is_active = False
            pooled.last_used_at = time.time()
            self._semaphore.release()
            self._update_stats()

    async def close(self) -> None:
        """Close all connections."""
        async with self._lock:
            for pooled in self._pool:
                close_fn = getattr(pooled.connection, "close", None)
                if close_fn is None:
                    continue
                closed = close_fn()
                if inspect.isawaitable(closed):
                    await closed
            self._pool.clear()
            self._stats = PoolStats()

    def _update_stats(self) -> None:
        """Update pool statistics."""
        self._stats.total_connections = len(self._pool)
        self._stats.active_connections = sum(1 for p in self._pool if p.is_active)
        self._stats.idle_connections = self._stats.total_connections - self._stats.active_connections

    async def stats(self) -> PoolStats:
        """Get pool statistics."""
        return PoolStats(
            total_connections=self._stats.total_connections,
            active_connections=self._stats.active_connections,
            idle_connections=self._stats.idle_connections,
            waiters=self._semaphore._waiters if hasattr(self._semaphore, "_waiters") else 0,
            created_count=self._stats.created_count,
            reused_count=self._stats.reused_count,
        )

    async def __aenter__(self) -> "AsyncConnectionPool[T]":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


@dataclass
class BatchRequest(Generic[T]):
    """A request to be batched."""

    id: str
    payload: T
    future: asyncio.Future


@dataclass
class BatchResult(Generic[R]):
    """Result of a batched request."""

    id: str
    result: R | None = None
    error: Exception | None = None


class RequestBatcher(Generic[T, R]):
    """Batch multiple requests into single operations."""

    def __init__(
        self,
        executor: Callable[[list[T]], list[R]],
        *,
        max_batch_size: int = 100,
        max_wait_ms: float = 10.0,
    ) -> None:
        self.executor = executor
        self.max_batch_size = max(1, int(max_batch_size))
        self.max_wait_ms = max(0.0, float(max_wait_ms))

        self._pending: list[BatchRequest[T]] = []
        self._lock = asyncio.Lock()
        self._batch_task: asyncio.Task | None = None
        self._running = False

    async def submit(self, request_id: str, payload: T) -> R:
        """Submit a request for batching."""
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        async with self._lock:
            batch_request = BatchRequest(
                id=request_id,
                payload=payload,
                future=future,
            )
            self._pending.append(batch_request)

            # Start batch processing if not running
            if not self._running:
                self._running = True
                self._batch_task = asyncio.create_task(self._process_batch())

        return await future

    async def _process_batch(self) -> None:
        """Process accumulated requests."""
        current_task = asyncio.current_task()

        if self.max_wait_ms > 0:
            await asyncio.sleep(self.max_wait_ms / 1000.0)

        while True:
            async with self._lock:
                if not self._pending:
                    if self._batch_task is current_task:
                        self._running = False
                        self._batch_task = None
                    return

                # Take up to max_batch_size
                batch = self._pending[:self.max_batch_size]
                self._pending = self._pending[self.max_batch_size:]

            # Execute batch outside lock
            payloads = [req.payload for req in batch]
            try:
                executed = self.executor(payloads)
                results = await executed if inspect.isawaitable(executed) else executed

                # Set results
                for i, req in enumerate(batch):
                    if i < len(results):
                        req.future.set_result(results[i])
                    else:
                        req.future.set_exception(ValueError("Missing result in batch"))
            except Exception as e:
                for req in batch:
                    req.future.set_exception(e)

    async def flush(self) -> None:
        """Flush all pending requests."""
        async with self._lock:
            if self._batch_task:
                try:
                    await self._batch_task
                except Exception:
                    pass
            self._running = False


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(
        self,
        rate: float,
        burst: float | None = None,
    ) -> None:
        self.rate = max(0.0, float(rate))
        self.burst = max(self.rate, float(burst) if burst is not None else self.rate)
        self._tokens = self.burst
        self._last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> bool:
        """Try to acquire tokens, return True if successful."""
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_update
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
            self._last_update = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    async def wait_and_acquire(self, tokens: float = 1.0) -> None:
        """Wait until tokens are available and acquire them."""
        while True:
            if await self.acquire(tokens):
                return
            # Calculate wait time
            async with self._lock:
                deficit = tokens - self._tokens
                wait_time = deficit / self.rate if self.rate > 0 else 1.0
            await asyncio.sleep(min(wait_time, 0.1))


class ConcurrencyManager:
    """Central manager for concurrency controls."""

    def __init__(self) -> None:
        self._rate_limiters: dict[str, RateLimiter] = {}
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._lock = asyncio.Lock()

    async def get_rate_limiter(
        self,
        name: str,
        rate: float,
        burst: float | None = None,
    ) -> RateLimiter:
        """Get or create a rate limiter."""
        async with self._lock:
            if name not in self._rate_limiters:
                self._rate_limiters[name] = RateLimiter(rate, burst)
            return self._rate_limiters[name]

    async def get_semaphore(
        self,
        name: str,
        max_concurrent: int,
    ) -> asyncio.Semaphore:
        """Get or create a semaphore."""
        async with self._lock:
            if name not in self._semaphores:
                self._semaphores[name] = asyncio.Semaphore(max_concurrent)
            return self._semaphores[name]

    @asynccontextmanager
    async def limited(
        self,
        name: str,
        rate: float | None = None,
        max_concurrent: int | None = None,
    ) -> AsyncIterator[None]:
        """Context manager for rate and concurrency limiting."""
        if max_concurrent is not None:
            sem = await self.get_semaphore(name, max_concurrent)
            await sem.acquire()
        if rate is not None:
            limiter = await self.get_rate_limiter(name, rate)
            await limiter.wait_and_acquire()

        try:
            yield
        finally:
            if max_concurrent is not None:
                sem.release()
