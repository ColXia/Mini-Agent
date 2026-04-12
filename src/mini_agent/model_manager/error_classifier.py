"""Error classification for provider failover decisions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re


_STATUS_CODE_PATTERN = re.compile(r"\b(?:status(?:\s*code)?|http)\s*[:=]?\s*(\d{3})\b", re.IGNORECASE)
_GENERIC_CODE_PATTERN = re.compile(r"\b([45]\d{2})\b")


@dataclass(frozen=True)
class ProviderErrorClassification:
    """Normalized provider error category for retry/failover decisions."""

    category: str
    reason: str
    retryable: bool
    failover_allowed: bool
    status_code: int | None = None
    context_window_limit: int | None = None
    requested_tokens: int | None = None


_OVERFLOW_MAX_PATTERNS = (
    re.compile(r"maximum context length is\s*([\d,]+)\s*tokens?", re.IGNORECASE),
    re.compile(r"context window(?:\s+of|\s+is)?\s*([\d,]+)\s*tokens?", re.IGNORECASE),
    re.compile(r"context limit(?:\s+of|\s+is)?\s*([\d,]+)\s*tokens?", re.IGNORECASE),
    re.compile(r"max(?:imum)?\s+context(?:\s+length)?(?:\s+of|\s+is)?\s*([\d,]+)", re.IGNORECASE),
)
_OVERFLOW_REQUESTED_PATTERNS = (
    re.compile(r"resulted in\s*([\d,]+)\s*tokens?", re.IGNORECASE),
    re.compile(r"prompt is\s*([\d,]+)\s*tokens?", re.IGNORECASE),
    re.compile(r"requested\s*([\d,]+)\s*tokens?", re.IGNORECASE),
    re.compile(r"input tokens?(?:\s*\(|\s*[:=]\s*|\s+)([\d,]+)", re.IGNORECASE),
)


def _normalize_token_number(raw: str | None) -> int | None:
    candidate = str(raw or "").replace(",", "").strip()
    if not candidate:
        return None
    try:
        value = int(candidate)
    except Exception:
        return None
    return value if value > 0 else None


def _extract_pattern_number(message: str, patterns: tuple[re.Pattern[str], ...]) -> int | None:
    for pattern in patterns:
        matched = pattern.search(message)
        if matched is None:
            continue
        value = _normalize_token_number(matched.group(1))
        if value is not None:
            return value
    return None


def _is_context_window_overflow(message: str) -> bool:
    lowered = message.lower()
    overflow_markers = (
        "maximum context length",
        "context window",
        "context length exceeded",
        "prompt is too long",
        "input is too long",
        "too many tokens",
        "input tokens exceed",
        "input length and max_tokens exceed context limit",
    )
    return any(marker in lowered for marker in overflow_markers)


def _extract_status_code(exc: Exception, message: str) -> int | None:
    for attr in ("status_code", "status", "http_status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value

    for pattern in (_STATUS_CODE_PATTERN, _GENERIC_CODE_PATTERN):
        matched = pattern.search(message)
        if matched is not None:
            try:
                value = int(matched.group(1))
            except Exception:
                value = None
            if value is not None and 100 <= value <= 599:
                return value
    return None


def classify_provider_error(exc: Exception) -> ProviderErrorClassification:
    """Classify a provider exception into retry/failover behavior."""
    if isinstance(exc, asyncio.CancelledError):
        return ProviderErrorClassification(
            category="cancelled",
            reason="cancelled_by_user",
            retryable=False,
            failover_allowed=False,
        )

    message = str(exc).strip()
    lowered = message.lower()
    if "cancelled" in lowered or "canceled" in lowered:
        return ProviderErrorClassification(
            category="cancelled",
            reason="cancelled_by_user",
            retryable=False,
            failover_allowed=False,
        )

    status_code = _extract_status_code(exc, message)
    if _is_context_window_overflow(message):
        return ProviderErrorClassification(
            category="non_retryable",
            reason="context_window_exceeded",
            retryable=False,
            failover_allowed=False,
            status_code=status_code,
            context_window_limit=_extract_pattern_number(message, _OVERFLOW_MAX_PATTERNS),
            requested_tokens=_extract_pattern_number(message, _OVERFLOW_REQUESTED_PATTERNS),
        )
    if status_code == 429:
        return ProviderErrorClassification(
            category="retryable",
            reason="rate_limited",
            retryable=True,
            failover_allowed=True,
            status_code=status_code,
        )
    if status_code is not None and status_code >= 500:
        return ProviderErrorClassification(
            category="retryable",
            reason="upstream_5xx",
            retryable=True,
            failover_allowed=True,
            status_code=status_code,
        )
    if status_code in {401, 403}:
        return ProviderErrorClassification(
            category="non_retryable",
            reason="auth_failed",
            retryable=False,
            failover_allowed=True,
            status_code=status_code,
        )
    if status_code == 404 and ("model" in lowered or "not found" in lowered):
        return ProviderErrorClassification(
            category="non_retryable",
            reason="model_not_found",
            retryable=False,
            failover_allowed=True,
            status_code=status_code,
        )

    if any(keyword in lowered for keyword in ("timeout", "timed out", "read timeout", "connect timeout")):
        return ProviderErrorClassification(
            category="retryable",
            reason="timeout",
            retryable=True,
            failover_allowed=True,
            status_code=status_code,
        )
    if any(keyword in lowered for keyword in ("connection", "network", "dns", "reset by peer")):
        return ProviderErrorClassification(
            category="retryable",
            reason="network_error",
            retryable=True,
            failover_allowed=True,
            status_code=status_code,
        )

    return ProviderErrorClassification(
        category="unknown",
        reason="unknown_error",
        retryable=False,
        failover_allowed=True,
        status_code=status_code,
    )

