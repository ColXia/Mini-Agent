from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from mini_agent.runtime.handlers.session_access_handler import (
    RuntimeSessionAccessCommand,
    RuntimeSessionAccessHandler,
)
from mini_agent.session import DEFAULT_SESSION_ID


def _dt() -> datetime:
    return datetime(2026, 4, 16, 18, 0, 0, tzinfo=timezone.utc)


def _same_workspace(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve()


def test_runtime_session_access_handler_preserves_legacy_team_reuse_without_default_session_support(
    tmp_path: Path,
) -> None:
    prepared: list[tuple[Path, datetime]] = []
    workspace = tmp_path.resolve()
    live_session = SimpleNamespace(session_id="sess-live", workspace_dir=workspace)

    handler = RuntimeSessionAccessHandler(
        normalize_surface=lambda value: " ".join(str(value or "").strip().lower().split()) or "api",
        normalize_channel_type=lambda value: str(value).lower() if value else None,
        same_workspace=_same_workspace,
    )

    plan = handler.build_plan(
        RuntimeSessionAccessCommand(
            session_id=None,
            workspace_dir=workspace,
            surface="QQ",
            channel_type="qq",
            conversation_id="group:demo",
            sender_id="user-1",
            session_title_hint="hint",
        ),
        now_utc=_dt(),
        team_mode=True,
        prepare_environment=lambda target_workspace, now_utc: prepared.append((target_workspace, now_utc)),
        load_active_session=lambda _candidate: None,
        find_latest_active_session=lambda _workspace: live_session,
        load_persisted_record=lambda _candidate: None,
        find_latest_persisted_record=lambda _workspace: None,
        raise_workspace_mismatch=lambda: (_ for _ in ()).throw(AssertionError("unexpected mismatch")),
        enforce_capacity=lambda: (_ for _ in ()).throw(AssertionError("capacity should not be enforced")),
        allocate_session_id=lambda: "unused",
    )

    assert prepared == [(workspace, _dt())]
    assert plan.action == "reuse_active"
    assert plan.session_id == "sess-live"
    assert plan.workspace_dir == workspace
    assert plan.is_default_session is False
    assert plan.normalized_title_hint == "hint"


def test_runtime_session_access_handler_supports_default_session_routing_when_enabled(tmp_path: Path) -> None:
    prepared: list[tuple[Path, datetime]] = []
    workspace = tmp_path.resolve()
    main_workspace = (tmp_path / "main").resolve()

    handler = RuntimeSessionAccessHandler(
        normalize_surface=lambda value: " ".join(str(value or "").strip().lower().split()) or "api",
        normalize_channel_type=lambda value: str(value).lower() if value else None,
        same_workspace=_same_workspace,
        resolve_main_workspace=lambda _workspace: main_workspace,
    )

    plan = handler.build_plan(
        RuntimeSessionAccessCommand(
            session_id=None,
            workspace_dir=workspace,
            surface="QQ",
            channel_type="qq",
            conversation_id="group:demo",
            sender_id="user-1",
            session_title_hint="ignored title hint",
        ),
        now_utc=_dt(),
        team_mode=True,
        prepare_environment=lambda target_workspace, now_utc: prepared.append((target_workspace, now_utc)),
        load_active_session=lambda _candidate: None,
        find_latest_active_session=lambda _workspace: None,
        load_persisted_record=lambda _candidate: None,
        find_latest_persisted_record=lambda _workspace: None,
        raise_workspace_mismatch=lambda: (_ for _ in ()).throw(AssertionError("unexpected mismatch")),
        enforce_capacity=lambda: (_ for _ in ()).throw(AssertionError("default session should not enforce capacity")),
        allocate_session_id=lambda: "unused",
    )

    assert prepared == [(main_workspace, _dt())]
    assert plan.action == "create_new"
    assert plan.session_id == DEFAULT_SESSION_ID
    assert plan.workspace_dir == main_workspace
    assert plan.is_default_session is True
    assert plan.normalized_title_hint == ""
