from __future__ import annotations

from pathlib import Path

from mini_agent.workspace import WorkspaceKind, WorkspaceManifest, WorkspaceRecord, workspace_path_key


def test_workspace_manifest_builds_default_workspace_identity(tmp_path: Path) -> None:
    manifest = WorkspaceManifest.default_workspace(tmp_path / "default-world")

    assert manifest.kind is WorkspaceKind.DEFAULT
    assert manifest.workspace_id == workspace_path_key(tmp_path / "default-world")
    assert manifest.title == "default-world"
    assert manifest.root_dir == (tmp_path / "default-world").resolve()


def test_workspace_manifest_builds_project_workspace_identity(tmp_path: Path) -> None:
    manifest = WorkspaceManifest.project_workspace(tmp_path / "project-a", title="Project A")

    assert manifest.kind is WorkspaceKind.PROJECT
    assert manifest.title == "Project A"
    assert manifest.to_summary_dict() == {
        "workspace_id": workspace_path_key(tmp_path / "project-a"),
        "workspace_dir": str((tmp_path / "project-a").resolve()),
        "title": "Project A",
        "kind": "project",
    }


def test_workspace_record_tracks_session_counters_and_runtime_summary(tmp_path: Path) -> None:
    manifest = WorkspaceManifest.project_workspace(tmp_path / "project-a")
    record = WorkspaceRecord.from_manifest(manifest, default=False, active=False)

    record = record.observe_session(shared=True, busy=True, updated_at="2026-04-19T01:00:00+00:00")
    record = record.observe_session(is_default=True, updated_at="2026-04-19T02:00:00+00:00")
    record = record.mark_active(switched=True)

    assert record.to_summary_dict() == {
        "workspace_id": workspace_path_key(tmp_path / "project-a"),
        "workspace_dir": str((tmp_path / "project-a").resolve()),
        "title": "project-a",
        "kind": "project",
        "default": False,
        "session_count": 1,
        "default_session_count": 1,
        "shared_session_count": 1,
        "busy_session_count": 1,
        "last_updated_at": "2026-04-19T02:00:00+00:00",
        "active": True,
        "switched": True,
    }

    assert record.to_runtime_summary_dict(
        runtime_policy={"mode": "single_main"},
        runtime={"scope": "workspace_only"},
        runtime_error=None,
    )["runtime"] == {"scope": "workspace_only"}
