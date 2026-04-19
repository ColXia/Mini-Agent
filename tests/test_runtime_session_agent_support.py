from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from mini_agent.runtime.support.session_agent_support import RuntimeSessionAgentSupport


class _KnowledgeBaseAgent:
    def __init__(self) -> None:
        self._enabled = True
        self.tools = {"knowledge_base_query": object()}

    def knowledge_base_enabled(self) -> bool:
        return self._enabled

    def set_knowledge_base_enabled(self, enabled: bool) -> bool:
        self._enabled = bool(enabled)
        return self._enabled


@pytest.mark.asyncio
async def test_agent_support_builds_selected_identity_when_available() -> None:
    calls: list[tuple[str, str | None, str | None, str | None]] = []

    async def _build_default(_workspace_dir):
        calls.append(("default", None, None, None))
        return SimpleNamespace(kind="default")

    async def _build_selected(_workspace_dir, source, provider_id, model_id):
        calls.append((str(source), provider_id, model_id, "selected"))
        return SimpleNamespace(kind="selected", route=(source, provider_id, model_id))

    support = RuntimeSessionAgentSupport(
        build_agent=_build_default,
        build_agent_with_selection=_build_selected,
    )

    default_agent = await support.build_agent_for_identity(Path("."), None)
    selected_agent = await support.build_agent_for_identity(
        Path("."),
        ("preset", "openai", "gpt-5.4"),
    )

    assert default_agent.kind == "default"
    assert selected_agent.kind == "selected"
    assert selected_agent.route == ("preset", "openai", "gpt-5.4")
    assert calls == [
        ("default", None, None, None),
        ("preset", "openai", "gpt-5.4", "selected"),
    ]


def test_agent_support_reads_and_applies_knowledge_base_state() -> None:
    async def _build_default(_workspace_dir: Path):
        return SimpleNamespace()

    support = RuntimeSessionAgentSupport(build_agent=_build_default)
    agent = _KnowledgeBaseAgent()

    assert support.agent_knowledge_base_enabled(agent) is True
    assert support.apply_agent_knowledge_base_enabled(agent, False) is False
    assert support.agent_knowledge_base_enabled(agent) is False


def test_agent_support_normalizes_runtime_policy_overrides_and_uses_injected_config_loader() -> None:
    sentinel = object()

    async def _build_default(_workspace_dir: Path):
        return SimpleNamespace()

    support = RuntimeSessionAgentSupport(
        build_agent=_build_default,
        load_runtime_config=lambda: sentinel,  # type: ignore[arg-type]
    )

    assert support.runtime_policy_overrides_from_diagnostics(
        {"approval_profile": " Build ", "access_level": " FULL-ACCESS "}
    ) == ("build", "full-access")
    assert support.load_runtime_config() is sentinel


def test_agent_support_requires_explicit_runtime_config_loader() -> None:
    async def _build_default(_workspace_dir: Path):
        return SimpleNamespace()

    support = RuntimeSessionAgentSupport(build_agent=_build_default)

    with pytest.raises(RuntimeError, match="Runtime config loader was not injected"):
        support.load_runtime_config()


def test_agent_support_exposes_runtime_read_helpers() -> None:
    async def _build_default(_workspace_dir: Path):
        return SimpleNamespace()

    support = RuntimeSessionAgentSupport(build_agent=_build_default)
    agent = SimpleNamespace(
        messages=[
            SimpleNamespace(role="system", content="system prompt"),
            SimpleNamespace(role="assistant", content="hello"),
        ],
        api_total_tokens=17,
        token_limit=128000,
        last_prepared_turn_context={"item_count": 1},
        prepared_context_diagnostics={"turn_count": 2},
        last_memory_automation={"stored": True},
        last_runtime_task_memory={"synced": True},
    )

    assert support.agent_message_count(agent) == 2
    assert support.serialize_agent_messages(agent)[-1]["content"] == "hello"
    assert support.agent_token_usage(agent) == 17
    assert support.agent_token_limit(agent) == 128000
    assert support.agent_last_prepared_context(agent) == {"item_count": 1}
    assert support.agent_prepared_context_diagnostics(agent) == {"turn_count": 2}
    assert support.agent_last_memory_automation(agent) == {"stored": True}
    assert support.agent_last_runtime_task_memory(agent) == {"synced": True}
