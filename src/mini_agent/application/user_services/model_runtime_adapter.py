"""Stable model-runtime adapter over the agent-owned model binding service."""

from __future__ import annotations

from typing import Any

from mini_agent.application.ports.model_runtime_port import ModelRuntimePort
from mini_agent.model_manager.agent_model_service import AgentModelService


class AgentModelRuntimeAdapter(ModelRuntimePort):
    """Typed model-runtime adapter over the agent-owned model binding service."""

    def __init__(self, model_service: AgentModelService) -> None:
        self._model_service = model_service

    async def list_model_bindings(self) -> Any:
        return self._model_service.list_model_bindings()

    async def get_model_binding(self, agent_id: str | None = None) -> Any:
        return self._model_service.get_model_binding(agent_id)

    async def update_model_binding(
        self,
        *,
        agent_id: str | None = None,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> Any:
        return self._model_service.update_model_binding(
            agent_id=agent_id,
            provider_source=provider_source,
            provider_id=provider_id,
            model_id=model_id,
        )

    async def list_model_capabilities(self, agent_id: str | None = None) -> Any:
        return self._model_service.list_model_capabilities(agent_id)

    async def get_model_binding_diagnostics(self, agent_id: str | None = None) -> Any:
        return self._model_service.get_model_binding_diagnostics(agent_id)
