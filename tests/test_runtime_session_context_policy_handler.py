from __future__ import annotations

from types import SimpleNamespace

from mini_agent.agent_core.context.command_service import ContextCommandRequest, ContextCommandService
from mini_agent.runtime.handlers.session_context_policy_handler import RuntimeSessionContextPolicyHandler
from tests.runtime_contract_fixtures import (
    runtime_projection_stub,
    runtime_session_stub,
)


def _build_context_policy_handler(**overrides):
    defaults = dict(
        normalize_surface=lambda value: str(value or "tui"),
        normalize_context_policy_payload=lambda value: dict(value or {}),
        session_commands=SimpleNamespace(
            execute_locked=lambda session, **kwargs: kwargs["operation"](),  # noqa: ARG005
        ),
        session_context_commands=ContextCommandService(),
    )
    defaults.update(overrides)
    return RuntimeSessionContextPolicyHandler(**defaults)


def test_runtime_session_context_policy_handler_normalizes_context_policy_writeback() -> None:
    handler = _build_context_policy_handler(
        normalize_context_policy_payload=lambda value: {
            **dict(value or {}),
            "normalized": True,
        }
    )
    session = runtime_session_stub(
        session_id="sess-context",
        projection=runtime_projection_stub(
            busy=False,
            active_surface="tui",
            origin_surface="cli",
            context_policy={},
        ),
    )

    execution = handler._execute_context_policy_update(
        session,
        ContextCommandRequest(action="include", sources=("knowledge_base",)),
    )

    assert session.projection.context_policy["normalized"] is True
    assert execution.response.context_policy["normalized"] is True
    assert execution.transcript_command == "context include"
    assert execution.response.action == "include"
