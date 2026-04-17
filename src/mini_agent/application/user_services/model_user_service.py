"""User-facing model operations facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_agent.application.ports.model_runtime_port import ModelRuntimePort


@dataclass(slots=True)
class ModelUserService:
    """Thin user-service facade for model binding and capability views."""

    model_runtime: ModelRuntimePort

    async def list_model_bindings(self) -> Any:
        return await self.model_runtime.list_model_bindings()

    async def get_model_binding(self, agent_id: str | None = None) -> Any:
        return await self.model_runtime.get_model_binding(agent_id)

    async def update_model_binding(
        self,
        *,
        agent_id: str | None = None,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> Any:
        return await self.model_runtime.update_model_binding(
            agent_id=agent_id,
            provider_source=provider_source,
            provider_id=provider_id,
            model_id=model_id,
        )

    async def list_model_capabilities(self, agent_id: str | None = None) -> Any:
        return await self.model_runtime.list_model_capabilities(agent_id)


__all__ = ["ModelUserService"]
