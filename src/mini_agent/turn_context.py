"""Turn-scoped context providers for Agent core.

This module gives the runtime one clean seam for injecting ephemeral
context into a single turn without polluting long-lived conversation
history. Future RAG, memory, MCP, and skill-context integrations can all
hang off this surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
from pathlib import Path
import re
from typing import Any, Protocol, runtime_checkable

from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime
from mini_agent.memory.promotion import has_workspace_shared_scope_signal
from mini_agent.memory.service import MemoryService
from mini_agent.tools.mcp.naming import format_mcp_tool_label


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\-\u4e00-\u9fff]+")
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
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


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _truncate_text(value: Any, *, limit: int) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def _message_payload(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_PATTERN.findall(text or "")]


def _parse_optional_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _mcp_tool_label(tool: Any) -> str:
    alias_name = _clean_text(getattr(tool, "name", None))
    raw_name = _clean_text(
        getattr(tool, "remote_name", None)
        or getattr(tool, "raw_name", None)
    )
    return format_mcp_tool_label(alias_name, raw_name)


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


def _score_text_match(
    *,
    query_text: str,
    query_tokens: list[str],
    haystack: str,
) -> float:
    normalized_haystack = _clean_text(haystack).lower()
    normalized_query = _clean_text(query_text).lower()
    if not normalized_haystack or not normalized_query:
        return 0.0

    score = 0.0
    if normalized_query in normalized_haystack:
        score += 4.0

    if not query_tokens:
        return score

    haystack_tokens = set(_tokenize(normalized_haystack))
    query_token_set = set(query_tokens)
    overlap = len(haystack_tokens & query_token_set)
    if overlap <= 0 and score <= 0.0:
        partial = 0.0
        for query_token in query_token_set:
            query_has_cjk = bool(_CJK_PATTERN.search(query_token))
            best_partial = 0.0
            for haystack_token in haystack_tokens:
                if query_token == haystack_token:
                    best_partial = max(best_partial, 1.0)
                    continue
                if query_has_cjk:
                    if len(query_token) >= 2 and len(haystack_token) >= 2 and (
                        query_token in haystack_token or haystack_token in query_token
                    ):
                        best_partial = max(
                            best_partial,
                            min(len(query_token), len(haystack_token))
                            / max(len(query_token), len(haystack_token)),
                        )
                else:
                    if len(query_token) >= 4 and len(haystack_token) >= 4 and (
                        query_token in haystack_token or haystack_token in query_token
                    ):
                        best_partial = max(
                            best_partial,
                            min(len(query_token), len(haystack_token))
                            / max(len(query_token), len(haystack_token)),
                        )
            partial += best_partial
        if partial <= 0.0 and score <= 0.0:
            return 0.0
        score += partial

    score += overlap * 1.5
    score += float(overlap) / float(max(1, len(query_tokens)))
    return round(score, 6)


def _metadata_text_chunks(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = _clean_text(value)
        return [text] if text else []
    if isinstance(value, dict):
        chunks: list[str] = []
        for nested in value.values():
            chunks.extend(_metadata_text_chunks(nested))
        return chunks
    if isinstance(value, (list, tuple, set)):
        chunks: list[str] = []
        for item in value:
            chunks.extend(_metadata_text_chunks(item))
        return chunks
    text = _clean_text(value)
    return [text] if text else []


def _skill_match_haystack(entry: Any) -> str:
    metadata = getattr(entry, "metadata", None)
    metadata_chunks: list[str] = []
    if isinstance(metadata, dict):
        for key in (
            "trigger_keywords",
            "trigger_phrases",
            "aliases",
            "keywords",
            "tags",
        ):
            metadata_chunks.extend(_metadata_text_chunks(metadata.get(key)))
    parts = [
        _clean_text(getattr(entry, "name", None)),
        _clean_text(getattr(entry, "description", None)),
        _clean_text(getattr(entry, "skill_key", None)),
        *metadata_chunks,
    ]
    return " ".join(part for part in parts if part)


def _skill_metadata_match_bonus(entry: Any, query_text: str) -> float:
    metadata = getattr(entry, "metadata", None)
    if not isinstance(metadata, dict):
        return 0.0
    lowered_query = _clean_text(query_text).lower()
    if not lowered_query:
        return 0.0

    bonuses = 0.0
    seen: set[str] = set()
    for key in ("trigger_keywords", "trigger_phrases", "aliases", "keywords", "tags"):
        for chunk in _metadata_text_chunks(metadata.get(key)):
            normalized_chunk = _clean_text(chunk).lower()
            if not normalized_chunk or normalized_chunk in seen:
                continue
            seen.add(normalized_chunk)
            if normalized_chunk not in lowered_query and lowered_query not in normalized_chunk:
                continue
            if _CJK_PATTERN.search(normalized_chunk):
                if len(normalized_chunk) >= 2:
                    bonuses += 1.25
            else:
                if len(normalized_chunk) >= 4:
                    bonuses += 0.75
    return round(min(bonuses, 4.0), 6)


def _last_user_message(agent: Any) -> str:
    for message in reversed(list(getattr(agent, "messages", []) or [])):
        if _clean_text(getattr(message, "role", None)) != "user":
            continue
        text = _clean_text(getattr(message, "content", ""))
        if text:
            return text
    return ""


def _previous_user_message(agent: Any, *, exclude: str) -> str:
    skipped_current = False
    target = _clean_text(exclude)
    for message in reversed(list(getattr(agent, "messages", []) or [])):
        if _clean_text(getattr(message, "role", None)) != "user":
            continue
        text = _clean_text(getattr(message, "content", ""))
        if not text:
            continue
        if not skipped_current and text == target:
            skipped_current = True
            continue
        return text
    return ""


def _resolve_followup_query(
    *,
    turn_context: RuntimeTurnContext,
    agent: Any,
    short_query_token_threshold: int = 4,
) -> str:
    query = str(turn_context.user_input or "").strip()
    if not query:
        query = _last_user_message(agent)
    if not query:
        return ""

    tokens = _tokenize(query)
    if len(tokens) > max(1, int(short_query_token_threshold)):
        return query

    previous_query = _previous_user_message(agent, exclude=query)
    if previous_query:
        return f"{previous_query} {query}".strip()
    return query


_SESSION_SEARCH_STOPWORDS = {
    "a",
    "an",
    "are",
    "be",
    "can",
    "could",
    "did",
    "do",
    "does",
    "how",
    "i",
    "is",
    "it",
    "keep",
    "me",
    "should",
    "the",
    "to",
    "we",
    "what",
    "why",
    "you",
}


def _session_search_query_candidates(query: str) -> list[str]:
    normalized_query = _clean_text(query)
    if not normalized_query:
        return []

    candidates: list[str] = [normalized_query]
    tokens = [
        token
        for token in _tokenize(normalized_query)
        if token not in _SESSION_SEARCH_STOPWORDS
    ]
    if not tokens:
        return candidates

    longest = sorted(tokens, key=lambda item: (-len(item), item))
    phrases = [
        " ".join(longest[:2]),
        " ".join(longest[:1]),
    ]
    phrases.extend(longest[:3])

    seen: set[str] = {normalized_query.lower()}
    for candidate in phrases:
        cleaned = _clean_text(candidate)
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        seen.add(lowered)
        candidates.append(cleaned)
    return candidates


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
        nested = metadata.get("prepared_context_policy") if isinstance(metadata, dict) else None
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

    # Prevent contradictory policy values from surviving normalization.
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


@dataclass(frozen=True)
class RuntimeTurnContext:
    """Normalized turn context passed into core providers."""

    session_id: str
    submission_id: str
    user_input: str
    metadata: dict[str, Any] = field(default_factory=dict)
    workspace_dir: str | None = None


@dataclass(frozen=True)
class TurnContextItem:
    """One prepared context fragment for the active turn."""

    source: str
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class TurnContextProvider(Protocol):
    """Protocol for turn-scoped context preparation."""

    name: str

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | list[TurnContextItem] | dict[str, Any] | None:
        """Return one or more context items for the current turn."""


class RuntimeRecoveryTurnContextProvider:
    """Inject one lightweight recovery hint for the first post-restart turn."""

    name = "runtime_recovery"

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        _ = agent
        metadata = turn_context.metadata if isinstance(turn_context.metadata, dict) else {}
        recovery = metadata.get("recovery")
        if not isinstance(recovery, dict):
            return None

        state = _clean_text(recovery.get("state")) or "interrupted"
        summary = _clean_text(recovery.get("summary")) or "previous shared-session task was interrupted"
        last_activity = _clean_text(recovery.get("last_activity"))
        last_user = _clean_text(recovery.get("last_user_message"))
        last_assistant = _clean_text(recovery.get("last_assistant_message"))
        pending_approvals = recovery.get("pending_approvals")
        pending_items = pending_approvals if isinstance(pending_approvals, list) else []
        approval_labels = [
            f"{_clean_text(item.get('tool_name')) or 'tool'}[{_clean_text(item.get('token'))}]"
            for item in pending_items
            if isinstance(item, dict) and _clean_text(item.get("token"))
        ]

        lines = [
            "Previous shared-session work was interrupted before this turn.",
            f"Restart state: {state}",
            f"Restart summary: {summary}",
        ]
        if last_activity:
            lines.append(f"Last activity: {last_activity}")
        if last_user:
            lines.append(f"Last user message: {last_user}")
        if last_assistant:
            lines.append(f"Last assistant message: {last_assistant}")
        if approval_labels:
            lines.append(
                "Pending approvals were lost after restart and must be re-evaluated: "
                + ", ".join(approval_labels)
            )
        lines.append(
            "Continue from the restored session context and reassess any interrupted tool step safely."
        )

        return TurnContextItem(
            source="runtime",
            title="Shared-session recovery",
            content="\n".join(lines),
            metadata={
                "ranking_score": 1.0,
                "ranking_basis": "runtime_recovery",
                "recovery_state": state,
                "recovery_pending_approval_count": len(approval_labels),
            },
        )


class UserProfileTurnContextProvider:
    """Prepare relevant global user-profile facts for one turn."""

    name = "user_profile"

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        top_k: int = 3,
        max_fact_chars: int = 220,
        global_memory_root: str | Path | None = None,
    ) -> None:
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.top_k = max(1, int(top_k))
        self.max_fact_chars = max(80, int(max_fact_chars))
        self.memory_service = MemoryService(
            self.workspace_dir,
            global_memory_root=global_memory_root,
        )

    async def describe_readiness(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any]:
        _ = (turn_context, agent)
        profile = self.memory_service.profile()
        facts = list(profile.get("facts") or [])
        if not facts:
            return {
                "status": "unavailable",
                "available": False,
                "reason": "no global user-profile facts found",
            }
        return {
            "status": "ready",
            "available": True,
            "reason": f"{len(facts)} global profile fact(s) available",
        }

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        query = _resolve_followup_query(
            turn_context=turn_context,
            agent=agent,
            short_query_token_threshold=4,
        )
        if not query:
            return None

        hits = self.memory_service.search_profile(query=query, limit=self.top_k)
        if not hits:
            return None

        profile = self.memory_service.profile()
        lines: list[str] = []
        for index, hit in enumerate(hits, start=1):
            fact = _truncate_text(hit.get("fact"), limit=self.max_fact_chars)
            lines.append(f"{index}. {fact}")

        return TurnContextItem(
            source=self.name,
            title="Relevant user profile",
            content="\n".join(lines),
            metadata={
                "query": query,
                "returned": len(hits),
                "scope": _clean_text(profile.get("scope")) or "global",
                "user_file": _clean_text(profile.get("user_file")),
                "ranking_score": _normalize_text_relevance_score(hits[0].get("score")),
                "ranking_score_raw": round(float(hits[0].get("score") or 0.0), 6),
                "ranking_basis": "user_profile_match",
            },
        )


def coerce_runtime_turn_context(
    raw: Any | None,
    *,
    workspace_dir: str | Path | None = None,
) -> RuntimeTurnContext:
    """Coerce external turn metadata into the core runtime shape."""

    fallback_workspace = None
    if workspace_dir is not None:
        fallback_workspace = str(Path(workspace_dir).expanduser().resolve())

    if isinstance(raw, RuntimeTurnContext):
        if raw.workspace_dir or fallback_workspace is None:
            return raw
        return RuntimeTurnContext(
            session_id=raw.session_id,
            submission_id=raw.submission_id,
            user_input=raw.user_input,
            metadata=dict(raw.metadata),
            workspace_dir=fallback_workspace,
        )

    session_id = _clean_text(_message_payload(raw, "session_id")) or "default"
    submission_id = _clean_text(_message_payload(raw, "submission_id")) or "submission"
    user_input = str(_message_payload(raw, "user_input") or "")
    metadata = _message_payload(raw, "metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    raw_workspace = _clean_text(_message_payload(raw, "workspace_dir"))
    return RuntimeTurnContext(
        session_id=session_id,
        submission_id=submission_id,
        user_input=user_input,
        metadata=dict(metadata),
        workspace_dir=raw_workspace or fallback_workspace,
    )


def normalize_turn_context_items(
    value: TurnContextItem | list[TurnContextItem] | dict[str, Any] | None,
    *,
    default_source: str,
) -> list[TurnContextItem]:
    """Normalize provider output into context items."""

    if value is None:
        return []
    if isinstance(value, TurnContextItem):
        return [value]
    if isinstance(value, list):
        normalized: list[TurnContextItem] = []
        for item in value:
            normalized.extend(
                normalize_turn_context_items(
                    item,
                    default_source=default_source,
                )
            )
        return normalized
    if isinstance(value, dict):
        title = _clean_text(value.get("title")) or default_source.replace("_", " ")
        content = str(value.get("content") or "").strip()
        if not content:
            return []
        metadata = value.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        return [
            TurnContextItem(
                source=_clean_text(value.get("source")) or default_source,
                title=title,
                content=content,
                metadata=dict(metadata),
            )
        ]
    return []


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

    def _fits_in_original_order(candidates: list[tuple[int, float, int, TurnContextItem]]) -> bool:
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
        "dropped_item_count": max(0, int(normalized_curation.get("dropped_item_count") or 0)),
        "dropped_duplicate_count": max(0, int(normalized_curation.get("dropped_duplicate_count") or 0)),
        "dropped_budget_count": max(0, int(normalized_curation.get("dropped_budget_count") or 0)),
        "curated": bool(normalized_curation.get("curated", False)),
        "max_items": int(normalized_curation.get("max_items") or 0),
        "max_items_per_source": int(normalized_curation.get("max_items_per_source") or 0),
        "max_total_chars": int(normalized_curation.get("max_total_chars") or 0),
        "provider_statuses": normalized_provider_statuses,
        "policy": normalized_policy,
    }


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
        "total_dropped_item_count": max(0, int(value.get("total_dropped_item_count") or 0)),
        "source_turn_counts": _normalize_counter_map(value.get("source_turn_counts")),
        "source_item_counts": _normalize_counter_map(value.get("source_item_counts")),
        "provider_status_totals": _normalize_counter_map(value.get("provider_status_totals")),
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
    summary_line = prepared_context_diagnostics_summary_line(diagnostics, include_none=False)
    if not summary_line:
        return "Context diagnostics: no prepared-context turns recorded yet." if include_header else "No prepared-context turns recorded yet."

    lines: list[str] = []
    if include_header:
        lines.append(f"Context diagnostics: {summary_line}")
    else:
        lines.append(summary_line)

    last_item_count = int(diagnostics.get("last_item_count") or 0)
    last_sources = list(diagnostics.get("last_sources") or [])
    if last_sources:
        lines.append(
            f"Last turn: {last_item_count} item(s) from {', '.join(last_sources)}"
        )
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
            count_label = ", ".join(f"{status} {count}" for status, count in ordered_counts)
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
        "deduped_item_count": max(0, int(value.get("deduped_item_count") or item_count)),
        "dropped_item_count": max(0, int(value.get("dropped_item_count") or 0)),
        "dropped_duplicate_count": max(0, int(value.get("dropped_duplicate_count") or 0)),
        "dropped_budget_count": max(0, int(value.get("dropped_budget_count") or 0)),
        "curated": bool(value.get("curated", False)),
        "max_items": max(0, int(value.get("max_items") or 0)),
        "max_items_per_source": max(0, int(value.get("max_items_per_source") or 0)),
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
            ranking_parts.append(f"raw {float(metadata.get('ranking_score_raw') or 0.0):.4f}")
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
        lines.append(f"Policy: {context_policy_summary_line(policy, include_default=True)}")

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


class WorkspaceMemoryContextProvider:
    """Prepare relevant workspace-memory snippets for one turn."""

    name = "workspace_memory"

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        top_k: int = 3,
        max_note_chars: int = 220,
    ) -> None:
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.top_k = max(1, int(top_k))
        self.max_note_chars = max(80, int(max_note_chars))
        self.memory_service = MemoryService(self.workspace_dir)

    async def describe_readiness(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any]:
        _ = (turn_context, agent)
        notes = self.memory_service.load_notes()
        if not notes:
            return {
                "status": "unavailable",
                "available": False,
                "reason": "no workspace memory notes found",
            }
        return {
            "status": "ready",
            "available": True,
            "reason": f"{len(notes)} note(s) available",
        }

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        notes = self.memory_service.load_notes()
        if not notes:
            return None

        query = self._resolve_query(turn_context=turn_context, agent=agent)
        if not query:
            return None

        ranked = self.memory_service.rank_workspace_notes(query=query)
        if not ranked:
            return None

        selected = ranked[: self.top_k]
        lines: list[str] = []
        for index, (note, _score) in enumerate(selected, start=1):
            source = self.memory_service.relative_path(note.path)
            note_text = _truncate_text(note.content, limit=self.max_note_chars)
            lines.append(f"{index}. [{note.category}] {note_text} (source: {source})")

        return TurnContextItem(
            source=self.name,
            title="Relevant workspace memory",
            content="\n".join(lines),
            metadata={
                "query": query,
                "returned": len(selected),
                "ranking_score": _normalize_text_relevance_score(selected[0][1]),
                "ranking_score_raw": round(float(selected[0][1]), 6),
                "ranking_basis": "workspace_memory_text_match",
            },
        )

    def _resolve_query(self, *, turn_context: RuntimeTurnContext, agent: Any) -> str:
        return _resolve_followup_query(
            turn_context=turn_context,
            agent=agent,
            short_query_token_threshold=4,
        )


class ConsolidatedMemoryTurnContextProvider:
    """Prepare relevant consolidated-memory hits for one turn."""

    name = "consolidated_memory"

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        memory_file: str | Path | None = None,
        session_store_dir: str | Path | None = None,
        top_k: int = 3,
        stale_after_days: int = 30,
        max_item_chars: int = 220,
        support_lookup: Any | None = None,
        auto_refresh: bool = True,
    ) -> None:
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.memory_file = (
            Path(memory_file).expanduser().resolve()
            if memory_file is not None
            else None
        )
        self.session_store_dir = (
            Path(session_store_dir).expanduser().resolve()
            if session_store_dir is not None
            else None
        )
        self.top_k = max(1, int(top_k))
        self.stale_after_days = max(1, int(stale_after_days))
        self.max_item_chars = max(80, int(max_item_chars))
        self.support_lookup = support_lookup
        self.auto_refresh = bool(auto_refresh)
        self.memory_service = MemoryService(
            self.workspace_dir,
            session_store_dir=self.session_store_dir,
        )

    async def describe_readiness(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any]:
        _ = agent
        refresh_status = self.memory_service.consolidated_refresh_status(
            memory_file=self.memory_file,
            exclude_session_id=turn_context.session_id,
        )
        if self.auto_refresh and bool(refresh_status.get("needs_refresh")):
            self.memory_service.refresh_consolidated_memory(
                memory_file=self.memory_file,
                exclude_session_id=turn_context.session_id,
            )
        snapshot = self.memory_service.consolidated_snapshot(memory_file=self.memory_file)
        if not snapshot.get("items"):
            return {
                "status": "unavailable",
                "available": False,
                "reason": "no consolidated memory entries found",
            }
        return {
            "status": "ready",
            "available": True,
            "reason": f"{len(snapshot.get('items') or [])} consolidated item(s) available",
        }

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        query = _resolve_followup_query(
            turn_context=turn_context,
            agent=agent,
            short_query_token_threshold=4,
        )
        if not query:
            return None

        refresh_status = self.memory_service.consolidated_refresh_status(
            memory_file=self.memory_file,
            exclude_session_id=turn_context.session_id,
        )
        refresh_result: dict[str, Any] | None = None
        if self.auto_refresh and bool(refresh_status.get("needs_refresh")):
            refresh_result = self.memory_service.refresh_consolidated_memory(
                memory_file=self.memory_file,
                exclude_session_id=turn_context.session_id,
            )

        payload = self.memory_service.search_relevant_consolidated_memory(
            query=query,
            top_k=self.top_k,
            stale_after_days=self.stale_after_days,
            memory_file=self.memory_file,
            support_lookup=self.support_lookup,
        )
        hits = payload.get("hits") or []
        if not hits:
            return None

        drift_summary: dict[str, int] = {}
        lines: list[str] = []
        for index, hit in enumerate(hits, start=1):
            content = _truncate_text(hit.get("content"), limit=self.max_item_chars)
            drift_status = _clean_text(hit.get("drift_status")) or "unverified"
            drift_summary[drift_status] = drift_summary.get(drift_status, 0) + 1
            drift_suffix = drift_status.replace("_", " ")
            reason = _truncate_text(hit.get("drift_reason"), limit=90)
            if reason and drift_status != "aligned":
                drift_suffix = f"{drift_suffix}: {reason}"
            lines.append(f"{index}. {content} (drift: {drift_suffix})")

        return TurnContextItem(
            source=self.name,
            title="Relevant consolidated memory",
            content="\n".join(lines),
            metadata={
                "query": payload.get("query") or query,
                "returned": int(payload.get("returned") or 0),
                "memory_file": _clean_text(payload.get("memory_file")) or str(self.memory_file or self.memory_service.long_term_file),
                "memory_last_updated_utc": _clean_text(payload.get("memory_last_updated_utc")),
                "memory_file_mtime_utc": _clean_text(payload.get("memory_file_mtime_utc")),
                "drift_summary": drift_summary,
                "refresh_reason": _clean_text(refresh_status.get("reason")),
                "refresh_triggered": bool(refresh_result and refresh_result.get("refreshed")),
                "ranking_score": _normalize_text_relevance_score(hits[0].get("score")),
                "ranking_score_raw": round(float(hits[0].get("score") or 0.0), 6),
                "ranking_basis": "consolidated_memory_relevance",
            },
        )


class RuntimeTaskMemoryTurnContextProvider:
    """Prepare relevant persisted runtime task memory for one turn."""

    name = "runtime_task_memory"

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        state_root: str | Path | None = None,
        session_top_k: int = 2,
        shared_top_k: int = 1,
        max_item_chars: int = 220,
        include_workspace_shared: bool = True,
    ) -> None:
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.session_top_k = max(1, int(session_top_k))
        self.shared_top_k = max(1, int(shared_top_k))
        self.max_item_chars = max(80, int(max_item_chars))
        self.include_workspace_shared = bool(include_workspace_shared)
        self.runtime = WorkspaceMemoriaRuntime(
            self.workspace_dir,
            state_root=state_root,
        )

    async def describe_readiness(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any]:
        _ = agent
        session_id = _clean_text(turn_context.session_id)
        if not session_id:
            return {
                "status": "unavailable",
                "available": False,
                "reason": "missing session id for runtime task memory",
            }

        stats = self.runtime.stats()
        namespaces = stats.get("namespaces", {}) if isinstance(stats.get("namespaces"), dict) else {}
        session_namespace = self.runtime.session_namespace(session_id)
        session_stats = namespaces.get(session_namespace, {}) if isinstance(namespaces.get(session_namespace), dict) else {}
        shared_stats = namespaces.get(self.runtime.shared_namespace(), {}) if isinstance(namespaces.get(self.runtime.shared_namespace()), dict) else {}
        count = sum(int(value or 0) for value in session_stats.values()) + sum(int(value or 0) for value in shared_stats.values())
        if count <= 0:
            return {
                "status": "unavailable",
                "available": False,
                "reason": "no persisted runtime task memory entries found",
            }
        return {
            "status": "ready",
            "available": True,
            "reason": f"{count} runtime task memory item(s) available",
        }

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        session_id = _clean_text(turn_context.session_id)
        if not session_id:
            return None

        query = _resolve_followup_query(
            turn_context=turn_context,
            agent=agent,
            short_query_token_threshold=4,
        )
        if not query:
            return None

        session_namespace = self.runtime.session_namespace(session_id)
        session_hits = [
            self.runtime._hit_to_dict(item)
            for item in self.runtime.retrieve(
                namespace=session_namespace,
                query=query,
                limit=self.session_top_k,
            )
        ]
        query_requests_workspace_shared = has_workspace_shared_scope_signal(query)
        include_shared_hits = bool(
            self.include_workspace_shared
            and (query_requests_workspace_shared or len(session_hits) < self.session_top_k)
        )
        shared_hits: list[dict[str, Any]] = []
        if include_shared_hits:
            shared_hits = [
                self.runtime._hit_to_dict(item)
                for item in self.runtime.retrieve(
                    namespace=self.runtime.shared_namespace(),
                    query=query,
                    limit=self.shared_top_k,
                )
            ]
        if not session_hits and not shared_hits:
            return None

        lines: list[str] = []
        top_score = 0.0
        for index, hit in enumerate(session_hits, start=1):
            content = _truncate_text(hit.get("content"), limit=self.max_item_chars)
            lines.append(f"S{index}. {content} (layer: {_clean_text(hit.get('layer')) or 'working'})")
            top_score = max(top_score, float(hit.get("score") or 0.0))
        for index, hit in enumerate(shared_hits, start=1):
            content = _truncate_text(hit.get("content"), limit=self.max_item_chars)
            lines.append(f"W{index}. {content} (layer: {_clean_text(hit.get('layer')) or 'working'})")
            top_score = max(top_score, float(hit.get("score") or 0.0))

        return TurnContextItem(
            source=self.name,
            title="Relevant runtime task memory",
            content="\n".join(lines),
            metadata={
                "query": query,
                "session_namespace": session_namespace,
                "workspace_shared_namespace": self.runtime.shared_namespace(),
                "session_returned": len(session_hits),
                "shared_returned": len(shared_hits),
                "returned": len(session_hits) + len(shared_hits),
                "workspace_shared_requested": query_requests_workspace_shared,
                "workspace_shared_included": include_shared_hits,
                "workspace_shared_reason": (
                    "query_scope"
                    if query_requests_workspace_shared
                    else "session_fallback" if include_shared_hits else "suppressed_by_session_hits"
                ),
                "ranking_score": _normalize_text_relevance_score(top_score),
                "ranking_score_raw": round(top_score, 6),
                "ranking_basis": "runtime_task_memory_relevance",
            },
        )


class SessionSearchTurnContextProvider:
    """Prepare relevant same-workspace session-history hits for one turn."""

    name = "session_search"

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        session_store_dir: str | Path | None = None,
        top_k: int = 3,
        max_snippet_chars: int = 220,
        exclude_current_session: bool = True,
    ) -> None:
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.session_store_dir = (
            Path(session_store_dir).expanduser().resolve()
            if session_store_dir is not None
            else None
        )
        self.top_k = max(1, int(top_k))
        self.max_snippet_chars = max(80, int(max_snippet_chars))
        self.exclude_current_session = bool(exclude_current_session)
        self.memory_service = MemoryService(
            self.workspace_dir,
            session_store_dir=self.session_store_dir,
        )

    async def describe_readiness(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any]:
        _ = (turn_context, agent)
        stats = self.memory_service.session_search_stats()
        indexed_sessions = int(stats.get("indexed_sessions") or 0)
        if indexed_sessions <= 0:
            return {
                "status": "unavailable",
                "available": False,
                "reason": "no indexed session history found",
            }
        return {
            "status": "ready",
            "available": True,
            "reason": f"{indexed_sessions} indexed session(s) available",
        }

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        query = _resolve_followup_query(
            turn_context=turn_context,
            agent=agent,
            short_query_token_threshold=4,
        )
        if not query:
            return None

        excluded_session_id = turn_context.session_id if self.exclude_current_session else None
        lookup_query = query
        hits: list[dict[str, Any]] = []
        for candidate_query in _session_search_query_candidates(query):
            hits = self.memory_service.search_sessions(
                query=candidate_query,
                limit=max(self.top_k * 3, self.top_k),
                workspace_anchor_dir=str(self.memory_service.anchor_dir),
                exclude_session_id=excluded_session_id,
            )
            if hits:
                lookup_query = candidate_query
                break
        if not hits:
            return None

        selected = hits[: self.top_k]
        lines: list[str] = []
        session_ids: list[str] = []
        query_tokens = _tokenize(lookup_query)
        ranking_raw = 0.0
        for index, hit in enumerate(selected, start=1):
            session_id = _clean_text(hit.get("session_id")) or "session"
            role = _clean_text(hit.get("role")).lower() or "message"
            snippet = _truncate_text(hit.get("snippet") or hit.get("content"), limit=self.max_snippet_chars)
            session_ids.append(session_id)
            if index == 1:
                ranking_raw = max(
                    _score_text_match(
                        query_text=lookup_query,
                        query_tokens=query_tokens,
                        haystack=_clean_text(hit.get("content")),
                    ),
                    0.5,
                )
            lines.append(f"{index}. [{session_id}/{role}] {snippet}")

        return TurnContextItem(
            source=self.name,
            title="Relevant workspace session history",
            content="\n".join(lines),
            metadata={
                "query": query,
                "lookup_query": lookup_query,
                "returned": len(selected),
                "workspace_anchor_dir": str(self.memory_service.anchor_dir),
                "excluded_session_id": excluded_session_id,
                "session_ids": session_ids,
                "ranking_score": _normalize_text_relevance_score(ranking_raw),
                "ranking_score_raw": round(float(ranking_raw), 6),
                "ranking_basis": "session_search_match",
            },
        )


class SkillCatalogTurnContextProvider:
    """Prepare lightweight relevant-skill hints for one turn."""

    name = "skill_catalog"

    def __init__(
        self,
        *,
        builtin_dir: str | Path,
        workspace_dir: str | Path | None = None,
        plugin_dirs: list[str | Path] | None = None,
        policy_store: Any | None = None,
        top_k: int = 3,
        max_description_chars: int = 180,
    ) -> None:
        self.builtin_dir = Path(builtin_dir).expanduser().resolve()
        self.workspace_dir = (
            Path(workspace_dir).expanduser().resolve()
            if workspace_dir is not None
            else None
        )
        self.plugin_dirs = [
            Path(path).expanduser().resolve()
            for path in (plugin_dirs or [])
        ]
        self.policy_store = policy_store
        self.top_k = max(1, int(top_k))
        self.max_description_chars = max(60, int(max_description_chars))
        self._loader: Any | None = None
        self._cached_entries: list[Any] | None = None

    async def describe_readiness(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any]:
        _ = (turn_context, agent)
        entries = self._active_entries()
        if not entries:
            return {
                "status": "unavailable",
                "available": False,
                "reason": "no active skills discovered",
            }
        return {
            "status": "ready",
            "available": True,
            "reason": f"{len(entries)} skill(s) available",
        }

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        query = _resolve_followup_query(
            turn_context=turn_context,
            agent=agent,
            short_query_token_threshold=4,
        )
        if not query:
            return None

        entries = self._active_entries()
        if not entries:
            return None

        ranked = self._rank_entries(entries, query=query)
        if not ranked:
            return None

        selected = ranked[: self.top_k]
        primary_skill_name = _clean_text(getattr(selected[0][0], "name", None)) if selected else ""
        lines: list[str] = [
            (
                f"Primary suggested skill for this request: `{primary_skill_name}`. "
                f"Call `get_skill(skill_name=\"{primary_skill_name}\")` before relying on it."
                if primary_skill_name
                else "If one of these skills is relevant, call `get_skill(skill_name)` before relying on it."
            ),
            "If one of these skills is relevant, call `get_skill(skill_name)` before relying on it.",
            "For clearly skill-shaped requests, `get_skill(...)` should usually come before `bash`, `read_file`, or other exploratory tools.",
            "If the task spans multiple domains, load multiple relevant skills instead of forcing one skill to cover everything.",
            "Do not merely mention a skill name from metadata; load the skill first.",
            "",
        ]
        skill_names: list[str] = []
        for index, (entry, _score) in enumerate(selected, start=1):
            skill_name = _clean_text(getattr(entry, "name", None))
            if skill_name:
                skill_names.append(skill_name)
            description = _truncate_text(
                getattr(entry, "description", ""),
                limit=self.max_description_chars,
            )
            source = _clean_text(getattr(getattr(entry, "source", None), "value", None) or getattr(entry, "source", None))
            details: list[str] = []
            if source:
                details.append(source)
            if bool(getattr(entry, "always", False)):
                details.append("always")
            label = f" [{', '.join(details)}]" if details else ""
            lines.append(f"{index}. `{skill_name}`{label} {description}".rstrip())

        return TurnContextItem(
            source=self.name,
            title="Relevant skills",
            content="\n".join(lines),
            metadata={
                "query": query,
                "returned": len(selected),
                "skills": skill_names,
                "ranking_score": _normalize_text_relevance_score(selected[0][1]),
                "ranking_score_raw": round(float(selected[0][1]), 6),
                "ranking_basis": "skill_catalog_match",
            },
        )

    def _list_entries(self) -> list[Any]:
        if self._cached_entries is not None:
            return list(self._cached_entries)

        from mini_agent.agent_core.skills.loader import AgentSkillLoader

        self._loader = AgentSkillLoader(
            builtin_dir=self.builtin_dir,
            workspace_dir=self.workspace_dir,
            plugin_dirs=self.plugin_dirs,
        )
        try:
            self._cached_entries = list(self._loader.discover())
        except Exception:
            self._cached_entries = []
        return list(self._cached_entries)

    def _active_entries(self) -> list[Any]:
        from mini_agent.agent_core.skills.policy import (
            WorkspaceSkillPolicyStore,
            compute_active_skill_names,
        )

        entries = self._list_entries()
        if not entries:
            return []
        policy_store = self.policy_store
        if policy_store is None and self.workspace_dir is not None:
            policy_store = WorkspaceSkillPolicyStore(self.workspace_dir)
            self.policy_store = policy_store
        active_names = compute_active_skill_names(
            entries,
            policy_store.load() if policy_store is not None else None,
        )
        return [
            entry
            for entry in entries
            if _clean_text(getattr(entry, "name", None)) in active_names
        ]

    def _rank_entries(
        self,
        entries: list[Any],
        *,
        query: str,
    ) -> list[tuple[Any, float]]:
        query_text = _clean_text(query)
        query_tokens = _tokenize(query_text)
        if not query_text:
            return []

        is_catalog_query = any(
            token in {"skill", "skills", "workflow", "template", "reference"}
            for token in query_tokens
        )
        ranked: list[tuple[Any, float]] = []
        for entry in entries:
            haystack = _skill_match_haystack(entry)
            score = _score_text_match(
                query_text=query_text,
                query_tokens=query_tokens,
                haystack=haystack,
            )
            score += _skill_metadata_match_bonus(entry, query_text)
            if bool(getattr(entry, "always", False)):
                score += 0.25
            if score <= 0.0 and not is_catalog_query:
                continue
            ranked.append((entry, round(score, 6)))

        ranked.sort(
            key=lambda item: (
                -item[1],
                _clean_text(getattr(item[0], "name", None)).lower(),
            ),
        )
        return ranked


class MCPToolCatalogTurnContextProvider:
    """Prepare lightweight MCP capability hints for one turn."""

    name = "mcp_catalog"

    def __init__(
        self,
        *,
        top_k_servers: int = 2,
        top_k_tools: int = 4,
        max_tool_name_chars: int = 48,
    ) -> None:
        self.top_k_servers = max(1, int(top_k_servers))
        self.top_k_tools = max(1, int(top_k_tools))
        self.max_tool_name_chars = max(16, int(max_tool_name_chars))

    async def describe_readiness(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any]:
        _ = (turn_context, agent)
        from mini_agent.tools.mcp.lifecycle import get_registered_connections

        connections = [
            item
            for item in get_registered_connections()
            if getattr(item, "tools", None)
        ]
        if not connections:
            return {
                "status": "unavailable",
                "available": False,
                "reason": "no active MCP connections with exposed tools",
            }
        tool_count = sum(len(list(getattr(item, "tools", []) or [])) for item in connections)
        return {
            "status": "ready",
            "available": True,
            "reason": f"{len(connections)} server(s), {tool_count} tool(s) available",
        }

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        from mini_agent.tools.mcp.lifecycle import get_registered_connections

        query = _resolve_followup_query(
            turn_context=turn_context,
            agent=agent,
            short_query_token_threshold=4,
        )
        if not query:
            return None

        connections = [
            item
            for item in get_registered_connections()
            if getattr(item, "tools", None)
        ]
        if not connections:
            return None

        ranked = self._rank_connections(connections, query=query)
        if not ranked:
            return None

        selected = ranked[: self.top_k_servers]
        lines: list[str] = []
        server_names: list[str] = []
        for index, (connection, matched_tools, _score) in enumerate(selected, start=1):
            server_name = _clean_text(getattr(connection, "name", None)) or f"server-{index}"
            server_names.append(server_name)
            connection_type = _clean_text(getattr(connection, "connection_type", None)) or "stdio"
            chosen_tools = matched_tools[: self.top_k_tools]
            if not chosen_tools:
                chosen_tools = list(getattr(connection, "tools", []) or [])[: self.top_k_tools]
            tool_names = [
                _truncate_text(_mcp_tool_label(tool), limit=self.max_tool_name_chars)
                for tool in chosen_tools
                if _mcp_tool_label(tool)
            ]
            tool_label = ", ".join(tool_names) if tool_names else "no exposed tools"
            lines.append(f"{index}. `{server_name}` [{connection_type}] tools: {tool_label}")

        return TurnContextItem(
            source=self.name,
            title="Relevant MCP capabilities",
            content="\n".join(lines),
            metadata={
                "query": query,
                "returned": len(selected),
                "active_server_count": len(connections),
                "servers": server_names,
                "ranking_score": _normalize_text_relevance_score(selected[0][2]),
                "ranking_score_raw": round(float(selected[0][2]), 6),
                "ranking_basis": "mcp_catalog_match",
            },
        )

    def _rank_connections(
        self,
        connections: list[Any],
        *,
        query: str,
    ) -> list[tuple[Any, list[Any], float]]:
        query_text = _clean_text(query)
        query_tokens = _tokenize(query_text)
        if not query_text:
            return []

        is_catalog_query = any(
            token in {
                "mcp",
                "server",
                "servers",
                "tool",
                "tools",
                "resource",
                "resources",
                "capability",
                "capabilities",
            }
            for token in query_tokens
        )
        ranked: list[tuple[Any, list[Any], float]] = []
        for connection in connections:
            header = " ".join(
                [
                    _clean_text(getattr(connection, "name", None)),
                    _clean_text(getattr(connection, "connection_type", None)),
                ]
            )
            server_score = _score_text_match(
                query_text=query_text,
                query_tokens=query_tokens,
                haystack=header,
            )

            matched_tools: list[tuple[Any, float]] = []
            for tool in list(getattr(connection, "tools", []) or []):
                tool_score = _score_text_match(
                    query_text=query_text,
                    query_tokens=query_tokens,
                    haystack=" ".join(
                        [
                            _clean_text(getattr(tool, "name", None)),
                            _clean_text(
                                getattr(tool, "remote_name", None)
                                or getattr(tool, "raw_name", None)
                            ),
                            _clean_text(getattr(tool, "description", None)),
                        ]
                    ),
                )
                if tool_score > 0.0:
                    matched_tools.append((tool, tool_score))

            matched_tools.sort(
                key=lambda item: (
                    -item[1],
                    _clean_text(getattr(item[0], "name", None)).lower(),
                ),
            )
            top_tool_score = matched_tools[0][1] if matched_tools else 0.0
            total_score = round(server_score + (top_tool_score * 1.5), 6)
            if total_score <= 0.0 and not is_catalog_query:
                continue

            ranked.append(
                (
                    connection,
                    [item[0] for item in matched_tools],
                    total_score,
                )
            )

        ranked.sort(
            key=lambda item: (
                -item[2],
                _clean_text(getattr(item[0], "name", None)).lower(),
            ),
        )
        return ranked


__all__ = [
    "ConsolidatedMemoryTurnContextProvider",
    "MCPToolCatalogTurnContextProvider",
    "RuntimeRecoveryTurnContextProvider",
    "RuntimeTaskMemoryTurnContextProvider",
    "RuntimeTurnContext",
    "SessionSearchTurnContextProvider",
    "SkillCatalogTurnContextProvider",
    "TurnContextItem",
    "TurnContextProvider",
    "UserProfileTurnContextProvider",
    "WorkspaceMemoryContextProvider",
    "context_policy_summary_line",
    "curate_turn_context_items",
    "coerce_runtime_turn_context",
    "format_context_policy_details",
    "format_prepared_context_diagnostics",
    "format_prepared_turn_context_details",
    "format_turn_context_block",
    "normalize_turn_context_items",
    "prepared_context_diagnostics_summary_line",
    "provider_allowed_by_policy",
    "prepared_turn_context_summary_line",
    "resolve_turn_context_policy",
    "summarize_turn_context_items",
    "update_prepared_context_diagnostics",
]
