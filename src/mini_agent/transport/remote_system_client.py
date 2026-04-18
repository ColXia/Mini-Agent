"""Typed client-side remote system client over the shared gateway transport."""

from __future__ import annotations

from mini_agent.interfaces import SystemHealthResponse

from .system_transport_port import RemoteSystemTransportPort


class RemoteSystemClient:
    """Typed client-side facade over remote system health transport."""

    def __init__(self, *, system_transport: RemoteSystemTransportPort) -> None:
        self._system_transport = system_transport

    def get_system_health_sync(self) -> SystemHealthResponse:
        payload = self._system_transport.get_system_health_sync()
        return SystemHealthResponse.model_validate(payload)


__all__ = ["RemoteSystemClient"]
