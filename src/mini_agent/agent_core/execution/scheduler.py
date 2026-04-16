"""Minimal scheduler state machine for agent-core execution turns."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterator

from mini_agent.agent_core.context.loop_context import TurnContext, TurnPolicySnapshot


class SchedulerState(str, Enum):
    """Scheduler states for one turn lifecycle."""

    VALIDATING = "validating"
    SCHEDULED = "scheduled"
    EXECUTING = "executing"
    COMPLETED = "completed"
    ERRORED = "errored"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class SchedulerResult:
    """Result payload for one scheduler execution."""

    state: SchedulerState
    turn_context: TurnContext
    stop_reason: str | None = None
    message: str = ""
    error: str | None = None


@contextmanager
def _turn_policy_override(agent: Any, policy: TurnPolicySnapshot) -> Iterator[None]:
    """Apply one turn-scoped execution policy and restore after completion."""
    override_policy = getattr(agent, "override_execution_policy", None)
    if callable(override_policy):
        with override_policy(policy):
            yield
        return

    had_max_steps = hasattr(agent, "max_steps")
    had_max_tool_calls = hasattr(agent, "max_tool_calls_per_step")
    had_execution_policy = hasattr(agent, "execution_policy")

    prev_max_steps = getattr(agent, "max_steps", None)
    prev_max_tool_calls = getattr(agent, "max_tool_calls_per_step", None)
    prev_execution_policy = getattr(agent, "execution_policy", None)

    try:
        if had_max_steps:
            setattr(agent, "max_steps", policy.max_steps)
        if had_max_tool_calls:
            setattr(agent, "max_tool_calls_per_step", policy.max_tool_calls_per_step)
        if had_execution_policy:
            if isinstance(prev_execution_policy, Mapping):
                updated_policy = dict(prev_execution_policy)
                updated_policy["max_steps"] = policy.max_steps
                updated_policy["max_tool_calls_per_step"] = policy.max_tool_calls_per_step
                setattr(agent, "execution_policy", updated_policy)
        yield
    finally:
        if had_max_steps:
            setattr(agent, "max_steps", prev_max_steps)
        if had_max_tool_calls:
            setattr(agent, "max_tool_calls_per_step", prev_max_tool_calls)
        if had_execution_policy:
            setattr(agent, "execution_policy", prev_execution_policy)


class TurnScheduler:
    """Minimal scheduler driving one turn with explicit states."""

    async def run(
        self,
        *,
        agent: Any,
        turn_context: TurnContext,
        cancel_event: Any | None = None,
        hooks: Any | None = None,
    ) -> SchedulerResult:
        user_input = turn_context.user_input.strip()
        if not user_input:
            return SchedulerResult(
                state=SchedulerState.ERRORED,
                turn_context=turn_context,
                message="Empty user input is not allowed.",
                error="empty_user_input",
            )

        if not hasattr(agent, "add_user_message") or not hasattr(agent, "run_turn"):
            return SchedulerResult(
                state=SchedulerState.ERRORED,
                turn_context=turn_context,
                message="Agent is missing required methods for scheduler execution.",
                error="invalid_agent_contract",
            )

        agent.add_user_message(user_input)
        try:
            with _turn_policy_override(agent, turn_context.policy):
                turn_result = await agent.run_turn(
                    cancel_event=cancel_event,
                    hooks=hooks,
                    turn_context=turn_context,
                    start_new_run=turn_context.start_new_run,
                )
        except Exception as exc:
            return SchedulerResult(
                state=SchedulerState.ERRORED,
                turn_context=turn_context,
                message=f"Scheduler execution failed: {exc}",
                error=type(exc).__name__,
            )

        stop_reason_raw = getattr(turn_result, "stop_reason", None)
        stop_reason = getattr(stop_reason_raw, "value", None) or str(stop_reason_raw or "").strip() or None
        message = str(getattr(turn_result, "message", "") or "")

        if stop_reason == "cancelled":
            return SchedulerResult(
                state=SchedulerState.INTERRUPTED,
                turn_context=turn_context,
                stop_reason=stop_reason,
                message=message,
            )

        if stop_reason == "refusal":
            return SchedulerResult(
                state=SchedulerState.ERRORED,
                turn_context=turn_context,
                stop_reason=stop_reason,
                message=message,
                error="turn_refusal",
            )

        return SchedulerResult(
            state=SchedulerState.COMPLETED,
            turn_context=turn_context,
            stop_reason=stop_reason,
            message=message,
        )
