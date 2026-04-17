"""Runtime-owned support seam for agent construction and KB/config helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

from mini_agent.agent_core.engine import Agent
from mini_agent.runtime.read_models.session_payload_codec import RuntimeSessionPayloadCodec


BuildAgentFn = Callable[[Path], Awaitable[Agent]]
BuildSelectedAgentFn = Callable[[Path, str | None, str | None, str | None], Awaitable[Agent]]
LoadRuntimeConfigFn = Callable[[], Any]


def _missing_runtime_config_loader() -> Any:
    raise RuntimeError("Runtime config loader was not injected.")


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


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


__all__ = [
    "BuildAgentFn",
    "BuildSelectedAgentFn",
    "LoadRuntimeConfigFn",
    "RuntimeSessionAgentSupport",
]
