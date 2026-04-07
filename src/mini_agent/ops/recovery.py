"""Fault recovery and resilience patterns."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class RecoveryAction(str, Enum):
    """Recovery actions."""

    RETRY = "retry"
    FALLBACK = "fallback"
    CIRCUIT_OPEN = "circuit_open"
    TIMEOUT = "timeout"
    FAIL_FAST = "fail_fast"


@dataclass
class RecoveryResult(Generic[T]):
    """Result of a recovery attempt."""

    success: bool
    value: T | None = None
    error: Exception | None = None
    action: RecoveryAction = RecoveryAction.RETRY
    attempts: int = 1
    total_time_ms: float = 0.0


@dataclass
class RecoveryConfig:
    """Configuration for recovery behavior."""

    max_retries: int = 3
    initial_delay_ms: float = 100.0
    max_delay_ms: float = 5000.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    timeout_ms: float = 30000.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout_ms: float = 60000.0


@dataclass
class CircuitState:
    """Circuit breaker state."""

    is_open: bool = False
    failure_count: int = 0
    last_failure_time: float | None = None
    opened_at: float | None = None


class RecoveryManager:
    """Manages fault recovery with retry, circuit breaker, and fallback."""

    def __init__(self, config: RecoveryConfig | None = None) -> None:
        self.config = config or RecoveryConfig()
        self._circuits: dict[str, CircuitState] = {}
        self._lock = asyncio.Lock()

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and optional jitter."""
        import random

        delay = self.config.initial_delay_ms * (self.config.backoff_multiplier ** (attempt - 1))
        delay = min(delay, self.config.max_delay_ms)

        if self.config.jitter:
            # Add random jitter (0-25% of delay)
            jitter = delay * (0.25 * random.random())
            delay += jitter

        return delay

    async def _check_circuit(self, circuit_key: str) -> bool:
        """Check if circuit is open (should fail fast)."""
        circuit = self._circuits.get(circuit_key)
        if circuit is None or not circuit.is_open:
            return False

        # Check if circuit should transition to half-open
        if circuit.opened_at is not None:
            elapsed = (time.time() * 1000) - circuit.opened_at
            if elapsed >= self.config.circuit_breaker_timeout_ms:
                return False  # Allow one attempt

        return True  # Circuit is open, fail fast

    async def _record_success(self, circuit_key: str) -> None:
        """Record a successful operation."""
        circuit = self._circuits.get(circuit_key)
        if circuit:
            circuit.failure_count = 0
            circuit.is_open = False
            circuit.opened_at = None

    async def _record_failure(self, circuit_key: str) -> None:
        """Record a failed operation."""
        if circuit_key not in self._circuits:
            self._circuits[circuit_key] = CircuitState()

        circuit = self._circuits[circuit_key]
        circuit.failure_count += 1
        circuit.last_failure_time = time.time()

        if circuit.failure_count >= self.config.circuit_breaker_threshold:
            circuit.is_open = True
            circuit.opened_at = time.time() * 1000

    async def execute_with_recovery(
        self,
        operation: Callable[[], asyncio.Future[T]],
        *,
        circuit_key: str = "default",
        fallback: Callable[[], asyncio.Future[T]] | None = None,
        retry_on: tuple[type[Exception], ...] | None = None,
    ) -> RecoveryResult[T]:
        """Execute an operation with full recovery support."""
        start_time = time.time() * 1000
        attempts = 0
        last_error: Exception | None = None

        # Check circuit breaker
        if await self._check_circuit(circuit_key):
            if fallback:
                try:
                    value = await fallback()
                    return RecoveryResult(
                        success=True,
                        value=value,
                        action=RecoveryAction.FALLBACK,
                    )
                except Exception as e:
                    return RecoveryResult(
                        success=False,
                        error=e,
                        action=RecoveryAction.CIRCUIT_OPEN,
                    )

            return RecoveryResult(
                success=False,
                error=Exception("Circuit breaker is open"),
                action=RecoveryAction.CIRCUIT_OPEN,
            )

        while attempts < self.config.max_retries:
            attempts += 1

            try:
                # Execute with timeout
                value = await asyncio.wait_for(
                    operation(),
                    timeout=self.config.timeout_ms / 1000,
                )
                await self._record_success(circuit_key)

                return RecoveryResult(
                    success=True,
                    value=value,
                    attempts=attempts,
                    total_time_ms=(time.time() * 1000) - start_time,
                )

            except asyncio.TimeoutError as e:
                last_error = e
                await self._record_failure(circuit_key)

                if fallback:
                    try:
                        value = await fallback()
                        return RecoveryResult(
                            success=True,
                            value=value,
                            action=RecoveryAction.FALLBACK,
                            attempts=attempts,
                        )
                    except Exception:
                        pass

            except Exception as e:
                last_error = e

                # Check if we should retry this exception
                if retry_on and not isinstance(e, retry_on):
                    await self._record_failure(circuit_key)
                    break

                await self._record_failure(circuit_key)

            # Wait before retry
            if attempts < self.config.max_retries:
                delay = self._calculate_delay(attempts)
                await asyncio.sleep(delay / 1000)

        # All retries failed
        return RecoveryResult(
            success=False,
            error=last_error,
            action=RecoveryAction.RETRY,
            attempts=attempts,
            total_time_ms=(time.time() * 1000) - start_time,
        )

    def get_circuit_state(self, circuit_key: str) -> CircuitState | None:
        """Get the state of a circuit breaker."""
        return self._circuits.get(circuit_key)

    async def reset_circuit(self, circuit_key: str) -> None:
        """Reset a circuit breaker."""
        if circuit_key in self._circuits:
            self._circuits[circuit_key] = CircuitState()


