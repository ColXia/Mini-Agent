"""Tests for P15 T3.5 session baseline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mini_agent.agent_core.session.lifecycle import SessionLifecycleManager, SessionLifecyclePolicy, SessionResetMode
from mini_agent.agent_core.session.lineage import SessionLineageNode, SessionLineageStore
from mini_agent.agent_core.session.session_key import (
    AgentSessionKey,
    AmbiguousSessionKeyError,
    SessionKeyError,
    SessionKeyIndex,
)


def _dt(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def test_session_key_parse_render_and_thread_inheritance():
    key = AgentSessionKey(agent_id="a1", channel="qq", peer_kind="group", peer_id="100")
    assert key.to_key() == "agent:a1:qq:group:100"

    threaded = key.with_thread("thread-1")
    assert threaded.to_key() == "agent:a1:qq:group:100:thread:thread-1"

    parsed = AgentSessionKey.parse(threaded.to_key())
    assert parsed == threaded
    assert parsed.base_key() == key.base_key()


def test_session_key_index_resolve_and_ambiguous_detection():
    idx = SessionKeyIndex()
    key1 = AgentSessionKey(agent_id="a1", channel="qq", peer_kind="group", peer_id="100")
    key2 = AgentSessionKey(agent_id="a1", channel="qq", peer_kind="group", peer_id="101")
    idx.add(key1)
    idx.add(key2)

    assert idx.resolve(key1.to_key()) == key1
    assert idx.resolve(key1.slug()) == key1

    with pytest.raises(AmbiguousSessionKeyError):
        idx.resolve("agent:a1:qq:group")

    with pytest.raises(SessionKeyError):
        idx.resolve("missing")


def test_lifecycle_daily_and_idle_reset_decisions():
    key = AgentSessionKey(agent_id="a1", channel="qq", peer_kind="group", peer_id="200")
    base = _dt(2026, 1, 1, 10, 0)

    daily_mgr = SessionLifecycleManager(SessionLifecyclePolicy(mode=SessionResetMode.DAILY, idle_seconds=120))
    daily_state = daily_mgr.bootstrap(key, now_utc=base)
    should_daily, reason_daily = daily_mgr.should_reset(daily_state, now_utc=_dt(2026, 1, 2, 9, 0))
    assert should_daily is True
    assert reason_daily == "daily"

    idle_mgr = SessionLifecycleManager(SessionLifecyclePolicy(mode=SessionResetMode.IDLE, idle_seconds=300))
    idle_state = idle_mgr.bootstrap(key, now_utc=base)
    should_idle, reason_idle = idle_mgr.should_reset(idle_state, now_utc=base + timedelta(seconds=301))
    assert should_idle is True
    assert reason_idle == "idle"


def test_lifecycle_ensure_active_resets_revision():
    key = AgentSessionKey(agent_id="a2", channel="qq", peer_kind="friend", peer_id="u-1")
    manager = SessionLifecycleManager(SessionLifecyclePolicy(mode=SessionResetMode.BOTH, idle_seconds=60))
    state = manager.bootstrap(key, now_utc=_dt(2026, 1, 1, 8, 0))

    result = manager.ensure_active(state, now_utc=_dt(2026, 1, 1, 8, 2))
    assert result.reset is True
    assert result.reason == "idle"
    assert result.state.revision == 1


def test_session_lineage_chain_and_cycle_guard():
    store = SessionLineageStore()
    root = store.add_root("agent:a1:qq:group:300")
    store.add_child(
        parent_session_key=root.session_key,
        child_session_key="agent:a1:qq:group:300:thread:t1",
        reason="delegation",
    )
    store.add_child(
        parent_session_key="agent:a1:qq:group:300:thread:t1",
        child_session_key="agent:a1:qq:group:300:thread:t2",
        reason="reset",
    )

    chain = store.chain_to_root("agent:a1:qq:group:300:thread:t2")
    assert [node.session_key for node in chain] == [
        "agent:a1:qq:group:300:thread:t2",
        "agent:a1:qq:group:300:thread:t1",
        "agent:a1:qq:group:300",
    ]

    with pytest.raises(ValueError, match="cycle"):
        store.add_child(
            parent_session_key="agent:a1:qq:group:300:thread:t2",
            child_session_key="agent:a1:qq:group:300",
            reason="invalid",
        )


def test_session_lineage_restore_node_can_upgrade_placeholder_parent() -> None:
    base = _dt(2026, 1, 1, 10, 0)
    store = SessionLineageStore()
    store.restore_node(
        SessionLineageNode(
            session_key="child",
            parent_session_key="parent",
            reason="import",
            created_utc=base,
            metadata={"root_session_id": "root"},
        )
    )
    store.restore_node(
        SessionLineageNode(
            session_key="parent",
            parent_session_key="root",
            reason="import",
            created_utc=base,
            metadata={"root_session_id": "root"},
        )
    )

    chain = store.chain_to_root("child")
    assert [node.session_key for node in chain] == ["child", "parent", "root"]
    assert store.get("parent") is not None
    assert store.get("parent").parent_session_key == "root"


def test_session_lineage_remove_promotes_children() -> None:
    store = SessionLineageStore()
    store.add_root("root")
    store.add_child(parent_session_key="root", child_session_key="child", reason="import")
    store.add_child(parent_session_key="child", child_session_key="grandchild", reason="import")

    assert store.remove("child") is True
    assert store.get("child") is None
    assert store.parent_of("grandchild") is None
    assert store.get("grandchild") is not None
    assert store.get("grandchild").reason == "root"
