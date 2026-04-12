"""Core Agent implementation."""

import asyncio
import inspect
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4

import tiktoken

from mini_agent.code_agent.context_compression import LayeredContextCompactor, estimate_tokens
from mini_agent.code_agent.permissions.approval import ApprovalEngine
from mini_agent.code_agent.permissions.policy import PermissionDecision
from mini_agent.code_agent.tools.builder import build_declarative_registry
from mini_agent.code_agent.tools.invocation import ToolInvocation
from mini_agent.memory.automation import TurnMemoryAutomation
from mini_agent.memory.runtime_task_memory import TurnRuntimeTaskMemory
from mini_agent.model_manager.error_classifier import (
    ProviderErrorClassification,
    classify_provider_error,
)
from mini_agent.model_manager.failover import ProviderFailoverError
from mini_agent.model_manager.model_registry_service import ModelRegistryService
from mini_agent.turn_context import (
    coerce_runtime_turn_context,
    context_policy_summary_line,
    curate_turn_context_items,
    format_turn_context_block,
    normalize_turn_context_items,
    provider_allowed_by_policy,
    resolve_turn_context_policy,
    summarize_turn_context_items,
    update_prepared_context_diagnostics,
)

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


@dataclass(frozen=True)
class ToolApprovalRequest:
    """Interactive approval request for one tool invocation."""

    token: str
    step: int
    tool_name: str
    arguments: dict[str, Any]
    kind: str
    reason: str
    cache_key: str | None = None
    can_escalate: bool = False


