"""Runtime port for session-task ownership seams."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from mini_agent.agent_core.engine import Agent
from mini_agent.interfaces.agent import (
    MainAgentSessionDetail,
    MainAgentSessionMessage,
    MainAgentSessionSummary,
)


class ManagedRuntimeSessionPort(Protocol):
    """Minimal managed-session view exposed to the session-task application seam."""

    @property
    def session_id(self) -> str: ...

    @property
    def workspace_dir(self) -> Path: ...

    @property
    def agent(self) -> Agent: ...

    @property
    def active_surface(self) -> str: ...

    @property
    def origin_surface(self) -> str: ...

    @property
    def channel_type(self) -> str | None: ...

    @property
    def conversation_id(self) -> str | None: ...

    @property
    def sender_id(self) -> str | None: ...

    @property
    def context_policy(self) -> dict[str, Any]: ...

    @property
    def cancel_event(self) -> Any: ...

    @property
    def busy(self) -> bool: ...

    @property
    def running_state(self) -> str: ...

    @running_state.setter
    def running_state(self, value: str) -> None: ...

    @property
    def pending_approvals(self) -> list[dict[str, Any]]: ...

    @property
    def updated_at(self) -> Any: ...

    @property
    def token_usage(self) -> int: ...

    @property
    def message_count(self) -> int: ...

    def touch(self) -> None: ...


class SessionTurnScopePort(Protocol):
    """Turn-scope lifecycle hooks exposed to the session-task application seam."""

    async def enter(
        self,
        session: Any,
        *,
        surface: str | None,
        channel_type: str | None,
        conversation_id: str | None,
        sender_id: str | None,
        user_message: str,
        running_detail: str,
    ) -> dict[str, Any] | None: ...

    async def exit(self, session: Any) -> None: ...

    def touch(self, session: Any) -> None: ...

    def restore_prepared_context_state(self, session: Any) -> None: ...

    def capture_prepared_context_state(self, session: Any) -> None: ...

    def clear_recovery_context(self, session: Any) -> None: ...

    def record_message(
        self,
        session: Any,
        *,
        role: str,
        content: str,
        surface: str | None,
        metadata: dict[str, Any] | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> None: ...

    def record_activity(
        self,
        session: Any,
        *,
        label: str,
        detail: str,
        surface: str | None,
        activity_id: str | None = None,
        preview: str = "",
        output_text: str = "",
        state: str = "",
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

    def record_pending_approval(
        self,
        session: Any,
        *,
        payload: dict[str, Any],
        future: Any,
    ) -> dict[str, Any]: ...

    def clear_pending_approval(
        self,
        session: Any,
        *,
        token: str | None = None,
    ) -> None: ...


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

__all__ = [
    "ManagedRuntimeSessionPort",
    "SessionTaskRuntimePort",
    "SessionTurnScopePort",
]
