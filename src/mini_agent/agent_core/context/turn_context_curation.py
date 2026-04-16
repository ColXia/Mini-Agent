"""Turn-context ranking, dedupe, and budget curation helpers."""

from __future__ import annotations

import math
from typing import Any

from mini_agent.agent_core.context.turn_context_policy import resolve_turn_context_policy
from mini_agent.agent_core.context.turn_context_types import (
    TurnContextItem,
    _clean_text,
    _truncate_text,
)


_TURN_CONTEXT_SOURCE_PRIORITY: dict[str, int] = {
    "knowledge_base": 100,
    "consolidated_memory": 90,
    "workspace_memory": 80,
    "user_profile": 75,
    "runtime_task_memory": 72,
    "session_search": 68,
    "static": 70,
    "runtime": 60,
    "skill_catalog": 40,
    "mcp_catalog": 30,
}
_TURN_CONTEXT_MAX_SOURCE_PRIORITY = max(_TURN_CONTEXT_SOURCE_PRIORITY.values()) or 100


def _turn_context_source_priority(source: str) -> int:
    normalized = _clean_text(source).lower()
    if not normalized:
        return 50
    return _TURN_CONTEXT_SOURCE_PRIORITY.get(normalized, 50)


def _clamp_unit_interval(value: Any) -> float:
    try:
        numeric = float(value)
    except Exception:
        return 0.0
    if numeric <= 0.0:
        return 0.0
    if numeric >= 1.0:
        return 1.0
    return round(numeric, 6)


def _normalize_text_relevance_score(value: Any, *, softness: float = 4.0) -> float:
    try:
        numeric = float(value)
    except Exception:
        return 0.0
    if numeric <= 0.0:
        return 0.0
    bounded_softness = max(0.5, float(softness))
    normalized = 1.0 - math.exp(-numeric / bounded_softness)
    return _clamp_unit_interval(normalized)


def _normalize_rrf_relevance_score(value: Any, *, rrf_k: int) -> float:
    try:
        numeric = float(value)
    except Exception:
        return 0.0
    if numeric <= 0.0:
        return 0.0
    bounded_rrf_k = max(1, int(rrf_k))
    theoretical_max = (1.0 / float(bounded_rrf_k + 1)) * 2.0
    if theoretical_max <= 0.0:
        return 0.0
    return _clamp_unit_interval(numeric / theoretical_max)


def _turn_context_item_ranking_score(item: TurnContextItem) -> float:
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    if "ranking_score" in metadata:
        return _clamp_unit_interval(metadata.get("ranking_score"))

    citations = metadata.get("citations")
    if isinstance(citations, list):
        citation_scores = []
        for citation in citations:
            if not isinstance(citation, dict):
                continue
            try:
                citation_scores.append(float(citation.get("score") or 0.0))
            except Exception:
                continue
        if citation_scores:
            return _normalize_rrf_relevance_score(
                max(citation_scores),
                rrf_k=int(metadata.get("ranking_rrf_k") or 60),
            )
    return 0.0


def _turn_context_item_selection_score(item: TurnContextItem) -> float:
    source_weight = (
        float(_turn_context_source_priority(item.source))
        / float(max(1, _TURN_CONTEXT_MAX_SOURCE_PRIORITY))
    )
    ranking_score = _turn_context_item_ranking_score(item)
    return round(source_weight + ranking_score, 6)


def _turn_context_fingerprint(item: TurnContextItem) -> str:
    content = _clean_text(item.content).lower()
    fingerprint = content or _clean_text(item.title).lower()
    if len(fingerprint) > 480:
        fingerprint = fingerprint[:480]
    return fingerprint


def _turn_context_item_size(item: TurnContextItem) -> int:
    return len(_clean_text(item.title)) + len(_clean_text(item.content))


