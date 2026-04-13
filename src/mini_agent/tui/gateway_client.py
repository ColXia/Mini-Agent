"""Small gateway client for shared remote TUI sessions."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import httpx
from mini_agent.runtime.interaction_surface import resolve_interaction_binding


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True)
class _GatewaySessionBinding:
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None

    @classmethod
    def from_values(
        cls,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        default_surface: str | None = None,
    ) -> _GatewaySessionBinding:
        binding = resolve_interaction_binding(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            default_surface=default_surface,
        )
        return cls(
            surface=binding.surface,
            channel_type=binding.channel_type,
            conversation_id=binding.conversation_id,
            sender_id=binding.sender_id,
        )

    def as_payload(self) -> dict[str, str | None]:
        return {
            "surface": self.surface,
            "channel_type": self.channel_type,
            "conversation_id": self.conversation_id,
            "sender_id": self.sender_id,
        }


class TuiGatewayClient:
    """Minimal HTTP client for the local Studio gateway."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        configured = _safe_text(base_url or os.getenv("MINI_AGENT_GATEWAY_BASE") or "http://127.0.0.1:8008")
        self.base_url = configured.rstrip("/")
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    @staticmethod
    def _create_session_payload(
        *,
        workspace_dir: str,
        title: str | None = None,
        surface: str = "tui",
        shared: bool = False,
    ) -> dict[str, Any]:
        binding = _GatewaySessionBinding.from_values(surface=surface, default_surface="tui")
        return {
            "workspace_dir": str(workspace_dir),
            "title": _safe_text(title) or None,
            "surface": binding.surface or "tui",
            "shared": bool(shared),
        }

    @staticmethod
    def _chat_payload(
        *,
        session_id: str,
        message: str,
        workspace_dir: str,
        surface: str = "tui",
    ) -> dict[str, Any]:
        binding = _GatewaySessionBinding.from_values(surface=surface, default_surface="tui")
        return {
            "message": str(message),
            "session_id": _safe_text(session_id) or None,
            "workspace_dir": str(workspace_dir),
            "surface": binding.surface or "tui",
            "dry_run": False,
        }

    async def list_sessions(
        self,
        *,
        workspace_dir: str | None = None,
        shared_only: bool = False,
    ) -> list[dict[str, Any]]:
        data = await asyncio.to_thread(
            self._request_json,
            "GET",
            "/api/v1/agent/sessions",
            query={
                "workspace_dir": workspace_dir,
                "shared_only": "true" if shared_only else None,
            },
        )
        return data if isinstance(data, list) else []

    async def get_system_health(self) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._request_json,
            "GET",
            "/api/v1/system/health",
        )

    def get_system_health_sync(self) -> dict[str, Any]:
        data = self._request_json(
            "GET",
            "/api/v1/system/health",
        )
        return data if isinstance(data, dict) else {}

    async def list_agent_models(self) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._request_json,
            "GET",
            "/api/v1/agent/models",
        )

    def list_agent_models_sync(self) -> dict[str, Any]:
        data = self._request_json(
            "GET",
            "/api/v1/agent/models",
        )
        return data if isinstance(data, dict) else {}

    def list_sessions_sync(
        self,
        *,
        workspace_dir: str | None = None,
        shared_only: bool = False,
    ) -> list[dict[str, Any]]:
        data = self._request_json(
            "GET",
            "/api/v1/agent/sessions",
            query={
                "workspace_dir": workspace_dir,
                "shared_only": "true" if shared_only else None,
            },
        )
        return data if isinstance(data, list) else []

    async def get_session_detail(self, session_id: str, *, recent_limit: int = 80) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        return await asyncio.to_thread(
            self._request_json,
            "GET",
            f"/api/v1/agent/sessions/{safe_id}",
            query={"recent_limit": max(1, int(recent_limit))},
        )

    def get_session_detail_sync(self, session_id: str, *, recent_limit: int = 80) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        return self._request_json(
            "GET",
            f"/api/v1/agent/sessions/{safe_id}",
            query={"recent_limit": max(1, int(recent_limit))},
        )

    async def get_session_messages(self, session_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        safe_id = quote(_safe_text(session_id), safe="")
        data = await asyncio.to_thread(
            self._request_json,
            "GET",
            f"/api/v1/agent/sessions/{safe_id}/messages",
            query={"limit": max(1, int(limit))},
        )
        return data if isinstance(data, list) else []

    async def create_session(
        self,
        *,
        workspace_dir: str,
        title: str | None = None,
        surface: str = "tui",
        shared: bool = False,
    ) -> dict[str, Any]:
        payload = self._create_session_payload(
            workspace_dir=workspace_dir,
            title=title,
            surface=surface,
            shared=shared,
        )
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            "/api/v1/agent/sessions",
            payload=payload,
        )

    async def create_derived_session(
        self,
        parent_session_id: str,
        *,
        title: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        safe_id = quote(_safe_text(parent_session_id), safe="")
        binding = _GatewaySessionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            default_surface="tui",
        )
        payload = {
            "title": _safe_text(title) or None,
            **binding.as_payload(),
        }
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/fork",
            payload=payload,
        )

    def create_derived_session_sync(
        self,
        parent_session_id: str,
        *,
        title: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        safe_id = quote(_safe_text(parent_session_id), safe="")
        binding = _GatewaySessionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            default_surface="tui",
        )
        payload = {
            "title": _safe_text(title) or None,
            **binding.as_payload(),
        }
        data = self._request_json(
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/fork",
            payload=payload,
        )
        return data if isinstance(data, dict) else {}

    def create_session_sync(
        self,
        *,
        workspace_dir: str,
        title: str | None = None,
        surface: str = "tui",
        shared: bool = False,
    ) -> dict[str, Any]:
        payload = self._create_session_payload(
            workspace_dir=workspace_dir,
            title=title,
            surface=surface,
            shared=shared,
        )
        return self._request_json(
            "POST",
            "/api/v1/agent/sessions",
            payload=payload,
        )

    async def rename_session(self, session_id: str, *, title: str) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        return await asyncio.to_thread(
            self._request_json,
            "PATCH",
            f"/api/v1/agent/sessions/{safe_id}",
            payload={"title": _safe_text(title)},
        )

    def rename_session_sync(self, session_id: str, *, title: str) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        data = self._request_json(
            "PATCH",
            f"/api/v1/agent/sessions/{safe_id}",
            payload={"title": _safe_text(title)},
        )
        return data if isinstance(data, dict) else {}

    async def set_session_shared(self, session_id: str, *, shared: bool) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/share",
            payload={"shared": bool(shared)},
        )

    def set_session_shared_sync(self, session_id: str, *, shared: bool) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        data = self._request_json(
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/share",
            payload={"shared": bool(shared)},
        )
        return data if isinstance(data, dict) else {}

    async def reset_session(self, session_id: str) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/reset",
        )

    async def cancel_session(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        binding = _GatewaySessionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        payload = {
            "reason": reason,
            **binding.as_payload(),
        }
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/cancel",
            payload=payload,
        )

    async def control_session(
        self,
        session_id: str,
        *,
        action: str,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        binding = _GatewaySessionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        payload = {
            "action": _safe_text(action),
            "reason": reason,
            **binding.as_payload(),
        }
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/control",
            payload=payload,
        )

    def control_session_sync(
        self,
        session_id: str,
        *,
        action: str,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        binding = _GatewaySessionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        payload = {
            "action": _safe_text(action),
            "reason": reason,
            **binding.as_payload(),
        }
        data = self._request_json(
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/control",
            payload=payload,
        )
        return data if isinstance(data, dict) else {}

    async def update_session_context(
        self,
        session_id: str,
        *,
        action: str,
        sources: list[str] | None = None,
        max_items: int | None = None,
        max_total_chars: int | None = None,
        max_items_per_source: int | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        binding = _GatewaySessionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        payload = {
            "action": _safe_text(action),
            "sources": [item for item in list(sources or []) if _safe_text(item)],
            "max_items": max_items,
            "max_total_chars": max_total_chars,
            "max_items_per_source": max_items_per_source,
            **binding.as_payload(),
        }
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/context",
            payload=payload,
        )

    async def manage_session_memory(
        self,
        session_id: str,
        *,
        action: str,
        engram_id: str | None = None,
        content: str | None = None,
        query: str | None = None,
        day: str | None = None,
        export_format: str | None = None,
        detail_mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        binding = _GatewaySessionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        payload = {
            "action": _safe_text(action),
            "engram_id": _safe_text(engram_id) or None,
            "content": _safe_text(content) or None,
            "query": _safe_text(query) or None,
            "day": _safe_text(day) or None,
            "export_format": _safe_text(export_format) or None,
            "detail_mode": _safe_text(detail_mode) or None,
            **binding.as_payload(),
        }
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/memory",
            payload=payload,
        )

    async def manage_session_skill(
        self,
        session_id: str,
        *,
        action: str,
        skill_name: str | None = None,
        path: str | None = None,
        query: str | None = None,
        mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        binding = _GatewaySessionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        payload = {
            "action": _safe_text(action),
            "skill_name": _safe_text(skill_name) or None,
            "path": _safe_text(path) or None,
            "query": _safe_text(query) or None,
            "mode": _safe_text(mode) or None,
            **binding.as_payload(),
        }
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/skill",
            payload=payload,
        )

    async def update_session_model(
        self,
        session_id: str,
        *,
        provider_source: str | None,
        provider_id: str,
        model_id: str,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        binding = _GatewaySessionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        payload = {
            "provider_source": _safe_text(provider_source) or None,
            "provider_id": _safe_text(provider_id),
            "model_id": _safe_text(model_id),
            **binding.as_payload(),
        }
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/model",
            payload=payload,
        )

    def update_session_model_sync(
        self,
        session_id: str,
        *,
        provider_source: str | None,
        provider_id: str,
        model_id: str,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        binding = _GatewaySessionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        payload = {
            "provider_source": _safe_text(provider_source) or None,
            "provider_id": _safe_text(provider_id),
            "model_id": _safe_text(model_id),
            **binding.as_payload(),
        }
        data = self._request_json(
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/model",
            payload=payload,
        )
        return data if isinstance(data, dict) else {}

    async def update_session_runtime_policy(
        self,
        session_id: str,
        *,
        approval_profile: str | None = None,
        access_level: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        binding = _GatewaySessionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        payload = {
            "approval_profile": _safe_text(approval_profile) or None,
            "access_level": _safe_text(access_level) or None,
            **binding.as_payload(),
        }
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/policy",
            payload=payload,
        )

    async def respond_to_approval(
        self,
        session_id: str,
        *,
        approved: bool,
        token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        binding = _GatewaySessionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        payload = {
            "approved": bool(approved),
            "token": _safe_text(token) or None,
            **binding.as_payload(),
        }
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/approval",
            payload=payload,
        )

    def respond_to_approval_sync(
        self,
        session_id: str,
        *,
        approved: bool,
        token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        binding = _GatewaySessionBinding.from_values(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        payload = {
            "approved": bool(approved),
            "token": _safe_text(token) or None,
            **binding.as_payload(),
        }
        data = self._request_json(
            "POST",
            f"/api/v1/agent/sessions/{safe_id}/approval",
            payload=payload,
        )
        return data if isinstance(data, dict) else {}

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        safe_id = quote(_safe_text(session_id), safe="")
        return await asyncio.to_thread(
            self._request_json,
            "DELETE",
            f"/api/v1/agent/sessions/{safe_id}",
        )

    async def run_chat(
        self,
        *,
        session_id: str,
        message: str,
        workspace_dir: str,
        surface: str = "tui",
    ) -> dict[str, Any]:
        payload = self._chat_payload(
            session_id=session_id,
            message=message,
            workspace_dir=workspace_dir,
            surface=surface,
        )
        return await asyncio.to_thread(self._request_json, "POST", "/api/v1/agent/chat", payload=payload)

    async def stream_chat_events(
        self,
        *,
        session_id: str,
        message: str,
        workspace_dir: str,
        surface: str = "tui",
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        params = {
            **self._chat_payload(
                session_id=session_id,
                message=message,
                workspace_dir=workspace_dir,
                surface=surface,
            ),
            "dry_run": "false",
        }
        timeout = httpx.Timeout(connect=self.timeout_seconds, read=None, write=self.timeout_seconds, pool=self.timeout_seconds)
        headers = {"Accept": "text/event-stream", "User-Agent": "Mini-Agent-TUI/1.0"}
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "GET",
                f"{self.base_url}/api/v1/agent/chat/stream",
                params={key: value for key, value in params.items() if value is not None},
                headers=headers,
            ) as response:
                if response.status_code >= 400:
                    raise RuntimeError(f"Gateway HTTP {response.status_code}: {await response.aread()}")
                event_name = "message"
                data_lines: list[str] = []
                async for raw_line in response.aiter_lines():
                    line = str(raw_line or "")
                    if not line:
                        if data_lines:
                            payload = self._parse_sse_payload("\n".join(data_lines))
                            yield event_name, payload
                        event_name = "message"
                        data_lines = []
                        continue
                    if line.startswith("event:"):
                        event_name = line.split(":", 1)[1].strip() or "message"
                        continue
                    if line.startswith("data:"):
                        data_lines.append(line.split(":", 1)[1].lstrip())
                if data_lines:
                    payload = self._parse_sse_payload("\n".join(data_lines))
                    yield event_name, payload

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if query:
            encoded_query = urlencode({key: value for key, value in query.items() if value is not None})
            if encoded_query:
                url = f"{url}?{encoded_query}"

        body: bytes | None = None
        headers = {"Accept": "application/json", "User-Agent": "Mini-Agent-TUI/1.0"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url=url, data=body, method=method.upper(), headers=headers)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = self._extract_error_detail(exc)
            raise RuntimeError(f"Gateway HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Gateway unavailable: {exc.reason}") from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Gateway request failed: {exc}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Gateway returned invalid JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("Gateway returned non-object payload.")
        if parsed.get("ok") is not True:
            error = parsed.get("error")
            if isinstance(error, dict):
                detail = _safe_text(error.get("message")) or _safe_text(error.get("detail"))
            else:
                detail = _safe_text(error)
            raise RuntimeError(detail or "Gateway returned unsuccessful envelope.")
        return parsed.get("data")

    @staticmethod
    def _parse_sse_payload(raw: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Gateway stream returned invalid JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("Gateway stream returned non-object payload.")
        return parsed

    @staticmethod
    def _extract_error_detail(exc: HTTPError) -> str:
        try:
            raw = exc.read().decode("utf-8")
        except Exception:
            raw = ""
        if not raw:
            return exc.reason or "request failed"
        try:
            parsed = json.loads(raw)
        except Exception:
            return raw
        if isinstance(parsed, dict):
            if isinstance(parsed.get("detail"), str):
                return parsed["detail"]
            error = parsed.get("error")
            if isinstance(error, dict):
                return _safe_text(error.get("message")) or _safe_text(error.get("detail")) or raw
        return raw
