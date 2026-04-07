"""Memory provider abstraction for user/profile memory backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class MemoryProvider(ABC):
    """Abstract provider contract for pluggable memory backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""

    @property
    @abstractmethod
    def workspace_root(self) -> Path:
        """Workspace root for this provider instance."""

    @abstractmethod
    def prefetch(self) -> dict[str, Any]:
        """Prefetch memory snapshot before the next agent turn."""

    @abstractmethod
    def sync_turn(
        self,
        *,
        user_message: str | None = None,
        assistant_message: str | None = None,
    ) -> None:
        """Sync one turn of interaction."""

    @abstractmethod
    def on_session_end(self) -> None:
        """Hook called when the session is ending."""

    @abstractmethod
    def on_delegation(
        self,
        *,
        delegated_task: str,
        delegation_summary: str | None = None,
    ) -> None:
        """Hook called when a subtask is delegated."""
