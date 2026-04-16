"""Shared runtime-contract test doubles for runtime-facing surface tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence

from mini_agent.agent_core.runtime_bindings import AgentRuntimeServices


def resolve_runtime_provider_id(
    *,
    provider_source: str | None = None,
    provider_id: str | None = None,
    runtime_provider_id: str | None = None,
) -> str | None:
    if runtime_provider_id:
        return str(runtime_provider_id)
    if not provider_id:
        return None
    if provider_source == "preset":
        return f"preset-{provider_id}"
    return str(provider_id)


class RuntimeContractAgentStub:
    """Small agent-like test double aligned to the maintained runtime contract."""

    def __init__(
        self,
        *,
        model: str = "gpt-test",
        provider_source: str | None = None,
        provider_id: str | None = None,
        runtime_provider_id: str | None = None,
        messages: Sequence[Any] | None = None,
        api_total_tokens: int = 0,
        token_limit: int = 0,
        expose_llm: bool = False,
        expose_llm_client: bool = False,
        knowledge_base_enabled: bool = True,
        include_knowledge_base_tool: bool = False,
        prepared_context: dict[str, Any] | None = None,
        prepared_context_diagnostics: dict[str, Any] | None = None,
        last_memory_automation: dict[str, Any] | None = None,
        last_runtime_task_memory: dict[str, Any] | None = None,
        runtime_services: AgentRuntimeServices | None = None,
    ) -> None:
        self.messages = list(messages) if messages is not None else [SimpleNamespace(role="system", content="system")]
        self.api_total_tokens = max(0, int(api_total_tokens))
        self.token_limit = max(0, int(token_limit))
        self.runtime_services = runtime_services or AgentRuntimeServices()
        self.last_prepared_turn_context = dict(prepared_context or {}) if prepared_context is not None else None
        self.prepared_context_diagnostics = dict(prepared_context_diagnostics or {})
        self.last_memory_automation = dict(last_memory_automation or {})
        self.last_runtime_task_memory = dict(last_runtime_task_memory or {})
        self._knowledge_base_enabled = bool(knowledge_base_enabled)
        self._include_knowledge_base_tool = bool(include_knowledge_base_tool)
        self.tools: dict[str, Any] = {}
        if self._include_knowledge_base_tool and self._knowledge_base_enabled:
            self.tools["knowledge_base_query"] = object()

        if expose_llm:
            self.llm = SimpleNamespace(model=model)
        if expose_llm_client:
            self.llm_client = SimpleNamespace(model=model)

        resolved_provider = resolve_runtime_provider_id(
            provider_source=provider_source,
            provider_id=provider_id,
            runtime_provider_id=runtime_provider_id,
        )
        if resolved_provider is not None:
            self.runtime_route = SimpleNamespace(provider_id=resolved_provider, model=model)

    @property
    def runtime_policy_engine(self) -> Any:
        return self.runtime_services.runtime_policy_engine

    @runtime_policy_engine.setter
    def runtime_policy_engine(self, value: Any) -> None:
        self.runtime_services = self.runtime_services.with_updates(runtime_policy_engine=value)

    @property
    def approval_engine(self) -> Any:
        return self.runtime_services.approval_engine

    @approval_engine.setter
    def approval_engine(self, value: Any) -> None:
        self.runtime_services = self.runtime_services.with_updates(approval_engine=value)

    @property
    def sandbox_manager(self) -> Any:
        return self.runtime_services.sandbox_manager

    @sandbox_manager.setter
    def sandbox_manager(self, value: Any) -> None:
        self.runtime_services = self.runtime_services.with_updates(sandbox_manager=value)

    @property
    def tool_approval_handler(self) -> Any:
        return self.runtime_services.tool_approval_handler

    @tool_approval_handler.setter
    def tool_approval_handler(self, value: Any) -> None:
        self.runtime_services = self.runtime_services.with_updates(tool_approval_handler=value)

    def knowledge_base_enabled(self) -> bool:
        return self._knowledge_base_enabled

    def set_knowledge_base_enabled(self, enabled: bool) -> bool:
        self._knowledge_base_enabled = bool(enabled)
        if self._include_knowledge_base_tool:
            if self._knowledge_base_enabled:
                self.tools["knowledge_base_query"] = object()
            else:
                self.tools.pop("knowledge_base_query", None)
        return self._knowledge_base_enabled

    def add_user_message(self, content: str) -> None:
        self.messages.append(SimpleNamespace(role="user", content=content))

    def append_assistant_message(self, content: str) -> None:
        self.messages.append(SimpleNamespace(role="assistant", content=content))


def runtime_policy_engine_stub(
    *,
    approval_profile: str = "build",
    access_level: str = "default",
    sandbox_mode: str = "workspace",
) -> Any:
    return SimpleNamespace(
        policy=SimpleNamespace(
            approval_profile=approval_profile,
            access_level=access_level,
            sandbox_mode=sandbox_mode,
        )
    )


def sandbox_manager_stub(
    *,
    backend: str = "none",
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
    network_mode: str = "allow_all",
    allow_domains: Sequence[str] = (),
    block_domains: Sequence[str] = (),
) -> Any:
    selection = SimpleNamespace(
        backend=backend,
        reason=reason,
        metadata=dict(metadata or {}),
    )
    return SimpleNamespace(
        select_initial=lambda: selection,
        network_policy=SimpleNamespace(
            mode=SimpleNamespace(value=network_mode),
            allow_domains=tuple(allow_domains),
            block_domains=tuple(block_domains),
        ),
    )


def runtime_projection_stub(**overrides: Any) -> Any:
    payload = {
        "knowledge_base_enabled": True,
        "last_prepared_context": {},
        "prepared_context_diagnostics": {},
        "memory_diagnostics": {},
        "sandbox_diagnostics": {},
        "pending_skill_reload": False,
        "pending_skill_reload_reason": "",
        "recovery_context_pending": False,
        "recovery_state": "",
        "recovery_summary": "",
        "recovery_last_activity": None,
        "recovery_last_user_message": None,
        "recovery_last_assistant_message": None,
        "recovery_pending_approvals": [],
        "busy": False,
        "running_state": "",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def lineage_state_stub(
    *,
    parent_session_id: str | None = None,
    root_session_id: str = "sess-1",
    reason: str = "root",
    created_at: Any = None,
    metadata: dict[str, Any] | None = None,
    **overrides: Any,
) -> Any:
    payload = {
        "parent_session_id": parent_session_id,
        "root_session_id": root_session_id,
        "reason": reason,
        "created_at": created_at,
        "metadata": dict(metadata or {}),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def transcript_entry_stub(
    *,
    role: str = "user",
    content: str = "",
    surface: str = "tui",
    created_at: Any = None,
    channel_type: str | None = None,
    conversation_id: str | None = None,
    sender_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    **overrides: Any,
) -> Any:
    payload = {
        "role": role,
        "content": content,
        "surface": surface,
        "created_at": created_at,
        "channel_type": channel_type,
        "conversation_id": conversation_id,
        "sender_id": sender_id,
        "metadata": dict(metadata or {}),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def transcript_state_stub(
    *,
    transcript: Sequence[Any] | None = None,
    next_transcript_index: int = 0,
    current_turn_id: str | None = None,
    **overrides: Any,
) -> Any:
    payload = {
        "transcript": list(transcript or []),
        "next_transcript_index": next_transcript_index,
        "current_turn_id": current_turn_id,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def runtime_state_stub(
    *,
    agent: Any | None = None,
    cancel_event: Any | None = None,
    pending_approvals: Sequence[Any] | None = None,
    pending_approval_waiters: dict[str, Any] | None = None,
    **overrides: Any,
) -> Any:
    payload = {
        "agent": agent,
        "cancel_event": cancel_event,
        "pending_approvals": list(pending_approvals or []),
        "pending_approval_waiters": dict(pending_approval_waiters or {}),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def runtime_session_stub(
    *,
    session_id: str = "sess-1",
    workspace_dir: str | Path = "workspace-1",
    agent: Any | None = None,
    projection: Any | None = None,
    runtime: Any | None = None,
    transcript_state: Any | None = None,
    touch: Any | None = None,
    **overrides: Any,
) -> Any:
    resolved_workspace = workspace_dir.resolve() if isinstance(workspace_dir, Path) else workspace_dir
    payload = {
        "session_id": session_id,
        "workspace_dir": resolved_workspace,
        "runtime": runtime or runtime_state_stub(agent=agent),
        "projection": projection or runtime_projection_stub(),
        "transcript_state": transcript_state or SimpleNamespace(current_turn_id=None),
        "touch": touch or (lambda **_kwargs: None),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


__all__ = [
    "RuntimeContractAgentStub",
    "lineage_state_stub",
    "resolve_runtime_provider_id",
    "runtime_policy_engine_stub",
    "runtime_projection_stub",
    "runtime_session_stub",
    "runtime_state_stub",
    "sandbox_manager_stub",
    "transcript_entry_stub",
    "transcript_state_stub",
]
