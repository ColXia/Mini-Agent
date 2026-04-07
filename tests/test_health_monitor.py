"""Tests for provider health monitor baseline."""

from __future__ import annotations

from mini_agent.model_manager import ProviderHealthMonitor


def test_health_monitor_route_and_success_failure_tracking():
    monitor = ProviderHealthMonitor(degraded_failure_threshold=2)

    monitor.record_route("provider-a", mapping_mode="exact")
    monitor.record_route("provider-a", mapping_mode="partial")
    monitor.record_success("provider-a")
    monitor.record_failure("provider-a", reason="timeout")

    snapshot = monitor.snapshot("provider-a", breaker_state="closed")
    assert snapshot["provider_id"] == "provider-a"
    assert snapshot["selected_count"] == 2
    assert snapshot["total_successes"] == 1
    assert snapshot["total_failures"] == 1
    assert snapshot["consecutive_failures"] == 1
    assert snapshot["status"] == "healthy"
    assert snapshot["mapping_mode_counts"]["exact"] == 1
    assert snapshot["mapping_mode_counts"]["partial"] == 1


def test_health_monitor_degraded_and_open_state():
    monitor = ProviderHealthMonitor(degraded_failure_threshold=2)

    monitor.record_failure("provider-b", reason="network")
    monitor.record_failure("provider-b", reason="network")
    degraded = monitor.snapshot("provider-b", breaker_state="closed")
    assert degraded["status"] == "degraded"

    unhealthy = monitor.snapshot("provider-b", breaker_state="open")
    assert unhealthy["status"] == "unhealthy"

    unknown = monitor.snapshot("provider-c", breaker_state=None)
    assert unknown["status"] == "unknown"
