"""Tests for P15 T3.7 DM pairing security baseline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mini_agent.agent_core.security.pairing import PairingLimitError, PairingStore
from mini_agent.agent_core.security.policy import (
    AccessPolicyConfig,
    DmGroupPolicyEngine,
    DmPolicyMode,
    GroupPolicyMode,
)


def _dt(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def test_pairing_store_upsert_reuses_code_and_has_8_char_code(tmp_path):
    store = PairingStore(storage_dir=tmp_path, pending_ttl_seconds=3600, max_pending=3)

    first = store.upsert_request(channel="qq", entry_id="user-1")
    second = store.upsert_request(channel="qq", entry_id="user-1")

    assert len(first.code) == 8
    assert first.code == second.code
    assert first.entry_id == "user-1"
    assert store.snapshot(channel="qq").pending[0].entry_id == "user-1"


def test_pairing_store_limit_expiry_and_approval_flow(tmp_path):
    store = PairingStore(storage_dir=tmp_path, pending_ttl_seconds=10, max_pending=2)
    base = _dt(2026, 1, 1, 10, 0)

    one = store.upsert_request(channel="qq", entry_id="u-1", now_utc=base)
    two = store.upsert_request(channel="qq", entry_id="u-2", now_utc=base + timedelta(seconds=1))

    with pytest.raises(PairingLimitError):
        store.upsert_request(channel="qq", entry_id="u-3", now_utc=base + timedelta(seconds=2))

    pending_before = store.list_pending(channel="qq", now_utc=base + timedelta(seconds=3))
    assert [item.entry_id for item in pending_before] == ["u-1", "u-2"]

    approved = store.approve_code(channel="qq", code=one.code, now_utc=base + timedelta(seconds=4))
    assert approved is not None
    assert approved.entry_id == "u-1"
    assert store.is_allowed(channel="qq", entry_id="u-1") is True

    pending_after = store.list_pending(channel="qq", now_utc=base + timedelta(seconds=4))
    assert [item.entry_id for item in pending_after] == ["u-2"]
    assert store.list_pending(channel="qq", now_utc=base + timedelta(seconds=15)) == ()

    assert two.entry_id == "u-2"


def test_dm_policy_pairing_mode_and_allowlist_merge(tmp_path):
    store = PairingStore(storage_dir=tmp_path, pending_ttl_seconds=3600, max_pending=3)
    engine = DmGroupPolicyEngine(pairing_store=store)
    policy = AccessPolicyConfig(
        dm_mode=DmPolicyMode.PAIRING,
        allow_from=("owner",),
    )

    owner = engine.evaluate_dm(channel="qq", sender_id="owner", policy=policy)
    assert owner.allowed is True

    guest_before = engine.evaluate_dm(channel="qq", sender_id="guest", policy=policy)
    assert guest_before.allowed is False
    assert guest_before.require_pairing is True

    request = engine.request_pairing(channel="qq", sender_id="guest")
    approved = engine.approve_pairing(channel="qq", code=request.code)
    assert approved is not None
    assert approved.entry_id == "guest"

    guest_after = engine.evaluate_dm(channel="qq", sender_id="guest", policy=policy)
    assert guest_after.allowed is True
    assert guest_after.require_pairing is False


def test_group_policy_allowlist_fallback_and_disabled():
    engine = DmGroupPolicyEngine()

    policy_fallback = AccessPolicyConfig(
        dm_mode=DmPolicyMode.ALLOWLIST,
        group_mode=GroupPolicyMode.ALLOWLIST,
        allow_from=("team-owner",),
        group_allow_from=(),
        fallback_group_to_dm=True,
    )
    allowed = engine.evaluate_group(sender_id="team-owner", policy=policy_fallback)
    blocked = engine.evaluate_group(sender_id="stranger", policy=policy_fallback)
    assert allowed.allowed is True
    assert blocked.allowed is False

    policy_disabled = AccessPolicyConfig(group_mode=GroupPolicyMode.DISABLED)
    disabled = engine.evaluate_group(sender_id="anyone", policy=policy_disabled)
    assert disabled.allowed is False
