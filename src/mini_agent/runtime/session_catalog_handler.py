"""Session catalog / metadata routing extracted from the runtime manager."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Sequence

from fastapi import HTTPException

from mini_agent.runtime.interaction_surface import normalize_surface_label

if TYPE_CHECKING:
    from mini_agent.interfaces import (
        MainAgentSessionDetail,
        MainAgentSessionMessage,
        MainAgentSessionSummary,
    )
    from mini_agent.runtime.session_state import (
        MainAgentSessionState,
        MainAgentSessionTranscriptEntry,
    )


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionCatalogHandler:
    same_workspace: Callable[[Path, Path], bool]
    build_session_summary: Callable[["MainAgentSessionState"], "MainAgentSessionSummary"]
    build_session_summary_from_record: Callable[[dict[str, Any]], "MainAgentSessionSummary"]
    build_session_detail: Callable[["MainAgentSessionState", int], "MainAgentSessionDetail"]
    build_session_detail_from_record: Callable[[dict[str, Any], int], "MainAgentSessionDetail"]
    build_session_message: Callable[["MainAgentSessionTranscriptEntry"], "MainAgentSessionMessage"]
    transcript_entries_from_record: Callable[[dict[str, Any]], list["MainAgentSessionTranscriptEntry"]]

    def find_latest_active_session(
        self,
        workspace_dir: Path,
        sessions: Iterable["MainAgentSessionState"],
    ) -> "MainAgentSessionState | None":
        candidates = [
            session
            for session in sessions
            if self.same_workspace(session.workspace_dir, workspace_dir)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.updated_at)

    def find_latest_persisted_record(
        self,
        workspace_dir: Path,
        records: Sequence[dict[str, Any]],
    ) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        for record in records:
            resolved_workspace = self.record_workspace_dir(record)
            if resolved_workspace is None:
                continue
            if self.same_workspace(resolved_workspace, workspace_dir):
                candidates.append(record)
        if not candidates:
            return None
        candidates.sort(key=lambda item: _safe_text(item.get("updated_at")), reverse=True)
        return dict(candidates[0])

    def allocate_session_title(
        self,
        base_title: str,
        *,
        workspace_dir: Path,
        active_sessions: Iterable["MainAgentSessionState"],
        persisted_records: Sequence[dict[str, Any]],
    ) -> str:
        normalized_base = _safe_text(base_title)
        if not normalized_base:
            return ""
        exact_taken = False
        numbered_suffixes: set[int] = set()

        def _observe_title(raw_title: object, raw_workspace: Path | None) -> None:
            nonlocal exact_taken
            title = _safe_text(raw_title)
            if not title:
                return
            if raw_workspace is not None and not self.same_workspace(raw_workspace, workspace_dir):
                return
            if title == normalized_base:
                exact_taken = True
                return
            prefix = f"{normalized_base} "
            if not title.startswith(prefix):
                return
            suffix = title[len(prefix) :].strip()
            if suffix.isdigit():
                numbered_suffixes.add(max(1, int(suffix)))

        for session in active_sessions:
            _observe_title(session.projection.title, session.workspace_dir)
        for record in persisted_records:
            _observe_title(record.get("title"), self.record_workspace_dir(record))

        if not exact_taken:
            return normalized_base
        suffix = 1
        while suffix in numbered_suffixes:
            suffix += 1
        return f"{normalized_base} {suffix}"

    def list_sessions(
        self,
        *,
        active_sessions: Iterable["MainAgentSessionState"],
        persisted_records: Sequence[dict[str, Any]],
        workspace_dir: Path | None = None,
        shared_only: bool = False,
    ) -> list["MainAgentSessionSummary"]:
        active_by_id = {
            session.session_id: self.build_session_summary(session)
            for session in active_sessions
        }
        for record in persisted_records:
            session_id = _safe_text(record.get("session_id"))
            if not session_id or session_id in active_by_id:
                continue
            active_by_id[session_id] = self.build_session_summary_from_record(record)
        sessions = list(active_by_id.values())
        if workspace_dir is not None:
            filtered: list["MainAgentSessionSummary"] = []
            for item in sessions:
                try:
                    item_workspace = Path(item.workspace_dir).expanduser().resolve()
                except Exception:
                    continue
                if self.same_workspace(item_workspace, workspace_dir):
                    filtered.append(item)
            sessions = filtered
        if shared_only:
            sessions = [item for item in sessions if bool(item.shared)]
        sessions.sort(key=lambda item: item.updated_at, reverse=True)
        return self.dedupe_session_summaries(sessions)

    @staticmethod
    def rename_session(session: "MainAgentSessionState", *, title: str) -> None:
        session.projection.title = _safe_text(title) or session.projection.title or "Session"

    @staticmethod
    def set_session_shared(session: "MainAgentSessionState", *, shared: bool) -> None:
        session.projection.shared = bool(shared)

    def get_session_detail(
        self,
        session_id: str,
        *,
        active_session: "MainAgentSessionState | None",
        persisted_record: dict[str, Any] | None,
        recent_limit: int,
    ) -> "MainAgentSessionDetail":
        if active_session is not None:
            return self.build_session_detail(active_session, recent_limit)
        if persisted_record is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        return self.build_session_detail_from_record(persisted_record, recent_limit)

    def get_recent_messages(
        self,
        session_id: str,
        *,
        active_session: "MainAgentSessionState | None",
        persisted_record: dict[str, Any] | None,
        limit: int,
    ) -> list["MainAgentSessionMessage"]:
        normalized_limit = max(1, int(limit))
        if active_session is not None:
            entries = active_session.transcript_state.transcript[-normalized_limit:]
            return [self.build_session_message(entry) for entry in entries]
        if persisted_record is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        transcript = self.transcript_entries_from_record(persisted_record)
        return [self.build_session_message(entry) for entry in transcript[-normalized_limit:]]

    @staticmethod
    def record_workspace_dir(record: dict[str, Any]) -> Path | None:
        record_workspace = _safe_text(record.get("workspace_dir"))
        if not record_workspace:
            return None
        try:
            return Path(record_workspace).expanduser().resolve()
        except Exception:
            return None

    @staticmethod
    def path_key(path: Path) -> str:
        resolved = str(path.resolve())
        return resolved.lower() if os.name == "nt" else resolved

    @classmethod
    def session_summary_dedup_key(
        cls,
        summary: "MainAgentSessionSummary",
    ) -> tuple[str, str, str, str, str] | None:
        channel = _safe_text(summary.channel_type).lower()
        conversation = _safe_text(summary.conversation_id)
        if not channel or not conversation:
            return None
        workspace_dir = _safe_text(summary.workspace_dir)
        try:
            workspace_key = cls.path_key(Path(workspace_dir).expanduser().resolve())
        except Exception:
            workspace_key = workspace_dir.lower()
        title = _safe_text(summary.title) or "<untitled>"
        origin = normalize_surface_label(summary.origin_surface)
        return workspace_key, channel, conversation, origin, title

    @classmethod
    def session_summary_conversation_key(
        cls,
        summary: "MainAgentSessionSummary",
    ) -> tuple[str, str, str] | None:
        channel = _safe_text(summary.channel_type).lower()
        conversation = _safe_text(summary.conversation_id)
        if not channel or not conversation:
            return None
        workspace_dir = _safe_text(summary.workspace_dir)
        try:
            workspace_key = cls.path_key(Path(workspace_dir).expanduser().resolve())
        except Exception:
            workspace_key = workspace_dir.lower()
        return workspace_key, channel, conversation

    @staticmethod
    def is_channel_stub_summary(summary: "MainAgentSessionSummary") -> bool:
        channel = _safe_text(summary.channel_type).lower()
        if not channel:
            return False
        title = _safe_text(summary.title)
        origin = normalize_surface_label(summary.origin_surface)
        return not title and origin == channel

    @staticmethod
    def is_interactive_shared_summary(summary: "MainAgentSessionSummary") -> bool:
        channel = _safe_text(summary.channel_type).lower()
        if not channel:
            return False
        title = _safe_text(summary.title)
        origin = normalize_surface_label(summary.origin_surface)
        return bool(title) and origin not in {"", channel}

    @classmethod
    def dedupe_session_summaries(
        cls,
        sessions: Sequence["MainAgentSessionSummary"],
    ) -> list["MainAgentSessionSummary"]:
        deduped: list["MainAgentSessionSummary"] = []
        seen_keys: set[tuple[str, str, str, str, str]] = set()
        for summary in sessions:
            key = cls.session_summary_dedup_key(summary)
            if key is not None:
                if key in seen_keys:
                    continue
                seen_keys.add(key)
            deduped.append(summary)

        grouped: dict[tuple[str, str, str], list["MainAgentSessionSummary"]] = {}
        for summary in deduped:
            key = cls.session_summary_conversation_key(summary)
            if key is None:
                continue
            grouped.setdefault(key, []).append(summary)

        filtered: list["MainAgentSessionSummary"] = []
        for summary in deduped:
            key = cls.session_summary_conversation_key(summary)
            if key is None:
                filtered.append(summary)
                continue
            siblings = grouped.get(key, [])
            if cls.is_channel_stub_summary(summary) and any(
                cls.is_interactive_shared_summary(candidate)
                for candidate in siblings
                if candidate.session_id != summary.session_id
            ):
                continue
            filtered.append(summary)
        return filtered


__all__ = [
    "RuntimeSessionCatalogHandler",
]
