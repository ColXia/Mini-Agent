from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from mini_agent.commands.execution import CommandExecutionResult
from mini_agent.transport import GatewayTransportError
from mini_agent.tui.session_kb_command_coordinator import TuiSessionKbCommandCoordinator


def _session() -> Any:
    return SimpleNamespace(
        title="Session 1",
        projection=SimpleNamespace(busy=False, knowledge_base_enabled=None),
        runtime=SimpleNamespace(agent=None),
    )


def test_tui_kb_command_coordinator_handles_plan_error() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    coordinator = TuiSessionKbCommandCoordinator(
        resolve_kb_command_plan=lambda args: CommandExecutionResult(
            command="kb",
            summary="unknown action",
            details="Unknown kb action: frob.",
            status_text="Unknown kb action.",
            kind="error",
        ),
        runs_via_gateway=lambda _session: False,
        sync_remote_session_detail=lambda _session: asyncio.sleep(0),
        execute_remote_kb_command=lambda _session, _plan: asyncio.sleep(0),
        execute_local_kb_command=lambda **kwargs: asyncio.sleep(0),
        session_knowledge_base_enabled=lambda _session: None,
        apply_agent_knowledge_base_enabled=lambda _agent, enabled: enabled,
        refresh_local_runtime_projection=lambda _session: None,
        persist_session_state=lambda: None,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["frob"]))

    assert feedback_calls == [
        {
            "command": "kb",
            "summary": "unknown action",
            "details": "Unknown kb action: frob.",
            "level": "error",
        }
    ]
    assert status_calls == ["Unknown kb action."]
    assert render_calls == ["rendered"]


def test_tui_kb_command_coordinator_handles_remote_status_sync_failure() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []
    status_runs: list[str] = []

    async def _broken_sync(_session: Any) -> None:
        raise GatewayTransportError("Gateway HTTP 503: kb sync unavailable", status_code=503)

    async def _run_status(_session: Any, _args: list[str]) -> CommandExecutionResult:
        status_runs.append("ran")
        return CommandExecutionResult(
            command="kb status",
            summary="knowledge base enabled",
            details="Knowledge base is enabled for Session 1.",
            status_text="Knowledge base is enabled.",
        )

    coordinator = TuiSessionKbCommandCoordinator(
        resolve_kb_command_plan=lambda args: SimpleNamespace(command="kb status", action="status"),
        runs_via_gateway=lambda _session: True,
        sync_remote_session_detail=_broken_sync,
        execute_remote_kb_command=lambda _session, _plan: asyncio.sleep(0),
        execute_local_kb_command=lambda **kwargs: _run_status(session, kwargs["args"]),
        session_knowledge_base_enabled=lambda _session: True,
        apply_agent_knowledge_base_enabled=lambda _agent, enabled: enabled,
        refresh_local_runtime_projection=lambda _session: None,
        persist_session_state=lambda: None,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["status"]))

    assert status_runs == []
    assert feedback_calls == [
        {
            "command": "kb status",
            "summary": "status failed",
            "details": "Remote KB status failed: kb sync unavailable",
            "level": "error",
        }
    ]
    assert status_calls == ["Remote KB status failed."]
    assert render_calls == ["rendered"]


def test_tui_kb_command_coordinator_handles_status_flow() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []
    sync_calls: list[str] = []

    async def _sync(_session: Any) -> None:
        sync_calls.append("synced")

    async def _run_status(_session: Any, _args: list[str]) -> CommandExecutionResult:
        return CommandExecutionResult(
            command="kb status",
            summary="knowledge base enabled",
            details="Knowledge base is enabled for Session 1.",
            status_text="Knowledge base is enabled.",
        )

    coordinator = TuiSessionKbCommandCoordinator(
        resolve_kb_command_plan=lambda args: SimpleNamespace(command="kb status", action="status"),
        runs_via_gateway=lambda _session: True,
        sync_remote_session_detail=_sync,
        execute_remote_kb_command=lambda _session, _plan: asyncio.sleep(0),
        execute_local_kb_command=lambda **kwargs: _run_status(session, kwargs["args"]),
        session_knowledge_base_enabled=lambda _session: True,
        apply_agent_knowledge_base_enabled=lambda _agent, enabled: enabled,
        refresh_local_runtime_projection=lambda _session: None,
        persist_session_state=lambda: None,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["status"]))

    assert sync_calls == ["synced"]
    assert feedback_calls == [
        {
            "command": "kb status",
            "summary": "knowledge base enabled",
            "details": "Knowledge base is enabled for Session 1.",
            "metadata": {"threads_visible": False},
        }
    ]
    assert status_calls == ["Knowledge base is enabled."]
    assert render_calls == ["rendered"]


def test_tui_kb_command_coordinator_routes_remote_toggle() -> None:
    session = _session()
    remote_calls: list[tuple[Any, str]] = []
    render_calls: list[str] = []

    async def _execute_remote(target_session: Any, plan: Any) -> None:
        remote_calls.append((target_session, plan.action))

    coordinator = TuiSessionKbCommandCoordinator(
        resolve_kb_command_plan=lambda args: SimpleNamespace(command="kb off", action="off"),
        runs_via_gateway=lambda _session: True,
        sync_remote_session_detail=lambda _session: asyncio.sleep(0),
        execute_remote_kb_command=_execute_remote,
        execute_local_kb_command=lambda **kwargs: asyncio.sleep(0),
        session_knowledge_base_enabled=lambda _session: True,
        apply_agent_knowledge_base_enabled=lambda _agent, enabled: enabled,
        refresh_local_runtime_projection=lambda _session: None,
        persist_session_state=lambda: None,
        append_command_feedback=lambda command, **kwargs: None,
        set_status=lambda text: None,
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["off"]))

    assert remote_calls == [(session, "off")]
    assert render_calls == ["rendered"]


def test_tui_kb_command_coordinator_runs_local_toggle_and_emits_feedback() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []
    local_calls: list[dict[str, Any]] = []
    persisted: list[str] = []

    async def _run_local(**kwargs: Any) -> CommandExecutionResult:
        local_calls.append(dict(kwargs))
        return CommandExecutionResult(
            command="kb off",
            summary="knowledge base disabled",
            details="Knowledge base is disabled for Session 1.",
            status_text="Knowledge base disabled for Session 1.",
            payload={"enabled": False},
        )

    coordinator = TuiSessionKbCommandCoordinator(
        resolve_kb_command_plan=lambda args: SimpleNamespace(command="kb off", action="off"),
        runs_via_gateway=lambda _session: False,
        sync_remote_session_detail=lambda _session: asyncio.sleep(0),
        execute_remote_kb_command=lambda _session, _plan: asyncio.sleep(0),
        execute_local_kb_command=_run_local,
        session_knowledge_base_enabled=lambda _session: True,
        apply_agent_knowledge_base_enabled=lambda _agent, enabled: enabled,
        refresh_local_runtime_projection=lambda _session: None,
        persist_session_state=lambda: persisted.append("persisted"),
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["off"]))

    assert len(local_calls) == 1
    assert local_calls[0]["action"] == "off"
    assert local_calls[0]["current_enabled"] is True
    assert local_calls[0]["busy"] is False
    assert session.projection.knowledge_base_enabled is False
    assert persisted == ["persisted"]
    assert feedback_calls == [
        {
            "command": "kb off",
            "summary": "knowledge base disabled",
            "details": "Knowledge base is disabled for Session 1.",
            "level": "info",
            "metadata": {"threads_visible": False},
        }
    ]
    assert status_calls == ["Knowledge base disabled for Session 1."]
    assert render_calls == ["rendered"]
