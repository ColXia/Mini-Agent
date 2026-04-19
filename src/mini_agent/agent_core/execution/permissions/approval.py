"""Approval engine with cache and escalation support."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json

from mini_agent.agent_core.execution.permissions.policy import PermissionDecision, PermissionPolicy
from mini_agent.agent_core.execution.tools.invocation import ToolInvocation


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def invocation_fingerprint(invocation: ToolInvocation) -> str:
    payload = {
        "tool_name": invocation.tool_name,
        "arguments": invocation.arguments,
        "kind": invocation.attributes.kind.value,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApprovalOutcome:
    """Approval decision payload."""

    decision: PermissionDecision
    reason: str
    requires_confirmation: bool = False
    from_cache: bool = False
    cache_key: str | None = None
    can_escalate: bool = False
    escalated: bool = False


@dataclass
class _CacheEntry:
    decision: PermissionDecision
    expires_at: datetime


class ApprovalCache:
    """Small in-memory approval cache keyed by invocation fingerprint."""

    def __init__(self, *, ttl_seconds: int = 1800, max_entries: int = 512) -> None:
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.max_entries = max(8, int(max_entries))
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> PermissionDecision | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= _utc_now():
            self._entries.pop(key, None)
            return None
        return entry.decision

    def set(self, key: str, decision: PermissionDecision) -> None:
        if len(self._entries) >= self.max_entries:
            oldest_key = min(self._entries, key=lambda item: self._entries[item].expires_at)
            self._entries.pop(oldest_key, None)
        self._entries[key] = _CacheEntry(
            decision=decision,
            expires_at=_utc_now() + timedelta(seconds=self.ttl_seconds),
        )

    def clear(self) -> None:
        self._entries.clear()


class ApprovalEngine:
    """Policy + cache based approval decision engine."""

    def __init__(
        self,
        policy: PermissionPolicy | None = None,
        *,
        cache: ApprovalCache | None = None,
    ) -> None:
        self.policy = policy or PermissionPolicy.strict_policy()
        self.cache = cache or ApprovalCache()

    def evaluate(self, invocation: ToolInvocation) -> ApprovalOutcome:
        decision = self.policy.evaluate_invocation(invocation)
        cache_key = invocation_fingerprint(invocation)

        if decision == PermissionDecision.ALLOW:
            return ApprovalOutcome(
                decision=PermissionDecision.ALLOW,
                reason="allowed_by_policy",
                requires_confirmation=False,
                cache_key=cache_key,
            )

        if decision == PermissionDecision.DENY:
            return ApprovalOutcome(
                decision=PermissionDecision.DENY,
                reason="denied_by_policy",
                requires_confirmation=False,
                cache_key=cache_key,
                can_escalate=self.policy.can_escalate(invocation),
            )

        cached = self.cache.get(cache_key)
        if cached is not None:
            return ApprovalOutcome(
                decision=cached,
                reason="approval_cache_hit",
                requires_confirmation=False,
                from_cache=True,
                cache_key=cache_key,
            )

        return ApprovalOutcome(
            decision=PermissionDecision.ASK,
            reason="requires_user_confirmation",
            requires_confirmation=True,
            cache_key=cache_key,
            can_escalate=self.policy.can_escalate(invocation),
        )

    def record_user_decision(
        self,
        invocation: ToolInvocation,
        decision: PermissionDecision,
        *,
        cache_decision: bool = True,
    ) -> ApprovalOutcome:
        cache_key = invocation_fingerprint(invocation)
        if cache_decision and decision in {PermissionDecision.ALLOW, PermissionDecision.DENY}:
            self.cache.set(cache_key, decision)
        return ApprovalOutcome(
            decision=decision,
            reason="recorded_user_decision",
            requires_confirmation=False,
            cache_key=cache_key,
        )

    def request_escalation(self, invocation: ToolInvocation, *, reason: str = "manual_escalation") -> ApprovalOutcome:
        if not self.policy.can_escalate(invocation):
            return ApprovalOutcome(
                decision=PermissionDecision.DENY,
                reason="escalation_not_supported",
                requires_confirmation=False,
                can_escalate=False,
            )
        return ApprovalOutcome(
            decision=PermissionDecision.ASK,
            reason=reason,
            requires_confirmation=True,
            can_escalate=True,
            escalated=True,
            cache_key=invocation_fingerprint(invocation),
        )
