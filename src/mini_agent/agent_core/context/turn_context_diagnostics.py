"""Prepared-context diagnostics and formatting helpers."""

from __future__ import annotations

from typing import Any

from mini_agent.agent_core.context.turn_context_curation import (
    _TURN_CONTEXT_MAX_SOURCE_PRIORITY,
    _clamp_unit_interval,
    _turn_context_source_priority,
)
from mini_agent.agent_core.context.turn_context_policy import (
    context_policy_summary_line,
    resolve_turn_context_policy,
)
from mini_agent.agent_core.context.turn_context_types import (
    TurnContextItem,
    _clean_text,
)


def _normalize_prepared_context_diagnostics(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}

    def _normalize_counter_map(raw: Any) -> dict[str, int]:
        if not isinstance(raw, dict):
            return {}
        normalized: dict[str, int] = {}
        for key, item in raw.items():
            label = _clean_text(key)
            if not label:
                continue
            normalized[label] = max(0, int(item or 0))
        return normalized

    provider_status_by_provider_raw = value.get("provider_status_by_provider")
    provider_status_by_provider: dict[str, dict[str, int]] = {}
    if isinstance(provider_status_by_provider_raw, dict):
        for provider, counts in provider_status_by_provider_raw.items():
            provider_name = _clean_text(provider)
            if not provider_name:
                continue
            provider_status_by_provider[provider_name] = _normalize_counter_map(counts)

    return {
        "turn_count": max(0, int(value.get("turn_count") or 0)),
        "turns_with_context": max(0, int(value.get("turns_with_context") or 0)),
        "turns_without_context": max(0, int(value.get("turns_without_context") or 0)),
        "total_item_count": max(0, int(value.get("total_item_count") or 0)),
        "curated_turn_count": max(0, int(value.get("curated_turn_count") or 0)),
        "total_dropped_item_count": max(
            0,
            int(value.get("total_dropped_item_count") or 0),
        ),
        "source_turn_counts": _normalize_counter_map(value.get("source_turn_counts")),
        "source_item_counts": _normalize_counter_map(value.get("source_item_counts")),
        "provider_status_totals": _normalize_counter_map(
            value.get("provider_status_totals")
        ),
        "provider_status_by_provider": provider_status_by_provider,
        "last_sources": [
            _clean_text(item)
            for item in (value.get("last_sources") or [])
            if _clean_text(item)
        ],
        "last_item_count": max(0, int(value.get("last_item_count") or 0)),
    }


def update_prepared_context_diagnostics(
    current: Any,
    summary: Any,
) -> dict[str, Any]:
    diagnostics = _normalize_prepared_context_diagnostics(current)
    normalized_summary = _normalize_prepared_turn_context_summary(summary)

    diagnostics["turn_count"] += 1
    item_count = int(normalized_summary.get("item_count") or 0)
    if item_count > 0:
        diagnostics["turns_with_context"] += 1
    else:
        diagnostics["turns_without_context"] += 1
    diagnostics["total_item_count"] += item_count
    if bool(normalized_summary.get("curated")):
        diagnostics["curated_turn_count"] += 1
    diagnostics["total_dropped_item_count"] += max(
        0,
        int(normalized_summary.get("dropped_item_count") or 0),
    )

    last_sources = list(normalized_summary.get("sources") or [])
    diagnostics["last_sources"] = last_sources
    diagnostics["last_item_count"] = item_count

    source_turn_counts = dict(diagnostics.get("source_turn_counts") or {})
    for source in last_sources:
        source_turn_counts[source] = source_turn_counts.get(source, 0) + 1
    diagnostics["source_turn_counts"] = source_turn_counts

    source_item_counts = dict(diagnostics.get("source_item_counts") or {})
    for item in list(normalized_summary.get("items") or []):
        source = _clean_text(item.get("source")) or "runtime"
        source_item_counts[source] = source_item_counts.get(source, 0) + 1
    diagnostics["source_item_counts"] = source_item_counts

    provider_status_totals = dict(diagnostics.get("provider_status_totals") or {})
    provider_status_by_provider = {
        _clean_text(provider): dict(counts)
        for provider, counts in (diagnostics.get("provider_status_by_provider") or {}).items()
        if _clean_text(provider)
    }
    for provider_status in list(normalized_summary.get("provider_statuses") or []):
        provider = _clean_text(provider_status.get("provider")) or "provider"
        status = _clean_text(provider_status.get("status")) or "unknown"
        provider_status_totals[status] = provider_status_totals.get(status, 0) + 1
        provider_counts = dict(provider_status_by_provider.get(provider) or {})
        provider_counts[status] = provider_counts.get(status, 0) + 1
        provider_status_by_provider[provider] = provider_counts
    diagnostics["provider_status_totals"] = provider_status_totals
    diagnostics["provider_status_by_provider"] = provider_status_by_provider

    return diagnostics


