"""Channel registry for managing channel instances.

This module provides a registry for managing channel instances
and their lifecycle.
"""

from typing import Dict, Optional, Type

from .base import IChannel, IGatewayClient


class ChannelRegistry:
    """Registry for managing channel instances.

    This class provides a centralized registry for all channels
    and the shared Gateway client.
    """

    _channels: Dict[str, IChannel] = {}
    _gateway_client: Optional[IGatewayClient] = None

    @classmethod
    def register(cls, channel: IChannel) -> None:
        """Register a channel instance.

        Args:
            channel: Channel instance to register
        """
        channel_type = channel.get_channel_type()
        cls._channels[channel_type] = channel

    @classmethod
    def unregister(cls, channel_type: str) -> bool:
        """Unregister a channel by type.

        Args:
            channel_type: Channel type identifier

        Returns:
            True if channel was unregistered, False if not found
        """
        if channel_type in cls._channels:
            del cls._channels[channel_type]
            return True
        return False

    @classmethod
    def get(cls, channel_type: str) -> Optional[IChannel]:
        """Get a channel by type.

        Args:
            channel_type: Channel type identifier

        Returns:
            Channel instance or None if not found
        """
        return cls._channels.get(channel_type)

    @classmethod
    def get_all(cls) -> Dict[str, IChannel]:
        """Get all registered channels.

        Returns:
            Dictionary of channel type to channel instance
        """
        return cls._channels.copy()

    @classmethod
    def set_gateway_client(cls, client: IGatewayClient) -> None:
        """Set the shared Gateway client.

        Args:
            client: Gateway client instance
        """
        cls._gateway_client = client

    @classmethod
    def get_gateway_client(cls) -> Optional[IGatewayClient]:
        """Get the shared Gateway client.

        Returns:
            Gateway client instance or None if not set
        """
        return cls._gateway_client

    @classmethod
    async def start_all(cls) -> None:
        """Start all registered channels."""
        for channel in cls._channels.values():
            await channel.start()

    @classmethod
    async def stop_all(cls) -> None:
        """Stop all registered channels."""
        for channel in cls._channels.values():
            await channel.stop()

    @classmethod
    def clear(cls) -> None:
        """Clear all registered channels."""
        cls._channels.clear()
