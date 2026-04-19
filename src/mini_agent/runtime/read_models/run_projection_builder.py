"""Run projection read-model ownership separated from run-control truth for v11.1."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mini_agent.agent_core.contracts._kernel_state_bundle import AgentKernelStateRecord
from mini_agent.agent_core.contracts.approval_wait import ApprovalWait
from mini_agent.agent_core.contracts.run import Run, RunPhase, RunStatus
from mini_agent.agent_core.contracts.run_control_state import RunControlMode, RunControlState, RunWaitKind
from mini_agent.runtime.live_control.run_control_constants import (
    CANCEL_REQUESTED_RUNNING_STATE,
    CANCEL_REQUESTED_STATUS,
    CANCELLING_PHASE,
    INTERRUPT_REQUESTED_RUNNING_STATE,
    INTERRUPT_REQUESTED_STATUS,
    INTERRUPTING_PHASE,
    PAUSED_STATUS,
    RESUME_REQUESTED_STATUS,
    RESUMING_PHASE,
)
from mini_agent.runtime.live_control.run_control_store import (
    RuntimeSessionRunControlStore,
)
from mini_agent.workspace_runtime.snapshot_store import (
    shared_workspace_snapshot_store,
    workspace_runtime_snapshot_payload,
)

if TYPE_CHECKING:
    from mini_agent.session.store_records import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _projection_text(session: "MainAgentSessionState", field: str) -> str:
    projection = getattr(session, "projection", None)
    return _safe_text(getattr(projection, field, ""))


def _projection_running_state(
    *,
    record: AgentKernelStateRecord,
    control_state: RunControlState | None,
    fallback: object,
) -> str | None:
    normalized_fallback = _safe_text(fallback) or _latest_running_detail(record)
    if control_state is not None:
        if control_state.control_mode is RunControlMode.CANCEL_REQUESTED:
            return CANCEL_REQUESTED_RUNNING_STATE
        if control_state.control_mode is RunControlMode.INTERRUPT_REQUESTED:
            return INTERRUPT_REQUESTED_RUNNING_STATE
        if control_state.control_mode is RunControlMode.RESUME_REQUESTED:
            return normalized_fallback or RESUME_REQUESTED_STATUS.replace("_", " ")
        if control_state.control_mode is RunControlMode.APPROVAL_WAIT:
            return record.run.waiting_reason or normalized_fallback
        if control_state.control_mode is RunControlMode.PAUSED:
            return record.run.waiting_reason or control_state.last_pause_reason or normalized_fallback
        if control_state.is_terminal:
            return record.run.terminal_reason or normalized_fallback
    if record.run.waiting_reason and record.run.status in {RunStatus.WAITING, RunStatus.PAUSED}:
        return record.run.waiting_reason
    if record.run.terminal_reason and record.run.is_terminal:
        return record.run.terminal_reason
    return normalized_fallback or None


def _persisted_projection_running_state(
    *,
    run_payload: dict[str, Any] | None,
    control_state: RunControlState | None,
    fallback: object,
) -> str | None:
    normalized_fallback = _safe_text(fallback) or None
    waiting_reason = _safe_text(run_payload.get("waiting_reason")) if isinstance(run_payload, dict) else None
    terminal_reason = _safe_text(run_payload.get("terminal_reason")) if isinstance(run_payload, dict) else None
    persisted_status = _safe_text(run_payload.get("status")).lower() if isinstance(run_payload, dict) else ""
    if control_state is not None:
        if control_state.control_mode is RunControlMode.CANCEL_REQUESTED:
            return CANCEL_REQUESTED_RUNNING_STATE
        if control_state.control_mode is RunControlMode.INTERRUPT_REQUESTED:
            return INTERRUPT_REQUESTED_RUNNING_STATE
        if control_state.control_mode is RunControlMode.RESUME_REQUESTED:
            return normalized_fallback or RESUME_REQUESTED_STATUS.replace("_", " ")
        if control_state.control_mode is RunControlMode.APPROVAL_WAIT:
            return waiting_reason or normalized_fallback
        if control_state.control_mode is RunControlMode.PAUSED:
            return waiting_reason or control_state.last_pause_reason or normalized_fallback
        if control_state.is_terminal:
            return terminal_reason or normalized_fallback
    if waiting_reason and persisted_status in {RunStatus.WAITING.value, RunStatus.PAUSED.value}:
        return waiting_reason
    if terminal_reason and persisted_status in {
        RunStatus.COMPLETED.value,
        RunStatus.CANCELLED.value,
        RunStatus.FAILED.value,
    }:
        return terminal_reason
    return normalized_fallback


def _projection_busy(
    *,
    run: Run | None,
    control_state: RunControlState | None,
    status: str | None = None,
) -> bool:
    if control_state is not None:
        if control_state.is_terminal or control_state.control_mode is RunControlMode.PAUSED:
            return False
        if control_state.control_mode in {
            RunControlMode.APPROVAL_WAIT,
            RunControlMode.INTERRUPT_REQUESTED,
            RunControlMode.RESUME_REQUESTED,
            RunControlMode.CANCEL_REQUESTED,
        }:
            return True
    if run is not None:
        return run.status in {RunStatus.RUNNING, RunStatus.WAITING}
    normalized_status = _safe_text(status).lower()
    return normalized_status in {
        RunStatus.RUNNING.value,
        RunStatus.WAITING.value,
        INTERRUPT_REQUESTED_STATUS,
        RESUME_REQUESTED_STATUS,
        CANCEL_REQUESTED_STATUS,
    }


def _latest_running_detail(record: AgentKernelStateRecord) -> str | None:
    latest_event = record.execution_journal.latest_event
    if latest_event is None:
        return None
    payload = latest_event.payload if isinstance(latest_event.payload, dict) else {}
    detail = _safe_text(payload.get("detail"))
    return detail or None


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
class RuntimeSessionRunProjectionBuilder:
    run_control_store: RuntimeSessionRunControlStore | None = None

    def build_active_run_projection(self, session: "MainAgentSessionState") -> dict[str, Any]:
        store = self._store()
        record = store.current_record(session)
        payloads = store.pending_approval_payloads(session)
        recovery_pending = bool(session.projection.recovery_context_pending)
        running_state = _projection_running_state(
            record=record,
            control_state=record.run_control,
            fallback=session.projection.running_state,
        )
        checkpoint = self._build_checkpoint_projection(
            record=record,
            workspace_runtime_payload=self._latest_workspace_runtime_snapshot_payload(session),
            source="live_workspace_runtime",
        )
        status, phase = self._resolve_status_phase(
            run=record.run,
            control_state=record.run_control,
            waiting_on_approval=bool(payloads),
            recovery_pending=recovery_pending,
            running_state=running_state,
        )
        projection = {
            "run_id": record.run_id,
            "session_id": session.session_id,
            "status": status,
            "phase": phase,
            "busy": _projection_busy(
                run=record.run,
                control_state=record.run_control,
                status=status,
            ),
            "waiting_on_approval": bool(payloads),
            "pending_approvals": payloads,
            "active_surface": _safe_text(record.run.trigger_source)
            or _projection_text(session, "active_surface")
            or _projection_text(session, "origin_surface")
            or None,
            "channel_type": session.projection.channel_type,
            "conversation_id": session.projection.conversation_id,
            "sender_id": session.projection.sender_id,
            "running_state": running_state,
            "control_mode": record.run_control.control_mode.value,
            "interrupt_requested": bool(record.run_control.interrupt_requested),
            "cancel_requested": bool(record.run_control.cancel_requested),
            "resumable": bool(record.run_control.resumable),
            "active_wait_id": record.run_control.active_wait_id,
            "approval_wait": store.serialize_approval_wait(record.approval_wait),
            "checkpoint": checkpoint,
        }
        store.sync_session_runtime(session)
        return projection

    @classmethod
    def build_persisted_run_projection(cls, *, run_id: str, record: dict[str, Any]) -> dict[str, Any]:
        kernel_state = record.get("kernel_state") if isinstance(record.get("kernel_state"), dict) else {}
        run_payload = kernel_state.get("run") if isinstance(kernel_state.get("run"), dict) else None
        control_state = RuntimeSessionRunControlStore.deserialize_run_control_state(
            kernel_state.get("run_control") if isinstance(kernel_state, dict) else record.get("run_control")
        )
        approval_wait = RuntimeSessionRunControlStore.deserialize_approval_wait(
            kernel_state.get("approval_wait") if isinstance(kernel_state, dict) else record.get("approval_wait")
        )
        pending_payload = cls._deserialize_pending_payload(record.get("pending_approvals"))
        checkpoint = cls._build_persisted_checkpoint_projection(
            kernel_state=kernel_state,
            workspace_runtime_payload=record.get("workspace_runtime_snapshot"),
            source="persisted_workspace_runtime",
        )
        if approval_wait is not None and approval_wait.is_pending and pending_payload is not None:
            pending_approvals = [pending_payload]
        else:
            pending_approvals = []
        recovery_pending = bool(record.get("recovery_context_pending")) or bool(record.get("recovery"))
        running_state = _persisted_projection_running_state(
            run_payload=run_payload,
            control_state=control_state,
            fallback=record.get("running_state"),
        )
        status, phase = cls._resolve_persisted_status_phase(
            run_payload=run_payload,
            control_state=control_state,
            waiting_on_approval=bool(pending_approvals),
            recovery_pending=recovery_pending,
            running_state=running_state,
        )
        return {
            "run_id": run_id,
            "session_id": _safe_text(record.get("session_id")) or "",
            "status": status,
            "phase": phase,
            "busy": _projection_busy(
                run=None,
                control_state=control_state,
                status=status,
            ),
            "waiting_on_approval": bool(pending_approvals),
            "pending_approvals": pending_approvals,
            "active_surface": _safe_text(run_payload.get("trigger_source"))
            if isinstance(run_payload, dict)
            else (_safe_text(record.get("active_surface")) or None),
            "channel_type": _safe_text(record.get("channel_type")) or None,
            "conversation_id": _safe_text(record.get("conversation_id")) or None,
            "sender_id": _safe_text(record.get("sender_id")) or None,
            "running_state": running_state,
            "control_mode": control_state.control_mode.value if control_state is not None else None,
            "interrupt_requested": bool(control_state.interrupt_requested) if control_state is not None else False,
            "cancel_requested": bool(control_state.cancel_requested) if control_state is not None else False,
            "resumable": bool(control_state.resumable) if control_state is not None else not recovery_pending,
            "active_wait_id": control_state.active_wait_id if control_state is not None else None,
            "approval_wait": RuntimeSessionRunControlStore.serialize_approval_wait(approval_wait),
            "checkpoint": checkpoint,
        }

    @staticmethod
    def _latest_workspace_runtime_snapshot_payload(session: "MainAgentSessionState") -> dict[str, Any] | None:
        workspace_dir = Path(getattr(session, "workspace_dir", ".")).resolve()
        latest = shared_workspace_snapshot_store(workspace_dir).latest(workspace_dir)
        return workspace_runtime_snapshot_payload(latest)

    @staticmethod
    def _deserialize_pending_payload(raw_items: Any) -> dict[str, Any] | None:
        if not isinstance(raw_items, list):
            return None
        for item in raw_items:
            normalized = _normalize_pending_approval_payload(item)
            if normalized is not None:
                return normalized
        return None

    @staticmethod
    def _build_checkpoint_projection(
        *,
        record: AgentKernelStateRecord,
        workspace_runtime_payload: dict[str, Any] | None,
        source: str,
    ) -> dict[str, Any] | None:
        runtime_projection = RuntimeSessionRunProjectionBuilder._build_workspace_runtime_checkpoint_projection(
            workspace_runtime_payload,
            source=source,
        )
        if runtime_projection is not None:
            return runtime_projection
        checkpoint = record.checkpoint
        if checkpoint is None:
            return None
        return {
            "checkpoint_id": checkpoint.checkpoint_id,
            "kind": "kernel_checkpoint",
            "source": "active_kernel_state",
            "created_at": checkpoint.created_at.isoformat() if checkpoint.created_at is not None else None,
            "workspace_dir": record.workspace_attachment.root_dir,
            "runtime_mode": record.workspace_attachment.runtime_backend.value,
            "access_scope": "workspace_only",
            "mutation_count": 0,
        }

    @staticmethod
    def _build_persisted_checkpoint_projection(
        *,
        kernel_state: dict[str, Any],
        workspace_runtime_payload: Any,
        source: str,
    ) -> dict[str, Any] | None:
        runtime_projection = RuntimeSessionRunProjectionBuilder._build_workspace_runtime_checkpoint_projection(
            workspace_runtime_payload,
            source=source,
        )
        if runtime_projection is not None:
            return runtime_projection
        checkpoint = kernel_state.get("checkpoint") if isinstance(kernel_state.get("checkpoint"), dict) else None
        workspace_attachment = (
            kernel_state.get("workspace_attachment")
            if isinstance(kernel_state.get("workspace_attachment"), dict)
            else None
        )
        if checkpoint is None:
            return None
        return {
            "checkpoint_id": _safe_text(checkpoint.get("checkpoint_id")) or None,
            "kind": "kernel_checkpoint",
            "source": "persisted_kernel_state",
            "created_at": _safe_text(checkpoint.get("created_at")) or None,
            "workspace_dir": _safe_text(workspace_attachment.get("root_dir")) if workspace_attachment else None,
            "runtime_mode": _safe_text(workspace_attachment.get("runtime_backend")) if workspace_attachment else None,
            "access_scope": "workspace_only",
            "mutation_count": 0,
        }

    @staticmethod
    def _build_workspace_runtime_checkpoint_projection(
        payload: Any,
        *,
        source: str,
    ) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        checkpoint_id = _safe_text(payload.get("snapshot_id"))
        if not checkpoint_id:
            return None
        try:
            mutation_count = max(0, int(payload.get("mutation_count") or 0))
        except Exception:
            mutation_count = 0
        return {
            "checkpoint_id": checkpoint_id,
            "kind": "workspace_runtime_snapshot",
            "source": _safe_text(source) or None,
            "created_at": _safe_text(payload.get("created_at")) or None,
            "workspace_dir": _safe_text(payload.get("workspace_dir")) or None,
            "runtime_mode": _safe_text(payload.get("mode")) or None,
            "access_scope": _safe_text(payload.get("scope")) or None,
            "mutation_count": mutation_count,
        }

    @staticmethod
    def _resolve_status_phase(
        *,
        run: Run,
        control_state: RunControlState | None,
        waiting_on_approval: bool,
        recovery_pending: bool,
        running_state: str | None,
    ) -> tuple[str, str]:
        normalized_running_state = _safe_text(running_state).lower()
        if control_state is not None:
            if control_state.is_terminal or run.is_terminal:
                return run.status.value, run.phase.value
            if control_state.control_mode is RunControlMode.CANCEL_REQUESTED:
                return CANCEL_REQUESTED_STATUS, CANCELLING_PHASE
            if control_state.control_mode is RunControlMode.INTERRUPT_REQUESTED:
                return INTERRUPT_REQUESTED_STATUS, INTERRUPTING_PHASE
            if control_state.control_mode is RunControlMode.RESUME_REQUESTED:
                return RESUME_REQUESTED_STATUS, RESUMING_PHASE
            if (
                control_state.control_mode is RunControlMode.APPROVAL_WAIT
                or control_state.active_wait_kind is RunWaitKind.APPROVAL
            ):
                return RunStatus.WAITING.value, RunPhase.AWAITING_APPROVAL.value
            if control_state.control_mode is RunControlMode.PAUSED:
                phase = run.phase.value if run.phase is not RunPhase.TERMINAL else RunPhase.PLANNING.value
                return PAUSED_STATUS, phase
        if normalized_running_state == CANCEL_REQUESTED_RUNNING_STATE:
            return CANCEL_REQUESTED_STATUS, CANCELLING_PHASE
        if normalized_running_state == INTERRUPT_REQUESTED_RUNNING_STATE:
            return INTERRUPT_REQUESTED_STATUS, INTERRUPTING_PHASE
        if waiting_on_approval or run.status is RunStatus.WAITING:
            return RunStatus.WAITING.value, RunPhase.AWAITING_APPROVAL.value
        if recovery_pending or run.status is RunStatus.PAUSED:
            phase = run.phase.value if run.phase is not RunPhase.TERMINAL else RunPhase.PLANNING.value
            return PAUSED_STATUS, phase
        return run.status.value, run.phase.value

    @staticmethod
    def _resolve_persisted_status_phase(
        *,
        run_payload: dict[str, Any] | None,
        control_state: RunControlState | None,
        waiting_on_approval: bool,
        recovery_pending: bool,
        running_state: str | None,
    ) -> tuple[str, str]:
        normalized_running_state = _safe_text(running_state).lower()
        if control_state is not None:
            if control_state.is_terminal and isinstance(run_payload, dict):
                status = _safe_text(run_payload.get("status")) or RunStatus.COMPLETED.value
                phase = _safe_text(run_payload.get("phase")) or RunPhase.TERMINAL.value
                return status, phase
            if control_state.control_mode is RunControlMode.CANCEL_REQUESTED:
                return CANCEL_REQUESTED_STATUS, CANCELLING_PHASE
            if control_state.control_mode is RunControlMode.INTERRUPT_REQUESTED:
                return INTERRUPT_REQUESTED_STATUS, INTERRUPTING_PHASE
            if control_state.control_mode is RunControlMode.RESUME_REQUESTED:
                return RESUME_REQUESTED_STATUS, RESUMING_PHASE
            if (
                control_state.control_mode is RunControlMode.APPROVAL_WAIT
                or control_state.active_wait_kind is RunWaitKind.APPROVAL
            ):
                return RunStatus.WAITING.value, RunPhase.AWAITING_APPROVAL.value
            if control_state.control_mode is RunControlMode.PAUSED:
                phase = _safe_text(run_payload.get("phase")) if isinstance(run_payload, dict) else None
                return PAUSED_STATUS, phase or RunPhase.PLANNING.value
        if normalized_running_state == CANCEL_REQUESTED_RUNNING_STATE:
            return CANCEL_REQUESTED_STATUS, CANCELLING_PHASE
        if normalized_running_state == INTERRUPT_REQUESTED_RUNNING_STATE:
            return INTERRUPT_REQUESTED_STATUS, INTERRUPTING_PHASE
        if waiting_on_approval:
            return RunStatus.WAITING.value, RunPhase.AWAITING_APPROVAL.value
        if recovery_pending:
            phase = _safe_text(run_payload.get("phase")) if isinstance(run_payload, dict) else None
            return PAUSED_STATUS, phase or RunPhase.PLANNING.value
        if isinstance(run_payload, dict):
            status = _safe_text(run_payload.get("status")) or RunStatus.COMPLETED.value
            phase = _safe_text(run_payload.get("phase")) or RunPhase.TERMINAL.value
            return status, phase
        return RunStatus.COMPLETED.value, RunPhase.TERMINAL.value

    def _store(self) -> RuntimeSessionRunControlStore:
        if self.run_control_store is None:
            self.run_control_store = RuntimeSessionRunControlStore()
        return self.run_control_store


__all__ = ["RuntimeSessionRunProjectionBuilder"]
