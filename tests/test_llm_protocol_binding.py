from __future__ import annotations

from mini_agent.llm import (
    LLMClient,
    AnthropicClient,
    OpenAIClient,
    ProtocolRequestPolicy,
    build_protocol_execution_profile,
)
from mini_agent.model_manager.rectifier import RequestRectifierOptions
from mini_agent.schema import LLMProvider


def test_protocol_binding_normalizes_minimax_anthropic_profile():
    profile = build_protocol_execution_profile(
        api_key="sk-minimax",
        provider=LLMProvider.ANTHROPIC,
        api_base="https://api.minimaxi.com",
        model="MiniMax-M2.7",
        request_policy=ProtocolRequestPolicy(
            thinking_budget_tokens=2048,
        ),
        rectifier_options=RequestRectifierOptions(
            enabled=True,
            cache_injection=True,
            strip_thinking_signature=True,
        ),
    )

    assert profile.provider == LLMProvider.ANTHROPIC
    assert profile.api_base == "https://api.minimaxi.com/anthropic"
    assert profile.client_headers == {"Authorization": "Bearer sk-minimax"}
    assert profile.request_policy.max_output_tokens == 16384
    assert profile.request_policy.reasoning_split_enabled is False
    assert profile.request_policy.thinking_budget_tokens == 2048
    assert profile.request_policy.streaming_enabled is True


def test_protocol_binding_normalizes_minimax_openai_profile():
    profile = build_protocol_execution_profile(
        api_key="sk-minimax",
        provider=LLMProvider.OPENAI,
        api_base="https://api.minimax.io/anthropic",
        model="MiniMax-M2.5",
        request_policy=ProtocolRequestPolicy(
            thinking_budget_tokens=1536,
        ),
        rectifier_options=RequestRectifierOptions(
            enabled=True,
            cache_injection=False,
            strip_thinking_signature=True,
        ),
    )

    assert profile.provider == LLMProvider.OPENAI
    assert profile.api_base == "https://api.minimax.io/v1"
    assert profile.client_headers == {}
    assert profile.request_policy.reasoning_split_enabled is True
    assert profile.request_policy.thinking_budget_tokens == 1536
    assert profile.request_policy.streaming_enabled is True


def test_protocol_binding_keeps_third_party_openai_endpoint_unchanged():
    profile = build_protocol_execution_profile(
        api_key="sk-relay",
        provider=LLMProvider.OPENAI,
        api_base="https://relay.example.com/v1",
        model="gpt-4.1",
        rectifier_options=RequestRectifierOptions(
            enabled=True,
            cache_injection=False,
            strip_thinking_signature=True,
        ),
    )

    assert profile.api_base == "https://relay.example.com/v1"
    assert profile.request_policy.reasoning_split_enabled is True
    assert profile.request_policy.thinking_budget_tokens is None


def test_protocol_binding_preserves_custom_headers_and_timeout():
    profile = build_protocol_execution_profile(
        api_key="sk-relay",
        provider=LLMProvider.OPENAI,
        api_base="https://relay.example.com/v1",
        model="gpt-4.1",
        client_headers={"X-Tenant": "tenant-a"},
        request_timeout_seconds=45,
    )

    assert profile.client_headers == {"X-Tenant": "tenant-a"}
    assert profile.client_timeout_seconds == 45.0


def test_protocol_binding_defaults_do_not_read_runtime_policy_from_env(monkeypatch):
    monkeypatch.setenv("MINI_AGENT_THINKING_BUDGET_TOKENS", "1024")
    monkeypatch.setenv("MINI_AGENT_LLM_TEMPERATURE", "0.5")
    monkeypatch.setenv("MINI_AGENT_STREAMING_ENABLED", "0")
    monkeypatch.setenv("MINI_AGENT_STREAM_USAGE_ENABLED", "0")

    profile = build_protocol_execution_profile(
        api_key="sk-relay",
        provider=LLMProvider.OPENAI,
        api_base="https://relay.example.com/v1",
        model="gpt-4.1",
    )

    assert profile.request_policy.thinking_budget_tokens is None
    assert profile.request_policy.temperature is None
    assert profile.request_policy.streaming_enabled is True
    assert profile.request_policy.include_stream_usage is True


