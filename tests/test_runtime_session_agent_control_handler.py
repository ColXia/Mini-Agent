from __future__ import annotations

import pytest
from fastapi import HTTPException

from mini_agent.runtime.handlers.session_agent_control_handler import (
    RuntimeSessionAgentControlHandler,
    RuntimeSessionControlCommand,
)
from tests.runtime_contract_fixtures import (
    RuntimeContractAgentStub,
    runtime_projection_stub,
    runtime_session_stub,
)


class _ControllableAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def compact_context(self, *, reason: str | None = None) -> dict[str, object]:
        self.calls.append(("compact", reason))
        return {
            "applied": True,
            "message_count_before": 10,
            "message_count_after": 4,
            "token_count_before": 420,
            "token_count_after": 180,
            "stats": {
                "masked_messages": 1,
                "snipped_messages": 2,
                "merged_messages": 0,
            },
        }


def _session(*, agent=None, busy: bool = False, kb_enabled: bool = True):
    return runtime_session_stub(
        session_id="sess-1",
        agent=agent,
        projection=runtime_projection_stub(
            busy=busy,
            active_surface="tui",
            origin_surface="cli",
            knowledge_base_enabled=kb_enabled,
        ),
    )


@pytest.mark.asyncio
async def test_agent_control_handler_routes_compact_and_formats_transcript() -> None:
    agent = _ControllableAgent()
    session = _session(agent=agent)
    refreshed: list[str] = []
    handler = RuntimeSessionAgentControlHandler(
        normalize_surface=lambda value: value,
        apply_agent_knowledge_base_enabled=lambda current, enabled: enabled,
        refresh_runtime_projection=lambda target: refreshed.append(target.session_id)
        or ({}, {"approval_profile": "build"}),
    )

    execution = await handler.execute(
        session,
        RuntimeSessionControlCommand(action="compact", reason="trim old context"),
    )

    assert execution.response.action == "compact"
    assert execution.response.applied is True
    assert execution.response.active_surface == "tui"
    assert execution.transcript_summary == "context compacted"
    assert "Messages: 10 -> 4" in execution.transcript_details
    assert "Tokens: 420 -> 180" in execution.transcript_details
    assert "Reason: trim old context" in execution.transcript_details
    assert "masked=1" in execution.transcript_details
    assert agent.calls == [("compact", "trim old context")]
    assert refreshed == ["sess-1"]


@pytest.mark.asyncio
async def test_agent_control_handler_toggles_knowledge_base_state() -> None:
    agent = RuntimeContractAgentStub()
    agent.kb_enabled = True
    session = _session(agent=agent, kb_enabled=True)
    refreshed: list[str] = []
    handler = RuntimeSessionAgentControlHandler(
        normalize_surface=lambda value: value,
        apply_agent_knowledge_base_enabled=lambda current, enabled: setattr(current, "kb_enabled", enabled) or enabled,
        refresh_runtime_projection=lambda target: refreshed.append(target.session_id)
        or (
            setattr(target.projection, "knowledge_base_enabled", bool(target.runtime.agent.kb_enabled)) or {},
            {"approval_profile": "build"},
        ),
    )

    execution = await handler.execute(
        session,
        RuntimeSessionControlCommand(action="kb_off"),
    )

    assert execution.response.action == "kb_off"
    assert execution.response.applied is True
    assert execution.response.knowledge_base_enabled is False
    assert session.projection.knowledge_base_enabled is False
    assert execution.transcript_summary == "knowledge base disabled"
    assert execution.transcript_details == "Action: kb_off\nKnowledge Base: disabled"
    assert refreshed == ["sess-1"]


@pytest.mark.asyncio
async def test_agent_control_handler_reports_knowledge_base_already_disabled() -> None:
    session = _session(agent=object(), kb_enabled=False)
    handler = RuntimeSessionAgentControlHandler(
        normalize_surface=lambda value: value,
        apply_agent_knowledge_base_enabled=lambda current, enabled: enabled,
        refresh_runtime_projection=lambda _session: ({}, {}),
    )

    execution = await handler.execute(
        session,
        RuntimeSessionControlCommand(action="kb_off"),
    )

    assert execution.response.applied is False
    assert execution.response.knowledge_base_enabled is False
    assert execution.transcript_summary == "knowledge base already disabled"


@pytest.mark.asyncio
async def test_agent_control_handler_rejects_mutation_when_session_busy() -> None:
    handler = RuntimeSessionAgentControlHandler(
        normalize_surface=lambda value: value,
        apply_agent_knowledge_base_enabled=lambda current, enabled: enabled,
        refresh_runtime_projection=lambda _session: ({}, {}),
    )

    with pytest.raises(HTTPException) as excinfo:
        await handler.execute(
            _session(agent=object(), busy=True),
            RuntimeSessionControlCommand(action="drop_memories"),
        )

    assert excinfo.value.status_code == 409
    assert "Session is busy" in str(excinfo.value.detail)



