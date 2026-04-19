"""Shared TUI context-command orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from typing import Any, Callable

from mini_agent.commands.execution import CommandExecutionResult, ContextCommandPlan


@dataclass(slots=True)
class TuiSessionContextCommandCoordinator:
    """Own TUI context-command orchestration above command planning/execution."""

    resolve_context_command_plan: Callable[[Sequence[str]], ContextCommandPlan]
    refresh_context_snapshot_if_gateway_bound: Callable[[Any], Awaitable[None]]
    run_context_command_result: Callable[[Any, str, Sequence[str]], Awaitable[CommandExecutionResult]]
    execute_context_result: Callable[[CommandExecutionResult], None]
    runs_via_gateway: Callable[[Any], bool]
    dispatch_remote_context_update: Callable[[Any, CommandExecutionResult], Awaitable[bool]]
    normalize_context_policy_payload: Callable[[Any], dict[str, Any]]
    has_local_runtime_state: Callable[[Any], bool]
    capture_local_runtime_projection: Callable[[Any], None]
    persist_session_state: Callable[[], None]
    render_all: Callable[[], None]

    async def handle(self, session: Any, args: Sequence[str]) -> None:
        plan = self.resolve_context_command_plan(args)

        if plan.refresh_snapshot:
            await self.refresh_context_snapshot_if_gateway_bound(session)

        initial_result = await self.run_context_command_result(
            session=session,
            action=plan.action,
            args=plan.args,
        )
        if not plan.mutate_policy:
            self.execute_context_result(initial_result)
            self.render_all()
            return

        if initial_result.kind in {"usage", "error"}:
            self.execute_context_result(initial_result)
            self.render_all()
            return

        if self.runs_via_gateway(session):
            updated = await self.dispatch_remote_context_update(session, initial_result)
            if not updated:
                self.render_all()
                return
        else:
            payload = initial_result.payload if isinstance(initial_result.payload, dict) else {}
            updated_policy = payload.get("policy")
            if isinstance(updated_policy, dict):
                session.projection.context_policy = self.normalize_context_policy_payload(updated_policy)
                if self.has_local_runtime_state(session):
                    self.capture_local_runtime_projection(session)
                self.persist_session_state()

        final_result = await self.run_context_command_result(
            session=session,
            action=plan.action,
            args=plan.args,
        )
        self.execute_context_result(final_result)
        self.render_all()


__all__ = ["TuiSessionContextCommandCoordinator"]
