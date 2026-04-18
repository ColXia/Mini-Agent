"""User-facing model operations facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_agent.application.legacy.session_model_selection_runtime_port import SessionModelSelectionRuntimePort
from mini_agent.application.ports.model_runtime_port import ModelRuntimePort
from mini_agent.application.use_cases.model_binding_application_service import ModelBindingApplicationService


@dataclass(slots=True)
class ModelUserService:
    """Thin user-service facade for model binding and capability views.

    Session model-selection remains a compatibility shim while session/task
    entrypoints migrate behind `SessionTaskService`.
    """

    application_service: ModelBindingApplicationService | None = None
    model_runtime: ModelRuntimePort | None = None
    session_model_runtime: SessionModelSelectionRuntimePort | None = None

    def _application(self) -> ModelBindingApplicationService:
        if self.application_service is None:
            self.application_service = ModelBindingApplicationService(
                model_runtime=self.model_runtime,
                session_model_runtime=self.session_model_runtime,
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

    # Compatibility-only session-scoped entrypoint. Prefer SessionTaskService when available.
    async def update_session_model_selection(
        self,
        session_id: str,
        *,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any:
        return await self._application().update_session_model_selection(
            session_id,
            provider_source=provider_source,
            provider_id=provider_id,
            model_id=model_id,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )


__all__ = ["ModelUserService"]
