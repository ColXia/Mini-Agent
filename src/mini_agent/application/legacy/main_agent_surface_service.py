"""Legacy/transitional cross-surface facade kept for compatibility during V11.1 migration."""

from __future__ import annotations

from typing import AsyncIterator

from mini_agent.application.support import (
    ApplicationInteractionBinding,
    FormatBootstrapErrorFn,
    ResolveWorkspaceDirFn,
    SseEventFn,
    ToUtcIsoFn,
)
from mini_agent.application.use_cases.agent_interaction_application_service import AgentInteractionApplicationService
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.application.use_cases.session_task_service import SessionTaskService
from mini_agent.application.user_services.agent_user_service import AgentUserService
from mini_agent.application.user_services.model_user_service import ModelUserService
from mini_agent.application.user_services.workspace_user_service import WorkspaceUserService
from mini_agent.interfaces import (
    MainAgentChatRequest,
    MainAgentChatResponse,
    MainAgentModelBindingDiagnostics,
    MainAgentModelBindingRequest,
    MainAgentModelBindingSummary,
    MainAgentModelCandidateListResponse,
    MainAgentModelCapabilities,
    MainAgentRoutingDiagnostics,
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
    MainAgentWorkspaceRuntimeSummary,
    MainAgentWorkspaceSummary,
    MainAgentWorkspaceSwitchRequest,
    MainAgentDefaultSessionRequest,
)

from mini_agent.application.facades.service_response_dto_adapter import (
    model_binding_diagnostics_response,
    model_binding_summary_response,
    model_candidate_list_response,
    model_capabilities_response,
    workspace_runtime_summary_response,
    workspace_summary_response,
)


