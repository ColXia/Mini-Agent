from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from mini_agent.commands import CommandExecutionResult
from mini_agent.tui.session_mcp_command_coordinator import TuiSessionMcpCommandCoordinator


def _session() -> Any:
    return SimpleNamespace(
        title="Session 1",
        projection=SimpleNamespace(),
    )


def test_tui_mcp_command_coordinator_handles_plan_error() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    coordinator = TuiSessionMcpCommandCoordinator(
        resolve_mcp_command_plan=lambda args: CommandExecutionResult(
            command="mcp",
            summary="unknown action",
            details="Unknown mcp action: frob.",
            status_text="Unknown mcp action.",
            kind="error",
        ),
        runs_via_gateway=lambda _session: False,
        dispatch_remote_mcp_command=lambda _session, _plan: asyncio.sleep(0, result=None),
        mcp_remote_status_text=lambda action: f"remote {action}",
        run_local_mcp_command_result=lambda _session, _args, _plan: asyncio.sleep(0),
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["frob"]))

    assert feedback_calls == [
        {
            "command": "mcp",
            "summary": "unknown action",
            "details": "Unknown mcp action: frob.",
            "level": "error",
            "metadata": {"threads_visible": False},
        }
    ]
    assert status_calls == ["Unknown mcp action."]
    assert render_calls == ["rendered"]


def test_tui_mcp_command_coordinator_handles_unsynced_remote_result() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    async def _dispatch_remote(_session: Any, plan: Any) -> tuple[Any, bool] | None:
        assert plan.action == "reload"
        return (
            {
                "stats": {
                    "summary": "reloaded MCP | 2 active server(s) | 5 tool(s)",
                    "details": "MCP Status:\n- refreshed",
                }
            },
            False,
        )

    coordinator = TuiSessionMcpCommandCoordinator(
        resolve_mcp_command_plan=lambda args: SimpleNamespace(command="mcp reload", action="reload"),
        runs_via_gateway=lambda _session: True,
        dispatch_remote_mcp_command=_dispatch_remote,
        mcp_remote_status_text=lambda action: {
            "reload": "Shared MCP bindings reloaded.",
        }.get(action, "Shared MCP status shown."),
        run_local_mcp_command_result=lambda _session, _args, _plan: asyncio.sleep(0),
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["reload"]))

    assert feedback_calls == [
        {
            "command": "mcp reload",
            "summary": "reloaded MCP | 2 active server(s) | 5 tool(s)",
            "details": "MCP Status:\n- refreshed",
            "metadata": {"threads_visible": False},
        }
    ]
    assert status_calls == ["Shared MCP bindings reloaded."]
    assert render_calls == ["rendered"]


def test_tui_mcp_command_coordinator_handles_synced_remote_result_without_duplicate_feedback() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []

    async def _dispatch_remote(_session: Any, plan: Any) -> tuple[Any, bool] | None:
        assert plan.action == "status"
        return (SimpleNamespace(stats={"summary": "ignored"}), True)

    coordinator = TuiSessionMcpCommandCoordinator(
        resolve_mcp_command_plan=lambda args: SimpleNamespace(command="mcp status", action="status"),
        runs_via_gateway=lambda _session: True,
        dispatch_remote_mcp_command=_dispatch_remote,
        mcp_remote_status_text=lambda action: "Shared MCP status shown.",
        run_local_mcp_command_result=lambda _session, _args, _plan: asyncio.sleep(0),
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["status"]))

    assert feedback_calls == []
    assert status_calls == ["Shared MCP status shown."]
    assert render_calls == ["rendered"]


def test_tui_mcp_command_coordinator_runs_local_flow_and_emits_feedback() -> None:
    session = _session()
    feedback_calls: list[dict[str, Any]] = []
    status_calls: list[str] = []
    render_calls: list[str] = []
    local_calls: list[tuple[Any, str]] = []

    async def _run_local(target_session: Any, _args: list[str], plan: Any) -> CommandExecutionResult:
        local_calls.append((target_session, plan.action))
        return CommandExecutionResult(
            command="mcp reload",
            summary="reloaded MCP | 1 active server(s) | 2 tool(s)",
            details="MCP Status:\n- connected",
            status_text="MCP bindings reloaded.",
        )

    coordinator = TuiSessionMcpCommandCoordinator(
        resolve_mcp_command_plan=lambda args: SimpleNamespace(command="mcp reload", action="reload"),
        runs_via_gateway=lambda _session: False,
        dispatch_remote_mcp_command=lambda _session, _plan: asyncio.sleep(0, result=None),
        mcp_remote_status_text=lambda action: f"remote {action}",
        run_local_mcp_command_result=_run_local,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["reload"]))

    assert local_calls == [(session, "reload")]
    assert feedback_calls == [
        {
            "command": "mcp reload",
            "summary": "reloaded MCP | 1 active server(s) | 2 tool(s)",
            "details": "MCP Status:\n- connected",
            "level": "info",
            "metadata": {"threads_visible": False},
        }
    ]
    assert status_calls == ["MCP bindings reloaded."]
    assert render_calls == ["rendered"]
