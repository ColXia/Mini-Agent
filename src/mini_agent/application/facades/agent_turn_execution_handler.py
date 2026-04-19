"""Surface-neutral single-turn agent execution orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from uuid import uuid4

from mini_agent.agent_core.engine import PlannerExecutorHooks, ToolApprovalRequest, TurnExecutionResult, TurnStopReason
from mini_agent.agent_core.runtime_bindings import override_agent_tool_approval_handler
from mini_agent.application.support import ManagedSessionTurn
from mini_agent.runtime.support.interaction_surface import resolve_interaction_binding
from mini_agent.schema import LLMStreamEvent, LLMStreamEventType


SurfaceActivityEmitter = Callable[[str, dict[str, Any]], Awaitable[None] | None]


@dataclass(frozen=True)
class SurfaceAgentExecutionRequest:
    message: str
    surface: str | None
    recovery_context: dict[str, Any] | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    activity_emitter: SurfaceActivityEmitter | None = None


@dataclass(slots=True)
class AgentTurnExecutionHandler:
    """Owns single-turn agent execution plus runtime approval/activity hooks."""

    async def run_agent_once(
        self,
        turn: ManagedSessionTurn,
        request: SurfaceAgentExecutionRequest,
    ) -> TurnExecutionResult:
        interaction = resolve_interaction_binding(
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
            default_surface="api",
        )
        normalized_surface = interaction.surface or "api"
        normalized_channel_type = interaction.channel_type
        assistant_id = uuid4().hex
        hooks = self._build_runtime_activity_hooks(
            turn,
            surface=normalized_surface,
            channel_type=normalized_channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
            activity_emitter=request.activity_emitter,
            assistant_id=assistant_id,
        )
        approval_handler = self._build_runtime_approval_handler(
            turn,
            surface=normalized_surface,
            channel_type=normalized_channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
            activity_emitter=request.activity_emitter,
        )
        turn.agent.add_user_message(request.message)
        turn.restore_prepared_context_state()
        cancel_event = turn.cancel_event
        with override_agent_tool_approval_handler(turn.agent, approval_handler):
            if hasattr(turn.agent, "run_turn"):
                reply = await turn.agent.run_turn(
                    cancel_event=cancel_event,
                    hooks=hooks,
                    turn_context={
                        "session_id": turn.session_id,
                        "submission_id": f"gateway:{turn.session_id}",
                        "user_input": request.message,
                        "metadata": {
                            "surface": normalized_surface,
                            "channel_type": normalized_channel_type,
                            "entrance": interaction.entrance,
                            "remote_channel": interaction.remote_channel,
                            "conversation_id": request.conversation_id,
                            "sender_id": request.sender_id,
                            "prepared_context_policy": dict(turn.context_policy),
                            **(
                                {"recovery": dict(request.recovery_context)}
                                if isinstance(request.recovery_context, dict)
                                else {}
                            ),
                        },
                        "workspace_dir": str(turn.workspace_dir),
                    },
                    start_new_run=True,
                )
            else:  # pragma: no cover - legacy defensive branch
                message_text = await turn.agent.run(cancel_event=cancel_event)
                reply = TurnExecutionResult(stop_reason=TurnStopReason.END_TURN, message=message_text)
        turn.touch()
        return reply

    def _build_runtime_approval_handler(
        self,
        turn: ManagedSessionTurn,
        *,
        surface: str | None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        activity_emitter: SurfaceActivityEmitter | None = None,
    ) -> Callable[[ToolApprovalRequest], Awaitable[bool | None]]:
        async def _emit(event_type: str, payload: dict[str, Any]) -> None:
            if activity_emitter is None:
                return
            await activity_emitter(event_type, payload)

        async def _handle(request: ToolApprovalRequest) -> bool | None:
            token = str(getattr(request, "token", "") or "").strip() or f"approval_{uuid4().hex[:12]}"
            normalized_payload = {
                "token": token,
                "tool_name": str(getattr(request, "tool_name", "") or "").strip() or "tool",
                "arguments": dict(getattr(request, "arguments", {}) or {}),
                "kind": str(getattr(request, "kind", "") or "").strip() or None,
                "reason": str(getattr(request, "reason", "") or "").strip() or None,
                "cache_key": str(getattr(request, "cache_key", "") or "").strip() or None,
                "can_escalate": bool(getattr(request, "can_escalate", False)),
                "step": int(getattr(request, "step", 0) or 0),
            }
            future: asyncio.Future[bool | None] = asyncio.get_running_loop().create_future()
            turn.record_pending_approval(
                payload=normalized_payload,
                future=future,
            )
            detail = f"approval required for {normalized_payload['tool_name']}"
            item = turn.record_activity(
                label="approval",
                detail=detail,
                surface=surface,
                activity_id=f"approval:{token}",
                preview=self._tool_activity_preview_from_arguments(normalized_payload["arguments"]),
                state="pending",
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            turn.running_state = detail
            await _emit("approval_requested", normalized_payload)
            await _emit(
                "activity",
                {
                    **item,
                    "token": token,
                    "tool_name": normalized_payload["tool_name"],
                    "running_state": detail,
                },
            )
            try:
                decision = await future
            finally:
                turn.clear_pending_approval(token=token)
            decision_label = "approved" if decision is True else ("denied" if decision is False else "cancelled")
            resolved_detail = f"{decision_label} for {normalized_payload['tool_name']}"
            resolved_item = turn.record_activity(
                label="approval",
                detail=resolved_detail,
                surface=surface,
                activity_id=f"approval:{token}",
                state="ok" if decision is True else "failed",
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            if not turn.pending_approvals and turn.busy:
                turn.running_state = f"continuing after {decision_label}"
            await _emit(
                "approval_resolved",
                {
                    "token": token,
                    "tool_name": normalized_payload["tool_name"],
                    "decision": decision_label,
                    "approved": decision is True,
                },
            )
            await _emit(
                "activity",
                {
                    **resolved_item,
                    "token": token,
                    "tool_name": normalized_payload["tool_name"],
                    "running_state": turn.running_state or resolved_detail,
                },
            )
            return decision

        return _handle

    def _build_runtime_activity_hooks(
        self,
        turn: ManagedSessionTurn,
        *,
        surface: str | None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        activity_emitter: SurfaceActivityEmitter | None = None,
        assistant_id: str,
    ) -> PlannerExecutorHooks:
        async def _emit_activity(payload: dict[str, Any]) -> None:
            if activity_emitter is None:
                return
            await activity_emitter("activity", payload)

        async def _on_llm_event(step: int, event: LLMStreamEvent) -> None:
            if activity_emitter is None:
                return
            if event.type == LLMStreamEventType.TEXT_DELTA and event.delta:
                await activity_emitter(
                    "delta",
                    {
                        "assistant_id": assistant_id,
                        "chunk": event.delta,
                        "step": step,
                    },
                )
                return
            if event.type == LLMStreamEventType.THINKING_DELTA and event.delta:
                await activity_emitter(
                    "thinking_delta",
                    {
                        "assistant_id": assistant_id,
                        "chunk": event.delta,
                        "step": step,
                    },
                )

        async def _on_step_plan(step_plan: Any) -> None:
            step = getattr(step_plan, "step", "?")
            planned_tool_calls = getattr(step_plan, "planned_tool_calls", None)
            tool_count = len(planned_tool_calls) if isinstance(planned_tool_calls, list) else 0
            if tool_count > 0:
                detail = f"step {step}: planned {tool_count} tool call(s)"
            else:
                detail = f"step {step}: preparing final response"
            item = turn.record_activity(
                label="thinking",
                detail=detail,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            await _emit_activity({**item, "running_state": detail})

        async def _on_tool_call_start(step: int, tool_call: Any) -> None:
            tool_name = self._tool_name_from_hook(tool_call)
            detail = "running"
            running_state = f"step {step}: running {tool_name}"
            item = turn.record_activity(
                label=tool_name,
                detail=detail,
                surface=surface,
                activity_id=self._tool_call_key(step, tool_call),
                preview=self._tool_activity_preview(tool_call),
                state="running",
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            await _emit_activity({**item, "running_state": running_state})

        async def _on_tool_call_result(step: int, tool_call: Any, result: Any) -> None:
            tool_name = self._tool_name_from_hook(tool_call)
            outcome = "ok" if bool(getattr(result, "success", False)) else "failed"
            output_text = ""
            if self._activity_has_output(tool_name, result):
                output_text = self._tool_result_output_text(result)
            elif outcome == "failed":
                output_text = str(getattr(result, "error", "") or "")
            running_state = f"step {step}: {tool_name} {outcome}"
            item = turn.record_activity(
                label=tool_name,
                detail=outcome,
                surface=surface,
                activity_id=self._tool_call_key(step, tool_call),
                preview=self._tool_activity_preview(tool_call),
                output_text=output_text,
                state=outcome,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            await _emit_activity({**item, "running_state": running_state})

        return PlannerExecutorHooks(
            on_step_plan=_on_step_plan,
            on_llm_event=_on_llm_event,
            on_tool_call_start=_on_tool_call_start,
            on_tool_call_result=_on_tool_call_result,
        )

    @staticmethod
    def _tool_name_from_hook(tool_call: Any) -> str:
        function_obj = getattr(tool_call, "function", None)
        if function_obj is not None:
            function_name = str(getattr(function_obj, "name", "") or "").strip()
            if function_name:
                return function_name
        return str(getattr(tool_call, "name", "") or "").strip() or "tool"

    @staticmethod
    def _tool_call_key(step: int, tool_call: Any) -> str:
        tool_call_id = str(getattr(tool_call, "id", "") or "").strip()
        if tool_call_id:
            return tool_call_id
        function_obj = getattr(tool_call, "function", None)
        function_name = str(getattr(function_obj, "name", "") or "").strip() or "tool"
        return f"step-{step}:{function_name}"

    @staticmethod
    def _tool_arguments_from_hook(tool_call: Any) -> dict[str, Any]:
        function_obj = getattr(tool_call, "function", None)
        arguments = getattr(function_obj, "arguments", None)
        return arguments if isinstance(arguments, dict) else {}

    def _tool_activity_preview(self, tool_call: Any) -> str:
        arguments = self._tool_arguments_from_hook(tool_call)
        return self._tool_activity_preview_from_arguments(arguments)

    @staticmethod
    def _tool_activity_preview_from_arguments(arguments: dict[str, Any]) -> str:
        if not arguments:
            return ""
        preview_keys = (
            "command",
            "query",
            "q",
            "prompt",
            "pattern",
            "path",
            "url",
            "model",
            "provider_id",
            "name",
        )
        for key in preview_keys:
            if key not in arguments:
                continue
            value = arguments.get(key)
            if isinstance(value, (list, tuple)):
                preview = ", ".join(str(item).strip() for item in value if str(item).strip())
            else:
                preview = str(value or "").strip()
            if not preview:
                continue
            if key == "command" and bool(arguments.get("run_in_background")):
                preview = f"{preview} [bg]"
            return preview[:69] + "..." if len(preview) > 72 else preview
        return ""

    @staticmethod
    def _activity_has_output(label: str, result: Any) -> bool:
        normalized = str(label or "").strip().lower()
        return normalized.startswith("shell") or hasattr(result, "stdout") or hasattr(result, "stderr")

    @staticmethod
    def _tool_result_output_text(result: Any) -> str:
        blocks: list[str] = []
        stdout = str(getattr(result, "stdout", "") or "").strip()
        stderr = str(getattr(result, "stderr", "") or "").strip()
        content = str(getattr(result, "content", "") or "").strip()
        bash_id = str(getattr(result, "bash_id", "") or "").strip()
        exit_code = getattr(result, "exit_code", None)

        if stdout:
            blocks.append(stdout)
        elif content:
            blocks.append(content)
        if stderr:
            blocks.append("[stderr]")
            blocks.append(stderr)
        if bash_id:
            blocks.append(f"[bash_id] {bash_id}")
        if exit_code is not None:
            blocks.append(f"[exit_code] {exit_code}")
        return "\n".join(blocks).strip()


__all__ = [
    "SurfaceActivityEmitter",
    "AgentTurnExecutionHandler",
    "SurfaceAgentExecutionRequest",
]
