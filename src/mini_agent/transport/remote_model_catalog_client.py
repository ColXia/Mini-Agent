"""Typed client-side remote model catalog client over the shared gateway transport."""

from __future__ import annotations

from mini_agent.interfaces import (
    MainAgentModelBindingDiagnostics,
    MainAgentModelBindingRequest,
    MainAgentModelBindingSummary,
    MainAgentModelCandidateListResponse,
    MainAgentModelCapabilities,
    StudioFeatureModelBindingClearResponse,
    StudioFeatureModelBindingRequest,
    StudioFeatureModelBindingSummary,
    StudioFeatureModelBindingsResponse,
    StudioModelCapabilityProbeRequest,
    StudioModelCapabilityProbeResponse,
    StudioModelListResponse,
    StudioModelRoleRequest,
    StudioModelProviderSummary,
)

from .model_catalog_transport_port import RemoteModelCatalogTransportPort


class RemoteModelCatalogClient:
    """Typed client-side facade over remote model catalog and registry transport."""

    def __init__(self, *, model_transport: RemoteModelCatalogTransportPort) -> None:
        self._model_transport = model_transport

    def list_agent_models_sync(self) -> StudioModelListResponse:
        payload = self._model_transport.list_agent_models_sync()
        return StudioModelListResponse.model_validate(payload)

    def list_agent_model_candidates_sync(
        self,
        *,
        agent_id: str | None = None,
    ) -> MainAgentModelCandidateListResponse:
        payload = self._model_transport.list_agent_model_candidates_sync(agent_id=agent_id)
        return MainAgentModelCandidateListResponse.model_validate(payload)

    def get_current_agent_model_binding_sync(
        self,
        *,
        agent_id: str | None = None,
    ) -> MainAgentModelBindingSummary:
        payload = self._model_transport.get_current_agent_model_binding_sync(agent_id=agent_id)
        return MainAgentModelBindingSummary.model_validate(payload)

    def set_agent_model_binding_sync(
        self,
        request: MainAgentModelBindingRequest,
    ) -> MainAgentModelBindingSummary:
        payload = self._model_transport.set_agent_model_binding_sync(
            agent_id=request.agent_id,
            provider_source=request.provider_source,
            provider_id=request.provider_id,
            model_id=request.model_id,
        )
        return MainAgentModelBindingSummary.model_validate(payload)

    def get_current_agent_model_capabilities_sync(
        self,
        *,
        agent_id: str | None = None,
    ) -> MainAgentModelCapabilities:
        payload = self._model_transport.get_current_agent_model_capabilities_sync(agent_id=agent_id)
        return MainAgentModelCapabilities.model_validate(payload)

    def get_agent_model_binding_diagnostics_sync(
        self,
        *,
        agent_id: str | None = None,
    ) -> MainAgentModelBindingDiagnostics:
        payload = self._model_transport.get_agent_model_binding_diagnostics_sync(agent_id=agent_id)
        return MainAgentModelBindingDiagnostics.model_validate(payload)

    def list_registry_models_sync(
        self,
        *,
        catalog_path: str | None = None,
    ) -> StudioModelListResponse:
        payload = self._model_transport.list_ops_models_sync(catalog_path=catalog_path)
        return StudioModelListResponse.model_validate(payload)

    def list_feature_model_bindings_sync(
        self,
        *,
        catalog_path: str | None = None,
    ) -> StudioFeatureModelBindingsResponse:
        payload = self._model_transport.list_feature_model_bindings_sync(catalog_path=catalog_path)
        return StudioFeatureModelBindingsResponse.model_validate(payload)

    def set_model_role_sync(
        self,
        request: StudioModelRoleRequest,
        *,
        catalog_path: str | None = None,
    ) -> StudioModelProviderSummary:
        payload = self._model_transport.set_model_role_sync(
            source=request.source,
            provider_id=request.provider_id,
            model_id=request.model_id,
            model_role=request.model_role,
            catalog_path=catalog_path,
        )
        return StudioModelProviderSummary.model_validate(payload)

    def probe_model_capabilities_sync(
        self,
        request: StudioModelCapabilityProbeRequest,
        *,
        catalog_path: str | None = None,
    ) -> StudioModelCapabilityProbeResponse:
        payload = self._model_transport.probe_model_capabilities_sync(
            source=request.source,
            provider_id=request.provider_id,
            model_id=request.model_id,
            catalog_path=catalog_path,
        )
        return StudioModelCapabilityProbeResponse.model_validate(payload)

    def bind_feature_model_sync(
        self,
        request: StudioFeatureModelBindingRequest,
        *,
        catalog_path: str | None = None,
    ) -> StudioFeatureModelBindingSummary:
        payload = self._model_transport.bind_feature_model_sync(
            feature_role=request.feature_role,
            source=request.source,
            provider_id=request.provider_id,
            model_id=request.model_id,
            catalog_path=catalog_path,
        )
        return StudioFeatureModelBindingSummary.model_validate(payload)

    def clear_feature_model_binding_sync(
        self,
        *,
        feature_role: str,
        catalog_path: str | None = None,
    ) -> StudioFeatureModelBindingClearResponse:
        payload = self._model_transport.clear_feature_model_binding_sync(
            feature_role=feature_role,
            catalog_path=catalog_path,
        )
        return StudioFeatureModelBindingClearResponse.model_validate(payload)


__all__ = ["RemoteModelCatalogClient"]
