"""Three-state circuit breaker baseline with hot-update support."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import RLock
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


class CircuitBreakerState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Circuit-breaker config (supports hot update without state reset)."""

    failure_threshold: int = 4
    success_threshold: int = 2
    timeout_seconds: int = 60
    error_rate_threshold: float = 0.6
    min_requests: int = 10

    def normalized(self) -> "CircuitBreakerConfig":
        failure_threshold = max(1, int(self.failure_threshold))
        success_threshold = max(1, int(self.success_threshold))
        timeout_seconds = max(1, int(self.timeout_seconds))
        error_rate_threshold = float(self.error_rate_threshold)
        if error_rate_threshold < 0.0:
            error_rate_threshold = 0.0
        if error_rate_threshold > 1.0:
            error_rate_threshold = 1.0
        min_requests = max(1, int(self.min_requests))
        return CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout_seconds=timeout_seconds,
            error_rate_threshold=error_rate_threshold,
            min_requests=min_requests,
        )


@dataclass(frozen=True)
class CircuitBreakerDecision:
    """Decision for whether one request is allowed."""

    allowed: bool
    reason: str | None = None
    state: CircuitBreakerState = CircuitBreakerState.CLOSED


class ProviderCircuitBreaker:
    """Circuit breaker for one provider."""

    def __init__(
        self,
        provider_id: str,
        config: CircuitBreakerConfig | None = None,
    ):
        self.provider_id = provider_id.strip() or "provider"
        self._config = (config or CircuitBreakerConfig()).normalized()
        self._state = CircuitBreakerState.CLOSED

        self._consecutive_failures = 0
        self._half_open_successes = 0
        self._total_requests = 0
        self._total_successes = 0
        self._total_failures = 0

        self._opened_at: datetime | None = None
        self._open_until: datetime | None = None
        self._last_success_at: datetime | None = None
        self._last_failure_at: datetime | None = None
        self._last_failure_reason: str | None = None
        self._lock = RLock()

    @property
    def state(self) -> CircuitBreakerState:
        with self._lock:
            return self._state

    @property
    def config(self) -> CircuitBreakerConfig:
        with self._lock:
            return self._config

    def should_allow_request(self, *, now: datetime | None = None) -> CircuitBreakerDecision:
        with self._lock:
            timestamp = now or _utc_now()
            if self._state == CircuitBreakerState.OPEN:
                if self._open_until is not None and timestamp >= self._open_until:
                    self._transition_to_half_open()
                    return CircuitBreakerDecision(
                        allowed=True,
                        reason=None,
                        state=self._state,
                    )
                return CircuitBreakerDecision(
                    allowed=False,
                    reason="circuit is open",
                    state=self._state,
                )
            return CircuitBreakerDecision(
                allowed=True,
                reason=None,
                state=self._state,
            )

    def record_success(self, *, now: datetime | None = None) -> None:
        with self._lock:
            timestamp = now or _utc_now()
            self._total_requests += 1
            self._total_successes += 1
            self._last_success_at = timestamp
            self._last_failure_reason = None

            if self._state == CircuitBreakerState.HALF_OPEN:
                self._half_open_successes += 1
                self._consecutive_failures = 0
                if self._half_open_successes >= self._config.success_threshold:
                    self._transition_to_closed()
                return

            self._consecutive_failures = 0
            if self._state == CircuitBreakerState.OPEN:
                # Defensive fallback for out-of-band success reporting.
                self._transition_to_half_open()

    def record_failure(self, *, reason: str | None = None, now: datetime | None = None) -> None:
        with self._lock:
            timestamp = now or _utc_now()
            self._total_requests += 1
            self._total_failures += 1
            self._last_failure_at = timestamp
            self._last_failure_reason = (reason or "").strip() or None

            if self._state == CircuitBreakerState.HALF_OPEN:
                self._consecutive_failures = max(1, self._consecutive_failures + 1)
                self._transition_to_open(timestamp)
                return

            if self._state == CircuitBreakerState.OPEN:
                # Keep tracking failure stats while open.
                if self._opened_at is None:
                    self._transition_to_open(timestamp)
                return

            self._consecutive_failures += 1
            if self._consecutive_failures >= self._config.failure_threshold:
                self._transition_to_open(timestamp)
                return

            if self._is_error_rate_triggered():
                self._transition_to_open(timestamp)

    def update_config(self, config: CircuitBreakerConfig) -> None:
        """Hot-update config while preserving current state and counters."""
        with self._lock:
            self._config = config.normalized()
            if self._state == CircuitBreakerState.OPEN and self._opened_at is not None:
                self._open_until = self._opened_at + timedelta(seconds=self._config.timeout_seconds)
            if (
                self._state == CircuitBreakerState.CLOSED
                and self._consecutive_failures >= self._config.failure_threshold
            ):
                self._transition_to_open(_utc_now())
            if (
                self._state == CircuitBreakerState.HALF_OPEN
                and self._half_open_successes >= self._config.success_threshold
            ):
                self._transition_to_closed()

    def snapshot(self, *, now: datetime | None = None) -> dict[str, Any]:
        with self._lock:
            timestamp = now or _utc_now()
            decision = self.should_allow_request(now=timestamp)
            return {
                "provider_id": self.provider_id,
                "state": self._state.value,
                "allowed": decision.allowed,
                "blocked_reason": decision.reason,
                "config": {
                    "failure_threshold": self._config.failure_threshold,
                    "success_threshold": self._config.success_threshold,
                    "timeout_seconds": self._config.timeout_seconds,
                    "error_rate_threshold": self._config.error_rate_threshold,
                    "min_requests": self._config.min_requests,
                },
                "consecutive_failures": self._consecutive_failures,
                "half_open_successes": self._half_open_successes,
                "total_requests": self._total_requests,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "error_rate": self.error_rate(),
                "opened_at": _utc_iso(self._opened_at),
                "open_until": _utc_iso(self._open_until),
                "last_success_at": _utc_iso(self._last_success_at),
                "last_failure_at": _utc_iso(self._last_failure_at),
                "last_failure_reason": self._last_failure_reason,
            }

    def error_rate(self) -> float:
        with self._lock:
            if self._total_requests <= 0:
                return 0.0
            return float(self._total_failures) / float(self._total_requests)

    def _is_error_rate_triggered(self) -> bool:
        if self._total_requests < self._config.min_requests:
            return False
        return self.error_rate() >= self._config.error_rate_threshold

    def _transition_to_open(self, now: datetime) -> None:
        self._state = CircuitBreakerState.OPEN
        self._opened_at = now
        self._open_until = now + timedelta(seconds=self._config.timeout_seconds)
        self._half_open_successes = 0

    def _transition_to_half_open(self) -> None:
        self._state = CircuitBreakerState.HALF_OPEN
        self._half_open_successes = 0

    def _transition_to_closed(self) -> None:
        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0
        self._half_open_successes = 0
        self._opened_at = None
        self._open_until = None
        self._last_failure_reason = None


