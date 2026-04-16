"""Explicit operator-driven durable memory actions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from mini_agent.memory.knowledge_base_grounding import extract_knowledge_base_grounding_from_prepared_context
from mini_agent.memory.promotion import evaluate_durable_memory_promotion
from mini_agent.memory.service import MemoryService


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalize_sources(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        cleaned = _clean_text(item).lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def save_operator_workspace_note(
    *,
    workspace_dir: str | Path,
    content: str,
    prepared_context_sources: list[str] | None = None,
    prepared_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision = evaluate_durable_memory_promotion(content)
    if not decision.allowed:
        raise ValueError(f"operator note cannot be stored in durable memory: {decision.reason}")

    normalized_sources = _normalize_sources(prepared_context_sources)
    kb_grounding = extract_knowledge_base_grounding_from_prepared_context(prepared_context)
    category = (
        "kb_confirmed"
        if "knowledge_base" in normalized_sources or bool(kb_grounding.get("used"))
        else "operator_note"
    )
    memory = MemoryService(workspace_dir)
    memory.append_note(
        content=decision.normalized_text,
        category=category,
        scope="long_term",
        now=datetime.now(),
    )
    return {
        "saved": True,
        "target": "workspace_note",
        "category": category,
        "content": decision.normalized_text,
        "memory_file": str(memory.long_term_file),
        "prepared_context_sources": normalized_sources,
        "knowledge_base_grounding": kb_grounding if bool(kb_grounding.get("used")) else None,
    }


def save_operator_profile_fact(
    *,
    workspace_dir: str | Path,
    content: str,
) -> dict[str, Any]:
    decision = evaluate_durable_memory_promotion(content)
    if not decision.allowed:
        raise ValueError(f"operator profile fact cannot be stored in durable memory: {decision.reason}")

    memory = MemoryService(workspace_dir)
    result = memory.add_profile_fact(fact=decision.normalized_text)
    profile_snapshot = memory.profile()
    return {
        "saved": bool(result.get("changed")),
        "changed": bool(result.get("changed")),
        "target": "global_profile",
        "content": decision.normalized_text,
        "user_file": profile_snapshot.get("user_file"),
    }


__all__ = [
    "save_operator_profile_fact",
    "save_operator_workspace_note",
]
