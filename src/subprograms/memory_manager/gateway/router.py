"""Memory manager API router."""

from __future__ import annotations

from datetime import datetime
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from mini_agent.memory.service import MemoryService


router = APIRouter(prefix="/api/memory", tags=["Memory Manager"])


def _memory_root() -> str:
    return os.getenv("MINI_AGENT_MEMORY_ROOT", "./workspace")


def _memory() -> MemoryService:
    return MemoryService(_memory_root())


class MemoryAppendRequest(BaseModel):
    """Memory append request."""

    content: str = Field(min_length=1)
    category: str = Field(default="general")
    topic: str | None = None
    scope: str = Field(default="both")


@router.get("/summary")
async def memory_summary() -> dict[str, Any]:
    memory = _memory()
    summary = memory.summary()
    return {
        "status": "ok",
        "memory_root": summary.memory_root,
        "long_term_file": summary.long_term_file,
        "daily_dir": summary.daily_dir,
        "daily_files": summary.daily_files,
        "notes_count": summary.notes_count,
        "categories": summary.categories,
    }


@router.post("/append")
async def memory_append(request: MemoryAppendRequest) -> dict[str, Any]:
    memory = _memory()
    scope = request.scope.strip().lower()
    if scope not in {"long_term", "daily", "both"}:
        raise HTTPException(status_code=400, detail="scope must be long_term, daily, or both.")
    now = datetime.now()
    memory.append_note(
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
    memory = _memory()
    matches = memory.search_notes(query=query, limit=limit)
    return {
        "status": "ok",
        "query": query,
        "total": len(matches),
        "items": [memory.note_to_dict(note) for note in matches],
    }


@router.get("/export")
async def memory_export(format: str = Query(default="jsonl")) -> dict[str, Any]:
    memory = _memory()
    fmt = format.strip().lower()
    try:
        payload = memory.export_notes(format=fmt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "ok",
        "format": payload["format"],
        "item_count": payload["item_count"],
        "content": payload["content"],
    }


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "memory-manager"}
