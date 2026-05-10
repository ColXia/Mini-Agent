"""Tool system contracts for v11.2 capability system.

This module defines the core objects for tool capability management:
- ToolSpec: Tool definition and metadata
- ToolBinding: Runtime execution binding
- ToolPolicy: Permission control result
- ToolGrant: Temporary authorization grant
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from mini_agent.utils.text import safe_text


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_text(value: Any) -> str:
    return safe_text(value)


class ToolOperationKind(str, Enum):
    """Operation kinds for tool classification."""

    READ = "read"
    WRITE = "write"
    EDIT = "edit"
    EXECUTE = "execute"
    QUERY = "query"
    EXTERNAL = "external"


class ToolRiskLevel(str, Enum):
    """Risk levels for tool operations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolPolicyDecision(str, Enum):
    """Permission decisions for tool execution."""

    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"
    CONSTRAINT_REWRITE = "constraint_rewrite"


class GrantSource(str, Enum):
    """Sources of tool authorization grants."""

    USER_APPROVAL = "user_approval"
    POLICY_RULE = "policy_rule"
    DELEGATION = "delegation"
    SYSTEM_OVERRIDE = "system_override"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Tool definition and capability metadata.

    This is the static definition of a tool's capabilities and constraints.
    It belongs to the Agent's capability catalog, not to any workspace.
    """

    tool_name: str
    namespace: str
    description: str
    operation_kind: ToolOperationKind
    requires_workspace_runtime: bool = True
    supports_outside_workspace: bool = False
    supports_mutation_tracking: bool = True
    default_risk_level: ToolRiskLevel = ToolRiskLevel.MEDIUM
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_name = _safe_text(self.tool_name)
        normalized_namespace = _safe_text(self.namespace)
        if not normalized_name:
            raise ValueError("tool_name is required")
        if not normalized_namespace:
            raise ValueError("namespace is required")
        object.__setattr__(self, "tool_name", normalized_name)
        object.__setattr__(self, "namespace", normalized_namespace)
        object.__setattr__(self, "description", _safe_text(self.description))
        object.__setattr__(self, "input_schema", dict(self.input_schema) if self.input_schema else {})
        object.__setattr__(self, "output_schema", dict(self.output_schema) if self.output_schema else {})
        object.__setattr__(self, "metadata", dict(self.metadata) if self.metadata else {})

    @property
    def full_name(self) -> str:
        """Return the fully qualified tool name."""
        return f"{self.namespace}.{self.tool_name}"

    @property
    def is_mutation(self) -> bool:
        """Return True if this tool can mutate workspace state."""
        return self.operation_kind in {
            ToolOperationKind.WRITE,
            ToolOperationKind.EDIT,
            ToolOperationKind.EXECUTE,
        }


@dataclass(frozen=True, slots=True)
class ToolBinding:
    """Runtime execution binding for a tool.

    This represents the resolved execution context for a tool within a specific
    run. It binds the tool to a workspace runtime and defines the execution scope.
    """

    binding_id: str
    tool_name: str
    workspace_id: str
    run_id: str
    runtime_backend: str = "direct"
    resolved_path_scope: str | None = None
    resolved_limits: dict[str, Any] = field(default_factory=dict)
    binding_valid_until: datetime | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        required_fields = {
            "binding_id": _safe_text(self.binding_id),
            "tool_name": _safe_text(self.tool_name),
            "workspace_id": _safe_text(self.workspace_id),
            "run_id": _safe_text(self.run_id),
        }
        for field_name, value in required_fields.items():
            if not value:
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "runtime_backend", _safe_text(self.runtime_backend) or "direct")
        object.__setattr__(self, "resolved_path_scope", _safe_text(self.resolved_path_scope))
        object.__setattr__(self, "resolved_limits", dict(self.resolved_limits) if self.resolved_limits else {})
        if self.created_at is None:
            object.__setattr__(self, "created_at", _utc_now())

    @property
    def is_valid(self) -> bool:
        """Return True if this binding is still valid."""
        if self.binding_valid_until is None:
            return True
        return datetime.now(timezone.utc) < self.binding_valid_until


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    """Permission control result for tool execution.

    This represents the PermissionEngine's decision for a tool execution request.
    It may allow, deny, require approval, or rewrite execution constraints.
    """

    policy_id: str
    tool_name: str
    decision: ToolPolicyDecision
    workspace_id: str
    session_id: str
    run_id: str | None = None
    path_policy: dict[str, Any] = field(default_factory=dict)
    network_policy: dict[str, Any] = field(default_factory=dict)
    resource_policy: dict[str, Any] = field(default_factory=dict)
    timeout_override: int | None = None
    mutation_tracking_mode: str = "enabled"
    reason: str | None = None
    constraint_rewrite: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        required_fields = {
            "policy_id": _safe_text(self.policy_id),
            "tool_name": _safe_text(self.tool_name),
            "workspace_id": _safe_text(self.workspace_id),
            "session_id": _safe_text(self.session_id),
        }
        for field_name, value in required_fields.items():
            if not value:
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "path_policy", dict(self.path_policy) if self.path_policy else {})
        object.__setattr__(self, "network_policy", dict(self.network_policy) if self.network_policy else {})
        object.__setattr__(self, "resource_policy", dict(self.resource_policy) if self.resource_policy else {})
        object.__setattr__(self, "mutation_tracking_mode", _safe_text(self.mutation_tracking_mode) or "enabled")
        object.__setattr__(self, "reason", _safe_text(self.reason))
        object.__setattr__(self, "constraint_rewrite", dict(self.constraint_rewrite) if self.constraint_rewrite else {})
        if self.created_at is None:
            object.__setattr__(self, "created_at", _utc_now())

    @property
    def is_allowed(self) -> bool:
        """Return True if the tool execution is allowed."""
        return self.decision == ToolPolicyDecision.ALLOW

    @property
    def requires_approval(self) -> bool:
        """Return True if the tool execution requires user approval."""
        return self.decision == ToolPolicyDecision.APPROVAL_REQUIRED

    @property
    def has_constraints(self) -> bool:
        """Return True if execution constraints were rewritten."""
        return self.decision == ToolPolicyDecision.CONSTRAINT_REWRITE and bool(self.constraint_rewrite)


@dataclass(frozen=True, slots=True)
class ToolGrant:
    """Temporary authorization grant for tool execution.

    This represents an approval or policy-based authorization for a specific
    tool execution. Grants are issued by user approval or policy rules.
    """

    grant_id: str
    tool_name: str
    workspace_id: str
    session_id: str
    run_id: str
    granted_scope: dict[str, Any] = field(default_factory=dict)
    grant_source: GrantSource = GrantSource.USER_APPROVAL
    expires_at: datetime | None = None
    created_at: datetime | None = None
    granted_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required_fields = {
            "grant_id": _safe_text(self.grant_id),
            "tool_name": _safe_text(self.tool_name),
            "workspace_id": _safe_text(self.workspace_id),
            "session_id": _safe_text(self.session_id),
            "run_id": _safe_text(self.run_id),
        }
        for field_name, value in required_fields.items():
            if not value:
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "granted_scope", dict(self.granted_scope) if self.granted_scope else {})
        object.__setattr__(self, "granted_by", _safe_text(self.granted_by))
        object.__setattr__(self, "metadata", dict(self.metadata) if self.metadata else {})
        if self.created_at is None:
            object.__setattr__(self, "created_at", _utc_now())

    @property
    def is_expired(self) -> bool:
        """Return True if this grant has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def is_valid(self) -> bool:
        """Return True if this grant is still valid."""
        return not self.is_expired

    @property
    def is_run_scoped(self) -> bool:
        """Return True if this grant is scoped to a single run."""
        return bool(self.run_id)


__all__ = [
    "GrantSource",
    "ToolBinding",
    "ToolGrant",
    "ToolOperationKind",
    "ToolPolicy",
    "ToolPolicyDecision",
    "ToolRiskLevel",
    "ToolSpec",
]