def prepared_context_diagnostics_summary_line(
    value: Any,
    *,
    include_none: bool = False,
) -> str:
    diagnostics = _normalize_prepared_context_diagnostics(value)
    turn_count = int(diagnostics.get("turn_count") or 0)
    if turn_count <= 0:
        return "none" if include_none else ""

    parts = [
        f"{turn_count} turn(s)",
        f"{int(diagnostics.get('turns_with_context') or 0)} with context",
        f"{int(diagnostics.get('total_item_count') or 0)} item(s)",
    ]
    curated_turn_count = int(diagnostics.get("curated_turn_count") or 0)
    if curated_turn_count > 0:
        parts.append(f"curated {curated_turn_count}")
    dropped = int(diagnostics.get("total_dropped_item_count") or 0)
    if dropped > 0:
        parts.append(f"dropped {dropped}")
    return " | ".join(parts)


def format_prepared_context_diagnostics(
    value: Any,
    *,
    include_header: bool = True,
) -> str:
    diagnostics = _normalize_prepared_context_diagnostics(value)
    summary_line = prepared_context_diagnostics_summary_line(
        diagnostics,
        include_none=False,
    )
    if not summary_line:
        if include_header:
            return "Context diagnostics: no prepared-context turns recorded yet."
        return "No prepared-context turns recorded yet."

    lines: list[str] = []
    if include_header:
        lines.append(f"Context diagnostics: {summary_line}")
    else:
        lines.append(summary_line)

    last_item_count = int(diagnostics.get("last_item_count") or 0)
    last_sources = list(diagnostics.get("last_sources") or [])
    if last_sources:
        lines.append(f"Last turn: {last_item_count} item(s) from {', '.join(last_sources)}")
    else:
        lines.append(f"Last turn: {last_item_count} item(s)")

    source_turn_counts = dict(diagnostics.get("source_turn_counts") or {})
    source_item_counts = dict(diagnostics.get("source_item_counts") or {})
    if source_turn_counts or source_item_counts:
        lines.append("Sources:")
        ordered_sources = sorted(
            set(source_turn_counts) | set(source_item_counts),
            key=lambda source: (
                -int(source_item_counts.get(source) or 0),
                -int(source_turn_counts.get(source) or 0),
                source,
            ),
        )
        for source in ordered_sources:
            lines.append(
                f"- {source}: {int(source_turn_counts.get(source) or 0)} turn(s) | "
                f"{int(source_item_counts.get(source) or 0)} item(s)"
            )

    provider_status_totals = dict(diagnostics.get("provider_status_totals") or {})
    if provider_status_totals:
        ordered_totals = sorted(
            provider_status_totals.items(),
            key=lambda item: (-int(item[1]), item[0]),
        )
        total_parts = [f"{status} {count}" for status, count in ordered_totals]
        lines.append(f"Provider totals: {', '.join(total_parts)}")

    provider_status_by_provider = dict(diagnostics.get("provider_status_by_provider") or {})
    if provider_status_by_provider:
        lines.append("Providers:")
        ordered_providers = sorted(
            provider_status_by_provider.items(),
            key=lambda item: item[0],
        )
        for provider, counts in ordered_providers:
            ordered_counts = sorted(
                counts.items(),
                key=lambda item: (-int(item[1]), item[0]),
            )
            count_label = ", ".join(
                f"{status} {count}"
                for status, count in ordered_counts
            )
            lines.append(f"- {provider}: {count_label}")

    return "\n".join(lines).strip()


