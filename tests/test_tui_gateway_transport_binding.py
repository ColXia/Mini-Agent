from __future__ import annotations

from mini_agent.transport import GatewayClient
from mini_agent.tui.gateway_transport_binding import TuiGatewayTransportBinding


def test_tui_gateway_transport_binding_shares_gateway_transport() -> None:
    gateway_client = GatewayClient(base_url="http://127.0.0.1:8008", timeout_seconds=15.0)

    binding = TuiGatewayTransportBinding.from_gateway_client(gateway_client)

    assert binding.gateway_client is gateway_client
    assert binding.chat_client._chat_transport is gateway_client
    assert binding.model_client._model_transport is gateway_client
    assert binding.session_client._session_transport is gateway_client
    assert binding.workspace_client._workspace_transport is gateway_client
