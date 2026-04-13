"""Runtime session diagnostics helpers shared by hydration and read models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from mini_agent.memory.diagnostics import build_memory_diagnostics

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionDiagnosticsService:
    normalize_prepared_context_payload: Callable[[Any], dict[str, Any]]
    normalize_memory_diagnostics_payload: Callable[[Any], dict[str, Any]]
    normalize_sandbox_diagnostics_payload: Callable[[Any], dict[str, Any]]
    collect_sandbox_diagnostics: Callable[[Any], dict[str, Any]]

    def build_memory_diagnostics_for_session(
        self,
        session: "MainAgentSessionState",
        *,
        preview_limit: int = 5,
    ) -> dict[str, Any]:
        try:
            diagnostics = build_memory_diagnostics(
                workspace_dir=session.workspace_dir,
                session_id=session.session_id,
                last_prepared_context=session.projection.last_prepared_context,
                last_memory_automation=getattr(session.runtime.agent, "last_memory_automation", {}),
                last_runtime_task_memory=getattr(session.runtime.agent, "last_runtime_task_memory", {}),
                preview_limit=preview_limit,
            )
        except Exception:
            diagnostics = self.normalize_memory_diagnostics_payload(session.projection.memory_diagnostics)
        session.projection.memory_diagnostics = self.normalize_memory_diagnostics_payload(diagnostics)
        return session.projection.memory_diagnostics

    def build_memory_diagnostics_from_record(
        self,
        record: dict[str, Any],
        *,
        preview_limit: int = 5,
    ) -> dict[str, Any]:
        workspace_dir = _safe_text(record.get("workspace_dir"))
        if not workspace_dir:
            return self.normalize_memory_diagnostics_payload(record.get("memory_diagnostics"))
        try:
            diagnostics = build_memory_diagnostics(
                workspace_dir=workspace_dir,
                session_id=_safe_text(record.get("session_id")) or None,
                last_prepared_context=self.normalize_prepared_context_payload(record.get("last_prepared_context")),
                last_memory_automation=record.get("last_memory_automation"),
                last_runtime_task_memory=record.get("last_runtime_task_memory"),
                preview_limit=preview_limit,
            )
        except Exception:
            diagnostics = record.get("memory_diagnostics")
        return self.normalize_memory_diagnostics_payload(diagnostics)

    def build_sandbox_diagnostics_for_session(
        self,
        session: "MainAgentSessionState",
    ) -> dict[str, Any]:
        try:
            diagnostics = self.collect_sandbox_diagnostics(session.runtime.agent)
        except Exception:
            diagnostics = session.projection.sandbox_diagnostics
        session.projection.sandbox_diagnostics = self.normalize_sandbox_diagnostics_payload(diagnostics)
        return session.projection.sandbox_diagnostics

    def build_sandbox_diagnostics_from_record(
        self,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        return self.normalize_sandbox_diagnostics_payload(record.get("sandbox_diagnostics"))


__all__ = ["RuntimeSessionDiagnosticsService"]
