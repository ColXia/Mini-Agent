from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from mini_agent.tui.session_approval_command_coordinator import TuiSessionApprovalCommandCoordinator


def _session(*, pending: list[dict[str, Any]] | None = None, loop: Any = None) -> Any:
    return SimpleNamespace(
        title="Session 1",
        projection=SimpleNamespace(
            pending_approvals=list(pending or []),
        ),
        runtime=SimpleNamespace(
            submission_loop=loop,
        ),
    )


def test_tui_approval_command_coordinator_handles_remote_success() -> None:
    session = _session(pending=[{"token": "tok-1", "tool_name": "shell"}])
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    clear_calls: list[str | None] = []
    close_calls: list[str] = []
    render_calls: list[str] = []
    sync_calls: list[str] = []

    async def _remote_respond(_session: Any, approved: bool, token: str | None) -> Any:
        assert approved is True
        assert token is None
        return SimpleNamespace(token="tok-1", tool_name="shell", decision="approved")

    async def _sync_remote_detail(_session: Any) -> None:
        sync_calls.append("synced")

    def _clear_pending(_session: Any, token: str | None) -> None:
        clear_calls.append(token)
        _session.projection.pending_approvals = []

    coordinator = TuiSessionApprovalCommandCoordinator(
        runs_via_gateway=lambda _session: True,
        has_local_runtime_state=lambda _session: False,
        pending_approval_token=lambda payload: str(payload.get("token") or ""),
        remote_respond_to_approval=_remote_respond,
        sync_remote_session_detail=_sync_remote_detail,
        clear_pending_approval=_clear_pending,
        close_approval_modal=lambda: close_calls.append("closed"),
        append_command_feedback=lambda command, **kwargs: feedback_calls.append(
            {"command": command, **kwargs}
        ),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    result = asyncio.run(coordinator.respond(session=session, approved=True))

    assert result is True
    assert clear_calls == ["tok-1"]
    assert sync_calls == ["synced"]
    assert close_calls == ["closed"]
    assert feedback_calls == [
        {
            "command": "approve tok-1",
            "summary": "approved shell",
            "details": "Approved pending tool call for shell.",
        }
    ]
    assert status_calls == ["Approved shell for Session 1."]
    assert render_calls == ["rendered"]


def test_tui_approval_command_coordinator_handles_remote_error() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    async def _remote_respond(_session: Any, approved: bool, token: str | None) -> Any:
        _ = (approved, token)
        raise RuntimeError("Gateway HTTP 409: Multiple approvals pending. Specify a token.")

    coordinator = TuiSessionApprovalCommandCoordinator(
        runs_via_gateway=lambda _session: True,
        has_local_runtime_state=lambda _session: False,
        pending_approval_token=lambda payload: str(payload.get("token") or ""),
        remote_respond_to_approval=_remote_respond,
        sync_remote_session_detail=lambda _session: asyncio.sleep(0),
        clear_pending_approval=lambda _session, token: None,
        close_approval_modal=lambda: None,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append(
            {"command": command, **kwargs}
        ),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    result = asyncio.run(coordinator.respond(session=session, approved=True))

    assert result is False
    assert feedback_calls == [
        {
            "command": "approve",
            "summary": "token required",
            "details": "Multiple approvals pending. Specify a token.",
            "level": "error",
        }
    ]
    assert status_calls == ["Specify approval token."]
    assert render_calls == ["rendered"]


def test_tui_approval_command_coordinator_handles_local_success() -> None:
    class _Loop:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def submit_exec_approval(self, *, approved: bool, token: str) -> None:
            self.calls.append({"approved": approved, "token": token})

    loop = _Loop()
    session = _session(
        pending=[{"token": "tok-local-1", "tool_name": "bash"}],
        loop=loop,
    )
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    clear_calls: list[str | None] = []
    close_calls: list[str] = []
    render_calls: list[str] = []

    def _clear_pending(_session: Any, token: str | None) -> None:
        clear_calls.append(token)
        _session.projection.pending_approvals = []

    coordinator = TuiSessionApprovalCommandCoordinator(
        runs_via_gateway=lambda _session: False,
        has_local_runtime_state=lambda _session: True,
        pending_approval_token=lambda payload: str(payload.get("token") or ""),
        remote_respond_to_approval=lambda _session, approved, token: asyncio.sleep(0),
        sync_remote_session_detail=lambda _session: asyncio.sleep(0),
        clear_pending_approval=_clear_pending,
        close_approval_modal=lambda: close_calls.append("closed"),
        append_command_feedback=lambda command, **kwargs: feedback_calls.append(
            {"command": command, **kwargs}
        ),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    result = asyncio.run(coordinator.respond(session=session, approved=False))

    assert result is True
    assert loop.calls == [{"approved": False, "token": "tok-local-1"}]
    assert clear_calls == ["tok-local-1"]
    assert close_calls == ["closed"]
    assert feedback_calls == [
        {
            "command": "deny tok-local-1",
            "summary": "denied bash",
            "details": "Denied pending tool call for bash.",
        }
    ]
    assert status_calls == ["Denied bash for Session 1."]
    assert render_calls == ["rendered"]


def test_tui_approval_command_coordinator_requires_token_for_multiple_local_pending() -> None:
    session = _session(
        pending=[
            {"token": "tok-local-1", "tool_name": "shell"},
            {"token": "tok-local-2", "tool_name": "bash"},
        ],
        loop=SimpleNamespace(submit_exec_approval=lambda **kwargs: None),
    )
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    coordinator = TuiSessionApprovalCommandCoordinator(
        runs_via_gateway=lambda _session: False,
        has_local_runtime_state=lambda _session: True,
        pending_approval_token=lambda payload: str(payload.get("token") or ""),
        remote_respond_to_approval=lambda _session, approved, token: asyncio.sleep(0),
        sync_remote_session_detail=lambda _session: asyncio.sleep(0),
        clear_pending_approval=lambda _session, token: None,
        close_approval_modal=lambda: None,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append(
            {"command": command, **kwargs}
        ),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    result = asyncio.run(coordinator.respond(session=session, approved=True))

    assert result is False
    assert feedback_calls == [
        {
            "command": "approve",
            "summary": "token required",
            "details": "Multiple approvals pending. Specify a token: tok-local-1, tok-local-2",
            "level": "error",
        }
    ]
    assert status_calls == ["Specify approval token."]
    assert render_calls == ["rendered"]
