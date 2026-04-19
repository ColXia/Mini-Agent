"""Runtime policy command ownership for managed sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Sequence

from mini_agent.interfaces.agent import MainAgentSessionRuntimePolicyResponse
from mini_agent.runtime.handlers.session_command_coordinator import (
    RuntimeSessionCommandCoordinator,
    RuntimeSessionCommandTranscript,
)
from mini_agent.runtime.orchestration.session_runtime_policy_coordinator import (
    SessionRuntimePolicyExecution,
    SessionRuntimePolicyPlan,
    SessionRuntimePolicyService,
)

if TYPE_CHECKING:
    from mini_agent.runtime.handlers.session_agent_runtime_handler import RuntimeSessionAgentRuntimeHandler
    from mini_agent.runtime.live_control.session_transcript_state_handler import (
        RuntimeSessionTranscriptStateHandler,
    )
    from mini_agent.session.store_records import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionRuntimePolicyHandler:
    normalize_surface: Callable[[str | None], str]
    normalize_sandbox_diagnostics_payload: Callable[[Any], dict[str, Any]]
    session_commands: RuntimeSessionCommandCoordinator
    session_runtime_policy: SessionRuntimePolicyService
    session_agent_runtime: "RuntimeSessionAgentRuntimeHandler"
    session_transcript_state: "RuntimeSessionTranscriptStateHandler"
    active_pending_approvals: Callable[["MainAgentSessionState"], Sequence[dict[str, Any]]] | None = None

    def _pending_approvals(self, session: "MainAgentSessionState") -> list[dict[str, Any]]:
        if callable(self.active_pending_approvals):
            try:
                payload = self.active_pending_approvals(session)
            except Exception:
                payload = None
            if isinstance(payload, Sequence):
                return [dict(item) for item in payload if isinstance(item, dict)]
        return []

    async def update_runtime_policy(
        self,
        session: "MainAgentSessionState",
        *,
        approval_profile: str | None = None,
        access_level: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionRuntimePolicyResponse:
        execution = await self.session_commands.execute_locked(
            session,
            operation=lambda: self._execute_runtime_policy_update(
                session,
                approval_profile=approval_profile,
                access_level=access_level,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            ),
            transcript_builder=lambda execution: RuntimeSessionCommandTranscript(
                command="policy",
                summary=self.session_runtime_policy.transcript_summary(execution.plan),
                content=self.session_runtime_policy.transcript_content(execution.plan),
            ),
            surface=self._active_surface(session, surface),
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return self._build_session_runtime_policy_response(
            session=session,
            plan=execution.plan,
            diagnostics=execution.diagnostics,
        )

    async def ensure_runtime_policy_ready_for_turn(
        self,
        session: "MainAgentSessionState",
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> SessionRuntimePolicyExecution | None:
        current_profile, current_access = self.session_runtime_policy.current_runtime_policy(
            agent=session.runtime.agent,
            sandbox_diagnostics=session.projection.sandbox_diagnostics,
        )
        autofix = self.session_runtime_policy.build_pre_turn_autofix_request(
            requested_surface=surface,
            origin_surface=session.projection.origin_surface,
            active_surface=session.projection.active_surface,
            shared=bool(session.projection.shared),
            current_approval_profile=current_profile,
            current_access_level=current_access,
        )
        if autofix is None:
            return None
        return await self.session_commands.execute_locked(
            session,
            operation=lambda: self._execute_runtime_policy_update(
                session,
                approval_profile=autofix.approval_profile,
                access_level=autofix.access_level,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            ),
        )

    def _build_session_runtime_policy_response(
        self,
        *,
        session: "MainAgentSessionState",
        plan: SessionRuntimePolicyPlan,
        diagnostics: dict[str, Any],
    ) -> MainAgentSessionRuntimePolicyResponse:
        active_surface = self.normalize_surface(
            session.projection.active_surface or session.projection.origin_surface
        )
        return MainAgentSessionRuntimePolicyResponse(
            status="updated",
            session_id=session.session_id,
            active_surface=active_surface,
            applied=True,
            approval_profile=plan.approval_profile,
            access_level=plan.access_level,
            summary=self.session_runtime_policy.command_summary(plan),
            details=self.session_runtime_policy.command_details(
                plan,
                session_label=_safe_text(session.projection.title) or None,
                session_id=session.session_id,
                active_surface=active_surface,
            ),
            status_text=self.session_runtime_policy.command_status_text(
                plan,
                session_label=_safe_text(session.projection.title) or None,
            ),
            sandbox_diagnostics=dict(diagnostics),
        )

    def _execute_runtime_policy_update(
        self,
        session: "MainAgentSessionState",
        *,
        approval_profile: str | None,
        access_level: str | None,
        surface: str | None,
        channel_type: str | None,
        conversation_id: str | None,
        sender_id: str | None,
    ) -> SessionRuntimePolicyExecution:
        current_profile, current_access = self.session_runtime_policy.current_runtime_policy(
            agent=session.runtime.agent,
            sandbox_diagnostics=session.projection.sandbox_diagnostics,
        )
        execution = self.session_runtime_policy.execute_update(
            current_approval_profile=current_profile,
            current_access_level=current_access,
            requested_approval_profile=approval_profile,
            requested_access_level=access_level,
            busy=bool(session.projection.busy),
            waiting_on_approval=bool(self._pending_approvals(session)),
            runtime_attached=session.runtime.agent is not None,
            sandbox_diagnostics=session.projection.sandbox_diagnostics,
            normalize_sandbox_diagnostics_payload=self.normalize_sandbox_diagnostics_payload,
            reconfigure_attached_runtime=(
                lambda resolved_profile, resolved_access: self.session_agent_runtime.reconfigure_runtime_policy(
                    session,
                    approval_profile=resolved_profile,
                    access_level=resolved_access,
                )
            )
            if session.runtime.agent is not None
            else None,
        )
        if session.runtime.agent is None:
            session.projection.sandbox_diagnostics = dict(execution.diagnostics)

        self.session_transcript_state.bind_surface(
            session,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return execution

    @staticmethod
    def _active_surface(
        session: "MainAgentSessionState",
        surface: str | None,
    ) -> str | None:
        return surface or session.projection.active_surface or session.projection.origin_surface


__all__ = ["RuntimeSessionRuntimePolicyHandler"]
