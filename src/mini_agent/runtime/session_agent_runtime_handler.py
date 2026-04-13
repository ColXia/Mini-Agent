"""Agent rebuild / runtime reconfiguration extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Iterable, Sequence

from mini_agent.runtime.sandbox_state import normalize_sandbox_diagnostics

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeWorkspaceSkillReloadQueueResult:
    queued_session_ids: tuple[str, ...]
    touched_sessions: tuple["MainAgentSessionState", ...]


@dataclass(slots=True)
class RuntimeSessionAgentRuntimeHandler:
    runtime_policy_overrides_from_diagnostics: Callable[[Any], tuple[str | None, str | None]]
    build_agent_for_identity: Callable[[Path, tuple[str, str, str] | None], Awaitable[Any]]
    load_runtime_config: Callable[[], Any]
    reconfigure_agent_runtime_policy: Callable[..., dict[str, Any]]
    capture_agent_prepared_context_state: Callable[["MainAgentSessionState"], None]
    restore_agent_prepared_context_state: Callable[["MainAgentSessionState"], None]
    serialize_agent_messages: Callable[[Sequence[Any]], list[dict[str, Any]]]
    restore_agent_messages_payload: Callable[[Sequence[Any], Any], None]
    apply_agent_knowledge_base_enabled: Callable[[Any, bool], bool]
    route_model_identity: Callable[[Any], tuple[str, str, str] | None]
    set_selected_model_identity: Callable[["MainAgentSessionState", tuple[str, str, str] | None], None]
    set_pending_model_identity: Callable[["MainAgentSessionState", tuple[str, str, str] | None], None]
    build_sandbox_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]]
    same_workspace: Callable[[Path, Path], bool]
    selected_model_identity: Callable[["MainAgentSessionState"], tuple[str, str, str] | None]
    pending_model_identity: Callable[["MainAgentSessionState"], tuple[str, str, str] | None]

    def desired_runtime_policy_for_session(
        self,
        session: "MainAgentSessionState",
    ) -> tuple[str | None, str | None]:
        return self.runtime_policy_overrides_from_diagnostics(session.projection.sandbox_diagnostics)

    @staticmethod
    def effective_runtime_policy_for_agent(agent: Any) -> tuple[str, str]:
        policy = getattr(getattr(agent, "runtime_policy_engine", None), "policy", None)
        approval_profile = _safe_text(getattr(policy, "approval_profile", None)).lower() or "build"
        access_level = _safe_text(getattr(policy, "access_level", None)).lower() or "default"
        return approval_profile, access_level

    def reconfigure_runtime_policy(
        self,
        session: "MainAgentSessionState",
        *,
        approval_profile: str | None,
        access_level: str | None,
    ) -> dict[str, Any]:
        diagnostics = self.reconfigure_agent_runtime_policy(
            agent=session.runtime.agent,
            config=self.load_runtime_config(),
            workspace_dir=session.workspace_dir,
            approval_profile_override=approval_profile,
            access_level_override=access_level,
        )
        session.projection.sandbox_diagnostics = normalize_sandbox_diagnostics(diagnostics)
        return session.projection.sandbox_diagnostics

    async def rebuild_agent_with_identity(
        self,
        session: "MainAgentSessionState",
        identity: tuple[str, str, str] | None,
    ) -> None:
        self.capture_agent_prepared_context_state(session)
        serialized_messages = self.serialize_agent_messages(getattr(session.runtime.agent, "messages", []) or [])
        rebuilt = await self.build_agent_for_identity(session.workspace_dir, identity)
        desired_approval_profile, desired_access_level = self.desired_runtime_policy_for_session(session)
        if desired_approval_profile or desired_access_level:
            try:
                self.reconfigure_agent_runtime_policy(
                    agent=rebuilt,
                    config=self.load_runtime_config(),
                    workspace_dir=session.workspace_dir,
                    approval_profile_override=desired_approval_profile,
                    access_level_override=desired_access_level,
                )
            except Exception:
                pass
        self.restore_agent_messages_payload(serialized_messages, rebuilt)
        session.projection.knowledge_base_enabled = self.apply_agent_knowledge_base_enabled(
            rebuilt,
            bool(session.projection.knowledge_base_enabled),
        )
        session.runtime.agent = rebuilt
        effective_identity = self.route_model_identity(rebuilt) or identity
        self.set_selected_model_identity(session, effective_identity)
        self.set_pending_model_identity(session, None)
        self.clear_pending_skill_reload(session)
        self.restore_agent_prepared_context_state(session)
        session.projection.sandbox_diagnostics = self.build_sandbox_diagnostics_for_session(session)

    def queue_workspace_skill_reload(
        self,
        workspace_dir: Path,
        *,
        sessions: Iterable["MainAgentSessionState"],
        current_session_id: str | None,
        reason: str,
        include_current: bool,
    ) -> RuntimeWorkspaceSkillReloadQueueResult:
        normalized_reason = _safe_text(reason) or "workspace skill runtime changed"
        queued: list["MainAgentSessionState"] = []
        queued_ids: list[str] = []
        for candidate in sessions:
            if not self.same_workspace(candidate.workspace_dir, workspace_dir):
                continue
            if current_session_id and candidate.session_id == current_session_id and not include_current:
                continue
            if candidate.runtime.agent is None and self.pending_model_identity(candidate) is None:
                continue
            self.mark_pending_skill_reload(candidate, reason=normalized_reason)
            candidate.touch()
            queued.append(candidate)
            queued_ids.append(candidate.session_id)
        return RuntimeWorkspaceSkillReloadQueueResult(
            queued_session_ids=tuple(queued_ids),
            touched_sessions=tuple(queued),
        )

    async def apply_pending_model_selection(
        self,
        session: "MainAgentSessionState",
        *,
        pending_identity: tuple[str, str, str] | None,
    ) -> bool:
        if pending_identity is None:
            return False
        await self.rebuild_agent_with_identity(session, pending_identity)
        return True

    async def apply_pending_skill_reload(
        self,
        session: "MainAgentSessionState",
    ) -> bool:
        if session.projection.busy or not bool(session.projection.pending_skill_reload):
            return False
        if self.pending_model_identity(session) is not None:
            return False
        identity = self.selected_model_identity(session)
        if identity is None:
            return False
        await self.rebuild_agent_with_identity(session, identity)
        return True

    @staticmethod
    def clear_pending_skill_reload(session: "MainAgentSessionState") -> None:
        session.projection.pending_skill_reload = False
        session.projection.pending_skill_reload_reason = ""

    @staticmethod
    def mark_pending_skill_reload(session: "MainAgentSessionState", *, reason: str) -> None:
        session.projection.pending_skill_reload = True
        session.projection.pending_skill_reload_reason = _safe_text(reason) or "workspace skill runtime changed"


__all__ = [
    "RuntimeSessionAgentRuntimeHandler",
    "RuntimeWorkspaceSkillReloadQueueResult",
]
