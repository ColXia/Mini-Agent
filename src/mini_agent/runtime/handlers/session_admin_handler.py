"""Session admin/live-state mutations extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from mini_agent.interfaces import MainAgentSessionSummary
    from mini_agent.runtime.session_state import MainAgentSessionState


@dataclass(slots=True)
class RuntimeSessionAdminHandler:
    rename_session_mutation: Callable[["MainAgentSessionState"], None] | Callable[..., None]
    set_session_shared_mutation: Callable[["MainAgentSessionState"], None] | Callable[..., None]
    reset_runtime_state_mutation: Callable[["MainAgentSessionState"], None] | Callable[..., None]
    bind_surface_mutation: Callable[["MainAgentSessionState"], None] | Callable[..., None]
    reset_session_lifecycle_mutation: Callable[["MainAgentSessionState"], None] | Callable[..., None]
    build_session_summary: Callable[["MainAgentSessionState"], "MainAgentSessionSummary"]
    persist_session: Callable[["MainAgentSessionState"], None]

    async def rename_session(
        self,
        session: "MainAgentSessionState",
        *,
        title: str,
    ) -> "MainAgentSessionSummary":
        async with session.runtime.lock:
            self.rename_session_mutation(session, title=title)
            session.touch()
            self.persist_session(session)
            return self.build_session_summary(session)

    async def set_session_shared(
        self,
        session: "MainAgentSessionState",
        *,
        shared: bool,
    ) -> "MainAgentSessionSummary":
        async with session.runtime.lock:
            self.set_session_shared_mutation(session, shared=shared)
            session.touch()
            self.persist_session(session)
            return self.build_session_summary(session)

    async def reset_session(
        self,
        session: "MainAgentSessionState",
        *,
        now_utc: datetime | None = None,
    ) -> None:
        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        async with session.runtime.lock:
            self.reset_runtime_state_mutation(
                session,
                clear_runtime_task_memory=True,
            )
            session.transcript_state.transcript.clear()
            session.transcript_state.next_transcript_index = 1
            self.reset_session_lifecycle_mutation(session, now_utc=now)
            session.touch(now_utc=now)
            self.persist_session(session)

    async def set_active_surface(
        self,
        session: "MainAgentSessionState",
        *,
        surface: str,
        now_utc: datetime | None = None,
    ) -> "MainAgentSessionSummary":
        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        async with session.runtime.lock:
            self.bind_surface_mutation(
                session,
                surface=surface,
                reply_enabled=False,
                now_utc=now,
            )
            session.touch(now_utc=now)
            self.persist_session(session)
            return self.build_session_summary(session)


__all__ = ["RuntimeSessionAdminHandler"]
