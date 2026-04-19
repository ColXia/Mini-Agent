"""DesktopUI gateway transport binding and typed client assembly."""

from __future__ import annotations

from dataclasses import dataclass

from mini_agent.desktop.gateway_supervisor import DesktopGatewayConnection
from mini_agent.transport.gateway_client import GatewayClient
from mini_agent.transport.remote_chat_client import RemoteChatClient
from mini_agent.transport.remote_memory_client import RemoteMemoryClient
from mini_agent.transport.remote_model_catalog_client import RemoteModelCatalogClient
from mini_agent.transport.remote_provider_client import RemoteProviderClient
from mini_agent.transport.remote_run_client import RemoteRunClient
from mini_agent.transport.remote_session_client import RemoteSessionClient
from mini_agent.transport.remote_system_client import RemoteSystemClient
from mini_agent.transport.remote_workspace_client import RemoteWorkspaceClient


@dataclass(slots=True)
class DesktopGatewayTransportBinding:
    """Shared gateway transport bundle for DesktopUI surfaces."""

    gateway_client: GatewayClient
    chat_client: RemoteChatClient
    run_client: RemoteRunClient
    session_client: RemoteSessionClient
    system_client: RemoteSystemClient
    memory_client: RemoteMemoryClient
    model_client: RemoteModelCatalogClient
    provider_client: RemoteProviderClient
    workspace_client: RemoteWorkspaceClient

    @classmethod
    def from_gateway_client(
        cls,
        gateway_client: GatewayClient,
    ) -> DesktopGatewayTransportBinding:
        return cls(
            gateway_client=gateway_client,
            chat_client=RemoteChatClient(chat_transport=gateway_client),
            run_client=RemoteRunClient(run_transport=gateway_client),
            session_client=RemoteSessionClient(session_transport=gateway_client),
            system_client=RemoteSystemClient(system_transport=gateway_client),
            memory_client=RemoteMemoryClient(memory_transport=gateway_client),
            model_client=RemoteModelCatalogClient(model_transport=gateway_client),
            provider_client=RemoteProviderClient(provider_transport=gateway_client),
            workspace_client=RemoteWorkspaceClient(workspace_transport=gateway_client),
        )

    @classmethod
    def from_connection(
        cls,
        *,
        connection: DesktopGatewayConnection,
        timeout_seconds: float,
    ) -> DesktopGatewayTransportBinding:
        return cls.from_gateway_client(
            GatewayClient(
                base_url=connection.base_url,
                timeout_seconds=timeout_seconds,
            )
        )

    def bind_connection(self, connection: DesktopGatewayConnection) -> None:
        self.gateway_client.base_url = str(connection.base_url or "").rstrip("/")


__all__ = ["DesktopGatewayTransportBinding"]
