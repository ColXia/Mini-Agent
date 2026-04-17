"""Application service for agent model binding and session-selection compatibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_agent.application.ports.model_runtime_port import ModelRuntimePort
from mini_agent.application.ports.session_model_selection_runtime_port import SessionModelSelectionRuntimePort


def _require_model_runtime(runtime: ModelRuntimePort | None) -> ModelRuntimePort:
    if runtime is None:
        raise RuntimeError("Model runtime port is not configured.")
    return runtime


def _require_session_model_runtime(
    runtime: SessionModelSelectionRuntimePort | None,
) -> SessionModelSelectionRuntimePort:
    if runtime is None:
        raise RuntimeError("Session model compatibility runtime is not configured.")
    return runtime


@dataclass(slots=True)
class ModelBindingApplicationService:
    """Owns application-layer model binding and compatibility selection flows."""

    model_runtime: ModelRuntimePort | None = None
    session_model_runtime: SessionModelSelectionRuntimePort | None = None

    async def list_model_bindings(self) -> Any:
        return await _require_model_runtime(self.model_runtime).list_model_bindings()

    async def get_model_binding(self, agent_id: str | None = None) -> Any:
        return await _require_model_runtime(self.model_runtime).get_model_binding(agent_id)

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

    async def list_model_capabilities(self, agent_id: str | None = None) -> Any:
        return await _require_model_runtime(self.model_runtime).list_model_capabilities(agent_id)

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
        return await _require_session_model_runtime(self.session_model_runtime).update_session_model_selection(
            session_id,
            provider_source=provider_source,
            provider_id=provider_id,
            model_id=model_id,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )


__all__ = ["ModelBindingApplicationService"]
