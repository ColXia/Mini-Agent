"""Shared session application service for gateway/terminal surfaces."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mini_agent.agent import Agent
from mini_agent.interfaces import (
    MainAgentSessionApprovalResponse,
    MainAgentSessionContextRequest,
    MainAgentSessionContextResponse,
    MainAgentSessionControlResponse,
    MainAgentSessionCreateRequest,
    MainAgentSessionDetail,
    MainAgentSessionForkRequest,
    MainAgentSessionMemoryRequest,
    MainAgentSessionMemoryResponse,
    MainAgentSessionMessage,
    MainAgentSessionModelSelectionRequest,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionMutationResponse,
    MainAgentSessionRenameRequest,
    MainAgentSessionRuntimePolicyRequest,
    MainAgentSessionRuntimePolicyResponse,
    MainAgentSessionShareRequest,
    MainAgentSessionSkillRequest,
    MainAgentSessionSkillResponse,
    MainAgentSessionSummary,
)
from mini_agent.runtime.main_agent_runtime_manager import MainAgentRuntimeManager
from mini_agent.runtime.interaction_surface import resolve_interaction_binding
from mini_agent.runtime.session_state import MainAgentSessionState
from mini_agent.runtime.session_turn_scope_handler import RuntimeSessionTurnScopeHandler


@dataclass(frozen=True)
class SessionSurfaceBinding:
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None

    @classmethod
    def from_values(
        cls,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        default_surface: str | None = None,
    ) -> SessionSurfaceBinding:
        binding = resolve_interaction_binding(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            default_surface=default_surface,
        )
        return cls(
            surface=binding.surface,
            channel_type=binding.channel_type,
            conversation_id=binding.conversation_id,
            sender_id=binding.sender_id,
        )

    @classmethod
    def from_request(
        cls,
        request: Any,
        *,
        default_surface: str | None = None,
    ) -> SessionSurfaceBinding:
        return cls.from_values(
            surface=getattr(request, "surface", None),
            channel_type=getattr(request, "channel_type", None),
            conversation_id=getattr(request, "conversation_id", None),
            sender_id=getattr(request, "sender_id", None),
            default_surface=default_surface,
        )

    def as_kwargs(self) -> dict[str, str | None]:
        return {
            "surface": self.surface,
            "channel_type": self.channel_type,
            "conversation_id": self.conversation_id,
            "sender_id": self.sender_id,
        }


class ManagedSessionTurn(AbstractAsyncContextManager["ManagedSessionTurn"]):
    """Scoped session turn lease that owns lock/lifecycle boundaries."""

    def __init__(
        self,
        *,
        turn_scope: RuntimeSessionTurnScopeHandler,
        session: MainAgentSessionState,
        binding: SessionSurfaceBinding,
        user_message: str,
        running_detail: str,
    ) -> None:
        self._turn_scope = turn_scope
        self._session = session
        self._binding = binding
        self._user_message = user_message
        self._running_detail = running_detail
        self._entered = False
        self._recovery_context: dict[str, Any] | None = None

    @property
    def session_id(self) -> str:
        return self._session.session_id

    @property
    def workspace_dir(self) -> Path:
        return self._session.workspace_dir

    @property
    def agent(self) -> Agent:
        return self._session.runtime.agent

    @property
    def active_surface(self) -> str:
        return self._session.projection.active_surface

    @property
    def origin_surface(self) -> str:
        return self._session.projection.origin_surface

    @property
    def channel_type(self) -> str | None:
        return self._session.projection.channel_type

    @property
    def conversation_id(self) -> str | None:
        return self._session.projection.conversation_id

    @property
    def sender_id(self) -> str | None:
        return self._session.projection.sender_id

    @property
    def context_policy(self) -> dict[str, Any]:
        return self._session.projection.context_policy

    @property
    def cancel_event(self):  # noqa: ANN201
        return self._session.runtime.cancel_event

    @property
    def busy(self) -> bool:
        return bool(self._session.projection.busy)

    @property
    def running_state(self) -> str:
        return self._session.projection.running_state

    @running_state.setter
    def running_state(self, value: str) -> None:
        self._session.projection.running_state = str(value or "")

    @property
    def pending_approvals(self) -> list[dict[str, Any]]:
        return list(self._session.runtime.pending_approvals)

    @property
    def updated_at(self):  # noqa: ANN201
        return self._session.updated_at

    @property
    def recovery_context(self) -> dict[str, Any] | None:
        return dict(self._recovery_context) if isinstance(self._recovery_context, dict) else None

    @property
    def token_usage(self) -> int:
        return int(getattr(self._session.runtime.agent, "api_total_tokens", 0) or 0)

    @property
    def message_count(self) -> int:
        messages = getattr(self._session.runtime.agent, "messages", None)
        return len(messages) if isinstance(messages, list) else 0

    async def __aenter__(self) -> ManagedSessionTurn:
        self._recovery_context = await self._turn_scope.enter(
            self._session,
            surface=self._binding.surface,
            channel_type=self._binding.channel_type,
            conversation_id=self._binding.conversation_id,
            sender_id=self._binding.sender_id,
            user_message=self._user_message,
            running_detail=self._running_detail,
        )
        self._entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        if self._entered:
            self._entered = False
            await self._turn_scope.exit(self._session)

    def touch(self) -> None:
        self._turn_scope.touch(self._session)

    def restore_prepared_context_state(self) -> None:
        self._turn_scope.restore_prepared_context_state(self._session)

    def capture_prepared_context_state(self) -> None:
        self._turn_scope.capture_prepared_context_state(self._session)

    def clear_recovery_context(self) -> None:
        self._turn_scope.clear_recovery_context(self._session)
        self._recovery_context = None

    def record_message(
        self,
        *,
        role: str,
        content: str,
        surface: str | None,
        metadata: dict[str, Any] | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> None:
        self._turn_scope.record_message(
            self._session,
            role=role,
            content=content,
            surface=surface,
            metadata=metadata,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    def record_activity(
        self,
        *,
        label: str,
        detail: str,
        surface: str | None,
        activity_id: str | None = None,
        preview: str = "",
        output_text: str = "",
        state: str = "",
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        return self._turn_scope.record_activity(
            self._session,
            label=label,
            detail=detail,
            surface=surface,
            activity_id=activity_id,
            preview=preview,
            output_text=output_text,
            state=state,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    def record_pending_approval(
        self,
        *,
        payload: dict[str, Any],
        future,
    ) -> dict[str, Any]:  # noqa: ANN001
        return self._turn_scope.record_pending_approval(
            self._session,
            payload=payload,
            future=future,
        )

    def clear_pending_approval(self, *, token: str | None = None) -> None:
        self._turn_scope.clear_pending_approval(self._session, token=token)


class SessionApplicationService:
    """Shared application-facing session operations and turn scoping."""

    def __init__(self, *, runtime_manager: MainAgentRuntimeManager) -> None:
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

    async def create_session(self, request: MainAgentSessionCreateRequest, *, workspace_dir: Path) -> MainAgentSessionDetail:
        session = await self._runtime_manager.create_session(
            workspace_dir=workspace_dir,
            title=request.title,
            surface=request.surface,
            shared=request.shared,
        )
        return await self._runtime_manager.get_session_detail(session.session_id, recent_limit=50)

    async def create_derived_session(
        self,
        parent_session_id: str,
        request: MainAgentSessionForkRequest,
    ) -> MainAgentSessionDetail:
        binding = SessionSurfaceBinding.from_request(request, default_surface="tui")
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

    async def cancel_session(
        self,
        session_id: str,
        *,
        reason: str | None,
        surface: str | None,
        channel_type: str | None,
        conversation_id: str | None,
        sender_id: str | None,
    ) -> MainAgentSessionMutationResponse:
        binding = SessionSurfaceBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return await self._runtime_manager.cancel_session_turn(
            session_id,
            reason=reason,
            **binding.as_kwargs(),
        )

    async def control_session(
        self,
        session_id: str,
        *,
        action: str,
        reason: str | None,
        surface: str | None,
        channel_type: str | None,
        conversation_id: str | None,
        sender_id: str | None,
    ) -> MainAgentSessionControlResponse:
        binding = SessionSurfaceBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return await self._runtime_manager.control_session_context(
            session_id,
            action=action,
            reason=reason,
            **binding.as_kwargs(),
        )

    async def update_session_context(
        self,
        session_id: str,
        request: MainAgentSessionContextRequest,
    ) -> MainAgentSessionContextResponse:
        binding = SessionSurfaceBinding.from_request(request)
        return await self._runtime_manager.update_session_context_policy(
            session_id,
            action=request.action,
            sources=request.sources,
            max_items=request.max_items,
            max_total_chars=request.max_total_chars,
            max_items_per_source=request.max_items_per_source,
            **binding.as_kwargs(),
        )

    async def manage_session_memory(
        self,
        session_id: str,
        request: MainAgentSessionMemoryRequest,
    ) -> MainAgentSessionMemoryResponse:
        binding = SessionSurfaceBinding.from_request(request)
        return await self._runtime_manager.manage_session_memory(
            session_id,
            action=request.action,
            engram_id=request.engram_id,
            content=request.content,
            query=request.query,
            day=request.day,
            export_format=request.export_format,
            detail_mode=request.detail_mode,
            **binding.as_kwargs(),
        )

    async def manage_session_skills(
        self,
        session_id: str,
        request: MainAgentSessionSkillRequest,
    ) -> MainAgentSessionSkillResponse:
        binding = SessionSurfaceBinding.from_request(request)
        return await self._runtime_manager.manage_session_skills(
            session_id,
            action=request.action,
            skill_name=request.skill_name,
            path=request.path,
            query=request.query,
            mode=request.mode,
            **binding.as_kwargs(),
        )

    async def update_session_model_selection(
        self,
        session_id: str,
        request: MainAgentSessionModelSelectionRequest,
    ) -> MainAgentSessionModelSelectionResponse:
        binding = SessionSurfaceBinding.from_request(request)
        return await self._runtime_manager.update_session_model_selection(
            session_id,
            provider_source=request.provider_source,
            provider_id=request.provider_id,
            model_id=request.model_id,
            **binding.as_kwargs(),
        )

    async def respond_to_approval(
        self,
        session_id: str,
        *,
        approved: bool,
        token: str | None,
        surface: str | None,
        channel_type: str | None,
        conversation_id: str | None,
        sender_id: str | None,
    ) -> MainAgentSessionApprovalResponse:
        binding = SessionSurfaceBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return await self._runtime_manager.resolve_pending_approval(
            session_id,
            approved=approved,
            token=token,
            **binding.as_kwargs(),
        )

    async def update_session_runtime_policy(
        self,
        session_id: str,
        request: MainAgentSessionRuntimePolicyRequest,
    ) -> MainAgentSessionRuntimePolicyResponse:
        binding = SessionSurfaceBinding.from_request(request)
        return await self._runtime_manager.update_session_runtime_policy(
            session_id,
            approval_profile=request.approval_profile,
            access_level=request.access_level,
            **binding.as_kwargs(),
        )

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
        binding = SessionSurfaceBinding.from_values(
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
        binding = SessionSurfaceBinding.from_values(
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
        return ManagedSessionTurn(
            turn_scope=self._runtime_manager.turn_scope_handler,
            session=session,
            binding=binding,
            user_message=message,
            running_detail=running_detail,
        )


__all__ = [
    "ManagedSessionTurn",
    "SessionApplicationService",
    "SessionSurfaceBinding",
]
