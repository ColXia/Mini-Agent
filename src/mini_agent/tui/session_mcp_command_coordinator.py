"""Shared TUI MCP-command orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable

from mini_agent.commands import CommandExecutionResult


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _response_value(response: Any, field: str) -> Any:
    if isinstance(response, Mapping):
        return response.get(field)
    return getattr(response, field, None)


@dataclass(slots=True)
class TuiSessionMcpCommandCoordinator:
    """Own TUI MCP-command orchestration above execution helpers."""

    resolve_mcp_command_plan: Callable[[Sequence[str]], Any]
    runs_via_gateway: Callable[[Any], bool]
    dispatch_remote_mcp_command: Callable[[Any, Any], Awaitable[tuple[Any, bool] | None]]
    mcp_remote_status_text: Callable[[str], str]
    run_local_mcp_command_result: Callable[[Any, Sequence[str], Any], Awaitable[CommandExecutionResult]]
    append_command_feedback: Callable[..., None]
    set_status: Callable[[str], None]
    render_all: Callable[[], None]

    async def handle(self, session: Any, args: Sequence[str]) -> None:
        plan = self.resolve_mcp_command_plan(args)
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
            remote_result = await self.dispatch_remote_mcp_command(session, plan)
            if remote_result is None:
                return
            response, synced = remote_result
            if not synced:
                stats = _response_value(response, "stats")
                stats_payload = dict(stats or {}) if isinstance(stats, Mapping) else {}
                summary = _safe_text(stats_payload.get("summary")) or f"mcp {plan.action} completed"
                details = str(stats_payload.get("details") or "").strip() or f"Remote MCP {plan.action} completed."
                self.append_command_feedback(
                    plan.command,
                    summary=summary,
                    details=details,
                    metadata={"threads_visible": False},
                )
            self.set_status(self.mcp_remote_status_text(plan.action))
            self.render_all()
            return

        result = await self.run_local_mcp_command_result(session, args, plan)
        self.append_command_feedback(
            result.command,
            summary=result.summary,
            details=result.details,
            level="error" if result.kind in {"usage", "error"} else "info",
            metadata={"threads_visible": False},
        )
        self.set_status(result.status_text)
        self.render_all()


__all__ = ["TuiSessionMcpCommandCoordinator"]
