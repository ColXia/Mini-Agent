"""Session hydration/restore coordination outside the top-level runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Callable, MutableMapping, Sequence

from mini_agent.runtime.session_hydration_builder import RuntimeSessionHydrationPayload

if TYPE_CHECKING:
    from mini_agent.runtime.orchestration.session_restore_handler import RuntimeSessionRestoreExecution
    from mini_agent.runtime.session_state import MainAgentSessionState


@dataclass(slots=True)
class RuntimeSessionHydrationCoordinator:
    prepare_restore_payload: Callable[[dict[str, Any], datetime], RuntimeSessionHydrationPayload]
    hydrate_payload: Callable[
        [RuntimeSessionHydrationPayload, datetime, "MainAgentSessionState | None"],
        Awaitable["RuntimeSessionRestoreExecution"],
    ]
    register_session: Callable[["MainAgentSessionState"], None]
    persist_hydrated_session: Callable[["MainAgentSessionState", Sequence[Any] | None], None]

    async def restore_persisted_session(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        record: dict[str, Any],
        *,
        now_utc: datetime | None = None,
    ) -> "MainAgentSessionState":
        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        payload = self.prepare_restore_payload(record, now)
        return await self.hydrate_session(
            sessions,
            payload,
            now_utc=now,
            persist_after=False,
        )

    async def hydrate_session(
        self,
        sessions: MutableMapping[str, "MainAgentSessionState"],
        payload: RuntimeSessionHydrationPayload,
        *,
        now_utc: datetime,
        persist_after: bool,
    ) -> "MainAgentSessionState":
        session_id = payload.session_id
        execution = await self.hydrate_payload(
            payload,
            now_utc,
            sessions.get(session_id),
        )
        if execution.created:
            sessions[session_id] = execution.session
            self.register_session(execution.session)
            if persist_after:
                self.persist_hydrated_session(
                    execution.session,
                    execution.agent_messages_for_persist,
                )
        return execution.session


__all__ = ["RuntimeSessionHydrationCoordinator"]
