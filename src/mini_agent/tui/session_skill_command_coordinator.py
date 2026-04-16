"""Shared TUI skill-command orchestration."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Callable

from mini_agent.commands import CommandExecutionResult
from mini_agent.transport import extract_gateway_error_info


@dataclass(slots=True)
class TuiSessionSkillCommandCoordinator:
    """Own TUI skill-command orchestration above domain helpers."""

    resolve_skill_command_plan: Callable[[Any], Any]
    runs_via_gateway: Callable[[Any], bool]
    resolve_remote_skill_command_plan: Callable[[Any], Any]
    run_remote_skill_action: Callable[[Any, Any], Awaitable[dict[str, Any]]]
    apply_remote_skill_response: Callable[[Any, Any, dict[str, Any]], None]
    run_local_skill_command_result: Callable[[Any, Any], CommandExecutionResult]
    apply_local_skill_command_result: Callable[[Any, CommandExecutionResult], Awaitable[None]]
    append_command_feedback: Callable[..., None]
    set_status: Callable[[str], None]
    render_all: Callable[[], None]

    async def handle(self, session: Any, invocation_or_args: Any) -> None:
        plan = self.resolve_skill_command_plan(invocation_or_args)
        if isinstance(plan, CommandExecutionResult):
            self.append_command_feedback(
                plan.command,
                summary=plan.summary,
                details=plan.details,
                level="error" if plan.kind in {"usage", "error"} else "info",
                metadata={"threads_visible": False},
            )
            self.set_status(plan.status_text)
            self.render_all()
            return

        if self.runs_via_gateway(session):
            remote_plan = self.resolve_remote_skill_command_plan(plan)
            try:
                response = await self.run_remote_skill_action(session, remote_plan)
                self.apply_remote_skill_response(session, remote_plan, response)
            except Exception as exc:
                detail = extract_gateway_error_info(exc).detail
                self.append_command_feedback(
                    remote_plan.command,
                    summary="command failed",
                    details=f"Remote skill command failed: {detail}",
                    level="error",
                    metadata={"threads_visible": False},
                )
                self.set_status("Remote skill command failed.")
            self.render_all()
            return

        result = self.run_local_skill_command_result(session, plan)
        await self.apply_local_skill_command_result(session, result)
        self.render_all()


__all__ = ["TuiSessionSkillCommandCoordinator"]
