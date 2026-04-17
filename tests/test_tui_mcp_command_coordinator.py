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
        dispatch_remote_control_command=lambda **kwargs: asyncio.sleep(0, result=None),
        mcp_remote_status_text=lambda action: f"remote {action}",
        execute_local_mcp_command=lambda **kwargs: asyncio.sleep(0),
        reload_local_mcp_bindings=lambda _session: asyncio.sleep(0),
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

    async def _dispatch_remote(**kwargs: Any) -> tuple[Any, bool] | None:
        assert kwargs["session"] is session
        assert kwargs["command_text"] == "mcp reload"
        assert kwargs["action"] == "mcp_reload"
        assert kwargs["metadata"] == {"threads_visible": False}
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
        dispatch_remote_control_command=_dispatch_remote,
        mcp_remote_status_text=lambda action: {
            "reload": "Shared MCP bindings reloaded.",
        }.get(action, "Shared MCP status shown."),
        execute_local_mcp_command=lambda **kwargs: asyncio.sleep(0),
        reload_local_mcp_bindings=lambda _session: asyncio.sleep(0),
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

    async def _dispatch_remote(**kwargs: Any) -> tuple[Any, bool] | None:
        assert kwargs["session"] is session
        assert kwargs["command_text"] == "mcp status"
        assert kwargs["action"] == "mcp_status"
        return (SimpleNamespace(stats={"summary": "ignored"}), True)

    coordinator = TuiSessionMcpCommandCoordinator(
        resolve_mcp_command_plan=lambda args: SimpleNamespace(command="mcp status", action="status"),
        runs_via_gateway=lambda _session: True,
        dispatch_remote_control_command=_dispatch_remote,
        mcp_remote_status_text=lambda action: "Shared MCP status shown.",
        execute_local_mcp_command=lambda **kwargs: asyncio.sleep(0),
        reload_local_mcp_bindings=lambda _session: asyncio.sleep(0),
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
    local_calls: list[dict[str, Any]] = []
    reload_calls: list[str] = []

    async def _reload_local(_session: Any) -> Any:
        reload_calls.append("reloaded")
        return {"rebuilt_runtime": True, "active_model_label": "openai/gpt-5.4"}

    async def _run_local(**kwargs: Any) -> CommandExecutionResult:
        local_calls.append(dict(kwargs))
        reload_callback = kwargs.get("reload_callback")
        assert callable(reload_callback)
        outcome = await reload_callback()
        assert outcome["active_model_label"] == "openai/gpt-5.4"
        return CommandExecutionResult(
            command="mcp reload",
            summary="reloaded MCP | 1 active server(s) | 2 tool(s)",
            details="MCP Status:\n- connected",
            status_text="MCP bindings reloaded.",
        )

    coordinator = TuiSessionMcpCommandCoordinator(
        resolve_mcp_command_plan=lambda args: SimpleNamespace(command="mcp reload", action="reload"),
        runs_via_gateway=lambda _session: False,
        dispatch_remote_control_command=lambda **kwargs: asyncio.sleep(0, result=None),
        mcp_remote_status_text=lambda action: f"remote {action}",
        execute_local_mcp_command=_run_local,
        reload_local_mcp_bindings=_reload_local,
        append_command_feedback=lambda command, **kwargs: feedback_calls.append({"command": command, **kwargs}),
        set_status=lambda text: status_calls.append(text),
        render_all=lambda: render_calls.append("rendered"),
    )

    asyncio.run(coordinator.handle(session, ["reload"]))

    assert len(local_calls) == 1
    assert local_calls[0]["action"] == "reload"
    assert local_calls[0]["busy_label"] == "Session 1"
    assert reload_calls == ["reloaded"]
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
