"""Typed client-side remote provider client over the shared gateway transport."""

from __future__ import annotations

from mini_agent.interfaces import (
    StudioProviderDeleteResponse,
    StudioProviderHealthResponse,
    StudioProviderListResponse,
    StudioProviderModelDiscoveryRequest,
    StudioProviderModelDiscoveryResponse,
    StudioProviderSummary,
    StudioProviderUpsertRequest,
    StudioProviderValidationRequest,
    StudioProviderValidationResponse,
)

from .provider_transport_port import RemoteProviderTransportPort


class RemoteProviderClient:
    """Typed client-side facade over remote provider catalog transport."""

    def __init__(self, *, provider_transport: RemoteProviderTransportPort) -> None:
        self._provider_transport = provider_transport

    def list_providers_sync(
        self,
        *,
        catalog_path: str | None = None,
    ) -> StudioProviderListResponse:
        payload = self._provider_transport.list_ops_providers_sync(catalog_path=catalog_path)
        return StudioProviderListResponse.model_validate(payload)

    def validate_provider_connection_sync(
        self,
        request: StudioProviderValidationRequest,
    ) -> StudioProviderValidationResponse:
        payload = self._provider_transport.validate_provider_connection_sync(
            api_type=request.api_type,
            api_base=request.api_base,
            api_key=request.api_key,
        )
        return StudioProviderValidationResponse.model_validate(payload)

    def discover_provider_models_sync(
        self,
        request: StudioProviderModelDiscoveryRequest,
    ) -> StudioProviderModelDiscoveryResponse:
        payload = self._provider_transport.discover_provider_models_sync(
            api_type=request.api_type,
            api_base=request.api_base,
            api_key=request.api_key or "",
        )
        return StudioProviderModelDiscoveryResponse.model_validate(payload)

    def create_provider_sync(
        self,
        request: StudioProviderUpsertRequest,
        *,
        catalog_path: str | None = None,
    ) -> StudioProviderSummary:
        payload = self._provider_transport.create_provider_sync(
            payload=request.model_dump(mode="json"),
            catalog_path=catalog_path,
        )
        return StudioProviderSummary.model_validate(payload)

    def update_provider_sync(
        self,
        provider_id: str,
        request: StudioProviderUpsertRequest,
        *,
        catalog_path: str | None = None,
    ) -> StudioProviderSummary:
        payload = self._provider_transport.update_provider_sync(
            provider_id=provider_id,
            payload=request.model_dump(mode="json"),
            catalog_path=catalog_path,
        )
        return StudioProviderSummary.model_validate(payload)

    def delete_provider_sync(
        self,
        provider_id: str,
        *,
        catalog_path: str | None = None,
    ) -> StudioProviderDeleteResponse:
        payload = self._provider_transport.delete_provider_sync(
            provider_id=provider_id,
            catalog_path=catalog_path,
        )
        return StudioProviderDeleteResponse.model_validate(payload)

    def get_provider_health_sync(
        self,
        provider_id: str,
        *,
        catalog_path: str | None = None,
    ) -> StudioProviderHealthResponse:
        payload = self._provider_transport.get_provider_health_sync(
            provider_id=provider_id,
            catalog_path=catalog_path,
        )
        return StudioProviderHealthResponse.model_validate(payload)


__all__ = ["RemoteProviderClient"]