def curate_turn_context_items(
    items: list[TurnContextItem],
    *,
    max_items: int = 4,
    max_items_per_source: int = 1,
    max_total_chars: int = 2400,
) -> tuple[list[TurnContextItem], dict[str, Any]]:
    """Deduplicate and budget prepared context before prompt injection."""

    raw_items = list(items)
    bounded_max_items = max(1, int(max_items))
    bounded_per_source = max(1, int(max_items_per_source))
    bounded_total_chars = max(200, int(max_total_chars))
    if not raw_items:
        summary = {
            "raw_item_count": 0,
            "deduped_item_count": 0,
            "dropped_item_count": 0,
            "dropped_duplicate_count": 0,
            "dropped_budget_count": 0,
            "curated": False,
            "max_items": bounded_max_items,
            "max_items_per_source": bounded_per_source,
            "max_total_chars": bounded_total_chars,
        }
        return [], summary

    deduped_by_fingerprint: dict[str, tuple[int, float, int, TurnContextItem]] = {}
    for index, item in enumerate(raw_items):
        fingerprint = _turn_context_fingerprint(item)
        priority = _turn_context_source_priority(item.source)
        ranking_score = _turn_context_item_ranking_score(item)
        current = deduped_by_fingerprint.get(fingerprint)
        candidate = (priority, ranking_score, index, item)
        if current is None:
            deduped_by_fingerprint[fingerprint] = candidate
            continue
        current_priority, current_ranking_score, current_index, _current_item = current
        if (
            priority > current_priority
            or (
                priority == current_priority
                and (
                    ranking_score > current_ranking_score
                    or (
                        ranking_score == current_ranking_score
                        and index < current_index
                    )
                )
            )
        ):
            deduped_by_fingerprint[fingerprint] = candidate

    deduped_candidates = sorted(
        deduped_by_fingerprint.values(),
        key=lambda item: item[2],
    )
    deduped_items = [item[3] for item in deduped_candidates]

    def _fits_in_original_order(
        candidates: list[tuple[int, float, int, TurnContextItem]],
    ) -> bool:
        if len(candidates) > bounded_max_items:
            return False
        total_chars = 0
        per_source: dict[str, int] = {}
        for _priority, _ranking_score, _index, candidate_item in candidates:
            source = _clean_text(candidate_item.source) or "runtime"
            per_source[source] = per_source.get(source, 0) + 1
            if per_source[source] > bounded_per_source:
                return False
            total_chars += _turn_context_item_size(candidate_item)
            if total_chars > bounded_total_chars:
                return False
        return True

    if _fits_in_original_order(deduped_candidates):
        summary = {
            "raw_item_count": len(raw_items),
            "deduped_item_count": len(deduped_items),
            "dropped_item_count": len(raw_items) - len(deduped_items),
            "dropped_duplicate_count": len(raw_items) - len(deduped_items),
            "dropped_budget_count": 0,
            "curated": len(raw_items) != len(deduped_items),
            "max_items": bounded_max_items,
            "max_items_per_source": bounded_per_source,
            "max_total_chars": bounded_total_chars,
        }
        return deduped_items, summary

    prioritized_candidates = sorted(
        deduped_candidates,
        key=lambda item: (
            -_turn_context_item_selection_score(item[3]),
            -item[0],
            -item[1],
            item[2],
        ),
    )
    selected: list[tuple[int, float, int, TurnContextItem]] = []
    selected_chars = 0
    per_source_counts: dict[str, int] = {}

    for priority, ranking_score, index, item in prioritized_candidates:
        _ = (priority, ranking_score, index)
        source = _clean_text(item.source) or "runtime"
        if per_source_counts.get(source, 0) >= bounded_per_source:
            continue
        if len(selected) >= bounded_max_items:
            continue

        item_size = _turn_context_item_size(item)
        if selected and (selected_chars + item_size) > bounded_total_chars:
            continue

        selected.append((priority, ranking_score, index, item))
        per_source_counts[source] = per_source_counts.get(source, 0) + 1
        selected_chars += item_size

    if not selected:
        selected = [prioritized_candidates[0]]

    selected_items = [item[3] for item in selected]
    dropped_duplicate_count = len(raw_items) - len(deduped_items)
    dropped_budget_count = len(deduped_items) - len(selected_items)
    summary = {
        "raw_item_count": len(raw_items),
        "deduped_item_count": len(deduped_items),
        "dropped_item_count": dropped_duplicate_count + dropped_budget_count,
        "dropped_duplicate_count": dropped_duplicate_count,
        "dropped_budget_count": dropped_budget_count,
        "curated": True,
        "max_items": bounded_max_items,
        "max_items_per_source": bounded_per_source,
        "max_total_chars": bounded_total_chars,
    }
    return selected_items, summary


def summarize_turn_context_items(
    items: list[TurnContextItem],
    *,
    failures: list[dict[str, Any]] | None = None,
    curation: dict[str, Any] | None = None,
    provider_statuses: list[dict[str, Any]] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact, surface-safe summary for observability."""

    normalized_items = list(items)
    normalized_failures = [dict(item) for item in (failures or [])]
    normalized_curation = dict(curation or {})
    normalized_provider_statuses = [
        dict(item)
        for item in (provider_statuses or [])
        if isinstance(item, dict)
    ]
    normalized_policy = resolve_turn_context_policy(policy or {})
    sources: list[str] = []
    for item in normalized_items:
        source = _clean_text(item.source)
        if source and source not in sources:
            sources.append(source)
    return {
        "item_count": len(normalized_items),
        "sources": sources,
        "items": [
            {
                "source": _clean_text(item.source),
                "title": _clean_text(item.title),
                "preview": _truncate_text(item.content, limit=160),
                "metadata": dict(item.metadata),
            }
            for item in normalized_items
        ],
        "provider_failures": normalized_failures,
        "raw_item_count": max(
            len(normalized_items),
            int(normalized_curation.get("raw_item_count") or 0),
        ),
        "deduped_item_count": max(
            len(normalized_items),
            int(normalized_curation.get("deduped_item_count") or 0),
        ),
        "dropped_item_count": max(
            0,
            int(normalized_curation.get("dropped_item_count") or 0),
        ),
        "dropped_duplicate_count": max(
            0,
            int(normalized_curation.get("dropped_duplicate_count") or 0),
        ),
        "dropped_budget_count": max(
            0,
            int(normalized_curation.get("dropped_budget_count") or 0),
        ),
        "curated": bool(normalized_curation.get("curated", False)),
        "max_items": int(normalized_curation.get("max_items") or 0),
        "max_items_per_source": int(
            normalized_curation.get("max_items_per_source") or 0
        ),
        "max_total_chars": int(normalized_curation.get("max_total_chars") or 0),
        "provider_statuses": normalized_provider_statuses,
        "policy": normalized_policy,
    }


__all__ = [
    "curate_turn_context_items",
    "summarize_turn_context_items",
]
