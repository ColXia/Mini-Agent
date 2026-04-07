"""Memory manager API router."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from mini_agent.tools.note_tool import MarkdownMemoryStore, MemoryNote


router = APIRouter(prefix="/api/memory", tags=["Memory Manager"])


def _memory_root() -> str:
    return os.getenv("MINI_AGENT_MEMORY_ROOT", "./workspace")


def _store() -> MarkdownMemoryStore:
    return MarkdownMemoryStore(memory_root=_memory_root())


def _note_to_dict(store: MarkdownMemoryStore, note: MemoryNote) -> dict[str, Any]:
    return {
        "timestamp": note.timestamp,
        "category": note.category,
        "content": note.content,
        "path": store.relative_path(note.path),
    }


def _search_notes(notes: list[MemoryNote], query: str, limit: int) -> list[MemoryNote]:
    terms = [token for token in query.lower().split() if token.strip()]
    if not terms:
        return notes[:limit]

    scored: list[tuple[int, MemoryNote]] = []
    for note in notes:
        haystack = f"{note.category} {note.content}".lower()
        score = sum(1 for token in terms if token in haystack)
        if score > 0:
            scored.append((score, note))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:limit]]


class MemoryAppendRequest(BaseModel):
    """Memory append request."""

    content: str = Field(min_length=1)
    category: str = Field(default="general")
    topic: str | None = None
    scope: str = Field(default="both")


@router.get("/summary")
async def memory_summary() -> dict[str, Any]:
    store = _store()
    notes = store.load_notes()
    daily_files = sorted(str(path.name) for path in store.daily_dir.glob("*.md"))
    categories = sorted({note.category for note in notes})
    return {
        "status": "ok",
        "memory_root": str(store.memory_root),
        "long_term_file": str(store.long_term_file),
        "daily_dir": str(store.daily_dir),
        "daily_files": daily_files,
        "notes_count": len(notes),
        "categories": categories,
    }


@router.post("/append")
async def memory_append(request: MemoryAppendRequest) -> dict[str, Any]:
    store = _store()
    scope = request.scope.strip().lower()
    if scope not in {"long_term", "daily", "both"}:
        raise HTTPException(status_code=400, detail="scope must be long_term, daily, or both.")
    now = datetime.now()
    store.append_note(
        content=request.content,
        category=request.category.strip() or "general",
        scope=scope,
        now=now,
        topic=request.topic,
    )
    return {
        "status": "ok",
        "scope": scope,
        "timestamp": now.isoformat(),
    }


@router.get("/search")
async def memory_search(query: str = Query(default="", min_length=0), limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
    store = _store()
    notes = store.load_notes()
    matches = _search_notes(notes, query=query, limit=limit)
    return {
        "status": "ok",
        "query": query,
        "total": len(matches),
        "items": [_note_to_dict(store, note) for note in matches],
    }


@router.get("/export")
async def memory_export(format: str = Query(default="jsonl")) -> dict[str, Any]:
    store = _store()
    notes = store.load_notes()
    fmt = format.strip().lower()
    if fmt not in {"jsonl", "markdown"}:
        raise HTTPException(status_code=400, detail="format must be jsonl or markdown.")

    if fmt == "jsonl":
        payload = "\n".join(json.dumps(_note_to_dict(store, note), ensure_ascii=False) for note in notes)
    else:
        grouped: dict[str, list[MemoryNote]] = defaultdict(list)
        for note in notes:
            grouped[store.relative_path(note.path)].append(note)
        sections: list[str] = []
        for rel_path in sorted(grouped):
            sections.append(f"## {rel_path}")
            for note in grouped[rel_path]:
                sections.append(f"- [{note.timestamp}] [{note.category}] {note.content}")
            sections.append("")
        payload = "\n".join(sections).strip()

    return {
        "status": "ok",
        "format": fmt,
        "item_count": len(notes),
        "content": payload,
    }


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "memory-manager"}
