from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from mini_agent.runtime.session_managed_store_handler import RuntimeManagedSessionStoreHandler


def _dt() -> datetime:
    return datetime(2026, 4, 13, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_managed_session_store_load_prefers_live_then_restores_persisted(tmp_path: Path) -> None:
    restored_session = SimpleNamespace(session_id="sess-2", workspace_dir=tmp_path)
    restore_calls: list[str] = []

    async def _restore(record: dict[str, object], now_utc: datetime | None):
        restore_calls.append(str(record["session_id"]))
        assert now_utc == _dt()
        return restored_session

    handler = RuntimeManagedSessionStoreHandler(
        expired_session_ids=lambda sessions, now_utc=None: [],
        build_sandbox_diagnostics_for_session=lambda session: {},
        save_session=lambda session, agent_messages, sandbox_diagnostics: None,
        load_session_record=lambda session_id: {"session_id": session_id} if session_id == "sess-2" else None,
        delete_session_record=lambda session_id: False,
        restore_persisted_session=_restore,
        record_workspace_dir=lambda record: tmp_path,
        clear_session_runtime_task_memory=lambda workspace_dir, session_id: None,
        remove_session_lineage=lambda session_id: None,
    )

    live_session = SimpleNamespace(session_id="sess-1", workspace_dir=tmp_path)
    sessions = {"sess-1": live_session}

    assert await handler.load_managed_session(sessions, "sess-1", now_utc=_dt()) is live_session
    assert await handler.load_managed_session(sessions, "sess-2", now_utc=_dt()) is restored_session
    assert await handler.load_managed_session(sessions, "missing", now_utc=_dt()) is None
    assert restore_calls == ["sess-2"]


def test_managed_session_store_delete_cleans_runtime_memory_and_lineage(tmp_path: Path) -> None:
    cleared: list[tuple[Path, str]] = []
    removed_lineage: list[str] = []
    deleted_records: list[str] = []

    def _delete_record(session_id: str) -> bool:
        deleted_records.append(session_id)
        return session_id == "persisted-only"

    handler = RuntimeManagedSessionStoreHandler(
        expired_session_ids=lambda sessions, now_utc=None: [],
        build_sandbox_diagnostics_for_session=lambda session: {},
        save_session=lambda session, agent_messages, sandbox_diagnostics: None,
        load_session_record=lambda session_id: (
            {"session_id": session_id, "workspace_dir": str(tmp_path)} if session_id == "persisted-only" else None
        ),
        delete_session_record=_delete_record,
        restore_persisted_session=lambda record, now_utc: None,  # type: ignore[arg-type]
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


def test_managed_session_store_persist_swallow_errors_and_uses_sandbox_diagnostics(tmp_path: Path) -> None:
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

    handler = RuntimeManagedSessionStoreHandler(
        expired_session_ids=lambda sessions, now_utc=None: [],
        build_sandbox_diagnostics_for_session=lambda session: {"access_level": "default"},
        save_session=_save,
        load_session_record=lambda session_id: None,
        delete_session_record=lambda session_id: False,
        restore_persisted_session=lambda record, now_utc: None,  # type: ignore[arg-type]
        record_workspace_dir=lambda record: None,
        clear_session_runtime_task_memory=lambda workspace_dir, session_id: None,
        remove_session_lineage=lambda session_id: None,
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
