"""Application service for agent-owned main model binding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_agent.application.ports.model_runtime_port import ModelRuntimePort


def _require_model_runtime(runtime: ModelRuntimePort | None) -> ModelRuntimePort:
    if runtime is None:
        raise RuntimeError("Model runtime port is not configured.")
    return runtime

@dataclass(slots=True)
class ModelBindingApplicationService:
    """Owns application-layer agent model binding flows."""

    model_runtime: ModelRuntimePort | None = None

    async def list_model_bindings(self) -> Any:
        return await _require_model_runtime(self.model_runtime).list_model_bindings()

    async def list_model_candidates(self) -> Any:
        return await self.list_model_bindings()

    async def get_model_binding(self, agent_id: str | None = None) -> Any:
        return await _require_model_runtime(self.model_runtime).get_model_binding(agent_id)

    async def get_current_model_binding(self, agent_id: str | None = None) -> Any:
        return await self.get_model_binding(agent_id)

    async def update_model_binding(
        self,
        *,
        agent_id: str | None = None,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> Any:
        return await _require_model_runtime(self.model_runtime).update_model_binding(
            agent_id=agent_id,
            provider_source=provider_source,
            provider_id=provider_id,
            model_id=model_id,
        )

    async def set_agent_model_binding(
        self,
        *,
        agent_id: str | None = None,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> Any:
        return await self.update_model_binding(
            agent_id=agent_id,
            provider_source=provider_source,
            provider_id=provider_id,
            model_id=model_id,
        )

    async def list_model_capabilities(self, agent_id: str | None = None) -> Any:
        return await _require_model_runtime(self.model_runtime).list_model_capabilities(agent_id)

    async def get_current_model_capabilities(self, agent_id: str | None = None) -> Any:
        return await self.list_model_capabilities(agent_id)

    async def get_model_binding_diagnostics(self, agent_id: str | None = None) -> Any:
        return await _require_model_runtime(self.model_runtime).get_model_binding_diagnostics(agent_id)


__all__ = ["ModelBindingApplicationService"]
