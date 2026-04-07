"""Open WebUI adapter that bridges OpenAI-compatible requests to Gateway chat API."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from threading import Lock
from typing import Any, Callable

import requests


class OpenWebUIAdapterError(RuntimeError):
    """Base adapter error."""


class GatewayRequestError(OpenWebUIAdapterError):
    """Raised when gateway request fails."""


GatewayChatTransport = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class OpenWebUIAdapterConfig:
    """Runtime config for Open WebUI adapter."""

    gateway_base_url: str = "http://127.0.0.1:8008"
    gateway_auth_token: str | None = None
    adapter_api_keys: tuple[str, ...] = ()
    default_model: str = "mini-agent"
    available_models: tuple[str, ...] = ("mini-agent",)
    timeout_seconds: float = 30.0
    channel_type: str = "open_webui"

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "OpenWebUIAdapterConfig":
        source = env or {}
        gateway_base_url = source.get("MINI_AGENT_GATEWAY_URL") or source.get("MINI_AGENT_GATEWAY_BASE_URL") or "http://127.0.0.1:8008"
        gateway_auth_token = source.get("MINI_AGENT_GATEWAY_AUTH_TOKEN") or source.get("MINI_AGENT_OPENWEBUI_GATEWAY_TOKEN")
        api_keys_raw = source.get("MINI_AGENT_OPENWEBUI_API_KEYS", "")
        api_keys = tuple(item.strip() for item in api_keys_raw.split(",") if item and item.strip())
        default_model = (source.get("MINI_AGENT_OPENWEBUI_DEFAULT_MODEL") or "mini-agent").strip() or "mini-agent"
        available_raw = source.get("MINI_AGENT_OPENWEBUI_MODELS", "")
        available_models = tuple(item.strip() for item in available_raw.split(",") if item and item.strip()) or (default_model,)
        timeout_seconds = float(source.get("MINI_AGENT_OPENWEBUI_TIMEOUT_SECONDS", "30") or "30")
        channel_type = (source.get("MINI_AGENT_OPENWEBUI_CHANNEL_TYPE") or "open_webui").strip() or "open_webui"
        return OpenWebUIAdapterConfig(
            gateway_base_url=gateway_base_url.strip().rstrip("/"),
            gateway_auth_token=(gateway_auth_token.strip() if gateway_auth_token else None),
            adapter_api_keys=api_keys,
            default_model=default_model,
            available_models=available_models,
            timeout_seconds=max(1.0, timeout_seconds),
            channel_type=channel_type,
        )


@dataclass(frozen=True)
class AdapterChatResult:
    """Normalized adapter chat response."""

    session_id: str
    reply: str
    token_usage: int
    workspace_dir: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class SessionSyncStore:
    """In-memory conversation/session mapping for Open WebUI conversation continuity."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._conversation_to_session: dict[str, str] = {}

    def get(self, conversation_key: str | None) -> str | None:
        if not conversation_key:
            return None
        with self._lock:
            return self._conversation_to_session.get(conversation_key)

    def set(self, conversation_key: str | None, session_id: str | None) -> None:
        if not conversation_key or not session_id:
            return
        with self._lock:
            self._conversation_to_session[conversation_key] = session_id


