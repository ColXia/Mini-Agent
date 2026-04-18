from __future__ import annotations

from pathlib import Path

from mini_agent.desktop.gateway_supervisor import DesktopGatewayConnection
from mini_agent.desktop.gateway_transport_binding import DesktopGatewayTransportBinding


def test_desktop_gateway_transport_binding_rebinds_shared_gateway_client() -> None:
    initial = DesktopGatewayConnection(
        host="127.0.0.1",
        port=8008,
        base_url="http://127.0.0.1:8008",
        workspace=Path("D:/file/Mini-Agent"),
        managed=False,
        started_here=False,
    )
    rebound = DesktopGatewayConnection(
        host="127.0.0.1",
        port=8010,
        base_url="http://127.0.0.1:8010/",
        workspace=Path("D:/file/Mini-Agent"),
        managed=False,
        started_here=False,
    )

    binding = DesktopGatewayTransportBinding.from_connection(
        connection=initial,
        timeout_seconds=15.0,
    )
    binding.bind_connection(rebound)

    assert binding.gateway_client.base_url == "http://127.0.0.1:8010"
    assert binding.chat_client._chat_transport is binding.gateway_client
    assert binding.session_client._session_transport is binding.gateway_client
    assert binding.workspace_client._workspace_transport is binding.gateway_client
