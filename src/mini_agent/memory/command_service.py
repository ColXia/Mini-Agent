"""Shared `/memory` command semantics for local and runtime surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

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
from mini_agent.memory.operator_actions import (
    save_operator_profile_fact,
    save_operator_workspace_note,
)
from mini_agent.memory.runtime_backend import RuntimeMemoryBackend, WorkspaceRuntimeMemoryBackend
from mini_agent.memory.service import MemoryService
from mini_agent.utils.text import safe_text


def _safe_text(value: object) -> str:
    return safe_text(value)


SUPPORTED_MEMORY_ACTIONS = frozenset(
    {
        "status",
        "show",
        "session_show",
        "list",
        "overview",
        "export",
        "consolidated_show",
        "consolidated_search",
        "profile",
        "notes",
        "daily",
        "refresh",
        "runtime",
        "shared_list",
        "shared_show",
        "shared_clear",
        "promote_shared",
        "promote_note",
        "promote_profile",
        "save_note",
        "save_profile",
    }
)

MUTATING_MEMORY_ACTIONS = frozenset(
    {
        "refresh",
        "shared_clear",
        "promote_shared",
        "promote_note",
        "promote_profile",
        "save_note",
        "save_profile",
    }
)


@dataclass(frozen=True, slots=True)
class MemoryCommandRequest:
    action: str
    engram_id: str | None = None
    content: str | None = None
    query: str | None = None
    day: str | None = None
    export_format: str | None = None
    detail_mode: str = "full"


@dataclass(frozen=True, slots=True)
class MemoryCommandError(Exception):
    detail: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class MemoryCommandOutcome:
    command: str
    summary: str
    details: str
    status_text: str
    memory_diagnostics: dict[str, Any]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MemoryCommandService:
    runtime_memory_backend: RuntimeMemoryBackend = field(default_factory=WorkspaceRuntimeMemoryBackend)
    save_workspace_note: Callable[..., dict[str, Any]] = save_operator_workspace_note
    save_profile_fact: Callable[..., dict[str, Any]] = save_operator_profile_fact

    def validate_action(self, action: str) -> None:
        if self._normalize_action(action) not in SUPPORTED_MEMORY_ACTIONS:
            raise MemoryCommandError(f"Unsupported session memory action: {action}")

    @staticmethod
    def is_mutating_action(action: str) -> bool:
        return MemoryCommandService._normalize_action(action) in MUTATING_MEMORY_ACTIONS

    def execute(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
        diagnostics_loader: Callable[[], dict[str, Any]],
        command: MemoryCommandRequest,
        prepared_context: dict[str, Any] | None = None,
    ) -> MemoryCommandOutcome:
        normalized = self._normalize_request(command)
        self.validate_action(normalized.action)
        action = normalized.action

        if action in {"status", "show", "runtime", "list", "shared_list"}:
            diagnostics = diagnostics_loader()
            summary, details = self._session_memory_read_content(
                action=action,
                diagnostics=diagnostics,
                detail_mode=normalized.detail_mode,
            )
            return MemoryCommandOutcome(
                command=self._read_command_name(action, normalized.detail_mode),
                summary=summary,
                details=details,
                status_text=self._read_status_text(action),
                memory_diagnostics=dict(diagnostics),
            )

        if action in {
            "overview",
            "export",
            "consolidated_show",
            "consolidated_search",
            "profile",
            "notes",
            "daily",
        }:
            return self._execute_durable_read(
                workspace_dir=workspace_dir,
                session_id=session_id,
                diagnostics_loader=diagnostics_loader,
                command=normalized,
            )

        if action == "session_show":
            diagnostics = diagnostics_loader()
            resolved_engram_id = self._resolve_session_selector(
                diagnostics,
                normalized.engram_id,
                usage_command="/memory show <selector>",
            )
            entry = self.runtime_memory_backend.get_session_entry(
                workspace_dir=workspace_dir,
                session_id=session_id,
                engram_id=resolved_engram_id,
            )
            if entry is None:
                raise MemoryCommandError(
                    format_runtime_session_selector_help(
                        diagnostics,
                        usage_command="/memory show <selector>",
                    ),
                    status_code=404,
                )
            return MemoryCommandOutcome(
                command=f"memory show {normalized.engram_id}",
                summary="session runtime memory entry shown",
                details="\n".join(
                    [
                        "Session Runtime Memory",
                        *format_runtime_memory_entry_details(entry),
                    ]
                ).strip(),
                status_text="Runtime memory entry shown.",
                memory_diagnostics=dict(diagnostics),
                payload={
                    "engram_id": resolved_engram_id,
                    "entry": entry,
                },
            )

        if action == "shared_show":
            diagnostics = diagnostics_loader()
            resolved_engram_id = self._resolve_shared_selector(
                diagnostics,
                normalized.engram_id,
                usage_command="/memory shared show <selector>",
            )
            entry = self.runtime_memory_backend.get_workspace_shared_entry(
                workspace_dir=workspace_dir,
                engram_id=resolved_engram_id,
            )
            if entry is None:
                raise MemoryCommandError(
                    format_runtime_shared_selector_help(
                        diagnostics,
                        usage_command="/memory shared show <selector>",
                    ),
                    status_code=404,
                )
            return MemoryCommandOutcome(
                command=f"memory shared show {normalized.engram_id}",
                summary="workspace-shared runtime memory entry shown",
                details="\n".join(
                    [
                        "Workspace-Shared Runtime Memory",
                        *format_runtime_memory_entry_details(entry),
                    ]
                ).strip(),
                status_text="Workspace-shared runtime memory entry shown.",
                memory_diagnostics=dict(diagnostics),
                payload={
                    "engram_id": resolved_engram_id,
                    "entry": entry,
                },
            )

        if action == "refresh":
            refresh = MemoryService(workspace_dir).refresh_consolidated_memory(exclude_session_id=session_id)
            diagnostics = diagnostics_loader()
            summary = (
                "memory refreshed"
                if bool(refresh.get("refreshed"))
                else f"memory {str(refresh.get('reason') or 'fresh').replace('_', ' ')}"
            )
            return MemoryCommandOutcome(
                command="memory refresh",
                summary=summary,
                details=format_memory_diagnostics(
                    diagnostics,
                    include_header=True,
                    detail_mode=normalized.detail_mode,
                ),
                status_text="Memory refresh completed.",
                memory_diagnostics=dict(diagnostics),
                payload={"refresh": refresh},
            )

        if action == "shared_clear":
            cleared = self.runtime_memory_backend.clear_workspace_shared_namespace(
                workspace_dir=workspace_dir,
            )
            diagnostics = diagnostics_loader()
            summary = (
                "workspace-shared runtime memory cleared"
                if cleared
                else "workspace-shared runtime memory already empty"
            )
            details_lines = [
                "Workspace-Shared Runtime Memory",
                f"Action: {action}",
                f"Cleared: {'yes' if cleared else 'no'}",
                "",
                format_memory_diagnostics(
                    diagnostics,
                    include_header=True,
                    detail_mode=normalized.detail_mode,
                ),
            ]
            return MemoryCommandOutcome(
                command="memory shared clear",
                summary=summary,
                details="\n".join(line for line in details_lines if line is not None).strip(),
                status_text="Workspace-shared runtime memory cleared.",
                memory_diagnostics=dict(diagnostics),
                payload={"cleared": cleared},
            )

        if action in {"promote_shared", "promote_note", "promote_profile"}:
            return self._execute_promote(
                workspace_dir=workspace_dir,
                session_id=session_id,
                diagnostics_loader=diagnostics_loader,
                command=normalized,
            )

        return self._execute_save(
            workspace_dir=workspace_dir,
            diagnostics_loader=diagnostics_loader,
            command=normalized,
            prepared_context=prepared_context,
        )

    def _execute_durable_read(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
        diagnostics_loader: Callable[[], dict[str, Any]],
        command: MemoryCommandRequest,
    ) -> MemoryCommandOutcome:
        diagnostics = diagnostics_loader()
        memory = MemoryService(workspace_dir)
        refresh_status = memory.consolidated_refresh_status(exclude_session_id=session_id)
        action = command.action

        if action == "overview":
            overview = build_memory_overview_payload(
                memory=memory,
                diagnostics=diagnostics,
                exclude_session_id=session_id,
            )
            return MemoryCommandOutcome(
                command="memory overview",
                summary="memory overview shown",
                details="\n".join(format_memory_overview_details(overview)).strip(),
                status_text="Memory overview shown.",
                memory_diagnostics=dict(diagnostics),
                payload={"overview": overview},
            )

        if action == "export":
            try:
                export_payload = memory.export_notes(format=command.export_format or "jsonl")
            except ValueError as exc:
                raise MemoryCommandError(str(exc), status_code=400) from exc
            summary = memory.summary()
            export_name = command.export_format or "jsonl"
            return MemoryCommandOutcome(
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
                memory_diagnostics=dict(diagnostics),
                payload={"export": export_payload},
            )

        if action == "consolidated_show":
            snapshot = memory.consolidated_snapshot()
            snapshot["memory_file"] = refresh_status.get("memory_file")
            return MemoryCommandOutcome(
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
                memory_diagnostics=dict(diagnostics),
                payload={"snapshot": snapshot},
            )

        if action == "consolidated_search":
            if not command.query:
                raise MemoryCommandError("Usage: /memory consolidated search <query>")
            payload = memory.search_relevant_consolidated_memory(
                query=command.query,
                top_k=10,
            )
            return MemoryCommandOutcome(
                command=f"memory consolidated search {command.query}",
                summary="consolidated memory matches shown",
                details="\n".join(
                    format_consolidated_memory_search_details(
                        payload,
                        refresh_status=refresh_status,
                        limit=10,
                    )
                ).strip(),
                status_text="Consolidated memory search shown.",
                memory_diagnostics=dict(diagnostics),
                payload={
                    "query": command.query,
                    "search": payload,
                },
            )

        if action == "profile":
            profile = memory.profile()
            matches = memory.search_profile(query=command.query, limit=10) if command.query else None
            return MemoryCommandOutcome(
                command="memory profile" + (f" {command.query}" if command.query else ""),
                summary="global profile matches shown" if command.query else "global profile shown",
                details="\n".join(
                    format_global_profile_details(
                        profile,
                        query=command.query,
                        matches=matches,
                        limit=20,
                    )
                ).strip(),
                status_text="Global profile shown.",
                memory_diagnostics=dict(diagnostics),
                payload={
                    "profile": profile,
                    "matches": matches or [],
                    "query": command.query,
                },
            )

        if action == "notes":
            summary = memory.summary()
            if command.query:
                ranked = memory.rank_workspace_notes(query=command.query)[:10]
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
                    query=command.query,
                    total=len(note_items),
                )
                return MemoryCommandOutcome(
                    command=f"memory notes {command.query}",
                    summary="workspace durable note matches shown",
                    details="\n".join(details).strip(),
                    status_text="Workspace durable notes shown.",
                    memory_diagnostics=dict(diagnostics),
                    payload={
                        "items": note_items,
                        "query": command.query,
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
            return MemoryCommandOutcome(
                command="memory notes",
                summary="workspace durable notes shown",
                details="\n".join(details).strip(),
                status_text="Workspace durable notes shown.",
                memory_diagnostics=dict(diagnostics),
                payload={"items": note_items},
            )

        if not command.day:
            raise MemoryCommandError("Usage: /memory daily <YYYY-MM-DD>")
        try:
            snapshot = memory.daily_snapshot(day=command.day)
        except FileNotFoundError as exc:
            raise MemoryCommandError(str(exc), status_code=404) from exc
        except ValueError as exc:
            raise MemoryCommandError(str(exc), status_code=400) from exc
        note_items = [memory.note_to_dict(note) for note in snapshot.notes]
        return MemoryCommandOutcome(
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
            memory_diagnostics=dict(diagnostics),
            payload={
                "day": snapshot.day,
                "items": note_items,
            },
        )

    def _execute_promote(
        self,
        *,
        workspace_dir: Path,
        session_id: str,
        diagnostics_loader: Callable[[], dict[str, Any]],
        command: MemoryCommandRequest,
    ) -> MemoryCommandOutcome:
        diagnostics = diagnostics_loader()
        promote_target = (
            "shared"
            if command.action == "promote_shared"
            else "note" if command.action == "promote_note" else "profile"
        )
        resolved_engram_id = self._resolve_session_selector(
            diagnostics,
            command.engram_id,
            usage_command=f"/memory promote {promote_target} <selector>",
        )
        if command.action == "promote_shared":
            promotion = self.runtime_memory_backend.promote_session_memory_to_workspace_shared(
                workspace_dir=workspace_dir,
                session_id=session_id,
                engram_id=resolved_engram_id,
            )
            summary = "runtime memory promoted to workspace-shared memory"
            command_name = "memory promote shared"
            status_text = "Memory promoted to shared."
        elif command.action == "promote_note":
            promotion = self.runtime_memory_backend.promote_session_memory_to_workspace_note(
                workspace_dir=workspace_dir,
                session_id=session_id,
                engram_id=resolved_engram_id,
            )
            summary = "runtime memory promoted to workspace note"
            command_name = "memory promote note"
            status_text = "Memory promoted to note."
        else:
            promotion = self.runtime_memory_backend.promote_session_memory_to_global_profile(
                workspace_dir=workspace_dir,
                session_id=session_id,
                engram_id=resolved_engram_id,
            )
            summary = "runtime memory promoted to global profile"
            command_name = "memory promote profile"
            status_text = "Memory promoted to profile."
        refreshed_diagnostics = diagnostics_loader()
        details_lines = [f"Action: {command.action}"]
        if command.engram_id != resolved_engram_id:
            details_lines.append(f"Selector: {command.engram_id}")
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
                detail_mode=command.detail_mode,
            )
        )
        return MemoryCommandOutcome(
            command=command_name,
            summary=summary,
            details="\n".join(line for line in details_lines if line is not None).strip(),
            status_text=status_text,
            memory_diagnostics=dict(refreshed_diagnostics),
            payload={
                "promotion": promotion,
                "engram_id": resolved_engram_id,
                "selector": command.engram_id,
            },
        )

    def _execute_save(
        self,
        *,
        workspace_dir: Path,
        diagnostics_loader: Callable[[], dict[str, Any]],
        command: MemoryCommandRequest,
        prepared_context: dict[str, Any] | None,
    ) -> MemoryCommandOutcome:
        if not command.content:
            raise MemoryCommandError(
                f"Usage: /memory save {'note' if command.action == 'save_note' else 'profile'} <text>"
            )
        diagnostics = diagnostics_loader()
        prepared_sources = self._prepared_context_sources(diagnostics)
        if command.action == "save_note":
            saved = self.save_workspace_note(
                workspace_dir=workspace_dir,
                content=command.content,
                prepared_context_sources=prepared_sources,
                prepared_context=prepared_context,
            )
            summary = "operator note saved to workspace memory"
            command_name = "memory save note"
            status_text = "Memory saved to note."
        else:
            saved = self.save_profile_fact(
                workspace_dir=workspace_dir,
                content=command.content,
            )
            summary = (
                "operator profile fact saved"
                if bool(saved.get("saved"))
                else "operator profile fact already present"
            )
            command_name = "memory save profile"
            status_text = "Memory saved to profile."
        refreshed_diagnostics = diagnostics_loader()
        details_lines = [
            f"Action: {command.action}",
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
                detail_mode=command.detail_mode,
            )
        )
        return MemoryCommandOutcome(
            command=command_name,
            summary=summary,
            details="\n".join(line for line in details_lines if line is not None).strip(),
            status_text=status_text,
            memory_diagnostics=dict(refreshed_diagnostics),
            payload={"saved": saved},
        )

    @staticmethod
    def _normalize_action(action: str | None) -> str:
        return _safe_text(action).lower().replace("-", "_")

    def _normalize_request(self, command: MemoryCommandRequest) -> MemoryCommandRequest:
        return MemoryCommandRequest(
            action=self._normalize_action(command.action),
            engram_id=_safe_text(command.engram_id) or None,
            content=_safe_text(command.content) or None,
            query=_safe_text(command.query) or None,
            day=_safe_text(command.day) or None,
            export_format=_safe_text(command.export_format).lower() or None,
            detail_mode=_safe_text(command.detail_mode).lower() or "full",
        )

    def _resolve_session_selector(
        self,
        diagnostics: dict[str, Any],
        selector: str | None,
        *,
        usage_command: str,
    ) -> str:
        if not selector:
            raise MemoryCommandError(
                format_runtime_session_selector_help(
                    diagnostics,
                    usage_command=usage_command,
                )
            )
        resolved = resolve_runtime_session_engram_selector(diagnostics, selector)
        if resolved:
            return resolved
        raise MemoryCommandError(
            format_runtime_session_selector_help(
                diagnostics,
                usage_command=usage_command,
            )
        )

    def _resolve_shared_selector(
        self,
        diagnostics: dict[str, Any],
        selector: str | None,
        *,
        usage_command: str,
    ) -> str:
        if not selector:
            raise MemoryCommandError(
                format_runtime_shared_selector_help(
                    diagnostics,
                    usage_command=usage_command,
                )
            )
        resolved = resolve_runtime_shared_engram_selector(diagnostics, selector)
        if resolved:
            return resolved
        raise MemoryCommandError(
            format_runtime_shared_selector_help(
                diagnostics,
                usage_command=usage_command,
            )
        )

    @staticmethod
    def _prepared_context_sources(diagnostics: dict[str, Any]) -> list[str]:
        prepared_sources = diagnostics.get("prepared_context_sources")
        if not isinstance(prepared_sources, list):
            return []
        normalized: list[str] = []
        for item in prepared_sources:
            cleaned = _safe_text(item).lower()
            if cleaned:
                normalized.append(cleaned)
        return normalized

    @staticmethod
    def _read_command_name(action: str, detail_mode: str) -> str:
        if action == "show":
            return "memory show" if detail_mode == "full" else f"memory show {detail_mode}"
        if action == "shared_list":
            return "memory shared list"
        return f"memory {action}"

    @staticmethod
    def _read_status_text(action: str) -> str:
        if action == "status":
            return "Memory status shown."
        if action == "show":
            return "Memory diagnostics shown."
        if action == "runtime":
            return "Runtime memory shown."
        if action == "list":
            return "Runtime memory list shown."
        return "Workspace-shared runtime memory list shown."

    @staticmethod
    def _session_memory_read_content(
        *,
        action: str,
        diagnostics: dict[str, Any],
        detail_mode: str,
    ) -> tuple[str, str]:
        summary = memory_diagnostics_summary_line(diagnostics)
        if action == "status":
            details = (
                f"Memory status: {summary}\n"
                f"Workspace: {_safe_text(diagnostics.get('workspace_anchor_dir')) or _safe_text(diagnostics.get('workspace_dir'))}"
            )
            return summary, details
        if action in {"runtime", "list"}:
            runtime = (
                diagnostics.get("runtime_task_memory")
                if isinstance(diagnostics.get("runtime_task_memory"), dict)
                else {}
            )
            details_lines = [
                "Session Runtime Memory" if action == "list" else "Runtime Task Memory",
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
            return summary, "\n".join(details_lines).strip()
        if action == "shared_list":
            runtime = (
                diagnostics.get("runtime_task_memory")
                if isinstance(diagnostics.get("runtime_task_memory"), dict)
                else {}
            )
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
            return summary, "\n".join(details_lines).strip()
        return summary, format_memory_diagnostics(
            diagnostics,
            include_header=True,
            detail_mode=detail_mode,
        )


__all__ = [
    "MUTATING_MEMORY_ACTIONS",
    "MemoryCommandError",
    "MemoryCommandOutcome",
    "MemoryCommandRequest",
    "MemoryCommandService",
    "SUPPORTED_MEMORY_ACTIONS",
]
