"""Brand-new session creation routing extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    from mini_agent.agent_core.engine import Agent
    from mini_agent.agent_core.session import SessionLifecycleState
    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True, slots=True)
class RuntimeSessionCreationCommand:
    session_id: str
    workspace_dir: "Path"
    title: str | None = None
    default_title: str | None = None
    is_default: bool = False
    surface: str | None = None
    surface_provided: bool = False
    default_surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    shared: bool = False


@dataclass(slots=True)
class RuntimeSessionCreationHandler:
    allocate_session_title: Callable[[str, Any], str]
    normalize_surface: Callable[[str | None], str]
    normalize_channel_type: Callable[[str | None], str | None]
    build_agent_for_identity: Callable[[Any, tuple[str, str, str] | None], Awaitable["Agent"]]
    agent_knowledge_base_enabled: Callable[[Any], bool]
    collect_sandbox_diagnostics: Callable[[Any], dict[str, Any]]
    route_model_identity: Callable[[Any], tuple[str, str, str] | None]
    bootstrap_session_lifecycle: Callable[[str, Any, "datetime"], "SessionLifecycleState"] | None = None
    build_session_key: Callable[[str, Any], Any] | None = None
    lifecycle_bootstrap: Callable[[Any, "datetime"], "SessionLifecycleState"] | None = None

    async def create(
        self,
        command: RuntimeSessionCreationCommand,
        *,
        now_utc: "datetime",
    ) -> "MainAgentSessionState":
        from mini_agent.runtime.session_state import (
            MainAgentSessionLineageState,
            MainAgentSessionProjectionState,
            MainAgentSessionRuntimeHostState,
            MainAgentSessionState,
        )

        agent = await self.build_agent_for_identity(command.workspace_dir, None)
        lifecycle_state = self._bootstrap_lifecycle_state(
            session_id=command.session_id,
            workspace_dir=command.workspace_dir,
            now_utc=now_utc,
        )
        selected_identity = self.route_model_identity(agent)
        knowledge_base_enabled = self.agent_knowledge_base_enabled(agent)
        sandbox_diagnostics = self.collect_sandbox_diagnostics(agent)

        return MainAgentSessionState(
            session_id=command.session_id,
            workspace_dir=command.workspace_dir,
            lifecycle_state=lifecycle_state,
            runtime=MainAgentSessionRuntimeHostState(agent=agent),
            created_at=now_utc,
            updated_at=now_utc,
            lineage_state=MainAgentSessionLineageState(
                parent_session_id=None,
                root_session_id=command.session_id,
                reason="root",
                created_at=now_utc,
            ),
            projection=MainAgentSessionProjectionState(
                title=self._resolve_title(command),
                origin_surface=self._resolve_surface(command),
                active_surface=self._resolve_surface(command),
                is_default=bool(command.is_default),
                channel_type=self.normalize_channel_type(command.channel_type),
                conversation_id=_safe_text(command.conversation_id) or None,
                sender_id=_safe_text(command.sender_id) or None,
                shared=bool(command.shared),
                knowledge_base_enabled=knowledge_base_enabled,
                selected_model_source=selected_identity[0] if selected_identity is not None else None,
                selected_provider_id=selected_identity[1] if selected_identity is not None else None,
                selected_model_id=selected_identity[2] if selected_identity is not None else None,
                sandbox_diagnostics=sandbox_diagnostics,
            ),
        )

    def _resolve_title(self, command: RuntimeSessionCreationCommand) -> str:
        base_title = _safe_text(command.title) or _safe_text(command.default_title)
        if not base_title:
            return ""
        if command.is_default:
            return base_title
        return self.allocate_session_title(base_title, command.workspace_dir)

    def _resolve_surface(self, command: RuntimeSessionCreationCommand) -> str:
        if command.surface_provided:
            return self.normalize_surface(command.surface)
        fallback = command.default_surface
        if fallback is None:
            return ""
        return self.normalize_surface(fallback)

    def _bootstrap_lifecycle_state(
        self,
        *,
        session_id: str,
        workspace_dir: Any,
        now_utc: "datetime",
    ) -> "SessionLifecycleState":
        if callable(self.bootstrap_session_lifecycle):
            return self.bootstrap_session_lifecycle(session_id, workspace_dir, now_utc)
        if callable(self.build_session_key) and callable(self.lifecycle_bootstrap):
            session_key = self.build_session_key(session_id, workspace_dir)
            return self.lifecycle_bootstrap(session_key, now_utc)
        raise TypeError("RuntimeSessionCreationHandler requires lifecycle bootstrap wiring.")


__all__ = [
    "RuntimeSessionCreationCommand",
    "RuntimeSessionCreationHandler",
]
