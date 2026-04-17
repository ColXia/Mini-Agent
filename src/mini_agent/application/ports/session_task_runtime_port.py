"""Runtime port for session-task ownership seams."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from mini_agent.agent_core.engine import Agent
from mini_agent.interfaces import (
    MainAgentSessionDetail,
    MainAgentSessionMessage,
    MainAgentSessionSummary,
)

from .session_runtime_port import ManagedRuntimeSessionPort, SessionTurnScopePort


class SessionTaskRuntimePort(Protocol):
    """Narrow runtime contract for session CRUD, read models, and turn prep."""

    @property
    def turn_scope_handler(self) -> SessionTurnScopePort: ...

    def validate_workspace(self, workspace_dir: Path) -> None: ...

    async def list_sessions(
        self,
        *,
        workspace_dir: Path | None = None,
        shared_only: bool = False,
    ) -> list[MainAgentSessionSummary]: ...

    async def ensure_default_session(
        self,
        workspace_dir: Path,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> ManagedRuntimeSessionPort: ...

    async def create_session(
        self,
        *,
        workspace_dir: Path,
        title: str | None = None,
        surface: str | None = None,
        shared: bool = False,
    ) -> ManagedRuntimeSessionPort: ...

    async def create_derived_session(
        self,
        *,
        parent_session_id: str,
        title: str | None = None,
        reason: str = "fork",
        metadata: dict[str, Any] | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> ManagedRuntimeSessionPort: ...

    async def get_session_detail(self, session_id: str, *, recent_limit: int = 50) -> MainAgentSessionDetail: ...

    async def get_recent_messages(self, session_id: str, *, limit: int = 10) -> list[MainAgentSessionMessage]: ...

    async def delete_session(self, session_id: str) -> None: ...

    async def rename_session(self, session_id: str, *, title: str) -> MainAgentSessionSummary: ...

    async def set_session_shared(self, session_id: str, *, shared: bool) -> MainAgentSessionSummary: ...

    async def reset_session(self, session_id: str) -> None: ...

    async def build_ephemeral_agent(self, workspace_dir: Path) -> Agent: ...

    async def get_or_create_session(
        self,
        session_id: str | None,
        workspace_dir: Path,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        session_title_hint: str | None = None,
    ) -> ManagedRuntimeSessionPort: ...

    async def ensure_session_runtime_policy_ready_for_turn(
        self,
        session: ManagedRuntimeSessionPort,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> Any: ...


__all__ = ["SessionTaskRuntimePort"]
