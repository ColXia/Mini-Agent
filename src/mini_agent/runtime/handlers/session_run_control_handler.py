"""Run and approval control ownership for session-backed runtime runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Mapping

from fastapi import HTTPException

from mini_agent.interfaces.agent import (
    MainAgentSessionApprovalResponse,
    MainAgentSessionMutationResponse,
)
from mini_agent.runtime.handlers.session_command_coordinator import (
    RuntimeSessionCommandCoordinator,
    RuntimeSessionCommandTranscript,
)
from mini_agent.runtime.live_control.run_control_constants import INTERRUPT_REQUESTED_RUNNING_STATE
from mini_agent.runtime.live_control.run_control_store import RuntimeSessionRunControlStore
from mini_agent.runtime.live_control.session_interrupt_handler import RuntimeSessionInterruptHandler
from mini_agent.runtime.read_models.run_projection_builder import RuntimeSessionRunProjectionBuilder

if TYPE_CHECKING:
    from mini_agent.session.store_records import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionRunControlHandler:
    run_control_store: RuntimeSessionRunControlStore
    run_projection_builder: RuntimeSessionRunProjectionBuilder
    session_commands: RuntimeSessionCommandCoordinator
    session_interrupt: RuntimeSessionInterruptHandler
    load_persisted_record: Callable[[str], dict[str, Any] | None]
    persist_session: Callable[["MainAgentSessionState"], None]

    def cancel_turn(
        self,
        *,
        session_id: str,
        active_session: "MainAgentSessionState | None",
        persisted_exists: bool,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionMutationResponse:
        session = active_session
        if session is None:
            if not persisted_exists:
                raise HTTPException(status_code=404, detail="Session not found.")
            raise HTTPException(status_code=409, detail="Session has no running turn to cancel.")

        execution = self.session_interrupt.execute_cancel(
            session,
            reason=reason,
        )
        self.session_commands.record(
            session,
            transcript=RuntimeSessionCommandTranscript(
                command="cancel",
                summary=execution.transcript_summary,
                content=execution.transcript_details,
            ),
            surface=surface or execution.response.active_surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return execution.response

    def resolve_pending_approval(
        self,
        *,
        session_id: str,
        active_session: "MainAgentSessionState | None",
        persisted_exists: bool,
        approved: bool,
        token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionApprovalResponse:
        session = active_session
        if session is None:
            if not persisted_exists:
                raise HTTPException(status_code=404, detail="Session not found.")
            raise HTTPException(
                status_code=409,
                detail=self.session_interrupt.restart_pending_approval_detail(),
            )

        execution = self.session_interrupt.execute_approval(
            session,
            approved=approved,
            token=token,
        )
        self.session_commands.record(
            session,
            transcript=RuntimeSessionCommandTranscript(
                command=execution.transcript_command,
                summary=execution.transcript_summary,
                content=execution.transcript_details,
                metadata={
                    "token": execution.token,
                    "tool_name": execution.tool_name,
                },
            ),
            surface=self._active_surface(session, surface),
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        execution.finalize()
        return execution.response

    def resolve_run_id_for_session(
        self,
        session_id: str,
        *,
        active_sessions: Mapping[str, "MainAgentSessionState"],
    ) -> str | None:
        normalized_session_id = _safe_text(session_id)
        if not normalized_session_id:
            return None
        if normalized_session_id in active_sessions:
            return RuntimeSessionRunControlStore.run_id_for_session(normalized_session_id)
        if self.load_persisted_record(normalized_session_id) is not None:
            return RuntimeSessionRunControlStore.run_id_for_session(normalized_session_id)
        return None

    def get_run(
        self,
        run_id: str,
        *,
        active_sessions: Mapping[str, "MainAgentSessionState"],
    ) -> dict[str, Any]:
        session_id = self._require_session_id_from_run_id(run_id)
        session = active_sessions.get(session_id)
        if session is not None:
            return self.run_projection_builder.build_active_run_projection(session)
        record = self.load_persisted_record(session_id)
        if record is None:
            raise LookupError(f"Run {run_id!r} was not found.")
        return self.run_projection_builder.build_persisted_run_projection(run_id=run_id, record=record)

    def interrupt_run(
        self,
        run_id: str,
        *,
        active_sessions: Mapping[str, "MainAgentSessionState"],
        reason: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        session = self._require_active_session_for_run_id(run_id, active_sessions=active_sessions)
        current_projection = self.run_projection_builder.build_active_run_projection(session)
        if not bool(current_projection.get("busy")):
            raise LookupError(f"Run {run_id!r} is not active and cannot be interrupted.")
        resolved_source = self._resolved_run_source(
            session,
            source=source,
            projection=current_projection,
        )
        self.run_control_store.request_interrupt(
            session,
            source=resolved_source,
            reason=reason,
        )
        session.projection.running_state = INTERRUPT_REQUESTED_RUNNING_STATE
        self.persist_session(session)
        return self.run_projection_builder.build_active_run_projection(session)

    def resume_run(
        self,
        run_id: str,
        *,
        active_sessions: Mapping[str, "MainAgentSessionState"],
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        session = self._require_active_session_for_run_id(run_id, active_sessions=active_sessions)
        pending = self.run_control_store.pending_approval_payloads(session)
        resolved_source = self._resolved_run_source(
            session,
            source=source,
            projection=self.run_projection_builder.build_active_run_projection(session),
        )
        if pending:
            self.run_control_store.request_resume(
                session,
                source=resolved_source,
                resume_token=resume_token,
            )
            return self.resolve_pending_approval(
                session_id=session.session_id,
                active_session=session,
                persisted_exists=False,
                approved=True,
                token=resume_token,
                surface=resolved_source,
                channel_type=session.projection.channel_type,
                conversation_id=session.projection.conversation_id,
                sender_id=session.projection.sender_id,
            )
        if bool(session.projection.recovery_context_pending):
            raise LookupError(
                f"Run {run_id!r} is in recovery state and cannot be resumed directly. "
                "Send a new message to continue with recovery context."
            )
        raise LookupError(f"Run {run_id!r} is not waiting for resume input.")

    def cancel_run(
        self,
        run_id: str,
        *,
        active_sessions: Mapping[str, "MainAgentSessionState"],
        reason: str | None = None,
        source: str | None = None,
    ) -> MainAgentSessionMutationResponse:
        session = self._require_active_session_for_run_id(run_id, active_sessions=active_sessions)
        return self.cancel_turn(
            session_id=session.session_id,
            active_session=session,
            persisted_exists=False,
            reason=reason,
            surface=self._resolved_run_source(session, source=source),
            channel_type=session.projection.channel_type,
            conversation_id=session.projection.conversation_id,
            sender_id=session.projection.sender_id,
        )

    def resolve_approval_wait(
        self,
        run_id: str,
        *,
        active_sessions: Mapping[str, "MainAgentSessionState"],
        approved: bool,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> MainAgentSessionApprovalResponse:
        _ = reason
        session = self._require_active_session_for_run_id(run_id, active_sessions=active_sessions)
        return self.resolve_pending_approval(
            session_id=session.session_id,
            active_session=session,
            persisted_exists=False,
            approved=approved,
            token=token,
            surface=self._resolved_run_source(session, source=source),
            channel_type=session.projection.channel_type,
            conversation_id=session.projection.conversation_id,
            sender_id=session.projection.sender_id,
        )

    @staticmethod
    def _require_session_id_from_run_id(run_id: str) -> str:
        session_id = RuntimeSessionRunControlStore.session_id_for_run_id(run_id)
        if session_id is None:
            raise LookupError(f"Run {run_id!r} is not a session-backed run identifier.")
        return session_id

    def _require_active_session_for_run_id(
        self,
        run_id: str,
        *,
        active_sessions: Mapping[str, "MainAgentSessionState"],
    ) -> "MainAgentSessionState":
        session_id = self._require_session_id_from_run_id(run_id)
        session = active_sessions.get(session_id)
        if session is None:
            if self.load_persisted_record(session_id) is not None:
                raise LookupError(f"Run {run_id!r} is not active in the current runtime host.")
            raise LookupError(f"Run {run_id!r} was not found.")
        return session

    @staticmethod
    def _active_surface(
        session: "MainAgentSessionState",
        surface: str | None,
    ) -> str | None:
        return surface or session.projection.active_surface or session.projection.origin_surface

    @staticmethod
    def _resolved_run_source(
        session: "MainAgentSessionState",
        *,
        source: str | None = None,
        projection: dict[str, Any] | None = None,
    ) -> str | None:
        if _safe_text(source):
            return _safe_text(source) or None
        run_surface = _safe_text((projection or {}).get("active_surface"))
        if run_surface:
            return run_surface
        return _safe_text(session.projection.active_surface or session.projection.origin_surface) or None


__all__ = ["RuntimeSessionRunControlHandler"]
