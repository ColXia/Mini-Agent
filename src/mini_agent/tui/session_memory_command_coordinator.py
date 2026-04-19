"""Shared TUI memory-command orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from typing import Any, Callable

from mini_agent.commands.execution import CommandExecutionResult, MemoryCommandPlan


@dataclass(slots=True)
class TuiSessionMemoryCommandCoordinator:
    """Own TUI memory-command orchestration above command planning/execution."""

    resolve_memory_command_plan: Callable[[Sequence[str]], MemoryCommandPlan | CommandExecutionResult]
    has_local_runtime_state: Callable[[Any], bool]
    execute_memory_command_plan: Callable[..., Awaitable[bool]]
    append_command_feedback: Callable[..., None]
    set_status: Callable[[str], None]
    render_all: Callable[[], None]

    async def handle(self, session: Any, args: Sequence[str]) -> None:
        plan = self.resolve_memory_command_plan(args)
        if isinstance(plan, CommandExecutionResult):
            self.append_command_feedback(
                plan.command,
                summary=plan.summary,
                details=plan.details,
                level="error" if plan.kind in {"usage", "error"} else "info",
            )
            self.set_status(plan.status_text)
            self.render_all()
            return

        if plan.requires_idle_local_runtime and self.has_local_runtime_state(session) and session.projection.busy:
            self.append_command_feedback(
                plan.command,
                summary="session busy",
                details=f"{session.title} is busy. Wait for the current turn to finish first.",
                level="error",
            )
            self.set_status(f"{session.title} is busy.")
            self.render_all()
            return

        await self.execute_memory_command_plan(
            session,
            command=plan.command,
            action=plan.action,
            engram_id=plan.engram_id,
            content=plan.content,
            query=plan.query,
            day=plan.day,
            export_format=plan.export_format,
            detail_mode=plan.detail_mode,
            success_status=plan.success_status,
            failure_summary=plan.failure_summary,
            failure_detail_prefix=plan.failure_detail_prefix,
            failure_status=plan.failure_status,
            summary_fallback=plan.summary_fallback,
            metadata_builder=plan.metadata_builder,
        )


__all__ = ["TuiSessionMemoryCommandCoordinator"]


