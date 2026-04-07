"""Tests for MaxKB query/ingest tool baseline (P16 T4.2)."""

from __future__ import annotations

import json

import pytest

from mini_agent.tools.maxkb_query import (
    MaxkbClient,
    MaxkbConfig,
    MaxkbError,
    MaxkbIngestTool,
    MaxkbQueryTool,
)


def test_maxkb_client_query_and_ingest_with_transport():
    captured: list[tuple[str, dict[str, object]]] = []

    def _transport(endpoint: str, payload: dict[str, object]) -> dict[str, object]:
        captured.append((endpoint, dict(payload)))
        if endpoint == "/api/search":
            return {
                "success": True,
                "hits": [
                    {
                        "id": "chunk-1",
                        "score": 0.92,
                        "content": "Mini-Agent baseline",
                    }
                ],
            }
        if endpoint == "/api/documents":
            return {"success": True, "document_id": "doc-1"}
        return {"success": False}

    client = MaxkbClient(transport=_transport)
    query = client.query(query="mini-agent", top_k=3)
    ingest = client.ingest(document_name="notes.md", content="hello")

    assert query.success is True
    assert len(query.hits) == 1
    assert ingest.success is True
    assert [item[0] for item in captured] == ["/api/search", "/api/documents"]


def test_maxkb_client_requires_transport_or_config():
    client = MaxkbClient()
    with pytest.raises(MaxkbError):
        client.query(query="x")

    with pytest.raises(MaxkbError):
        MaxkbConfig(base_url="").normalized()


@pytest.mark.asyncio
async def test_maxkb_tools_execute_with_stub_transport():
    def _transport(endpoint: str, payload: dict[str, object]) -> dict[str, object]:
        if endpoint == "/api/search":
            return {"success": True, "hits": [{"id": "1", "content": payload["query"]}]}
        if endpoint == "/api/documents":
            return {"success": True, "document_id": "doc-2"}
        return {"success": False}

    client = MaxkbClient(transport=_transport)
    query_tool = MaxkbQueryTool(client)
    ingest_tool = MaxkbIngestTool(client)

    query_result = await query_tool.execute(query="hello", top_k=2)
    ingest_result = await ingest_tool.execute(document_name="memo.txt", content="text body")

    assert query_result.success is True
    query_payload = json.loads(query_result.content)
    assert query_payload["hits"][0]["content"] == "hello"
    assert ingest_result.success is True
