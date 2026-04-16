from __future__ import annotations

from mini_agent.transport import GatewayTransportError, extract_gateway_error_info


def test_extract_gateway_error_info_parses_legacy_http_runtime_error() -> None:
    info = extract_gateway_error_info(RuntimeError("Gateway HTTP 409: Session has no pending approval."))

    assert info.status_code == 409
    assert info.detail == "Session has no pending approval."
    assert info.message == "Gateway HTTP 409: Session has no pending approval."


def test_extract_gateway_error_info_preserves_non_http_gateway_message() -> None:
    info = extract_gateway_error_info(RuntimeError("Gateway unavailable: [WinError 10061] refused"))

    assert info.status_code is None
    assert info.detail == "Gateway unavailable: [WinError 10061] refused"


def test_extract_gateway_error_info_reads_typed_gateway_status_code() -> None:
    info = extract_gateway_error_info(
        GatewayTransportError(
            "Gateway HTTP 404: Pending approval not found: tok-1",
            status_code=404,
        )
    )

    assert info.status_code == 404
    assert info.detail == "Pending approval not found: tok-1"
