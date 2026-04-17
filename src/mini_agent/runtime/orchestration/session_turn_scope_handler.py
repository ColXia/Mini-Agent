"""Turn-scope orchestration extracted from runtime manager / session service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


@dataclass(slots=True)
class RuntimeSessionTurnScopeHandler:
    bind_surface_mutation: Callable[..., None]
    mark_turn_started_mutation: Callable[..., None]
    mark_turn_finished_mutation: Callable[..., None]
    record_message_mutation: Callable[..., None]
    record_activity_mutation: Callable[..., dict[str, Any]]
    record_pending_approval_mutation: Callable[..., dict[str, Any]]
    clear_pending_approval_mutation: Callable[..., None]
    build_recovery_turn_context_fn: Callable[["MainAgentSessionState"], dict[str, Any] | None]
    clear_recovery_context_mutation: Callable[..., None]
    capture_prepared_context_state_mutation: Callable[["MainAgentSessionState"], None]
    restore_prepared_context_state_mutation: Callable[["MainAgentSessionState"], None]
    apply_pending_session_model_selection: Callable[["MainAgentSessionState"], Awaitable[bool]]
    apply_pending_session_skill_reload: Callable[["MainAgentSessionState"], Awaitable[bool]]
    persist_session: Callable[["MainAgentSessionState"], None]

    async def enter(
        self,
        session: "MainAgentSessionState",
        *,
        surface: str | None,
        channel_type: str | None,
        conversation_id: str | None,
        sender_id: str | None,
        user_message: str,
        running_detail: str,
    ) -> dict[str, Any] | None:
        await session.runtime.lock.acquire()
        try:
            self.bind_surface(
                session,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            await self.apply_pending_session_model_selection(session)
            await self.apply_pending_session_skill_reload(session)
            recovery_context = self.build_recovery_turn_context(session)
            self.mark_turn_started(
                session,
                surface=surface,
                detail=running_detail,
            )
            self.record_message(
                session,
                role="user",
                content=user_message,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            return recovery_context
        except Exception:
            session.runtime.lock.release()
            raise

    async def exit(self, session: "MainAgentSessionState") -> None:
        try:
            self.mark_turn_finished(session)
            await self.apply_pending_session_skill_reload(session)
        finally:
            session.runtime.lock.release()

    @staticmethod
    def touch(session: "MainAgentSessionState") -> None:
        session.touch()

    def bind_surface(
        self,
        session: "MainAgentSessionState",
        *,
        surface: str | None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self.bind_surface_mutation(
            session,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )
        self.persist_session(session)

    def mark_turn_started(
        self,
        session: "MainAgentSessionState",
        *,
        surface: str | None,
        detail: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self.mark_turn_started_mutation(
            session,
            surface=surface,
            detail=detail,
            now_utc=now_utc,
        )
        self.persist_session(session)

    def mark_turn_finished(
        self,
        session: "MainAgentSessionState",
        *,
        now_utc: datetime | None = None,
    ) -> None:
        self.mark_turn_finished_mutation(
            session,
            now_utc=now_utc,
        )
        self.persist_session(session)

    def record_message(
        self,
        session: "MainAgentSessionState",
        *,
        role: str,
        content: str,
        surface: str | None,
        metadata: dict[str, Any] | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self.record_message_mutation(
            session,
            role=role,
            content=content,
            surface=surface,
            metadata=metadata,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )
        self.persist_session(session)

    def record_turn(
        self,
        session: "MainAgentSessionState",
        *,
        user_message: str,
        assistant_reply: str,
        surface: str | None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self.record_message(
            session,
            role="user",
            content=user_message,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )
        self.record_message(
            session,
            role="assistant",
            content=assistant_reply,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )

    def record_activity(
        self,
        session: "MainAgentSessionState",
        *,
        label: str,
        detail: str,
        surface: str | None,
        activity_id: str | None = None,
        preview: str = "",
        output_text: str = "",
        state: str = "",
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        result = self.record_activity_mutation(
            session,
            label=label,
            detail=detail,
            surface=surface,
            activity_id=activity_id,
            preview=preview,
            output_text=output_text,
            state=state,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )
        self.persist_session(session)
        return result

    def record_pending_approval(
        self,
        session: "MainAgentSessionState",
        *,
        payload: dict[str, Any],
        future: Any,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        normalized = self.record_pending_approval_mutation(
            session,
            payload=payload,
            future=future,
            now_utc=now_utc,
        )
        self.persist_session(session)
        return normalized

    def clear_pending_approval(
        self,
        session: "MainAgentSessionState",
        *,
        token: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self.clear_pending_approval_mutation(
            session,
            token=token,
            now_utc=now_utc,
        )
        self.persist_session(session)

    def build_recovery_turn_context(
        self,
        session: "MainAgentSessionState",
    ) -> dict[str, Any] | None:
        return self.build_recovery_turn_context_fn(session)

    def clear_recovery_context(
        self,
        session: "MainAgentSessionState",
        *,
        now_utc: datetime | None = None,
    ) -> None:
        self.clear_recovery_context_mutation(
            session,
            now_utc=now_utc,
        )
        self.persist_session(session)

    def restore_prepared_context_state(self, session: "MainAgentSessionState") -> None:
        self.restore_prepared_context_state_mutation(session)

    def capture_prepared_context_state(self, session: "MainAgentSessionState") -> None:
        self.capture_prepared_context_state_mutation(session)
        self.persist_session(session)


__all__ = ["RuntimeSessionTurnScopeHandler"]
