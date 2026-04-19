from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from mini_agent.memory.command_service import MemoryCommandError, MemoryCommandRequest
from mini_agent.memory.diagnostics import build_memory_diagnostics
from mini_agent.runtime.handlers.session_memory_command_handler import (
    RuntimeSessionMemoryCommand,
    RuntimeSessionMemoryCommandHandler,
)
from tests.runtime_contract_fixtures import runtime_projection_stub, runtime_session_stub


def _session(tmp_path: Path):
    return runtime_session_stub(
        session_id="sess-memory",
        workspace_dir=tmp_path,
        projection=runtime_projection_stub(
            last_prepared_context={"sources": ["knowledge_base"]},
            memory_diagnostics={},
        ),
    )


def test_runtime_session_memory_command_handler_supports_legacy_command_and_constructor(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    save_calls: list[dict[str, object]] = []

    def _diagnostics_loader(target) -> dict[str, object]:  # noqa: ANN001
        return build_memory_diagnostics(
            workspace_dir=target.workspace_dir,
            session_id=target.session_id,
            last_prepared_context=target.projection.last_prepared_context,
        )

    def _save_note(**kwargs):  # noqa: ANN003
        save_calls.append(dict(kwargs))
        return {
            "target": "workspace_note",
            "category": "kb_confirmed",
            "content": kwargs["content"],
            "knowledge_base_grounding": {
                "used": True,
                "grounded": True,
                "query": "reply target routing",
                "knowledge_base_id": "default",
                "hits": 2,
                "refs": ["docs/routing.md", "docs/gateway.md"],
            },
        }

    handler = RuntimeSessionMemoryCommandHandler(
        build_memory_diagnostics_for_session=_diagnostics_loader,
        save_operator_workspace_note=_save_note,
    )

    execution = handler.execute(
        session,
        RuntimeSessionMemoryCommand(
            action="save_note",
            content="Remember active-surface reply routing",
            detail_mode="brief",
        ),
    )

    assert save_calls == [
        {
            "workspace_dir": Path(session.workspace_dir),
            "content": "Remember active-surface reply routing",
            "prepared_context_sources": ["knowledge_base"],
            "prepared_context": {"sources": ["knowledge_base"]},
        }
    ]
    assert execution.result["saved"]["target"] == "workspace_note"
    assert execution.result["saved"]["category"] == "kb_confirmed"
    assert execution.result["saved"]["content"] == "Remember active-surface reply routing"
    assert execution.result["summary"] == "operator note saved to workspace memory"
    assert "Action: save_note" in execution.result["details"]
    assert "Knowledge Base: grounded" in execution.result["details"]
    assert "- query: reply target routing" in execution.result["details"]
    assert session.projection.memory_diagnostics["session_id"] == "sess-memory"
    assert session.projection.memory_diagnostics["prepared_context_sources"] == ["knowledge_base"]


def test_runtime_session_memory_command_handler_supports_injected_command_service(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    command_calls: list[dict[str, object]] = []

    def _execute(**kwargs):  # noqa: ANN003
        command_calls.append(dict(kwargs))
        return SimpleNamespace(
            memory_diagnostics={"updated": True},
            summary="memory refreshed",
            details="Memory diagnostics updated",
            payload={"refresh": {"refreshed": True}},
        )

    handler = RuntimeSessionMemoryCommandHandler(
        build_memory_diagnostics_for_session=lambda _session: {"ignored": True},
        command_service=SimpleNamespace(execute=_execute),
    )
    request = MemoryCommandRequest(action="refresh")

    execution = handler.execute(session, request)

    assert command_calls and command_calls[0]["command"] is request
    assert command_calls[0]["workspace_dir"] == Path(session.workspace_dir)
    assert command_calls[0]["session_id"] == "sess-memory"
    assert execution.result["summary"] == "memory refreshed"
    assert execution.result["refresh"]["refreshed"] is True
    assert session.projection.memory_diagnostics == {"updated": True}


def test_runtime_session_memory_command_handler_wraps_memory_command_errors(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)

    def _execute(**kwargs):  # noqa: ANN003
        raise MemoryCommandError("memory unavailable", status_code=409)

    handler = RuntimeSessionMemoryCommandHandler(
        build_memory_diagnostics_for_session=lambda _session: {"ignored": True},
        command_service=SimpleNamespace(execute=_execute),
    )

    with pytest.raises(HTTPException) as exc_info:
        handler.execute(session, MemoryCommandRequest(action="refresh"))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "memory unavailable"
