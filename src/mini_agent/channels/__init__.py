"""Channel adapters for multi-platform agent deployment."""

from mini_agent.channels.base import (
    ChannelAdapter,
    ChannelConfig,
    ChannelMessage,
    ChannelResponse,
    ChannelRegistry,
    ChannelType,
)

__all__ = [
    "ChannelType",
    "ChannelConfig",
    "ChannelMessage",
    "ChannelResponse",
    "ChannelAdapter",
    "ChannelRegistry",
]
