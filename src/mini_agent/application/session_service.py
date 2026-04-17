"""Shared session application service for gateway/terminal surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_agent.agent_core.engine import Agent
from mini_agent.application.user_services.agent_user_service import AgentUserService
from mini_agent.application.interaction_request_adapter import ApplicationInteractionBinding
from mini_agent.application.managed_session_turn import ManagedSessionTurn
from mini_agent.application.ports.session_agent_runtime_port import SessionAgentRuntimePort
from mini_agent.application.ports.session_model_selection_runtime_port import SessionModelSelectionRuntimePort
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.application.use_cases.session_task_service import SessionTaskService
from mini_agent.application.user_services.model_user_service import ModelUserService
from mini_agent.interfaces import (
    MainAgentSessionApprovalRequest,
    MainAgentSessionApprovalResponse,
    MainAgentSessionCancelRequest,
    MainAgentSessionContextRequest,
    MainAgentSessionContextResponse,
    MainAgentSessionControlRequest,
    MainAgentSessionControlResponse,
    MainAgentSessionCreateRequest,
    MainAgentDefaultSessionRequest,
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
from mini_agent.application.session_runtime_port import SessionRuntimePort


class _UnavailableRunRuntimeAdapter:
    """Compatibility placeholder until a real run-runtime port is wired."""

    @staticmethod
    def _unsupported(run_id: str) -> LookupError:
        return LookupError(f"Run-level control is not wired for run {run_id!r}.")

    async def get_run(self, run_id: str) -> Any:
        raise self._unsupported(run_id)

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        _ = (reason, source)
        raise self._unsupported(run_id)

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        _ = (resume_token, source)
        raise self._unsupported(run_id)

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        _ = (reason, source)
        raise self._unsupported(run_id)

    async def resolve_approval_wait(
        self,
        run_id: str,
        *,
        approved: bool,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        _ = (approved, token, source, reason)
        raise self._unsupported(run_id)


class _SessionTaskCompatibilityAdapter:
    """Bridge session-era runtime operations into the run-control use case."""

    def __init__(self, runtime_manager: SessionRuntimePort) -> None:
        self._runtime_manager = runtime_manager

    async def get_session_task(self, session_id: str) -> Any:
        return await self._runtime_manager.get_session_detail(session_id, recent_limit=1)

    async def resolve_run_id_for_session(self, session_id: str) -> str | None:
        _ = session_id
        return None

    async def cancel_session_turn(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any:
        return await self._runtime_manager.cancel_session_turn(
            session_id,
            reason=reason,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def resolve_pending_approval(
        self,
        session_id: str,
        *,
        approved: bool,
        token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionApprovalResponse:
        return await self._runtime_manager.resolve_pending_approval(
            session_id,
            approved=approved,
            token=token,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )


class _SessionModelSelectionCompatibilityAdapter:
    """Bridge session-era model selection operations into the model user service."""

    def __init__(self, runtime_manager: SessionRuntimePort) -> None:
        self._runtime_manager = runtime_manager

    async def update_session_model_selection(
        self,
        session_id: str,
        *,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionModelSelectionResponse:
        return await self._runtime_manager.update_session_model_selection(
            session_id,
            provider_source=provider_source,
            provider_id=provider_id,
            model_id=model_id,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )


class _SessionAgentCompatibilityAdapter:
    """Bridge session-era agent-facing actions into the agent user service."""

    def __init__(self, runtime_manager: SessionRuntimePort) -> None:
        self._runtime_manager = runtime_manager

    async def update_session_runtime_policy(
        self,
        session_id: str,
        *,
        approval_profile: str | None = None,
        access_level: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any:
        return await self._runtime_manager.update_session_runtime_policy(
            session_id,
            approval_profile=approval_profile,
            access_level=access_level,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def control_session_context(
        self,
        session_id: str,
        *,
        action: str,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionControlResponse:
        return await self._runtime_manager.control_session_context(
            session_id,
            action=action,
            reason=reason,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def update_session_context_policy(
        self,
        session_id: str,
        *,
        action: str,
        sources: list[str] | None = None,
        max_items: int | None = None,
        max_total_chars: int | None = None,
        max_items_per_source: int | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionContextResponse:
        return await self._runtime_manager.update_session_context_policy(
            session_id,
            action=action,
            sources=sources,
            max_items=max_items,
            max_total_chars=max_total_chars,
            max_items_per_source=max_items_per_source,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def manage_session_memory(
        self,
        session_id: str,
        *,
        action: str,
        engram_id: str | None = None,
        content: str | None = None,
        query: str | None = None,
        day: str | None = None,
        export_format: str | None = None,
        detail_mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionMemoryResponse:
        return await self._runtime_manager.manage_session_memory(
            session_id,
            action=action,
            engram_id=engram_id,
            content=content,
            query=query,
            day=day,
            export_format=export_format,
            detail_mode=detail_mode,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def manage_session_skills(
        self,
        session_id: str,
        *,
        action: str,
        skill_name: str | None = None,
        path: str | None = None,
        query: str | None = None,
        mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionSkillResponse:
        return await self._runtime_manager.manage_session_skills(
            session_id,
            action=action,
            skill_name=skill_name,
            path=path,
            query=query,
            mode=mode,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )


class SessionApplicationService:
    """Shared application-facing session operations and turn scoping."""

    def __init__(
        self,
        *,
        runtime_manager: SessionRuntimePort,
        run_control_service: RunControlApplicationService | None = None,
        agent_service: AgentUserService | None = None,
        model_service: ModelUserService | None = None,
        session_task_service: SessionTaskService | None = None,
    ) -> None:
        self._runtime_manager = runtime_manager
        self._session_task_service = session_task_service or SessionTaskService(runtime_manager=runtime_manager)
        session_agent_runtime: SessionAgentRuntimePort = _SessionAgentCompatibilityAdapter(runtime_manager)
        session_model_runtime: SessionModelSelectionRuntimePort = _SessionModelSelectionCompatibilityAdapter(
            runtime_manager
        )
        self._run_control_service = run_control_service or RunControlApplicationService(
            run_runtime=_UnavailableRunRuntimeAdapter(),
            session_tasks=_SessionTaskCompatibilityAdapter(runtime_manager),
        )
        self._agent_service = agent_service or AgentUserService(
            run_control=self._run_control_service,
            session_agent_runtime=session_agent_runtime,
        )
        self._model_service = model_service or ModelUserService(
            session_model_runtime=session_model_runtime,
        )

    def validate_workspace(self, workspace_dir: Path) -> None:
        self._session_task_service.validate_workspace(workspace_dir)

    @property
    def run_control_service(self) -> RunControlApplicationService:
        return self._run_control_service

    @property
    def agent_service(self) -> AgentUserService:
        return self._agent_service

    @property
    def model_service(self) -> ModelUserService:
        return self._model_service

    @property
    def session_task_service(self) -> SessionTaskService:
        return self._session_task_service

    async def list_sessions(
        self,
        *,
        workspace_dir: Path | None = None,
        shared_only: bool = False,
    ) -> list[MainAgentSessionSummary]:
        return await self._session_task_service.list_sessions(
            workspace_dir=workspace_dir,
            shared_only=shared_only,
        )

    async def create_session(
        self,
        request: MainAgentSessionCreateRequest,
        *,
        workspace_dir: Path,
    ) -> MainAgentSessionDetail:
        return await self._session_task_service.create_session(request, workspace_dir=workspace_dir)

    async def ensure_default_session(
        self,
        request: MainAgentDefaultSessionRequest,
        *,
        workspace_dir: Path,
    ) -> MainAgentSessionDetail:
        return await self._session_task_service.ensure_default_session(request, workspace_dir=workspace_dir)

    async def create_derived_session(
        self,
        parent_session_id: str,
        request: MainAgentSessionForkRequest,
    ) -> MainAgentSessionDetail:
        return await self._session_task_service.create_derived_session(parent_session_id, request)

    async def get_session_detail(self, session_id: str, *, recent_limit: int = 50) -> MainAgentSessionDetail:
        return await self._session_task_service.get_session_detail(session_id, recent_limit=recent_limit)

    async def get_session_messages(self, session_id: str, *, limit: int = 10) -> list[MainAgentSessionMessage]:
        return await self._session_task_service.get_session_messages(session_id, limit=limit)

    async def delete_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        return await self._session_task_service.delete_session(session_id)

    async def rename_session(
        self,
        session_id: str,
        request: MainAgentSessionRenameRequest,
    ) -> MainAgentSessionMutationResponse:
        return await self._session_task_service.rename_session(session_id, request)

    async def set_session_shared(
        self,
        session_id: str,
        request: MainAgentSessionShareRequest,
    ) -> MainAgentSessionMutationResponse:
        return await self._session_task_service.set_session_shared(session_id, request)

    async def reset_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        return await self._session_task_service.reset_session(session_id)

    async def cancel_session(
        self,
        session_id: str,
        request: MainAgentSessionCancelRequest,
    ) -> MainAgentSessionMutationResponse:
        binding = ApplicationInteractionBinding.from_request(request)
        return await self._run_control_service.cancel_session_run(
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
        return await self._agent_service.control_session(
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
        return await self._agent_service.update_session_context(
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
        return await self._agent_service.manage_session_memory(
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
        return await self._agent_service.manage_session_skills(
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
        return await self._model_service.update_session_model_selection(
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
            return await self._run_control_service.approve_session_wait(
                session_id,
                token=request.token,
                source=binding.surface,
                **binding.as_kwargs(),
            )
        return await self._run_control_service.deny_session_wait(
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
        return await self._agent_service.update_session_runtime_policy(
            session_id,
            approval_profile=request.approval_profile,
            access_level=request.access_level,
            **binding.as_kwargs(),
        )

    async def build_ephemeral_agent(self, workspace_dir: Path) -> Agent:
        return await self._session_task_service.build_ephemeral_agent(workspace_dir)

    async def prepare_derived_chat_turn(self, **kwargs: Any) -> ManagedSessionTurn:
        return await self._session_task_service.prepare_derived_chat_turn(**kwargs)

    async def prepare_chat_turn(self, **kwargs: Any) -> ManagedSessionTurn:
        return await self._session_task_service.prepare_chat_turn(**kwargs)


__all__ = [
    "SessionApplicationService",
]
