"""Tests for v11.3 WorkspaceUserService."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from mini_agent.agent_core.contracts.attachments import WorkspaceKind
from mini_agent.user_services.workspace_user_service import (
    WorkspaceStatusKind,
    WorkspaceSwitchResult,
    WorkspaceUserService,
    WorkspaceView,
)


class TestWorkspaceView:
    """Tests for WorkspaceView."""

    def test_workspace_view_creation(self) -> None:
        view = WorkspaceView(
            workspace_id="ws-001",
            workspace_kind=WorkspaceKind.PROJECT,
            root_dir="/home/user/project",
            title="My Project",
            status=WorkspaceStatusKind.ACTIVE,
            session_count=5,
        )
        assert view.workspace_id == "ws-001"
        assert view.workspace_kind == WorkspaceKind.PROJECT
        assert view.title == "My Project"
        assert view.is_active is True
        assert view.is_default is False

    def test_workspace_view_default_kind(self) -> None:
        view = WorkspaceView(
            workspace_id="ws-default",
            workspace_kind=WorkspaceKind.DEFAULT,
            root_dir="/home/user/.mini-agent",
            title="Default Workspace",
        )
        assert view.is_default is True

    def test_workspace_view_root_path(self) -> None:
        view = WorkspaceView(
            workspace_id="ws-001",
            workspace_kind=WorkspaceKind.PROJECT,
            root_dir="/home/user/project",
            title="My Project",
        )
        assert view.root_path.name == "project"


class TestWorkspaceUserService:
    """Tests for WorkspaceUserService."""

    def test_service_creation(self) -> None:
        service = WorkspaceUserService()
        assert service._current_workspace_id is None
        assert len(service.list_workspaces()) == 0

    def test_register_workspace(self) -> None:
        service = WorkspaceUserService()
        view = WorkspaceView(
            workspace_id="ws-001",
            workspace_kind=WorkspaceKind.PROJECT,
            root_dir="/home/user/project",
            title="My Project",
        )
        service.register_workspace(view)
        assert len(service.list_workspaces()) == 1
        assert service.get_workspace("ws-001") is not None

    def test_unregister_workspace(self) -> None:
        service = WorkspaceUserService()
        view = WorkspaceView(
            workspace_id="ws-001",
            workspace_kind=WorkspaceKind.PROJECT,
            root_dir="/home/user/project",
            title="My Project",
        )
        service.register_workspace(view)
        removed = service.unregister_workspace("ws-001")
        assert removed is not None
        assert removed.workspace_id == "ws-001"
        assert len(service.list_workspaces()) == 0

    def test_get_current_workspace_none(self) -> None:
        service = WorkspaceUserService()
        current = service.get_current_workspace()
        assert current is None

    def test_get_current_workspace(self) -> None:
        service = WorkspaceUserService()
        view = WorkspaceView(
            workspace_id="ws-001",
            workspace_kind=WorkspaceKind.PROJECT,
            root_dir="/home/user/project",
            title="My Project",
            status=WorkspaceStatusKind.ACTIVE,
        )
        service.register_workspace(view)
        service.set_current_workspace_id("ws-001")
        current = service.get_current_workspace()
        assert current is not None
        assert current.workspace_id == "ws-001"
        assert current.is_active is True

    def test_switch_workspace_not_found(self) -> None:
        service = WorkspaceUserService()
        result = service.switch_workspace("nonexistent")
        assert result.success is False
        assert "not found" in result.error_reason

    def test_switch_workspace_empty_id(self) -> None:
        service = WorkspaceUserService()
        result = service.switch_workspace("")
        assert result.success is False
        assert "required" in result.error_reason

    def test_switch_workspace_success(self) -> None:
        service = WorkspaceUserService()
        view1 = WorkspaceView(
            workspace_id="ws-001",
            workspace_kind=WorkspaceKind.PROJECT,
            root_dir="/home/user/project1",
            title="Project 1",
        )
        view2 = WorkspaceView(
            workspace_id="ws-002",
            workspace_kind=WorkspaceKind.PROJECT,
            root_dir="/home/user/project2",
            title="Project 2",
        )
        service.register_workspace(view1)
        service.register_workspace(view2)
        service.set_current_workspace_id("ws-001")

        result = service.switch_workspace("ws-002")
        assert result.success is True
        assert result.workspace_id == "ws-002"
        assert result.previous_workspace_id == "ws-001"

    def test_switch_workspace_with_handler(self) -> None:
        service = WorkspaceUserService()
        view = WorkspaceView(
            workspace_id="ws-001",
            workspace_kind=WorkspaceKind.PROJECT,
            root_dir="/home/user/project",
            title="Project",
        )
        service.register_workspace(view)

        def custom_switcher(workspace_id: str) -> WorkspaceSwitchResult:
            return WorkspaceSwitchResult(
                success=True,
                workspace_id=workspace_id,
                requires_confirmation=True,
            )

        service.set_workspace_switcher(custom_switcher)
        result = service.switch_workspace("ws-001")
        assert result.success is True
        assert result.requires_confirmation is True

    def test_list_workspaces_with_handler(self) -> None:
        service = WorkspaceUserService()

        def custom_lister() -> list[WorkspaceView]:
            return [
                WorkspaceView(
                    workspace_id="ws-001",
                    workspace_kind=WorkspaceKind.PROJECT,
                    root_dir="/home/user/project",
                    title="Project",
                ),
            ]

        service.set_workspace_lister(custom_lister)
        workspaces = service.list_workspaces()
        assert len(workspaces) == 1

    def test_clear(self) -> None:
        service = WorkspaceUserService()
        view = WorkspaceView(
            workspace_id="ws-001",
            workspace_kind=WorkspaceKind.PROJECT,
            root_dir="/home/user/project",
            title="Project",
        )
        service.register_workspace(view)
        service.set_current_workspace_id("ws-001")
        service.clear()
        assert len(service.list_workspaces()) == 0
        assert service.get_current_workspace() is None