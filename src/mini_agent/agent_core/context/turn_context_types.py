"""Shared turn-context types and low-level normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
from typing import Any, Protocol, runtime_checkable

from mini_agent.tools.mcp.naming import format_mcp_tool_label


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\-\u4e00-\u9fff]+")
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
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


__all__ = [
    "RuntimeTurnContext",
    "TurnContextItem",
    "TurnContextProvider",
    "coerce_runtime_turn_context",
    "normalize_turn_context_items",
]
