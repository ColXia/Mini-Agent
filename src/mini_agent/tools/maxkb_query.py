"""MaxKB query/ingest tool baseline with pluggable transport."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Callable

import requests

from mini_agent.tools.base import Tool, ToolResult


class MaxkbError(RuntimeError):
    """Base MaxKB client error."""


@dataclass(frozen=True)
class MaxkbConfig:
    """MaxKB endpoint config."""

    base_url: str
    api_key: str | None = None
    timeout_seconds: float = 20.0

    def normalized(self) -> "MaxkbConfig":
        base = self.base_url.strip().rstrip("/")
        if not base:
            raise MaxkbError("MaxKB base_url must not be empty.")
        return MaxkbConfig(
            base_url=base,
            api_key=(self.api_key.strip() if self.api_key else None),
            timeout_seconds=max(1.0, float(self.timeout_seconds)),
        )


MaxkbTransport = Callable[[str, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class MaxkbQueryResult:
    """Query result envelope."""

    success: bool
    query: str
    hits: tuple[dict[str, Any], ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MaxkbIngestResult:
    """Ingest result envelope."""

    success: bool
    document_name: str
    raw: dict[str, Any] = field(default_factory=dict)


class MaxkbClient:
    """Lean MaxKB client with query + ingest APIs."""

    def __init__(
        self,
        *,
        config: MaxkbConfig | None = None,
        transport: MaxkbTransport | None = None,
    ) -> None:
        self._config = config.normalized() if config is not None else None
        self._transport = transport

    def query(
        self,
        *,
        query: str,
        knowledge_base_id: str | None = None,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> MaxkbQueryResult:
        normalized_query = query.strip()
        if not normalized_query:
            raise MaxkbError("query must not be empty.")

        payload = {
            "query": normalized_query,
            "top_k": max(1, int(top_k)),
            "knowledge_base_id": knowledge_base_id.strip() if knowledge_base_id else None,
            "filters": dict(filters or {}),
        }
        raw = self._request("/api/search", payload)
        hits_raw = raw.get("hits", [])
        hits = tuple(item for item in hits_raw if isinstance(item, dict)) if isinstance(hits_raw, list) else ()
        success = bool(raw.get("success", True))
        return MaxkbQueryResult(success=success, query=normalized_query, hits=hits, raw=raw)

    def ingest(
        self,
        *,
        document_name: str,
        content: str,
        knowledge_base_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MaxkbIngestResult:
        name = document_name.strip()
        if not name:
            raise MaxkbError("document_name must not be empty.")
        if not content.strip():
            raise MaxkbError("content must not be empty.")

        payload = {
            "document_name": name,
            "content": content,
            "knowledge_base_id": knowledge_base_id.strip() if knowledge_base_id else None,
            "metadata": dict(metadata or {}),
        }
        raw = self._request("/api/documents", payload)
        success = bool(raw.get("success", True))
        return MaxkbIngestResult(success=success, document_name=name, raw=raw)

    def _request(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._transport is not None:
            raw = self._transport(endpoint, dict(payload))
            if not isinstance(raw, dict):
                raise TypeError("MaxKB transport must return dict payload.")
            return raw

        if self._config is None:
            raise MaxkbError("MaxKB transport is not configured (missing config or custom transport).")

        headers = {
            "Content-Type": "application/json",
        }
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"

        response = requests.post(
            f"{self._config.base_url}{endpoint}",
            headers=headers,
            json=payload,
            timeout=self._config.timeout_seconds,
        )
        try:
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            raise MaxkbError(f"MaxKB response is not valid JSON: {exc}") from exc
        if response.status_code >= 400:
            detail = data.get("error") if isinstance(data, dict) else None
            raise MaxkbError(f"MaxKB request failed ({response.status_code}): {detail or 'unknown error'}")
        if not isinstance(data, dict):
            raise MaxkbError("MaxKB response JSON must be an object.")
        return data


class MaxkbQueryTool(Tool):
    """Tool for querying MaxKB knowledge base."""

    def __init__(self, client: MaxkbClient) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "maxkb_query"

    @property
    def description(self) -> str:
        return "Query MaxKB knowledge base and return top matching chunks."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "knowledge_base_id": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                "filters": {"type": "object"},
            },
            "required": ["query"],
        }

    async def execute(self, *args, **kwargs) -> ToolResult:  # type: ignore[override]
        try:
            result = self._client.query(
                query=str(kwargs.get("query", "")),
                knowledge_base_id=(str(kwargs["knowledge_base_id"]) if kwargs.get("knowledge_base_id") else None),
                top_k=int(kwargs.get("top_k", 5)),
                filters=(dict(kwargs["filters"]) if isinstance(kwargs.get("filters"), dict) else None),
            )
            payload = {
                "success": result.success,
                "query": result.query,
                "hits": list(result.hits),
                "raw": result.raw,
            }
            return ToolResult(success=True, content=json.dumps(payload, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")


class MaxkbIngestTool(Tool):
    """Tool for ingesting documents into MaxKB."""

    def __init__(self, client: MaxkbClient) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "maxkb_ingest"

    @property
    def description(self) -> str:
        return "Ingest a document payload into MaxKB knowledge base."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_name": {"type": "string"},
                "content": {"type": "string"},
                "knowledge_base_id": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["document_name", "content"],
        }

    async def execute(self, *args, **kwargs) -> ToolResult:  # type: ignore[override]
        try:
            result = self._client.ingest(
                document_name=str(kwargs.get("document_name", "")),
                content=str(kwargs.get("content", "")),
                knowledge_base_id=(str(kwargs["knowledge_base_id"]) if kwargs.get("knowledge_base_id") else None),
                metadata=(dict(kwargs["metadata"]) if isinstance(kwargs.get("metadata"), dict) else None),
            )
            payload = {
                "success": result.success,
                "document_name": result.document_name,
                "raw": result.raw,
            }
            return ToolResult(success=True, content=json.dumps(payload, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")


def create_maxkb_tools(client: MaxkbClient) -> list[Tool]:
    """Create MaxKB tool bundle."""
    return [MaxkbQueryTool(client), MaxkbIngestTool(client)]