def _normalize_prepared_turn_context_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "item_count": 0,
            "sources": [],
            "items": [],
            "provider_failures": [],
            "raw_item_count": 0,
            "deduped_item_count": 0,
            "dropped_item_count": 0,
            "dropped_duplicate_count": 0,
            "dropped_budget_count": 0,
            "curated": False,
            "max_items": 0,
            "max_items_per_source": 0,
            "max_total_chars": 0,
            "provider_statuses": [],
            "policy": resolve_turn_context_policy({}),
        }
    item_count = int(value.get("item_count") or 0)
    sources = [
        _clean_text(item)
        for item in (value.get("sources") or [])
        if _clean_text(item)
    ]
    items = [
        dict(item)
        for item in (value.get("items") or [])
        if isinstance(item, dict)
    ]
    provider_failures = [
        dict(item)
        for item in (value.get("provider_failures") or [])
        if isinstance(item, dict)
    ]
    return {
        "item_count": max(0, item_count),
        "sources": sources,
        "items": items,
        "provider_failures": provider_failures,
        "raw_item_count": max(0, int(value.get("raw_item_count") or item_count)),
        "deduped_item_count": max(
            0,
            int(value.get("deduped_item_count") or item_count),
        ),
        "dropped_item_count": max(0, int(value.get("dropped_item_count") or 0)),
        "dropped_duplicate_count": max(
            0,
            int(value.get("dropped_duplicate_count") or 0),
        ),
        "dropped_budget_count": max(
            0,
            int(value.get("dropped_budget_count") or 0),
        ),
        "curated": bool(value.get("curated", False)),
        "max_items": max(0, int(value.get("max_items") or 0)),
        "max_items_per_source": max(
            0,
            int(value.get("max_items_per_source") or 0),
        ),
        "max_total_chars": max(0, int(value.get("max_total_chars") or 0)),
        "provider_statuses": [
            dict(item)
            for item in (value.get("provider_statuses") or [])
            if isinstance(item, dict)
        ],
        "policy": resolve_turn_context_policy(value.get("policy") or {}),
    }


def prepared_turn_context_summary_line(
    value: Any,
    *,
    include_none: bool = False,
) -> str:
    """Render one compact operator-facing summary line for prepared context."""

    summary = _normalize_prepared_turn_context_summary(value)
    item_count = int(summary["item_count"])
    sources = list(summary["sources"])
    failure_count = len(summary["provider_failures"])
    dropped_item_count = int(summary.get("dropped_item_count") or 0)

    base = ""
    if item_count > 0:
        if sources:
            base = f"{item_count} item(s) from {', '.join(sources)}"
        else:
            base = f"{item_count} item(s)"
    elif include_none:
        base = "none"

    if dropped_item_count > 0:
        dropped_label = f"dropped {dropped_item_count} item(s)"
        base = f"{base} | {dropped_label}" if base else dropped_label

    if failure_count > 0:
        failure_label = f"{failure_count} provider failure(s)"
        base = f"{base} | {failure_label}" if base else failure_label
    return base


def _normalize_prepared_context_detail_mode(value: Any) -> str:
    normalized = _clean_text(value).lower()
    if normalized == "brief":
        return "brief"
    return "full"


def _prepared_context_item_ranking_line(
    item: dict[str, Any],
    *,
    detail_mode: str = "full",
) -> list[str]:
    if _normalize_prepared_context_detail_mode(detail_mode) != "full":
        return []

    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    source = _clean_text(item.get("source")) or "runtime"
    source_priority = _turn_context_source_priority(source)
    ranking_score = _clamp_unit_interval(metadata.get("ranking_score"))
    provider_weight = round(
        float(source_priority) / float(max(1, _TURN_CONTEXT_MAX_SOURCE_PRIORITY)),
        6,
    )
    selection_score = round(provider_weight + ranking_score, 6)

    ranking_parts: list[str] = []
    basis = _clean_text(metadata.get("ranking_basis"))
    if basis:
        ranking_parts.append(f"basis {basis}")
    if "ranking_score_raw" in metadata:
        try:
            ranking_parts.append(
                f"raw {float(metadata.get('ranking_score_raw') or 0.0):.4f}"
            )
        except Exception:
            pass
    ranking_parts.append(f"item-relevance {ranking_score:.3f}")

    selection_parts = [
        f"provider-weight {provider_weight:.3f}",
        f"priority {source_priority}",
        f"final-selection {selection_score:.3f}",
    ]
    return [
        f"ranking: {' | '.join(ranking_parts)}",
        f"selection: {' | '.join(selection_parts)}",
    ]


