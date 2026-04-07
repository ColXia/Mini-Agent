"""Tests for web-search tool baseline (P16 T4.3)."""

from __future__ import annotations

import json

import pytest

from mini_agent.tools.web_search import SearchHit, WebSearchClient, WebSearchTool


def test_web_search_client_merges_dedupes_and_limits_hits():
    def _searxng(query: str, limit: int):  # noqa: ARG001
        return [
            SearchHit(
                title="A",
                url="https://example.com/a",
                snippet="first",
                source_engine="searxng",
                rank=1,
            ),
            SearchHit(
                title="B",
                url="https://example.com/b",
                snippet="second",
                source_engine="searxng",
                rank=2,
            ),
        ][:limit]

    def _brave(query: str, limit: int):  # noqa: ARG001
        return [
            SearchHit(
                title="Dup A",
                url="https://example.com/a",
                snippet="duplicate",
                source_engine="brave",
                rank=1,
            ),
            SearchHit(
                title="C",
                url="https://example.com/c",
                snippet="third",
                source_engine="brave",
                rank=2,
            ),
        ][:limit]

    client = WebSearchClient(providers={"searxng": _searxng, "brave": _brave})
    response = client.search(query="mini-agent", limit=3, engines=["searxng", "brave"])

    assert len(response.hits) == 3
    assert [item.url for item in response.hits] == [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
    ]
    assert response.errors == ()


def test_web_search_client_records_provider_errors():
    def _broken(_query: str, _limit: int):
        raise RuntimeError("boom")

    client = WebSearchClient(providers={"searxng": _broken})
    response = client.search(query="x", engines=["searxng"], limit=2)

    assert response.hits == ()
    assert len(response.errors) == 1
    assert "boom" in response.errors[0]


@pytest.mark.asyncio
async def test_web_search_tool_execute_success_and_validation():
    def _provider(query: str, limit: int):
        return [
            SearchHit(
                title="Result",
                url=f"https://example.com/{query}",
                snippet="ok",
                source_engine="mock",
                rank=1,
            )
        ][:limit]

    tool = WebSearchTool(client=WebSearchClient(providers={"duckduckgo": _provider}))

    ok = await tool.execute(query="mini", limit=1, engines=["duckduckgo"])
    bad = await tool.execute(query="", limit=1)

    assert ok.success is True
    payload = json.loads(ok.content)
    assert payload["hits"][0]["url"].endswith("/mini")
    assert bad.success is False
    assert "query" in (bad.error or "").lower()
