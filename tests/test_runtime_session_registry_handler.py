from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from mini_agent.runtime.handlers.session_access_handler import RuntimeSessionAccessPlan
from mini_agent.runtime.handlers.session_creation_handler import RuntimeSessionCreationCommand
from mini_agent.runtime.handlers.session_registry_handler import (
    RuntimeSessionRegistryHandler,
    RuntimeSessionSnapshotImportCommand,
)
from mini_agent.session.bindings import DEFAULT_SESSION_TITLE
from tests.runtime_contract_fixtures import runtime_session_stub


def _dt() -> datetime:
    return datetime(2026, 4, 16, 19, 0, 0, tzinfo=timezone.utc)


def _build_registry_handler(**overrides) -> RuntimeSessionRegistryHandler:
    defaults = dict(
        session_access=SimpleNamespace(),
        session_creation=SimpleNamespace(),
        session_catalog=SimpleNamespace(),
        enforce_workspace_entry=lambda _active_sessions, _workspace_dir: None,
        enforce_capacity=lambda: None,
        raise_workspace_mismatch=lambda: None,
        load_persisted_record=lambda _session_id: None,
        list_persisted_records=lambda: [],
        restore_persisted_session=lambda _record, _now_utc: None,  # type: ignore[arg-type]
        hydrate_session=lambda _payload, _now_utc, _persist_after: None,  # type: ignore[arg-type]
        build_derived_hydration_payload=lambda *args, **kwargs: None,  # type: ignore[arg-type]
        build_snapshot_hydration_payload=lambda **kwargs: kwargs,
        build_session_snapshot=lambda session: f"live:{session.session_id}",
        build_session_snapshot_from_record=lambda record: f"persisted:{record['session_id']}",
        refresh_session_lifecycle=lambda _session, _now_utc: False,
        register_session=lambda _session: None,
        expired_session_ids=lambda sessions, now_utc=None: [],  # noqa: ARG005
        build_sandbox_diagnostics_for_session=lambda _session: {},
        save_session=lambda _session, _agent_messages, _sandbox_diagnostics: None,
        delete_session_record=lambda _session_id: False,
        record_workspace_dir=lambda _record: None,
        clear_session_runtime_task_memory=lambda _workspace_dir, _session_id: None,
        remove_session_lineage=lambda _session_id: None,
    )
    defaults.update(overrides)
    return RuntimeSessionRegistryHandler(**defaults)


@pytest.mark.asyncio
async def test_runtime_session_registry_handler_supports_legacy_enforce_capacity_signature(tmp_path: Path) -> None:
    capacity_calls: list[int] = []
    registered: list[str] = []
    saved: list[dict[str, object]] = []

    async def _create(command: RuntimeSessionCreationCommand, *, now_utc: datetime):
        assert now_utc == _dt()
        return runtime_session_stub(session_id=command.session_id, workspace_dir=command.workspace_dir)

    handler = _build_registry_handler(
        session_creation=SimpleNamespace(create=_create),
        enforce_capacity=lambda count: capacity_calls.append(count),
        register_session=lambda session: registered.append(session.session_id),
        save_session=lambda session, agent_messages, sandbox_diagnostics: saved.append(
            {
                "session_id": session.session_id,
                "agent_messages": list(agent_messages or []),
                "sandbox_diagnostics": dict(sandbox_diagnostics),
            }
        ),
    )

    sessions: dict[str, object] = {}
    with patch(
        "mini_agent.runtime.handlers.session_registry_handler.uuid4",
        return_value=SimpleNamespace(hex="sess-legacy-capacity"),
    ):
        session = await handler.create_session(
            sessions,
            now_utc=_dt(),
            workspace_dir=tmp_path,
            title="Task",
        )

    assert session.session_id == "sess-legacy-capacity"
    assert capacity_calls == [0]
    assert registered == ["sess-legacy-capacity"]
    assert saved == [
        {
            "session_id": "sess-legacy-capacity",
            "agent_messages": [],
            "sandbox_diagnostics": {},
        }
    ]