def format_prepared_turn_context_details(
    value: Any,
    *,
    include_header: bool = True,
    detail_mode: str = "full",
) -> str:
    """Render detailed operator-facing prepared-context lines."""

    summary = _normalize_prepared_turn_context_summary(value)
    normalized_detail_mode = _normalize_prepared_context_detail_mode(detail_mode)
    item_count = int(summary["item_count"])
    items = list(summary["items"])
    provider_failures = list(summary["provider_failures"])
    raw_item_count = int(summary.get("raw_item_count") or item_count)
    dropped_duplicate_count = int(summary.get("dropped_duplicate_count") or 0)
    dropped_budget_count = int(summary.get("dropped_budget_count") or 0)
    provider_statuses = list(summary.get("provider_statuses") or [])
    policy = resolve_turn_context_policy(summary.get("policy") or {})

    lines: list[str] = []
    summary_line = prepared_turn_context_summary_line(summary, include_none=False)
    if include_header and summary_line:
        lines.append(f"Prepared context: {summary_line}")

    if raw_item_count > item_count:
        parts = [f"kept {item_count}/{raw_item_count}"]
        if dropped_duplicate_count > 0:
            parts.append(f"duplicates {dropped_duplicate_count}")
        if dropped_budget_count > 0:
            parts.append(f"budget {dropped_budget_count}")
        lines.append(f"Curated: {' | '.join(parts)}")

    if policy.get("active"):
        lines.append(
            f"Policy: {context_policy_summary_line(policy, include_default=True)}"
        )

    if item_count > 0:
        for index, item in enumerate(items, start=1):
            source = _clean_text(item.get("source")) or "runtime"
            title = _clean_text(item.get("title")) or "Context"
            preview = _clean_text(item.get("preview"))
            item_line = f"{index}. [{source}] {title}"
            if preview:
                item_line = f"{item_line} -> {preview}"
            lines.append(item_line)
            ranking_lines = _prepared_context_item_ranking_line(
                item,
                detail_mode=normalized_detail_mode,
            )
            for ranking_line in ranking_lines:
                lines.append(f"   {ranking_line}")

    if provider_statuses and normalized_detail_mode == "full":
        lines.append("Providers:")
        for provider_status in provider_statuses:
            provider = _clean_text(provider_status.get("provider")) or "provider"
            status = _clean_text(provider_status.get("status")) or "unknown"
            reason = _clean_text(provider_status.get("reason"))
            item_count_label = int(provider_status.get("item_count") or 0)
            provider_line = f"- {provider}: {status}"
            if item_count_label > 0:
                provider_line = f"{provider_line} ({item_count_label} item(s))"
            if reason:
                provider_line = f"{provider_line} | {reason}"
            lines.append(provider_line)

    if provider_failures:
        lines.append("Provider failures:")
        for failure in provider_failures:
            provider = _clean_text(failure.get("provider")) or "provider"
            error = _clean_text(failure.get("error")) or "unknown error"
            lines.append(f"- {provider}: {error}")

    return "\n".join(lines).strip()


def format_turn_context_block(items: list[TurnContextItem]) -> str:
    """Render prepared turn context into one ephemeral system message."""

    lines = [
        "Runtime context for the current turn.",
        "Use this context only when relevant to the user's latest request.",
        "Treat it as system-prepared workspace context, not as new user intent.",
    ]
    for item in items:
        title = _clean_text(item.title) or "Context"
        source = _clean_text(item.source) or "runtime"
        lines.append("")
        lines.append(f"## {title} [{source}]")
        lines.append(str(item.content).strip())
    return "\n".join(lines).strip()


__all__ = [
    "format_prepared_context_diagnostics",
    "format_prepared_turn_context_details",
    "format_turn_context_block",
    "prepared_context_diagnostics_summary_line",
    "prepared_turn_context_summary_line",
    "update_prepared_context_diagnostics",
]
