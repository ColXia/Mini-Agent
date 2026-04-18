"""Legacy/transitional session facade kept for compatibility during V11.1 migration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_agent.agent_core.engine import Agent
from mini_agent.application.ports.agent_runtime_port import AgentRuntimePort
from mini_agent.application.ports.model_runtime_port import ModelRuntimePort
from mini_agent.application.ports.run_runtime_port import RunRuntimePort
from mini_agent.application.ports.session_runtime_port import SessionRuntimePort
from mini_agent.application.ports.session_task_port import SessionTaskPort
from mini_agent.application.ports.session_task_runtime_port import SessionTaskRuntimePort
from mini_agent.application.ports.workspace_runtime_port import WorkspaceRuntimePort
from mini_agent.application.support import ApplicationInteractionBinding, ManagedSessionTurn
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.application.use_cases.session_task_service import SessionTaskService
from mini_agent.application.user_services.agent_user_service import AgentUserService
from mini_agent.application.user_services.command_user_service import CommandUserService
from mini_agent.application.user_services.model_user_service import ModelUserService
from mini_agent.application.user_services.workspace_user_service import WorkspaceUserService
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

from .session_agent_runtime_port import SessionAgentRuntimePort
from .session_model_selection_runtime_port import SessionModelSelectionRuntimePort


def _require_session_task_service(service: SessionTaskService | None) -> SessionTaskService:
    if service is None:
        raise RuntimeError("Session task service is not configured.")
    return service


def _require_run_control_service(service: RunControlApplicationService | None) -> RunControlApplicationService:
    if service is None:
        raise RuntimeError("Run control application service is not configured.")
    return service


def _resolve_run_control_entry_service(
    run_control_service: RunControlApplicationService | None,
    agent_service: AgentUserService | None,
):
    if run_control_service is not None:
        return run_control_service
    if agent_service is not None and all(
        hasattr(agent_service, attr)
        for attr in ("cancel_session_run", "approve_session_wait", "deny_session_wait")
    ):
        return agent_service
    return _require_run_control_service(run_control_service)


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

    @classmethod
    def from_services(
        cls,
        *,
        session_task_service: SessionTaskService | None = None,
        run_control_service: RunControlApplicationService | None = None,
        agent_service: AgentUserService | None = None,
        model_service: ModelUserService | None = None,
        runtime_manager: SessionRuntimePort | None = None,
    ) -> "SessionApplicationService":
        """Build the legacy facade from already-resolved explicit owners."""

        service = cls(
            session_task_service=session_task_service,
            run_control_service=run_control_service,
            agent_service=agent_service,
            model_service=model_service,
        )
        service._runtime_manager = runtime_manager or getattr(session_task_service, "_runtime_manager", None)
        return service

    @classmethod
    def from_runtime_compatibility(
        cls,
        *,
        runtime_manager: SessionRuntimePort,
        session_task_runtime: SessionTaskRuntimePort | None = None,
        session_task_port: SessionTaskPort | None = None,
        session_agent_runtime: SessionAgentRuntimePort | None = None,
        session_model_runtime: SessionModelSelectionRuntimePort | None = None,
        agent_runtime: AgentRuntimePort | None = None,
        run_runtime: RunRuntimePort | None = None,
        model_runtime: ModelRuntimePort | None = None,
        workspace_runtime: WorkspaceRuntimePort | None = None,
        command_runtime: object = None,
        run_control_service: RunControlApplicationService | None = None,
        agent_service: AgentUserService | None = None,
        workspace_service: WorkspaceUserService | None = None,
        model_service: ModelUserService | None = None,
        command_service: CommandUserService | None = None,
        session_task_service: SessionTaskService | None = None,
    ) -> "SessionApplicationService":
        """Build the legacy facade from runtime-backed compatibility seams."""

        from mini_agent.application.legacy.session_service_assembly import (
            assemble_runtime_backed_session_application,
        )

        assembly = assemble_runtime_backed_session_application(
            runtime_manager=runtime_manager,
            session_task_runtime=session_task_runtime,
            session_task_port=session_task_port,
            session_agent_runtime=session_agent_runtime,
            session_model_runtime=session_model_runtime,
            agent_runtime=agent_runtime,
            run_runtime=run_runtime,
            model_runtime=model_runtime,
            workspace_runtime=workspace_runtime,
            command_runtime=command_runtime,
            session_task_service=session_task_service,
            run_control_service=run_control_service,
            agent_service=agent_service,
            workspace_service=workspace_service,
            model_service=model_service,
            command_service=command_service,
        )
        return cls.from_services(
            session_task_service=assembly.session_task_service,
            run_control_service=assembly.run_control_service,
            agent_service=assembly.agent_service,
            model_service=assembly.model_service,
            runtime_manager=runtime_manager,
        )

    @classmethod
    def from_typed_compatibility(
        cls,
        *,
        session_task_runtime: SessionTaskRuntimePort | None = None,
        session_task_port: SessionTaskPort | None = None,
        session_agent_runtime: SessionAgentRuntimePort | None = None,
        session_model_runtime: SessionModelSelectionRuntimePort | None = None,
        agent_runtime: AgentRuntimePort | None = None,
        run_runtime: RunRuntimePort | None = None,
        model_runtime: ModelRuntimePort | None = None,
        workspace_runtime: WorkspaceRuntimePort | None = None,
        command_runtime: object = None,
        run_control_service: RunControlApplicationService | None = None,
        agent_service: AgentUserService | None = None,
        workspace_service: WorkspaceUserService | None = None,
        model_service: ModelUserService | None = None,
        command_service: CommandUserService | None = None,
        session_task_service: SessionTaskService | None = None,
    ) -> "SessionApplicationService":
        """Build the legacy facade from typed compatibility seams."""

        from mini_agent.application.legacy.session_service_assembly import (
            assemble_typed_session_application,
        )

        assembly = assemble_typed_session_application(
            session_task_runtime=session_task_runtime,
            session_task_port=session_task_port,
            session_agent_runtime=session_agent_runtime,
            session_model_runtime=session_model_runtime,
            agent_runtime=agent_runtime,
            run_runtime=run_runtime,
            model_runtime=model_runtime,
            workspace_runtime=workspace_runtime,
            command_runtime=command_runtime,
            session_task_service=session_task_service,
            run_control_service=run_control_service,
            agent_service=agent_service,
            workspace_service=workspace_service,
            model_service=model_service,
            command_service=command_service,
        )
        return cls.from_services(
            session_task_service=assembly.session_task_service,
            run_control_service=assembly.run_control_service,
            agent_service=assembly.agent_service,
            model_service=assembly.model_service,
        )

    def __init__(
        self,
        *,
        runtime_manager: SessionRuntimePort | None = None,
        session_task_runtime: SessionTaskRuntimePort | None = None,
        session_task_port: SessionTaskPort | None = None,
        session_agent_runtime: SessionAgentRuntimePort | None = None,
        session_model_runtime: SessionModelSelectionRuntimePort | None = None,
        agent_runtime: AgentRuntimePort | None = None,
        run_runtime: RunRuntimePort | None = None,
        model_runtime: ModelRuntimePort | None = None,
        run_control_service: RunControlApplicationService | None = None,
        agent_service: AgentUserService | None = None,
        model_service: ModelUserService | None = None,
        session_task_service: SessionTaskService | None = None,
    ) -> None:
        if any(
            value is not None
            for value in (
                runtime_manager,
                session_task_runtime,
                session_task_port,
                session_agent_runtime,
                session_model_runtime,
                agent_runtime,
                run_runtime,
                model_runtime,
            )
        ):
            compatibility_service = (
                type(self).from_runtime_compatibility(
                    runtime_manager=runtime_manager,
                    session_task_runtime=session_task_runtime,
                    session_task_port=session_task_port,
                    session_agent_runtime=session_agent_runtime,
                    session_model_runtime=session_model_runtime,
                    agent_runtime=agent_runtime,
                    run_runtime=run_runtime,
                    model_runtime=model_runtime,
                    session_task_service=session_task_service,
                    run_control_service=run_control_service,
                    agent_service=agent_service,
                    model_service=model_service,
                )
                if runtime_manager is not None
                else type(self).from_typed_compatibility(
                    session_task_runtime=session_task_runtime,
                    session_task_port=session_task_port,
                    session_agent_runtime=session_agent_runtime,
                    session_model_runtime=session_model_runtime,
                    agent_runtime=agent_runtime,
                    run_runtime=run_runtime,
                    model_runtime=model_runtime,
                    session_task_service=session_task_service,
                    run_control_service=run_control_service,
                    agent_service=agent_service,
                    model_service=model_service,
                )
            )
            self._session_task_service = compatibility_service._session_task_service
            self._run_control_service = compatibility_service._run_control_service
            self._agent_service = compatibility_service._agent_service
            self._model_service = compatibility_service._model_service
            self._runtime_manager = compatibility_service._runtime_manager
            return

        self._session_task_service = session_task_service
        self._run_control_service = run_control_service
        self._agent_service = agent_service
        self._model_service = model_service
        self._runtime_manager = runtime_manager or getattr(session_task_service, "_runtime_manager", None)

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

    @property
    def runtime_manager(self) -> SessionRuntimePort | None:
        return self._runtime_manager

    def _run_control_entry_service(self):
        return _resolve_run_control_entry_service(self._run_control_service, self._agent_service)

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
        return await self._run_control_entry_service().cancel_session_run(
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
            return await self._run_control_entry_service().approve_session_wait(
                session_id,
                token=request.token,
                source=binding.surface,
                **binding.as_kwargs(),
            )
        return await self._run_control_entry_service().deny_session_wait(
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
