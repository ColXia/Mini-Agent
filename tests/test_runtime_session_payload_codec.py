from __future__ import annotations

from types import SimpleNamespace

from mini_agent.runtime.read_models.session_payload_codec import RuntimeSessionPayloadCodec
from tests.runtime_contract_fixtures import RuntimeContractAgentStub


def test_payload_codec_restores_system_message_and_token_state_from_raw_messages() -> None:
    codec = RuntimeSessionPayloadCodec()
    agent = RuntimeContractAgentStub(messages=[SimpleNamespace(role="system", content="system prompt")])

    raw_messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]

    codec.restore_agent_messages_payload(raw_messages, agent)
    codec.restore_agent_token_state(agent, raw_messages=raw_messages, token_limit="128000")

    assert [item.role for item in agent.messages] == ["system", "user", "assistant"]
    assert [item.content for item in agent.messages] == ["system prompt", "hello", "world"]
    assert agent.api_total_tokens >= 0
    assert agent.token_limit == 128000


def test_payload_codec_serializes_agent_messages_with_common_optional_fields() -> None:
    codec = RuntimeSessionPayloadCodec()

    messages = [
        SimpleNamespace(
            role="assistant",
            content="done",
            thinking="plan",
            tool_calls=[{"name": "shell"}],
            tool_call_id="call-1",
            name="mini-agent",
        )
    ]

    serialized = codec.serialize_agent_messages(messages)

    assert serialized == [
        {
            "role": "assistant",
            "content": "done",
            "thinking": "plan",
            "tool_calls": [{"name": "shell"}],
            "tool_call_id": "call-1",
            "name": "mini-agent",
        }
    ]


def test_payload_codec_reads_live_agent_runtime_state_with_message_fallback() -> None:
    codec = RuntimeSessionPayloadCodec()
    agent = RuntimeContractAgentStub(
        messages=[
            SimpleNamespace(role="system", content="system prompt"),
            SimpleNamespace(role="user", content="hello"),
            SimpleNamespace(role="assistant", content="world"),
        ],
        prepared_context={"item_count": 1},
        prepared_context_diagnostics={"turn_count": 2},
        last_memory_automation={"stored_long_term_note": True},
        last_runtime_task_memory={"stored": True},
    )
    agent.token_limit = "64000"

    assert codec.agent_messages(agent)[1].content == "hello"
    assert codec.serialize_live_agent_messages(agent)[-1]["content"] == "world"
    assert codec.agent_message_count(agent) == 3
    assert codec.agent_token_usage(agent) >= 0
    assert codec.agent_token_limit(agent) == 64000
    assert codec.agent_last_prepared_context(agent) == {"item_count": 1}
    assert codec.agent_prepared_context_diagnostics(agent) == {"turn_count": 2}
    assert codec.agent_last_memory_automation(agent) == {"stored_long_term_note": True}
    assert codec.agent_last_runtime_task_memory(agent) == {"stored": True}
