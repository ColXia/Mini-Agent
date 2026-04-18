"""Workspace-runtime execution modes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WorkspaceRuntimeMode(str, Enum):
    """Maintained workspace execution modes from the v11.1 baseline."""

    DIRECT = "direct"
    CONTAINER_MOUNTED = "container_mounted"
    ISOLATED_COPY = "isolated_copy"


@dataclass(frozen=True, slots=True)
class WorkspaceRuntimeDescriptor:
    """Compact descriptor for one workspace execution environment."""

    mode: WorkspaceRuntimeMode
    mounted: bool = True
    writable: bool = True


__all__ = [
    "WorkspaceRuntimeDescriptor",
    "WorkspaceRuntimeMode",
]
