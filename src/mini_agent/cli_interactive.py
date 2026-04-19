"""Interactive CLI session for Mini-Agent.

This module provides the interactive terminal session for Mini-Agent,
supporting both interactive mode and single-task execution.
"""

import asyncio
from datetime import datetime
import inspect
import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings

from .agent_core.engine import Agent, TurnStopReason
from .commands.completions import (
    command_completion_tokens,
    suggest_command_name,
)
from .commands.metadata import (
    build_command_example_text,
    build_command_help_text,
    build_command_usage_text,
)
from .commands.execution import (
    CommandExecutionResult,
    LocalOperatorCommandService,
    McpReloadOutcome,
    prepare_context_command_plan,
    prepare_memory_command_plan,
    prepare_model_command_plan,
)
from .commands.parser import (
    CommandDispatcher,
    CommandParseError,
    normalize_command_name,
    parse_command_text,
)
from .commands.mcp_support import (
    collect_mcp_operator_snapshot,
    format_mcp_server_list,
    format_mcp_status,
)
from .tools.mcp.command_service import format_cli_mcp_reload_success
from .agent_core.context.loop_context import AgentLoopContext
from .agent_core.execution.agent_loop import (
    AgentSubmissionLoop,
    InMemoryLoopMessageBus,
    wait_for_loop_event,
    wait_for_submission_completion,
)
from .agent_core.execution.coordinator import CoordinatorStage
from .agent_core.execution.minimal_workflow import (
    format_minimal_workflow_report,
    run_minimal_workflow_with_runner,
)
from .memory.diagnostics import build_memory_diagnostics
from .memory.memoria_runtime import WorkspaceMemoriaRuntime
from .agent_core.kernel import AgentKernelBuildOptions, build_agent_kernel
from .config import Config
from .config_bootstrap import load_entry_config
from .model_manager.model_registry_service import ModelRegistryService
from .runtime.support.sandbox_state import collect_sandbox_diagnostics, compact_sandbox_summary
from .runtime.orchestration.session_runtime_lifecycle_handler import (
    SurfaceSessionLifecycleRuntime,
)
from .agent_core.context.control_result_service import (
    SessionContextControlResultService,
)
from .agent_core.context.turn_context import (
    format_prepared_turn_context_details,
    prepared_turn_context_summary_line,
    resolve_turn_context_policy,
)
from .agent_core.skills.runtime_feedback import (
    describe_skill_runtime_reload,
    format_cli_skill_reload_failure,
    format_cli_skill_reload_success,
)
from .tools.mcp_loader import cleanup_mcp_connections
from .utils.terminal_utils import supports_unicode_box_art


