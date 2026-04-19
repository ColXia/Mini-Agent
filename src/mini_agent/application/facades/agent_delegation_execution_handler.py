"""Delegation execution and fallback orchestration for surface chat flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from mini_agent.agent_core.delegation import DelegationManager, DelegationRequest
from mini_agent.application.support.managed_session_turn import ManagedSessionTurn

from .agent_turn_execution_handler import AgentTurnExecutionHandler, SurfaceAgentExecutionRequest


class SessionTaskDelegationPort(Protocol):
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
    ) -> ManagedSessionTurn: ...


@dataclass(frozen=True)
class AgentDelegationExecutionResult:
    reply: str
    used: bool
    fallback_used: bool
    success: bool
    worker_id: str
    child_session_id: str | None
    error: str | None
    events: tuple[dict[str, Any], ...]


class AgentDelegationExecutionHandler:
    """Owns delegated child-turn execution plus main-agent fallback behavior."""

    def __init__(
        self,
        *,
        session_task_service: SessionTaskDelegationPort | None = None,
        session_service: SessionTaskDelegationPort | None = None,
        agent_execution: AgentTurnExecutionHandler,
        delegation_owner: str = "sub-agent",
        fallback_worker_id: str = "main-agent",
    ) -> None:
        resolved_session_task_service = session_task_service or session_service
        if resolved_session_task_service is None:
            raise RuntimeError("Session task service is not configured.")
        self._session_task_service = resolved_session_task_service
        self._agent_execution = agent_execution
        self._delegation_owner = delegation_owner
        self._fallback_worker_id = fallback_worker_id

    async def execute(
        self,
        *,
        turn: ManagedSessionTurn,
        delegate_prompt: str,
    ) -> AgentDelegationExecutionResult:
        events: list[dict[str, Any]] = []
        owner = self._delegation_owner
        write_scope = f"workspace:{turn.workspace_dir}"

        def _emit(event_type: str, payload: dict[str, Any]) -> None:
            events.append({"event_type": event_type, "payload": dict(payload)})

        async def _runner(request: DelegationRequest) -> dict[str, Any]:
            child_turn = await self._session_task_service.prepare_derived_chat_turn(
                parent_session_id=turn.session_id,
                message=request.prompt,
                title=self._delegated_session_title(request.prompt),
                surface=turn.active_surface or turn.origin_surface,
                running_detail="delegated task running",
                reason="delegation",
                metadata={
                    "delegation_task_id": request.task_id,
                    "owner": owner,
                    "write_scope": write_scope,
                },
            )

            async with child_turn:
                try:
                    result = await self._agent_execution.run_agent_once(
                        child_turn,
                        SurfaceAgentExecutionRequest(
                            message=request.prompt,
                            surface=child_turn.active_surface or child_turn.origin_surface,
                            channel_type=child_turn.channel_type,
                            conversation_id=child_turn.conversation_id,
                            sender_id=child_turn.sender_id,
                        ),
                    )
                    child_turn.capture_prepared_context_state()
                    if child_turn.recovery_context is not None:
                        child_turn.clear_recovery_context()
                    child_turn.record_message(
                        role="assistant",
                        content=result.message,
                        surface=child_turn.active_surface or child_turn.origin_surface,
                        channel_type=child_turn.channel_type,
                        conversation_id=child_turn.conversation_id,
                        sender_id=child_turn.sender_id,
                    )
                    child_turn.touch()
                    return {
                        "success": True,
                        "worker_id": owner,
                        "child_session_id": child_turn.session_id,
                        "output": result.message,
                    }
                except Exception as exc:
                    error_text = str(getattr(exc, "detail", "") or str(exc) or "delegation failed")
                    child_turn.record_message(
                        role="assistant",
                        content=f"Delegation failed: {error_text}",
                        surface=child_turn.active_surface or child_turn.origin_surface,
                        metadata={"kind": "delegation_error"},
                        channel_type=child_turn.channel_type,
                        conversation_id=child_turn.conversation_id,
                        sender_id=child_turn.sender_id,
                    )
                    child_turn.touch()
                    return {
                        "success": False,
                        "worker_id": owner,
                        "child_session_id": child_turn.session_id,
                        "output": "",
                        "error": error_text,
                    }

        manager = DelegationManager(
            runner=_runner,
            max_depth=2,
            max_concurrent=1,
        )
        task = manager.create_task(
            prompt=delegate_prompt,
            parent_session_id=turn.session_id,
            metadata={"owner": owner, "write_scope": write_scope},
        )

        _emit(
            "delegation.started",
            {
                "task_id": task.task_id,
                "session_id": turn.session_id,
                "owner": owner,
                "write_scope": write_scope,
            },
        )
        result = await manager.delegate(task, parent_depth=0)
        child_session_id = str(getattr(result, "child_session_id", "") or "")
        normalized_child_session_id = child_session_id or None

        if result.success:
            _emit(
                "delegation.completed",
                {
                    "task_id": task.task_id,
                    "success": True,
                    "worker_id": result.worker_id,
                    "child_session_id": normalized_child_session_id,
                    "fallback_used": False,
                    "duration_seconds": result.duration_seconds,
                },
            )
            turn.touch()
            return AgentDelegationExecutionResult(
                reply=result.output,
                used=True,
                fallback_used=False,
                success=True,
                worker_id=result.worker_id,
                child_session_id=normalized_child_session_id,
                error=None,
                events=tuple(events),
            )

        _emit(
            "delegation.failed",
            {
                "task_id": task.task_id,
                "success": False,
                "worker_id": result.worker_id,
                "child_session_id": normalized_child_session_id,
                "error": result.error,
                "duration_seconds": result.duration_seconds,
            },
        )
        fallback_turn = await self._agent_execution.run_agent_once(
            turn,
            SurfaceAgentExecutionRequest(
                message=delegate_prompt,
                surface=turn.active_surface or turn.origin_surface,
                channel_type=turn.channel_type,
                conversation_id=turn.conversation_id,
                sender_id=turn.sender_id,
            ),
        )
        _emit(
            "delegation.completed",
            {
                "task_id": task.task_id,
                "success": False,
                "worker_id": self._fallback_worker_id,
                "child_session_id": normalized_child_session_id,
                "fallback_used": True,
            },
        )
        return AgentDelegationExecutionResult(
            reply=fallback_turn.message,
            used=True,
            fallback_used=True,
            success=False,
            worker_id=self._fallback_worker_id,
            child_session_id=normalized_child_session_id,
            error=result.error,
            events=tuple(events),
        )

    @staticmethod
    def _delegated_session_title(prompt: str) -> str:
        preview = " ".join(str(prompt or "").split())
        if not preview:
            return "Task"
        if len(preview) > 48:
            preview = f"{preview[:45]}..."
        return f"Task: {preview}"


__all__ = [
    "AgentDelegationExecutionHandler",
    "AgentDelegationExecutionResult",
]
