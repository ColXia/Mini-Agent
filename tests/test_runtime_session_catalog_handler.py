from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from mini_agent.runtime.handlers.session_catalog_handler import RuntimeSessionCatalogHandler


def _same_workspace(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve()


def test_runtime_session_catalog_handler_keeps_default_session_when_filtering_workspace(tmp_path: Path) -> None:
    workspace = tmp_path.resolve()
    other_workspace = (tmp_path / "other").resolve()
    handler = RuntimeSessionCatalogHandler(
        same_workspace=_same_workspace,
        build_session_summary=lambda session: session,
        build_session_summary_from_record=lambda record: record["_summary"],
        build_session_detail=lambda session, _recent_limit: session,
        build_session_detail_from_record=lambda record, _recent_limit: record["_summary"],
        build_session_message=lambda entry: entry,
        transcript_entries_from_record=lambda _record: [],
    )

    default_summary = SimpleNamespace(
        session_id="default",
        workspace_dir=str(other_workspace),
        updated_at="2026-04-16T10:00:00+00:00",
        shared=False,
        is_default=True,
        channel_type=None,
        conversation_id=None,
        title="Session 1",
        origin_surface="tui",
    )
    other_summary = SimpleNamespace(
        session_id="other",
        workspace_dir=str(other_workspace),
        updated_at="2026-04-16T09:59:00+00:00",
        shared=False,
        is_default=False,
        channel_type=None,
        conversation_id=None,
        title="Other",
        origin_surface="qq",
    )

    summaries = handler.list_sessions(
        active_sessions=[default_summary, other_summary],
        persisted_records=[],
        workspace_dir=workspace,
    )

    assert [item.session_id for item in summaries] == ["default"]
