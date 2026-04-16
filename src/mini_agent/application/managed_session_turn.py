"""Application-level managed session turn lease."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

from mini_agent.agent_core.engine import Agent
from mini_agent.application.interaction_request_adapter import ApplicationInteractionBinding
from mini_agent.application.session_runtime_port import (
    ManagedRuntimeSessionPort,
    SessionTurnScopePort,
)


class ManagedSessionTurn(AbstractAsyncContextManager["ManagedSessionTurn"]):
    """Scoped session turn lease that owns lock/lifecycle boundaries."""

    def __init__(
        self,
        *,
        turn_scope: SessionTurnScopePort,
        session: ManagedRuntimeSessionPort,
        binding: ApplicationInteractionBinding,
        user_message: str,
        running_detail: str,
    ) -> None:
        self._turn_scope = turn_scope
        self._session = session
        self._binding = binding
        self._user_message = user_message
        self._running_detail = running_detail
        self._entered = False
        self._recovery_context: dict[str, Any] | None = None

    @property
    def session_id(self) -> str:
        return self._session.session_id

    @property
    def workspace_dir(self) -> Path:
        return self._session.workspace_dir

    @property
    def agent(self) -> Agent:
        return self._session.agent

    @property
    def active_surface(self) -> str:
        return self._session.active_surface

    @property
    def origin_surface(self) -> str:
        return self._session.origin_surface

    @property
    def channel_type(self) -> str | None:
        return self._session.channel_type

    @property
    def conversation_id(self) -> str | None:
        return self._session.conversation_id

    @property
    def sender_id(self) -> str | None:
        return self._session.sender_id

    @property
    def context_policy(self) -> dict[str, Any]:
        return self._session.context_policy

    @property
    def cancel_event(self):  # noqa: ANN201
        return self._session.cancel_event

    @property
    def busy(self) -> bool:
        return self._session.busy

    @property
    def running_state(self) -> str:
        return self._session.running_state

    @running_state.setter
    def running_state(self, value: str) -> None:
        self._session.running_state = value

    @property
    def pending_approvals(self) -> list[dict[str, Any]]:
        return self._session.pending_approvals

    @property
    def updated_at(self):  # noqa: ANN201
        return self._session.updated_at

    @property
    def recovery_context(self) -> dict[str, Any] | None:
        return dict(self._recovery_context) if isinstance(self._recovery_context, dict) else None

    @property
    def token_usage(self) -> int:
        return self._session.token_usage

    @property
    def message_count(self) -> int:
        return self._session.message_count

    async def __aenter__(self) -> ManagedSessionTurn:
        self._recovery_context = await self._turn_scope.enter(
            self._session,
            surface=self._binding.surface,
            channel_type=self._binding.channel_type,
            conversation_id=self._binding.conversation_id,
            sender_id=self._binding.sender_id,
            user_message=self._user_message,
            running_detail=self._running_detail,
        )
        self._entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        if self._entered:
            self._entered = False
            await self._turn_scope.exit(self._session)

    def touch(self) -> None:
        self._turn_scope.touch(self._session)

    def restore_prepared_context_state(self) -> None:
        self._turn_scope.restore_prepared_context_state(self._session)

    def capture_prepared_context_state(self) -> None:
        self._turn_scope.capture_prepared_context_state(self._session)

    def clear_recovery_context(self) -> None:
        self._turn_scope.clear_recovery_context(self._session)
        self._recovery_context = None

    def record_message(
        self,
        *,
        role: str,
        content: str,
        surface: str | None,
        metadata: dict[str, Any] | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> None:
        self._turn_scope.record_message(
            self._session,
            role=role,
            content=content,
            surface=surface,
            metadata=metadata,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )

    def record_activity(
        self,
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
    ) -> dict[str, Any]:
        return self._turn_scope.record_activity(
            self._session,
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
        )

    def record_pending_approval(
        self,
        *,
        payload: dict[str, Any],
        future,
    ) -> dict[str, Any]:  # noqa: ANN001
        return self._turn_scope.record_pending_approval(
            self._session,
            payload=payload,
            future=future,
        )

    def clear_pending_approval(self, *, token: str | None = None) -> None:
        self._turn_scope.clear_pending_approval(self._session, token=token)


__all__ = ["ManagedSessionTurn"]