class OpenWebUIAdapter:
    """Adapter for translating OpenAI-style chat requests into Gateway chat requests."""

    def __init__(
        self,
        *,
        config: OpenWebUIAdapterConfig | None = None,
        transport: GatewayChatTransport | None = None,
        session_store: SessionSyncStore | None = None,
    ) -> None:
        self.config = config or OpenWebUIAdapterConfig()
        self._transport = transport or self._default_transport
        self.session_store = session_store or SessionSyncStore()

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        user: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AdapterChatResult:
        prompt = self._extract_prompt(messages)
        if not prompt:
            raise OpenWebUIAdapterError("no usable prompt content found in messages.")

        metadata = dict(metadata or {})
        conversation_key = self.resolve_conversation_key(user=user, metadata=metadata)
        session_id = self.session_store.get(conversation_key)

        payload: dict[str, Any] = {
            "message": prompt,
            "session_id": session_id,
            "channel_type": self.config.channel_type,
            "conversation_id": metadata.get("conversation_id") or metadata.get("thread_id") or conversation_key,
            "sender_id": (str(user).strip() if user else None),
            "workspace_dir": (str(metadata.get("workspace_dir")).strip() if metadata.get("workspace_dir") else None),
            "dry_run": bool(metadata.get("dry_run", False)),
        }
        gateway_response = self._transport(payload)
        if not isinstance(gateway_response, dict):
            raise GatewayRequestError("gateway response must be an object.")

        resolved_session_id = str(gateway_response.get("session_id", "")).strip()
        if not resolved_session_id:
            raise GatewayRequestError("gateway response missing session_id.")

        self.session_store.set(conversation_key, resolved_session_id)
        token_usage_raw = gateway_response.get("token_usage", 0)
        try:
            token_usage = int(token_usage_raw)
        except Exception:
            token_usage = 0
        return AdapterChatResult(
            session_id=resolved_session_id,
            reply=str(gateway_response.get("reply", "")),
            token_usage=max(0, token_usage),
            workspace_dir=(
                str(gateway_response.get("workspace_dir")).strip()
                if gateway_response.get("workspace_dir")
                else None
            ),
            raw=dict(gateway_response),
        )

    @staticmethod
    def _extract_prompt(messages: list[dict[str, Any]]) -> str:
        user_messages = [item for item in messages if str(item.get("role", "")).strip().lower() == "user"]
        source = user_messages[-1] if user_messages else (messages[-1] if messages else {})
        content = source.get("content")
        return OpenWebUIAdapter._content_to_text(content)

    @staticmethod
    def _content_to_text(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        chunks.append(text)
                    continue
                if isinstance(item, dict):
                    item_type = str(item.get("type", "")).strip().lower()
                    if item_type and item_type != "text":
                        continue
                    text = str(item.get("text", "")).strip()
                    if text:
                        chunks.append(text)
            return "\n".join(chunks).strip()
        if isinstance(content, dict):
            text = str(content.get("text", "")).strip()
            return text
        return ""

    @staticmethod
    def resolve_conversation_key(user: str | None, metadata: dict[str, Any] | None) -> str | None:
        metadata = metadata or {}
        conversation_id = (
            str(metadata.get("conversation_id", "")).strip()
            or str(metadata.get("thread_id", "")).strip()
            or str(metadata.get("chat_id", "")).strip()
        )
        normalized_user = str(user).strip() if user else ""

        if conversation_id and normalized_user:
            return f"{normalized_user}:{conversation_id}"
        if conversation_id:
            return conversation_id
        if normalized_user:
            return f"user:{normalized_user}"
        return None

    def _default_transport(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.config.gateway_auth_token:
            headers["Authorization"] = f"Bearer {self.config.gateway_auth_token}"

        response = requests.post(
            f"{self.config.gateway_base_url}/api/v1/agent/chat",
            headers=headers,
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        body_text = response.text
        try:
            body = response.json()
        except Exception as exc:  # noqa: BLE001
            raise GatewayRequestError(f"gateway response is not valid JSON: {exc}") from exc

        if response.status_code >= 400:
            detail = body.get("detail") if isinstance(body, dict) else body_text
            raise GatewayRequestError(f"gateway request failed ({response.status_code}): {detail}")
        if not isinstance(body, dict):
            raise GatewayRequestError("gateway response JSON must be an object.")
        ok = bool(body.get("ok"))
        data = body.get("data")
        error = body.get("error")
        if not ok:
            if isinstance(error, dict):
                message = str(error.get("message") or error.get("code") or "unknown gateway error")
            else:
                message = "unknown gateway error"
            raise GatewayRequestError(f"gateway request failed (contract error): {message}")
        if not isinstance(data, dict):
            raise GatewayRequestError("gateway v1 response missing data object.")
        return data

    def list_models(self) -> tuple[str, ...]:
        models = tuple(item for item in self.config.available_models if item and item.strip())
        if not models:
            return (self.config.default_model,)
        return models
