"""Two-phase memory consolidation pipeline facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from mini_agent.memory.consolidation_scheduler import ConsolidationScheduler
from mini_agent.memory.memory_files import discover_memory_layout
from mini_agent.session.persistence import SessionPersistence


class MemoryConsolidationPipeline:
    """Single-entry API for phase1/phase2 consolidation runs."""

    def __init__(
        self,
        *,
        session_store_dir: Path | str | None = None,
        memory_file: Path | str | None = None,
    ):
        if session_store_dir is None:
            session_persistence = SessionPersistence()
            base_dir = session_persistence.base_dir
        else:
            base_dir = Path(session_store_dir).expanduser().resolve()
            session_persistence = SessionPersistence(base_dir)

        if memory_file is None:
            layout = discover_memory_layout(Path.cwd())
            resolved_memory_file = layout.memory_file or (layout.anchor_dir / "MEMORY.md")
        else:
            resolved_memory_file = Path(memory_file).expanduser().resolve()

        self.session_persistence = session_persistence
        self.scheduler = ConsolidationScheduler(
            session_persistence=session_persistence,
            base_dir=base_dir,
            memory_file=resolved_memory_file,
        )
        self.base_dir = base_dir
        self.memory_file = resolved_memory_file

    def run(
        self,
        *,
        phase: Literal["phase1", "phase2", "all"] = "all",
        max_jobs: int = 8,
        lease_seconds: int = 3600,
        retry_seconds: int = 3600,
        top_n: int = 40,
    ) -> dict[str, Any]:
        if phase == "phase1":
            summary = self.scheduler.run_phase1(
                max_jobs=max_jobs,
                lease_seconds=lease_seconds,
                retry_seconds=retry_seconds,
            )
            return {
                "phase": "phase1",
                "base_dir": str(self.base_dir),
                "memory_file": str(self.memory_file),
                "phase1": summary.__dict__,
                "job_stats": self.scheduler.job_store.stats(),
            }

        if phase == "phase2":
            summary = self.scheduler.run_phase2(top_n=top_n)
            return {
                "phase": "phase2",
                "base_dir": str(self.base_dir),
                "memory_file": str(self.memory_file),
                "phase2": summary.__dict__,
                "job_stats": self.scheduler.job_store.stats(),
            }

        full = self.scheduler.run_all(
            max_jobs=max_jobs,
            lease_seconds=lease_seconds,
            retry_seconds=retry_seconds,
            top_n=top_n,
        )
        return {
            "phase": "all",
            "base_dir": str(self.base_dir),
            "memory_file": str(self.memory_file),
            **full,
        }
