"""Graceful shutdown management for clean service termination."""

from __future__ import annotations

import asyncio
import signal
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


class ShutdownPhase(str, Enum):
    """Shutdown phases."""

    RUNNING = "running"
    DRAINING = "draining"
    CLOSING = "closing"
    TERMINATED = "terminated"


@dataclass
class ShutdownHook:
    """A shutdown hook with priority."""

    name: str
    callback: Callable[[], Coroutine[Any, Any, None] | None]
    priority: int = 100  # Lower = earlier
    timeout: float = 30.0
    required: bool = True


@dataclass
class ShutdownState:
    """Current shutdown state."""

    phase: ShutdownPhase = ShutdownPhase.RUNNING
    started_at: float | None = None
    completed_hooks: list[str] = field(default_factory=list)
    failed_hooks: list[str] = field(default_factory=list)
    timeout_seconds: float = 60.0


class GracefulShutdown:
    """Manager for graceful shutdown with hooks."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        drain_timeout_seconds: float = 30.0,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.drain_timeout_seconds = drain_timeout_seconds
        self._hooks: list[ShutdownHook] = []
        self._state = ShutdownState(timeout_seconds=timeout_seconds)
        self._shutdown_event = asyncio.Event()
        self._drain_event = asyncio.Event()
        self._lock = asyncio.Lock()

    def register_hook(
        self,
        name: str,
        callback: Callable[[], Coroutine[Any, Any, None] | None],
        *,
        priority: int = 100,
        timeout: float = 30.0,
        required: bool = True,
    ) -> None:
        """Register a shutdown hook.

        Hooks are executed in priority order (lower = earlier).
        """
        hook = ShutdownHook(
            name=name,
            callback=callback,
            priority=priority,
            timeout=timeout,
            required=required,
        )
        self._hooks.append(hook)
        self._hooks.sort(key=lambda h: h.priority)

    def unregister_hook(self, name: str) -> None:
        """Unregister a shutdown hook."""
        self._hooks = [h for h in self._hooks if h.name != name]

    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()

        def handle_signal(sig: signal.Signals) -> None:
            print(f"\nReceived signal {sig.name}, initiating graceful shutdown...")
            asyncio.create_task(self.shutdown(str(sig.name)))

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                signal.signal(sig, lambda s, f: asyncio.create_task(self.shutdown(str(s))))

    async def shutdown(self, reason: str = "manual") -> None:
        """Initiate graceful shutdown."""
        async with self._lock:
            if self._state.phase != ShutdownPhase.RUNNING:
                return

            self._state.phase = ShutdownPhase.DRAINING
            self._state.started_at = asyncio.get_event_loop().time()
            print(f"Starting graceful shutdown: {reason}")

        # Phase 1: Drain - stop accepting new requests
        self._drain_event.set()
        await asyncio.sleep(1)  # Allow in-flight requests to complete

        # Phase 2: Execute shutdown hooks
        async with self._lock:
            self._state.phase = ShutdownPhase.CLOSING

        await self._execute_hooks()

        # Phase 3: Complete
        async with self._lock:
            self._state.phase = ShutdownPhase.TERMINATED

        self._shutdown_event.set()
        print("Graceful shutdown completed")

    async def _execute_hooks(self) -> None:
        """Execute all shutdown hooks."""
        for hook in self._hooks:
            try:
                print(f"Executing shutdown hook: {hook.name}")
                result = hook.callback()

                if asyncio.iscoroutine(result):
                    try:
                        await asyncio.wait_for(result, timeout=hook.timeout)
                    except asyncio.TimeoutError:
                        if hook.required:
                            self._state.failed_hooks.append(hook.name)
                            print(f"Shutdown hook {hook.name} timed out after {hook.timeout}s")
                        else:
                            print(f"Non-required hook {hook.name} timed out, continuing...")
                        continue

                self._state.completed_hooks.append(hook.name)
                print(f"Shutdown hook {hook.name} completed")

            except Exception as e:
                self._state.failed_hooks.append(hook.name)
                print(f"Shutdown hook {hook.name} failed: {e}")

                if hook.required:
                    raise

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown to complete."""
        await self._shutdown_event.wait()

    def is_shutting_down(self) -> bool:
        """Check if shutdown is in progress."""
        return self._state.phase != ShutdownPhase.RUNNING

    def is_draining(self) -> bool:
        """Check if in draining phase."""
        return self._state.phase == ShutdownPhase.DRAINING

    def get_state(self) -> ShutdownState:
        """Get current shutdown state."""
        return self._state


class ConnectionDrainer:
    """Drains connections during graceful shutdown."""

    def __init__(
        self,
        shutdown_manager: GracefulShutdown,
        *,
        drain_timeout: float = 30.0,
    ) -> None:
        self.shutdown_manager = shutdown_manager
        self.drain_timeout = drain_timeout
        self._active_connections: set[Any] = set()
        self._lock = asyncio.Lock()

    async def track(self, connection: Any) -> None:
        """Track an active connection."""
        async with self._lock:
            self._active_connections.add(connection)

    async def untrack(self, connection: Any) -> None:
        """Untrack a connection."""
        async with self._lock:
            self._active_connections.discard(connection)

    async def drain(self) -> None:
        """Wait for all connections to close."""
        start_time = asyncio.get_event_loop().time()

        while True:
            async with self._lock:
                if not self._active_connections:
                    return

                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= self.drain_timeout:
                    print(f"Drain timeout reached, {len(self._active_connections)} connections remaining")
                    return

                remaining = len(self._active_connections)

            print(f"Waiting for {remaining} connections to close...")
            await asyncio.sleep(1)


class RequestTracker:
    """Tracks in-flight requests for graceful shutdown."""

    def __init__(self, shutdown_manager: GracefulShutdown) -> None:
        self.shutdown_manager = shutdown_manager
        self._requests: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._request_counter = 0

    async def start_request(self) -> str | None:
        """Start tracking a request, return request ID or None if shutting down."""
        if self.shutdown_manager.is_shutting_down():
            return None

        async with self._lock:
            self._request_counter += 1
            request_id = f"req_{self._request_counter}"
            self._requests[request_id] = asyncio.get_event_loop().time()
            return request_id

    async def end_request(self, request_id: str) -> None:
        """End tracking a request."""
        async with self._lock:
            self._requests.pop(request_id, None)

    async def wait_for_requests(self, timeout: float = 30.0) -> int:
        """Wait for all requests to complete, return remaining count."""
        start_time = asyncio.get_event_loop().time()

        while True:
            async with self._lock:
                if not self._requests:
                    return 0

                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    return len(self._requests)

            await asyncio.sleep(0.5)

    async def get_active_count(self) -> int:
        """Get count of active requests."""
        async with self._lock:
            return len(self._requests)


# Global shutdown manager
_shutdown_manager: GracefulShutdown | None = None


def get_shutdown_manager() -> GracefulShutdown:
    """Get the global shutdown manager."""
    global _shutdown_manager
    if _shutdown_manager is None:
        _shutdown_manager = GracefulShutdown()
    return _shutdown_manager


def setup_graceful_shutdown(
    *,
    timeout_seconds: float = 60.0,
    drain_timeout_seconds: float = 30.0,
) -> GracefulShutdown:
    """Setup graceful shutdown with signal handlers."""
    global _shutdown_manager
    _shutdown_manager = GracefulShutdown(
        timeout_seconds=timeout_seconds,
        drain_timeout_seconds=drain_timeout_seconds,
    )
    _shutdown_manager.setup_signal_handlers()
    return _shutdown_manager
