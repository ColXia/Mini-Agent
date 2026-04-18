"""Transport-facing contract for remote provider client operations."""

from __future__ import annotations

from typing import Any, Protocol


class RemoteProviderTransportPort(Protocol):
    """Transport contract consumed by `RemoteProviderClient`."""

    def list_ops_providers_sync(self, *, catalog_path: str | None = None) -> dict[str, Any]: ...

    def validate_provider_connection_sync(
        self,
        *,
        api_type: str,
        api_base: str,
        api_key: str | None = None,
    ) -> dict[str, Any]: ...

    def discover_provider_models_sync(
        self,
        *,
        api_type: str,
        api_base: str,
        api_key: str,
    ) -> dict[str, Any]: ...

    def create_provider_sync(
        self,
        *,
        payload: dict[str, Any],
        catalog_path: str | None = None,
    ) -> dict[str, Any]: ...

    def update_provider_sync(
        self,
        *,
        provider_id: str,
        payload: dict[str, Any],
        catalog_path: str | None = None,
    ) -> dict[str, Any]: ...

    def delete_provider_sync(
        self,
        *,
        provider_id: str,
        catalog_path: str | None = None,
    ) -> dict[str, Any]: ...

    def get_provider_health_sync(
        self,
        *,
        provider_id: str,
        catalog_path: str | None = None,
    ) -> dict[str, Any]: ...


__all__ = ["RemoteProviderTransportPort"]
