"""QQ Bot channel adapter using OneBot protocol."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from mini_agent.channels.base import (
    ChannelAdapter,
    ChannelConfig,
    ChannelMessage,
    ChannelResponse,
    ChannelType,
)


@dataclass(frozen=True)
class QQBotConfig:
    """QQ Bot specific configuration."""

    name: str = "qqbot"
    ws_url: str = "ws://127.0.0.1:8080"
    access_token: str = ""
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.QQBOT

    def to_channel_config(self) -> ChannelConfig:
        return ChannelConfig(
            channel_type=ChannelType.QQBOT,
            name=self.name,
            enabled=self.enabled,
            options={
                "ws_url": self.ws_url,
                "access_token": self.access_token,
                **self.options,
            },
        )


class QQBotAdapter(ChannelAdapter):
    """QQ Bot adapter using OneBot WebSocket protocol."""

    def __init__(self, config: QQBotConfig | ChannelConfig) -> None:
        if isinstance(config, QQBotConfig):
            self._qq_config = config
            channel_config = config.to_channel_config()
        else:
            self._qq_config = QQBotConfig(
                name=config.name,
                enabled=config.enabled,
                **config.options,
            )
            channel_config = config
        super().__init__(channel_config)
        self._ws: Any = None
        self._message_queue: asyncio.Queue[ChannelMessage] = asyncio.Queue()
        self._receive_task: asyncio.Task[None] | None = None

    @property
    def qq_config(self) -> QQBotConfig:
        return self._qq_config

    async def _do_start(self) -> None:
        """Connect to OneBot WebSocket."""
        try:
            import websockets
        except ImportError:
            raise RuntimeError("websockets package required for QQ Bot adapter")

        headers = {}
        if self.qq_config.access_token:
            headers["Authorization"] = f"Bearer {self.qq_config.access_token}"

        self._ws = await websockets.connect(
            self.qq_config.ws_url,
            additional_headers=headers,
        )
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def _do_stop(self) -> None:
        """Disconnect from WebSocket."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _receive_loop(self) -> None:
        """Process incoming WebSocket messages."""
        if not self._ws:
            return

        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                    await self._handle_event(data)
                except json.JSONDecodeError:
                    continue
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def _handle_event(self, data: dict[str, Any]) -> None:
        """Handle a OneBot event."""
        post_type = data.get("post_type")
        if post_type != "message":
            return

        message_type = data.get("message_type")
        if message_type == "private":
            await self._handle_private_message(data)
        elif message_type == "group":
            await self._handle_group_message(data)

    async def _handle_private_message(self, data: dict[str, Any]) -> None:
        """Handle a private message."""
        user_id = str(data.get("user_id", ""))
        content = self._extract_content(data.get("message", []))

        message = ChannelMessage(
            channel_type=ChannelType.QQBOT,
            channel_id=f"private_{user_id}",
            user_id=user_id,
            content=content,
            metadata={"raw": data, "message_type": "private"},
        )
        await self._message_queue.put(message)

    async def _handle_group_message(self, data: dict[str, Any]) -> None:
        """Handle a group message."""
        group_id = str(data.get("group_id", ""))
        user_id = str(data.get("user_id", ""))
        content = self._extract_content(data.get("message", []))

        message = ChannelMessage(
            channel_type=ChannelType.QQBOT,
            channel_id=f"group_{group_id}",
            user_id=user_id,
            content=content,
            metadata={"raw": data, "message_type": "group", "group_id": group_id},
        )
        await self._message_queue.put(message)

    def _extract_content(self, message: Any) -> str:
        """Extract text content from message."""
        if isinstance(message, str):
            return message
        if isinstance(message, list):
            parts = []
            for seg in message:
                if isinstance(seg, dict) and seg.get("type") == "text":
                    parts.append(seg.get("data", {}).get("text", ""))
            return "".join(parts)
        return ""

    async def send(self, response: ChannelResponse) -> bool:
        """Send a message through QQ Bot."""
        if not self._ws:
            return False

        metadata = response.metadata
        message_type = metadata.get("message_type", "private")

        if message_type == "group":
            group_id = metadata.get("group_id", "")
            if not group_id:
                return False
            payload = {
                "action": "send_group_msg",
                "params": {
                    "group_id": int(group_id),
                    "message": response.content,
                },
            }
        else:
            user_id = response.reply_to or metadata.get("user_id", "")
            if not user_id:
                return False
            payload = {
                "action": "send_private_msg",
                "params": {
                    "user_id": int(user_id),
                    "message": response.content,
                },
            }

        try:
            await self._ws.send(json.dumps(payload))
            return True
        except Exception:
            return False

    async def receive(self) -> AsyncIterator[ChannelMessage]:
        """Receive messages from QQ Bot."""
        while self._started:
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=1.0,
                )
                yield message
            except asyncio.TimeoutError:
                continue
