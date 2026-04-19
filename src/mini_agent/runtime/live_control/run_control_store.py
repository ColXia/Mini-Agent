"""Run-owned control truth backed by the v11.1 kernel runtime registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from mini_agent.agent_core.contracts import ApprovalWait, RunControlState
from mini_agent.runtime.orchestration.kernel_state_registry import (
    CANCEL_REQUESTED_RUNNING_STATE,
    CANCEL_REQUESTED_STATUS,
    CANCELLING_PHASE,
    INTERRUPT_REQUESTED_RUNNING_STATE,
    INTERRUPT_REQUESTED_STATUS,
    INTERRUPTING_PHASE,
    PAUSED_PHASE,
    PAUSED_STATUS,
    RESUME_REQUESTED_STATUS,
    RESUMING_PHASE,
    RuntimeKernelControlBridge as RunControlRuntimeBridge,
    RuntimeKernelStateRegistry,
)

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


class RuntimeSessionRunControlStore:
    """Thin compatibility adapter over the kernel-backed runtime registry."""

    def __init__(
        self,
        *,
        selected_model_identity_for_session: (
            Callable[["MainAgentSessionState"], tuple[str, str, str] | None] | None
        ) = None,
    ) -> None:
        self._registry = RuntimeKernelStateRegistry(
            selected_model_identity_for_session=selected_model_identity_for_session,
        )

    @staticmethod
    def run_id_for_session(session_id: str) -> str:
        return RuntimeKernelStateRegistry.run_id_for_session(session_id)

    def clear(self) -> None:
        self._registry.clear()

    def drop_session(self, session_id: str) -> None:
        self._registry.drop_session(session_id)

    def current_control_state(self, session: "MainAgentSessionState") -> RunControlState:
        return self._registry.current_control_state(session)

    def current_control_state_for_run_id(self, run_id: str) -> RunControlState | None:
        return self._registry.current_control_state_for_run_id(run_id)

    def current_approval_wait(self, session: "MainAgentSessionState") -> ApprovalWait | None:
        return self._registry.current_approval_wait(session)

    def pending_approval_payloads(self, session: "MainAgentSessionState") -> list[dict[str, Any]]:
        return self._registry.pending_approval_payloads(session)

    def pending_approval_payloads_for_run_id(self, run_id: str) -> list[dict[str, Any]]:
        return self._registry.pending_approval_payloads_for_run_id(run_id)

    def pending_approval_waiter(
        self,
        session: "MainAgentSessionState",
        *,
        token: str | None,
    ):
        return self._registry.pending_approval_waiter(session, token=token)

    def begin_turn(
        self,
        session: "MainAgentSessionState",
        *,
        surface: str | None = None,
        detail: str | None = None,
    ) -> RunControlState:
        record = self._registry.begin_turn(session, surface=surface, detail=detail)
        self._registry.sync_session_runtime(session)
        return record.run_control

    def finish_turn(self, session: "MainAgentSessionState") -> RunControlState:
        record = self._registry.finish_turn(session)
        self._registry.sync_session_runtime(session)
        return record.run_control

    def pause_turn(
        self,
        session: "MainAgentSessionState",
        *,
        reason: str | None = None,
    ) -> RunControlState:
        record = self._registry.pause_turn(session, reason=reason)
        self._registry.sync_session_runtime(session)
        return record.run_control

    def request_interrupt(
        self,
        session: "MainAgentSessionState",
        *,
        source: str | None = None,
        reason: str | None = None,
    ) -> RunControlState:
        record = self._registry.request_interrupt(session, source=source, reason=reason)
        self._registry.sync_session_runtime(session)
        return record.run_control

    def request_cancel(
        self,
        session: "MainAgentSessionState",
        *,
        source: str | None = None,
        reason: str | None = None,
        force_stop: bool = False,
    ) -> RunControlState:
        record = self._registry.request_cancel(
            session,
            source=source,
            reason=reason,
            force_stop=force_stop,
        )
        self._registry.sync_session_runtime(session)
        return record.run_control

    def request_resume(
        self,
        session: "MainAgentSessionState",
        *,
        source: str | None = None,
        resume_token: str | None = None,
    ) -> RunControlState:
        record = self._registry.request_resume(
            session,
            source=source,
            resume_token=resume_token,
        )
        self._registry.sync_session_runtime(session)
        return record.run_control

    def replace_active_approval_wait(
        self,
        session: "MainAgentSessionState",
        *,
        payload: dict[str, Any],
        future,
    ) -> ApprovalWait:
        record = self._registry.replace_active_approval_wait(
            session,
            payload=payload,
            future=future,
        )
        self._registry.sync_session_runtime(session)
        if record.approval_wait is None:
            raise RuntimeError("approval wait was not recorded")
        return record.approval_wait

    def resolve_active_approval_wait(
        self,
        session: "MainAgentSessionState",
        *,
        token: str | None,
        approved: bool,
    ):
        result = self._registry.resolve_active_approval_wait(
            session,
            token=token,
            approved=approved,
        )
        self._registry.sync_session_runtime(session)
        return result

    def clear_pending_approval(
        self,
        session: "MainAgentSessionState",
        *,
        token: str | None = None,
        invalidate_reason: str | None = None,
    ) -> None:
        self._registry.clear_pending_approval(
            session,
            token=token,
            invalidate_reason=invalidate_reason,
        )
        self._registry.sync_session_runtime(session)

    def reset_runtime_state(
        self,
        session: "MainAgentSessionState",
        *,
        reason: str,
    ) -> None:
        self._registry.reset_runtime_state(session, reason=reason)
        self._registry.sync_session_runtime(session)

    def build_active_run_projection(self, session: "MainAgentSessionState") -> dict[str, Any]:
        projection = self._registry.build_active_run_projection(session)
        self._registry.sync_session_runtime(session)
        return projection

    @classmethod
    def build_persisted_run_projection(cls, *, run_id: str, record: dict[str, Any]) -> dict[str, Any]:
        return RuntimeKernelStateRegistry.build_persisted_run_projection(run_id=run_id, record=record)

    def build_kernel_state_payload(self, session: "MainAgentSessionState") -> dict[str, Any] | None:
        return self._registry.build_kernel_state_payload(session)

    @staticmethod
    def serialize_run_control_state(state: RunControlState | None) -> dict[str, Any] | None:
        return RuntimeKernelStateRegistry.serialize_run_control_state(state)

    @staticmethod
    def serialize_approval_wait(wait: ApprovalWait | None) -> dict[str, Any] | None:
        return RuntimeKernelStateRegistry.serialize_approval_wait(wait)

    @staticmethod
    def deserialize_run_control_state(payload: Any) -> RunControlState | None:
        return RuntimeKernelStateRegistry.deserialize_run_control_state(payload)

    @staticmethod
    def deserialize_approval_wait(payload: Any) -> ApprovalWait | None:
        return RuntimeKernelStateRegistry.deserialize_approval_wait(payload)


__all__ = [
    "CANCEL_REQUESTED_RUNNING_STATE",
    "CANCEL_REQUESTED_STATUS",
    "CANCELLING_PHASE",
    "INTERRUPT_REQUESTED_RUNNING_STATE",
    "INTERRUPT_REQUESTED_STATUS",
    "INTERRUPTING_PHASE",
    "PAUSED_PHASE",
    "PAUSED_STATUS",
    "RESUME_REQUESTED_STATUS",
    "RESUMING_PHASE",
    "RunControlRuntimeBridge",
    "RuntimeSessionRunControlStore",
]
