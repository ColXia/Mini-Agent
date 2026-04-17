"""Legacy/transitional session facade kept for compatibility during V11.1 migration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_agent.agent_core.engine import Agent
from mini_agent.application.support import ApplicationInteractionBinding, ManagedSessionTurn
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.application.use_cases.session_task_service import SessionTaskService
from mini_agent.application.user_services.agent_user_service import AgentUserService
from mini_agent.application.user_services.model_user_service import ModelUserService
from mini_agent.interfaces import (
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


def _require_session_task_service(service: SessionTaskService | None) -> SessionTaskService:
    if service is None:
        raise RuntimeError("Session task service is not configured.")
    return service


def _require_run_control_service(service: RunControlApplicationService | None) -> RunControlApplicationService:
    if service is None:
        raise RuntimeError("Run control application service is not configured.")
    return service


def _require_agent_service(service: AgentUserService | None) -> AgentUserService:
    if service is None:
        raise RuntimeError("Agent user service is not configured.")
    return service


def _require_model_service(service: ModelUserService | None) -> ModelUserService:
    if service is None:
        raise RuntimeError("Model user service is not configured.")
    return service


class SessionApplicationService:
    """Legacy/transitional session-task carrier for compatibility-facing callers."""

    def __init__(
        self,
        *,
        run_control_service: RunControlApplicationService | None = None,
        agent_service: AgentUserService | None = None,
        model_service: ModelUserService | None = None,
        session_task_service: SessionTaskService | None = None,
    ) -> None:
        self._session_task_service = session_task_service
        self._run_control_service = run_control_service
        self._agent_service = agent_service
        self._model_service = model_service

    def validate_workspace(self, workspace_dir: Path) -> None:
        self.session_task_service.validate_workspace(workspace_dir)

    @property
    def run_control_service(self) -> RunControlApplicationService:
        return _require_run_control_service(self._run_control_service)

    @property
    def agent_service(self) -> AgentUserService:
        return _require_agent_service(self._agent_service)

    @property
    def model_service(self) -> ModelUserService:
        return _require_model_service(self._model_service)

    @property
    def session_task_service(self) -> SessionTaskService:
        return _require_session_task_service(self._session_task_service)

    async def list_sessions(
        self,
        *,
        workspace_dir: Path | None = None,
        shared_only: bool = False,
    ) -> list[MainAgentSessionSummary]:
        return await self.session_task_service.list_sessions(
            workspace_dir=workspace_dir,
            shared_only=shared_only,
        )

    async def create_session(
        self,
        request: MainAgentSessionCreateRequest,
        *,
        workspace_dir: Path,
    ) -> MainAgentSessionDetail:
        return await self.session_task_service.create_session(request, workspace_dir=workspace_dir)

    async def ensure_default_session(
        self,
        request: MainAgentDefaultSessionRequest,
        *,
        workspace_dir: Path,
    ) -> MainAgentSessionDetail:
        return await self.session_task_service.ensure_default_session(request, workspace_dir=workspace_dir)

    async def create_derived_session(
        self,
        parent_session_id: str,
        request: MainAgentSessionForkRequest,
    ) -> MainAgentSessionDetail:
        return await self.session_task_service.create_derived_session(parent_session_id, request)

    async def get_session_detail(self, session_id: str, *, recent_limit: int = 50) -> MainAgentSessionDetail:
        return await self.session_task_service.get_session_detail(session_id, recent_limit=recent_limit)

    async def get_session_messages(self, session_id: str, *, limit: int = 10) -> list[MainAgentSessionMessage]:
        return await self.session_task_service.get_session_messages(session_id, limit=limit)

    async def delete_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        return await self.session_task_service.delete_session(session_id)

    async def rename_session(
        self,
        session_id: str,
        request: MainAgentSessionRenameRequest,
    ) -> MainAgentSessionMutationResponse:
        return await self.session_task_service.rename_session(session_id, request)

    async def set_session_shared(
        self,
        session_id: str,
        request: MainAgentSessionShareRequest,
    ) -> MainAgentSessionMutationResponse:
        return await self.session_task_service.set_session_shared(session_id, request)

    async def reset_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        return await self.session_task_service.reset_session(session_id)

    async def cancel_session(
        self,
        session_id: str,
        request: MainAgentSessionCancelRequest,
    ) -> MainAgentSessionMutationResponse:
        binding = ApplicationInteractionBinding.from_request(request)
        return await self.run_control_service.cancel_session_run(
            session_id,
            reason=request.reason,
            source=binding.surface,
            **binding.as_kwargs(),
        )

    async def control_session(
        self,
        session_id: str,
        request: MainAgentSessionControlRequest,
    ) -> MainAgentSessionControlResponse:
        binding = ApplicationInteractionBinding.from_request(request)
        return await self.agent_service.control_session(
            session_id,
            action=request.action,
            reason=request.reason,
            **binding.as_kwargs(),
        )

    async def update_session_context(
        self,
        session_id: str,
        request: MainAgentSessionContextRequest,
    ) -> MainAgentSessionContextResponse:
        binding = ApplicationInteractionBinding.from_request(request)
        return await self.agent_service.update_session_context(
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
        binding = ApplicationInteractionBinding.from_request(request)
        return await self.agent_service.manage_session_memory(
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
        binding = ApplicationInteractionBinding.from_request(request)
        return await self.agent_service.manage_session_skills(
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
        binding = ApplicationInteractionBinding.from_request(request)
        return await self.model_service.update_session_model_selection(
            session_id,
            provider_source=request.provider_source,
            provider_id=request.provider_id,
            model_id=request.model_id,
            **binding.as_kwargs(),
        )

    async def respond_to_approval(
        self,
        session_id: str,
        request: MainAgentSessionApprovalRequest,
    ) -> MainAgentSessionApprovalResponse:
        binding = ApplicationInteractionBinding.from_request(request)
        if request.approved:
            return await self.run_control_service.approve_session_wait(
                session_id,
                token=request.token,
                source=binding.surface,
                **binding.as_kwargs(),
            )
        return await self.run_control_service.deny_session_wait(
            session_id,
            token=request.token,
            source=binding.surface,
            **binding.as_kwargs(),
        )

    async def update_session_runtime_policy(
        self,
        session_id: str,
        request: MainAgentSessionRuntimePolicyRequest,
    ) -> MainAgentSessionRuntimePolicyResponse:
        binding = ApplicationInteractionBinding.from_request(request)
        return await self.agent_service.update_session_runtime_policy(
            session_id,
            approval_profile=request.approval_profile,
            access_level=request.access_level,
            **binding.as_kwargs(),
        )

    async def build_ephemeral_agent(self, workspace_dir: Path) -> Agent:
        return await self.session_task_service.build_ephemeral_agent(workspace_dir)

    async def prepare_derived_chat_turn(self, **kwargs: Any) -> ManagedSessionTurn:
        return await self.session_task_service.prepare_derived_chat_turn(**kwargs)

    async def prepare_chat_turn(self, **kwargs: Any) -> ManagedSessionTurn:
        return await self.session_task_service.prepare_chat_turn(**kwargs)


__all__ = ["SessionApplicationService"]
