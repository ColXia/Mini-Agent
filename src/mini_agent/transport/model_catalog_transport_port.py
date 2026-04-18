"""Transport-facing contract for remote model catalog client operations."""

from __future__ import annotations

from typing import Any, Protocol


class RemoteModelCatalogTransportPort(Protocol):
    """Transport contract consumed by `RemoteModelCatalogClient`."""

    def list_agent_models_sync(self) -> dict[str, Any]: ...

    def list_agent_model_candidates_sync(self, *, agent_id: str | None = None) -> dict[str, Any]: ...

    def get_current_agent_model_binding_sync(self, *, agent_id: str | None = None) -> dict[str, Any]: ...

    def set_agent_model_binding_sync(
        self,
        *,
        agent_id: str | None = None,
        provider_source: str | None = None,
        provider_id: str,
        model_id: str,
    ) -> dict[str, Any]: ...

    def get_current_agent_model_capabilities_sync(self, *, agent_id: str | None = None) -> dict[str, Any]: ...

    def get_agent_model_binding_diagnostics_sync(self, *, agent_id: str | None = None) -> dict[str, Any]: ...

    def list_ops_models_sync(self, *, catalog_path: str | None = None) -> dict[str, Any]: ...

    def list_feature_model_bindings_sync(self, *, catalog_path: str | None = None) -> dict[str, Any]: ...

    def set_model_role_sync(
        self,
        *,
        source: str,
        provider_id: str,
        model_id: str,
        model_role: str,
        catalog_path: str | None = None,
    ) -> dict[str, Any]: ...

    def probe_model_capabilities_sync(
        self,
        *,
        source: str,
        provider_id: str,
        model_id: str,
        catalog_path: str | None = None,
    ) -> dict[str, Any]: ...

    def bind_feature_model_sync(
        self,
        *,
        feature_role: str,
        source: str,
        provider_id: str,
        model_id: str,
        catalog_path: str | None = None,
    ) -> dict[str, Any]: ...

    def clear_feature_model_binding_sync(
        self,
        *,
        feature_role: str,
        catalog_path: str | None = None,
    ) -> dict[str, Any]: ...


__all__ = ["RemoteModelCatalogTransportPort"]
