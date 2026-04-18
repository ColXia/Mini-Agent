"""Runtime session state hydration and synchronization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState
    from mini_agent.runtime.orchestration.session_hydration_builder import RuntimeSessionHydrationPayload


@dataclass(slots=True)
class RuntimeSessionStateHydrator:
    agent_knowledge_base_enabled: Callable[[Any], bool]
    restore_session_runtime_task_memory: Callable[..., dict[str, Any]]
    restore_workspace_shared_runtime_task_memory: Callable[..., dict[str, Any]]
    build_memory_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]]
    build_sandbox_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]]
    restore_workspace_runtime_snapshot: Callable[..., Any] | None = None
    agent_last_prepared_context: Callable[[Any], dict[str, Any]] | None = None
    agent_prepared_context_diagnostics: Callable[[Any], dict[str, Any]] | None = None
    normalize_prepared_context_payload: Callable[[Any], dict[str, Any]] | None = None
    normalize_prepared_context_diagnostics_payload: Callable[[Any], dict[str, Any]] | None = None

    @staticmethod
    def _normalize_payload(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    def _read_agent_last_prepared_context(self, agent: Any) -> dict[str, Any]:
        if callable(self.agent_last_prepared_context):
            try:
                return self._normalize_payload(self.agent_last_prepared_context(agent))
            except Exception:
                return {}
        raw_value = getattr(agent, "last_prepared_turn_context", None)
        if callable(self.normalize_prepared_context_payload):
            try:
                return self._normalize_payload(self.normalize_prepared_context_payload(raw_value))
            except Exception:
                return {}
        return self._normalize_payload(raw_value)

    def _read_agent_prepared_context_diagnostics(self, agent: Any) -> dict[str, Any]:
        if callable(self.agent_prepared_context_diagnostics):
            try:
                return self._normalize_payload(self.agent_prepared_context_diagnostics(agent))
            except Exception:
                return {}
        raw_value = getattr(agent, "prepared_context_diagnostics", None)
        if callable(self.normalize_prepared_context_diagnostics_payload):
            try:
                return self._normalize_payload(self.normalize_prepared_context_diagnostics_payload(raw_value))
            except Exception:
                return {}
        return self._normalize_payload(raw_value)

    def restore_agent_prepared_context_state(self, session: "MainAgentSessionState") -> None:
        agent = session.runtime.agent
        if hasattr(agent, "last_prepared_turn_context"):
            try:
                agent.last_prepared_turn_context = dict(session.projection.last_prepared_context)
            except Exception:
                agent.last_prepared_turn_context = None
        if hasattr(agent, "prepared_context_diagnostics"):
            try:
                agent.prepared_context_diagnostics = dict(session.projection.prepared_context_diagnostics)
            except Exception:
                agent.prepared_context_diagnostics = {}

    def refresh_session_diagnostics(self, session: "MainAgentSessionState") -> tuple[dict[str, Any], dict[str, Any]]:
        memory = self.build_memory_diagnostics_for_session(session)
        sandbox = self.build_sandbox_diagnostics_for_session(session)
        return memory, sandbox

    def refresh_runtime_projection(self, session: "MainAgentSessionState") -> tuple[dict[str, Any], dict[str, Any]]:
        agent = session.runtime.agent
        if agent is not None:
            session.projection.knowledge_base_enabled = self.agent_knowledge_base_enabled(agent)
        return self.refresh_session_diagnostics(session)

    def capture_agent_prepared_context_state(self, session: "MainAgentSessionState") -> None:
        session.projection.knowledge_base_enabled = self.agent_knowledge_base_enabled(session.runtime.agent)
        session.projection.last_prepared_context = self._read_agent_last_prepared_context(session.runtime.agent)
        session.projection.prepared_context_diagnostics = self._read_agent_prepared_context_diagnostics(
            session.runtime.agent
        )
        self.refresh_runtime_projection(session)

    def hydrate_runtime_state(
        self,
        session: "MainAgentSessionState",
        *,
        payload: "RuntimeSessionHydrationPayload",
    ) -> None:
        if payload.runtime_task_memory_payload is not None:
            self.restore_session_runtime_task_memory(
                workspace_dir=payload.workspace_dir,
                session_id=payload.session_id,
                payload=payload.runtime_task_memory_payload,
            )
        if payload.workspace_shared_runtime_memory_payload is not None:
            self.restore_workspace_shared_runtime_task_memory(
                workspace_dir=payload.workspace_dir,
                payload=payload.workspace_shared_runtime_memory_payload,
            )
        if payload.workspace_runtime_snapshot is not None and callable(self.restore_workspace_runtime_snapshot):
            self.restore_workspace_runtime_snapshot(
                workspace_dir=payload.workspace_dir,
                payload=payload.workspace_runtime_snapshot,
            )
        self.restore_agent_prepared_context_state(session)
        self.refresh_runtime_projection(session)


__all__ = ["RuntimeSessionStateHydrator"]
