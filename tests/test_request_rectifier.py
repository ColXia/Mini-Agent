"""Tests for P13 T1.6 request rectifier baseline."""

from __future__ import annotations

from mini_agent.model_manager.rectifier import (
    RequestRectifierOptions,
    anthropic_messages_to_openai,
    openai_messages_to_anthropic,
    openai_messages_to_gemini_contents,
    reset_rectifier_metrics,
    rectify_anthropic_request,
    rectify_openai_request,
    snapshot_rectifier_metrics,
)

import pytest


@pytest.fixture(autouse=True)
def _reset_rectifier_metrics():
    reset_rectifier_metrics()
    yield
    reset_rectifier_metrics()


def test_rectify_anthropic_request_applies_budget_cache_and_signature_strip():
    params = {
        "model": "claude-3-7-sonnet",
        "thinking": {"type": "enabled", "budget_tokens": 2048},
        "system": "You are system.",
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "chain", "signature": "sig-1"},
                    {"type": "text", "text": "answer"},
                ],
            },
            {
                "role": "user",
                "content": "latest prompt",
            },
        ],
    }
    rectified = rectify_anthropic_request(
        params,
        options=RequestRectifierOptions(
            enabled=True,
            cache_injection=True,
            strip_thinking_signature=True,
        ),
    )

    assert rectified["thinking"]["type"] == "enabled"
    assert rectified["thinking"]["budget_tokens"] == 2048

    system_blocks = rectified["system"]
    assert isinstance(system_blocks, list)
    assert system_blocks[-1]["cache_control"]["type"] == "ephemeral"

    assistant_blocks = rectified["messages"][0]["content"]
    thinking_block = assistant_blocks[0]
    assert thinking_block["type"] == "thinking"
    assert "signature" not in thinking_block

    user_blocks = rectified["messages"][1]["content"]
    assert isinstance(user_blocks, list)
    assert user_blocks[-1]["cache_control"]["type"] == "ephemeral"

    metrics = snapshot_rectifier_metrics()
    assert metrics["total_requests"] == 1
    assert metrics["anthropic_requests"] == 1
    assert metrics["thinking_budget_injections"] == 0
    assert metrics["cache_injections"] >= 2
    assert metrics["signature_strips"] == 1


def test_rectify_openai_request_normalizes_reasoning_details_and_content():
    params = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "assistant",
                "content": None,
                "reasoning_details": [{"text": "keep"}, {"text": ""}, {"foo": "bar"}],
            },
            {
                "role": "user",
                "content": None,
            },
        ],
        "extra_body": {"reasoning_split": True, "thinking_budget": 1536},
    }
    rectified = rectify_openai_request(
        params,
        options=RequestRectifierOptions(
            enabled=True,
            cache_injection=False,
            strip_thinking_signature=True,
        ),
    )

    assistant = rectified["messages"][0]
    assert assistant["content"] == ""
    assert assistant["reasoning_details"] == [{"text": "keep"}]

    user = rectified["messages"][1]
    assert user["content"] == ""
    assert rectified["extra_body"]["thinking_budget"] == 1536

    metrics = snapshot_rectifier_metrics()
    assert metrics["total_requests"] == 1
    assert metrics["openai_requests"] == 1
    assert metrics["thinking_budget_injections"] == 0
    assert metrics["cache_injections"] == 0


def test_openai_anthropic_openai_conversion_roundtrip_baseline():
    openai_messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": "answer",
            "reasoning_details": [{"text": "reasoning"}],
            "tool_calls": [
                {
                    "id": "tool-1",
                    "type": "function",
                    "function": {"name": "calc", "arguments": {"a": 1, "b": 2}},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "tool-1", "content": "3"},
    ]
    system_message, anthropic_messages = openai_messages_to_anthropic(openai_messages)
    assert system_message == "sys"
    assert anthropic_messages[0]["role"] == "user"
    assert anthropic_messages[1]["role"] == "assistant"

    converted = anthropic_messages_to_openai(system_message, anthropic_messages)
    assert converted[0]["role"] == "system"
    assert any(item["role"] == "assistant" for item in converted)
    assert any(item["role"] == "tool" for item in converted)

    metrics = snapshot_rectifier_metrics()
    assert metrics["protocol_conversion_calls"] == 2
    assert metrics["openai_to_anthropic_conversions"] == 1
    assert metrics["anthropic_to_openai_conversions"] == 1


def test_openai_to_gemini_contents_baseline():
    openai_messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
    ]
    contents = openai_messages_to_gemini_contents(openai_messages)
    assert contents == [
        {"role": "user", "parts": [{"text": "u1"}]},
        {"role": "model", "parts": [{"text": "a1"}]},
    ]

    metrics = snapshot_rectifier_metrics()
    assert metrics["protocol_conversion_calls"] == 1
    assert metrics["openai_to_gemini_conversions"] == 1


def test_rectifier_defaults_do_not_read_env(monkeypatch):
    monkeypatch.setenv("MINI_AGENT_RECTIFIER_ENABLED", "0")
    monkeypatch.setenv("MINI_AGENT_RECTIFIER_CACHE_INJECTION", "0")
    monkeypatch.setenv("MINI_AGENT_RECTIFIER_STRIP_THINKING_SIGNATURE", "0")

    params = {
        "model": "claude-3-7-sonnet",
        "system": "You are system.",
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "chain", "signature": "sig-1"},
                    {"type": "text", "text": "answer"},
                ],
            },
            {
                "role": "user",
                "content": "latest prompt",
            },
        ],
    }

    rectified = rectify_anthropic_request(params)

    assert rectified["system"][-1]["cache_control"]["type"] == "ephemeral"
    assert "signature" not in rectified["messages"][0]["content"][0]
