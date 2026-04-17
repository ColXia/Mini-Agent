"""Thin application service for run-level control operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_agent.application.ports.run_runtime_port import RunRuntimePort
from mini_agent.application.ports.session_task_port import SessionTaskPort


@dataclass(slots=True)
class RunControlApplicationService:
    """Resolve user control actions against run truth with session compatibility."""

    run_runtime: RunRuntimePort
    session_tasks: SessionTaskPort | None = None

    async def get_run(self, run_id: str) -> Any:
        return await self.run_runtime.get_run(run_id)

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        return await self.run_runtime.interrupt_run(run_id, reason=reason, source=source)

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        return await self.run_runtime.resume_run(run_id, resume_token=resume_token, source=source)

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        return await self.run_runtime.cancel_run(run_id, reason=reason, source=source)

    async def approve_wait(
        self,
        run_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        return await self.run_runtime.resolve_approval_wait(
            run_id,
            approved=True,
            token=token,
            source=source,
            reason=reason,
        )

    async def deny_wait(
        self,
        run_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        return await self.run_runtime.resolve_approval_wait(
            run_id,
            approved=False,
            token=token,
            source=source,
            reason=reason,
        )

    async def interrupt_session_run(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        run_id = await self._require_run_id(session_id)
        return await self.interrupt_run(run_id, reason=reason, source=source)

    async def resume_session_run(
        self,
        session_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        run_id = await self._require_run_id(session_id)
        return await self.resume_run(run_id, resume_token=resume_token, source=source)

    async def cancel_session_run(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any:
        run_id = await self._try_resolve_run_id(session_id)
        if run_id:
            return await self.cancel_run(run_id, reason=reason, source=source)
        session_tasks = self._require_session_tasks()
        return await session_tasks.cancel_session_turn(
            session_id,
            reason=reason,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def approve_session_wait(
        self,
        session_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any:
        run_id = await self._try_resolve_run_id(session_id)
        if run_id:
            return await self.approve_wait(run_id, token=token, source=source, reason=reason)
        return await self._resolve_session_approval(
            session_id,
            approved=True,
            token=token,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def deny_session_wait(
        self,
        session_id: str,
        *,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any:
        run_id = await self._try_resolve_run_id(session_id)
        if run_id:
            return await self.deny_wait(run_id, token=token, source=source, reason=reason)
        return await self._resolve_session_approval(
            session_id,
            approved=False,
            token=token,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    async def _try_resolve_run_id(self, session_id: str) -> str | None:
        if self.session_tasks is None:
            return None
        return await self.session_tasks.resolve_run_id_for_session(session_id)

    async def _require_run_id(self, session_id: str) -> str:
        run_id = await self._try_resolve_run_id(session_id)
        if run_id:
            return run_id
        raise LookupError(f"Session {session_id!r} is not attached to a run.")

    def _require_session_tasks(self) -> SessionTaskPort:
        if self.session_tasks is None:
            raise LookupError("Session task compatibility port is not configured.")
        return self.session_tasks

    async def _resolve_session_approval(
        self,
        session_id: str,
        *,
        approved: bool,
        token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any:
        session_tasks = self._require_session_tasks()
        return await session_tasks.resolve_pending_approval(
            session_id,
            approved=approved,
            token=token,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )


__all__ = ["RunControlApplicationService"]
