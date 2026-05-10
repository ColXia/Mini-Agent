"""Permission engine for tool execution control.

This module provides the PermissionEngine for evaluating tool execution requests
and producing ToolPolicy decisions. It implements the constraint rewrite capability
for fine-grained execution control.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from mini_agent.tools.contracts import (
    ToolGrant,
    ToolOperationKind,
    ToolPolicy,
    ToolPolicyDecision,
    ToolRiskLevel,
    ToolSpec,
)
from mini_agent.utils.text import safe_text
from mini_agent.workspace_runtime.boundary import WorkspaceBoundary


def _safe_text(value: Any) -> str:
    return safe_text(value)


def _generate_id() -> str:
    return uuid.uuid4().hex[:16]


@dataclass(frozen=True, slots=True)
class PermissionRequest:
    """Request for tool execution permission."""

    tool_name: str
    workspace_id: str
    session_id: str
    run_id: str | None = None
    target_paths: tuple[str, ...] = ()
    execution_mode: str = "direct"
    arguments: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OutsideZonePolicy:
    """Policy for accessing paths outside the attached workspace."""

    allow_read: bool = True
    require_approval_for_write: bool = True
    deny_delete: bool = True
    blacklist_paths: tuple[str, ...] = ()
    whitelist_paths: tuple[str, ...] = ()

    def is_blacklisted(self, path: str | Path) -> bool:
        """Check if a path is in the blacklist."""
        try:
            normalized = str(Path(path).expanduser().resolve(strict=False)).lower()
        except Exception:
            normalized = str(path).lower()
        for blacklisted in self.blacklist_paths:
            if normalized.startswith(blacklisted.lower()):
                return True
        return False

    def is_whitelisted(self, path: str | Path) -> bool:
        """Check if a path is in the whitelist."""
        try:
            normalized = str(Path(path).expanduser().resolve(strict=False)).lower()
        except Exception:
            normalized = str(path).lower()
        for whitelisted in self.whitelist_paths:
            if normalized.startswith(whitelisted.lower()):
                return True
        return False


DEFAULT_OUTSIDE_ZONE_POLICY = OutsideZonePolicy(
    allow_read=True,
    require_approval_for_write=True,
    deny_delete=True,
    blacklist_paths=(
        "/etc",
        "/sys",
        "/proc",
        "C:\\Windows",
        "C:\\Program Files",
    ),
)


@dataclass(slots=True)
class PermissionEngine:
    """Engine for evaluating tool execution permissions.

    This engine evaluates tool execution requests against workspace boundaries,
    risk levels, and outside-zone policies to produce ToolPolicy decisions.
    It supports constraint rewriting for fine-grained execution control.
    """

    workspace_boundary: WorkspaceBoundary | None = None
    outside_zone_policy: OutsideZonePolicy = DEFAULT_OUTSIDE_ZONE_POLICY
    risk_approval_threshold: ToolRiskLevel = ToolRiskLevel.HIGH
    _active_grants: dict[str, ToolGrant] = field(default_factory=dict)

    def evaluate(self, request: PermissionRequest, spec: ToolSpec) -> ToolPolicy:
        """Evaluate a permission request for a tool.

        Args:
            request: The permission request
            spec: The tool specification

        Returns:
            A ToolPolicy with the decision and any constraints
        """
        policy_id = _generate_id()

        if self._has_valid_grant(request):
            return ToolPolicy(
                policy_id=policy_id,
                tool_name=request.tool_name,
                decision=ToolPolicyDecision.ALLOW,
                workspace_id=request.workspace_id,
                session_id=request.session_id,
                run_id=request.run_id,
                reason="Valid grant exists",
            )

        if spec.requires_workspace_runtime and self.workspace_boundary is None:
            pass

        outside_workspace = self._check_outside_workspace(request, spec)
        if outside_workspace:
            return self._evaluate_outside_zone(request, spec, policy_id)

        if self._requires_risk_approval(spec):
            return ToolPolicy(
                policy_id=policy_id,
                tool_name=request.tool_name,
                decision=ToolPolicyDecision.APPROVAL_REQUIRED,
                workspace_id=request.workspace_id,
                session_id=request.session_id,
                run_id=request.run_id,
                reason=f"Tool has risk level {spec.default_risk_level.value}, approval required",
            )

        constraints = self._compute_constraints(request, spec)
        if constraints:
            return ToolPolicy(
                policy_id=policy_id,
                tool_name=request.tool_name,
                decision=ToolPolicyDecision.CONSTRAINT_REWRITE,
                workspace_id=request.workspace_id,
                session_id=request.session_id,
                run_id=request.run_id,
                constraint_rewrite=constraints,
                reason="Execution constraints applied",
            )

        return ToolPolicy(
            policy_id=policy_id,
            tool_name=request.tool_name,
            decision=ToolPolicyDecision.ALLOW,
            workspace_id=request.workspace_id,
            session_id=request.session_id,
            run_id=request.run_id,
        )

    def issue_grant(
        self,
        tool_name: str,
        workspace_id: str,
        session_id: str,
        run_id: str,
        granted_scope: dict[str, Any] | None = None,
        expires_at: Any | None = None,
    ) -> ToolGrant:
        """Issue a new tool grant.

        Args:
            tool_name: The tool name
            workspace_id: The workspace ID
            session_id: The session ID
            run_id: The run ID
            granted_scope: Optional scope constraints
            expires_at: Optional expiration time

        Returns:
            A new ToolGrant
        """
        grant = ToolGrant(
            grant_id=_generate_id(),
            tool_name=_safe_text(tool_name),
            workspace_id=_safe_text(workspace_id),
            session_id=_safe_text(session_id),
            run_id=_safe_text(run_id),
            granted_scope=granted_scope or {},
        )
        self._active_grants[grant.grant_id] = grant
        return grant

    def revoke_grant(self, grant_id: str) -> ToolGrant | None:
        """Revoke a tool grant.

        Args:
            grant_id: The grant ID to revoke

        Returns:
            The revoked ToolGrant, or None if not found
        """
        return self._active_grants.pop(_safe_text(grant_id), None)

    def get_grant(self, grant_id: str) -> ToolGrant | None:
        """Get a tool grant by ID.

        Args:
            grant_id: The grant ID

        Returns:
            The ToolGrant, or None if not found
        """
        return self._active_grants.get(_safe_text(grant_id))

    def clear_grants(self) -> None:
        """Clear all active grants."""
        self._active_grants.clear()

    def _has_valid_grant(self, request: PermissionRequest) -> bool:
        """Check if there's a valid grant for this request."""
        for grant in self._active_grants.values():
            if grant.is_expired:
                continue
            if grant.tool_name != request.tool_name:
                continue
            if grant.workspace_id != request.workspace_id:
                continue
            if grant.session_id != request.session_id:
                continue
            if grant.run_id and grant.run_id != request.run_id:
                continue
            return True
        return False

    def _check_outside_workspace(self, request: PermissionRequest, spec: ToolSpec) -> bool:
        """Check if any target path is outside the workspace."""
        if not request.target_paths:
            return False
        if self.workspace_boundary is None:
            return True
        for path in request.target_paths:
            if not self.workspace_boundary.contains_path(path):
                return True
        return False

    def _evaluate_outside_zone(
        self,
        request: PermissionRequest,
        spec: ToolSpec,
        policy_id: str,
    ) -> ToolPolicy:
        """Evaluate access to paths outside the workspace."""
        for path in request.target_paths:
            if self.outside_zone_policy.is_blacklisted(path):
                return ToolPolicy(
                    policy_id=policy_id,
                    tool_name=request.tool_name,
                    decision=ToolPolicyDecision.DENY,
                    workspace_id=request.workspace_id,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    reason=f"Path is blacklisted: {path}",
                )

        if spec.operation_kind == ToolOperationKind.READ:
            if self.outside_zone_policy.allow_read:
                return ToolPolicy(
                    policy_id=policy_id,
                    tool_name=request.tool_name,
                    decision=ToolPolicyDecision.ALLOW,
                    workspace_id=request.workspace_id,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    reason="Outside zone read allowed",
                )
            return ToolPolicy(
                policy_id=policy_id,
                tool_name=request.tool_name,
                decision=ToolPolicyDecision.APPROVAL_REQUIRED,
                workspace_id=request.workspace_id,
                session_id=request.session_id,
                run_id=request.run_id,
                reason="Outside zone read requires approval",
            )

        if spec.operation_kind in {ToolOperationKind.WRITE, ToolOperationKind.EDIT}:
            if self.outside_zone_policy.require_approval_for_write:
                return ToolPolicy(
                    policy_id=policy_id,
                    tool_name=request.tool_name,
                    decision=ToolPolicyDecision.APPROVAL_REQUIRED,
                    workspace_id=request.workspace_id,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    reason="Outside zone write requires approval",
                )
            return ToolPolicy(
                policy_id=policy_id,
                tool_name=request.tool_name,
                decision=ToolPolicyDecision.ALLOW,
                workspace_id=request.workspace_id,
                session_id=request.session_id,
                run_id=request.run_id,
            )

        if spec.operation_kind == ToolOperationKind.EXECUTE:
            if self.outside_zone_policy.deny_delete:
                return ToolPolicy(
                    policy_id=policy_id,
                    tool_name=request.tool_name,
                    decision=ToolPolicyDecision.DENY,
                    workspace_id=request.workspace_id,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    reason="Outside zone execute denied",
                )

        return ToolPolicy(
            policy_id=policy_id,
            tool_name=request.tool_name,
            decision=ToolPolicyDecision.DENY,
            workspace_id=request.workspace_id,
            session_id=request.session_id,
            run_id=request.run_id,
            reason="Outside zone access denied by default",
        )

    def _requires_risk_approval(self, spec: ToolSpec) -> bool:
        """Check if a tool requires approval based on risk level."""
        risk_order = {
            ToolRiskLevel.LOW: 0,
            ToolRiskLevel.MEDIUM: 1,
            ToolRiskLevel.HIGH: 2,
            ToolRiskLevel.CRITICAL: 3,
        }
        return risk_order.get(spec.default_risk_level, 0) >= risk_order.get(self.risk_approval_threshold, 2)

    def _compute_constraints(self, request: PermissionRequest, spec: ToolSpec) -> dict[str, Any]:
        """Compute execution constraints for a tool."""
        constraints: dict[str, Any] = {}

        if spec.timeout_seconds is not None:
            constraints["timeout_seconds"] = spec.timeout_seconds

        if spec.operation_kind == ToolOperationKind.EXECUTE:
            constraints["require_mutation_tracking"] = True
            constraints["network_policy"] = "restricted"

        if spec.is_mutation:
            constraints["mutation_tracking_mode"] = "full"

        return constraints


__all__ = [
    "DEFAULT_OUTSIDE_ZONE_POLICY",
    "OutsideZonePolicy",
    "PermissionEngine",
    "PermissionRequest",
]