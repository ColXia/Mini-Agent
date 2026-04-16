"""Shared execution helpers for operator commands with common local semantics."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Sequence

from mini_agent.memory.command_service import (
    MemoryCommandError,
    MemoryCommandRequest,
    MemoryCommandService,
)
from mini_agent.agent_core.skills.command_service import (
    SkillCommandError,
    SkillCommandRequest,
    SkillCommandService,
    SUPPORTED_SKILL_ACTIONS,
)
from mini_agent.agent_core.skills.workspace_support import (
    load_workspace_skill_policy,
)

from mini_agent.runtime.sandbox_state import compact_sandbox_summary, format_sandbox_status
from mini_agent.agent_core.context.turn_context import (
    context_policy_summary_line,
    format_context_policy_details,
    format_prepared_context_diagnostics,
    format_prepared_turn_context_details,
    resolve_turn_context_policy,
)
from mini_agent.agent_core.context.command_service import (
    ContextCommandError,
    ContextCommandRequest,
    ContextCommandService,
)
from mini_agent.tools.mcp.command_service import (
    McpCommandError,
    McpCommandService,
    McpReloadOutcome,
)
from mini_agent.tools.knowledge_base_control_service import KnowledgeBaseControlService

from .catalog import build_command_usage_text, build_unknown_action_text
from .mcp_support import collect_mcp_operator_snapshot, format_mcp_server_list, format_mcp_status


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split())


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


@dataclass(slots=True)
class CommandExecutionResult:
    """Structured result returned by a shared command execution helper."""

    command: str
    summary: str
    details: str
    status_text: str
    kind: str = "info"
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a dict payload that keeps structured metadata plus summary/details."""

        payload = dict(self.payload)
        payload.setdefault("summary", self.summary)
        payload.setdefault("details", self.details)
        return payload


@dataclass(frozen=True, slots=True)
class CatalogModelUseRequest:
    """One validated `/model use` request resolved against a catalog snapshot."""

    identity: tuple[str, str, str]
    provider_id: str
    model_id: str


@dataclass(frozen=True, slots=True)
class MemoryCommandPlan:
    """Shared `/memory` command plan resolved before local or remote execution."""

    command: str
    action: str
    success_status: str
    failure_summary: str
    failure_detail_prefix: str
    failure_status: str
    detail_mode: str = "full"
    engram_id: str | None = None
    content: str | None = None
    query: str | None = None
    day: str | None = None
    export_format: str | None = None
    summary_fallback: str | Callable[[Any, dict[str, Any]], str] = ""
    metadata_builder: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    requires_idle_local_runtime: bool = False
    is_mutation: bool = False


@dataclass(frozen=True, slots=True)
class ModelCommandPlan:
    """Shared `/model` command plan resolved before surface-specific execution."""

    command: str
    action: str
    cursor_delta: int = 0
    request: CatalogModelUseRequest | None = None
    filter_value: str | None = None
    limit_args: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ContextCommandPlan:
    """Shared `/context` command plan resolved before surface-specific execution."""

    action: str
    args: tuple[str, ...]
    refresh_snapshot: bool = False
    mutate_policy: bool = False


def parse_memory_show_target(surface: str, parts: Sequence[str]) -> tuple[str, str | None, str | None]:
    """Normalize `/memory show` arguments across terminal surfaces."""

    if not parts:
        return "full", None, None

    first = _safe_text(parts[0])
    lowered = first.lower()
    if lowered in {"brief", "full"}:
        if len(parts) > 1:
            return "full", None, build_command_usage_text(surface, "memory", action="show")
        return lowered, None, None
    if len(parts) > 1:
        return "full", None, build_command_usage_text(surface, "memory", action="show")
    return "full", first, None


def _memory_usage_result(
    *,
    surface: str,
    command: str,
    action: str | None,
    status_text: str,
) -> CommandExecutionResult:
    return CommandExecutionResult(
        command=command,
        summary="usage",
        details=build_command_usage_text(surface, "memory", action=action),
        status_text=status_text,
        kind="usage",
    )


def _memory_unknown_action_result(
    *,
    surface: str,
    command: str,
    action: str,
    fallback_action: str | None = None,
    status_text: str,
) -> CommandExecutionResult:
    return CommandExecutionResult(
        command=command,
        summary="unknown action",
        details=build_unknown_action_text(
            surface,
            "memory",
            action,
            fallback=build_command_usage_text(surface, "memory", action=fallback_action),
        ),
        status_text=status_text,
        kind="error",
    )


def _model_usage_result(
    *,
    surface: str,
    command: str,
    action: str | None,
    status_text: str,
    details: str | None = None,
    summary: str = "usage",
) -> CommandExecutionResult:
    return CommandExecutionResult(
        command=command,
        summary=summary,
        details=details or build_command_usage_text(surface, "model", action=action),
        status_text=status_text,
        kind="usage",
    )


def _model_unknown_action_result(
    *,
    surface: str,
    command: str,
    action: str,
    fallback_action: str | None = None,
    status_text: str,
) -> CommandExecutionResult:
    return CommandExecutionResult(
        command=command,
        summary="unknown action",
        details=build_unknown_action_text(
            surface,
            "model",
            action,
            fallback=build_command_usage_text(surface, "model", action=fallback_action),
        ),
        status_text=status_text,
        kind="error",
    )


