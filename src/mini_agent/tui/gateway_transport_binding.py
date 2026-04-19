"""TUI gateway transport binding and typed client assembly."""

from __future__ import annotations

from dataclasses import dataclass

from mini_agent.transport.gateway_client import GatewayClient
from mini_agent.transport.remote_chat_client import RemoteChatClient
from mini_agent.transport.remote_model_catalog_client import RemoteModelCatalogClient
from mini_agent.transport.remote_run_client import RemoteRunClient
from mini_agent.transport.remote_session_client import RemoteSessionClient
from mini_agent.transport.remote_workspace_client import RemoteWorkspaceClient


@dataclass(slots=True)
class TuiGatewayTransportBinding:
    """Shared gateway transport bundle for TUI remote surface operations."""

    gateway_client: GatewayClient
    chat_client: RemoteChatClient
    model_client: RemoteModelCatalogClient
    run_client: RemoteRunClient
    session_client: RemoteSessionClient
    workspace_client: RemoteWorkspaceClient

    @classmethod
    def from_gateway_client(
        cls,
        gateway_client: GatewayClient,
    ) -> TuiGatewayTransportBinding:
        return cls(
            gateway_client=gateway_client,
            chat_client=RemoteChatClient(chat_transport=gateway_client),
            model_client=RemoteModelCatalogClient(model_transport=gateway_client),
            run_client=RemoteRunClient(run_transport=gateway_client),
            session_client=RemoteSessionClient(session_transport=gateway_client),
            workspace_client=RemoteWorkspaceClient(workspace_transport=gateway_client),
        )


__all__ = ["TuiGatewayTransportBinding"]
