"""Workspace runtime-memory backend access owned by the memory package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime


class RuntimeMemoryBackend(Protocol):
    """Port for workspace-scoped runtime-memory operations."""

    def clear_session_namespace(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
    ) -> bool: ...

    def clear_workspace_shared_namespace(
        self,
        *,
        workspace_dir: Path,
    ) -> bool: ...

    def snapshot_session_payload(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
    ) -> dict[str, Any]: ...

    def snapshot_workspace_shared_payload(
        self,
        *,
        workspace_dir: Path,
    ) -> dict[str, Any]: ...

    def restore_session_payload(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]: ...

    def restore_workspace_shared_payload(
        self,
        *,
        workspace_dir: Path,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]: ...

    def get_session_entry(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
        engram_id: str,
    ) -> dict[str, Any] | None: ...

    def get_workspace_shared_entry(
        self,
        *,
        workspace_dir: Path,
        engram_id: str,
    ) -> dict[str, Any] | None: ...

    def promote_session_memory_to_workspace_shared(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
        engram_id: str,
    ) -> dict[str, Any]: ...

    def promote_session_memory_to_workspace_note(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
        engram_id: str,
    ) -> dict[str, Any]: ...

    def promote_session_memory_to_global_profile(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
        engram_id: str,
    ) -> dict[str, Any]: ...


@dataclass(slots=True)
class WorkspaceRuntimeMemoryBackend:
    """Thin adapter over ``WorkspaceMemoriaRuntime`` for shared callers."""

    def clear_session_namespace(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
    ) -> bool:
        try:
            return WorkspaceMemoriaRuntime(workspace_dir).clear_session_namespace(session_id)
        except Exception:
            return False

    def clear_workspace_shared_namespace(
        self,
        *,
        workspace_dir: Path,
    ) -> bool:
        try:
            return WorkspaceMemoriaRuntime(workspace_dir).clear_workspace_shared_namespace()
        except Exception:
            return False

    def snapshot_session_payload(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
    ) -> dict[str, Any]:
        try:
            return WorkspaceMemoriaRuntime(workspace_dir).snapshot_session_namespace_payload(session_id)
        except Exception:
            return {}

    def snapshot_workspace_shared_payload(
        self,
        *,
        workspace_dir: Path,
    ) -> dict[str, Any]:
        try:
            return WorkspaceMemoriaRuntime(workspace_dir).snapshot_workspace_shared_namespace_payload()
        except Exception:
            return {}

    def restore_session_payload(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            return WorkspaceMemoriaRuntime(workspace_dir).restore_session_namespace_payload(
                session_id,
                payload,
                replace=True,
            )
        except Exception:
            return {
                "restored": False,
                "namespace": WorkspaceMemoriaRuntime.session_namespace(session_id),
                "entry_count": 0,
                "stats": {},
            }

    def restore_workspace_shared_payload(
        self,
        *,
        workspace_dir: Path,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            return WorkspaceMemoriaRuntime(workspace_dir).restore_workspace_shared_namespace_payload(
                payload,
                replace=False,
            )
        except Exception:
            return {
                "restored": False,
                "namespace": WorkspaceMemoriaRuntime.shared_namespace(),
                "entry_count": 0,
                "stats": {},
                "merged": True,
            }

    def get_session_entry(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
        engram_id: str,
    ) -> dict[str, Any] | None:
        try:
            return WorkspaceMemoriaRuntime(workspace_dir).get_namespace_entry(
                WorkspaceMemoriaRuntime.session_namespace(session_id),
                engram_id=engram_id,
            )
        except Exception:
            return None

    def get_workspace_shared_entry(
        self,
        *,
        workspace_dir: Path,
        engram_id: str,
    ) -> dict[str, Any] | None:
        try:
            return WorkspaceMemoriaRuntime(workspace_dir).get_workspace_shared_entry(engram_id=engram_id)
        except Exception:
            return None

    def promote_session_memory_to_workspace_shared(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
        engram_id: str,
    ) -> dict[str, Any]:
        return WorkspaceMemoriaRuntime(workspace_dir).promote_session_memory_to_workspace_shared(
            session_id=session_id,
            engram_id=engram_id,
        )

    def promote_session_memory_to_workspace_note(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
        engram_id: str,
    ) -> dict[str, Any]:
        return WorkspaceMemoriaRuntime(workspace_dir).promote_session_memory_to_workspace_note(
            session_id=session_id,
            engram_id=engram_id,
        )

    def promote_session_memory_to_global_profile(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
        engram_id: str,
    ) -> dict[str, Any]:
        return WorkspaceMemoriaRuntime(workspace_dir).promote_session_memory_to_global_profile(
            session_id=session_id,
            engram_id=engram_id,
        )


__all__ = [
    "RuntimeMemoryBackend",
    "WorkspaceRuntimeMemoryBackend",
]
