from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from mini_agent.tui.session_runtime_policy_command_coordinator import (
    TuiSessionRuntimePolicyCommandCoordinator,
)


def _session() -> Any:
    return SimpleNamespace(
        title="Session 1",
        projection=SimpleNamespace(
            sandbox_diagnostics={
                "approval_profile": "build",
                "access_level": "default",
                "sandbox_mode": "workspace",
            }
        ),
    )


def test_tui_runtime_policy_command_coordinator_handles_unchanged_policy() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    coordinator = TuiSessionRuntimePolicyCommandCoordinator(
        session_runtime_policy=lambda _session: ("plan", "full-access"),
        runs_via_gateway=lambda _session: False,
        apply_local_session_runtime_policy=lambda _session, approval_profile, access_level: asyncio.sleep(0),
        apply_remote_session_runtime_policy=lambda _session, approval_profile, access_level: asyncio.sleep(0),
        normalize_sandbox_diagnostics_payload=lambda value: dict(value or {}),
        append_command_feedback=lambda command, **kwargs: feedback_calls.append(
            {"command": command, **kwargs}
        ),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    result = asyncio.run(
        coordinator.update(
            session,
            approval_profile="plan",
            access_level="full-access",
            command_label="plan",
        )
    )

    assert result is True
    assert feedback_calls == [
        {
            "command": "plan",
            "summary": "runtime unchanged",
            "details": "Session 1 already uses plan / full-access.",
        }
    ]
    assert status_calls == ["Session 1 already uses plan / full-access."]
    assert render_calls == ["rendered"]


def test_tui_runtime_policy_command_coordinator_handles_remote_success() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    async def _apply_remote(_session: Any, approval_profile: str, access_level: str) -> Any:
        assert approval_profile == "plan"
        assert access_level == "full-access"
        return SimpleNamespace(
            summary="runtime plan / full-access",
            details="Runtime policy updated.\n- session: Session 1\n- execution: plan\n- access: full-access",
            sandbox_diagnostics={
                "approval_profile": "plan",
                "access_level": "full-access",
                "sandbox_mode": "unrestricted",
            },
        )

    coordinator = TuiSessionRuntimePolicyCommandCoordinator(
        session_runtime_policy=lambda _session: ("build", "default"),
        runs_via_gateway=lambda _session: True,
        apply_local_session_runtime_policy=lambda _session, approval_profile, access_level: asyncio.sleep(0),
        apply_remote_session_runtime_policy=_apply_remote,
        normalize_sandbox_diagnostics_payload=lambda value: dict(value or {}),
        append_command_feedback=lambda command, **kwargs: feedback_calls.append(
            {"command": command, **kwargs}
        ),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    result = asyncio.run(
        coordinator.update(
            session,
            approval_profile="plan",
            access_level="full-access",
            command_label="full-access",
        )
    )

    assert result is True
    assert session.projection.sandbox_diagnostics == {
        "approval_profile": "plan",
        "access_level": "full-access",
        "sandbox_mode": "unrestricted",
    }
    assert feedback_calls == [
        {
            "command": "full-access",
            "summary": "runtime plan / full-access",
            "details": "Runtime policy updated.\n- session: Session 1\n- execution: plan\n- access: full-access",
            "metadata": {"threads_visible": False},
        }
    ]
    assert status_calls == ["Session 1: runtime set to plan / full-access."]
    assert render_calls == ["rendered"]


def test_tui_runtime_policy_command_coordinator_handles_failure() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    async def _apply_local(_session: Any, approval_profile: str, access_level: str) -> dict[str, Any]:
        _ = (approval_profile, access_level)
        raise RuntimeError("Session is busy. Runtime mode can only change while idle or waiting on approval.")

    coordinator = TuiSessionRuntimePolicyCommandCoordinator(
        session_runtime_policy=lambda _session: ("build", "default"),
        runs_via_gateway=lambda _session: False,
        apply_local_session_runtime_policy=_apply_local,
        apply_remote_session_runtime_policy=lambda _session, approval_profile, access_level: asyncio.sleep(0),
        normalize_sandbox_diagnostics_payload=lambda value: dict(value or {}),
        append_command_feedback=lambda command, **kwargs: feedback_calls.append(
            {"command": command, **kwargs}
        ),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    result = asyncio.run(coordinator.update(session, approval_profile="plan", command_label="plan"))

    assert result is False
    assert feedback_calls == [
        {
            "command": "plan",
            "summary": "runtime policy failed",
            "details": (
                "Runtime policy update failed: "
                "Session is busy. Runtime mode can only change while idle or waiting on approval."
            ),
            "level": "error",
        }
    ]
    assert status_calls == [
        "Runtime policy update failed: Session is busy. Runtime mode can only change while idle or waiting on approval."
    ]
    assert render_calls == ["rendered"]


