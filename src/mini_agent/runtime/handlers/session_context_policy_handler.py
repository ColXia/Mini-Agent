"""Context policy command ownership for managed sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Sequence

from mini_agent.agent_core.context.command_service import (
    ContextCommandError,
    ContextCommandRequest,
    ContextCommandService,
)
from mini_agent.agent_core.context.turn_context import context_policy_summary_line, format_context_policy_details
from mini_agent.interfaces.agent import MainAgentSessionContextResponse
from mini_agent.runtime.handlers.session_command_coordinator import (
    RuntimeSessionCommandCoordinator,
    RuntimeSessionCommandTranscript,
)
from mini_agent.runtime.handlers.session_agent_control_handler import SessionControlErrorService

if TYPE_CHECKING:
    from mini_agent.session.store_records import MainAgentSessionState


@dataclass(frozen=True, slots=True)
class RuntimeSessionContextPolicyExecution:
    response: MainAgentSessionContextResponse
    transcript_command: str
    transcript_summary: str
    transcript_details: str


@dataclass(slots=True)
class RuntimeSessionContextPolicyHandler:
    normalize_surface: Callable[[str | None], str]
    normalize_context_policy_payload: Callable[[Any], dict[str, Any]]
    session_commands: RuntimeSessionCommandCoordinator
    session_context_commands: ContextCommandService

    async def update_context_policy(
        self,
        session: "MainAgentSessionState",
        *,
        action: str,
        sources: Sequence[str] | None = None,
        max_items: int | None = None,
        max_total_chars: int | None = None,
        max_items_per_source: int | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionContextResponse:
        command = ContextCommandRequest(
            action=action,
            sources=tuple(sources or ()),
            max_items=max_items,
            max_total_chars=max_total_chars,
            max_items_per_source=max_items_per_source,
        )
        execution = await self.session_commands.execute_locked(
            session,
            operation=lambda: self._execute_context_policy_update(session, command),
            transcript_builder=lambda execution: RuntimeSessionCommandTranscript(
                command=execution.transcript_command,
                summary=execution.transcript_summary,
                content=execution.transcript_details,
            ),
            surface=self._active_surface(session, surface),
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return execution.response

    def _execute_context_policy_update(
        self,
        session: "MainAgentSessionState",
        command: ContextCommandRequest,
    ) -> RuntimeSessionContextPolicyExecution:
        from fastapi import HTTPException

        if session.projection.busy:
            raise HTTPException(status_code=409, detail=SessionControlErrorService.busy_detail())
        try:
            mutation = self.session_context_commands.apply_mutation(
                current_policy=session.projection.context_policy,
                command=command,
            )
        except ContextCommandError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        normalized_policy = self.normalize_context_policy_payload(mutation.policy)
        session.projection.context_policy = dict(normalized_policy)
        response = MainAgentSessionContextResponse(
            status="updated",
            session_id=session.session_id,
            action=mutation.action,
            active_surface=self.normalize_surface(
                session.projection.active_surface or session.projection.origin_surface
            ),
            context_policy=dict(normalized_policy),
        )
        transcript_summary = context_policy_summary_line(normalized_policy, include_default=True)
        transcript_details = format_context_policy_details(normalized_policy, include_header=True)
        return RuntimeSessionContextPolicyExecution(
            response=response,
            transcript_command=mutation.command_name,
            transcript_summary=transcript_summary,
            transcript_details=transcript_details,
        )

    @staticmethod
    def _active_surface(
        session: "MainAgentSessionState",
        surface: str | None,
    ) -> str | None:
        return surface or session.projection.active_surface or session.projection.origin_surface


__all__ = [
    "RuntimeSessionContextPolicyExecution",
    "RuntimeSessionContextPolicyHandler",
]
