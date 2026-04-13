"""Session memory command routing extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from fastapi import HTTPException

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
from mini_agent.memory.service import MemoryService
from mini_agent.runtime.session_runtime_memory_backend_adapter import RuntimeTaskMemoryBackendAdapter

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


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
class RuntimeSessionMemoryCommand:
    action: str
    engram_id: str | None = None
    content: str | None = None
    query: str | None = None
    day: str | None = None
    export_format: str | None = None
    detail_mode: str = "full"


@dataclass(slots=True)
class RuntimeSessionMemoryCommandExecution:
    memory_diagnostics: dict[str, Any]
    result: dict[str, Any]


@dataclass(slots=True)
class RuntimeSessionMemoryCommandHandler:
    build_memory_diagnostics_for_session: Callable[..., dict[str, Any]]
    runtime_task_memory_backend: RuntimeTaskMemoryBackendAdapter
    save_operator_workspace_note: Callable[..., dict[str, Any]]
    save_operator_profile_fact: Callable[..., dict[str, Any]]

    def validate_action(self, action: str) -> None:
        if action not in SUPPORTED_MEMORY_ACTIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported session memory action: {action}")

    @staticmethod
    def is_mutating_action(action: str) -> bool:
        return action in MUTATING_MEMORY_ACTIONS

    def execute(
        self,
        session: "MainAgentSessionState",
        command: RuntimeSessionMemoryCommand,
    ) -> RuntimeSessionMemoryCommandExecution:
        action = command.action
        if action in {"status", "show", "runtime", "list", "shared_list"}:
            diagnostics = self.build_memory_diagnostics_for_session(session)
            return RuntimeSessionMemoryCommandExecution(
                memory_diagnostics=dict(diagnostics),
                result=self._session_memory_read_result(
                    action=action,
                    diagnostics=diagnostics,
                    detail_mode=command.detail_mode,
                ),
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
            return self._execute_durable_read(session, command)
        if action == "session_show":
            return self._execute_session_show(session, command)
        if action == "shared_show":
            return self._execute_shared_show(session, command)
        return self._execute_mutation(session, command)

    def _execute_durable_read(
        self,
        session: "MainAgentSessionState",
        command: RuntimeSessionMemoryCommand,
    ) -> RuntimeSessionMemoryCommandExecution:
        diagnostics = self.build_memory_diagnostics_for_session(session)
        memory = MemoryService(session.workspace_dir)
        refresh_status = memory.consolidated_refresh_status(exclude_session_id=session.session_id)
        action = command.action
        if action == "overview":
            overview = build_memory_overview_payload(
                memory=memory,
                diagnostics=diagnostics,
                exclude_session_id=session.session_id,
            )
            result = {
                "summary": "memory overview shown",
                "details": "\n".join(format_memory_overview_details(overview)).strip(),
                "overview": overview,
            }
        elif action == "export":
            try:
                export_payload = memory.export_notes(format=command.export_format or "jsonl")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            summary = memory.summary()
            result = {
                "summary": "memory export prepared",
                "details": "\n".join(
                    format_memory_export_details(
                        export_payload,
                        workspace_dir=summary.workspace_dir,
                        memory_root=summary.memory_root,
                        long_term_file=summary.long_term_file,
                        daily_dir=summary.daily_dir,
                    )
                ).strip(),
                "export": export_payload,
            }
        elif action == "consolidated_show":
            snapshot = memory.consolidated_snapshot()
            snapshot["memory_file"] = refresh_status.get("memory_file")
            result = {
                "summary": "consolidated memory shown",
                "details": "\n".join(
                    format_consolidated_memory_details(
                        snapshot,
                        refresh_status=refresh_status,
                        limit=20,
                    )
                ).strip(),
                "snapshot": snapshot,
            }
        elif action == "consolidated_search":
            if not command.query:
                raise HTTPException(status_code=400, detail="Usage: /memory consolidated search <query>")
            payload = memory.search_relevant_consolidated_memory(
                query=command.query,
                top_k=10,
            )
            result = {
                "summary": "consolidated memory matches shown",
                "details": "\n".join(
                    format_consolidated_memory_search_details(
                        payload,
                        refresh_status=refresh_status,
                        limit=10,
                    )
                ).strip(),
                "query": command.query,
                "search": payload,
            }
        elif action == "profile":
            profile = memory.profile()
            matches = memory.search_profile(query=command.query, limit=10) if command.query else None
            result = {
                "summary": "global profile matches shown" if command.query else "global profile shown",
                "details": "\n".join(
                    format_global_profile_details(
                        profile,
                        query=command.query,
                        matches=matches,
                        limit=20,
                    )
                ).strip(),
                "profile": profile,
                "matches": matches or [],
                "query": command.query,
            }
        elif action == "notes":
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
                result = {
                    "summary": "workspace durable note matches shown",
                    "details": "\n".join(
                        format_workspace_note_details(
                            workspace_dir=summary.workspace_dir,
                            memory_root=summary.memory_root,
                            long_term_file=summary.long_term_file,
                            daily_dir=summary.daily_dir,
                            categories=summary.categories,
                            notes=note_items,
                            query=command.query,
                            total=len(note_items),
                        )
                    ).strip(),
                    "query": command.query,
                    "items": note_items,
                }
            else:
                recent_notes = [
                    memory.note_to_dict(note)
                    for note in memory.search_notes(query="", limit=10)
                ]
                result = {
                    "summary": "workspace durable notes shown",
                    "details": "\n".join(
                        format_workspace_note_details(
                            workspace_dir=summary.workspace_dir,
                            memory_root=summary.memory_root,
                            long_term_file=summary.long_term_file,
                            daily_dir=summary.daily_dir,
                            categories=summary.categories,
                            notes=recent_notes,
                            total=summary.notes_count,
                        )
                    ).strip(),
                    "items": recent_notes,
                }
        else:
            if not command.day:
                raise HTTPException(status_code=400, detail="Usage: /memory daily <YYYY-MM-DD>")
            try:
                snapshot = memory.daily_snapshot(day=command.day)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            note_items = [memory.note_to_dict(note) for note in snapshot.notes]
            result = {
                "summary": "workspace daily memory shown",
                "details": "\n".join(
                    format_workspace_daily_details(
                        workspace_dir=snapshot.workspace_dir,
                        day=snapshot.day,
                        path=snapshot.path,
                        notes=note_items,
                        note_count=snapshot.note_count,
                    )
                ).strip(),
                "day": snapshot.day,
                "items": note_items,
            }
        return RuntimeSessionMemoryCommandExecution(
            memory_diagnostics=dict(diagnostics),
            result=result,
        )

    def _execute_session_show(
        self,
        session: "MainAgentSessionState",
        command: RuntimeSessionMemoryCommand,
    ) -> RuntimeSessionMemoryCommandExecution:
        diagnostics = self.build_memory_diagnostics_for_session(session)
        resolved_engram_id = self._resolve_session_selector(
            diagnostics,
            command.engram_id,
            usage_command="/memory show <selector>",
        )
        entry = self.runtime_task_memory_backend.get_session_entry(
            workspace_dir=session.workspace_dir,
            session_id=session.session_id,
            engram_id=resolved_engram_id,
        )
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=format_runtime_session_selector_help(
                    diagnostics,
                    usage_command="/memory show <selector>",
                ),
            )
        result = {
            "summary": "session runtime memory entry shown",
            "details": "\n".join(
                [
                    "Session Runtime Memory",
                    *format_runtime_memory_entry_details(entry),
                ]
            ).strip(),
            "engram_id": resolved_engram_id,
            "entry": entry,
        }
        return RuntimeSessionMemoryCommandExecution(
            memory_diagnostics=dict(diagnostics),
            result=result,
        )

    def _execute_shared_show(
        self,
        session: "MainAgentSessionState",
        command: RuntimeSessionMemoryCommand,
    ) -> RuntimeSessionMemoryCommandExecution:
        diagnostics = self.build_memory_diagnostics_for_session(session)
        resolved_engram_id = self._resolve_shared_selector(
            diagnostics,
            command.engram_id,
            usage_command="/memory shared show <selector>",
        )
        entry = self.runtime_task_memory_backend.get_workspace_shared_entry(
            workspace_dir=session.workspace_dir,
            engram_id=resolved_engram_id,
        )
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=format_runtime_shared_selector_help(
                    diagnostics,
                    usage_command="/memory shared show <selector>",
                ),
            )
        result = {
            "summary": "workspace-shared runtime memory entry shown",
            "details": "\n".join(
                [
                    "Workspace-Shared Runtime Memory",
                    *format_runtime_memory_entry_details(entry),
                ]
            ).strip(),
            "engram_id": resolved_engram_id,
            "entry": entry,
        }
        return RuntimeSessionMemoryCommandExecution(
            memory_diagnostics=dict(diagnostics),
            result=result,
        )

    def _execute_mutation(
        self,
        session: "MainAgentSessionState",
        command: RuntimeSessionMemoryCommand,
    ) -> RuntimeSessionMemoryCommandExecution:
        action = command.action
        if action == "refresh":
            memory = MemoryService(session.workspace_dir)
            refresh = memory.refresh_consolidated_memory(exclude_session_id=session.session_id)
            session.projection.memory_diagnostics = self.build_memory_diagnostics_for_session(session)
            summary = (
                "memory refreshed"
                if bool(refresh.get("refreshed"))
                else f"memory {str(refresh.get('reason') or 'fresh').replace('_', ' ')}"
            )
            result = {
                "summary": summary,
                "details": format_memory_diagnostics(
                    session.projection.memory_diagnostics,
                    include_header=True,
                    detail_mode=command.detail_mode,
                ),
                "refresh": refresh,
            }
            return RuntimeSessionMemoryCommandExecution(
                memory_diagnostics=dict(session.projection.memory_diagnostics),
                result=result,
            )

        if action == "shared_clear":
            cleared = self.runtime_task_memory_backend.clear_workspace_shared_namespace(
                workspace_dir=session.workspace_dir,
            )
            session.projection.memory_diagnostics = self.build_memory_diagnostics_for_session(session)
            summary = (
                "workspace-shared runtime memory cleared"
                if cleared
                else "workspace-shared runtime memory already empty"
            )
            result = {
                "summary": summary,
                "details": "\n".join(
                    [
                        "Workspace-Shared Runtime Memory",
                        f"Action: {action}",
                        f"Cleared: {'yes' if cleared else 'no'}",
                        "",
                        format_memory_diagnostics(
                            session.projection.memory_diagnostics,
                            include_header=True,
                            detail_mode=command.detail_mode,
                        ),
                    ]
                ).strip(),
                "cleared": cleared,
            }
            return RuntimeSessionMemoryCommandExecution(
                memory_diagnostics=dict(session.projection.memory_diagnostics),
                result=result,
            )

        session.projection.memory_diagnostics = self.build_memory_diagnostics_for_session(session)
        if action in {"promote_shared", "promote_note", "promote_profile"}:
            return self._execute_promote(session, command)
        return self._execute_save(session, command)

    def _execute_promote(
        self,
        session: "MainAgentSessionState",
        command: RuntimeSessionMemoryCommand,
    ) -> RuntimeSessionMemoryCommandExecution:
        action = command.action
        promote_target = (
            "shared"
            if action == "promote_shared"
            else "note" if action == "promote_note" else "profile"
        )
        resolved_engram_id = self._resolve_session_selector(
            session.projection.memory_diagnostics,
            command.engram_id,
            usage_command=f"/memory promote {promote_target} <selector>",
        )
        if action == "promote_shared":
            promotion = self.runtime_task_memory_backend.promote_session_memory_to_workspace_shared(
                workspace_dir=session.workspace_dir,
                session_id=session.session_id,
                engram_id=resolved_engram_id,
            )
            summary = "runtime memory promoted to workspace-shared memory"
        elif action == "promote_note":
            promotion = self.runtime_task_memory_backend.promote_session_memory_to_workspace_note(
                workspace_dir=session.workspace_dir,
                session_id=session.session_id,
                engram_id=resolved_engram_id,
            )
            summary = "runtime memory promoted to workspace note"
        else:
            promotion = self.runtime_task_memory_backend.promote_session_memory_to_global_profile(
                workspace_dir=session.workspace_dir,
                session_id=session.session_id,
                engram_id=resolved_engram_id,
            )
            summary = "runtime memory promoted to global profile"
        session.projection.memory_diagnostics = self.build_memory_diagnostics_for_session(session)
        details_lines = [f"Action: {action}"]
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
                session.projection.memory_diagnostics,
                include_header=True,
                detail_mode=command.detail_mode,
            )
        )
        return RuntimeSessionMemoryCommandExecution(
            memory_diagnostics=dict(session.projection.memory_diagnostics),
            result={
                "summary": summary,
                "details": "\n".join(line for line in details_lines if line is not None).strip(),
                "promotion": promotion,
                "engram_id": resolved_engram_id,
                "selector": command.engram_id,
            },
        )

    def _execute_save(
        self,
        session: "MainAgentSessionState",
        command: RuntimeSessionMemoryCommand,
    ) -> RuntimeSessionMemoryCommandExecution:
        action = command.action
        if not command.content:
            raise HTTPException(
                status_code=400,
                detail=f"Usage: /memory save {'note' if action == 'save_note' else 'profile'} <text>",
            )
        prepared_sources = self._prepared_context_sources(session.projection.memory_diagnostics)
        if action == "save_note":
            save_result = self.save_operator_workspace_note(
                workspace_dir=session.workspace_dir,
                content=command.content,
                prepared_context_sources=prepared_sources,
                prepared_context=session.projection.last_prepared_context,
            )
            summary = "operator note saved to workspace memory"
        else:
            save_result = self.save_operator_profile_fact(
                workspace_dir=session.workspace_dir,
                content=command.content,
            )
            summary = (
                "operator profile fact saved"
                if bool(save_result.get("saved"))
                else "operator profile fact already present"
            )
        session.projection.memory_diagnostics = self.build_memory_diagnostics_for_session(session)
        details_lines = [
            f"Action: {action}",
            f"Target: {save_result.get('target')}",
        ]
        if save_result.get("category"):
            details_lines.append(f"Category: {save_result.get('category')}")
        if save_result.get("content"):
            details_lines.append(f"Content: {save_result.get('content')}")
        details_lines.extend(
            format_knowledge_base_grounding_lines(
                save_result.get("knowledge_base_grounding"),
            )
        )
        details_lines.append("")
        details_lines.append(
            format_memory_diagnostics(
                session.projection.memory_diagnostics,
                include_header=True,
                detail_mode=command.detail_mode,
            )
        )
        return RuntimeSessionMemoryCommandExecution(
            memory_diagnostics=dict(session.projection.memory_diagnostics),
            result={
                "summary": summary,
                "details": "\n".join(line for line in details_lines if line is not None).strip(),
                "saved": save_result,
            },
        )

    def _resolve_session_selector(
        self,
        diagnostics: dict[str, Any],
        selector: str | None,
        *,
        usage_command: str,
    ) -> str:
        if not selector:
            raise HTTPException(
                status_code=400,
                detail=format_runtime_session_selector_help(
                    diagnostics,
                    usage_command=usage_command,
                ),
            )
        resolved = resolve_runtime_session_engram_selector(diagnostics, selector)
        if resolved:
            return resolved
        raise HTTPException(
            status_code=400,
            detail=format_runtime_session_selector_help(
                diagnostics,
                usage_command=usage_command,
            ),
        )

    def _resolve_shared_selector(
        self,
        diagnostics: dict[str, Any],
        selector: str | None,
        *,
        usage_command: str,
    ) -> str:
        if not selector:
            raise HTTPException(
                status_code=400,
                detail=format_runtime_shared_selector_help(
                    diagnostics,
                    usage_command=usage_command,
                ),
            )
        resolved = resolve_runtime_shared_engram_selector(diagnostics, selector)
        if resolved:
            return resolved
        raise HTTPException(
            status_code=400,
            detail=format_runtime_shared_selector_help(
                diagnostics,
                usage_command=usage_command,
            ),
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
    def _session_memory_read_result(
        *,
        action: str,
        diagnostics: dict[str, Any],
        detail_mode: str,
    ) -> dict[str, Any]:
        summary = memory_diagnostics_summary_line(diagnostics)
        if action == "status":
            details = (
                f"Memory status: {summary}\n"
                f"Workspace: {_safe_text(diagnostics.get('workspace_anchor_dir')) or _safe_text(diagnostics.get('workspace_dir'))}"
            )
        elif action in {"runtime", "list"}:
            runtime = diagnostics.get("runtime_task_memory") if isinstance(diagnostics.get("runtime_task_memory"), dict) else {}
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
            details = "\n".join(details_lines).strip()
        elif action == "shared_list":
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
            details = "\n".join(details_lines).strip()
        else:
            details = format_memory_diagnostics(
                diagnostics,
                include_header=True,
                detail_mode=detail_mode,
            )
        return {
            "summary": summary,
            "details": details,
        }


__all__ = [
    "MUTATING_MEMORY_ACTIONS",
    "SUPPORTED_MEMORY_ACTIONS",
    "RuntimeSessionMemoryCommand",
    "RuntimeSessionMemoryCommandExecution",
    "RuntimeSessionMemoryCommandHandler",
]
