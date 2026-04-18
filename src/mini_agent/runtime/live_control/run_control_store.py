"""Run-owned control truth for transitional session-backed runs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from mini_agent.agent_core.contracts import (
    ApprovalDecision,
    ApprovalWait,
    ApprovalWaitState,
    RunControlMode,
    RunControlState,
    RunWaitKind,
)
from mini_agent.runtime.support.session_backed_run_id import build_session_backed_run_id

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


INTERRUPT_REQUESTED_RUNNING_STATE = "interrupt requested"
INTERRUPT_REQUESTED_STATUS = "interrupt_requested"
INTERRUPTING_PHASE = "interrupting"
RESUME_REQUESTED_STATUS = "resume_requested"
RESUMING_PHASE = "resuming"
PAUSED_STATUS = "paused"
PAUSED_PHASE = "paused"
CANCEL_REQUESTED_RUNNING_STATE = "cancellation requested"
CANCEL_REQUESTED_STATUS = "cancel_requested"
CANCELLING_PHASE = "cancelling"


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = _safe_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


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
class RunControlRuntimeBridge:
    """In-process bridge objects for one active run."""

    cancel_event: Any | None = None
    pending_approval_waiters: dict[str, asyncio.Future[bool | None]] = field(default_factory=dict)


@dataclass(slots=True)
class SessionBackedRunControlRecord:
    """Durable control truth plus compatibility payload for one session-backed run."""

    run_id: str
    session_id: str
    control_state: RunControlState
    approval_wait: ApprovalWait | None = None
    approval_payload: dict[str, Any] | None = None


class RuntimeSessionRunControlStore:
    """Own run control state while mirroring compatibility data into session runtime state."""

    def __init__(self) -> None:
        self._records: dict[str, SessionBackedRunControlRecord] = {}
        self._bridges: dict[str, RunControlRuntimeBridge] = {}

    @staticmethod
    def run_id_for_session(session_id: str) -> str:
        return build_session_backed_run_id(session_id)

    def clear(self) -> None:
        self._records.clear()
        self._bridges.clear()

    def drop_session(self, session_id: str) -> None:
        run_id = self.run_id_for_session(session_id)
        self._records.pop(run_id, None)
        self._bridges.pop(run_id, None)

    def current_control_state(self, session: "MainAgentSessionState") -> RunControlState:
        record = self._adopt_session_compat_state(session)
        return record.control_state

    def current_control_state_for_run_id(self, run_id: str) -> RunControlState | None:
        record = self._records.get(run_id)
        return record.control_state if record is not None else None

    def current_approval_wait(self, session: "MainAgentSessionState") -> ApprovalWait | None:
        return self._adopt_session_compat_state(session).approval_wait

    def pending_approval_payloads(self, session: "MainAgentSessionState") -> list[dict[str, Any]]:
        record = self._adopt_session_compat_state(session)
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

    def begin_turn(self, session: "MainAgentSessionState") -> RunControlState:
        run_id = self.run_id_for_session(session.session_id)
        self._records[run_id] = SessionBackedRunControlRecord(
            run_id=run_id,
            session_id=session.session_id,
            control_state=RunControlState(run_id=run_id),
            approval_wait=None,
            approval_payload=None,
        )
        self._bridges[run_id] = RunControlRuntimeBridge(cancel_event=asyncio.Event())
        self._sync_session_runtime(session)
        return self._records[run_id].control_state

    def finish_turn(self, session: "MainAgentSessionState") -> RunControlState:
        record = self._adopt_session_compat_state(session)
        if record.approval_wait is not None and record.approval_wait.is_pending:
            record.approval_wait = record.approval_wait.invalidate("turn finished before approval resolved")
        record.approval_payload = None
        record.control_state = record.control_state.clear_wait().mark_terminal()
        bridge = self._adopt_runtime_bridge(session)
        self._resolve_all_waiters(bridge, result=None)
        bridge.cancel_event = None
        self._sync_session_runtime(session)
        return record.control_state

    def pause_turn(
        self,
        session: "MainAgentSessionState",
        *,
        reason: str | None = None,
    ) -> RunControlState:
        record = self._adopt_session_compat_state(session)
        if record.approval_wait is not None and record.approval_wait.is_pending:
            record.approval_wait = record.approval_wait.invalidate(
                reason or "interrupt acknowledged before approval resolution"
            )
        record.approval_payload = None
        record.control_state = record.control_state.clear_wait().pause(reason=reason)
        bridge = self._adopt_runtime_bridge(session)
        self._resolve_all_waiters(bridge, result=None)
        bridge.cancel_event = None
        self._sync_session_runtime(session)
        return record.control_state

    def request_interrupt(
        self,
        session: "MainAgentSessionState",
        *,
        source: str | None = None,
        reason: str | None = None,
    ) -> RunControlState:
        record = self._adopt_session_compat_state(session)
        record.control_state = record.control_state.request_interrupt(source=source, reason=reason)
        bridge = self._adopt_runtime_bridge(session)
        self._signal_cancel_event(bridge.cancel_event)
        self._sync_session_runtime(session)
        return record.control_state

    def request_cancel(
        self,
        session: "MainAgentSessionState",
        *,
        source: str | None = None,
        reason: str | None = None,
        force_stop: bool = False,
    ) -> RunControlState:
        record = self._adopt_session_compat_state(session)
        record.control_state = record.control_state.request_cancel(
            source=source,
            reason=reason,
            force_stop=force_stop,
        )
        bridge = self._adopt_runtime_bridge(session)
        self._signal_cancel_event(bridge.cancel_event)
        self._resolve_all_waiters(bridge, result=None)
        self._sync_session_runtime(session)
        return record.control_state

    def request_resume(
        self,
        session: "MainAgentSessionState",
        *,
        source: str | None = None,
        resume_token: str | None = None,
    ) -> RunControlState:
        record = self._adopt_session_compat_state(session)
        record.control_state = record.control_state.clear_wait().request_resume(
            source=source,
            resume_token=resume_token,
        )
        self._sync_session_runtime(session)
        return record.control_state

    def replace_active_approval_wait(
        self,
        session: "MainAgentSessionState",
        *,
        payload: dict[str, Any],
        future: asyncio.Future[bool | None],
    ) -> ApprovalWait:
        record = self._adopt_session_compat_state(session)
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
            workspace_id=str(session.workspace_dir),
            approval_token=token,
            tool_name=normalized["tool_name"],
            tool_arguments_summary=dict(normalized["arguments"]),
            approval_kind=normalized["kind"],
            policy_reason=normalized["reason"],
            cache_key=normalized["cache_key"],
            can_escalate=bool(normalized["can_escalate"]),
        )
        record.approval_payload = dict(normalized)
        record.control_state = record.control_state.enter_approval_wait(
            record.approval_wait.wait_id,
            approval_token=token,
        )
        bridge.pending_approval_waiters = {token: future}
        self._sync_session_runtime(session)
        return record.approval_wait

    def resolve_active_approval_wait(
        self,
        session: "MainAgentSessionState",
        *,
        token: str | None,
        approved: bool,
    ) -> tuple[ApprovalWait | None, asyncio.Future[bool | None] | None]:
        record = self._adopt_session_compat_state(session)
        approval_wait = record.approval_wait
        if approval_wait is None:
            return None, None
        target_token = _safe_text(token) or _safe_text(approval_wait.approval_token)
        wait_token = _safe_text(approval_wait.approval_token)
        if not target_token or target_token != wait_token or not approval_wait.is_pending:
            return approval_wait, None
        record.approval_wait = approval_wait.resolve(approved=approved)
        record.approval_payload = None
        record.control_state = record.control_state.clear_wait()
        bridge = self._adopt_runtime_bridge(session)
        waiter = bridge.pending_approval_waiters.pop(wait_token, None)
        self._sync_session_runtime(session)
        return record.approval_wait, waiter

    def clear_pending_approval(
        self,
        session: "MainAgentSessionState",
        *,
        token: str | None = None,
        invalidate_reason: str | None = None,
    ) -> None:
        record = self._adopt_session_compat_state(session)
        bridge = self._adopt_runtime_bridge(session)
        normalized_token = _safe_text(token)
        approval_wait = record.approval_wait
        wait_token = _safe_text(approval_wait.approval_token) if approval_wait is not None else ""
        if approval_wait is not None and (not normalized_token or wait_token == normalized_token):
            if approval_wait.is_pending:
                record.approval_wait = approval_wait.invalidate(
                    invalidate_reason or "approval wait cleared from compatibility projection"
                )
                record.control_state = record.control_state.clear_wait()
            record.approval_payload = None
        if normalized_token:
            bridge.pending_approval_waiters.pop(normalized_token, None)
        else:
            bridge.pending_approval_waiters.clear()
        self._sync_session_runtime(session)

    def reset_runtime_state(
        self,
        session: "MainAgentSessionState",
        *,
        reason: str,
    ) -> None:
        record = self._adopt_session_compat_state(session)
        approval_wait = record.approval_wait
        if approval_wait is not None and approval_wait.is_pending:
            record.approval_wait = approval_wait.invalidate(reason)
        record.approval_payload = None
        record.control_state = record.control_state.clear_wait().mark_terminal()
        bridge = self._adopt_runtime_bridge(session)
        self._resolve_all_waiters(bridge, result=None)
        bridge.cancel_event = None
        self._sync_session_runtime(session)

    def build_active_run_projection(self, session: "MainAgentSessionState") -> dict[str, Any]:
        record = self._adopt_session_compat_state(session)
        payloads = self.pending_approval_payloads(session)
        recovery_pending = bool(session.projection.recovery_context_pending)
        running_state = _safe_text(session.projection.running_state) or None
        status, phase = self._resolve_status_phase(
            control_state=record.control_state,
            busy=bool(session.projection.busy),
            waiting_on_approval=bool(payloads),
            recovery_pending=recovery_pending,
            running_state=running_state,
        )
        return {
            "run_id": record.run_id,
            "session_id": session.session_id,
            "status": status,
            "phase": phase,
            "busy": bool(session.projection.busy),
            "waiting_on_approval": bool(payloads),
            "pending_approvals": payloads,
            "active_surface": session.projection.active_surface or session.projection.origin_surface,
            "channel_type": session.projection.channel_type,
            "conversation_id": session.projection.conversation_id,
            "sender_id": session.projection.sender_id,
            "running_state": running_state,
            "control_mode": record.control_state.control_mode.value,
            "interrupt_requested": bool(record.control_state.interrupt_requested),
            "cancel_requested": bool(record.control_state.cancel_requested),
            "resumable": bool(record.control_state.resumable),
            "active_wait_id": record.control_state.active_wait_id,
            "approval_wait": self.serialize_approval_wait(record.approval_wait),
        }

    @classmethod
    def build_persisted_run_projection(cls, *, run_id: str, record: dict[str, Any]) -> dict[str, Any]:
        control_state = cls.deserialize_run_control_state(record.get("run_control"))
        approval_wait = cls.deserialize_approval_wait(record.get("approval_wait"))
        pending_payload = cls._deserialize_pending_payload(record.get("pending_approvals"))
        if approval_wait is not None and approval_wait.is_pending and pending_payload is not None:
            pending_approvals = [pending_payload]
        else:
            pending_approvals = []
        recovery_pending = bool(record.get("recovery_context_pending")) or bool(record.get("recovery"))
        running_state = _safe_text(record.get("running_state")) or None
        busy = bool(record.get("busy", False))
        status, phase = cls._resolve_status_phase(
            control_state=control_state,
            busy=busy,
            waiting_on_approval=bool(pending_approvals),
            recovery_pending=recovery_pending,
            running_state=running_state,
        )
        return {
            "run_id": run_id,
            "session_id": _safe_text(record.get("session_id")) or "",
            "status": status,
            "phase": phase,
            "busy": busy,
            "waiting_on_approval": bool(pending_approvals),
            "pending_approvals": pending_approvals,
            "active_surface": _safe_text(record.get("active_surface")) or None,
            "channel_type": _safe_text(record.get("channel_type")) or None,
            "conversation_id": _safe_text(record.get("conversation_id")) or None,
            "sender_id": _safe_text(record.get("sender_id")) or None,
            "running_state": running_state,
            "control_mode": control_state.control_mode.value if control_state is not None else None,
            "interrupt_requested": bool(control_state.interrupt_requested) if control_state is not None else False,
            "cancel_requested": bool(control_state.cancel_requested) if control_state is not None else False,
            "resumable": bool(control_state.resumable) if control_state is not None else not recovery_pending,
            "active_wait_id": control_state.active_wait_id if control_state is not None else None,
            "approval_wait": cls.serialize_approval_wait(approval_wait),
        }

    @staticmethod
    def serialize_run_control_state(state: RunControlState | None) -> dict[str, Any] | None:
        if state is None:
            return None
        return {
            "run_id": state.run_id,
            "control_mode": state.control_mode.value,
            "active_wait_kind": state.active_wait_kind.value,
            "active_wait_id": state.active_wait_id,
            "interrupt_requested": bool(state.interrupt_requested),
            "cancel_requested": bool(state.cancel_requested),
            "resumable": bool(state.resumable),
            "last_command": state.last_command,
            "last_command_source": state.last_command_source,
            "last_command_at": state.last_command_at.isoformat() if state.last_command_at is not None else None,
            "control_updated_at": state.control_updated_at.isoformat()
            if state.control_updated_at is not None
            else None,
            "force_stop_requested": bool(state.force_stop_requested),
            "last_resume_token": state.last_resume_token,
            "last_pause_reason": state.last_pause_reason,
            "last_cancel_reason": state.last_cancel_reason,
            "last_approval_token": state.last_approval_token,
        }

    @staticmethod
    def serialize_approval_wait(wait: ApprovalWait | None) -> dict[str, Any] | None:
        if wait is None:
            return None
        return {
            "wait_id": wait.wait_id,
            "run_id": wait.run_id,
            "session_id": wait.session_id,
            "workspace_id": wait.workspace_id,
            "approval_token": wait.approval_token,
            "tool_name": wait.tool_name,
            "tool_arguments_summary": dict(wait.tool_arguments_summary),
            "approval_kind": wait.approval_kind,
            "policy_reason": wait.policy_reason,
            "cache_key": wait.cache_key,
            "can_escalate": bool(wait.can_escalate),
            "wait_state": wait.wait_state.value,
            "decision_result": wait.decision_result.value if wait.decision_result is not None else None,
            "created_at": wait.created_at.isoformat() if wait.created_at is not None else None,
            "resolved_at": wait.resolved_at.isoformat() if wait.resolved_at is not None else None,
            "invalidated_reason": wait.invalidated_reason,
        }

    @staticmethod
    def deserialize_run_control_state(payload: Any) -> RunControlState | None:
        if not isinstance(payload, dict):
            return None
        run_id = _safe_text(payload.get("run_id"))
        if not run_id:
            return None
        try:
            return RunControlState(
                run_id=run_id,
                control_mode=RunControlMode(str(payload.get("control_mode") or RunControlMode.NORMAL.value)),
                active_wait_kind=RunWaitKind(str(payload.get("active_wait_kind") or RunWaitKind.NONE.value)),
                active_wait_id=_safe_text(payload.get("active_wait_id")) or None,
                interrupt_requested=bool(payload.get("interrupt_requested", False)),
                cancel_requested=bool(payload.get("cancel_requested", False)),
                resumable=bool(payload.get("resumable", True)),
                last_command=_safe_text(payload.get("last_command")) or None,
                last_command_source=_safe_text(payload.get("last_command_source")) or None,
                last_command_at=_parse_datetime(payload.get("last_command_at")),
                control_updated_at=_parse_datetime(payload.get("control_updated_at")),
                force_stop_requested=bool(payload.get("force_stop_requested", False)),
                last_resume_token=_safe_text(payload.get("last_resume_token")) or None,
                last_pause_reason=_safe_text(payload.get("last_pause_reason")) or None,
                last_cancel_reason=_safe_text(payload.get("last_cancel_reason")) or None,
                last_approval_token=_safe_text(payload.get("last_approval_token")) or None,
            )
        except Exception:
            return None

    @staticmethod
    def deserialize_approval_wait(payload: Any) -> ApprovalWait | None:
        if not isinstance(payload, dict):
            return None
        wait_id = _safe_text(payload.get("wait_id"))
        run_id = _safe_text(payload.get("run_id"))
        if not wait_id or not run_id:
            return None
        try:
            return ApprovalWait(
                wait_id=wait_id,
                run_id=run_id,
                session_id=_safe_text(payload.get("session_id")) or None,
                workspace_id=_safe_text(payload.get("workspace_id")) or None,
                approval_token=_safe_text(payload.get("approval_token")) or None,
                tool_name=_safe_text(payload.get("tool_name")) or "tool",
                tool_arguments_summary=dict(payload.get("tool_arguments_summary") or {}),
                approval_kind=_safe_text(payload.get("approval_kind")) or None,
                policy_reason=_safe_text(payload.get("policy_reason")) or None,
                cache_key=_safe_text(payload.get("cache_key")) or None,
                can_escalate=bool(payload.get("can_escalate", False)),
                wait_state=ApprovalWaitState(str(payload.get("wait_state") or ApprovalWaitState.PENDING.value)),
                decision_result=(
                    ApprovalDecision(str(payload.get("decision_result")))
                    if payload.get("decision_result")
                    else None
                ),
                created_at=_parse_datetime(payload.get("created_at")),
                resolved_at=_parse_datetime(payload.get("resolved_at")),
                invalidated_reason=_safe_text(payload.get("invalidated_reason")) or None,
            )
        except Exception:
            return None

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
    def _resolve_status_phase(
        *,
        control_state: RunControlState | None,
        busy: bool,
        waiting_on_approval: bool,
        recovery_pending: bool,
        running_state: str | None,
    ) -> tuple[str, str]:
        normalized_running_state = _safe_text(running_state).lower()
        if control_state is not None:
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
                return "waiting", "awaiting_approval"
            if control_state.control_mode is RunControlMode.PAUSED:
                return PAUSED_STATUS, PAUSED_PHASE
        if normalized_running_state == CANCEL_REQUESTED_RUNNING_STATE:
            return CANCEL_REQUESTED_STATUS, CANCELLING_PHASE
        if normalized_running_state == INTERRUPT_REQUESTED_RUNNING_STATE:
            return INTERRUPT_REQUESTED_STATUS, INTERRUPTING_PHASE
        if waiting_on_approval:
            return "waiting", "awaiting_approval"
        if recovery_pending:
            return PAUSED_STATUS, PAUSED_PHASE
        if busy:
            return "running", "executing_tools"
        return "completed", "terminal"

    def _adopt_session_compat_state(self, session: "MainAgentSessionState") -> SessionBackedRunControlRecord:
        run_id = self.run_id_for_session(session.session_id)
        record = self._records.get(run_id)
        if record is None:
            record = SessionBackedRunControlRecord(
                run_id=run_id,
                session_id=session.session_id,
                control_state=RunControlState(run_id=run_id),
            )
            self._records[run_id] = record

        compat_payload = self._deserialize_pending_payload(getattr(session.runtime, "pending_approvals", None))
        if compat_payload is not None:
            existing_wait = record.approval_wait
            same_token = existing_wait is not None and _safe_text(existing_wait.approval_token) == compat_payload["token"]
            if existing_wait is None or (existing_wait.is_pending and not same_token):
                record.approval_wait = ApprovalWait(
                    wait_id=f"{run_id}:approval:{compat_payload['token']}",
                    run_id=run_id,
                    session_id=session.session_id,
                    workspace_id=str(session.workspace_dir),
                    approval_token=compat_payload["token"],
                    tool_name=compat_payload["tool_name"],
                    tool_arguments_summary=dict(compat_payload["arguments"]),
                    approval_kind=compat_payload["kind"],
                    policy_reason=compat_payload["reason"],
                    cache_key=compat_payload["cache_key"],
                    can_escalate=bool(compat_payload["can_escalate"]),
                )
            record.approval_payload = dict(compat_payload)
            if record.control_state.active_wait_id is None or not record.control_state.is_waiting:
                record.control_state = record.control_state.enter_approval_wait(
                    record.approval_wait.wait_id,
                    approval_token=compat_payload["token"],
                )
        elif record.approval_wait is not None and record.approval_wait.is_pending and record.approval_payload is None:
            record.approval_payload = self._approval_wait_payload(record.approval_wait)

        normalized_running_state = _safe_text(getattr(session.projection, "running_state", "")).lower()
        if (
            normalized_running_state == INTERRUPT_REQUESTED_RUNNING_STATE
            and not record.control_state.interrupt_requested
            and not record.control_state.cancel_requested
        ):
            record.control_state = record.control_state.request_interrupt(
                reason=INTERRUPT_REQUESTED_RUNNING_STATE
            )
        if (
            normalized_running_state == CANCEL_REQUESTED_RUNNING_STATE
            and not record.control_state.cancel_requested
        ):
            record.control_state = record.control_state.request_cancel(
                reason=CANCEL_REQUESTED_RUNNING_STATE
            )
        return record

    def _adopt_runtime_bridge(self, session: "MainAgentSessionState") -> RunControlRuntimeBridge:
        run_id = self.run_id_for_session(session.session_id)
        bridge = self._bridges.get(run_id)
        if bridge is None:
            bridge = RunControlRuntimeBridge()
            self._bridges[run_id] = bridge
        compat_cancel_event = getattr(session.runtime, "cancel_event", None)
        if compat_cancel_event is not None and bridge.cancel_event is None:
            bridge.cancel_event = compat_cancel_event
        compat_waiters = getattr(session.runtime, "pending_approval_waiters", None)
        if isinstance(compat_waiters, dict) and compat_waiters and not bridge.pending_approval_waiters:
            bridge.pending_approval_waiters = dict(compat_waiters)
        return bridge

    def _sync_session_runtime(self, session: "MainAgentSessionState") -> None:
        run_id = self.run_id_for_session(session.session_id)
        record = self._records.get(run_id)
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
        bridge: RunControlRuntimeBridge,
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
    "SessionBackedRunControlRecord",
]
