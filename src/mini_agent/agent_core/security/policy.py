"""DM/group access policy baseline with pairing integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from mini_agent.agent_core.security.pairing import PairingRequest, PairingStore


def _normalize_entries(values: Iterable[str | int]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return tuple(out)


class DmPolicyMode(str, Enum):
    """DM access policy modes."""

    OPEN = "open"
    DISABLED = "disabled"
    ALLOWLIST = "allowlist"
    PAIRING = "pairing"


class GroupPolicyMode(str, Enum):
    """Group access policy modes."""

    OPEN = "open"
    DISABLED = "disabled"
    ALLOWLIST = "allowlist"


@dataclass(frozen=True)
class AccessPolicyConfig:
    """Policy config shared by DM and group decision paths."""

    dm_mode: DmPolicyMode = DmPolicyMode.PAIRING
    group_mode: GroupPolicyMode = GroupPolicyMode.ALLOWLIST
    allow_from: tuple[str, ...] = ()
    group_allow_from: tuple[str, ...] = ()
    fallback_group_to_dm: bool = True

    def normalized(self) -> "AccessPolicyConfig":
        return AccessPolicyConfig(
            dm_mode=self.dm_mode,
            group_mode=self.group_mode,
            allow_from=_normalize_entries(self.allow_from),
            group_allow_from=_normalize_entries(self.group_allow_from),
            fallback_group_to_dm=bool(self.fallback_group_to_dm),
        )


@dataclass(frozen=True)
class AccessDecision:
    """Resolved access decision."""

    allowed: bool
    require_pairing: bool
    reason: str
    effective_allow_from: tuple[str, ...] = field(default_factory=tuple)


class DmGroupPolicyEngine:
    """Resolve DM/group access using config policy and pairing store."""

    def __init__(self, pairing_store: PairingStore | None = None) -> None:
        self.pairing_store = pairing_store

    def evaluate(
        self,
        *,
        is_group: bool,
        channel: str,
        sender_id: str | int,
        policy: AccessPolicyConfig,
    ) -> AccessDecision:
        if is_group:
            return self.evaluate_group(sender_id=sender_id, policy=policy)
        return self.evaluate_dm(channel=channel, sender_id=sender_id, policy=policy)

    def evaluate_dm(
        self,
        *,
        channel: str,
        sender_id: str | int,
        policy: AccessPolicyConfig,
    ) -> AccessDecision:
        normalized_policy = policy.normalized()
        sender = str(sender_id).strip()
        effective_allow_from = self._effective_dm_allow_from(
            channel=channel,
            allow_from=normalized_policy.allow_from,
        )
        if normalized_policy.dm_mode == DmPolicyMode.DISABLED:
            return AccessDecision(
                allowed=False,
                require_pairing=False,
                reason="dm_policy=disabled",
                effective_allow_from=effective_allow_from,
            )
        if normalized_policy.dm_mode == DmPolicyMode.OPEN:
            return AccessDecision(
                allowed=True,
                require_pairing=False,
                reason="dm_policy=open",
                effective_allow_from=effective_allow_from,
            )
        if sender and sender in effective_allow_from:
            return AccessDecision(
                allowed=True,
                require_pairing=False,
                reason=f"dm_policy={normalized_policy.dm_mode.value} (allowlisted)",
                effective_allow_from=effective_allow_from,
            )
        if normalized_policy.dm_mode == DmPolicyMode.PAIRING:
            return AccessDecision(
                allowed=False,
                require_pairing=True,
                reason="dm_policy=pairing (not allowlisted)",
                effective_allow_from=effective_allow_from,
            )
        return AccessDecision(
            allowed=False,
            require_pairing=False,
            reason="dm_policy=allowlist (not allowlisted)",
            effective_allow_from=effective_allow_from,
        )

    def evaluate_group(
        self,
        *,
        sender_id: str | int,
        policy: AccessPolicyConfig,
    ) -> AccessDecision:
        normalized_policy = policy.normalized()
        sender = str(sender_id).strip()
        if normalized_policy.group_mode == GroupPolicyMode.DISABLED:
            return AccessDecision(
                allowed=False,
                require_pairing=False,
                reason="group_policy=disabled",
                effective_allow_from=(),
            )
        if normalized_policy.group_mode == GroupPolicyMode.OPEN:
            return AccessDecision(
                allowed=True,
                require_pairing=False,
                reason="group_policy=open",
                effective_allow_from=(),
            )
        effective = normalized_policy.group_allow_from
        if not effective and normalized_policy.fallback_group_to_dm:
            effective = normalized_policy.allow_from
        if sender and sender in effective:
            return AccessDecision(
                allowed=True,
                require_pairing=False,
                reason="group_policy=allowlist (allowlisted)",
                effective_allow_from=effective,
            )
        if not effective:
            return AccessDecision(
                allowed=False,
                require_pairing=False,
                reason="group_policy=allowlist (empty allowlist)",
                effective_allow_from=effective,
            )
        return AccessDecision(
            allowed=False,
            require_pairing=False,
            reason="group_policy=allowlist (not allowlisted)",
            effective_allow_from=effective,
        )

    def request_pairing(
        self,
        *,
        channel: str,
        sender_id: str | int,
        metadata: dict[str, object] | None = None,
    ) -> PairingRequest:
        if self.pairing_store is None:
            raise RuntimeError("pairing_store is required for request_pairing.")
        return self.pairing_store.upsert_request(
            channel=channel,
            entry_id=sender_id,
            metadata=dict(metadata or {}),
        )

    def approve_pairing(self, *, channel: str, code: str) -> PairingRequest | None:
        if self.pairing_store is None:
            raise RuntimeError("pairing_store is required for approve_pairing.")
        return self.pairing_store.approve_code(channel=channel, code=code)

    def _effective_dm_allow_from(self, *, channel: str, allow_from: tuple[str, ...]) -> tuple[str, ...]:
        if self.pairing_store is None:
            return allow_from
        merged = [*allow_from, *self.pairing_store.list_allowed(channel=channel)]
        return _normalize_entries(merged)
