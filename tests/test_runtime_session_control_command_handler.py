from __future__ import annotations

import asyncio
from types import SimpleNamespace

from mini_agent.runtime.handlers.session_agent_control_handler import RuntimeSessionControlCommand
from mini_agent.runtime.handlers.session_control_command_handler import (
    RuntimeSessionControlCommandHandler,
)
from tests.runtime_contract_fixtures import (
    runtime_projection_stub,
    runtime_session_stub,
)


def _build_control_handler(**overrides):
    defaults = dict(
        session_commands=SimpleNamespace(),
        session_agent_control=SimpleNamespace(),
        session_mcp_control=SimpleNamespace(),
        session_agent_runtime=SimpleNamespace(
            rebuild_agent_with_identity=lambda *args, **kwargs: None,  # noqa: ARG005
        ),
        selected_model_identity=lambda _session: None,
        cleanup_mcp_connections=lambda: None,
    )
    defaults.update(overrides)
    return RuntimeSessionControlCommandHandler(**defaults)


def test_runtime_session_control_command_handler_routes_agent_control_actions() -> None:
    calls: list[str] = []

    async def _agent_execute(session, command):  # noqa: ANN001
        calls.append(f"agent:{command.action}")
        return SimpleNamespace(response="agent")

    handler = _build_control_handler(
        session_agent_control=SimpleNamespace(execute=_agent_execute),
    )
    session = runtime_session_stub(
        session_id="sess-control",
        projection=runtime_projection_stub(active_surface="tui", origin_surface="tui"),
    )

    execution = asyncio.run(
        handler._execute_session_control(
            session,
            command=RuntimeSessionControlCommand(action="restart", reason=None),
            normalized_action="restart",
        )
    )

    assert execution.response == "agent"
    assert calls == ["agent:restart"]


def test_runtime_session_control_command_handler_routes_mcp_control_actions() -> None:
    calls: list[str] = []

    async def _mcp_execute(session, command, *, cleanup_mcp_connections, rebuild_session_agent):  # noqa: ANN001
        _ = cleanup_mcp_connections
        rebuild_session_agent()
        calls.append(f"mcp:{command.action}")
        return SimpleNamespace(response="mcp")

    handler = _build_control_handler(
        session_mcp_control=SimpleNamespace(execute=_mcp_execute),
        session_agent_runtime=SimpleNamespace(
            rebuild_agent_with_identity=lambda *args, **kwargs: calls.append("rebuild"),  # noqa: ARG005
        ),
        selected_model_identity=lambda _session: ("source", "provider", "model"),
    )
    session = runtime_session_stub(
        session_id="sess-mcp",
        projection=runtime_projection_stub(active_surface="tui", origin_surface="tui"),
    )

    execution = asyncio.run(
        handler._execute_session_control(
            session,
            command=RuntimeSessionControlCommand(action="mcp_reload", reason=None),
            normalized_action="mcp_reload",
        )
    )

    assert execution.response == "mcp"
    assert calls == ["rebuild", "mcp:mcp_reload"]
