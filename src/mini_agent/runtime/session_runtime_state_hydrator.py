"""Runtime session state hydration and synchronization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState
    from mini_agent.runtime.session_hydration_builder import RuntimeSessionHydrationPayload


@dataclass(slots=True)
class RuntimeSessionStateHydrator:
    agent_knowledge_base_enabled: Callable[[Any], bool]
    normalize_prepared_context_payload: Callable[[Any], dict[str, Any]]
    normalize_prepared_context_diagnostics_payload: Callable[[Any], dict[str, Any]]
    restore_session_runtime_task_memory: Callable[..., dict[str, Any]]
    restore_workspace_shared_runtime_task_memory: Callable[..., dict[str, Any]]
    build_memory_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]]
    build_sandbox_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]]

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

    def capture_agent_prepared_context_state(self, session: "MainAgentSessionState") -> None:
        session.projection.knowledge_base_enabled = self.agent_knowledge_base_enabled(session.runtime.agent)
        last_prepared = getattr(session.runtime.agent, "last_prepared_turn_context", None)
        diagnostics = getattr(session.runtime.agent, "prepared_context_diagnostics", None)
        session.projection.last_prepared_context = self.normalize_prepared_context_payload(last_prepared)
        session.projection.prepared_context_diagnostics = self.normalize_prepared_context_diagnostics_payload(
            diagnostics
        )
        self.refresh_session_diagnostics(session)

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
        self.restore_agent_prepared_context_state(session)
        self.refresh_session_diagnostics(session)


__all__ = ["RuntimeSessionStateHydrator"]
