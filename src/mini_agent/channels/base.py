"""Channel adapter base classes and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable


class ChannelType(str, Enum):
    """Supported channel types."""

    CLI = "cli"
    QQBOT = "qqbot"
    WECHAT = "wechat"
    DISCORD = "discord"
    SLACK = "slack"
    TELEGRAM = "telegram"
    WEB = "web"
    API = "api"


@dataclass(frozen=True)
class ChannelConfig:
    """Channel configuration."""

    channel_type: ChannelType
    name: str
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "ChannelConfig":
        return ChannelConfig(
            channel_type=self.channel_type,
            name=self.name.strip(),
            enabled=bool(self.enabled),
            options={k: v for k, v in self.options.items() if k.strip()},
        )


@dataclass(frozen=True)
class ChannelMessage:
    """Incoming message from a channel."""

    channel_type: ChannelType
    channel_id: str
    user_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.content.strip()


@dataclass(frozen=True)
class ChannelResponse:
    """Outgoing response to a channel."""

    content: str
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ChannelAdapter(ABC):
    """Abstract base class for channel adapters."""

    def __init__(self, config: ChannelConfig) -> None:
        self.config = config.normalized()
        self._started = False

    @property
    def channel_type(self) -> ChannelType:
        return self.config.channel_type

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def is_started(self) -> bool:
        return self._started

    async def start(self) -> None:
        """Start the channel adapter."""
        if self._started:
            return
        await self._do_start()
        self._started = True

    async def stop(self) -> None:
        """Stop the channel adapter."""
        if not self._started:
            return
        await self._do_stop()
        self._started = False

    @abstractmethod
    async def _do_start(self) -> None:
        """Implementation-specific start logic."""
        ...

    @abstractmethod
    async def _do_stop(self) -> None:
        """Implementation-specific stop logic."""
        ...

    @abstractmethod
    async def send(self, response: ChannelResponse) -> bool:
        """Send a response through this channel."""
        ...

    @abstractmethod
    async def receive(self) -> AsyncIterator[ChannelMessage]:
        """Receive messages from this channel."""
        ...


class ChannelRegistry:
    """Registry for channel adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, ChannelAdapter] = {}
        self._factories: dict[ChannelType, Callable[[ChannelConfig], ChannelAdapter]] = {}

    def register_factory(
        self,
        channel_type: ChannelType,
        factory: Callable[[ChannelConfig], ChannelAdapter],
    ) -> None:
        """Register a factory for a channel type."""
        self._factories[channel_type] = factory

    def create(self, config: ChannelConfig) -> ChannelAdapter:
        """Create an adapter from configuration."""
        factory = self._factories.get(config.channel_type)
        if factory is None:
            raise ValueError(f"No factory registered for channel type: {config.channel_type}")
        return factory(config)

    def register(self, adapter: ChannelAdapter) -> None:
        """Register an adapter instance."""
        self._adapters[adapter.name] = adapter

    def unregister(self, name: str) -> None:
        """Unregister an adapter by name."""
        self._adapters.pop(name, None)

    def get(self, name: str) -> ChannelAdapter | None:
        """Get an adapter by name."""
        return self._adapters.get(name)

    def list_adapters(self) -> list[ChannelAdapter]:
        """List all registered adapters."""
        return list(self._adapters.values())

    async def start_all(self) -> None:
        """Start all registered adapters."""
        for adapter in self._adapters.values():
            await adapter.start()

    async def stop_all(self) -> None:
        """Stop all registered adapters."""
        for adapter in self._adapters.values():
            await adapter.stop()
