"""Agent rebuild / runtime reconfiguration extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Iterable, Sequence

from mini_agent.agent_core.engine import Agent
from mini_agent.runtime.read_models.session_payload_codec import RuntimeSessionPayloadCodec
from mini_agent.runtime.orchestration.session_runtime_policy_coordinator import SessionRuntimePolicyService

if TYPE_CHECKING:
    from mini_agent.session.store_records import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


BuildAgentFn = Callable[[Path], Awaitable[Agent]]
BuildSelectedAgentFn = Callable[[Path, str | None, str | None, str | None], Awaitable[Agent]]
LoadRuntimeConfigFn = Callable[[], Any]


def _missing_runtime_config_loader() -> Any:
    raise RuntimeError("Runtime config loader was not injected.")


class RuntimeSessionAgentSupport:
    """Own runtime-local agent build/config/KB inspection helpers."""

    def __init__(
        self,
        *,
        build_agent: BuildAgentFn,
        build_agent_with_selection: BuildSelectedAgentFn | None = None,
        load_runtime_config: LoadRuntimeConfigFn | None = None,
        payload_codec: RuntimeSessionPayloadCodec | None = None,
    ) -> None:
        self._build_agent = build_agent
        self._build_agent_with_selection = build_agent_with_selection
        self._load_runtime_config = load_runtime_config or _missing_runtime_config_loader
        self._payload_codec = payload_codec or RuntimeSessionPayloadCodec()

    @staticmethod
    def agent_knowledge_base_enabled(agent: Any) -> bool:
        checker = getattr(agent, "knowledge_base_enabled", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                pass
        tools = getattr(agent, "tools", None)
        if isinstance(tools, dict):
            return "knowledge_base_query" in tools
        return True

    @classmethod
    def apply_agent_knowledge_base_enabled(cls, agent: Any, enabled: bool) -> bool:
        setter = getattr(agent, "set_knowledge_base_enabled", None)
        if callable(setter):
            try:
                return bool(setter(enabled))
            except Exception:
                return cls.agent_knowledge_base_enabled(agent)
        return cls.agent_knowledge_base_enabled(agent)

    async def build_agent_for_identity(
        self,
        workspace_dir: Path,
        identity: tuple[str, str, str] | None,
    ) -> Agent:
        if identity is None or self._build_agent_with_selection is None:
            return await self._build_agent(workspace_dir)
        source, provider_id, model_id = identity
        return await self._build_agent_with_selection(
            workspace_dir,
            source,
            provider_id,
            model_id,
        )

    @staticmethod
    def runtime_policy_overrides_from_diagnostics(
        value: Any,
    ) -> tuple[str | None, str | None]:
        diagnostics = RuntimeSessionPayloadCodec.normalize_sandbox_diagnostics_payload(value)
        approval_profile = _safe_text(diagnostics.get("approval_profile")).lower() or None
        access_level = _safe_text(diagnostics.get("access_level")).lower() or None
        return approval_profile, access_level

    def agent_messages(self, agent: Any) -> list[Any]:
        return self._payload_codec.agent_messages(agent)

    def serialize_agent_messages(self, agent: Any) -> list[dict[str, Any]]:
        return self._payload_codec.serialize_live_agent_messages(agent)

    def agent_message_count(self, agent: Any) -> int:
        return self._payload_codec.agent_message_count(agent)

    def agent_token_usage(self, agent: Any) -> int:
        return self._payload_codec.agent_token_usage(agent)

    def agent_token_limit(self, agent: Any) -> int:
        return self._payload_codec.agent_token_limit(agent)

    def agent_last_prepared_context(self, agent: Any) -> dict[str, Any]:
        return self._payload_codec.agent_last_prepared_context(agent)

    def agent_prepared_context_diagnostics(self, agent: Any) -> dict[str, Any]:
        return self._payload_codec.agent_prepared_context_diagnostics(agent)

    def agent_last_memory_automation(self, agent: Any) -> dict[str, Any]:
        return self._payload_codec.agent_last_memory_automation(agent)

    def agent_last_runtime_task_memory(self, agent: Any) -> dict[str, Any]:
        return self._payload_codec.agent_last_runtime_task_memory(agent)

    def load_runtime_config(self) -> Any:
        return self._load_runtime_config()


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
    same_workspace: Callable[[Path, Path], bool]
    selected_model_identity: Callable[["MainAgentSessionState"], tuple[str, str, str] | None]
    pending_model_identity: Callable[["MainAgentSessionState"], tuple[str, str, str] | None]
    agent_messages: Callable[[Any], list[Any]] | None = None
    build_sandbox_diagnostics_for_session: Callable[["MainAgentSessionState"], dict[str, Any]] | None = None
    refresh_runtime_projection: Callable[["MainAgentSessionState"], tuple[dict[str, Any], dict[str, Any]]] | None = None

    def desired_runtime_policy_for_session(
        self,
        session: "MainAgentSessionState",
    ) -> tuple[str | None, str | None]:
        approval_profile, access_level = self.runtime_policy_overrides_from_diagnostics(
            session.projection.sandbox_diagnostics
        )
        if approval_profile or access_level:
            return approval_profile, access_level
        return SessionRuntimePolicyService.desired_runtime_policy_from_diagnostics(
            session.projection.sandbox_diagnostics
        )

    @staticmethod
    def effective_runtime_policy_for_agent(agent: Any) -> tuple[str, str]:
        return SessionRuntimePolicyService.effective_runtime_policy_for_agent(agent)

    def reconfigure_runtime_policy(
        self,
        session: "MainAgentSessionState",
        *,
        approval_profile: str | None,
        access_level: str | None,
    ) -> dict[str, Any]:
        self.reconfigure_agent_runtime_policy(
            agent=session.runtime.agent,
            config=self.load_runtime_config(),
            workspace_dir=session.workspace_dir,
            approval_profile_override=approval_profile,
            access_level_override=access_level,
        )
        return self._refresh_sandbox_diagnostics(session)

    async def rebuild_agent_with_identity(
        self,
        session: "MainAgentSessionState",
        identity: tuple[str, str, str] | None,
    ) -> None:
        self.capture_agent_prepared_context_state(session)
        serialized_messages = self.serialize_agent_messages(self._agent_messages(session.runtime.agent))
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
        session.projection.knowledge_base_enabled = bool(
            self.apply_agent_knowledge_base_enabled(
                rebuilt,
                bool(session.projection.knowledge_base_enabled),
            )
        )
        session.runtime.agent = rebuilt
        effective_identity = self.route_model_identity(rebuilt) or identity
        self.set_selected_model_identity(session, effective_identity)
        self.set_pending_model_identity(session, None)
        self.clear_pending_skill_reload(session)
        self.restore_agent_prepared_context_state(session)
        self._refresh_sandbox_diagnostics(session)

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

    def _agent_messages(self, agent: Any) -> list[Any]:
        if self.agent_messages is not None:
            return list(self.agent_messages(agent))
        return list(getattr(agent, "messages", []) or [])

    def _refresh_sandbox_diagnostics(
        self,
        session: "MainAgentSessionState",
    ) -> dict[str, Any]:
        if self.refresh_runtime_projection is not None:
            _, sandbox = self.refresh_runtime_projection(session)
            return dict(sandbox)
        if self.build_sandbox_diagnostics_for_session is not None:
            sandbox = self.build_sandbox_diagnostics_for_session(session)
            session.projection.sandbox_diagnostics = dict(sandbox)
            return dict(session.projection.sandbox_diagnostics)
        return dict(session.projection.sandbox_diagnostics or {})


__all__ = [
    "BuildAgentFn",
    "BuildSelectedAgentFn",
    "LoadRuntimeConfigFn",
    "RuntimeSessionAgentSupport",
    "RuntimeSessionAgentRuntimeHandler",
    "RuntimeWorkspaceSkillReloadQueueResult",
]