# ANSI color codes
class Colors:
    """Terminal color definitions."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"


def print_banner():
    """Print the CLI banner."""
    if supports_unicode_box_art():
        banner = f"""
{Colors.BRIGHT_CYAN}╔═══════════════════════════════════════════════════════════╗
║  {Colors.BOLD}Mini-Agent CLI{Colors.RESET}{Colors.BRIGHT_CYAN} - Interactive Session                     ║
╚═══════════════════════════════════════════════════════════╝{Colors.RESET}
"""
        print(banner)
        return
    print("=" * 60)
    print("  Mini-Agent CLI - Interactive Session")
    print("=" * 60)


def print_help():
    """Print help information."""
    print(f"\n{Colors.BOLD}{Colors.BRIGHT_YELLOW}Available Commands:{Colors.RESET}")
    body = build_command_help_text(
        "cli",
        include_header=False,
        leading_slash=True,
    )
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            print("")
            continue
        if not line.startswith("  "):
            print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}{stripped}{Colors.RESET}")
            continue
        print(line)
    print("")
    examples = build_command_example_text(
        "cli",
        include_header=True,
        leading_slash=True,
        max_examples=10,
    )
    for line in examples.splitlines():
        stripped = line.strip()
        if not stripped:
            print("")
            continue
        if line.startswith("Examples:"):
            print(f"{Colors.BOLD}{Colors.BRIGHT_YELLOW}{stripped}{Colors.RESET}")
            continue
        print(line)
    print(
        f"\n{Colors.BOLD}{Colors.BRIGHT_YELLOW}Keyboard Shortcuts:{Colors.RESET}\n"
        f"  {Colors.CYAN}Ctrl+C{Colors.RESET}     Exit program\n"
        f"  {Colors.CYAN}Ctrl+J{Colors.RESET}     Insert newline\n"
        f"  {Colors.CYAN}Tab{Colors.RESET}        Auto-complete commands\n"
    )


def print_session_info(agent: Agent, workspace: Path, model: str):
    """Print session information."""
    sandbox_summary = compact_sandbox_summary(collect_sandbox_diagnostics(agent=agent))
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}Session Info:{Colors.RESET}")
    print(f"  Model: {model}")
    print(f"  Workspace: {workspace}")
    print(f"  Tools: {len(agent.tools)}")
    print(f"  Sandbox: {sandbox_summary}")
    print(
        f"\n{Colors.DIM}Type {Colors.BRIGHT_GREEN}/help{Colors.DIM} for help, "
        f"{Colors.BRIGHT_GREEN}/exit{Colors.DIM} to quit{Colors.RESET}\n"
    )


def print_stats(agent: Agent, session_start: datetime):
    """Print session statistics."""
    duration = datetime.now() - session_start
    hours, remainder = divmod(int(duration.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    user_msgs = sum(1 for m in agent.messages if m.role == "user")
    assistant_msgs = sum(1 for m in agent.messages if m.role == "assistant")

    print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}Session Statistics:{Colors.RESET}")
    try:
        print(f"{Colors.DIM}{'鈹€' * 40}{Colors.RESET}")
    except UnicodeEncodeError:
        print("-" * 40)
    print(f"  Duration: {hours:02d}:{minutes:02d}:{seconds:02d}")
    print(f"  Messages: {len(agent.messages)}")
    print(f"    - User: {Colors.BRIGHT_GREEN}{user_msgs}{Colors.RESET}")
    print(f"    - Assistant: {Colors.BRIGHT_BLUE}{assistant_msgs}{Colors.RESET}")
    if agent.api_total_tokens > 0:
        print(f"  Tokens: {Colors.BRIGHT_MAGENTA}{agent.api_total_tokens:,}{Colors.RESET}")
    try:
        print(f"{Colors.DIM}{'鈹€' * 40}{Colors.RESET}\n")
    except UnicodeEncodeError:
        print("-" * 40 + "\n")


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _active_model_identity(agent: Agent) -> tuple[str, str, str] | None:
    resolver = getattr(agent, "_active_runtime_model_identity", None)
    if callable(resolver):
        try:
            identity = resolver()
        except Exception:
            identity = None
        if identity is not None:
            return identity
    route = getattr(agent, "runtime_route", None)
    if route is None:
        return None
    model_id = _safe_text(getattr(route, "model", ""))
    provider_id = _safe_text(getattr(route, "provider_id", ""))
    if not model_id:
        return None
    if provider_id.startswith("preset-"):
        return ("preset", provider_id.removeprefix("preset-"), model_id)
    if provider_id:
        return ("custom", provider_id, model_id)
    return None


def _format_model_identity(identity: tuple[str, str, str] | None, *, fallback_model: str | None = None) -> str:
    if identity is None:
        fallback = _safe_text(fallback_model)
        return fallback or "unknown"
    return f"{identity[1]}/{identity[2]}"


def _cli_model_registry() -> list[dict[str, Any]]:
    try:
        return ModelRegistryService().list_registry()
    except Exception:
        return []


def _render_cli_model_catalog(
    providers: list[dict[str, Any]],
    *,
    selected_identity: tuple[str, str, str] | None = None,
) -> str:
    if not providers:
        return "No models available. Configure preset keys or add a custom provider first."

    lines = ["Available models:"]
    for provider in providers:
        provider_source = _safe_text(provider.get("source")) or "custom"
        provider_id = _safe_text(provider.get("provider_id"))
        provider_name = _safe_text(provider.get("provider_name")) or provider_id or "provider"
        default_model_id = _safe_text(provider.get("default_model_id"))
        lines.append(f"- {provider_name} [{provider_source}] ({provider_id or 'unknown'})")
        models = provider.get("models")
        if not isinstance(models, list) or not models:
            lines.append("    (no models)")
            continue
        for model in models:
            if not isinstance(model, dict):
                continue
            model_id = _safe_text(model.get("model_id"))
            if not model_id:
                continue
            display_name = _safe_text(model.get("display_name")) or model_id
            tags: list[str] = []
            if default_model_id and model_id == default_model_id:
                tags.append("default")
            if (
                selected_identity is not None
                and selected_identity[0] == provider_source
                and selected_identity[1] == provider_id
                and selected_identity[2] == model_id
            ):
                tags.append("selected")
            tag_text = f" [{' | '.join(tags)}]" if tags else ""
            lines.append(f"    - {model_id} ({display_name}){tag_text}")
    return "\n".join(lines)


def _copy_agent_session_state(source: Agent, target: Agent) -> None:
    source_messages = getattr(source, "messages", None)
    if isinstance(source_messages, list):
        target.messages = list(source_messages)
    for attr in (
        "api_total_tokens",
        "last_prepared_turn_context",
        "prepared_context_diagnostics",
        "last_runtime_task_memory",
    ):
        if hasattr(source, attr):
            setattr(target, attr, getattr(source, attr))
    checker = getattr(source, "knowledge_base_enabled", None)
    setter = getattr(target, "set_knowledge_base_enabled", None)
    if callable(checker) and callable(setter):
        try:
            setter(bool(checker()))
        except Exception:
            pass


def _build_cli_completer_tokens() -> list[str]:
    tokens = set(
        command_completion_tokens(
            "cli",
            include_leading_slash=True,
            include_plain=False,
        )
    )
    tokens.update({"/drop-memories", "/quit"})
    for provider in _cli_model_registry():
        provider_id = _safe_text(provider.get("provider_id"))
        if provider_id:
            tokens.add(provider_id)
            tokens.add(f"/model use {provider_id}")
        models = provider.get("models")
        if not isinstance(models, list):
            continue
        for model in models:
            if not isinstance(model, dict):
                continue
            model_id = _safe_text(model.get("model_id"))
            if model_id:
                tokens.add(model_id)
    return sorted(tokens)


def _reset_agent_messages(agent: Agent) -> None:
    messages = getattr(agent, "messages", None)
    if not isinstance(messages, list) or not messages:
        pass
    else:
        agent.messages = [messages[0]]
    if hasattr(agent, "api_total_tokens"):
        agent.api_total_tokens = 0
    reset_runtime_state = getattr(agent, "reset_ephemeral_runtime_state", None)
    if callable(reset_runtime_state):
        reset_runtime_state()
        return
    if hasattr(agent, "last_prepared_turn_context"):
        agent.last_prepared_turn_context = None
    if hasattr(agent, "prepared_context_diagnostics"):
        agent.prepared_context_diagnostics = {}
    if hasattr(agent, "last_memory_automation"):
        agent.last_memory_automation = {}
    if hasattr(agent, "last_runtime_task_memory"):
        agent.last_runtime_task_memory = {}


def _clear_cli_runtime_task_memory(workspace: Path, *, session_id: str = "cli-session") -> bool:
    try:
        return WorkspaceMemoriaRuntime(workspace).clear_session_namespace(session_id)
    except Exception:
        return False


def _policy_overrides(agent: Agent) -> dict[str, Any]:
    return {
        "max_steps": getattr(agent, "max_steps", 50),
        "max_tool_calls_per_step": getattr(agent, "max_tool_calls_per_step", None),
    }


def _knowledge_base_enabled(agent: Any) -> bool:
    checker = getattr(agent, "knowledge_base_enabled", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            pass
    tools = getattr(agent, "tools", None)
    if isinstance(tools, dict):
        return "knowledge_base_query" in tools
    if isinstance(tools, list):
        return any(getattr(tool, "name", None) == "knowledge_base_query" for tool in tools)
    return True


def _with_prepared_context_policy(
    metadata: dict[str, Any] | None,
    policy: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    normalized = resolve_turn_context_policy(policy or {})
    if normalized.get("active"):
        payload["prepared_context_policy"] = normalized
    return payload


async def create_submission_loop_for_agent(
    *,
    agent: Agent,
    session_id: str,
    hooks: Any | None = None,
) -> tuple[AgentSubmissionLoop, InMemoryLoopMessageBus]:
    bus = InMemoryLoopMessageBus()
    context = AgentLoopContext(message_bus=bus, session_id=session_id)
    loop = AgentSubmissionLoop(
        context=context,
        agent_factory=lambda _context: agent,
        hooks=hooks,
    )
    await loop.start()
    return loop, bus


async def run_prompt_via_submission_loop(
    *,
    loop: AgentSubmissionLoop,
    bus: InMemoryLoopMessageBus,
    agent: Agent,
    prompt: str,
    metadata: dict[str, Any] | None = None,
    start_new_run: bool = True,
    approval_resolver: Callable[[dict[str, Any]], Awaitable[bool | None] | bool | None] | None = None,
    event_handler: Callable[[str, dict[str, Any]], Awaitable[None] | None] | None = None,
) -> dict[str, Any]:
    event_start_index = len(bus.events)
    submission_id = await loop.submit_user_input(
        prompt,
        policy_overrides=_policy_overrides(agent),
        metadata=metadata or {},
        start_new_run=start_new_run,
    )

    handled_tokens: set[str] = set()

    async def _on_event(event_type: str, payload: dict[str, Any]) -> None:
        if event_type != "loop.approval.requested":
            if event_handler is not None:
                maybe_awaitable = event_handler(event_type, payload)
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable
            return
        if str(payload.get("submission_id", "") or "").strip() == submission_id:
            token = str(payload.get("token", "") or "").strip()
            if token and token not in handled_tokens:
                handled_tokens.add(token)
                if approval_resolver is None:
                    await loop.submit_exec_approval(approved=False, token=token)
                else:
                    maybe_awaitable = approval_resolver(payload)
                    decision = await maybe_awaitable if inspect.isawaitable(maybe_awaitable) else maybe_awaitable
                    await loop.submit_exec_approval(approved=bool(decision), token=token)
        if event_handler is not None:
            maybe_awaitable = event_handler(event_type, payload)
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable

    payload = await wait_for_submission_completion(
        bus=bus,
        submission_id=submission_id,
        event_start_index=event_start_index,
        on_event=_on_event,
    )
    return payload


async def run_loop_control_via_submission_loop(
    *,
    loop: AgentSubmissionLoop,
    bus: InMemoryLoopMessageBus,
    action: str,
    reason: str | None = None,
) -> dict[str, Any]:
    normalized_action = _safe_text(action).lower().replace("-", "_")
    event_start_index = len(bus.events)
    if normalized_action == "compact":
        event_id = await loop.submit_compact(reason=reason)
        target_event_type = "loop.compact"
    elif normalized_action == "drop_memories":
        event_id = await loop.submit_drop_memories(reason=reason)
        target_event_type = "loop.drop_memories"
    else:
        raise ValueError(f"Unknown loop control action: {action}")
    return await wait_for_loop_event(
        bus=bus,
        event_type=target_event_type,
        event_start_index=event_start_index,
        event_id=event_id,
    )


def _print_loop_control_result(action: str, payload: dict[str, Any]) -> None:
    normalized_action = _safe_text(action).lower().replace("-", "_")
    error = _safe_text(payload.get("error"))
    if error:
        print(f"{Colors.RED}[X] {normalized_action} failed: {error}{Colors.RESET}")
        return
    if payload.get("unsupported"):
        print(f"{Colors.RED}[X] {normalized_action} is not supported by the active agent.{Colors.RESET}")
        return

    result = SessionContextControlResultService.normalize_result(
        action=normalized_action,
        payload=payload,
    )

    print(f"{Colors.GREEN}[OK] {SessionContextControlResultService.cli_label(result=result)}{Colors.RESET}")
    print(
        f"{Colors.DIM}  Messages: {result.message_count_before} -> {result.message_count_after} | "
        f"Tokens: {result.token_count_before} -> {result.token_count_after}{Colors.RESET}"
    )
    if result.stats:
        print(
            f"{Colors.DIM}  Stats: masked={result.stats.get('masked_messages', 0)}, "
            f"snipped={result.stats.get('snipped_messages', 0)}, "
            f"merged={result.stats.get('merged_messages', 0)}{Colors.RESET}"
        )


def _approval_prompt_lines(payload: dict[str, Any]) -> list[str]:
    tool_name = _safe_text(payload.get("tool_name")) or "tool"
    kind = _safe_text(payload.get("kind")) or "other"
    reason = _safe_text(payload.get("reason")) or "requires confirmation"
    arguments = payload.get("arguments")
    preview = ""
    if isinstance(arguments, dict) and arguments:
        preview = json.dumps(arguments, ensure_ascii=False)
        if len(preview) > 180:
            preview = preview[:177] + "..."
    lines = [
        f"{Colors.BRIGHT_YELLOW}[approval]{Colors.RESET} {tool_name} ({kind})",
        f"  reason: {reason}",
    ]
    if preview:
        lines.append(f"  args:   {preview}")
    return lines


async def prompt_cli_approval(payload: dict[str, Any]) -> bool:
    for line in _approval_prompt_lines(payload):
        print(line)

    prompt = (
        f"{Colors.BRIGHT_GREEN}Approve this tool call? [y/N]: {Colors.RESET}"
    )

    def _read_choice() -> str:
        try:
            return input(prompt)
        except EOFError:
            return ""

    answer = (await asyncio.to_thread(_read_choice)).strip().lower()
    return answer in {"y", "yes"}


def _print_submission_failure(payload: dict[str, Any]) -> None:
    state = _safe_text(payload.get("state")).lower()
    stop_reason = _safe_text(payload.get("stop_reason")).lower()
    message = _safe_text(payload.get("message"))
    error = _safe_text(payload.get("error"))

    if state == "completed" and stop_reason in {"end_turn", ""}:
        return
    if state == "interrupted" or stop_reason == TurnStopReason.CANCELLED.value:
        print(f"{Colors.BRIGHT_YELLOW}[!]  {message or 'Task cancelled by user.'}{Colors.RESET}")
        return
    if stop_reason == TurnStopReason.MAX_TURN_REQUESTS.value:
        print(f"{Colors.BRIGHT_YELLOW}[!]  {message or 'Turn reached max request limit.'}{Colors.RESET}")
        return
    failure = message or error or "Turn failed."
    print(f"{Colors.RED}[X] {failure}{Colors.RESET}")

def _build_cli_memory_diagnostics(
    *,
    workspace: Path,
    agent: Agent,
    session_id: str = "cli-session",
) -> dict[str, Any]:
    return build_memory_diagnostics(
        workspace_dir=workspace,
        session_id=session_id,
        last_prepared_context=getattr(agent, "last_prepared_turn_context", None),
        last_memory_automation=getattr(agent, "last_memory_automation", {}),
        last_runtime_task_memory=getattr(agent, "last_runtime_task_memory", {}),
    )


def _run_cli_memory_action(
    *,
    command_service: LocalOperatorCommandService,
    workspace: Path,
    agent: Agent,
    action: str,
    engram_id: str | None = None,
    content: str | None = None,
    query: str | None = None,
    day: str | None = None,
    export_format: str | None = None,
    detail_mode: str = "full",
) -> dict[str, Any]:
    result = command_service.execute_memory_action(
        workspace=workspace,
        session_id="cli-session",
        diagnostics_loader=lambda: _build_cli_memory_diagnostics(workspace=workspace, agent=agent),
        action=action,
        engram_id=engram_id,
        content=content,
        query=query,
        day=day,
        export_format=export_format,
        detail_mode=detail_mode,
        prepared_context=getattr(agent, "last_prepared_turn_context", None),
    )
    return result.to_dict()


def _print_submission_runtime_event(event_type: str, payload: dict[str, Any]) -> None:
    if event_type == "loop.activity":
        label = _safe_text(payload.get("label")) or "activity"
        detail = _safe_text(payload.get("detail")) or _safe_text(payload.get("state")) or "running"
        preview = _safe_text(payload.get("preview"))
        output_summary = _safe_text(payload.get("output_summary"))
        parts = [detail]
        if preview:
            parts.append(preview)
        if output_summary:
            parts.append(output_summary)
        suffix = " | ".join(part for part in parts if part).strip()
        print(f"{Colors.DIM}[activity]{Colors.RESET} {label:<10} {suffix}".rstrip())
        return

    if event_type != "loop.turn.completed":
        return

    summary_line = prepared_turn_context_summary_line(payload.get("prepared_context"))
    if not summary_line:
        return
    print(f"{Colors.DIM}[context]{Colors.RESET} prepared {summary_line}")
    details = format_prepared_turn_context_details(
        payload.get("prepared_context"),
        include_header=False,
    )
    for line in details.splitlines():
        print(f"{Colors.DIM}          {line}{Colors.RESET}")


def build_submission_runtime_event_handler() -> Callable[[str, dict[str, Any]], None]:
    stream_open = False

    def _handle(event_type: str, payload: dict[str, Any]) -> None:
        nonlocal stream_open

        if event_type == "loop.llm_event":
            llm_event_type = _safe_text(payload.get("llm_event_type")).lower()
            if llm_event_type == "text_delta":
                chunk = str(payload.get("delta") or "")
                if chunk:
                    print(chunk, end="", flush=True)
                    stream_open = True
                return
            if llm_event_type == "message_stop":
                if stream_open:
                    print("")
                    stream_open = False
                return
            return

        if stream_open:
            print("")
            stream_open = False
        _print_submission_runtime_event(event_type, payload)

    return _handle


async def run_minimal_workflow_via_submission_loop(
    *,
    agent: Agent,
    loop: AgentSubmissionLoop,
    bus: InMemoryLoopMessageBus,
    objective: str,
    surface: str = "cli",
    prepared_context_policy: dict[str, Any] | None = None,
    approval_resolver: Callable[[dict[str, Any]], Awaitable[bool | None] | bool | None] | None = None,
) -> str:
    objective_text = _safe_text(objective)

    async def _stage_runner(
        stage: CoordinatorStage,
        stage_prompt: str,
    ) -> tuple[bool, str, str | None]:
        payload = await run_prompt_via_submission_loop(
            loop=loop,
            bus=bus,
            agent=agent,
            prompt=stage_prompt,
            metadata=_with_prepared_context_policy({
                "surface": surface,
                "mode": "workflow",
                "workflow": "minimal",
                "stage": stage.value,
            }, prepared_context_policy),
            start_new_run=True,
            approval_resolver=approval_resolver,
            event_handler=lambda event_type, payload: _print_submission_runtime_event(event_type, payload),
        )
        state = _safe_text(payload.get("state")).lower()
        stop_reason = _safe_text(payload.get("stop_reason")).lower()
        message = str(payload.get("message") or "").strip()
        error = str(payload.get("error") or "").strip()

        if state == "completed" and stop_reason in {"end_turn", ""}:
            return True, message or "(empty stage summary)", None
        if state == "interrupted" or stop_reason == TurnStopReason.CANCELLED.value:
            return False, "", message or "Task cancelled by user."
        if stop_reason == TurnStopReason.MAX_TURN_REQUESTS.value:
            return False, "", message or "Turn reached max request limit."
        return False, "", message or error or f"Stage {stage.value} failed."

    result, _ = await run_minimal_workflow_with_runner(
        objective=objective_text,
        stage_runner=_stage_runner,
        stop_on_failure=True,
    )
    return format_minimal_workflow_report(
        objective=objective_text,
        result=result,
    )


async def build_agent(
    workspace: Path,
    approval_profile: str | None = None,
    *,
    config: Config,
) -> Agent:
    """Build an Agent instance.

    Args:
        workspace: Workspace directory path

    Returns:
        Agent instance
    """
    return await build_agent_kernel(
        workspace_dir=workspace,
        options=AgentKernelBuildOptions(
            config=config,
            approval_profile=approval_profile,
            console_output=True,
        ),
    )


async def run_interactive_session(
    workspace: Path,
    task: Optional[str] = None,
    approval_profile: str | None = None,
) -> None:
    """Run an interactive CLI session.

    Args:
        workspace: Workspace directory
        task: Optional single task to execute
        approval_profile: Optional runtime execution mode override.
    """
    session_start = datetime.now()

    try:
        config = load_entry_config()
    except Exception as e:
        print(f"{Colors.RED}[X] Failed to load configuration: {e}{Colors.RESET}")
        return

    from .ops.doctor import format_doctor_report, run_startup_self_check

    is_ready, findings = run_startup_self_check(config=config, workspace=workspace.resolve())
    print(format_doctor_report(findings, title="Startup Self-Check"))
    if not is_ready:
        print(f"{Colors.RED}[X] Startup self-check failed. Fix blocking issues before running CLI.{Colors.RESET}")
        return

    print_banner()

    # Build agent
    print(f"{Colors.DIM}Initializing agent...{Colors.RESET}")
    try:
        agent = await build_agent(
            workspace,
            approval_profile=approval_profile,
            config=config,
        )
        agent.console_output = False
    except Exception as e:
        print(f"{Colors.RED}[X] Failed to initialize agent: {e}{Colors.RESET}")
        return

    print_session_info(agent, workspace, str(getattr(agent.llm_client, "model", "unknown") or "unknown"))
    try:
        submission_loop, loop_bus = await create_submission_loop_for_agent(
            agent=agent,
            session_id="cli-session",
        )
    except Exception as e:
        print(f"{Colors.RED}[X] Failed to initialize scheduler loop: {e}{Colors.RESET}")
        await cleanup_mcp_connections()
        return

    lifecycle_runtime = SurfaceSessionLifecycleRuntime(
        surface="cli",
        workspace_dir=workspace.resolve(),
    )

    def _apply_session_lifecycle() -> None:
        def _reset_cli_state() -> None:
            _reset_agent_messages(agent)
            _clear_cli_runtime_task_memory(workspace)

        decision = lifecycle_runtime.ensure_active(
            "cli-session",
            on_reset=_reset_cli_state,
        )
        if not decision.reset:
            return
        reason = _safe_text(decision.reason) or "policy"
        print(
            f"{Colors.YELLOW}[session-reset] "
            f"Session lifecycle reset applied ({reason}).{Colors.RESET}"
        )

    def _current_model_identity() -> tuple[str, str, str] | None:
        return _active_model_identity(agent)

    async def _switch_cli_model(provider_source: str, provider_id: str, model_id: str) -> tuple[str, str, str]:
        nonlocal agent, submission_loop, loop_bus

        replacement = await build_agent_kernel(
            workspace_dir=workspace,
            options=AgentKernelBuildOptions(
                config=config,
                approval_profile=approval_profile,
                requested_provider_source=provider_source,
                requested_provider_id=provider_id,
                requested_model=model_id,
                console_output=False,
            ),
        )
        _copy_agent_session_state(agent, replacement)
        replacement_loop, replacement_bus = await create_submission_loop_for_agent(
            agent=replacement,
            session_id="cli-session",
        )

        await submission_loop.stop()
        agent = replacement
        submission_loop = replacement_loop
        loop_bus = replacement_bus

        identity = _active_model_identity(agent)
        if identity is None:
            raise RuntimeError("Switched agent did not expose an active runtime model.")
        return identity

    async def _rebuild_cli_agent_for_skill_refresh() -> tuple[bool, str]:
        nonlocal agent, submission_loop, loop_bus

        current_identity = _current_model_identity()
        if current_identity is not None:
            replacement = await build_agent_kernel(
                workspace_dir=workspace,
                options=AgentKernelBuildOptions(
                    config=config,
                    approval_profile=approval_profile,
                    requested_provider_source=current_identity[0],
                    requested_provider_id=current_identity[1],
                    requested_model=current_identity[2],
                    console_output=False,
                ),
            )
        else:
            replacement = await build_agent_kernel(
                workspace_dir=workspace,
                options=AgentKernelBuildOptions(
                    config=config,
                    approval_profile=approval_profile,
                    console_output=False,
                ),
            )

        _copy_agent_session_state(agent, replacement)
        replacement_loop, replacement_bus = await create_submission_loop_for_agent(
            agent=replacement,
            session_id="cli-session",
        )
        await submission_loop.stop()
        agent = replacement
        submission_loop = replacement_loop
        loop_bus = replacement_bus
        active_identity = _current_model_identity()
        if active_identity is None:
            return True, str(getattr(agent.llm_client, "model", "unknown") or "unknown")
        return True, _format_model_identity(active_identity)

    # Single task mode
    if task:
        print(f"{Colors.BRIGHT_BLUE}Agent{Colors.RESET} {Colors.DIM}>{Colors.RESET} {task}\n")
        runtime_event_handler = build_submission_runtime_event_handler()
        try:
            _apply_session_lifecycle()
            payload = await run_prompt_via_submission_loop(
                loop=submission_loop,
                bus=loop_bus,
                agent=agent,
                prompt=task,
                metadata={"surface": "cli", "mode": "single_task"},
                start_new_run=True,
                approval_resolver=prompt_cli_approval,
                event_handler=runtime_event_handler,
            )
            _print_submission_failure(payload)
        except Exception as e:
            print(f"{Colors.RED}[X] Error: {e}{Colors.RESET}")
        print_stats(agent, session_start)
        await submission_loop.stop()
        await cleanup_mcp_connections()
        return

    # Interactive mode
    kb = KeyBindings()

    @kb.add("c-j")
    def _(event):
        event.current_buffer.insert_text("\n")

    history_file = Path.home() / ".mini-agent" / ".history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=WordCompleter(
            _build_cli_completer_tokens(),
            ignore_case=True,
            sentence=True,
            match_middle=True,
        ),
        key_bindings=kb,
    )
    prepared_context_policy: dict[str, Any] = {}
    should_exit = False
    local_command_service = LocalOperatorCommandService(
        config_loader=lambda: config,
        mcp_cleanup=cleanup_mcp_connections,
        mcp_snapshot_loader=collect_mcp_operator_snapshot,
        mcp_status_formatter=format_mcp_status,
        mcp_server_list_formatter=format_mcp_server_list,
    )

    def _print_local_operator_result(result) -> None:  # noqa: ANN001
        color = ""
        if getattr(result, "kind", "") == "error":
            color = Colors.RED
        elif getattr(result, "kind", "") == "usage":
            color = Colors.YELLOW
        details = str(getattr(result, "details", "") or "").strip()
        if details:
            if color:
                print(f"{color}{details}{Colors.RESET}")
            else:
                print(details)
        print(f"\n{Colors.DIM}{'-' * 50}{Colors.RESET}\n")

    async def _dispatch_help(_invocation) -> None:  # noqa: ANN001
        print_help()

    async def _dispatch_clear(_invocation) -> None:  # noqa: ANN001
        old_count = len(agent.messages)
        def _reset_cli_state() -> None:
            _reset_agent_messages(agent)
            _clear_cli_runtime_task_memory(workspace)

        lifecycle_runtime.force_reset(
            "cli-session",
            on_reset=_reset_cli_state,
        )
        print(f"{Colors.GREEN}[OK] Cleared {old_count - 1} messages{Colors.RESET}\n")

    async def _dispatch_history(_invocation) -> None:  # noqa: ANN001
        print(f"\n{Colors.BRIGHT_CYAN}Messages: {len(agent.messages)}{Colors.RESET}\n")

    async def _dispatch_stats(_invocation) -> None:  # noqa: ANN001
        print_stats(agent, session_start)

    async def _dispatch_exit(_invocation) -> None:  # noqa: ANN001
        nonlocal should_exit
        print(f"\n{Colors.BRIGHT_YELLOW}Goodbye!{Colors.RESET}\n")
        print_stats(agent, session_start)
        should_exit = True

    async def _dispatch_kb(invocation) -> None:
        action = invocation.action or "status"
        toggle = getattr(agent, "set_knowledge_base_enabled", None)
        result = await local_command_service.execute_kb(
            surface="cli",
            action=action,
            args=invocation.args,
            current_enabled=_knowledge_base_enabled(agent),
            session_label="this session",
            runtime_attached=True,
            toggle_callback=(lambda enabled: bool(toggle(enabled))) if callable(toggle) else None,
            toggle_supported=callable(toggle) or action == "status",
            unsupported_message="KB toggle is not supported by the current agent.",
        )
        _print_local_operator_result(result)

    async def _dispatch_mcp(invocation) -> None:
        action = invocation.action or "status"
        async def _reload_cli_mcp() -> McpReloadOutcome:
            rebuilt, active_model = await _rebuild_cli_agent_for_skill_refresh()
            return McpReloadOutcome(
                rebuilt_runtime=rebuilt,
                active_model_label=active_model,
            )

        result = await local_command_service.execute_mcp(
            surface="cli",
            action=action,
            args=invocation.args,
            reload_callback=_reload_cli_mcp if action == "reload" else None,
        )
        if action == "reload" and result.kind == "info":
            print(
                f"{Colors.GREEN}[OK] {format_cli_mcp_reload_success(McpReloadOutcome(
                    rebuilt_runtime=bool(result.payload.get('rebuilt_runtime')),
                    active_model_label=_safe_text(result.payload.get('active_model_label')) or None,
                ))}{Colors.RESET}"
            )
        _print_local_operator_result(result)

    async def _dispatch_sandbox(invocation) -> None:
        action = invocation.action or "status"
        result = local_command_service.execute_sandbox_status(
            surface="cli",
            action=action,
            args=invocation.args,
            diagnostics=collect_sandbox_diagnostics(agent=agent),
        )
        _print_local_operator_result(result)

    async def _dispatch_model(invocation) -> None:
        plan = prepare_model_command_plan(
            surface="cli",
            args=invocation.args,
            providers=_cli_model_registry(),
            default_action="show",
            allow_show=True,
            extended_actions=False,
            strict_basic_arity=True,
        )
        if isinstance(plan, CommandExecutionResult):
            color = Colors.YELLOW if plan.kind == "usage" else Colors.RED
            print(f"{color}{plan.details}{Colors.RESET}")
            print(f"\n{Colors.DIM}{'-' * 50}{Colors.RESET}\n")
            return

        if plan.action == "show":
            identity = _current_model_identity()
            current_model = str(getattr(agent.llm_client, "model", "unknown") or "unknown")
            print(
                f"{Colors.BRIGHT_CYAN}Selected model:{Colors.RESET} "
                f"{_format_model_identity(identity, fallback_model=current_model)}"
            )
            print(f"\n{Colors.DIM}{'-' * 50}{Colors.RESET}\n")
            return
        if plan.action == "list":
            print(_render_cli_model_catalog(_cli_model_registry(), selected_identity=_current_model_identity()))
            print(f"\n{Colors.DIM}{'-' * 50}{Colors.RESET}\n")
            return
        if plan.action == "use":
            request = plan.request
            if request is None:
                print(
                    f"{Colors.YELLOW}{build_command_usage_text('cli', 'model', action='use')}{Colors.RESET}"
                )
                print(f"\n{Colors.DIM}{'-' * 50}{Colors.RESET}\n")
                return
            current_identity = _current_model_identity()
            if current_identity == request.identity:
                print(
                    f"{Colors.YELLOW}Already using "
                    f"{_format_model_identity(current_identity, fallback_model=request.model_id)}.{Colors.RESET}"
                )
                print(f"\n{Colors.DIM}{'-' * 50}{Colors.RESET}\n")
                return
            try:
                active_identity = await _switch_cli_model(*request.identity)
            except Exception as e:
                print(f"{Colors.RED}[X] Model switch failed: {e}{Colors.RESET}")
                print(f"\n{Colors.DIM}{'-' * 50}{Colors.RESET}\n")
                return
            print(
                f"{Colors.GREEN}[OK] Switched session model to "
                f"{_format_model_identity(active_identity)}{Colors.RESET}"
            )
            print(f"\n{Colors.DIM}{'-' * 50}{Colors.RESET}\n")
            return
        print(f"{Colors.RED}Unknown model action.{Colors.RESET}")

    async def _dispatch_skill(invocation) -> None:
        action = invocation.action or "list"
        result = local_command_service.execute_skill(
            surface="cli",
            workspace=workspace,
            action=action,
            args=invocation.args,
            raw_text=invocation.raw_text,
            agent=agent,
            config=config,
        )
        if result.kind in {"usage", "error"} or not bool(result.payload.get("reload_required")):
            _print_local_operator_result(result)
            return

        feedback = describe_skill_runtime_reload(result.payload)
        try:
            rebuilt, active_model = await _rebuild_cli_agent_for_skill_refresh()
        except Exception as exc:
            print(f"{Colors.YELLOW}[!] {format_cli_skill_reload_failure(feedback, exc)}{Colors.RESET}")
            _print_local_operator_result(result)
            return

        success_message = format_cli_skill_reload_success(
            feedback,
            rebuilt=rebuilt,
            active_model=_safe_text(active_model),
        )
        if success_message:
            print(f"{Colors.GREEN}[OK] {success_message}{Colors.RESET}")
        _print_local_operator_result(result)

    async def _dispatch_compaction(invocation) -> None:
        reason = invocation.joined_args() or None
        try:
            payload = await run_loop_control_via_submission_loop(
                loop=submission_loop,
                bus=loop_bus,
                action=invocation.name,
                reason=reason,
            )
            _print_loop_control_result(invocation.name, payload)
        except Exception as e:
            print(f"{Colors.RED}[X] {invocation.name} failed: {e}{Colors.RESET}")
        print(f"\n{Colors.DIM}{'-' * 50}{Colors.RESET}\n")

    command_dispatcher = CommandDispatcher(
        surface="cli",
        aliases={
            "q": "exit",
            "quit": "exit",
            "drop-memories": "drop_memories",
        },
    )
    command_dispatcher.register("help", _dispatch_help, aliases=["h", "?"])
    command_dispatcher.register("clear", _dispatch_clear)
    command_dispatcher.register("history", _dispatch_history)
    command_dispatcher.register("stats", _dispatch_stats)
    command_dispatcher.register("kb", _dispatch_kb)
    command_dispatcher.register("mcp", _dispatch_mcp)
    command_dispatcher.register("sandbox", _dispatch_sandbox)
    command_dispatcher.register("skill", _dispatch_skill)
    command_dispatcher.register("model", _dispatch_model)
    command_dispatcher.register("compact", _dispatch_compaction)
    command_dispatcher.register("drop_memories", _dispatch_compaction, aliases=["drop-memories"])
    command_dispatcher.register("exit", _dispatch_exit, aliases=["quit", "q"])

    while True:
        try:
            user_input = await session.prompt_async(
                [("class:prompt", "You"), ("", " 鈥?")],
                multiline=False,
            )
            user_input = user_input.strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                raw_command = user_input[1:].strip()
                if not raw_command:
                    continue
                try:
                    invocation = parse_command_text(
                        raw_command,
                        surface="cli",
                        aliases=command_dispatcher.aliases,
                    )
                except CommandParseError as exc:
                    print(f"{Colors.RED}Invalid command: {exc}{Colors.RESET}")
                    continue

                if await command_dispatcher.dispatch(invocation):
                    if should_exit:
                        break
                    continue

                command_name = invocation.name
                command_args = invocation.args

                if command_name == "workflow":
                    objective_parts = command_args
                    if command_args and normalize_command_name(command_args[0]) == "run":
                        objective_parts = command_args[1:]
                    objective = " ".join(objective_parts).strip()
                    if not objective:
                        print(
                            f"{Colors.YELLOW}{build_command_usage_text('cli', 'workflow', action='run')}{Colors.RESET}"
                        )
                        continue
                    print(
                        f"\n{Colors.BRIGHT_BLUE}Agent{Colors.RESET} "
                        f"{Colors.DIM}> Running minimal workflow...{Colors.RESET}\n"
                    )
                    try:
                        _apply_session_lifecycle()
                        report = await run_minimal_workflow_via_submission_loop(
                            agent=agent,
                            loop=submission_loop,
                            bus=loop_bus,
                            objective=objective,
                            surface="cli",
                            prepared_context_policy=prepared_context_policy,
                            approval_resolver=prompt_cli_approval,
                        )
                        print(report)
                    except Exception as e:
                        print(f"{Colors.RED}[X] Workflow failed: {e}{Colors.RESET}")
                    print(f"\n{Colors.DIM}{'-' * 50}{Colors.RESET}\n")
                    continue
                elif command_name == "context":
                    plan = prepare_context_command_plan(args=command_args, default_action="show")
                    result = local_command_service.execute_context(
                        surface="cli",
                        action=plan.action,
                        args=list(plan.args),
                        current_policy=prepared_context_policy,
                        prepared_context=getattr(agent, "last_prepared_turn_context", None),
                        prepared_context_diagnostics=getattr(agent, "prepared_context_diagnostics", None),
                        session_label="this session",
                    )
                    updated_policy = result.payload.get("policy")
                    if isinstance(updated_policy, dict):
                        prepared_context_policy = updated_policy
                    _print_local_operator_result(result)
                    continue
                elif command_name == "memory":
                    plan = prepare_memory_command_plan(
                        surface="cli",
                        args=command_args,
                    )
                    if isinstance(plan, CommandExecutionResult):
                        _print_local_operator_result(plan)
                        continue
                    try:
                        result = _run_cli_memory_action(
                            command_service=local_command_service,
                            workspace=workspace,
                            agent=agent,
                            action=plan.action,
                            engram_id=plan.engram_id,
                            content=plan.content,
                            query=plan.query,
                            day=plan.day,
                            export_format=plan.export_format,
                            detail_mode=plan.detail_mode,
                        )
                    except Exception as e:
                        print(f"{Colors.RED}[X] {plan.failure_detail_prefix}{e}{Colors.RESET}")
                        continue
                    if plan.is_mutation:
                        print(f"{Colors.GREEN}[OK] {result['summary']}{Colors.RESET}")
                    details = str(result.get("details") or "").strip()
                    if details:
                        print(details)
                    print(f"\n{Colors.DIM}{'-' * 50}{Colors.RESET}\n")
                    continue
                else:
                    hint = suggest_command_name(
                        command_name,
                        surface="cli",
                        extra_candidates=set(command_dispatcher.known_commands()) | set(command_dispatcher.aliases),
                    )
                    print(f"{Colors.RED}Unknown command: /{command_name}.{hint}{Colors.RESET}")
                    continue

            # Normal message
            print(f"\n{Colors.BRIGHT_BLUE}Agent{Colors.RESET} {Colors.DIM}> Thinking...{Colors.RESET}\n")
            runtime_event_handler = build_submission_runtime_event_handler()
            try:
                _apply_session_lifecycle()
                payload = await run_prompt_via_submission_loop(
                    loop=submission_loop,
                    bus=loop_bus,
                    agent=agent,
                    prompt=user_input,
                    metadata=_with_prepared_context_policy(
                        {"surface": "cli", "mode": "interactive"},
                        prepared_context_policy,
                    ),
                    start_new_run=True,
                    approval_resolver=prompt_cli_approval,
                    event_handler=runtime_event_handler,
                )
                _print_submission_failure(payload)
            except Exception as e:
                print(f"{Colors.RED}[X] Error: {e}{Colors.RESET}")

            print(f"\n{Colors.DIM}{'-' * 50}{Colors.RESET}\n")

        except KeyboardInterrupt:
            print(f"\n\n{Colors.BRIGHT_YELLOW}Interrupted. Goodbye!{Colors.RESET}\n")
            print_stats(agent, session_start)
            break

    await submission_loop.stop()
    await cleanup_mcp_connections()


def main() -> None:
    """Standalone entry point for CLI mode."""
    import argparse

    parser = argparse.ArgumentParser(description="Mini-Agent CLI - Interactive Terminal")
    parser.add_argument(
        "--task", "-t",
        type=str,
        default=None,
        help="Execute a single task and exit",
    )
    parser.add_argument(
        "--workspace", "-w",
        type=str,
        default=None,
        help="Workspace directory",
    )
    parser.add_argument(
        "--agent-mode",
        dest="approval_profile",
        type=str,
        choices=["plan", "build"],
        default=None,
        help="Execution mode override",
    )
    parser.add_argument(
        "--access-level",
        type=str,
        choices=["default", "full-access"],
        default=None,
        help="Access level override",
    )

    args = parser.parse_args()
    if args.approval_profile:
        os.environ["MINI_AGENT_APPROVAL_PROFILE"] = args.approval_profile
        os.environ["MINI_AGENT_AGENT_MODE"] = args.approval_profile
    if args.access_level:
        os.environ["MINI_AGENT_ACCESS_LEVEL"] = args.access_level
    workspace = Path(args.workspace) if args.workspace else Path.cwd()

    asyncio.run(
        run_interactive_session(
            workspace=workspace,
            task=args.task,
            approval_profile=args.approval_profile,
        )
    )


if __name__ == "__main__":
    main()

