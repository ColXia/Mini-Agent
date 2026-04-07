"""Tests for P13 T1.3 circuit-breaker baseline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mini_agent.model_manager import (
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitBreakerState,
    ProviderCircuitBreaker,
)


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(timezone.utc)


def test_circuit_breaker_opens_after_failure_threshold():
    breaker = ProviderCircuitBreaker(
        "provider-a",
        CircuitBreakerConfig(failure_threshold=3, success_threshold=2, timeout_seconds=30),
    )

    assert breaker.should_allow_request().allowed is True
    breaker.record_failure(reason="f1")
    breaker.record_failure(reason="f2")
    assert breaker.state == CircuitBreakerState.CLOSED

    breaker.record_failure(reason="f3")
    assert breaker.state == CircuitBreakerState.OPEN
    blocked = breaker.should_allow_request()
    assert blocked.allowed is False
    assert blocked.state == CircuitBreakerState.OPEN


def test_circuit_breaker_transitions_open_to_half_open_after_timeout():
    breaker = ProviderCircuitBreaker(
        "provider-a",
        CircuitBreakerConfig(failure_threshold=1, success_threshold=2, timeout_seconds=10),
    )
    t0 = _utc("2026-04-05T10:00:00+00:00")
    breaker.record_failure(reason="fail", now=t0)
    assert breaker.state == CircuitBreakerState.OPEN

    denied = breaker.should_allow_request(now=t0 + timedelta(seconds=9))
    assert denied.allowed is False
    assert breaker.state == CircuitBreakerState.OPEN

    probe = breaker.should_allow_request(now=t0 + timedelta(seconds=10))
    assert probe.allowed is True
    assert breaker.state == CircuitBreakerState.HALF_OPEN


def test_circuit_breaker_half_open_success_closes_and_failure_reopens():
    breaker = ProviderCircuitBreaker(
        "provider-a",
        CircuitBreakerConfig(failure_threshold=1, success_threshold=2, timeout_seconds=5),
    )
    t0 = _utc("2026-04-05T10:00:00+00:00")
    breaker.record_failure(reason="open", now=t0)
    assert breaker.state == CircuitBreakerState.OPEN

    breaker.should_allow_request(now=t0 + timedelta(seconds=5))
    assert breaker.state == CircuitBreakerState.HALF_OPEN

    breaker.record_success(now=t0 + timedelta(seconds=6))
    assert breaker.state == CircuitBreakerState.HALF_OPEN
    breaker.record_success(now=t0 + timedelta(seconds=7))
    assert breaker.state == CircuitBreakerState.CLOSED

    breaker.record_failure(reason="open-again", now=t0 + timedelta(seconds=8))
    assert breaker.state == CircuitBreakerState.OPEN
    breaker.should_allow_request(now=t0 + timedelta(seconds=13))
    breaker.record_failure(reason="half-open-fail", now=t0 + timedelta(seconds=14))
    assert breaker.state == CircuitBreakerState.OPEN


def test_circuit_breaker_hot_update_keeps_state_and_counters():
    breaker = ProviderCircuitBreaker(
        "provider-a",
        CircuitBreakerConfig(failure_threshold=4, success_threshold=2, timeout_seconds=60),
    )
    t0 = _utc("2026-04-05T10:00:00+00:00")
    breaker.record_failure(now=t0)
    breaker.record_failure(now=t0 + timedelta(seconds=1))
    assert breaker.state == CircuitBreakerState.CLOSED

    breaker.update_config(
        CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=3,
            timeout_seconds=120,
        )
    )
    # Hot update should not reset counters; threshold drop can trigger immediate open.
    assert breaker.state == CircuitBreakerState.OPEN
    snapshot = breaker.snapshot(now=t0 + timedelta(seconds=2))
    assert snapshot["consecutive_failures"] >= 2
    assert snapshot["config"]["timeout_seconds"] == 120


def test_circuit_breaker_registry_reuses_instances_and_tracks_stats():
    registry = CircuitBreakerRegistry()
    first = registry.get("provider-a")
    second = registry.get("provider-a")
    assert first is second

    registry.record_failure("provider-a", reason="network")
    registry.record_success("provider-a")
    snap = registry.snapshot("provider-a")
    assert snap["total_requests"] == 2
    assert snap["total_failures"] == 1
    assert 0.0 <= snap["error_rate"] <= 1.0

    registry.get("provider-b")
    all_snaps = registry.snapshots()
    assert len(all_snaps) == 2
