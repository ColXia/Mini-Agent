from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from mini_agent.runtime.session_hydration_coordinator import (
    RuntimeSessionHydrationCoordinator,
)
from tests.runtime_contract_fixtures import runtime_session_stub


def _dt() -> datetime:
    return datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_runtime_session_hydration_coordinator_restores_record_and_registers_new_session() -> None:
    session = runtime_session_stub(session_id="sess-1")
    payload = SimpleNamespace(session_id="sess-1")
    prepare_calls: list[tuple[dict[str, object], datetime]] = []
    hydrate_calls: list[tuple[object, datetime, object]] = []
    registered: list[str] = []
    persisted: list[tuple[str, object]] = []

    async def _hydrate_payload(payload_value, now_utc, existing_session):  # noqa: ANN001
        hydrate_calls.append((payload_value, now_utc, existing_session))
        return SimpleNamespace(
            created=True,
            session=session,
            agent_messages_for_persist=[{"role": "assistant", "content": "ok"}],
        )

    coordinator = RuntimeSessionHydrationCoordinator(
        prepare_restore_payload=lambda record, now_utc: (
            prepare_calls.append((dict(record), now_utc)) or payload
        ),
        hydrate_payload=_hydrate_payload,
        register_session=lambda current: registered.append(current.session_id),
        persist_hydrated_session=lambda current, agent_messages=None: persisted.append(
            (current.session_id, list(agent_messages or []))
        ),
    )

    sessions: dict[str, object] = {}
    restored = await coordinator.restore_persisted_session(
        sessions,
        {"session_id": "sess-1"},
        now_utc=_dt(),
    )

    assert restored is session
    assert sessions == {"sess-1": session}
    assert prepare_calls == [({"session_id": "sess-1"}, _dt())]
    assert hydrate_calls == [(payload, _dt(), None)]
    assert registered == ["sess-1"]
    assert persisted == []


@pytest.mark.asyncio
async def test_runtime_session_hydration_coordinator_persists_only_when_requested() -> None:
    session = runtime_session_stub(session_id="sess-2")
    payload = SimpleNamespace(session_id="sess-2")
    registered: list[str] = []
    persisted: list[tuple[str, object]] = []

    async def _hydrate_payload(payload_value, now_utc, existing_session):  # noqa: ANN001
        assert payload_value is payload
        assert now_utc == _dt()
        assert existing_session is None
        return SimpleNamespace(
            created=True,
            session=session,
            agent_messages_for_persist=[{"role": "assistant", "content": "seed"}],
        )

    coordinator = RuntimeSessionHydrationCoordinator(
        prepare_restore_payload=lambda record, now_utc: payload,
        hydrate_payload=_hydrate_payload,
        register_session=lambda current: registered.append(current.session_id),
        persist_hydrated_session=lambda current, agent_messages=None: persisted.append(
            (current.session_id, list(agent_messages or []))
        ),
    )

    sessions: dict[str, object] = {}
    hydrated = await coordinator.hydrate_session(
        sessions,
        payload,
        now_utc=_dt(),
        persist_after=True,
    )

    assert hydrated is session
    assert sessions == {"sess-2": session}
    assert registered == ["sess-2"]
    assert persisted == [("sess-2", [{"role": "assistant", "content": "seed"}])]
