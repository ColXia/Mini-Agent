"""Shared local-session agent rebuild semantics for TUI-owned runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _agent_model_label(agent: Any) -> str | None:
    llm_client_model = _safe_text(getattr(getattr(agent, "llm_client", None), "model", None))
    if llm_client_model:
        return llm_client_model
    llm_model = _safe_text(getattr(getattr(agent, "llm", None), "model", None))
    return llm_model or None


@dataclass(frozen=True, slots=True)
class LocalSessionAgentRebuildOutcome:
    warmed_agent: Any | None
    selected_identity: tuple[str, str, str] | None
    active_model_label: str | None


@dataclass(slots=True)
class LocalSessionAgentRuntimeHandler:
    """Own shared local-runtime rebuild flow beneath TUI coordinators."""

    selected_model_identity: Callable[[Any], tuple[str, str, str] | None]
    set_selected_model_identity: Callable[[Any, tuple[str, str, str] | None], None]
    set_pending_model_identity: Callable[[Any, tuple[str, str, str] | None], None]
    clear_pending_skill_reload: Callable[[Any], None]
    capture_session_agent_snapshot: Callable[[Any], None]
    shutdown_submission_loop: Callable[[Any], Awaitable[None]]
    reset_runtime_execution_state: Callable[[Any], None]
    warm_session_agent: Callable[[Any, str], Awaitable[Any | None]]
    format_model_identity: Callable[[tuple[str, str, str] | None], str]
    persist_session_state: Callable[[], None]

    async def rebuild_with_identity(
        self,
        session: Any,
        *,
        identity: tuple[str, str, str],
        warm_prefix: str,
        clear_pending_model_identity: bool = False,
        clear_pending_skill_reload_on_success: bool = False,
        persist_before_warm: bool = False,
    ) -> LocalSessionAgentRebuildOutcome:
        self.set_selected_model_identity(session, identity)
        return await self._rebuild(
            session,
            warm_prefix=warm_prefix,
            clear_pending_model_identity=clear_pending_model_identity,
            clear_pending_skill_reload_on_success=clear_pending_skill_reload_on_success,
            persist_before_warm=persist_before_warm,
        )

    async def rebuild_current_identity(
        self,
        session: Any,
        *,
        warm_prefix: str,
        clear_pending_model_identity: bool = False,
        clear_pending_skill_reload_on_success: bool = False,
        persist_before_warm: bool = False,
    ) -> LocalSessionAgentRebuildOutcome:
        identity = self.selected_model_identity(session)
        if identity is not None:
            self.set_selected_model_identity(session, identity)
        return await self._rebuild(
            session,
            warm_prefix=warm_prefix,
            clear_pending_model_identity=clear_pending_model_identity,
            clear_pending_skill_reload_on_success=clear_pending_skill_reload_on_success,
            persist_before_warm=persist_before_warm,
        )

    async def _rebuild(
        self,
        session: Any,
        *,
        warm_prefix: str,
        clear_pending_model_identity: bool,
        clear_pending_skill_reload_on_success: bool,
        persist_before_warm: bool,
    ) -> LocalSessionAgentRebuildOutcome:
        if clear_pending_model_identity:
            self.set_pending_model_identity(session, None)
        self.capture_session_agent_snapshot(session)
        await self.shutdown_submission_loop(session)
        self.reset_runtime_execution_state(session)
        if persist_before_warm:
            self.persist_session_state()
        warmed_agent = await self.warm_session_agent(session, prefix=warm_prefix)
        if warmed_agent is not None and clear_pending_skill_reload_on_success:
            self.clear_pending_skill_reload(session)
            self.persist_session_state()

        current_identity = self.selected_model_identity(session)
        current_label = self.format_model_identity(current_identity)
        fallback_label = _agent_model_label(warmed_agent) or _agent_model_label(
            getattr(getattr(session, "runtime", None), "agent", None)
        )
        active_model_label = fallback_label if current_label == "auto" and fallback_label else current_label
        return LocalSessionAgentRebuildOutcome(
            warmed_agent=warmed_agent,
            selected_identity=current_identity,
            active_model_label=active_model_label or None,
        )


__all__ = [
    "LocalSessionAgentRebuildOutcome",
    "LocalSessionAgentRuntimeHandler",
]
