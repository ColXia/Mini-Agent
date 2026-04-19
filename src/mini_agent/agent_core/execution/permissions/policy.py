"""Permission policy model for agent-core execution tool approvals."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import fnmatch

from mini_agent.agent_core.execution.tools.attributes import ToolKind
from mini_agent.agent_core.execution.tools.invocation import ToolInvocation


class PermissionDecision(str, Enum):
    """Decision modes for permission checks."""

    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass(frozen=True)
class PermissionRule:
    """Ordered permission rule matched against tool metadata."""

    tool_pattern: str = "*"
    decision: PermissionDecision = PermissionDecision.ASK
    kind: ToolKind | None = None
    reason: str | None = None

    def matches(self, invocation: ToolInvocation) -> bool:
        if self.kind is not None and invocation.attributes.kind != self.kind:
            return False
        return fnmatch.fnmatch(invocation.tool_name, self.tool_pattern)


@dataclass(frozen=True)
class PermissionPolicy:
    """Layered ask/allow/deny policy with optional unrestricted bypass."""

    default_decision: PermissionDecision = PermissionDecision.ASK
    rules: tuple[PermissionRule, ...] = field(default_factory=tuple)
    full_auto: bool = False

    @staticmethod
    def full_auto_policy() -> "PermissionPolicy":
        return PermissionPolicy(default_decision=PermissionDecision.ALLOW, full_auto=True)

    @staticmethod
    def strict_policy() -> "PermissionPolicy":
        return PermissionPolicy(default_decision=PermissionDecision.ASK)

    def evaluate_invocation(self, invocation: ToolInvocation) -> PermissionDecision:
        if self.full_auto:
            return PermissionDecision.ALLOW

        for rule in self.rules:
            if rule.matches(invocation):
                return rule.decision

        if invocation.attributes.is_read_only:
            return PermissionDecision.ALLOW

        return self.default_decision

    def can_escalate(self, invocation: ToolInvocation) -> bool:
        return invocation.attributes.kind in {
            ToolKind.WRITE,
            ToolKind.EDIT,
            ToolKind.DELETE,
            ToolKind.EXECUTE,
            ToolKind.NETWORK,
            ToolKind.DELEGATE,
        }