def prepare_model_command_plan(
    *,
    surface: str,
    args: Sequence[str],
    providers: Sequence[dict[str, Any]],
    default_action: str,
    allow_show: bool,
    extended_actions: bool,
    current_filter: str | None = None,
    strict_basic_arity: bool = False,
) -> ModelCommandPlan | CommandExecutionResult:
    """Normalize `/model` semantics into one reusable plan for CLI/TUI."""

    normalized_args = list(args or [])
    action = normalized_args[0].lower() if normalized_args else default_action

    if action == "show":
        if not allow_show:
            return _model_unknown_action_result(
                surface=surface,
                command="model",
                action=action,
                status_text="Unknown model action.",
            )
        if strict_basic_arity and len(normalized_args) > 1:
            return _model_usage_result(
                surface=surface,
                command="model show",
                action="show",
                status_text="Model show usage shown.",
            )
        return ModelCommandPlan(command="model show", action="show")

    if action == "list":
        if strict_basic_arity and len(normalized_args) > 1:
            return _model_usage_result(
                surface=surface,
                command="model list",
                action="list",
                status_text="Model list usage shown.",
            )
        return ModelCommandPlan(command="model list", action="list")

    if action == "use":
        request = resolve_catalog_model_use_request(
            surface=surface,
            providers=providers,
            args=normalized_args,
        )
        if isinstance(request, CommandExecutionResult):
            return request
        return ModelCommandPlan(
            command="model use",
            action="use",
            request=request,
        )

    if not extended_actions:
        return _model_unknown_action_result(
            surface=surface,
            command="model",
            action=action,
            status_text="Unknown model action.",
        )

    if action == "next":
        return ModelCommandPlan(command="model next", action="cursor", cursor_delta=1)
    if action == "prev":
        return ModelCommandPlan(command="model prev", action="cursor", cursor_delta=-1)
    if action == "apply":
        return ModelCommandPlan(command="model apply", action="apply")
    if action == "discover":
        return ModelCommandPlan(command="model discover", action="discover")
    if action == "refresh":
        return ModelCommandPlan(command="model refresh", action="refresh")
    if action == "filter":
        if len(normalized_args) < 2:
            current = current_filter or "off"
            return _model_usage_result(
                surface=surface,
                command="model filter",
                action="filter",
                status_text="Model filter usage shown.",
                summary=f"current={current}",
                details=(
                    f"Current model filter: {current}\n"
                    f"{build_command_usage_text(surface, 'model', action='filter')}"
                ),
            )
        raw_filter = " ".join(normalized_args[1:]).strip()
        if raw_filter.lower() in {"clear", "none", "off", "*"}:
            return ModelCommandPlan(command="model filter", action="filter_clear")
        return ModelCommandPlan(
            command="model filter",
            action="filter_set",
            filter_value=raw_filter,
        )
    if action == "limit":
        limit_args = list(normalized_args[1:])
        limit_action = "show"
        if limit_args and limit_args[0].lower() in {"show", "list", "clear"}:
            limit_action = limit_args[0].lower()
            limit_args = limit_args[1:]
        if limit_action == "list":
            return ModelCommandPlan(command="model limit list", action="limit_list")
        if limit_action == "show":
            return ModelCommandPlan(
                command="model limit show",
                action="limit_show",
                limit_args=tuple(limit_args),
            )
        if limit_action == "clear":
            return ModelCommandPlan(
                command="model limit clear",
                action="limit_clear",
                limit_args=tuple(limit_args),
            )
        return _model_unknown_action_result(
            surface=surface,
            command="model limit",
            action=limit_action,
            fallback_action="limit",
            status_text="Unknown model limit action.",
        )
    return _model_unknown_action_result(
        surface=surface,
        command="model",
        action=action,
        status_text="Unknown model action.",
    )


def prepare_context_command_plan(
    *,
    args: Sequence[str],
    default_action: str = "show",
) -> ContextCommandPlan:
    """Normalize `/context` command aliases and side-effect flags across surfaces."""

    normalized_args = list(args or [])
    action = normalized_args[0].lower() if normalized_args else default_action
    if action in {"brief", "full"}:
        normalized_args = ["show", action]
        action = "show"
    return ContextCommandPlan(
        action=action,
        args=tuple(normalized_args),
        refresh_snapshot=action in {"show", "stats"},
        mutate_policy=action in {"include", "exclude", "budget", "reset"},
    )


