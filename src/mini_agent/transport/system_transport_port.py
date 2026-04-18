"""Transport-facing contract for remote system health client operations."""

from __future__ import annotations

from typing import Protocol


class RemoteSystemTransportPort(Protocol):
    """Transport contract consumed by `RemoteSystemClient`."""

    def get_system_health_sync(self) -> dict: ...


__all__ = ["RemoteSystemTransportPort"]