def test_protocol_binding_defaults_do_not_read_rectifier_from_env(monkeypatch):
    monkeypatch.setenv("MINI_AGENT_RECTIFIER_ENABLED", "0")
    monkeypatch.setenv("MINI_AGENT_RECTIFIER_CACHE_INJECTION", "0")
    monkeypatch.setenv("MINI_AGENT_RECTIFIER_STRIP_THINKING_SIGNATURE", "0")

    profile = build_protocol_execution_profile(
        api_key="sk-relay",
        provider=LLMProvider.OPENAI,
        api_base="https://relay.example.com/v1",
        model="gpt-4.1",
    )

    assert profile.rectifier_options.enabled is True
    assert profile.rectifier_options.cache_injection is True
    assert profile.rectifier_options.strip_thinking_signature is True


def test_protocol_request_policy_produces_protocol_specific_kwargs():
    policy = ProtocolRequestPolicy(
        max_output_tokens=4096,
        reasoning_split_enabled=True,
        thinking_budget_tokens=1024,
        temperature=0.3,
        streaming_enabled=True,
        tool_choice_policy="required",
    )

    openai_kwargs = policy.openai_request_kwargs(tools_enabled=True, streaming=True)
    anthropic_kwargs = policy.anthropic_request_kwargs(tools_enabled=True, streaming=True)

    assert openai_kwargs == {
        "max_tokens": 4096,
        "temperature": 0.3,
        "tool_choice": "required",
        "extra_body": {
            "reasoning_split": True,
            "thinking_budget": 1024,
        },
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    assert anthropic_kwargs == {
        "max_tokens": 4096,
        "temperature": 0.3,
        "thinking": {
            "type": "enabled",
            "budget_tokens": 1024,
        },
        "tool_choice": {"type": "any"},
        "stream": True,
    }


def test_openai_client_build_request_params_consumes_request_policy():
    profile = build_protocol_execution_profile(
        api_key="sk-openai",
        provider=LLMProvider.OPENAI,
        api_base="https://relay.example.com/v1",
        model="gpt-4.1",
        rectifier_options=RequestRectifierOptions(
            enabled=True,
            cache_injection=False,
            strip_thinking_signature=True,
        ),
        request_policy=ProtocolRequestPolicy(
            max_output_tokens=2048,
            reasoning_split_enabled=True,
            thinking_budget_tokens=768,
            temperature=0.2,
            tool_choice_policy="required",
        ),
    )
    client = OpenAIClient(profile=profile)

    params = client._build_request_params(
        [{"role": "user", "content": "hello"}],
        tools=[
            {
                "name": "read_file",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ],
        streaming=True,
    )

    assert params["model"] == "gpt-4.1"
    assert params["max_tokens"] == 2048
    assert params["temperature"] == 0.2
    assert params["tool_choice"] == "required"
    assert params["stream"] is True
    assert params["stream_options"] == {"include_usage": True}
    assert params["extra_body"] == {
        "reasoning_split": True,
        "thinking_budget": 768,
    }


def test_anthropic_client_build_request_params_consumes_request_policy():
    profile = build_protocol_execution_profile(
        api_key="sk-anthropic",
        provider=LLMProvider.ANTHROPIC,
        api_base="https://anthropic.example.com",
        model="claude-test",
        rectifier_options=RequestRectifierOptions(
            enabled=True,
            cache_injection=True,
            strip_thinking_signature=True,
        ),
        request_policy=ProtocolRequestPolicy(
            max_output_tokens=8192,
            thinking_budget_tokens=1536,
            temperature=0.1,
            tool_choice_policy="required",
        ),
    )
    client = AnthropicClient(profile=profile)

    params = client._build_request_params(
        "system prompt",
        [{"role": "user", "content": "hello"}],
        tools=[
            {
                "name": "search_docs",
                "description": "Search docs",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ],
        streaming=True,
    )

    assert params["model"] == "claude-test"
    assert params["max_tokens"] == 8192
    assert params["temperature"] == 0.1
    assert params["thinking"] == {
        "type": "enabled",
        "budget_tokens": 1536,
    }
    assert params["tool_choice"] == {"type": "any"}
    assert params["stream"] is True
    assert params["system"] == [{"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}]


def test_llm_wrapper_exposes_bound_profile_identity():
    profile = build_protocol_execution_profile(
        api_key="sk-test",
        provider=LLMProvider.OPENAI,
        api_base="https://relay.example.com/v1",
        model="gpt-4.1",
        request_policy=ProtocolRequestPolicy(
            reasoning_split_enabled=True,
        ),
    )

    client = LLMClient(profile=profile)

    assert client.provider == LLMProvider.OPENAI
    assert client.api_base == "https://relay.example.com/v1"
    assert client.model == "gpt-4.1"
    assert client.profile.request_policy.reasoning_split_enabled is True


def test_anthropic_client_uses_loopback_http_client_for_local_routes(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeAsyncAnthropic:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured.update(kwargs)

        async def close(self):  # pragma: no cover - defensive
            return None

    monkeypatch.setattr("mini_agent.llm.anthropic_client.anthropic.AsyncAnthropic", _FakeAsyncAnthropic)

    profile = build_protocol_execution_profile(
        api_key="ollama",
        provider=LLMProvider.ANTHROPIC,
        api_base="http://localhost:11434",
        model="qwen3.5:9b",
    )
    AnthropicClient(profile=profile)

    http_client = captured.get("http_client")
    assert http_client is not None
    assert getattr(http_client, "_trust_env", True) is False


def test_openai_client_forwards_custom_headers_and_timeout_to_sdk(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured.update(kwargs)

        async def close(self):  # pragma: no cover - defensive
            return None

    monkeypatch.setattr("mini_agent.llm.openai_client.AsyncOpenAI", _FakeAsyncOpenAI)

    profile = build_protocol_execution_profile(
        api_key="sk-openai",
        provider=LLMProvider.OPENAI,
        api_base="https://relay.example.com/v1",
        model="gpt-5.4",
        client_headers={"X-Tenant": "tenant-a"},
        request_timeout_seconds=45,
    )
    OpenAIClient(profile=profile)

    assert captured["default_headers"] == {"X-Tenant": "tenant-a"}
    assert captured["timeout"] == 45.0


def test_anthropic_client_forwards_custom_headers_and_timeout_to_sdk(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeAsyncAnthropic:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured.update(kwargs)

        async def close(self):  # pragma: no cover - defensive
            return None

    monkeypatch.setattr("mini_agent.llm.anthropic_client.anthropic.AsyncAnthropic", _FakeAsyncAnthropic)

    profile = build_protocol_execution_profile(
        api_key="sk-anthropic",
        provider=LLMProvider.ANTHROPIC,
        api_base="https://anthropic.example.com",
        model="claude-test",
        client_headers={"X-Tenant": "tenant-a"},
        request_timeout_seconds=50,
    )
    AnthropicClient(profile=profile)

    assert captured["default_headers"] == {
        "X-Tenant": "tenant-a",
        "Authorization": "Bearer sk-anthropic",
    }
    assert captured["timeout"] == 50.0


def test_openai_client_keeps_default_transport_for_remote_routes(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured.update(kwargs)

        async def close(self):  # pragma: no cover - defensive
            return None

    monkeypatch.setattr("mini_agent.llm.openai_client.AsyncOpenAI", _FakeAsyncOpenAI)

    profile = build_protocol_execution_profile(
        api_key="sk-openai",
        provider=LLMProvider.OPENAI,
        api_base="https://api.openai.com/v1",
        model="gpt-5.4",
    )
    OpenAIClient(profile=profile)

    assert "http_client" not in captured
