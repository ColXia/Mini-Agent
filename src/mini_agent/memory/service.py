"""Unified workspace-scoped memory service."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from mini_agent.memory.builtin_memory import BuiltinMemoryProvider
from mini_agent.memory.consolidation import MemoryConsolidationPipeline
from mini_agent.memory.memory_files import resolve_workspace_memory_layout, resolve_workspace_root
from mini_agent.memory.paths import resolve_global_memory_dir
from mini_agent.memory.relevance import ConsolidatedMemoryRelevanceRetriever
from mini_agent.session.persistence import SessionPersistence
from mini_agent.tools.note_tool import MarkdownMemoryStore, MemoryNote


_DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\-\u4e00-\u9fff]+")


@dataclass(frozen=True)
class MemorySummarySnapshot:
    workspace_dir: str
    memory_root: str
    long_term_file: str
    daily_dir: str
    daily_files: list[str]
    notes_count: int
    categories: list[str]


@dataclass(frozen=True)
class MemoryDailySnapshot:
    workspace_dir: str
    day: str
    path: str
    note_count: int
    content: str
    notes: list[MemoryNote]


class MemoryService:
    """Single entry point for existing workspace memory capabilities."""

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        session_store_dir: str | Path | None = None,
        global_memory_root: str | Path | None = None,
    ) -> None:
        self.workspace_dir = resolve_workspace_root(workspace_dir)
        self.layout = resolve_workspace_memory_layout(self.workspace_dir)
        self.note_store = MarkdownMemoryStore(memory_root=str(self.workspace_dir))
        self.global_memory_root = resolve_global_memory_dir(global_memory_root)
        self._session_store_dir = (
            Path(session_store_dir).expanduser().resolve()
            if session_store_dir is not None
            else None
        )
        self._session_persistence: SessionPersistence | None = None
        self._global_profile_provider: BuiltinMemoryProvider | None = None
        self._workspace_profile_provider: BuiltinMemoryProvider | None = None

    @property
    def memory_root(self) -> Path:
        return self.note_store.memory_root

    @property
    def anchor_dir(self) -> Path:
        return self.layout.anchor_dir

    @property
    def long_term_file(self) -> Path:
        return self.note_store.long_term_file

    @property
    def daily_dir(self) -> Path:
        return self.note_store.daily_dir

    def summary(self) -> MemorySummarySnapshot:
        notes = self.load_notes()
        return MemorySummarySnapshot(
            workspace_dir=str(self.workspace_dir),
            memory_root=str(self.memory_root),
            long_term_file=str(self.long_term_file),
            daily_dir=str(self.daily_dir),
            daily_files=sorted(path.name for path in self.daily_dir.glob("*.md")),
            notes_count=len(notes),
            categories=sorted({note.category for note in notes}),
        )

    def load_notes(self) -> list[MemoryNote]:
        return self.note_store.load_notes()

    def append_note(
        self,
        *,
        content: str,
        category: str,
        scope: str,
        now: datetime,
        topic: str | None = None,
    ) -> None:
        self.note_store.append_note(
            content=content,
            category=category,
            scope=scope,
            now=now,
            topic=topic,
        )

    def search_notes(
        self,
        *,
        query: str,
        limit: int = 20,
    ) -> list[MemoryNote]:
        bounded_limit = max(1, min(int(limit), 200))
        notes = self.load_notes()
        if not query.strip():
            notes.sort(key=self.note_sort_key, reverse=True)
            return notes[:bounded_limit]
        ranked = self.rank_workspace_notes(query=query)
        return [note for note, _score in ranked[:bounded_limit]]

    def rank_workspace_notes(self, *, query: str) -> list[tuple[MemoryNote, float]]:
        query_text = query.strip().lower()
        query_tokens = set(self._tokenize(query_text))
        if not query_text or not query_tokens:
            return []

        ranked: list[tuple[MemoryNote, float]] = []
        for note in self.load_notes():
            haystack = f"{note.category} {note.content}".lower()
            score = 0.0
            if query_text in haystack:
                score += 4.0
            note_tokens = set(self._tokenize(haystack))
            overlap = len(query_tokens & note_tokens)
            if overlap <= 0 and score <= 0.0:
                continue
            score += overlap * 1.5
            score += float(overlap) / float(max(1, len(query_tokens)))

            note_dt = self._parse_optional_dt(note.timestamp)
            if note_dt is not None:
                age_days = max(0.0, (datetime.now(note_dt.tzinfo) - note_dt).total_seconds() / 86400.0)
                score += 1.0 / (1.0 + age_days)

            ranked.append((note, round(score, 6)))

        ranked.sort(
            key=lambda item: (
                -item[1],
                item[0].timestamp,
                item[0].content,
            ),
            reverse=False,
        )
        return ranked

    def daily_snapshot(self, *, day: str) -> MemoryDailySnapshot:
        normalized_day = " ".join(str(day or "").split())
        if not _DAY_PATTERN.fullmatch(normalized_day):
            raise ValueError("day must be YYYY-MM-DD.")

        daily_path = self.daily_dir / f"{normalized_day}.md"
        if not daily_path.exists():
            raise FileNotFoundError(f"daily memory file not found: {normalized_day}")

        content = daily_path.read_text(encoding="utf-8")
        notes = [note for note in self.load_notes() if note.path.resolve() == daily_path.resolve()]
        notes.sort(key=self.note_sort_key, reverse=True)
        return MemoryDailySnapshot(
            workspace_dir=str(self.workspace_dir),
            day=normalized_day,
            path=str(daily_path),
            note_count=len(notes),
            content=content,
            notes=notes,
        )

    def export_notes(self, *, format: str = "jsonl") -> dict[str, Any]:
        normalized_format = str(format or "").strip().lower()
        if normalized_format not in {"jsonl", "markdown"}:
            raise ValueError("format must be jsonl or markdown.")

        notes = self.load_notes()
        if normalized_format == "jsonl":
            content = "\n".join(
                json.dumps(self.note_to_dict(note), ensure_ascii=False)
                for note in notes
            )
        else:
            grouped: dict[str, list[MemoryNote]] = defaultdict(list)
            for note in notes:
                grouped[self.relative_path(note.path)].append(note)
            sections: list[str] = []
            for rel_path in sorted(grouped):
                sections.append(f"## {rel_path}")
                for note in grouped[rel_path]:
                    sections.append(f"- [{note.timestamp}] [{note.category}] {note.content}")
                sections.append("")
            content = "\n".join(sections).strip()
        return {
            "format": normalized_format,
            "item_count": len(notes),
            "content": content,
        }

    def profile(self) -> dict[str, Any]:
        return self._global_profile_store().profile()

    def workspace_profile(self) -> dict[str, Any]:
        return self._workspace_profile_store().profile()

    def search_profile(self, *, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return self._global_profile_store().search(query=query, limit=limit)

    def search_workspace_profile(self, *, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return self._workspace_profile_store().search(query=query, limit=limit)

    def add_profile_fact(self, *, fact: str) -> dict[str, Any]:
        return self._global_profile_store().add_fact(fact=fact)

    def add_workspace_profile_fact(self, *, fact: str) -> dict[str, Any]:
        return self._workspace_profile_store().add_fact(fact=fact)

    def replace_profile_fact(self, *, match: str, fact: str) -> dict[str, Any]:
        return self._global_profile_store().replace_fact(match=match, fact=fact)

    def replace_workspace_profile_fact(self, *, match: str, fact: str) -> dict[str, Any]:
        return self._workspace_profile_store().replace_fact(match=match, fact=fact)

    def remove_profile_fact(self, *, match: str) -> dict[str, Any]:
        return self._global_profile_store().remove_fact(match=match)

    def remove_workspace_profile_fact(self, *, match: str) -> dict[str, Any]:
        return self._workspace_profile_store().remove_fact(match=match)

    def search_sessions(
        self,
        *,
        query: str,
        limit: int = 20,
        session_id: str | None = None,
        workspace_anchor_dir: str | None = None,
        exclude_session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._session_store().search_sessions(
            query=query,
            limit=limit,
            session_id=session_id,
            workspace_anchor_dir=workspace_anchor_dir,
            exclude_session_id=exclude_session_id,
        )

    def session_search_stats(self) -> dict[str, Any]:
        return self._session_store().session_search_stats()

    def consolidated_snapshot(
        self,
        *,
        memory_file: str | Path | None = None,
    ) -> dict[str, Any]:
        snapshot = ConsolidatedMemoryRelevanceRetriever(self._resolve_memory_file(memory_file)).load_snapshot()
        return {
            "items": list(snapshot.items),
            "memory_last_updated_utc": snapshot.memory_last_updated_utc,
            "memory_file_mtime_utc": snapshot.memory_file_mtime_utc,
        }

    def consolidated_refresh_status(
        self,
        *,
        memory_file: str | Path | None = None,
        exclude_session_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_memory_file = self._resolve_memory_file(memory_file)
        snapshot = ConsolidatedMemoryRelevanceRetriever(resolved_memory_file).load_snapshot()
        workspace_sessions = self._workspace_session_records(exclude_session_id=exclude_session_id)
        latest_workspace_session_updated_utc = (
            workspace_sessions[0].get("updated_at")
            if workspace_sessions
            else None
        )
        memory_last_updated = (
            self._parse_optional_dt(snapshot.memory_last_updated_utc)
            or self._parse_optional_dt(snapshot.memory_file_mtime_utc)
        )
        latest_session_updated = self._parse_optional_dt(latest_workspace_session_updated_utc)
        has_section = self._has_consolidated_memory_section(resolved_memory_file)

        if not workspace_sessions:
            reason = "no_workspace_sessions_available"
            needs_refresh = False
        elif not has_section:
            reason = "missing_consolidated_section"
            needs_refresh = True
        elif latest_session_updated is not None and memory_last_updated is None:
            reason = "missing_consolidated_timestamp"
            needs_refresh = True
        elif (
            latest_session_updated is not None
            and memory_last_updated is not None
            and latest_session_updated > memory_last_updated
        ):
            reason = "workspace_session_history_newer_than_consolidated_memory"
            needs_refresh = True
        else:
            reason = "fresh"
            needs_refresh = False

        pending_session_count = 0
        if needs_refresh and latest_session_updated is not None and memory_last_updated is not None:
            pending_session_count = sum(
                1
                for session in workspace_sessions
                if (
                    self._parse_optional_dt(session.get("updated_at"))
                    and self._parse_optional_dt(session.get("updated_at")) > memory_last_updated
                )
            )
        elif needs_refresh and workspace_sessions:
            pending_session_count = len(workspace_sessions)

        return {
            "workspace_dir": str(self.workspace_dir),
            "workspace_anchor_dir": str(self.anchor_dir),
            "session_store_dir": str(self._session_store().base_dir),
            "memory_file": str(resolved_memory_file),
            "has_consolidated_section": has_section,
            "consolidated_item_count": len(snapshot.items),
            "memory_last_updated_utc": snapshot.memory_last_updated_utc,
            "memory_file_mtime_utc": snapshot.memory_file_mtime_utc,
            "workspace_session_count": len(workspace_sessions),
            "latest_workspace_session_updated_utc": latest_workspace_session_updated_utc,
            "pending_session_count": pending_session_count,
            "needs_refresh": needs_refresh,
            "reason": reason,
            "excluded_session_id": str(exclude_session_id or "").strip() or None,
        }

    def refresh_consolidated_memory(
        self,
        *,
        force: bool = False,
        max_jobs: int = 8,
        lease_seconds: int = 3600,
        retry_seconds: int = 3600,
        top_n: int = 40,
        memory_file: str | Path | None = None,
        exclude_session_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_memory_file = self._resolve_memory_file(memory_file)
        before = self.consolidated_refresh_status(
            memory_file=resolved_memory_file,
            exclude_session_id=exclude_session_id,
        )

        if not force and not bool(before.get("needs_refresh")):
            return {
                "refreshed": False,
                "forced": False,
                "skipped": True,
                "reason": str(before.get("reason") or "fresh"),
                "summary": None,
                "before": before,
                "after": before,
            }

        pipeline = MemoryConsolidationPipeline(
            session_store_dir=self._session_store().base_dir,
            workspace_anchor_dir=self.anchor_dir,
            memory_file=resolved_memory_file,
            workspace_dir=self.anchor_dir,
        )
        summary = pipeline.run(
            phase="all",
            max_jobs=max_jobs,
            lease_seconds=lease_seconds,
            retry_seconds=retry_seconds,
            top_n=top_n,
            exclude_session_id=exclude_session_id,
        )
        after = self.consolidated_refresh_status(
            memory_file=resolved_memory_file,
            exclude_session_id=exclude_session_id,
        )
        return {
            "refreshed": True,
            "forced": bool(force),
            "skipped": False,
            "reason": "forced" if force else str(before.get("reason") or "refresh_requested"),
            "summary": summary,
            "before": before,
            "after": after,
        }

    def search_relevant_consolidated_memory(
        self,
        *,
        query: str,
        top_k: int = 5,
        stale_after_days: int = 30,
        use_session_search_support: bool = False,
        memory_file: str | Path | None = None,
        support_lookup: Any | None = None,
    ) -> dict[str, Any]:
        resolved_memory_file = self._resolve_memory_file(memory_file)
        if use_session_search_support:
            return self._session_store().search_relevant_memory(
                query=query,
                memory_file=resolved_memory_file,
                top_k=top_k,
                stale_after_days=stale_after_days,
                workspace_anchor_dir=str(self.anchor_dir),
            )
        return ConsolidatedMemoryRelevanceRetriever(resolved_memory_file).search(
            query=query,
            top_k=top_k,
            stale_after_days=stale_after_days,
            support_lookup=support_lookup,
        )

    def note_to_dict(self, note: MemoryNote) -> dict[str, Any]:
        return {
            "timestamp": note.timestamp,
            "category": note.category,
            "content": note.content,
            "path": self.relative_path(note.path),
        }

    def relative_path(self, path: Path) -> str:
        return self.note_store.relative_path(path)

    @staticmethod
    def note_sort_key(note: MemoryNote) -> datetime:
        try:
            return datetime.fromisoformat(note.timestamp)
        except Exception:
            return datetime.min

    def _session_store(self) -> SessionPersistence:
        if self._session_persistence is None:
            self._session_persistence = SessionPersistence(self._session_store_dir)
        return self._session_persistence

    def _global_profile_store(self) -> BuiltinMemoryProvider:
        if self._global_profile_provider is None:
            self._global_profile_provider = BuiltinMemoryProvider(
                workspace_root=self.workspace_dir,
                profile_scope="global",
                global_root=self.global_memory_root,
            )
        return self._global_profile_provider

    def _workspace_profile_store(self) -> BuiltinMemoryProvider:
        if self._workspace_profile_provider is None:
            self._workspace_profile_provider = BuiltinMemoryProvider(
                workspace_root=self.workspace_dir,
                profile_scope="workspace",
            )
        return self._workspace_profile_provider

    def _resolve_memory_file(self, memory_file: str | Path | None) -> Path:
        if memory_file is None:
            return self.long_term_file
        return Path(memory_file).expanduser().resolve()

    def _workspace_session_records(
        self,
        *,
        exclude_session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_excluded = str(exclude_session_id or "").strip()
        records: list[dict[str, Any]] = []
        for session in self._session_store().list_sessions():
            session_id = str(session.get("session_id", "")).strip()
            if not session_id:
                continue
            if normalized_excluded and session_id == normalized_excluded:
                continue
            workspace_dir = session.get("workspace_dir")
            if not workspace_dir:
                continue
            try:
                session_anchor_dir = resolve_workspace_root(workspace_dir)
            except Exception:
                continue
            if session_anchor_dir != self.anchor_dir:
                continue
            records.append(dict(session))
        records.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return records

    @staticmethod
    def _has_consolidated_memory_section(memory_file: Path) -> bool:
        if not memory_file.exists():
            return False
        try:
            text = memory_file.read_text(encoding="utf-8")
        except Exception:
            return False
        return (
            "MINI_AGENT_CONSOLIDATED_MEMORY_BEGIN" in text
            and "MINI_AGENT_CONSOLIDATED_MEMORY_END" in text
        )

    @staticmethod
    def _parse_optional_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token.lower() for token in _TOKEN_PATTERN.findall(text or "")]
