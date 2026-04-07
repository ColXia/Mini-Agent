"""Channel abstraction interfaces.

This module defines the abstract interfaces for channels,
gateway clients, and session stores to enable pluggable
communication channels (QQ Bot, WeChat, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class ChannelMessage:
    """Unified message format from any channel.

    Attributes:
        message_id: Unique message identifier from the channel
        content: Message text content
        channel_type: Channel type identifier (e.g., "qq", "wechat")
        conversation_id: Conversation/channel/group identifier
        sender_id: Optional sender identifier
        metadata: Additional channel-specific metadata
    """

    message_id: str
    content: str
    channel_type: str
    conversation_id: str
    sender_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    class Config:
        extra = "allow"


@dataclass
class ChannelReply:
    """Unified reply format to send back to a channel.

    Attributes:
        success: Whether the operation was successful
        content: Reply content
        error: Optional error message
    """

    success: bool
    content: str = ""
    error: Optional[str] = None


class IGatewayClient(ABC):
    """Gateway client interface.

    Channels use this interface to communicate with the Gateway
    via HTTP or other protocols.
    """

    @abstractmethod
    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        workspace_dir: Optional[str] = None,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a message to the Gateway and get a reply.

        Args:
            message: User message content
            session_id: Optional session ID for conversation continuity
            workspace_dir: Optional workspace directory
            dry_run: If True, don't actually call the LLM
            **kwargs: Additional channel-specific parameters

        Returns:
            Dictionary containing:
                - session_id: Session identifier
                - reply: Assistant reply text
                - message_count: Total messages in session
                - token_usage: Token usage count
        """
        pass

    @abstractmethod
    async def reset_session(self, session_id: str) -> bool:
        """Reset a session's context.

        Args:
            session_id: Session identifier

        Returns:
            True if reset successful, False otherwise
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the Gateway is healthy.

        Returns:
            True if healthy, False otherwise
        """
        pass


class ISessionStore(ABC):
    """Session store interface for channel-side session management.

    Channels can implement this interface to store session state
    in memory, Redis, database, etc.
    """

    @abstractmethod
    async def get(self, conversation_id: str) -> Optional[dict[str, Any]]:
        """Get session state for a conversation.

        Args:
            conversation_id: Conversation identifier

        Returns:
            Session state dictionary or None if not found
        """
        pass

    @abstractmethod
    async def set(self, conversation_id: str, state: dict[str, Any]) -> None:
        """Save session state for a conversation.

        Args:
            conversation_id: Conversation identifier
            state: Session state to save
        """
        pass

    @abstractmethod
    async def delete(self, conversation_id: str) -> None:
        """Delete session state for a conversation.

        Args:
            conversation_id: Conversation identifier
        """
        pass

    @abstractmethod
    async def exists(self, conversation_id: str) -> bool:
        """Check if a session exists.

        Args:
            conversation_id: Conversation identifier

        Returns:
            True if session exists, False otherwise
        """
        pass


class IChannel(ABC):
    """Channel interface.

    All communication channels (QQ Bot, WeChat, etc.) must implement
    this interface to be registered with the Gateway.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start the channel.

        This method should initialize the channel's connection
        to its respective platform and begin listening for messages.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel.

        This method should cleanly disconnect from the platform
        and release all resources.
        """
        pass

    @abstractmethod
    async def send_message(self, conversation_id: str, content: str) -> ChannelReply:
        """Send a message to a specific conversation.

        Args:
            conversation_id: Target conversation identifier
            content: Message content to send

        Returns:
            ChannelReply indicating success or failure
        """
        pass

    @abstractmethod
    def get_channel_type(self) -> str:
        """Get the channel type identifier.

        Returns:
            Channel type string (e.g., "qq", "wechat")
        """
        pass

    @property
    @abstractmethod
    def gateway_client(self) -> IGatewayClient:
        """Get the Gateway client for this channel.

        Returns:
            IGatewayClient instance
        """
        pass

    @property
    @abstractmethod
    def session_store(self) -> ISessionStore:
        """Get the session store for this channel.

        Returns:
            ISessionStore instance
        """
        pass
