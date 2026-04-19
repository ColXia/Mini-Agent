"""Persisted restore / hydration routing extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Sequence

from mini_agent.runtime.orchestration.session_hydration_coordinator import RuntimeSessionHydrationPayload

if TYPE_CHECKING:
    from mini_agent.agent_core.engine import Agent
    from mini_agent.agent_core.session.lifecycle import SessionLifecycleState
    from mini_agent.interfaces.agent import MainAgentSessionRecoverySnapshot
    from mini_agent.session.store_records import MainAgentSessionState
    from mini_agent.session.store_records import MainAgentSessionTranscriptEntry


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
        payload: RuntimeSessionHydrationPayload,
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


@dataclass(slots=True)
class RuntimeSessionRestoreExecution:
    session: "MainAgentSessionState"
    created: bool
    agent_messages_for_persist: Sequence[Any] | None = None


@dataclass(slots=True)
class RuntimeSessionRestoreHandler:
    transcript_entries_from_record: Callable[[dict[str, Any]], list["MainAgentSessionTranscriptEntry"]]
    stored_recovery_snapshot_from_record: Callable[
        [dict[str, Any], Sequence["MainAgentSessionTranscriptEntry"]],
        "MainAgentSessionRecoverySnapshot | None",
    ]
    build_record_hydration_payload: Callable[..., RuntimeSessionHydrationPayload]
    build_agent_for_identity: Callable[[Any, tuple[str, str, str] | None], Awaitable["Agent"]]
    load_runtime_config: Callable[[], Any]
    reconfigure_agent_runtime_policy: Callable[..., dict[str, Any]]
    restore_agent_messages_payload: Callable[[Sequence[Any], "Agent"], None]
    restore_agent_token_state: Callable[..., None]
    agent_knowledge_base_enabled: Callable[[Any], bool]
    apply_agent_knowledge_base_enabled: Callable[[Any, bool], bool]
    build_session_state: Callable[..., "MainAgentSessionState"]
    apply_stored_recovery: Callable[["MainAgentSessionState", "MainAgentSessionRecoverySnapshot | None"], None]
    set_selected_model_identity: Callable[["MainAgentSessionState", tuple[str, str, str] | None], None]
    route_model_identity: Callable[[Any], tuple[str, str, str] | None]
    hydrate_runtime_state: Callable[["MainAgentSessionState", RuntimeSessionHydrationPayload], None]
    bootstrap_session_lifecycle: Callable[[str, Any, datetime], "SessionLifecycleState"] | None = None
    build_session_key: Callable[[str, Any], Any] | None = None
    lifecycle_bootstrap: Callable[[Any, datetime], "SessionLifecycleState"] | None = None

    def prepare_restore_payload(
        self,
        record: dict[str, Any],
        *,
        now_utc: datetime,
    ) -> RuntimeSessionHydrationPayload:
        transcript = self.transcript_entries_from_record(record)
        stored_recovery = self.stored_recovery_snapshot_from_record(record, transcript)
        return self.build_record_hydration_payload(
            record,
            now_utc=now_utc,
            transcript=transcript,
            stored_recovery=stored_recovery,
        )

    async def hydrate_payload(
        self,
        payload: RuntimeSessionHydrationPayload,
        *,
        now_utc: datetime,
        existing_session: "MainAgentSessionState | None" = None,
    ) -> RuntimeSessionRestoreExecution:
        if existing_session is not None:
            return RuntimeSessionRestoreExecution(
                session=existing_session,
                created=False,
            )

        agent = await self.build_agent_for_identity(payload.workspace_dir, payload.selected_identity)
        if payload.desired_approval_profile or payload.desired_access_level:
            try:
                self.reconfigure_agent_runtime_policy(
                    agent=agent,
                    config=self.load_runtime_config(),
                    workspace_dir=payload.workspace_dir,
                    approval_profile_override=payload.desired_approval_profile,
                    access_level_override=payload.desired_access_level,
                )
            except Exception:
                pass

        self.restore_agent_messages_payload(payload.agent_messages or [], agent)
        self.restore_agent_token_state(
            agent,
            token_usage=payload.token_usage,
            token_limit=payload.token_limit,
            raw_messages=payload.agent_messages,
        )
        effective_knowledge_base_enabled = (
            bool(payload.requested_knowledge_base_enabled)
            if payload.requested_knowledge_base_enabled is not None
            else self.agent_knowledge_base_enabled(agent)
        )
        effective_knowledge_base_enabled = self.apply_agent_knowledge_base_enabled(
            agent,
            effective_knowledge_base_enabled,
        )
        lifecycle_state = self._bootstrap_lifecycle_state(
            session_id=payload.session_id,
            workspace_dir=payload.workspace_dir,
            now_utc=now_utc,
        )
        session = self.build_session_state(
            payload,
            lifecycle_state=lifecycle_state,
            agent=agent,
            effective_knowledge_base_enabled=effective_knowledge_base_enabled,
        )
        self.apply_stored_recovery(session, payload.stored_recovery)
        if payload.selected_identity is None:
            self.set_selected_model_identity(session, self.route_model_identity(agent))
        self.hydrate_runtime_state(session, payload)
        return RuntimeSessionRestoreExecution(
            session=session,
            created=True,
            agent_messages_for_persist=payload.agent_messages,
        )

    def _bootstrap_lifecycle_state(
        self,
        *,
        session_id: str,
        workspace_dir: Any,
        now_utc: datetime,
    ) -> "SessionLifecycleState":
        if callable(self.bootstrap_session_lifecycle):
            return self.bootstrap_session_lifecycle(
                session_id,
                workspace_dir,
                now_utc,
            )
        if callable(self.build_session_key) and callable(self.lifecycle_bootstrap):
            session_key = self.build_session_key(session_id, workspace_dir)
            return self.lifecycle_bootstrap(session_key, now_utc)
        raise TypeError("RuntimeSessionRestoreHandler requires lifecycle bootstrap wiring.")


__all__ = [
    "RuntimeSessionStateHydrator",
    "RuntimeSessionRestoreExecution",
    "RuntimeSessionRestoreHandler",
]



