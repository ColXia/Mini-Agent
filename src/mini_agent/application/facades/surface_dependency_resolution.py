"""Dependency resolution helpers for the transitional surface facade."""

from __future__ import annotations

from mini_agent.application.user_services.agent_user_service import AgentUserService
from mini_agent.application.user_services.model_user_service import ModelUserService
from mini_agent.application.user_services.workspace_user_service import WorkspaceUserService
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.application.use_cases.session_task_service import SessionTaskService
from mini_agent.interfaces import (
    MainAgentSessionApprovalRequest,
    MainAgentSessionApprovalResponse,
    MainAgentSessionCancelRequest,
    MainAgentSessionMutationResponse,
)


class LegacySurfaceRunControlAdapter:
    """Bridge legacy session-service run control entrypoints into the surface seam."""

    def __init__(self, session_service: object) -> None:
        self._session_service = session_service

    async def cancel_session_run(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionMutationResponse:
        _ = source
        return await self._session_service.cancel_session(
            session_id,
            MainAgentSessionCancelRequest(
                reason=reason,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            ),
        )

    async def approve_session_wait(
        self,
        session_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionApprovalResponse:
        _ = (source, reason)
        return await self._session_service.respond_to_approval(
            session_id,
            MainAgentSessionApprovalRequest(
                approved=True,
                token=token,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            ),
        )

    async def deny_session_wait(
        self,
        session_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionApprovalResponse:
        _ = (source, reason)
        return await self._session_service.respond_to_approval(
            session_id,
            MainAgentSessionApprovalRequest(
                approved=False,
                token=token,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            ),
        )


def resolve_surface_session_task_service(
    session_service: object | None,
    explicit_service: SessionTaskService | None,
):
    if explicit_service is not None:
        return explicit_service
    if session_service is None:
        raise RuntimeError("Session task service is not configured.")
    return getattr(session_service, "session_task_service", session_service)


def resolve_surface_agent_entry_service(
    session_service: object | None,
    explicit_service: AgentUserService | None,
):
    if explicit_service is not None:
        return explicit_service
    if session_service is None:
        raise RuntimeError("Agent entry service is not configured.")
    return getattr(session_service, "agent_service", session_service)


def resolve_surface_model_entry_service(
    session_service: object | None,
    explicit_service: ModelUserService | None,
):
    if explicit_service is not None:
        return explicit_service
    if session_service is None:
        raise RuntimeError("Model entry service is not configured.")
    return getattr(session_service, "model_service", session_service)


def resolve_surface_workspace_entry_service(
    session_service: object | None,
    explicit_service: WorkspaceUserService | None,
):
    if explicit_service is not None:
        return explicit_service
    if session_service is None:
        raise RuntimeError("Workspace entry service is not configured.")
    resolved_service = getattr(session_service, "workspace_service", None)
    if resolved_service is not None:
        return resolved_service
    if all(
        hasattr(session_service, attr)
        for attr in (
            "list_workspaces",
            "get_workspace",
            "get_active_workspace",
            "switch_workspace",
            "get_workspace_runtime_summary",
        )
    ):
        return session_service
    raise RuntimeError("Workspace entry service is not configured.")


def resolve_surface_run_control_service(
    session_service: object | None,
    explicit_service: RunControlApplicationService | AgentUserService | None,
    explicit_agent_service: AgentUserService | None,
):
    if explicit_service is not None:
        return explicit_service
    if explicit_agent_service is not None and all(
        hasattr(explicit_agent_service, attr)
        for attr in ("cancel_session_run", "approve_session_wait", "deny_session_wait")
    ):
        return explicit_agent_service
    if session_service is None:
        raise RuntimeError("Run control service is not configured.")
    resolved_service = getattr(session_service, "run_control_service", None)
    if resolved_service is not None:
        return resolved_service
    if all(hasattr(session_service, attr) for attr in ("cancel_session", "respond_to_approval")):
        return LegacySurfaceRunControlAdapter(session_service)
    raise RuntimeError("Run control service is not configured.")


__all__ = [
    "LegacySurfaceRunControlAdapter",
    "resolve_surface_agent_entry_service",
    "resolve_surface_model_entry_service",
    "resolve_surface_run_control_service",
    "resolve_surface_session_task_service",
    "resolve_surface_workspace_entry_service",
]
