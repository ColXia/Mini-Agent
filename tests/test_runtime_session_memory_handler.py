from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from mini_agent.runtime.handlers.session_memory_command_handler import (
    RuntimeSessionMemoryCommandExecution,
)
from mini_agent.runtime.handlers.session_memory_handler import RuntimeSessionMemoryHandler
from tests.runtime_contract_fixtures import runtime_projection_stub, runtime_session_stub


def _build_memory_handler(**overrides):
    defaults = dict(
        normalize_surface=lambda value: str(value or "tui"),
        session_commands=SimpleNamespace(
            execute_locked=lambda session, **kwargs: kwargs["operation"](),  # noqa: ARG005
        ),
        session_memory_commands=SimpleNamespace(),
        persist_session=lambda _session: None,
    )
    defaults.update(overrides)
    return RuntimeSessionMemoryHandler(**defaults)


def test_runtime_session_memory_handler_non_mutating_actions_persist_immediately() -> None:
    persisted: list[str] = []
    handler = _build_memory_handler(
        session_memory_commands=SimpleNamespace(
            validate_action=lambda action: None,  # noqa: ARG005
            is_mutating_action=lambda action: False,  # noqa: ARG005
            execute=lambda session, command: RuntimeSessionMemoryCommandExecution(
                memory_diagnostics={"status": "ok"},
                result={"summary": f"memory {command.action}", "details": "done"},
            ),
        ),
        persist_session=lambda session: persisted.append(session.session_id),
    )
    session = runtime_session_stub(
        session_id="sess-memory",
        projection=runtime_projection_stub(active_surface="desktop", origin_surface="desktop"),
    )

    response = asyncio.run(handler.manage_memory(session, action="show", detail_mode="brief"))

    assert response.status == "ok"
    assert response.action == "show"
    assert response.result["summary"] == "memory show"
    assert persisted == ["sess-memory"]


def test_runtime_session_memory_handler_mutating_busy_actions_raise_busy_detail() -> None:
    handler = _build_memory_handler(
        session_memory_commands=SimpleNamespace(
            validate_action=lambda action: None,  # noqa: ARG005
            is_mutating_action=lambda action: True,  # noqa: ARG005
            execute=lambda session, command: RuntimeSessionMemoryCommandExecution(
                memory_diagnostics={},
                result={},
            ),
        ),
    )
    session = runtime_session_stub(
        session_id="sess-memory-busy",
        projection=runtime_projection_stub(busy=True, active_surface="tui", origin_surface="tui"),
    )

    with pytest.raises(HTTPException, match="Session is busy"):
        asyncio.run(handler.manage_memory(session, action="save_note", content="remember this"))
