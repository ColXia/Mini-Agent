"""Application-layer memory operations use cases."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

from mini_agent.interfaces.ops import (
    StudioMemoryDailyResponse,
    StudioMemoryNote,
    StudioMemorySearchResponse,
    StudioMemorySummaryResponse,
)
from mini_agent.memory.service import MemoryService
from mini_agent.tools.note_tool import MemoryNote

from .operations_path_policy import OperationsPathPolicy


_DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class MemoryOperationsUseCases:
    """Workspace memory summary/search/read flows for gateway operations."""

    def __init__(
        self,
        *,
        repo_root: Path,
        workspace_root: Path,
        path_policy: OperationsPathPolicy | None = None,
    ) -> None:
        self._path_policy = path_policy or OperationsPathPolicy(
            repo_root=repo_root,
            workspace_root=workspace_root,
        )

    def get_memory_summary(self, *, workspace_dir: str | None) -> StudioMemorySummaryResponse:
        resolved_workspace = self._path_policy.resolve_workspace_dir(workspace_dir)
        memory = MemoryService(resolved_workspace)
        summary = memory.summary()
        return StudioMemorySummaryResponse(
            workspace_dir=summary.workspace_dir,
            memory_root=summary.memory_root,
            long_term_file=summary.long_term_file,
            daily_dir=summary.daily_dir,
            daily_files=summary.daily_files,
            notes_count=summary.notes_count,
            categories=summary.categories,
        )

    def search_memory(
        self,
        *,
        query: str,
        limit: int,
        workspace_dir: str | None,
    ) -> StudioMemorySearchResponse:
        resolved_workspace = self._path_policy.resolve_workspace_dir(workspace_dir)
        memory = MemoryService(resolved_workspace)
        matches = memory.search_notes(query=query, limit=limit)
        return StudioMemorySearchResponse(
            workspace_dir=str(resolved_workspace),
            query=query,
            limit=limit,
            total=len(matches),
            items=[self._note_to_dict(memory, note) for note in matches],
        )

    def get_memory_daily(
        self,
        *,
        day: str,
        workspace_dir: str | None,
    ) -> StudioMemoryDailyResponse:
        normalized_day = self._path_policy.normalize_text(day)
        if not _DAY_PATTERN.fullmatch(normalized_day):
            raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD.")

        resolved_workspace = self._path_policy.resolve_workspace_dir(workspace_dir)
        memory = MemoryService(resolved_workspace)
        try:
            snapshot = memory.daily_snapshot(day=normalized_day)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return StudioMemoryDailyResponse(
            workspace_dir=snapshot.workspace_dir,
            day=snapshot.day,
            path=snapshot.path,
            note_count=snapshot.note_count,
            content=snapshot.content,
            items=[self._note_to_dict(memory, note) for note in snapshot.notes],
        )

    @staticmethod
    def _note_to_dict(memory: MemoryService, note: MemoryNote) -> StudioMemoryNote:
        return StudioMemoryNote(
            timestamp=note.timestamp,
            category=note.category,
            content=note.content,
            path=memory.relative_path(note.path),
        )


__all__ = ["MemoryOperationsUseCases"]
