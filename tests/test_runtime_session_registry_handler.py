from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from mini_agent.runtime.handlers.session_access_handler import RuntimeSessionAccessPlan
from mini_agent.runtime.handlers.session_creation_handler import RuntimeSessionCreationCommand
from mini_agent.runtime.handlers.session_registry_handler import RuntimeSessionRegistryHandler
from mini_agent.session import DEFAULT_SESSION_TITLE
from tests.runtime_contract_fixtures import runtime_session_stub


def _dt() -> datetime:
    return datetime(2026, 4, 16, 19, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_runtime_session_registry_handler_supports_legacy_enforce_capacity_signature(tmp_path: Path) -> None:
    capacity_calls: list[int] = []
    registered: list[str] = []
    persisted: list[str] = []

    async def _create(command: RuntimeSessionCreationCommand, *, now_utc: datetime):
        assert now_utc == _dt()
        return runtime_session_stub(session_id=command.session_id, workspace_dir=command.workspace_dir)

    handler = RuntimeSessionRegistryHandler(
        session_access=SimpleNamespace(),
        session_creation=SimpleNamespace(create=_create),
        session_snapshots=SimpleNamespace(),
        session_catalog=SimpleNamespace(),
        drop_expired_sessions=lambda **_kwargs: None,
        enforce_workspace_entry=lambda _active_sessions, _workspace_dir: None,
        enforce_capacity=lambda count: capacity_calls.append(count),
        raise_workspace_mismatch=lambda: None,
        allocate_session_id=lambda: "sess-legacy-capacity",
        load_persisted_record=lambda _session_id: None,
        list_persisted_records=lambda: [],
        restore_persisted_session=lambda _record, _now_utc: None,  # type: ignore[arg-type]
        hydrate_session=lambda _payload, _now_utc, _persist_after: None,  # type: ignore[arg-type]
        build_derived_hydration_payload=lambda *args, **kwargs: None,  # type: ignore[arg-type]
        refresh_session_lifecycle=lambda _session, _now_utc: False,
        register_session=lambda session: registered.append(session.session_id),
        persist_session=lambda session: persisted.append(session.session_id),
    )

    sessions: dict[str, object] = {}
    session = await handler.create_session(
        sessions,
        now_utc=_dt(),
        workspace_dir=tmp_path,
        title="Task",
    )

    assert session.session_id == "sess-legacy-capacity"
    assert capacity_calls == [0]
    assert registered == ["sess-legacy-capacity"]
    assert persisted == ["sess-legacy-capacity"]


@pytest.mark.asyncio
async def test_runtime_session_registry_handler_passes_default_session_title_and_flag(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    created_session = runtime_session_stub(session_id="default", workspace_dir=tmp_path)

    async def _create(command: RuntimeSessionCreationCommand, *, now_utc: datetime):
        captured["command"] = command
        captured["now_utc"] = now_utc
        return created_session

    handler = RuntimeSessionRegistryHandler(
        session_access=SimpleNamespace(
            build_plan=lambda *args, **kwargs: RuntimeSessionAccessPlan(
                action="create_new",
                workspace_dir=tmp_path,
                session_id="default",
                is_default_session=True,
            )
        ),
        session_creation=SimpleNamespace(create=_create),
        session_snapshots=SimpleNamespace(),
        session_catalog=SimpleNamespace(
            find_latest_active_session=lambda _workspace, _sessions: None,
            find_latest_persisted_record=lambda _workspace, _records: None,
        ),
        drop_expired_sessions=lambda **_kwargs: None,
        enforce_workspace_entry=lambda _active_sessions, _workspace_dir: None,
        enforce_capacity=lambda: None,
        raise_workspace_mismatch=lambda: None,
        allocate_session_id=lambda: "ignored",
        load_persisted_record=lambda _session_id: None,
        list_persisted_records=lambda: [],
        restore_persisted_session=lambda _record, _now_utc: None,  # type: ignore[arg-type]
        hydrate_session=lambda _payload, _now_utc, _persist_after: None,  # type: ignore[arg-type]
        build_derived_hydration_payload=lambda *args, **kwargs: None,  # type: ignore[arg-type]
        refresh_session_lifecycle=lambda _session, _now_utc: False,
        register_session=lambda _session: None,
        persist_session=lambda _session: None,
    )

    sessions: dict[str, object] = {}
    session = await handler.get_or_create_session(
        sessions,
        now_utc=_dt(),
        team_mode=True,
        session_id=None,
        workspace_dir=tmp_path,
    )

    command = captured["command"]

    assert session is created_session
    assert isinstance(command, RuntimeSessionCreationCommand)
    assert command.session_id == "default"
    assert command.title == DEFAULT_SESSION_TITLE
    assert command.default_title == DEFAULT_SESSION_TITLE
    assert command.is_default is True
