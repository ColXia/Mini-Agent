"""Web search tool baseline with pluggable multi-engine providers."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from typing import Any, Callable

import requests

from mini_agent.tools.base import Tool, ToolResult


class WebSearchError(RuntimeError):
    """Base web-search error."""


@dataclass(frozen=True)
class SearchHit:
    """One normalized web search result."""

    title: str
    url: str
    snippet: str
    source_engine: str
    rank: int


@dataclass(frozen=True)
class SearchResponse:
    """Search response envelope."""

    query: str
    hits: tuple[SearchHit, ...]
    errors: tuple[str, ...] = ()
    engines_used: tuple[str, ...] = ()


SearchProvider = Callable[[str, int], list[SearchHit]]


@dataclass(frozen=True)
class WebSearchConfig:
    """Search provider configuration."""

    searxng_url: str | None = None
    brave_api_key: str | None = None
    google_api_key: str | None = None
    google_cx: str | None = None
    timeout_seconds: float = 10.0

    @staticmethod
    def from_env() -> "WebSearchConfig":
        return WebSearchConfig(
            searxng_url=(os.getenv("MINI_AGENT_SEARXNG_URL", "").strip() or None),
            brave_api_key=(os.getenv("MINI_AGENT_BRAVE_API_KEY", "").strip() or None),
            google_api_key=(os.getenv("MINI_AGENT_GOOGLE_API_KEY", "").strip() or None),
            google_cx=(os.getenv("MINI_AGENT_GOOGLE_CX", "").strip() or None),
            timeout_seconds=max(1.0, float(os.getenv("MINI_AGENT_WEB_SEARCH_TIMEOUT", "10") or "10")),
        )


class WebSearchClient:
    """Multi-engine web-search client."""

    DEFAULT_ENGINE_ORDER = ("searxng", "brave", "google", "duckduckgo")

    def __init__(
        self,
        *,
        config: WebSearchConfig | None = None,
        providers: dict[str, SearchProvider] | None = None,
    ) -> None:
        self.config = config or WebSearchConfig.from_env()
        self.providers: dict[str, SearchProvider] = {
            "searxng": self._search_searxng,
            "brave": self._search_brave,
            "google": self._search_google,
            "duckduckgo": self._search_duckduckgo,
        }
        if providers:
            self.providers.update({key.strip().lower(): value for key, value in providers.items()})

    def search(
        self,
        *,
        query: str,
        limit: int = 5,
        engines: list[str] | None = None,
    ) -> SearchResponse:
        normalized_query = query.strip()
        if not normalized_query:
            raise WebSearchError("query must not be empty.")

        requested_engines = tuple(
            item.strip().lower() for item in (engines or list(self.DEFAULT_ENGINE_ORDER)) if item and item.strip()
        )
        max_hits = max(1, int(limit))

        merged: list[SearchHit] = []
        errors: list[str] = []
        seen_urls: set[str] = set()
        used_engines: list[str] = []

        for engine in requested_engines:
            provider = self.providers.get(engine)
            if provider is None:
                errors.append(f"{engine}: provider not registered")
                continue
            used_engines.append(engine)
            try:
                raw_hits = provider(normalized_query, max_hits)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{engine}: {type(exc).__name__}: {exc}")
                continue
            for item in raw_hits:
                normalized_url = item.url.strip().lower()
                if not normalized_url or normalized_url in seen_urls:
                    continue
                seen_urls.add(normalized_url)
                merged.append(
                    SearchHit(
                        title=item.title.strip(),
                        url=item.url.strip(),
                        snippet=item.snippet.strip(),
                        source_engine=item.source_engine,
                        rank=len(merged) + 1,
                    )
                )
                if len(merged) >= max_hits:
                    break
            if len(merged) >= max_hits:
                break

        return SearchResponse(
            query=normalized_query,
            hits=tuple(merged[:max_hits]),
            errors=tuple(errors),
            engines_used=tuple(used_engines),
        )

    def _search_searxng(self, query: str, limit: int) -> list[SearchHit]:
        base = (self.config.searxng_url or "").strip().rstrip("/")
        if not base:
            raise WebSearchError("searxng_url is not configured.")
        response = requests.get(
            f"{base}/search",
            params={"q": query, "format": "json"},
            timeout=self.config.timeout_seconds,
        )
        payload = self._read_json_response(response)
        raw_results = payload.get("results", [])
        if not isinstance(raw_results, list):
            return []
        hits: list[SearchHit] = []
        for item in raw_results[:limit]:
            if not isinstance(item, dict):
                continue
            hits.append(
                SearchHit(
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    snippet=str(item.get("content", "")),
                    source_engine="searxng",
                    rank=len(hits) + 1,
                )
            )
        return hits

    def _search_brave(self, query: str, limit: int) -> list[SearchHit]:
        api_key = (self.config.brave_api_key or "").strip()
        if not api_key:
            raise WebSearchError("brave_api_key is not configured.")
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            params={"q": query, "count": limit},
            timeout=self.config.timeout_seconds,
        )
        payload = self._read_json_response(response)
        raw_results = payload.get("web", {}).get("results", []) if isinstance(payload.get("web"), dict) else []
        if not isinstance(raw_results, list):
            return []
        hits: list[SearchHit] = []
        for item in raw_results[:limit]:
            if not isinstance(item, dict):
                continue
            hits.append(
                SearchHit(
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    snippet=str(item.get("description", "")),
                    source_engine="brave",
                    rank=len(hits) + 1,
                )
            )
        return hits

    def _search_google(self, query: str, limit: int) -> list[SearchHit]:
        api_key = (self.config.google_api_key or "").strip()
        cx = (self.config.google_cx or "").strip()
        if not api_key or not cx:
            raise WebSearchError("google_api_key/google_cx are not configured.")
        response = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"q": query, "num": min(10, limit), "key": api_key, "cx": cx},
            timeout=self.config.timeout_seconds,
        )
        payload = self._read_json_response(response)
        raw_items = payload.get("items", [])
        if not isinstance(raw_items, list):
            return []
        hits: list[SearchHit] = []
        for item in raw_items[:limit]:
            if not isinstance(item, dict):
                continue
            hits.append(
                SearchHit(
                    title=str(item.get("title", "")),
                    url=str(item.get("link", "")),
                    snippet=str(item.get("snippet", "")),
                    source_engine="google",
                    rank=len(hits) + 1,
                )
            )
        return hits

    def _search_duckduckgo(self, query: str, limit: int) -> list[SearchHit]:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=self.config.timeout_seconds,
        )
        payload = self._read_json_response(response)
        hits: list[SearchHit] = []

        abstract_url = str(payload.get("AbstractURL", "")).strip()
        abstract_text = str(payload.get("AbstractText", "")).strip()
        heading = str(payload.get("Heading", "")).strip()
        if abstract_url:
            hits.append(
                SearchHit(
                    title=heading or "DuckDuckGo Result",
                    url=abstract_url,
                    snippet=abstract_text,
                    source_engine="duckduckgo",
                    rank=1,
                )
            )

        related = payload.get("RelatedTopics", [])
        if isinstance(related, list):
            for item in related:
                if len(hits) >= limit:
                    break
                if not isinstance(item, dict):
                    continue
                if "Topics" in item and isinstance(item["Topics"], list):
                    for sub in item["Topics"]:
                        if len(hits) >= limit:
                            break
                        self._append_ddg_topic(hits, sub)
                else:
                    self._append_ddg_topic(hits, item)

        return hits[:limit]

    @staticmethod
    def _append_ddg_topic(hits: list[SearchHit], item: dict[str, Any]) -> None:
        if not isinstance(item, dict):
            return
        url = str(item.get("FirstURL", "")).strip()
        text = str(item.get("Text", "")).strip()
        if not url:
            return
        title = text.split(" - ", 1)[0].strip() if text else "DuckDuckGo Topic"
        hits.append(
            SearchHit(
                title=title,
                url=url,
                snippet=text,
                source_engine="duckduckgo",
                rank=len(hits) + 1,
            )
        )

    @staticmethod
    def _read_json_response(response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise WebSearchError(f"search response is not valid JSON: {exc}") from exc
        if response.status_code >= 400:
            raise WebSearchError(f"search request failed ({response.status_code}).")
        if not isinstance(payload, dict):
            raise WebSearchError("search response JSON must be an object.")
        return payload


class WebSearchTool(Tool):
    """Tool wrapper for multi-engine web search."""

    def __init__(self, client: WebSearchClient | None = None) -> None:
        self._client = client or WebSearchClient()

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web with multiple engines and return deduplicated results."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                "engines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional engine priority, e.g. ['searxng','duckduckgo'].",
                },
            },
            "required": ["query"],
        }

    async def execute(self, *args, **kwargs) -> ToolResult:  # type: ignore[override]
        query = str(kwargs.get("query", "")).strip()
        if not query:
            return ToolResult(success=False, error="query is required.")
        limit = int(kwargs.get("limit", 5))
        engines = kwargs.get("engines")
        if engines is not None and not isinstance(engines, list):
            return ToolResult(success=False, error="engines must be a list of strings.")

        try:
            response = self._client.search(
                query=query,
                limit=limit,
                engines=[str(item) for item in engines] if isinstance(engines, list) else None,
            )
            payload = {
                "query": response.query,
                "hits": [item.__dict__ for item in response.hits],
                "errors": list(response.errors),
                "engines_used": list(response.engines_used),
            }
            return ToolResult(success=True, content=json.dumps(payload, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")