class Agent:
    """Single agent with basic tools and MCP support."""

    _TURN_CONTEXT_MESSAGE_NAME = "__mini_agent_turn_context__"
    _KNOWLEDGE_BASE_TOOL_NAME = "knowledge_base_query"

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
        approval_engine: ApprovalEngine | None = None,
        tool_approval_handler: Callable[[ToolApprovalRequest], Awaitable[bool | None] | bool | None] | None = None,
        runtime_policy_engine: Any | None = None,
        sandbox_manager: Any | None = None,
        context_compactor: LayeredContextCompactor | None = None,
        turn_context_providers: list[Any] | None = None,
        turn_context_max_items: int = 4,
        turn_context_max_items_per_source: int = 1,
        turn_context_max_total_chars: int = 2400,
        turn_memory_automation: TurnMemoryAutomation | None = None,
        turn_runtime_task_memory: TurnRuntimeTaskMemory | None = None,
    ):
        self.llm = llm_client
        self.llm_client = llm_client
        self._tool_catalog = {tool.name: tool for tool in tools}
        self.tools = dict(self._tool_catalog)
        self.declarative_tools = build_declarative_registry(self.tools.values())
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
        self.approval_engine = approval_engine
        self.tool_approval_handler = tool_approval_handler
        self.runtime_policy_engine = runtime_policy_engine
        self.sandbox_manager = sandbox_manager
        self.context_compactor = context_compactor
        self.turn_context_providers = list(turn_context_providers or [])
        self.turn_context_max_items = max(1, int(turn_context_max_items))
        self.turn_context_max_items_per_source = max(1, int(turn_context_max_items_per_source))
        self.turn_context_max_total_chars = max(200, int(turn_context_max_total_chars))
        self.last_prepared_turn_context: dict[str, Any] | None = None
        self.prepared_context_diagnostics: dict[str, Any] = {}
        self.turn_memory_automation = turn_memory_automation
        self.last_memory_automation: dict[str, Any] = {}
        self.turn_runtime_task_memory = turn_runtime_task_memory
        self.last_runtime_task_memory: dict[str, Any] = {}

        # Token usage from last API response (updated after each LLM call)
        self.api_total_tokens: int = 0
        # Flag to skip token check right after summary (avoid consecutive triggers)
        self._skip_next_token_check: bool = False

    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.messages.append(Message(role="user", content=content))

    def _refresh_tool_registry(self) -> None:
        self.declarative_tools = build_declarative_registry(self.tools.values())

    def _build_lazy_tool(self, tool_name: str) -> Tool | None:
        normalized_name = str(tool_name or "").strip().lower()
        if normalized_name != self._KNOWLEDGE_BASE_TOOL_NAME:
            return None
        from mini_agent.tools.knowledge_base import KnowledgeBaseQueryTool

        return KnowledgeBaseQueryTool(workspace_dir=self.workspace_dir)

    def is_tool_enabled(self, tool_name: str) -> bool:
        normalized_name = str(tool_name or "").strip()
        return bool(normalized_name and normalized_name in self.tools)

    def set_tool_enabled(self, tool_name: str, enabled: bool) -> bool:
        normalized_name = str(tool_name or "").strip()
        if not normalized_name:
            return False

        desired_state = bool(enabled)
        current_state = normalized_name in self.tools
        if desired_state == current_state:
            return current_state

        if desired_state:
            tool = self._tool_catalog.get(normalized_name)
            if tool is None:
                tool = self._build_lazy_tool(normalized_name)
                if tool is None:
                    return False
                self._tool_catalog[normalized_name] = tool
            self.tools[normalized_name] = tool
        else:
            self.tools.pop(normalized_name, None)

        self._refresh_tool_registry()
        return normalized_name in self.tools

    def knowledge_base_enabled(self) -> bool:
        return self.is_tool_enabled(self._KNOWLEDGE_BASE_TOOL_NAME)

    def set_knowledge_base_enabled(self, enabled: bool) -> bool:
        return self.set_tool_enabled(self._KNOWLEDGE_BASE_TOOL_NAME, enabled)

    def reset_ephemeral_runtime_state(self) -> None:
        self._clear_ephemeral_turn_context_messages()
        self.last_prepared_turn_context = None
        self.prepared_context_diagnostics = {}
        self.last_memory_automation = {}
        self.last_runtime_task_memory = {}

    def _last_user_query(self) -> str | None:
        for message in reversed(self.messages):
            if message.role != "user":
                continue
            if isinstance(message.content, str):
                content = message.content.strip()
            else:
                content = str(message.content).strip()
            if content:
                return content
        return None

    def _last_user_message_index(self) -> int | None:
        for index in range(len(self.messages) - 1, -1, -1):
            if str(getattr(self.messages[index], "role", "")).strip().lower() == "user":
                return index
        return None

    def _run_memory_automation(
        self,
        *,
        stop_reason: str,
        turn_start_index: int | None,
        turn_context: Any | None,
        assistant_message: str,
    ) -> None:
        automation = self.turn_memory_automation
        if automation is None:
            self.last_memory_automation = {}
            return
        if turn_start_index is None or turn_start_index < 0 or turn_start_index >= len(self.messages):
            self.last_memory_automation = {
                "enabled": True,
                "skipped_reason": "missing_turn_anchor",
                "action_count": 0,
                "actions": [],
            }
            return

        try:
            result = automation.process_turn(
                stop_reason=stop_reason,
                turn_messages=self.messages[turn_start_index:],
                turn_context=turn_context,
                assistant_message=assistant_message,
            )
            payload = result.to_payload()
            self.last_memory_automation = payload
            self.logger.log_event(
                "memory.auto_writeback",
                {
                    **payload,
                    "workspace_dir": str(self.workspace_dir),
                },
            )
        except Exception as exc:
            payload = {
                "enabled": True,
                "skipped_reason": "automation_failed",
                "action_count": 0,
                "actions": [],
                "error": f"{type(exc).__name__}: {exc}",
            }
            self.last_memory_automation = payload
            self.logger.log_event(
                "memory.auto_writeback_failed",
                {
                    **payload,
                    "workspace_dir": str(self.workspace_dir),
                },
                level="warning",
            )

    def _run_runtime_task_memory(
        self,
        *,
        stop_reason: str,
        turn_start_index: int | None,
        turn_context: Any | None,
        assistant_message: str,
    ) -> None:
        runtime_memory = self.turn_runtime_task_memory
        if runtime_memory is None:
            self.last_runtime_task_memory = {}
            return
        if turn_start_index is None or turn_start_index < 0 or turn_start_index >= len(self.messages):
            self.last_runtime_task_memory = {
                "enabled": True,
                "skipped_reason": "missing_turn_anchor",
                "stored": False,
                "duplicate": False,
                "namespace": None,
                "engram_id": None,
                "content": "",
            }
            return

        try:
            result = runtime_memory.process_turn(
                stop_reason=stop_reason,
                turn_messages=self.messages[turn_start_index:],
                turn_context=turn_context,
                assistant_message=assistant_message,
            )
            payload = result.to_payload()
            self.last_runtime_task_memory = payload
            self.logger.log_event(
                "memory.runtime_task_writeback",
                {
                    **payload,
                    "workspace_dir": str(self.workspace_dir),
                },
            )
        except Exception as exc:
            payload = {
                "enabled": True,
                "skipped_reason": "runtime_task_memory_failed",
                "stored": False,
                "duplicate": False,
                "namespace": None,
                "engram_id": None,
                "content": "",
                "error": f"{type(exc).__name__}: {exc}",
            }
            self.last_runtime_task_memory = payload
            self.logger.log_event(
                "memory.runtime_task_writeback_failed",
                {
                    **payload,
                    "workspace_dir": str(self.workspace_dir),
                },
                level="warning",
            )

    @staticmethod
    def _route_model_identity(route: Any) -> tuple[str, str, str] | None:
        if route is None:
            return None
        model_id = " ".join(str(getattr(route, "model", "") or "").split())
        provider_id = " ".join(str(getattr(route, "provider_id", "") or "").split())
        if not model_id:
            return None
        if provider_id.startswith("preset-"):
            return ("preset", provider_id.removeprefix("preset-"), model_id)
        if provider_id:
            return ("custom", provider_id, model_id)
        return None

    def _active_runtime_model_identity(self) -> tuple[str, str, str] | None:
        return self._route_model_identity(getattr(self, "runtime_route", None))

    def _runtime_catalog_path(self) -> Path | None:
        route = getattr(self, "runtime_route", None)
        raw = str(getattr(route, "catalog_path", "") or "").strip()
        if not raw:
            return None
        try:
            return Path(raw).expanduser().resolve()
        except Exception:
            return None

    @staticmethod
    def _unwrap_provider_error(exc: Exception) -> Exception:
        from .retry import RetryExhaustedError

        if isinstance(exc, RetryExhaustedError) and isinstance(exc.last_exception, Exception):
            return exc.last_exception
        return exc

    def _classify_generation_error(self, exc: Exception) -> ProviderErrorClassification:
        unwrapped = self._unwrap_provider_error(exc)
        if isinstance(unwrapped, ProviderFailoverError):
            attempts = list(getattr(unwrapped, "attempts", []) or [])
            for attempt in reversed(attempts):
                if str(getattr(attempt, "reason", "") or "").strip() == "context_window_exceeded":
                    return classify_provider_error(RuntimeError(str(getattr(attempt, "message", "") or "")))
        return classify_provider_error(unwrapped)

    def _record_learned_token_limit(self, *, learned_token_limit: int) -> int | None:
        normalized_limit = max(0, int(learned_token_limit or 0))
        if normalized_limit <= 0:
            return None
        current_limit = max(0, int(self.token_limit or 0))
        effective_limit = min(current_limit, normalized_limit) if current_limit > 0 else normalized_limit
        self.token_limit = effective_limit

        identity = self._active_runtime_model_identity()
        if identity is None:
            return effective_limit

        catalog_path = self._runtime_catalog_path()
        try:
            ModelRegistryService(catalog_path=catalog_path).record_learned_token_limit(
                source=identity[0],
                provider_id=identity[1],
                model_id=identity[2],
                learned_token_limit=effective_limit,
            )
        except Exception:
            pass
        return effective_limit

    async def _recover_from_context_overflow(
        self,
        *,
        step: int,
        exc: Exception,
    ) -> bool:
        classification = self._classify_generation_error(exc)
        if classification.reason != "context_window_exceeded":
            return False

        estimated_before = max(self._estimate_tokens(), estimate_tokens(self.messages))
        learned_limit = None
        if classification.context_window_limit is not None:
            learned_limit = self._record_learned_token_limit(
                learned_token_limit=classification.context_window_limit
            )

        reason_parts = ["context overflow recovery"]
        if learned_limit is not None:
            reason_parts.append(f"learned_limit={learned_limit}")
        if classification.requested_tokens is not None:
            reason_parts.append(f"requested={classification.requested_tokens}")
        recovery_reason = ", ".join(reason_parts)

        self.logger.log_event(
            "context.overflow_detected",
            {
                "step": step,
                "message": str(self._unwrap_provider_error(exc)),
                "context_window_limit": classification.context_window_limit,
                "requested_tokens": classification.requested_tokens,
                "estimated_tokens_before": estimated_before,
                "learned_token_limit": learned_limit,
                "identity": self._active_runtime_model_identity(),
            },
            level="warning",
        )
        self._emit_console(
            f"{Colors.BRIGHT_YELLOW}[...] Context overflow detected. Attempting automatic recovery...{Colors.RESET}"
        )

        compact_payload = self.compact_context(reason=recovery_reason)
        estimated_after_compact = max(self._estimate_tokens(), estimate_tokens(self.messages))
        drop_payload: dict[str, Any] | None = None
        if (
            not compact_payload.get("applied")
            or (
                self.token_limit > 0
                and estimated_after_compact >= max(1, int(self.token_limit))
            )
        ):
            drop_payload = self.drop_memories(reason=recovery_reason)

        estimated_after = max(self._estimate_tokens(), estimate_tokens(self.messages))
        changed = bool(compact_payload.get("applied")) or bool(drop_payload and drop_payload.get("applied"))
        if not changed and learned_limit is None:
            self._emit_console(
                f"{Colors.BRIGHT_YELLOW}[!]  Context overflow recovery could not reduce message history.{Colors.RESET}"
            )
            return False

        self.logger.log_event(
            "context.overflow_recovered",
            {
                "step": step,
                "estimated_tokens_before": estimated_before,
                "estimated_tokens_after": estimated_after,
                "learned_token_limit": learned_limit,
                "compact": compact_payload,
                "drop_memories": drop_payload,
            },
            level="warning",
        )
        self._emit_console(
            f"{Colors.BRIGHT_GREEN}[OK] Context recovery applied: {estimated_before} -> {estimated_after} tokens{Colors.RESET}"
        )
        return True

    def _build_context_compactor(self, *, aggressive: bool = False) -> LayeredContextCompactor:
        configured = self.context_compactor
        if configured is not None and not aggressive:
            return configured

        current_tokens = max(estimate_tokens(self.messages), 1)
        budget_ratio = 0.35 if aggressive else 0.65
        budget = max(200, int(current_tokens * budget_ratio))
        if self.token_limit > 0:
            limit_ratio = 0.3 if aggressive else 0.75
            budget = min(budget, max(200, int(self.token_limit * limit_ratio)))
        return LayeredContextCompactor(
            token_budget=budget,
            keep_recent_tool_messages=1 if aggressive else 2,
            snip_tail_lines=12 if aggressive else 24,
        )

    def compact_context(self, *, reason: str | None = None) -> dict[str, Any]:
        """Compact message history with the layered context compactor."""
        before_messages = len(self.messages)
        before_tokens = estimate_tokens(self.messages)
        compactor = self._build_context_compactor(aggressive=False)
        result = compactor.compact(
            self.messages,
            query=(reason or self._last_user_query()),
            enable_masking=True,
        )
        self.messages = list(result.messages)
        self.api_total_tokens = result.stats.compressed_tokens
        self._skip_next_token_check = True

        changed = (
            before_messages != len(self.messages)
            or before_tokens != result.stats.compressed_tokens
        )
        payload = {
            "reason": (reason or "").strip() or None,
            "applied": changed,
            "message_count_before": before_messages,
            "message_count_after": len(self.messages),
            "token_count_before": before_tokens,
            "token_count_after": result.stats.compressed_tokens,
            "stats": asdict(result.stats),
        }
        self.logger.log_event("context.compacted", payload)
        return payload

    def drop_memories(self, *, reason: str | None = None) -> dict[str, Any]:
        """Drop older conversational memory and keep only the freshest turn context."""
        before_messages = len(self.messages)
        before_tokens = estimate_tokens(self.messages)
        preserved = [message.model_copy(deep=True) for message in self.messages[:1]]

        last_user_index = None
        for index in range(len(self.messages) - 1, -1, -1):
            if self.messages[index].role == "user":
                last_user_index = index
                break

        if last_user_index is None:
            tail_start = max(1, len(self.messages) - 2)
            preserved.extend(message.model_copy(deep=True) for message in self.messages[tail_start:])
        else:
            preserved.extend(message.model_copy(deep=True) for message in self.messages[last_user_index:])

        compactor = self._build_context_compactor(aggressive=True)
        result = compactor.compact(
            preserved,
            query=(reason or self._last_user_query()),
            enable_masking=True,
        )
        self.messages = list(result.messages)
        self.api_total_tokens = result.stats.compressed_tokens
        self._skip_next_token_check = True

        changed = (
            before_messages != len(self.messages)
            or before_tokens != result.stats.compressed_tokens
        )
        payload = {
            "reason": (reason or "").strip() or None,
            "applied": changed,
            "message_count_before": before_messages,
            "message_count_after": len(self.messages),
            "token_count_before": before_tokens,
            "token_count_after": result.stats.compressed_tokens,
            "stats": asdict(result.stats),
        }
        self.logger.log_event("context.memories_dropped", payload, level="warning")
        return payload

    def _emit_console(self, text: str) -> None:
        if self.console_output:
            print(text)

    def _clear_ephemeral_turn_context_messages(self) -> None:
        self.messages = [
            message
            for message in self.messages
            if not (
                getattr(message, "role", None) == "system"
                and str(getattr(message, "name", "") or "").startswith(self._TURN_CONTEXT_MESSAGE_NAME)
            )
        ]

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

    async def _describe_turn_context_provider(
        self,
        *,
        provider: Any,
        provider_name: str,
        runtime_turn_context: Any,
    ) -> dict[str, Any] | None:
        describe = getattr(provider, "describe_readiness", None)
        if describe is None:
            return None
        result = describe(
            turn_context=runtime_turn_context,
            agent=self,
        )
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, dict):
            return None

        raw_status = str(result.get("status") or "").strip().lower()
        available = result.get("available")
        if raw_status:
            status = raw_status
        elif available is False:
            status = "unavailable"
        else:
            status = "ready"
        return {
            "provider": provider_name,
            "status": status,
            "reason": " ".join(str(result.get("reason") or "").split()),
            "item_count": max(0, int(result.get("item_count") or 0)),
            "available": bool(available) if available is not None else status not in {"unavailable", "disabled"},
        }

    async def _prepare_turn_context_messages(
        self,
        *,
        turn_context: Any | None = None,
    ) -> None:
        self._clear_ephemeral_turn_context_messages()
        self.last_prepared_turn_context = None

        if not self.turn_context_providers:
            self.last_prepared_turn_context = summarize_turn_context_items([])
            return

        runtime_turn_context = coerce_runtime_turn_context(
            turn_context,
            workspace_dir=self.workspace_dir,
        )
        policy = resolve_turn_context_policy(
            runtime_turn_context,
            default_max_items=self.turn_context_max_items,
            default_max_items_per_source=self.turn_context_max_items_per_source,
            default_max_total_chars=self.turn_context_max_total_chars,
        )
        prepared_items = []
        provider_failures: list[dict[str, Any]] = []
        provider_statuses: list[dict[str, Any]] = []

        for provider in self.turn_context_providers:
            provider_name = "turn_context_provider"
            if provider is not None:
                provider_name = str(getattr(provider, "name", "") or provider.__class__.__name__).strip() or provider_name
            allowed, filter_reason = provider_allowed_by_policy(provider_name, policy)
            if not allowed:
                provider_statuses.append(
                    {
                        "provider": provider_name,
                        "status": "filtered",
                        "reason": filter_reason,
                        "item_count": 0,
                    }
                )
                continue
            try:
                readiness = await self._describe_turn_context_provider(
                    provider=provider,
                    provider_name=provider_name,
                    runtime_turn_context=runtime_turn_context,
                )
                if readiness is not None and not readiness.get("available", True):
                    provider_statuses.append(
                        {
                            "provider": provider_name,
                            "status": str(readiness.get("status") or "unavailable"),
                            "reason": str(readiness.get("reason") or ""),
                            "item_count": int(readiness.get("item_count") or 0),
                        }
                    )
                    continue
                result = provider.prepare(
                    turn_context=runtime_turn_context,
                    agent=self,
                )
                if inspect.isawaitable(result):
                    result = await result
                normalized_items = normalize_turn_context_items(
                    result,
                    default_source=provider_name,
                )
                prepared_items.extend(normalized_items)
                provider_statuses.append(
                    {
                        "provider": provider_name,
                        "status": "used" if normalized_items else "no_match",
                        "reason": (
                            str(readiness.get("reason") or "")
                            if readiness is not None and readiness.get("reason")
                            else ("no relevant context for this turn" if not normalized_items else "")
                        ),
                        "item_count": len(normalized_items),
                    }
                )
            except Exception as exc:
                failure_payload = {
                    "provider": provider_name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                provider_failures.append(failure_payload)
                provider_statuses.append(
                    {
                        "provider": provider_name,
                        "status": "failed",
                        "reason": failure_payload["error"],
                        "item_count": 0,
                    }
                )
                self.logger.log_event(
                    "turn_context.provider_failed",
                    {
                        **failure_payload,
                        "session_id": runtime_turn_context.session_id,
                        "submission_id": runtime_turn_context.submission_id,
                    },
                    level="warning",
                )

        curated_items, curation_summary = curate_turn_context_items(
            prepared_items,
            max_items=int(policy.get("max_items") or self.turn_context_max_items),
            max_items_per_source=int(
                policy.get("max_items_per_source") or self.turn_context_max_items_per_source
            ),
            max_total_chars=int(policy.get("max_total_chars") or self.turn_context_max_total_chars),
        )
        summary = summarize_turn_context_items(
            curated_items,
            failures=provider_failures,
            curation=curation_summary,
            provider_statuses=provider_statuses,
            policy=policy,
        )
        self.last_prepared_turn_context = summary
        self.prepared_context_diagnostics = update_prepared_context_diagnostics(
            self.prepared_context_diagnostics,
            summary,
        )
        self.logger.log_event(
            "turn_context.prepared",
            {
                **summary,
                "diagnostics": dict(self.prepared_context_diagnostics),
                "session_id": runtime_turn_context.session_id,
                "submission_id": runtime_turn_context.submission_id,
                "policy_summary": context_policy_summary_line(policy, include_default=True),
            },
        )
        if not curated_items:
            return

        context_message = Message(
            role="system",
            content=format_turn_context_block(curated_items),
            name=f"{self._TURN_CONTEXT_MESSAGE_NAME}:{runtime_turn_context.submission_id}",
        )
        insert_at = len(self.messages)
        if self.messages and self.messages[-1].role == "user":
            insert_at = max(1, len(self.messages) - 1)
        self.messages.insert(insert_at, context_message)

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

    def _build_planner_generation_failure(
        self,
        *,
        step: int,
        exc: Exception,
    ) -> tuple[str, StepFailureEnvelope]:
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
            return error_msg, failure

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
        return error_msg, failure

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
            recovered = await self._recover_from_context_overflow(step=step, exc=exc)
            if not recovered:
                error_msg, failure = self._build_planner_generation_failure(step=step, exc=exc)
                return self._build_failed_outcome(step=step, error_msg=error_msg, failure=failure)
            self._emit_console(
                f"{Colors.BRIGHT_CYAN}[...] Retrying planner generation once after context recovery...{Colors.RESET}"
            )
            try:
                response = await self.llm.generate(messages=self.messages, tools=tool_list)
            except Exception as retry_exc:
                error_msg, failure = self._build_planner_generation_failure(
                    step=step,
                    exc=retry_exc,
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

    async def _best_effort_cancel_tool(
        self,
        *,
        step: int,
        tool_name: str,
        tool: Tool,
    ) -> bool:
        """Try to interrupt one running tool invocation."""
        cancel_running = getattr(tool, "cancel_running", None)
        if cancel_running is None:
            self.logger.log_event(
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
            self.logger.log_event(
                "tool.cancel_attempt",
                {
                    "step": step,
                    "tool_name": tool_name,
                    "cancelled": cancelled_flag,
                },
            )
            return cancelled_flag
        except Exception as exc:
            self.logger.log_event(
                "tool.cancel_failed",
                {
                    "step": step,
                    "tool_name": tool_name,
                    "error": f"{type(exc).__name__}: {exc}",
                },
                level="warning",
            )
            return False

    async def _execute_tool_with_interrupt_support(
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
            if self.cancel_event is None:
                return await tool_task

            cancel_wait_task = asyncio.create_task(self.cancel_event.wait())
            done, _ = await asyncio.wait(
                {tool_task, cancel_wait_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if tool_task in done:
                return await tool_task

            # Cancellation fired while tool call is still running.
            self.logger.log_event(
                "tool.cancel_requested",
                {"step": step, "tool_name": tool_name},
                level="warning",
            )
            interrupted = await self._best_effort_cancel_tool(
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

    def _build_tool_invocation(
        self,
        *,
        function_name: str,
        arguments: dict[str, object],
    ) -> ToolInvocation:
        declarative_tool = self.declarative_tools.get(function_name)
        if declarative_tool is None:
            raise KeyError(function_name)
        return declarative_tool.build(arguments)

    async def _request_tool_approval(
        self,
        *,
        step: int,
        invocation: ToolInvocation,
        reason: str,
        cache_key: str | None,
        can_escalate: bool,
    ) -> bool | None:
        handler = self.tool_approval_handler
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

    async def _authorize_tool_invocation(
        self,
        *,
        step: int,
        invocation: ToolInvocation,
    ) -> ToolResult | None:
        policy_engine = self.runtime_policy_engine
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
                if self.approval_engine is None:
                    return ToolResult(
                        success=False,
                        content="",
                        error=(
                            policy_decision.reason
                            or "Shell command requires approval, but no approval engine is configured."
                        ),
                    )
                approval = self.approval_engine.request_escalation(
                    invocation,
                    reason=policy_decision.reason or "runtime_policy_requires_approval",
                )
                self.logger.log_event(
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
                approval_decision = await self._request_tool_approval(
                    step=step,
                    invocation=invocation,
                    reason=approval.reason,
                    cache_key=approval.cache_key,
                    can_escalate=approval.can_escalate,
                )
                if approval_decision is True:
                    self.approval_engine.record_user_decision(invocation, PermissionDecision.ALLOW)
                    if policy_decision.host_access_required:
                        invocation.arguments["_mini_agent_host_access_approved"] = True
                    return None
                if approval_decision is False:
                    self.approval_engine.record_user_decision(invocation, PermissionDecision.DENY)
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

        if self.approval_engine is None:
            return None

        approval = self.approval_engine.evaluate(invocation)
        self.logger.log_event(
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

        approval_decision = await self._request_tool_approval(
            step=step,
            invocation=invocation,
            reason=approval.reason,
            cache_key=approval.cache_key,
            can_escalate=approval.can_escalate,
        )
        if approval_decision is True:
            self.approval_engine.record_user_decision(invocation, PermissionDecision.ALLOW)
            return None
        if approval_decision is False:
            self.approval_engine.record_user_decision(invocation, PermissionDecision.DENY)
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
                    invocation = self._build_tool_invocation(
                        function_name=function_name,
                        arguments=arguments,
                    )
                    approval_result = await self._authorize_tool_invocation(
                        step=step,
                        invocation=invocation,
                    )
                    if approval_result is not None:
                        result = approval_result
                    else:
                        result = await self._execute_tool_with_interrupt_support(
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
        turn_context: Any | None = None,
        start_new_run: bool = True,
    ) -> RunLoopResult:
        if cancel_event is not None:
            self.cancel_event = cancel_event

        if start_new_run:
            self._start_run_logging()

        await self._prepare_turn_context_messages(turn_context=turn_context)

        run_start_time = perf_counter()
        run_metrics = RunExecutionMetrics()
        try:
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
        finally:
            self._clear_ephemeral_turn_context_messages()

    async def run(self, cancel_event: Optional[asyncio.Event] = None) -> str:
        """Execute agent loop until task is complete or max steps reached."""
        run_result = await self._run_planner_executor_loop(
            cancel_event=cancel_event,
            hooks=None,
            turn_context=None,
            start_new_run=True,
        )
        return run_result.message

    async def run_turn(
        self,
        *,
        cancel_event: asyncio.Event | None = None,
        hooks: PlannerExecutorHooks | None = None,
        turn_context: Any | None = None,
        start_new_run: bool = True,
    ) -> TurnExecutionResult:
        """Execute one conversational turn using the shared planner/executor loop."""
        turn_start_index = self._last_user_message_index()
        run_result = await self._run_planner_executor_loop(
            cancel_event=cancel_event,
            hooks=hooks,
            turn_context=turn_context,
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
        stop_reason_value = getattr(stop_reason, "value", str(stop_reason or ""))
        self._run_memory_automation(
            stop_reason=stop_reason_value,
            turn_start_index=turn_start_index,
            turn_context=turn_context,
            assistant_message=run_result.message,
        )
        self._run_runtime_task_memory(
            stop_reason=stop_reason_value,
            turn_start_index=turn_start_index,
            turn_context=turn_context,
            assistant_message=run_result.message,
        )
        return TurnExecutionResult(
            stop_reason=stop_reason,
            message=run_result.message,
        )

    def get_history(self) -> list[Message]:
        """Get message history."""
        return self.messages.copy()


