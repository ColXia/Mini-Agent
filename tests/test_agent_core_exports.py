from __future__ import annotations

from mini_agent.agent_core.context.turn_context import (
    AgentPreparedTurnContextService,
    PreparedTurnContextResult,
)
from mini_agent.agent_core.history.summarization import AgentHistoryCompactionService, HistoryCompactionResult
from mini_agent.agent_core.post_turn import AgentPostTurnSideEffectService, PostTurnSideEffectResult
from mini_agent.agent_core.runtime_bindings import AgentRuntimeBindings, AgentRuntimeServices


def test_agent_core_exports_runtime_seam_types() -> None:
    assert AgentHistoryCompactionService is not None
    assert HistoryCompactionResult is not None
    assert AgentPreparedTurnContextService is not None
    assert PreparedTurnContextResult is not None
    assert AgentPostTurnSideEffectService is not None
    assert PostTurnSideEffectResult is not None
    assert AgentRuntimeBindings is not None
    assert AgentRuntimeServices is not None
