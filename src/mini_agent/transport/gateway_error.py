"""Shared gateway transport error helpers for remote surfaces."""

from __future__ import annotations

from dataclasses import dataclass
import re

from mini_agent.utils.text import safe_text


def _safe_text(value: object) -> str:
    return safe_text(value)


_GATEWAY_HTTP_ERROR_RE = re.compile(r"^Gateway HTTP (?P<status>\d+):\s*(?P<detail>.+)$")


@dataclass(frozen=True, slots=True)
class GatewayErrorInfo:
    """Normalized gateway failure details for UI/application consumers."""

    status_code: int | None
    detail: str
    message: str


class GatewayTransportError(RuntimeError):
    """Transport-level error raised by the shared gateway client."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = int(status_code) if status_code is not None else None
        super().__init__(_safe_text(message) or "Gateway request failed.")


def extract_gateway_error_info(exc: Exception) -> GatewayErrorInfo:
    """Normalize typed or legacy gateway exceptions into one stable shape."""

    message = _safe_text(exc) or "Remote request failed."
    status_code = getattr(exc, "status_code", None)
    normalized_status = int(status_code) if isinstance(status_code, int) else None

    match = _GATEWAY_HTTP_ERROR_RE.match(message)
    if match:
        normalized_status = int(match.group("status"))
        detail = _safe_text(match.group("detail")) or message
        return GatewayErrorInfo(
            status_code=normalized_status,
            detail=detail,
            message=message,
        )

    return GatewayErrorInfo(
        status_code=normalized_status,
        detail=message,
        message=message,
    )


__all__ = [
    "GatewayErrorInfo",
    "GatewayTransportError",
    "extract_gateway_error_info",
]
