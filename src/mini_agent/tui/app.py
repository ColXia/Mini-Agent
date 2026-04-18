"""Full-screen terminal UI for Mini-Agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import difflib
import json
from pathlib import Path
import re
import time
import textwrap
from typing import Any, Callable, Sequence

from prompt_toolkit.application import Application
from prompt_toolkit.completion import Completer, WordCompleter
from prompt_toolkit.data_structures import Point
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition, has_focus
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.dimension import Dimension as D
from prompt_toolkit.layout import Float, FloatContainer, HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.containers import ConditionalContainer, ScrollOffsets
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea

from mini_agent.agent_core.engine import Agent, PlannerExecutorHooks, TurnStopReason
from mini_agent.application.support import ApplicationInteractionBinding
from mini_agent.agent_core.session import SessionLifecyclePolicy
from mini_agent.agent_core.kernel import AgentKernelBuildOptions, build_agent_kernel
from mini_agent.agent_core.execution import (
    AgentLoopContext,
    AgentSubmissionLoop,
    CoordinatorStage,
    InMemoryLoopMessageBus,
    format_minimal_workflow_report,
    run_minimal_workflow_with_runner,
    wait_for_loop_event,
    wait_for_submission_completion,
)
from mini_agent.agent_core.context.context_compaction import estimate_tokens
from mini_agent.memory.diagnostics import (
    build_memory_diagnostics,
    memory_diagnostics_summary_line,
)
from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime
from mini_agent.commands import (
    CommandExecutionResult,
    ContextCommandPlan,
    LocalOperatorCommandService,
    MemoryCommandPlan,
    CommandDispatcher,
    CommandParseError,
    ModelCommandPlan,
    build_command_example_text,
    build_command_help_text,
    build_command_usage_text,
    build_unknown_action_text,
    command_completion_tokens,
    parse_command_text,
    prepare_context_command_plan,
    prepare_memory_command_plan,
    prepare_model_command_plan,
    suggest_command_name,
)
from mini_agent.agent_core.skills.workspace_support import (
    list_skill_entries,
    load_workspace_skill_policy,
    resolve_skill_catalog_loader,
    skill_catalog_signature,
    summarize_skill_entries,
)
from mini_agent.agent_core.skills.command_service import SkillCommandRequest
from mini_agent.agent_core.skills.runtime_feedback import describe_skill_runtime_reload
from mini_agent.config import Config
from mini_agent.interfaces import (
    MainAgentRunApprovalRequest,
    MainAgentRunCancelRequest,
    MainAgentSessionApprovalRequest,
    MainAgentSessionContextRequest,
    MainAgentSessionControlRequest,
    MainAgentSessionCreateRequest,
    MainAgentDefaultSessionRequest,
    MainAgentSessionForkRequest,
    MainAgentSessionMemoryRequest,
    MainAgentSessionModelSelectionRequest,
    MainAgentSessionRuntimePolicyResponse,
    MainAgentSessionRenameRequest,
    MainAgentSessionRuntimePolicyRequest,
    MainAgentSessionShareRequest,
    MainAgentSessionSkillRequest,
    surface_payload_from_dto,
    surface_payload_list_from_dtos,
)
from mini_agent.model_manager.model_registry_service import ModelRegistryService
from mini_agent.model_manager.session_selection_service import (
    SessionModelSelectionRequest,
    SessionModelSelectionService,
)
from mini_agent.runtime.support.sandbox_state import (
    collect_sandbox_diagnostics,
    compact_sandbox_summary,
    sandbox_guardrail_summary,
    sandbox_network_summary,
    sandbox_policy_summary,
)
from mini_agent.runtime.support.session_backed_run_id import build_session_backed_run_id
from mini_agent.runtime.support.session_local_agent_runtime_handler import LocalSessionAgentRuntimeHandler
from mini_agent.runtime.support.session_local_mcp_runtime_service import LocalSessionMcpRuntimeService
from mini_agent.runtime.support.runtime_policy_service import SessionRuntimePolicyService
from mini_agent.runtime.support.session_agent_support import RuntimeSessionAgentSupport
from mini_agent.runtime.live_control.session_cancel_service import SessionCancelService
from mini_agent.runtime.support.session_control_error_service import SessionControlErrorService
from mini_agent.runtime.read_models.session_model_identity_codec import RuntimeSessionModelIdentityCodec
from mini_agent.runtime.read_models.session_payload_codec import RuntimeSessionPayloadCodec
from mini_agent.runtime.support.tooling import reconfigure_agent_runtime_policy
from mini_agent.session import (
    SessionFeedbackService,
    SessionPendingApprovalProjection,
    SessionRecoveryProjection,
    SessionSummaryProjection,
)
from mini_agent.tui.session_approval_command_coordinator import TuiSessionApprovalCommandCoordinator
from mini_agent.tui.session_context_command_coordinator import TuiSessionContextCommandCoordinator
from mini_agent.tui.session_kb_command_coordinator import TuiSessionKbCommandCoordinator
from mini_agent.tui.session_memory_command_coordinator import TuiSessionMemoryCommandCoordinator
from mini_agent.tui.session_mcp_command_coordinator import TuiSessionMcpCommandCoordinator
from mini_agent.tui.session_model_command_coordinator import TuiSessionModelCommandCoordinator
from mini_agent.tui.session_remote_projector import TuiRemoteSessionProjector
from mini_agent.tui.session_remote_turn_stream_coordinator import TuiRemoteTurnStreamCoordinator
from mini_agent.tui.session_runtime_policy_command_coordinator import (
    TuiSessionRuntimePolicyCommandCoordinator,
)
from mini_agent.tui.session_skill_command_coordinator import TuiSessionSkillCommandCoordinator
from mini_agent.tui.gateway_transport_binding import TuiGatewayTransportBinding
from mini_agent.tui.session_turn_outcome_coordinator import TuiSessionTurnOutcomeCoordinator
from mini_agent.tui.session_turn_state_coordinator import TuiSessionTurnStateCoordinator
from mini_agent.tui.session_projection import TerminalSessionProjection
from mini_agent.runtime.support.session_lifecycle import SurfaceSessionLifecycleRuntime
from mini_agent.schema import Message
from mini_agent.tools.mcp_loader import cleanup_mcp_connections
from mini_agent.agent_core.context.turn_context import (
    context_policy_summary_line,
    format_prepared_turn_context_details,
    prepared_turn_context_summary_line,
)
from mini_agent.agent_core.context.control_result_service import (
    SessionContextControlResultService,
)
from mini_agent.transport import (
    GatewayClient,
    RemoteChatClient,
    RemoteSessionClient,
    RemoteWorkspaceClient,
    RemoteStreamErrorService,
    extract_gateway_error_info,
)

SESSION_STATE_VERSION = 7
CHAT_SCROLL_STEP_LINES = 15
AGENT_ACTIVITY_WIDTH = 10
AGENT_ACTIVITY_FRAME_INTERVAL = 0.08
CONTEXT_USAGE_BAR_WIDTH = 12
COMMAND_COMPLETION_MENU_HEIGHT = 8
ASSISTANT_STREAM_CHUNK_SIZE = 24
STREAM_RENDER_INTERVAL_SECONDS = 0.04
SKILL_CATALOG_CHECK_INTERVAL_SECONDS = 2.5
REMOTE_SKILL_MUTATION_ACTIONS = frozenset(
    {
        "refresh",
        "mode",
        "enable",
        "disable",
        "reset",
        "install",
        "uninstall",
        "rollback",
    }
)


def _now_label() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _label_from_iso_timestamp(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return _now_label()
    try:
        return datetime.fromisoformat(raw).astimezone().strftime("%H:%M:%S")
    except Exception:
        return _now_label()


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _safe_session_title(value: str, *, fallback: str) -> str:
    cleaned = _safe_text(value)
    return cleaned or fallback


def _safe_model_filter(value: str) -> str:
    return _safe_text(value).lower()


def _truncate_inline(value: Any, *, limit: int) -> str:
    cleaned = _safe_text(value)
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: max(0, limit - 3)]}..."


def _safe_nonnegative_int(value: Any, *, default: int = 0) -> int:
    try:
        parsed = int(value or 0)
    except Exception:
        return max(0, int(default))
    return max(0, parsed)


def _format_token_compact(value: Any) -> str:
    number = _safe_nonnegative_int(value)
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}m"
    if number >= 10_000:
        return f"{number / 1_000:.1f}k"
    if number >= 1_000:
        return f"{number / 1_000:.1f}k"
    return str(number)


def _role_heading(role: str) -> str:
    normalized = _safe_text(role).lower()
    if normalized == "user":
        return "YOU"
    if normalized == "assistant":
        return "MINI-AGENT"
    if normalized == "command":
        return "COMMAND"
    if normalized == "system":
        return "SYSTEM"
    if normalized == "tool":
        return "ACTIVITY"
    return normalized.upper() or "MESSAGE"


def _normalize_chat_content(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.expandtabs(4)


def _preserve_message_text(value: Any) -> str:
    return _normalize_chat_content(value).strip()


def _preview_line_text(value: Any) -> str:
    text = _preserve_message_text(value)
    if not text:
        return ""
    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("```"):
            continue
        if stripped.startswith("#"):
            return _safe_text(stripped.lstrip("#").strip())
        if stripped.startswith(">"):
            return _safe_text(stripped.lstrip(">").strip())
        if stripped.startswith(("-", "*")):
            return _safe_text(stripped[1:].strip())
        first_token = stripped.split(" ", 1)[0]
        if first_token.endswith(".") and first_token[:-1].isdigit():
            return _safe_text(stripped[len(first_token) :].strip())
        return _safe_text(stripped)
    return ""


def _format_assistant_content(value: Any) -> str:
    text = _preserve_message_text(value)
    if not text:
        return ""

    lines = text.split("\n")
    formatted: list[str] = []
    in_code_block = False
    pending_blank = False

    def _flush_blank() -> None:
        nonlocal pending_blank
        if pending_blank and formatted and formatted[-1] != "":
            formatted.append("")
        pending_blank = False

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            _flush_blank()
            formatted.append(line)
            in_code_block = not in_code_block
            continue

        if in_code_block:
            formatted.append(line)
            continue

        if not stripped:
            pending_blank = True
            continue

        first_token = stripped.split(" ", 1)[0]
        is_numbered_item = first_token.endswith(".") and first_token[:-1].isdigit()
        is_block_start = stripped.startswith(("#", "-", "*", ">")) or is_numbered_item
        if is_block_start:
            _flush_blank()
            formatted.append(line)
            continue

        sentence_breaks = ("\u3002", "\uff01", "\uff1f", ". ", "! ", "? ")
        if len(stripped) >= 72 and any(token in stripped for token in sentence_breaks):
            _flush_blank()
            buffer = stripped
            paragraph_lines: list[str] = []
            for separator in sentence_breaks:
                if separator not in buffer:
                    continue
                if separator.endswith(" "):
                    parts = [part.strip() for part in buffer.split(separator) if part.strip()]
                    if len(parts) > 1:
                        paragraph_lines = [f"{part}{separator.strip()}" for part in parts[:-1]] + [parts[-1]]
                        break
                else:
                    parts = [part.strip() for part in buffer.split(separator) if part.strip()]
                    if len(parts) > 1:
                        paragraph_lines = [f"{part}{separator}" for part in parts[:-1]] + [parts[-1]]
                        break
            if paragraph_lines:
                for paragraph_line in paragraph_lines:
                    formatted.append(paragraph_line)
                pending_blank = True
                continue

        _flush_blank()
        formatted.append(line)

    while formatted and formatted[-1] == "":
        formatted.pop()
    return "\n".join(formatted)


def _thinking_stage_label(detail: str) -> str:
    normalized = _safe_text(detail).lower()
    if not normalized:
        return "thinking"
    if normalized == "starting run":
        return "starting"
    if "planned" in normalized:
        return "planning"
    if "preparing final response" in normalized:
        return "drafting"
    if normalized == "response ready":
        return "ready"
    if normalized == "agent unavailable":
        return "agent unavailable"
    if normalized == "turn limit reached":
        return "turn limit"
    if normalized == "cancelled":
        return "cancelled"
    if normalized in {"run failed", "exception raised"}:
        return "failed"
    return normalized


def _default_session_state_path(workspace: Path) -> Path:
    return workspace / ".mini-agent" / "tui_sessions.json"


def _serialize_agent_message(value: Any) -> dict[str, Any]:
    payload = surface_payload_from_dto(value)
    if not payload:
        if isinstance(value, dict):
            payload = dict(value)
        elif hasattr(value, "__dict__"):
            payload = dict(vars(value))
        else:
            payload = {"role": "assistant", "content": str(value)}

    serialized = {
        "role": _safe_text(payload.get("role")) or "assistant",
        "content": payload.get("content", ""),
    }
    for key in ("thinking", "tool_calls", "tool_call_id", "name"):
        if payload.get(key) is not None:
            serialized[key] = payload.get(key)
    return serialized


def _fallback_agent_messages_from_chat(messages: Sequence["ChatEntry"]) -> list[dict[str, Any]]:
    restored: list[dict[str, Any]] = []
    for entry in messages:
        role = _safe_text(getattr(entry, "role", "")).lower()
        if role not in {"user", "assistant"}:
            continue
        content = _preserve_message_text(getattr(entry, "content", ""))
        if not content:
            continue
        restored.append(
            {
                "role": role,
                "content": content,
            }
        )
    return restored


def _copy_serialized_messages(values: Sequence[dict[str, Any]] | None) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    for item in values or []:
        if isinstance(item, dict):
            copied.append(dict(item))
    return copied


def _append_task_note(existing: str, addition: str) -> str:
    base = _safe_text(existing)
    extra = _safe_text(addition)
    if not extra:
        return base
    if not base:
        return extra
    if extra in base:
        return base
    return f"{base}; {extra}"

def _resume_agent_messages_from_history(
    messages: Sequence[dict[str, Any]],
    *,
    prompt: str,
) -> list[dict[str, Any]]:
    restored = _copy_serialized_messages(messages)
    prompt_text = _preserve_message_text(prompt)
    if not restored or not prompt_text:
        return restored

    last = restored[-1]
    if _safe_text(last.get("role")).lower() == "user" and _preserve_message_text(last.get("content")) == prompt_text:
        return restored[:-1]
    return restored


@dataclass
class ChatEntry:
    role: str
    content: str
    timestamp: str = field(default_factory=_now_label)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatRenderLine:
    text: str
    style: str = ""
    prefix: str = ""
    prefix_style: str = ""


@dataclass
class TaskEntry:
    task_id: str
    prompt: str
    status: str
    created_at: str = field(default_factory=_now_label)
    updated_at: str = field(default_factory=_now_label)
    submission_id: str = ""
    stop_reason: str = ""
    note: str = ""


@dataclass(slots=True)
class TuiSessionSupplementalState:
    """TUI-local sync and recovery summary cache.

    These fields are derived from remote sync or local resume flow and exist only
    to support surface behavior. They are not shared session truth.
    """

    remote_message_count: int = 0
    remote_updated_at: str | None = None
    remote_recovery_state: str = ""
    remote_recovery_summary: str = ""
    remote_last_activity_summary: str = ""
    remote_last_command_summary: str = ""
    recovery_running_state: str = ""
    recovery_pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    remote_run_id: str = ""
    remote_run_status: str = ""
    remote_run_phase: str = ""
    remote_run_busy: bool = False
    remote_run_running_state: str = ""
    remote_run_control_mode: str = ""
    remote_run_interrupt_requested: bool = False
    remote_run_cancel_requested: bool = False
    remote_run_resumable: bool = False
    remote_run_waiting_on_approval: bool = False
    remote_run_active_wait_id: str | None = None
    remote_run_approval_wait: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TuiSessionProjectionState:
    """Shared-session projection cache for TUI presentation.

    This mirrors gateway/runtime session detail for rendering and operator flow.
    It must never be treated as canonical session truth.
    """

    origin_surface: str = "tui"
    active_surface: str = "tui"
    reply_enabled: bool = False
    busy: bool = False
    running_state: str = ""
    is_default: bool = False
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    shared: bool = False
    token_usage: int = 0
    token_limit: int = 0
    knowledge_base_enabled: bool | None = None
    selected_model_source: str | None = None
    selected_provider_id: str | None = None
    selected_model_id: str | None = None
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    last_prepared_context: dict[str, Any] = field(default_factory=dict)
    prepared_context_diagnostics: dict[str, Any] = field(default_factory=dict)
    memory_diagnostics: dict[str, Any] = field(default_factory=dict)
    sandbox_diagnostics: dict[str, Any] = field(default_factory=dict)
    context_policy: dict[str, Any] = field(default_factory=dict)
    supplemental: TuiSessionSupplementalState = field(default_factory=TuiSessionSupplementalState)


@dataclass(slots=True)
class TuiSessionOperatorState:
    """TUI-local operator-flow cache.

    These fields support local command flow and surface interaction. They may
    mirror remote/runtime detail, but they are not canonical session truth.
    """

    pending_model_source: str | None = None
    pending_provider_id: str | None = None
    pending_model_id: str | None = None
    pending_skill_reload: bool = False
    pending_skill_reload_reason: str = ""


@dataclass(slots=True)
class TuiSessionRuntimeState:
    """TUI-local runtime handles and resume coordination state.

    These fields exist only for local execution ownership inside the TUI surface.
    They are not part of shared/persisted session truth.
    """

    restored_agent_messages: list[dict[str, Any]] = field(default_factory=list)
    pending_resume_task_id: str | None = None
    pending_resume_agent_messages: list[dict[str, Any]] = field(default_factory=list)
    next_task_index: int = 1
    active_task_id: str | None = None
    agent: Agent | None = None
    submission_loop: AgentSubmissionLoop | None = None
    loop_bus: InMemoryLoopMessageBus | None = None
    cancel_event: asyncio.Event | None = None
    pending_resume_started: bool = False


@dataclass(slots=True)
class TuiSessionViewState:
    """Pure TUI presentation state and render caches.

    Nothing in this struct should be consumed as domain truth by runtime/application layers.
    """

    messages: list[ChatEntry] = field(default_factory=list)
    tasks: list[TaskEntry] = field(default_factory=list)
    active_activity_message_index: int | None = None
    activity_details_expanded: bool = False
    command_details_expanded: bool = False
    chat_render_revision: int = 0
    chat_scroll_line: int = 0
    chat_follow_output: bool = True
    usage_cache_signature: str = ""
    usage_cache_estimate: int = 0
    usage_cache_at: float = 0.0


@dataclass(slots=True)
class TuiSession:
    """TUI container over session reference + projection/operator/runtime/view slices."""

    session_id: str
    title: str
    projection: TuiSessionProjectionState = field(default_factory=TuiSessionProjectionState)
    operator: TuiSessionOperatorState = field(default_factory=TuiSessionOperatorState)
    runtime: TuiSessionRuntimeState = field(default_factory=TuiSessionRuntimeState)
    view: TuiSessionViewState = field(default_factory=TuiSessionViewState)


@dataclass(frozen=True)
class SessionDisplayModel:
    source_tag: str
    scope_summary: str
    route_summary: str
    share_state: str
    share_summary: str
    peer_summary: str
    has_external_peer: bool
    show_gateway_panel: bool
    recovery_pending: bool
    last_command_preview: str | None


@dataclass(frozen=True, slots=True)
class RemoteSkillCommandPlan:
    command: str
    action: str
    request_kwargs: dict[str, Any] = field(default_factory=dict)
    skill_name: str | None = None


@dataclass(frozen=True, slots=True)
class SessionCommandPlan:
    command: str
    action: str
    selector: str | None = None
    title: str | None = None
    cursor_delta: int = 0


@dataclass(frozen=True, slots=True)
class McpCommandPlan:
    command: str
    action: str


@dataclass(frozen=True, slots=True)
class KbCommandPlan:
    command: str
    action: str


@dataclass(frozen=True, slots=True)
class SkillCommandPlan:
    command: str
    action: str
    args: tuple[str, ...]
    raw_text: str
    request: SkillCommandRequest


class _ThreadSidebarLexer(Lexer):
    def __init__(self, app: Any) -> None:
        self.app = app

    def lex_document(self, document: Document):
        line_styles = list(getattr(self.app, "_sessions_line_styles", []))

        def _get_line(lineno: int) -> list[tuple[str, str]]:
            if lineno < 0 or lineno >= len(document.lines):
                return []
            line = document.lines[lineno]
            style_key = line_styles[lineno] if lineno < len(line_styles) else "muted:body"
            return self.app._session_line_fragments(line, style_key)

        return _get_line


class _ModelSidebarLexer(Lexer):
    def __init__(self, app: Any) -> None:
        self.app = app

    def lex_document(self, document: Document):
        line_styles = list(getattr(self.app, "_models_line_styles", []))

        def _get_line(lineno: int) -> list[tuple[str, str]]:
            if lineno < 0 or lineno >= len(document.lines):
                return []
            line = document.lines[lineno]
            style_key = line_styles[lineno] if lineno < len(line_styles) else "muted:body"
            return self.app._model_line_fragments(line, style_key)

        return _get_line


class _SlashCommandCompleter(Completer):
    def __init__(self, token_getter: Any) -> None:
        self._token_getter = token_getter

    def get_completions(self, document: Document, complete_event):  # noqa: ANN001
        if not document.text_before_cursor.lstrip().startswith("/"):
            return
        completer = WordCompleter(
            self._token_getter(),
            ignore_case=True,
            sentence=True,
            match_middle=True,
        )
        yield from completer.get_completions(document, complete_event)


def _iter_stream_chunks(text: str, *, chunk_size: int = ASSISTANT_STREAM_CHUNK_SIZE) -> Sequence[str]:
    normalized = str(text or "")
    if not normalized:
        return []

    chunks: list[str] = []
    pending = normalized
    size = max(1, int(chunk_size))
    while pending:
        if pending.startswith("\n"):
            chunks.append("\n")
            pending = pending[1:]
            continue
        split_at = min(len(pending), size)
        newline_at = pending.find("\n", 0, split_at + 1)
        if newline_at > 0:
            chunks.append(pending[:newline_at])
            pending = pending[newline_at:]
            continue
        if split_at < len(pending):
            boundary = max(pending.rfind(" ", 0, split_at), pending.rfind("\t", 0, split_at))
            if boundary >= max(1, split_at // 2):
                split_at = boundary + 1
        chunks.append(pending[:split_at])
        pending = pending[split_at:]
    return chunks


def save_tui_session_state(
    *,
    state_path: Path,
    sessions: Sequence[TuiSession],
    current_session_id: str | None,
) -> None:
    persisted_ids = {_safe_text(session.session_id) for session in sessions if _safe_text(session.session_id)}
    persisted_current_session_id = _safe_text(current_session_id) if _safe_text(current_session_id) in persisted_ids else None
    ui_state: dict[str, dict[str, Any]] = {}
    for session in sessions:
        session_id = _safe_text(session.session_id)
        if not session_id:
            continue
        view = session.view
        ui_state[session_id] = {
            "activity_details_expanded": bool(view.activity_details_expanded),
            "command_details_expanded": bool(view.command_details_expanded),
            "chat_scroll_line": max(0, int(view.chat_scroll_line)),
            "chat_follow_output": bool(view.chat_follow_output),
        }
    payload = {
        "version": SESSION_STATE_VERSION,
        "current_session_id": persisted_current_session_id,
        "session_ui_state": ui_state,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_tui_session_state(state_path: Path) -> tuple[dict[str, dict[str, Any]], str | None]:
    if not state_path.exists():
        return {}, None

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}, None

    if not isinstance(payload, dict):
        return {}, None

    ui_state: dict[str, dict[str, Any]] = {}
    raw_ui_state = payload.get("session_ui_state")
    if isinstance(raw_ui_state, dict):
        for session_id, raw_state in raw_ui_state.items():
            normalized_id = _safe_text(session_id)
            if not normalized_id or not isinstance(raw_state, dict):
                continue
            ui_state[normalized_id] = {
                "activity_details_expanded": bool(raw_state.get("activity_details_expanded", False)),
                "command_details_expanded": bool(raw_state.get("command_details_expanded", False)),
                "chat_scroll_line": max(0, int(raw_state.get("chat_scroll_line", 0) or 0)),
                "chat_follow_output": bool(raw_state.get("chat_follow_output", True)),
            }
    elif isinstance(payload.get("sessions"), list):
        for raw in payload.get("sessions") or []:
            if not isinstance(raw, dict):
                continue
            session_id = _safe_text(raw.get("session_id"))
            if not session_id:
                continue
            ui_state[session_id] = {
                "activity_details_expanded": bool(raw.get("activity_details_expanded", False)),
                "command_details_expanded": bool(raw.get("command_details_expanded", False)),
                "chat_scroll_line": max(0, int(raw.get("chat_scroll_line", 0) or 0)),
                "chat_follow_output": bool(raw.get("chat_follow_output", True)),
            }

    current_session_id = _safe_text(payload.get("current_session_id"))
    return ui_state, (current_session_id or None)


class _NoopApplication:
    def __init__(self, *, style: Style) -> None:
        self.layout = _NoopLayout()
        self.style = style

    def invalidate(self) -> None:
        return

    def exit(self) -> None:
        return

    async def run_async(self) -> None:
        return


class _NoopLayout:
    def __init__(self) -> None:
        self._focused: Any | None = None

    def focus(self, target: Any) -> None:
        self._focused = target

    def has_focus(self, target: Any) -> bool:
        return self._focused is target


class MiniAgentTuiApp:
    """Standalone full-screen terminal UI."""

    def __init__(
        self,
        *,
        workspace: Path,
        approval_profile: str | None = None,
        access_level: str | None = None,
        initial_prompt: str | None = None,
        config_loader: Callable[[], Config],
        registry: ModelRegistryService | None = None,
        gateway_client: GatewayClient | None = None,
        state_path: Path | None = None,
        session_lifecycle_runtime: SurfaceSessionLifecycleRuntime | None = None,
        session_lifecycle_policy: SessionLifecyclePolicy | None = None,
        build_ui: bool = True,
    ) -> None:
        self.workspace = workspace.resolve()
        self.approval_profile = approval_profile
        self.access_level = access_level
        self.default_approval_profile = (_safe_text(approval_profile).lower() or "build")
        self.default_access_level = (_safe_text(access_level).lower() or "default")
        self.initial_prompt = initial_prompt
        self._config_loader = config_loader
        self.registry = registry or ModelRegistryService()
        self._transport_binding = TuiGatewayTransportBinding.from_gateway_client(
            gateway_client or GatewayClient()
        )
        self.gateway_client = self._transport_binding.gateway_client
        self.remote_chat_service = self._transport_binding.chat_client
        self.remote_model_service = self._transport_binding.model_client
        self.remote_run_service = self._transport_binding.run_client
        self.remote_session_service = self._transport_binding.session_client
        self.remote_workspace_service = self._transport_binding.workspace_client
        self._session_payload_codec = RuntimeSessionPayloadCodec()
        self._session_model_identity_codec = RuntimeSessionModelIdentityCodec()
        self._remote_workspace_summary: dict[str, Any] = {}
        self._remote_workspace_runtime_summary: dict[str, Any] = {}
        self._remote_session_projector = TuiRemoteSessionProjector(
            resolve_session_title=lambda projection, fallback: self._remote_session_title_from_projection(
                projection,
                fallback=fallback,
            ),
            normalize_model_identity=self._session_model_identity_codec.normalize_model_identity,
            set_selected_model_identity=self._set_session_selected_model_identity,
            set_pending_model_identity=self._set_session_pending_model_identity,
            normalize_pending_approvals_payload=self._normalize_pending_approvals_payload,
            normalize_memory_diagnostics_payload=self._normalize_memory_diagnostics_payload,
            normalize_sandbox_diagnostics_payload=self._normalize_sandbox_diagnostics_payload,
            normalize_context_policy_payload=self._normalize_context_policy_payload,
            normalize_prepared_context_payload=self._normalize_prepared_context_payload,
            normalize_prepared_context_diagnostics_payload=self._normalize_prepared_context_diagnostics_payload,
            build_chat_entries=self._remote_chat_entries,
            replace_messages=lambda session, messages, preserve_follow_output: self._replace_session_messages(
                session,
                messages,
                preserve_follow_output=preserve_follow_output,
            ),
            last_command_summary=lambda session: self._session_last_command_preview_from_messages(session) or "",
        )
        self._remote_turn_stream = TuiRemoteTurnStreamCoordinator(
            append_activity_line=lambda session, **kwargs: self._append_activity_line(session, **kwargs),
            update_running_state=self._update_running_state,
            record_pending_approval=self._record_pending_approval,
            handle_approval_requested=self._handle_remote_stream_approval_requested,
            pending_approval_token=self._pending_approval_token,
            clear_pending_approval=self._clear_pending_approval,
            handle_approval_resolved=self._handle_remote_stream_approval_resolved,
            append_assistant_stream_chunk=lambda session, chunk, message_index: self._append_assistant_stream_chunk(
                session,
                chunk,
                message_index=message_index,
            ),
            schedule_stream_render=self._schedule_stream_render,
            render_all=self._render_all,
        )
        self.local_command_service = LocalOperatorCommandService(
            config_loader=self._load_runtime_config,
            mcp_cleanup=cleanup_mcp_connections,
        )
        self._local_agent_runtime = LocalSessionAgentRuntimeHandler(
            selected_model_identity=self._session_active_model_identity,
            set_selected_model_identity=self._set_session_selected_model_identity,
            set_pending_model_identity=self._set_session_pending_model_identity,
            clear_pending_skill_reload=self._clear_session_skill_reload_pending,
            capture_session_agent_snapshot=self._capture_session_agent_snapshot,
            shutdown_submission_loop=self._shutdown_submission_loop,
            reset_runtime_execution_state=self._reset_local_runtime_execution_state,
            warm_session_agent=self._warm_session_agent,
            format_model_identity=self._format_model_identity,
            persist_session_state=self._persist_session_state,
        )
        self._local_mcp_runtime = LocalSessionMcpRuntimeService(
            agent_runtime=self._local_agent_runtime,
        )
        self._approval_commands = TuiSessionApprovalCommandCoordinator(
            runs_via_gateway=self._runs_via_gateway,
            has_local_runtime_state=self._has_local_runtime_state,
            pending_approval_token=self._pending_approval_token,
            remote_respond_to_approval=self._remote_respond_to_pending_approval,
            sync_remote_session_detail=self._sync_remote_session_detail_for_command,
            clear_pending_approval=self._clear_pending_approval,
            close_approval_modal=self._close_approval_modal,
            append_command_feedback=self._append_command_feedback,
            set_status=self._set_status,
            render_all=self._render_all,
        )
        self._runtime_policy_commands = TuiSessionRuntimePolicyCommandCoordinator(
            session_runtime_policy=self._session_runtime_policy,
            runs_via_gateway=self._runs_via_gateway,
            apply_local_session_runtime_policy=self._apply_local_session_runtime_policy,
            apply_remote_session_runtime_policy=self._apply_remote_session_runtime_policy,
            normalize_sandbox_diagnostics_payload=self._normalize_sandbox_diagnostics_payload,
            append_command_feedback=self._append_command_feedback,
            set_status=self._set_status,
            render_all=self._render_all,
        )
        self._context_commands = TuiSessionContextCommandCoordinator(
            resolve_context_command_plan=self._resolve_context_command_plan,
            refresh_context_snapshot_if_gateway_bound=lambda session: self._refresh_context_snapshot_if_gateway_bound(
                session,
                recent_limit=80,
            ),
            run_context_command_result=self._run_context_command_result,
            execute_context_result=self._execute_context_result,
            runs_via_gateway=self._runs_via_gateway,
            dispatch_remote_context_update=self._dispatch_remote_context_update,
            normalize_context_policy_payload=self._normalize_context_policy_payload,
            has_local_runtime_state=self._has_local_runtime_state,
            capture_local_runtime_projection=self._capture_local_runtime_projection,
            persist_session_state=self._persist_session_state,
            render_all=self._render_all,
        )
        self._memory_commands = TuiSessionMemoryCommandCoordinator(
            resolve_memory_command_plan=self._resolve_memory_command_plan,
            has_local_runtime_state=self._has_local_runtime_state,
            execute_memory_command_plan=self._execute_memory_command_plan,
            append_command_feedback=self._append_command_feedback,
            set_status=self._set_status,
            render_all=self._render_all,
        )
        self._kb_commands = TuiSessionKbCommandCoordinator(
            resolve_kb_command_plan=self._resolve_kb_command_plan,
            runs_via_gateway=self._runs_via_gateway,
            sync_remote_session_detail=self._sync_remote_session_detail_for_command,
            execute_remote_kb_command=self._execute_remote_kb_command,
            execute_local_kb_command=self.local_command_service.execute_kb,
            session_knowledge_base_enabled=self._session_knowledge_base_enabled,
            apply_agent_knowledge_base_enabled=self._apply_agent_knowledge_base_enabled,
            refresh_local_runtime_projection=self._refresh_local_runtime_projection,
            persist_session_state=self._persist_session_state,
            append_command_feedback=self._append_command_feedback,
            set_status=self._set_status,
            render_all=self._render_all,
        )
        self._mcp_commands = TuiSessionMcpCommandCoordinator(
            resolve_mcp_command_plan=self._resolve_mcp_command_plan,
            runs_via_gateway=self._runs_via_gateway,
            dispatch_remote_control_command=self._dispatch_remote_control_command,
            mcp_remote_status_text=self._mcp_remote_status_text,
            execute_local_mcp_command=self.local_command_service.execute_mcp,
            reload_local_mcp_bindings=self._local_mcp_runtime.reload_bindings,
            append_command_feedback=self._append_command_feedback,
            set_status=self._set_status,
            render_all=self._render_all,
        )
        self._skill_commands = TuiSessionSkillCommandCoordinator(
            resolve_skill_command_plan=self._resolve_skill_command_plan,
            runs_via_gateway=self._runs_via_gateway,
            resolve_remote_skill_command_plan=self._resolve_remote_skill_command_plan,
            run_remote_skill_action=self._run_remote_skill_action,
            apply_remote_skill_response=self._apply_remote_skill_response,
            workspace=self.workspace,
            execute_local_skill_command=self.local_command_service.execute_skill,
            apply_local_skill_command_result=self._apply_local_skill_command_result,
            append_command_feedback=self._append_command_feedback,
            set_status=self._set_status,
            render_all=self._render_all,
        )
        self._model_commands = TuiSessionModelCommandCoordinator(
            resolve_model_command_plan=self._resolve_model_command_plan,
            provider_inventory=lambda: self.providers,
            render_model_summary=self._render_model_summary,
            move_model_cursor=self._move_model_cursor,
            apply_selected_model=self._apply_selected_model,
            discover_for_selected_provider=self._discover_for_selected_provider,
            refresh_registry=self._refresh_registry,
            apply_session_model_selection=self._apply_session_model_selection,
            model_use_usage_details=lambda: build_command_usage_text("tui", "model", action="use"),
            set_model_filter=self._set_model_filter,
            model_filter_value=lambda: self.model_filter,
            execute_model_limit_command_plan=self._execute_model_limit_command_plan,
            append_command_feedback=self._append_command_feedback,
            set_status=self._set_status,
            render_all=self._render_all,
        )
        self._turn_state = TuiSessionTurnStateCoordinator()
        self._turn_outcomes = TuiSessionTurnOutcomeCoordinator()
        self.state_path = (
            state_path.expanduser().resolve()
            if state_path is not None
            else _default_session_state_path(self.workspace).resolve()
        )
        self.session_lifecycle_runtime = session_lifecycle_runtime or SurfaceSessionLifecycleRuntime(
            surface="tui",
            workspace_dir=self.workspace,
            policy=session_lifecycle_policy,
        )
        self.build_ui = bool(build_ui)

        self.sessions: list[TuiSession] = []
        self.session_index = 0
        self.providers: list[dict[str, Any]] = []
        self.model_cursor: tuple[int, int] | None = None
        self.model_filter = ""
        self.command_palette_open = False
        self.theme_mode = "dark"
        self.status = "Ready"
        self.background_tasks: set[asyncio.Task[Any]] = set()
        self.remote_poll_interval_seconds = 2.0
        self._remote_sync_task: asyncio.Task[Any] | None = None
        self._remote_sync_started = False
        self._remote_sync_error: str = ""
        self._approval_modal_open = False
        self._approval_modal_choice = "approve"
        self._approval_modal_snoozed_token: str | None = None
        self._sessions_line_styles: list[str] = []
        self._models_line_styles: list[str] = []
        self._chat_render_cache_key: tuple[Any, ...] | None = None
        self._chat_render_cache_lines: list[ChatRenderLine] = []
        self._chat_render_cache_fragments: list[tuple[str, str]] = []
        self._pending_stream_render_task: asyncio.Task[Any] | None = None
        self._last_stream_render_at = 0.0
        self._completion_suppressed_buffers: set[int] = set()
        self._skill_catalog_signature: tuple[str, ...] | None = None
        self._skill_catalog_change_notice = ""
        self._last_skill_catalog_check_at = 0.0
        self._local_skill_policy_snapshot: dict[str, Any] | None = None
        self._session_view_state, self._saved_current_session_id = load_tui_session_state(self.state_path)

        self.status_panel = TextArea(read_only=True, focusable=False, wrap_lines=False, style="class:panel.surface")
        self.sessions_panel = TextArea(
            read_only=True,
            focusable=False,
            wrap_lines=False,
            lexer=_ThreadSidebarLexer(self),
            style="class:panel.surface",
        )
        self.chat_control = FormattedTextControl(
            self._render_chat_fragments,
            focusable=False,
            show_cursor=False,
            get_cursor_position=self._chat_cursor_position,
        )
        self.chat_panel = Window(
            content=self.chat_control,
            wrap_lines=True,
            always_hide_cursor=True,
            right_margins=[ScrollbarMargin(display_arrows=False)],
            scroll_offsets=ScrollOffsets(top=1, bottom=1),
            get_line_prefix=self._chat_line_prefix,
            style="class:chat.panel",
        )
        self.models_panel = TextArea(
            read_only=True,
            focusable=False,
            wrap_lines=False,
            lexer=_ModelSidebarLexer(self),
            style="class:panel.surface",
        )
        self.input_box = TextArea(
            multiline=True,
            prompt="",
            wrap_lines=True,
            scrollbar=True,
            accept_handler=None,
            complete_while_typing=True,
            style="class:panel.surface",
        )
        self.command_box = TextArea(
            multiline=False,
            prompt="Command > ",
            wrap_lines=False,
            accept_handler=self._on_command_submit,
            complete_while_typing=True,
            style="class:panel.surface",
        )
        self.command_help = TextArea(
            read_only=True,
            focusable=False,
            height=8,
            text=self._command_palette_examples(),
            style="class:panel.surface",
        )
        self.input_box.buffer.complete_while_typing = Condition(
            lambda: self._completion_allowed(self.input_box.buffer, slash_only=True)
        )
        self.command_box.buffer.complete_while_typing = Condition(
            lambda: self._completion_allowed(self.command_box.buffer)
        )

        def _trigger_inline_command_completion(*_args: Any) -> None:
            buffer = self.input_box.buffer
            if not self._completion_allowed(buffer, slash_only=True):
                return
            if not buffer.document.text_before_cursor.lstrip().startswith("/"):
                return
            if buffer.complete_state is None:
                buffer.start_completion(select_first=False)

        self.input_box.buffer.on_text_insert += _trigger_inline_command_completion

        self._bootstrap_runtime_sessions_sync()

        self._refresh_registry()
        self._set_status(f"Loaded {len(self.sessions)} runtime session(s). Use /help or Ctrl+K for commands.")

        self._skill_catalog_signature = self._read_skill_catalog_signature()
        self.bindings = self._build_keybindings()
        if self.build_ui:
            self.application: Application[None] | _NoopApplication = self._build_application()
        else:
            self.application = _NoopApplication(style=self._style_for_mode(self.theme_mode))

        self._refresh_command_completer()
        self._render_all()
        self._persist_session_state()

    def _build_application(self) -> Application[None]:
        layout = Layout(self._build_layout(), focused_element=self.input_box)
        return Application(
            layout=layout,
            key_bindings=self.bindings,
            full_screen=True,
            style=self._style_for_mode(self.theme_mode),
            mouse_support=False,
            refresh_interval=AGENT_ACTIVITY_FRAME_INTERVAL,
            before_render=self._before_render,
        )

    def _build_layout(self) -> FloatContainer:
        header = Window(height=1, content=FormattedTextControl(self._render_header))
        footer = Window(height=1, content=FormattedTextControl(self._render_footer))

        self.chat_frame = Frame(
            self.chat_panel,
            title=" Mini-Agent ",
            height=D(weight=1),
        )
        self.prompt_frame = Frame(
            self.input_box,
            title=self._render_prompt_title,
            height=D(min=6, max=12, preferred=8),
        )
        main_column = HSplit(
            [
                self.chat_frame,
                self.prompt_frame,
            ],
            padding=1,
            width=D(weight=5),
            height=D(weight=1),
        )
        sidebar = HSplit(
            [
                Frame(
                    self.sessions_panel,
                    title=" Threads ",
                    height=D(weight=8, min=12, preferred=16),
                ),
                Frame(
                    self.models_panel,
                    title=" Models ",
                    height=D(weight=5, min=10, preferred=12),
                ),
                Frame(
                    self.status_panel,
                    title=" Status ",
                    height=D(weight=4, min=9, preferred=11),
                ),
            ],
            padding=1,
            width=D(min=30, max=42, preferred=34),
            height=D(weight=1),
        )
        body = VSplit(
            [
                main_column,
                sidebar,
            ],
            padding=1,
            height=D(weight=1),
        )

        content = HSplit(
            [
                header,
                body,
                footer,
            ],
            height=D(weight=1),
        )

        palette = ConditionalContainer(
            content=Frame(
                HSplit([self.command_box, self.command_help]),
                title=" Command Palette ",
            ),
            filter=Condition(lambda: self.command_palette_open),
        )
        approval_modal = ConditionalContainer(
            content=Frame(
                Window(
                    content=FormattedTextControl(self._render_approval_modal_fragments),
                    wrap_lines=True,
                    always_hide_cursor=True,
                ),
                title=" Approval ",
                width=D(preferred=80),
                height=D(preferred=12),
            ),
            filter=Condition(self._approval_modal_visible),
        )
        completion_menu = ConditionalContainer(
            content=CompletionsMenu(max_height=COMMAND_COMPLETION_MENU_HEIGHT),
            filter=Condition(self._command_completion_menu_visible),
        )

        return FloatContainer(
            content=content,
            floats=[
                Float(top=2, left=6, right=6, content=palette),
                Float(top=4, left=10, right=10, content=approval_modal),
                Float(xcursor=True, ycursor=True, content=completion_menu),
            ],
        )

    @staticmethod
    def _style_for_mode(mode: str) -> Style:
        if mode == "light":
            return Style.from_dict(
                {
                    "divider": "fg:#666666",
                    "frame.border": "fg:#9ba3af",
                    "frame.label": "fg:#0f4c5c bold",
                    "panel.surface": "fg:#1f2937",
                    "header.activity.busy": "fg:#9a3412 bold",
                    "header.activity.idle": "fg:#64748b",
                    "header.activity.bracket": "fg:#94a3b8",
                    "header.activity.bracket.active": "fg:#f59e0b",
                    "header.activity.head": "fg:#b45309 bold",
                    "header.activity.tail": "fg:#d97706",
                    "header.activity.trail": "fg:#f59e0b",
                    "header.metric.value": "fg:#0f4c5c bold",
                    "header.usage.bracket": "fg:#94a3b8",
                    "header.usage.fill.low": "fg:#0f766e bold",
                    "header.usage.fill.medium": "fg:#b45309 bold",
                    "header.usage.fill.high": "fg:#b91c1c bold",
                    "header.usage.empty": "fg:#cbd5e1",
                    "chat.panel": "fg:#dbeafe bg:#0b1220",
                    "chat.empty.title": "fg:#0f4c5c bold",
                    "chat.empty.body": "fg:#4b5563",
                    "chat.meta": "fg:#52606d italic",
                    "chat.role.user": "fg:#8b5a00 bold",
                    "chat.role.assistant": "fg:#0f4c5c bold",
                    "chat.role.command": "fg:#7c2d12 bold",
                    "chat.role.system": "fg:#1d4ed8 bold",
                    "chat.role.tool": "fg:#9a3412 bold",
                    "chat.body": "fg:#1f2937",
                    "chat.body.system": "fg:#475569",
                    "chat.body.assistant.heading": "fg:#0f4c5c bold underline",
                    "chat.body.assistant.list": "fg:#334155",
                    "chat.body.assistant.quote": "fg:#475569 italic",
                    "chat.body.assistant.code.fence": "fg:#0f4c5c bold",
                    "chat.body.assistant.code.border": "fg:#0f4c5c bold bg:#ddeaf4",
                    "chat.body.assistant.code": "fg:#0b4f6c bg:#e8f1f8",
                    "chat.body.command": "fg:#334155",
                    "chat.body.command.summary": "fg:#7c2d12 bold",
                    "chat.body.command.summary.error": "fg:#b91c1c bold",
                    "chat.body.command.meta": "fg:#92400e",
                    "chat.body.command.output": "fg:#475569",
                    "chat.body.command.output.error": "fg:#991b1b",
                    "chat.body.tool": "fg:#7c2d12",
                    "chat.body.tool.thinking": "fg:#7c3aed italic",
                    "chat.body.tool.thinking.old": "fg:#a78bfa",
                    "chat.body.tool.shell": "fg:#9a3412 bold",
                    "chat.body.tool.shell.old": "fg:#c2410c",
                    "chat.body.tool.read": "fg:#0f766e bold",
                    "chat.body.tool.read.old": "fg:#2dd4bf",
                    "chat.body.tool.search": "fg:#1d4ed8 bold",
                    "chat.body.tool.search.old": "fg:#60a5fa",
                    "chat.body.tool.write": "fg:#b45309 bold",
                    "chat.body.tool.write.old": "fg:#f59e0b",
                    "chat.body.tool.generic": "fg:#7c2d12 bold",
                    "chat.body.tool.generic.old": "fg:#c2410c",
                    "chat.body.tool.meta": "fg:#92400e",
                    "chat.body.tool.meta.old": "fg:#b45309",
                    "chat.body.tool.output": "fg:#7c2d12",
                    "chat.body.tool.output.old": "fg:#b45309",
                    "chat.prefix.user": "fg:#d4a017 bold",
                    "chat.prefix.assistant": "fg:#0f766e bold",
                    "chat.prefix.command": "fg:#b45309 bold",
                    "chat.prefix.system": "fg:#2563eb bold",
                    "chat.prefix.tool": "fg:#c2410c bold",
                    "sidebar.section": "fg:#0f4c5c bold",
                    "sidebar.hint": "fg:#64748b",
                    "sidebar.thread.current.marker": "fg:#0f766e bold",
                    "sidebar.thread.current.title": "fg:#0f4c5c bold",
                    "sidebar.thread.current.meta": "fg:#0369a1 bold",
                    "sidebar.thread.current.tag.live": "fg:#0f766e bold",
                    "sidebar.thread.current.tag.focus": "fg:#b45309 bold",
                    "sidebar.thread.current.tag.remote": "fg:#7c3aed bold",
                    "sidebar.thread.current.tag.source": "fg:#0891b2 bold",
                    "sidebar.thread.current.label": "fg:#075985 bold",
                    "sidebar.thread.current.pipe": "fg:#38bdf8",
                    "sidebar.thread.current.value": "fg:#0f172a bold",
                    "sidebar.thread.current.divider": "fg:#38bdf8",
                    "sidebar.thread.near.marker": "fg:#0284c7",
                    "sidebar.thread.near.title": "fg:#0f4c5c",
                    "sidebar.thread.near.meta": "fg:#64748b",
                    "sidebar.thread.near.tag.live": "fg:#0f766e",
                    "sidebar.thread.near.tag.focus": "fg:#b45309",
                    "sidebar.thread.near.tag.remote": "fg:#7c3aed",
                    "sidebar.thread.near.tag.source": "fg:#0891b2",
                    "sidebar.thread.near.label": "fg:#475569",
                    "sidebar.thread.near.pipe": "fg:#94a3b8",
                    "sidebar.thread.near.value": "fg:#334155",
                    "sidebar.thread.near.divider": "fg:#cbd5e1",
                    "sidebar.thread.muted.marker": "fg:#94a3b8",
                    "sidebar.thread.muted.title": "fg:#475569",
                    "sidebar.thread.muted.meta": "fg:#94a3b8",
                    "sidebar.thread.muted.tag.live": "fg:#64748b",
                    "sidebar.thread.muted.tag.focus": "fg:#64748b",
                    "sidebar.thread.muted.tag.remote": "fg:#64748b",
                    "sidebar.thread.muted.tag.source": "fg:#64748b",
                    "sidebar.thread.muted.label": "fg:#64748b",
                    "sidebar.thread.muted.pipe": "fg:#cbd5e1",
                    "sidebar.thread.muted.value": "fg:#475569",
                    "sidebar.thread.muted.divider": "fg:#dbe4ee",
                    "sidebar.model.current.marker": "fg:#0f766e bold",
                    "sidebar.model.current.title": "fg:#0f4c5c bold",
                    "sidebar.model.current.meta": "fg:#0369a1 bold",
                    "sidebar.model.current.label": "fg:#075985 bold",
                    "sidebar.model.current.pipe": "fg:#38bdf8",
                    "sidebar.model.current.value": "fg:#0f172a bold",
                    "sidebar.model.near.marker": "fg:#0284c7",
                    "sidebar.model.near.title": "fg:#0f4c5c",
                    "sidebar.model.near.meta": "fg:#64748b",
                    "sidebar.model.near.label": "fg:#475569",
                    "sidebar.model.near.pipe": "fg:#94a3b8",
                    "sidebar.model.near.value": "fg:#334155",
                    "sidebar.model.muted.marker": "fg:#94a3b8",
                    "sidebar.model.muted.title": "fg:#475569",
                    "sidebar.model.muted.meta": "fg:#94a3b8",
                    "sidebar.model.muted.label": "fg:#64748b",
                    "sidebar.model.muted.pipe": "fg:#cbd5e1",
                    "sidebar.model.muted.value": "fg:#475569",
                }
            )
        return Style.from_dict(
            {
                "divider": "fg:#666666",
                "frame.border": "fg:#4b5563",
                "frame.label": "fg:#9dd9f3 bold",
                "panel.surface": "fg:#dbeafe",
                "header.activity.busy": "fg:#f6ad55 bold",
                "header.activity.idle": "fg:#7c8aa0",
                "header.activity.bracket": "fg:#64748b",
                "header.activity.bracket.active": "fg:#f59e0b",
                "header.activity.head": "fg:#fde68a bold",
                "header.activity.tail": "fg:#f6ad55",
                "header.activity.trail": "fg:#fb923c",
                "header.metric.value": "fg:#f8fafc bold",
                "header.usage.bracket": "fg:#64748b",
                "header.usage.fill.low": "fg:#22c55e bold",
                "header.usage.fill.medium": "fg:#f59e0b bold",
                "header.usage.fill.high": "fg:#f87171 bold",
                "header.usage.empty": "fg:#334155",
                "chat.panel": "fg:#dbeafe bg:#0b1220",
                "chat.empty.title": "fg:#7ed6a5 bold",
                "chat.empty.body": "fg:#94a3b8",
                "chat.meta": "fg:#7c8aa0 italic",
                "chat.role.user": "fg:#f6c177 bold",
                "chat.role.assistant": "fg:#7dd3fc bold",
                "chat.role.command": "fg:#fdba74 bold",
                "chat.role.system": "fg:#93c5fd bold",
                "chat.role.tool": "fg:#f6ad55 bold",
                "chat.body": "fg:#e2e8f0",
                "chat.body.system": "fg:#cbd5e1",
                "chat.body.assistant.heading": "fg:#7dd3fc bold underline",
                "chat.body.assistant.list": "fg:#dbeafe",
                "chat.body.assistant.quote": "fg:#cbd5e1 italic",
                "chat.body.assistant.code.fence": "fg:#67e8f9 bold",
                "chat.body.assistant.code.border": "fg:#67e8f9 bold bg:#13263d",
                "chat.body.assistant.code": "fg:#f8fafc bg:#162033",
                "chat.body.command": "fg:#cbd5e1",
                "chat.body.command.summary": "fg:#fdba74 bold",
                "chat.body.command.summary.error": "fg:#fda4af bold",
                "chat.body.command.meta": "fg:#f59e0b",
                "chat.body.command.output": "fg:#e2e8f0",
                "chat.body.command.output.error": "fg:#fecdd3",
                "chat.body.tool": "fg:#fde68a",
                "chat.body.tool.thinking": "fg:#c4b5fd italic",
                "chat.body.tool.thinking.old": "fg:#8b5cf6",
                "chat.body.tool.shell": "fg:#f6ad55 bold",
                "chat.body.tool.shell.old": "fg:#fb923c",
                "chat.body.tool.read": "fg:#5eead4 bold",
                "chat.body.tool.read.old": "fg:#2dd4bf",
                "chat.body.tool.search": "fg:#93c5fd bold",
                "chat.body.tool.search.old": "fg:#60a5fa",
                "chat.body.tool.write": "fg:#fdba74 bold",
                "chat.body.tool.write.old": "fg:#fb923c",
                "chat.body.tool.generic": "fg:#fde68a bold",
                "chat.body.tool.generic.old": "fg:#f59e0b",
                "chat.body.tool.meta": "fg:#fdba74",
                "chat.body.tool.meta.old": "fg:#f59e0b",
                "chat.body.tool.output": "fg:#fffbeb",
                "chat.body.tool.output.old": "fg:#fde68a",
                "chat.prefix.user": "fg:#f59e0b bold",
                "chat.prefix.assistant": "fg:#22c55e bold",
                "chat.prefix.command": "fg:#f59e0b bold",
                "chat.prefix.system": "fg:#60a5fa bold",
                "chat.prefix.tool": "fg:#fb923c bold",
                "sidebar.section": "fg:#9dd9f3 bold",
                "sidebar.hint": "fg:#7c8aa0",
                "sidebar.thread.current.marker": "fg:#f6c177 bold",
                "sidebar.thread.current.title": "fg:#7dd3fc bold",
                "sidebar.thread.current.meta": "fg:#67e8f9 bold",
                "sidebar.thread.current.tag.live": "fg:#4ade80 bold",
                "sidebar.thread.current.tag.focus": "fg:#f6c177 bold",
                "sidebar.thread.current.tag.remote": "fg:#c4b5fd bold",
                "sidebar.thread.current.tag.source": "fg:#67e8f9 bold",
                "sidebar.thread.current.label": "fg:#93c5fd bold",
                "sidebar.thread.current.pipe": "fg:#38bdf8",
                "sidebar.thread.current.value": "fg:#e2e8f0 bold",
                "sidebar.thread.current.divider": "fg:#38bdf8",
                "sidebar.thread.near.marker": "fg:#60a5fa",
                "sidebar.thread.near.title": "fg:#9dd9f3",
                "sidebar.thread.near.meta": "fg:#7c8aa0",
                "sidebar.thread.near.tag.live": "fg:#34d399",
                "sidebar.thread.near.tag.focus": "fg:#fdba74",
                "sidebar.thread.near.tag.remote": "fg:#a78bfa",
                "sidebar.thread.near.tag.source": "fg:#7dd3fc",
                "sidebar.thread.near.label": "fg:#94a3b8",
                "sidebar.thread.near.pipe": "fg:#475569",
                "sidebar.thread.near.value": "fg:#cbd5e1",
                "sidebar.thread.near.divider": "fg:#334155",
                "sidebar.thread.muted.marker": "fg:#64748b",
                "sidebar.thread.muted.title": "fg:#94a3b8",
                "sidebar.thread.muted.meta": "fg:#64748b",
                "sidebar.thread.muted.tag.live": "fg:#64748b",
                "sidebar.thread.muted.tag.focus": "fg:#64748b",
                "sidebar.thread.muted.tag.remote": "fg:#64748b",
                "sidebar.thread.muted.tag.source": "fg:#64748b",
                "sidebar.thread.muted.label": "fg:#64748b",
                "sidebar.thread.muted.pipe": "fg:#334155",
                "sidebar.thread.muted.value": "fg:#94a3b8",
                "sidebar.thread.muted.divider": "fg:#1f2937",
                "sidebar.model.current.marker": "fg:#f6c177 bold",
                "sidebar.model.current.title": "fg:#7dd3fc bold",
                "sidebar.model.current.meta": "fg:#67e8f9 bold",
                "sidebar.model.current.label": "fg:#93c5fd bold",
                "sidebar.model.current.pipe": "fg:#38bdf8",
                "sidebar.model.current.value": "fg:#e2e8f0 bold",
                "sidebar.model.near.marker": "fg:#60a5fa",
                "sidebar.model.near.title": "fg:#9dd9f3",
                "sidebar.model.near.meta": "fg:#7c8aa0",
                "sidebar.model.near.label": "fg:#94a3b8",
                "sidebar.model.near.pipe": "fg:#475569",
                "sidebar.model.near.value": "fg:#cbd5e1",
                "sidebar.model.muted.marker": "fg:#64748b",
                "sidebar.model.muted.title": "fg:#94a3b8",
                "sidebar.model.muted.meta": "fg:#64748b",
                "sidebar.model.muted.label": "fg:#64748b",
                "sidebar.model.muted.pipe": "fg:#334155",
                "sidebar.model.muted.value": "fg:#94a3b8",
            }
        )

    def _build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()
        single_line_scroll_filter = Condition(
            lambda: not self.command_palette_open and not self.input_box.buffer.text
        ) & has_focus(self.input_box)
        approval_modal_filter = Condition(self._approval_modal_visible)

        @kb.add("c-c")
        @kb.add("c-q")
        def _exit_(event) -> None:
            self._request_exit()
            event.app.exit()

        @kb.add("c-k")
        def _palette(event) -> None:
            self.command_palette_open = not self.command_palette_open
            if self.command_palette_open:
                event.app.layout.focus(self.command_box)
            else:
                event.app.layout.focus(self.input_box)
            self._render_all()

        @kb.add("escape")
        def _escape(event) -> None:
            if self._approval_modal_visible():
                self._close_approval_modal(snooze=True)
                self._render_all()
                return
            if not self.command_palette_open:
                return
            self.command_palette_open = False
            self.command_box.buffer.document = Document("")
            event.app.layout.focus(self.input_box)
            self._render_all()

        @kb.add("f2")
        def _theme(event) -> None:
            self._toggle_theme()
            event.app.invalidate()

        @kb.add("f4")
        def _activity_toggle(event) -> None:
            self._toggle_activity_details("toggle")
            event.app.invalidate()

        @kb.add("f5")
        def _command_toggle(event) -> None:
            self._toggle_command_details("toggle")
            event.app.invalidate()

        @kb.add("f6")
        def _runtime_mode_toggle(event) -> None:
            session = self.current_session
            current_mode, _current_access = self._session_runtime_policy(session)
            next_mode = "plan" if current_mode == "build" else "build"
            self._schedule(
                self._update_session_runtime_policy(
                    session,
                    approval_profile=next_mode,
                    command_label=next_mode,
                )
            )
            event.app.invalidate()

        @kb.add("f7")
        def _runtime_access_toggle(event) -> None:
            session = self.current_session
            _current_mode, current_access = self._session_runtime_policy(session)
            next_access = "full-access" if current_access == "default" else "default"
            self._schedule(
                self._update_session_runtime_policy(
                    session,
                    access_level=next_access,
                    command_label=next_access,
                )
            )
            event.app.invalidate()

        @kb.add("f8")
        def _approval_modal_toggle(event) -> None:
            if self._approval_modal_visible():
                self._close_approval_modal(snooze=True)
            elif self._open_approval_modal(force=True):
                pass
            else:
                self._set_status("No pending approval request.")
            self._render_all()
            event.app.invalidate()

        @kb.add("c-n")
        def _new_sess(event) -> None:
            self._schedule(self._create_runtime_session())
            self._set_status("Creating a new runtime session...")
            event.app.invalidate()

        @kb.add("c-up")
        @kb.add("c-pageup")
        @kb.add("escape", "up")
        def _sess_prev(event) -> None:
            self._switch_session(-1)
            event.app.invalidate()

        @kb.add("c-down")
        @kb.add("c-pagedown")
        @kb.add("escape", "down")
        def _sess_next(event) -> None:
            self._switch_session(1)
            event.app.invalidate()

        @kb.add("c-left")
        def _model_prev(event) -> None:
            self._move_model_cursor(-1)
            event.app.invalidate()

        @kb.add("c-right")
        def _model_next(event) -> None:
            self._move_model_cursor(1)
            event.app.invalidate()

        @kb.add("c-s")
        def _model_apply(event) -> None:
            self._schedule(self._apply_selected_model())
            event.app.invalidate()

        @kb.add("c-r")
        def _model_discover(event) -> None:
            self._schedule(self._discover_for_selected_provider())
            event.app.invalidate()

        @kb.add("c-x")
        def _cancel_turn(event) -> None:
            self._schedule(self._request_cancel_current_turn_async(emit_system_when_idle=False))
            event.app.invalidate()

        @kb.add(
            "up",
            eager=True,
            is_global=True,
            filter=single_line_scroll_filter,
        )
        def _chat_line_up(event) -> None:
            self._scroll_chat_lines(-1)
            event.app.layout.focus(self.input_box)
            event.app.invalidate()

        @kb.add(
            "down",
            eager=True,
            is_global=True,
            filter=single_line_scroll_filter,
        )
        def _chat_line_down(event) -> None:
            self._scroll_chat_lines(1)
            event.app.layout.focus(self.input_box)
            event.app.invalidate()

        @kb.add(
            "pageup",
            eager=True,
            is_global=True,
            filter=Condition(lambda: not self.command_palette_open),
        )
        def _chat_page_up(event) -> None:
            self._scroll_chat_page(-1)
            event.app.layout.focus(self.input_box)
            event.app.invalidate()

        @kb.add(
            "pagedown",
            eager=True,
            is_global=True,
            filter=Condition(lambda: not self.command_palette_open),
        )
        def _chat_page_down(event) -> None:
            self._scroll_chat_page(1)
            event.app.layout.focus(self.input_box)
            event.app.invalidate()

        @kb.add(
            "c-home",
            eager=True,
            is_global=True,
            filter=Condition(lambda: not self.command_palette_open),
        )
        def _chat_to_top(event) -> None:
            self._scroll_chat_home()
            event.app.layout.focus(self.input_box)
            event.app.invalidate()

        @kb.add(
            "c-end",
            eager=True,
            is_global=True,
            filter=Condition(lambda: not self.command_palette_open),
        )
        def _chat_to_bottom(event) -> None:
            self._scroll_chat_end()
            event.app.layout.focus(self.input_box)
            event.app.invalidate()

        @kb.add("tab", filter=has_focus(self.input_box))
        def _complete_input_command(event) -> None:
            buffer = self.input_box.buffer
            if not buffer.document.text_before_cursor.lstrip().startswith("/"):
                buffer.insert_text("    ")
                event.app.invalidate()
                return
            if buffer.complete_state is None:
                buffer.start_completion(select_first=False)
            else:
                buffer.complete_next()
            event.app.invalidate()

        @kb.add("s-tab", filter=has_focus(self.input_box))
        def _complete_previous_input_command(event) -> None:
            buffer = self.input_box.buffer
            if buffer.complete_state is None:
                return
            buffer.complete_previous()
            event.app.invalidate()

        @kb.add("tab", filter=has_focus(self.command_box))
        def _complete_palette_command(event) -> None:
            buffer = self.command_box.buffer
            if buffer.complete_state is None:
                buffer.start_completion(select_first=False)
            else:
                buffer.complete_next()
            event.app.invalidate()

        @kb.add("s-tab", filter=has_focus(self.command_box))
        def _complete_previous_palette_command(event) -> None:
            buffer = self.command_box.buffer
            if buffer.complete_state is None:
                return
            buffer.complete_previous()
            event.app.invalidate()

        @kb.add(
            "left",
            eager=True,
            is_global=True,
            filter=approval_modal_filter,
        )
        @kb.add(
            "right",
            eager=True,
            is_global=True,
            filter=approval_modal_filter,
        )
        @kb.add(
            "tab",
            eager=True,
            is_global=True,
            filter=approval_modal_filter,
        )
        def _approval_modal_cycle(_event) -> None:
            self._toggle_approval_modal_choice()
            self._render_all()

        @kb.add(
            "s-tab",
            eager=True,
            is_global=True,
            filter=approval_modal_filter,
        )
        def _approval_modal_cycle_reverse(_event) -> None:
            self._toggle_approval_modal_choice(backward=True)
            self._render_all()

        @kb.add(
            "enter",
            eager=True,
            is_global=True,
            filter=approval_modal_filter,
        )
        def _approval_modal_submit(event) -> None:
            self._schedule(self._confirm_approval_modal())
            event.app.invalidate()

        @kb.add(
            "enter",
            eager=True,
            filter=has_focus(self.input_box)
            & Condition(lambda: self.input_box.buffer.complete_state is not None),
        )
        def _accept_input_completion(event) -> None:
            if self._accept_completion(self.input_box.buffer):
                event.app.invalidate()

        @kb.add(
            "enter",
            eager=True,
            filter=has_focus(self.command_box)
            & Condition(lambda: self.command_box.buffer.complete_state is not None),
        )
        def _accept_command_completion(event) -> None:
            if self._accept_completion(self.command_box.buffer):
                event.app.invalidate()

        @kb.add("enter", filter=has_focus(self.input_box))
        def _submit_input(event) -> None:
            self._submit_input_buffer()
            event.app.invalidate()

        @kb.add("escape", "enter", filter=has_focus(self.input_box))
        def _insert_newline(event) -> None:
            self.input_box.buffer.insert_text("\n")
            event.app.invalidate()

        return kb

    def _completion_allowed(self, buffer: Any, *, slash_only: bool = False) -> bool:
        if id(buffer) in self._completion_suppressed_buffers:
            return False
        if slash_only:
            text_before_cursor = _safe_text(getattr(getattr(buffer, "document", None), "text_before_cursor", ""))
            return text_before_cursor.lstrip().startswith("/")
        return True

    def _accept_completion(self, buffer: Any) -> bool:
        state = getattr(buffer, "complete_state", None)
        if state is None:
            return False
        completion = getattr(state, "current_completion", None)
        if completion is None:
            completions = list(getattr(state, "completions", ()) or [])
            if not completions:
                return False
            completion = completions[0]
        buffer_id = id(buffer)
        self._completion_suppressed_buffers.add(buffer_id)
        try:
            buffer.apply_completion(completion)
            cancel_completion = getattr(buffer, "cancel_completion", None)
            if callable(cancel_completion):
                cancel_completion()
            elif getattr(buffer, "complete_state", None) is not None:
                try:
                    buffer.complete_state = None
                except Exception:
                    pass
            return True
        finally:
            self._completion_suppressed_buffers.discard(buffer_id)

    def _render_header(self) -> list[tuple[str, str]]:
        title = self.current_session.title if self.sessions else "No Session"
        thread_count = len(self.sessions)
        workspace_hint = _truncate_inline(self._workspace_header_hint(), limit=18) or "-"
        model_hint = self._current_model_hint()
        approval_profile, access_level = self._session_runtime_policy(self.current_session if self.sessions else None)
        usage = self._session_usage_stats(self.current_session if self.sessions else None)
        fragments: list[tuple[str, str]] = [
            ("class:frame.label", " Mini-Agent "),
            ("class:frame.label", f"| {title} | threads={thread_count} | ws={workspace_hint} | "),
            ("class:header.metric.value", f"mode={approval_profile} "),
            ("class:frame.label", "| "),
            ("class:header.metric.value", f"access={access_level} "),
            ("class:frame.label", f"| model={model_hint} | "),
        ]
        fragments.extend(
            self._context_usage_bar_fragments(
                usage=usage["usage"],
                limit=usage["limit"],
                width=8,
            )
        )
        if usage["limit"] > 0:
            fragments.append(
                (
                    "class:header.metric.value",
                    f" {usage['percent']}% ",
                )
            )
        else:
            fragments.append(("class:header.metric.value", " -- "))
        return fragments

    def _render_prompt_title(self) -> list[tuple[str, str]]:
        _, activity_label, _ = self._agent_activity_display()
        fragments: list[tuple[str, str]] = [("class:frame.label", " Prompt ")]
        fragments.extend(self._agent_activity_bar_fragments(active=activity_label != "idle"))
        fragments.append(
            (
                "class:header.activity.busy" if activity_label != "idle" else "class:header.activity.idle",
                f" {activity_label} ",
            )
        )
        return fragments

    def _render_footer(self) -> list[tuple[str, str]]:
        keys = (
            "Enter send | Esc+Enter newline | Ctrl+K commands | Ctrl+PgUp/PgDn thread | "
            "Ctrl+Left/Right model | Up/Down scroll | PgUp/PgDn +15 lines | Ctrl+End live | Ctrl+S apply | "
            "F4 activity | F5 command | F6 mode | F7 access | F8 approval | Ctrl+X cancel"
        )
        text = f" {self.status} || {keys} "
        return [("", text)]

    def _render_approval_modal_fragments(self) -> list[tuple[str, str]]:
        session = self.current_session if self.sessions else None
        target = self._pending_approval_target(session)
        if session is None or target is None:
            return [("", "No pending approval request.")]

        token = self._pending_approval_token(target) or "(missing token)"
        tool_name = _safe_text(target.get("tool_name")) or "tool"
        reason = _preserve_message_text(target.get("reason")) or "No reason provided."
        preview = _normalize_chat_content(target.get("arguments")).strip()
        if not preview:
            preview = "No arguments preview."
        reason_block = textwrap.fill(reason, width=68)
        preview_block = textwrap.fill(preview, width=68)
        approve_label = "> APPROVE <" if self._approval_modal_choice == "approve" else "  approve  "
        deny_label = "> DENY <" if self._approval_modal_choice == "deny" else "  deny  "

        return [
            ("", f"Session: {session.title}\n"),
            ("", f"Tool: {tool_name}\n"),
            ("", f"Token: {token}\n"),
            ("", "\nReason:\n"),
            ("", f"{reason_block}\n"),
            ("", "\nArguments:\n"),
            ("", f"{preview_block}\n"),
            ("", "\n"),
            ("class:header.metric.value" if self._approval_modal_choice == "approve" else "", approve_label),
            ("", "    "),
            ("class:header.metric.value" if self._approval_modal_choice == "deny" else "", deny_label),
            ("", "\nLeft/Right or Tab switch | Enter confirm | Esc hide"),
        ]

    @staticmethod
    def _estimate_serialized_messages_tokens(raw_messages: Sequence[dict[str, Any]] | None) -> int:
        restored: list[Message] = []
        for raw in raw_messages or []:
            if not isinstance(raw, dict):
                continue
            try:
                restored.append(Message.model_validate(raw))
            except Exception:
                continue
        if not restored:
            return 0
        try:
            return _safe_nonnegative_int(estimate_tokens(restored))
        except Exception:
            return 0

    @staticmethod
    def _usage_cache_signature(raw_messages: Sequence[Any] | None) -> str:
        if not isinstance(raw_messages, Sequence) or not raw_messages:
            return ""
        parts = [str(len(raw_messages))]
        tail = list(raw_messages[-3:])
        for item in tail:
            if isinstance(item, dict):
                role = _safe_text(item.get("role"))
                content = str(item.get("content", ""))
            else:
                role = _safe_text(getattr(item, "role", ""))
                content = str(getattr(item, "content", ""))
            parts.append(f"{role}:{len(content)}")
        return "|".join(parts)

    def _estimate_usage_with_cache(
        self,
        session: TuiSession,
        raw_messages: Sequence[Any] | None,
        *,
        serialized: bool,
    ) -> int:
        view = session.view
        signature = self._usage_cache_signature(raw_messages)
        if (
            signature
            and signature == view.usage_cache_signature
            and (time.monotonic() - float(view.usage_cache_at or 0.0)) < 1.0
        ):
            return _safe_nonnegative_int(view.usage_cache_estimate)
        if serialized:
            estimate_value = self._estimate_serialized_messages_tokens(raw_messages)  # type: ignore[arg-type]
        else:
            try:
                estimate_value = _safe_nonnegative_int(estimate_tokens(raw_messages))
            except Exception:
                estimate_value = 0
        view.usage_cache_signature = signature
        view.usage_cache_estimate = _safe_nonnegative_int(estimate_value)
        view.usage_cache_at = time.monotonic()
        return view.usage_cache_estimate

    @staticmethod
    def _context_usage_bar_text(*, usage: int, limit: int, width: int = CONTEXT_USAGE_BAR_WIDTH) -> str:
        width = max(6, int(width))
        if limit <= 0:
            return "[" + "?" * width + "]"
        ratio = max(0.0, float(usage) / float(limit))
        filled = min(width, int(round(min(1.0, ratio) * width)))
        if usage > 0 and filled == 0:
            filled = 1
        return "[" + ("=" * filled) + ("." * max(0, width - filled)) + "]"

    @classmethod
    def _context_usage_bar_fragments(
        cls,
        *,
        usage: int,
        limit: int,
        width: int = CONTEXT_USAGE_BAR_WIDTH,
    ) -> list[tuple[str, str]]:
        width = max(6, int(width))
        fragments: list[tuple[str, str]] = [("class:header.usage.bracket", "[")]
        if limit <= 0:
            fragments.extend(("class:header.usage.empty", "?") for _ in range(width))
            fragments.append(("class:header.usage.bracket", "]"))
            return fragments

        ratio = max(0.0, float(usage) / float(limit))
        filled = min(width, int(round(min(1.0, ratio) * width)))
        if usage > 0 and filled == 0:
            filled = 1
        if ratio >= 0.85:
            fill_style = "class:header.usage.fill.high"
        elif ratio >= 0.6:
            fill_style = "class:header.usage.fill.medium"
        else:
            fill_style = "class:header.usage.fill.low"
        fragments.extend((fill_style, "=") for _ in range(filled))
        fragments.extend(("class:header.usage.empty", ".") for _ in range(max(0, width - filled)))
        fragments.append(("class:header.usage.bracket", "]"))
        return fragments

    def _session_usage_stats(self, session: TuiSession | None = None) -> dict[str, Any]:
        target = session or (self.current_session if self.sessions else None)
        if target is None:
            return {
                "usage": 0,
                "limit": 0,
                "percent": 0,
                "ratio": 0.0,
                "usage_text": "0",
                "usage_label": "0",
                "budget_text": "0 / --",
                "compact_usage": "0",
                "compact_limit": "--",
                "source": "reported",
                "limit_source": "unknown",
            }

        reported_usage = 0
        estimated_usage = 0
        reported_limit = 0
        projection = target.projection
        runtime = target.runtime
        view = target.view

        if runtime.agent is not None:
            reported_usage = _safe_nonnegative_int(getattr(runtime.agent, "api_total_tokens", 0))
            reported_limit = _safe_nonnegative_int(getattr(runtime.agent, "token_limit", 0))
            messages = getattr(runtime.agent, "messages", None)
            if isinstance(messages, list) and messages and reported_usage <= 0:
                estimated_usage = self._estimate_usage_with_cache(
                    target,
                    messages,
                    serialized=False,
                )
        else:
            reported_usage = _safe_nonnegative_int(projection.token_usage)
            reported_limit = _safe_nonnegative_int(projection.token_limit)
            if not self._runs_via_gateway(target) and reported_usage <= 0:
                serialized_messages = (
                    runtime.restored_agent_messages
                    or runtime.pending_resume_agent_messages
                    or _fallback_agent_messages_from_chat(view.messages)
                )
                estimated_usage = self._estimate_usage_with_cache(
                    target,
                    serialized_messages,
                    serialized=True,
                )

        effective_usage = reported_usage
        if runtime.agent is not None or not self._runs_via_gateway(target):
            effective_usage = max(reported_usage, estimated_usage)
        elif effective_usage <= 0:
            effective_usage = estimated_usage

        effective_usage = _safe_nonnegative_int(effective_usage)
        reported_limit = reported_limit or _safe_nonnegative_int(projection.token_limit)
        model_limit, model_limit_source = self._lookup_model_usage_limit(
            self._session_active_model_identity(target)
        )
        limit = model_limit or reported_limit
        if model_limit > 0:
            limit_source = model_limit_source
        elif reported_limit > 0:
            limit_source = "token_limit"
        else:
            limit_source = "unknown"

        if effective_usage > 0:
            projection.token_usage = effective_usage
        if reported_limit > 0:
            projection.token_limit = reported_limit

        percent = 0
        ratio = 0.0
        if limit > 0:
            ratio = max(0.0, float(effective_usage) / float(limit))
            percent = min(999, int(round(ratio * 100)))

        source = "estimated" if reported_usage <= 0 and effective_usage > 0 else "reported"
        usage_label = f"{effective_usage:,}"
        if source == "estimated":
            usage_label = f"{usage_label} est"
        return {
            "usage": effective_usage,
            "limit": limit,
            "percent": percent,
            "ratio": ratio,
            "usage_text": f"{effective_usage:,}",
            "usage_label": usage_label,
            "budget_text": (
                f"{effective_usage:,} / {limit:,}"
                if limit > 0
                else f"{effective_usage:,} / --"
            ),
            "compact_usage": _format_token_compact(effective_usage),
            "compact_limit": _format_token_compact(limit) if limit > 0 else "--",
            "source": source,
            "limit_source": limit_source,
        }

    @staticmethod
    def _agent_activity_frame_index() -> int:
        return int(time.monotonic() / AGENT_ACTIVITY_FRAME_INTERVAL)

    @staticmethod
    def _agent_activity_levels(
        frame_index: int,
        *,
        width: int = AGENT_ACTIVITY_WIDTH,
        hold_start: int = 3,
        hold_end: int = 2,
    ) -> tuple[list[int], bool]:
        width = max(6, int(width))
        total_frames = width + hold_end + (width - 1) + hold_start
        index = frame_index % total_frames

        if index < width:
            position = index
            backward = False
        elif index < width + hold_end:
            position = width - 1
            backward = False
        elif index < width + hold_end + (width - 1):
            backward_index = index - width - hold_end
            position = width - 2 - backward_index
            backward = True
        else:
            position = 0
            backward = True

        levels = [0] * width
        levels[position] = 3
        for distance, level in ((1, 2), (2, 1)):
            trail_index = position + distance if backward else position - distance
            if 0 <= trail_index < width:
                levels[trail_index] = max(levels[trail_index], level)
        return levels, backward

    @classmethod
    def _agent_activity_bar_text(
        cls,
        *,
        active: bool,
        width: int = AGENT_ACTIVITY_WIDTH,
        frame_index: int | None = None,
    ) -> str:
        width = max(6, int(width))
        if not active:
            return "[" + "." * width + "]"

        index = cls._agent_activity_frame_index() if frame_index is None else int(frame_index)
        levels, backward = cls._agent_activity_levels(index, width=width)
        cells: list[str] = []
        for level in levels:
            if level == 3:
                cells.append("<" if backward else ">")
            elif level == 2:
                cells.append("=")
            elif level == 1:
                cells.append("-")
            else:
                cells.append(".")
        return "[" + "".join(cells) + "]"

    @classmethod
    def _agent_activity_bar_fragments(
        cls,
        *,
        active: bool,
        width: int = AGENT_ACTIVITY_WIDTH,
        frame_index: int | None = None,
    ) -> list[tuple[str, str]]:
        width = max(6, int(width))
        bracket_style = "class:header.activity.bracket.active" if active else "class:header.activity.bracket"
        fragments: list[tuple[str, str]] = [(bracket_style, "[")]
        if not active:
            fragments.extend(("class:header.activity.idle", ".") for _ in range(width))
            fragments.append((bracket_style, "]"))
            return fragments

        index = cls._agent_activity_frame_index() if frame_index is None else int(frame_index)
        levels, backward = cls._agent_activity_levels(index, width=width)
        for level in levels:
            if level == 3:
                fragments.append(("class:header.activity.head", "<" if backward else ">"))
            elif level == 2:
                fragments.append(("class:header.activity.tail", "="))
            elif level == 1:
                fragments.append(("class:header.activity.trail", "-"))
            else:
                fragments.append(("class:header.activity.idle", "."))
        fragments.append((bracket_style, "]"))
        return fragments

    @classmethod
    def _activity_bar_text_fragments(
        cls,
        text: str,
        *,
        base_style: str,
    ) -> list[tuple[str, str]]:
        source = str(text or "")
        match = re.search(r"\[[.<>=-]+\]", source)
        if not match:
            return [(base_style, source)]

        fragments: list[tuple[str, str]] = []
        if match.start() > 0:
            fragments.append((base_style, source[: match.start()]))

        bar_text = match.group(0)
        active = any(char in "<>=-" for char in bar_text)
        fragments.extend(cls._activity_bar_fragments_from_text(bar_text, active=active))

        if match.end() < len(source):
            fragments.append((base_style, source[match.end() :]))
        return fragments

    @staticmethod
    def _activity_bar_fragments_from_text(
        text: str,
        *,
        active: bool,
    ) -> list[tuple[str, str]]:
        bracket_style = "class:header.activity.bracket.active" if active else "class:header.activity.bracket"
        fragments: list[tuple[str, str]] = []
        for char in str(text or ""):
            if char in "[]":
                fragments.append((bracket_style, char))
            elif char in "<>":
                fragments.append(("class:header.activity.head", char))
            elif char == "=":
                fragments.append(("class:header.activity.tail", char))
            elif char == "-":
                fragments.append(("class:header.activity.trail", char))
            else:
                fragments.append(("class:header.activity.idle", char))
        return fragments

    def _session_activity_summary(self, session: TuiSession, *, is_current: bool) -> str:
        projection = session.projection
        runtime = session.runtime
        run_state = self._session_run_state_text(session)
        if self._runs_via_gateway(session) and run_state in {"waiting", "paused", "interrupting", "cancelling"}:
            return run_state
        if projection.busy:
            running = _safe_text(projection.running_state).lower()
            if "resum" in running:
                label = "resuming"
            elif is_current:
                label = "working"
            else:
                label = "background"
            return f"{label} {self._agent_activity_bar_text(active=True)}"
        if self._session_has_gateway_recovery(session):
            return "recovery pending"
        if runtime.pending_resume_task_id:
            return "resume pending"
        if is_current:
            return "current"
        return self._session_status_label(session)

    @staticmethod
    def _session_meta_summary(session: TuiSession) -> str:
        operator = session.operator
        parts = [
            f"{MiniAgentTuiApp._session_message_count(session)}msg",
            f"{len(session.view.tasks)}tsk",
            MiniAgentTuiApp._session_last_active_label(session),
        ]
        if bool(operator.pending_skill_reload):
            parts.append("reload")
        return " ".join(parts)

    @classmethod
    def _session_share_summary(cls, session: TuiSession) -> str:
        projection = cls._terminal_session_projection(session)
        return projection.share_summary if projection is not None else "local only"

    @classmethod
    def _session_visibility_summary(cls, session: TuiSession) -> str:
        projection = cls._terminal_session_projection(session)
        return projection.scope_summary if projection is not None else "private [tui]"

    @classmethod
    def _session_route_summary(cls, session: TuiSession) -> str:
        projection = cls._terminal_session_projection(session)
        return projection.route_summary if projection is not None else "tui / own / local"

    @staticmethod
    def _distance_color_band(distance: int) -> str:
        distance = abs(int(distance))
        if distance == 0:
            return "current"
        if distance == 1:
            return "near"
        return "muted"

    @staticmethod
    def _window_bounds(total: int, focus_index: int, *, window_size: int) -> tuple[int, int]:
        if total <= 0:
            return 0, 0
        size = max(1, int(window_size))
        focus = min(max(0, int(focus_index)), total - 1)
        start = max(0, focus - (size // 2))
        end = min(total, start + size)
        start = max(0, end - size)
        return start, end

    def _session_color_band(self, session_position: int) -> str:
        return self._distance_color_band(int(session_position) - int(self.session_index))

    def _render_sessions_text_and_cursor(self) -> tuple[str, int, int]:
        width = self._panel_content_width(self.sessions_panel, fallback=32)
        lines: list[str] = []
        line_styles: list[str] = []
        current_line_index = 0
        for idx, session in enumerate(self.sessions, start=1):
            band = self._session_color_band(idx - 1)
            display = self._build_session_display_model(session)
            if idx > 1:
                divider_strong = (idx - 1 == self.session_index) or (idx - 2 == self.session_index)
                lines.append(self._sidebar_divider(width, strong=divider_strong))
                line_styles.append(f"{'current' if divider_strong else 'muted'}:divider")
            is_current = idx - 1 == self.session_index
            if is_current:
                current_line_index = len(lines)
            current_marker = ">" if is_current else " "
            title = _truncate_inline(session.title, limit=max(10, width - 8)) or f"Thread {idx}"
            title_parts = [f"{current_marker} {title}"]
            title_parts.append(f"[{display.source_tag}]")
            if is_current:
                title_parts.append("[live]")
                title_parts.append("[focus]")
            lines.append(" ".join(title_parts))
            line_styles.append(f"{band}:title")
            state_lines = self._sidebar_labeled_lines(
                "state",
                self._session_activity_summary(session, is_current=is_current),
                width=width,
                max_lines=3,
            )
            lines.extend(state_lines)
            line_styles.extend([f"{band}:body"] * len(state_lines))
            meta_lines = self._sidebar_labeled_lines(
                "meta",
                self._session_meta_summary(session),
                width=width,
                max_lines=2,
            )
            lines.extend(meta_lines)
            line_styles.extend([f"{band}:body"] * len(meta_lines))
            share_lines = self._sidebar_labeled_lines(
                "share",
                display.share_summary,
                width=width,
                max_lines=2,
            )
            lines.extend(share_lines)
            line_styles.extend([f"{band}:body"] * len(share_lines))
            command_preview = display.last_command_preview
            if command_preview:
                command_lines = self._sidebar_labeled_lines(
                    "cmd",
                    command_preview,
                    width=width,
                    max_lines=2,
                )
                lines.extend(command_lines)
                line_styles.extend([f"{band}:body"] * len(command_lines))
            last_block = self._sidebar_labeled_lines(
                "last",
                self._session_last_message_preview(session),
                width=width,
                max_lines=3,
            )
            lines.extend(last_block)
            line_styles.extend([f"{band}:body"] * len(last_block))
        if not lines:
            lines.append("(no threads)")
            line_styles.append("muted:body")

        self._sessions_line_styles = line_styles
        cursor_position = 0
        if lines:
            cursor_position = sum(len(line) + 1 for line in lines[:current_line_index])
        return "\n".join(lines), cursor_position, current_line_index

    def _session_line_fragments(self, line: str, style_key: str) -> list[tuple[str, str]]:
        band, _, kind = style_key.partition(":")
        if band not in {"current", "near", "muted"}:
            band = "muted"

        if kind == "divider":
            return [(f"class:sidebar.thread.{band}.divider", line)]

        if kind == "title":
            return self._session_title_fragments(line, band)

        if "|" in line:
            left, right = line.split("|", 1)
            fragments: list[tuple[str, str]] = [
                (f"class:sidebar.thread.{band}.label", left),
                (f"class:sidebar.thread.{band}.pipe", "|"),
            ]
            fragments.extend(
                self._activity_bar_text_fragments(
                    right,
                    base_style=f"class:sidebar.thread.{band}.value",
                )
            )
            return fragments

        return self._activity_bar_text_fragments(
            line,
            base_style=f"class:sidebar.thread.{band}.value",
        )

    @staticmethod
    def _session_title_fragments(line: str, band: str) -> list[tuple[str, str]]:
        match = re.match(r"^(..)(.*?)(\s+\[[^\]]+\](?:\s+\[[^\]]+\])*)?$", line)
        if not match:
            return [(f"class:sidebar.thread.{band}.title", line)]

        marker = match.group(1) or ""
        title = match.group(2) or ""
        meta = match.group(3) or ""
        fragments: list[tuple[str, str]] = [
            (f"class:sidebar.thread.{band}.marker", marker),
            (f"class:sidebar.thread.{band}.title", title),
        ]
        if not meta:
            return fragments

        last_index = 0
        for tag_match in re.finditer(r"\s+\[([^\]]+)\]", meta):
            start, end = tag_match.span()
            if start > last_index:
                fragments.append((f"class:sidebar.thread.{band}.meta", meta[last_index:start]))
            tag_text = tag_match.group(0)
            tag_value = _safe_text(tag_match.group(1)).lower()
            if tag_value == "live":
                tag_style = f"class:sidebar.thread.{band}.tag.live"
            elif tag_value == "focus":
                tag_style = f"class:sidebar.thread.{band}.tag.focus"
            elif tag_value == "remote":
                tag_style = f"class:sidebar.thread.{band}.tag.remote"
            else:
                tag_style = f"class:sidebar.thread.{band}.tag.source"
            fragments.append((tag_style, tag_text))
            last_index = end
        if last_index < len(meta):
            fragments.append((f"class:sidebar.thread.{band}.meta", meta[last_index:]))
        return fragments

    def _model_line_fragments(self, line: str, style_key: str) -> list[tuple[str, str]]:
        band, _, kind = style_key.partition(":")
        if band not in {"current", "near", "muted"}:
            band = "muted"

        if kind == "section":
            return [("class:sidebar.section", line)]
        if kind == "summary":
            if "|" in line:
                left, right = line.split("|", 1)
                return [
                    (f"class:sidebar.model.{band}.label", left),
                    (f"class:sidebar.model.{band}.pipe", "|"),
                    (f"class:sidebar.model.{band}.value", right),
                ]
            return [(f"class:sidebar.model.{band}.value", line)]
        if kind == "provider":
            return self._model_provider_fragments(line, band)
        if kind == "provider-detail":
            return [(f"class:sidebar.model.{band}.value", line)]
        if kind == "model":
            return self._model_title_fragments(line, band)
        return [(f"class:sidebar.model.{band}.value", line)]

    @staticmethod
    def _model_provider_fragments(line: str, band: str) -> list[tuple[str, str]]:
        leading = line[: len(line) - len(line.lstrip())]
        content = line.lstrip()
        if content.startswith("> "):
            marker = f"{leading}> "
            rest = content[2:]
        else:
            marker = leading
            rest = content
        if not rest:
            return [(f"class:sidebar.model.{band}.title", line)]
        if "|" in rest:
            title, tail_value = rest.split("|", 1)
            tail = "|" + tail_value
        else:
            title = rest
            tail = ""
        title = title or ""
        if "|" in tail:
            pipe_index = tail.index("|")
            meta_marker = tail[:pipe_index]
            pipe = tail[pipe_index : pipe_index + 1]
            meta = tail[pipe_index + 1 :]
            return [
                (f"class:sidebar.model.{band}.marker", marker),
                (f"class:sidebar.model.{band}.title", title),
                (f"class:sidebar.model.{band}.meta", meta_marker),
                (f"class:sidebar.model.{band}.pipe", pipe),
                (f"class:sidebar.model.{band}.value", meta),
            ]
        return [
            (f"class:sidebar.model.{band}.marker", marker),
            (f"class:sidebar.model.{band}.title", title),
            (f"class:sidebar.model.{band}.meta", tail),
        ]

    @staticmethod
    def _model_title_fragments(line: str, band: str) -> list[tuple[str, str]]:
        match = re.match(r"^(\s+[>* ]{2}\s+)(.*?)(\s+\[[^\]]+\])?$", line)
        if not match:
            return [(f"class:sidebar.model.{band}.title", line)]
        marker = match.group(1) or ""
        title = match.group(2) or ""
        meta = match.group(3) or ""
        return [
            (f"class:sidebar.model.{band}.marker", marker),
            (f"class:sidebar.model.{band}.title", title),
            (f"class:sidebar.model.{band}.meta", meta),
        ]

    def _agent_activity_display(self) -> tuple[str, str, str]:
        busy_sessions = [session for session in self.sessions if session.projection.busy]
        if not busy_sessions:
            return (self._agent_activity_bar_text(active=False), "idle", "class:header.activity.idle")

        current = self.current_session if self.sessions else None
        if current is not None and current.projection.busy:
            label = "resuming" if "resum" in _safe_text(current.projection.running_state).lower() else "working"
        else:
            label = "background"

        return (self._agent_activity_bar_text(active=True), label, "class:header.activity.busy")

    @property
    def current_session(self) -> TuiSession:
        return self.sessions[self.session_index]

    @staticmethod
    def _has_local_runtime_state(session: TuiSession | None) -> bool:
        if session is None:
            return False
        runtime = session.runtime
        return any(
            (
                runtime.agent is not None,
                runtime.submission_loop is not None,
                runtime.loop_bus is not None,
                runtime.cancel_event is not None,
            )
        )

    @classmethod
    def _runs_via_gateway(cls, session: TuiSession | None) -> bool:
        return session is not None and not cls._has_local_runtime_state(session)

    @classmethod
    def _session_summary_projection(cls, session: TuiSession | None) -> SessionSummaryProjection | None:
        if session is None:
            return None
        projection = session.projection
        operator = session.operator
        supplemental = projection.supplemental
        recovery = None
        if any(
            (
                _safe_text(supplemental.remote_recovery_state),
                _safe_text(supplemental.remote_recovery_summary),
                _safe_text(supplemental.remote_last_activity_summary),
                supplemental.recovery_pending_approvals,
            )
        ):
            recovery = SessionRecoveryProjection(
                state=_safe_text(supplemental.remote_recovery_state) or "idle",
                summary=_safe_text(supplemental.remote_recovery_summary) or "idle",
                last_activity=_safe_text(supplemental.remote_last_activity_summary) or None,
                pending_approvals=SessionPendingApprovalProjection.from_payloads(
                    supplemental.recovery_pending_approvals
                ),
            )
        knowledge_base_enabled = projection.knowledge_base_enabled
        return SessionSummaryProjection(
            session_id=_safe_text(session.session_id),
            workspace_dir="",
            created_at="",
            updated_at=_safe_text(supplemental.remote_updated_at),
            title=_safe_text(session.title) or None,
            message_count=cls._session_message_count(session),
            origin_surface=_safe_text(projection.origin_surface) or "tui",
            active_surface=_safe_text(projection.active_surface)
            or _safe_text(projection.origin_surface)
            or "tui",
            reply_enabled=bool(projection.reply_enabled),
            busy=bool(projection.busy),
            running_state=_safe_text(projection.running_state) or None,
            channel_type=_safe_text(projection.channel_type) or None,
            conversation_id=_safe_text(projection.conversation_id) or None,
            sender_id=_safe_text(projection.sender_id) or None,
            token_usage=max(0, int(projection.token_usage or 0)),
            token_limit=max(0, int(projection.token_limit or 0)),
            shared=bool(projection.shared),
            knowledge_base_enabled=True if knowledge_base_enabled is None else bool(knowledge_base_enabled),
            selected_model_source=_safe_text(projection.selected_model_source) or None,
            selected_provider_id=_safe_text(projection.selected_provider_id) or None,
            selected_model_id=_safe_text(projection.selected_model_id) or None,
            pending_model_source=_safe_text(operator.pending_model_source) or None,
            pending_provider_id=_safe_text(operator.pending_provider_id) or None,
            pending_model_id=_safe_text(operator.pending_model_id) or None,
            pending_skill_reload=bool(operator.pending_skill_reload),
            pending_skill_reload_reason=_safe_text(operator.pending_skill_reload_reason) or None,
            pending_approvals=SessionPendingApprovalProjection.from_payloads(projection.pending_approvals),
            recovery=recovery,
            memory_diagnostics=dict(projection.memory_diagnostics or {}),
            sandbox_diagnostics=dict(projection.sandbox_diagnostics or {}),
        )

    @classmethod
    def _terminal_session_projection(cls, session: TuiSession | None) -> TerminalSessionProjection | None:
        summary = cls._session_summary_projection(session)
        if summary is None:
            return None
        return TerminalSessionProjection.from_summary(
            summary,
            has_local_runtime_state=cls._has_local_runtime_state(session),
            last_command_preview=cls._session_last_command_preview(session),
        )

    @classmethod
    def _session_source_tag(cls, session: TuiSession | None) -> str:
        projection = cls._terminal_session_projection(session)
        return projection.source_tag if projection is not None else "tui"

    @classmethod
    def _session_has_external_peer(cls, session: TuiSession | None) -> bool:
        projection = cls._terminal_session_projection(session)
        return bool(projection and projection.has_external_peer)

    @classmethod
    def _session_is_local_only_surface(cls, session: TuiSession | None) -> bool:
        summary = cls._session_summary_projection(session)
        if summary is None:
            return False
        source_tag = cls._session_source_tag(session)
        if cls._session_has_external_peer(session):
            return False
        return source_tag in {"tui", "cli", "local"}

    @classmethod
    def _session_has_gateway_recovery(cls, session: TuiSession | None) -> bool:
        projection = cls._terminal_session_projection(session)
        return bool(projection and projection.recovery_pending)

    @classmethod
    def _session_run_state_text(cls, session: TuiSession | None) -> str:
        if session is None:
            return "idle"
        projection = session.projection
        supplemental = projection.supplemental
        run_status = _safe_text(supplemental.remote_run_status).lower()
        if projection.busy and run_status not in {"waiting", "paused", "interrupt_requested", "cancel_requested"}:
            return "busy"
        if cls._session_has_gateway_recovery(session):
            return "interrupted"
        if cls._runs_via_gateway(session) and run_status:
            return {
                "running": "busy",
                "waiting": "waiting",
                "paused": "paused",
                "interrupt_requested": "interrupting",
                "cancel_requested": "cancelling",
                "completed": "idle",
                "failed": "failed",
            }.get(run_status, run_status)
        if projection.busy:
            return "busy"
        if cls._session_has_gateway_recovery(session):
            return "interrupted"
        return "idle"

    @classmethod
    def _session_run_task_text(cls, session: TuiSession | None) -> str:
        if session is None:
            return "idle"
        projection = session.projection
        supplemental = projection.supplemental
        run_wait = cls._run_approval_wait_payload(session)
        if cls._session_has_gateway_recovery(session) and projection.supplemental.remote_recovery_summary:
            return projection.supplemental.remote_recovery_summary
        run_running_state = _safe_text(supplemental.remote_run_running_state)
        if cls._runs_via_gateway(session):
            if run_running_state:
                return run_running_state
            if run_wait is not None:
                tool_name = _safe_text(run_wait.get("tool_name")) or "tool"
                return f"approval wait for {tool_name}"
            run_phase = _safe_text(supplemental.remote_run_phase).replace("_", " ")
            if run_phase:
                return run_phase
        if projection.busy and projection.running_state:
            return projection.running_state
        return "idle"

    @classmethod
    def _session_should_show_gateway_panel(cls, session: TuiSession | None) -> bool:
        projection = cls._terminal_session_projection(session)
        return bool(projection and projection.show_gateway_panel)

    @classmethod
    def _build_session_display_model(cls, session: TuiSession) -> SessionDisplayModel:
        projection = cls._terminal_session_projection(session)
        if projection is None:
            return SessionDisplayModel(
                source_tag="TUI",
                scope_summary="private [tui]",
                route_summary="tui / own / local",
                share_state="local only",
                share_summary="local only",
                peer_summary="no external peer",
                has_external_peer=False,
                show_gateway_panel=False,
                recovery_pending=False,
                last_command_preview=None,
            )
        return SessionDisplayModel(
            source_tag=projection.source_tag.upper(),
            scope_summary=projection.scope_summary,
            route_summary=projection.route_summary,
            share_state=projection.share_state,
            share_summary=projection.share_summary,
            peer_summary=projection.peer_summary,
            has_external_peer=projection.has_external_peer,
            show_gateway_panel=projection.show_gateway_panel,
            recovery_pending=projection.recovery_pending,
            last_command_preview=projection.last_command_preview,
        )

    async def _refresh_context_snapshot_if_gateway_bound(
        self,
        session: TuiSession,
        *,
        recent_limit: int = 80,
    ) -> None:
        if self._runs_via_gateway(session):
            await self._sync_remote_session_detail(session, recent_limit=recent_limit)
            return
        if self._has_local_runtime_state(session):
            self._capture_local_runtime_projection(session)

    @staticmethod
    def _session_message_count(session: TuiSession) -> int:
        if MiniAgentTuiApp._runs_via_gateway(session):
            remote_count = int(session.projection.supplemental.remote_message_count or 0)
            if remote_count > 0:
                return remote_count
        return len(MiniAgentTuiApp._session_visible_messages(session))

    @staticmethod
    def _session_surface_flow(session: TuiSession) -> str:
        projection = session.projection
        origin = _safe_text(projection.origin_surface) or "tui"
        active = _safe_text(projection.active_surface) or origin
        return origin if origin == active else f"{origin} -> {active}"

    @classmethod
    def _session_share_state_label(cls, session: TuiSession) -> str:
        projection = cls._terminal_session_projection(session)
        return projection.share_state if projection is not None else "local only"

    @staticmethod
    def _session_peer_label(session: TuiSession) -> str:
        projection = session.projection
        channel = _safe_text(projection.channel_type).lower()
        conversation = _safe_text(projection.conversation_id)
        sender = _safe_text(projection.sender_id)
        pieces: list[str] = []
        if channel:
            pieces.append(channel)
        if conversation:
            pieces.append(conversation)
        if sender:
            pieces.append(f"from {sender}")
        return " | ".join(piece for piece in pieces if piece)

    @classmethod
    def _session_peer_summary(cls, session: TuiSession) -> str:
        projection = cls._terminal_session_projection(session)
        return projection.peer_summary if projection is not None else "no external peer"

    def _requested_remote_workspace_id(self) -> str:
        return str(self.workspace)

    def _effective_remote_workspace_dir(self) -> str:
        for payload in (self._remote_workspace_summary, self._remote_workspace_runtime_summary):
            raw_workspace = _safe_text(payload.get("workspace_dir"))
            if raw_workspace:
                return raw_workspace
        return str(self.workspace)

    def _workspace_header_hint(self) -> str:
        explicit_title = _safe_text(self._remote_workspace_summary.get("title"))
        if explicit_title:
            return explicit_title
        raw_workspace = self._effective_remote_workspace_dir()
        try:
            resolved = Path(raw_workspace).expanduser().resolve()
            return resolved.name or str(resolved)
        except Exception:
            return raw_workspace

    async def _refresh_remote_workspace_snapshot(self) -> None:
        requested_workspace = self._requested_remote_workspace_id()
        try:
            summary = await self.remote_workspace_service.get_workspace(requested_workspace)
            self._remote_workspace_summary = surface_payload_from_dto(summary)
        except Exception:
            try:
                active = await self.remote_workspace_service.get_active_workspace()
                self._remote_workspace_summary = surface_payload_from_dto(active)
            except Exception:
                self._remote_workspace_summary = {}

        runtime_workspace_id = (
            _safe_text(self._remote_workspace_summary.get("workspace_id"))
            or _safe_text(self._remote_workspace_summary.get("workspace_dir"))
            or requested_workspace
        )
        try:
            runtime_summary = await self.remote_workspace_service.get_workspace_runtime_summary(
                workspace_id=runtime_workspace_id
            )
            self._remote_workspace_runtime_summary = surface_payload_from_dto(runtime_summary)
        except Exception:
            self._remote_workspace_runtime_summary = {}

    def _refresh_remote_workspace_snapshot_sync(self) -> None:
        requested_workspace = self._requested_remote_workspace_id()
        try:
            summary = self.remote_workspace_service.get_workspace_sync(requested_workspace)
            self._remote_workspace_summary = surface_payload_from_dto(summary)
        except Exception:
            try:
                active = self.remote_workspace_service.get_active_workspace_sync()
                self._remote_workspace_summary = surface_payload_from_dto(active)
            except Exception:
                self._remote_workspace_summary = {}

        runtime_workspace_id = (
            _safe_text(self._remote_workspace_summary.get("workspace_id"))
            or _safe_text(self._remote_workspace_summary.get("workspace_dir"))
            or requested_workspace
        )
        try:
            runtime_summary = self.remote_workspace_service.get_workspace_runtime_summary_sync(
                workspace_id=runtime_workspace_id
            )
            self._remote_workspace_runtime_summary = surface_payload_from_dto(runtime_summary)
        except Exception:
            self._remote_workspace_runtime_summary = {}

    def _payload_workspace_matches_current(self, payload: dict[str, Any]) -> bool:
        raw_workspace = _safe_text(payload.get("workspace_dir"))
        if not raw_workspace:
            return False
        for candidate in (str(self.workspace), self._effective_remote_workspace_dir()):
            if not candidate:
                continue
            try:
                if Path(raw_workspace).expanduser().resolve() == Path(candidate).expanduser().resolve():
                    return True
            except Exception:
                if raw_workspace.lower() == candidate.lower():
                    return True
        return False

    @staticmethod
    def _remote_request_binding_kwargs(session: TuiSession) -> dict[str, str | None]:
        projection = session.projection
        return ApplicationInteractionBinding.from_values(
            surface="tui",
            channel_type=projection.channel_type,
            conversation_id=projection.conversation_id,
            sender_id=projection.sender_id,
            default_surface="tui",
        ).as_kwargs()

    def _remote_session_title(self, payload: dict[str, Any], *, fallback: str) -> str:
        projection = SessionSummaryProjection.from_transport_payload(payload)
        if projection is not None:
            return self._remote_session_title_from_projection(projection, fallback=fallback)
        explicit_title = _safe_text(payload.get("title"))
        if explicit_title:
            return _safe_session_title(explicit_title, fallback=fallback)
        channel = _safe_text(payload.get("channel_type")).lower()
        conversation = _safe_text(payload.get("conversation_id"))
        origin = _safe_text(payload.get("origin_surface")).lower() or channel or "remote"
        if channel:
            prefix = channel.upper()
        else:
            prefix = origin.upper()
        if conversation:
            return _safe_session_title(f"{prefix} {conversation}", fallback=fallback)
        session_id = _safe_text(payload.get("session_id"))
        suffix = _truncate_inline(session_id, limit=12) or fallback
        return _safe_session_title(f"{prefix} {suffix}", fallback=fallback)

    def _remote_session_title_from_projection(
        self,
        projection: SessionSummaryProjection,
        *,
        fallback: str,
    ) -> str:
        explicit_title = _safe_text(projection.title)
        if explicit_title:
            return _safe_session_title(explicit_title, fallback=fallback)
        channel = _safe_text(projection.channel_type).lower()
        conversation = _safe_text(projection.conversation_id)
        origin = _safe_text(projection.origin_surface).lower() or channel or "remote"
        if channel:
            prefix = channel.upper()
        else:
            prefix = origin.upper()
        if conversation:
            return _safe_session_title(f"{prefix} {conversation}", fallback=fallback)
        session_id = _safe_text(projection.session_id)
        suffix = _truncate_inline(session_id, limit=12) or fallback
        return _safe_session_title(f"{prefix} {suffix}", fallback=fallback)

    def _remote_chat_entries(self, items: Sequence[dict[str, Any]]) -> list[ChatEntry]:
        entries: list[ChatEntry] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            role = _safe_text(item.get("role")) or "system"
            content = str(item.get("content", ""))
            raw_metadata = item.get("metadata")
            metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
            metadata.setdefault("surface", _safe_text(item.get("surface")) or "remote")
            metadata.setdefault("channel_type", _safe_text(item.get("channel_type")) or None)
            metadata.setdefault("conversation_id", _safe_text(item.get("conversation_id")) or None)
            metadata.setdefault("sender_id", _safe_text(item.get("sender_id")) or None)
            metadata.setdefault("threads_visible", role.lower() != "system")
            entries.append(
                ChatEntry(
                    role=role,
                    content=content,
                    timestamp=_label_from_iso_timestamp(item.get("created_at")),
                    metadata=metadata,
                )
            )
        return entries

    def _apply_remote_session_summary(self, session: TuiSession, payload: dict[str, Any]) -> None:
        self._remote_session_projector.apply_summary(session, payload)

    def _apply_remote_session_detail(self, session: TuiSession, payload: dict[str, Any]) -> None:
        should_follow_output = self._should_follow_output_after_session_update(session)
        self._remote_session_projector.apply_detail(
            session,
            payload,
            preserve_follow_output=should_follow_output,
        )

    def _apply_remote_session_messages(self, session: TuiSession, items: Sequence[dict[str, Any]]) -> None:
        self._remote_session_projector.apply_messages(session, items)

    def _apply_remote_run_summary(self, session: TuiSession, payload: dict[str, Any]) -> None:
        self._remote_session_projector.apply_run(session, payload)

    def _clear_remote_run_summary(self, session: TuiSession) -> None:
        self._remote_session_projector.clear_run(session)

    @staticmethod
    def _remote_run_id_for_session(session: TuiSession | None) -> str | None:
        if session is None:
            return None
        run_id = _safe_text(session.projection.supplemental.remote_run_id)
        if run_id:
            return run_id
        try:
            return build_session_backed_run_id(session.session_id)
        except Exception:
            return None

    async def _sync_remote_run_summary(self, session: TuiSession) -> None:
        if self._has_local_runtime_state(session):
            return
        run_id = self._remote_run_id_for_session(session)
        if not run_id:
            self._clear_remote_run_summary(session)
            return
        try:
            run = await self.remote_run_service.get_run(run_id)
        except Exception:
            self._clear_remote_run_summary(session)
            return
        self._apply_remote_run_summary(session, surface_payload_from_dto(run))

    def _sync_remote_run_summary_sync(self, session: TuiSession) -> None:
        if self._has_local_runtime_state(session):
            return
        run_id = self._remote_run_id_for_session(session)
        if not run_id:
            self._clear_remote_run_summary(session)
            return
        try:
            run = self.remote_run_service.get_run_sync(run_id)
        except Exception:
            self._clear_remote_run_summary(session)
            return
        self._apply_remote_run_summary(session, surface_payload_from_dto(run))

    async def _sync_remote_session_detail(self, session: TuiSession, *, recent_limit: int = 80) -> None:
        if self._has_local_runtime_state(session):
            return
        detail = await self.remote_session_service.get_session_detail(session.session_id, recent_limit=recent_limit)
        self._apply_remote_session_detail(session, surface_payload_from_dto(detail))
        await self._sync_remote_run_summary(session)

    async def _sync_remote_sessions_once(self, *, focus_current: bool = True) -> None:
        current_session_id = self.current_session.session_id if self.sessions else None
        await self._refresh_remote_workspace_snapshot()
        remote_summaries = await self.remote_session_service.list_sessions(
            workspace_dir=self._effective_remote_workspace_dir()
        )
        ordered_summaries = sorted(
            surface_payload_list_from_dtos(remote_summaries),
            key=lambda item: _safe_text(item.get("updated_at")),
            reverse=True,
        )
        changed = False
        next_sessions: list[TuiSession] = []
        existing_by_id = {session.session_id: session for session in self.sessions}

        for summary in ordered_summaries:
            session_id = _safe_text(summary.get("session_id"))
            if not session_id:
                continue
            session = existing_by_id.get(session_id)
            if session is None:
                session = self._build_runtime_session_from_summary(summary)
                if session is None:
                    continue
                changed = True
            previous_count = int(session.projection.supplemental.remote_message_count)
            previous_updated = _safe_text(session.projection.supplemental.remote_updated_at)
            self._apply_remote_session_summary(session, summary)
            local_runtime_authoritative = self._has_local_runtime_state(session)
            should_fetch_detail = (
                not local_runtime_authoritative
                and (
                    (focus_current and current_session_id == session.session_id)
                    or session.projection.busy
                    or not session.view.messages
                )
            )
            if should_fetch_detail:
                detail_payload = await self.remote_session_service.get_session_detail(session.session_id, recent_limit=80)
                self._apply_remote_session_detail(session, surface_payload_from_dto(detail_payload))
                await self._sync_remote_run_summary(session)
                changed = True
            elif (
                not local_runtime_authoritative
                and (
                    previous_count != session.projection.supplemental.remote_message_count
                    or previous_updated != _safe_text(session.projection.supplemental.remote_updated_at)
                )
            ):
                messages = await self.remote_session_service.get_session_messages(session.session_id, limit=6)
                self._apply_remote_session_messages(session, surface_payload_list_from_dtos(messages))
                if (
                    focus_current
                    and current_session_id == session.session_id
                ) or session.projection.busy or bool(session.projection.pending_approvals):
                    await self._sync_remote_run_summary(session)
                changed = True
            next_sessions.append(session)

        if next_sessions:
            if len(next_sessions) != len(self.sessions):
                changed = True
            self.sessions = next_sessions
        else:
            created = await self._ensure_remote_default_session()
            if created is not None:
                self._remote_sync_error = ""
                return
            self.sessions = []
            self.session_index = 0

        if self.sessions:
            preferred_index = self._preferred_remote_session_index(
                current_session_id=current_session_id,
                saved_session_id=self._saved_current_session_id,
            )
            if preferred_index is not None:
                self.session_index = preferred_index
            else:
                self.session_index = min(self.session_index, len(self.sessions) - 1)

        if changed:
            self._refresh_command_completer()
            self._persist_session_state()
            self._render_all()
        self._remote_sync_error = ""

    async def _remote_sync_loop(self) -> None:
        while True:
            try:
                await self._sync_remote_sessions_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._remote_sync_error = _safe_text(exc)
            await asyncio.sleep(self.remote_poll_interval_seconds)

    def _ensure_remote_sync_started(self) -> None:
        if self._remote_sync_started:
            return
        self._remote_sync_started = True
        self._remote_sync_task = asyncio.create_task(self._remote_sync_loop())
        self.background_tasks.add(self._remote_sync_task)

        def _cleanup(done: asyncio.Task[Any]) -> None:
            self.background_tasks.discard(done)
            if self._remote_sync_task is done:
                self._remote_sync_task = None
            try:
                done.result()
            except asyncio.CancelledError:
                return
            except Exception as exc:  # pragma: no cover - defensive
                self._remote_sync_error = _safe_text(exc)

        self._remote_sync_task.add_done_callback(_cleanup)

    def _apply_saved_session_ui_state(self, session: TuiSession) -> None:
        raw_state = self._session_view_state.get(_safe_text(session.session_id), {})
        if not isinstance(raw_state, dict):
            return
        view = session.view
        view.activity_details_expanded = bool(raw_state.get("activity_details_expanded", False))
        view.command_details_expanded = bool(raw_state.get("command_details_expanded", False))
        view.chat_scroll_line = max(0, int(raw_state.get("chat_scroll_line", 0) or 0))
        view.chat_follow_output = bool(raw_state.get("chat_follow_output", True))

    def _build_runtime_session_from_summary(self, payload: dict[str, Any]) -> TuiSession | None:
        session_id = _safe_text(payload.get("session_id"))
        if not session_id:
            return None
        session = TuiSession(
            session_id=session_id,
            title=self._remote_session_title(payload, fallback=session_id),
            projection=TuiSessionProjectionState(
                origin_surface=_safe_text(payload.get("origin_surface")) or "tui",
                active_surface=_safe_text(payload.get("active_surface")) or "tui",
            ),
        )
        self._apply_remote_session_summary(session, payload)
        self._apply_saved_session_ui_state(session)
        return session

    def _default_session_index(self) -> int | None:
        for index, session in enumerate(self.sessions):
            if bool(getattr(session.projection, "is_default", False)):
                return index
        return self._find_session_index("default")

    def _preferred_remote_session_index(
        self,
        *,
        current_session_id: str | None,
        saved_session_id: str | None,
    ) -> int | None:
        for candidate in (current_session_id, saved_session_id):
            resolved = self._find_session_index(_safe_text(candidate))
            if resolved is not None:
                return resolved
        return self._default_session_index()

    def _bootstrap_runtime_sessions_sync(self) -> None:
        self._refresh_remote_workspace_snapshot_sync()
        effective_workspace_dir = self._effective_remote_workspace_dir()
        summaries = self.remote_session_service.list_sessions_sync(workspace_dir=effective_workspace_dir)
        if not summaries:
            created = self.remote_session_service.ensure_default_session_sync(
                MainAgentDefaultSessionRequest(
                    workspace_dir=effective_workspace_dir,
                    surface="tui",
                )
            )
            summaries = [created]
        ordered = sorted(
            surface_payload_list_from_dtos(summaries),
            key=lambda item: _safe_text(item.get("updated_at")),
            reverse=True,
        )
        self.sessions = [
            session
            for session in (
                self._build_runtime_session_from_summary(item)
                for item in ordered
            )
            if session is not None
        ]
        if not self.sessions:
            raise RuntimeError("Gateway returned no runtime sessions.")
        preferred_index = self._preferred_remote_session_index(
            current_session_id=None,
            saved_session_id=self._saved_current_session_id,
        )
        self.session_index = preferred_index if preferred_index is not None else 0
        try:
            detail = self.remote_session_service.get_session_detail_sync(
                self.current_session.session_id,
                recent_limit=80,
            )
        except Exception:
            detail = None
        if detail is not None:
            self._apply_remote_session_detail(self.current_session, surface_payload_from_dto(detail))
            self._sync_remote_run_summary_sync(self.current_session)
        self._refresh_command_completer()

    def _persist_session_state(self) -> None:
        if not self.sessions:
            return
        current_session_id = (
            self.sessions[self.session_index].session_id
            if 0 <= self.session_index < len(self.sessions)
            else self.sessions[0].session_id
        )
        try:
            save_tui_session_state(
                state_path=self.state_path,
                sessions=self.sessions,
                current_session_id=current_session_id,
            )
        except Exception as exc:
            self._set_status(f"Session persistence failed: {exc}")

    async def _create_runtime_session(self, *, title: str | None = None, shared: bool = False) -> TuiSession | None:
        await self._refresh_remote_workspace_snapshot()
        response = await self.remote_session_service.create_session(
            MainAgentSessionCreateRequest(
                workspace_dir=self._effective_remote_workspace_dir(),
                title=title,
                surface="tui",
                shared=shared,
            )
        )
        payload = surface_payload_from_dto(response)
        session = self._build_runtime_session_from_summary(payload)
        if session is None:
            return None
        if isinstance(payload.get("recent_messages"), list):
            self._apply_remote_session_detail(session, payload)
        self._capture_chat_view_state()
        self.sessions.insert(0, session)
        self.session_index = 0
        self._refresh_command_completer()
        self._persist_session_state()
        self._render_all()
        return session

    @staticmethod
    def _derived_session_title_from_prompt(prompt: str | None) -> str | None:
        cleaned = _safe_text(prompt)
        if not cleaned:
            return None
        return f"Task: {_truncate_inline(cleaned, limit=42)}"

    async def _create_derived_runtime_session(
        self,
        *,
        parent_session: TuiSession,
        title: str | None = None,
    ) -> TuiSession | None:
        response = await self.remote_session_service.create_derived_session(
            parent_session.session_id,
            MainAgentSessionForkRequest(
                title=title,
                surface="tui",
            ),
        )
        payload = surface_payload_from_dto(response)
        session = self._build_runtime_session_from_summary(payload)
        if session is None:
            return None
        if isinstance(payload.get("recent_messages"), list):
            self._apply_remote_session_detail(session, payload)
        self._capture_chat_view_state()
        self.sessions.insert(0, session)
        self.session_index = 0
        self._restore_chat_view_state()
        preferred_model = self._preferred_cursor_model_identity(self.current_session)
        if preferred_model is not None:
            self._set_model_cursor_by_identity(preferred_model)
        self._refresh_command_completer()
        self._persist_session_state()
        self._render_all()
        return session

    async def _ensure_remote_default_session(self) -> TuiSession | None:
        await self._refresh_remote_workspace_snapshot()
        response = await self.remote_session_service.ensure_default_session(
            MainAgentDefaultSessionRequest(
                workspace_dir=self._effective_remote_workspace_dir(),
                surface="tui",
            )
        )
        payload = surface_payload_from_dto(response)
        session = self._build_runtime_session_from_summary(payload)
        if session is None:
            return None
        if isinstance(payload.get("recent_messages"), list):
            self._apply_remote_session_detail(session, payload)
        self._capture_chat_view_state()
        self.sessions = [item for item in self.sessions if item.session_id != session.session_id]
        self.sessions.insert(0, session)
        resolved_index = self._find_session_index(session.session_id)
        self.session_index = resolved_index if resolved_index is not None else 0
        self._refresh_command_completer()
        self._persist_session_state()
        self._render_all()
        return session

    async def _fork_current_session(
        self,
        *,
        prompt: str | None = None,
        command_label: str,
    ) -> None:
        parent_session = self.current_session
        title = self._derived_session_title_from_prompt(prompt)
        try:
            child_session = await self._create_derived_runtime_session(
                parent_session=parent_session,
                title=title,
            )
        except Exception as exc:
            detail = extract_gateway_error_info(exc).detail
            message = f"Derived session creation failed: {detail}"
            self._append_command_feedback(
                command_label,
                summary="fork failed",
                details=message,
                level="error",
            )
            self._set_status(message)
            self._render_all()
            return
        if child_session is None:
            self._set_status("Derived session creation failed.")
            self._render_all()
            return
        self._set_status(
            SessionFeedbackService.fork_feedback(
                title=child_session.title,
                parent_title=parent_session.title,
            ).status_text
        )
        if _safe_text(prompt):
            await self._run_remote_chat_turn(str(prompt), session=child_session)
            return
        self._render_all()

    def _find_session_index(self, session_id: str) -> int | None:
        target = _safe_text(session_id)
        if not target:
            return None
        for index, session in enumerate(self.sessions):
            if session.session_id == target:
                return index
        return None

    def _find_session_index_by_selector(self, selector: str) -> int | None:
        target = _safe_text(selector)
        if not target:
            return None
        if target.isdigit():
            ordinal = int(target)
            if 1 <= ordinal <= len(self.sessions):
                return ordinal - 1
            return None
        return self._find_session_index(target)

    def _activate_session_index(self, index: int) -> bool:
        if not self.sessions:
            return False
        if index < 0 or index >= len(self.sessions):
            return False
        self._capture_chat_view_state()
        self.session_index = index
        self._restore_chat_view_state()
        preferred_model = self._preferred_cursor_model_identity(self.current_session)
        self._refresh_registry(preferred_model=preferred_model)
        self._set_status(f"Switched to {self.current_session.title}.")
        self._schedule(self._sync_remote_session_detail(self.current_session, recent_limit=80))
        self._persist_session_state()
        self._render_all()
        return True

    def _rename_session(self, *, title: str, session_id: str | None = None) -> TuiSession | None:
        if not self.sessions:
            return None
        if session_id:
            index = self._find_session_index(session_id)
            if index is None:
                return None
        else:
            index = self.session_index
        fallback_title = self.sessions[index].title
        self.sessions[index].title = _safe_session_title(title, fallback=fallback_title)
        self._refresh_command_completer()
        self._persist_session_state()
        return self.sessions[index]

    def _delete_session(self, *, session_id: str | None = None) -> TuiSession | None:
        if not self.sessions:
            return None
        if session_id:
            index = self._find_session_index(session_id)
            if index is None:
                return None
        else:
            index = self.session_index

        deleted = self.sessions[index]
        deleted = self.sessions.pop(index)
        if self.sessions:
            if index < self.session_index:
                self.session_index -= 1
            elif index == self.session_index and self.session_index >= len(self.sessions):
                self.session_index = len(self.sessions) - 1
        self._refresh_command_completer()
        self._persist_session_state()
        return deleted

    def _switch_session(self, delta: int) -> None:
        if not self.sessions:
            return
        self._activate_session_index((self.session_index + delta) % len(self.sessions))

    def _append_session_message(
        self,
        session: TuiSession,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
        persist: bool = True,
    ) -> int:
        should_follow_output = self._should_follow_output_after_session_update(session)
        view = session.view
        view.messages.append(ChatEntry(role=role, content=content, metadata=dict(metadata or {})))
        self._bump_chat_render_revision(session)
        if should_follow_output:
            view.chat_follow_output = True
        if persist:
            self._persist_session_state()
        return len(view.messages) - 1

    def _update_session_message_content(
        self,
        session: TuiSession,
        index: int,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
        persist: bool = False,
    ) -> bool:
        view = session.view
        if index < 0 or index >= len(view.messages):
            return False
        should_follow_output = self._should_follow_output_after_session_update(session)
        entry = view.messages[index]
        entry.content = content
        if isinstance(metadata, dict):
            entry.metadata.update(metadata)
        self._bump_chat_render_revision(session)
        if should_follow_output:
            view.chat_follow_output = True
        if persist:
            self._persist_session_state()
        return True

    def _replace_session_messages(
        self,
        session: TuiSession,
        messages: Sequence[ChatEntry],
        *,
        preserve_follow_output: bool = True,
    ) -> None:
        should_follow_output = preserve_follow_output and self._should_follow_output_after_session_update(session)
        view = session.view
        view.messages = list(messages)
        view.active_activity_message_index = None
        self._bump_chat_render_revision(session)
        if should_follow_output:
            view.chat_follow_output = True

    def _invalidate_chat_render_cache(self) -> None:
        self._chat_render_cache_key = None
        self._chat_render_cache_lines = []
        self._chat_render_cache_fragments = []

    def _bump_chat_render_revision(self, session: TuiSession) -> None:
        view = session.view
        view.chat_render_revision = int(getattr(view, "chat_render_revision", 0)) + 1
        if self.sessions and self.current_session is session:
            self._invalidate_chat_render_cache()

    def _clear_pending_stream_render_task(self, task: asyncio.Task[Any] | None = None) -> None:
        if task is None or self._pending_stream_render_task is task:
            self._pending_stream_render_task = None

    async def _delayed_stream_render(self, delay: float) -> None:
        try:
            await asyncio.sleep(max(0.0, delay))
        except asyncio.CancelledError:
            return
        self._last_stream_render_at = time.monotonic()
        self._pending_stream_render_task = None
        self._render_all()

    def _schedule_stream_render(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_stream_render_at
        if elapsed >= STREAM_RENDER_INTERVAL_SECONDS:
            pending = self._pending_stream_render_task
            if pending is not None and not pending.done():
                pending.cancel()
            self._last_stream_render_at = now
            self._clear_pending_stream_render_task(pending)
            self._render_all()
            return
        pending = self._pending_stream_render_task
        if pending is not None and not pending.done():
            return
        delay = max(0.0, STREAM_RENDER_INTERVAL_SECONDS - elapsed)
        task = asyncio.create_task(self._delayed_stream_render(delay))
        self._pending_stream_render_task = task
        self.background_tasks.add(task)

        def _cleanup(done: asyncio.Task[Any]) -> None:
            self.background_tasks.discard(done)
            self._clear_pending_stream_render_task(done)
            try:
                done.result()
            except asyncio.CancelledError:
                return
            except Exception as exc:  # pragma: no cover - defensive
                self._set_status(f"Background task failed: {exc}")
                self._render_all()

        task.add_done_callback(_cleanup)

    async def _flush_stream_render(self) -> None:
        pending = self._pending_stream_render_task
        if pending is not None and not pending.done():
            pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                pass
        self._pending_stream_render_task = None
        self._last_stream_render_at = time.monotonic()
        self._render_all()

    def _append_assistant_stream_chunk(
        self,
        session: TuiSession,
        chunk: str,
        *,
        message_index: int | None = None,
    ) -> int:
        view = session.view
        entry_index = message_index
        if entry_index is None or entry_index < 0 or entry_index >= len(view.messages):
            entry_index = self._append_session_message(
                session,
                "assistant",
                "",
                metadata={"streaming": True},
                persist=False,
            )
        entry = view.messages[entry_index]
        metadata = dict(entry.metadata) if isinstance(entry.metadata, dict) else {}
        metadata["streaming"] = True
        self._update_session_message_content(
            session,
            entry_index,
            f"{entry.content}{chunk}",
            metadata=metadata,
            persist=False,
        )
        return entry_index

    async def _stream_assistant_reply(
        self,
        session: TuiSession,
        content: str,
        *,
        message_index: int | None = None,
    ) -> int:
        display_text = _format_assistant_content(content) or "(empty response)"
        view = session.view
        entry_index = message_index
        if entry_index is None or entry_index < 0 or entry_index >= len(view.messages):
            entry_index = self._append_session_message(
                session,
                "assistant",
                "",
                metadata={"streaming": True},
                persist=False,
            )
        metadata = dict(view.messages[entry_index].metadata)
        metadata["streaming"] = True
        self._update_session_message_content(session, entry_index, "", metadata=metadata, persist=False)
        for chunk in _iter_stream_chunks(display_text):
            self._append_assistant_stream_chunk(session, chunk, message_index=entry_index)
            self._schedule_stream_render()
            await asyncio.sleep(0)
        metadata["streaming"] = False
        self._update_session_message_content(
            session,
            entry_index,
            display_text,
            metadata=metadata,
            persist=False,
        )
        await self._flush_stream_render()
        return entry_index

    def _append_system(self, content: str, *, persist: bool = True) -> None:
        self._append_session_message(self.current_session, "system", content, persist=persist)

    def _append_message(self, role: str, content: str, *, persist: bool = True) -> None:
        self._append_session_message(self.current_session, role, content, persist=persist)

    def _append_command_feedback(
        self,
        command: str,
        *,
        session: TuiSession | None = None,
        summary: str | None = None,
        details: str = "",
        level: str = "info",
        metadata: dict[str, Any] | None = None,
        persist: bool = True,
    ) -> None:
        detail_text = _normalize_chat_content(details).strip()
        summary_text = _safe_text(summary)
        if not summary_text:
            summary_text = _safe_text(_preview_line_text(detail_text)) or "completed"
        payload_metadata = {
            "kind": "command",
            "command": _safe_text(command) or "command",
            "summary": summary_text,
            "level": _safe_text(level).lower() or "info",
        }
        if isinstance(metadata, dict):
            payload_metadata.update(metadata)
        self._append_session_message(
            session or self.current_session,
            "system",
            detail_text,
            metadata=payload_metadata,
            persist=persist,
        )

    def _session_share_transcript_payload(self, session: TuiSession) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for entry in session.view.messages:
            metadata = dict(entry.metadata) if isinstance(entry.metadata, dict) else {}
            payload: dict[str, Any] = {
                "role": _safe_text(entry.role) or "system",
                "content": str(entry.content or ""),
                "surface": _safe_text(metadata.get("surface")) or "tui",
            }
            if metadata:
                payload["metadata"] = metadata
            items.append(payload)
        return items

    @staticmethod
    def _activity_items(entry: ChatEntry) -> list[dict[str, Any]]:
        metadata = getattr(entry, "metadata", None)
        if not isinstance(metadata, dict):
            metadata = {}
            try:
                entry.metadata = metadata
            except Exception:
                return []
        raw = metadata.get("activity_items")
        if isinstance(raw, list):
            if all(isinstance(item, dict) for item in raw):
                return raw
            cleaned = [item for item in raw if isinstance(item, dict)]
            metadata["activity_items"] = cleaned
            return cleaned
        items: list[dict[str, Any]] = []
        metadata["activity_items"] = items
        metadata["kind"] = "activity"
        return items

    @staticmethod
    def _activity_label(value: str) -> str:
        normalized = _safe_text(value).lower().replace("_", "-")
        if normalized in {"bash", "powershell", "shell", "shell-command"}:
            return "shell"
        if normalized.startswith("bash-"):
            return normalized.replace("bash-", "shell-", 1)
        return normalized or "activity"

    @staticmethod
    def _tool_arguments_from_hook(tool_call: Any) -> dict[str, Any]:
        function_obj = getattr(tool_call, "function", None)
        arguments = getattr(function_obj, "arguments", None)
        return arguments if isinstance(arguments, dict) else {}

    def _tool_activity_preview(self, tool_call: Any) -> str:
        arguments = self._tool_arguments_from_hook(tool_call)
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
                preview = ", ".join(_safe_text(item) for item in value if _safe_text(item))
            else:
                preview = _safe_text(value)
            if not preview:
                continue
            if key == "command" and bool(arguments.get("run_in_background")):
                preview = f"{preview} [bg]"
            return _truncate_inline(preview, limit=72)

        try:
            return _truncate_inline(json.dumps(arguments, ensure_ascii=False), limit=72)
        except Exception:
            return ""

    @staticmethod
    def _tool_call_key(step: int, tool_call: Any) -> str:
        tool_call_id = _safe_text(getattr(tool_call, "id", ""))
        if tool_call_id:
            return tool_call_id
        function_obj = getattr(tool_call, "function", None)
        function_name = _safe_text(getattr(function_obj, "name", "")) or "tool"
        return f"step-{step}:{function_name}"

    @staticmethod
    def _activity_has_output(label: str, result: Any) -> bool:
        activity_label = _safe_text(label).lower()
        return activity_label.startswith("shell") or hasattr(result, "stdout") or hasattr(result, "stderr")

    @staticmethod
    def _tool_result_output_text(result: Any) -> str:
        blocks: list[str] = []
        stdout = _normalize_chat_content(getattr(result, "stdout", "")).strip()
        stderr = _normalize_chat_content(getattr(result, "stderr", "")).strip()
        content = _normalize_chat_content(getattr(result, "content", "")).strip()
        bash_id = _safe_text(getattr(result, "bash_id", ""))
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

    @staticmethod
    def _activity_output_summary(output_text: str) -> str:
        normalized = _normalize_chat_content(output_text).strip()
        if not normalized:
            return ""
        non_empty = [line.strip() for line in normalized.splitlines() if line.strip()]
        if not non_empty:
            return ""
        summary_lines = [
            line
            for line in non_empty
            if not (line.startswith("[") and "]" in line[:20])
        ] or non_empty
        first = _truncate_inline(summary_lines[0], limit=68)
        remaining = len(summary_lines) - 1
        if remaining > 0:
            return f"{first} (+{remaining} more line(s))"
        return first

    def _ensure_activity_message(self, session: TuiSession) -> ChatEntry:
        view = session.view
        index = view.active_activity_message_index
        if index is not None and 0 <= index < len(view.messages):
            entry = view.messages[index]
            if _safe_text(entry.role).lower() == "tool" and entry.metadata.get("kind") == "activity":
                return entry
        index = self._append_session_message(
            session,
            "tool",
            "",
            metadata={"kind": "activity", "activity_items": []},
            persist=False,
        )
        view.active_activity_message_index = index
        return view.messages[index]

    def _append_activity_line(
        self,
        session: TuiSession,
        *,
        label: str,
        detail: str,
        activity_id: str | None = None,
        preview: str = "",
        output_text: str = "",
        state: str = "",
    ) -> None:
        detail_text = _safe_text(detail)
        if not detail_text:
            return
        should_follow_output = self._should_follow_output_after_session_update(session)
        entry = self._ensure_activity_message(session)
        label_text = self._activity_label(label)
        if label_text == "thinking":
            detail_text = _thinking_stage_label(detail_text)
        items = self._activity_items(entry)
        item_key = _safe_text(activity_id)
        target: dict[str, Any] | None = None
        if item_key:
            for item in items:
                if _safe_text(item.get("id")) == item_key:
                    target = item
                    break
        if target is None:
            target = {
                "id": item_key or f"activity-{len(items) + 1}",
                "label": label_text,
                "detail": detail_text,
                "preview": _safe_text(preview),
                "output_text": _normalize_chat_content(output_text).strip(),
                "output_summary": self._activity_output_summary(output_text),
                "state": _safe_text(state).lower(),
            }
            items.append(target)
        else:
            target["label"] = label_text
            target["detail"] = detail_text
            if preview:
                target["preview"] = _safe_text(preview)
            if output_text:
                normalized_output = _normalize_chat_content(output_text).strip()
                target["output_text"] = normalized_output
                target["output_summary"] = self._activity_output_summary(normalized_output)
            if state:
                target["state"] = _safe_text(state).lower()
        self._bump_chat_render_revision(session)
        if should_follow_output:
            session.view.chat_follow_output = True
        self._persist_session_state()

    def _start_turn_activity(self, session: TuiSession, *, detail: str) -> None:
        session.view.active_activity_message_index = None
        self._append_activity_line(session, label="thinking", detail=detail)

    def _finish_turn_activity(self, session: TuiSession, *, detail: str | None = None) -> None:
        if detail:
            self._append_activity_line(session, label="thinking", detail=detail)
        session.view.active_activity_message_index = None

    def _toggle_activity_details(self, mode: str = "toggle") -> bool:
        session = self.current_session
        view = session.view
        if not any(
            self._activity_items(message)
            for message in view.messages
            if _safe_text(getattr(message, "role", "")).lower() == "tool"
            and isinstance(getattr(message, "metadata", None), dict)
            and getattr(message, "metadata", {}).get("kind") == "activity"
        ):
            self._set_status(f"No activity blocks in {session.title}.")
            self._render_all()
            return False

        action = _safe_text(mode).lower() or "toggle"
        if action in {"expand", "open", "on"}:
            view.activity_details_expanded = True
        elif action in {"collapse", "close", "off"}:
            view.activity_details_expanded = False
        else:
            view.activity_details_expanded = not view.activity_details_expanded
        self._bump_chat_render_revision(session)
        state = "expanded" if view.activity_details_expanded else "collapsed"
        self._set_status(f"Activity output {state} for {session.title}.")
        self._persist_session_state()
        self._render_all()
        return True

    def _toggle_command_details(self, mode: str = "toggle") -> bool:
        session = self.current_session
        view = session.view
        has_command_blocks = any(
            _safe_text(getattr(message, "role", "")).lower() == "system"
            and isinstance(getattr(message, "metadata", None), dict)
            and getattr(message, "metadata", {}).get("kind") == "command"
            for message in view.messages
        )
        if not has_command_blocks:
            self._set_status(f"No command blocks in {session.title}.")
            self._render_all()
            return False

        action = _safe_text(mode).lower() or "toggle"
        if action in {"expand", "open", "on"}:
            view.command_details_expanded = True
        elif action in {"collapse", "close", "off"}:
            view.command_details_expanded = False
        else:
            view.command_details_expanded = not view.command_details_expanded
        self._bump_chat_render_revision(session)
        state = "expanded" if view.command_details_expanded else "collapsed"
        self._set_status(f"Command output {state} for {session.title}.")
        self._persist_session_state()
        self._render_all()
        return True

    def _chat_line_count(self) -> int:
        return len(self._current_chat_render_lines())

    def _chat_window_height(self) -> int:
        info = self.chat_panel.render_info
        if info is not None:
            return max(1, info.window_height)
        return 10

    def _chat_max_scroll(self) -> int:
        info = self.chat_panel.render_info
        if info is not None:
            return max(0, info.content_height - info.window_height)
        return max(0, self._chat_line_count() - self._chat_window_height())

    def _should_follow_output_after_session_update(self, session: TuiSession) -> bool:
        if not self.sessions:
            return True
        if self.current_session is not session:
            return True
        self._capture_chat_view_state()
        return bool(session.view.chat_follow_output)

    def _capture_chat_view_state(self) -> None:
        if not self.sessions:
            return
        session = self.current_session
        view = session.view
        view.chat_scroll_line = max(0, int(self.chat_panel.vertical_scroll))
        view.chat_follow_output = view.chat_scroll_line >= self._chat_max_scroll()

    def _restore_chat_view_state(self) -> None:
        if not self.sessions:
            return
        session = self.current_session
        view = session.view
        if view.chat_follow_output:
            self._scroll_chat_to_bottom(force=True)
            return
        max_scroll = self._chat_max_scroll()
        self.chat_panel.vertical_scroll = min(max(0, view.chat_scroll_line), max_scroll)

    def _scroll_chat_to_bottom(self, *, force: bool = False) -> None:
        if not self.sessions:
            return
        session = self.current_session
        view = session.view
        if not force and not view.chat_follow_output:
            return
        target = self._chat_max_scroll()
        view.chat_scroll_line = target
        view.chat_follow_output = True
        self.chat_panel.vertical_scroll = target

    def _scroll_chat_lines(self, delta: int) -> None:
        if not self.sessions or delta == 0:
            return
        session = self.current_session
        view = session.view
        max_scroll = self._chat_max_scroll()
        if view.chat_follow_output:
            if int(view.chat_scroll_line) >= max_scroll:
                current = max_scroll
            else:
                current = max(0, int(self.chat_panel.vertical_scroll))
        else:
            current = max(0, int(view.chat_scroll_line))
        target = current + delta
        target = min(max(0, target), max_scroll)
        view.chat_scroll_line = target
        view.chat_follow_output = target >= max_scroll
        self.chat_panel.vertical_scroll = target
        self._render_all()

    def _scroll_chat_page(self, page_delta: int) -> None:
        self._scroll_chat_lines(CHAT_SCROLL_STEP_LINES * page_delta)

    def _scroll_chat_home(self) -> None:
        if not self.sessions:
            return
        session = self.current_session
        view = session.view
        view.chat_scroll_line = 0
        view.chat_follow_output = False
        self.chat_panel.vertical_scroll = 0
        self._render_all()

    def _scroll_chat_end(self) -> None:
        self._scroll_chat_to_bottom(force=True)
        self._render_all()

    def _set_status(self, text: str) -> None:
        self.status = _safe_text(text) or "Ready"

    @staticmethod
    def _clear_session_skill_reload_pending(session: TuiSession) -> None:
        operator = session.operator
        operator.pending_skill_reload = False
        operator.pending_skill_reload_reason = ""

    @staticmethod
    def _mark_session_skill_reload_pending(session: TuiSession, *, reason: str) -> None:
        operator = session.operator
        operator.pending_skill_reload = True
        operator.pending_skill_reload_reason = _safe_text(reason) or "workspace skill runtime changed"

    def _queue_workspace_skill_reload(
        self,
        *,
        active_session: TuiSession,
        reason: str,
        include_current: bool,
    ) -> int:
        queued = 0
        for session in self.sessions:
            if self._runs_via_gateway(session):
                continue
            if session.session_id == active_session.session_id and not include_current:
                continue
            if not session.projection.busy and session.runtime.agent is None:
                continue
            self._mark_session_skill_reload_pending(session, reason=reason)
            queued += 1
            if session.session_id != active_session.session_id and not session.projection.busy and session.runtime.agent is not None:
                self._invalidate_session_agent(session)
        if queued:
            self._persist_session_state()
        return queued

    def _session_skill_runtime_summary(self, session: TuiSession) -> str:
        if self._runs_via_gateway(session):
            if session.operator.pending_skill_reload:
                return "queued reload"
            return "remote managed"
        if session.operator.pending_skill_reload:
            return "reload pending"
        if session.runtime.agent is None:
            return "cold"
        return "synced"

    def _clear_local_skill_policy_snapshot(self) -> None:
        self._local_skill_policy_snapshot = None

    def _cache_local_skill_policy_snapshot(
        self,
        session: TuiSession | None,
        *,
        loader: Any | None = None,
        entries: list[Any] | None = None,
        policy: Any | None = None,
        allow_discover: bool = True,
    ) -> dict[str, Any] | None:
        target = session or (self.current_session if self.sessions else None)
        if target is None or self._runs_via_gateway(target):
            self._clear_local_skill_policy_snapshot()
            return None

        effective_policy = policy
        if effective_policy is None:
            try:
                effective_policy = load_workspace_skill_policy(self.workspace)
            except Exception:
                effective_policy = None

        effective_loader = loader
        if effective_loader is None and allow_discover:
            try:
                effective_loader = resolve_skill_catalog_loader(
                    workspace_dir=self.workspace,
                    agent=target.runtime.agent,
                    config=self._load_runtime_config(),
                )
            except Exception:
                effective_loader = None

        effective_entries = list(entries) if entries is not None else None
        if effective_entries is None and effective_loader is not None:
            try:
                effective_entries = list_skill_entries(effective_loader, include_blocked=True)
            except Exception:
                effective_entries = []
        if effective_entries is None:
            effective_entries = []

        counts = summarize_skill_entries(effective_entries, effective_policy)
        snapshot = {
            "enabled": bool(effective_loader is not None),
            "mode": _safe_text(counts.get("mode")) or _safe_text(getattr(effective_policy, "mode", "")) or "all",
            "active": _safe_nonnegative_int(counts.get("active")),
            "ready": _safe_nonnegative_int(counts.get("ready")),
            "blocked": _safe_nonnegative_int(counts.get("blocked")),
            "total": _safe_nonnegative_int(counts.get("total")),
            "workspace": _safe_nonnegative_int(counts.get("workspace")),
            "allow_count": len(tuple(getattr(effective_policy, "allowlist", ()) or ())),
            "deny_count": len(tuple(getattr(effective_policy, "denylist", ()) or ())),
        }
        self._local_skill_policy_snapshot = snapshot
        return snapshot

    def _local_skill_policy_snapshot_for(self, session: TuiSession) -> dict[str, Any] | None:
        if self._runs_via_gateway(session):
            return None
        cached = self._local_skill_policy_snapshot
        if cached is not None:
            return cached
        return self._cache_local_skill_policy_snapshot(session)

    def _local_skill_runtime_overview(self, session: TuiSession) -> str:
        runtime = self._session_skill_runtime_summary(session)
        snapshot = self._local_skill_policy_snapshot_for(session)
        if not snapshot or not bool(snapshot.get("enabled")):
            return runtime
        return (
            f"{runtime} | "
            f"a{_safe_nonnegative_int(snapshot.get('active'))} / "
            f"r{_safe_nonnegative_int(snapshot.get('ready'))}"
        )

    def _local_skill_policy_overview(self, session: TuiSession) -> str:
        snapshot = self._local_skill_policy_snapshot_for(session)
        if not snapshot:
            return "unavailable"
        if not bool(snapshot.get("enabled")):
            return "disabled"
        return (
            f"{_safe_text(snapshot.get('mode')) or 'all'} | "
            f"+{_safe_nonnegative_int(snapshot.get('allow_count'))} | "
            f"-{_safe_nonnegative_int(snapshot.get('deny_count'))}"
        )

    def _read_skill_catalog_signature(self) -> tuple[str, ...] | None:
        session = self.current_session if self.sessions else None
        agent = session.runtime.agent if session is not None else None
        try:
            return skill_catalog_signature(
                workspace_dir=self.workspace,
                agent=agent,
                config=self._load_runtime_config(),
            )
        except Exception:
            return None

    def _clear_skill_catalog_change_notice(self) -> None:
        self._skill_catalog_change_notice = ""

    def _refresh_skill_catalog_signature_baseline(self) -> None:
        self._skill_catalog_signature = self._read_skill_catalog_signature()
        self._clear_skill_catalog_change_notice()
        self._last_skill_catalog_check_at = time.monotonic()

    def _check_skill_catalog_change(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if (
            not force
            and self._last_skill_catalog_check_at > 0
            and (now - self._last_skill_catalog_check_at) < SKILL_CATALOG_CHECK_INTERVAL_SECONDS
        ):
            return
        self._last_skill_catalog_check_at = now
        current_signature = self._read_skill_catalog_signature()
        baseline_signature = self._skill_catalog_signature
        if baseline_signature is None:
            self._skill_catalog_signature = current_signature
            if current_signature is None:
                self._clear_skill_catalog_change_notice()
            return
        if current_signature is None:
            self._skill_catalog_signature = None
            self._clear_skill_catalog_change_notice()
            return
        if current_signature == baseline_signature:
            self._clear_skill_catalog_change_notice()
            return
        reminder = "changed; run /skill refresh"
        if self._skill_catalog_change_notice != reminder:
            self._skill_catalog_change_notice = reminder
            self._set_status("Skill catalog changed. Run /skill refresh to reload skills.")

    @staticmethod
    def _task_prompt_preview(prompt: str, *, limit: int = 56) -> str:
        cleaned = _safe_text(prompt)
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[: max(0, limit - 3)]}..."

    def _find_task(self, session: TuiSession, task_id: str | None) -> TaskEntry | None:
        target = _safe_text(task_id)
        if not target:
            return None
        for task in session.view.tasks:
            if task.task_id == target:
                return task
        return None

    def _create_task(self, session: TuiSession, prompt: str) -> TaskEntry:
        runtime = session.runtime
        view = session.view
        task = TaskEntry(
            task_id=f"task-{runtime.next_task_index}",
            prompt=prompt,
            status="queued",
        )
        runtime.next_task_index += 1
        view.tasks.append(task)
        runtime.active_task_id = task.task_id
        self._persist_session_state()
        return task

    def _update_task(
        self,
        task: TaskEntry | None,
        *,
        status: str | None = None,
        submission_id: str | None = None,
        stop_reason: str | None = None,
        note: str | None = None,
    ) -> None:
        if task is None:
            return
        if status:
            task.status = _safe_text(status).lower() or task.status
        if submission_id is not None:
            task.submission_id = _safe_text(submission_id)
        if stop_reason is not None:
            task.stop_reason = _safe_text(stop_reason).lower()
        if note is not None:
            task.note = _safe_text(note)
        task.updated_at = _now_label()
        self._persist_session_state()

    def _render_tasks(self, session: TuiSession | None = None) -> str:
        target = session or self.current_session
        tasks = target.view.tasks
        if not tasks:
            return f"Tasks ({target.title}):\n  (none)"
        lines: list[str] = [f"Tasks ({target.title}):"]
        for task in tasks:
            prompt = self._task_prompt_preview(task.prompt)
            detail_parts = [f"{task.task_id}", f"status={task.status}", f"updated={task.updated_at}"]
            if task.submission_id:
                detail_parts.append(f"submission={task.submission_id}")
            if task.stop_reason:
                detail_parts.append(f"stop={task.stop_reason}")
            if task.note:
                detail_parts.append(f"note={task.note}")
            lines.append(f"  - {' | '.join(detail_parts)} | prompt={prompt}")
        return "\n".join(lines)

    def _snapshot_resume_agent_messages(self, session: TuiSession) -> list[dict[str, Any]]:
        runtime = session.runtime
        messages = getattr(runtime.agent, "messages", None)
        if isinstance(messages, list) and messages:
            return [_serialize_agent_message(item) for item in messages]
        if runtime.restored_agent_messages:
            return _copy_serialized_messages(runtime.restored_agent_messages)
        return _fallback_agent_messages_from_chat(session.view.messages)

    def _set_pending_resume(
        self,
        session: TuiSession,
        *,
        task_id: str | None,
        agent_messages: Sequence[dict[str, Any]] | None = None,
    ) -> None:
        runtime = session.runtime
        projection = session.projection
        supplemental = projection.supplemental
        runtime.pending_resume_task_id = _safe_text(task_id) or None
        runtime.pending_resume_agent_messages = _copy_serialized_messages(agent_messages)
        runtime.pending_resume_started = False
        supplemental.recovery_running_state = _safe_text(
            projection.running_state or supplemental.recovery_running_state
        )
        supplemental.recovery_pending_approvals = [
            dict(item)
            for item in projection.pending_approvals
            if isinstance(item, dict) and _safe_text(item.get("token"))
        ]

    def _clear_pending_resume(self, session: TuiSession, *, task_id: str | None = None) -> None:
        runtime = session.runtime
        supplemental = session.projection.supplemental
        if task_id is not None:
            current = _safe_text(runtime.pending_resume_task_id)
            target = _safe_text(task_id)
            if current and current != target:
                return
        runtime.pending_resume_task_id = None
        runtime.pending_resume_agent_messages = []
        runtime.pending_resume_started = False
        supplemental.recovery_running_state = ""
        supplemental.recovery_pending_approvals = []

    async def _resume_pending_session_task(self, session: TuiSession) -> bool:
        runtime = session.runtime
        projection = session.projection
        task_id = _safe_text(runtime.pending_resume_task_id)
        if not task_id or runtime.pending_resume_started or projection.busy:
            return False

        task = self._find_task(session, task_id)
        if task is None or not _preserve_message_text(task.prompt):
            if task is not None:
                self._update_task(
                    task,
                    status="cancelled",
                    stop_reason="restart",
                    note=_append_task_note(task.note, "resume data missing"),
                )
            self._clear_pending_resume(session, task_id=task_id)
            self._persist_session_state()
            self._render_all()
            return False

        runtime.pending_resume_started = True
        self._schedule(
            self._run_chat_turn(
                task.prompt,
                session=session,
                existing_task=task,
                append_user_message=False,
                resuming=True,
                restore_agent_messages=runtime.pending_resume_agent_messages or runtime.restored_agent_messages,
            )
        )
        return True

    async def _resume_pending_tasks(self) -> int:
        resumed = 0
        for session in self.sessions:
            if await self._resume_pending_session_task(session):
                resumed += 1
        if resumed:
            noun = "task" if resumed == 1 else "tasks"
            self._set_status(f"Resuming {resumed} interrupted {noun} from previous run.")
            self._render_all()
        return resumed

    @staticmethod
    def _provider_identity(provider: dict[str, Any]) -> tuple[str, str]:
        return (
            _safe_text(provider.get("source")),
            _safe_text(provider.get("provider_id")),
        )

    @classmethod
    def _model_identity(
        cls,
        provider: dict[str, Any],
        model: dict[str, Any],
    ) -> tuple[str, str, str]:
        source, provider_id = cls._provider_identity(provider)
        return (source, provider_id, _safe_text(model.get("model_id")))

    @staticmethod
    def _provider_default_model_id(provider: dict[str, Any]) -> str:
        default_model_id = _safe_text(provider.get("default_model_id"))
        if default_model_id:
            return default_model_id
        raw_models = provider.get("models", [])
        if isinstance(raw_models, list):
            for item in raw_models:
                if not isinstance(item, dict):
                    continue
                model_id = _safe_text(item.get("model_id"))
                if not model_id:
                    continue
                if item.get("is_default"):
                    return model_id
            for item in raw_models:
                if not isinstance(item, dict):
                    continue
                model_id = _safe_text(item.get("model_id"))
                if model_id:
                    return model_id
        return ""

    @staticmethod
    def _session_selected_model_identity(session: TuiSession) -> tuple[str, str, str] | None:
        return RuntimeSessionModelIdentityCodec.selected_identity_from_projection(session.projection)

    @staticmethod
    def _session_pending_model_identity(session: TuiSession) -> tuple[str, str, str] | None:
        return RuntimeSessionModelIdentityCodec.pending_identity_from_projection(session.operator)

    @staticmethod
    def _route_model_identity(route: Any) -> tuple[str, str, str] | None:
        return RuntimeSessionModelIdentityCodec.route_model_identity_from_route(route)

    @staticmethod
    def _format_model_identity(identity: tuple[str, str, str] | None) -> str:
        if identity is None:
            return "auto"
        source, provider_id, model_id = identity
        if source in {"config", "bootstrap"}:
            return model_id or "auto"
        if provider_id and model_id:
            return f"{provider_id}/{model_id}"
        return model_id or provider_id or "auto"

    @classmethod
    def _set_session_selected_model_identity(
        cls,
        session: TuiSession,
        identity: tuple[str, str, str] | None,
    ) -> None:
        RuntimeSessionModelIdentityCodec.set_selected_identity_on_projection(session.projection, identity)

    @classmethod
    def _set_session_pending_model_identity(
        cls,
        session: TuiSession,
        identity: tuple[str, str, str] | None,
    ) -> None:
        RuntimeSessionModelIdentityCodec.set_pending_identity_on_projection(session.operator, identity)

    def _session_active_model_identity(self, session: TuiSession) -> tuple[str, str, str] | None:
        selected = self._session_selected_model_identity(session)
        if selected is not None:
            return selected
        if session.runtime.agent is not None:
            return self._route_model_identity(getattr(session.runtime.agent, "runtime_route", None))
        return None

    def _preferred_cursor_model_identity(self, session: TuiSession | None) -> tuple[str, str, str] | None:
        if session is None:
            return None
        pending = self._session_pending_model_identity(session)
        if session.projection.busy and pending is not None:
            return pending
        return self._session_active_model_identity(session)

    def _registry_model_entry(
        self,
        identity: tuple[str, str, str] | None,
    ) -> dict[str, Any] | None:
        if identity is None:
            return None
        source, provider_id, model_id = identity
        normalized_model_id = _safe_text(model_id)
        if not normalized_model_id:
            return None
        for provider in self.providers:
            if self._provider_identity(provider) != (source, provider_id):
                continue
            for model in provider.get("models", []):
                if not isinstance(model, dict):
                    continue
                if _safe_text(model.get("model_id")) != normalized_model_id:
                    continue
                return model
        return None

    def _lookup_model_usage_limit(
        self,
        identity: tuple[str, str, str] | None,
    ) -> tuple[int, str]:
        entry = self._registry_model_entry(identity)
        if not isinstance(entry, dict):
            return 0, "unknown"
        learned = _safe_nonnegative_int(entry.get("learned_token_limit"))
        if learned > 0:
            return learned, "learned_token_limit"
        context_window = _safe_nonnegative_int(entry.get("context_window"))
        if context_window > 0:
            return context_window, "model_context_window"
        return 0, "unknown"

    def _provider_and_model_from_identity(
        self,
        identity: tuple[str, str, str] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if identity is None:
            return None
        source, provider_id, model_id = identity
        for provider in self.providers:
            if self._provider_identity(provider) != (source, provider_id):
                continue
            for model in provider.get("models", []):
                if not isinstance(model, dict):
                    continue
                if _safe_text(model.get("model_id")) == model_id:
                    return provider, model
        return None

    def _find_model_limit_matches(
        self,
        *,
        provider_id: str,
        model_id: str,
        source: str | None = None,
    ) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], bool]:
        matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
        provider_found = False
        normalized_source = _safe_text(source).lower()
        normalized_provider_id = _safe_text(provider_id)
        normalized_model_id = _safe_text(model_id)
        for provider in self.providers:
            provider_source, current_provider_id = self._provider_identity(provider)
            if normalized_source and provider_source != normalized_source:
                continue
            if current_provider_id != normalized_provider_id:
                continue
            provider_found = True
            for model in provider.get("models", []):
                if not isinstance(model, dict):
                    continue
                if _safe_text(model.get("model_id")) == normalized_model_id:
                    matches.append((provider, model))
        return matches, provider_found

    def _resolve_model_limit_target(
        self,
        args: Sequence[str],
    ) -> tuple[tuple[dict[str, Any], dict[str, Any]] | None, str | None]:
        parts = [_safe_text(item) for item in args if _safe_text(item)]
        if not parts:
            selected = self._selected_provider_and_model()
            if selected is not None:
                return selected, None
            active = self._provider_and_model_from_identity(
                self._session_active_model_identity(self.current_session)
            )
            if active is not None:
                return active, None
            return None, "No model selected. Focus a model first or use /model limit show <provider_id> <model_id>."

        explicit_source: str | None = None
        if parts[0].lower() in {"custom", "preset"}:
            explicit_source = parts[0].lower()
            parts = parts[1:]

        if len(parts) != 2:
            return (
                None,
                "Usage: /model limit [show|clear] [custom|preset] <provider_id> <model_id>",
            )

        matches, provider_found = self._find_model_limit_matches(
            provider_id=parts[0],
            model_id=parts[1],
            source=explicit_source,
        )
        if not provider_found:
            return None, f"Provider not found: {parts[0]}"
        if not matches:
            return None, f"Model not found in {parts[0]}: {parts[1]}"
        if len(matches) > 1:
            return (
                None,
                f"Multiple providers match {parts[0]}/{parts[1]}. Use /model limit show <custom|preset> {parts[0]} {parts[1]}.",
            )
        return matches[0], None

    def _render_model_limit_details(
        self,
        provider: dict[str, Any],
        model: dict[str, Any],
    ) -> str:
        identity = self._model_identity(provider, model)
        learned_limit = _safe_nonnegative_int(model.get("learned_token_limit"))
        context_window = _safe_nonnegative_int(model.get("context_window"))
        effective_limit, limit_source = self._lookup_model_usage_limit(identity)
        lines = [
            f"source   | {_safe_text(provider.get('source'))}",
            f"provider | {_safe_text(provider.get('provider_id'))}",
            f"model    | {_safe_text(model.get('model_id'))}",
            f"display  | {_safe_text(model.get('display_name')) or _safe_text(model.get('model_id'))}",
            f"learned  | {learned_limit:,}" if learned_limit > 0 else "learned  | --",
            f"context  | {context_window:,}" if context_window > 0 else "context  | --",
        ]
        if effective_limit > 0:
            lines.append(f"effective| {effective_limit:,} ({limit_source})")
        else:
            lines.append("effective| --")
        if self._model_is_effective_default(provider, model, session=self.current_session):
            lines.append("default  | yes")
        return "\n".join(lines)

    def _render_model_limit_list(self) -> str:
        rows: list[str] = []
        for provider in self.providers:
            source = _safe_text(provider.get("source"))
            provider_id = _safe_text(provider.get("provider_id"))
            for model in provider.get("models", []):
                if not isinstance(model, dict):
                    continue
                learned_limit = _safe_nonnegative_int(model.get("learned_token_limit"))
                if learned_limit <= 0:
                    continue
                model_id = _safe_text(model.get("model_id"))
                context_window = _safe_nonnegative_int(model.get("context_window"))
                default_suffix = " | default" if self._model_is_effective_default(provider, model, session=self.current_session) else ""
                context_text = f"{context_window:,}" if context_window > 0 else "--"
                rows.append(
                    f"[{source}] {provider_id}/{model_id}{default_suffix} | learned {learned_limit:,} | context {context_text}"
                )
        if not rows:
            return "No learned token limits recorded."
        return "\n".join(rows)

    def _refresh_sessions_after_model_limit_change(
        self,
        identity: tuple[str, str, str],
    ) -> None:
        refreshed_limit, _ = self._lookup_model_usage_limit(identity)
        for session in self.sessions:
            projection = session.projection
            runtime = session.runtime
            active_identity = self._session_active_model_identity(session)
            pending_identity = self._session_pending_model_identity(session)
            if active_identity == identity or pending_identity == identity:
                projection.token_limit = refreshed_limit
            if (
                active_identity == identity
                and not self._runs_via_gateway(session)
                and not projection.busy
                and runtime.agent is not None
            ):
                self._invalidate_session_agent(session)

    def _effective_provider_default_model_id(
        self,
        provider: dict[str, Any],
        *,
        session: TuiSession | None = None,
    ) -> str:
        if session is not None:
            identity = self._session_active_model_identity(session)
            if identity is not None:
                source, provider_id, model_id = identity
                if self._provider_identity(provider) == (source, provider_id):
                    return model_id
        return self._provider_default_model_id(provider)

    def _model_is_effective_default(
        self,
        provider: dict[str, Any],
        model: dict[str, Any],
        *,
        session: TuiSession | None = None,
    ) -> bool:
        model_id = _safe_text(model.get("model_id"))
        if session is not None:
            identity = self._session_active_model_identity(session)
            if identity is not None and self._provider_identity(provider) == identity[:2]:
                return model_id == identity[2]
        return bool(model.get("is_default"))

    @staticmethod
    def _agent_knowledge_base_enabled(agent: Any) -> bool:
        return RuntimeSessionAgentSupport.agent_knowledge_base_enabled(agent)

    @classmethod
    def _apply_agent_knowledge_base_enabled(cls, agent: Any, enabled: bool) -> bool:
        return RuntimeSessionAgentSupport.apply_agent_knowledge_base_enabled(agent, enabled)

    @classmethod
    def _session_knowledge_base_enabled(cls, session: TuiSession) -> bool | None:
        projection = session.projection
        runtime = session.runtime
        if runtime.agent is not None:
            projection.knowledge_base_enabled = cls._agent_knowledge_base_enabled(runtime.agent)
        return projection.knowledge_base_enabled

    def _refresh_local_runtime_projection(self, session: TuiSession) -> tuple[dict[str, Any], dict[str, Any]]:
        projection = session.projection
        runtime = session.runtime
        if self._runs_via_gateway(session):
            return (
                self._normalize_memory_diagnostics_payload(projection.memory_diagnostics),
                self._normalize_sandbox_diagnostics_payload(projection.sandbox_diagnostics),
            )
        if runtime.agent is not None:
            projection.knowledge_base_enabled = self._agent_knowledge_base_enabled(runtime.agent)
        return (
            self._refresh_local_memory_diagnostics(session),
            self._refresh_local_sandbox_diagnostics(session),
        )

    def _capture_local_runtime_projection(self, session: TuiSession) -> None:
        if self._runs_via_gateway(session):
            return
        projection = session.projection
        runtime = session.runtime
        if runtime.agent is not None:
            projection.knowledge_base_enabled = self._agent_knowledge_base_enabled(runtime.agent)
            projection.last_prepared_context = self._session_payload_codec.agent_last_prepared_context(
                runtime.agent
            )
            projection.prepared_context_diagnostics = (
                self._session_payload_codec.agent_prepared_context_diagnostics(runtime.agent)
            )
        self._refresh_local_runtime_projection(session)

    def _capture_session_agent_snapshot(self, session: TuiSession) -> None:
        self._capture_local_runtime_projection(session)
        runtime = session.runtime
        live_messages = self._session_payload_codec.serialize_live_agent_messages(runtime.agent)
        if live_messages:
            runtime.restored_agent_messages = live_messages
            return
        if runtime.restored_agent_messages:
            return
        runtime.restored_agent_messages = _fallback_agent_messages_from_chat(session.view.messages)

    @staticmethod
    def _reset_local_runtime_execution_state(session: TuiSession) -> None:
        runtime = session.runtime
        projection = session.projection
        runtime.agent = None
        runtime.cancel_event = None
        projection.running_state = ""
        projection.pending_approvals = []

    def _selected_model_identity(self) -> tuple[str, str, str] | None:
        selected = self._selected_provider_and_model()
        if selected is None:
            return None
        provider, model = selected
        return self._model_identity(provider, model)

    def _set_model_cursor_by_identity(
        self,
        identity: tuple[str, str, str] | None,
    ) -> bool:
        if identity is None:
            return False
        source, provider_id, model_id = identity
        for p_idx, provider, models in self._visible_provider_models():
            if self._provider_identity(provider) != (source, provider_id):
                continue
            for m_idx, model in models:
                if _safe_text(model.get("model_id")) != model_id:
                    continue
                self.model_cursor = (p_idx, m_idx)
                return True
        return False

    def _refresh_registry(
        self,
        *,
        preferred_model: tuple[str, str, str] | None = None,
    ) -> None:
        try:
            previous_cursor = self.model_cursor
            session_preferred = self._preferred_cursor_model_identity(self.current_session) if self.sessions else None
            previous_model = preferred_model or session_preferred or self._selected_model_identity()
            self.providers = self._load_provider_inventory()
            positions = self._model_positions()
            if not positions:
                self.model_cursor = None
            elif previous_model and self._set_model_cursor_by_identity(previous_model):
                pass
            elif previous_cursor in positions:
                self.model_cursor = previous_cursor
            else:
                self.model_cursor = positions[0]
            self._refresh_command_completer()
        except Exception as exc:
            self.providers = []
            self.model_cursor = None
            self._set_status(f"Model registry unavailable: {exc}")

    def _load_provider_inventory(self) -> list[dict[str, Any]]:
        session = self.current_session if self.sessions else None
        if self._runs_via_gateway(session):
            try:
                payload = surface_payload_from_dto(
                    self.remote_model_service.list_agent_model_candidates_sync()
                )
                items = list(payload.get("items") or [])
                if items:
                    return items
            except Exception:
                pass
        return self.registry.list_registry()

    def _visible_provider_models(
        self,
    ) -> list[tuple[int, dict[str, Any], list[tuple[int, dict[str, Any]]]]]:
        if not self.providers:
            return []
        token = self.model_filter
        visible: list[tuple[int, dict[str, Any], list[tuple[int, dict[str, Any]]]]] = []
        for p_idx, provider in enumerate(self.providers):
            models = provider.get("models", [])
            if not isinstance(models, list):
                continue

            provider_text = _safe_model_filter(
                " ".join(
                    [
                        str(provider.get("provider_id", "")),
                        str(provider.get("provider_name", "")),
                        str(provider.get("source", "")),
                    ]
                )
            )
            provider_match = bool(token and token in provider_text)

            matched_models: list[tuple[int, dict[str, Any]]] = []
            for m_idx, model in enumerate(models):
                if not isinstance(model, dict):
                    continue
                if not token or provider_match:
                    matched_models.append((m_idx, model))
                    continue

                model_text = _safe_model_filter(
                    " ".join(
                        [
                            str(model.get("model_id", "")),
                            str(model.get("display_name", "")),
                        ]
                    )
                )
                if token in model_text:
                    matched_models.append((m_idx, model))

            if matched_models:
                visible.append((p_idx, provider, matched_models))
        return visible

    def _model_positions(self) -> list[tuple[int, int]]:
        positions: list[tuple[int, int]] = []
        for p_idx, _, models in self._visible_provider_models():
            for m_idx, _ in models:
                positions.append((p_idx, m_idx))
        return positions

    def _set_model_filter(self, value: str) -> None:
        self.model_filter = _safe_model_filter(value)
        positions = self._model_positions()
        if not positions:
            self.model_cursor = None
            return
        if self.model_cursor not in positions:
            self.model_cursor = positions[0]

    def _move_model_cursor(self, delta: int) -> None:
        positions = self._model_positions()
        if not positions:
            self.model_cursor = None
            if self.model_filter:
                self._set_status(f"No models match filter: {self.model_filter}")
            else:
                self._set_status("No models available.")
            self._render_all()
            return
        if self.model_cursor not in positions:
            self.model_cursor = positions[0]
            self._render_all()
            return
        idx = positions.index(self.model_cursor)
        self.model_cursor = positions[(idx + delta) % len(positions)]
        self._render_all()

    def _selected_provider_and_model(self) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if self.model_cursor is None:
            return None
        p_idx, m_idx = self.model_cursor
        for visible_provider_index, provider, models in self._visible_provider_models():
            if visible_provider_index != p_idx:
                continue
            for visible_model_index, model in models:
                if visible_model_index == m_idx:
                    return provider, model
        return None

    def _current_model_hint(self) -> str:
        if not self.sessions:
            return "none"
        session = self.current_session
        active_identity = self._session_active_model_identity(session)
        if active_identity is None:
            active_identity = self._selected_model_identity()
        pending_identity = self._session_pending_model_identity(session)
        if pending_identity is not None and pending_identity != active_identity:
            return (
                f"{self._format_model_identity(active_identity)} -> "
                f"{self._format_model_identity(pending_identity)} queued"
            )
        return self._format_model_identity(active_identity)

    async def _activate_session_model_selection(
        self,
        session: TuiSession,
        identity: tuple[str, str, str],
        *,
        warm_prefix: str,
        clear_pending_skill_reload_on_success: bool = False,
    ) -> None:
        view = session.view
        view.active_activity_message_index = None
        if session.session_id == self.current_session.session_id:
            self._set_model_cursor_by_identity(identity)
        await self._local_agent_runtime.rebuild_with_identity(
            session,
            identity=identity,
            warm_prefix=warm_prefix,
            clear_pending_model_identity=True,
            clear_pending_skill_reload_on_success=clear_pending_skill_reload_on_success,
            persist_before_warm=True,
        )

    async def _build_session_agent(self, session: TuiSession) -> Agent:
        projection = session.projection
        runtime = session.runtime
        selected_identity = self._session_selected_model_identity(session)
        approval_profile, access_level = self._session_runtime_policy(session)
        agent = await build_agent_kernel(
            workspace_dir=self.workspace,
            options=AgentKernelBuildOptions(
                config=self._load_runtime_config(),
                approval_profile=approval_profile,
                access_level=access_level,
                requested_model=selected_identity[2] if selected_identity is not None else None,
                requested_provider_source=(
                    selected_identity[0]
                    if selected_identity is not None and selected_identity[0] in {"custom", "preset"}
                    else None
                ),
                requested_provider_id=(
                    selected_identity[1]
                    if selected_identity is not None and selected_identity[0] in {"custom", "preset"}
                    else None
                ),
                console_output=False,
                allow_interactive_setup=False,
                suppress_background_output=True,
            ),
        )
        self._restore_agent_messages(session, agent)
        if projection.knowledge_base_enabled is None:
            projection.knowledge_base_enabled = self._agent_knowledge_base_enabled(agent)
        else:
            projection.knowledge_base_enabled = self._apply_agent_knowledge_base_enabled(
                agent,
                bool(projection.knowledge_base_enabled),
            )
        if hasattr(agent, "api_total_tokens"):
            agent.api_total_tokens = _safe_nonnegative_int(projection.token_usage)
        if _safe_nonnegative_int(projection.token_limit) > 0 and hasattr(agent, "token_limit"):
            agent.token_limit = _safe_nonnegative_int(projection.token_limit)
        if isinstance(projection.last_prepared_context, dict):
            agent.last_prepared_turn_context = dict(projection.last_prepared_context)
        if isinstance(projection.prepared_context_diagnostics, dict):
            agent.prepared_context_diagnostics = dict(projection.prepared_context_diagnostics)
        runtime.agent = agent
        self._cache_local_skill_policy_snapshot(session, allow_discover=True)
        self._session_usage_stats(session)
        return agent

    async def _warm_session_agent(
        self,
        session: TuiSession,
        *,
        prefix: str,
    ) -> Agent | None:
        try:
            agent = await self._build_session_agent(session)
        except Exception as exc:
            self._set_status(f"{prefix}, but warmup failed: {exc}. It will retry on next turn.")
            return None
        self._set_status(f"{prefix} and warmed agent on {agent.llm.model}.")
        return agent

    async def _apply_session_model_selection(
        self,
        session: TuiSession,
        identity: tuple[str, str, str],
    ) -> None:
        projection = session.projection
        runtime = session.runtime
        if self._runs_via_gateway(session):
            await self._apply_remote_session_model_selection(session, identity)
            return

        plan = SessionModelSelectionService.plan_update(
            request=SessionModelSelectionRequest(
                provider_source=identity[0],
                provider_id=identity[1],
                model_id=identity[2],
            ),
            current_identity=self._session_active_model_identity(session),
            pending_identity=self._session_pending_model_identity(session),
            busy=bool(projection.busy),
            runtime_attached=runtime.agent is not None,
        )
        if plan.update_pending_identity:
            self._set_session_pending_model_identity(session, plan.pending_identity)
        if plan.touch_and_persist and plan.activate_identity is None:
            self._persist_session_state()
        if plan.queued:
            feedback = (
                SessionModelSelectionService.already_queued_feedback(
                    model_label=self._format_model_identity(identity),
                    session_title=session.title,
                )
                if plan.already_queued
                else SessionModelSelectionService.queued_feedback(
                    model_label=self._format_model_identity(identity),
                    session_title=session.title,
                )
            )
            if plan.already_queued:
                self._set_status(feedback.status_text)
            else:
                self._set_status(feedback.status_text)
            if session.session_id == self.current_session.session_id:
                self._set_model_cursor_by_identity(identity)
            self._render_all()
            return

        if plan.already_selected:
            self._set_status(
                SessionModelSelectionService.already_selected_feedback(
                    model_label=self._format_model_identity(identity),
                    session_title=session.title,
                ).status_text
            )
            if session.session_id == self.current_session.session_id:
                self._set_model_cursor_by_identity(identity)
            self._render_all()
            return

        target_identity = plan.activate_identity or identity
        applied_feedback = SessionModelSelectionService.applied_feedback(
            model_label=self._format_model_identity(target_identity),
            session_title=session.title,
        )
        await self._activate_session_model_selection(
            session,
            target_identity,
            warm_prefix=applied_feedback.status_text.rstrip("."),
        )
        self._render_all()

    async def _apply_remote_session_model_selection(
        self,
        session: TuiSession,
        identity: tuple[str, str, str],
    ) -> None:
        projection = session.projection
        source, provider_id, model_id = identity
        response = await self.remote_session_service.update_session_model(
            session.session_id,
            MainAgentSessionModelSelectionRequest(
                provider_source=source,
                provider_id=provider_id,
                model_id=model_id,
                **self._remote_request_binding_kwargs(session),
            ),
        )
        await self._sync_remote_session_detail(session, recent_limit=80)
        response_payload = surface_payload_from_dto(response)
        normalized_identity = (
            self._normalize_remote_model_identity_payload(response_payload, prefix="pending_")
            if response.queued
            else self._normalize_remote_model_identity_payload(response_payload, prefix="selected_")
        )
        if normalized_identity is not None and session.session_id == self.current_session.session_id:
            self._set_model_cursor_by_identity(normalized_identity)
        if response.queued:
            projection.supplemental.remote_last_command_summary = (
                f"model use | queued {self._format_model_identity(identity)}"
            )
            self._set_status(
                SessionModelSelectionService.queued_feedback(
                    model_label=self._format_model_identity(identity),
                    session_title=session.title,
                ).status_text
            )
        else:
            projection.supplemental.remote_last_command_summary = (
                f"model use | applied {self._format_model_identity(identity)}"
            )
            self._set_status(
                SessionModelSelectionService.applied_feedback(
                    model_label=self._format_model_identity(identity),
                    session_title=session.title,
                ).status_text
            )
        self._render_all()

    @classmethod
    def _normalize_remote_model_identity_payload(
        cls,
        payload: dict[str, Any],
        *,
        prefix: str,
    ) -> tuple[str, str, str] | None:
        return cls._normalize_session_model_identity_payload(
            source=payload.get(f"{prefix}model_source"),
            provider_id=payload.get(f"{prefix}provider_id"),
            model_id=payload.get(f"{prefix}model_id"),
        )

    @classmethod
    def _normalize_session_model_identity_payload(
        cls,
        *,
        source: Any,
        provider_id: Any,
        model_id: Any,
    ) -> tuple[str, str, str] | None:
        return RuntimeSessionModelIdentityCodec.normalize_model_identity(
            source=source,
            provider_id=provider_id,
            model_id=model_id,
        )

    async def _apply_pending_session_model_selection(self, session: TuiSession) -> None:
        pending_identity = SessionModelSelectionService.pending_identity_to_apply(
            pending_identity=self._session_pending_model_identity(session),
            busy=bool(session.projection.busy),
        )
        if pending_identity is None:
            return
        await self._activate_session_model_selection(
            session,
            pending_identity,
            warm_prefix=(
                f"Applied queued model {self._format_model_identity(pending_identity)} "
                f"for {session.title}"
            ),
            clear_pending_skill_reload_on_success=bool(session.operator.pending_skill_reload),
        )

    async def _apply_pending_session_skill_reload(self, session: TuiSession) -> bool:
        projection = session.projection
        operator = session.operator
        if self._runs_via_gateway(session) or projection.busy or not operator.pending_skill_reload:
            return False
        outcome = await self._local_agent_runtime.rebuild_current_identity(
            session,
            warm_prefix=f"Reloaded skills for {session.title}",
            clear_pending_skill_reload_on_success=True,
        )
        if outcome.warmed_agent is None:
            return False
        return True

    async def _apply_selected_model(self) -> None:
        selected = self._selected_provider_and_model()
        if selected is None:
            self._set_status("No model selected.")
            self._render_all()
            return
        provider, model = selected
        try:
            await self._apply_session_model_selection(
                self.current_session,
                self._model_identity(provider, model),
            )
        except Exception as exc:
            self._set_status(f"Model apply failed: {exc}")
            self._render_all()

    async def _discover_for_selected_provider(self) -> None:
        selected = self._selected_provider_and_model()
        if selected is None:
            self._set_status("No provider selected for discovery.")
            self._render_all()
            return
        provider, _ = selected
        try:
            updated = self.registry.discover_models(
                source=str(provider.get("source", "custom")),
                provider_id=str(provider.get("provider_id", "")),
            )
            discovered_default = self._provider_default_model_id(updated)
            self._refresh_registry(
                preferred_model=(
                    _safe_text(updated.get("source")),
                    _safe_text(updated.get("provider_id")),
                    discovered_default,
                )
            )
            self._set_status(f"Discovered models for {provider.get('provider_id')}.")
        except Exception as exc:
            self._set_status(f"Model discovery failed: {exc}")
        self._render_all()

    def _on_input_submit(self, buffer) -> bool:
        text = buffer.text.strip()
        if not text:
            return False
        buffer.document = Document("")
        self._schedule(self._handle_prompt(text))
        return False

    def _submit_input_buffer(self) -> None:
        buffer = self.input_box.buffer
        text = buffer.text.strip()
        if not text:
            self._set_status("Input is empty.")
            self._render_all()
            return
        buffer.document = Document("")
        self._schedule(self._handle_prompt(text))
        self.application.invalidate()

    def _on_command_submit(self, buffer) -> bool:
        text = buffer.text.strip()
        if not text:
            return False
        buffer.document = Document("")
        self.command_palette_open = False
        self.application.layout.focus(self.input_box)
        self._schedule(self._run_command(text.lstrip("/")))
        self._render_all()
        return False

    def _schedule(self, coro: asyncio.Future[Any] | asyncio.Task[Any] | Any) -> None:
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)

        def _cleanup(done: asyncio.Task[Any]) -> None:
            self.background_tasks.discard(done)
            try:
                done.result()
            except asyncio.CancelledError:
                return
            except Exception as exc:  # pragma: no cover - defensive
                self._set_status(f"Background task failed: {exc}")
                self._render_all()

        task.add_done_callback(_cleanup)

    async def _handle_prompt(self, text: str) -> None:
        if text.startswith("/"):
            await self._run_command(text[1:])
            return
        session = self.current_session
        if self._runs_via_gateway(session):
            await self._run_remote_chat_turn(text, session=session)
            return
        await self._run_chat_turn(text, session=session)

    def _session_runtime_policy(self, session: TuiSession | None) -> tuple[str, str]:
        if session is None:
            return self.default_approval_profile, self.default_access_level
        return SessionRuntimePolicyService.current_runtime_policy(
            agent=session.runtime.agent,
            sandbox_diagnostics=session.projection.sandbox_diagnostics,
            default_approval_profile=self.default_approval_profile,
            default_access_level=self.default_access_level,
        )

    def _load_runtime_config(self) -> Config:
        return self._config_loader()

    async def _apply_local_session_runtime_policy(
        self,
        session: TuiSession,
        *,
        approval_profile: str,
        access_level: str,
    ) -> dict[str, Any]:
        projection = session.projection
        runtime = session.runtime
        current_profile, current_access = self._session_runtime_policy(session)
        execution = SessionRuntimePolicyService.execute_update(
            current_approval_profile=current_profile,
            current_access_level=current_access,
            requested_approval_profile=approval_profile,
            requested_access_level=access_level,
            busy=bool(projection.busy),
            waiting_on_approval=bool(projection.pending_approvals),
            runtime_attached=runtime.agent is not None,
            sandbox_diagnostics=projection.sandbox_diagnostics,
            normalize_sandbox_diagnostics_payload=self._normalize_sandbox_diagnostics_payload,
            reconfigure_attached_runtime=(
                lambda resolved_profile, resolved_access: reconfigure_agent_runtime_policy(
                    agent=runtime.agent,
                    config=self._load_runtime_config(),
                    workspace_dir=self.workspace,
                    approval_profile_override=resolved_profile,
                    access_level_override=resolved_access,
                )
            )
            if runtime.agent is not None
            else None,
        )
        projection.sandbox_diagnostics = dict(execution.diagnostics)
        if runtime.agent is not None:
            self._refresh_local_runtime_projection(session)
            diagnostics = self._normalize_sandbox_diagnostics_payload(projection.sandbox_diagnostics)
        else:
            diagnostics = dict(execution.diagnostics)
        projection.sandbox_diagnostics = diagnostics
        self._persist_session_state()
        return diagnostics

    async def _apply_remote_session_runtime_policy(
        self,
        session: TuiSession,
        *,
        approval_profile: str,
        access_level: str,
    ) -> MainAgentSessionRuntimePolicyResponse:
        response = await self.remote_session_service.update_session_runtime_policy(
            session.session_id,
            MainAgentSessionRuntimePolicyRequest(
                approval_profile=approval_profile,
                access_level=access_level,
                **self._remote_request_binding_kwargs(session),
            ),
        )
        projection = session.projection
        projection.active_surface = _safe_text(response.active_surface) or projection.active_surface
        projection.sandbox_diagnostics = self._normalize_sandbox_diagnostics_payload(
            response.sandbox_diagnostics
        )
        try:
            await self._sync_remote_session_detail(session, recent_limit=80)
        except Exception:
            pass
        self._persist_session_state()
        return response

    async def _update_session_runtime_policy(
        self,
        session: TuiSession,
        *,
        approval_profile: str | None = None,
        access_level: str | None = None,
        command_label: str | None = None,
    ) -> bool:
        return await self._runtime_policy_commands.update(
            session,
            approval_profile=approval_profile,
            access_level=access_level,
            command_label=command_label,
        )

    @staticmethod
    def _tool_name_from_hook(tool_call: Any) -> str:
        function_obj = getattr(tool_call, "function", None)
        if function_obj is not None:
            function_name = _safe_text(getattr(function_obj, "name", ""))
            if function_name:
                return function_name
        fallback = _safe_text(getattr(tool_call, "name", ""))
        return fallback or "tool"

    def _update_running_state(self, session: TuiSession, text: str) -> None:
        projection = session.projection
        if not projection.busy:
            return
        projection.running_state = _safe_text(text)
        if projection.running_state and session.session_id == self.current_session.session_id:
            self._set_status(f"{session.title}: {projection.running_state}")
        self._persist_session_state()
        self._render_all()

    async def _ensure_submission_loop(self, session: TuiSession) -> AgentSubmissionLoop:
        runtime = session.runtime
        if runtime.submission_loop is not None:
            await runtime.submission_loop.start()
            return runtime.submission_loop

        bus = InMemoryLoopMessageBus()
        loop_context = AgentLoopContext(
            message_bus=bus,
            session_id=session.session_id,
        )

        async def _agent_factory(_context: AgentLoopContext) -> Agent:
            agent = await self._ensure_agent(session)
            if agent is None:
                raise RuntimeError("Agent is not available.")
            return agent

        submission_loop = AgentSubmissionLoop(
            context=loop_context,
            agent_factory=_agent_factory,
            hooks=self._build_turn_hooks(session),
        )
        await submission_loop.start()
        runtime.submission_loop = submission_loop
        runtime.loop_bus = bus
        return submission_loop

    async def _shutdown_submission_loop(self, session: TuiSession) -> None:
        runtime = session.runtime
        projection = session.projection
        loop = runtime.submission_loop
        if loop is None:
            runtime.loop_bus = None
            return
        try:
            await loop.stop()
        finally:
            runtime.submission_loop = None
            runtime.loop_bus = None
            projection.pending_approvals = []

    async def _shutdown_all_submission_loops(self) -> None:
        for session in self.sessions:
            await self._shutdown_submission_loop(session)

    @staticmethod
    def _pending_approval_token(payload: dict[str, Any]) -> str:
        return _safe_text(payload.get("token"))

    @classmethod
    def _normalize_pending_approvals_payload(cls, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            token = cls._pending_approval_token(item)
            if not token:
                continue
            normalized.append(
                {
                    "token": token,
                    "tool_name": _safe_text(item.get("tool_name")) or "tool",
                    "arguments": dict(item.get("arguments")) if isinstance(item.get("arguments"), dict) else {},
                    "kind": _safe_text(item.get("kind")) or None,
                    "reason": _safe_text(item.get("reason")) or None,
                    "cache_key": _safe_text(item.get("cache_key")) or None,
                    "can_escalate": bool(item.get("can_escalate", False)),
                    "step": max(0, int(item.get("step") or 0)),
                }
            )
        return normalized

    def _pending_approval_summary(self, session: TuiSession) -> str:
        projection = session.projection
        supplemental = projection.supplemental
        runtime = session.runtime
        run_wait = self._run_approval_wait_payload(session)
        if run_wait is not None:
            tool_name = _safe_text(run_wait.get("tool_name")) or "tool"
            token = self._pending_approval_token(run_wait)
            return f"1 pending | {tool_name} [{token}]" if token else f"1 pending | {tool_name}"
        approvals = [item for item in projection.pending_approvals if self._pending_approval_token(item)]
        if not approvals:
            recovered = [
                item
                for item in supplemental.recovery_pending_approvals
                if self._pending_approval_token(item)
            ]
            if recovered and (runtime.pending_resume_task_id or self._session_has_gateway_recovery(session)):
                if len(recovered) == 1:
                    item = recovered[0]
                    tool_name = _safe_text(item.get("tool_name")) or "tool"
                    return f"restart lost | {tool_name}"
                return f"restart lost | {len(recovered)} approvals"
            return "none"
        if len(approvals) == 1:
            item = approvals[0]
            tool_name = _safe_text(item.get("tool_name")) or "tool"
            token = self._pending_approval_token(item)
            return f"1 pending | {tool_name} [{token}]"
        return f"{len(approvals)} pending"

    @staticmethod
    def _run_approval_wait_payload(session: TuiSession | None) -> dict[str, Any] | None:
        if session is None:
            return None
        payload = session.projection.supplemental.remote_run_approval_wait
        if not isinstance(payload, dict):
            return None
        token = MiniAgentTuiApp._pending_approval_token(payload)
        tool_name = _safe_text(payload.get("tool_name"))
        return payload if token or tool_name else None

    def _pending_approval_target(self, session: TuiSession | None = None) -> dict[str, Any] | None:
        target_session = session or (self.current_session if self.sessions else None)
        if target_session is None:
            return None
        run_wait = self._run_approval_wait_payload(target_session)
        if run_wait is not None:
            return run_wait
        pending = [
            item
            for item in target_session.projection.pending_approvals
            if self._pending_approval_token(item)
        ]
        if not pending:
            return None
        return pending[0]

    def _approval_modal_visible(self) -> bool:
        return self._approval_modal_open and self._pending_approval_target() is not None

    def _open_approval_modal(self, *, force: bool = False) -> bool:
        target = self._pending_approval_target()
        if target is None:
            self._approval_modal_open = False
            return False
        token = self._pending_approval_token(target)
        if force:
            self._approval_modal_snoozed_token = None
        elif self._approval_modal_snoozed_token and token == self._approval_modal_snoozed_token:
            return False
        self._approval_modal_open = True
        self._approval_modal_choice = "approve"
        return True

    def _close_approval_modal(self, *, snooze: bool = False) -> None:
        target = self._pending_approval_target()
        if snooze and target is not None:
            self._approval_modal_snoozed_token = self._pending_approval_token(target) or None
        elif not snooze:
            self._approval_modal_snoozed_token = None
        self._approval_modal_open = False

    def _toggle_approval_modal_choice(self, *, backward: bool = False) -> None:
        current = self._approval_modal_choice
        if backward:
            self._approval_modal_choice = "deny" if current == "approve" else "approve"
            return
        self._approval_modal_choice = "deny" if current == "approve" else "approve"

    async def _confirm_approval_modal(self) -> bool:
        session = self.current_session
        target = self._pending_approval_target(session)
        if target is None:
            self._close_approval_modal()
            self._set_status("No pending approval request.")
            self._render_all()
            return False
        approved = self._approval_modal_choice == "approve"
        token = self._pending_approval_token(target) or None
        result = await self._respond_to_pending_approval(
            session=session,
            approved=approved,
            token=token,
        )
        if result:
            self._close_approval_modal()
        return result

    def _knowledge_base_summary(self, session: TuiSession) -> str:
        enabled = self._session_knowledge_base_enabled(session)
        if enabled is None:
            return "default"
        return "enabled" if enabled else "disabled"

    @staticmethod
    def _normalize_prepared_context_payload(value: Any) -> dict[str, Any]:
        return RuntimeSessionPayloadCodec.normalize_prepared_context_payload(value)

    @staticmethod
    def _normalize_prepared_context_diagnostics_payload(value: Any) -> dict[str, Any]:
        return RuntimeSessionPayloadCodec.normalize_prepared_context_diagnostics_payload(value)

    @staticmethod
    def _normalize_memory_diagnostics_payload(value: Any) -> dict[str, Any]:
        return RuntimeSessionPayloadCodec.normalize_memory_diagnostics_payload(value)

    @staticmethod
    def _normalize_sandbox_diagnostics_payload(value: Any) -> dict[str, Any]:
        return RuntimeSessionPayloadCodec.normalize_sandbox_diagnostics_payload(value)

    def _record_local_prepared_context_projection(
        self,
        session: TuiSession,
        *,
        prepared_context: Any = None,
        prepared_context_present: bool = False,
        prepared_context_diagnostics: Any = None,
        prepared_context_diagnostics_present: bool = False,
    ) -> dict[str, Any]:
        projection = session.projection
        runtime = session.runtime
        normalized_prepared_context = (
            self._normalize_prepared_context_payload(prepared_context)
            if prepared_context_present
            else None
        )
        normalized_diagnostics = (
            self._normalize_prepared_context_diagnostics_payload(prepared_context_diagnostics)
            if prepared_context_diagnostics_present
            else None
        )

        if runtime.agent is not None:
            if prepared_context_present:
                try:
                    runtime.agent.last_prepared_turn_context = dict(normalized_prepared_context or {})
                except Exception:
                    pass
            if prepared_context_diagnostics_present:
                try:
                    runtime.agent.prepared_context_diagnostics = dict(normalized_diagnostics or {})
                except Exception:
                    pass
            self._capture_local_runtime_projection(session)
            return self._normalize_prepared_context_payload(projection.last_prepared_context)

        if prepared_context_present:
            projection.last_prepared_context = dict(normalized_prepared_context or {})
        if prepared_context_diagnostics_present:
            projection.prepared_context_diagnostics = dict(normalized_diagnostics or {})
        if prepared_context_present or prepared_context_diagnostics_present:
            self._refresh_local_runtime_projection(session)
        return self._normalize_prepared_context_payload(projection.last_prepared_context)

    def _refresh_local_memory_diagnostics(self, session: TuiSession) -> dict[str, Any]:
        projection = session.projection
        runtime = session.runtime
        if self._runs_via_gateway(session):
            return self._normalize_memory_diagnostics_payload(projection.memory_diagnostics)
        try:
            projection.memory_diagnostics = build_memory_diagnostics(
                workspace_dir=self.workspace,
                session_id=session.session_id,
                last_prepared_context=projection.last_prepared_context,
                last_memory_automation=self._session_payload_codec.agent_last_memory_automation(runtime.agent),
                last_runtime_task_memory=self._session_payload_codec.agent_last_runtime_task_memory(runtime.agent),
            )
        except Exception:
            projection.memory_diagnostics = self._normalize_memory_diagnostics_payload(projection.memory_diagnostics)
        return self._normalize_memory_diagnostics_payload(projection.memory_diagnostics)

    def _session_memory_diagnostics(
        self,
        session: TuiSession,
        *,
        refresh_local: bool = False,
    ) -> dict[str, Any]:
        projection = session.projection
        if self._runs_via_gateway(session):
            return self._normalize_memory_diagnostics_payload(projection.memory_diagnostics)
        if refresh_local or not isinstance(projection.memory_diagnostics, dict) or not projection.memory_diagnostics:
            return self._refresh_local_memory_diagnostics(session)
        return self._normalize_memory_diagnostics_payload(projection.memory_diagnostics)

    def _refresh_local_sandbox_diagnostics(self, session: TuiSession) -> dict[str, Any]:
        projection = session.projection
        runtime = session.runtime
        if self._runs_via_gateway(session):
            return self._normalize_sandbox_diagnostics_payload(projection.sandbox_diagnostics)
        existing = self._normalize_sandbox_diagnostics_payload(projection.sandbox_diagnostics)
        if runtime.agent is None:
            approval_profile, access_level = SessionRuntimePolicyService.current_runtime_policy(
                agent=None,
                sandbox_diagnostics=existing,
                default_approval_profile=self.default_approval_profile,
                default_access_level=self.default_access_level,
            )
            projection.sandbox_diagnostics = self._normalize_sandbox_diagnostics_payload(
                SessionRuntimePolicyService.local_sandbox_diagnostics(
                    sandbox_diagnostics=existing,
                    approval_profile=approval_profile,
                    access_level=access_level,
                )
            )
            return self._normalize_sandbox_diagnostics_payload(projection.sandbox_diagnostics)
        try:
            projection.sandbox_diagnostics = collect_sandbox_diagnostics(agent=runtime.agent)
        except Exception:
            projection.sandbox_diagnostics = self._normalize_sandbox_diagnostics_payload(projection.sandbox_diagnostics)
        return self._normalize_sandbox_diagnostics_payload(projection.sandbox_diagnostics)

    def _session_sandbox_diagnostics(
        self,
        session: TuiSession,
        *,
        refresh_local: bool = False,
    ) -> dict[str, Any]:
        projection = session.projection
        if self._runs_via_gateway(session):
            return self._normalize_sandbox_diagnostics_payload(projection.sandbox_diagnostics)
        if refresh_local or not isinstance(projection.sandbox_diagnostics, dict) or not projection.sandbox_diagnostics:
            return self._refresh_local_sandbox_diagnostics(session)
        return self._normalize_sandbox_diagnostics_payload(projection.sandbox_diagnostics)

    def _prepared_context_summary(self, session: TuiSession) -> str:
        return prepared_turn_context_summary_line(
            session.projection.last_prepared_context,
            include_none=True,
        )

    def _memory_summary(self, session: TuiSession) -> str:
        diagnostics = self._session_memory_diagnostics(session)
        summary = memory_diagnostics_summary_line(diagnostics)
        return summary or "cons unknown | rtm 0+0 | profile 0"

    @staticmethod
    def _normalize_context_policy_payload(value: Any) -> dict[str, Any]:
        return RuntimeSessionPayloadCodec.normalize_context_policy_payload(value)

    def _context_policy_summary(self, session: TuiSession) -> str:
        return context_policy_summary_line(
            session.projection.context_policy,
            include_default=True,
        )

    def _context_policy_metadata(self, session: TuiSession) -> dict[str, Any]:
        normalized = self._normalize_context_policy_payload(session.projection.context_policy)
        if not normalized.get("active"):
            return {}
        return {"prepared_context_policy": normalized}

    async def _update_remote_context_policy(
        self,
        session: TuiSession,
        *,
        action: str,
        sources: list[str] | None = None,
        max_items: int | None = None,
        max_total_chars: int | None = None,
        max_items_per_source: int | None = None,
    ) -> dict[str, Any]:
        response = await self.remote_session_service.update_session_context(
            session.session_id,
            MainAgentSessionContextRequest(
                action=action,
                sources=sources or [],
                max_items=max_items,
                max_total_chars=max_total_chars,
                max_items_per_source=max_items_per_source,
                **self._remote_request_binding_kwargs(session),
            ),
        )
        projection = session.projection
        await self._sync_remote_session_detail(session, recent_limit=80)
        context_policy = dict(response.context_policy or {})
        projection.supplemental.remote_last_command_summary = (
            f"context {action} | "
            f"{context_policy_summary_line(context_policy, include_default=True) if context_policy else 'context policy updated'}"
        )
        self._persist_session_state()
        return surface_payload_from_dto(response)

    async def _dispatch_remote_context_update(
        self,
        session: TuiSession,
        validation_result: CommandExecutionResult,
    ) -> bool:
        payload = validation_result.payload if isinstance(validation_result.payload, dict) else {}
        remote_request = payload.get("remote_request") if isinstance(payload.get("remote_request"), dict) else {}
        action = _safe_text(remote_request.get("action"))
        if not action:
            self._append_command_feedback(
                validation_result.command,
                summary="update failed",
                details="Remote context update request was not prepared.",
                level="error",
                metadata={"threads_visible": False},
            )
            self._set_status("Remote context update failed.")
            self._render_all()
            return False
        try:
            await self._update_remote_context_policy(
                session,
                action=action,
                sources=list(remote_request.get("sources") or []),
                max_items=remote_request.get("max_items"),
                max_total_chars=remote_request.get("max_total_chars"),
                max_items_per_source=remote_request.get("max_items_per_source"),
            )
        except Exception as exc:
            detail = extract_gateway_error_info(exc).detail
            self._append_command_feedback(
                validation_result.command,
                summary="reset failed" if action == "reset" else "update failed",
                details=detail,
                level="error",
                metadata={"threads_visible": False},
            )
            self._set_status(detail or f"Remote context {'reset' if action == 'reset' else 'update'} failed.")
            self._render_all()
            return False
        return True

    def _run_local_memory_action(
        self,
        session: TuiSession,
        *,
        action: str,
        engram_id: str | None = None,
        content: str | None = None,
        query: str | None = None,
        day: str | None = None,
        export_format: str | None = None,
        detail_mode: str = "full",
    ) -> dict[str, Any]:
        result = self.local_command_service.execute_memory_action(
            workspace=self.workspace,
            session_id=session.session_id,
            diagnostics_loader=lambda: self._session_memory_diagnostics(session, refresh_local=True),
            action=action,
            engram_id=engram_id,
            content=content,
            query=query,
            day=day,
            export_format=export_format,
            detail_mode=detail_mode,
            prepared_context=session.projection.last_prepared_context,
        )
        self._persist_session_state()
        return result.to_dict()

    async def _run_remote_memory_action(
        self,
        session: TuiSession,
        *,
        action: str,
        engram_id: str | None = None,
        content: str | None = None,
        query: str | None = None,
        day: str | None = None,
        export_format: str | None = None,
        detail_mode: str = "full",
    ) -> dict[str, Any]:
        response = await self.remote_session_service.manage_session_memory(
            session.session_id,
            MainAgentSessionMemoryRequest(
                action=action,
                engram_id=engram_id,
                content=content,
                query=query,
                day=day,
                export_format=export_format,
                detail_mode=detail_mode,
                **self._remote_request_binding_kwargs(session),
            ),
        )
        projection = session.projection
        projection.memory_diagnostics = self._normalize_memory_diagnostics_payload(
            response.memory_diagnostics
        )
        result = dict(response.result or {})
        if result:
            summary_text = _safe_text(result.get("summary")) or "memory command"
            projection.supplemental.remote_last_command_summary = f"memory {action} | {summary_text}"
        if _safe_text(action).lower().replace("-", "_") in {
            "refresh",
            "shared_clear",
            "promote_shared",
            "promote_note",
            "promote_profile",
            "save_note",
            "save_profile",
        }:
            await self._sync_remote_session_detail(session, recent_limit=80)
        self._persist_session_state()
        return surface_payload_from_dto(response)

    async def _run_memory_action_for_session(
        self,
        session: TuiSession,
        *,
        action: str,
        engram_id: str | None = None,
        content: str | None = None,
        query: str | None = None,
        day: str | None = None,
        export_format: str | None = None,
        detail_mode: str = "full",
    ) -> dict[str, Any]:
        if self._runs_via_gateway(session):
            return await self._run_remote_memory_action(
                session,
                action=action,
                engram_id=engram_id,
                content=content,
                query=query,
                day=day,
                export_format=export_format,
                detail_mode=detail_mode,
            )
        return self._run_local_memory_action(
            session,
            action=action,
            engram_id=engram_id,
            content=content,
            query=query,
            day=day,
            export_format=export_format,
            detail_mode=detail_mode,
        )

    @staticmethod
    def _memory_command_result(response: Any) -> dict[str, Any]:
        if isinstance(response, dict) and isinstance(response.get("result"), dict):
            return dict(response.get("result") or {})
        if isinstance(response, dict):
            return dict(response)
        return {}

    async def _execute_memory_command_plan(
        self,
        session: TuiSession,
        *,
        command: str,
        action: str,
        success_status: str,
        failure_summary: str,
        failure_detail_prefix: str,
        failure_status: str,
        summary_fallback: str | Callable[[TuiSession, dict[str, Any]], str] = "",
        metadata: dict[str, Any] | None = None,
        metadata_builder: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        **request_kwargs: Any,
    ) -> bool:
        try:
            response = await self._run_memory_action_for_session(
                session,
                action=action,
                **request_kwargs,
            )
        except Exception as exc:
            detail = extract_gateway_error_info(exc).detail
            self._append_command_feedback(
                command,
                summary=failure_summary,
                details=f"{failure_detail_prefix}{detail}",
                level="error",
            )
            self._set_status(failure_status)
            self._render_all()
            return False

        result = self._memory_command_result(response)
        summary = _safe_text(result.get("summary"))
        if not summary:
            if callable(summary_fallback):
                summary = _safe_text(summary_fallback(session, result))
            else:
                summary = _safe_text(summary_fallback)
        resolved_metadata = {"threads_visible": False}
        if isinstance(metadata, dict):
            resolved_metadata.update(metadata)
        if callable(metadata_builder):
            extra_metadata = metadata_builder(result)
            if isinstance(extra_metadata, dict):
                resolved_metadata.update(extra_metadata)
        self._append_command_feedback(
            command,
            summary=summary,
            details=str(result.get("details") or ""),
            metadata=resolved_metadata,
        )
        self._set_status(success_status)
        self._render_all()
        return True

    def _resolve_memory_command_plan(
        self,
        args: Sequence[str],
    ) -> MemoryCommandPlan | CommandExecutionResult:
        return prepare_memory_command_plan(
            surface="tui",
            args=args,
            memory_summary_resolver=lambda current_session, _result: self._memory_summary(current_session),
        )

    async def _run_remote_skill_action(
        self,
        session: TuiSession,
        *,
        action: str,
        skill_name: str | None = None,
        path: str | None = None,
        query: str | None = None,
        mode: str | None = None,
    ) -> dict[str, Any]:
        response = await self.remote_session_service.manage_session_skill(
            session.session_id,
            MainAgentSessionSkillRequest(
                action=action,
                skill_name=skill_name,
                path=path,
                query=query,
                mode=mode if _safe_text(mode) else None,
                **self._remote_request_binding_kwargs(session),
            ),
        )
        projection = session.projection
        result = dict(response.result or {})
        if result:
            summary_text = _safe_text(result.get("summary")) or "skill command"
            projection.supplemental.remote_last_command_summary = f"skill {action} | {summary_text}"
        if _safe_text(action).lower().replace("-", "_") in REMOTE_SKILL_MUTATION_ACTIONS:
            await self._sync_remote_session_detail(session, recent_limit=80)
            if _safe_text(response.status).lower() == "ok":
                self._refresh_skill_catalog_signature_baseline()
        self._persist_session_state()
        return surface_payload_from_dto(response)

    @staticmethod
    def _remote_skill_feedback_level(
        status: str,
        *,
        found: bool | None = None,
    ) -> str:
        normalized_status = _safe_text(status).lower()
        if normalized_status in {"busy", "disabled", "unavailable", "not_found"}:
            return "error"
        if found is False:
            return "error"
        return "info"

    def _remote_skill_status_text(
        self,
        session: TuiSession,
        *,
        action: str,
        status: str,
        found: bool | None = None,
        skill_name: str | None = None,
    ) -> str:
        normalized_action = _safe_text(action).lower().replace("-", "_")
        normalized_status = _safe_text(status).lower()
        if normalized_status == "disabled":
            return "Skill support is disabled."
        if normalized_status == "unavailable":
            return "Skill catalog unavailable."
        if normalized_status == "busy":
            return f"{session.title} is busy."
        if normalized_status == "not_found" or found is False:
            return "Skill not found."
        if normalized_action == "show":
            return f"Showing skill {skill_name}." if _safe_text(skill_name) else "Showing skill."
        if normalized_action == "list":
            return "Skill catalog shown."
        if normalized_action == "active":
            return "Workspace skill policy shown."
        if normalized_action == "search":
            return "Skill search completed."
        if normalized_action == "mode":
            return "Workspace skill mode updated."
        if normalized_action in {"enable", "disable"}:
            return "Workspace skill policy updated."
        if normalized_action == "reset":
            return "Workspace skill policy reset."
        if normalized_action == "refresh":
            return f"Skill catalog refreshed for {session.title}."
        if normalized_action == "install":
            return "Workspace skill installed."
        if normalized_action == "uninstall":
            return "Workspace skill uninstalled."
        if normalized_action == "rollback":
            return "Workspace skill rolled back."
        return "Skill command completed."

    @staticmethod
    def _remote_skill_usage_status_text(action: str) -> str:
        normalized_action = _safe_text(action).lower().replace("-", "_")
        if normalized_action == "list":
            return "Skill list usage shown."
        return f"Skill {normalized_action or 'command'} usage displayed."

    def _remote_skill_usage_result(self, action: str) -> CommandExecutionResult:
        normalized_action = _safe_text(action).lower().replace("-", "_")
        command = f"skill {normalized_action}".strip() if normalized_action else "skill"
        return CommandExecutionResult(
            command=command,
            summary="usage",
            details=build_command_usage_text("tui", "skill", action=normalized_action or None),
            status_text=self._remote_skill_usage_status_text(normalized_action),
            kind="usage",
        )

    def _resolve_skill_command_plan(
        self,
        invocation_or_args: Any,
    ) -> SkillCommandPlan | CommandExecutionResult:
        if hasattr(invocation_or_args, "args"):
            args = list(getattr(invocation_or_args, "args", []))
            raw_text = str(getattr(invocation_or_args, "raw_text", "") or "")
        else:
            args = list(invocation_or_args or [])
            raw_text = ""
        action = _safe_text(args[0]).lower() if args else "list"
        prepared = self.local_command_service.prepare_skill_request(
            surface="tui",
            action=action,
            args=args,
            raw_text=raw_text,
        )
        if isinstance(prepared, CommandExecutionResult):
            return prepared
        return SkillCommandPlan(
            command=self.local_command_service.format_skill_command_name(
                prepared,
                fallback_action=prepared.action,
            ),
            action=_safe_text(prepared.action).lower() or "list",
            args=tuple(args),
            raw_text=raw_text,
            request=prepared,
        )

    @staticmethod
    def _remote_skill_request_kwargs(request: SkillCommandRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        skill_name = _safe_text(request.skill_name)
        path = _safe_text(request.path)
        query = _safe_text(request.query)
        mode = _safe_text(request.mode)
        if skill_name:
            payload["skill_name"] = skill_name
        if path:
            payload["path"] = path
        if query:
            payload["query"] = query
        if mode:
            payload["mode"] = mode
        return payload

    def _resolve_remote_skill_command_plan(
        self,
        plan: SkillCommandPlan,
    ) -> RemoteSkillCommandPlan:
        return RemoteSkillCommandPlan(
            command=plan.command,
            action=plan.action,
            request_kwargs=self._remote_skill_request_kwargs(plan.request),
            skill_name=_safe_text(plan.request.skill_name) or None,
        )

    @staticmethod
    def _remote_skill_summary_fallback(
        action: str,
        *,
        found: bool | None = None,
    ) -> str:
        normalized_action = _safe_text(action).lower().replace("-", "_")
        if normalized_action == "show":
            return "showing skill" if found is not False else "skill not found"
        return {
            "list": "skill catalog shown",
            "active": "workspace skill policy shown",
            "search": "skill search completed",
            "mode": "workspace skill mode updated",
            "enable": "workspace skill policy updated",
            "disable": "workspace skill policy updated",
            "reset": "workspace skill policy reset",
            "refresh": "skill catalog refreshed",
            "install": "skill installed",
            "uninstall": "skill uninstalled",
            "rollback": "skill rolled back",
        }.get(normalized_action, "skill command completed")

    def _apply_remote_skill_response(
        self,
        session: TuiSession,
        plan: RemoteSkillCommandPlan,
        response: dict[str, Any],
    ) -> None:
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        status = _safe_text(response.get("status")).lower()
        found = bool(result.get("found", True)) if plan.action == "show" else None
        self._append_command_feedback(
            plan.command,
            summary=_safe_text(result.get("summary"))
            or self._remote_skill_summary_fallback(plan.action, found=found),
            details=str(result.get("details") or ""),
            level=self._remote_skill_feedback_level(status, found=found),
            metadata={"threads_visible": False},
        )
        self._set_status(
            self._remote_skill_status_text(
                session,
                action=plan.action,
                status=status,
                found=found,
                skill_name=plan.skill_name,
            )
        )

    def _cache_local_skill_result_snapshot(
        self,
        session: TuiSession,
        payload: dict[str, Any],
        *,
        refresh_signature: bool = False,
    ) -> None:
        if refresh_signature:
            self._refresh_skill_catalog_signature_baseline()
        loader = payload.get("loader")
        entries = payload.get("entries")
        policy = payload.get("policy")
        if loader is None and entries is None and policy is None:
            return
        self._cache_local_skill_policy_snapshot(
            session,
            loader=loader,
            entries=list(entries) if isinstance(entries, list) else None,
            policy=policy,
            allow_discover=False,
        )

    async def _apply_local_skill_command_result(
        self,
        session: TuiSession,
        result: CommandExecutionResult,
    ) -> None:
        payload = result.payload if isinstance(result.payload, dict) else {}
        reload_required = bool(payload.get("reload_required"))
        if result.kind == "info":
            self._cache_local_skill_result_snapshot(
                session,
                payload,
                refresh_signature=reload_required,
            )
        if result.kind in {"usage", "error"} or not reload_required:
            self._append_command_feedback(
                result.command,
                summary=result.summary,
                details=result.details,
                level="error" if result.kind in {"usage", "error"} else "info",
                metadata={"threads_visible": False},
            )
            self._set_status(result.status_text)
            return

        feedback = describe_skill_runtime_reload(payload)
        if session.projection.busy:
            self._queue_workspace_skill_reload(
                active_session=session,
                reason=feedback.reason,
                include_current=True,
            )
            self._append_command_feedback(
                result.command,
                summary=feedback.busy_summary,
                details=(
                    result.details
                    + "\n\nRun `/skill refresh` after the turn finishes to reload the agent."
                ),
                level="error",
                metadata={"threads_visible": False},
            )
            self._set_status(f"{session.title} is busy.")
            return

        self._queue_workspace_skill_reload(
            active_session=session,
            reason=feedback.reason,
            include_current=False,
        )
        await self._local_agent_runtime.rebuild_current_identity(
            session,
            warm_prefix=f"{feedback.warm_prefix_base} for {session.title}",
        )
        self._append_command_feedback(
            result.command,
            summary=result.summary,
            details=result.details,
            metadata={"threads_visible": False},
        )
        if feedback.success_status:
            self._set_status(feedback.success_status)
        else:
            self._set_status(result.status_text)

    def _append_prepared_context_feedback(
        self,
        session: TuiSession,
        payload: Any,
        *,
        persist: bool = True,
    ) -> None:
        normalized = self._normalize_prepared_context_payload(payload)
        summary_line = prepared_turn_context_summary_line(normalized)
        if not summary_line:
            return
        details = format_prepared_turn_context_details(
            normalized,
            include_header=False,
        )
        self._append_command_feedback(
            "context",
            session=session,
            summary=f"prepared {summary_line}",
            details=details,
            metadata={"threads_visible": False},
            persist=persist,
        )

    def _record_pending_approval(self, session: TuiSession, payload: dict[str, Any]) -> str | None:
        projection = session.projection
        token = self._pending_approval_token(payload)
        if not token:
            return None
        normalized = dict(payload)
        normalized["token"] = token
        for index, item in enumerate(projection.pending_approvals):
            if self._pending_approval_token(item) == token:
                projection.pending_approvals[index] = normalized
                self._persist_session_state()
                return token
        projection.pending_approvals.append(normalized)
        self._persist_session_state()
        return token

    def _clear_pending_approval(self, session: TuiSession, token: str | None = None) -> None:
        projection = session.projection
        supplemental = projection.supplemental
        normalized = _safe_text(token)
        if not normalized:
            projection.pending_approvals = []
            supplemental.remote_run_approval_wait = {}
            supplemental.remote_run_waiting_on_approval = False
            supplemental.remote_run_active_wait_id = None
            self._persist_session_state()
            return
        projection.pending_approvals = [
            item
            for item in projection.pending_approvals
            if self._pending_approval_token(item) != normalized
        ]
        if self._pending_approval_token(supplemental.remote_run_approval_wait) == normalized:
            supplemental.remote_run_approval_wait = {}
            supplemental.remote_run_waiting_on_approval = False
            supplemental.remote_run_active_wait_id = None
        self._persist_session_state()

    def _handle_remote_stream_approval_requested(
        self,
        session: TuiSession,
        tool_name: str,
        token: str | None,
    ) -> None:
        if token:
            self._set_status(
                f"Approval required for {session.title}: {tool_name}. Use /approve {token} or /deny {token}."
            )
        else:
            self._set_status(f"Approval required for {session.title}: {tool_name}.")
        if session.session_id == self.current_session.session_id:
            self._approval_modal_snoozed_token = None
            self._open_approval_modal(force=True)
        self._render_all()

    def _handle_remote_stream_approval_resolved(self, session: TuiSession) -> None:
        if session.session_id == self.current_session.session_id and not session.projection.pending_approvals:
            self._close_approval_modal()
        self._render_all()

    async def _remote_respond_to_pending_approval(
        self,
        session: TuiSession,
        approved: bool,
        token: str | None,
    ) -> Any:
        run_id = self._remote_run_id_for_session(session)
        if run_id:
            try:
                response = await self.remote_run_service.respond_to_approval(
                    run_id,
                    MainAgentRunApprovalRequest(
                        approved=approved,
                        token=token,
                        **self._remote_request_binding_kwargs(session),
                    ),
                )
            except Exception as exc:
                detail = extract_gateway_error_info(exc).detail.lower()
                if "not a session-backed run identifier" not in detail and "run-level control is not wired" not in detail:
                    raise
            else:
                self._apply_remote_run_summary(session, surface_payload_from_dto(response))
                return response
        return await self.remote_session_service.respond_to_approval(
            session.session_id,
            MainAgentSessionApprovalRequest(
                approved=approved,
                token=token,
                **self._remote_request_binding_kwargs(session),
            ),
        )

    async def _sync_remote_session_detail_for_command(self, session: TuiSession) -> None:
        await self._sync_remote_session_detail(session, recent_limit=80)

    async def _handle_submission_bus_event(
        self,
        *,
        session: TuiSession,
        submission_id: str,
        event_type: str,
        payload: dict[str, Any],
        stream_state: dict[str, Any] | None = None,
    ) -> None:
        if str(payload.get("submission_id", "") or "").strip() != submission_id:
            return
        projection = session.projection

        if event_type == "loop.llm_event":
            llm_event_type = _safe_text(payload.get("llm_event_type")).lower()
            if llm_event_type == "text_delta":
                chunk = str(payload.get("delta") or "")
                if chunk:
                    message_index = None
                    if isinstance(stream_state, dict):
                        raw_index = stream_state.get("assistant_message_index")
                        message_index = raw_index if isinstance(raw_index, int) else None
                    updated_index = self._append_assistant_stream_chunk(
                        session,
                        chunk,
                        message_index=message_index,
                    )
                    if isinstance(stream_state, dict):
                        stream_state["assistant_message_index"] = updated_index
                        stream_state["emitted_live_reply"] = True
                    self._schedule_stream_render()
                return
            return

        if event_type == "loop.approval.requested":
            token = self._record_pending_approval(session, payload)
            tool_name = _safe_text(payload.get("tool_name")) or "tool"
            preview = _safe_text(payload.get("arguments"))
            detail = f"approval required for {tool_name}"
            self._append_activity_line(
                session,
                label="approval",
                detail=detail,
                activity_id=f"approval:{token or tool_name}",
                preview=preview,
                state="pending",
            )
            self._update_running_state(session, detail)
            if token:
                self._set_status(
                    f"Approval required for {session.title}: {tool_name}. Use /approve {token} or /deny {token}."
                )
            else:
                self._set_status(f"Approval required for {session.title}: {tool_name}.")
            if session.session_id == self.current_session.session_id:
                self._approval_modal_snoozed_token = None
                self._open_approval_modal(force=True)
            self._render_all()
            return

        if event_type == "loop.approval.resolved":
            token = self._pending_approval_token(payload)
            decision = _safe_text(payload.get("decision")) or "resolved"
            tool_name = _safe_text(payload.get("tool_name")) or "tool"
            self._clear_pending_approval(session, token)
            self._append_activity_line(
                session,
                label="approval",
                detail=f"{decision} for {tool_name}",
                activity_id=f"approval:{token or tool_name}",
                state="ok" if decision == "approved" else "failed",
            )
            if not projection.pending_approvals and projection.busy:
                self._update_running_state(session, f"continuing after {decision}")
            if session.session_id == self.current_session.session_id and not projection.pending_approvals:
                self._close_approval_modal()
            self._render_all()

    async def _wait_for_submission_payload(
        self,
        *,
        session: TuiSession,
        submission_id: str,
        event_start_index: int,
        stream_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        bus = session.runtime.loop_bus
        if bus is None:
            raise RuntimeError("Missing submission loop bus.")
        return await wait_for_submission_completion(
            bus=bus,
            submission_id=submission_id,
            event_start_index=event_start_index,
            on_event=lambda event_type, payload: self._handle_submission_bus_event(
                session=session,
                submission_id=submission_id,
                event_type=event_type,
                payload=payload,
                stream_state=stream_state,
            ),
        )

    async def _submit_prompt_via_scheduler(
        self,
        *,
        session: TuiSession,
        agent: Agent,
        prompt: str,
        metadata: dict[str, Any] | None = None,
        start_new_run: bool = True,
    ) -> dict[str, Any]:
        runtime = session.runtime
        loop = await self._ensure_submission_loop(session)
        event_start_index = len(runtime.loop_bus.events) if runtime.loop_bus is not None else 0
        policy_overrides = {
            "max_steps": getattr(agent, "max_steps", 50),
            "max_tool_calls_per_step": getattr(agent, "max_tool_calls_per_step", None),
        }
        submission_id = await loop.submit_user_input(
            prompt,
            policy_overrides=policy_overrides,
            metadata=metadata or {},
            start_new_run=start_new_run,
        )
        payload = await self._wait_for_submission_payload(
            session=session,
            submission_id=submission_id,
            event_start_index=event_start_index,
        )
        prepared_context = self._record_local_prepared_context_projection(
            session,
            prepared_context=payload.get("prepared_context"),
            prepared_context_present="prepared_context" in payload,
            prepared_context_diagnostics=payload.get("prepared_context_diagnostics"),
            prepared_context_diagnostics_present="prepared_context_diagnostics" in payload,
        )
        self._append_prepared_context_feedback(
            session,
            prepared_context,
            persist=False,
        )
        return payload

    async def _run_minimal_workflow(self, objective: str) -> None:
        session = self.current_session
        projection = session.projection
        runtime = session.runtime
        if projection.busy:
            self._set_status(f"{session.title} is busy. Please wait for completion.")
            self._render_all()
            return

        objective_text = _safe_text(objective)
        if not objective_text:
            self._append_command_feedback(
                "workflow run",
                summary="usage",
                details="Usage: /workflow run <objective>",
                level="error",
            )
            self._set_status("Workflow objective is required.")
            self._render_all()
            return

        self._apply_session_lifecycle(session)
        self._append_message("user", f"[workflow] {objective_text}")
        projection.busy = True
        runtime.cancel_event = None
        projection.running_state = "workflow starting"
        projection.pending_approvals = []
        self._set_status(f"Running workflow for {session.title}...")
        self._render_all()

        try:
            agent = await self._ensure_agent(session)
            if agent is None:
                self._append_command_feedback(
                    "workflow run",
                    summary="agent unavailable",
                    details="Agent is not available. Configure API keys (env or .env.local) and retry.",
                    level="error",
                )
                self._set_status("Agent is not available.")
                return

            async def _stage_runner(
                stage: CoordinatorStage,
                stage_prompt: str,
            ) -> tuple[bool, str, str | None]:
                self._update_running_state(session, f"workflow {stage.value}")
                payload = await self._submit_prompt_via_scheduler(
                    session=session,
                    agent=agent,
                    prompt=stage_prompt,
                    metadata={
                        "surface": "tui",
                        "mode": "workflow",
                        "workflow": "minimal",
                        "stage": stage.value,
                    },
                    start_new_run=True,
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

            run_result, _ = await run_minimal_workflow_with_runner(
                objective=objective_text,
                stage_runner=_stage_runner,
                stop_on_failure=True,
            )
            report = format_minimal_workflow_report(
                objective=objective_text,
                result=run_result,
            )

            if run_result.status == "completed":
                self._append_message("assistant", report)
                self._set_status(f"Workflow completed for {session.title}.")
            else:
                self._append_command_feedback(
                    "workflow run",
                    summary="workflow failed",
                    details=report,
                    level="error",
                )
                self._set_status(f"Workflow failed for {session.title}.")
        except Exception as exc:
            message = f"Workflow failed: {exc}"
            self._append_command_feedback(
                "workflow run",
                summary="workflow failed",
                details=message,
                level="error",
            )
            self._set_status(message)
        finally:
            projection.busy = False
            runtime.cancel_event = None
            projection.running_state = ""
            projection.pending_approvals = []
            await self._apply_pending_session_model_selection(session)
            self._persist_session_state()
            self._render_all()

    def _invalidate_session_agent(self, session: TuiSession) -> None:
        projection = session.projection
        runtime = session.runtime
        self._capture_session_agent_snapshot(session)
        if projection.busy:
            self._cancel_session_turn(session)
        if runtime.submission_loop is not None:
            self._schedule(self._shutdown_submission_loop(session))
        self._reset_local_runtime_execution_state(session)

    def _invalidate_all_session_agents(self) -> None:
        for session in self.sessions:
            self._invalidate_session_agent(session)

    def _cancel_session_turn(self, session: TuiSession) -> bool:
        projection = session.projection
        runtime = session.runtime
        if not projection.busy:
            return False
        task = self._find_task(session, runtime.active_task_id)
        if runtime.submission_loop is not None:
            agent_cancel_event = getattr(runtime.agent, "cancel_event", None)
            if isinstance(agent_cancel_event, asyncio.Event) and not agent_cancel_event.is_set():
                agent_cancel_event.set()
            self._schedule(runtime.submission_loop.submit_interrupt(reason="user_cancel"))
            self._update_task(task, note=SessionCancelService.REQUESTED_STATE)
            projection.running_state = SessionCancelService.REQUESTED_STATE
            if session.session_id == self.current_session.session_id:
                self._set_status(SessionCancelService.requested_status_text(session.title))
                self._append_command_feedback(
                    "cancel",
                    summary=SessionCancelService.requested_summary(),
                    details=SessionCancelService.requested_status_text(session.title),
                )
            self._render_all()
            return True
        cancel_event = runtime.cancel_event
        if cancel_event is None or cancel_event.is_set():
            return False
        cancel_event.set()
        self._update_task(task, note=SessionCancelService.REQUESTED_STATE)
        projection.running_state = SessionCancelService.REQUESTED_STATE
        if session.session_id == self.current_session.session_id:
            self._set_status(SessionCancelService.requested_status_text(session.title))
            self._append_command_feedback(
                "cancel",
                summary=SessionCancelService.requested_summary(),
                details=SessionCancelService.requested_status_text(session.title),
            )
        self._render_all()
        return True

    def _cancel_current_turn(self) -> bool:
        return self._cancel_session_turn(self.current_session)

    def _request_cancel_current_turn(self, *, emit_system_when_idle: bool) -> bool:
        if self._cancel_current_turn():
            return True
        self._set_status(SessionCancelService.no_running_turn_user_text())
        if emit_system_when_idle:
            self._append_command_feedback(
                "cancel",
                summary="nothing to cancel",
                details=SessionCancelService.no_running_turn_user_text(),
                level="error",
            )
        self._render_all()
        return False

    async def _request_cancel_current_turn_async(self, *, emit_system_when_idle: bool) -> bool:
        session = self.current_session
        if not self._runs_via_gateway(session):
            return self._request_cancel_current_turn(emit_system_when_idle=emit_system_when_idle)
        return await self._request_remote_cancel_turn(session, emit_system_when_idle=emit_system_when_idle)

    async def _request_remote_cancel_turn(self, session: TuiSession, *, emit_system_when_idle: bool) -> bool:
        try:
            run_id = self._remote_run_id_for_session(session)
            if not run_id:
                raise LookupError("Missing run identifier for remote cancel.")
            response = await self.remote_run_service.cancel_run(
                run_id,
                MainAgentRunCancelRequest(
                    reason="user_cancel",
                    **self._remote_request_binding_kwargs(session),
                ),
            )
            self._apply_remote_run_summary(session, surface_payload_from_dto(response))
        except Exception as exc:
            detail = extract_gateway_error_info(exc).detail
            if SessionCancelService.is_no_running_turn_detail(detail):
                self._set_status(SessionCancelService.no_running_turn_user_text())
                if emit_system_when_idle:
                    self._append_command_feedback(
                        "cancel",
                        summary="nothing to cancel",
                        details=SessionCancelService.no_running_turn_user_text(),
                        level="error",
                    )
                self._render_all()
                return False

            message = detail or "Remote cancel failed."
            self._append_command_feedback(
                "cancel",
                summary="cancel failed",
                details=message,
                level="error",
            )
            self._set_status(message)
            self._render_all()
            return False

        projection = session.projection
        runtime = session.runtime
        task = self._find_task(session, runtime.active_task_id)
        self._update_task(task, note=SessionCancelService.REQUESTED_STATE)
        projection.busy = True
        projection.running_state = SessionCancelService.REQUESTED_STATE
        try:
            await self._sync_remote_session_detail(session, recent_limit=80)
        except Exception:
            pass
        self._set_status(SessionCancelService.requested_status_text(session.title))
        self._render_all()
        return True

    async def _run_remote_chat_turn(
        self,
        text: str,
        *,
        session: TuiSession | None = None,
    ) -> None:
        session = session or self.current_session
        projection = session.projection
        view = session.view
        if not self._runs_via_gateway(session):
            await self._run_chat_turn(text, session=session)
            return
        if projection.busy:
            self._set_status(f"{session.title} is busy. Please wait for the remote turn to finish.")
            self._render_all()
            return

        task = self._create_task(session, text)
        self._update_task(task, status="queued", note="accepted")
        self._append_session_message(
            session,
            "user",
            text,
            metadata={
                "surface": "tui",
                "threads_visible": True,
            },
        )
        self._start_turn_activity(session, detail="starting run")
        self._turn_state.begin_remote_turn(session, task_id=task.task_id)
        self._set_status(f"Submitting remote turn for {session.title}...")
        self._persist_session_state()
        self._render_all()

        try:
            self._update_task(task, status="running", note="submitted to gateway")
            stream_result = await self._remote_turn_stream.consume(
                chat_client=self.remote_chat_service,
                session=session,
                message=text,
                workspace_dir=self._effective_remote_workspace_dir(),
                surface="tui",
            )
            response = stream_result.response
            stop_reason = stream_result.stop_reason
            reply_text = stream_result.reply_text
            assistant_message_index = stream_result.assistant_message_index

            outcome = self._turn_outcomes.resolve_remote_completion(
                session_title=session.title,
                stop_reason=stop_reason,
                reply_text=reply_text,
            )
            self._update_task(
                task,
                status=outcome.task_status,
                stop_reason=outcome.task_stop_reason,
                note=outcome.task_note,
            )
            self._finish_turn_activity(session, detail=outcome.activity_detail)
            if outcome.kind == "success":
                if isinstance(assistant_message_index, int) and 0 <= assistant_message_index < len(view.messages):
                    metadata = dict(view.messages[assistant_message_index].metadata)
                    metadata["streaming"] = False
                    self._update_session_message_content(
                        session,
                        assistant_message_index,
                        view.messages[assistant_message_index].content,
                        metadata=metadata,
                        persist=False,
                    )
                    await self._flush_stream_render()
                elif reply_text:
                    await self._stream_assistant_reply(session, reply_text)
            self._turn_state.finish_remote_turn(session)
            if isinstance(response, dict):
                projection.supplemental.remote_message_count = max(
                    int(
                        response.get(
                            "message_count",
                            projection.supplemental.remote_message_count,
                        )
                        or 0
                    ),
                    projection.supplemental.remote_message_count,
                )
                projection.token_usage = _safe_nonnegative_int(response.get("token_usage"), default=projection.token_usage)
            await self._sync_remote_session_detail(session, recent_limit=80)
            if outcome.system_message:
                self._append_session_message(session, "system", outcome.system_message)
            self._set_status(outcome.status_text)
        except Exception as exc:
            detail = RemoteStreamErrorService.exception_detail(exc)
            outcome = self._turn_outcomes.resolve_remote_exception(session_title=session.title, detail=detail)
            self._turn_state.finish_remote_turn(session)
            self._update_task(
                task,
                status=outcome.task_status,
                stop_reason=outcome.task_stop_reason,
                note=outcome.task_note,
            )
            self._finish_turn_activity(session, detail=outcome.activity_detail)
            if outcome.system_message:
                self._append_session_message(session, "system", outcome.system_message)
            self._set_status(outcome.status_text)
        finally:
            self._render_all()

    def _build_turn_hooks(self, session: TuiSession) -> PlannerExecutorHooks:
        async def _on_step_plan(step_plan: Any) -> None:
            step = getattr(step_plan, "step", "?")
            planned_tool_calls = getattr(step_plan, "planned_tool_calls", None)
            tool_count = len(planned_tool_calls) if isinstance(planned_tool_calls, list) else 0
            if tool_count > 0:
                detail = f"step {step}: planned {tool_count} tool call(s)"
            else:
                detail = f"step {step}: preparing final response"
            self._append_activity_line(session, label="thinking", detail=detail)
            self._update_running_state(session, detail)

        async def _on_tool_call_start(step: int, tool_call: Any) -> None:
            tool_name = self._tool_name_from_hook(tool_call)
            tool_preview = self._tool_activity_preview(tool_call)
            activity_detail = "running"
            self._append_activity_line(
                session,
                label=tool_name,
                detail=activity_detail,
                activity_id=self._tool_call_key(step, tool_call),
                preview=tool_preview,
                state="running",
            )
            self._update_running_state(session, f"step {step}: running {tool_name}")

        async def _on_tool_call_result(step: int, tool_call: Any, result: Any) -> None:
            tool_name = self._tool_name_from_hook(tool_call)
            outcome = "ok" if bool(getattr(result, "success", False)) else "failed"
            error_text = _truncate_inline(getattr(result, "error", ""), limit=72)
            activity_detail = outcome
            output_text = ""
            if self._activity_has_output(tool_name, result):
                output_text = self._tool_result_output_text(result)
            elif outcome == "failed" and error_text:
                output_text = error_text
            self._append_activity_line(
                session,
                label=tool_name,
                detail=activity_detail,
                activity_id=self._tool_call_key(step, tool_call),
                output_text=output_text,
                state=outcome,
            )
            self._update_running_state(session, f"step {step}: {tool_name} {outcome}")

        return PlannerExecutorHooks(
            on_step_plan=_on_step_plan,
            on_tool_call_start=_on_tool_call_start,
            on_tool_call_result=_on_tool_call_result,
        )

    async def _run_chat_turn(
        self,
        text: str,
        *,
        session: TuiSession | None = None,
        existing_task: TaskEntry | None = None,
        append_user_message: bool = True,
        resuming: bool = False,
        restore_agent_messages: Sequence[dict[str, Any]] | None = None,
    ) -> None:
        session = session or self.current_session
        projection = session.projection
        runtime = session.runtime
        view = session.view
        if projection.busy:
            self._set_status(f"{session.title} is busy. Please wait for completion.")
            self._render_all()
            return

        if not resuming:
            self._apply_session_lifecycle(session)

        task = existing_task or self._create_task(session, text)
        if existing_task is None:
            self._set_pending_resume(
                session,
                task_id=task.task_id,
                agent_messages=self._snapshot_resume_agent_messages(session),
            )
            self._update_task(task, status="queued", note="accepted")
        else:
            self._set_pending_resume(
                session,
                task_id=task.task_id,
                agent_messages=restore_agent_messages or runtime.pending_resume_agent_messages or runtime.restored_agent_messages,
            )
            self._update_task(
                task,
                status="resume_pending" if resuming else (task.status or "queued"),
                stop_reason="restart" if resuming else task.stop_reason,
                note=_append_task_note(task.note, "resuming after restart") if resuming else task.note,
            )

        if append_user_message:
            self._append_session_message(session, "user", text)
        elif resuming:
            self._append_session_message(
                session,
                "system",
                f"Resuming {task.task_id} after restart.",
                metadata={"threads_visible": False},
            )
            recovery_notes: list[str] = []
            supplemental = projection.supplemental
            if _safe_text(supplemental.recovery_running_state):
                recovery_notes.append(f"Last state before restart: {supplemental.recovery_running_state}")
            if supplemental.recovery_pending_approvals:
                approval_labels = ", ".join(
                    _safe_text(item.get("tool_name")) or _safe_text(item.get("token")) or "tool"
                    for item in supplemental.recovery_pending_approvals
                    if isinstance(item, dict)
                )
                if approval_labels:
                    recovery_notes.append(f"Pending approval before restart: {approval_labels}")
            if recovery_notes:
                self._append_session_message(
                    session,
                    "system",
                    "\n".join(recovery_notes),
                    metadata={"threads_visible": False},
                )

        self._start_turn_activity(session, detail="resuming after restart" if resuming else "starting run")
        self._turn_state.begin_local_turn(session, task_id=task.task_id, resuming=resuming)
        self._set_status(f"{'Resuming' if resuming else 'Running'} turn for {session.title}...")
        self._persist_session_state()
        self._render_all()

        clear_pending_resume = False
        submission_started = False
        try:
            if restore_agent_messages:
                runtime.restored_agent_messages = _copy_serialized_messages(
                    [item for item in restore_agent_messages if isinstance(item, dict)]
                )
                if runtime.agent is not None:
                    self._restore_agent_messages_payload(runtime.restored_agent_messages, runtime.agent)

            agent = await self._ensure_agent(session)
            if agent is None:
                self._finish_turn_activity(session, detail="agent unavailable")
                if resuming:
                    self._update_task(
                        task,
                        status="resume_pending",
                        stop_reason="restart",
                        note=_append_task_note(task.note, "agent unavailable"),
                    )
                    self._append_session_message(
                        session,
                        "system",
                        "Resume paused: agent is not available. Configure API keys (env or .env.local) and retry.",
                        metadata={"threads_visible": False},
                    )
                    self._set_status(f"Resume paused for {session.title}: agent unavailable.")
                else:
                    self._append_session_message(
                        session,
                        "system",
                        "Agent is not available. Configure API keys (env or .env.local) and retry.",
                    )
                return

            loop = await self._ensure_submission_loop(session)
            event_start_index = len(runtime.loop_bus.events) if runtime.loop_bus is not None else 0
            policy_overrides = {
                "max_steps": getattr(agent, "max_steps", 50),
                "max_tool_calls_per_step": getattr(agent, "max_tool_calls_per_step", None),
            }
            metadata = {"surface": "tui", "resume": resuming}
            metadata.update(self._context_policy_metadata(session))
            submission_id = await loop.submit_user_input(
                text,
                policy_overrides=policy_overrides,
                metadata=metadata,
                start_new_run=True,
            )
            live_stream_state = {
                "assistant_message_index": None,
                "emitted_live_reply": False,
            }
            submission_started = True
            self._update_task(
                task,
                status="resuming" if resuming else "running",
                submission_id=submission_id,
                note="resubmitted after restart" if resuming else "submitted",
            )
            payload = await self._wait_for_submission_payload(
                session=session,
                submission_id=submission_id,
                event_start_index=event_start_index,
                stream_state=live_stream_state,
            )

            state = _safe_text(payload.get("state")).lower()
            stop_reason = _safe_text(payload.get("stop_reason")).lower()
            message = _preserve_message_text(payload.get("message"))
            error = _preserve_message_text(payload.get("error"))
            prepared_context = self._record_local_prepared_context_projection(
                session,
                prepared_context=payload.get("prepared_context"),
                prepared_context_present="prepared_context" in payload,
                prepared_context_diagnostics=payload.get("prepared_context_diagnostics"),
                prepared_context_diagnostics_present="prepared_context_diagnostics" in payload,
            )
            self._append_prepared_context_feedback(
                session,
                prepared_context,
                persist=False,
            )

            outcome = self._turn_outcomes.resolve_local_completion(
                session_title=session.title,
                state=state,
                stop_reason=stop_reason,
                message=message,
                error=error,
            )
            self._update_task(
                task,
                status=outcome.task_status,
                stop_reason=outcome.task_stop_reason,
                note=outcome.task_note,
            )
            clear_pending_resume = True
            self._finish_turn_activity(session, detail=outcome.activity_detail)
            if outcome.kind == "success":
                assistant_message_index = live_stream_state.get("assistant_message_index")
                if bool(live_stream_state.get("emitted_live_reply")) and isinstance(assistant_message_index, int):
                    if 0 <= assistant_message_index < len(view.messages):
                        current_content = _preserve_message_text(view.messages[assistant_message_index].content)
                        final_content = message or current_content
                        metadata = dict(view.messages[assistant_message_index].metadata)
                        metadata["streaming"] = False
                        self._update_session_message_content(
                            session,
                            assistant_message_index,
                            final_content,
                            metadata=metadata,
                            persist=False,
                        )
                        await self._flush_stream_render()
                    elif message:
                        await self._stream_assistant_reply(session, message)
                else:
                    await self._stream_assistant_reply(session, message)
            else:
                if outcome.system_message:
                    self._append_session_message(session, "system", outcome.system_message)
            self._set_status(outcome.status_text)
        except Exception as exc:
            if resuming and not submission_started:
                self._update_task(
                    task,
                    status="resume_pending",
                    stop_reason="restart",
                    note=_append_task_note(task.note, str(exc)),
                )
                self._finish_turn_activity(session, detail="resume paused")
                self._append_session_message(
                    session,
                    "system",
                    f"Resume paused: {exc}",
                    metadata={"threads_visible": False},
                )
                self._set_status(f"Resume paused for {session.title}: {exc}")
            else:
                outcome = self._turn_outcomes.resolve_local_exception(detail=str(exc))
                self._update_task(
                    task,
                    status=outcome.task_status,
                    stop_reason=outcome.task_stop_reason,
                    note=outcome.task_note,
                )
                clear_pending_resume = True
                self._finish_turn_activity(session, detail=outcome.activity_detail)
                if outcome.system_message:
                    self._append_session_message(session, "system", outcome.system_message)
                self._set_status(outcome.status_text)
        finally:
            if clear_pending_resume:
                self._clear_pending_resume(session, task_id=task.task_id)
            else:
                runtime.pending_resume_started = False
            self._turn_state.finish_local_turn(session)
            await self._apply_pending_session_model_selection(session)
            await self._apply_pending_session_skill_reload(session)
            self._persist_session_state()
            self._render_all()

    async def _ensure_agent(self, session: TuiSession) -> Agent | None:
        operator = session.operator
        runtime = session.runtime
        if operator.pending_skill_reload and self._has_local_runtime_state(session):
            applied = await self._apply_pending_session_skill_reload(session)
            if applied and runtime.agent is not None:
                return runtime.agent
        if runtime.agent is not None:
            return runtime.agent
        try:
            agent = await self._build_session_agent(session)
            if operator.pending_skill_reload:
                self._clear_session_skill_reload_pending(session)
                self._persist_session_state()
            self._set_status(f"Agent ready on {agent.llm.model}.")
            return runtime.agent
        except Exception as exc:
            self._append_message("system", f"Agent initialization failed: {exc}")
            self._set_status(f"Agent init failed: {exc}")
            return None

    @staticmethod
    def _reset_agent_messages(agent: Agent | None) -> None:
        if agent is None:
            return
        messages = getattr(agent, "messages", None)
        if isinstance(messages, list) and messages:
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

    def _clear_local_runtime_task_memory(self, session_id: str) -> bool:
        try:
            return WorkspaceMemoriaRuntime(self.workspace).clear_session_namespace(session_id)
        except Exception:
            return False

    def _reset_session_runtime_state(self, session: TuiSession) -> None:
        runtime = session.runtime
        projection = session.projection
        view = session.view
        self._reset_agent_messages(runtime.agent)
        if self._has_local_runtime_state(session):
            self._clear_local_runtime_task_memory(session.session_id)
        projection.token_usage = 0
        if runtime.agent is not None:
            projection.token_limit = _safe_nonnegative_int(getattr(runtime.agent, "token_limit", projection.token_limit))
        runtime.restored_agent_messages = []
        runtime.pending_resume_task_id = None
        runtime.pending_resume_agent_messages = []
        runtime.pending_resume_started = False
        projection.supplemental.recovery_running_state = ""
        projection.supplemental.recovery_pending_approvals = []
        projection.pending_approvals = []
        runtime.active_task_id = None
        runtime.cancel_event = None
        projection.busy = False
        projection.running_state = ""
        view.active_activity_message_index = None
        view.chat_scroll_line = 0
        view.chat_follow_output = True
        projection.last_prepared_context = {}
        projection.prepared_context_diagnostics = {}
        self._bump_chat_render_revision(session)
        self._refresh_local_memory_diagnostics(session)

    @staticmethod
    def _restore_agent_messages_payload(
        raw_messages: Sequence[dict[str, Any]],
        agent: Agent,
    ) -> None:
        raw_messages = list(raw_messages or [])
        if not raw_messages:
            return

        restored: list[Message] = []
        for raw in raw_messages:
            if not isinstance(raw, dict):
                continue
            try:
                restored.append(Message.model_validate(raw))
            except Exception:
                continue
        if not restored:
            return

        if restored[0].role != "system":
            base_messages = getattr(agent, "messages", None)
            if isinstance(base_messages, list) and base_messages:
                system_message = base_messages[0]
                try:
                    restored.insert(0, Message.model_validate(_serialize_agent_message(system_message)))
                except Exception:
                    pass
        agent.messages = restored

    @classmethod
    def _restore_agent_messages(cls, session: TuiSession, agent: Agent) -> None:
        cls._restore_agent_messages_payload(session.runtime.restored_agent_messages, agent)

    def _apply_session_lifecycle(self, session: TuiSession) -> None:
        decision = self.session_lifecycle_runtime.ensure_active(
            session.session_id,
            on_reset=lambda: self._reset_session_runtime_state(session),
        )
        if not decision.reset:
            return
        reason = _safe_text(decision.reason) or "policy"
        notice = f"Session lifecycle reset applied ({reason})."
        self._append_message("system", notice)
        self._set_status(notice)

    @staticmethod
    def _command_palette_examples() -> str:
        return build_command_example_text(
            "tui",
            include_header=True,
            leading_slash=True,
            max_examples=20,
        )

    @staticmethod
    def _command_help_text() -> str:
        return build_command_help_text(
            "tui",
            include_header=True,
            leading_slash=True,
        )

    @staticmethod
    def _suggest(value: str, candidates: Sequence[str]) -> str:
        options = [item for item in candidates if item]
        matches = difflib.get_close_matches(value, options, n=3, cutoff=0.45)
        if not matches:
            return ""
        return f" Did you mean: {', '.join(matches)}?"

    def _command_tokens(self) -> list[str]:
        tokens = set(
            command_completion_tokens(
                "tui",
                include_leading_slash=True,
                include_plain=True,
            )
        )
        tokens.update({"drop-memories", "/drop-memories", "quit", "/quit"})
        for session in self.sessions:
            tokens.add(session.session_id)
            for approval in session.projection.pending_approvals:
                approval_token = self._pending_approval_token(approval)
                if approval_token:
                    tokens.add(approval_token)
            for task in session.view.tasks:
                task_id = _safe_text(task.task_id)
                if task_id:
                    tokens.add(task_id)
        for provider in self.providers:
            provider_id = _safe_text(provider.get("provider_id"))
            if provider_id:
                tokens.add(provider_id)
            raw_models = provider.get("models")
            if isinstance(raw_models, list):
                for model in raw_models:
                    if not isinstance(model, dict):
                        continue
                    model_id = _safe_text(model.get("model_id"))
                    if model_id:
                        tokens.add(model_id)
        return sorted(tokens)

    def _refresh_command_completer(self) -> None:
        self.input_box.completer = _SlashCommandCompleter(self._command_tokens)
        self.command_box.completer = WordCompleter(
            self._command_tokens(),
            ignore_case=True,
            sentence=True,
            match_middle=True,
        )

    def _command_completion_menu_visible(self) -> bool:
        if self.command_palette_open and self.application.layout.has_focus(self.command_box):
            return self.command_box.buffer.complete_state is not None
        if self.application.layout.has_focus(self.input_box):
            return self.input_box.buffer.complete_state is not None
        return False

    def _render_session_summary(self) -> str:
        lines = []
        for index, session in enumerate(self.sessions):
            marker = ">" if index == self.session_index else " "
            visible_count = self._session_message_count(session)
            source_tag = (
                _safe_text(session.projection.channel_type) or _safe_text(session.projection.origin_surface) or "tui"
            ).upper()
            lines.append(
                f"{marker} #{index + 1} {session.title} ({session.session_id}) [{source_tag}] - {visible_count} msg"
            )
        return "\n".join(lines) if lines else "  (none)"

    def _render_model_summary(self) -> str:
        visible = self._visible_provider_models()
        if not visible:
            if self.model_filter:
                return f"  (no providers match filter: {self.model_filter})"
            return "  (none)"
        lines: list[str] = []
        for _, provider, models in visible:
            lines.append(
                f"[{provider.get('source')}] {provider.get('provider_id')} -> default={provider.get('default_model_id')}"
            )
            lines.extend([f"  - {model.get('model_id')}" for _, model in models])
        return "\n".join(lines)

    async def _dispatch_remote_control_command(
        self,
        *,
        session: TuiSession,
        command_text: str,
        action: str,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[Any, bool] | None:
        try:
            response = await self.remote_session_service.control_session(
                session.session_id,
                MainAgentSessionControlRequest(
                    action=action,
                    reason=reason,
                    **self._remote_request_binding_kwargs(session),
                ),
            )
        except Exception as exc:
            detail = extract_gateway_error_info(exc).detail
            self._append_command_feedback(
                command_text,
                summary=SessionControlErrorService.remote_summary(detail),
                details=detail,
                level="error",
                metadata=metadata,
            )
            self._set_status(SessionControlErrorService.remote_status_text(detail))
            self._render_all()
            return None

        synced = False
        try:
            await self._sync_remote_session_detail(session, recent_limit=80)
            synced = True
        except Exception:
            pass
        return response, synced

    async def _respond_to_pending_approval(
        self,
        *,
        session: TuiSession,
        approved: bool,
        token: str | None = None,
    ) -> bool:
        return await self._approval_commands.respond(
            session=session,
            approved=approved,
            token=token,
        )

    async def _run_context_control_command(
        self,
        *,
        session: TuiSession,
        action: str,
        reason: str | None = None,
    ) -> bool:
        normalized_action = _safe_text(action).lower().replace("-", "_")
        command_text = normalized_action if not reason else f"{normalized_action} {reason}"
        projection = session.projection
        runtime = session.runtime

        if self._runs_via_gateway(session):
            remote_result = await self._dispatch_remote_control_command(
                session=session,
                command_text=command_text,
                action=normalized_action,
                reason=reason,
            )
            if remote_result is None:
                return False
            response, _ = remote_result

            applied = bool(response.applied)
            if normalized_action == "compact":
                status_message = (
                    f"Compacted shared session {session.title}."
                    if applied
                    else f"{session.title} is already compact."
                )
            else:
                status_message = (
                    f"Dropped older memories for {session.title}."
                    if applied
                    else f"No older memories to drop for {session.title}."
                )
            self._set_status(status_message)
            self._render_all()
            return True

        if projection.busy:
            message = f"{session.title} is busy. Wait for the current turn to finish first."
            self._append_command_feedback(
                normalized_action,
                summary="session busy",
                details=message,
                level="error",
            )
            self._set_status(message)
            self._render_all()
            return False

        agent = await self._ensure_agent(session)
        if agent is None:
            self._append_command_feedback(
                normalized_action,
                summary="agent unavailable",
                details="Agent is not available. Configure API keys (env or .env.local) and retry.",
                level="error",
            )
            self._set_status("Agent is not available.")
            self._render_all()
            return False

        loop = await self._ensure_submission_loop(session)
        bus = runtime.loop_bus
        if bus is None:
            message = "Missing submission loop bus."
            self._append_command_feedback(
                normalized_action,
                summary="runtime unavailable",
                details=message,
                level="error",
            )
            self._set_status(message)
            self._render_all()
            return False

        event_start_index = len(bus.events)
        if normalized_action == "compact":
            event_id = await loop.submit_compact(reason=reason)
            target_event_type = "loop.compact"
            running_label = "compacting context"
        elif normalized_action == "drop_memories":
            event_id = await loop.submit_drop_memories(reason=reason)
            target_event_type = "loop.drop_memories"
            running_label = "dropping older memories"
        else:
            raise ValueError(f"Unknown context control action: {action}")

        self._set_status(f"{session.title}: {running_label}...")
        try:
            payload = await wait_for_loop_event(
                bus=bus,
                event_type=target_event_type,
                event_start_index=event_start_index,
                event_id=event_id,
            )
        except Exception as exc:
            message = f"{normalized_action} failed: {exc}"
            self._append_command_feedback(
                command_text,
                summary="command failed",
                details=message,
                level="error",
            )
            self._set_status(message)
            self._render_all()
            return False

        error = _safe_text(payload.get("error"))
        if error:
            self._append_command_feedback(
                command_text,
                summary="command failed",
                details=error,
                level="error",
            )
            self._set_status(f"{normalized_action} failed for {session.title}.")
            self._render_all()
            return False

        if payload.get("unsupported"):
            message = f"{normalized_action} is not supported by the active agent."
            self._append_command_feedback(
                command_text,
                summary="unsupported",
                details=message,
                level="error",
            )
            self._set_status(message)
            self._render_all()
            return False

        self._capture_session_agent_snapshot(session)
        self._persist_session_state()

        control_result = SessionContextControlResultService.normalize_result(
            action=normalized_action,
            payload=payload,
            reason=reason,
        )
        self._append_command_feedback(
            command_text,
            summary=control_result.summary,
            details=control_result.details,
        )
        self._set_status(
            SessionContextControlResultService.tui_status_text(
                result=control_result,
                session_title=session.title,
            )
        )
        self._render_all()
        return True

    def _session_usage_result(
        self,
        *,
        command: str,
        action: str | None,
        status_text: str,
    ) -> CommandExecutionResult:
        return CommandExecutionResult(
            command=command,
            summary="usage",
            details=build_command_usage_text("tui", "session", action=action),
            status_text=status_text,
            kind="usage",
        )

    def _session_unknown_action_result(
        self,
        *,
        command: str,
        action: str,
        status_text: str,
    ) -> CommandExecutionResult:
        return CommandExecutionResult(
            command=command,
            summary="unknown action",
            details=build_unknown_action_text(
                "tui",
                "session",
                action,
                fallback=build_command_usage_text("tui", "session"),
            ),
            status_text=status_text,
            kind="error",
        )

    def _resolve_session_target(
        self,
        *,
        command: str,
        selector: str | None,
        activate: bool = False,
    ) -> tuple[int, TuiSession] | CommandExecutionResult:
        if not selector:
            return self.session_index, self.current_session
        target_index = self._find_session_index(selector)
        if target_index is None:
            message = f"Session not found: {selector}"
            return CommandExecutionResult(
                command=command,
                summary="session not found",
                details=message,
                status_text=message,
                kind="error",
            )
        if activate:
            self.session_index = target_index
        return target_index, self.sessions[target_index]

    def _resolve_session_command_plan(
        self,
        args: Sequence[str],
    ) -> SessionCommandPlan | CommandExecutionResult:
        normalized_args = list(args or [])
        action = normalized_args[0].lower() if normalized_args else "list"
        if action.isdigit():
            return SessionCommandPlan(command="session", action="select", selector=action)
        if action == "new":
            return SessionCommandPlan(command="session new", action="new")
        if action == "next":
            return SessionCommandPlan(command="session next", action="cursor", cursor_delta=1)
        if action == "prev":
            return SessionCommandPlan(command="session prev", action="cursor", cursor_delta=-1)
        if action == "list":
            return SessionCommandPlan(command="session list", action="list")
        if action == "share":
            return SessionCommandPlan(
                command="session share",
                action="share",
                selector=normalized_args[1] if len(normalized_args) >= 2 else None,
            )
        if action == "unshare":
            return SessionCommandPlan(
                command="session unshare",
                action="unshare",
                selector=normalized_args[1] if len(normalized_args) >= 2 else None,
            )
        if action == "rename":
            if len(normalized_args) < 2:
                return self._session_usage_result(
                    command="session rename",
                    action="rename",
                    status_text="Session rename requires a title.",
                )
            selector: str | None = None
            title_parts = normalized_args[1:]
            if len(normalized_args) >= 3 and self._find_session_index(normalized_args[1]) is not None:
                selector = normalized_args[1]
                title_parts = normalized_args[2:]
            title = " ".join(title_parts).strip()
            if not title:
                return self._session_usage_result(
                    command="session rename",
                    action="rename",
                    status_text="Session rename requires a title.",
                )
            return SessionCommandPlan(
                command="session rename",
                action="rename",
                selector=selector,
                title=title,
            )
        if action in {"delete", "remove", "rm"}:
            return SessionCommandPlan(
                command="session delete",
                action="delete",
                selector=normalized_args[1] if len(normalized_args) >= 2 else None,
            )
        return self._session_unknown_action_result(
            command="session",
            action=action,
            status_text="Unknown session action.",
        )

    async def _execute_session_share_command(self, plan: SessionCommandPlan) -> None:
        target = self._resolve_session_target(
            command=plan.command,
            selector=plan.selector,
            activate=bool(plan.selector),
        )
        if isinstance(target, CommandExecutionResult):
            self._append_command_feedback(
                target.command,
                summary=target.summary,
                details=target.details,
                level="error",
            )
            self._set_status(target.status_text)
            return

        _, target_session = target
        shared = plan.action == "share"
        try:
            response = await self.remote_session_service.set_session_shared(
                target_session.session_id,
                MainAgentSessionShareRequest(shared=shared),
            )
            target_session.projection.shared = bool(response.shared if response.shared is not None else shared)
            await self._sync_remote_session_detail(target_session, recent_limit=80)
            feedback = SessionFeedbackService.mutation_feedback(
                status=response.status,
                title=target_session.title,
                shared=response.shared,
            )
            self._set_status(feedback.status_text)
        except Exception as exc:
            detail = extract_gateway_error_info(exc).detail
            message = f"Session {plan.action} failed: {detail}"
            self._append_command_feedback(
                plan.command,
                summary=f"{plan.action} failed",
                details=message,
                level="error",
            )
            self._set_status(message)

    async def _execute_session_rename_command(self, plan: SessionCommandPlan) -> None:
        target = self._resolve_session_target(
            command=plan.command,
            selector=plan.selector,
        )
        if isinstance(target, CommandExecutionResult):
            self._append_command_feedback(
                target.command,
                summary=target.summary,
                details=target.details,
                level="error",
            )
            self._set_status(target.status_text)
            return

        _, target_session = target
        title = plan.title or ""
        try:
            response = await self.remote_session_service.rename_session(
                target_session.session_id,
                MainAgentSessionRenameRequest(title=title),
            )
            renamed_title = _safe_text(response.title) or title
            self._rename_session(title=renamed_title, session_id=target_session.session_id)
            feedback = SessionFeedbackService.mutation_feedback(
                status=response.status,
                title=renamed_title,
                shared=response.shared,
            )
            self._set_status(feedback.status_text)
        except Exception as exc:
            detail = extract_gateway_error_info(exc).detail
            message = f"Session rename failed: {detail}"
            self._append_command_feedback(
                plan.command,
                summary="rename failed",
                details=message,
                level="error",
            )
            self._set_status(message)

    async def _execute_session_delete_command(self, plan: SessionCommandPlan) -> None:
        target_session = self.current_session
        if plan.selector:
            target_index = self._find_session_index(plan.selector)
            if target_index is None:
                target_session = None
            else:
                target_session = self.sessions[target_index]

        if target_session is not None:
            try:
                response = await self.remote_session_service.delete_session(target_session.session_id)
            except Exception as exc:
                detail = extract_gateway_error_info(exc).detail
                message = f"Runtime session delete failed: {detail}"
                self._append_command_feedback(
                    plan.command,
                    summary="delete failed",
                    details=message,
                    level="error",
                )
                self._set_status(message)
                return
            delete_feedback = SessionFeedbackService.mutation_feedback(
                status=response.status,
                title=target_session.title,
            )
        else:
            delete_feedback = None

        deleted = self._delete_session(session_id=plan.selector)
        if deleted is None:
            message = f"Session not found: {plan.selector}"
            self._append_command_feedback(
                plan.command,
                summary="session not found",
                details=message,
                level="error",
            )
            self._set_status(message)
            return

        if not self.sessions:
            await self._ensure_remote_default_session()
        self._set_status(
            (delete_feedback.status_text if delete_feedback is not None else None)
            or SessionFeedbackService.mutation_feedback(status="deleted", title=deleted.title).status_text
        )

    async def _handle_session_command(self, args: list[str]) -> None:
        plan = self._resolve_session_command_plan(args)
        if isinstance(plan, CommandExecutionResult):
            self._append_command_feedback(
                plan.command,
                summary=plan.summary,
                details=plan.details,
                level="error" if plan.kind in {"usage", "error"} else "info",
            )
            self._set_status(plan.status_text)
            self._render_all()
            return

        if plan.action == "select":
            target_index = self._find_session_index_by_selector(plan.selector or "")
            if target_index is None:
                message = f"Session not found: #{plan.selector}"
                self._append_command_feedback(
                    plan.command,
                    summary="session not found",
                    details=message,
                    level="error",
                )
                self._set_status(message)
            else:
                self._activate_session_index(target_index)
                return
        elif plan.action == "new":
            try:
                created = await self._create_runtime_session()
            except Exception as exc:
                detail = extract_gateway_error_info(exc).detail
                message = f"Runtime session creation failed: {detail}"
                self._append_command_feedback(
                    plan.command,
                    summary="create failed",
                    details=message,
                    level="error",
                )
                self._set_status(message)
            else:
                if created is None:
                    self._set_status("Runtime session creation failed.")
                else:
                    self._set_status(
                        SessionFeedbackService.creation_feedback(
                            title=created.title,
                        ).status_text
                    )
        elif plan.action == "cursor":
            self._switch_session(plan.cursor_delta)
        elif plan.action == "list":
            self._append_command_feedback(
                plan.command,
                summary=f"{len(self.sessions)} session(s)",
                details="Sessions:\n" + self._render_session_summary(),
            )
            self._set_status("Listed sessions.")
        elif plan.action in {"share", "unshare"}:
            await self._execute_session_share_command(plan)
        elif plan.action == "rename":
            await self._execute_session_rename_command(plan)
        else:
            await self._execute_session_delete_command(plan)
        self._render_all()

    def _resolve_context_command_plan(self, args: Sequence[str]) -> ContextCommandPlan:
        return prepare_context_command_plan(args=args, default_action="show")

    def _execute_context_result(
        self,
        result: CommandExecutionResult,
    ) -> None:
        self._append_command_feedback(
            result.command,
            summary=result.summary,
            details=result.details,
            level="error" if result.kind in {"usage", "error"} else "info",
            metadata={"threads_visible": False},
        )
        self._set_status(result.status_text)

    async def _run_context_command_result(
        self,
        *,
        session: TuiSession,
        action: str,
        args: Sequence[str],
    ) -> CommandExecutionResult:
        projection = session.projection
        return self.local_command_service.execute_context(
            surface="tui",
            action=action,
            args=list(args),
            current_policy=projection.context_policy,
            prepared_context=projection.last_prepared_context,
            prepared_context_diagnostics=projection.prepared_context_diagnostics,
            session_label=session.title,
        )

    async def _handle_context_command(self, args: list[str]) -> None:
        session = self.current_session
        await self._context_commands.handle(session, args)

    async def _handle_memory_command(self, args: list[str]) -> None:
        session = self.current_session
        await self._memory_commands.handle(session, args)

    async def _handle_kb_command(self, args: list[str]) -> None:
        session = self.current_session
        await self._kb_commands.handle(session, args)

    def _resolve_kb_command_plan(
        self,
        args: Sequence[str],
    ) -> KbCommandPlan | CommandExecutionResult:
        action = args[0].lower() if args else "status"
        if action not in {"status", "on", "off"}:
            return CommandExecutionResult(
                command="kb",
                summary="unknown action",
                details=build_unknown_action_text(
                    "tui",
                    "kb",
                    action,
                    fallback=build_command_usage_text("tui", "kb"),
                ),
                status_text="Unknown kb action.",
                kind="error",
            )
        return KbCommandPlan(command=f"kb {action}", action=action)

    async def _execute_remote_kb_command(self, session: TuiSession, plan: KbCommandPlan) -> None:
        projection = session.projection
        try:
            response = await self.remote_session_service.control_session(
                session.session_id,
                MainAgentSessionControlRequest(
                    action=f"kb_{plan.action}",
                    **self._remote_request_binding_kwargs(session),
                ),
            )
        except Exception as exc:
            detail = extract_gateway_error_info(exc).detail
            self._append_command_feedback(
                plan.command,
                summary="command failed",
                details=f"Remote KB {plan.action} failed: {detail}",
                level="error",
            )
            self._set_status(f"Remote KB {plan.action} failed.")
            return

        if response.knowledge_base_enabled is not None:
            projection.knowledge_base_enabled = bool(response.knowledge_base_enabled)
        try:
            await self._sync_remote_session_detail(session, recent_limit=80)
        except Exception:
            pass
        enabled = self._session_knowledge_base_enabled(session)
        self._set_status(
            f"Knowledge base {'enabled' if enabled else 'disabled'} for shared session {session.title}."
        )

    async def _handle_mcp_command(self, args: list[str]) -> None:
        session = self.current_session
        await self._mcp_commands.handle(session, args)

    def _resolve_mcp_command_plan(
        self,
        args: Sequence[str],
    ) -> McpCommandPlan | CommandExecutionResult:
        normalized_args = list(args or [])
        action = normalized_args[0].lower() if normalized_args else "status"
        if action not in {"status", "list", "reload"}:
            return CommandExecutionResult(
                command="mcp",
                summary="unknown action",
                details=build_unknown_action_text(
                    "tui",
                    "mcp",
                    action,
                    fallback=build_command_usage_text("tui", "mcp"),
                ),
                status_text="Unknown mcp action.",
                kind="error",
            )
        if len(normalized_args) > 1:
            return CommandExecutionResult(
                command=f"mcp {action}",
                summary="usage",
                details=build_command_usage_text("tui", "mcp", action=action),
                status_text=f"MCP {action} usage displayed.",
                kind="usage",
            )
        return McpCommandPlan(command=f"mcp {action}", action=action)

    @staticmethod
    def _mcp_remote_status_text(action: str) -> str:
        return {
            "status": "Shared MCP status shown.",
            "list": "Shared MCP server list shown.",
            "reload": "Shared MCP bindings reloaded.",
        }.get(action, "Shared MCP status shown.")

    async def _handle_sandbox_command(self, args: list[str]) -> None:
        action = args[0].lower() if args else "status"
        session = self.current_session
        diagnostics = self._session_sandbox_diagnostics(
            session,
            refresh_local=not self._runs_via_gateway(session),
        )
        result = self.local_command_service.execute_sandbox_status(
            surface="tui",
            action=action,
            args=args,
            diagnostics=diagnostics,
        )
        self._append_command_feedback(
            result.command,
            summary=result.summary,
            details=result.details,
            level="error" if result.kind in {"usage", "error"} else "info",
            metadata={"threads_visible": False},
        )
        self._set_status(result.status_text)
        self._render_all()

    async def _handle_skill_command(self, invocation_or_args: Any) -> None:
        session = self.current_session
        await self._skill_commands.handle(session, invocation_or_args)

    def _resolve_model_command_plan(
        self,
        args: Sequence[str],
    ) -> ModelCommandPlan | CommandExecutionResult:
        return prepare_model_command_plan(
            surface="tui",
            args=args,
            providers=self.providers,
            default_action="list",
            allow_show=False,
            extended_actions=True,
            current_filter=self.model_filter,
            strict_basic_arity=False,
        )

    def _execute_model_limit_command_plan(self, plan: ModelCommandPlan) -> None:
        if plan.action == "limit_list":
            self._append_command_feedback(
                plan.command,
                summary="learned token limits",
                details=self._render_model_limit_list(),
                metadata={"threads_visible": False},
            )
            self._set_status("Listed learned token limits.")
            return

        if plan.action == "limit_show":
            target, error = self._resolve_model_limit_target(list(plan.limit_args))
            if target is None:
                self._append_command_feedback(
                    plan.command,
                    summary="usage",
                    details=error or build_command_usage_text("tui", "model", action="limit"),
                    level="error",
                )
                self._set_status("Model limit show usage displayed.")
                return
            provider, model = target
            self._append_command_feedback(
                plan.command,
                summary=f"limit for {_safe_text(provider.get('provider_id'))}/{_safe_text(model.get('model_id'))}",
                details=self._render_model_limit_details(provider, model),
                metadata={"threads_visible": False},
            )
            self._set_status("Model limit shown.")
            return

        target, error = self._resolve_model_limit_target(list(plan.limit_args))
        if target is None:
            self._append_command_feedback(
                plan.command,
                summary="usage",
                details=error or build_command_usage_text("tui", "model", action="limit"),
                level="error",
            )
            self._set_status("Model limit clear usage displayed.")
            return

        provider, model = target
        identity = self._model_identity(provider, model)
        try:
            result = self.registry.clear_learned_token_limit(
                source=identity[0],
                provider_id=identity[1],
                model_id=identity[2],
            )
        except Exception as exc:
            message = f"Failed to clear learned limit: {exc}"
            self._append_command_feedback(
                plan.command,
                summary="clear failed",
                details=message,
                level="error",
            )
            self._set_status(message)
            return

        removed_count = int(result.get("removed_count") or 0) if isinstance(result, dict) else 0
        self._refresh_registry(preferred_model=identity)
        self._refresh_sessions_after_model_limit_change(identity)
        refreshed = self._provider_and_model_from_identity(identity)
        detail_lines = []
        if removed_count > 0:
            detail_lines.append(f"Cleared learned token limit for {identity[1]}/{identity[2]}.")
        else:
            detail_lines.append(f"No learned token limit was set for {identity[1]}/{identity[2]}.")
        detail_lines.append("Change takes effect on the next turn for idle local sessions.")
        if refreshed is not None:
            detail_lines.append("")
            detail_lines.append(self._render_model_limit_details(*refreshed))
        self._append_command_feedback(
            plan.command,
            summary="learned limit cleared" if removed_count > 0 else "nothing to clear",
            details="\n".join(detail_lines).strip(),
            metadata={"threads_visible": False},
        )
        if removed_count > 0:
            self._set_status(f"Cleared learned limit for {identity[1]}/{identity[2]}.")
        else:
            self._set_status(f"No learned limit to clear for {identity[1]}/{identity[2]}.")

    async def _handle_model_command(self, args: list[str]) -> None:
        await self._model_commands.handle(self.current_session, args)

    async def _run_command(self, command: str) -> None:
        raw = _safe_text(command)
        if not raw:
            return
        head_aliases = {
            "?": "help",
            "h": "help",
            "q": "exit",
            "drop-memories": "drop_memories",
            "fill-access": "full_access",
        }
        try:
            invocation = parse_command_text(
                raw,
                surface="tui",
                aliases=head_aliases,
            )
        except CommandParseError as exc:
            self._append_command_feedback(
                raw,
                summary="invalid command",
                details=f"Invalid command: {exc}",
                level="error",
            )
            self._set_status("Invalid command.")
            self._render_all()
            return

        head = invocation.name

        async def _dispatch_help(_invocation) -> None:  # noqa: ANN001
            self._append_command_feedback(
                "help",
                summary="command reference",
                details=self._command_help_text(),
            )
            self._set_status("Printed command help.")
            self._render_all()

        async def _dispatch_theme(inv) -> None:  # noqa: ANN001
            mode = inv.action or "toggle"
            if mode in {"toggle", "switch"}:
                self._toggle_theme()
                self._set_status(f"Theme set to {self.theme_mode}.")
            elif mode in {"dark", "light"}:
                self.theme_mode = mode
                self.application.style = self._style_for_mode(self.theme_mode)
                self._set_status(f"Theme set to {self.theme_mode}.")
            else:
                message = f"Unknown theme mode: {mode}"
                self._append_command_feedback(
                    "theme",
                    summary="unknown theme mode",
                    details=message,
                    level="error",
                )
                self._set_status(message)
            self._render_all()

        async def _dispatch_activity(inv) -> None:  # noqa: ANN001
            action = inv.action or "toggle"
            if action in {"toggle", "expand", "collapse"}:
                self._toggle_activity_details(action)
            else:
                self._append_command_feedback(
                    "activity",
                    summary="unknown action",
                    details=build_unknown_action_text(
                        "tui",
                        "activity",
                        action,
                        fallback=build_command_usage_text("tui", "activity"),
                    ),
                    level="error",
                )
                self._set_status("Unknown activity action.")
                self._render_all()

        async def _dispatch_command_panel(inv) -> None:  # noqa: ANN001
            action = inv.action or "toggle"
            if action in {"toggle", "expand", "collapse"}:
                self._toggle_command_details(action)
            else:
                self._append_command_feedback(
                    "command",
                    summary="unknown action",
                    details=build_unknown_action_text(
                        "tui",
                        "command",
                        action,
                        fallback=build_command_usage_text("tui", "command"),
                    ),
                    level="error",
                )
                self._set_status("Unknown command action.")
                self._render_all()

        async def _dispatch_tasks(inv) -> None:  # noqa: ANN001
            action = inv.action or "list"
            if action == "list":
                self._append_command_feedback(
                    "tasks list",
                    summary=f"{len(self.current_session.view.tasks)} task(s)",
                    details=self._render_tasks(),
                )
                self._set_status("Listed tasks.")
            else:
                self._append_command_feedback(
                    "tasks",
                    summary="unknown action",
                    details=build_unknown_action_text(
                        "tui",
                        "tasks",
                        action,
                        fallback=build_command_usage_text("tui", "tasks"),
                    ),
                    level="error",
                )
                self._set_status("Unknown tasks action.")
            self._render_all()

        async def _dispatch_fork(inv) -> None:  # noqa: ANN001
            if inv.name == "task":
                action = inv.action or "new"
                if action != "new":
                    self._append_command_feedback(
                        "task",
                        summary="unknown action",
                        details=build_unknown_action_text(
                            "tui",
                            "task",
                            action,
                            fallback=build_command_usage_text("tui", "task"),
                        ),
                        level="error",
                    )
                    self._set_status("Unknown task action.")
                    self._render_all()
                    return
                await self._fork_current_session(
                    prompt=inv.joined_args(1) or None,
                    command_label="task new",
                )
                return

            await self._fork_current_session(
                prompt=inv.joined_args() or None,
                command_label="fork",
            )

        async def _dispatch_workflow(inv) -> None:  # noqa: ANN001
            action = inv.action or "run"
            objective_parts = inv.args
            if inv.args and action == "run":
                objective_parts = inv.args[1:]
            if action == "run":
                objective = " ".join(objective_parts).strip()
                if not objective:
                    message = build_command_usage_text("tui", "workflow", action="run")
                    self._append_command_feedback(
                        "workflow run",
                        summary="usage",
                        details=message,
                        level="error",
                    )
                    self._set_status("Workflow objective is required.")
                else:
                    await self._run_minimal_workflow(objective)
            else:
                self._append_command_feedback(
                    "workflow",
                    summary="unknown action",
                    details=build_unknown_action_text(
                        "tui",
                        "workflow",
                        action,
                        fallback=build_command_usage_text("tui", "workflow"),
                    ),
                    level="error",
                )
                self._set_status("Unknown workflow action.")
            self._render_all()

        async def _dispatch_approval(inv) -> None:  # noqa: ANN001
            await self._respond_to_pending_approval(
                session=self.current_session,
                approved=inv.name == "approve",
                token=inv.arg(0) or None,
            )

        async def _dispatch_runtime_policy(inv) -> None:  # noqa: ANN001
            if inv.name in {"plan", "build"}:
                await self._update_session_runtime_policy(
                    self.current_session,
                    approval_profile=inv.name,
                    command_label=inv.name,
                )
                return
            if inv.name == "default":
                await self._update_session_runtime_policy(
                    self.current_session,
                    access_level="default",
                    command_label="default",
                )
                return
            if inv.name == "full_access":
                await self._update_session_runtime_policy(
                    self.current_session,
                    access_level="full-access",
                    command_label="full-access",
                )
                return

        async def _dispatch_context_control(inv) -> None:  # noqa: ANN001
            await self._run_context_control_command(
                session=self.current_session,
                action=inv.name,
                reason=inv.joined_args() or None,
            )

        async def _dispatch_clear(_invocation) -> None:  # noqa: ANN001
            session = self.current_session
            if self._runs_via_gateway(session):
                try:
                    await self.remote_session_service.reset_session(session.session_id)
                    await self._sync_remote_session_detail(session, recent_limit=80)
                    self._set_status(
                        SessionFeedbackService.mutation_feedback(
                            status="reset",
                            title=session.title,
                        ).status_text
                    )
                except Exception as exc:
                    detail = extract_gateway_error_info(exc).detail
                    message = f"Remote clear failed: {detail}"
                    self._append_command_feedback(
                        "clear",
                        summary="clear failed",
                        details=message,
                        level="error",
                    )
                    self._set_status(message)
                self._render_all()
                return
            self._replace_session_messages(session, [])
            self.session_lifecycle_runtime.force_reset(
                session.session_id,
                on_reset=lambda: self._reset_session_runtime_state(session),
            )
            self._persist_session_state()
            self._set_status(f"Cleared {session.title}.")
            self._render_all()

        async def _dispatch_cancel(_invocation) -> None:  # noqa: ANN001
            await self._request_cancel_current_turn_async(emit_system_when_idle=True)

        async def _dispatch_exit(_invocation) -> None:  # noqa: ANN001
            self._request_exit()
            self.application.exit()

        dispatcher = CommandDispatcher(surface="tui", aliases=head_aliases)
        dispatcher.register("help", _dispatch_help, aliases=["h", "?"])
        dispatcher.register("theme", _dispatch_theme)
        dispatcher.register("activity", _dispatch_activity)
        dispatcher.register("command", _dispatch_command_panel)
        dispatcher.register("tasks", _dispatch_tasks)
        dispatcher.register("fork", _dispatch_fork)
        dispatcher.register("task", _dispatch_fork)
        dispatcher.register("workflow", _dispatch_workflow)
        dispatcher.register("approve", _dispatch_approval)
        dispatcher.register("deny", _dispatch_approval)
        dispatcher.register("plan", _dispatch_runtime_policy)
        dispatcher.register("build", _dispatch_runtime_policy)
        dispatcher.register("default", _dispatch_runtime_policy)
        dispatcher.register("full_access", _dispatch_runtime_policy)
        dispatcher.register("compact", _dispatch_context_control)
        dispatcher.register("drop_memories", _dispatch_context_control, aliases=["drop-memories"])
        dispatcher.register("session", lambda inv: self._handle_session_command(inv.args))
        dispatcher.register("context", lambda inv: self._handle_context_command(inv.args))
        dispatcher.register("memory", lambda inv: self._handle_memory_command(inv.args))
        dispatcher.register("kb", lambda inv: self._handle_kb_command(inv.args))
        dispatcher.register("mcp", lambda inv: self._handle_mcp_command(inv.args))
        dispatcher.register("sandbox", lambda inv: self._handle_sandbox_command(inv.args))
        dispatcher.register("skill", lambda inv: self._handle_skill_command(inv))
        dispatcher.register("model", lambda inv: self._handle_model_command(inv.args))
        dispatcher.register("clear", _dispatch_clear)
        dispatcher.register("cancel", _dispatch_cancel)
        dispatcher.register("exit", _dispatch_exit, aliases=["quit", "q"])

        if await dispatcher.dispatch(invocation):
            return

        hint = suggest_command_name(
            head,
            surface="tui",
            extra_candidates={
                "theme",
                "session",
                "activity",
                "command",
                "tasks",
                "fork",
                "task",
                "mcp",
                "approve",
                "deny",
                "plan",
                "build",
                "default",
                "full_access",
                "cancel",
                "clear",
                "exit",
                "quit",
                "drop_memories",
                "drop-memories",
            },
        )
        self._append_command_feedback(
            raw,
            summary="unknown command",
            details=f"Unknown command: {raw}.{hint}",
            level="error",
        )
        self._set_status("Unknown command.")
        self._render_all()

    def _request_exit(self) -> None:
        for session in self.sessions:
            self._cancel_session_turn(session)
        for task in list(self.background_tasks):
            task.cancel()

    def _toggle_theme(self) -> None:
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        self.application.style = self._style_for_mode(self.theme_mode)

    @staticmethod
    def _panel_content_width(panel: Any, *, fallback: int) -> int:
        window = getattr(panel, "window", None)
        render_info = getattr(window, "render_info", None)
        if render_info is not None:
            try:
                return max(18, int(render_info.window_width) - 2)
            except Exception:
                pass
        return max(18, int(fallback))

    @staticmethod
    def _wrap_sidebar_text(value: Any, *, width: int, max_lines: int = 2) -> list[str]:
        text = _safe_text(value)
        if not text:
            return ["No messages yet"]
        wrapped = textwrap.wrap(
            text,
            width=max(8, width),
            break_long_words=True,
            break_on_hyphens=False,
        )
        if not wrapped:
            return [text]
        if len(wrapped) <= max_lines:
            return wrapped
        kept = wrapped[: max_lines]
        remainder = " ".join(wrapped[max_lines - 1 :])
        kept[-1] = _truncate_inline(remainder, limit=max(8, width))
        return kept

    def _sidebar_labeled_lines(
        self,
        label: str,
        value: Any,
        *,
        width: int,
        indent: str = "  ",
        label_width: int = 5,
        max_lines: int = 2,
    ) -> list[str]:
        content_width = max(8, width - len(indent) - label_width - 3)
        wrapped = self._wrap_sidebar_text(value, width=content_width, max_lines=max_lines)
        lines: list[str] = []
        for index, line in enumerate(wrapped):
            label_text = label if index == 0 else ""
            lines.append(f"{indent}{label_text:<{label_width}} | {line}")
        return lines

    @staticmethod
    def _sidebar_divider(width: int, *, strong: bool = False, indent: str = "  ") -> str:
        line_width = max(10, width - len(indent))
        return f"{indent}{('=' if strong else '-') * line_width}"

    @staticmethod
    def _session_status_label(session: TuiSession) -> str:
        run_state = MiniAgentTuiApp._session_run_state_text(session)
        if run_state != "idle":
            return run_state
        if session.view.tasks:
            latest_status = _safe_text(session.view.tasks[-1].status).lower()
            if latest_status in {"completed", "cancelled", "queued", "running", "resume_pending", "resuming"}:
                return latest_status
        return "idle"

    @staticmethod
    def _session_last_active_label(session: TuiSession) -> str:
        if MiniAgentTuiApp._runs_via_gateway(session):
            remote_updated = _safe_text(getattr(session.projection.supplemental, "remote_updated_at", ""))
            if remote_updated:
                return _label_from_iso_timestamp(remote_updated)
        latest_message = MiniAgentTuiApp._session_latest_visible_message(session)
        if latest_message is not None:
            return _safe_text(getattr(latest_message, "timestamp", "")) or "--:--:--"
        if session.view.tasks:
            return _safe_text(session.view.tasks[-1].updated_at) or "--:--:--"
        return "--:--:--"

    @staticmethod
    def _message_visible_in_threads(message: Any) -> bool:
        metadata = getattr(message, "metadata", {})
        if isinstance(metadata, dict):
            override = metadata.get("threads_visible")
            if override is True:
                return True
            if override is False:
                return False
        return _safe_text(getattr(message, "role", "")).lower() != "system"

    @staticmethod
    def _message_is_command(message: Any) -> bool:
        metadata = getattr(message, "metadata", {})
        return isinstance(metadata, dict) and _safe_text(metadata.get("kind")).lower() == "command"

    @staticmethod
    def _session_visible_messages(session: TuiSession) -> list[Any]:
        return [
            message
            for message in session.view.messages
            if MiniAgentTuiApp._message_visible_in_threads(message)
        ]

    @staticmethod
    def _session_latest_visible_message(session: TuiSession) -> Any | None:
        visible = MiniAgentTuiApp._session_visible_messages(session)
        if not visible:
            return None
        return visible[-1]

    @staticmethod
    def _session_latest_command_message(session: TuiSession) -> Any | None:
        for message in reversed(session.view.messages):
            if MiniAgentTuiApp._message_is_command(message):
                return message
        return None

    @staticmethod
    def _session_last_command_preview_from_messages(session: TuiSession) -> str | None:
        latest = MiniAgentTuiApp._session_latest_command_message(session)
        if latest is None:
            return None
        return MiniAgentTuiApp._command_message_preview(latest)

    @staticmethod
    def _command_message_preview(message: Any) -> str:
        metadata = getattr(message, "metadata", {})
        if not isinstance(metadata, dict):
            return _preview_line_text(getattr(message, "content", "")) or "(empty)"
        command = _safe_text(metadata.get("command")) or "command"
        summary = _safe_text(metadata.get("summary")) or _preview_line_text(getattr(message, "content", "")) or "applied"
        return f"{command} | {summary}"

    @staticmethod
    def _session_last_message_preview(session: TuiSession) -> str:
        messages = session.view.messages
        last_any = messages[-1] if messages else None
        if last_any is not None and MiniAgentTuiApp._message_is_command(last_any):
            return MiniAgentTuiApp._command_message_preview(last_any)

        latest = MiniAgentTuiApp._session_latest_visible_message(session)
        if latest is None:
            last_command = MiniAgentTuiApp._session_latest_command_message(session)
            if last_command is not None:
                return MiniAgentTuiApp._command_message_preview(last_command)
            return "No messages yet"

        metadata = getattr(latest, "metadata", {})
        if _safe_text(latest.role).lower() == "tool" and isinstance(metadata, dict) and metadata.get("kind") == "activity":
            items = MiniAgentTuiApp._activity_items(latest)
            if items:
                activity = items[-1]
                label = _truncate_inline(activity.get("label"), limit=10) or "activity"
                detail = _safe_text(activity.get("detail")) or _safe_text(activity.get("state")) or "running"
                preview = _safe_text(activity.get("preview"))
                if preview:
                    content = f"{label} {detail}: {preview}"
                else:
                    content = f"{label} {detail}"
                return content

        preview_source = _preview_line_text(latest.content) or "(empty)"
        return preview_source

    @staticmethod
    def _session_last_command_preview(session: TuiSession) -> str | None:
        remote_summary = _safe_text(getattr(session.projection.supplemental, "remote_last_command_summary", ""))
        if MiniAgentTuiApp._runs_via_gateway(session) and remote_summary:
            return remote_summary
        return MiniAgentTuiApp._session_last_command_preview_from_messages(session)

    @staticmethod
    def _session_metrics_preview(session: TuiSession) -> str:
        status_label = MiniAgentTuiApp._session_status_label(session)
        last_active = MiniAgentTuiApp._session_last_active_label(session)
        visible_message_count = len(MiniAgentTuiApp._session_visible_messages(session))
        return f"state {status_label} | at {last_active}\ncount {visible_message_count} msg | {len(session.view.tasks)} task"

    def _render_sessions(self) -> str:
        rendered, _cursor_position, _current_line_index = self._render_sessions_text_and_cursor()
        return rendered

    def _refresh_sessions_panel(self) -> None:
        sessions_text, sessions_cursor_position, current_line_index = self._render_sessions_text_and_cursor()
        current_document = self.sessions_panel.buffer.document
        if (
            current_document.text != sessions_text
            or current_document.cursor_position != sessions_cursor_position
        ):
            self.sessions_panel.buffer.set_document(
                Document(sessions_text, cursor_position=sessions_cursor_position),
                bypass_readonly=True,
            )
        try:
            self.sessions_panel.window.vertical_scroll = max(0, current_line_index - 1)
        except Exception:
            pass

    def _render_status_panel(self) -> str:
        width = self._panel_content_width(self.status_panel, fallback=32)
        session = self.current_session if self.sessions else None
        lines = ["Summary"]
        lines.extend(
            self._sidebar_labeled_lines(
                "status",
                self.status or "Ready",
                width=width,
                max_lines=3,
                label_width=8,
            )
        )
        if self._skill_catalog_change_notice:
            lines.extend(
                self._sidebar_labeled_lines(
                    "skills",
                    self._skill_catalog_change_notice,
                    width=width,
                    max_lines=2,
                    label_width=8,
                )
            )
        if session is None:
            return "\n".join(lines)
        display = self._build_session_display_model(session)
        projection = session.projection
        view = session.view

        lines.extend(
            self._sidebar_labeled_lines(
                "thread",
                session.title,
                width=width,
                max_lines=2,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "scope",
                display.scope_summary,
                width=width,
                max_lines=1,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "route",
                display.route_summary,
                width=width,
                max_lines=1,
                label_width=8,
            )
        )

        lines.append("")
        lines.append("Run")
        lines.extend(
            self._sidebar_labeled_lines(
                "state",
                self._session_run_state_text(session),
                width=width,
                max_lines=1,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "task",
                self._session_run_task_text(session),
                width=width,
                max_lines=3,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "share",
                display.share_state,
                width=width,
                max_lines=2,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "approve",
                self._pending_approval_summary(session),
                width=width,
                max_lines=2,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "kb",
                self._knowledge_base_summary(session),
                width=width,
                max_lines=1,
                label_width=8,
            )
        )
        sandbox_diagnostics = self._session_sandbox_diagnostics(
            session,
            refresh_local=not self._runs_via_gateway(session),
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "sandbox",
                compact_sandbox_summary(sandbox_diagnostics),
                width=width,
                max_lines=2,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "policy",
                sandbox_policy_summary(sandbox_diagnostics),
                width=width,
                max_lines=2,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "guard",
                sandbox_guardrail_summary(sandbox_diagnostics),
                width=width,
                max_lines=3,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "net",
                sandbox_network_summary(sandbox_diagnostics),
                width=width,
                max_lines=2,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "ctx",
                self._prepared_context_summary(session),
                width=width,
                max_lines=3,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "ctxctl",
                self._context_policy_summary(session),
                width=width,
                max_lines=3,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "skills",
                (
                    self._session_skill_runtime_summary(session)
                    if self._runs_via_gateway(session)
                    else self._local_skill_runtime_overview(session)
                ),
                width=width,
                max_lines=2,
                label_width=8,
            )
        )
        if not self._runs_via_gateway(session):
            lines.extend(
                self._sidebar_labeled_lines(
                    "policy",
                    self._local_skill_policy_overview(session),
                    width=width,
                    max_lines=2,
                    label_width=8,
                )
            )
        lines.extend(
            self._sidebar_labeled_lines(
                "memory",
                self._memory_summary(session),
                width=width,
                max_lines=3,
                label_width=8,
            )
        )
        usage = self._session_usage_stats(session)
        lines.extend(
            self._sidebar_labeled_lines(
                "tokens",
                usage["budget_text"],
                width=width,
                max_lines=2,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "window",
                (
                    f"{self._context_usage_bar_text(usage=usage['usage'], limit=usage['limit'])} "
                    f"{usage['percent']}%"
                    if usage["limit"] > 0
                    else f"{self._context_usage_bar_text(usage=usage['usage'], limit=usage['limit'])} "
                    "--"
                ),
                width=width,
                max_lines=2,
                label_width=8,
            )
        )

        lines.append("")
        lines.append("View")
        lines.extend(
            self._sidebar_labeled_lines(
                "chat",
                "live" if view.chat_follow_output else "history",
                width=width,
                max_lines=1,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "activity",
                "expanded" if view.activity_details_expanded else "compact",
                width=width,
                max_lines=1,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "command",
                "expanded" if view.command_details_expanded else "compact",
                width=width,
                max_lines=1,
                label_width=8,
            )
        )
        if display.show_gateway_panel:
            lines.append("")
            lines.append("Channel")
            if display.has_external_peer:
                lines.extend(
                    self._sidebar_labeled_lines(
                        "peer",
                        display.peer_summary,
                        width=width,
                        max_lines=3,
                        label_width=8,
                    )
                )
            if projection.supplemental.remote_recovery_summary:
                lines.extend(
                    self._sidebar_labeled_lines(
                        "recover",
                        projection.supplemental.remote_recovery_summary,
                        width=width,
                        max_lines=3,
                        label_width=8,
                    )
                )
            if projection.supplemental.remote_last_activity_summary:
                lines.extend(
                    self._sidebar_labeled_lines(
                        "activity",
                        projection.supplemental.remote_last_activity_summary,
                        width=width,
                        max_lines=3,
                        label_width=8,
                    )
                )
            remote_command_summary = display.last_command_preview
            if remote_command_summary:
                lines.extend(
                    self._sidebar_labeled_lines(
                        "command",
                        remote_command_summary,
                        width=width,
                        max_lines=3,
                        label_width=8,
                    )
                )

        lines.append("")
        lines.append("Model")
        lines.extend(
            self._sidebar_labeled_lines(
                "active",
                self._current_model_hint(),
                width=width,
                max_lines=2,
                label_width=8,
            )
        )
        lines.extend(
            self._sidebar_labeled_lines(
                "filter",
                self.model_filter or "off",
                width=width,
                max_lines=1,
                label_width=8,
            )
        )
        return "\n".join(lines)

    def _render_chat(self) -> str:
        lines = self._current_chat_render_lines()
        return "\n".join(f"{line.prefix}{line.text}" for line in lines).rstrip()

    @staticmethod
    def _assistant_line_style(line: str, *, in_code_block: bool) -> str:
        stripped = line.strip()
        if in_code_block:
            if stripped.startswith("```"):
                return "class:chat.body.assistant.code.fence"
            return "class:chat.body.assistant.code"
        if stripped.startswith("```"):
            return "class:chat.body.assistant.code.fence"
        if stripped.startswith("#"):
            return "class:chat.body.assistant.heading"
        first_token = stripped.split(" ", 1)[0]
        is_numbered_item = first_token.endswith(".") and first_token[:-1].isdigit()
        if stripped.startswith(("-", "*")) or is_numbered_item:
            return "class:chat.body.assistant.list"
        if stripped.startswith(">"):
            return "class:chat.body.assistant.quote"
        return "class:chat.body"

    @staticmethod
    def _assistant_code_border_text(line: str, *, closing: bool) -> str:
        if closing:
            return "+ end code"
        language = line.strip()[3:].strip()
        return f"+ code: {language}" if language else "+ code"

    def _render_assistant_entry(
        self,
        item: ChatEntry,
        *,
        prefix_style: str,
    ) -> list[ChatRenderLine]:
        content_value = _format_assistant_content(item.content)
        content_lines = str(content_value or "").split("\n") or [""]
        rendered_lines: list[ChatRenderLine] = []
        in_code_block = False
        for content_line in content_lines:
            stripped = content_line.strip()
            if stripped.startswith("```"):
                rendered_lines.append(
                    ChatRenderLine(
                        self._assistant_code_border_text(content_line, closing=in_code_block),
                        "class:chat.body.assistant.code.border",
                        prefix="| ",
                        prefix_style=prefix_style,
                    )
                )
                in_code_block = not in_code_block
                continue
            rendered_lines.append(
                ChatRenderLine(
                    content_line,
                    self._assistant_line_style(content_line, in_code_block=in_code_block),
                    prefix="|   " if in_code_block else "| ",
                    prefix_style=prefix_style,
                )
            )
        return rendered_lines

    @staticmethod
    def _activity_summary_style(label: str, *, is_recent: bool) -> str:
        normalized = _safe_text(label).lower()
        if normalized == "thinking":
            return "class:chat.body.tool.thinking" if is_recent else "class:chat.body.tool.thinking.old"
        if normalized in {"shell", "bash", "powershell"}:
            return "class:chat.body.tool.shell" if is_recent else "class:chat.body.tool.shell.old"
        if normalized in {
            "read",
            "read-file",
            "read_file",
            "cat",
            "glob",
            "list",
            "ls",
        }:
            return "class:chat.body.tool.read" if is_recent else "class:chat.body.tool.read.old"
        if normalized in {
            "search",
            "grep",
            "find",
            "rg",
            "websearch",
            "web-search",
            "webfetch",
            "fetch",
        }:
            return "class:chat.body.tool.search" if is_recent else "class:chat.body.tool.search.old"
        if normalized in {
            "edit",
            "write",
            "patch",
            "apply_patch",
            "write-file",
            "write_file",
            "edit-file",
            "edit_file",
        }:
            return "class:chat.body.tool.write" if is_recent else "class:chat.body.tool.write.old"
        return "class:chat.body.tool.generic" if is_recent else "class:chat.body.tool.generic.old"

    @staticmethod
    def _is_command_entry(item: Any) -> bool:
        metadata = getattr(item, "metadata", None)
        return (
            _safe_text(getattr(item, "role", "")).lower() == "system"
            and isinstance(metadata, dict)
            and metadata.get("kind") == "command"
        )

    @staticmethod
    def _entry_heading(item: Any) -> str:
        if MiniAgentTuiApp._is_command_entry(item):
            return _role_heading("command")
        return _role_heading(_safe_text(getattr(item, "role", "")))

    @staticmethod
    def _chat_styles_for_role(role: str) -> tuple[str, str, str]:
        normalized = _safe_text(role).lower()
        if normalized == "user":
            return (
                "class:chat.role.user",
                "class:chat.body",
                "class:chat.prefix.user",
            )
        if normalized == "assistant":
            return (
                "class:chat.role.assistant",
                "class:chat.body",
                "class:chat.prefix.assistant",
            )
        if normalized == "command":
            return (
                "class:chat.role.command",
                "class:chat.body.command",
                "class:chat.prefix.command",
            )
        if normalized == "system":
            return (
                "class:chat.role.system",
                "class:chat.body.system",
                "class:chat.prefix.system",
            )
        if normalized == "tool":
            return (
                "class:chat.role.tool",
                "class:chat.body.tool",
                "class:chat.prefix.tool",
            )
        return (
            "class:chat.role.system",
            "class:chat.body.system",
            "class:chat.prefix.system",
        )

    def _render_command_entry(
        self,
        item: ChatEntry,
        *,
        body_style: str,
        prefix_style: str,
    ) -> list[ChatRenderLine]:
        metadata = getattr(item, "metadata", {})
        command_name = _safe_text(metadata.get("command")) or "command"
        summary = _safe_text(metadata.get("summary")) or _safe_text(_preview_line_text(item.content)) or "completed"
        level = _safe_text(metadata.get("level")).lower() or "info"
        summary_style = (
            "class:chat.body.command.summary.error"
            if level == "error"
            else "class:chat.body.command.summary"
        )
        output_style = (
            "class:chat.body.command.output.error"
            if level == "error"
            else "class:chat.body.command.output"
        )
        detail_text = _normalize_chat_content(item.content).strip()
        display_command = command_name if command_name.startswith("/") else f"/{command_name}"
        lines = [
            ChatRenderLine(
                f"{display_command} | {summary}",
                summary_style,
                prefix="| > ",
                prefix_style=prefix_style,
            )
        ]
        if detail_text and self.current_session.view.command_details_expanded:
            lines.append(
                ChatRenderLine(
                    "output:",
                    "class:chat.body.command.meta",
                    prefix="|   ",
                    prefix_style=prefix_style,
                )
            )
            for detail_line in detail_text.split("\n"):
                lines.append(
                    ChatRenderLine(
                        detail_line,
                        output_style or body_style,
                        prefix="|     ",
                        prefix_style=prefix_style,
                    )
                )
        return lines

    def _render_activity_entry(
        self,
        item: ChatEntry,
        *,
        body_style: str,
        prefix_style: str,
    ) -> list[ChatRenderLine]:
        activity_lines: list[ChatRenderLine] = []
        items = self._activity_items(item)
        expanded = bool(self.current_session.view.activity_details_expanded)

        if not items:
            content_lines = _normalize_chat_content(item.content).split("\n") or [""]
            for content_line in content_lines:
                activity_lines.append(
                    ChatRenderLine(
                        content_line,
                        body_style,
                        prefix="| ",
                        prefix_style=prefix_style,
                    )
                )
            return activity_lines

        for index, activity in enumerate(items):
            label = _truncate_inline(activity.get("label"), limit=10) or "activity"
            detail = _safe_text(activity.get("detail")) or "running"
            preview = _safe_text(activity.get("preview"))
            output_summary = _safe_text(activity.get("output_summary"))
            output_text = _normalize_chat_content(activity.get("output_text")).strip()
            state = _safe_text(activity.get("state")).lower()
            is_completed_tool = label != "thinking" and state in {"ok", "failed"}
            is_recent = index == len(items) - 1
            activity_style = self._activity_summary_style(label, is_recent=is_recent)
            main_prefix = "| > " if is_recent else "| . "
            meta_style = "class:chat.body.tool.meta" if is_recent else "class:chat.body.tool.meta.old"
            output_style = "class:chat.body.tool.output" if is_recent else "class:chat.body.tool.output.old"

            compact_parts: list[str] = []
            if is_completed_tool:
                compact_parts.append(state)
                if preview:
                    compact_parts.append(preview)
                if output_summary and label == "shell":
                    compact_parts.append(output_summary)
                compact_line = " | ".join(part for part in compact_parts if part).strip()
                if compact_line and not expanded:
                    activity_lines.append(
                        ChatRenderLine(
                            f"{label:<10} {compact_line}".rstrip(),
                            activity_style,
                            prefix=main_prefix,
                            prefix_style=prefix_style,
                        )
                    )
                    continue

            activity_lines.append(
                ChatRenderLine(
                    f"{label:<10} {detail}".rstrip(),
                    activity_style,
                    prefix=main_prefix,
                    prefix_style=prefix_style,
                )
            )
            if preview:
                activity_lines.append(
                    ChatRenderLine(
                        f"cmd: {preview}",
                        meta_style,
                        prefix="|   ",
                        prefix_style=prefix_style,
                    )
                )
            if output_text:
                if expanded:
                    activity_lines.append(
                        ChatRenderLine(
                            "output:",
                            meta_style,
                            prefix="|   ",
                            prefix_style=prefix_style,
                        )
                    )
                    for output_line in output_text.split("\n"):
                        activity_lines.append(
                            ChatRenderLine(
                                output_line,
                                output_style,
                                prefix="|     ",
                                prefix_style=prefix_style,
                            )
                        )
                elif output_summary:
                    activity_lines.append(
                        ChatRenderLine(
                            f"out: {output_summary}",
                            meta_style,
                            prefix="|   ",
                            prefix_style=prefix_style,
                        )
                    )
        return activity_lines

    def _build_chat_render_lines(self) -> list[ChatRenderLine]:
        view = self.current_session.view
        if not view.messages:
            return [
                ChatRenderLine("MINI-AGENT", "class:chat.empty.title"),
                ChatRenderLine("Start the conversation below.", "class:chat.empty.body"),
                ChatRenderLine("", "class:chat.empty.body"),
                ChatRenderLine(
                    "Enter sends. Esc+Enter inserts a newline.",
                    "class:chat.empty.body",
                ),
            ]

        lines: list[ChatRenderLine] = []
        for item in view.messages:
            if lines:
                lines.append(ChatRenderLine(""))
            if self._is_command_entry(item):
                heading_style, body_style, prefix_style = self._chat_styles_for_role("command")
            else:
                heading_style, body_style, prefix_style = self._chat_styles_for_role(item.role)
            lines.append(
                ChatRenderLine(
                    f"{self._entry_heading(item)}  {item.timestamp}",
                    heading_style,
                )
            )
            metadata = getattr(item, "metadata", {})
            if _safe_text(item.role).lower() == "tool" and isinstance(metadata, dict) and metadata.get("kind") == "activity":
                lines.extend(
                    self._render_activity_entry(
                        item,
                        body_style=body_style,
                        prefix_style=prefix_style,
                    )
                )
            elif self._is_command_entry(item):
                lines.extend(
                    self._render_command_entry(
                        item,
                        body_style=body_style,
                        prefix_style=prefix_style,
                    )
                )
            else:
                content_value = item.content
                if _safe_text(item.role).lower() == "assistant":
                    lines.extend(
                        self._render_assistant_entry(
                            item,
                            prefix_style=prefix_style,
                        )
                    )
                    continue
                else:
                    content_value = _normalize_chat_content(content_value)
                content_lines = str(content_value or "").split("\n") or [""]
                for content_line in content_lines:
                    lines.append(
                        ChatRenderLine(
                            content_line,
                            body_style,
                            prefix="| ",
                            prefix_style=prefix_style,
                        )
                    )
        return lines

    @staticmethod
    def _message_cache_signature(message: Any) -> tuple[str, str, str, str]:
        metadata = getattr(message, "metadata", None)
        kind = ""
        if isinstance(metadata, dict):
            kind = _safe_text(metadata.get("kind"))
        return (
            _safe_text(getattr(message, "role", "")),
            _safe_text(getattr(message, "content", "")),
            _safe_text(getattr(message, "timestamp", "")),
            kind,
        )

    def _current_chat_render_key(self) -> tuple[str, int, bool, bool, int, int, tuple[str, str, str, str], tuple[str, str, str, str]]:
        session = self.current_session
        view = session.view
        messages = list(getattr(view, "messages", []) or [])
        first_signature = self._message_cache_signature(messages[0]) if messages else ("", "", "", "")
        last_signature = self._message_cache_signature(messages[-1]) if messages else ("", "", "", "")
        return (
            _safe_text(session.session_id),
            int(getattr(view, "chat_render_revision", 0)),
            bool(view.activity_details_expanded),
            bool(view.command_details_expanded),
            id(getattr(view, "messages", None)),
            len(messages),
            first_signature,
            last_signature,
        )

    def _current_chat_render_lines(self) -> list[ChatRenderLine]:
        key = self._current_chat_render_key()
        if self._chat_render_cache_key != key:
            lines = self._build_chat_render_lines()
            fragments: list[tuple[str, str]] = []
            for index, line in enumerate(lines):
                fragments.append((line.style, line.text))
                if index < len(lines) - 1:
                    fragments.append(("", "\n"))
            self._chat_render_cache_key = key
            self._chat_render_cache_lines = lines
            self._chat_render_cache_fragments = fragments
        return self._chat_render_cache_lines

    def _render_chat_fragments(self) -> list[tuple[str, str]]:
        self._current_chat_render_lines()
        return self._chat_render_cache_fragments

    def _chat_line_prefix(self, line_number: int, wrap_count: int) -> list[tuple[str, str]] | str:
        _ = wrap_count
        lines = self._current_chat_render_lines()
        if line_number < 0 or line_number >= len(lines):
            return ""
        line = lines[line_number]
        if not line.prefix:
            return ""
        return [(line.prefix_style, line.prefix)]

    def _chat_cursor_position(self) -> Point:
        lines = self._current_chat_render_lines()
        if not lines:
            return Point(x=0, y=0)
        last_index = len(lines) - 1
        if not self.sessions:
            return Point(x=len(lines[last_index].text), y=last_index)
        session = self.current_session
        view = session.view
        if view.chat_follow_output:
            return Point(x=len(lines[last_index].text), y=last_index)
        target_line = min(max(0, view.chat_scroll_line), last_index)
        return Point(x=0, y=target_line)

    def _render_models_text_and_cursor(self) -> tuple[str, int, int]:
        width = self._panel_content_width(self.models_panel, fallback=32)
        session = self.current_session if self.sessions else None
        if not self.providers:
            self._models_line_styles = ["muted:body", "muted:body"]
            text = "No providers/models available.\nConfigure API keys or add custom providers."
            return text, 0, 0
        visible = self._visible_provider_models()
        if not visible:
            self._models_line_styles = ["muted:body"]
            text = f"No models match filter: {self.model_filter}"
            return text, 0, 0

        focused_provider_index = self.model_cursor[0] if self.model_cursor is not None else visible[0][0]
        focused_bundle = next(
            (
                (p_idx, provider, models)
                for p_idx, provider, models in visible
                if p_idx == focused_provider_index
            ),
            visible[0],
        )
        focus_provider_idx, focus_provider, focus_models = focused_bundle
        focus_model_idx = 0
        if self.model_cursor is not None:
            for local_index, (m_idx, _) in enumerate(focus_models):
                if (focus_provider_idx, m_idx) == self.model_cursor:
                    focus_model_idx = local_index
                    break

        focus_source = _safe_text(focus_provider.get("source", "custom"))
        focus_source_tag = "C" if focus_source == "custom" else "P"
        focus_name = _safe_text(focus_provider.get("provider_name")) or _safe_text(
            focus_provider.get("provider_id")
        )
        lines: list[str] = []
        line_styles: list[str] = []
        current_line_index = 0
        focus_lines = self._sidebar_labeled_lines(
            "focus",
            f"{focus_name} [{focus_source_tag}]",
            width=width,
            max_lines=2,
        )
        lines.extend(focus_lines)
        line_styles.extend(["current:summary"] * len(focus_lines))
        count_lines = self._sidebar_labeled_lines(
            "count",
            f"{len(focus_models)} model(s)",
            width=width,
            max_lines=2,
        )
        lines.extend(count_lines)
        line_styles.extend(["current:summary"] * len(count_lines))
        active_lines = self._sidebar_labeled_lines(
            "active",
            self._current_model_hint(),
            width=width,
            max_lines=2,
        )
        lines.extend(active_lines)
        line_styles.extend(["current:summary"] * len(active_lines))
        filter_lines = self._sidebar_labeled_lines(
            "filter",
            self.model_filter or "off",
            width=width,
            max_lines=2,
        )
        lines.extend(filter_lines)
        line_styles.extend(["current:summary"] * len(filter_lines))

        lines.append("Providers")
        line_styles.append("muted:section")
        visible_provider_order = [p_idx for p_idx, _provider, _models in visible]
        focus_provider_local_index = visible_provider_order.index(focus_provider_idx)
        provider_start, provider_end = self._window_bounds(
            len(visible),
            focus_provider_local_index,
            window_size=3,
        )
        if provider_start > 0:
            lines.append("  ...")
            line_styles.append("muted:body")
        for p_idx, provider, _models in visible[provider_start:provider_end]:
            source = provider.get("source", "custom")
            source_tag = "C" if _safe_text(source) == "custom" else "P"
            provider_name = _safe_text(provider.get("provider_name")) or _safe_text(
                provider.get("provider_id")
            )
            provider_default = self._effective_provider_default_model_id(
                provider,
                session=session,
            ) or "-"
            marker = ">" if p_idx == focus_provider_idx else " "
            provider_local_index = visible_provider_order.index(p_idx)
            provider_band = self._distance_color_band(provider_local_index - focus_provider_local_index)
            provider_title_line = f"{provider_name} [{source_tag}] | default"
            title_chunks = self._wrap_sidebar_text(
                provider_title_line,
                width=max(12, width - 4),
                max_lines=2,
            )
            for index, provider_chunk in enumerate(title_chunks):
                if index == 0:
                    prefix = "  > " if marker == ">" else "  "
                else:
                    prefix = "    "
                lines.append(f"{prefix}{provider_chunk}")
                line_styles.append(f"{provider_band}:provider")
            default_chunks = self._wrap_sidebar_text(
                provider_default,
                width=max(10, width - 6),
                max_lines=2,
            )
            for provider_chunk in default_chunks:
                lines.append(f"    {provider_chunk}")
                line_styles.append(f"{provider_band}:provider-detail")
        if provider_end < len(visible):
            lines.append("  ...")
            line_styles.append("muted:body")

        lines.append(f"Models ({focus_name})")
        line_styles.append("muted:section")
        start, end = self._window_bounds(
            len(focus_models),
            focus_model_idx,
            window_size=4,
        )
        if start > 0:
            lines.append("  ...")
            line_styles.append("muted:body")
        for local_index in range(start, end):
            m_idx, model = focus_models[local_index]
            cursor = ">" if self.model_cursor == (focus_provider_idx, m_idx) else " "
            if cursor == ">":
                current_line_index = len(lines)
            default = (
                "*"
                if self._model_is_effective_default(
                    focus_provider,
                    model,
                    session=session,
                )
                else " "
            )
            display_name = _safe_text(model.get("display_name")) or _safe_text(model.get("model_id"))
            model_id = _safe_text(model.get("model_id"))
            if display_name != model_id:
                model_line = f"{display_name} [{model_id}]"
            else:
                model_line = display_name
            model_band = self._distance_color_band(local_index - focus_model_idx)
            wrapped_model_lines = self._wrap_sidebar_text(
                model_line,
                width=max(10, width - 6),
                max_lines=2,
            )
            for index, model_chunk in enumerate(wrapped_model_lines):
                prefix = f"  {cursor}{default} " if index == 0 else "     "
                lines.append(f"{prefix}{model_chunk}")
                line_styles.append(f"{model_band}:model")
        if end < len(focus_models):
            lines.append("  ...")
            line_styles.append("muted:body")
        self._models_line_styles = line_styles
        cursor_position = 0
        if lines:
            cursor_position = sum(len(line) + 1 for line in lines[:current_line_index])
        return "\n".join(lines), cursor_position, current_line_index

    def _render_models(self) -> str:
        rendered, _cursor_position, _current_line_index = self._render_models_text_and_cursor()
        return rendered

    def _refresh_models_panel(self) -> None:
        models_text, _models_cursor_position, _current_line_index = self._render_models_text_and_cursor()
        current_document = self.models_panel.buffer.document
        if current_document.text != models_text or current_document.cursor_position != 0:
            self.models_panel.buffer.set_document(
                Document(models_text, cursor_position=0),
                bypass_readonly=True,
            )
        try:
            self.models_panel.window.vertical_scroll = 0
        except Exception:
            pass

    def _before_render(self, app: Application[None]) -> None:
        del app
        self._check_skill_catalog_change()
        pending = self._pending_approval_target()
        if pending is None:
            self._approval_modal_open = False
            self._approval_modal_snoozed_token = None
        else:
            token = self._pending_approval_token(pending)
            if self._approval_modal_snoozed_token and token != self._approval_modal_snoozed_token:
                self._approval_modal_snoozed_token = None
            if not self._approval_modal_open and token != self._approval_modal_snoozed_token:
                self._open_approval_modal(force=True)
        self._refresh_sessions_panel()
        self._refresh_models_panel()

    def _render_all(self) -> None:
        self.status_panel.buffer.set_document(
            Document(self._render_status_panel(), cursor_position=0),
            bypass_readonly=True,
        )
        self._refresh_sessions_panel()
        self._restore_chat_view_state()
        self._refresh_models_panel()
        self.application.invalidate()

    async def run(self) -> None:
        if self.initial_prompt:
            self.input_box.buffer.document = Document(
                text=self.initial_prompt,
                cursor_position=len(self.initial_prompt),
            )
        if any(session.runtime.pending_resume_task_id for session in self.sessions):
            await self._resume_pending_tasks()
        try:
            await self._sync_remote_sessions_once(focus_current=True)
        except Exception:
            pass
        self._ensure_remote_sync_started()
        try:
            await self.application.run_async()
        finally:
            self._request_exit()
            if self.background_tasks:
                await asyncio.gather(*self.background_tasks, return_exceptions=True)
            await self._shutdown_all_submission_loops()
            self._persist_session_state()


async def run_tui(
    *,
    workspace: Path,
    approval_profile: str | None = None,
    access_level: str | None = None,
    initial_prompt: str | None = None,
    config_loader: Callable[[], Config],
) -> None:
    """Run Mini-Agent full-screen TUI mode."""
    app = MiniAgentTuiApp(
        workspace=workspace,
        approval_profile=approval_profile,
        access_level=access_level,
        initial_prompt=initial_prompt,
        config_loader=config_loader,
    )
    try:
        await app.run()
    finally:
        await cleanup_mcp_connections()
