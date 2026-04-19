"""Run-control store facade over the kernel-backed live-control registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from mini_agent.agent_core.contracts._kernel_state_bundle import AgentKernelStateRecord
from mini_agent.agent_core.contracts.approval_wait import ApprovalWait
from mini_agent.agent_core.contracts.run_control_state import RunControlState
from mini_agent.runtime.live_control.kernel_state_registry import (
    RuntimeKernelStateRegistry as _RuntimeKernelStateRegistry,
)
from mini_agent.runtime.live_control.run_control_constants import SESSION_BACKED_RUN_ID_PREFIX

if TYPE_CHECKING:
    from mini_agent.session.store_records import MainAgentSessionState


class RuntimeSessionRunControlStore:
    """Thin facade that delegates run truth mutations to the kernel-state registry owner."""

    def __init__(
        self,
        *,
        selected_model_identity_for_session: (
            Callable[["MainAgentSessionState"], tuple[str, str, str] | None] | None
        ) = None,
    ) -> None:
        self._registry = _RuntimeKernelStateRegistry(
            selected_model_identity_for_session=selected_model_identity_for_session,
        )

    @staticmethod
    def run_id_for_session(session_id: str) -> str:
        normalized = str(session_id or "").strip()
        if not normalized:
            raise ValueError("session_id is required")
        return f"{SESSION_BACKED_RUN_ID_PREFIX}{normalized}"

    @staticmethod
    def session_id_for_run_id(run_id: str) -> str | None:
        normalized = str(run_id or "").strip()
        if not normalized.startswith(SESSION_BACKED_RUN_ID_PREFIX):
            return None
        session_id = normalized[len(SESSION_BACKED_RUN_ID_PREFIX) :].strip()
        return session_id or None

    def clear(self) -> None:
        self._registry.clear()

    def drop_session(self, session_id: str) -> None:
        self._registry.drop_session(session_id)

    def current_control_state(self, session: "MainAgentSessionState") -> RunControlState:
        return self._registry.current_control_state(session)

    def current_record(self, session: "MainAgentSessionState") -> AgentKernelStateRecord:
        return self._registry.current_record(session)

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

    def build_kernel_state_payload(self, session: "MainAgentSessionState") -> dict[str, Any] | None:
        return self._registry.build_kernel_state_payload(session)

    def sync_session_runtime(self, session: "MainAgentSessionState") -> None:
        self._registry.sync_session_runtime(session)

    @staticmethod
    def serialize_run_control_state(state: RunControlState | None) -> dict[str, Any] | None:
        return _RuntimeKernelStateRegistry.serialize_run_control_state(state)

    @staticmethod
    def serialize_approval_wait(wait: ApprovalWait | None) -> dict[str, Any] | None:
        return _RuntimeKernelStateRegistry.serialize_approval_wait(wait)

    @staticmethod
    def deserialize_run_control_state(payload: Any) -> RunControlState | None:
        return _RuntimeKernelStateRegistry.deserialize_run_control_state(payload)

    @staticmethod
    def deserialize_approval_wait(payload: Any) -> ApprovalWait | None:
        return _RuntimeKernelStateRegistry.deserialize_approval_wait(payload)


__all__ = ["RuntimeSessionRunControlStore"]
