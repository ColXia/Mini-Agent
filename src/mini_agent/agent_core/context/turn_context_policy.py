"""Prepared-context policy normalization and rendering helpers."""

from __future__ import annotations

import re
from typing import Any

from mini_agent.agent_core.context.turn_context_types import (
    RuntimeTurnContext,
    _clean_text,
)


def _positive_int_or_default(value: Any, default: int, *, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except Exception:
        return max(minimum, int(default))
    return max(minimum, parsed)


def _normalize_source_names(value: Any) -> list[str]:
    if value is None:
        return []
    raw_parts: list[str] = []
    if isinstance(value, str):
        raw_parts = re.split(r"[\s,]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw_parts = [str(item or "") for item in value]
    else:
        raw_parts = [str(value)]

    normalized: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        cleaned = _clean_text(part).lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def resolve_turn_context_policy(
    raw: Any,
    *,
    default_max_items: int = 4,
    default_max_items_per_source: int = 1,
    default_max_total_chars: int = 2400,
) -> dict[str, Any]:
    """Normalize operator/runtime policy controlling prepared-context injection."""

    policy_keys = {
        "include_sources",
        "include",
        "exclude_sources",
        "exclude",
        "max_items",
        "max_items_per_source",
        "max_total_chars",
    }
    metadata = {}
    if isinstance(raw, RuntimeTurnContext):
        metadata = raw.metadata if isinstance(raw.metadata, dict) else {}
    elif isinstance(raw, dict):
        metadata = raw
    elif hasattr(raw, "metadata") and isinstance(getattr(raw, "metadata", None), dict):
        metadata = dict(getattr(raw, "metadata"))

    nested: dict[str, Any]
    if isinstance(metadata, dict) and any(key in metadata for key in policy_keys):
        nested = dict(metadata)
    else:
        nested = (
            metadata.get("prepared_context_policy")
            if isinstance(metadata, dict)
            else None
        )
        if not isinstance(nested, dict):
            nested = metadata.get("context_policy") if isinstance(metadata, dict) else None
        if not isinstance(nested, dict):
            nested = {}

    include_sources = _normalize_source_names(
        nested.get("include_sources")
        if "include_sources" in nested
        else nested.get("include")
    )
    exclude_sources = _normalize_source_names(
        nested.get("exclude_sources")
        if "exclude_sources" in nested
        else nested.get("exclude")
    )

    exclude_sources = [item for item in exclude_sources if item not in include_sources]

    max_items = _positive_int_or_default(
        nested.get("max_items"),
        default_max_items,
    )
    max_items_per_source = _positive_int_or_default(
        nested.get("max_items_per_source"),
        default_max_items_per_source,
    )
    max_total_chars = _positive_int_or_default(
        nested.get("max_total_chars"),
        default_max_total_chars,
        minimum=200,
    )
    active = bool(
        include_sources
        or exclude_sources
        or max_items != int(default_max_items)
        or max_items_per_source != int(default_max_items_per_source)
        or max_total_chars != int(default_max_total_chars)
    )
    return {
        "include_sources": include_sources,
        "exclude_sources": exclude_sources,
        "max_items": max_items,
        "max_items_per_source": max_items_per_source,
        "max_total_chars": max_total_chars,
        "active": active,
    }


def provider_allowed_by_policy(
    provider_name: str,
    policy: dict[str, Any] | None,
) -> tuple[bool, str]:
    normalized_provider = _clean_text(provider_name).lower()
    normalized_policy = resolve_turn_context_policy(policy or {})
    include_sources = list(normalized_policy.get("include_sources") or [])
    exclude_sources = list(normalized_policy.get("exclude_sources") or [])

    if include_sources and normalized_provider not in include_sources:
        return False, "not included by prepared-context policy"
    if normalized_provider in exclude_sources:
        return False, "excluded by prepared-context policy"
    return True, ""


def context_policy_summary_line(
    value: Any,
    *,
    include_default: bool = False,
) -> str:
    """Render one compact summary line for prepared-context policy."""

    policy = resolve_turn_context_policy(value)
    if not policy.get("active") and not include_default:
        return ""

    parts: list[str] = []
    include_sources = list(policy.get("include_sources") or [])
    exclude_sources = list(policy.get("exclude_sources") or [])
    if include_sources:
        parts.append(f"include={', '.join(include_sources)}")
    if exclude_sources:
        parts.append(f"exclude={', '.join(exclude_sources)}")
    parts.append(
        "budget="
        f"{int(policy.get('max_items') or 0)} item(s)"
        f"/{int(policy.get('max_total_chars') or 0)} chars"
        f"/{int(policy.get('max_items_per_source') or 0)} per-source"
    )
    if not parts:
        return "default"
    return " | ".join(parts)


def format_context_policy_details(
    value: Any,
    *,
    include_header: bool = True,
) -> str:
    """Render detailed prepared-context policy lines."""

    policy = resolve_turn_context_policy(value)
    lines: list[str] = []
    if include_header:
        lines.append(f"Policy: {context_policy_summary_line(policy, include_default=True)}")
    else:
        lines.append(context_policy_summary_line(policy, include_default=True))
    return "\n".join(line for line in lines if line).strip()


__all__ = [
    "context_policy_summary_line",
    "format_context_policy_details",
    "provider_allowed_by_policy",
    "resolve_turn_context_policy",
]
