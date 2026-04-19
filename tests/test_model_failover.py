"""Tests for P13 T1.5 provider failover baseline."""

from __future__ import annotations

import pytest

from mini_agent.model_manager.failover import FailoverLLMClient, ProviderFailoverError
from mini_agent.model_manager.runtime import (
    RoutedLLMSettings,
    get_health_monitor,
    reset_model_manager_runtime_state,
)
from mini_agent.schema.schema import LLMProvider, LLMCompletionResult, Message


@pytest.fixture(autouse=True)
def _reset_runtime_state():
    reset_model_manager_runtime_state()
    yield
    reset_model_manager_runtime_state()


def _route(
    *,
    provider_id: str,
    provider: LLMProvider,
    api_base: str,
    model: str,
) -> RoutedLLMSettings:
    return RoutedLLMSettings(
        source="provider_catalog",
        provider=provider,
        api_key=f"sk-{provider_id}",
        api_base=api_base,
        model=model,
        provider_id=provider_id,
        provider_name=provider_id,
        mapping_mode="exact",
        requested_model=model,
    )


class _FakeLLMClient:
    behavior: dict[tuple[str, str], object] = {}
    call_order: list[tuple[str, str]] = []

    def __init__(self, *, profile, retry_config=None):
        self.profile = profile
        self.api_key = profile.api_key
        self.provider = profile.provider
        self.api_base = profile.api_base
        self.model = profile.model
        self.retry_config = retry_config
        self.retry_callback = None

    async def generate(self, messages, tools=None):
        del messages, tools
        key = (self.api_base, self.model)
        _FakeLLMClient.call_order.append(key)
        outcome = _FakeLLMClient.behavior[key]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_failover_llm_client_switches_provider_on_error(monkeypatch):
    monkeypatch.setattr("mini_agent.model_manager.failover.LLMClient", _FakeLLMClient)
    _FakeLLMClient.call_order = []
    _FakeLLMClient.behavior = {
        ("https://anth.example.com", "claude-3-7-sonnet"): TimeoutError("read timeout"),
        ("https://openai.example.com/v1", "gpt-4o-mini"): LLMCompletionResult(
            content="ok-from-openai",
            finish_reason="stop",
        ),
    }

    llm = FailoverLLMClient(
        routes=[
            _route(
                provider_id="anth-primary",
                provider=LLMProvider.ANTHROPIC,
                api_base="https://anth.example.com",
                model="claude-3-7-sonnet",
            ),
            _route(
                provider_id="openai-secondary",
                provider=LLMProvider.OPENAI,
                api_base="https://openai.example.com/v1",
                model="gpt-4o-mini",
            ),
        ]
    )

    response = await llm.generate(messages=[Message(role="user", content="hello")])
    assert response.content == "ok-from-openai"
    assert _FakeLLMClient.call_order == [
        ("https://anth.example.com", "claude-3-7-sonnet"),
        ("https://openai.example.com/v1", "gpt-4o-mini"),
    ]

    health = get_health_monitor()
    anth_snapshot = health.snapshot("anth-primary")
    openai_snapshot = health.snapshot("openai-secondary")
    assert anth_snapshot["total_failures"] == 1
    assert openai_snapshot["total_successes"] == 1


@pytest.mark.asyncio
async def test_failover_llm_client_stops_on_cancelled_classification(monkeypatch):
    monkeypatch.setattr("mini_agent.model_manager.failover.LLMClient", _FakeLLMClient)
    _FakeLLMClient.call_order = []
    _FakeLLMClient.behavior = {
        ("https://anth.example.com", "claude-3-7-sonnet"): RuntimeError("request cancelled by user"),
        ("https://openai.example.com/v1", "gpt-4o-mini"): LLMCompletionResult(
            content="should-not-run",
            finish_reason="stop",
        ),
    }

    llm = FailoverLLMClient(
        routes=[
            _route(
                provider_id="anth-primary",
                provider=LLMProvider.ANTHROPIC,
                api_base="https://anth.example.com",
                model="claude-3-7-sonnet",
            ),
            _route(
                provider_id="openai-secondary",
                provider=LLMProvider.OPENAI,
                api_base="https://openai.example.com/v1",
                model="gpt-4o-mini",
            ),
        ]
    )

    with pytest.raises(ProviderFailoverError) as exc_info:
        await llm.generate(messages=[Message(role="user", content="hello")])
    assert len(exc_info.value.attempts) == 1
    assert exc_info.value.attempts[0].reason == "cancelled_by_user"
    assert _FakeLLMClient.call_order == [("https://anth.example.com", "claude-3-7-sonnet")]


@pytest.mark.asyncio
async def test_failover_single_route_raises_original_exception(monkeypatch):
    monkeypatch.setattr("mini_agent.model_manager.failover.LLMClient", _FakeLLMClient)
    _FakeLLMClient.call_order = []
    _FakeLLMClient.behavior = {
        ("https://anth.example.com", "claude-3-7-sonnet"): RuntimeError("upstream 500 error"),
    }

    llm = FailoverLLMClient(
        routes=[
            _route(
                provider_id="anth-primary",
                provider=LLMProvider.ANTHROPIC,
                api_base="https://anth.example.com",
                model="claude-3-7-sonnet",
            ),
        ]
    )

    with pytest.raises(RuntimeError, match="upstream 500 error"):
        await llm.generate(messages=[Message(role="user", content="hello")])


@pytest.mark.asyncio
async def test_failover_binds_minimax_route_before_client_creation(monkeypatch):
    monkeypatch.setattr("mini_agent.model_manager.failover.LLMClient", _FakeLLMClient)
    _FakeLLMClient.call_order = []
    _FakeLLMClient.behavior = {
        ("https://api.minimaxi.com/anthropic", "MiniMax-M2.7"): LLMCompletionResult(
            content="ok",
            finish_reason="stop",
        ),
    }

    llm = FailoverLLMClient(
        routes=[
            _route(
                provider_id="preset-minimax",
                provider=LLMProvider.ANTHROPIC,
                api_base="https://api.minimaxi.com",
                model="MiniMax-M2.7",
            ),
        ]
    )

    response = await llm.generate(messages=[Message(role="user", content="hello")])

    assert response.content == "ok"
    assert _FakeLLMClient.call_order == [("https://api.minimaxi.com/anthropic", "MiniMax-M2.7")]
