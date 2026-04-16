"""Tests for P14 T2.7 permission baseline."""

from __future__ import annotations

from mini_agent.agent_core.execution import (
    ApprovalEngine,
    PermissionDecision,
    PermissionPolicy,
    PermissionRule,
    ToolBuilder,
    ToolKind,
)
from mini_agent.agent_core.execution.tools import DeclarativeToolAttributes
from mini_agent.tools.base import ToolResult


def _build_invocation(
    *,
    tool_name: str,
    kind: ToolKind,
    is_read_only: bool,
    arguments: dict | None = None,
):
    declarative = ToolBuilder.from_callable(
        name=tool_name,
        description=f"tool {tool_name}",
        schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        execute=lambda _args: ToolResult(success=True, content="ok"),
        attributes=DeclarativeToolAttributes(kind=kind, is_read_only=is_read_only),
    )
    return declarative.build(arguments or {"value": "x"})


def test_permission_policy_allows_read_only_by_default():
    invocation = _build_invocation(tool_name="read_file", kind=ToolKind.READ, is_read_only=True)
    policy = PermissionPolicy.strict_policy()
    assert policy.evaluate_invocation(invocation) == PermissionDecision.ALLOW


def test_permission_policy_rule_denies_tool_pattern():
    invocation = _build_invocation(tool_name="bash", kind=ToolKind.EXECUTE, is_read_only=False)
    policy = PermissionPolicy(
        default_decision=PermissionDecision.ASK,
        rules=(PermissionRule(tool_pattern="bash*", decision=PermissionDecision.DENY),),
    )
    assert policy.evaluate_invocation(invocation) == PermissionDecision.DENY


def test_approval_engine_uses_cache_for_repeated_invocation():
    invocation = _build_invocation(tool_name="write_file", kind=ToolKind.WRITE, is_read_only=False)
    engine = ApprovalEngine(PermissionPolicy.strict_policy())

    first = engine.evaluate(invocation)
    assert first.decision == PermissionDecision.ASK
    assert first.requires_confirmation is True

    engine.record_user_decision(invocation, PermissionDecision.ALLOW)
    second = engine.evaluate(invocation)
    assert second.decision == PermissionDecision.ALLOW
    assert second.from_cache is True


def test_approval_engine_denied_decision_can_escalate_for_execute_tools():
    invocation = _build_invocation(tool_name="bash", kind=ToolKind.EXECUTE, is_read_only=False)
    policy = PermissionPolicy(
        default_decision=PermissionDecision.ASK,
        rules=(PermissionRule(tool_pattern="bash", decision=PermissionDecision.DENY),),
    )
    engine = ApprovalEngine(policy)

    denied = engine.evaluate(invocation)
    assert denied.decision == PermissionDecision.DENY
    assert denied.can_escalate is True

    escalated = engine.request_escalation(invocation, reason="retry_with_elevation")
    assert escalated.decision == PermissionDecision.ASK
    assert escalated.escalated is True
    assert escalated.requires_confirmation is True


def test_full_auto_policy_allows_without_confirmation():
    invocation = _build_invocation(tool_name="bash", kind=ToolKind.EXECUTE, is_read_only=False)
    engine = ApprovalEngine(PermissionPolicy.full_auto_policy())
    outcome = engine.evaluate(invocation)
    assert outcome.decision == PermissionDecision.ALLOW
    assert outcome.requires_confirmation is False
