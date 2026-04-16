from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from mini_agent.agent_core.session import SessionLifecycleManager, SessionLifecyclePolicy, SessionResetMode
from mini_agent.runtime.session_runtime_lifecycle_handler import RuntimeSessionLifecycleHandler
from mini_agent.runtime.session_runtime_policy_coordinator import RuntimeSessionPolicyCoordinator
from tests.runtime_contract_fixtures import runtime_session_stub


def _dt(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def test_runtime_session_lifecycle_handler_builds_gateway_session_key(tmp_path: Path) -> None:
    policy = SessionLifecyclePolicy(mode=SessionResetMode.NONE, idle_seconds=60)
    coordinator = RuntimeSessionPolicyCoordinator(
        policy=SimpleNamespace(mode="single_main", session_lifecycle=policy),
        ttl_seconds=3600,
        lifecycle_manager=SessionLifecycleManager(policy),
    )
    handler = RuntimeSessionLifecycleHandler(
        lifecycle_manager=coordinator.lifecycle_manager,
        policy_coordinator=coordinator,
    )

    key = handler.build_session_key("sess-1", tmp_path)

    assert key.agent_id == "main-agent"
    assert key.channel == "gateway"
    assert key.peer_kind == "workspace"
    assert key.thread_id == "sess-1"


def test_runtime_session_lifecycle_handler_refreshes_and_resets_runtime_state(tmp_path: Path) -> None:
    policy = SessionLifecyclePolicy(mode=SessionResetMode.IDLE, idle_seconds=5)
    coordinator = RuntimeSessionPolicyCoordinator(
        policy=SimpleNamespace(mode="single_main", session_lifecycle=policy),
        ttl_seconds=3600,
        lifecycle_manager=SessionLifecycleManager(policy),
    )
    handler = RuntimeSessionLifecycleHandler(
        lifecycle_manager=coordinator.lifecycle_manager,
        policy_coordinator=coordinator,
    )

    base = _dt(2026, 4, 13, 10, 0, 0)
    session = runtime_session_stub(
        lifecycle_state=handler.bootstrap_session("sess-1", tmp_path, now_utc=base),
    )
    reset_calls = 0

    def _on_reset() -> None:
        nonlocal reset_calls
        reset_calls += 1

    first = handler.refresh_session(
        session,
        now_utc=base + timedelta(seconds=4),
        reset_runtime_state=_on_reset,
    )
    second = handler.refresh_session(
        session,
        now_utc=base + timedelta(seconds=11),
        reset_runtime_state=_on_reset,
    )

    assert first is False
    assert second is True
    assert reset_calls == 1
    assert coordinator.lifecycle_auto_resets == 1
