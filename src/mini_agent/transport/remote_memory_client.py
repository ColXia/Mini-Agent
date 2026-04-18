"""Typed client-side remote memory client over the shared gateway transport."""

from __future__ import annotations

from mini_agent.interfaces import (
    StudioMemoryDailyResponse,
    StudioMemorySearchResponse,
    StudioMemorySummaryResponse,
)

from .memory_transport_port import RemoteMemoryTransportPort


class RemoteMemoryClient:
    """Typed client-side facade over remote memory transport."""

    def __init__(self, *, memory_transport: RemoteMemoryTransportPort) -> None:
        self._memory_transport = memory_transport

    def get_ops_memory_summary_sync(
        self,
        *,
        workspace_dir: str | None = None,
    ) -> StudioMemorySummaryResponse:
        payload = self._memory_transport.get_ops_memory_summary_sync(workspace_dir=workspace_dir)
        return StudioMemorySummaryResponse.model_validate(payload)

    def search_ops_memory_sync(
        self,
        *,
        query: str = "",
        limit: int = 20,
        workspace_dir: str | None = None,
    ) -> StudioMemorySearchResponse:
        payload = self._memory_transport.search_ops_memory_sync(
            query=query,
            limit=limit,
            workspace_dir=workspace_dir,
        )
        return StudioMemorySearchResponse.model_validate(payload)

    def get_ops_memory_daily_sync(
        self,
        *,
        day: str,
        workspace_dir: str | None = None,
    ) -> StudioMemoryDailyResponse:
        payload = self._memory_transport.get_ops_memory_daily_sync(
            day=day,
            workspace_dir=workspace_dir,
        )
        return StudioMemoryDailyResponse.model_validate(payload)


__all__ = ["RemoteMemoryClient"]
