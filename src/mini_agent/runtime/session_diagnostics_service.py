"""Compatibility wrapper for runtime session diagnostics helpers."""

from __future__ import annotations

from mini_agent.memory.diagnostics import build_memory_diagnostics
from mini_agent.runtime.support import session_diagnostics_service as _impl

class RuntimeSessionDiagnosticsService(_impl.RuntimeSessionDiagnosticsService):
    def build_memory_diagnostics_for_session(
        self,
        session,
        *,
        preview_limit: int = 5,
    ) -> dict[str, object]:
        try:
            diagnostics = build_memory_diagnostics(
                workspace_dir=session.workspace_dir,
                session_id=session.session_id,
                last_prepared_context=session.projection.last_prepared_context,
                last_memory_automation=self._read_agent_last_memory_automation(session.runtime.agent),
                last_runtime_task_memory=self._read_agent_last_runtime_task_memory(session.runtime.agent),
                preview_limit=preview_limit,
            )
        except Exception:
            diagnostics = self.normalize_memory_diagnostics_payload(session.projection.memory_diagnostics)
        session.projection.memory_diagnostics = self.normalize_memory_diagnostics_payload(diagnostics)
        return session.projection.memory_diagnostics

    def build_memory_diagnostics_from_record(
        self,
        record: dict[str, object],
        *,
        preview_limit: int = 5,
    ) -> dict[str, object]:
        workspace_dir = _impl._safe_text(record.get("workspace_dir"))
        if not workspace_dir:
            return self.normalize_memory_diagnostics_payload(record.get("memory_diagnostics"))
        try:
            diagnostics = build_memory_diagnostics(
                workspace_dir=workspace_dir,
                session_id=_impl._safe_text(record.get("session_id")) or None,
                last_prepared_context=self.normalize_prepared_context_payload(record.get("last_prepared_context")),
                last_memory_automation=record.get("last_memory_automation"),
                last_runtime_task_memory=record.get("last_runtime_task_memory"),
                preview_limit=preview_limit,
            )
        except Exception:
            diagnostics = record.get("memory_diagnostics")
        return self.normalize_memory_diagnostics_payload(diagnostics)


__all__ = [
    "RuntimeSessionDiagnosticsService",
    "build_memory_diagnostics",
]
