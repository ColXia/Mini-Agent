"""Shared remote stream failure normalization for interactive surfaces."""

from __future__ import annotations

from typing import Any, Mapping

from mini_agent.transport.gateway_error import extract_gateway_error_info


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


class RemoteStreamErrorService:
    """Own remote stream error normalization across TUI/Desktop surfaces."""

    @staticmethod
    def payload_detail(payload: Mapping[str, Any] | None = None, *, message: object | None = None) -> str:
        resolved_message = message
        if resolved_message is None and isinstance(payload, Mapping):
            resolved_message = payload.get("message")
        return _safe_text(resolved_message) or "Remote stream failed."

    @classmethod
    def exception_detail(cls, exc: Exception) -> str:
        return _safe_text(extract_gateway_error_info(exc).detail) or "Remote stream failed."


__all__ = ["RemoteStreamErrorService"]
