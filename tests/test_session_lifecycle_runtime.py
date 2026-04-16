"""Tests for shared surface session lifecycle runtime helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from mini_agent.agent_core.session import SessionLifecyclePolicy, SessionResetMode
from mini_agent.runtime.session_lifecycle import (
    SESSION_IDLE_SECONDS_ENV,
    SESSION_RESET_MODE_ENV,
    SurfaceSessionLifecycleRuntime,
    build_surface_session_key,
    resolve_session_lifecycle_policy,
)
from mini_agent.runtime.workspace_path_utils import workspace_path_key


def _dt(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def test_resolve_session_lifecycle_policy_reads_env(monkeypatch) -> None:
    monkeypatch.setenv(SESSION_RESET_MODE_ENV, "idle")
    monkeypatch.setenv(SESSION_IDLE_SECONDS_ENV, "45")

    policy = resolve_session_lifecycle_policy()

    assert policy.mode == SessionResetMode.IDLE
    assert policy.idle_seconds == 45


def test_resolve_session_lifecycle_policy_falls_back_for_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv(SESSION_RESET_MODE_ENV, "invalid-mode")
    monkeypatch.setenv(SESSION_IDLE_SECONDS_ENV, "invalid-seconds")

    policy = resolve_session_lifecycle_policy()
    assert policy.mode == SessionResetMode.NONE
    assert policy.idle_seconds == 1800

    policy_min_idle = resolve_session_lifecycle_policy(reset_mode_raw="idle", idle_seconds_raw="-5")
    assert policy_min_idle.mode == SessionResetMode.IDLE
    assert policy_min_idle.idle_seconds == 1


def test_build_surface_session_key_normalizes_surface_and_workspace(tmp_path: Path) -> None:
    key = build_surface_session_key(
        surface="  TUI  Console ",
        workspace_dir=tmp_path,
        session_id="session-1",
        agent_id="main-agent",
    )

    assert key.agent_id == "main-agent"
    assert key.channel == "tui console"
    assert key.peer_kind == "workspace"
    assert key.peer_id == workspace_path_key(tmp_path)
    assert key.thread_id == "session-1"


def test_surface_session_lifecycle_runtime_idle_reset_and_force_reset(tmp_path: Path) -> None:
    runtime = SurfaceSessionLifecycleRuntime(
        surface=" cli ",
        workspace_dir=tmp_path,
        policy=SessionLifecyclePolicy(mode=SessionResetMode.IDLE, idle_seconds=5),
    )
    reset_calls = 0

    def _on_reset() -> None:
        nonlocal reset_calls
        reset_calls += 1

    base = _dt(2026, 1, 1, 8, 0, 0)
    first = runtime.ensure_active("s-1", now_utc=base, on_reset=_on_reset)
    assert first.reset is False

    second = runtime.ensure_active("s-1", now_utc=base + timedelta(seconds=4), on_reset=_on_reset)
    assert second.reset is False

    third = runtime.ensure_active("s-1", now_utc=base + timedelta(seconds=11), on_reset=_on_reset)
    assert third.reset is True
    assert third.reason == "idle"
    assert reset_calls == 1
    assert runtime.auto_reset_count == 1

    runtime.force_reset("s-1", now_utc=base + timedelta(seconds=12), on_reset=_on_reset)
    assert reset_calls == 2
    assert runtime.auto_reset_count == 1

    runtime.drop_session("s-1")
    after_drop = runtime.ensure_active("s-1", now_utc=base + timedelta(seconds=13))
    assert after_drop.reset is False
