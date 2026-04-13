"""Session operator-command orchestration extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Sequence

from fastapi import HTTPException

from mini_agent.interfaces import (
    MainAgentSessionApprovalResponse,
    MainAgentSessionContextResponse,
    MainAgentSessionControlResponse,
    MainAgentSessionMemoryResponse,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionMutationResponse,
    MainAgentSessionRuntimePolicyResponse,
    MainAgentSessionSkillResponse,
)
from mini_agent.runtime.session_command_coordinator import (
    RuntimeSessionCommandCoordinator,
    RuntimeSessionCommandTranscript,
)
from mini_agent.runtime.session_context_policy_handler import (
    RuntimeSessionContextPolicyCommand,
    RuntimeSessionContextPolicyHandler,
)
from mini_agent.runtime.session_control_handler import (
    RuntimeSessionControlCommand,
    RuntimeSessionControlHandler,
)
from mini_agent.runtime.session_memory_command_handler import (
    RuntimeSessionMemoryCommand,
    RuntimeSessionMemoryCommandExecution,
    RuntimeSessionMemoryCommandHandler,
)
from mini_agent.runtime.session_model_selection_handler import (
    RuntimeSessionModelSelectionHandler,
    RuntimeSessionModelSelectionPlan,
)
from mini_agent.runtime.session_runtime_policy_handler import (
    RuntimeSessionRuntimePolicyHandler,
    RuntimeSessionRuntimePolicyPlan,
)
from mini_agent.runtime.session_skill_command_handler import (
    RuntimeSessionSkillCommand,
    RuntimeSessionSkillCommandHandler,
)
from mini_agent.runtime.session_interrupt_handler import RuntimeSessionInterruptHandler

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState
    from mini_agent.runtime.session_agent_runtime_handler import RuntimeSessionAgentRuntimeHandler
    from mini_agent.runtime.session_live_state_handler import RuntimeSessionLiveStateHandler


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True, slots=True)
class RuntimeSessionRuntimePolicyExecution:
    plan: RuntimeSessionRuntimePolicyPlan
    diagnostics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RuntimeSessionSkillMutationExecution:
    status: str
    result: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RuntimeSessionModelSelectionExecution:
    plan: RuntimeSessionModelSelectionPlan


@dataclass(slots=True)
class RuntimeSessionOperatorHandler:
    normalize_surface: Callable[[str | None], str]
    session_commands: RuntimeSessionCommandCoordinator
    session_control: RuntimeSessionControlHandler
    session_context_policy: RuntimeSessionContextPolicyHandler
    session_memory_commands: RuntimeSessionMemoryCommandHandler
    session_skill_commands: RuntimeSessionSkillCommandHandler
    session_model_selection: RuntimeSessionModelSelectionHandler
    session_runtime_policy: RuntimeSessionRuntimePolicyHandler
    session_interrupt: RuntimeSessionInterruptHandler
    session_agent_runtime: "RuntimeSessionAgentRuntimeHandler"
    session_live_state: "RuntimeSessionLiveStateHandler"
    selected_model_identity: Callable[["MainAgentSessionState"], tuple[str, str, str] | None]
    pending_model_identity: Callable[["MainAgentSessionState"], tuple[str, str, str] | None]
    set_pending_model_identity: Callable[["MainAgentSessionState", tuple[str, str, str] | None], None]
    persist_session: Callable[["MainAgentSessionState"], None]
    queue_workspace_skill_reload: Callable[..., Awaitable[tuple[str, ...]]]
    cleanup_mcp_connections: Callable[[], Awaitable[None]]

    async def control_session(
        self,
        session: "MainAgentSessionState",
        *,
        action: str,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionControlResponse:
        command = RuntimeSessionControlCommand(
            action=action,
            reason=_safe_text(reason) or None,
        )
        normalized_action = self.session_control.validate_action(command.action)
        execution = await self.session_commands.execute_locked(
            session,
            operation=lambda: self.session_control.execute(
                session,
                command,
                cleanup_mcp_connections=self.cleanup_mcp_connections,
                rebuild_session_agent=lambda: self.session_agent_runtime.rebuild_agent_with_identity(
                    session,
                    self.selected_model_identity(session),
                ),
            ),
            transcript_builder=lambda execution: RuntimeSessionCommandTranscript(
                command=self._session_control_command_name(normalized_action),
                summary=execution.transcript_summary,
                content=execution.transcript_details,
                threads_visible=False if normalized_action.startswith("mcp_") else None,
            ),
            surface=self._active_surface(session, surface),
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return execution.response

    def cancel_turn(
        self,
        *,
        session_id: str,
        active_session: "MainAgentSessionState | None",
        persisted_exists: bool,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionMutationResponse:
        session = active_session
        if session is None:
            if not persisted_exists:
                raise HTTPException(status_code=404, detail="Session not found.")
            raise HTTPException(status_code=409, detail="Session has no running turn to cancel.")

        execution = self.session_interrupt.execute_cancel(
            session,
            reason=reason,
        )
        self.session_commands.record(
            session,
            transcript=RuntimeSessionCommandTranscript(
                command="cancel",
                summary=execution.transcript_summary,
                content=execution.transcript_details,
            ),
            surface=surface or execution.response.active_surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return execution.response

    def resolve_pending_approval(
        self,
        *,
        session_id: str,
        active_session: "MainAgentSessionState | None",
        persisted_exists: bool,
        approved: bool,
        token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionApprovalResponse:
        session = active_session
        if session is None:
            if not persisted_exists:
                raise HTTPException(status_code=404, detail="Session not found.")
            raise HTTPException(
                status_code=409,
                detail=self.session_interrupt.restart_pending_approval_detail(),
            )

        execution = self.session_interrupt.execute_approval(
            session,
            approved=approved,
            token=token,
        )
        self.session_commands.record(
            session,
            transcript=RuntimeSessionCommandTranscript(
                command=execution.transcript_command,
                summary=execution.transcript_summary,
                content=execution.transcript_details,
                metadata={
                    "token": execution.token,
                    "tool_name": execution.tool_name,
                },
            ),
            surface=self._active_surface(session, surface),
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        execution.finalize()
        return execution.response

    async def update_context_policy(
        self,
        session: "MainAgentSessionState",
        *,
        action: str,
        sources: Sequence[str] | None = None,
        max_items: int | None = None,
        max_total_chars: int | None = None,
        max_items_per_source: int | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionContextResponse:
        command = RuntimeSessionContextPolicyCommand(
            action=action,
            sources=tuple(sources or ()),
            max_items=max_items,
            max_total_chars=max_total_chars,
            max_items_per_source=max_items_per_source,
        )
        execution = await self.session_commands.execute_locked(
            session,
            operation=lambda: self.session_context_policy.execute(session, command),
            transcript_builder=lambda execution: RuntimeSessionCommandTranscript(
                command=execution.transcript_command,
                summary=execution.transcript_summary,
                content=execution.transcript_details,
                threads_visible=False,
            ),
            surface=self._active_surface(session, surface),
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return execution.response

    async def manage_memory(
        self,
        session: "MainAgentSessionState",
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
        normalized_detail_mode = _safe_text(detail_mode).lower() or "full"
        if normalized_detail_mode not in {"brief", "full"}:
            raise HTTPException(status_code=400, detail="detail_mode must be brief or full.")
        command = RuntimeSessionMemoryCommand(
            action=_safe_text(action).lower().replace("-", "_"),
            engram_id=_safe_text(engram_id) or None,
            content=_safe_text(content) or None,
            query=_safe_text(query) or None,
            day=_safe_text(day) or None,
            export_format=_safe_text(export_format).lower() or None,
            detail_mode=normalized_detail_mode,
        )
        self.session_memory_commands.validate_action(command.action)

        if not self.session_memory_commands.is_mutating_action(command.action):
            execution = self.session_memory_commands.execute(session, command)
            self.persist_session(session)
            return self._build_session_memory_response(
                session=session,
                action=command.action,
                execution=execution,
            )

        execution = await self.session_commands.execute_locked(
            session,
            operation=lambda: self._execute_mutating_memory_command(session, command),
            transcript_builder=lambda execution: RuntimeSessionCommandTranscript(
                command=f"memory {command.action}",
                summary=str(execution.result.get("summary") or "memory command"),
                content=str(execution.result.get("details") or ""),
                threads_visible=False,
                metadata=(
                    {"engram_id": str(execution.result.get("engram_id") or command.engram_id)}
                    if (execution.result.get("engram_id") or command.engram_id)
                    else None
                ),
            ),
            surface=self._active_surface(session, surface),
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return self._build_session_memory_response(
            session=session,
            action=command.action,
            execution=execution,
        )

    async def manage_skills(
        self,
        session: "MainAgentSessionState",
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
        command = RuntimeSessionSkillCommand(
            action=_safe_text(action).lower().replace("-", "_"),
            skill_name=_safe_text(skill_name) or None,
            path=_safe_text(path) or None,
            query=_safe_text(query) or None,
            mode=_safe_text(mode) or None,
        )
        self.session_skill_commands.validate_action(command.action)
        prepared = self.session_skill_commands.prepare(session, command)
        if prepared.mutation is None:
            return self._build_session_skill_response(
                session=session,
                action=command.action,
                status=prepared.status,
                result=prepared.result or {},
            )

        mutation = prepared.mutation
        if session.projection.busy:
            queued_ids = await self.queue_workspace_skill_reload(
                session.workspace_dir,
                current_session_id=session.session_id,
                reason=mutation.reload_reason,
                include_current=True,
            )
            return self._build_session_skill_response(
                session=session,
                action=command.action,
                status="busy",
                result=self.session_skill_commands.build_busy_result(
                    session,
                    mutation,
                    queued_ids=queued_ids,
                    include_current_note=True,
                ),
            )

        queued_other_ids = await self.queue_workspace_skill_reload(
            session.workspace_dir,
            current_session_id=session.session_id,
            reason=mutation.reload_reason,
            include_current=False,
        )

        execution = await self.session_commands.execute_locked(
            session,
            operation=lambda: self._execute_skill_mutation(
                session,
                mutation=mutation,
                queued_other_ids=queued_other_ids,
            ),
            transcript_builder=lambda execution: (
                RuntimeSessionCommandTranscript(
                    command=mutation.command_name,
                    summary=str(execution.result.get("summary") or "skill command completed"),
                    content=str(execution.result.get("details") or ""),
                    threads_visible=False,
                )
                if execution.status == "ok"
                else None
            ),
            surface=self._active_surface(session, surface),
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            touch=lambda execution: execution.status == "ok",
            persist=lambda execution: execution.status == "ok",
        )
        return self._build_session_skill_response(
            session=session,
            action=command.action,
            status=execution.status,
            result=execution.result,
        )

    async def update_model_selection(
        self,
        session: "MainAgentSessionState",
        *,
        provider_source: str | None,
        provider_id: str,
        model_id: str,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionModelSelectionResponse:
        request = self.session_model_selection.resolve_request(
            provider_source=provider_source,
            provider_id=provider_id,
            model_id=model_id,
        )
        execution = await self.session_commands.execute_locked(
            session,
            operation=lambda: self._execute_model_selection_update(
                session,
                request=request,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            ),
            touch=lambda execution: execution.plan.touch_and_persist,
            persist=lambda execution: execution.plan.touch_and_persist,
        )
        return self._build_session_model_selection_response(
            session=session,
            status=execution.plan.status,
            applied=execution.plan.applied,
            queued=execution.plan.queued,
            surface=surface,
        )

    async def update_runtime_policy(
        self,
        session: "MainAgentSessionState",
        *,
        approval_profile: str | None = None,
        access_level: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionRuntimePolicyResponse:
        execution = await self.session_commands.execute_locked(
            session,
            operation=lambda: self._execute_runtime_policy_update(
                session,
                approval_profile=approval_profile,
                access_level=access_level,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            ),
            transcript_builder=lambda execution: RuntimeSessionCommandTranscript(
                command="policy",
                summary=self.session_runtime_policy.transcript_summary(execution.plan),
                content=self.session_runtime_policy.transcript_content(execution.plan),
            ),
            surface=self._active_surface(session, surface),
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return self._build_session_runtime_policy_response(
            session=session,
            plan=execution.plan,
            diagnostics=execution.diagnostics,
        )

    def _build_session_memory_response(
        self,
        *,
        session: "MainAgentSessionState",
        action: str,
        execution: RuntimeSessionMemoryCommandExecution,
    ) -> MainAgentSessionMemoryResponse:
        return MainAgentSessionMemoryResponse(
            status="ok",
            session_id=session.session_id,
            action=action,
            active_surface=self.normalize_surface(
                session.projection.active_surface or session.projection.origin_surface
            ),
            memory_diagnostics=dict(execution.memory_diagnostics),
            result=execution.result,
        )

    def _execute_mutating_memory_command(
        self,
        session: "MainAgentSessionState",
        command: RuntimeSessionMemoryCommand,
    ) -> RuntimeSessionMemoryCommandExecution:
        if session.projection.busy:
            raise HTTPException(status_code=409, detail="Session is busy. Wait for the current turn to finish.")
        return self.session_memory_commands.execute(session, command)

    def _build_session_skill_response(
        self,
        *,
        session: "MainAgentSessionState",
        action: str,
        status: str,
        result: dict[str, Any],
    ) -> MainAgentSessionSkillResponse:
        return MainAgentSessionSkillResponse(
            status=status,
            session_id=session.session_id,
            action=action,
            active_surface=self.normalize_surface(
                session.projection.active_surface or session.projection.origin_surface
            ),
            result=result,
        )

    def _apply_model_selection_plan_state(
        self,
        session: "MainAgentSessionState",
        *,
        plan: RuntimeSessionModelSelectionPlan,
    ) -> None:
        if plan.update_pending_identity:
            self.set_pending_model_identity(session, plan.pending_identity)

    def _build_session_model_selection_response(
        self,
        *,
        session: "MainAgentSessionState",
        status: str,
        applied: bool,
        queued: bool,
        surface: str | None,
    ) -> MainAgentSessionModelSelectionResponse:
        active_surface = self.normalize_surface(
            session.projection.active_surface or session.projection.origin_surface or surface
        )
        selected_identity = self.selected_model_identity(session)
        pending_identity = self.pending_model_identity(session)
        return MainAgentSessionModelSelectionResponse(
            status=status,
            session_id=session.session_id,
            active_surface=active_surface,
            applied=applied,
            queued=queued,
            selected_model_source=selected_identity[0] if selected_identity is not None else None,
            selected_provider_id=selected_identity[1] if selected_identity is not None else None,
            selected_model_id=selected_identity[2] if selected_identity is not None else None,
            pending_model_source=pending_identity[0] if pending_identity is not None else None,
            pending_provider_id=pending_identity[1] if pending_identity is not None else None,
            pending_model_id=pending_identity[2] if pending_identity is not None else None,
        )

    def _build_session_runtime_policy_response(
        self,
        *,
        session: "MainAgentSessionState",
        plan: RuntimeSessionRuntimePolicyPlan,
        diagnostics: dict[str, Any],
    ) -> MainAgentSessionRuntimePolicyResponse:
        return MainAgentSessionRuntimePolicyResponse(
            status="updated",
            session_id=session.session_id,
            active_surface=self.normalize_surface(
                session.projection.active_surface or session.projection.origin_surface
            ),
            applied=True,
            approval_profile=plan.approval_profile,
            access_level=plan.access_level,
            sandbox_diagnostics=dict(diagnostics),
        )

    def _execute_runtime_policy_update(
        self,
        session: "MainAgentSessionState",
        *,
        approval_profile: str | None,
        access_level: str | None,
        surface: str | None,
        channel_type: str | None,
        conversation_id: str | None,
        sender_id: str | None,
    ) -> RuntimeSessionRuntimePolicyExecution:
        plan = self.session_runtime_policy.build_plan(
            session,
            approval_profile=approval_profile,
            access_level=access_level,
        )
        if session.runtime.agent is not None:
            diagnostics = self.session_agent_runtime.reconfigure_runtime_policy(
                session,
                approval_profile=plan.approval_profile,
                access_level=plan.access_level,
            )
        else:
            diagnostics = dict(plan.local_sandbox_diagnostics or {})
            session.projection.sandbox_diagnostics = dict(diagnostics)

        self.session_live_state.bind_surface(
            session,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        return RuntimeSessionRuntimePolicyExecution(
            plan=plan,
            diagnostics=dict(diagnostics),
        )

    async def _execute_skill_mutation(
        self,
        session: "MainAgentSessionState",
        *,
        mutation: Any,
        queued_other_ids: tuple[str, ...],
    ) -> RuntimeSessionSkillMutationExecution:
        if session.projection.busy:
            queued_ids = await self.queue_workspace_skill_reload(
                session.workspace_dir,
                current_session_id=session.session_id,
                reason=mutation.reload_reason,
                include_current=True,
            )
            return RuntimeSessionSkillMutationExecution(
                status="busy",
                result=self.session_skill_commands.build_busy_result(
                    session,
                    mutation,
                    queued_ids=queued_ids,
                    include_current_note=True,
                ),
            )

        result = await self.session_skill_commands.complete_mutation(
            session,
            mutation,
            queued_ids=queued_other_ids,
            rebuild_session_agent=lambda identity: self.session_agent_runtime.rebuild_agent_with_identity(
                session,
                identity,
            ),
            selected_model_identity=self.selected_model_identity(session),
        )
        return RuntimeSessionSkillMutationExecution(
            status="ok",
            result=result,
        )

    async def _execute_model_selection_update(
        self,
        session: "MainAgentSessionState",
        *,
        request: Any,
        surface: str | None,
        channel_type: str | None,
        conversation_id: str | None,
        sender_id: str | None,
    ) -> RuntimeSessionModelSelectionExecution:
        plan = self.session_model_selection.plan_update(session, request)
        self._apply_model_selection_plan_state(session, plan=plan)
        if plan.rebuild_identity is not None:
            await self.session_agent_runtime.rebuild_agent_with_identity(session, plan.rebuild_identity)
        if plan.bind_surface:
            self.session_live_state.bind_surface(
                session,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
        return RuntimeSessionModelSelectionExecution(plan=plan)

    @staticmethod
    def _session_control_command_name(action: str) -> str:
        normalized = _safe_text(action).lower().replace("-", "_")
        if normalized.startswith("mcp_"):
            return normalized.replace("_", " ")
        return normalized

    @staticmethod
    def _active_surface(
        session: "MainAgentSessionState",
        surface: str | None,
    ) -> str | None:
        return surface or session.projection.active_surface or session.projection.origin_surface


__all__ = [
    "RuntimeSessionModelSelectionExecution",
    "RuntimeSessionOperatorHandler",
    "RuntimeSessionRuntimePolicyExecution",
    "RuntimeSessionSkillMutationExecution",
]