class CircuitBreakerRegistry:
    """Registry for provider-level circuit breakers."""

    def __init__(self, default_config: CircuitBreakerConfig | None = None):
        self._default_config = (default_config or CircuitBreakerConfig()).normalized()
        self._breakers: dict[str, ProviderCircuitBreaker] = {}
        self._lock = RLock()

    def get(self, provider_id: str) -> ProviderCircuitBreaker:
        normalized = provider_id.strip() or "provider"
        with self._lock:
            breaker = self._breakers.get(normalized)
            if breaker is None:
                breaker = ProviderCircuitBreaker(
                    provider_id=normalized,
                    config=replace(self._default_config),
                )
                self._breakers[normalized] = breaker
            return breaker

    def update_config(self, provider_id: str, config: CircuitBreakerConfig) -> ProviderCircuitBreaker:
        breaker = self.get(provider_id)
        breaker.update_config(config)
        return breaker

    def should_allow(self, provider_id: str) -> CircuitBreakerDecision:
        return self.get(provider_id).should_allow_request()

    def record_success(self, provider_id: str) -> None:
        self.get(provider_id).record_success()

    def record_failure(self, provider_id: str, *, reason: str | None = None) -> None:
        self.get(provider_id).record_failure(reason=reason)

    def snapshot(self, provider_id: str) -> dict[str, Any]:
        return self.get(provider_id).snapshot()

    def snapshots(self) -> list[dict[str, Any]]:
        with self._lock:
            ids = sorted(self._breakers.keys())
        return [self.get(provider_id).snapshot() for provider_id in ids]
