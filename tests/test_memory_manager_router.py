"""Tests for memory-manager subprogram router (P16 T4.4)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from subprograms.memory_manager.gateway.router import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_memory_manager_append_summary_search_export(monkeypatch, tmp_path):
    monkeypatch.setenv("MINI_AGENT_MEMORY_ROOT", str(tmp_path))
    client = _client()

    append = client.post(
        "/api/memory/append",
        json={
            "content": "remember the mini-agent roadmap",
            "category": "plan",
            "scope": "both",
        },
    )
    summary = client.get("/api/memory/summary")
    search = client.get("/api/memory/search", params={"query": "roadmap", "limit": 10})
    export_jsonl = client.get("/api/memory/export", params={"format": "jsonl"})
    export_markdown = client.get("/api/memory/export", params={"format": "markdown"})

    assert append.status_code == 200
    assert append.json()["status"] == "ok"

    assert summary.status_code == 200
    assert summary.json()["notes_count"] >= 1
    assert "plan" in summary.json()["categories"]

    assert search.status_code == 200
    assert search.json()["total"] >= 1
    assert "roadmap" in search.json()["items"][0]["content"]

    assert export_jsonl.status_code == 200
    assert export_jsonl.json()["format"] == "jsonl"
    assert "mini-agent roadmap" in export_jsonl.json()["content"]

    assert export_markdown.status_code == 200
    assert export_markdown.json()["format"] == "markdown"
    assert "##" in export_markdown.json()["content"]


def test_memory_manager_health():
    client = _client()
    resp = client.get("/api/memory/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "memory-manager"
