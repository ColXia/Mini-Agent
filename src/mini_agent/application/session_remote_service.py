"""Client-side session service backed by the local gateway client."""

from __future__ import annotations

from typing import Any, Sequence

from mini_agent.interfaces import (
    MainAgentSessionApprovalRequest,
    MainAgentSessionApprovalResponse,
    MainAgentSessionContextRequest,
    MainAgentSessionContextResponse,
    MainAgentSessionControlRequest,
    MainAgentSessionControlResponse,
    MainAgentSessionCreateRequest,
    MainAgentSessionDetail,
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


class RemoteSessionService:
    """Typed client-side facade over the TUI gateway HTTP client."""

    def __init__(self, *, gateway_client: Any) -> None:
        self._gateway_client = gateway_client

    @staticmethod
    def _list_model(model: type, payload: Sequence[Any]) -> list[Any]:
        return [model.model_validate(item) for item in payload if isinstance(item, dict)]

    async def list_sessions(
        self,
        *,
        workspace_dir: str | None = None,
        shared_only: bool = False,
    ) -> list[MainAgentSessionSummary]:
        payload = await self._gateway_client.list_sessions(workspace_dir=workspace_dir, shared_only=shared_only)
        return self._list_model(MainAgentSessionSummary, payload if isinstance(payload, list) else [])

    def list_sessions_sync(
        self,
        *,
        workspace_dir: str | None = None,
        shared_only: bool = False,
    ) -> list[MainAgentSessionSummary]:
        payload = self._gateway_client.list_sessions_sync(workspace_dir=workspace_dir, shared_only=shared_only)
        return self._list_model(MainAgentSessionSummary, payload if isinstance(payload, list) else [])

    async def get_session_detail(self, session_id: str, *, recent_limit: int = 80) -> MainAgentSessionDetail:
        payload = await self._gateway_client.get_session_detail(session_id, recent_limit=recent_limit)
        return MainAgentSessionDetail.model_validate(payload)

    def get_session_detail_sync(self, session_id: str, *, recent_limit: int = 80) -> MainAgentSessionDetail:
        payload = self._gateway_client.get_session_detail_sync(session_id, recent_limit=recent_limit)
        return MainAgentSessionDetail.model_validate(payload)

    async def get_session_messages(self, session_id: str, *, limit: int = 10) -> list[MainAgentSessionMessage]:
        payload = await self._gateway_client.get_session_messages(session_id, limit=limit)
        return self._list_model(MainAgentSessionMessage, payload if isinstance(payload, list) else [])

    async def create_session(self, request: MainAgentSessionCreateRequest) -> MainAgentSessionDetail:
        payload = await self._gateway_client.create_session(
            workspace_dir=request.workspace_dir or ".",
            title=request.title,
            surface=request.surface or "tui",
            shared=request.shared,
        )
        return MainAgentSessionDetail.model_validate(payload)

    def create_session_sync(self, request: MainAgentSessionCreateRequest) -> MainAgentSessionDetail:
        payload = self._gateway_client.create_session_sync(
            workspace_dir=request.workspace_dir or ".",
            title=request.title,
            surface=request.surface or "tui",
            shared=request.shared,
        )
        return MainAgentSessionDetail.model_validate(payload)

    async def rename_session(
        self,
        session_id: str,
        request: MainAgentSessionRenameRequest,
    ) -> MainAgentSessionMutationResponse:
        payload = await self._gateway_client.rename_session(session_id, title=request.title)
        return MainAgentSessionMutationResponse.model_validate(payload)

    async def set_session_shared(
        self,
        session_id: str,
        request: MainAgentSessionShareRequest,
    ) -> MainAgentSessionMutationResponse:
        payload = await self._gateway_client.set_session_shared(session_id, shared=request.shared)
        return MainAgentSessionMutationResponse.model_validate(payload)

    async def reset_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        payload = await self._gateway_client.reset_session(session_id)
        return MainAgentSessionMutationResponse.model_validate(payload)

    async def delete_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        payload = await self._gateway_client.delete_session(session_id)
        return MainAgentSessionMutationResponse.model_validate(payload)

    async def cancel_session(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionMutationResponse:
        payload = await self._gateway_client.cancel_session(
            session_id,
            reason=reason,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return MainAgentSessionMutationResponse.model_validate(payload)

    async def control_session(
        self,
        session_id: str,
        request: MainAgentSessionControlRequest,
    ) -> MainAgentSessionControlResponse:
        payload = await self._gateway_client.control_session(
            session_id,
            action=request.action,
            reason=request.reason,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentSessionControlResponse.model_validate(payload)

    async def update_session_context(
        self,
        session_id: str,
        request: MainAgentSessionContextRequest,
    ) -> MainAgentSessionContextResponse:
        payload = await self._gateway_client.update_session_context(
            session_id,
            action=request.action,
            sources=request.sources,
            max_items=request.max_items,
            max_total_chars=request.max_total_chars,
            max_items_per_source=request.max_items_per_source,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentSessionContextResponse.model_validate(payload)

    async def manage_session_memory(
        self,
        session_id: str,
        request: MainAgentSessionMemoryRequest,
    ) -> MainAgentSessionMemoryResponse:
        payload = await self._gateway_client.manage_session_memory(
            session_id,
            action=request.action,
            engram_id=request.engram_id,
            content=request.content,
            query=request.query,
            day=request.day,
            export_format=request.export_format,
            detail_mode=request.detail_mode,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentSessionMemoryResponse.model_validate(payload)

    async def manage_session_skill(
        self,
        session_id: str,
        request: MainAgentSessionSkillRequest,
    ) -> MainAgentSessionSkillResponse:
        payload = await self._gateway_client.manage_session_skill(
            session_id,
            action=request.action,
            skill_name=request.skill_name,
            path=request.path,
            query=request.query,
            mode=request.mode,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentSessionSkillResponse.model_validate(payload)

    async def update_session_model(
        self,
        session_id: str,
        request: MainAgentSessionModelSelectionRequest,
    ) -> MainAgentSessionModelSelectionResponse:
        payload = await self._gateway_client.update_session_model(
            session_id,
            provider_source=request.provider_source,
            provider_id=request.provider_id,
            model_id=request.model_id,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentSessionModelSelectionResponse.model_validate(payload)

    async def update_session_runtime_policy(
        self,
        session_id: str,
        request: MainAgentSessionRuntimePolicyRequest,
    ) -> MainAgentSessionRuntimePolicyResponse:
        payload = await self._gateway_client.update_session_runtime_policy(
            session_id,
            approval_profile=request.approval_profile,
            access_level=request.access_level,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentSessionRuntimePolicyResponse.model_validate(payload)

    async def respond_to_approval(
        self,
        session_id: str,
        request: MainAgentSessionApprovalRequest,
    ) -> MainAgentSessionApprovalResponse:
        payload = await self._gateway_client.respond_to_approval(
            session_id,
            approved=request.approved,
            token=request.token,
            surface=request.surface,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )
        return MainAgentSessionApprovalResponse.model_validate(payload)


__all__ = ["RemoteSessionService"]
