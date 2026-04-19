from __future__ import annotations

import asyncio
from types import SimpleNamespace

from mini_agent.runtime.support.session_local_agent_runtime_handler import LocalSessionAgentRebuildOutcome
from mini_agent.runtime.support.session_local_mcp_runtime_service import LocalSessionMcpRuntimeService


def test_local_session_mcp_runtime_service_reloads_with_selected_identity() -> None:
    warm_prefixes: list[str] = []
    session = SimpleNamespace(title="Session 1")

    async def _rebuild_current_identity(_session, *, warm_prefix: str, **kwargs):  # noqa: ANN001
        _ = kwargs
        warm_prefixes.append(warm_prefix)
        return LocalSessionAgentRebuildOutcome(
            warmed_agent=object(),
            selected_identity=("preset", "openai", "gpt-5.4"),
            active_model_label="openai/gpt-5.4",
        )

    service = LocalSessionMcpRuntimeService(
        agent_runtime=SimpleNamespace(rebuild_current_identity=_rebuild_current_identity),
    )

    outcome = asyncio.run(service.reload_bindings(session))

    assert warm_prefixes == ["MCP bindings reloaded for Session 1"]
    assert outcome.rebuilt_runtime is True
    assert outcome.active_model_label == "openai/gpt-5.4"


def test_local_session_mcp_runtime_service_falls_back_to_warmed_model_label_without_identity() -> None:
    session = SimpleNamespace(title="Local Session")

    async def _rebuild_current_identity(_session, *, warm_prefix: str, **kwargs):  # noqa: ANN001
        _ = (warm_prefix, kwargs)
        return LocalSessionAgentRebuildOutcome(
            warmed_agent=object(),
            selected_identity=None,
            active_model_label="gemma4:e4b",
        )

    service = LocalSessionMcpRuntimeService(
        agent_runtime=SimpleNamespace(rebuild_current_identity=_rebuild_current_identity),
    )

    outcome = asyncio.run(service.reload_bindings(session))

    assert outcome.rebuilt_runtime is True
    assert outcome.active_model_label == "gemma4:e4b"
