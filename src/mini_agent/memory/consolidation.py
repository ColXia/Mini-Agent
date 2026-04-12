"""Two-phase memory consolidation pipeline facade."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from mini_agent.memory.consolidation_scheduler import ConsolidationScheduler
from mini_agent.memory.memory_files import resolve_workspace_memory_layout, resolve_workspace_root
from mini_agent.session.persistence import SessionPersistence


class MemoryConsolidationPipeline:
    """Single-entry API for phase1/phase2 consolidation runs."""

    def __init__(
        self,
        *,
        session_store_dir: Path | str | None = None,
        state_dir: Path | str | None = None,
        memory_file: Path | str | None = None,
        workspace_dir: Path | str | None = None,
        workspace_anchor_dir: Path | str | None = None,
    ):
        if session_store_dir is None:
            session_persistence = SessionPersistence()
        else:
            session_persistence = SessionPersistence(Path(session_store_dir).expanduser().resolve())
        resolved_session_store_dir = session_persistence.base_dir

        if workspace_anchor_dir is not None:
            resolved_workspace_anchor_dir = resolve_workspace_root(workspace_anchor_dir)
        else:
            layout_start_dir = (
                resolve_workspace_root(workspace_dir)
                if workspace_dir is not None
                else (
                    Path(memory_file).expanduser().resolve().parent
                    if memory_file is not None
                    else Path.cwd().resolve()
                )
            )
            resolved_workspace_anchor_dir = resolve_workspace_root(layout_start_dir)

        if memory_file is None:
            layout = resolve_workspace_memory_layout(resolved_workspace_anchor_dir)
            resolved_memory_file = layout.memory_file or (resolved_workspace_anchor_dir / "MEMORY.md")
        else:
            resolved_memory_file = Path(memory_file).expanduser().resolve()

        if state_dir is None:
            resolved_state_dir = self._default_state_dir(
                session_store_dir=resolved_session_store_dir,
                workspace_anchor_dir=resolved_workspace_anchor_dir,
            )
        else:
            resolved_state_dir = Path(state_dir).expanduser().resolve()

        self.session_persistence = session_persistence
        self.scheduler = ConsolidationScheduler(
            session_persistence=session_persistence,
            base_dir=resolved_state_dir,
            memory_file=resolved_memory_file,
            workspace_anchor_dir=resolved_workspace_anchor_dir,
        )
        self.session_store_dir = resolved_session_store_dir
        self.base_dir = resolved_session_store_dir
        self.state_dir = resolved_state_dir
        self.memory_file = resolved_memory_file
        self.workspace_anchor_dir = resolved_workspace_anchor_dir

    @staticmethod
    def _default_state_dir(
        *,
        session_store_dir: Path,
        workspace_anchor_dir: Path,
    ) -> Path:
        anchor_text = str(workspace_anchor_dir.expanduser().resolve())
        digest = hashlib.sha1(anchor_text.encode("utf-8")).hexdigest()[:12]
        anchor_name = workspace_anchor_dir.name or "workspace"
        safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in anchor_name).strip("-")
        if not safe_name:
            safe_name = "workspace"
        return session_store_dir / "consolidation_workspaces" / f"{safe_name}-{digest}"

    def run(
        self,
        *,
        phase: Literal["phase1", "phase2", "all"] = "all",
        max_jobs: int = 8,
        lease_seconds: int = 3600,
        retry_seconds: int = 3600,
        top_n: int = 40,
        exclude_session_id: str | None = None,
    ) -> dict[str, Any]:
        if phase == "phase1":
            summary = self.scheduler.run_phase1(
                max_jobs=max_jobs,
                lease_seconds=lease_seconds,
                retry_seconds=retry_seconds,
                exclude_session_id=exclude_session_id,
            )
            return {
                "phase": "phase1",
                "base_dir": str(self.base_dir),
                "session_store_dir": str(self.session_store_dir),
                "state_dir": str(self.state_dir),
                "workspace_anchor_dir": str(self.workspace_anchor_dir),
                "memory_file": str(self.memory_file),
                "phase1": summary.__dict__,
                "job_stats": self.scheduler.job_store.stats(),
            }

        if phase == "phase2":
            summary = self.scheduler.run_phase2(top_n=top_n)
            return {
                "phase": "phase2",
                "base_dir": str(self.base_dir),
                "session_store_dir": str(self.session_store_dir),
                "state_dir": str(self.state_dir),
                "workspace_anchor_dir": str(self.workspace_anchor_dir),
                "memory_file": str(self.memory_file),
                "phase2": summary.__dict__,
                "job_stats": self.scheduler.job_store.stats(),
            }

        full = self.scheduler.run_all(
            max_jobs=max_jobs,
            lease_seconds=lease_seconds,
            retry_seconds=retry_seconds,
            top_n=top_n,
            exclude_session_id=exclude_session_id,
        )
        return {
            "phase": "all",
            "base_dir": str(self.base_dir),
            "session_store_dir": str(self.session_store_dir),
            "state_dir": str(self.state_dir),
            "workspace_anchor_dir": str(self.workspace_anchor_dir),
            "memory_file": str(self.memory_file),
            **full,
        }
