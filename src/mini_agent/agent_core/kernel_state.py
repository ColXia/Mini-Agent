"""Agent-owned assembly helpers for the v11.1 kernel truth family."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mini_agent.agent_core.contracts import (
    AgentInstance,
    AgentInstanceLifecycleState,
    AgentProfile,
    ApprovalDecision,
    ApprovalWait,
    ApprovalWaitState,
    CapabilitySnapshot,
    Checkpoint,
    CheckpointType,
    ExecutionJournal,
    ExecutionJournalEvent,
    Run,
    RunInterruptState,
    RunControlState,
    RunControlMode,
    RunPhase,
    RunStatus,
    RunWaitKind,
    SessionAttachment,
    WorkspaceAttachment,
    WorkspaceKind,
    WorkspaceRuntimeBackend,
)


def _clean_text(value: object) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = _clean_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _stable_ref(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"


@dataclass(frozen=True, slots=True)
class AgentKernelStateSeed:
    """Resolved input required to materialize one live kernel truth bundle."""

    run_id: str
    session_id: str
    workspace_id: str
    workspace_root: str
    trigger_source: str
    initial_status: RunStatus
    initial_phase: RunPhase
    waiting_reason: str | None = None
    agent_profile_id: str = "agent-profile:main-agent"
    agent_role: str = "main_agent"
    agent_identity_label: str = "Mini-Agent"
    built_in_tool_names: tuple[str, ...] = ()
    built_in_internal_skill_names: tuple[str, ...] = ()
    capability_hints: tuple[str, ...] = ()
    visible_skill_names: tuple[str, ...] = ()
    visible_memory_scopes: tuple[str, ...] = ("session", "workspace", "global")
    enabled_external_capabilities: tuple[str, ...] = ()
    agent_model_provider_id: str | None = None
    agent_model_id: str | None = None
    approval_profile: dict[str, Any] | None = None
    context_policy: dict[str, Any] | None = None
    workspace_kind: WorkspaceKind = WorkspaceKind.PROJECT
    workspace_runtime_backend: WorkspaceRuntimeBackend = WorkspaceRuntimeBackend.DIRECT
    snapshot_strategy: str | None = "workspace_runtime_snapshot"
    recovery_context_pending: bool = False

    def __post_init__(self) -> None:
        required_fields = {
            "run_id": _clean_text(self.run_id),
            "session_id": _clean_text(self.session_id),
            "workspace_id": _clean_text(self.workspace_id),
            "workspace_root": _clean_text(self.workspace_root),
            "trigger_source": _clean_text(self.trigger_source),
            "agent_profile_id": _clean_text(self.agent_profile_id),
            "agent_role": _clean_text(self.agent_role),
            "agent_identity_label": _clean_text(self.agent_identity_label),
        }
        for field_name, value in required_fields.items():
            if not value:
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "waiting_reason", _clean_text(self.waiting_reason))
        object.__setattr__(
            self,
            "built_in_tool_names",
            tuple(sorted(_clean_text(name) for name in self.built_in_tool_names if _clean_text(name))),
        )
        object.__setattr__(
            self,
            "built_in_internal_skill_names",
            tuple(
                _clean_text(name)
                for name in self.built_in_internal_skill_names
                if _clean_text(name)
            ),
        )
        object.__setattr__(
            self,
            "capability_hints",
            tuple(_clean_text(name) for name in self.capability_hints if _clean_text(name)),
        )
        object.__setattr__(
            self,
            "visible_skill_names",
            tuple(_clean_text(name) for name in self.visible_skill_names if _clean_text(name)),
        )
        object.__setattr__(
            self,
            "visible_memory_scopes",
            tuple(_clean_text(name) for name in self.visible_memory_scopes if _clean_text(name)),
        )
        object.__setattr__(
            self,
            "enabled_external_capabilities",
            tuple(
                _clean_text(name)
                for name in self.enabled_external_capabilities
                if _clean_text(name)
            ),
        )
        object.__setattr__(
            self,
            "agent_model_provider_id",
            _clean_text(self.agent_model_provider_id),
        )
        object.__setattr__(self, "agent_model_id", _clean_text(self.agent_model_id))
        object.__setattr__(
            self,
            "approval_profile",
            dict(self.approval_profile or {}) if self.approval_profile else None,
        )
        object.__setattr__(
            self,
            "context_policy",
            dict(self.context_policy or {}) if self.context_policy else {},
        )
        object.__setattr__(self, "snapshot_strategy", _clean_text(self.snapshot_strategy))


@dataclass(slots=True)
class AgentKernelStateRecord:
    """Live aggregate of the kernel truth family for one active run."""

    run_id: str
    session_id: str
    agent_profile: AgentProfile
    agent_instance: AgentInstance
    run: Run
    workspace_attachment: WorkspaceAttachment
    session_attachment: SessionAttachment
    capability_snapshot: CapabilitySnapshot
    execution_journal: ExecutionJournal
    run_control: RunControlState
    approval_wait: ApprovalWait | None = None
    approval_payload: dict[str, Any] | None = None
    checkpoint: Checkpoint | None = None


def build_agent_profile(seed: AgentKernelStateSeed) -> AgentProfile:
    """Build the durable agent identity for one live run bundle."""

    return AgentProfile(
        agent_profile_id=seed.agent_profile_id,
        role=seed.agent_role,
        identity_label=seed.agent_identity_label,
        built_in_tool_names=seed.built_in_tool_names,
        built_in_internal_skill_names=seed.built_in_internal_skill_names,
        capability_hints=seed.capability_hints,
        static_policy_hints={},
    )


def build_workspace_attachment(seed: AgentKernelStateSeed) -> WorkspaceAttachment:
    """Build the workspace execution-world binding for one run."""

    path_ref = seed.workspace_root.lower()
    return WorkspaceAttachment(
        workspace_attachment_id=f"workspace-attachment:{seed.run_id}",
        workspace_id=seed.workspace_id,
        workspace_kind=seed.workspace_kind,
        root_dir=seed.workspace_root,
        runtime_backend=seed.workspace_runtime_backend,
        runtime_ref=f"workspace-runtime:{seed.workspace_id}",
        boundary_manifest_hash=_stable_ref("boundary", path_ref),
        permission_table_ref=_stable_ref("permission-table", path_ref),
        outside_zone_policy_ref=_stable_ref("outside-zone", path_ref),
        mutation_ledger_ref=_stable_ref("mutation-ledger", path_ref),
        snapshot_strategy=seed.snapshot_strategy,
    )


def build_session_attachment(seed: AgentKernelStateSeed) -> SessionAttachment:
    """Build the task-container binding for one run."""

    return SessionAttachment(
        session_attachment_id=f"session-attachment:{seed.run_id}",
        session_id=seed.session_id,
        workspace_id=seed.workspace_id,
        transcript_ref=f"transcript:{seed.session_id}",
        session_memory_ref=f"session-memory:{seed.session_id}",
        approval_scope_ref=f"approval-scope:{seed.session_id}",
        context_policy_ref=f"context-policy:{seed.session_id}",
        lineage_ref=f"session-lineage:{seed.session_id}",
        task_summary_ref=f"task-summary:{seed.session_id}",
        recovery_context_ref=(
            f"recovery:{seed.session_id}" if seed.recovery_context_pending else None
        ),
    )


def build_agent_instance(
    seed: AgentKernelStateSeed,
    *,
    agent_profile: AgentProfile,
    workspace_attachment: WorkspaceAttachment,
    session_attachment: SessionAttachment,
) -> AgentInstance:
    """Build the persistent execution subject for one run."""

    instance = AgentInstance(
        agent_instance_id=f"agent-instance:{seed.session_id}",
        agent_profile_id=agent_profile.agent_profile_id,
        lifecycle_state=AgentInstanceLifecycleState.READY,
    )
    return instance.attach(
        workspace_id=workspace_attachment.workspace_id,
        session_id=seed.session_id,
        workspace_attachment_id=workspace_attachment.workspace_attachment_id,
        session_attachment_id=session_attachment.session_attachment_id,
    )


def build_run(
    seed: AgentKernelStateSeed,
    *,
    agent_profile: AgentProfile,
    agent_instance: AgentInstance,
    workspace_attachment: WorkspaceAttachment,
    session_attachment: SessionAttachment,
) -> Run:
    """Build the formal run object for one execution unit."""

    return Run(
        run_id=seed.run_id,
        agent_instance_id=agent_instance.agent_instance_id,
        agent_profile_id=agent_profile.agent_profile_id,
        workspace_id=seed.workspace_id,
        session_id=seed.session_id,
        trigger_source=seed.trigger_source,
        journal_stream_id=f"journal:{seed.run_id}",
        waiting_reason=seed.waiting_reason,
    ).bind_attachments(
        workspace_attachment_id=workspace_attachment.workspace_attachment_id,
        session_attachment_id=session_attachment.session_attachment_id,
    ).transition(
        status=seed.initial_status,
        phase=seed.initial_phase,
        waiting_reason=seed.waiting_reason,
    )


def build_capability_snapshot(
    seed: AgentKernelStateSeed,
    *,
    agent_profile: AgentProfile,
    agent_instance: AgentInstance,
    run: Run,
) -> CapabilitySnapshot:
    """Build the stable capability view consumed by one run."""

    return CapabilitySnapshot(
        capability_snapshot_id=f"capability-snapshot:{run.run_id}",
        agent_profile_id=agent_profile.agent_profile_id,
        agent_instance_id=agent_instance.agent_instance_id,
        run_id=run.run_id,
        workspace_id=seed.workspace_id,
        session_id=seed.session_id,
        resolved_tool_names=agent_profile.built_in_tool_names,
        resolved_tool_policies={},
        visible_skill_names=seed.visible_skill_names,
        visible_memory_scopes=seed.visible_memory_scopes,
        enabled_external_capabilities=seed.enabled_external_capabilities,
        agent_model_provider_id=seed.agent_model_provider_id,
        agent_model_id=seed.agent_model_id,
        workspace_runtime_mode=seed.workspace_runtime_backend.value,
        approval_profile=seed.approval_profile,
        context_policy=seed.context_policy,
        refresh_reason="run_start",
    )


def build_agent_kernel_state_record(seed: AgentKernelStateSeed) -> AgentKernelStateRecord:
    """Materialize the kernel truth bundle that runtime can then host and mutate."""

    agent_profile = build_agent_profile(seed)
    workspace_attachment = build_workspace_attachment(seed)
    session_attachment = build_session_attachment(seed)
    agent_instance = build_agent_instance(
        seed,
        agent_profile=agent_profile,
        workspace_attachment=workspace_attachment,
        session_attachment=session_attachment,
    )
    run = build_run(
        seed,
        agent_profile=agent_profile,
        agent_instance=agent_instance,
        workspace_attachment=workspace_attachment,
        session_attachment=session_attachment,
    )
    capability_snapshot = build_capability_snapshot(
        seed,
        agent_profile=agent_profile,
        agent_instance=agent_instance,
        run=run,
    )
    run = run.attach_capability_snapshot(capability_snapshot.capability_snapshot_id)
    agent_instance = agent_instance.activate_run(run.run_id)
    if seed.initial_status is RunStatus.WAITING:
        agent_instance = agent_instance.mark_waiting(wait_kind=RunWaitKind.APPROVAL)
    elif seed.initial_status is RunStatus.PAUSED:
        agent_instance = agent_instance.mark_paused()
    execution_journal = ExecutionJournal(
        journal_stream_id=run.journal_stream_id or f"journal:{seed.run_id}",
        run_id=run.run_id,
        agent_instance_id=agent_instance.agent_instance_id,
        workspace_id=seed.workspace_id,
        session_id=seed.session_id,
    )
    return AgentKernelStateRecord(
        run_id=seed.run_id,
        session_id=seed.session_id,
        agent_profile=agent_profile,
        agent_instance=agent_instance,
        run=run,
        workspace_attachment=workspace_attachment,
        session_attachment=session_attachment,
        capability_snapshot=capability_snapshot,
        execution_journal=execution_journal,
        run_control=RunControlState(run_id=seed.run_id),
    )


def build_checkpoint_for_record(
    record: AgentKernelStateRecord,
    *,
    checkpoint_type: CheckpointType,
    waiting_reason: str | None,
    resume_token: str | None,
) -> tuple[Run, Checkpoint]:
    """Create the next checkpoint for an existing kernel truth bundle."""

    checkpoint_seq = record.run.last_checkpoint_seq + 1
    checkpoint = Checkpoint(
        checkpoint_id=f"checkpoint:{record.run_id}:{checkpoint_seq}",
        run_id=record.run.run_id,
        agent_instance_id=record.agent_instance.agent_instance_id,
        checkpoint_seq=checkpoint_seq,
        checkpoint_type=checkpoint_type,
        status=record.run.status,
        phase=record.run.phase,
        step_index=record.run.step_index,
        workspace_attachment_id=record.workspace_attachment.workspace_attachment_id,
        session_attachment_id=record.session_attachment.session_attachment_id,
        capability_snapshot_hash=record.capability_snapshot.capability_snapshot_id,
        journal_offset=record.execution_journal.last_event_seq,
        waiting_reason=waiting_reason,
        resume_token=resume_token,
        recovery_context_ref=record.session_attachment.recovery_context_ref,
    )
    updated_run = record.run.activate_checkpoint(
        checkpoint.checkpoint_id,
        checkpoint_seq=checkpoint_seq,
        restorable=checkpoint.recoverable,
    )
    return updated_run, checkpoint


def serialize_run_control_state(state: RunControlState | None) -> dict[str, Any] | None:
    """Serialize durable run-control truth."""

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
        "control_updated_at": (
            state.control_updated_at.isoformat() if state.control_updated_at is not None else None
        ),
        "force_stop_requested": bool(state.force_stop_requested),
        "last_resume_token": state.last_resume_token,
        "last_pause_reason": state.last_pause_reason,
        "last_cancel_reason": state.last_cancel_reason,
        "last_approval_token": state.last_approval_token,
    }


def deserialize_run_control_state(payload: Any) -> RunControlState | None:
    """Deserialize durable run-control truth."""

    if not isinstance(payload, dict):
        return None
    run_id = _clean_text(payload.get("run_id"))
    if not run_id:
        return None
    try:
        return RunControlState(
            run_id=run_id,
            control_mode=RunControlMode(
                str(payload.get("control_mode") or RunControlMode.NORMAL.value)
            ),
            active_wait_kind=RunWaitKind(
                str(payload.get("active_wait_kind") or RunWaitKind.NONE.value)
            ),
            active_wait_id=_clean_text(payload.get("active_wait_id")) or None,
            interrupt_requested=bool(payload.get("interrupt_requested", False)),
            cancel_requested=bool(payload.get("cancel_requested", False)),
            resumable=bool(payload.get("resumable", True)),
            last_command=_clean_text(payload.get("last_command")) or None,
            last_command_source=_clean_text(payload.get("last_command_source")) or None,
            last_command_at=_parse_datetime(payload.get("last_command_at")),
            control_updated_at=_parse_datetime(payload.get("control_updated_at")),
            force_stop_requested=bool(payload.get("force_stop_requested", False)),
            last_resume_token=_clean_text(payload.get("last_resume_token")) or None,
            last_pause_reason=_clean_text(payload.get("last_pause_reason")) or None,
            last_cancel_reason=_clean_text(payload.get("last_cancel_reason")) or None,
            last_approval_token=_clean_text(payload.get("last_approval_token")) or None,
        )
    except Exception:
        return None


def serialize_approval_wait(wait: ApprovalWait | None) -> dict[str, Any] | None:
    """Serialize durable approval-wait truth."""

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


def deserialize_approval_wait(payload: Any) -> ApprovalWait | None:
    """Deserialize durable approval-wait truth."""

    if not isinstance(payload, dict):
        return None
    wait_id = _clean_text(payload.get("wait_id"))
    run_id = _clean_text(payload.get("run_id"))
    if not wait_id or not run_id:
        return None
    try:
        return ApprovalWait(
            wait_id=wait_id,
            run_id=run_id,
            session_id=_clean_text(payload.get("session_id")) or None,
            workspace_id=_clean_text(payload.get("workspace_id")) or None,
            approval_token=_clean_text(payload.get("approval_token")) or None,
            tool_name=_clean_text(payload.get("tool_name")) or "tool",
            tool_arguments_summary=dict(payload.get("tool_arguments_summary") or {}),
            approval_kind=_clean_text(payload.get("approval_kind")) or None,
            policy_reason=_clean_text(payload.get("policy_reason")) or None,
            cache_key=_clean_text(payload.get("cache_key")) or None,
            can_escalate=bool(payload.get("can_escalate", False)),
            wait_state=ApprovalWaitState(
                str(payload.get("wait_state") or ApprovalWaitState.PENDING.value)
            ),
            decision_result=(
                ApprovalDecision(str(payload.get("decision_result")))
                if payload.get("decision_result")
                else None
            ),
            created_at=_parse_datetime(payload.get("created_at")),
            resolved_at=_parse_datetime(payload.get("resolved_at")),
            invalidated_reason=_clean_text(payload.get("invalidated_reason")) or None,
        )
    except Exception:
        return None


def serialize_agent_kernel_state_record(record: AgentKernelStateRecord) -> dict[str, Any]:
    """Serialize the full agent-owned kernel truth bundle."""

    latest = record.execution_journal.latest_event
    return {
        "agent_profile": {
            "agent_profile_id": record.agent_profile.agent_profile_id,
            "role": record.agent_profile.role,
            "identity_label": record.agent_profile.identity_label,
            "static_policy_hints": dict(record.agent_profile.static_policy_hints or {}),
            "built_in_tool_names": list(record.agent_profile.built_in_tool_names),
            "built_in_internal_skill_names": list(record.agent_profile.built_in_internal_skill_names),
            "default_model_routing_intent": record.agent_profile.default_model_routing_intent,
            "stable_behavior_defaults": dict(record.agent_profile.stable_behavior_defaults or {}),
            "capability_hints": list(record.agent_profile.capability_hints),
            "created_at": (
                record.agent_profile.created_at.isoformat()
                if record.agent_profile.created_at is not None
                else None
            ),
            "updated_at": (
                record.agent_profile.updated_at.isoformat()
                if record.agent_profile.updated_at is not None
                else None
            ),
        },
        "agent_instance": {
            "agent_instance_id": record.agent_instance.agent_instance_id,
            "agent_profile_id": record.agent_instance.agent_profile_id,
            "lifecycle_state": record.agent_instance.lifecycle_state.value,
            "active_run_id": record.agent_instance.active_run_id,
            "current_workspace_id": record.agent_instance.current_workspace_id,
            "current_session_id": record.agent_instance.current_session_id,
            "current_workspace_attachment_id": record.agent_instance.current_workspace_attachment_id,
            "current_session_attachment_id": record.agent_instance.current_session_attachment_id,
            "checkpoint_head_id": record.agent_instance.checkpoint_head_id,
            "journal_head_seq": record.agent_instance.journal_head_seq,
            "interrupt_requested": bool(record.agent_instance.interrupt_requested),
            "cancel_requested": bool(record.agent_instance.cancel_requested),
            "pending_wait_kind": record.agent_instance.pending_wait_kind.value,
            "pending_wait_id": record.agent_instance.pending_wait_id,
            "restored_from_checkpoint_id": record.agent_instance.restored_from_checkpoint_id,
            "created_at": (
                record.agent_instance.created_at.isoformat()
                if record.agent_instance.created_at is not None
                else None
            ),
            "updated_at": (
                record.agent_instance.updated_at.isoformat()
                if record.agent_instance.updated_at is not None
                else None
            ),
            "retired_at": (
                record.agent_instance.retired_at.isoformat()
                if record.agent_instance.retired_at is not None
                else None
            ),
        },
        "run": {
            "run_id": record.run.run_id,
            "agent_instance_id": record.run.agent_instance_id,
            "agent_profile_id": record.run.agent_profile_id,
            "workspace_id": record.run.workspace_id,
            "session_id": record.run.session_id,
            "trigger_source": record.run.trigger_source,
            "status": record.run.status.value,
            "phase": record.run.phase.value,
            "step_index": record.run.step_index,
            "waiting_reason": record.run.waiting_reason,
            "interrupt_state": record.run.interrupt_state.value,
            "terminal_reason": record.run.terminal_reason,
            "workspace_attachment_id": record.run.workspace_attachment_id,
            "session_attachment_id": record.run.session_attachment_id,
            "capability_snapshot_id": record.run.capability_snapshot_id,
            "active_checkpoint_id": record.run.active_checkpoint_id,
            "last_checkpoint_seq": record.run.last_checkpoint_seq,
            "journal_stream_id": record.run.journal_stream_id,
            "restorable": bool(record.run.restorable),
            "created_at": record.run.created_at.isoformat() if record.run.created_at is not None else None,
            "started_at": record.run.started_at.isoformat() if record.run.started_at is not None else None,
            "updated_at": record.run.updated_at.isoformat() if record.run.updated_at is not None else None,
            "ended_at": record.run.ended_at.isoformat() if record.run.ended_at is not None else None,
            "last_error_code": record.run.last_error_code,
            "last_error_summary": record.run.last_error_summary,
            "last_model_request_id": record.run.last_model_request_id,
            "last_tool_batch_id": record.run.last_tool_batch_id,
            "last_mutation_ledger_seq": record.run.last_mutation_ledger_seq,
        },
        "workspace_attachment": {
            "workspace_attachment_id": record.workspace_attachment.workspace_attachment_id,
            "workspace_id": record.workspace_attachment.workspace_id,
            "workspace_kind": record.workspace_attachment.workspace_kind.value,
            "root_dir": record.workspace_attachment.root_dir,
            "runtime_backend": record.workspace_attachment.runtime_backend.value,
            "runtime_ref": record.workspace_attachment.runtime_ref,
            "boundary_manifest_hash": record.workspace_attachment.boundary_manifest_hash,
            "permission_table_ref": record.workspace_attachment.permission_table_ref,
            "outside_zone_policy_ref": record.workspace_attachment.outside_zone_policy_ref,
            "mutation_ledger_ref": record.workspace_attachment.mutation_ledger_ref,
            "mounted_at": (
                record.workspace_attachment.mounted_at.isoformat()
                if record.workspace_attachment.mounted_at is not None
                else None
            ),
            "snapshot_strategy": record.workspace_attachment.snapshot_strategy,
            "network_policy_ref": record.workspace_attachment.network_policy_ref,
            "resource_policy_ref": record.workspace_attachment.resource_policy_ref,
            "attachment_note": record.workspace_attachment.attachment_note,
        },
        "session_attachment": {
            "session_attachment_id": record.session_attachment.session_attachment_id,
            "session_id": record.session_attachment.session_id,
            "workspace_id": record.session_attachment.workspace_id,
            "transcript_ref": record.session_attachment.transcript_ref,
            "session_memory_ref": record.session_attachment.session_memory_ref,
            "approval_scope_ref": record.session_attachment.approval_scope_ref,
            "context_policy_ref": record.session_attachment.context_policy_ref,
            "lineage_ref": record.session_attachment.lineage_ref,
            "attached_at": (
                record.session_attachment.attached_at.isoformat()
                if record.session_attachment.attached_at is not None
                else None
            ),
            "task_summary_ref": record.session_attachment.task_summary_ref,
            "recovery_context_ref": record.session_attachment.recovery_context_ref,
            "operator_override_ref": record.session_attachment.operator_override_ref,
            "attachment_note": record.session_attachment.attachment_note,
        },
        "capability_snapshot": {
            "capability_snapshot_id": record.capability_snapshot.capability_snapshot_id,
            "agent_profile_id": record.capability_snapshot.agent_profile_id,
            "agent_instance_id": record.capability_snapshot.agent_instance_id,
            "run_id": record.capability_snapshot.run_id,
            "workspace_id": record.capability_snapshot.workspace_id,
            "session_id": record.capability_snapshot.session_id,
            "resolved_tool_names": list(record.capability_snapshot.resolved_tool_names),
            "resolved_tool_policies": dict(record.capability_snapshot.resolved_tool_policies or {}),
            "visible_skill_names": list(record.capability_snapshot.visible_skill_names),
            "visible_memory_scopes": list(record.capability_snapshot.visible_memory_scopes),
            "enabled_external_capabilities": list(
                record.capability_snapshot.enabled_external_capabilities
            ),
            "agent_model_provider_id": record.capability_snapshot.agent_model_provider_id,
            "agent_model_id": record.capability_snapshot.agent_model_id,
            "agent_model_capability_profile": dict(
                record.capability_snapshot.agent_model_capability_profile or {}
            ),
            "workspace_runtime_mode": record.capability_snapshot.workspace_runtime_mode,
            "approval_profile": dict(record.capability_snapshot.approval_profile or {}),
            "context_policy": dict(record.capability_snapshot.context_policy or {}),
            "refresh_reason": record.capability_snapshot.refresh_reason,
            "created_at": (
                record.capability_snapshot.created_at.isoformat()
                if record.capability_snapshot.created_at is not None
                else None
            ),
            "revision": record.capability_snapshot.revision,
        },
        "checkpoint": (
            {
                "checkpoint_id": record.checkpoint.checkpoint_id,
                "run_id": record.checkpoint.run_id,
                "agent_instance_id": record.checkpoint.agent_instance_id,
                "checkpoint_seq": record.checkpoint.checkpoint_seq,
                "checkpoint_type": record.checkpoint.checkpoint_type.value,
                "status": record.checkpoint.status.value,
                "phase": record.checkpoint.phase.value,
                "step_index": record.checkpoint.step_index,
                "workspace_attachment_id": record.checkpoint.workspace_attachment_id,
                "session_attachment_id": record.checkpoint.session_attachment_id,
                "capability_snapshot_hash": record.checkpoint.capability_snapshot_hash,
                "journal_offset": record.checkpoint.journal_offset,
                "waiting_reason": record.checkpoint.waiting_reason,
                "resume_token": record.checkpoint.resume_token,
                "created_at": (
                    record.checkpoint.created_at.isoformat()
                    if record.checkpoint.created_at is not None
                    else None
                ),
                "schema_version": record.checkpoint.schema_version,
                "last_model_turn_ref": record.checkpoint.last_model_turn_ref,
                "last_tool_batch_ref": record.checkpoint.last_tool_batch_ref,
                "last_mutation_ledger_seq": record.checkpoint.last_mutation_ledger_seq,
                "recovery_context_ref": record.checkpoint.recovery_context_ref,
                "error_ref": record.checkpoint.error_ref,
                "recoverable": bool(record.checkpoint.recoverable),
            }
            if record.checkpoint is not None
            else None
        ),
        "journal": {
            "journal_stream_id": record.execution_journal.journal_stream_id,
            "run_id": record.execution_journal.run_id,
            "agent_instance_id": record.execution_journal.agent_instance_id,
            "workspace_id": record.execution_journal.workspace_id,
            "session_id": record.execution_journal.session_id,
            "last_event_seq": record.execution_journal.last_event_seq,
            "latest_event_type": latest.event_type if latest is not None else None,
            "created_at": (
                record.execution_journal.created_at.isoformat()
                if record.execution_journal.created_at is not None
                else None
            ),
            "closed_at": (
                record.execution_journal.closed_at.isoformat()
                if record.execution_journal.closed_at is not None
                else None
            ),
            "events": [
                {
                    "event_seq": event.event_seq,
                    "event_type": event.event_type,
                    "run_id": event.run_id,
                    "agent_instance_id": event.agent_instance_id,
                    "workspace_id": event.workspace_id,
                    "session_id": event.session_id,
                    "status": event.status.value,
                    "phase": event.phase.value,
                    "step_index": event.step_index,
                    "event_ts": event.event_ts.isoformat() if event.event_ts is not None else None,
                    "correlation_id": event.correlation_id,
                    "causation_id": event.causation_id,
                    "payload": dict(event.payload),
                }
                for event in record.execution_journal.events
            ],
        },
        "run_control": serialize_run_control_state(record.run_control),
        "approval_wait": serialize_approval_wait(record.approval_wait),
    }


def deserialize_agent_kernel_state_record(payload: Any) -> AgentKernelStateRecord | None:
    """Deserialize the full agent-owned kernel truth bundle."""

    if not isinstance(payload, dict):
        return None
    try:
        profile_payload = payload.get("agent_profile")
        instance_payload = payload.get("agent_instance")
        run_payload = payload.get("run")
        workspace_attachment_payload = payload.get("workspace_attachment")
        session_attachment_payload = payload.get("session_attachment")
        capability_snapshot_payload = payload.get("capability_snapshot")
        journal_payload = payload.get("journal")
        if not all(
            isinstance(item, dict)
            for item in (
                profile_payload,
                instance_payload,
                run_payload,
                workspace_attachment_payload,
                session_attachment_payload,
                capability_snapshot_payload,
                journal_payload,
            )
        ):
            return None

        agent_profile = AgentProfile(
            agent_profile_id=_clean_text(profile_payload.get("agent_profile_id")) or "",
            role=_clean_text(profile_payload.get("role")) or None,
            identity_label=_clean_text(profile_payload.get("identity_label")) or None,
            static_policy_hints=dict(profile_payload.get("static_policy_hints") or {}),
            built_in_tool_names=tuple(profile_payload.get("built_in_tool_names") or ()),
            built_in_internal_skill_names=tuple(
                profile_payload.get("built_in_internal_skill_names") or ()
            ),
            default_model_routing_intent=(
                _clean_text(profile_payload.get("default_model_routing_intent")) or None
            ),
            stable_behavior_defaults=dict(profile_payload.get("stable_behavior_defaults") or {}),
            capability_hints=tuple(profile_payload.get("capability_hints") or ()),
            created_at=_parse_datetime(profile_payload.get("created_at")),
            updated_at=_parse_datetime(profile_payload.get("updated_at")),
        )
        agent_instance = AgentInstance(
            agent_instance_id=_clean_text(instance_payload.get("agent_instance_id")) or "",
            agent_profile_id=_clean_text(instance_payload.get("agent_profile_id")) or "",
            lifecycle_state=AgentInstanceLifecycleState(
                str(
                    instance_payload.get("lifecycle_state")
                    or AgentInstanceLifecycleState.COLD.value
                )
            ),
            active_run_id=_clean_text(instance_payload.get("active_run_id")) or None,
            current_workspace_id=_clean_text(instance_payload.get("current_workspace_id")) or None,
            current_session_id=_clean_text(instance_payload.get("current_session_id")) or None,
            current_workspace_attachment_id=(
                _clean_text(instance_payload.get("current_workspace_attachment_id")) or None
            ),
            current_session_attachment_id=(
                _clean_text(instance_payload.get("current_session_attachment_id")) or None
            ),
            checkpoint_head_id=_clean_text(instance_payload.get("checkpoint_head_id")) or None,
            journal_head_seq=max(0, int(instance_payload.get("journal_head_seq") or 0)),
            interrupt_requested=bool(instance_payload.get("interrupt_requested", False)),
            cancel_requested=bool(instance_payload.get("cancel_requested", False)),
            pending_wait_kind=RunWaitKind(
                str(instance_payload.get("pending_wait_kind") or RunWaitKind.NONE.value)
            ),
            pending_wait_id=_clean_text(instance_payload.get("pending_wait_id")) or None,
            restored_from_checkpoint_id=(
                _clean_text(instance_payload.get("restored_from_checkpoint_id")) or None
            ),
            created_at=_parse_datetime(instance_payload.get("created_at")),
            updated_at=_parse_datetime(instance_payload.get("updated_at")),
            retired_at=_parse_datetime(instance_payload.get("retired_at")),
        )
        run = Run(
            run_id=_clean_text(run_payload.get("run_id")) or "",
            agent_instance_id=_clean_text(run_payload.get("agent_instance_id")) or "",
            agent_profile_id=_clean_text(run_payload.get("agent_profile_id")) or "",
            workspace_id=_clean_text(run_payload.get("workspace_id")) or "",
            session_id=_clean_text(run_payload.get("session_id")) or "",
            trigger_source=_clean_text(run_payload.get("trigger_source")) or "",
            status=RunStatus(str(run_payload.get("status") or RunStatus.QUEUED.value)),
            phase=RunPhase(str(run_payload.get("phase") or RunPhase.CREATED.value)),
            step_index=max(0, int(run_payload.get("step_index") or 0)),
            waiting_reason=_clean_text(run_payload.get("waiting_reason")) or None,
            interrupt_state=RunInterruptState(
                str(run_payload.get("interrupt_state") or RunInterruptState.NONE.value)
            ),
            terminal_reason=_clean_text(run_payload.get("terminal_reason")) or None,
            workspace_attachment_id=(
                _clean_text(run_payload.get("workspace_attachment_id")) or None
            ),
            session_attachment_id=_clean_text(run_payload.get("session_attachment_id")) or None,
            capability_snapshot_id=_clean_text(run_payload.get("capability_snapshot_id")) or None,
            active_checkpoint_id=_clean_text(run_payload.get("active_checkpoint_id")) or None,
            last_checkpoint_seq=max(0, int(run_payload.get("last_checkpoint_seq") or 0)),
            journal_stream_id=_clean_text(run_payload.get("journal_stream_id")) or None,
            restorable=bool(run_payload.get("restorable", True)),
            created_at=_parse_datetime(run_payload.get("created_at")),
            started_at=_parse_datetime(run_payload.get("started_at")),
            updated_at=_parse_datetime(run_payload.get("updated_at")),
            ended_at=_parse_datetime(run_payload.get("ended_at")),
            last_error_code=_clean_text(run_payload.get("last_error_code")) or None,
            last_error_summary=_clean_text(run_payload.get("last_error_summary")) or None,
            last_model_request_id=_clean_text(run_payload.get("last_model_request_id")) or None,
            last_tool_batch_id=_clean_text(run_payload.get("last_tool_batch_id")) or None,
            last_mutation_ledger_seq=(
                int(run_payload.get("last_mutation_ledger_seq"))
                if run_payload.get("last_mutation_ledger_seq") is not None
                else None
            ),
        )
        workspace_attachment = WorkspaceAttachment(
            workspace_attachment_id=(
                _clean_text(workspace_attachment_payload.get("workspace_attachment_id")) or ""
            ),
            workspace_id=_clean_text(workspace_attachment_payload.get("workspace_id")) or "",
            workspace_kind=WorkspaceKind(
                str(
                    workspace_attachment_payload.get("workspace_kind")
                    or WorkspaceKind.PROJECT.value
                )
            ),
            root_dir=_clean_text(workspace_attachment_payload.get("root_dir")) or "",
            runtime_backend=WorkspaceRuntimeBackend(
                str(
                    workspace_attachment_payload.get("runtime_backend")
                    or WorkspaceRuntimeBackend.DIRECT.value
                )
            ),
            runtime_ref=_clean_text(workspace_attachment_payload.get("runtime_ref")) or "",
            boundary_manifest_hash=(
                _clean_text(workspace_attachment_payload.get("boundary_manifest_hash")) or ""
            ),
            permission_table_ref=(
                _clean_text(workspace_attachment_payload.get("permission_table_ref")) or ""
            ),
            outside_zone_policy_ref=(
                _clean_text(workspace_attachment_payload.get("outside_zone_policy_ref")) or ""
            ),
            mutation_ledger_ref=(
                _clean_text(workspace_attachment_payload.get("mutation_ledger_ref")) or ""
            ),
            mounted_at=_parse_datetime(workspace_attachment_payload.get("mounted_at")),
            snapshot_strategy=_clean_text(workspace_attachment_payload.get("snapshot_strategy")) or None,
            network_policy_ref=(
                _clean_text(workspace_attachment_payload.get("network_policy_ref")) or None
            ),
            resource_policy_ref=(
                _clean_text(workspace_attachment_payload.get("resource_policy_ref")) or None
            ),
            attachment_note=_clean_text(workspace_attachment_payload.get("attachment_note")) or None,
        )
        session_attachment = SessionAttachment(
            session_attachment_id=(
                _clean_text(session_attachment_payload.get("session_attachment_id")) or ""
            ),
            session_id=_clean_text(session_attachment_payload.get("session_id")) or "",
            workspace_id=_clean_text(session_attachment_payload.get("workspace_id")) or "",
            transcript_ref=_clean_text(session_attachment_payload.get("transcript_ref")) or "",
            session_memory_ref=(
                _clean_text(session_attachment_payload.get("session_memory_ref")) or ""
            ),
            approval_scope_ref=(
                _clean_text(session_attachment_payload.get("approval_scope_ref")) or ""
            ),
            context_policy_ref=(
                _clean_text(session_attachment_payload.get("context_policy_ref")) or ""
            ),
            lineage_ref=_clean_text(session_attachment_payload.get("lineage_ref")) or "",
            attached_at=_parse_datetime(session_attachment_payload.get("attached_at")),
            task_summary_ref=_clean_text(session_attachment_payload.get("task_summary_ref")) or None,
            recovery_context_ref=(
                _clean_text(session_attachment_payload.get("recovery_context_ref")) or None
            ),
            operator_override_ref=(
                _clean_text(session_attachment_payload.get("operator_override_ref")) or None
            ),
            attachment_note=_clean_text(session_attachment_payload.get("attachment_note")) or None,
        )
        capability_snapshot = CapabilitySnapshot(
            capability_snapshot_id=(
                _clean_text(capability_snapshot_payload.get("capability_snapshot_id")) or ""
            ),
            agent_profile_id=(
                _clean_text(capability_snapshot_payload.get("agent_profile_id")) or ""
            ),
            agent_instance_id=(
                _clean_text(capability_snapshot_payload.get("agent_instance_id")) or ""
            ),
            run_id=_clean_text(capability_snapshot_payload.get("run_id")) or "",
            workspace_id=_clean_text(capability_snapshot_payload.get("workspace_id")) or "",
            session_id=_clean_text(capability_snapshot_payload.get("session_id")) or "",
            resolved_tool_names=tuple(capability_snapshot_payload.get("resolved_tool_names") or ()),
            resolved_tool_policies=dict(
                capability_snapshot_payload.get("resolved_tool_policies") or {}
            ),
            visible_skill_names=tuple(capability_snapshot_payload.get("visible_skill_names") or ()),
            visible_memory_scopes=tuple(
                capability_snapshot_payload.get("visible_memory_scopes") or ()
            ),
            enabled_external_capabilities=tuple(
                capability_snapshot_payload.get("enabled_external_capabilities") or ()
            ),
            agent_model_provider_id=(
                _clean_text(capability_snapshot_payload.get("agent_model_provider_id")) or None
            ),
            agent_model_id=_clean_text(capability_snapshot_payload.get("agent_model_id")) or None,
            agent_model_capability_profile=dict(
                capability_snapshot_payload.get("agent_model_capability_profile") or {}
            ),
            workspace_runtime_mode=(
                _clean_text(capability_snapshot_payload.get("workspace_runtime_mode")) or None
            ),
            approval_profile=dict(capability_snapshot_payload.get("approval_profile") or {}),
            context_policy=dict(capability_snapshot_payload.get("context_policy") or {}),
            refresh_reason=_clean_text(capability_snapshot_payload.get("refresh_reason")) or None,
            created_at=_parse_datetime(capability_snapshot_payload.get("created_at")),
            revision=max(1, int(capability_snapshot_payload.get("revision") or 1)),
        )

        checkpoint_payload = payload.get("checkpoint")
        checkpoint = None
        if isinstance(checkpoint_payload, dict):
            checkpoint = Checkpoint(
                checkpoint_id=_clean_text(checkpoint_payload.get("checkpoint_id")) or "",
                run_id=_clean_text(checkpoint_payload.get("run_id")) or "",
                agent_instance_id=_clean_text(checkpoint_payload.get("agent_instance_id")) or "",
                checkpoint_seq=max(0, int(checkpoint_payload.get("checkpoint_seq") or 0)),
                checkpoint_type=CheckpointType(
                    str(checkpoint_payload.get("checkpoint_type") or CheckpointType.BOOTSTRAP.value)
                ),
                status=RunStatus(str(checkpoint_payload.get("status") or RunStatus.QUEUED.value)),
                phase=RunPhase(str(checkpoint_payload.get("phase") or RunPhase.CREATED.value)),
                step_index=max(0, int(checkpoint_payload.get("step_index") or 0)),
                workspace_attachment_id=(
                    _clean_text(checkpoint_payload.get("workspace_attachment_id")) or ""
                ),
                session_attachment_id=(
                    _clean_text(checkpoint_payload.get("session_attachment_id")) or ""
                ),
                capability_snapshot_hash=(
                    _clean_text(checkpoint_payload.get("capability_snapshot_hash")) or ""
                ),
                journal_offset=max(0, int(checkpoint_payload.get("journal_offset") or 0)),
                waiting_reason=_clean_text(checkpoint_payload.get("waiting_reason")) or None,
                resume_token=_clean_text(checkpoint_payload.get("resume_token")) or None,
                created_at=_parse_datetime(checkpoint_payload.get("created_at")),
                schema_version=_clean_text(checkpoint_payload.get("schema_version")) or "v11.1",
                last_model_turn_ref=_clean_text(checkpoint_payload.get("last_model_turn_ref")) or None,
                last_tool_batch_ref=_clean_text(checkpoint_payload.get("last_tool_batch_ref")) or None,
                last_mutation_ledger_seq=(
                    int(checkpoint_payload.get("last_mutation_ledger_seq"))
                    if checkpoint_payload.get("last_mutation_ledger_seq") is not None
                    else None
                ),
                recovery_context_ref=_clean_text(checkpoint_payload.get("recovery_context_ref")) or None,
                error_ref=_clean_text(checkpoint_payload.get("error_ref")) or None,
                recoverable=bool(checkpoint_payload.get("recoverable", True)),
            )

        journal_events_payload = journal_payload.get("events")
        journal_events: list[ExecutionJournalEvent] = []
        if isinstance(journal_events_payload, list):
            for item in journal_events_payload:
                if not isinstance(item, dict):
                    return None
                journal_events.append(
                    ExecutionJournalEvent(
                        event_seq=max(1, int(item.get("event_seq") or 1)),
                        event_type=_clean_text(item.get("event_type")) or "",
                        run_id=_clean_text(item.get("run_id")) or "",
                        agent_instance_id=_clean_text(item.get("agent_instance_id")) or "",
                        workspace_id=_clean_text(item.get("workspace_id")) or "",
                        session_id=_clean_text(item.get("session_id")) or "",
                        status=RunStatus(str(item.get("status") or RunStatus.QUEUED.value)),
                        phase=RunPhase(str(item.get("phase") or RunPhase.CREATED.value)),
                        step_index=max(0, int(item.get("step_index") or 0)),
                        event_ts=_parse_datetime(item.get("event_ts")),
                        correlation_id=_clean_text(item.get("correlation_id")) or None,
                        causation_id=_clean_text(item.get("causation_id")) or None,
                        payload=dict(item.get("payload") or {}),
                    )
                )
        execution_journal = ExecutionJournal(
            journal_stream_id=_clean_text(journal_payload.get("journal_stream_id")) or "",
            run_id=_clean_text(journal_payload.get("run_id")) or "",
            agent_instance_id=_clean_text(journal_payload.get("agent_instance_id")) or "",
            workspace_id=_clean_text(journal_payload.get("workspace_id")) or "",
            session_id=_clean_text(journal_payload.get("session_id")) or "",
            events=tuple(journal_events),
            created_at=_parse_datetime(journal_payload.get("created_at")),
            closed_at=_parse_datetime(journal_payload.get("closed_at")),
        )
        run_control = deserialize_run_control_state(payload.get("run_control"))
        if run_control is None:
            return None
        return AgentKernelStateRecord(
            run_id=run.run_id,
            session_id=run.session_id,
            agent_profile=agent_profile,
            agent_instance=agent_instance,
            run=run,
            workspace_attachment=workspace_attachment,
            session_attachment=session_attachment,
            capability_snapshot=capability_snapshot,
            execution_journal=execution_journal,
            run_control=run_control,
            approval_wait=deserialize_approval_wait(payload.get("approval_wait")),
            checkpoint=checkpoint,
        )
    except Exception:
        return None


__all__ = [
    "AgentKernelStateRecord",
    "AgentKernelStateSeed",
    "deserialize_agent_kernel_state_record",
    "deserialize_approval_wait",
    "deserialize_run_control_state",
    "build_agent_instance",
    "build_agent_kernel_state_record",
    "build_agent_profile",
    "build_capability_snapshot",
    "build_checkpoint_for_record",
    "build_run",
    "build_session_attachment",
    "build_workspace_attachment",
    "serialize_agent_kernel_state_record",
    "serialize_approval_wait",
    "serialize_run_control_state",
]