@pytest.mark.asyncio
async def test_runtime_session_registry_handler_passes_default_session_title_and_flag(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    created_session = runtime_session_stub(session_id="default", workspace_dir=tmp_path)

    async def _create(command: RuntimeSessionCreationCommand, *, now_utc: datetime):
        captured["command"] = command
        captured["now_utc"] = now_utc
        return created_session

    handler = _build_registry_handler(
        session_access=SimpleNamespace(
            build_plan=lambda *args, **kwargs: RuntimeSessionAccessPlan(
                action="create_new",
                workspace_dir=tmp_path,
                session_id="default",
                is_default_session=True,
            )
        ),
        session_creation=SimpleNamespace(create=_create),
        session_catalog=SimpleNamespace(
            find_latest_active_session=lambda _workspace, _sessions: None,
            find_latest_persisted_record=lambda _workspace, _records: None,
        ),
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


@pytest.mark.asyncio
async def test_runtime_session_registry_handler_load_prefers_live_then_restores_persisted(tmp_path: Path) -> None:
    restored_session = SimpleNamespace(session_id="sess-2", workspace_dir=tmp_path)
    restore_calls: list[str] = []

    async def _restore(record: dict[str, object], now_utc: datetime | None):
        restore_calls.append(str(record["session_id"]))
        assert now_utc == _dt()
        return restored_session

    handler = _build_registry_handler(
        load_persisted_record=lambda session_id: {"session_id": session_id} if session_id == "sess-2" else None,
        restore_persisted_session=_restore,
    )

    live_session = SimpleNamespace(session_id="sess-1", workspace_dir=tmp_path)
    sessions = {"sess-1": live_session}

    assert await handler.load_managed_session(sessions, "sess-1", now_utc=_dt()) is live_session
    assert await handler.load_managed_session(sessions, "sess-2", now_utc=_dt()) is restored_session
    assert await handler.load_managed_session(sessions, "missing", now_utc=_dt()) is None
    assert restore_calls == ["sess-2"]


def test_runtime_session_registry_handler_delete_cleans_runtime_memory_and_lineage(tmp_path: Path) -> None:
    cleared: list[tuple[Path, str]] = []
    removed_lineage: list[str] = []
    deleted_records: list[str] = []

    def _delete_record(session_id: str) -> bool:
        deleted_records.append(session_id)
        return session_id == "persisted-only"

    handler = _build_registry_handler(
        load_persisted_record=lambda session_id: (
            {"session_id": session_id, "workspace_dir": str(tmp_path)} if session_id == "persisted-only" else None
        ),
        delete_session_record=_delete_record,
        record_workspace_dir=lambda record: Path(str(record["workspace_dir"])).resolve(),
        clear_session_runtime_task_memory=lambda workspace_dir, session_id: cleared.append((workspace_dir, session_id)),
        remove_session_lineage=lambda session_id: removed_lineage.append(session_id),
    )

    live_session = SimpleNamespace(session_id="live-1", workspace_dir=tmp_path.resolve())
    sessions = {"live-1": live_session}

    handler.delete_session(sessions, "live-1")
    handler.delete_session(sessions, "persisted-only")

    assert "live-1" not in sessions
    assert cleared == [
        (tmp_path.resolve(), "live-1"),
        (tmp_path.resolve(), "persisted-only"),
    ]
    assert removed_lineage == ["live-1", "persisted-only"]
    assert deleted_records == ["live-1", "persisted-only"]


def test_runtime_session_registry_handler_persist_swallow_errors_and_uses_sandbox_diagnostics(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def _save(session, agent_messages, sandbox_diagnostics):  # noqa: ANN001
        calls.append(
            {
                "session_id": session.session_id,
                "agent_messages": list(agent_messages or []),
                "sandbox_diagnostics": dict(sandbox_diagnostics),
            }
        )
        raise RuntimeError("disk busy")

    handler = _build_registry_handler(
        build_sandbox_diagnostics_for_session=lambda _session: {"access_level": "default"},
        save_session=_save,
    )

    session = SimpleNamespace(session_id="sess-1", workspace_dir=tmp_path)
    handler.persist_session(session, agent_messages=[{"role": "assistant", "content": "ok"}])

    assert calls == [
        {
            "session_id": "sess-1",
            "agent_messages": [{"role": "assistant", "content": "ok"}],
            "sandbox_diagnostics": {"access_level": "default"},
        }
    ]


@pytest.mark.asyncio
async def test_runtime_session_registry_handler_imports_snapshot_via_target_owner(tmp_path: Path) -> None:
    prepared: list[tuple[Path, datetime]] = []
    captured: dict[str, object] = {}
    hydrated: list[dict[str, object]] = []
    payload = SimpleNamespace(session_id="sess-import")

    async def _hydrate_session(snapshot_payload, now_utc, persist_after):
        hydrated.append(
            {
                "payload": snapshot_payload,
                "now_utc": now_utc,
                "persist_after": persist_after,
            }
        )
        return payload

    handler = _build_registry_handler(
        enforce_workspace_entry=lambda _active_sessions, workspace_dir: prepared.append((workspace_dir, _dt())),
        build_snapshot_hydration_payload=lambda **kwargs: captured.update(kwargs) or payload,
        hydrate_session=_hydrate_session,
    )

    with patch(
        "mini_agent.runtime.handlers.session_registry_handler.uuid4",
        return_value=SimpleNamespace(hex="sess-import"),
    ):
        result = await handler.import_session_snapshot(
            {},
            now_utc=_dt(),
            command=RuntimeSessionSnapshotImportCommand(
                session_id=None,
                workspace_dir=tmp_path,
                workspace_runtime_snapshot={"snapshot_id": "import-snap"},
            ),
        )

    assert result is payload
    assert prepared == [(tmp_path, _dt())]
    assert captured["session_id"] == "sess-import"
    assert captured["workspace_runtime_snapshot"] == {"snapshot_id": "import-snap"}
    assert hydrated == [
        {
            "payload": payload,
            "now_utc": _dt(),
            "persist_after": True,
        }
    ]


def test_runtime_session_registry_handler_exports_live_or_persisted_snapshot() -> None:
    handler = _build_registry_handler(
        load_persisted_record=lambda session_id: {"session_id": session_id} if session_id == "sess-record" else None,
    )

    assert (
        handler.export_session_snapshot(
            {"sess-live": SimpleNamespace(session_id="sess-live")},
            session_id="sess-live",
        )
        == "live:sess-live"
    )
    assert (
        handler.export_session_snapshot(
            {},
            session_id="sess-record",
        )
        == "persisted:sess-record"
    )

    with pytest.raises(HTTPException) as exc_info:
        handler.export_session_snapshot({}, session_id="missing")

    assert exc_info.value.status_code == 404
