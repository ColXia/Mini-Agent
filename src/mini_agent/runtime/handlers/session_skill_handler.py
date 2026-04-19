"""Session skill command ownership for managed runtime sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from fastapi import HTTPException

from mini_agent.agent_core.skills.command_service import (
    SkillCommandError,
    SkillCommandMutationPlan,
    SkillCommandRequest,
    SkillCommandService,
)
from mini_agent.interfaces.agent import MainAgentSessionSkillResponse
from mini_agent.runtime.handlers.session_command_coordinator import (
    RuntimeSessionCommandCoordinator,
    RuntimeSessionCommandTranscript,
)

if TYPE_CHECKING:
    from mini_agent.runtime.handlers.session_agent_runtime_handler import RuntimeSessionAgentRuntimeHandler
    from mini_agent.session.store_records import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True, slots=True)
class RuntimeSessionSkillMutationExecution:
    status: str
    result: dict[str, Any]


@dataclass(slots=True)
class RuntimeSessionSkillHandler:
    normalize_surface: Callable[[str | None], str]
    session_commands: RuntimeSessionCommandCoordinator
    session_skill_commands: SkillCommandService
    session_agent_runtime: "RuntimeSessionAgentRuntimeHandler"
    load_runtime_config: Callable[[], Any]
    selected_model_identity: Callable[["MainAgentSessionState"], tuple[str, str, str] | None]
    queue_workspace_skill_reload: Callable[..., Awaitable[tuple[str, ...]]]

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
        command = SkillCommandRequest(
            action=_safe_text(action).lower().replace("-", "_"),
            skill_name=_safe_text(skill_name) or None,
            path=_safe_text(path) or None,
            query=_safe_text(query) or None,
            mode=_safe_text(mode) or None,
        )
        try:
            self.session_skill_commands.validate_action(command.action)
            prepared = self.session_skill_commands.prepare(
                workspace_dir=session.workspace_dir,
                command=command,
                agent=session.runtime.agent,
                config=self.load_runtime_config(),
            )
        except SkillCommandError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
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
                    session_id=session.session_id,
                    mutation=mutation,
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

    async def _execute_skill_mutation(
        self,
        session: "MainAgentSessionState",
        *,
        mutation: SkillCommandMutationPlan,
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
                    session_id=session.session_id,
                    mutation=mutation,
                    queued_ids=queued_ids,
                    include_current_note=True,
                ),
            )

        result = await self.session_skill_commands.complete_mutation(
            workspace_dir=session.workspace_dir,
            mutation=mutation,
            queued_ids=queued_other_ids,
            session_id=session.session_id,
            include_current_note=False,
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

    @staticmethod
    def _active_surface(
        session: "MainAgentSessionState",
        surface: str | None,
    ) -> str | None:
        return surface or session.projection.active_surface or session.projection.origin_surface


__all__ = [
    "RuntimeSessionSkillHandler",
    "RuntimeSessionSkillMutationExecution",
]
