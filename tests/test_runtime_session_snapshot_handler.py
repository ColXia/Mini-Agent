from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from mini_agent.runtime.session_snapshot_handler import (
    RuntimeSessionSnapshotHandler,
    RuntimeSessionSnapshotImportCommand,
)


def _dt() -> datetime:
    return datetime(2026, 4, 16, 19, 30, 0, tzinfo=timezone.utc)


def test_runtime_session_snapshot_handler_prepares_import_plan(tmp_path: Path) -> None:
    prepared: list[tuple[Path, datetime]] = []
    captured: dict[str, object] = {}
    payload = SimpleNamespace(session_id="sess-import")
    handler = RuntimeSessionSnapshotHandler(
        build_snapshot_hydration_payload=lambda **kwargs: captured.update(kwargs) or payload,
        build_session_snapshot=lambda _session: "live-snapshot",
        build_session_snapshot_from_record=lambda _record: "persisted-snapshot",
    )

    plan = handler.prepare_import(
        RuntimeSessionSnapshotImportCommand(
            session_id=None,
            workspace_dir=tmp_path,
            workspace_runtime_snapshot={"snapshot_id": "import-snap"},
        ),
        now_utc=_dt(),
        prepare_environment=lambda workspace_dir, now_utc: prepared.append((workspace_dir, now_utc)),
        session_exists=lambda _candidate: False,
        allocate_session_id=lambda: "sess-import",
    )

    assert prepared == [(tmp_path, _dt())]
    assert plan.session_id == "sess-import"
    assert plan.payload is payload
    assert captured["session_id"] == "sess-import"
    assert captured["workspace_runtime_snapshot"] == {"snapshot_id": "import-snap"}


def test_runtime_session_snapshot_handler_exports_live_or_persisted_snapshot() -> None:
    handler = RuntimeSessionSnapshotHandler(
        build_snapshot_hydration_payload=lambda **kwargs: None,
        build_session_snapshot=lambda session: f"live:{session.session_id}",
        build_session_snapshot_from_record=lambda record: f"persisted:{record['session_id']}",
    )

    assert (
        handler.export_snapshot(
            "sess-live",
            active_session=SimpleNamespace(session_id="sess-live"),
            persisted_record=None,
        )
        == "live:sess-live"
    )
    assert (
        handler.export_snapshot(
            "sess-record",
            active_session=None,
            persisted_record={"session_id": "sess-record"},
        )
        == "persisted:sess-record"
    )

    with pytest.raises(HTTPException) as exc_info:
        handler.export_snapshot("missing", active_session=None, persisted_record=None)

    assert exc_info.value.status_code == 404
