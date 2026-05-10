"""Memory resolver for three-layer memory resolution.

This module provides the MemoryResolver for resolving memory across three layers:
- Session Memory: Current task working memory, scratchpad
- Workspace Memory: Project experience, local knowledge
- Global Memory: User preferences, long-term learning

Resolution follows priority order for reading:
- session → workspace → global

Writing defaults to session scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from mini_agent.utils.text import safe_text


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_text(value: Any) -> str:
    return safe_text(value)


class MemoryScope(str, Enum):
    """Memory scope types for three-layer resolution."""

    SESSION = "session"
    WORKSPACE = "workspace"
    GLOBAL = "global"


class MemoryKind(str, Enum):
    """Memory entry kinds."""

    FACT = "fact"
    PREFERENCE = "preference"
    EXPERIENCE = "experience"
    SCRATCHPAD = "scratchpad"
    SUMMARY = "summary"


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """A single memory entry with scope metadata."""

    entry_id: str
    scope: MemoryScope
    kind: MemoryKind
    content: str
    source: str | None = None
    tags: tuple[str, ...] = ()
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_id = _safe_text(self.entry_id)
        normalized_content = _safe_text(self.content)
        if not normalized_id:
            raise ValueError("entry_id is required")
        object.__setattr__(self, "entry_id", normalized_id)
        object.__setattr__(self, "content", normalized_content)
        object.__setattr__(self, "source", _safe_text(self.source))
        object.__setattr__(self, "tags", tuple(self.tags) if self.tags else ())
        object.__setattr__(self, "metadata", dict(self.metadata) if self.metadata else {})
        if self.created_at is None:
            object.__setattr__(self, "created_at", _utc_now())


@dataclass(frozen=True, slots=True)
class ResolvedMemory:
    """Resolved memory view across all scopes."""

    session_id: str
    workspace_id: str
    session_entries: tuple[MemoryEntry, ...] = ()
    workspace_entries: tuple[MemoryEntry, ...] = ()
    global_entries: tuple[MemoryEntry, ...] = ()
    resolution_timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.resolution_timestamp is None:
            object.__setattr__(self, "resolution_timestamp", _utc_now())

    @property
    def total_entry_count(self) -> int:
        """Return the total number of memory entries."""
        return len(self.session_entries) + len(self.workspace_entries) + len(self.global_entries)

    def get_all_entries(self) -> list[MemoryEntry]:
        """Get all entries in priority order (session → workspace → global)."""
        return list(self.session_entries) + list(self.workspace_entries) + list(self.global_entries)

    def get_entries_by_kind(self, kind: MemoryKind) -> list[MemoryEntry]:
        """Get all entries of a specific kind."""
        return [entry for entry in self.get_all_entries() if entry.kind == kind]

    def get_entries_by_tag(self, tag: str) -> list[MemoryEntry]:
        """Get all entries with a specific tag."""
        normalized_tag = _safe_text(tag).lower()
        return [entry for entry in self.get_all_entries() if normalized_tag in [t.lower() for t in entry.tags]]

    def search_content(self, query: str) -> list[MemoryEntry]:
        """Search entries by content (case-insensitive substring match)."""
        normalized_query = _safe_text(query).lower()
        if not normalized_query:
            return []
        return [entry for entry in self.get_all_entries() if normalized_query in entry.content.lower()]


@dataclass(slots=True)
class SessionMemoryStore:
    """Store for session-scoped memory.

    Session memory is the current task's working memory and scratchpad.
    It is the default write target and has the highest read priority.
    """

    session_id: str
    _entries: dict[str, MemoryEntry] = field(default_factory=dict)

    def write(self, entry: MemoryEntry) -> MemoryEntry:
        """Write a memory entry to the session store."""
        if entry.scope != MemoryScope.SESSION:
            raise ValueError("Only session-scoped entries can be written to SessionMemoryStore")
        self._entries[entry.entry_id] = entry
        return entry

    def read(self, entry_id: str) -> MemoryEntry | None:
        """Read a memory entry by ID."""
        return self._entries.get(_safe_text(entry_id))

    def delete(self, entry_id: str) -> MemoryEntry | None:
        """Delete a memory entry by ID."""
        return self._entries.pop(_safe_text(entry_id), None)

    def list_all(self) -> list[MemoryEntry]:
        """List all session memory entries."""
        return list(self._entries.values())

    def clear(self) -> None:
        """Clear all session memory."""
        self._entries.clear()


@dataclass(slots=True)
class WorkspaceMemoryStore:
    """Store for workspace-scoped memory.

    Workspace memory contains project experience and local knowledge.
    It is bound to the workspace lifecycle and does not propagate to global.
    """

    workspace_id: str
    workspace_dir: Path | None = None
    _entries: dict[str, MemoryEntry] = field(default_factory=dict)

    def write(self, entry: MemoryEntry) -> MemoryEntry:
        """Write a memory entry to the workspace store."""
        if entry.scope != MemoryScope.WORKSPACE:
            raise ValueError("Only workspace-scoped entries can be written to WorkspaceMemoryStore")
        self._entries[entry.entry_id] = entry
        return entry

    def read(self, entry_id: str) -> MemoryEntry | None:
        """Read a memory entry by ID."""
        return self._entries.get(_safe_text(entry_id))

    def delete(self, entry_id: str) -> MemoryEntry | None:
        """Delete a memory entry by ID."""
        return self._entries.pop(_safe_text(entry_id), None)

    def list_all(self) -> list[MemoryEntry]:
        """List all workspace memory entries."""
        return list(self._entries.values())

    def clear(self) -> None:
        """Clear all workspace memory."""
        self._entries.clear()


@dataclass(slots=True)
class GlobalMemoryStore:
    """Store for global-scoped memory.

    Global memory contains user preferences and long-term learning.
    It is shared across all workspaces but requires explicit write.
    """

    _entries: dict[str, MemoryEntry] = field(default_factory=dict)

    def write(self, entry: MemoryEntry) -> MemoryEntry:
        """Write a memory entry to the global store."""
        if entry.scope != MemoryScope.GLOBAL:
            raise ValueError("Only global-scoped entries can be written to GlobalMemoryStore")
        self._entries[entry.entry_id] = entry
        return entry

    def read(self, entry_id: str) -> MemoryEntry | None:
        """Read a memory entry by ID."""
        return self._entries.get(_safe_text(entry_id))

    def delete(self, entry_id: str) -> MemoryEntry | None:
        """Delete a memory entry by ID."""
        return self._entries.pop(_safe_text(entry_id), None)

    def list_all(self) -> list[MemoryEntry]:
        """List all global memory entries."""
        return list(self._entries.values())

    def clear(self) -> None:
        """Clear all global memory."""
        self._entries.clear()


@dataclass(slots=True)
class MemoryResolver:
    """Resolver for three-layer memory assembly.

    This resolver assembles memory from session, workspace, and global
    layers following the priority order:
    - Reading: session → workspace → global
    - Writing: defaults to session

    Promotion rules:
    - session → workspace: allowed
    - workspace → global: requires explicit authorization
    - session → global: requires explicit authorization
    """

    global_store: GlobalMemoryStore = field(default_factory=GlobalMemoryStore)
    workspace_stores: dict[str, WorkspaceMemoryStore] = field(default_factory=dict)
    session_stores: dict[str, SessionMemoryStore] = field(default_factory=dict)

    def get_or_create_session_store(self, session_id: str) -> SessionMemoryStore:
        """Get or create a session memory store."""
        normalized_session_id = _safe_text(session_id)
        if normalized_session_id not in self.session_stores:
            self.session_stores[normalized_session_id] = SessionMemoryStore(
                session_id=normalized_session_id
            )
        return self.session_stores[normalized_session_id]

    def get_or_create_workspace_store(self, workspace_id: str) -> WorkspaceMemoryStore:
        """Get or create a workspace memory store."""
        normalized_workspace_id = _safe_text(workspace_id)
        if normalized_workspace_id not in self.workspace_stores:
            self.workspace_stores[normalized_workspace_id] = WorkspaceMemoryStore(
                workspace_id=normalized_workspace_id
            )
        return self.workspace_stores[normalized_workspace_id]

    def resolve(
        self,
        session_id: str,
        workspace_id: str,
    ) -> ResolvedMemory:
        """Resolve memory for a specific session and workspace.

        Args:
            session_id: The session ID
            workspace_id: The workspace ID

        Returns:
            A ResolvedMemory containing all assembled entries
        """
        session_store = self.session_stores.get(_safe_text(session_id))
        workspace_store = self.workspace_stores.get(_safe_text(workspace_id))

        session_entries = tuple(session_store.list_all()) if session_store else ()
        workspace_entries = tuple(workspace_store.list_all()) if workspace_store else ()
        global_entries = tuple(self.global_store.list_all())

        return ResolvedMemory(
            session_id=_safe_text(session_id),
            workspace_id=_safe_text(workspace_id),
            session_entries=session_entries,
            workspace_entries=workspace_entries,
            global_entries=global_entries,
        )

    def write(
        self,
        entry: MemoryEntry,
        session_id: str | None = None,
        workspace_id: str | None = None,
        promote_to_workspace: bool = False,
        promote_to_global: bool = False,
    ) -> MemoryEntry:
        """Write a memory entry to the appropriate store.

        Args:
            entry: The memory entry to write
            session_id: The session ID (required for session scope)
            workspace_id: The workspace ID (required for workspace scope)
            promote_to_workspace: If True and entry is session-scoped, also write to workspace
            promote_to_global: If True and entry is workspace-scoped, also write to global

        Returns:
            The written memory entry
        """
        if entry.scope == MemoryScope.SESSION:
            if not session_id:
                raise ValueError("session_id is required for session-scoped entries")
            store = self.get_or_create_session_store(session_id)
            store.write(entry)

            if promote_to_workspace and workspace_id:
                workspace_entry = MemoryEntry(
                    entry_id=f"ws-{entry.entry_id}",
                    scope=MemoryScope.WORKSPACE,
                    kind=entry.kind,
                    content=entry.content,
                    source=entry.source,
                    tags=entry.tags,
                    metadata={"promoted_from": "session", "original_entry_id": entry.entry_id},
                )
                workspace_store = self.get_or_create_workspace_store(workspace_id)
                workspace_store.write(workspace_entry)

        elif entry.scope == MemoryScope.WORKSPACE:
            if not workspace_id:
                raise ValueError("workspace_id is required for workspace-scoped entries")
            store = self.get_or_create_workspace_store(workspace_id)
            store.write(entry)

            if promote_to_global:
                global_entry = MemoryEntry(
                    entry_id=f"global-{entry.entry_id}",
                    scope=MemoryScope.GLOBAL,
                    kind=entry.kind,
                    content=entry.content,
                    source=entry.source,
                    tags=entry.tags,
                    metadata={"promoted_from": "workspace", "original_entry_id": entry.entry_id},
                )
                self.global_store.write(global_entry)

        elif entry.scope == MemoryScope.GLOBAL:
            self.global_store.write(entry)

        return entry

    def promote_to_workspace(
        self,
        entry_id: str,
        session_id: str,
        workspace_id: str,
    ) -> MemoryEntry | None:
        """Promote a session entry to workspace scope.

        Args:
            entry_id: The entry ID to promote
            session_id: The source session ID
            workspace_id: The target workspace ID

        Returns:
            The new workspace-scoped entry, or None if source not found
        """
        session_store = self.session_stores.get(_safe_text(session_id))
        if session_store is None:
            return None

        source_entry = session_store.read(entry_id)
        if source_entry is None:
            return None

        workspace_entry = MemoryEntry(
            entry_id=f"ws-{entry_id}",
            scope=MemoryScope.WORKSPACE,
            kind=source_entry.kind,
            content=source_entry.content,
            source=source_entry.source,
            tags=source_entry.tags,
            metadata={"promoted_from": "session", "original_entry_id": entry_id},
        )

        workspace_store = self.get_or_create_workspace_store(workspace_id)
        return workspace_store.write(workspace_entry)

    def clear_session(self, session_id: str) -> None:
        """Clear all memory for a session."""
        session_store = self.session_stores.pop(_safe_text(session_id), None)
        if session_store is not None:
            session_store.clear()

    def clear_workspace(self, workspace_id: str) -> None:
        """Clear all memory for a workspace."""
        workspace_store = self.workspace_stores.pop(_safe_text(workspace_id), None)
        if workspace_store is not None:
            workspace_store.clear()

    def clear(self) -> None:
        """Clear all memory stores."""
        self.global_store.clear()
        self.workspace_stores.clear()
        self.session_stores.clear()


_SHARED_RESOLVER: MemoryResolver | None = None


def shared_memory_resolver() -> MemoryResolver:
    """Return the process-local shared memory resolver."""
    global _SHARED_RESOLVER
    if _SHARED_RESOLVER is None:
        _SHARED_RESOLVER = MemoryResolver()
    return _SHARED_RESOLVER


def clear_shared_memory_resolver() -> None:
    """Clear the process-local shared memory resolver."""
    global _SHARED_RESOLVER
    if _SHARED_RESOLVER is not None:
        _SHARED_RESOLVER.clear()
    _SHARED_RESOLVER = None


__all__ = [
    "clear_shared_memory_resolver",
    "GlobalMemoryStore",
    "MemoryEntry",
    "MemoryKind",
    "MemoryResolver",
    "MemoryScope",
    "ResolvedMemory",
    "SessionMemoryStore",
    "shared_memory_resolver",
    "WorkspaceMemoryStore",
]