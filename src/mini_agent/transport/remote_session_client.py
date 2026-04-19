"""Typed client-side remote session client over the shared gateway transport."""

from __future__ import annotations

from typing import Any, Sequence

from mini_agent.interfaces.agent import (
    MainAgentDefaultSessionRequest,
    MainAgentSessionApprovalRequest,
    MainAgentSessionApprovalResponse,
    MainAgentSessionCancelRequest,
    MainAgentSessionContextRequest,
    MainAgentSessionContextResponse,
    MainAgentSessionControlRequest,
    MainAgentSessionControlResponse,
    MainAgentSessionCreateRequest,
    MainAgentSessionDetail,
    MainAgentSessionForkRequest,
    MainAgentSessionInterruptRequest,
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
from mini_agent.runtime.support.interaction_surface import resolve_interaction_binding
from mini_agent.transport.session_transport_port import RemoteSessionTransportPort


class RemoteSessionClient:
    """Typed client-side facade over the shared remote session transport."""

    def __init__(self, *, session_transport: RemoteSessionTransportPort) -> None:
        self._session_transport = session_transport

    @staticmethod
    def _list_model(model: type, payload: Sequence[Any]) -> list[Any]:
        return [model.model_validate(item) for item in payload if isinstance(item, dict)]

    @staticmethod
    def _create_session_payload(request: MainAgentSessionCreateRequest) -> dict[str, Any]:
        binding = resolve_interaction_binding(
            surface=request.surface,
            channel_type=None,
            default_surface="tui",
        )
        return {
            "workspace_dir": request.workspace_dir or ".",
            "title": request.title,
            "surface": binding.surface or "tui",
            "shared": request.shared,
        }

    @staticmethod
    def _binding_kwargs(
        *,
        surface: str | None,
        channel_type: str | None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        default_surface: str | None = None,
    ) -> dict[str, str | None]:
        binding = resolve_interaction_binding(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            default_surface=default_surface,
        )
        return {
            "surface": binding.surface,
            "channel_type": binding.channel_type,
            "conversation_id": binding.conversation_id,
            "sender_id": binding.sender_id,
        }

    async def list_sessions(
        self,
        *,
        workspace_dir: str | None = None,
        shared_only: bool = False,
    ) -> list[MainAgentSessionSummary]:
        payload = await self._session_transport.list_sessions(workspace_dir=workspace_dir, shared_only=shared_only)
        return self._list_model(MainAgentSessionSummary, payload if isinstance(payload, list) else [])

    def list_sessions_sync(
        self,
        *,
        workspace_dir: str | None = None,
        shared_only: bool = False,
    ) -> list[MainAgentSessionSummary]:
        payload = self._session_transport.list_sessions_sync(workspace_dir=workspace_dir, shared_only=shared_only)
        return self._list_model(MainAgentSessionSummary, payload if isinstance(payload, list) else [])

    async def ensure_default_session(self, request: MainAgentDefaultSessionRequest) -> MainAgentSessionDetail:
        payload = await self._session_transport.ensure_default_session(
            workspace_dir=request.workspace_dir or ".",
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
                default_surface="tui",
            ),
        )
        return MainAgentSessionDetail.model_validate(payload)

    def ensure_default_session_sync(self, request: MainAgentDefaultSessionRequest) -> MainAgentSessionDetail:
        payload = self._session_transport.ensure_default_session_sync(
            workspace_dir=request.workspace_dir or ".",
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
                default_surface="tui",
            ),
        )
        return MainAgentSessionDetail.model_validate(payload)

    async def get_session_detail(self, session_id: str, *, recent_limit: int = 80) -> MainAgentSessionDetail:
        payload = await self._session_transport.get_session_detail(session_id, recent_limit=recent_limit)
        return MainAgentSessionDetail.model_validate(payload)

    def get_session_detail_sync(self, session_id: str, *, recent_limit: int = 80) -> MainAgentSessionDetail:
        payload = self._session_transport.get_session_detail_sync(session_id, recent_limit=recent_limit)
        return MainAgentSessionDetail.model_validate(payload)

    async def get_session_messages(self, session_id: str, *, limit: int = 10) -> list[MainAgentSessionMessage]:
        payload = await self._session_transport.get_session_messages(session_id, limit=limit)
        return self._list_model(MainAgentSessionMessage, payload if isinstance(payload, list) else [])

    async def create_session(self, request: MainAgentSessionCreateRequest) -> MainAgentSessionDetail:
        payload = await self._session_transport.create_session(**self._create_session_payload(request))
        return MainAgentSessionDetail.model_validate(payload)

    def create_session_sync(self, request: MainAgentSessionCreateRequest) -> MainAgentSessionDetail:
        payload = self._session_transport.create_session_sync(**self._create_session_payload(request))
        return MainAgentSessionDetail.model_validate(payload)

    async def create_derived_session(
        self,
        parent_session_id: str,
        request: MainAgentSessionForkRequest,
    ) -> MainAgentSessionDetail:
        payload = await self._session_transport.create_derived_session(
            parent_session_id,
            title=request.title,
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
                default_surface="tui",
            ),
        )
        return MainAgentSessionDetail.model_validate(payload)

    def create_derived_session_sync(
        self,
        parent_session_id: str,
        request: MainAgentSessionForkRequest,
    ) -> MainAgentSessionDetail:
        payload = self._session_transport.create_derived_session_sync(
            parent_session_id,
            title=request.title,
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
                default_surface="tui",
            ),
        )
        return MainAgentSessionDetail.model_validate(payload)

    async def rename_session(
        self,
        session_id: str,
        request: MainAgentSessionRenameRequest,
    ) -> MainAgentSessionMutationResponse:
        payload = await self._session_transport.rename_session(session_id, title=request.title)
        return MainAgentSessionMutationResponse.model_validate(payload)

    def rename_session_sync(
        self,
        session_id: str,
        request: MainAgentSessionRenameRequest,
    ) -> MainAgentSessionMutationResponse:
        payload = self._session_transport.rename_session_sync(session_id, title=request.title)
        return MainAgentSessionMutationResponse.model_validate(payload)

    async def set_session_shared(
        self,
        session_id: str,
        request: MainAgentSessionShareRequest,
    ) -> MainAgentSessionMutationResponse:
        payload = await self._session_transport.set_session_shared(session_id, shared=request.shared)
        return MainAgentSessionMutationResponse.model_validate(payload)

    def set_session_shared_sync(
        self,
        session_id: str,
        request: MainAgentSessionShareRequest,
    ) -> MainAgentSessionMutationResponse:
        payload = self._session_transport.set_session_shared_sync(session_id, shared=request.shared)
        return MainAgentSessionMutationResponse.model_validate(payload)

    async def reset_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        payload = await self._session_transport.reset_session(session_id)
        return MainAgentSessionMutationResponse.model_validate(payload)

    async def delete_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        payload = await self._session_transport.delete_session(session_id)
        return MainAgentSessionMutationResponse.model_validate(payload)

    async def cancel_session(
        self,
        session_id: str,
        request: MainAgentSessionCancelRequest,
    ) -> MainAgentSessionMutationResponse:
        payload = await self._session_transport.cancel_session(
            session_id,
            reason=request.reason,
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
            ),
        )
        return MainAgentSessionMutationResponse.model_validate(payload)

    async def interrupt_session(
        self,
        session_id: str,
        request: MainAgentSessionInterruptRequest,
    ) -> MainAgentSessionMutationResponse:
        payload = await self._session_transport.interrupt_session(
            session_id,
            reason=request.reason,
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
            ),
        )
        return MainAgentSessionMutationResponse.model_validate(payload)

    async def control_session(
        self,
        session_id: str,
        request: MainAgentSessionControlRequest,
    ) -> MainAgentSessionControlResponse:
        payload = await self._session_transport.control_session(
            session_id,
            action=request.action,
            reason=request.reason,
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
            ),
        )
        return MainAgentSessionControlResponse.model_validate(payload)

    def control_session_sync(
        self,
        session_id: str,
        request: MainAgentSessionControlRequest,
    ) -> MainAgentSessionControlResponse:
        payload = self._session_transport.control_session_sync(
            session_id,
            action=request.action,
            reason=request.reason,
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
            ),
        )
        return MainAgentSessionControlResponse.model_validate(payload)

    async def update_session_context(
        self,
        session_id: str,
        request: MainAgentSessionContextRequest,
    ) -> MainAgentSessionContextResponse:
        payload = await self._session_transport.update_session_context(
            session_id,
            action=request.action,
            sources=request.sources,
            max_items=request.max_items,
            max_total_chars=request.max_total_chars,
            max_items_per_source=request.max_items_per_source,
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
            ),
        )
        return MainAgentSessionContextResponse.model_validate(payload)

    async def manage_session_memory(
        self,
        session_id: str,
        request: MainAgentSessionMemoryRequest,
    ) -> MainAgentSessionMemoryResponse:
        payload = await self._session_transport.manage_session_memory(
            session_id,
            action=request.action,
            engram_id=request.engram_id,
            content=request.content,
            query=request.query,
            day=request.day,
            export_format=request.export_format,
            detail_mode=request.detail_mode,
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
            ),
        )
        return MainAgentSessionMemoryResponse.model_validate(payload)

    async def manage_session_skill(
        self,
        session_id: str,
        request: MainAgentSessionSkillRequest,
    ) -> MainAgentSessionSkillResponse:
        payload = await self._session_transport.manage_session_skill(
            session_id,
            action=request.action,
            skill_name=request.skill_name,
            path=request.path,
            query=request.query,
            mode=request.mode,
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
            ),
        )
        return MainAgentSessionSkillResponse.model_validate(payload)

    async def update_session_model(
        self,
        session_id: str,
        request: MainAgentSessionModelSelectionRequest,
    ) -> MainAgentSessionModelSelectionResponse:
        payload = await self._session_transport.update_session_model(
            session_id,
            provider_source=request.provider_source,
            provider_id=request.provider_id,
            model_id=request.model_id,
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
            ),
        )
        return MainAgentSessionModelSelectionResponse.model_validate(payload)

    def update_session_model_sync(
        self,
        session_id: str,
        request: MainAgentSessionModelSelectionRequest,
    ) -> MainAgentSessionModelSelectionResponse:
        payload = self._session_transport.update_session_model_sync(
            session_id,
            provider_source=request.provider_source,
            provider_id=request.provider_id,
            model_id=request.model_id,
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
            ),
        )
        return MainAgentSessionModelSelectionResponse.model_validate(payload)

    async def update_session_runtime_policy(
        self,
        session_id: str,
        request: MainAgentSessionRuntimePolicyRequest,
    ) -> MainAgentSessionRuntimePolicyResponse:
        payload = await self._session_transport.update_session_runtime_policy(
            session_id,
            approval_profile=request.approval_profile,
            access_level=request.access_level,
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
            ),
        )
        return MainAgentSessionRuntimePolicyResponse.model_validate(payload)

    async def respond_to_approval(
        self,
        session_id: str,
        request: MainAgentSessionApprovalRequest,
    ) -> MainAgentSessionApprovalResponse:
        payload = await self._session_transport.respond_to_approval(
            session_id,
            approved=request.approved,
            token=request.token,
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
            ),
        )
        return MainAgentSessionApprovalResponse.model_validate(payload)

    def respond_to_approval_sync(
        self,
        session_id: str,
        request: MainAgentSessionApprovalRequest,
    ) -> MainAgentSessionApprovalResponse:
        payload = self._session_transport.respond_to_approval_sync(
            session_id,
            approved=request.approved,
            token=request.token,
            **self._binding_kwargs(
                surface=request.surface,
                channel_type=request.channel_type,
                conversation_id=request.conversation_id,
                sender_id=request.sender_id,
            ),
        )
        return MainAgentSessionApprovalResponse.model_validate(payload)


__all__ = ["RemoteSessionClient"]