def prepare_memory_command_plan(
    *,
    surface: str,
    args: Sequence[str],
    memory_summary_resolver: Callable[[Any, dict[str, Any]], str] | None = None,
) -> MemoryCommandPlan | CommandExecutionResult:
    """Normalize `/memory` semantics into one reusable plan for CLI/TUI."""

    normalized_args = list(args or [])
    action = normalized_args[0].lower() if normalized_args else "status"
    if action in {"brief", "full"}:
        normalized_args = ["show", action]
        action = "show"

    status_summary_fallback: str | Callable[[Any, dict[str, Any]], str]
    show_summary_fallback: str | Callable[[Any, dict[str, Any]], str]
    list_summary_fallback: str | Callable[[Any, dict[str, Any]], str]
    runtime_summary_fallback: str | Callable[[Any, dict[str, Any]], str]
    if memory_summary_resolver is None:
        status_summary_fallback = "memory status shown"
        show_summary_fallback = "memory diagnostics shown"
        list_summary_fallback = "runtime memory list shown"
        runtime_summary_fallback = "runtime task memory shown"
    else:
        status_summary_fallback = memory_summary_resolver
        show_summary_fallback = memory_summary_resolver
        list_summary_fallback = memory_summary_resolver
        runtime_summary_fallback = memory_summary_resolver

    if action == "status":
        if len(normalized_args) > 1:
            return _memory_usage_result(
                surface=surface,
                command="memory status",
                action="status",
                status_text="Memory status usage shown.",
            )
        return MemoryCommandPlan(
            command="memory status",
            action="status",
            detail_mode="brief",
            success_status="Memory status shown.",
            failure_summary="status failed",
            failure_detail_prefix="Memory status failed: ",
            failure_status="Memory status failed.",
            summary_fallback=status_summary_fallback,
        )

    if action == "show":
        detail_mode, selector, usage_error = parse_memory_show_target(surface, normalized_args[1:])
        if usage_error:
            return _memory_usage_result(
                surface=surface,
                command="memory show",
                action="show",
                status_text="Memory show usage displayed.",
            )
        return MemoryCommandPlan(
            command=(
                f"memory show {selector}"
                if selector
                else f"memory show {detail_mode}" if detail_mode != "full" else "memory show"
            ),
            action="session_show" if selector else "show",
            engram_id=selector,
            detail_mode=detail_mode,
            success_status="Runtime memory entry shown." if selector else "Memory diagnostics shown.",
            failure_summary="show failed",
            failure_detail_prefix=f"{'Runtime memory entry' if selector else 'Memory diagnostics'} failed: ",
            failure_status="Runtime memory entry failed." if selector else "Memory diagnostics failed.",
            summary_fallback=show_summary_fallback,
        )

    if action == "list":
        if len(normalized_args) > 1:
            return _memory_usage_result(
                surface=surface,
                command="memory list",
                action="list",
                status_text="Memory list usage shown.",
            )
        return MemoryCommandPlan(
            command="memory list",
            action="list",
            detail_mode="full",
            success_status="Runtime memory list shown.",
            failure_summary="list failed",
            failure_detail_prefix="Runtime memory list failed: ",
            failure_status="Runtime memory list failed.",
            summary_fallback=list_summary_fallback,
        )

    if action == "overview":
        if len(normalized_args) > 1:
            return _memory_usage_result(
                surface=surface,
                command="memory overview",
                action="overview",
                status_text="Memory overview usage shown.",
            )
        return MemoryCommandPlan(
            command="memory overview",
            action="overview",
            detail_mode="full",
            success_status="Memory overview shown.",
            failure_summary="overview failed",
            failure_detail_prefix="Memory overview failed: ",
            failure_status="Memory overview failed.",
            summary_fallback="memory overview shown",
        )

    if action == "export":
        export_format = normalized_args[1].lower() if len(normalized_args) >= 2 else "jsonl"
        if len(normalized_args) > 2 or export_format not in {"jsonl", "markdown"}:
            return _memory_usage_result(
                surface=surface,
                command="memory export",
                action="export",
                status_text="Memory export usage shown.",
            )
        return MemoryCommandPlan(
            command=f"memory export {export_format}",
            action="export",
            export_format=export_format,
            detail_mode="full",
            success_status="Memory export prepared.",
            failure_summary="export failed",
            failure_detail_prefix="Memory export failed: ",
            failure_status="Memory export failed.",
            summary_fallback="memory export prepared",
        )

    if action == "consolidated":
        consolidated_action = normalized_args[1].lower() if len(normalized_args) >= 2 else "show"
        if consolidated_action == "show":
            if len(normalized_args) > 2:
                return _memory_usage_result(
                    surface=surface,
                    command="memory consolidated",
                    action="consolidated",
                    status_text="Memory consolidated usage shown.",
                )
            return MemoryCommandPlan(
                command="memory consolidated",
                action="consolidated_show",
                detail_mode="full",
                success_status="Consolidated memory shown.",
                failure_summary="consolidated failed",
                failure_detail_prefix="Consolidated memory view failed: ",
                failure_status="Consolidated memory view failed.",
                summary_fallback="consolidated memory shown",
            )
        if consolidated_action == "search":
            query = " ".join(normalized_args[2:]).strip() if len(normalized_args) >= 3 else ""
            if not query:
                return _memory_usage_result(
                    surface=surface,
                    command="memory consolidated",
                    action="consolidated",
                    status_text="Memory consolidated usage shown.",
                )
            return MemoryCommandPlan(
                command=f"memory consolidated search {query}",
                action="consolidated_search",
                query=query,
                detail_mode="full",
                success_status="Consolidated memory matches shown.",
                failure_summary="consolidated search failed",
                failure_detail_prefix="Consolidated memory search failed: ",
                failure_status="Consolidated memory search failed.",
                summary_fallback="consolidated memory matches shown",
            )
        return _memory_unknown_action_result(
            surface=surface,
            command="memory consolidated",
            action=consolidated_action,
            fallback_action="consolidated",
            status_text="Unknown memory consolidated action.",
        )

    if action == "profile":
        query = " ".join(normalized_args[1:]).strip() if len(normalized_args) > 1 else ""
        return MemoryCommandPlan(
            command="memory profile" + (f" {query}" if query else ""),
            action="profile",
            query=query or None,
            detail_mode="full",
            success_status="Global profile shown.",
            failure_summary="profile failed",
            failure_detail_prefix="Global profile view failed: ",
            failure_status="Global profile view failed.",
            summary_fallback="global profile shown",
        )

    if action == "notes":
        query = " ".join(normalized_args[1:]).strip() if len(normalized_args) > 1 else ""
        return MemoryCommandPlan(
            command="memory notes" + (f" {query}" if query else ""),
            action="notes",
            query=query or None,
            detail_mode="full",
            success_status="Workspace durable notes shown.",
            failure_summary="notes failed",
            failure_detail_prefix="Workspace durable notes view failed: ",
            failure_status="Workspace durable notes view failed.",
            summary_fallback="workspace durable notes shown",
        )

    if action == "daily":
        if len(normalized_args) != 2:
            return _memory_usage_result(
                surface=surface,
                command="memory daily",
                action="daily",
                status_text="Memory daily usage shown.",
            )
        day = _safe_text(normalized_args[1])
        return MemoryCommandPlan(
            command=f"memory daily {day}",
            action="daily",
            day=day or None,
            detail_mode="full",
            success_status="Workspace daily memory shown.",
            failure_summary="daily failed",
            failure_detail_prefix="Workspace daily memory view failed: ",
            failure_status="Workspace daily memory view failed.",
            summary_fallback="workspace daily memory shown",
        )

    if action == "shared":
        shared_action = normalized_args[1].lower() if len(normalized_args) >= 2 else "list"
        selector = _safe_text(normalized_args[2]) if len(normalized_args) >= 3 else ""
        if shared_action == "list":
            if len(normalized_args) > 2:
                return _memory_usage_result(
                    surface=surface,
                    command="memory shared",
                    action="shared",
                    status_text="Memory shared usage shown.",
                )
            return MemoryCommandPlan(
                command="memory shared list",
                action="shared_list",
                detail_mode="full",
                success_status="Workspace-shared runtime memory list shown.",
                failure_summary="shared list failed",
                failure_detail_prefix="Workspace-shared runtime memory list failed: ",
                failure_status="Workspace-shared runtime memory list failed.",
                summary_fallback="workspace-shared runtime memory listed",
            )
        if shared_action == "show":
            if len(normalized_args) > 3:
                return _memory_usage_result(
                    surface=surface,
                    command="memory shared",
                    action="shared",
                    status_text="Memory shared usage shown.",
                )
            return MemoryCommandPlan(
                command="memory shared show",
                action="shared_show",
                engram_id=selector or None,
                detail_mode="full",
                success_status="Workspace-shared runtime memory entry shown.",
                failure_summary="shared show failed",
                failure_detail_prefix="Workspace-shared runtime memory entry failed: ",
                failure_status="Workspace-shared runtime memory entry failed.",
                summary_fallback="workspace-shared runtime memory entry shown",
                metadata_builder=lambda result: (
                    {"engram_id": _safe_text(result.get("engram_id"))}
                    if _safe_text(result.get("engram_id"))
                    else {}
                ),
            )
        if shared_action == "clear":
            if len(normalized_args) > 2:
                return _memory_usage_result(
                    surface=surface,
                    command="memory shared",
                    action="shared",
                    status_text="Memory shared usage shown.",
                )
            return MemoryCommandPlan(
                command="memory shared clear",
                action="shared_clear",
                detail_mode="full",
                success_status="Workspace-shared runtime memory cleared.",
                failure_summary="shared clear failed",
                failure_detail_prefix="Workspace-shared runtime memory clear failed: ",
                failure_status="Workspace-shared runtime memory clear failed.",
                summary_fallback="workspace-shared runtime memory cleared",
                requires_idle_local_runtime=True,
                is_mutation=True,
            )
        return _memory_unknown_action_result(
            surface=surface,
            command="memory shared",
            action=shared_action,
            fallback_action="shared",
            status_text="Unknown memory shared action.",
        )

    if action == "runtime":
        if len(normalized_args) > 1:
            return _memory_usage_result(
                surface=surface,
                command="memory runtime",
                action="runtime",
                status_text="Memory runtime usage shown.",
            )
        return MemoryCommandPlan(
            command="memory runtime",
            action="runtime",
            detail_mode="full",
            success_status="Runtime task memory shown.",
            failure_summary="runtime failed",
            failure_detail_prefix="Runtime task memory inspection failed: ",
            failure_status="Runtime task memory inspection failed.",
            summary_fallback=runtime_summary_fallback,
        )

    if action == "refresh":
        if len(normalized_args) > 1:
            return _memory_usage_result(
                surface=surface,
                command="memory refresh",
                action="refresh",
                status_text="Memory refresh usage shown.",
            )
        return MemoryCommandPlan(
            command="memory refresh",
            action="refresh",
            detail_mode="full",
            success_status="Memory refresh completed.",
            failure_summary="refresh failed",
            failure_detail_prefix="Memory refresh failed: ",
            failure_status="Memory refresh failed.",
            summary_fallback="memory refreshed",
            requires_idle_local_runtime=True,
            is_mutation=True,
        )

    if action == "promote":
        target = normalized_args[1].lower() if len(normalized_args) >= 2 else ""
        engram_id = _safe_text(normalized_args[2]) if len(normalized_args) >= 3 else ""
        if target not in {"shared", "note", "profile"}:
            return _memory_usage_result(
                surface=surface,
                command="memory promote",
                action="promote",
                status_text="Memory promote usage shown.",
            )
        promote_action = {
            "shared": "promote_shared",
            "note": "promote_note",
            "profile": "promote_profile",
        }[target]
        return MemoryCommandPlan(
            command=f"memory promote {target}",
            action=promote_action,
            engram_id=engram_id or None,
            detail_mode="full",
            success_status=f"Memory promoted to {target}.",
            failure_summary="promotion failed",
            failure_detail_prefix="Memory promotion failed: ",
            failure_status="Memory promotion failed.",
            summary_fallback=f"runtime memory promoted to {target}",
            metadata_builder=lambda result: (
                {"engram_id": _safe_text(result.get("engram_id"))}
                if _safe_text(result.get("engram_id"))
                else {}
            ),
            requires_idle_local_runtime=True,
            is_mutation=True,
        )

    if action == "save":
        target = normalized_args[1].lower() if len(normalized_args) >= 2 else ""
        content = " ".join(normalized_args[2:]).strip() if len(normalized_args) >= 3 else ""
        if target not in {"note", "profile"}:
            return _memory_usage_result(
                surface=surface,
                command="memory save",
                action="save",
                status_text="Memory save usage shown.",
            )
        save_action = "save_note" if target == "note" else "save_profile"
        return MemoryCommandPlan(
            command=f"memory save {target}",
            action=save_action,
            content=content or None,
            detail_mode="full",
            success_status=f"Memory saved to {target}.",
            failure_summary="save failed",
            failure_detail_prefix="Memory save failed: ",
            failure_status="Memory save failed.",
            summary_fallback=f"memory saved to {target}",
            requires_idle_local_runtime=True,
            is_mutation=True,
        )

    return _memory_unknown_action_result(
        surface=surface,
        command="memory",
        action=action,
        fallback_action=None,
        status_text="Unknown memory action.",
    )


