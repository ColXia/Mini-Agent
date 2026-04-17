"""Session agent-side controls: context compaction and KB toggles."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from fastapi import HTTPException

from mini_agent.agent_core.context.control_result_service import (
    SessionContextControlResultService,
)
from mini_agent.interfaces import MainAgentSessionControlResponse
from mini_agent.runtime.support.session_control_error_service import SessionControlErrorService
from mini_agent.runtime.support.session_control_models import (
    RuntimeSessionControlCommand,
    RuntimeSessionControlExecution,
    SESSION_AGENT_CONTROL_ACTIONS,
    normalize_session_control_action,
)
from mini_agent.tools.knowledge_base_control_service import KnowledgeBaseControlService

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionAgentControlHandler:
    normalize_surface: Callable[[str | None], str | None]
    apply_agent_knowledge_base_enabled: Callable[[Any, bool], bool]
    refresh_runtime_projection: Callable[["MainAgentSessionState"], tuple[dict[str, Any], dict[str, Any]]]

    def validate_action(self, action: str) -> str:
        normalized = normalize_session_control_action(action)
        if normalized not in SESSION_AGENT_CONTROL_ACTIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported session control action: {action}")
        return normalized

    async def execute(
        self,
        session: "MainAgentSessionState",
        command: RuntimeSessionControlCommand,
    ) -> RuntimeSessionControlExecution:
        normalized_action = self.validate_action(command.action)
        normalized_reason = _safe_text(command.reason) or None

        if session.projection.busy:
            raise HTTPException(status_code=409, detail=SessionControlErrorService.busy_detail())

        active_surface = self.normalize_surface(session.projection.active_surface or session.projection.origin_surface)
        if normalized_action in {"kb_on", "kb_off"}:
            response = await self._execute_knowledge_base_action(
                session,
                action=normalized_action,
                reason=normalized_reason,
                active_surface=active_surface,
            )
        else:
            response = await self._execute_context_action(
                session,
                action=normalized_action,
                reason=normalized_reason,
                active_surface=active_surface,
            )

        return RuntimeSessionControlExecution(
            response=response,
            transcript_summary=self._control_summary(normalized_action, applied=response.applied),
            transcript_details=self._control_details(response),
        )

    async def _execute_knowledge_base_action(
        self,
        session: "MainAgentSessionState",
        *,
        action: str,
        reason: str | None,
        active_surface: str | None,
    ) -> MainAgentSessionControlResponse:
        toggle = await KnowledgeBaseControlService.toggle(
            current_enabled=session.projection.knowledge_base_enabled,
            desired_enabled=(action == "kb_on"),
            toggle_callback=lambda enabled: self.apply_agent_knowledge_base_enabled(
                session.runtime.agent,
                enabled,
            ),
        )
        self.refresh_runtime_projection(session)
        return MainAgentSessionControlResponse(
            status="controlled",
            session_id=session.session_id,
            action=action,
            applied=toggle.applied,
            active_surface=active_surface,
            reason=reason,
            knowledge_base_enabled=bool(session.projection.knowledge_base_enabled),
        )

    async def _execute_context_action(
        self,
        session: "MainAgentSessionState",
        *,
        action: str,
        reason: str | None,
        active_surface: str | None,
    ) -> MainAgentSessionControlResponse:
        control_method = (
            getattr(session.runtime.agent, "compact_context", None)
            if action == "compact"
            else getattr(session.runtime.agent, "drop_memories", None)
        )
        if control_method is None:
            raise HTTPException(status_code=400, detail=f"Session control not supported: {action}")

        result = control_method(reason=reason)
        if inspect.isawaitable(result):
            result = await result
        normalized = SessionContextControlResultService.normalize_result(
            action=action,
            payload=result,
            reason=reason,
        )
        self.refresh_runtime_projection(session)

        return MainAgentSessionControlResponse(
            status="controlled",
            session_id=session.session_id,
            action=action,
            applied=normalized.applied,
            active_surface=active_surface,
            reason=reason,
            message_count_before=normalized.message_count_before,
            message_count_after=normalized.message_count_after,
            token_count_before=normalized.token_count_before,
            token_count_after=normalized.token_count_after,
            knowledge_base_enabled=bool(session.projection.knowledge_base_enabled),
            stats=dict(normalized.stats),
        )

    @staticmethod
    def _control_summary(action: str, *, applied: bool) -> str:
        if action == "compact":
            return SessionContextControlResultService.summary(action="compact", applied=applied)
        if action == "kb_on":
            return KnowledgeBaseControlService.toggle_summary(enabled=True, applied=applied)
        if action == "kb_off":
            return KnowledgeBaseControlService.toggle_summary(enabled=False, applied=applied)
        return SessionContextControlResultService.summary(action="drop_memories", applied=applied)

    @staticmethod
    def _control_details(response: MainAgentSessionControlResponse) -> str:
        normalized = normalize_session_control_action(response.action)
        if normalized in {"kb_on", "kb_off"}:
            return KnowledgeBaseControlService.control_details(
                action=response.action,
                enabled=bool(response.knowledge_base_enabled),
                reason=response.reason,
            )
        return SessionContextControlResultService.details(
            action=response.action,
            message_count_before=response.message_count_before,
            message_count_after=response.message_count_after,
            token_count_before=response.token_count_before,
            token_count_after=response.token_count_after,
            stats=dict(response.stats or {}),
            reason=response.reason,
        )


__all__ = [
    "RuntimeSessionAgentControlHandler",
]
