"""Transport-facing contract for remote memory client operations."""

from __future__ import annotations

from typing import Any, Protocol


class RemoteMemoryTransportPort(Protocol):
    """Transport contract consumed by `RemoteMemoryClient`."""

    def get_ops_memory_summary_sync(self, *, workspace_dir: str | None = None) -> dict[str, Any]: ...

    def search_ops_memory_sync(
        self,
        *,
        query: str = "",
        limit: int = 20,
        workspace_dir: str | None = None,
    ) -> dict[str, Any]: ...

    def get_ops_memory_daily_sync(
        self,
        *,
        day: str,
        workspace_dir: str | None = None,
    ) -> dict[str, Any]: ...


__all__ = ["RemoteMemoryTransportPort"]
