"""Core Agent implementation."""

import asyncio
import inspect
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Awaitable, Callable, Optional

import tiktoken

from .llm import LLMClient
from .logger import AgentLogger
from .schema import Message, ToolCall
from .tools.base import Tool, ToolResult
from .utils import calculate_display_width


# ANSI color codes
class Colors:
    """Terminal color definitions"""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"


@dataclass(frozen=True)
class AgentExecutionPolicy:
    """Policy controls for one Agent run loop."""

    max_steps: int
    max_tool_calls_per_step: int | None = None

    def normalized(self) -> "AgentExecutionPolicy":
        normalized_max_steps = max(1, int(self.max_steps))
        normalized_tool_limit = self.max_tool_calls_per_step
        if normalized_tool_limit is not None:
            normalized_tool_limit = max(1, int(normalized_tool_limit))
        return AgentExecutionPolicy(
            max_steps=normalized_max_steps,
            max_tool_calls_per_step=normalized_tool_limit,
        )


@dataclass
class StepExecutionState:
    """Per-step execution counters used by run loops and telemetry."""

    step: int
    requested_tool_calls: int = 0
    truncated_tool_calls: int = 0
    executed_tool_calls: int = 0


@dataclass
class StepPlan:
    """Planner output for a single step."""

    step: int
    response_content: str
    response_thinking: str | None
    planned_tool_calls: list[ToolCall]
    step_state: StepExecutionState


class StepTransition(str, Enum):
    """Step transition decisions for the run state machine."""

    CONTINUE = "continue"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class StepOutcome:
    """Executor output that drives run-level state transitions."""

    transition: StepTransition
    message: str
    failure: "StepFailureEnvelope | None" = None


@dataclass(frozen=True)
class StepFailureEnvelope:
    """Structured step failure details for observability and recovery policy."""

    step: int
    phase: str
    error_type: str
    recoverable: bool
    retryable: bool
    message: str
    details: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "step": self.step,
            "phase": self.phase,
            "error_type": self.error_type,
            "recoverable": self.recoverable,
            "retryable": self.retryable,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass
class RunExecutionMetrics:
    """Per-run counters emitted in terminal run events."""

    steps_started: int = 0
    steps_completed: int = 0
    steps_failed: int = 0
    steps_cancelled: int = 0
    tool_calls_requested: int = 0
    tool_calls_truncated: int = 0
    tool_calls_executed: int = 0
    failures_by_type: dict[str, int] = field(default_factory=dict)

    def record_step_plan(self, step_state: StepExecutionState) -> None:
        self.tool_calls_requested += step_state.requested_tool_calls
        self.tool_calls_truncated += step_state.truncated_tool_calls

    def record_step_completion(self, step_state: StepExecutionState) -> None:
        self.steps_completed += 1
        self.tool_calls_executed += step_state.executed_tool_calls

    def record_failure(self, error_type: str) -> None:
        self.steps_failed += 1
        self.failures_by_type[error_type] = self.failures_by_type.get(error_type, 0) + 1

    def to_payload(self) -> dict[str, object]:
        return {
            "steps_started": self.steps_started,
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "steps_cancelled": self.steps_cancelled,
            "tool_calls_requested": self.tool_calls_requested,
            "tool_calls_truncated": self.tool_calls_truncated,
            "tool_calls_executed": self.tool_calls_executed,
            "failures_by_type": dict(self.failures_by_type),
        }


StepPlanHook = Callable[[StepPlan], Awaitable[None] | None]
ToolCallStartHook = Callable[[int, ToolCall], Awaitable[None] | None]
ToolCallResultHook = Callable[[int, ToolCall, ToolResult], Awaitable[None] | None]


@dataclass
class PlannerExecutorHooks:
    """Optional callbacks emitted by the planner/executor loop."""

    on_step_plan: StepPlanHook | None = None
    on_tool_call_start: ToolCallStartHook | None = None
    on_tool_call_result: ToolCallResultHook | None = None


class RunLoopTerminalState(str, Enum):
    """Terminal states for one planner/executor run loop."""

    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    MAX_STEPS = "max_steps"


