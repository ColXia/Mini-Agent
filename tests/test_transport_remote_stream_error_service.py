from __future__ import annotations

from mini_agent.transport import GatewayTransportError, RemoteStreamErrorService


def test_remote_stream_error_service_reads_payload_message() -> None:
    detail = RemoteStreamErrorService.payload_detail({"message": "upstream tool failed"})

    assert detail == "upstream tool failed"


def test_remote_stream_error_service_normalizes_gateway_exception_detail() -> None:
    detail = RemoteStreamErrorService.exception_detail(
        GatewayTransportError("Gateway HTTP 502: upstream gateway failed", status_code=502)
    )

    assert detail == "upstream gateway failed"
