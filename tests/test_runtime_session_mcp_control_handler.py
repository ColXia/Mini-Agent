from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from mini_agent.runtime.handlers.session_agent_control_handler import RuntimeSessionControlCommand
from mini_agent.runtime.handlers.session_mcp_control_handler import RuntimeSessionMcpControlHandler
from tests.runtime_contract_fixtures import runtime_projection_stub, runtime_session_stub


def _session(*, busy: bool = False):
    return runtime_session_stub(
        session_id="sess-mcp",
        projection=runtime_projection_stub(
            busy=busy,
            active_surface="qq",
            origin_surface="cli",
            knowledge_base_enabled=True,
        ),
    )


def _handler() -> RuntimeSessionMcpControlHandler:
    return RuntimeSessionMcpControlHandler(
        normalize_surface=lambda value: value,
        load_runtime_config=lambda: object(),
        collect_mcp_operator_snapshot=lambda config: SimpleNamespace(
            configured_total=3,
            discoverable_total=2,
            disabled_total=1,
            active_total=1,
            tool_total=4,
        ),
        format_mcp_status=lambda snapshot: f"status active={snapshot.active_total} tools={snapshot.tool_total}",
        format_mcp_server_list=lambda snapshot: f"servers configured={snapshot.configured_total}",
    )


@pytest.mark.asyncio
async def test_mcp_control_handler_reports_mcp_list_without_rebuild() -> None:
    handler = _handler()

    execution = await handler.execute(
        _session(busy=True),
        RuntimeSessionControlCommand(action="mcp_list"),
        cleanup_mcp_connections=lambda: _async_noop(),
        rebuild_session_agent=lambda: _async_noop(),
    )

    assert execution.response.action == "mcp_list"
    assert execution.response.applied is False
    assert execution.response.active_surface == "qq"
    assert execution.response.stats is not None
    assert execution.response.stats["summary"] == "3 configured server(s) | 1 active"
    assert "status active=1 tools=4" in execution.transcript_details
    assert "servers configured=3" in execution.transcript_details


@pytest.mark.asyncio
async def test_mcp_control_handler_reload_cleans_up_and_rebuilds_agent() -> None:
    calls = {"cleanup": 0, "rebuild": 0}
    handler = _handler()

    async def _cleanup() -> None:
        calls["cleanup"] += 1

    async def _rebuild() -> None:
        calls["rebuild"] += 1

    execution = await handler.execute(
        _session(),
        RuntimeSessionControlCommand(action="mcp_reload"),
        cleanup_mcp_connections=_cleanup,
        rebuild_session_agent=_rebuild,
    )

    assert execution.response.action == "mcp_reload"
    assert execution.response.applied is True
    assert execution.transcript_summary == "reloaded MCP | 1 active server(s) | 4 tool(s)"
    assert calls == {"cleanup": 1, "rebuild": 1}


@pytest.mark.asyncio
async def test_mcp_control_handler_blocks_reload_while_busy() -> None:
    handler = _handler()

    with pytest.raises(HTTPException) as excinfo:
        await handler.execute(
            _session(busy=True),
            RuntimeSessionControlCommand(action="mcp_reload"),
            cleanup_mcp_connections=lambda: _async_noop(),
            rebuild_session_agent=lambda: _async_noop(),
        )

    assert excinfo.value.status_code == 409
    assert "Session is busy" in str(excinfo.value.detail)


async def _async_noop() -> None:
    return None