def resolve_catalog_model_use_request(
    *,
    surface: str,
    providers: Sequence[dict[str, Any]],
    args: Sequence[str],
) -> CatalogModelUseRequest | CommandExecutionResult:
    """Validate and resolve one `/model use` request against a provider catalog snapshot."""

    if len(args) < 3:
        return CommandExecutionResult(
            command="model use",
            summary="usage",
            details=build_command_usage_text(surface, "model", action="use"),
            status_text="Model use requires provider_id and model_id.",
            kind="usage",
        )

    normalized_provider_id = _safe_text(args[1])
    normalized_model_id = _safe_text(args[2])
    if not normalized_provider_id or not normalized_model_id:
        return CommandExecutionResult(
            command="model use",
            summary="usage",
            details=build_command_usage_text(surface, "model", action="use"),
            status_text="Model use requires provider_id and model_id.",
            kind="usage",
        )

    matched_provider: dict[str, Any] | None = None
    for provider in providers:
        if _safe_text(provider.get("provider_id")) == normalized_provider_id:
            matched_provider = provider
            break

    if matched_provider is None:
        message = f"Provider not found: {normalized_provider_id}"
        return CommandExecutionResult(
            command="model use",
            summary="provider not found",
            details=message,
            status_text=message,
            kind="error",
        )

    models = matched_provider.get("models")
    if not isinstance(models, Sequence):
        message = f"Model not found in {normalized_provider_id}: {normalized_model_id}"
        return CommandExecutionResult(
            command="model use",
            summary="model not found",
            details=message,
            status_text=message,
            kind="error",
        )

    for model in models:
        if not isinstance(model, dict):
            continue
        if _safe_text(model.get("model_id")) != normalized_model_id:
            continue
        source = _safe_text(matched_provider.get("source")) or "custom"
        return CatalogModelUseRequest(
            identity=(source, normalized_provider_id, normalized_model_id),
            provider_id=normalized_provider_id,
            model_id=normalized_model_id,
        )

    message = f"Model not found in {normalized_provider_id}: {normalized_model_id}"
    return CommandExecutionResult(
        command="model use",
        summary="model not found",
        details=message,
        status_text=message,
        kind="error",
    )


