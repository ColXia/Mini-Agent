from __future__ import annotations

from mini_agent.agent_core import (
    AgentHistoryCompactionService,
    AgentPostTurnSideEffectService,
    AgentPreparedTurnContextService,
    AgentRuntimeBindings,
    AgentRuntimeServices,
    HistoryCompactionResult,
    PreparedTurnContextResult,
    PostTurnSideEffectResult,
)


def test_agent_core_exports_runtime_seam_types() -> None:
    assert AgentHistoryCompactionService is not None
    assert HistoryCompactionResult is not None
    assert AgentPreparedTurnContextService is not None
    assert PreparedTurnContextResult is not None
    assert AgentPostTurnSideEffectService is not None
    assert PostTurnSideEffectResult is not None
    assert AgentRuntimeBindings is not None
    assert AgentRuntimeServices is not None
