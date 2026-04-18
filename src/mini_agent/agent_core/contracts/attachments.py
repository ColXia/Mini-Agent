"""Run attachment contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from ._common import clean_text, utc_now


class WorkspaceKind(str, Enum):
    """Kinds of workspace supported by v11.1."""

    DEFAULT = "default"
    PROJECT = "project"


class WorkspaceRuntimeBackend(str, Enum):
    """Runtime backends supported by a workspace attachment."""

    DIRECT = "direct"
    CONTAINER_MOUNTED = "container_mounted"
    ISOLATED_COPY = "isolated_copy"


@dataclass(frozen=True, slots=True)
class WorkspaceAttachment:
    """Reference-based binding between one run and one workspace execution world."""

    workspace_attachment_id: str
    workspace_id: str
    workspace_kind: WorkspaceKind
    root_dir: str
    runtime_backend: WorkspaceRuntimeBackend
    runtime_ref: str
    boundary_manifest_hash: str
    permission_table_ref: str
    outside_zone_policy_ref: str
    mutation_ledger_ref: str
    mounted_at: datetime | None = None
    snapshot_strategy: str | None = None
    network_policy_ref: str | None = None
    resource_policy_ref: str | None = None
    attachment_note: str | None = None

    def __post_init__(self) -> None:
        required_fields = {
            "workspace_attachment_id": clean_text(self.workspace_attachment_id),
            "workspace_id": clean_text(self.workspace_id),
            "root_dir": clean_text(self.root_dir),
            "runtime_ref": clean_text(self.runtime_ref),
            "boundary_manifest_hash": clean_text(self.boundary_manifest_hash),
            "permission_table_ref": clean_text(self.permission_table_ref),
            "outside_zone_policy_ref": clean_text(self.outside_zone_policy_ref),
            "mutation_ledger_ref": clean_text(self.mutation_ledger_ref),
        }
        for field_name, value in required_fields.items():
            if not value:
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "snapshot_strategy", clean_text(self.snapshot_strategy))
        object.__setattr__(self, "network_policy_ref", clean_text(self.network_policy_ref))
        object.__setattr__(self, "resource_policy_ref", clean_text(self.resource_policy_ref))
        object.__setattr__(self, "attachment_note", clean_text(self.attachment_note))
        if self.mounted_at is None:
            object.__setattr__(self, "mounted_at", utc_now())

    @property
    def root_path(self) -> Path:
        return Path(self.root_dir)


@dataclass(frozen=True, slots=True)
class SessionAttachment:
    """Reference-based binding between one run and one task container."""

    session_attachment_id: str
    session_id: str
    workspace_id: str
    transcript_ref: str
    session_memory_ref: str
    approval_scope_ref: str
    context_policy_ref: str
    lineage_ref: str
    attached_at: datetime | None = None
    task_summary_ref: str | None = None
    recovery_context_ref: str | None = None
    operator_override_ref: str | None = None
    attachment_note: str | None = None

    def __post_init__(self) -> None:
        required_fields = {
            "session_attachment_id": clean_text(self.session_attachment_id),
            "session_id": clean_text(self.session_id),
            "workspace_id": clean_text(self.workspace_id),
            "transcript_ref": clean_text(self.transcript_ref),
            "session_memory_ref": clean_text(self.session_memory_ref),
            "approval_scope_ref": clean_text(self.approval_scope_ref),
            "context_policy_ref": clean_text(self.context_policy_ref),
            "lineage_ref": clean_text(self.lineage_ref),
        }
        for field_name, value in required_fields.items():
            if not value:
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "task_summary_ref", clean_text(self.task_summary_ref))
        object.__setattr__(self, "recovery_context_ref", clean_text(self.recovery_context_ref))
        object.__setattr__(self, "operator_override_ref", clean_text(self.operator_override_ref))
        object.__setattr__(self, "attachment_note", clean_text(self.attachment_note))
        if self.attached_at is None:
            object.__setattr__(self, "attached_at", utc_now())


__all__ = [
    "SessionAttachment",
    "WorkspaceAttachment",
    "WorkspaceKind",
    "WorkspaceRuntimeBackend",
]