class LocalOperatorCommandService:
    """Shared execution service for local operator commands across terminal surfaces."""

    def __init__(
        self,
        *,
        config_loader: Callable[[], Any],
        mcp_cleanup: Callable[[], Awaitable[None] | None],
        mcp_snapshot_loader: Callable[[Any], Any] = collect_mcp_operator_snapshot,
        mcp_status_formatter: Callable[[Any], str] = format_mcp_status,
        mcp_server_list_formatter: Callable[[Any], str] = format_mcp_server_list,
    ) -> None:
        self._config_loader = config_loader
        self._mcp_cleanup = mcp_cleanup
        self._mcp_snapshot_loader = mcp_snapshot_loader
        self._mcp_status_formatter = mcp_status_formatter
        self._mcp_server_list_formatter = mcp_server_list_formatter
        self._memory_commands = MemoryCommandService()
        self._context_commands = ContextCommandService()
        self._skill_commands = SkillCommandService()
        self._mcp_commands = McpCommandService(
            load_config=self._config_loader,
            snapshot_loader=self._mcp_snapshot_loader,
            status_formatter=self._mcp_status_formatter,
            server_list_formatter=self._mcp_server_list_formatter,
        )

    def execute_sandbox_status(
        self,
        *,
        surface: str,
        action: str,
        args: list[str],
        diagnostics: dict[str, Any],
    ) -> CommandExecutionResult:
        normalized_action = _safe_text(action).lower() or "status"
        if normalized_action != "status" or len(args) > 1:
            return CommandExecutionResult(
                command="sandbox",
                summary="usage",
                details=build_command_usage_text(surface, "sandbox", action="status"),
                status_text="Sandbox status usage displayed.",
                kind="usage",
            )
        return CommandExecutionResult(
            command="sandbox status",
            summary=compact_sandbox_summary(diagnostics),
            details=format_sandbox_status(diagnostics),
            status_text="Sandbox status shown.",
            payload={"diagnostics": diagnostics},
        )

    def execute_memory_action(
        self,
        *,
        workspace: Path,
        session_id: str,
        diagnostics_loader: Callable[[], dict[str, Any]],
        action: str,
        engram_id: str | None = None,
        content: str | None = None,
        query: str | None = None,
        day: str | None = None,
        export_format: str | None = None,
        detail_mode: str = "full",
        prepared_context: dict[str, Any] | None = None,
    ) -> CommandExecutionResult:
        request = MemoryCommandRequest(
            action=action,
            engram_id=engram_id,
            content=content,
            query=query,
            day=day,
            export_format=export_format,
            detail_mode=detail_mode,
        )
        try:
            outcome = self._memory_commands.execute(
                workspace_dir=workspace,
                session_id=session_id,
                diagnostics_loader=diagnostics_loader,
                command=request,
                prepared_context=prepared_context,
            )
        except MemoryCommandError as exc:
            raise ValueError(exc.detail) from exc

        payload = {"memory_diagnostics": outcome.memory_diagnostics}
        payload.update(outcome.payload)
        return CommandExecutionResult(
            command=outcome.command,
            summary=outcome.summary,
            details=outcome.details,
            status_text=outcome.status_text,
            payload=payload,
        )

        raise ValueError(f"Unsupported session memory action: {action}")

    def execute_skill(
        self,
        *,
        surface: str,
        workspace: Path,
        action: str,
        args: list[str],
        raw_text: str = "",
        agent: Any | None = None,
        config: Any | None = None,
        parsed_request: SkillCommandRequest | None = None,
    ) -> CommandExecutionResult:
        prepared_request = parsed_request or self.prepare_skill_request(
            surface=surface,
            action=action,
            args=args,
            raw_text=raw_text,
        )
        if isinstance(prepared_request, CommandExecutionResult):
            return prepared_request

        normalized_action = _safe_text(prepared_request.action).lower() or "list"
        parsed_command = prepared_request
        active_config = config
        if active_config is None:
            active_config = self._config_loader()

        try:
            prepared = self._skill_commands.prepare(
                workspace_dir=workspace,
                command=parsed_command,
                agent=agent,
                config=active_config,
            )
        except SkillCommandError as exc:
            return self._local_skill_error_result(
                action=normalized_action,
                command=parsed_command,
                detail=exc.detail,
                status_code=exc.status_code,
            )
        except Exception as exc:
            return CommandExecutionResult(
                command="skill",
                summary="policy unavailable",
                details=f"Workspace skill policy unavailable: {exc}",
                status_text="Workspace skill policy unavailable.",
                kind="error",
            )

        if prepared.mutation is None:
            payload = dict(prepared.result or {})
            payload["policy"] = self._safe_local_skill_policy(
                workspace,
                fallback=payload.get("policy"),
            )
            return self._local_skill_prepared_result(
                action=normalized_action,
                command=parsed_command,
                status=prepared.status,
                payload=payload,
            )

        payload = self._skill_commands.build_mutation_result(
            workspace_dir=workspace,
            mutation=prepared.mutation,
        )
        payload["policy"] = (
            prepared.mutation.updated_policy
            if prepared.mutation.action != "refresh"
            else self._safe_local_skill_policy(workspace, fallback=payload.get("policy"))
        )
        return self._local_skill_mutation_result(
            command=parsed_command,
            mutation=prepared.mutation.action,
            payload=payload,
        )

    def prepare_skill_request(
        self,
        *,
        surface: str,
        action: str,
        args: Sequence[str],
        raw_text: str = "",
    ) -> SkillCommandRequest | CommandExecutionResult:
        normalized_action = _safe_text(action).lower() or "list"
        if normalized_action not in SUPPORTED_SKILL_ACTIONS:
            return CommandExecutionResult(
                command="skill",
                summary="unknown action",
                details=build_unknown_action_text(
                    surface,
                    "skill",
                    normalized_action,
                    fallback=build_command_usage_text(surface, "skill"),
                ),
                status_text="Unknown skill action.",
                kind="error",
            )

        return self._parse_local_skill_request(
            surface=surface,
            action=normalized_action,
            args=args,
            raw_text=raw_text,
        )

    def format_skill_command_name(
        self,
        command: SkillCommandRequest,
        *,
        fallback_action: str | None = None,
    ) -> str:
        return self._local_skill_command_name(
            command,
            fallback_action=_safe_text(fallback_action) or _safe_text(command.action) or "skill",
        )

    def _parse_local_skill_request(
        self,
        *,
        surface: str,
        action: str,
        args: Sequence[str],
        raw_text: str,
    ) -> SkillCommandRequest | CommandExecutionResult:
        normalized_args = list(args or [])
        if action in {"list", "active", "reset", "refresh"} and len(normalized_args) > 1:
            return self._local_skill_usage_result(surface=surface, action=action)

        if action == "show":
            skill_name = " ".join(normalized_args[1:]).strip()
            if not skill_name:
                return self._local_skill_usage_result(surface=surface, action=action)
            return SkillCommandRequest(action=action, skill_name=skill_name)

        if action == "search":
            query = " ".join(normalized_args[1:]).strip()
            if not query:
                return self._local_skill_usage_result(surface=surface, action=action)
            return SkillCommandRequest(action=action, query=query)

        if action == "install":
            source_path = (
                raw_text[len("skill install") :].strip()
                if raw_text.lower().startswith("skill install")
                else " ".join(normalized_args[1:]).strip()
            )
            if not source_path:
                return self._local_skill_usage_result(surface=surface, action=action)
            return SkillCommandRequest(action=action, path=source_path)

        if action in {"uninstall", "rollback", "enable", "disable"}:
            skill_name = " ".join(normalized_args[1:]).strip()
            if not skill_name:
                return self._local_skill_usage_result(surface=surface, action=action)
            return SkillCommandRequest(action=action, skill_name=skill_name)

        if action == "mode":
            requested_mode = _safe_text(normalized_args[1]) if len(normalized_args) > 1 else ""
            if not requested_mode or len(normalized_args) > 2:
                return self._local_skill_usage_result(surface=surface, action=action)
            return SkillCommandRequest(action=action, mode=requested_mode)

        return SkillCommandRequest(action=action)

    def _local_skill_usage_result(
        self,
        *,
        surface: str,
        action: str,
    ) -> CommandExecutionResult:
        status_text = {
            "list": "Skill list usage shown.",
            "active": "Skill active usage displayed.",
            "show": "Skill show usage displayed.",
            "search": "Skill search usage displayed.",
            "install": "Skill install usage displayed.",
            "uninstall": "Skill uninstall usage displayed.",
            "rollback": "Skill rollback usage displayed.",
            "mode": "Skill mode usage displayed.",
            "enable": "Skill enable usage displayed.",
            "disable": "Skill disable usage displayed.",
            "reset": "Skill reset usage displayed.",
            "refresh": "Skill refresh usage displayed.",
        }.get(action, "Skill usage shown.")
        command_name = f"skill {action}".strip()
        return CommandExecutionResult(
            command=command_name,
            summary="usage",
            details=build_command_usage_text(surface, "skill", action=action),
            status_text=status_text,
            kind="usage",
        )

    def _local_skill_prepared_result(
        self,
        *,
        action: str,
        command: SkillCommandRequest,
        status: str,
        payload: dict[str, Any],
    ) -> CommandExecutionResult:
        summary = str(payload.get("summary") or "")
        details = str(payload.get("details") or "")
        if status == "disabled":
            return CommandExecutionResult(
                command=self._local_skill_command_name(command, fallback_action=action),
                summary=summary or "disabled",
                details=details or "Skill support is disabled in the active configuration.",
                status_text="Skill support is disabled.",
                kind="error",
                payload=payload,
            )
        if status == "unavailable":
            return CommandExecutionResult(
                command=self._local_skill_command_name(command, fallback_action=action),
                summary=summary or "catalog unavailable",
                details=details or "Skill catalog unavailable.",
                status_text="Skill catalog unavailable.",
                kind="error",
                payload=payload,
            )
        if status == "not_found":
            return CommandExecutionResult(
                command=self._local_skill_command_name(command, fallback_action=action),
                summary=summary or "skill not found",
                details=details,
                status_text="Skill not found.",
                kind="error",
                payload=payload,
            )

        return CommandExecutionResult(
            command=self._local_skill_command_name(command, fallback_action=action, payload=payload),
            summary=summary,
            details=details,
            status_text=self._local_skill_status_text(action=action, payload=payload),
            payload=payload,
        )

    def _local_skill_mutation_result(
        self,
        *,
        command: SkillCommandRequest,
        mutation: str,
        payload: dict[str, Any],
    ) -> CommandExecutionResult:
        return CommandExecutionResult(
            command=self._local_skill_command_name(command, fallback_action=mutation, payload=payload),
            summary=str(payload.get("summary") or ""),
            details=str(payload.get("details") or ""),
            status_text=self._local_skill_status_text(action=mutation, payload=payload),
            payload=payload,
        )

    def _local_skill_error_result(
        self,
        *,
        action: str,
        command: SkillCommandRequest,
        detail: str,
        status_code: int,
    ) -> CommandExecutionResult:
        summary: str
        status_text: str
        if action == "install" and status_code == 404:
            summary = "source not found"
            status_text = "Skill source not found."
        elif action == "install" and status_code == 409:
            summary = "skill already exists"
            status_text = "Skill already exists."
        elif action == "install":
            summary = "install failed"
            status_text = "Workspace skill install failed."
            detail = f"Workspace skill install failed: {detail}"
        elif action == "uninstall" and status_code == 404:
            summary = "skill not found"
            status_text = "Skill not found."
        elif action == "uninstall":
            summary = "uninstall failed"
            status_text = "Workspace skill uninstall failed."
            detail = f"Workspace skill uninstall failed: {detail}"
        elif action == "rollback" and status_code == 404:
            summary = "rollback unavailable"
            status_text = "Skill rollback unavailable."
        elif action == "rollback":
            summary = "rollback failed"
            status_text = "Workspace skill rollback failed."
            detail = f"Workspace skill rollback failed: {detail}"
        elif action == "mode":
            summary = "update failed"
            status_text = "Workspace skill mode update failed."
            detail = f"Workspace skill mode update failed: {detail}"
        elif action in {"enable", "disable"} and status_code == 404:
            summary = "skill not found"
            status_text = "Skill not found."
        else:
            summary = "command failed"
            status_text = "Skill command failed."
        return CommandExecutionResult(
            command=self._local_skill_command_name(command, fallback_action=action),
            summary=summary,
            details=detail,
            status_text=status_text,
            kind="error",
        )

    def _local_skill_command_name(
        self,
        command: SkillCommandRequest,
        *,
        fallback_action: str,
        payload: dict[str, Any] | None = None,
    ) -> str:
        if command.action == "show":
            skill_name = _safe_text(payload.get("entry").name if payload and payload.get("entry") else command.skill_name)
            return f"skill show {skill_name}".strip()
        if command.action == "search":
            return f"skill search {_safe_text(command.query)}".strip()
        if command.action == "install":
            return f"skill install {_safe_text(command.path)}".strip()
        if command.action in {"uninstall", "rollback", "enable", "disable"}:
            skill_name = _safe_text(payload.get("skill_name") if payload else command.skill_name) or _safe_text(command.skill_name)
            return f"skill {command.action} {skill_name}".strip()
        if command.action == "mode":
            mode = _safe_text(payload.get("mode") if payload else command.mode) or _safe_text(command.mode)
            return f"skill mode {mode}".strip()
        resolved_action = _safe_text(command.action) or _safe_text(fallback_action)
        return f"skill {resolved_action}".strip()

    @staticmethod
    def _local_skill_status_text(
        *,
        action: str,
        payload: dict[str, Any],
    ) -> str:
        if action == "list":
            return "Skill catalog shown."
        if action == "active":
            return "Workspace skill policy shown."
        if action == "show":
            entry = payload.get("entry")
            entry_name = _safe_text(getattr(entry, "name", ""))
            return f"Showing skill {entry_name}." if entry_name else "Showing skill."
        if action == "search":
            return "Skill search completed."
        if action == "install":
            return "Workspace skill installed."
        if action == "uninstall":
            return "Workspace skill uninstalled."
        if action == "rollback":
            return "Workspace skill rolled back."
        if action == "mode":
            return "Workspace skill mode updated."
        if action in {"enable", "disable"}:
            return "Workspace skill policy updated."
        if action == "reset":
            return "Workspace skill policy reset."
        if action == "refresh":
            return "Skill catalog refreshed."
        return "Skill command completed."

    @staticmethod
    def _safe_local_skill_policy(
        workspace: Path,
        *,
        fallback: Any | None = None,
    ) -> Any | None:
        try:
            return load_workspace_skill_policy(workspace)
        except Exception:
            return fallback

    def execute_context(
        self,
        *,
        surface: str,
        action: str,
        args: list[str],
        current_policy: dict[str, Any] | None,
        prepared_context: dict[str, Any] | None = None,
        prepared_context_diagnostics: dict[str, Any] | None = None,
        session_label: str | None = None,
    ) -> CommandExecutionResult:
        normalized_action = self._context_commands.normalize_action(action) or "show"
        normalized_policy = resolve_turn_context_policy(current_policy or {})
        policy_owner = _safe_text(session_label) or "this session"

        if normalized_action == "show":
            detail_mode, usage_error = self._parse_context_show_mode(surface, args[1:])
            if usage_error:
                return CommandExecutionResult(
                    command="context show",
                    summary="usage",
                    details=usage_error,
                    status_text="Context show usage displayed.",
                    kind="usage",
                )
            details_parts = [
                format_context_policy_details(normalized_policy, include_header=True),
            ]
            if prepared_context:
                details_parts.append("")
                details_parts.append(
                    format_prepared_turn_context_details(
                        prepared_context,
                        include_header=True,
                        detail_mode=detail_mode,
                    )
                )
            return CommandExecutionResult(
                command=f"context show {detail_mode}" if detail_mode != "full" else "context show",
                summary=context_policy_summary_line(normalized_policy, include_default=True),
                details="\n".join(part for part in details_parts if part).strip(),
                status_text="Context policy shown.",
                payload={"policy": normalized_policy, "detail_mode": detail_mode},
            )

        if normalized_action == "stats":
            if len(args) > 1:
                return CommandExecutionResult(
                    command="context stats",
                    summary="usage",
                    details=build_command_usage_text(surface, "context", action="stats"),
                    status_text="Context stats usage shown.",
                    kind="usage",
                )
            return CommandExecutionResult(
                command="context stats",
                summary="prepared-context diagnostics",
                details=format_prepared_context_diagnostics(
                    prepared_context_diagnostics,
                    include_header=True,
                ),
                status_text="Context diagnostics shown.",
                payload={"policy": normalized_policy},
            )

        if normalized_action in {"include", "exclude"}:
            if len(args) < 2:
                return CommandExecutionResult(
                    command=f"context {normalized_action}",
                    summary="usage",
                    details=build_command_usage_text(surface, "context", action=normalized_action),
                    status_text="Context source list is required.",
                    kind="usage",
                )
            mutation = self._context_commands.apply_mutation(
                current_policy=normalized_policy,
                command=ContextCommandRequest(
                    action=normalized_action,
                    sources=tuple(args[1:]),
                ),
            )
            updated_policy = mutation.policy
            return CommandExecutionResult(
                command=f"context {normalized_action}",
                summary=context_policy_summary_line(updated_policy, include_default=True),
                details=format_context_policy_details(updated_policy, include_header=True),
                status_text=f"Context policy updated for {policy_owner}.",
                payload={
                    "policy": updated_policy,
                    "remote_request": mutation.remote_request,
                },
            )

        if normalized_action == "budget":
            if len(args) < 2:
                return CommandExecutionResult(
                    command="context budget",
                    summary="usage",
                    details=build_command_usage_text(surface, "context", action="budget"),
                    status_text="Context budget usage shown.",
                    kind="usage",
                )
            try:
                max_items = int(args[1])
                max_total_chars = int(args[2]) if len(args) >= 3 else None
                max_items_per_source = int(args[3]) if len(args) >= 4 else None
            except Exception:
                return CommandExecutionResult(
                    command="context budget",
                    summary="invalid number",
                    details=build_command_usage_text(surface, "context", action="budget"),
                    status_text="Context budget values must be integers.",
                    kind="error",
                )
            try:
                mutation = self._context_commands.apply_mutation(
                    current_policy=normalized_policy,
                    command=ContextCommandRequest(
                        action="budget",
                        max_items=max_items,
                        max_total_chars=max_total_chars,
                        max_items_per_source=max_items_per_source,
                    ),
                )
            except ContextCommandError:
                return CommandExecutionResult(
                    command="context budget",
                    summary="invalid number",
                    details=build_command_usage_text(surface, "context", action="budget"),
                    status_text="Context budget values must be integers.",
                    kind="error",
                )
            updated_policy = mutation.policy
            return CommandExecutionResult(
                command="context budget",
                summary=context_policy_summary_line(updated_policy, include_default=True),
                details=format_context_policy_details(updated_policy, include_header=True),
                status_text=f"Context budget updated for {policy_owner}.",
                payload={
                    "policy": updated_policy,
                    "remote_request": mutation.remote_request,
                },
            )

        if normalized_action == "reset":
            mutation = self._context_commands.apply_mutation(
                current_policy=normalized_policy,
                command=ContextCommandRequest(action="reset"),
            )
            updated_policy = mutation.policy
            return CommandExecutionResult(
                command="context reset",
                summary=context_policy_summary_line(updated_policy, include_default=True),
                details=format_context_policy_details(updated_policy, include_header=True),
                status_text=f"Context policy reset for {policy_owner}.",
                payload={
                    "policy": {},
                    "remote_request": mutation.remote_request,
                },
            )

        return CommandExecutionResult(
            command="context",
            summary="unknown action",
            details=build_unknown_action_text(
                surface,
                "context",
                normalized_action,
                fallback=build_command_usage_text(surface, "context"),
            ),
            status_text="Unknown context action.",
            kind="error",
        )

    async def execute_kb(
        self,
        *,
        surface: str,
        action: str,
        args: list[str],
        current_enabled: bool | None,
        session_label: str,
        runtime_attached: bool,
        busy: bool = False,
        toggle_callback: Callable[[bool], Awaitable[bool | None] | bool | None] | None = None,
        toggle_supported: bool = True,
        unsupported_message: str | None = None,
    ) -> CommandExecutionResult:
        normalized_action = _safe_text(action).lower() or "status"
        normalized_surface = _safe_text(surface).lower() or "tui"

        if normalized_action == "status":
            state = KnowledgeBaseControlService.status(current_enabled=current_enabled)
            if state.enabled is None:
                details = (
                    "Knowledge Base: pending default"
                    if normalized_surface == "cli"
                    else "Knowledge base state will follow the kernel default when this session starts."
                )
                return CommandExecutionResult(
                    command="kb status",
                    summary="knowledge base pending default",
                    details=details,
                    status_text="Knowledge base status is pending.",
                    payload={"enabled": None},
                )
            enabled = bool(state.enabled)
            details = (
                f"Knowledge Base: {'enabled' if enabled else 'disabled'}"
                if normalized_surface == "cli"
                else f"Knowledge base is {'enabled' if enabled else 'disabled'} for {session_label}."
            )
            return CommandExecutionResult(
                command="kb status",
                summary=state.summary,
                details=details,
                status_text=f"Knowledge base is {'enabled' if enabled else 'disabled'}.",
                payload={"enabled": enabled},
            )

        if normalized_action not in {"on", "off"}:
            return CommandExecutionResult(
                command="kb",
                summary="unknown action",
                details=build_unknown_action_text(
                    surface,
                    "kb",
                    normalized_action,
                    fallback=build_command_usage_text(surface, "kb"),
                ),
                status_text="Unknown kb action.",
                kind="error",
            )

        if busy:
            return CommandExecutionResult(
                command=f"kb {normalized_action}",
                summary="session busy",
                details=f"{session_label} is busy. Wait for the current turn to finish first.",
                status_text=f"{session_label} is busy.",
                kind="error",
            )

        if not toggle_supported:
            return CommandExecutionResult(
                command=f"kb {normalized_action}",
                summary="command failed",
                details=_safe_text(unsupported_message) or "KB toggle is not supported by the current agent.",
                status_text="Knowledge base toggle failed.",
                kind="error",
                payload={"enabled": current_enabled},
            )

        desired_enabled = normalized_action == "on"
        toggle = await KnowledgeBaseControlService.toggle(
            current_enabled=current_enabled,
            desired_enabled=desired_enabled,
            toggle_callback=toggle_callback,
        )
        enabled = toggle.effective_enabled
        if enabled == desired_enabled:
            details = (
                f"Knowledge base {'enabled' if enabled else 'disabled'} for this session"
                if normalized_surface == "cli"
                else (
                    f"Knowledge base is {'enabled' if enabled else 'disabled'} for {session_label}."
                    if runtime_attached
                    else (
                        f"Knowledge base will start {'enabled' if enabled else 'disabled'} for {session_label} "
                        "when the agent starts."
                    )
                )
            )
            return CommandExecutionResult(
                command=f"kb {normalized_action}",
                summary=KnowledgeBaseControlService.toggle_summary(
                    enabled=enabled,
                    applied=toggle.applied,
                ),
                details=details,
                status_text=f"Knowledge base {'enabled' if enabled else 'disabled'} for {session_label}.",
                payload={"enabled": enabled},
            )

        return CommandExecutionResult(
            command=f"kb {normalized_action}",
            summary="command failed",
            details=f"Knowledge base could not be switched {normalized_action} for {session_label}.",
            status_text="Knowledge base toggle failed.",
            kind="error",
            payload={"enabled": enabled},
        )

    async def execute_mcp(
        self,
        *,
        surface: str,
        action: str,
        args: list[str],
        busy: bool = False,
        busy_label: str = "session",
        reload_callback: Callable[[], Awaitable[McpReloadOutcome | tuple[bool, str] | None] | McpReloadOutcome | tuple[bool, str] | None]
        | None = None,
    ) -> CommandExecutionResult:
        normalized_action = self._mcp_commands.normalize_action(action) or "status"
        if normalized_action not in {"status", "list", "reload"}:
            return CommandExecutionResult(
                command="mcp",
                summary="unknown action",
                details=build_unknown_action_text(
                    surface,
                    "mcp",
                    normalized_action,
                    fallback=build_command_usage_text(surface, "mcp"),
                ),
                status_text="Unknown mcp action.",
                kind="error",
            )

        if len(args) > 1:
            return CommandExecutionResult(
                command=f"mcp {normalized_action}",
                summary="usage",
                details=build_command_usage_text(surface, "mcp", action=normalized_action),
                status_text=f"MCP {normalized_action} usage displayed.",
                kind="usage",
            )
        try:
            result = await self._mcp_commands.execute(
                action=normalized_action,
                busy=busy,
                cleanup_connections=self._mcp_cleanup,
                reload_callback=reload_callback,
            )
        except McpCommandError as exc:
            summary = "command failed"
            status_text = "MCP command failed."
            command_name = "mcp"
            if normalized_action == "reload" and exc.status_code == 409:
                summary = "session busy"
                status_text = f"{busy_label} is busy."
                command_name = "mcp reload"
                detail = f"{busy_label} is busy. Wait for the current turn to finish first."
            elif normalized_action == "reload":
                summary = "reload failed"
                status_text = "MCP reload failed."
                command_name = "mcp reload"
                detail = exc.detail
            elif "Failed to load config for MCP inspection" in exc.detail:
                summary = "config unavailable"
                status_text = "MCP config unavailable."
                detail = exc.detail
            else:
                detail = exc.detail
            return CommandExecutionResult(
                command=command_name,
                summary=summary,
                details=detail,
                status_text=status_text,
                kind="error",
            )

        status_text = {
            "status": "MCP status shown.",
            "list": "MCP server list shown.",
            "reload": "MCP bindings reloaded.",
        }.get(result.action, "MCP status shown.")
        payload = {
            "snapshot": result.snapshot,
            "rebuilt_runtime": bool(result.reload_outcome.rebuilt_runtime),
            "active_model_label": _safe_text(result.reload_outcome.active_model_label) or None,
        }
        return CommandExecutionResult(
            command=f"mcp {result.action}",
            summary=result.summary,
            details=result.details,
            status_text=status_text,
            payload=payload,
        )

    @staticmethod
    def _parse_context_show_mode(surface: str, parts: list[str]) -> tuple[str, str | None]:
        if not parts:
            return "full", None

        mode = _safe_text(parts[0]).lower()
        if mode not in {"brief", "full"}:
            return "full", build_command_usage_text(surface, "context", action="show")
        if len(parts) > 1:
            return "full", build_command_usage_text(surface, "context", action="show")
        return mode, None

__all__ = [
    "CommandExecutionResult",
    "ContextCommandPlan",
    "LocalOperatorCommandService",
    "MemoryCommandPlan",
    "McpReloadOutcome",
    "ModelCommandPlan",
    "prepare_context_command_plan",
    "parse_memory_show_target",
    "prepare_memory_command_plan",
    "prepare_model_command_plan",
    "resolve_catalog_model_use_request",
]
