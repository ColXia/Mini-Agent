"""Workspace user service for v11.3.

This module provides the WorkspaceUserService that sits between
User Surfaces and the Business Logic Layer for workspace-related operations.

Key responsibilities:
- Workspace list
- Workspace switching
- Workspace status
- Workspace configuration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from mini_agent.agent_core.contracts.attachments import WorkspaceKind
from mini_agent.utils.text import safe_text


def _safe_text(value: Any) -> str:
    return safe_text(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceStatusKind(str, Enum):
    """Workspace status kinds exposed to user surfaces."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DETACHED = "detached"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class WorkspaceView:
    """View of a workspace for user surfaces."""

    workspace_id: str
    workspace_kind: WorkspaceKind
    root_dir: str
    title: str
    status: WorkspaceStatusKind = WorkspaceStatusKind.INACTIVE
    session_count: int = 0
    last_activity_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def root_path(self) -> Path:
        return Path(self.root_dir)

    @property
    def is_active(self) -> bool:
        return self.status == WorkspaceStatusKind.ACTIVE

    @property
    def is_default(self) -> bool:
        return self.workspace_kind == WorkspaceKind.DEFAULT


@dataclass(frozen=True, slots=True)
class WorkspaceSwitchResult:
    """Result of workspace switch operation."""

    success: bool
    workspace_id: str | None = None
    previous_workspace_id: str | None = None
    error_reason: str | None = None
    requires_confirmation: bool = False


@dataclass(slots=True)
class WorkspaceUserService:
    """User service for workspace-related operations.

    This service provides a stable interface for TUI / Desktop / Remote
    to interact with workspaces without directly accessing the runtime.

    The service aggregates:
    - Workspace registry
    - Workspace attachment state
    - Session counts
    - Workspace switching logic
    """

    _current_workspace_id: str | None = None
    _workspaces: dict[str, WorkspaceView] = field(default_factory=dict)
    _workspace_switcher: Callable[[str], WorkspaceSwitchResult] | None = None
    _workspace_lister: Callable[[], list[WorkspaceView]] | None = None

    def list_workspaces(self) -> list[WorkspaceView]:
        """List all available workspaces.

        Returns:
            A list of WorkspaceView objects
        """
        if self._workspace_lister:
            try:
                return self._workspace_lister()
            except Exception:
                pass
        return list(self._workspaces.values())

    def get_current_workspace(self) -> WorkspaceView | None:
        """Get the current workspace.

        Returns:
            The current WorkspaceView, or None if no workspace is active
        """
        if not self._current_workspace_id:
            return None
        return self._workspaces.get(self._current_workspace_id)

    def get_workspace(self, workspace_id: str) -> WorkspaceView | None:
        """Get a specific workspace by ID.

        Args:
            workspace_id: The workspace ID

        Returns:
            The WorkspaceView, or None if not found
        """
        return self._workspaces.get(_safe_text(workspace_id))

    def switch_workspace(self, workspace_id: str) -> WorkspaceSwitchResult:
        """Switch to a different workspace.

        Args:
            workspace_id: The target workspace ID

        Returns:
            A WorkspaceSwitchResult indicating the outcome
        """
        normalized_id = _safe_text(workspace_id)
        if not normalized_id:
            return WorkspaceSwitchResult(
                success=False,
                error_reason="Workspace ID is required",
            )

        if normalized_id not in self._workspaces:
            return WorkspaceSwitchResult(
                success=False,
                error_reason=f"Workspace not found: {workspace_id}",
            )

        if self._workspace_switcher:
            return self._workspace_switcher(normalized_id)

        # Default implementation
        previous_id = self._current_workspace_id
        self._current_workspace_id = normalized_id
        return WorkspaceSwitchResult(
            success=True,
            workspace_id=normalized_id,
            previous_workspace_id=previous_id,
        )

    def register_workspace(self, view: WorkspaceView) -> None:
        """Register a workspace view.

        Args:
            view: The WorkspaceView to register
        """
        self._workspaces[view.workspace_id] = view

    def unregister_workspace(self, workspace_id: str) -> WorkspaceView | None:
        """Unregister a workspace view.

        Args:
            workspace_id: The workspace ID to unregister

        Returns:
            The removed WorkspaceView, or None if not found
        """
        return self._workspaces.pop(_safe_text(workspace_id), None)

    def set_current_workspace_id(self, workspace_id: str | None) -> None:
        """Set the current workspace ID directly.

        Args:
            workspace_id: The workspace ID, or None to clear
        """
        self._current_workspace_id = _safe_text(workspace_id) if workspace_id else None

    def set_workspace_switcher(self, switcher: Callable[[str], WorkspaceSwitchResult]) -> None:
        """Set the workspace switch handler.

        Args:
            switcher: A function that handles workspace switching
        """
        self._workspace_switcher = switcher

    def set_workspace_lister(self, lister: Callable[[], list[WorkspaceView]]) -> None:
        """Set the workspace list handler.

        Args:
            lister: A function that returns the list of workspaces
        """
        self._workspace_lister = lister

    def clear(self) -> None:
        """Clear all registered workspaces."""
        self._workspaces.clear()
        self._current_workspace_id = None


__all__ = [
    "WorkspaceKind",
    "WorkspaceStatusKind",
    "WorkspaceSwitchResult",
    "WorkspaceUserService",
    "WorkspaceView",
]
