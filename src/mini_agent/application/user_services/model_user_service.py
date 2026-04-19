"""User-facing agent model operations facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_agent.application.ports.model_runtime_port import ModelRuntimePort
from mini_agent.application.use_cases.model_binding_application_service import ModelBindingApplicationService


@dataclass(slots=True)
class ModelUserService:
    """Thin user-service facade for agent model binding and capability views."""

    application_service: ModelBindingApplicationService | None = None
    model_runtime: ModelRuntimePort | None = None

    def _application(self) -> ModelBindingApplicationService:
        if self.application_service is None:
            self.application_service = ModelBindingApplicationService(
                model_runtime=self.model_runtime,
            )
        return self.application_service

    async def list_model_bindings(self) -> Any:
        return await self._application().list_model_bindings()

    async def list_model_candidates(self) -> Any:
        return await self._application().list_model_candidates()

    async def get_model_binding(self, agent_id: str | None = None) -> Any:
        return await self._application().get_model_binding(agent_id)

    async def get_current_model_binding(self, agent_id: str | None = None) -> Any:
        return await self._application().get_current_model_binding(agent_id)

    async def update_model_binding(
        self,
        *,
        agent_id: str | None = None,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> Any:
        return await self._application().update_model_binding(
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
        return await self._application().set_agent_model_binding(
            agent_id=agent_id,
            provider_source=provider_source,
            provider_id=provider_id,
            model_id=model_id,
        )

    async def list_model_capabilities(self, agent_id: str | None = None) -> Any:
        return await self._application().list_model_capabilities(agent_id)

    async def get_current_model_capabilities(self, agent_id: str | None = None) -> Any:
        return await self._application().get_current_model_capabilities(agent_id)

    async def get_model_binding_diagnostics(self, agent_id: str | None = None) -> Any:
        return await self._application().get_model_binding_diagnostics(agent_id)


__all__ = ["ModelUserService"]
