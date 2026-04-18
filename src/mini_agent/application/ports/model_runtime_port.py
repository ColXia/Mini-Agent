"""Runtime-facing model seams for application services."""

from __future__ import annotations

from typing import Any, Protocol


class ModelRuntimePort(Protocol):
    """Application-facing contract for agent model selection and capability views."""

    async def list_model_bindings(self) -> Any: ...

    async def get_model_binding(self, agent_id: str | None = None) -> Any: ...

    async def update_model_binding(
        self,
        *,
        agent_id: str | None = None,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> Any: ...

    async def list_model_capabilities(self, agent_id: str | None = None) -> Any: ...

    async def get_model_binding_diagnostics(self, agent_id: str | None = None) -> Any: ...


__all__ = ["ModelRuntimePort"]
