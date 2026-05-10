"""Run-owned control truth and kernel-backed runtime registry for v11.1 live control."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from mini_agent.agent_core.contracts._kernel_state_bundle import (
    AgentKernelStateRecord,
    AgentKernelStateSeed,
    build_agent_kernel_state_record,
    build_checkpoint_for_record,
    deserialize_agent_kernel_state_record,
    deserialize_approval_wait as deserialize_kernel_approval_wait,
    deserialize_run_control_state as deserialize_kernel_run_control_state,
    serialize_agent_kernel_state_record,
    serialize_approval_wait as serialize_kernel_approval_wait,
    serialize_run_control_state as serialize_kernel_run_control_state,
)
from mini_agent.agent_core.contracts.agent_instance import AgentInstanceLifecycleState
from mini_agent.agent_core.contracts.approval_wait import ApprovalDecision, ApprovalWait
from mini_agent.agent_core.contracts.checkpoint import Checkpoint, CheckpointType
from mini_agent.agent_core.contracts.run import Run, RunInterruptState, RunPhase, RunStatus
from mini_agent.agent_core.contracts.run_control_state import RunControlMode, RunControlState, RunWaitKind
from mini_agent.runtime.live_control.run_control_constants import (
    CANCEL_REQUESTED_RUNNING_STATE,
    INTERRUPT_REQUESTED_RUNNING_STATE,
    SESSION_BACKED_RUN_ID_PREFIX,
)

if TYPE_CHECKING:
    from mini_agent.session.store_records import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _projection_text(session: "MainAgentSessionState", field: str) -> str:
    projection = getattr(session, "projection", None)
    return _safe_text(getattr(projection, field, ""))


def _workspace_root_str(session: "MainAgentSessionState") -> str:
    return str(Path(getattr(session, "workspace_dir", ".")).resolve())


def _normalize_pending_approval_payload(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    token = _safe_text(item.get("token"))
    tool_name = _safe_text(item.get("tool_name")) or "tool"
    if not token:
        return None
    return {
        "token": token,
        "tool_name": tool_name,
        "arguments": dict(item.get("arguments")) if isinstance(item.get("arguments"), dict) else {},
        "kind": _safe_text(item.get("kind")) or None,
        "reason": _safe_text(item.get("reason")) or None,
        "cache_key": _safe_text(item.get("cache_key")) or None,
        "can_escalate": bool(item.get("can_escalate", False)),
        "step": max(0, int(item.get("step") or 0)),
    }


@dataclass(slots=True)
class RuntimeKernelControlBridge:
    """In-process bridge objects for one active kernel-backed run."""

    cancel_event: Any | None = None
    pending_approval_waiters: dict[str, asyncio.Future[bool | None]] = field(default_factory=dict)


class RuntimeKernelStateRegistry:
    """Runtime owner for active kernel truth and live-control bridge state."""

    def __init__(
        self,
        *,
        selected_model_identity_for_session: (
            Callable[["MainAgentSessionState"], tuple[str, str, str] | None] | None
        ) = None,
    ) -> None:
        self._records: dict[str, AgentKernelStateRecord] = {}
        self._bridges: dict[str, RuntimeKernelControlBridge] = {}
        self._selected_model_identity_for_session = selected_model_identity_for_session

    @staticmethod
    def run_id_for_session(session_id: str) -> str:
        normalized = str(session_id or "").strip()
        if not normalized:
            raise ValueError("session_id is required")
        return f"{SESSION_BACKED_RUN_ID_PREFIX}{normalized}"

    def clear(self) -> None:
        self._records.clear()
        self._bridges.clear()

    def drop_session(self, session_id: str) -> None:
        run_id = self.run_id_for_session(session_id)
        self._records.pop(run_id, None)
        self._bridges.pop(run_id, None)

    def current_record(self, session: "MainAgentSessionState") -> AgentKernelStateRecord:
        return self._materialize_session_record(session)

    def current_control_state(self, session: "MainAgentSessionState") -> RunControlState:
        return self.current_record(session).run_control

    def current_control_state_for_run_id(self, run_id: str) -> RunControlState | None:
        record = self._records.get(run_id)
        return record.run_control if record is not None else None

    def current_approval_wait(self, session: "MainAgentSessionState") -> ApprovalWait | None:
        return self.current_record(session).approval_wait

    def pending_approval_payloads(self, session: "MainAgentSessionState") -> list[dict[str, Any]]:
        record = self.current_record(session)
        if record.approval_wait is None or not record.approval_wait.is_pending or record.approval_payload is None:
            return []
        return [dict(record.approval_payload)]

    def pending_approval_payloads_for_run_id(self, run_id: str) -> list[dict[str, Any]]:
        record = self._records.get(run_id)
        if record is None or record.approval_wait is None or not record.approval_wait.is_pending:
            return []
        return [dict(record.approval_payload or {})] if record.approval_payload is not None else []

    def pending_approval_waiter(
        self,
        session: "MainAgentSessionState",
        *,
        token: str | None,
    ) -> asyncio.Future[bool | None] | None:
        normalized_token = _safe_text(token)
        if not normalized_token:
            return None
        bridge = self._adopt_runtime_bridge(session)
        return bridge.pending_approval_waiters.get(normalized_token)

    def cancel_event(self, session: "MainAgentSessionState") -> asyncio.Event | None:
        """Return the cancel_event from the run-owned control bridge."""
        bridge = self._adopt_runtime_bridge(session)
        return bridge.cancel_event

    def begin_turn(
        self,
        session: "MainAgentSessionState",
        *,
        surface: str | None = None,
        detail: str | None = None,
    ) -> AgentKernelStateRecord:
        run_id = self.run_id_for_session(session.session_id)
        record = self._build_live_record(
            session,
            run_id=run_id,
            initial_status=RunStatus.RUNNING,
            initial_phase=RunPhase.PLANNING,
            trigger_source=surface or _projection_text(session, "active_surface") or _projection_text(session, "origin_surface") or "api",
            waiting_reason=None,
        )
        record.execution_journal = record.execution_journal.append(
            event_type="run.turn_started",
            status=record.run.status,
            phase=record.run.phase,
            step_index=record.run.step_index,
            payload={
                "surface": _safe_text(surface) or None,
                "detail": _safe_text(detail) or None,
            },
        )
        record.agent_instance = replace(
            record.agent_instance,
            journal_head_seq=record.execution_journal.last_event_seq,
        )
        self._records[run_id] = record
        self._bridges[run_id] = RuntimeKernelControlBridge(cancel_event=asyncio.Event())
        return record

    def finish_turn(self, session: "MainAgentSessionState") -> AgentKernelStateRecord:
        record = self.current_record(session)
        if record.approval_wait is not None and record.approval_wait.is_pending:
            record.approval_wait = record.approval_wait.invalidate("turn finished before approval resolved")
        record.approval_payload = None
        terminal_status = RunStatus.CANCELLED if record.run_control.cancel_requested else RunStatus.COMPLETED
        terminal_reason = record.run_control.last_cancel_reason if terminal_status is RunStatus.CANCELLED else None
        record.run = record.run.transition(
            status=terminal_status,
            phase=RunPhase.TERMINAL,
            terminal_reason=terminal_reason,
        )
        record.run_control = record.run_control.clear_wait().mark_terminal()
        record.checkpoint = self._create_checkpoint(
            session,
            record,
            checkpoint_type=CheckpointType.TERMINAL,
            waiting_reason=None,
            resume_token=None,
        )
        record.execution_journal = record.execution_journal.append(
            event_type="run.finished",
            status=record.run.status,
            phase=record.run.phase,
            step_index=record.run.step_index,
            payload={"terminal_reason": record.run.terminal_reason},
        ).close()
        record.agent_instance = (
            record.agent_instance.record_checkpoint(
                record.checkpoint.checkpoint_id,
                journal_head_seq=record.execution_journal.last_event_seq,
            )
            .clear_active_run()
        )
        bridge = self._adopt_runtime_bridge(session)
        self._resolve_all_waiters(bridge, result=None)
        bridge.cancel_event = None
        return record

    def pause_turn(
        self,
        session: "MainAgentSessionState",
        *,
        reason: str | None = None,
    ) -> AgentKernelStateRecord:
        record = self.current_record(session)
        if record.approval_wait is not None and record.approval_wait.is_pending:
            record.approval_wait = record.approval_wait.invalidate(
                reason or "interrupt acknowledged before approval resolution"
            )
        record.approval_payload = None
        paused_phase = record.run.phase if record.run.phase in {RunPhase.PLANNING, RunPhase.EXECUTING_TOOLS} else RunPhase.PLANNING
        record.run = record.run.transition(
            status=RunStatus.PAUSED,
            phase=paused_phase,
            waiting_reason=None,
            interrupt_state=RunInterruptState.ACKNOWLEDGED,
        )
        record.run_control = record.run_control.clear_wait().pause(reason=reason)
        record.checkpoint = self._create_checkpoint(
            session,
            record,
            checkpoint_type=CheckpointType.WAITING,
            waiting_reason=reason or record.run_control.last_pause_reason,
            resume_token=record.run_control.last_resume_token,
        )
        record.execution_journal = record.execution_journal.append(
            event_type="control.interrupt_acknowledged",
            status=record.run.status,
            phase=record.run.phase,
            step_index=record.run.step_index,
            payload={"reason": _safe_text(reason) or None},
        )
        record.agent_instance = (
            record.agent_instance.record_checkpoint(
                record.checkpoint.checkpoint_id,
                journal_head_seq=record.execution_journal.last_event_seq,
            )
            .mark_paused(wait_id=record.run_control.active_wait_id)
        )
        bridge = self._adopt_runtime_bridge(session)
        self._resolve_all_waiters(bridge, result=None)
        bridge.cancel_event = None
        return record

    def request_interrupt(
        self,
        session: "MainAgentSessionState",
        *,
        source: str | None = None,
        reason: str | None = None,
    ) -> AgentKernelStateRecord:
        record = self.current_record(session)
        record.run_control = record.run_control.request_interrupt(source=source, reason=reason)
        record.run = replace(record.run, interrupt_state=RunInterruptState.REQUESTED)
        record.agent_instance = record.agent_instance.request_interrupt()
        record.execution_journal = record.execution_journal.append(
            event_type="control.interrupt_requested",
            status=record.run.status,
            phase=record.run.phase,
            step_index=record.run.step_index,
            payload={"source": _safe_text(source) or None, "reason": _safe_text(reason) or None},
        )
        record.agent_instance = replace(
            record.agent_instance,
            journal_head_seq=record.execution_journal.last_event_seq,
        )
        bridge = self._adopt_runtime_bridge(session)
        self._signal_cancel_event(bridge.cancel_event)
        return record

    def request_cancel(
        self,
        session: "MainAgentSessionState",
        *,
        source: str | None = None,
        reason: str | None = None,
        force_stop: bool = False,
    ) -> AgentKernelStateRecord:
        record = self.current_record(session)
        record.run_control = record.run_control.request_cancel(
            source=source,
            reason=reason,
            force_stop=force_stop,
        )
        record.agent_instance = record.agent_instance.request_cancel()
        record.execution_journal = record.execution_journal.append(
            event_type="control.cancel_requested",
            status=record.run.status,
            phase=record.run.phase,
            step_index=record.run.step_index,
            payload={
                "source": _safe_text(source) or None,
                "reason": _safe_text(reason) or None,
                "force_stop": bool(force_stop),
            },
        )
        record.agent_instance = replace(
            record.agent_instance,
            journal_head_seq=record.execution_journal.last_event_seq,
        )
        bridge = self._adopt_runtime_bridge(session)
        self._signal_cancel_event(bridge.cancel_event)
        self._resolve_all_waiters(bridge, result=None)
        return record

    def request_resume(
        self,
        session: "MainAgentSessionState",
        *,
        source: str | None = None,
        resume_token: str | None = None,
    ) -> AgentKernelStateRecord:
        record = self.current_record(session)
        record.run_control = record.run_control.clear_wait().request_resume(
            source=source,
            resume_token=resume_token,
        )
        record.run = replace(record.run, interrupt_state=RunInterruptState.RESUMING)
        record.agent_instance = record.agent_instance.transition_lifecycle(
            AgentInstanceLifecycleState.RUNNING
        )
        record.execution_journal = record.execution_journal.append(
            event_type="control.resume_requested",
            status=record.run.status,
            phase=record.run.phase,
            step_index=record.run.step_index,
            payload={"source": _safe_text(source) or None, "resume_token": _safe_text(resume_token) or None},
        )
        record.agent_instance = replace(
            record.agent_instance,
            journal_head_seq=record.execution_journal.last_event_seq,
        )
        return record

    def replace_active_approval_wait(
        self,
        session: "MainAgentSessionState",
        *,
        payload: dict[str, Any],
        future: asyncio.Future[bool | None],
    ) -> AgentKernelStateRecord:
        record = self.current_record(session)
        bridge = self._adopt_runtime_bridge(session)
        normalized = _normalize_pending_approval_payload(payload)
        if normalized is None:
            raise ValueError("Invalid pending approval payload.")

        existing = record.approval_wait
        existing_token = _safe_text(existing.approval_token) if existing is not None else ""
        token = normalized["token"]
        if existing is not None and existing.is_pending and existing_token and existing_token != token:
            waiter = bridge.pending_approval_waiters.get(existing_token)
            if waiter is not None and not waiter.done():
                waiter.set_result(None)
            record.approval_wait = existing.invalidate("superseded by a newer approval wait")

        wait_id = (
            existing.wait_id
            if existing is not None and existing_token == token
            else f"{record.run_id}:approval:{token}"
        )
        record.approval_wait = ApprovalWait(
            wait_id=wait_id,
            run_id=record.run_id,
            session_id=session.session_id,
            workspace_id=record.workspace_attachment.workspace_id,
            approval_token=token,
            tool_name=normalized["tool_name"],
            tool_arguments_summary=dict(normalized["arguments"]),
            approval_kind=normalized["kind"],
            policy_reason=normalized["reason"],
            cache_key=normalized["cache_key"],
            can_escalate=bool(normalized["can_escalate"]),
        )
        record.approval_payload = dict(normalized)
        record.run_control = record.run_control.enter_approval_wait(
            record.approval_wait.wait_id,
            approval_token=token,
        )
        record.run = record.run.transition(
            status=RunStatus.WAITING,
            phase=RunPhase.AWAITING_APPROVAL,
            waiting_reason=normalized["reason"] or f"approval required for {normalized['tool_name']}",
        )
        record.agent_instance = record.agent_instance.mark_waiting(
            wait_kind=RunWaitKind.APPROVAL,
            wait_id=record.approval_wait.wait_id,
        )
        record.checkpoint = self._create_checkpoint(
            session,
            record,
            checkpoint_type=CheckpointType.WAITING,
            waiting_reason=record.run.waiting_reason,
            resume_token=token,
        )
        record.execution_journal = record.execution_journal.append(
            event_type="control.approval_wait_started",
            status=record.run.status,
            phase=record.run.phase,
            step_index=record.run.step_index,
            payload=dict(normalized),
        )
        record.agent_instance = record.agent_instance.record_checkpoint(
            record.checkpoint.checkpoint_id,
            journal_head_seq=record.execution_journal.last_event_seq,
        )
        bridge.pending_approval_waiters = {token: future}
        return record

    def resolve_active_approval_wait(
        self,
        session: "MainAgentSessionState",
        *,
        token: str | None,
        approved: bool,
    ) -> tuple[ApprovalWait | None, asyncio.Future[bool | None] | None]:
        record = self.current_record(session)
        approval_wait = record.approval_wait
        if approval_wait is None:
            return None, None
        target_token = _safe_text(token) or _safe_text(approval_wait.approval_token)
        wait_token = _safe_text(approval_wait.approval_token)
        if not target_token or target_token != wait_token or not approval_wait.is_pending:
            return approval_wait, None
        record.approval_wait = approval_wait.resolve(approved=approved)
        record.approval_payload = None
        record.run_control = record.run_control.clear_wait()
        record.run = record.run.transition(
            status=RunStatus.RUNNING,
            phase=RunPhase.EXECUTING_TOOLS if approved else RunPhase.WRITING_REPLY,
            waiting_reason=None,
            interrupt_state=(
                RunInterruptState.RESUMING
                if record.run_control.control_mode is RunControlMode.RESUME_REQUESTED
                else RunInterruptState.NONE
            ),
        )
        record.agent_instance = record.agent_instance.transition_lifecycle(
            AgentInstanceLifecycleState.RUNNING
        )
        record.execution_journal = record.execution_journal.append(
            event_type="control.approval_wait_resolved",
            status=record.run.status,
            phase=record.run.phase,
            step_index=record.run.step_index,
            payload={
                "token": wait_token,
                "approved": bool(approved),
                "decision": ApprovalDecision.APPROVED.value if approved else ApprovalDecision.DENIED.value,
            },
        )
        record.agent_instance = replace(
            record.agent_instance,
            journal_head_seq=record.execution_journal.last_event_seq,
        )
        bridge = self._adopt_runtime_bridge(session)
        waiter = bridge.pending_approval_waiters.pop(wait_token, None)
        return record.approval_wait, waiter

    def clear_pending_approval(
        self,
        session: "MainAgentSessionState",
        *,
        token: str | None = None,
        invalidate_reason: str | None = None,
    ) -> None:
        record = self.current_record(session)
        bridge = self._adopt_runtime_bridge(session)
        normalized_token = _safe_text(token)
        approval_wait = record.approval_wait
        wait_token = _safe_text(approval_wait.approval_token) if approval_wait is not None else ""
        if approval_wait is not None and (not normalized_token or wait_token == normalized_token):
            if approval_wait.is_pending:
                record.approval_wait = approval_wait.invalidate(
                    invalidate_reason or "approval wait cleared from session runtime state"
                )
                record.run_control = record.run_control.clear_wait()
                record.run = record.run.transition(
                    status=RunStatus.RUNNING,
                    phase=RunPhase.PLANNING,
                    waiting_reason=None,
                )
            record.approval_payload = None
        if normalized_token:
            bridge.pending_approval_waiters.pop(normalized_token, None)
        else:
            bridge.pending_approval_waiters.clear()

    def reset_runtime_state(
        self,
        session: "MainAgentSessionState",
        *,
        reason: str,
    ) -> None:
        record = self.current_record(session)
        approval_wait = record.approval_wait
        if approval_wait is not None and approval_wait.is_pending:
            record.approval_wait = approval_wait.invalidate(reason)
        record.approval_payload = None
        record.run_control = record.run_control.clear_wait().mark_terminal()
        record.run = record.run.transition(
            status=RunStatus.FAILED,
            phase=RunPhase.TERMINAL,
            terminal_reason=reason,
        )
        record.checkpoint = self._create_checkpoint(
            session,
            record,
            checkpoint_type=CheckpointType.TERMINAL,
            waiting_reason=None,
            resume_token=None,
        )
        record.execution_journal = record.execution_journal.append(
            event_type="run.runtime_reset",
            status=record.run.status,
            phase=record.run.phase,
            step_index=record.run.step_index,
            payload={"reason": _safe_text(reason) or None},
        ).close()
        record.agent_instance = (
            record.agent_instance.record_checkpoint(
                record.checkpoint.checkpoint_id,
                journal_head_seq=record.execution_journal.last_event_seq,
            )
            .clear_active_run()
        )
        bridge = self._adopt_runtime_bridge(session)
        self._resolve_all_waiters(bridge, result=None)
        bridge.cancel_event = None

    def build_kernel_state_payload(self, session: "MainAgentSessionState") -> dict[str, Any] | None:
        return serialize_agent_kernel_state_record(self.current_record(session))

    @staticmethod
    def serialize_run_control_state(state: RunControlState | None) -> dict[str, Any] | None:
        return serialize_kernel_run_control_state(state)

    @staticmethod
    def serialize_approval_wait(wait: ApprovalWait | None) -> dict[str, Any] | None:
        return serialize_kernel_approval_wait(wait)

    @staticmethod
    def deserialize_run_control_state(payload: Any) -> RunControlState | None:
        return deserialize_kernel_run_control_state(payload)

    @staticmethod
    def deserialize_approval_wait(payload: Any) -> ApprovalWait | None:
        return deserialize_kernel_approval_wait(payload)

    @staticmethod
    def _deserialize_pending_payload(raw_items: Any) -> dict[str, Any] | None:
        if not isinstance(raw_items, list):
            return None
        for item in raw_items:
            normalized = _normalize_pending_approval_payload(item)
            if normalized is not None:
                return normalized
        return None

    def _materialize_session_record(self, session: "MainAgentSessionState") -> AgentKernelStateRecord:
        run_id = self.run_id_for_session(session.session_id)
        record = self._records.get(run_id)
        if record is None:
            record = self._restore_record_for_session(session, run_id=run_id)
            self._records[run_id] = record

        runtime_pending_payload = self._deserialize_pending_payload(getattr(session.runtime, "pending_approvals", None))
        if runtime_pending_payload is not None:
            existing_wait = record.approval_wait
            same_token = (
                existing_wait is not None
                and _safe_text(existing_wait.approval_token) == runtime_pending_payload["token"]
            )
            if existing_wait is None or (existing_wait.is_pending and not same_token):
                record.approval_wait = ApprovalWait(
                    wait_id=f"{run_id}:approval:{runtime_pending_payload['token']}",
                    run_id=run_id,
                    session_id=session.session_id,
                    workspace_id=record.workspace_attachment.workspace_id,
                    approval_token=runtime_pending_payload["token"],
                    tool_name=runtime_pending_payload["tool_name"],
                    tool_arguments_summary=dict(runtime_pending_payload["arguments"]),
                    approval_kind=runtime_pending_payload["kind"],
                    policy_reason=runtime_pending_payload["reason"],
                    cache_key=runtime_pending_payload["cache_key"],
                    can_escalate=bool(runtime_pending_payload["can_escalate"]),
                )
            record.approval_payload = dict(runtime_pending_payload)
            if record.run_control.active_wait_id is None or not record.run_control.is_waiting:
                record.run_control = record.run_control.enter_approval_wait(
                    record.approval_wait.wait_id,
                    approval_token=runtime_pending_payload["token"],
                )
            record.run = record.run.transition(
                status=RunStatus.WAITING,
                phase=RunPhase.AWAITING_APPROVAL,
                waiting_reason=runtime_pending_payload["reason"]
                or f"approval required for {runtime_pending_payload['tool_name']}",
            )
            record.agent_instance = record.agent_instance.mark_waiting(
                wait_kind=RunWaitKind.APPROVAL,
                wait_id=record.approval_wait.wait_id,
            )
        elif record.approval_wait is not None and record.approval_wait.is_pending and record.approval_payload is None:
            record.approval_payload = self._approval_wait_payload(record.approval_wait)

        return record

    def _adopt_runtime_bridge(self, session: "MainAgentSessionState") -> RuntimeKernelControlBridge:
        run_id = self.run_id_for_session(session.session_id)
        bridge = self._bridges.get(run_id)
        if bridge is None:
            bridge = RuntimeKernelControlBridge()
            self._bridges[run_id] = bridge
        carried_cancel_event = getattr(session.runtime, "cancel_event", None)
        if carried_cancel_event is not None and bridge.cancel_event is None:
            bridge.cancel_event = carried_cancel_event
        carried_waiters = getattr(session.runtime, "pending_approval_waiters", None)
        if isinstance(carried_waiters, dict) and carried_waiters and not bridge.pending_approval_waiters:
            bridge.pending_approval_waiters = dict(carried_waiters)
        return bridge

    def sync_session_runtime(self, session: "MainAgentSessionState") -> None:
        run_id = self.run_id_for_session(session.session_id)
        record = self.current_record(session) if run_id not in self._records else self._records.get(run_id)
        bridge = self._bridges.get(run_id)
        session.runtime.cancel_event = bridge.cancel_event if bridge is not None else None
        session.runtime.pending_approval_waiters = (
            bridge.pending_approval_waiters if bridge is not None else {}
        )
        session.runtime.pending_approvals = (
            [dict(record.approval_payload)]
            if record is not None
            and record.approval_wait is not None
            and record.approval_wait.is_pending
            and record.approval_payload is not None
            else []
        )
        session.runtime.kernel_state_payload = (
            serialize_agent_kernel_state_record(record) if record is not None else None
        )

    def _restore_record_for_session(
        self,
        session: "MainAgentSessionState",
        *,
        run_id: str,
    ) -> AgentKernelStateRecord:
        restored = deserialize_agent_kernel_state_record(
            getattr(session.runtime, "kernel_state_payload", None)
        )
        if restored is not None:
            self._normalize_restored_recovery_record(session, restored)
            return restored
        return self._build_record_from_session_state(session, run_id=run_id)

    def _build_record_from_session_state(
        self,
        session: "MainAgentSessionState",
        *,
        run_id: str,
    ) -> AgentKernelStateRecord:
        pending_payload = self._deserialize_pending_payload(getattr(session.runtime, "pending_approvals", None))
        running_state = _safe_text(getattr(session.projection, "running_state", "")).lower()
        recovery_pending = bool(getattr(session.projection, "recovery_context_pending", False))
        if pending_payload is not None:
            initial_status = RunStatus.WAITING
            initial_phase = RunPhase.AWAITING_APPROVAL
            waiting_reason = pending_payload["reason"] or f"approval required for {pending_payload['tool_name']}"
        elif recovery_pending:
            initial_status = RunStatus.PAUSED
            initial_phase = RunPhase.PLANNING
            waiting_reason = _safe_text(getattr(session.projection, "recovery_summary", "")) or None
        elif bool(getattr(session.projection, "busy", False)):
            initial_status = RunStatus.RUNNING
            initial_phase = RunPhase.EXECUTING_TOOLS
            waiting_reason = None
        else:
            initial_status = RunStatus.COMPLETED
            initial_phase = RunPhase.TERMINAL
            waiting_reason = None
        record = self._build_live_record(
            session,
            run_id=run_id,
            initial_status=initial_status,
            initial_phase=initial_phase,
            trigger_source=_projection_text(session, "active_surface") or _projection_text(session, "origin_surface") or "api",
            waiting_reason=waiting_reason,
        )
        if running_state == INTERRUPT_REQUESTED_RUNNING_STATE:
            record.run_control = record.run_control.request_interrupt(reason=INTERRUPT_REQUESTED_RUNNING_STATE)
            record.run = replace(record.run, interrupt_state=RunInterruptState.REQUESTED)
            record.agent_instance = record.agent_instance.request_interrupt()
        if running_state == CANCEL_REQUESTED_RUNNING_STATE:
            record.run_control = record.run_control.request_cancel(reason=CANCEL_REQUESTED_RUNNING_STATE)
            record.agent_instance = record.agent_instance.request_cancel()
        if initial_status is RunStatus.PAUSED:
            record.agent_instance = record.agent_instance.mark_paused()
        elif initial_status is RunStatus.COMPLETED:
            record.agent_instance = record.agent_instance.clear_active_run()
        return record

    def _build_live_record(
        self,
        session: "MainAgentSessionState",
        *,
        run_id: str,
        initial_status: RunStatus,
        initial_phase: RunPhase,
        trigger_source: str,
        waiting_reason: str | None,
    ) -> AgentKernelStateRecord:
        seed = self._build_record_seed(
            session,
            run_id=run_id,
            initial_status=initial_status,
            initial_phase=initial_phase,
            trigger_source=trigger_source,
            waiting_reason=waiting_reason,
        )
        return build_agent_kernel_state_record(seed)

    def _build_record_seed(
        self,
        session: "MainAgentSessionState",
        *,
        run_id: str,
        initial_status: RunStatus,
        initial_phase: RunPhase,
        trigger_source: str,
        waiting_reason: str | None,
    ) -> AgentKernelStateSeed:
        agent = getattr(session.runtime, "agent", None)
        tools = getattr(agent, "tools", None)
        tool_names = tuple(sorted(str(name).strip() for name in tools.keys())) if isinstance(tools, dict) else ()
        capability_hints: list[str] = []
        if getattr(agent, "tool_approval_handler", None) is not None:
            capability_hints.append("approval")
        if bool(getattr(session.projection, "knowledge_base_enabled", False)):
            capability_hints.append("memory")

        source = provider_id = model_id = None
        if callable(self._selected_model_identity_for_session):
            try:
                identity = self._selected_model_identity_for_session(session)
            except Exception:
                identity = None
            if isinstance(identity, tuple) and len(identity) == 3:
                source, provider_id, model_id = identity
        resolved_provider_id = provider_id or source
        if resolved_provider_id is None:
            resolved_provider_id = _safe_text(getattr(session.projection, "selected_provider_id", None)) or None
        if model_id is None:
            model_id = _safe_text(getattr(session.projection, "selected_model_id", None)) or None

        approval_profile = None
        runtime_policy_engine = getattr(agent, "runtime_policy_engine", None)
        policy = getattr(runtime_policy_engine, "policy", None)
        policy_profile = _safe_text(getattr(policy, "approval_profile", None)) or None
        if policy_profile:
            approval_profile = {"default_scope": policy_profile}
        context_policy = getattr(session.projection, "context_policy", None)
        workspace_root = _workspace_root_str(session)
        return AgentKernelStateSeed(
            run_id=run_id,
            session_id=session.session_id,
            workspace_id=workspace_root,
            workspace_root=workspace_root,
            trigger_source=_safe_text(trigger_source) or "api",
            initial_status=initial_status,
            initial_phase=initial_phase,
            waiting_reason=waiting_reason,
            built_in_tool_names=tool_names,
            built_in_internal_skill_names=(),
            capability_hints=tuple(capability_hints),
            visible_skill_names=(),
            visible_memory_scopes=("session", "workspace", "global"),
            enabled_external_capabilities=(),
            agent_model_provider_id=resolved_provider_id,
            agent_model_id=model_id,
            approval_profile=approval_profile,
            context_policy=dict(context_policy) if isinstance(context_policy, dict) else {},
            recovery_context_pending=bool(
                getattr(session.projection, "recovery_context_pending", False)
            ),
        )

    def _create_checkpoint(
        self,
        session: "MainAgentSessionState",
        record: AgentKernelStateRecord,
        *,
        checkpoint_type: CheckpointType,
        waiting_reason: str | None,
        resume_token: str | None,
    ) -> Checkpoint:
        record.run, checkpoint = build_checkpoint_for_record(
            record,
            checkpoint_type=checkpoint_type,
            waiting_reason=waiting_reason,
            resume_token=resume_token,
        )
        return checkpoint

    def _normalize_restored_recovery_record(
        self,
        session: "MainAgentSessionState",
        record: AgentKernelStateRecord,
    ) -> None:
        approval_wait = record.approval_wait
        if approval_wait is None or not approval_wait.is_pending:
            return
        if not bool(getattr(session.projection, "recovery_context_pending", False)):
            return
        bridge = self._adopt_runtime_bridge(session)
        approval_token = _safe_text(approval_wait.approval_token)
        if approval_token and approval_token in bridge.pending_approval_waiters:
            return
        recovery_summary = (
            _safe_text(getattr(session.projection, "recovery_summary", ""))
            or "approval wait became recovery-only after restart"
        )
        record.approval_wait = approval_wait.invalidate(
            "approval wait could not be resumed after restart"
        )
        record.approval_payload = None
        record.run_control = record.run_control.clear_wait().pause(
            reason=recovery_summary,
            resumable=False,
        )
        record.run = record.run.transition(
            status=RunStatus.PAUSED,
            phase=RunPhase.PLANNING,
            waiting_reason=recovery_summary,
            interrupt_state=RunInterruptState.ACKNOWLEDGED,
        )
        record.agent_instance = replace(
            record.agent_instance,
            lifecycle_state=AgentInstanceLifecycleState.PAUSED,
            pending_wait_kind=RunWaitKind.NONE,
            pending_wait_id=None,
        )

    @staticmethod
    def _signal_cancel_event(cancel_event: Any | None) -> None:
        if cancel_event is None:
            return
        is_set = getattr(cancel_event, "is_set", None)
        already_set = bool(is_set()) if callable(is_set) else False
        if already_set:
            return
        setter = getattr(cancel_event, "set", None)
        if callable(setter):
            setter()

    @staticmethod
    def _resolve_all_waiters(
        bridge: RuntimeKernelControlBridge,
        *,
        result: bool | None,
    ) -> None:
        for future in list(bridge.pending_approval_waiters.values()):
            if not future.done():
                future.set_result(result)
        bridge.pending_approval_waiters.clear()

    @staticmethod
    def _approval_wait_payload(wait: ApprovalWait) -> dict[str, Any]:
        return {
            "token": _safe_text(wait.approval_token),
            "tool_name": wait.tool_name,
            "arguments": dict(wait.tool_arguments_summary),
            "kind": wait.approval_kind,
            "reason": wait.policy_reason,
            "cache_key": wait.cache_key,
            "can_escalate": bool(wait.can_escalate),
            "step": 0,
        }

__all__ = [
    "RuntimeKernelControlBridge",
    "RuntimeKernelStateRegistry",
]



