"""Tool authorization and execution coordination for agent-core."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
import inspect
import traceback
from typing import Any, Awaitable, Callable
from uuid import uuid4

from mini_agent.agent_core.execution.permissions.policy import PermissionDecision
from mini_agent.agent_core.execution.tool_approval import ToolApprovalRequest
from mini_agent.agent_core.execution.tools.invocation import ToolInvocation
from mini_agent.tools.base import Tool, ToolResult
from mini_agent.schema.schema import Message


class ToolExecutionBatchState(str, Enum):
    """Execution states for one batch of tool calls in a planner step."""

    CONTINUE = "continue"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ToolExecutionBatchResult:
    """Result payload for one tool-call execution batch."""

    state: ToolExecutionBatchState
    message: str = ""


@dataclass(frozen=True)
class AgentToolExecutionRuntime:
    """Narrow runtime contract used by the tool-execution seam."""

    cancel_event_getter: Callable[[], asyncio.Event | None]
    cancelled_checker: Callable[[], bool]
    hook_emitter: Callable[[Any, Any], Awaitable[None]]
    tool_getter: Callable[[str], Tool | None]
    invocation_builder: Callable[[str, dict[str, object]], ToolInvocation]
    tool_approval_handler_getter: Callable[[], Any]
    runtime_policy_engine_getter: Callable[[], Any]
    approval_engine_getter: Callable[[], Any]
    message_appender: Callable[[Message], None]
    event_logger: Callable[[str, dict[str, Any], str], None]
    tool_result_logger: Callable[[str, dict[str, object], bool, str | None, str | None], None]

    def cancel_event(self) -> asyncio.Event | None:
        return self.cancel_event_getter()

    def check_cancelled(self) -> bool:
        return bool(self.cancelled_checker())

    async def emit_hook(self, callback: Any, *args: Any) -> None:
        await self.hook_emitter(callback, *args)

    def get_tool(self, tool_name: str) -> Tool | None:
        return self.tool_getter(tool_name)

    def build_tool_invocation(
        self,
        *,
        function_name: str,
        arguments: dict[str, object],
    ) -> ToolInvocation:
        return self.invocation_builder(function_name, arguments)

    def get_tool_approval_handler(self) -> Any:
        return self.tool_approval_handler_getter()

    def get_runtime_policy_engine(self) -> Any:
        return self.runtime_policy_engine_getter()

    def get_approval_engine(self) -> Any:
        return self.approval_engine_getter()

    def append_message(self, message: Message) -> None:
        self.message_appender(message)

    def log_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        level: str = "info",
    ) -> None:
        self.event_logger(event_type, payload, level)

    def log_tool_result(
        self,
        *,
        tool_name: str,
        arguments: dict[str, object],
        result_success: bool,
        result_content: str | None,
        result_error: str | None,
    ) -> None:
        self.tool_result_logger(
            tool_name,
            arguments,
            result_success,
            result_content,
            result_error,
        )


class AgentToolExecutionCoordinator:
    """Own tool authorization and execution sequencing for one agent."""

    def __init__(self, *, runtime: AgentToolExecutionRuntime, presenter: Any) -> None:
        self.runtime = runtime
        self.presenter = presenter

    def _check_cancelled(self) -> bool:
        return self.runtime.check_cancelled()

    async def _emit_hook(self, callback: Any, *args: Any) -> None:
        await self.runtime.emit_hook(callback, *args)

    async def best_effort_cancel_tool(
        self,
        *,
        step: int,
        tool_name: str,
        tool: Tool,
    ) -> bool:
        """Try to interrupt one running tool invocation."""
        cancel_running = getattr(tool, "cancel_running", None)
        if cancel_running is None:
            self.runtime.log_event(
                "tool.cancel_not_supported",
                {"step": step, "tool_name": tool_name},
                level="warning",
            )
            return False

        try:
            cancelled = cancel_running(reason="agent_cancelled")
            if inspect.isawaitable(cancelled):
                cancelled = await cancelled
            cancelled_flag = bool(cancelled)
            self.runtime.log_event(
                "tool.cancel_attempt",
                {
                    "step": step,
                    "tool_name": tool_name,
                    "cancelled": cancelled_flag,
                },
            )
            return cancelled_flag
        except Exception as exc:
            self.runtime.log_event(
                "tool.cancel_failed",
                {
                    "step": step,
                    "tool_name": tool_name,
                    "error": f"{type(exc).__name__}: {exc}",
                },
                level="warning",
            )
            return False

    async def execute_tool_with_interrupt_support(
        self,
        *,
        step: int,
        tool_name: str,
        tool: Tool,
        arguments: dict[str, object] | None = None,
        invocation: ToolInvocation | None = None,
    ) -> ToolResult:
        """Execute one tool call with cancel-event race handling."""
        if invocation is not None:
            tool_task = asyncio.create_task(invocation.execute())
        else:
            tool_task = asyncio.create_task(tool.execute(**dict(arguments or {})))
        cancel_wait_task: asyncio.Task[bool] | None = None
        try:
            cancel_event = self.runtime.cancel_event()
            if cancel_event is None:
                return await tool_task

            cancel_wait_task = asyncio.create_task(cancel_event.wait())
            done, _ = await asyncio.wait(
                {tool_task, cancel_wait_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if tool_task in done:
                return await tool_task

            self.runtime.log_event(
                "tool.cancel_requested",
                {"step": step, "tool_name": tool_name},
                level="warning",
            )
            interrupted = await self.best_effort_cancel_tool(
                step=step,
                tool_name=tool_name,
                tool=tool,
            )
            try:
                result = await asyncio.wait_for(tool_task, timeout=2)
            except asyncio.TimeoutError:
                tool_task.cancel()
                try:
                    await tool_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
                reason = "hard stop requested" if interrupted else "tool does not support hard stop"
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Tool interrupted due to cancellation request ({reason}).",
                )
            except asyncio.CancelledError:
                return ToolResult(
                    success=False,
                    content="",
                    error="Tool interrupted due to cancellation request.",
                )

            if self._check_cancelled() and result.success:
                return ToolResult(
                    success=False,
                    content="",
                    error="Tool interrupted due to cancellation request.",
                )
            return result
        finally:
            if cancel_wait_task is not None and not cancel_wait_task.done():
                cancel_wait_task.cancel()
            if cancel_wait_task is not None:
                try:
                    await cancel_wait_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

    def build_tool_invocation(
        self,
        *,
        function_name: str,
        arguments: dict[str, object],
    ) -> ToolInvocation:
        return self.runtime.build_tool_invocation(
            function_name=function_name,
            arguments=arguments,
        )

    async def request_tool_approval(
        self,
        *,
        step: int,
        invocation: ToolInvocation,
        reason: str,
        cache_key: str | None,
        can_escalate: bool,
    ) -> bool | None:
        handler = self.runtime.get_tool_approval_handler()
        if handler is None:
            return None
        request = ToolApprovalRequest(
            token=f"approval_{uuid4().hex[:12]}",
            step=step,
            tool_name=invocation.tool_name,
            arguments=dict(invocation.arguments),
            kind=invocation.attributes.kind.value,
            reason=reason,
            cache_key=cache_key,
            can_escalate=can_escalate,
        )
        maybe_awaitable = handler(request)
        if inspect.isawaitable(maybe_awaitable):
            return await maybe_awaitable
        return maybe_awaitable

    async def authorize_tool_invocation(
        self,
        *,
        step: int,
        invocation: ToolInvocation,
    ) -> ToolResult | None:
        policy_engine = self.runtime.get_runtime_policy_engine()
        if policy_engine is not None and invocation.tool_name == "bash":
            command = str(invocation.arguments.get("command") or "")
            run_in_background = bool(invocation.arguments.get("run_in_background", False))
            policy_decision = policy_engine.inspect_bash_command(
                command,
                run_in_background=run_in_background,
            )
            if not policy_decision.allowed:
                return ToolResult(
                    success=False,
                    content="",
                    error=policy_decision.reason or "Shell command blocked by runtime policy.",
                )
            if policy_decision.requires_approval:
                approval_engine = self.runtime.get_approval_engine()
                if approval_engine is None:
                    return ToolResult(
                        success=False,
                        content="",
                        error=(
                            policy_decision.reason
                            or "Shell command requires approval, but no approval engine is configured."
                        ),
                    )
                approval = approval_engine.request_escalation(
                    invocation,
                    reason=policy_decision.reason or "runtime_policy_requires_approval",
                )
                self.runtime.log_event(
                    "tool.approval.evaluated",
                    {
                        "step": step,
                        "tool_name": invocation.tool_name,
                        "decision": approval.decision.value,
                        "reason": approval.reason,
                        "requires_confirmation": approval.requires_confirmation,
                        "from_cache": approval.from_cache,
                        "runtime_policy": "elevated_shell_requires_approval",
                    },
                )
                approval_decision = await self.request_tool_approval(
                    step=step,
                    invocation=invocation,
                    reason=approval.reason,
                    cache_key=approval.cache_key,
                    can_escalate=approval.can_escalate,
                )
                if approval_decision is True:
                    approval_engine.record_user_decision(invocation, PermissionDecision.ALLOW)
                    if policy_decision.host_access_required:
                        invocation.arguments["_mini_agent_host_access_approved"] = True
                    return None
                if approval_decision is False:
                    approval_engine.record_user_decision(invocation, PermissionDecision.DENY)
                    return ToolResult(
                        success=False,
                        content="",
                        error=f"Tool execution denied by user approval for '{invocation.tool_name}'.",
                    )
                return ToolResult(
                    success=False,
                    content="",
                    error=(
                        f"Tool execution for '{invocation.tool_name}' was cancelled while waiting "
                        "for approval."
                    ),
                )

        approval_engine = self.runtime.get_approval_engine()
        if approval_engine is None:
            return None

        approval = approval_engine.evaluate(invocation)
        self.runtime.log_event(
            "tool.approval.evaluated",
            {
                "step": step,
                "tool_name": invocation.tool_name,
                "decision": approval.decision.value,
                "reason": approval.reason,
                "requires_confirmation": approval.requires_confirmation,
                "from_cache": approval.from_cache,
            },
        )

        if approval.decision == PermissionDecision.ALLOW:
            return None

        if approval.decision == PermissionDecision.DENY:
            return ToolResult(
                success=False,
                content="",
                error=(
                    f"Tool execution denied by policy for '{invocation.tool_name}' "
                    f"({approval.reason})."
                ),
            )

        approval_decision = await self.request_tool_approval(
            step=step,
            invocation=invocation,
            reason=approval.reason,
            cache_key=approval.cache_key,
            can_escalate=approval.can_escalate,
        )
        if approval_decision is True:
            approval_engine.record_user_decision(invocation, PermissionDecision.ALLOW)
            return None
        if approval_decision is False:
            approval_engine.record_user_decision(invocation, PermissionDecision.DENY)
            return ToolResult(
                success=False,
                content="",
                error=f"Tool execution denied by user approval for '{invocation.tool_name}'.",
            )
        return ToolResult(
            success=False,
            content="",
            error=(
                f"Tool execution for '{invocation.tool_name}' was cancelled while waiting "
                "for approval."
            ),
        )

    async def execute_tool_calls(
        self,
        *,
        step: int,
        tool_calls: list[Any],
        step_state: Any,
        hooks: Any | None = None,
    ) -> ToolExecutionBatchResult:
        """Run planned tool calls for one planner step."""
        if not tool_calls:
            return ToolExecutionBatchResult(
                state=ToolExecutionBatchState.COMPLETE,
                message="",
            )

        if self._check_cancelled():
            return ToolExecutionBatchResult(
                state=ToolExecutionBatchState.CANCELLED,
                message="",
            )

        for tool_call in tool_calls:
            tool_call_id = tool_call.id
            function_name = tool_call.function.name
            arguments = tool_call.function.arguments
            await self._emit_hook(
                hooks.on_tool_call_start if hooks else None,
                step,
                tool_call,
            )

            self.presenter.tool_call(function_name=function_name, arguments=arguments)
            self.runtime.log_event(
                "tool.call",
                {"step": step, "tool_name": function_name, "arguments": arguments},
            )

            tool = self.runtime.get_tool(function_name)
            if tool is None:
                result = ToolResult(
                    success=False,
                    content="",
                    error=f"Unknown tool: {function_name}",
                )
            else:
                try:
                    invocation = self.build_tool_invocation(
                        function_name=function_name,
                        arguments=arguments,
                    )
                    approval_result = await self.authorize_tool_invocation(
                        step=step,
                        invocation=invocation,
                    )
                    if approval_result is not None:
                        result = approval_result
                    else:
                        result = await self.execute_tool_with_interrupt_support(
                            step=step,
                            tool_name=function_name,
                            tool=tool,
                            invocation=invocation,
                        )
                except KeyError:
                    result = ToolResult(
                        success=False,
                        content="",
                        error=f"Unknown tool: {function_name}",
                    )
                except Exception as exc:
                    error_detail = f"{type(exc).__name__}: {str(exc)}"
                    error_trace = traceback.format_exc()
                    result = ToolResult(
                        success=False,
                        content="",
                        error=f"Tool execution failed: {error_detail}\n\nTraceback:\n{error_trace}",
                    )

            self.runtime.log_tool_result(
                tool_name=function_name,
                arguments=arguments,
                result_success=result.success,
                result_content=result.content if result.success else None,
                result_error=result.error if not result.success else None,
            )

            self.presenter.tool_result(result=result)
            await self._emit_hook(
                hooks.on_tool_call_result if hooks else None,
                step,
                tool_call,
                result,
            )

            tool_msg = Message(
                role="tool",
                content=result.content if result.success else f"Error: {result.error}",
                tool_call_id=tool_call_id,
                name=function_name,
            )
            self.runtime.append_message(tool_msg)
            step_state.executed_tool_calls += 1

            if self._check_cancelled():
                return ToolExecutionBatchResult(
                    state=ToolExecutionBatchState.CANCELLED,
                    message="",
                )

        return ToolExecutionBatchResult(
            state=ToolExecutionBatchState.CONTINUE,
            message="",
        )


__all__ = [
    "AgentToolExecutionRuntime",
    "AgentToolExecutionCoordinator",
    "ToolExecutionBatchResult",
    "ToolExecutionBatchState",
]
