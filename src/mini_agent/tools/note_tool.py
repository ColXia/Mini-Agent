"""Session note tools backed by markdown memory files.

Memory layout:
- MEMORY.md: long-term notes
- memory/YYYY-MM-DD.md: daily notes
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from mini_agent.memory.memory_files import discover_memory_layout
from mini_agent.rag.embeddings import EmbeddingProvider
from mini_agent.workspace_runtime.mutation_ledger import MutationKind
from mini_agent.workspace_runtime.workspace_executor import WorkspaceExecutor

from .base import Tool, ToolResult


_NOTE_LINE_PATTERN = re.compile(
    r"^- \[(?P<timestamp>[^\]]+)\] \[(?P<category>[^\]]+)\] (?P<content>.+)$"
)
_VALID_SCOPES = {"long_term", "daily", "both"}


@dataclass(frozen=True)
class MemoryNote:
    timestamp: str
    category: str
    content: str
    path: Path


class MarkdownMemoryStore:
    """Store and load memory notes from markdown files."""

    def __init__(
        self,
        memory_root: str = "./workspace",
        *,
        workspace_executor: WorkspaceExecutor | None = None,
    ):
        requested_root = Path(memory_root).expanduser().resolve()
        layout = discover_memory_layout(requested_root)
        self.memory_root = layout.anchor_dir
        self.workspace_root = requested_root
        self.long_term_file = layout.memory_file or (self.memory_root / "MEMORY.md")
        self.daily_dir = self.memory_root / "memory"
        self.workspace_executor = workspace_executor

    def append_note(
        self,
        content: str,
        category: str,
        scope: str,
        now: datetime,
        topic: str | None = None,
    ) -> None:
        normalized_topic = (topic or "").strip()
        content_payload = content.strip()
        if normalized_topic:
            content_payload = f"[topic:{normalized_topic}] {content_payload}"

        note_line = f"- [{now.isoformat()}] [{category}] {content_payload}"

        if scope in ("long_term", "both"):
            self._append_markdown_line(
                self.long_term_file,
                "# Long-Term Memory\n\n",
                note_line,
            )

        if scope in ("daily", "both"):
            day_file = self.daily_dir / f"{now.date().isoformat()}.md"
            self._append_markdown_line(
                day_file,
                f"# Daily Memory {now.date().isoformat()}\n\n",
                note_line,
            )

    def load_notes(self) -> list[MemoryNote]:
        notes: list[MemoryNote] = []

        notes.extend(self._parse_file(self.long_term_file))
        for daily_file in self._iter_daily_files():
            notes.extend(self._parse_file(daily_file))

        return notes

    def relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.memory_root))
        except Exception:
            return str(path)

    def _append_markdown_line(self, path: Path, header: str, note_line: str) -> None:
        if self.workspace_executor is not None:
            try:
                existing = self.workspace_executor.read_text(path, encoding="utf-8")
            except FileNotFoundError:
                existing = header
            else:
                if not existing:
                    existing = header
            separator = "" if existing.endswith(("\n", "\r")) else "\n"
            payload = f"{existing}{separator}{note_line}\n"
            self.workspace_executor.write_text(path, payload, encoding="utf-8")
            return

        path.parent.mkdir(parents=True, exist_ok=True)

        if not path.exists():
            path.write_text(f"{header}{note_line}\n", encoding="utf-8")
            return

        existing = path.read_text(encoding="utf-8")
        separator = "" if existing.endswith("\n") else "\n"
        path.write_text(f"{existing}{separator}{note_line}\n", encoding="utf-8")

    def _parse_file(self, path: Path) -> list[MemoryNote]:
        try:
            if self.workspace_executor is not None:
                content = self.workspace_executor.read_text(path, encoding="utf-8")
            else:
                content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []

        notes: list[MemoryNote] = []
        for line in content.splitlines():
            match = _NOTE_LINE_PATTERN.match(line.strip())
            if not match:
                continue

            notes.append(
                MemoryNote(
                    timestamp=match.group("timestamp"),
                    category=match.group("category"),
                    content=match.group("content"),
                    path=path,
                )
            )

        return notes

    def _iter_daily_files(self) -> list[Path]:
        if self.workspace_executor is None:
            return sorted(self.daily_dir.glob("*.md"))

        access = self.workspace_executor.resolve_access(
            self.daily_dir,
            kind=MutationKind.READ,
            detail="list workspace memory notes",
        )
        if not access.resolved_path.exists():
            return []
        return sorted(access.resolved_path.glob("*.md"))


class SessionNoteTool(Tool):
    """Tool for recording session notes in markdown memory files."""

    def __init__(
        self,
        memory_root: str = "./workspace",
        *,
        workspace_executor: WorkspaceExecutor | None = None,
    ):
        self.memory_store = MarkdownMemoryStore(
            memory_root=memory_root,
            workspace_executor=workspace_executor,
        )

    @property
    def name(self) -> str:
        return "record_note"

    @property
    def description(self) -> str:
        return (
            "Record important information into markdown memory files. "
            "Long-term memory is written to MEMORY.md and daily context is written to "
            "memory/YYYY-MM-DD.md."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Information to record.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category tag.",
                    "default": "general",
                },
                "topic": {
                    "type": "string",
                    "description": "Optional topic slug or label for grouping memories.",
                },
                "scope": {
                    "type": "string",
                    "description": "Storage scope: long_term, daily, or both.",
                    "enum": ["long_term", "daily", "both"],
                    "default": "both",
                },
            },
            "required": ["content"],
        }

    async def execute(
        self,
        content: str,
        category: str = "general",
        topic: str | None = None,
        scope: str = "both",
    ) -> ToolResult:
        try:
            normalized_scope = scope.strip().lower()
            if normalized_scope not in _VALID_SCOPES:
                return ToolResult(
                    success=False,
                    content="",
                    error="Invalid scope. Use one of: long_term, daily, both.",
                )

            self.memory_store.append_note(
                content=content,
                category=category,
                scope=normalized_scope,
                now=datetime.now(),
                topic=topic,
            )

            topic_suffix = ""
            if topic and topic.strip():
                topic_suffix = f" (topic: {topic.strip()})"
            return ToolResult(
                success=True,
                content=(
                    f"Recorded note in {normalized_scope}: {content} "
                    f"(category: {category}){topic_suffix}"
                ),
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                content="",
                error=f"Failed to record note: {exc}",
            )


class RecallNoteTool(Tool):
    """Tool for recalling notes from markdown memory files."""

    def __init__(
        self,
        memory_root: str = "./workspace",
        embedding_provider: EmbeddingProvider | Callable[[str], list[float]] | None = None,
        *,
        workspace_executor: WorkspaceExecutor | None = None,
    ):
        self.memory_store = MarkdownMemoryStore(
            memory_root=memory_root,
            workspace_executor=workspace_executor,
        )
        self.embedding_provider = embedding_provider

    @property
    def name(self) -> str:
        return "recall_notes"

    @property
    def description(self) -> str:
        return (
            "Recall notes from MEMORY.md and memory/YYYY-MM-DD.md. "
            "Supports category filtering and hybrid keyword plus optional embedding ranking."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Optional category filter.",
                },
                "query": {
                    "type": "string",
                    "description": "Optional search query for relevance ranking.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of notes to return.",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
                "use_embedding": {
                    "type": "boolean",
                    "description": "Enable embedding ranking when provider is available.",
                    "default": True,
                },
            },
        }

    async def execute(
        self,
        category: str | None = None,
        query: str | None = None,
        limit: int = 20,
        use_embedding: bool = True,
    ) -> ToolResult:
        try:
            notes = self.memory_store.load_notes()
            if not notes:
                return ToolResult(success=True, content="No notes recorded yet.")
            notes = self._deduplicate(notes)

            if category:
                notes = [note for note in notes if note.category == category]
                if not notes:
                    return ToolResult(
                        success=True,
                        content=f"No notes found in category: {category}",
                    )

            bounded_limit = max(1, min(int(limit), 100))

            if query:
                ranked = self._rank_notes(notes, query=query, use_embedding=use_embedding)
                if not ranked:
                    return ToolResult(
                        success=True,
                        content=f"No notes matched query: {query}",
                    )
                selected_notes = [note for note, _ in ranked[:bounded_limit]]
            else:
                selected_notes = sorted(notes, key=self._sort_key, reverse=True)[:bounded_limit]

            formatted: list[str] = []
            for index, note in enumerate(selected_notes, start=1):
                source = self.memory_store.relative_path(note.path)
                formatted.append(
                    f"{index}. [{note.category}] {note.content}\n"
                    f"   (recorded at {note.timestamp}, source: {source})"
                )

            return ToolResult(success=True, content="Memory Notes:\n" + "\n".join(formatted))
        except Exception as exc:
            return ToolResult(
                success=False,
                content="",
                error=f"Failed to recall notes: {exc}",
            )

    def _rank_notes(
        self,
        notes: list[MemoryNote],
        query: str,
        use_embedding: bool,
    ) -> list[tuple[MemoryNote, float]]:
        query_text = query.strip().lower()
        if not query_text:
            return [(note, 0.0) for note in sorted(notes, key=self._sort_key, reverse=True)]

        query_vector = None
        if use_embedding:
            query_vector = self._embed(query)

        ranked: list[tuple[MemoryNote, float]] = []
        for note in notes:
            keyword_score = self._keyword_score(note=note, query_text=query_text)

            semantic_score = 0.0
            if query_vector is not None:
                note_vector = self._embed(note.content)
                if note_vector is not None:
                    semantic_score = max(0.0, self._cosine_similarity(query_vector, note_vector))

            total_score = keyword_score + semantic_score
            if total_score > 0:
                ranked.append((note, total_score))

        ranked.sort(key=lambda item: (item[1], self._sort_key(item[0])), reverse=True)
        return ranked

    def _deduplicate(self, notes: list[MemoryNote]) -> list[MemoryNote]:
        deduped: list[MemoryNote] = []
        seen: set[tuple[str, str, str]] = set()
        for note in notes:
            fingerprint = (note.timestamp, note.category, note.content)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            deduped.append(note)
        return deduped

    def _keyword_score(self, note: MemoryNote, query_text: str) -> float:
        haystack = f"{note.category} {note.content}".lower()
        score = 0.0

        if query_text in haystack:
            score += 4.0

        for token in self._tokenize(query_text):
            if len(token) < 2:
                continue
            if token in haystack:
                score += 1.0

        return score

    def _tokenize(self, text: str) -> list[str]:
        return [token for token in re.findall(r"\w+", text.lower()) if token]

    def _sort_key(self, note: MemoryNote) -> datetime:
        try:
            return datetime.fromisoformat(note.timestamp)
        except Exception:
            return datetime.min

    def _embed(self, text: str) -> list[float] | None:
        provider = self.embedding_provider
        if provider is None:
            return None

        try:
            if hasattr(provider, "embed"):
                raw_vector = provider.embed(text)  # type: ignore[attr-defined]
            else:
                raw_vector = provider(text)  # type: ignore[operator]
        except Exception:
            return None

        if not raw_vector:
            return None

        try:
            vector = [float(value) for value in raw_vector]
        except Exception:
            return None

        if not any(vector):
            return None

        return vector

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        size = min(len(left), len(right))
        if size == 0:
            return 0.0

        left_slice = left[:size]
        right_slice = right[:size]

        dot = sum(a * b for a, b in zip(left_slice, right_slice, strict=False))
        left_norm = math.sqrt(sum(a * a for a in left_slice))
        right_norm = math.sqrt(sum(b * b for b in right_slice))

        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0

        return dot / (left_norm * right_norm)
