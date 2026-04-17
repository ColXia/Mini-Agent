"""Session-task use case owner for session CRUD, read models, and turn prep."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_agent.agent_core.engine import Agent
from mini_agent.application.interaction_request_adapter import ApplicationInteractionBinding
from mini_agent.application.managed_session_turn import ManagedSessionTurn
from mini_agent.application.session_runtime_port import SessionRuntimePort
from mini_agent.interfaces import (
    MainAgentDefaultSessionRequest,
    MainAgentSessionCreateRequest,
    MainAgentSessionDetail,
    MainAgentSessionForkRequest,
    MainAgentSessionMessage,
    MainAgentSessionMutationResponse,
    MainAgentSessionRenameRequest,
    MainAgentSessionShareRequest,
    MainAgentSessionSummary,
)


class SessionTaskService:
    """Owns session/task application behavior during the v11.1 transition."""

    def __init__(self, *, runtime_manager: SessionRuntimePort) -> None:
        self._runtime_manager = runtime_manager

    def validate_workspace(self, workspace_dir: Path) -> None:
        self._runtime_manager.validate_workspace(workspace_dir)

    async def list_sessions(
        self,
        *,
        workspace_dir: Path | None = None,
        shared_only: bool = False,
    ) -> list[MainAgentSessionSummary]:
        return await self._runtime_manager.list_sessions(
            workspace_dir=workspace_dir,
            shared_only=shared_only,
        )

    async def create_session(
        self,
        request: MainAgentSessionCreateRequest,
        *,
        workspace_dir: Path,
    ) -> MainAgentSessionDetail:
        session = await self._runtime_manager.create_session(
            workspace_dir=workspace_dir,
            title=request.title,
            surface=request.surface,
            shared=request.shared,
        )
        return await self._runtime_manager.get_session_detail(session.session_id, recent_limit=50)

    async def ensure_default_session(
        self,
        request: MainAgentDefaultSessionRequest,
        *,
        workspace_dir: Path,
    ) -> MainAgentSessionDetail:
        session = await self._runtime_manager.ensure_default_session(
            workspace_dir,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return await self._runtime_manager.get_session_detail(session.session_id, recent_limit=50)

    async def create_derived_session(
        self,
        parent_session_id: str,
        request: MainAgentSessionForkRequest,
    ) -> MainAgentSessionDetail:
        binding = ApplicationInteractionBinding.from_request(request, default_surface="tui")
        session = await self._runtime_manager.create_derived_session(
            parent_session_id=parent_session_id,
            title=request.title,
            reason="fork",
            **binding.as_kwargs(),
        )
        return await self._runtime_manager.get_session_detail(session.session_id, recent_limit=50)

    async def get_session_detail(self, session_id: str, *, recent_limit: int = 50) -> MainAgentSessionDetail:
        return await self._runtime_manager.get_session_detail(session_id, recent_limit=recent_limit)

    async def get_session_messages(self, session_id: str, *, limit: int = 10) -> list[MainAgentSessionMessage]:
        return await self._runtime_manager.get_recent_messages(session_id, limit=limit)

    async def delete_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        await self._runtime_manager.delete_session(session_id)
        return MainAgentSessionMutationResponse(status="deleted", session_id=session_id)

    async def rename_session(
        self,
        session_id: str,
        request: MainAgentSessionRenameRequest,
    ) -> MainAgentSessionMutationResponse:
        summary = await self._runtime_manager.rename_session(session_id, title=request.title)
        return MainAgentSessionMutationResponse(
            status="renamed",
            session_id=summary.session_id,
            active_surface=summary.active_surface,
            title=summary.title,
            shared=summary.shared,
        )

    async def set_session_shared(
        self,
        session_id: str,
        request: MainAgentSessionShareRequest,
    ) -> MainAgentSessionMutationResponse:
        summary = await self._runtime_manager.set_session_shared(session_id, shared=request.shared)
        return MainAgentSessionMutationResponse(
            status="shared" if summary.shared else "unshared",
            session_id=summary.session_id,
            active_surface=summary.active_surface,
            title=summary.title,
            shared=summary.shared,
        )

    async def reset_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        await self._runtime_manager.reset_session(session_id)
        return MainAgentSessionMutationResponse(status="reset", session_id=session_id)

    async def build_ephemeral_agent(self, workspace_dir: Path) -> Agent:
        return await self._runtime_manager.build_ephemeral_agent(workspace_dir)

    async def prepare_derived_chat_turn(
        self,
        *,
        parent_session_id: str,
        message: str,
        title: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        running_detail: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> ManagedSessionTurn:
        binding = ApplicationInteractionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        session = await self._runtime_manager.create_derived_session(
            parent_session_id=parent_session_id,
            title=title,
            reason=reason,
            metadata=metadata,
            **binding.as_kwargs(),
        )
        return ManagedSessionTurn(
            turn_scope=self._runtime_manager.turn_scope_handler,
            session=session,
            binding=binding,
            user_message=message,
            running_detail=running_detail,
        )

    async def prepare_chat_turn(
        self,
        *,
        workspace_dir: Path,
        message: str,
        session_id: str | None = None,
        session_title_hint: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        running_detail: str,
    ) -> ManagedSessionTurn:
        binding = ApplicationInteractionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        session = await self._runtime_manager.get_or_create_session(
            session_id,
            workspace_dir,
            **binding.as_kwargs(),
            session_title_hint=session_title_hint,
        )
        await self._runtime_manager.ensure_session_runtime_policy_ready_for_turn(
            session,
            **binding.as_kwargs(),
        )
        return ManagedSessionTurn(
            turn_scope=self._runtime_manager.turn_scope_handler,
            session=session,
            binding=binding,
            user_message=message,
            running_detail=running_detail,
        )


__all__ = ["SessionTaskService"]
