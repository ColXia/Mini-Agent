"""Core Agent implementation."""

import asyncio
from collections.abc import Mapping
from contextlib import contextmanager
import inspect
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Any, Awaitable, Callable, Optional

from mini_agent.agent_core.context.context_compaction import LayeredContextCompactor, estimate_tokens
from mini_agent.agent_core.execution.permissions.approval import ApprovalEngine
from mini_agent.agent_core.history.summarization import AgentHistoryCompactionService
from mini_agent.agent_core.presentation import (
    AgentRuntimePresenter,
    AnsiConsoleAgentRuntimePresenter,
    NullAgentRuntimePresenter,
)
from mini_agent.agent_core.post_turn import AgentPostTurnSideEffectService
from mini_agent.agent_core.runtime_bindings import (
    AgentRuntimeBindings,
    AgentRuntimeServices,
    UNSET_RUNTIME_VALUE,
)
from mini_agent.agent_core.execution.tool_approval import ToolApprovalRequest
from mini_agent.agent_core.execution.tool_execution_coordinator import (
    AgentToolExecutionRuntime,
    AgentToolExecutionCoordinator,
    ToolExecutionBatchState,
)
from mini_agent.agent_core.execution.tools.builder import ToolInvocation, build_declarative_registry
from mini_agent.memory.automation import TurnMemoryAutomation
from mini_agent.memory.runtime_task_memory import TurnRuntimeTaskMemory
from mini_agent.model_manager.error_classifier import (
    ProviderErrorClassification,
    classify_provider_error,
)
from mini_agent.model_manager.failover import ProviderFailoverError
from mini_agent.model_manager.model_registry_service import ModelRegistryService
from mini_agent.agent_core.context.turn_context import AgentPreparedTurnContextService

from mini_agent.llm.llm_wrapper import LLMClient
from mini_agent.logger import AgentLogger
from mini_agent.schema.schema import LLMCompletionResult, LLMStreamEvent, Message, ToolCall
from mini_agent.tools.base import Tool, ToolResult


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
LLMEventHook = Callable[[int, LLMStreamEvent], Awaitable[None] | None]
ToolCallStartHook = Callable[[int, ToolCall], Awaitable[None] | None]
ToolCallResultHook = Callable[[int, ToolCall, ToolResult], Awaitable[None] | None]


