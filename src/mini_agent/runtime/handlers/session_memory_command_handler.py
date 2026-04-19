"""Runtime wrapper for shared session-memory command execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from fastapi import HTTPException

from mini_agent.memory.command_service import (
    MUTATING_MEMORY_ACTIONS,
    SUPPORTED_MEMORY_ACTIONS,
    MemoryCommandError,
    MemoryCommandRequest,
    MemoryCommandService,
)
from mini_agent.memory.operator_actions import (
    save_operator_profile_fact as default_save_operator_profile_fact,
    save_operator_workspace_note as default_save_operator_workspace_note,
)
from mini_agent.memory.runtime_backend import WorkspaceRuntimeMemoryBackend

if TYPE_CHECKING:
    from mini_agent.session.store_records import MainAgentSessionState


@dataclass(frozen=True, slots=True)
class RuntimeSessionMemoryCommand:
    action: str
    engram_id: str | None = None
    content: str | None = None
    query: str | None = None
    day: str | None = None
    export_format: str | None = None
    detail_mode: str = "full"


@dataclass(slots=True)
class RuntimeSessionMemoryCommandExecution:
    memory_diagnostics: dict[str, Any]
    result: dict[str, Any]


@dataclass(slots=True)
class RuntimeSessionMemoryCommandHandler:
    build_memory_diagnostics_for_session: Callable[..., dict[str, Any]]
    command_service: MemoryCommandService | None = None
    runtime_task_memory_backend: Any | None = None
    save_operator_workspace_note: Callable[..., dict[str, Any]] | None = None
    save_operator_profile_fact: Callable[..., dict[str, Any]] | None = None

    def validate_action(self, action: str) -> None:
        if action not in SUPPORTED_MEMORY_ACTIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported session memory action: {action}")

    @staticmethod
    def is_mutating_action(action: str) -> bool:
        return action in MUTATING_MEMORY_ACTIONS

    def execute(
        self,
        session: "MainAgentSessionState",
        command: MemoryCommandRequest | RuntimeSessionMemoryCommand,
    ) -> RuntimeSessionMemoryCommandExecution:
        request = self._normalize_request(command)
        try:
            outcome = self._command_service().execute(
                workspace_dir=session.workspace_dir,
                session_id=session.session_id,
                diagnostics_loader=lambda: self.build_memory_diagnostics_for_session(session),
                command=request,
                prepared_context=session.projection.last_prepared_context,
            )
        except MemoryCommandError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

        session.projection.memory_diagnostics = dict(outcome.memory_diagnostics)
        result = {
            "summary": outcome.summary,
            "details": outcome.details,
        }
        result.update(outcome.payload)
        return RuntimeSessionMemoryCommandExecution(
            memory_diagnostics=dict(outcome.memory_diagnostics),
            result=result,
        )

    def _command_service(self) -> MemoryCommandService:
        if self.command_service is not None:
            return self.command_service
        runtime_memory_backend = self.runtime_task_memory_backend
        if runtime_memory_backend is None:
            runtime_memory_backend = WorkspaceRuntimeMemoryBackend()
        return MemoryCommandService(
            runtime_memory_backend=runtime_memory_backend,
            save_workspace_note=self.save_operator_workspace_note or default_save_operator_workspace_note,
            save_profile_fact=self.save_operator_profile_fact or default_save_operator_profile_fact,
        )

    @staticmethod
    def _normalize_request(
        command: MemoryCommandRequest | RuntimeSessionMemoryCommand,
    ) -> MemoryCommandRequest:
        if isinstance(command, MemoryCommandRequest):
            return command
        return MemoryCommandRequest(
            action=command.action,
            engram_id=command.engram_id,
            content=command.content,
            query=command.query,
            day=command.day,
            export_format=command.export_format,
            detail_mode=command.detail_mode,
        )


__all__ = [
    "MUTATING_MEMORY_ACTIONS",
    "RuntimeSessionMemoryCommand",
    "RuntimeSessionMemoryCommandExecution",
    "RuntimeSessionMemoryCommandHandler",
    "SUPPORTED_MEMORY_ACTIONS",
]