class HealthMonitor:
    """Monitors component health and triggers recovery."""

    def __init__(self) -> None:
        self._components: dict[str, Callable[[], bool]] = {}
        self._statuses: dict[str, bool] = {}
        self._listeners: list[Callable[[str, bool], None]] = []

    def register(
        self,
        name: str,
        health_check: Callable[[], bool],
    ) -> None:
        """Register a component health check."""
        self._components[name] = health_check

    def unregister(self, name: str) -> None:
        """Unregister a component."""
        self._components.pop(name, None)
        self._statuses.pop(name, None)

    def add_listener(self, listener: Callable[[str, bool], None]) -> None:
        """Add a health change listener."""
        self._listeners.append(listener)

    async def check_all(self) -> dict[str, bool]:
        """Check health of all components."""
        for name, check in self._components.items():
            try:
                if asyncio.iscoroutinefunction(check):
                    is_healthy = await check()
                else:
                    is_healthy = check()

                old_status = self._statuses.get(name)
                self._statuses[name] = is_healthy

                if old_status is not None and old_status != is_healthy:
                    for listener in self._listeners:
                        try:
                            listener(name, is_healthy)
                        except Exception:
                            pass

            except Exception:
                self._statuses[name] = False

        return dict(self._statuses)

    def get_status(self, name: str) -> bool | None:
        """Get status of a component."""
        return self._statuses.get(name)

    def get_all_statuses(self) -> dict[str, bool]:
        """Get all component statuses."""
        return dict(self._statuses)


class StateRecovery:
    """Recovery for application state."""

    def __init__(self, state_dir: str = "./state") -> None:
        from pathlib import Path
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoints: dict[str, Any] = {}

    def save_checkpoint(self, name: str, state: Any) -> None:
        """Save a state checkpoint."""
        import json

        self._checkpoints[name] = state
        checkpoint_file = self.state_dir / f"{name}.json"

        try:
            with open(checkpoint_file, "w") as f:
                json.dump({"state": state, "timestamp": time.time()}, f)
        except Exception:
            pass

    def load_checkpoint(self, name: str) -> Any | None:
        """Load a state checkpoint."""
        import json

        # Try memory first
        if name in self._checkpoints:
            return self._checkpoints[name]

        # Try file
        checkpoint_file = self.state_dir / f"{name}.json"
        if checkpoint_file.exists():
            try:
                with open(checkpoint_file) as f:
                    data = json.load(f)
                    return data.get("state")
            except Exception:
                pass

        return None

    def clear_checkpoint(self, name: str) -> None:
        """Clear a checkpoint."""
        self._checkpoints.pop(name, None)
        checkpoint_file = self.state_dir / f"{name}.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()


# Global instances
_recovery_manager: RecoveryManager | None = None
_health_monitor: HealthMonitor | None = None


def get_recovery_manager() -> RecoveryManager:
    """Get the global recovery manager."""
    global _recovery_manager
    if _recovery_manager is None:
        _recovery_manager = RecoveryManager()
    return _recovery_manager


def get_health_monitor() -> HealthMonitor:
    """Get the global health monitor."""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor
