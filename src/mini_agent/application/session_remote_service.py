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
from mini_agent.application.session_service import SessionSurfaceBinding


class RemoteSessionService:
    """Typed client-side facade over the TUI gateway HTTP client."""

    def __init__(self, *, gateway_client: Any) -> None:
        self._gateway_client = gateway_client

    @staticmethod
    def _list_model(model: type, payload: Sequence[Any]) -> list[Any]:
        return [model.model_validate(item) for item in payload if isinstance(item, dict)]

    @staticmethod
    def _create_session_payload(request: MainAgentSessionCreateRequest) -> dict[str, Any]:
        binding = SessionSurfaceBinding.from_values(surface=request.surface or "tui")
        return {
            "workspace_dir": request.workspace_dir or ".",
            "title": request.title,
            "surface": binding.surface or "tui",
            "shared": request.shared,
        }

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
        payload = await self._gateway_client.create_session(**self._create_session_payload(request))
        return MainAgentSessionDetail.model_validate(payload)

    def create_session_sync(self, request: MainAgentSessionCreateRequest) -> MainAgentSessionDetail:
        payload = self._gateway_client.create_session_sync(**self._create_session_payload(request))
        return MainAgentSessionDetail.model_validate(payload)

    async def create_derived_session(
        self,
        parent_session_id: str,
        request: MainAgentSessionForkRequest,
    ) -> MainAgentSessionDetail:
        binding = SessionSurfaceBinding.from_request(request, default_surface="tui")
        payload = await self._gateway_client.create_derived_session(
            parent_session_id,
            title=request.title,
            **binding.as_kwargs(),
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
        binding = SessionSurfaceBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        payload = await self._gateway_client.cancel_session(
            session_id,
            reason=reason,
            **binding.as_kwargs(),
        )
        return MainAgentSessionMutationResponse.model_validate(payload)

    async def control_session(
        self,
        session_id: str,
        request: MainAgentSessionControlRequest,
    ) -> MainAgentSessionControlResponse:
        binding = SessionSurfaceBinding.from_request(request)
        payload = await self._gateway_client.control_session(
            session_id,
            action=request.action,
            reason=request.reason,
            **binding.as_kwargs(),
        )
        return MainAgentSessionControlResponse.model_validate(payload)

    async def update_session_context(
        self,
        session_id: str,
        request: MainAgentSessionContextRequest,
    ) -> MainAgentSessionContextResponse:
        binding = SessionSurfaceBinding.from_request(request)
        payload = await self._gateway_client.update_session_context(
            session_id,
            action=request.action,
            sources=request.sources,
            max_items=request.max_items,
            max_total_chars=request.max_total_chars,
            max_items_per_source=request.max_items_per_source,
            **binding.as_kwargs(),
        )
        return MainAgentSessionContextResponse.model_validate(payload)

    async def manage_session_memory(
        self,
        session_id: str,
        request: MainAgentSessionMemoryRequest,
    ) -> MainAgentSessionMemoryResponse:
        binding = SessionSurfaceBinding.from_request(request)
        payload = await self._gateway_client.manage_session_memory(
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
        return MainAgentSessionMemoryResponse.model_validate(payload)

    async def manage_session_skill(
        self,
        session_id: str,
        request: MainAgentSessionSkillRequest,
    ) -> MainAgentSessionSkillResponse:
        binding = SessionSurfaceBinding.from_request(request)
        payload = await self._gateway_client.manage_session_skill(
            session_id,
            action=request.action,
            skill_name=request.skill_name,
            path=request.path,
            query=request.query,
            mode=request.mode,
            **binding.as_kwargs(),
        )
        return MainAgentSessionSkillResponse.model_validate(payload)

    async def update_session_model(
        self,
        session_id: str,
        request: MainAgentSessionModelSelectionRequest,
    ) -> MainAgentSessionModelSelectionResponse:
        binding = SessionSurfaceBinding.from_request(request)
        payload = await self._gateway_client.update_session_model(
            session_id,
            provider_source=request.provider_source,
            provider_id=request.provider_id,
            model_id=request.model_id,
            **binding.as_kwargs(),
        )
        return MainAgentSessionModelSelectionResponse.model_validate(payload)

    async def update_session_runtime_policy(
        self,
        session_id: str,
        request: MainAgentSessionRuntimePolicyRequest,
    ) -> MainAgentSessionRuntimePolicyResponse:
        binding = SessionSurfaceBinding.from_request(request)
        payload = await self._gateway_client.update_session_runtime_policy(
            session_id,
            approval_profile=request.approval_profile,
            access_level=request.access_level,
            **binding.as_kwargs(),
        )
        return MainAgentSessionRuntimePolicyResponse.model_validate(payload)

    async def respond_to_approval(
        self,
        session_id: str,
        request: MainAgentSessionApprovalRequest,
    ) -> MainAgentSessionApprovalResponse:
        binding = SessionSurfaceBinding.from_request(request)
        payload = await self._gateway_client.respond_to_approval(
            session_id,
            approved=request.approved,
            token=request.token,
            **binding.as_kwargs(),
        )
        return MainAgentSessionApprovalResponse.model_validate(payload)


__all__ = ["RemoteSessionService"]
