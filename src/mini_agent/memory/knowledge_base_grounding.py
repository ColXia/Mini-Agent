from __future__ import annotations

import re
from typing import Any


_KB_QUERY_RE = re.compile(r"^- query:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_KB_ID_RE = re.compile(r"^- knowledge_base_id:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_KB_HITS_RE = re.compile(r"^- hits:\s*(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
_KB_RESULT_RE = re.compile(r"^\d+\.\s+\[(.+?)\]\s+(.+?)\s*$", re.MULTILINE)
_KB_CITATION_RE = re.compile(r"citation:\s*(.+?)(?:\s+\|\s+score=|$)", re.IGNORECASE)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalize_ref_list(values: list[str], *, limit: int = 3) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    bounded_limit = max(1, int(limit))
    for value in values:
        cleaned = _clean_text(value)
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        seen.add(lowered)
        refs.append(cleaned)
        if len(refs) >= bounded_limit:
            break
    return refs


def extract_knowledge_base_grounding_from_turn_messages(
    turn_messages: list[Any] | None,
    *,
    max_refs: int = 3,
) -> dict[str, Any]:
    tool_outputs: list[str] = []
    for message in list(turn_messages or []):
        role = _clean_text(getattr(message, "role", "")).lower()
        if role != "tool":
            continue
        tool_name = _clean_text(getattr(message, "name", "")).lower()
        if tool_name != "knowledge_base_query":
            continue
        content = getattr(message, "content", "")
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        text = str(content or "")
        if text.strip():
            tool_outputs.append(text)

    if not tool_outputs:
        return {
            "used": False,
            "grounded": False,
            "query": "",
            "knowledge_base_id": "",
            "hits": 0,
            "refs": [],
        }

    merged = "\n".join(tool_outputs)
    query_match = _KB_QUERY_RE.search(merged)
    kb_id_match = _KB_ID_RE.search(merged)
    hits_match = _KB_HITS_RE.search(merged)
    hits = int(hits_match.group(1)) if hits_match else 0

    refs: list[str] = []
    for line in merged.splitlines():
        citation_match = _KB_CITATION_RE.search(line)
        if citation_match:
            refs.append(citation_match.group(1))
    if not refs:
        refs.extend(match.group(1) for match in _KB_RESULT_RE.finditer(merged))

    grounded = "Knowledge base results:" in merged and hits > 0
    return {
        "used": True,
        "grounded": grounded,
        "query": _clean_text(query_match.group(1)) if query_match else "",
        "knowledge_base_id": _clean_text(kb_id_match.group(1)) if kb_id_match else "",
        "hits": hits,
        "refs": _normalize_ref_list(refs, limit=max_refs),
    }


def extract_knowledge_base_grounding_from_prepared_context(
    prepared_context: dict[str, Any] | None,
    *,
    max_refs: int = 3,
) -> dict[str, Any]:
    payload = prepared_context if isinstance(prepared_context, dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    kb_items = [
        dict(item)
        for item in items
        if isinstance(item, dict) and _clean_text(item.get("source")).lower() == "knowledge_base"
    ]
    sources = [
        _clean_text(item).lower()
        for item in (payload.get("sources") or [])
        if _clean_text(item)
    ]
    if not kb_items and "knowledge_base" not in sources:
        return {
            "used": False,
            "grounded": False,
            "query": "",
            "knowledge_base_id": "",
            "hits": 0,
            "refs": [],
        }

    first_metadata = (
        dict(kb_items[0].get("metadata"))
        if kb_items and isinstance(kb_items[0].get("metadata"), dict)
        else {}
    )
    refs: list[str] = []
    for item in kb_items:
        metadata = dict(item.get("metadata")) if isinstance(item.get("metadata"), dict) else {}
        refs.append(
            _clean_text(
                metadata.get("source_path")
                or metadata.get("url")
                or metadata.get("title")
                or metadata.get("source_id")
                or item.get("title")
            )
        )
    return {
        "used": True,
        "grounded": bool(kb_items),
        "query": _clean_text(first_metadata.get("query")),
        "knowledge_base_id": _clean_text(first_metadata.get("knowledge_base_id")) or "default",
        "hits": len(kb_items),
        "refs": _normalize_ref_list(refs, limit=max_refs),
    }


def knowledge_base_grounding_from_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(metadata or {})
    refs = payload.get("knowledge_base_refs")
    return {
        "used": bool(payload.get("knowledge_base_grounded") or payload.get("knowledge_base_used")),
        "grounded": bool(payload.get("knowledge_base_grounded")),
        "query": _clean_text(payload.get("knowledge_base_query")),
        "knowledge_base_id": _clean_text(payload.get("knowledge_base_id")),
        "hits": max(0, int(payload.get("knowledge_base_hits") or 0)),
        "refs": [
            _clean_text(item)
            for item in (refs if isinstance(refs, list) else [])
            if _clean_text(item)
        ],
    }


def format_knowledge_base_grounding_lines(
    grounding: dict[str, Any] | None,
    *,
    heading: str = "Knowledge Base",
) -> list[str]:
    payload = grounding if isinstance(grounding, dict) else {}
    if not bool(payload.get("used")):
        return []
    lines = [
        (
            f"{heading}: grounded"
            if bool(payload.get("grounded"))
            else f"{heading}: referenced"
        )
    ]
    query = _clean_text(payload.get("query"))
    kb_id = _clean_text(payload.get("knowledge_base_id")) or "default"
    hits = max(0, int(payload.get("hits") or 0))
    lines.append(f"- kb: {kb_id} | hits: {hits}")
    if query:
        lines.append(f"- query: {query}")
    refs = [
        _clean_text(item)
        for item in (payload.get("refs") or [])
        if _clean_text(item)
    ]
    if refs:
        lines.append(f"- refs: {'; '.join(refs)}")
    return lines


__all__ = [
    "extract_knowledge_base_grounding_from_prepared_context",
    "extract_knowledge_base_grounding_from_turn_messages",
    "format_knowledge_base_grounding_lines",
    "knowledge_base_grounding_from_metadata",
]