@dataclass
class PlannerExecutorHooks:
    """Optional callbacks emitted by the planner/executor loop."""

    on_step_plan: StepPlanHook | None = None
    on_llm_event: LLMEventHook | None = None
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
        presenter: AgentRuntimePresenter | None = None,
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
        self.presenter = presenter or (
            AnsiConsoleAgentRuntimePresenter()
            if self.console_output
            else NullAgentRuntimePresenter()
        )
        self._runtime_bindings = AgentRuntimeBindings()
        self._runtime_services = AgentRuntimeServices(
            runtime_policy_engine=runtime_policy_engine,
            approval_engine=approval_engine,
            sandbox_manager=sandbox_manager,
            tool_approval_handler=tool_approval_handler,
        )
        self.tool_execution_runtime = AgentToolExecutionRuntime(
            cancel_event_getter=self._tool_execution_cancel_event,
            cancelled_checker=self._check_cancelled,
            hook_emitter=self._emit_hook,
            tool_getter=self._get_runtime_tool,
            invocation_builder=self._build_tool_invocation,
            tool_approval_handler_getter=self._get_tool_approval_handler,
            runtime_policy_engine_getter=self._get_runtime_policy_engine,
            approval_engine_getter=self._get_approval_engine,
            message_appender=self._append_runtime_message,
            event_logger=self._log_tool_execution_event,
            tool_result_logger=self._log_tool_execution_result,
        )
        self.tool_execution_coordinator = AgentToolExecutionCoordinator(
            runtime=self.tool_execution_runtime,
            presenter=self.presenter,
        )
        self.history_compaction_service = AgentHistoryCompactionService(
            llm_client=self.llm,
            presenter=self.presenter,
            token_estimator=estimate_tokens,
        )
        self.context_compactor = context_compactor
        self.turn_context_providers = list(turn_context_providers or [])
        self.turn_context_max_items = max(1, int(turn_context_max_items))
        self.turn_context_max_items_per_source = max(1, int(turn_context_max_items_per_source))
        self.turn_context_max_total_chars = max(200, int(turn_context_max_total_chars))
        self.turn_context_preparation_service = AgentPreparedTurnContextService(
            workspace_dir=self.workspace_dir,
            providers=self.turn_context_providers,
            default_max_items=self.turn_context_max_items,
            default_max_items_per_source=self.turn_context_max_items_per_source,
            default_max_total_chars=self.turn_context_max_total_chars,
            logger=self.logger,
            context_message_name_prefix=self._TURN_CONTEXT_MESSAGE_NAME,
        )
        self.last_prepared_turn_context: dict[str, Any] | None = None
        self.prepared_context_diagnostics: dict[str, Any] = {}
        self.turn_memory_automation = turn_memory_automation
        self.last_memory_automation: dict[str, Any] = {}
        self.turn_runtime_task_memory = turn_runtime_task_memory
        self.last_runtime_task_memory: dict[str, Any] = {}
        self.post_turn_side_effect_service = AgentPostTurnSideEffectService(
            logger=self.logger,
            workspace_dir=self.workspace_dir,
            turn_memory_automation=self.turn_memory_automation,
            turn_runtime_task_memory=self.turn_runtime_task_memory,
        )

        # Token usage from last API response (updated after each LLM call)
        self.api_total_tokens: int = 0
        # Flag to skip token check right after summary (avoid consecutive triggers)
        self._skip_next_token_check: bool = False

    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.messages.append(Message(role="user", content=content))

    @property
    def runtime_bindings(self) -> AgentRuntimeBindings:
        return self._runtime_bindings

    @property
    def runtime_services(self) -> AgentRuntimeServices:
        return self._runtime_services

    @runtime_services.setter
    def runtime_services(self, value: AgentRuntimeServices) -> None:
        if not isinstance(value, AgentRuntimeServices):
            raise TypeError("runtime_services must be an AgentRuntimeServices instance.")
        self._runtime_services = value

    def set_runtime_bindings(
        self,
        *,
        runtime_route: Any = UNSET_RUNTIME_VALUE,
        skill_runtime: Any = UNSET_RUNTIME_VALUE,
        skill_catalog_loader: Any = UNSET_RUNTIME_VALUE,
        kernel_diagnostics: Any = UNSET_RUNTIME_VALUE,
    ) -> AgentRuntimeBindings:
        self._runtime_bindings = self._runtime_bindings.with_updates(
            runtime_route=runtime_route,
            skill_runtime=skill_runtime,
            skill_catalog_loader=skill_catalog_loader,
            kernel_diagnostics=kernel_diagnostics,
        )
        return self._runtime_bindings

    @property
    def runtime_route(self) -> Any | None:
        return self._runtime_bindings.runtime_route

    @runtime_route.setter
    def runtime_route(self, value: Any | None) -> None:
        self.set_runtime_bindings(runtime_route=value)

    @property
    def skill_runtime(self) -> Any | None:
        return self._runtime_bindings.skill_runtime

    @skill_runtime.setter
    def skill_runtime(self, value: Any | None) -> None:
        self.set_runtime_bindings(skill_runtime=value)

    @property
    def skill_catalog_loader(self) -> Any | None:
        return self._runtime_bindings.skill_catalog_loader

    @skill_catalog_loader.setter
    def skill_catalog_loader(self, value: Any | None) -> None:
        self.set_runtime_bindings(skill_catalog_loader=value)

    @property
    def kernel_diagnostics(self) -> dict[str, Any]:
        return self._runtime_bindings.kernel_diagnostics

    @kernel_diagnostics.setter
    def kernel_diagnostics(self, value: Any) -> None:
        self.set_runtime_bindings(kernel_diagnostics=value)

    @property
    def runtime_policy_engine(self) -> Any | None:
        return self._runtime_services.runtime_policy_engine

    @runtime_policy_engine.setter
    def runtime_policy_engine(self, value: Any | None) -> None:
        self.set_runtime_services(runtime_policy_engine=value)

    @property
    def approval_engine(self) -> ApprovalEngine | None:
        return self._runtime_services.approval_engine

    @approval_engine.setter
    def approval_engine(self, value: ApprovalEngine | None) -> None:
        self.set_runtime_services(approval_engine=value)

    @property
    def sandbox_manager(self) -> Any | None:
        return self._runtime_services.sandbox_manager

    @sandbox_manager.setter
    def sandbox_manager(self, value: Any | None) -> None:
        self.set_runtime_services(sandbox_manager=value)

    @property
    def tool_approval_handler(
        self,
    ) -> Callable[[ToolApprovalRequest], Awaitable[bool | None] | bool | None] | None:
        return self._runtime_services.tool_approval_handler

    @tool_approval_handler.setter
    def tool_approval_handler(
        self,
        value: Callable[[ToolApprovalRequest], Awaitable[bool | None] | bool | None] | None,
    ) -> None:
        self.set_runtime_services(tool_approval_handler=value)

    def set_runtime_services(
        self,
        *,
        runtime_policy_engine: Any = UNSET_RUNTIME_VALUE,
        approval_engine: ApprovalEngine | None = UNSET_RUNTIME_VALUE,
        sandbox_manager: Any = UNSET_RUNTIME_VALUE,
        tool_approval_handler: Any = UNSET_RUNTIME_VALUE,
    ) -> AgentRuntimeServices:
        self._runtime_services = self._runtime_services.with_updates(
            runtime_policy_engine=runtime_policy_engine,
            approval_engine=approval_engine,
            sandbox_manager=sandbox_manager,
            tool_approval_handler=tool_approval_handler,
        )
        return self._runtime_services

    def set_tool_approval_handler(
        self,
        handler: Callable[[ToolApprovalRequest], Awaitable[bool | None] | bool | None] | None,
    ) -> None:
        self.set_runtime_services(tool_approval_handler=handler)

    @contextmanager
    def override_tool_approval_handler(
        self,
        handler: Callable[[ToolApprovalRequest], Awaitable[bool | None] | bool | None] | None,
    ):
        previous_handler = self.tool_approval_handler
        self.set_runtime_services(tool_approval_handler=handler)
        try:
            yield previous_handler
        finally:
            self.set_runtime_services(tool_approval_handler=previous_handler)

    @staticmethod
    def _normalize_execution_policy_override(policy: Any) -> AgentExecutionPolicy:
        if isinstance(policy, AgentExecutionPolicy):
            return policy.normalized()

        max_steps = getattr(policy, "max_steps", None)
        max_tool_calls_per_step = getattr(policy, "max_tool_calls_per_step", None)
        if isinstance(policy, Mapping):
            max_steps = policy.get("max_steps")
            max_tool_calls_per_step = policy.get("max_tool_calls_per_step")
        if max_steps is None:
            raise ValueError("Execution policy override must define max_steps.")
        return AgentExecutionPolicy(
            max_steps=int(max_steps),
            max_tool_calls_per_step=max_tool_calls_per_step,
        ).normalized()

    @contextmanager
    def override_execution_policy(self, policy: Any):
        previous_policy = self.execution_policy
        previous_max_steps = self.max_steps
        previous_max_tool_calls = self.max_tool_calls_per_step
        normalized_policy = self._normalize_execution_policy_override(policy)
        self.execution_policy = normalized_policy
        self.max_steps = normalized_policy.max_steps
        self.max_tool_calls_per_step = normalized_policy.max_tool_calls_per_step
        try:
            yield previous_policy
        finally:
            self.execution_policy = previous_policy
            self.max_steps = previous_max_steps
            self.max_tool_calls_per_step = previous_max_tool_calls

    def _refresh_tool_registry(self) -> None:
        self.declarative_tools = build_declarative_registry(self.tools.values())

    def _tool_execution_cancel_event(self) -> asyncio.Event | None:
        return self.cancel_event

    def _get_runtime_tool(self, tool_name: str) -> Tool | None:
        return self.tools.get(tool_name)

    def _build_tool_invocation(
        self,
        function_name: str,
        arguments: dict[str, object],
    ) -> ToolInvocation:
        declarative_tool = self.declarative_tools.get(function_name)
        if declarative_tool is None:
            raise KeyError(function_name)
        return declarative_tool.build(arguments)

    def _get_tool_approval_handler(self) -> Any:
        return self.tool_approval_handler

    def _get_runtime_policy_engine(self) -> Any:
        return self.runtime_policy_engine

    def _get_approval_engine(self) -> ApprovalEngine | None:
        return self.approval_engine

    def _append_runtime_message(self, message: Message) -> None:
        self.messages.append(message)

    def _log_tool_execution_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        level: str = "info",
    ) -> None:
        self.logger.log_event(event_type, payload, level=level)

    def _log_tool_execution_result(
        self,
        tool_name: str,
        arguments: dict[str, object],
        result_success: bool,
        result_content: str | None,
        result_error: str | None,
    ) -> None:
        self.logger.log_tool_result(
            tool_name=tool_name,
            arguments=arguments,
            result_success=result_success,
            result_content=result_content,
            result_error=result_error,
        )

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
        from mini_agent.retry import RetryExhaustedError

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
        self.presenter.context_overflow_detected()

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
            self.presenter.context_overflow_recovery_failed()
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
        self.presenter.context_recovery_applied(
            estimated_before=estimated_before,
            estimated_after=estimated_after,
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

    async def _prepare_turn_context_messages(
        self,
        *,
        turn_context: Any | None = None,
    ) -> None:
        self._clear_ephemeral_turn_context_messages()
        result = await self.turn_context_preparation_service.prepare_turn_context(
            turn_context=turn_context,
            agent=self,
            current_diagnostics=self.prepared_context_diagnostics,
        )
        self.last_prepared_turn_context = dict(result.summary)
        self.prepared_context_diagnostics = dict(result.diagnostics)
        if result.context_message is None:
            return

        insert_at = len(self.messages)
        if self.messages and self.messages[-1].role == "user":
            insert_at = max(1, len(self.messages) - 1)
        self.messages.insert(insert_at, result.context_message)

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
            self.presenter.incomplete_message_cleanup(removed_count=removed_count)

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
            self.presenter.tool_calls_truncated(
                step=step,
                requested_tool_calls=requested_tool_calls,
                planned_tool_calls=len(planned_tool_calls),
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

    def _build_cancelled_outcome(self, step: int, run_start_time: float) -> StepOutcome:
        """Build and log a cancellation outcome."""
        self._cleanup_incomplete_messages()
        cancel_msg = "Task cancelled by user."
        self.presenter.cancelled(message=cancel_msg)
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
        from mini_agent.retry import RetryExhaustedError

        if isinstance(exc, RetryExhaustedError):
            error_msg = f"LLM call failed after {exc.attempts} retries\nLast error: {str(exc.last_exception)}"
            self.presenter.planner_retry_failed(error_message=error_msg)
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
        self.presenter.planner_error(error_message=error_msg)
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
        self.presenter.step_timing(
            step=step,
            step_elapsed=step_elapsed,
            total_elapsed=total_elapsed,
        )
        self._log_step_completed(
            step_state=step_state,
            step_elapsed=step_elapsed,
            total_elapsed=total_elapsed,
        )
        return step_elapsed, total_elapsed

    async def _generate_completion_result(
        self,
        *,
        step: int,
        tool_list: list[Tool],
        hooks: PlannerExecutorHooks | None = None,
    ) -> LLMCompletionResult:
        stream_generate = getattr(self.llm, "stream_generate", None)
        if callable(stream_generate):
            events: list[LLMStreamEvent] = []
            metadata: dict[str, Any] = {}
            async for event in stream_generate(messages=self.messages, tools=tool_list):
                events.append(event)
                if not metadata and isinstance(event.metadata, dict) and event.metadata:
                    metadata = dict(event.metadata)
                await self._emit_hook(hooks.on_llm_event if hooks else None, step, event)
            return LLMCompletionResult.from_events(events, metadata=metadata or None)

        response = await self.llm.generate(messages=self.messages, tools=tool_list)
        if not isinstance(response, LLMCompletionResult):
            response = LLMCompletionResult(
                content=str(getattr(response, "content", "") or ""),
                thinking=getattr(response, "thinking", None),
                tool_calls=getattr(response, "tool_calls", None),
                finish_reason=str(getattr(response, "finish_reason", "stop") or "stop"),
                usage=getattr(response, "usage", None),
                error=getattr(response, "error", None),
            )
        for event in response.events:
            await self._emit_hook(hooks.on_llm_event if hooks else None, step, event)
        return response

    async def _plan_step(
        self,
        step: int,
        run_start_time: float,
        hooks: PlannerExecutorHooks | None = None,
    ) -> StepPlan | StepOutcome:
        """Planner phase: summarize, call LLM, and plan tool execution."""
        if self._check_cancelled():
            return self._build_cancelled_outcome(step=step, run_start_time=run_start_time)

        await self._apply_history_compaction()
        self.presenter.step_header(step=step, max_steps=self.max_steps)

        tool_list = list(self.tools.values())
        self.logger.log_request(messages=self.messages, tools=tool_list)

        try:
            response = await self._generate_completion_result(
                step=step,
                tool_list=tool_list,
                hooks=hooks,
            )
        except Exception as exc:
            recovered = await self._recover_from_context_overflow(step=step, exc=exc)
            if not recovered:
                error_msg, failure = self._build_planner_generation_failure(step=step, exc=exc)
                return self._build_failed_outcome(step=step, error_msg=error_msg, failure=failure)
            self.presenter.retrying_planner_generation()
            try:
                response = await self._generate_completion_result(
                    step=step,
                    tool_list=tool_list,
                    hooks=hooks,
                )
            except Exception as retry_exc:
                error_msg, failure = self._build_planner_generation_failure(
                    step=step,
                    exc=retry_exc,
                )
                return self._build_failed_outcome(step=step, error_msg=error_msg, failure=failure)

        if response.usage:
            self.api_total_tokens = response.usage.total_tokens

        self.logger.log_completion(response)

        assistant_msg = Message(
            role="assistant",
            content=response.content,
            thinking=response.thinking,
            tool_calls=response.tool_calls,
        )
        self.messages.append(assistant_msg)

        if response.thinking:
            self.presenter.assistant_thinking(thinking=response.thinking)

        if response.content:
            self.presenter.assistant_response(content=response.content)

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
        batch_result = await self.tool_execution_coordinator.execute_tool_calls(
            step=step,
            tool_calls=tool_calls,
            step_state=step_state,
            hooks=hooks,
        )
        if batch_result.state == ToolExecutionBatchState.COMPLETE:
            return StepOutcome(
                transition=StepTransition.COMPLETE,
                message=batch_result.message,
            )
        if batch_result.state == ToolExecutionBatchState.CANCELLED:
            return self._build_cancelled_outcome(step=step, run_start_time=run_start_time)
        return StepOutcome(
            transition=StepTransition.CONTINUE,
            message=batch_result.message,
        )

    def _estimate_tokens(self) -> int:
        """Accurately calculate token count for message history using tiktoken

        Uses cl100k_base encoder (GPT-4/Claude/M2 compatible)
        """
        try:
            import tiktoken

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

    async def _apply_history_compaction(self) -> None:
        """Apply history-compaction results back into agent runtime state."""
        compaction_result = await self.history_compaction_service.compact_history(
            messages=self.messages,
            token_limit=self.token_limit,
            api_total_tokens=self.api_total_tokens,
            skip_next_token_check=self._skip_next_token_check,
        )
        self.messages = list(compaction_result.messages)
        self._skip_next_token_check = compaction_result.skip_next_token_check

    def _start_run_logging(self) -> None:
        self.logger.start_new_run(workspace=self.workspace_dir)
        self.presenter.run_log_paths(
            log_file_path=self.logger.get_log_file_path(),
            event_file_path=self.logger.get_event_file_path(),
        )
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

                plan_or_outcome = await self._plan_step(
                    step=step,
                    run_start_time=run_start_time,
                    hooks=hooks,
                )
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
            self.presenter.max_steps_reached(error_message=error_msg)
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
        side_effect_result = self.post_turn_side_effect_service.process_turn(
            stop_reason=stop_reason_value,
            messages=self.messages,
            turn_start_index=turn_start_index,
            turn_context=turn_context,
            assistant_message=run_result.message,
        )
        self.last_memory_automation = side_effect_result.memory_automation
        self.last_runtime_task_memory = side_effect_result.runtime_task_memory
        return TurnExecutionResult(
            stop_reason=stop_reason,
            message=run_result.message,
        )

    def get_history(self) -> list[Message]:
        """Get message history."""
        return self.messages.copy()
