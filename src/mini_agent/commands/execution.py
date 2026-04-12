"""Shared execution helpers for operator commands with common local semantics."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Sequence

from mini_agent.memory.diagnostics import (
    build_memory_overview_payload,
    format_consolidated_memory_details,
    format_consolidated_memory_search_details,
    format_global_profile_details,
    format_memory_diagnostics,
    format_memory_export_details,
    format_memory_overview_details,
    format_runtime_memory_entry_details,
    format_runtime_memory_preview_lines,
    format_runtime_shared_selector_help,
    format_runtime_session_selector_help,
    format_workspace_daily_details,
    format_workspace_note_details,
    memory_diagnostics_summary_line,
    resolve_runtime_shared_engram_selector,
    resolve_runtime_session_engram_selector,
)
from mini_agent.memory.knowledge_base_grounding import format_knowledge_base_grounding_lines
from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime
from mini_agent.memory.operator_actions import (
    save_operator_profile_fact,
    save_operator_workspace_note,
)
from mini_agent.memory.service import MemoryService
from mini_agent.commands.skill_support import (
    find_skill_entry,
    format_skill_detail,
    format_skill_entries,
    format_skill_install_result,
    format_skill_policy_overview,
    format_skill_rollback_result,
    format_skill_search_results,
    format_skill_uninstall_result,
    install_workspace_skill_from_path,
    load_workspace_skill_policy,
    refresh_skill_catalog_loader,
    resolve_skill_catalog_loader,
    resolve_workspace_skill_policy_store,
    rollback_workspace_skill,
    search_skill_entries,
    summarize_skill_entries,
    uninstall_workspace_skill,
)

from mini_agent.runtime.sandbox_state import compact_sandbox_summary, format_sandbox_status
from mini_agent.turn_context import (
    context_policy_summary_line,
    format_context_policy_details,
    format_prepared_context_diagnostics,
    format_prepared_turn_context_details,
    resolve_turn_context_policy,
)

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


@dataclass(slots=True)
class McpReloadOutcome:
    """Surface-specific reload outcome that can be surfaced after shared MCP execution."""

    rebuilt_runtime: bool = False
    active_model_label: str | None = None


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
        normalized_action = _safe_text(action).lower().replace("-", "_")
        normalized_engram_id = _safe_text(engram_id) or None
        normalized_content = _safe_text(content) or None
        normalized_query = _safe_text(query) or None
        normalized_day = _safe_text(day) or None
        normalized_export_format = _safe_text(export_format).lower() or None

        if normalized_action == "status":
            diagnostics = diagnostics_loader()
            summary = memory_diagnostics_summary_line(diagnostics)
            return CommandExecutionResult(
                command="memory status",
                summary=summary,
                details=(
                    f"Memory status: {summary}\n"
                    f"Workspace: {_safe_text(diagnostics.get('workspace_anchor_dir')) or _safe_text(diagnostics.get('workspace_dir'))}"
                ),
                status_text="Memory status shown.",
                payload={"memory_diagnostics": diagnostics},
            )

        if normalized_action == "show":
            diagnostics = diagnostics_loader()
            return CommandExecutionResult(
                command="memory show" if detail_mode == "full" else f"memory show {detail_mode}",
                summary=memory_diagnostics_summary_line(diagnostics),
                details=format_memory_diagnostics(
                    diagnostics,
                    include_header=True,
                    detail_mode=detail_mode,
                ),
                status_text="Memory diagnostics shown.",
                payload={"memory_diagnostics": diagnostics},
            )

        if normalized_action == "overview":
            diagnostics = diagnostics_loader()
            memory = MemoryService(workspace)
            overview = build_memory_overview_payload(
                memory=memory,
                diagnostics=diagnostics,
                exclude_session_id=session_id,
            )
            return CommandExecutionResult(
                command="memory overview",
                summary="memory overview shown",
                details="\n".join(format_memory_overview_details(overview)).strip(),
                status_text="Memory overview shown.",
                payload={
                    "memory_diagnostics": diagnostics,
                    "overview": overview,
                },
            )

        if normalized_action == "export":
            diagnostics = diagnostics_loader()
            memory = MemoryService(workspace)
            export_payload = memory.export_notes(format=normalized_export_format or "jsonl")
            summary = memory.summary()
            export_name = normalized_export_format or "jsonl"
            return CommandExecutionResult(
                command=f"memory export {export_name}",
                summary="memory export prepared",
                details="\n".join(
                    format_memory_export_details(
                        export_payload,
                        workspace_dir=summary.workspace_dir,
                        memory_root=summary.memory_root,
                        long_term_file=summary.long_term_file,
                        daily_dir=summary.daily_dir,
                    )
                ).strip(),
                status_text="Memory export prepared.",
                payload={
                    "memory_diagnostics": diagnostics,
                    "export": export_payload,
                },
            )

        if normalized_action == "session_show":
            diagnostics = diagnostics_loader()
            if not normalized_engram_id:
                raise ValueError(
                    format_runtime_session_selector_help(
                        diagnostics,
                        usage_command="/memory show <selector>",
                    )
                )
            resolved_engram_id = resolve_runtime_session_engram_selector(diagnostics, normalized_engram_id)
            if not resolved_engram_id:
                raise ValueError(
                    format_runtime_session_selector_help(
                        diagnostics,
                        usage_command="/memory show <selector>",
                    )
                )
            runtime = WorkspaceMemoriaRuntime(workspace)
            entry = runtime.get_namespace_entry(
                WorkspaceMemoriaRuntime.session_namespace(session_id),
                engram_id=resolved_engram_id,
            )
            if entry is None:
                raise ValueError(
                    format_runtime_session_selector_help(
                        diagnostics,
                        usage_command="/memory show <selector>",
                    )
                )
            return CommandExecutionResult(
                command=f"memory show {normalized_engram_id}",
                summary="session runtime memory entry shown",
                details="\n".join(
                    [
                        "Session Runtime Memory",
                        *format_runtime_memory_entry_details(entry),
                    ]
                ).strip(),
                status_text="Runtime memory entry shown.",
                payload={
                    "memory_diagnostics": diagnostics,
                    "engram_id": resolved_engram_id,
                    "entry": entry,
                },
            )

        if normalized_action in {"runtime", "list"}:
            diagnostics = diagnostics_loader()
            runtime = diagnostics.get("runtime_task_memory") if isinstance(diagnostics.get("runtime_task_memory"), dict) else {}
            details_lines = [
                "Session Runtime Memory" if normalized_action == "list" else "Runtime Task Memory",
                f"Session namespace: {_safe_text(runtime.get('session_namespace')) or 'n/a'}",
                f"Session entries: {int(runtime.get('session_count') or 0)}",
                f"Shared namespace: {_safe_text(runtime.get('workspace_shared_namespace')) or 'n/a'}",
                f"Shared entries: {int(runtime.get('shared_count') or 0)}",
            ]
            session_preview = runtime.get("session_preview") if isinstance(runtime.get("session_preview"), list) else []
            shared_preview = runtime.get("shared_preview") if isinstance(runtime.get("shared_preview"), list) else []
            if session_preview:
                details_lines.append("")
                details_lines.append("Session Preview")
                details_lines.extend(
                    format_runtime_memory_preview_lines(
                        session_preview,
                        limit=5,
                        include_latest_hint=True,
                        latest_hint_label="session preview entry",
                    )
                )
            if shared_preview:
                details_lines.append("")
                details_lines.append("Shared Preview")
                details_lines.extend(format_runtime_memory_preview_lines(shared_preview, limit=5))
            return CommandExecutionResult(
                command=f"memory {normalized_action}",
                summary=memory_diagnostics_summary_line(diagnostics),
                details="\n".join(details_lines).strip(),
                status_text="Runtime memory shown." if normalized_action == "runtime" else "Runtime memory list shown.",
                payload={"memory_diagnostics": diagnostics},
            )

        if normalized_action == "shared_list":
            diagnostics = diagnostics_loader()
            runtime = diagnostics.get("runtime_task_memory") if isinstance(diagnostics.get("runtime_task_memory"), dict) else {}
            details_lines = [
                "Workspace-Shared Runtime Memory",
                f"Shared namespace: {_safe_text(runtime.get('workspace_shared_namespace')) or 'n/a'}",
                f"Shared entries: {int(runtime.get('shared_count') or 0)}",
            ]
            shared_preview = runtime.get("shared_preview") if isinstance(runtime.get("shared_preview"), list) else []
            if shared_preview:
                details_lines.append("")
                details_lines.append("Shared Preview")
                details_lines.extend(
                    format_runtime_memory_preview_lines(
                        shared_preview,
                        limit=5,
                        include_latest_hint=True,
                        latest_hint_label="shared preview entry",
                    )
                )
            return CommandExecutionResult(
                command="memory shared list",
                summary=memory_diagnostics_summary_line(diagnostics),
                details="\n".join(details_lines).strip(),
                status_text="Workspace-shared runtime memory list shown.",
                payload={"memory_diagnostics": diagnostics},
            )

        if normalized_action == "shared_show":
            diagnostics = diagnostics_loader()
            if not normalized_engram_id:
                raise ValueError(
                    format_runtime_shared_selector_help(
                        diagnostics,
                        usage_command="/memory shared show <selector>",
                    )
                )
            resolved_engram_id = resolve_runtime_shared_engram_selector(diagnostics, normalized_engram_id)
            if not resolved_engram_id:
                raise ValueError(
                    format_runtime_shared_selector_help(
                        diagnostics,
                        usage_command="/memory shared show <selector>",
                    )
                )
            runtime = WorkspaceMemoriaRuntime(workspace)
            entry = runtime.get_workspace_shared_entry(engram_id=resolved_engram_id)
            if entry is None:
                raise ValueError(
                    format_runtime_shared_selector_help(
                        diagnostics,
                        usage_command="/memory shared show <selector>",
                    )
                )
            return CommandExecutionResult(
                command="memory shared show" + (f" {normalized_engram_id}" if normalized_engram_id else ""),
                summary="workspace-shared runtime memory entry shown",
                details="\n".join(
                    [
                        "Workspace-Shared Runtime Memory",
                        *format_runtime_memory_entry_details(entry),
                    ]
                ).strip(),
                status_text="Workspace-shared runtime memory entry shown.",
                payload={
                    "memory_diagnostics": diagnostics,
                    "engram_id": resolved_engram_id,
                    "entry": entry,
                },
            )

        if normalized_action == "profile":
            diagnostics = diagnostics_loader()
            memory = MemoryService(workspace)
            profile = memory.profile()
            matches = memory.search_profile(query=normalized_query, limit=10) if normalized_query else None
            return CommandExecutionResult(
                command="memory profile" + (f" {normalized_query}" if normalized_query else ""),
                summary="global profile matches shown" if normalized_query else "global profile shown",
                details="\n".join(
                    format_global_profile_details(
                        profile,
                        query=normalized_query,
                        matches=matches,
                        limit=20,
                    )
                ).strip(),
                status_text="Global profile shown.",
                payload={
                    "memory_diagnostics": diagnostics,
                    "profile": profile,
                    "matches": matches or [],
                    "query": normalized_query,
                },
            )

        if normalized_action == "consolidated_show":
            diagnostics = diagnostics_loader()
            memory = MemoryService(workspace)
            refresh_status = memory.consolidated_refresh_status(exclude_session_id=session_id)
            snapshot = memory.consolidated_snapshot()
            snapshot["memory_file"] = refresh_status.get("memory_file")
            return CommandExecutionResult(
                command="memory consolidated",
                summary="consolidated memory shown",
                details="\n".join(
                    format_consolidated_memory_details(
                        snapshot,
                        refresh_status=refresh_status,
                        limit=20,
                    )
                ).strip(),
                status_text="Consolidated memory shown.",
                payload={
                    "memory_diagnostics": diagnostics,
                    "snapshot": snapshot,
                },
            )

        if normalized_action == "consolidated_search":
            if not normalized_query:
                raise ValueError("Usage: /memory consolidated search <query>")
            diagnostics = diagnostics_loader()
            memory = MemoryService(workspace)
            refresh_status = memory.consolidated_refresh_status(exclude_session_id=session_id)
            payload = memory.search_relevant_consolidated_memory(
                query=normalized_query,
                top_k=10,
            )
            return CommandExecutionResult(
                command=f"memory consolidated search {normalized_query}",
                summary="consolidated memory matches shown",
                details="\n".join(
                    format_consolidated_memory_search_details(
                        payload,
                        refresh_status=refresh_status,
                        limit=10,
                    )
                ).strip(),
                status_text="Consolidated memory search shown.",
                payload={
                    "memory_diagnostics": diagnostics,
                    "search": payload,
                    "query": normalized_query,
                },
            )

        if normalized_action == "notes":
            diagnostics = diagnostics_loader()
            memory = MemoryService(workspace)
            summary = memory.summary()
            if normalized_query:
                ranked = memory.rank_workspace_notes(query=normalized_query)[:10]
                note_items = [
                    {
                        **memory.note_to_dict(note),
                        "score": score,
                    }
                    for note, score in ranked
                ]
                details = format_workspace_note_details(
                    workspace_dir=summary.workspace_dir,
                    memory_root=summary.memory_root,
                    long_term_file=summary.long_term_file,
                    daily_dir=summary.daily_dir,
                    categories=summary.categories,
                    notes=note_items,
                    query=normalized_query,
                    total=len(note_items),
                )
                return CommandExecutionResult(
                    command=f"memory notes {normalized_query}",
                    summary="workspace durable note matches shown",
                    details="\n".join(details).strip(),
                    status_text="Workspace durable notes shown.",
                    payload={
                        "memory_diagnostics": diagnostics,
                        "items": note_items,
                        "query": normalized_query,
                    },
                )
            note_items = [memory.note_to_dict(note) for note in memory.search_notes(query="", limit=10)]
            details = format_workspace_note_details(
                workspace_dir=summary.workspace_dir,
                memory_root=summary.memory_root,
                long_term_file=summary.long_term_file,
                daily_dir=summary.daily_dir,
                categories=summary.categories,
                notes=note_items,
                total=summary.notes_count,
            )
            return CommandExecutionResult(
                command="memory notes",
                summary="workspace durable notes shown",
                details="\n".join(details).strip(),
                status_text="Workspace durable notes shown.",
                payload={
                    "memory_diagnostics": diagnostics,
                    "items": note_items,
                },
            )

        if normalized_action == "daily":
            if not normalized_day:
                raise ValueError("Usage: /memory daily <YYYY-MM-DD>")
            diagnostics = diagnostics_loader()
            memory = MemoryService(workspace)
            snapshot = memory.daily_snapshot(day=normalized_day)
            note_items = [memory.note_to_dict(note) for note in snapshot.notes]
            return CommandExecutionResult(
                command=f"memory daily {snapshot.day}",
                summary="workspace daily memory shown",
                details="\n".join(
                    format_workspace_daily_details(
                        workspace_dir=snapshot.workspace_dir,
                        day=snapshot.day,
                        path=snapshot.path,
                        notes=note_items,
                        note_count=snapshot.note_count,
                    )
                ).strip(),
                status_text="Workspace daily memory shown.",
                payload={
                    "memory_diagnostics": diagnostics,
                    "day": snapshot.day,
                    "items": note_items,
                },
            )

        if normalized_action == "refresh":
            refresh = MemoryService(workspace).refresh_consolidated_memory(exclude_session_id=session_id)
            refreshed_diagnostics = diagnostics_loader()
            summary = (
                "memory refreshed"
                if bool(refresh.get("refreshed"))
                else f"memory {str(refresh.get('reason') or 'fresh').replace('_', ' ')}"
            )
            return CommandExecutionResult(
                command="memory refresh",
                summary=summary,
                details=format_memory_diagnostics(
                    refreshed_diagnostics,
                    include_header=True,
                    detail_mode=detail_mode,
                ),
                status_text="Memory refresh completed.",
                payload={
                    "memory_diagnostics": refreshed_diagnostics,
                    "refresh": refresh,
                },
            )

        if normalized_action == "shared_clear":
            runtime = WorkspaceMemoriaRuntime(workspace)
            cleared = runtime.clear_workspace_shared_namespace()
            refreshed_diagnostics = diagnostics_loader()
            summary = (
                "workspace-shared runtime memory cleared"
                if cleared
                else "workspace-shared runtime memory already empty"
            )
            details_lines = [
                "Workspace-Shared Runtime Memory",
                f"Action: {normalized_action}",
                f"Cleared: {'yes' if cleared else 'no'}",
                "",
                format_memory_diagnostics(
                    refreshed_diagnostics,
                    include_header=True,
                    detail_mode=detail_mode,
                ),
            ]
            return CommandExecutionResult(
                command="memory shared clear",
                summary=summary,
                details="\n".join(line for line in details_lines if line is not None).strip(),
                status_text="Workspace-shared runtime memory cleared.",
                payload={
                    "memory_diagnostics": refreshed_diagnostics,
                    "cleared": cleared,
                },
            )

        if normalized_action in {"promote_shared", "promote_note", "promote_profile"}:
            diagnostics = diagnostics_loader()
            if not normalized_engram_id:
                promote_target = (
                    "shared"
                    if normalized_action == "promote_shared"
                    else "note" if normalized_action == "promote_note" else "profile"
                )
                raise ValueError(
                    format_runtime_session_selector_help(
                        diagnostics,
                        usage_command=f"/memory promote {promote_target} <selector>",
                    )
                )
            resolved_engram_id = resolve_runtime_session_engram_selector(diagnostics, normalized_engram_id)
            if not resolved_engram_id:
                promote_target = (
                    "shared"
                    if normalized_action == "promote_shared"
                    else "note" if normalized_action == "promote_note" else "profile"
                )
                raise ValueError(
                    format_runtime_session_selector_help(
                        diagnostics,
                        usage_command=f"/memory promote {promote_target} <selector>",
                    )
                )
            runtime = WorkspaceMemoriaRuntime(workspace)
            if normalized_action == "promote_shared":
                promotion = runtime.promote_session_memory_to_workspace_shared(
                    session_id=session_id,
                    engram_id=resolved_engram_id,
                )
                summary = "runtime memory promoted to workspace-shared memory"
                command = "memory promote shared"
                status_text = "Memory promoted to shared."
            elif normalized_action == "promote_note":
                promotion = runtime.promote_session_memory_to_workspace_note(
                    session_id=session_id,
                    engram_id=resolved_engram_id,
                )
                summary = "runtime memory promoted to workspace note"
                command = "memory promote note"
                status_text = "Memory promoted to note."
            else:
                promotion = runtime.promote_session_memory_to_global_profile(
                    session_id=session_id,
                    engram_id=resolved_engram_id,
                )
                summary = "runtime memory promoted to global profile"
                command = "memory promote profile"
                status_text = "Memory promoted to profile."
            refreshed_diagnostics = diagnostics_loader()
            details_lines = [
                f"Action: {normalized_action}",
            ]
            if normalized_engram_id != resolved_engram_id:
                details_lines.append(f"Selector: {normalized_engram_id}")
            details_lines.append(f"Engram: {resolved_engram_id}")
            if promotion.get("target"):
                details_lines.append(f"Target: {promotion.get('target')}")
            if promotion.get("category"):
                details_lines.append(f"Category: {promotion.get('category')}")
            if promotion.get("content"):
                details_lines.append(f"Content: {promotion.get('content')}")
            details_lines.extend(
                format_knowledge_base_grounding_lines(
                    promotion.get("knowledge_base_grounding"),
                )
            )
            details_lines.append("")
            details_lines.append(
                format_memory_diagnostics(
                    refreshed_diagnostics,
                    include_header=True,
                    detail_mode=detail_mode,
                )
            )
            return CommandExecutionResult(
                command=command,
                summary=summary,
                details="\n".join(line for line in details_lines if line is not None).strip(),
                status_text=status_text,
                payload={
                    "memory_diagnostics": refreshed_diagnostics,
                    "promotion": promotion,
                    "engram_id": resolved_engram_id,
                    "selector": normalized_engram_id,
                },
            )

        if normalized_action in {"save_note", "save_profile"}:
            if not normalized_content:
                raise ValueError(
                    f"Usage: /memory save {'note' if normalized_action == 'save_note' else 'profile'} <text>"
                )
            diagnostics = diagnostics_loader()
            prepared_sources = diagnostics.get("prepared_context_sources")
            if normalized_action == "save_note":
                saved = save_operator_workspace_note(
                    workspace_dir=workspace,
                    content=normalized_content,
                    prepared_context_sources=prepared_sources if isinstance(prepared_sources, list) else None,
                    prepared_context=prepared_context,
                )
                summary = "operator note saved to workspace memory"
                command = "memory save note"
                status_text = "Memory saved to note."
            else:
                saved = save_operator_profile_fact(
                    workspace_dir=workspace,
                    content=normalized_content,
                )
                summary = (
                    "operator profile fact saved"
                    if bool(saved.get("saved"))
                    else "operator profile fact already present"
                )
                command = "memory save profile"
                status_text = "Memory saved to profile."
            refreshed_diagnostics = diagnostics_loader()
            details_lines = [
                f"Action: {normalized_action}",
                f"Target: {saved.get('target')}",
            ]
            if saved.get("category"):
                details_lines.append(f"Category: {saved.get('category')}")
            if saved.get("content"):
                details_lines.append(f"Content: {saved.get('content')}")
            details_lines.extend(
                format_knowledge_base_grounding_lines(
                    saved.get("knowledge_base_grounding"),
                )
            )
            details_lines.append("")
            details_lines.append(
                format_memory_diagnostics(
                    refreshed_diagnostics,
                    include_header=True,
                    detail_mode=detail_mode,
                )
            )
            return CommandExecutionResult(
                command=command,
                summary=summary,
                details="\n".join(line for line in details_lines if line is not None).strip(),
                status_text=status_text,
                payload={
                    "memory_diagnostics": refreshed_diagnostics,
                    "saved": saved,
                },
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
    ) -> CommandExecutionResult:
        normalized_action = _safe_text(action).lower() or "list"

        try:
            loader = resolve_skill_catalog_loader(
                workspace_dir=workspace,
                agent=agent,
                config=config,
            )
        except Exception as exc:
            return CommandExecutionResult(
                command="skill",
                summary="catalog unavailable",
                details=f"Skill catalog unavailable: {exc}",
                status_text="Skill catalog unavailable.",
                kind="error",
            )

        if loader is None:
            return CommandExecutionResult(
                command="skill",
                summary="disabled",
                details="Skill support is disabled in the active configuration.",
                status_text="Skill support is disabled.",
                kind="error",
            )

        try:
            policy_store = resolve_workspace_skill_policy_store(workspace)
            policy = load_workspace_skill_policy(workspace)
        except Exception as exc:
            return CommandExecutionResult(
                command="skill",
                summary="policy unavailable",
                details=f"Workspace skill policy unavailable: {exc}",
                status_text="Workspace skill policy unavailable.",
                kind="error",
            )

        if normalized_action == "list":
            if len(args) > 1:
                return CommandExecutionResult(
                    command="skill list",
                    summary="usage",
                    details=build_command_usage_text(surface, "skill", action="list"),
                    status_text="Skill list usage shown.",
                    kind="usage",
                )
            entries = refresh_skill_catalog_loader(loader)
            counts = summarize_skill_entries(entries, policy)
            return CommandExecutionResult(
                command="skill list",
                summary=(
                    f"{counts['total']} skill(s) | {counts['active']} active | "
                    f"{counts['ready']} ready | {counts['blocked']} blocked | mode {policy.mode}"
                ),
                details=format_skill_entries(entries, policy),
                status_text="Skill catalog shown.",
                payload={
                    "loader": loader,
                    "entries": entries,
                    "policy": policy,
                    "counts": counts,
                },
            )

        if normalized_action == "active":
            if len(args) > 1:
                return CommandExecutionResult(
                    command="skill active",
                    summary="usage",
                    details=build_command_usage_text(surface, "skill", action="active"),
                    status_text="Skill active usage displayed.",
                    kind="usage",
                )
            entries = refresh_skill_catalog_loader(loader)
            counts = summarize_skill_entries(entries, policy)
            return CommandExecutionResult(
                command="skill active",
                summary=f"{counts['active']} active skill(s) | mode {policy.mode}",
                details=format_skill_policy_overview(policy, entries),
                status_text="Workspace skill policy shown.",
                payload={
                    "loader": loader,
                    "entries": entries,
                    "policy": policy,
                    "counts": counts,
                },
            )

        if normalized_action == "show":
            skill_name = " ".join(args[1:]).strip()
            if not skill_name:
                return CommandExecutionResult(
                    command="skill show",
                    summary="usage",
                    details=build_command_usage_text(surface, "skill", action="show"),
                    status_text="Skill show usage displayed.",
                    kind="usage",
                )
            refresh_skill_catalog_loader(loader)
            entry, details = format_skill_detail(loader, skill_name)
            if entry is None:
                return CommandExecutionResult(
                    command="skill show",
                    summary="skill not found",
                    details=details,
                    status_text="Skill not found.",
                    kind="error",
                    payload={"loader": loader, "found": False},
                )
            return CommandExecutionResult(
                command=f"skill show {entry.name}",
                summary=f"showing {entry.name}",
                details=details,
                status_text=f"Showing skill {entry.name}.",
                payload={
                    "loader": loader,
                    "found": True,
                    "entry": entry,
                },
            )

        if normalized_action == "install":
            source_path = (
                raw_text[len("skill install") :].strip()
                if raw_text.lower().startswith("skill install")
                else " ".join(args[1:]).strip()
            )
            if not source_path:
                return CommandExecutionResult(
                    command="skill install",
                    summary="usage",
                    details=build_command_usage_text(surface, "skill", action="install"),
                    status_text="Skill install usage displayed.",
                    kind="usage",
                )
            try:
                install_result = install_workspace_skill_from_path(
                    workspace_dir=workspace,
                    source_path=source_path,
                    loader=loader,
                    activate=True,
                )
            except FileNotFoundError as exc:
                return CommandExecutionResult(
                    command="skill install",
                    summary="source not found",
                    details=str(exc),
                    status_text="Skill source not found.",
                    kind="error",
                )
            except FileExistsError as exc:
                return CommandExecutionResult(
                    command="skill install",
                    summary="skill already exists",
                    details=str(exc),
                    status_text="Skill already exists.",
                    kind="error",
                )
            except Exception as exc:
                return CommandExecutionResult(
                    command="skill install",
                    summary="install failed",
                    details=f"Workspace skill install failed: {exc}",
                    status_text="Workspace skill install failed.",
                    kind="error",
                )
            entries = refresh_skill_catalog_loader(loader)
            updated_policy = install_result.policy
            return CommandExecutionResult(
                command=f"skill install {source_path}",
                summary=f"installed {install_result.skill_name}",
                details=format_skill_install_result(install_result, entries, updated_policy),
                status_text="Workspace skill installed.",
                payload={
                    "loader": loader,
                    "entries": entries,
                    "policy": updated_policy,
                    "reload_required": True,
                    "reload_reason": "workspace skill installed",
                    "mutation": "install",
                    "skill_name": install_result.skill_name,
                    "install_result": install_result,
                },
            )

        if normalized_action == "uninstall":
            skill_name = " ".join(args[1:]).strip()
            if not skill_name:
                return CommandExecutionResult(
                    command="skill uninstall",
                    summary="usage",
                    details=build_command_usage_text(surface, "skill", action="uninstall"),
                    status_text="Skill uninstall usage displayed.",
                    kind="usage",
                )
            try:
                uninstall_result = uninstall_workspace_skill(
                    workspace_dir=workspace,
                    skill_name=skill_name,
                    loader=loader,
                )
            except FileNotFoundError as exc:
                return CommandExecutionResult(
                    command="skill uninstall",
                    summary="skill not found",
                    details=str(exc),
                    status_text="Skill not found.",
                    kind="error",
                )
            except Exception as exc:
                return CommandExecutionResult(
                    command="skill uninstall",
                    summary="uninstall failed",
                    details=f"Workspace skill uninstall failed: {exc}",
                    status_text="Workspace skill uninstall failed.",
                    kind="error",
                )
            entries = refresh_skill_catalog_loader(loader)
            updated_policy = uninstall_result.policy
            return CommandExecutionResult(
                command=f"skill uninstall {skill_name}",
                summary=f"uninstalled {uninstall_result.skill_name}",
                details=format_skill_uninstall_result(uninstall_result, entries, updated_policy),
                status_text="Workspace skill uninstalled.",
                payload={
                    "loader": loader,
                    "entries": entries,
                    "policy": updated_policy,
                    "reload_required": True,
                    "reload_reason": "workspace skill uninstalled",
                    "mutation": "uninstall",
                    "skill_name": uninstall_result.skill_name,
                    "uninstall_result": uninstall_result,
                },
            )

        if normalized_action == "rollback":
            skill_name = " ".join(args[1:]).strip()
            if not skill_name:
                return CommandExecutionResult(
                    command="skill rollback",
                    summary="usage",
                    details=build_command_usage_text(surface, "skill", action="rollback"),
                    status_text="Skill rollback usage displayed.",
                    kind="usage",
                )
            try:
                rollback_result = rollback_workspace_skill(
                    workspace_dir=workspace,
                    skill_name=skill_name,
                    loader=loader,
                )
            except FileNotFoundError as exc:
                return CommandExecutionResult(
                    command="skill rollback",
                    summary="rollback unavailable",
                    details=str(exc),
                    status_text="Skill rollback unavailable.",
                    kind="error",
                )
            except Exception as exc:
                return CommandExecutionResult(
                    command="skill rollback",
                    summary="rollback failed",
                    details=f"Workspace skill rollback failed: {exc}",
                    status_text="Workspace skill rollback failed.",
                    kind="error",
                )
            entries = refresh_skill_catalog_loader(loader)
            updated_policy = rollback_result.policy
            return CommandExecutionResult(
                command=f"skill rollback {skill_name}",
                summary=f"rolled back {rollback_result.skill_name}",
                details=format_skill_rollback_result(rollback_result, entries, updated_policy),
                status_text="Workspace skill rolled back.",
                payload={
                    "loader": loader,
                    "entries": entries,
                    "policy": updated_policy,
                    "reload_required": True,
                    "reload_reason": "workspace skill rolled back",
                    "mutation": "rollback",
                    "skill_name": rollback_result.skill_name,
                    "rollback_result": rollback_result,
                },
            )

        if normalized_action == "search":
            query = " ".join(args[1:]).strip()
            if not query:
                return CommandExecutionResult(
                    command="skill search",
                    summary="usage",
                    details=build_command_usage_text(surface, "skill", action="search"),
                    status_text="Skill search usage displayed.",
                    kind="usage",
                )
            refresh_skill_catalog_loader(loader)
            hits = search_skill_entries(loader, query)
            return CommandExecutionResult(
                command=f"skill search {query}",
                summary=f"{len(hits)} match(es)" if hits else "no matches",
                details=format_skill_search_results(query, hits, policy),
                status_text="Skill search completed.",
                payload={
                    "loader": loader,
                    "policy": policy,
                    "hits": hits,
                    "query": query,
                },
            )

        if normalized_action == "mode":
            requested_mode = _safe_text(args[1]) if len(args) > 1 else ""
            if not requested_mode or len(args) > 2:
                return CommandExecutionResult(
                    command="skill mode",
                    summary="usage",
                    details=build_command_usage_text(surface, "skill", action="mode"),
                    status_text="Skill mode usage displayed.",
                    kind="usage",
                )
            try:
                updated_policy = policy_store.set_mode(requested_mode)
            except Exception as exc:
                return CommandExecutionResult(
                    command="skill mode",
                    summary="update failed",
                    details=f"Workspace skill mode update failed: {exc}",
                    status_text="Workspace skill mode update failed.",
                    kind="error",
                )
            entries = refresh_skill_catalog_loader(loader)
            return CommandExecutionResult(
                command=f"skill mode {updated_policy.mode}",
                summary=f"skill mode set to {updated_policy.mode}",
                details=format_skill_policy_overview(updated_policy, entries),
                status_text="Workspace skill mode updated.",
                payload={
                    "loader": loader,
                    "entries": entries,
                    "policy": updated_policy,
                    "reload_required": True,
                    "reload_reason": "workspace skill mode updated",
                    "mutation": "mode",
                    "mode": updated_policy.mode,
                },
            )

        if normalized_action in {"enable", "disable"}:
            skill_name = " ".join(args[1:]).strip()
            if not skill_name:
                return CommandExecutionResult(
                    command=f"skill {normalized_action}",
                    summary="usage",
                    details=build_command_usage_text(surface, "skill", action=normalized_action),
                    status_text=f"Skill {normalized_action} usage displayed.",
                    kind="usage",
                )
            entries = refresh_skill_catalog_loader(loader)
            entry = find_skill_entry(loader, skill_name)
            if entry is None:
                return CommandExecutionResult(
                    command=f"skill {normalized_action}",
                    summary="skill not found",
                    details=f"Skill not found: {skill_name}",
                    status_text="Skill not found.",
                    kind="error",
                )
            updated_policy = (
                policy_store.enable([entry.name])
                if normalized_action == "enable"
                else policy_store.disable([entry.name])
            )
            return CommandExecutionResult(
                command=f"skill {normalized_action} {entry.name}",
                summary=f"{normalized_action}d {entry.name} in workspace policy",
                details=format_skill_policy_overview(updated_policy, entries),
                status_text="Workspace skill policy updated.",
                payload={
                    "loader": loader,
                    "entries": entries,
                    "policy": updated_policy,
                    "reload_required": True,
                    "reload_reason": f"workspace skill policy {normalized_action}d",
                    "mutation": normalized_action,
                    "skill_name": entry.name,
                },
            )

        if normalized_action == "reset":
            if len(args) > 1:
                return CommandExecutionResult(
                    command="skill reset",
                    summary="usage",
                    details=build_command_usage_text(surface, "skill", action="reset"),
                    status_text="Skill reset usage displayed.",
                    kind="usage",
                )
            updated_policy = policy_store.reset()
            entries = refresh_skill_catalog_loader(loader)
            return CommandExecutionResult(
                command="skill reset",
                summary="workspace skill policy reset",
                details=format_skill_policy_overview(updated_policy, entries),
                status_text="Workspace skill policy reset.",
                payload={
                    "loader": loader,
                    "entries": entries,
                    "policy": updated_policy,
                    "reload_required": True,
                    "reload_reason": "workspace skill policy reset",
                    "mutation": "reset",
                },
            )

        if normalized_action == "refresh":
            if len(args) > 1:
                return CommandExecutionResult(
                    command="skill refresh",
                    summary="usage",
                    details=build_command_usage_text(surface, "skill", action="refresh"),
                    status_text="Skill refresh usage displayed.",
                    kind="usage",
                )
            entries = refresh_skill_catalog_loader(loader)
            refreshed_policy = load_workspace_skill_policy(workspace)
            counts = summarize_skill_entries(entries, refreshed_policy)
            return CommandExecutionResult(
                command="skill refresh",
                summary=(
                    f"{counts['total']} skill(s) refreshed | {counts['active']} active | "
                    f"{counts['ready']} ready | {counts['blocked']} blocked"
                ),
                details=format_skill_entries(entries, refreshed_policy),
                status_text="Skill catalog refreshed.",
                payload={
                    "loader": loader,
                    "entries": entries,
                    "policy": refreshed_policy,
                    "counts": counts,
                    "reload_required": True,
                    "reload_reason": "skill catalog refreshed",
                    "mutation": "refresh",
                },
            )

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
        normalized_action = _safe_text(action).lower() or "show"
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
            updated_policy = self._set_context_policy_sources(
                normalized_policy,
                field_name="include_sources" if normalized_action == "include" else "exclude_sources",
                sources=args[1:],
            )
            return CommandExecutionResult(
                command=f"context {normalized_action}",
                summary=context_policy_summary_line(updated_policy, include_default=True),
                details=format_context_policy_details(updated_policy, include_header=True),
                status_text=f"Context policy updated for {policy_owner}.",
                payload={"policy": updated_policy},
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
            updated_policy = self._set_context_policy_budget(
                normalized_policy,
                max_items=max_items,
                max_total_chars=max_total_chars,
                max_items_per_source=max_items_per_source,
            )
            return CommandExecutionResult(
                command="context budget",
                summary=context_policy_summary_line(updated_policy, include_default=True),
                details=format_context_policy_details(updated_policy, include_header=True),
                status_text=f"Context budget updated for {policy_owner}.",
                payload={"policy": updated_policy},
            )

        if normalized_action == "reset":
            updated_policy = resolve_turn_context_policy({})
            return CommandExecutionResult(
                command="context reset",
                summary=context_policy_summary_line(updated_policy, include_default=True),
                details=format_context_policy_details(updated_policy, include_header=True),
                status_text=f"Context policy reset for {policy_owner}.",
                payload={"policy": {}},
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
            if current_enabled is None:
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
            enabled = bool(current_enabled)
            details = (
                f"Knowledge Base: {'enabled' if enabled else 'disabled'}"
                if normalized_surface == "cli"
                else f"Knowledge base is {'enabled' if enabled else 'disabled'} for {session_label}."
            )
            return CommandExecutionResult(
                command="kb status",
                summary=f"knowledge base {'enabled' if enabled else 'disabled'}",
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
        if toggle_callback is None:
            enabled = desired_enabled
        else:
            raw_enabled = await _maybe_await(toggle_callback(desired_enabled))
            enabled = bool(raw_enabled) if raw_enabled is not None else bool(current_enabled)

        changed = current_enabled != enabled
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
                summary=(
                    f"knowledge base {'enabled' if changed else 'already enabled'}"
                    if enabled
                    else f"knowledge base {'disabled' if changed else 'already disabled'}"
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
        normalized_action = _safe_text(action).lower() or "status"
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

        if normalized_action == "reload" and busy:
            return CommandExecutionResult(
                command="mcp reload",
                summary="session busy",
                details=f"{busy_label} is busy. Wait for the current turn to finish first.",
                status_text=f"{busy_label} is busy.",
                kind="error",
            )

        try:
            config = self._config_loader()
        except Exception as exc:
            return CommandExecutionResult(
                command="mcp",
                summary="config unavailable",
                details=f"Failed to load config for MCP inspection: {exc}",
                status_text="MCP config unavailable.",
                kind="error",
            )

        reload_outcome = McpReloadOutcome()
        if normalized_action == "reload":
            try:
                self._mcp_snapshot_loader(config)
                await _maybe_await(self._mcp_cleanup())
                raw_outcome = await _maybe_await(reload_callback()) if reload_callback is not None else None
                reload_outcome = self._normalize_reload_outcome(raw_outcome)
            except Exception as exc:
                return CommandExecutionResult(
                    command="mcp reload",
                    summary="reload failed",
                    details=f"MCP reload failed: {exc}",
                    status_text="MCP reload failed.",
                    kind="error",
                )

        snapshot = self._mcp_snapshot_loader(config)
        status_details = self._mcp_status_formatter(snapshot)
        server_list_details = self._mcp_server_list_formatter(snapshot)

        if normalized_action == "status":
            return CommandExecutionResult(
                command="mcp status",
                summary=f"{int(getattr(snapshot, 'active_total', 0) or 0)} active server(s) | {int(getattr(snapshot, 'tool_total', 0) or 0)} tool(s)",
                details=status_details,
                status_text="MCP status shown.",
                payload={"snapshot": snapshot},
            )

        if normalized_action == "list":
            return CommandExecutionResult(
                command="mcp list",
                summary=f"{int(getattr(snapshot, 'configured_total', 0) or 0)} configured server(s) | {int(getattr(snapshot, 'active_total', 0) or 0)} active",
                details=f"{status_details}\n\n{server_list_details}",
                status_text="MCP server list shown.",
                payload={"snapshot": snapshot},
            )

        return CommandExecutionResult(
            command="mcp reload",
            summary=f"reloaded MCP | {int(getattr(snapshot, 'active_total', 0) or 0)} active server(s) | {int(getattr(snapshot, 'tool_total', 0) or 0)} tool(s)",
            details=f"{status_details}\n\n{server_list_details}",
            status_text="MCP bindings reloaded.",
            payload={
                "snapshot": snapshot,
                "rebuilt_runtime": bool(reload_outcome.rebuilt_runtime),
                "active_model_label": _safe_text(reload_outcome.active_model_label) or None,
            },
        )

    @staticmethod
    def _normalize_reload_outcome(raw: Any) -> McpReloadOutcome:
        if isinstance(raw, McpReloadOutcome):
            return raw
        if isinstance(raw, tuple) and raw:
            rebuilt = bool(raw[0])
            active_model_label = _safe_text(raw[1]) if len(raw) > 1 else ""
            return McpReloadOutcome(
                rebuilt_runtime=rebuilt,
                active_model_label=active_model_label or None,
            )
        if isinstance(raw, dict):
            return McpReloadOutcome(
                rebuilt_runtime=bool(raw.get("rebuilt_runtime")),
                active_model_label=_safe_text(raw.get("active_model_label")) or None,
            )
        return McpReloadOutcome()

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

    @staticmethod
    def _set_context_policy_sources(
        current_policy: dict[str, Any],
        *,
        field_name: str,
        sources: list[str],
    ) -> dict[str, Any]:
        normalized = resolve_turn_context_policy(current_policy or {})
        values: list[str] = []
        seen: set[str] = set()
        for item in list(sources or []):
            cleaned = _safe_text(item).lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            values.append(cleaned)
        normalized[field_name] = values
        opposite = "exclude_sources" if field_name == "include_sources" else "include_sources"
        normalized[opposite] = [
            item for item in list(normalized.get(opposite) or [])
            if item not in values
        ]
        return normalized

    @staticmethod
    def _set_context_policy_budget(
        current_policy: dict[str, Any],
        *,
        max_items: int,
        max_total_chars: int | None = None,
        max_items_per_source: int | None = None,
    ) -> dict[str, Any]:
        normalized = resolve_turn_context_policy(current_policy or {})
        normalized["max_items"] = max(1, int(max_items))
        if max_total_chars is not None:
            normalized["max_total_chars"] = max(200, int(max_total_chars))
        if max_items_per_source is not None:
            normalized["max_items_per_source"] = max(1, int(max_items_per_source))
        return normalized


__all__ = [
    "CommandExecutionResult",
    "LocalOperatorCommandService",
    "McpReloadOutcome",
    "parse_memory_show_target",
]
