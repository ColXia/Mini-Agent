"""Shared TUI model-command orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from typing import Any, Callable

from mini_agent.commands import CommandExecutionResult


@dataclass(slots=True)
class TuiSessionModelCommandCoordinator:
    """Own TUI model-command orchestration above model/runtime helpers."""

    resolve_model_command_plan: Callable[[Sequence[str]], Any]
    provider_inventory: Callable[[], Sequence[dict[str, Any]]]
    render_model_summary: Callable[[], str]
    move_model_cursor: Callable[[int], None]
    apply_selected_model: Callable[[], Awaitable[None]]
    discover_for_selected_provider: Callable[[], Awaitable[None]]
    refresh_registry: Callable[[], None]
    apply_session_model_selection: Callable[[Any, tuple[str, str, str]], Awaitable[None]]
    model_use_usage_details: Callable[[], str]
    set_model_filter: Callable[[str], None]
    model_filter_value: Callable[[], str]
    execute_model_limit_command_plan: Callable[[Any], None]
    append_command_feedback: Callable[..., None]
    set_status: Callable[[str], None]
    render_all: Callable[[], None]

    async def handle(self, session: Any, args: Sequence[str]) -> None:
        plan = self.resolve_model_command_plan(args)
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

        if plan.action == "list":
            providers = list(self.provider_inventory())
            provider_count = len(providers)
            model_count = sum(
                len(provider.get("models", []))
                for provider in providers
                if isinstance(provider.get("models", []), list)
            )
            details = "Models:\n" + self.render_model_summary()
            self.append_command_feedback(
                plan.command,
                summary=f"{provider_count} provider(s), {model_count} model(s)",
                details=details,
            )
            self.set_status("Listed providers/models.")
        elif plan.action == "cursor":
            self.move_model_cursor(plan.cursor_delta)
        elif plan.action == "apply":
            await self.apply_selected_model()
        elif plan.action == "discover":
            await self.discover_for_selected_provider()
        elif plan.action == "refresh":
            self.refresh_registry()
            self.set_status("Refreshed model registry.")
        elif plan.action == "use":
            request = plan.request
            if request is None:
                self.append_command_feedback(
                    plan.command,
                    summary="usage",
                    details=self.model_use_usage_details(),
                    level="error",
                )
                self.set_status("Model use requires provider_id and model_id.")
                self.render_all()
                return
            try:
                await self.apply_session_model_selection(session, request.identity)
            except Exception as exc:
                message = f"Model switch failed: {exc}"
                self.append_command_feedback(
                    plan.command,
                    summary="model switch failed",
                    details=message,
                    level="error",
                )
                self.set_status(message)
        elif plan.action == "filter_clear":
            self.set_model_filter("")
            self.set_status("Model filter cleared.")
        elif plan.action == "filter_set":
            self.set_model_filter(plan.filter_value or "")
            self.set_status(f"Model filter set to: {self.model_filter_value()}")
        else:
            self.execute_model_limit_command_plan(plan)
        self.render_all()


__all__ = ["TuiSessionModelCommandCoordinator"]