@dataclass(frozen=True)
class RunLoopResult:
    """Terminal output for one planner/executor run loop."""

    terminal_state: RunLoopTerminalState
    message: str


class TurnStopReason(str, Enum):
    """Protocol-facing stop reasons for one conversational turn."""

    END_TURN = "end_turn"
    CANCELLED = "cancelled"
    REFUSAL = "refusal"
    MAX_TURN_REQUESTS = "max_turn_requests"


@dataclass(frozen=True)
class TurnExecutionResult:
    """Structured result for one turn execution."""

    stop_reason: TurnStopReason
    message: str


class Agent:
    """Single agent with basic tools and MCP support."""

    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str,
        tools: list[Tool],
        max_steps: int = 50,
        max_tool_calls_per_step: int | None = None,
        workspace_dir: str = "./workspace",
        token_limit: int = 80000,  # Summary triggered when tokens exceed this value
        logger: AgentLogger | None = None,
        console_output: bool = True,
    ):
        self.llm = llm_client
        self.tools = {tool.name: tool for tool in tools}
        self.execution_policy = AgentExecutionPolicy(
            max_steps=max_steps,
            max_tool_calls_per_step=max_tool_calls_per_step,
        ).normalized()
        self.max_steps = self.execution_policy.max_steps
        self.max_tool_calls_per_step = self.execution_policy.max_tool_calls_per_step
        self.token_limit = token_limit
        self.workspace_dir = Path(workspace_dir)
        self.console_output = bool(console_output)
        # Cancellation event for interrupting agent execution (set externally, e.g., by Esc key)
        self.cancel_event: Optional[asyncio.Event] = None

        # Ensure workspace exists
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Inject workspace information into system prompt if not already present
        if "Current Workspace" not in system_prompt:
            workspace_info = f"\n\n## Current Workspace\nYou are currently working in: `{self.workspace_dir.absolute()}`\nAll relative paths will be resolved relative to this directory."
            system_prompt = system_prompt + workspace_info

        self.system_prompt = system_prompt

        # Initialize message history
        self.messages: list[Message] = [Message(role="system", content=system_prompt)]

        # Initialize logger
        self.logger = logger or AgentLogger()

        # Token usage from last API response (updated after each LLM call)
        self.api_total_tokens: int = 0
        # Flag to skip token check right after summary (avoid consecutive triggers)
        self._skip_next_token_check: bool = False

    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.messages.append(Message(role="user", content=content))

    def _emit_console(self, text: str) -> None:
        if self.console_output:
            print(text)

    async def _emit_hook(
        self,
        callback: Callable[..., Awaitable[None] | None] | None,
        *args: object,
    ) -> None:
        if callback is None:
            return
        callback_result = callback(*args)
        if inspect.isawaitable(callback_result):
            await callback_result

    def _check_cancelled(self) -> bool:
        """Check if agent execution has been cancelled.

        Returns:
            True if cancelled, False otherwise.
        """
        if self.cancel_event is not None and self.cancel_event.is_set():
            return True
        return False

    def _cleanup_incomplete_messages(self):
        """Remove the incomplete assistant message and its partial tool results.

        This ensures message consistency after cancellation by removing
        only the current step's incomplete messages, preserving completed steps.
        """
        # Find the index of the last assistant message
        last_assistant_idx = -1
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].role == "assistant":
                last_assistant_idx = i
                break

        if last_assistant_idx == -1:
            # No assistant message found, nothing to clean
            return

        # Remove the last assistant message and all tool results after it
        removed_count = len(self.messages) - last_assistant_idx
        if removed_count > 0:
            self.messages = self.messages[:last_assistant_idx]
            self._emit_console(f"{Colors.DIM}   Cleaned up {removed_count} incomplete message(s){Colors.RESET}")

    def _plan_step_tool_calls(
        self,
        step: int,
        tool_calls: list[ToolCall] | None,
    ) -> tuple[list[ToolCall], StepExecutionState]:
        """Create an execution plan for tool calls in the current step."""
        requested_tool_calls = len(tool_calls or [])
        step_state = StepExecutionState(step=step, requested_tool_calls=requested_tool_calls)
        if not tool_calls:
            return [], step_state

        planned_tool_calls = list(tool_calls)
        limit = self.max_tool_calls_per_step
        if limit is not None and len(planned_tool_calls) > limit:
            step_state.truncated_tool_calls = len(planned_tool_calls) - limit
            planned_tool_calls = planned_tool_calls[:limit]
            self.logger.log_event(
                "step.tool_calls_truncated",
                {
                    "step": step,
                    "requested_tool_calls": requested_tool_calls,
                    "executed_tool_calls": len(planned_tool_calls),
                    "truncated_tool_calls": step_state.truncated_tool_calls,
                    "max_tool_calls_per_step": limit,
                },
                level="warning",
            )
            self._emit_console(
                f"{Colors.BRIGHT_YELLOW}[Guard] Step {step} tool calls truncated: "
                f"{requested_tool_calls} -> {len(planned_tool_calls)}{Colors.RESET}"
            )
        return planned_tool_calls, step_state

    def _log_step_completed(
        self,
        step_state: StepExecutionState,
        step_elapsed: float,
        total_elapsed: float,
    ) -> None:
        """Emit per-step completion telemetry."""
        self.logger.log_event(
            "step.completed",
            {
                "step": step_state.step,
                "requested_tool_calls": step_state.requested_tool_calls,
                "executed_tool_calls": step_state.executed_tool_calls,
                "truncated_tool_calls": step_state.truncated_tool_calls,
                "elapsed_seconds": step_elapsed,
                "total_elapsed_seconds": total_elapsed,
            },
        )

    def _emit_step_header(self, step: int) -> None:
        """Print the visual header for one step."""
        box_width = 58
        step_text = f"{Colors.BOLD}{Colors.BRIGHT_CYAN}[Thinking] Step {step}/{self.max_steps}{Colors.RESET}"
        step_display_width = calculate_display_width(step_text)
        padding = max(0, box_width - 1 - step_display_width)  # -1 for leading space

        horizontal = "-" * box_width
        self._emit_console(f"\n{Colors.DIM}+{horizontal}+{Colors.RESET}")
        self._emit_console(f"{Colors.DIM}|{Colors.RESET} {step_text}{' ' * padding}{Colors.DIM}|{Colors.RESET}")
        self._emit_console(f"{Colors.DIM}+{horizontal}+{Colors.RESET}")

    def _build_cancelled_outcome(self, step: int, run_start_time: float) -> StepOutcome:
        """Build and log a cancellation outcome."""
        self._cleanup_incomplete_messages()
        cancel_msg = "Task cancelled by user."
        self._emit_console(f"\n{Colors.BRIGHT_YELLOW}[!]  {cancel_msg}{Colors.RESET}")
        return StepOutcome(transition=StepTransition.CANCELLED, message=cancel_msg)

    def _build_step_failure_envelope(
        self,
        step: int,
        phase: str,
        error_type: str,
        message: str,
        recoverable: bool,
        retryable: bool,
        details: dict[str, object] | None = None,
    ) -> StepFailureEnvelope:
        """Build a structured step failure envelope."""
        return StepFailureEnvelope(
            step=step,
            phase=phase,
            error_type=error_type,
            recoverable=recoverable,
            retryable=retryable,
            message=message,
            details=details or {},
        )

    def _build_failed_outcome(
        self,
        step: int,
        error_msg: str,
        failure: StepFailureEnvelope | None = None,
    ) -> StepOutcome:
        """Build and log a step-level failure outcome."""
        payload: dict[str, object] = {
            "step": step,
            "error": error_msg,
        }
        if failure is not None:
            payload["failure"] = failure.to_payload()
        self.logger.log_event(
            "step.failed",
            payload,
            level="error",
        )
        return StepOutcome(
            transition=StepTransition.FAILED,
            message=error_msg,
            failure=failure,
        )

    def _finalize_step_timing(
        self,
        step: int,
        step_state: StepExecutionState,
        step_start_time: float,
        run_start_time: float,
    ) -> tuple[float, float]:
        """Log per-step timing and completion metrics."""
        step_elapsed = perf_counter() - step_start_time
        total_elapsed = perf_counter() - run_start_time
        self._emit_console(f"\n{Colors.DIM}[Time]  Step {step} completed in {step_elapsed:.2f}s (total: {total_elapsed:.2f}s){Colors.RESET}")
        self._log_step_completed(
            step_state=step_state,
            step_elapsed=step_elapsed,
            total_elapsed=total_elapsed,
        )
        return step_elapsed, total_elapsed

    async def _plan_step(
        self,
        step: int,
        run_start_time: float,
    ) -> StepPlan | StepOutcome:
        """Planner phase: summarize, call LLM, and plan tool execution."""
        if self._check_cancelled():
            return self._build_cancelled_outcome(step=step, run_start_time=run_start_time)

        await self._summarize_messages()
        self._emit_step_header(step=step)

        tool_list = list(self.tools.values())
        self.logger.log_request(messages=self.messages, tools=tool_list)

        try:
            response = await self.llm.generate(messages=self.messages, tools=tool_list)
        except Exception as exc:
            from .retry import RetryExhaustedError

            if isinstance(exc, RetryExhaustedError):
                error_msg = f"LLM call failed after {exc.attempts} retries\nLast error: {str(exc.last_exception)}"
                self._emit_console(f"\n{Colors.BRIGHT_RED}[Error] Retry failed:{Colors.RESET} {error_msg}")
                failure = self._build_step_failure_envelope(
                    step=step,
                    phase="planner",
                    error_type=type(exc).__name__,
                    message=error_msg,
                    recoverable=False,
                    retryable=False,
                    details={
                        "attempts": exc.attempts,
                        "last_error_type": type(exc.last_exception).__name__,
                    },
                )
            else:
                error_msg = f"LLM call failed: {str(exc)}"
                self._emit_console(f"\n{Colors.BRIGHT_RED}[Error] Error:{Colors.RESET} {error_msg}")
                failure = self._build_step_failure_envelope(
                    step=step,
                    phase="planner",
                    error_type=type(exc).__name__,
                    message=error_msg,
                    recoverable=False,
                    retryable=False,
                )
            return self._build_failed_outcome(step=step, error_msg=error_msg, failure=failure)

        if response.usage:
            self.api_total_tokens = response.usage.total_tokens

        self.logger.log_response(
            content=response.content,
            thinking=response.thinking,
            tool_calls=response.tool_calls,
            finish_reason=response.finish_reason,
        )

        assistant_msg = Message(
            role="assistant",
            content=response.content,
            thinking=response.thinking,
            tool_calls=response.tool_calls,
        )
        self.messages.append(assistant_msg)

        if response.thinking:
            self._emit_console(f"\n{Colors.BOLD}{Colors.MAGENTA}[Brain] Thinking:{Colors.RESET}")
            self._emit_console(f"{Colors.DIM}{response.thinking}{Colors.RESET}")

        if response.content:
            self._emit_console(f"\n{Colors.BOLD}{Colors.BRIGHT_BLUE}[Agent] Assistant:{Colors.RESET}")
            self._emit_console(f"{response.content}")

        planned_tool_calls, step_state = self._plan_step_tool_calls(
            step=step,
            tool_calls=response.tool_calls,
        )
        return StepPlan(
            step=step,
            response_content=response.content,
            response_thinking=response.thinking,
            planned_tool_calls=planned_tool_calls,
            step_state=step_state,
        )

    async def _execute_tool_calls(
        self,
        step: int,
        tool_calls: list[ToolCall],
        step_state: StepExecutionState,
        run_start_time: float,
        hooks: PlannerExecutorHooks | None = None,
    ) -> StepOutcome:
        """Executor phase: run planned tool calls for the current step."""
        if not tool_calls:
            return StepOutcome(
                transition=StepTransition.COMPLETE,
                message="",
            )

        if self._check_cancelled():
            return self._build_cancelled_outcome(step=step, run_start_time=run_start_time)

        for tool_call in tool_calls:
            tool_call_id = tool_call.id
            function_name = tool_call.function.name
            arguments = tool_call.function.arguments
            await self._emit_hook(
                hooks.on_tool_call_start if hooks else None,
                step,
                tool_call,
            )

            self._emit_console(f"\n{Colors.BRIGHT_YELLOW}[Tool] Tool Call:{Colors.RESET} {Colors.BOLD}{Colors.CYAN}{function_name}{Colors.RESET}")
            self.logger.log_event(
                "tool.call",
                {"step": step, "tool_name": function_name, "arguments": arguments},
            )

            self._emit_console(f"{Colors.DIM}   Arguments:{Colors.RESET}")
            truncated_args: dict[str, object] = {}
            for key, value in arguments.items():
                value_str = str(value)
                if len(value_str) > 200:
                    truncated_args[key] = value_str[:200] + "..."
                else:
                    truncated_args[key] = value
            args_json = json.dumps(truncated_args, indent=2, ensure_ascii=False)
            for line in args_json.split("\n"):
                self._emit_console(f"   {Colors.DIM}{line}{Colors.RESET}")

            if function_name not in self.tools:
                result = ToolResult(
                    success=False,
                    content="",
                    error=f"Unknown tool: {function_name}",
                )
            else:
                try:
                    tool = self.tools[function_name]
                    result = await tool.execute(**arguments)
                except Exception as exc:
                    import traceback

                    error_detail = f"{type(exc).__name__}: {str(exc)}"
                    error_trace = traceback.format_exc()
                    result = ToolResult(
                        success=False,
                        content="",
                        error=f"Tool execution failed: {error_detail}\n\nTraceback:\n{error_trace}",
                    )

            self.logger.log_tool_result(
                tool_name=function_name,
                arguments=arguments,
                result_success=result.success,
                result_content=result.content if result.success else None,
                result_error=result.error if not result.success else None,
            )

            if result.success:
                result_text = result.content
                if len(result_text) > 300:
                    result_text = result_text[:300] + f"{Colors.DIM}...{Colors.RESET}"
                self._emit_console(f"{Colors.BRIGHT_GREEN}[OK] Result:{Colors.RESET} {result_text}")
            else:
                self._emit_console(f"{Colors.BRIGHT_RED}[X] Error:{Colors.RESET} {Colors.RED}{result.error}{Colors.RESET}")
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
            self.messages.append(tool_msg)
            step_state.executed_tool_calls += 1

            if self._check_cancelled():
                return self._build_cancelled_outcome(step=step, run_start_time=run_start_time)

        return StepOutcome(
            transition=StepTransition.CONTINUE,
            message="",
        )

    def _estimate_tokens(self) -> int:
        """Accurately calculate token count for message history using tiktoken

        Uses cl100k_base encoder (GPT-4/Claude/M2 compatible)
        """
        try:
            # Use cl100k_base encoder (used by GPT-4 and most modern models)
            encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            # Fallback: if tiktoken initialization fails, use simple estimation
            return self._estimate_tokens_fallback()

        total_tokens = 0

        for msg in self.messages:
            # Count text content
            if isinstance(msg.content, str):
                total_tokens += len(encoding.encode(msg.content))
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        # Convert dict to string for calculation
                        total_tokens += len(encoding.encode(str(block)))

            # Count thinking
            if msg.thinking:
                total_tokens += len(encoding.encode(msg.thinking))

            # Count tool_calls
            if msg.tool_calls:
                total_tokens += len(encoding.encode(str(msg.tool_calls)))

            # Metadata overhead per message (approximately 4 tokens)
            total_tokens += 4

        return total_tokens

    def _estimate_tokens_fallback(self) -> int:
        """Fallback token estimation method (when tiktoken is unavailable)"""
        total_chars = 0
        for msg in self.messages:
            if isinstance(msg.content, str):
                total_chars += len(msg.content)
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        total_chars += len(str(block))

            if msg.thinking:
                total_chars += len(msg.thinking)

            if msg.tool_calls:
                total_chars += len(str(msg.tool_calls))

        # Rough estimation: average 2.5 characters = 1 token
        return int(total_chars / 2.5)

    async def _summarize_messages(self):
        """Message history summarization: summarize conversations between user messages when tokens exceed limit

        Strategy (Agent mode):
        - Keep all user messages (these are user intents)
        - Summarize content between each user-user pair (agent execution process)
        - If last round is still executing (has agent/tool messages but no next user), also summarize
        - Structure: system -> user1 -> summary1 -> user2 -> summary2 -> user3 -> summary3 (if executing)

        Summary is triggered when EITHER:
        - Local token estimation exceeds limit
        - API reported total_tokens exceeds limit
        """
        # Skip check if we just completed a summary (wait for next LLM call to update api_total_tokens)
        if self._skip_next_token_check:
            self._skip_next_token_check = False
            return

        estimated_tokens = self._estimate_tokens()

        # Check both local estimation and API reported tokens
        should_summarize = estimated_tokens > self.token_limit or self.api_total_tokens > self.token_limit

        # If neither exceeded, no summary needed
        if not should_summarize:
            return

        self._emit_console(
            f"\n{Colors.BRIGHT_YELLOW}[Stats] Token usage - Local estimate: {estimated_tokens}, API reported: {self.api_total_tokens}, Limit: {self.token_limit}{Colors.RESET}"
        )
        self._emit_console(f"{Colors.BRIGHT_YELLOW}[...] Triggering message history summarization...{Colors.RESET}")

        # Find all user message indices (skip system prompt)
        user_indices = [i for i, msg in enumerate(self.messages) if msg.role == "user" and i > 0]

        # Need at least 1 user message to perform summary
        if len(user_indices) < 1:
            self._emit_console(f"{Colors.BRIGHT_YELLOW}[!]  Insufficient messages, cannot summarize{Colors.RESET}")
            return

        # Build new message list
        new_messages = [self.messages[0]]  # Keep system prompt
        summary_count = 0

        # Iterate through each user message and summarize the execution process after it
        for i, user_idx in enumerate(user_indices):
            # Add current user message
            new_messages.append(self.messages[user_idx])

            # Determine message range to summarize
            # If last user, go to end of message list; otherwise to before next user
            if i < len(user_indices) - 1:
                next_user_idx = user_indices[i + 1]
            else:
                next_user_idx = len(self.messages)

            # Extract execution messages for this round
            execution_messages = self.messages[user_idx + 1 : next_user_idx]

            # If there are execution messages in this round, summarize them
            if execution_messages:
                summary_text = await self._create_summary(execution_messages, i + 1)
                if summary_text:
                    summary_message = Message(
                        role="user",
                        content=f"[Assistant Execution Summary]\n\n{summary_text}",
                    )
                    new_messages.append(summary_message)
                    summary_count += 1

        # Replace message list
        self.messages = new_messages

        # Skip next token check to avoid consecutive summary triggers
        # (api_total_tokens will be updated after next LLM call)
        self._skip_next_token_check = True

        new_tokens = self._estimate_tokens()
        self._emit_console(f"{Colors.BRIGHT_GREEN}[OK] Summary completed, local tokens: {estimated_tokens} 鈫?{new_tokens}{Colors.RESET}")
        self._emit_console(f"{Colors.DIM}  Structure: system + {len(user_indices)} user messages + {summary_count} summaries{Colors.RESET}")
        self._emit_console(f"{Colors.DIM}  Note: API token count will update on next LLM call{Colors.RESET}")

    async def _create_summary(self, messages: list[Message], round_num: int) -> str:
        """Create summary for one execution round

        Args:
            messages: List of messages to summarize
            round_num: Round number

        Returns:
            Summary text
        """
        if not messages:
            return ""

        # Build summary content
        summary_content = f"Round {round_num} execution process:\n\n"
        for msg in messages:
            if msg.role == "assistant":
                content_text = msg.content if isinstance(msg.content, str) else str(msg.content)
                summary_content += f"Assistant: {content_text}\n"
                if msg.tool_calls:
                    tool_names = [tc.function.name for tc in msg.tool_calls]
                    summary_content += f"  鈫?Called tools: {', '.join(tool_names)}\n"
            elif msg.role == "tool":
                result_preview = msg.content if isinstance(msg.content, str) else str(msg.content)
                summary_content += f"  鈫?Tool returned: {result_preview}...\n"

        # Call LLM to generate concise summary
        try:
            summary_prompt = f"""Please provide a concise summary of the following Agent execution process:

{summary_content}

Requirements:
1. Focus on what tasks were completed and which tools were called
2. Keep key execution results and important findings
3. Be concise and clear, within 1000 words
4. Use English
5. Do not include "user" related content, only summarize the Agent's execution process"""

            summary_msg = Message(role="user", content=summary_prompt)
            response = await self.llm.generate(
                messages=[
                    Message(
                        role="system",
                        content="You are an assistant skilled at summarizing Agent execution processes.",
                    ),
                    summary_msg,
                ]
            )

            summary_text = response.content
            self._emit_console(f"{Colors.BRIGHT_GREEN}[OK] Summary for round {round_num} generated successfully{Colors.RESET}")
            return summary_text

        except Exception as e:
            self._emit_console(f"{Colors.BRIGHT_RED}[X] Summary generation failed for round {round_num}: {e}{Colors.RESET}")
            # Use simple text summary on failure
            return summary_content

    def _start_run_logging(self) -> None:
        self.logger.start_new_run(workspace=self.workspace_dir)
        self._emit_console(f"{Colors.DIM}[Note] Log file: {self.logger.get_log_file_path()}{Colors.RESET}")
        self._emit_console(f"{Colors.DIM}[Note] Event log: {self.logger.get_event_file_path()}{Colors.RESET}")
        self.logger.log_event(
            "run.start",
            {
                "workspace": str(self.workspace_dir),
                "max_steps": self.max_steps,
                "max_tool_calls_per_step": self.max_tool_calls_per_step,
                "tool_count": len(self.tools),
            },
        )

    def _log_cancelled_run(
        self,
        step: int,
        run_start_time: float,
        run_metrics: RunExecutionMetrics,
    ) -> None:
        self.logger.log_event(
            "run.cancelled",
            {
                "step": step,
                "elapsed_seconds": perf_counter() - run_start_time,
                "metrics": run_metrics.to_payload(),
            },
            level="warning",
        )

    def _log_failed_run(
        self,
        step: int,
        message: str,
        run_start_time: float,
        run_metrics: RunExecutionMetrics,
        failure: StepFailureEnvelope | None = None,
    ) -> None:
        failure_payload: dict[str, object] = {}
        if failure is not None:
            run_metrics.record_failure(failure.error_type)
            failure_payload["failure"] = failure.to_payload()
        else:
            run_metrics.steps_failed += 1
        self.logger.log_event(
            "run.failed",
            {
                "step": step,
                "error": message,
                **failure_payload,
                "elapsed_seconds": perf_counter() - run_start_time,
                "metrics": run_metrics.to_payload(),
            },
            level="error",
        )

    async def _run_planner_executor_loop(
        self,
        *,
        cancel_event: asyncio.Event | None = None,
        hooks: PlannerExecutorHooks | None = None,
        start_new_run: bool = True,
    ) -> RunLoopResult:
        if cancel_event is not None:
            self.cancel_event = cancel_event

        if start_new_run:
            self._start_run_logging()

        run_start_time = perf_counter()
        run_metrics = RunExecutionMetrics()

        for step in range(1, self.max_steps + 1):
            self.logger.log_event("step.start", {"step": step, "max_steps": self.max_steps})
            run_metrics.steps_started += 1
            step_start_time = perf_counter()

            plan_or_outcome = await self._plan_step(step=step, run_start_time=run_start_time)
            if isinstance(plan_or_outcome, StepOutcome):
                if plan_or_outcome.transition == StepTransition.CANCELLED:
                    run_metrics.steps_cancelled += 1
                    self._log_cancelled_run(
                        step=step,
                        run_start_time=run_start_time,
                        run_metrics=run_metrics,
                    )
                    return RunLoopResult(
                        terminal_state=RunLoopTerminalState.CANCELLED,
                        message=plan_or_outcome.message,
                    )
                if plan_or_outcome.transition == StepTransition.FAILED:
                    self._log_failed_run(
                        step=step,
                        message=plan_or_outcome.message,
                        run_start_time=run_start_time,
                        run_metrics=run_metrics,
                        failure=plan_or_outcome.failure,
                    )
                    return RunLoopResult(
                        terminal_state=RunLoopTerminalState.FAILED,
                        message=plan_or_outcome.message,
                    )
                continue

            step_plan = plan_or_outcome
            run_metrics.record_step_plan(step_plan.step_state)
            await self._emit_hook(hooks.on_step_plan if hooks else None, step_plan)

            execution_outcome = await self._execute_tool_calls(
                step=step,
                tool_calls=step_plan.planned_tool_calls,
                step_state=step_plan.step_state,
                run_start_time=run_start_time,
                hooks=hooks,
            )
            if execution_outcome.transition in {StepTransition.CANCELLED, StepTransition.FAILED}:
                run_metrics.tool_calls_executed += step_plan.step_state.executed_tool_calls
                if execution_outcome.transition == StepTransition.CANCELLED:
                    run_metrics.steps_cancelled += 1
                    self._log_cancelled_run(
                        step=step,
                        run_start_time=run_start_time,
                        run_metrics=run_metrics,
                    )
                    return RunLoopResult(
                        terminal_state=RunLoopTerminalState.CANCELLED,
                        message=execution_outcome.message,
                    )

                self._log_failed_run(
                    step=step,
                    message=execution_outcome.message,
                    run_start_time=run_start_time,
                    run_metrics=run_metrics,
                    failure=execution_outcome.failure,
                )
                return RunLoopResult(
                    terminal_state=RunLoopTerminalState.FAILED,
                    message=execution_outcome.message,
                )

            _, total_elapsed = self._finalize_step_timing(
                step=step,
                step_state=step_plan.step_state,
                step_start_time=step_start_time,
                run_start_time=run_start_time,
            )
            run_metrics.record_step_completion(step_plan.step_state)
            if execution_outcome.transition == StepTransition.COMPLETE:
                self.logger.log_event(
                    "run.completed",
                    {
                        "steps": step,
                        "elapsed_seconds": total_elapsed,
                        "metrics": run_metrics.to_payload(),
                    },
                )
                return RunLoopResult(
                    terminal_state=RunLoopTerminalState.COMPLETED,
                    message=step_plan.response_content,
                )

        error_msg = f"Task couldn't be completed after {self.max_steps} steps."
        self._emit_console(f"\n{Colors.BRIGHT_YELLOW}[!]  {error_msg}{Colors.RESET}")
        self.logger.log_event(
            "run.max_steps",
            {
                "max_steps": self.max_steps,
                "elapsed_seconds": perf_counter() - run_start_time,
                "metrics": run_metrics.to_payload(),
            },
            level="warning",
        )
        return RunLoopResult(
            terminal_state=RunLoopTerminalState.MAX_STEPS,
            message=error_msg,
        )

    async def run(self, cancel_event: Optional[asyncio.Event] = None) -> str:
        """Execute agent loop until task is complete or max steps reached."""
        run_result = await self._run_planner_executor_loop(
            cancel_event=cancel_event,
            hooks=None,
            start_new_run=True,
        )
        return run_result.message

    async def run_turn(
        self,
        *,
        cancel_event: asyncio.Event | None = None,
        hooks: PlannerExecutorHooks | None = None,
        start_new_run: bool = True,
    ) -> TurnExecutionResult:
        """Execute one conversational turn using the shared planner/executor loop."""
        run_result = await self._run_planner_executor_loop(
            cancel_event=cancel_event,
            hooks=hooks,
            start_new_run=start_new_run,
        )
        if run_result.terminal_state == RunLoopTerminalState.COMPLETED:
            stop_reason = TurnStopReason.END_TURN
        elif run_result.terminal_state == RunLoopTerminalState.CANCELLED:
            stop_reason = TurnStopReason.CANCELLED
        elif run_result.terminal_state == RunLoopTerminalState.FAILED:
            stop_reason = TurnStopReason.REFUSAL
        else:
            stop_reason = TurnStopReason.MAX_TURN_REQUESTS
        return TurnExecutionResult(
            stop_reason=stop_reason,
            message=run_result.message,
        )

    def get_history(self) -> list[Message]:
        """Get message history."""
        return self.messages.copy()