class MainAgentSurfaceService:
    """Compatibility-only facade over explicit session/agent/model owners."""

    def __init__(
        self,
        *,
        session_task_service: SessionTaskService | None = None,
        run_control_service: RunControlApplicationService | None = None,
        agent_service: AgentUserService | None = None,
        model_service: ModelUserService | None = None,
        workspace_service: WorkspaceUserService | None = None,
        interaction_service: AgentInteractionApplicationService | None = None,
        resolve_workspace_dir: ResolveWorkspaceDirFn,
        to_utc_iso: ToUtcIsoFn,
        sse_event: SseEventFn,
        format_bootstrap_error: FormatBootstrapErrorFn,
        stream_chunk_size: int,
    ) -> None:
        self._session_task_service = session_task_service
        self._run_control_service = run_control_service
        self._agent_service = agent_service
        self._model_service = model_service
        self._workspace_service = workspace_service
        self._resolve_workspace_dir = resolve_workspace_dir
        if interaction_service is None:
            if self._session_task_service is None:
                raise RuntimeError(
                    "Session task service is required when interaction_service is not configured."
                )
            self._interaction_service = AgentInteractionApplicationService(
                session_task_service=self._session_task_service,
                resolve_workspace_dir=resolve_workspace_dir,
                to_utc_iso=to_utc_iso,
                sse_event=sse_event,
                format_bootstrap_error=format_bootstrap_error,
                stream_chunk_size=stream_chunk_size,
            )
        else:
            self._interaction_service = interaction_service
        self._chat_flow = self._interaction_service.chat_flow
        self._route_execution = self._interaction_service.route_execution

    def _require_session_task_service(self) -> SessionTaskService:
        if self._session_task_service is None:
            raise RuntimeError("Session task service is not configured.")
        return self._session_task_service

    def _require_run_control_service(self):
        if self._run_control_service is None:
            raise RuntimeError("Run control service is not configured.")
        return self._run_control_service

    def _require_agent_service(self) -> AgentUserService:
        if self._agent_service is None:
            raise RuntimeError("Agent service is not configured.")
        return self._agent_service

    def _require_model_service(self) -> ModelUserService:
        if self._model_service is None:
            raise RuntimeError("Model service is not configured.")
        return self._model_service

    def _session_task_method(self, name: str):
        if self._session_task_service is None:
            return None
        supports_entrypoint = getattr(self._session_task_service, "supports_entrypoint", None)
        if callable(supports_entrypoint) and not supports_entrypoint(name):
            return None
        method = getattr(self._session_task_service, name, None)
        return method if callable(method) else None

    def _require_workspace_service(self) -> WorkspaceUserService:
        if self._workspace_service is None:
            raise RuntimeError("Workspace service is not configured.")
        return self._workspace_service

    async def list_model_candidates(self) -> MainAgentModelCandidateListResponse:
        payload = await self._require_model_service().list_model_candidates()
        return model_candidate_list_response(payload)

    async def get_current_model_binding(self, agent_id: str | None = None) -> MainAgentModelBindingSummary:
        payload = await self._require_model_service().get_current_model_binding(agent_id)
        return model_binding_summary_response(payload)

    async def set_agent_model_binding(
        self,
        request: MainAgentModelBindingRequest,
    ) -> MainAgentModelBindingSummary:
        payload = await self._require_model_service().set_agent_model_binding(
            agent_id=request.agent_id,
            provider_source=request.provider_source,
            provider_id=request.provider_id,
            model_id=request.model_id,
        )
        return model_binding_summary_response(payload)

    async def get_current_model_capabilities(self, agent_id: str | None = None) -> MainAgentModelCapabilities:
        payload = await self._require_model_service().get_current_model_capabilities(agent_id)
        return model_capabilities_response(payload)

    async def get_model_binding_diagnostics(self, agent_id: str | None = None) -> MainAgentModelBindingDiagnostics:
        payload = await self._require_model_service().get_model_binding_diagnostics(agent_id)
        return model_binding_diagnostics_response(payload)

    async def run_chat(self, request: MainAgentChatRequest) -> MainAgentChatResponse:
        return await self._interaction_service.submit_message(request)

    async def get_routing_diagnostics(self) -> MainAgentRoutingDiagnostics:
        return await self._interaction_service.get_routing_diagnostics()

    async def list_workspaces(self) -> list[MainAgentWorkspaceSummary]:
        payload = await self._require_workspace_service().list_workspaces()
        return [workspace_summary_response(item) for item in list(payload or [])]

    async def get_workspace(self, workspace_id: str) -> MainAgentWorkspaceSummary:
        payload = await self._require_workspace_service().get_workspace(workspace_id)
        return workspace_summary_response(payload)

    async def get_active_workspace(self) -> MainAgentWorkspaceSummary:
        payload = await self._require_workspace_service().get_active_workspace()
        return workspace_summary_response(payload)

    async def switch_workspace(
        self,
        request: MainAgentWorkspaceSwitchRequest,
    ) -> MainAgentWorkspaceSummary:
        payload = await self._require_workspace_service().switch_workspace(request.workspace_id)
        return workspace_summary_response(payload)

    async def get_workspace_runtime_summary(
        self,
        *,
        workspace_id: str | None = None,
    ) -> MainAgentWorkspaceRuntimeSummary:
        payload = await self._require_workspace_service().get_workspace_runtime_summary(workspace_id)
        return workspace_runtime_summary_response(payload)

    async def list_sessions(
        self,
        *,
        workspace_dir: str | None = None,
        shared_only: bool = False,
    ) -> list[MainAgentSessionSummary]:
        resolved_workspace = self._resolve_workspace_dir(workspace_dir) if workspace_dir else None
        return await self._require_session_task_service().list_sessions(
            workspace_dir=resolved_workspace,
            shared_only=shared_only,
        )

    async def create_session(self, request: MainAgentSessionCreateRequest) -> MainAgentSessionDetail:
        resolved_workspace = self._resolve_workspace_dir(request.workspace_dir)
        session_task_service = self._require_session_task_service()
        session_task_service.validate_workspace(resolved_workspace)
        return await session_task_service.create_session(request, workspace_dir=resolved_workspace)

    async def ensure_default_session(self, request: MainAgentDefaultSessionRequest) -> MainAgentSessionDetail:
        resolved_workspace = self._resolve_workspace_dir(request.workspace_dir)
        session_task_service = self._require_session_task_service()
        session_task_service.validate_workspace(resolved_workspace)
        return await session_task_service.ensure_default_session(request, workspace_dir=resolved_workspace)

    async def create_derived_session(
        self,
        parent_session_id: str,
        request: MainAgentSessionForkRequest,
    ) -> MainAgentSessionDetail:
        return await self._require_session_task_service().create_derived_session(parent_session_id, request)

    async def get_session_detail(self, session_id: str, *, recent_limit: int = 50) -> MainAgentSessionDetail:
        return await self._require_session_task_service().get_session_detail(session_id, recent_limit=recent_limit)

    async def get_session_messages(self, session_id: str, *, limit: int = 10) -> list[MainAgentSessionMessage]:
        return await self._require_session_task_service().get_session_messages(session_id, limit=limit)

    async def delete_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        return await self._require_session_task_service().delete_session(session_id)

    async def rename_session(
        self,
        session_id: str,
        request: MainAgentSessionRenameRequest,
    ) -> MainAgentSessionMutationResponse:
        return await self._require_session_task_service().rename_session(session_id, request)

    async def set_session_shared(
        self,
        session_id: str,
        request: MainAgentSessionShareRequest,
    ) -> MainAgentSessionMutationResponse:
        return await self._require_session_task_service().set_session_shared(session_id, request)

    async def reset_session(self, session_id: str) -> MainAgentSessionMutationResponse:
        return await self._require_session_task_service().reset_session(session_id)

    async def cancel_session(
        self,
        session_id: str,
        request: MainAgentSessionCancelRequest,
    ) -> MainAgentSessionMutationResponse:
        binding = ApplicationInteractionBinding.from_request(request)
        return await self._require_run_control_service().cancel_session_run(
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
        session_control = self._session_task_method("control_session")
        if session_control is not None:
            return await session_control(
                session_id,
                action=request.action,
                reason=request.reason,
                **binding.as_kwargs(),
            )
        return await self._require_agent_service().control_session(
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
        session_context = self._session_task_method("update_session_context")
        if session_context is not None:
            return await session_context(
                session_id,
                action=request.action,
                sources=request.sources,
                max_items=request.max_items,
                max_total_chars=request.max_total_chars,
                max_items_per_source=request.max_items_per_source,
                **binding.as_kwargs(),
            )
        return await self._require_agent_service().update_session_context(
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
        session_memory = self._session_task_method("manage_session_memory")
        if session_memory is not None:
            return await session_memory(
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
        return await self._require_agent_service().manage_session_memory(
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
        session_skills = self._session_task_method("manage_session_skills")
        if session_skills is not None:
            return await session_skills(
                session_id,
                action=request.action,
                skill_name=request.skill_name,
                path=request.path,
                query=request.query,
                mode=request.mode,
                **binding.as_kwargs(),
            )
        return await self._require_agent_service().manage_session_skills(
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
        session_model = self._session_task_method("update_session_model_selection")
        if session_model is not None:
            return await session_model(
                session_id,
                provider_source=request.provider_source,
                provider_id=request.provider_id,
                model_id=request.model_id,
                **binding.as_kwargs(),
            )
        return await self._require_model_service().update_session_model_selection(
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
            return await self._require_run_control_service().approve_session_wait(
                session_id,
                token=request.token,
                source=binding.surface,
                **binding.as_kwargs(),
            )
        return await self._require_run_control_service().deny_session_wait(
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
        session_policy = self._session_task_method("update_session_runtime_policy")
        if session_policy is not None:
            return await session_policy(
                session_id,
                approval_profile=request.approval_profile,
                access_level=request.access_level,
                **binding.as_kwargs(),
            )
        return await self._require_agent_service().update_session_runtime_policy(
            session_id,
            approval_profile=request.approval_profile,
            access_level=request.access_level,
            **binding.as_kwargs(),
        )

    async def stream_chat_events(
        self,
        *,
        message: str,
        session_id: str | None = None,
        session_title_hint: str | None = None,
        workspace_dir: str | None = None,
        dry_run: bool = False,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> AsyncIterator[str]:
        async for item in self._interaction_service.stream_message(
            message=message,
            session_id=session_id,
            session_title_hint=session_title_hint,
            workspace_dir=workspace_dir,
            dry_run=dry_run,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        ):
            yield item


MainAgentSurfaceService.__module__ = "mini_agent.application.main_agent_surface_service"

__all__ = ["MainAgentSurfaceService"]
