"""Tests for channel adapters."""

from __future__ import annotations

import pytest

from mini_agent.channels.base import (
    ChannelAdapter,
    ChannelConfig,
    ChannelMessage,
    ChannelRegistry,
    ChannelResponse,
    ChannelType,
)
from mini_agent.channels.qqbot import QQBotAdapter, QQBotConfig
from mini_agent.channels.wechat import WeChatAdapter, WeChatConfig


class MockChannelAdapter(ChannelAdapter):
    """Mock adapter for testing."""

    def __init__(self, config: ChannelConfig) -> None:
        super().__init__(config)
        self._messages: list[ChannelMessage] = []
        self._sent: list[ChannelResponse] = []

    async def _do_start(self) -> None:
        pass

    async def _do_stop(self) -> None:
        pass

    async def send(self, response: ChannelResponse) -> bool:
        self._sent.append(response)
        return True

    async def receive(self):
        for msg in self._messages:
            yield msg


def test_channel_config_normalized():
    config = ChannelConfig(
        channel_type=ChannelType.CLI,
        name="  test  ",
        enabled=True,
        options={"key": "value", "": "empty"},
    )
    normalized = config.normalized()
    assert normalized.name == "test"
    assert "" not in normalized.options


def test_channel_message_is_empty():
    empty_msg = ChannelMessage(
        channel_type=ChannelType.CLI,
        channel_id="test",
        user_id="user1",
        content="   ",
    )
    assert empty_msg.is_empty

    non_empty_msg = ChannelMessage(
        channel_type=ChannelType.CLI,
        channel_id="test",
        user_id="user1",
        content="hello",
    )
    assert not non_empty_msg.is_empty


def test_channel_registry_register_factory():
    registry = ChannelRegistry()
    registry.register_factory(ChannelType.CLI, MockChannelAdapter)

    config = ChannelConfig(channel_type=ChannelType.CLI, name="test")
    adapter = registry.create(config)

    assert isinstance(adapter, MockChannelAdapter)
    assert adapter.name == "test"


def test_channel_registry_register_and_get():
    registry = ChannelRegistry()
    config = ChannelConfig(channel_type=ChannelType.CLI, name="test")
    adapter = MockChannelAdapter(config)

    registry.register(adapter)
    retrieved = registry.get("test")

    assert retrieved is adapter
    assert len(registry.list_adapters()) == 1


def test_channel_registry_unregister():
    registry = ChannelRegistry()
    config = ChannelConfig(channel_type=ChannelType.CLI, name="test")
    adapter = MockChannelAdapter(config)

    registry.register(adapter)
    registry.unregister("test")

    assert registry.get("test") is None
    assert len(registry.list_adapters()) == 0


def test_qqbot_config():
    config = QQBotConfig(
        name="my-qqbot",
        ws_url="ws://localhost:9000",
        access_token="secret",
    )

    assert config.channel_type == ChannelType.QQBOT
    assert config.ws_url == "ws://localhost:9000"
    assert config.access_token == "secret"


def test_qqbot_adapter_extract_content():
    config = QQBotConfig()
    adapter = QQBotAdapter(config)

    # String message
    assert adapter._extract_content("hello") == "hello"

    # List message
    message = [
        {"type": "text", "data": {"text": "hello "}},
        {"type": "text", "data": {"text": "world"}},
    ]
    assert adapter._extract_content(message) == "hello world"

    # Empty list
    assert adapter._extract_content([]) == ""


def test_wechat_config():
    config = WeChatConfig(
        name="my-wechat",
        corp_id="corp123",
        agent_id="agent456",
        secret="secret789",
    )

    assert config.channel_type == ChannelType.WECHAT
    assert config.corp_id == "corp123"
    assert config.agent_id == "agent456"
    assert config.secret == "secret789"


def test_wechat_adapter_verify_signature():
    config = WeChatConfig(name="test", token="mytoken")
    adapter = WeChatAdapter(config)

    # Valid signature
    import hashlib
    items = sorted(["mytoken", "123456", "nonce"])
    expected = hashlib.sha1("".join(items).encode()).hexdigest()
    assert adapter.verify_signature(expected, "123456", "nonce")

    # Invalid signature
    assert not adapter.verify_signature("invalid", "123456", "nonce")


@pytest.mark.asyncio
async def test_mock_adapter_start_stop():
    config = ChannelConfig(channel_type=ChannelType.CLI, name="test")
    adapter = MockChannelAdapter(config)

    assert not adapter.is_started
    await adapter.start()
    assert adapter.is_started
    await adapter.stop()
    assert not adapter.is_started


@pytest.mark.asyncio
async def test_mock_adapter_send():
    config = ChannelConfig(channel_type=ChannelType.CLI, name="test")
    adapter = MockChannelAdapter(config)

    response = ChannelResponse(content="hello", reply_to="user1")
    result = await adapter.send(response)

    assert result is True
    assert len(adapter._sent) == 1
    assert adapter._sent[0].content == "hello"
