"""Promotion-policy helpers for durable memory writes."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


_URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)
_JSON_HINT_PATTERN = re.compile(r'"(?:content|source|chunk|score|citation|citations|document_id)"\s*:')
_RAW_KB_HINTS = (
    "knowledge base",
    "knowledge_base",
    "kb result",
    "citation",
    "citations",
    "source:",
    "sources:",
    "chunk",
    "document:",
    "document_id",
    "score:",
    "retrieved from",
)
_RUNTIME_SHARED_SCOPE_HINTS = (
    "workspace",
    "project",
    "repo",
    "repository",
    "session",
    "shared session",
    "gateway",
    "runtime",
    "tui",
    "cli",
    "qq",
    "memory",
    "rag",
    "knowledge base",
    "knowledge_base",
    "model",
    "provider",
    "workflow",
    "mcp",
    "tool",
    "approval",
    "context",
    "recovery",
)
_RUNTIME_SHARED_RULE_HINTS = (
    "prefer",
    "default",
    "defaults",
    "should",
    "must",
    "keep",
    "keeps",
    "use",
    "uses",
    "reuse",
    "avoid",
    "route",
    "routes",
    "persist",
    "persists",
    "support",
    "supports",
    "shared",
    "global",
    "local",
    "enabled",
    "disabled",
    "through",
    "via",
)


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True)
class PromotionDecision:
    allowed: bool
    reason: str
    normalized_text: str


def is_raw_knowledge_base_payload(
    text: str,
    *,
    role: str = "",
    tool_name: str = "",
) -> bool:
    normalized = _clean_text(text)
    lowered = normalized.lower()
    normalized_role = _clean_text(role).lower()
    normalized_tool_name = _clean_text(tool_name).lower()

    if not normalized:
        return False

    if normalized_role == "tool" and any(
        token in normalized_tool_name
        for token in ("knowledge_base", "kb", "rag", "maxkb")
    ):
        return True

    hint_count = sum(1 for token in _RAW_KB_HINTS if token in lowered)
    if hint_count >= 3:
        return True
    if hint_count >= 1 and _URL_PATTERN.search(normalized):
        return True
    if _JSON_HINT_PATTERN.search(normalized):
        return True
    return False


def evaluate_durable_memory_promotion(
    text: str,
    *,
    role: str = "",
    tool_name: str = "",
    min_chars: int = 8,
    max_chars: int = 280,
) -> PromotionDecision:
    normalized = _clean_text(text)
    normalized_role = _clean_text(role).lower()
    normalized_tool_name = _clean_text(tool_name).lower()

    if len(normalized) < max(1, int(min_chars)):
        return PromotionDecision(False, "too_short", normalized)
    if len(normalized) > max(32, int(max_chars)):
        return PromotionDecision(False, "too_long", normalized)
    if normalized_role == "tool":
        return PromotionDecision(False, "tool_output_not_promoted", normalized)
    if "```" in normalized:
        return PromotionDecision(False, "code_block_not_promoted", normalized)
    if is_raw_knowledge_base_payload(
        normalized,
        role=normalized_role,
        tool_name=normalized_tool_name,
    ):
        return PromotionDecision(False, "raw_knowledge_base_payload", normalized)
    return PromotionDecision(True, "", normalized)


def extract_workspace_shared_candidate_text(text: str) -> str:
    normalized = _clean_text(text)
    if not normalized:
        return ""

    lowered = normalized.lower()
    latest_marker = "| latest:"
    marker_index = lowered.find(latest_marker)
    if marker_index < 0:
        return normalized

    candidate = normalized[marker_index + len(latest_marker) :].strip()
    tool_marker_index = candidate.lower().find("| tools=")
    if tool_marker_index >= 0:
        candidate = candidate[:tool_marker_index].strip()
    return _clean_text(candidate)


def has_workspace_shared_scope_signal(text: str) -> bool:
    normalized = _clean_text(text).lower()
    if not normalized:
        return False
    return any(token in normalized for token in _RUNTIME_SHARED_SCOPE_HINTS)


def evaluate_workspace_shared_runtime_promotion(
    text: str,
    *,
    role: str = "",
    tool_name: str = "",
    min_chars: int = 18,
    max_chars: int = 220,
) -> PromotionDecision:
    candidate = extract_workspace_shared_candidate_text(text)
    normalized_role = _clean_text(role).lower()
    normalized_tool_name = _clean_text(tool_name).lower()

    if len(candidate) < max(1, int(min_chars)):
        return PromotionDecision(False, "too_short", candidate)
    if len(candidate) > max(32, int(max_chars)):
        return PromotionDecision(False, "too_long", candidate)
    if "```" in candidate:
        return PromotionDecision(False, "code_block_not_promoted", candidate)
    if normalized_role == "tool":
        return PromotionDecision(False, "tool_output_not_promoted", candidate)
    if is_raw_knowledge_base_payload(candidate, role=normalized_role, tool_name=normalized_tool_name):
        return PromotionDecision(False, "raw_knowledge_base_payload", candidate)

    lowered = candidate.lower()
    if not has_workspace_shared_scope_signal(candidate):
        return PromotionDecision(False, "missing_workspace_scope_signal", candidate)
    if not any(token in lowered for token in _RUNTIME_SHARED_RULE_HINTS):
        return PromotionDecision(False, "missing_workspace_rule_signal", candidate)
    return PromotionDecision(True, "", candidate)


def filter_promotable_memory_candidates(
    candidates: Iterable[str],
    *,
    role: str = "",
    tool_name: str = "",
    min_chars: int = 8,
    max_chars: int = 280,
) -> list[str]:
    accepted: list[str] = []
    for candidate in candidates:
        decision = evaluate_durable_memory_promotion(
            candidate,
            role=role,
            tool_name=tool_name,
            min_chars=min_chars,
            max_chars=max_chars,
        )
        if decision.allowed:
            accepted.append(decision.normalized_text)
    return accepted


__all__ = [
    "PromotionDecision",
    "evaluate_workspace_shared_runtime_promotion",
    "evaluate_durable_memory_promotion",
    "extract_workspace_shared_candidate_text",
    "filter_promotable_memory_candidates",
    "has_workspace_shared_scope_signal",
    "is_raw_knowledge_base_payload",
]
