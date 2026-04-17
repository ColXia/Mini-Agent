"""Persisted restore / hydration routing extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Sequence

from mini_agent.runtime.orchestration.session_hydration_builder import RuntimeSessionHydrationPayload

if TYPE_CHECKING:
    from mini_agent.agent_core.engine import Agent
    from mini_agent.agent_core.session import SessionLifecycleState
    from mini_agent.interfaces import MainAgentSessionRecoverySnapshot
    from mini_agent.runtime.session_state import MainAgentSessionState
    from mini_agent.runtime.session_state import MainAgentSessionTranscriptEntry


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
    "RuntimeSessionRestoreExecution",
    "RuntimeSessionRestoreHandler",
]
