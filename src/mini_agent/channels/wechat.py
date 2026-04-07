"""WeChat channel adapter using WeChat Bot API."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
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
class WeChatConfig:
    """WeChat specific configuration."""

    name: str = "wechat"
    corp_id: str = ""
    agent_id: str = ""
    secret: str = ""
    token: str = ""
    encoding_aes_key: str = ""
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.WECHAT

    def to_channel_config(self) -> ChannelConfig:
        return ChannelConfig(
            channel_type=ChannelType.WECHAT,
            name=self.name,
            enabled=self.enabled,
            options={
                "corp_id": self.corp_id,
                "agent_id": self.agent_id,
                "secret": self.secret,
                "token": self.token,
                "encoding_aes_key": self.encoding_aes_key,
                **self.options,
            },
        )


class WeChatAdapter(ChannelAdapter):
    """WeChat Work adapter using WeChat API."""

    API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"

    def __init__(self, config: WeChatConfig | ChannelConfig) -> None:
        if isinstance(config, WeChatConfig):
            self._wechat_config = config
            channel_config = config.to_channel_config()
        else:
            self._wechat_config = WeChatConfig(
                name=config.name,
                enabled=config.enabled,
                **config.options,
            )
            channel_config = config
        super().__init__(channel_config)
        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self._message_queue: asyncio.Queue[ChannelMessage] = asyncio.Queue()

    @property
    def wechat_config(self) -> WeChatConfig:
        return self._wechat_config

    async def _do_start(self) -> None:
        """Initialize WeChat connection."""
        await self._refresh_access_token()

    async def _do_stop(self) -> None:
        """Cleanup WeChat connection."""
        self._access_token = None
        self._token_expires_at = 0

    async def _refresh_access_token(self) -> None:
        """Refresh access token from WeChat API."""
        import aiohttp

        if not self.wechat_config.corp_id or not self.wechat_config.secret:
            return

        url = f"{self.API_BASE}/gettoken"
        params = {
            "corpid": self.wechat_config.corp_id,
            "corpsecret": self.wechat_config.secret,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
                    if data.get("errcode") == 0:
                        self._access_token = data.get("access_token")
                        expires_in = data.get("expires_in", 7200)
                        self._token_expires_at = time.time() + expires_in - 300
        except Exception:
            pass

    async def _ensure_token(self) -> str | None:
        """Ensure we have a valid access token."""
        if not self._access_token or time.time() >= self._token_expires_at:
            await self._refresh_access_token()
        return self._access_token

    def verify_signature(self, signature: str, timestamp: str, nonce: str, echostr: str = "") -> bool:
        """Verify WeChat callback signature."""
        token = self.wechat_config.token
        if not token:
            return False

        items = sorted([token, timestamp, nonce])
        combined = "".join(items)
        expected = hashlib.sha1(combined.encode()).hexdigest()
        return hmac.compare_digest(signature, expected)

    async def handle_callback(self, data: dict[str, Any]) -> None:
        """Handle a callback from WeChat."""
        msg_type = data.get("MsgType", "")
        from_user = data.get("FromUserName", "")
        content = data.get("Content", "")

        if msg_type == "text" and content:
            message = ChannelMessage(
                channel_type=ChannelType.WECHAT,
                channel_id=self.wechat_config.agent_id,
                user_id=from_user,
                content=content,
                metadata={"raw": data, "msg_type": msg_type},
            )
            await self._message_queue.put(message)

    async def send(self, response: ChannelResponse) -> bool:
        """Send a message through WeChat."""
        import aiohttp

        token = await self._ensure_token()
        if not token:
            return False

        user_id = response.reply_to or response.metadata.get("user_id", "")
        if not user_id:
            return False

        url = f"{self.API_BASE}/message/send"
        params = {"access_token": token}
        payload = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": int(self.wechat_config.agent_id),
            "text": {"content": response.content},
            "safe": 0,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params, json=payload) as resp:
                    data = await resp.json()
                    return data.get("errcode") == 0
        except Exception:
            return False

    async def receive(self) -> AsyncIterator[ChannelMessage]:
        """Receive messages from WeChat (via callback queue)."""
        while self._started:
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=1.0,
                )
                yield message
            except asyncio.TimeoutError:
                continue
