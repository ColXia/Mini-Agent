"""Shared TUI knowledge-base command orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from typing import Any, Callable

from mini_agent.commands.execution import CommandExecutionResult
from mini_agent.transport import extract_gateway_error_info


@dataclass(slots=True)
class TuiSessionKbCommandCoordinator:
    """Own TUI knowledge-base command orchestration above execution helpers."""

    resolve_kb_command_plan: Callable[[Sequence[str]], Any]
    runs_via_gateway: Callable[[Any], bool]
    sync_remote_session_detail: Callable[[Any], Awaitable[None]]
    execute_remote_kb_command: Callable[[Any, Any], Awaitable[None]]
    execute_local_kb_command: Callable[..., Awaitable[CommandExecutionResult]]
    session_knowledge_base_enabled: Callable[[Any], bool | None]
    apply_agent_knowledge_base_enabled: Callable[[Any, bool], bool]
    refresh_local_runtime_projection: Callable[[Any], Any]
    persist_session_state: Callable[[], None]
    append_command_feedback: Callable[..., None]
    set_status: Callable[[str], None]
    render_all: Callable[[], None]

    async def handle(self, session: Any, args: Sequence[str]) -> None:
        plan = self.resolve_kb_command_plan(args)
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

        if plan.action == "status":
            await self._handle_status(session, plan=plan, args=args)
            return

        if self.runs_via_gateway(session):
            await self.execute_remote_kb_command(session, plan)
            self.render_all()
            return

        result = await self._run_local_mutation_result(session, args, plan)
        self.append_command_feedback(
            result.command,
            summary=result.summary,
            details=result.details,
            level="error" if result.kind in {"usage", "error"} else "info",
            metadata={"threads_visible": False},
        )
        self.set_status(result.status_text)
        self.render_all()

    async def _handle_status(self, session: Any, *, plan: Any, args: Sequence[str]) -> None:
        if self.runs_via_gateway(session):
            try:
                await self.sync_remote_session_detail(session)
            except Exception as exc:
                detail = extract_gateway_error_info(exc).detail
                self.append_command_feedback(
                    plan.command,
                    summary="status failed",
                    details=f"Remote KB status failed: {detail}",
                    level="error",
                )
                self.set_status("Remote KB status failed.")
                self.render_all()
                return

        runtime = getattr(session, "runtime", None)
        agent = getattr(runtime, "agent", None)
        result = await self.execute_local_kb_command(
            surface="tui",
            action="status",
            args=list(args),
            current_enabled=self.session_knowledge_base_enabled(session),
            session_label=session.title,
            runtime_attached=agent is not None,
        )
        self.append_command_feedback(
            result.command,
            summary=result.summary,
            details=result.details,
            metadata={"threads_visible": False},
        )
        self.set_status(result.status_text)
        self.render_all()

    async def _run_local_mutation_result(
        self,
        session: Any,
        args: Sequence[str],
        plan: Any,
    ) -> CommandExecutionResult:
        projection = getattr(session, "projection", None)
        runtime = getattr(session, "runtime", None)
        agent = getattr(runtime, "agent", None)

        def _apply_local_kb(enabled: bool) -> bool:
            if agent is not None:
                return self.apply_agent_knowledge_base_enabled(agent, enabled)
            if projection is not None:
                projection.knowledge_base_enabled = enabled
            return enabled

        result = await self.execute_local_kb_command(
            surface="tui",
            action=plan.action,
            args=list(args),
            current_enabled=self.session_knowledge_base_enabled(session),
            session_label=session.title,
            runtime_attached=agent is not None,
            busy=bool(getattr(projection, "busy", False)),
            toggle_callback=_apply_local_kb,
        )

        if agent is not None:
            self.refresh_local_runtime_projection(session)
        else:
            payload = result.payload if isinstance(result.payload, dict) else {}
            enabled_payload = payload.get("enabled")
            if projection is not None and (isinstance(enabled_payload, bool) or enabled_payload is None):
                projection.knowledge_base_enabled = enabled_payload
        self.persist_session_state()
        return result


__all__ = ["TuiSessionKbCommandCoordinator"]
