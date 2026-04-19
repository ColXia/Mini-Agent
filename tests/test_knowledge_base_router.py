"""Tests for knowledge-base subprogram router."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mini_agent.rag.lightweight_hybrid import HybridSearchStore
import subprograms.knowledge_base.gateway.router as kb_router_module


def test_knowledge_base_router_query_and_ingest(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "rag_store.json"
    monkeypatch.setattr(kb_router_module, "_STORE", HybridSearchStore(store_path))

    app = FastAPI()
    app.include_router(kb_router_module.router)
    client = TestClient(app)

    ingest_resp = client.post(
        "/api/knowledge-base/ingest",
        json={
            "document_name": "doc.md",
            "content": "hello mini-agent knowledge base",
        },
    )
    query_resp = client.post(
        "/api/knowledge-base/query",
        json={
            "query": "mini-agent",
            "top_k": 3,
        },
    )
    stats_resp = client.get("/api/knowledge-base/stats")
    health_resp = client.get("/api/knowledge-base/health")

    assert ingest_resp.status_code == 200
    assert ingest_resp.json()["status"] == "ok"
    assert ingest_resp.json()["chunk_count"] >= 1

    assert query_resp.status_code == 200
    assert query_resp.json()["status"] == "ok"
    assert query_resp.json()["hits"]
    assert "mini-agent" in query_resp.json()["hits"][0]["content"]
    assert "citation" in query_resp.json()["hits"][0]
    assert query_resp.json()["hits"][0]["citation"]["chunk_id"]
    assert query_resp.json()["hits"][0]["citation"]["title"] == "doc.md"

    assert stats_resp.status_code == 200
    assert stats_resp.json()["chunk_count"] >= 1

    assert health_resp.status_code == 200
    assert health_resp.json()["service"] == "knowledge-base"


def test_knowledge_base_router_ingest_file(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "rag_store.json"
    source_file = tmp_path / "note.md"
    source_file.write_text("# Title\n\nRAG with docling parser.", encoding="utf-8")

    monkeypatch.setattr(kb_router_module, "_STORE", HybridSearchStore(store_path))

    app = FastAPI()
    app.include_router(kb_router_module.router)
    client = TestClient(app)

    ingest_resp = client.post(
        "/api/knowledge-base/ingest/file",
        json={
            "path": str(source_file),
            "knowledge_base_id": "docs",
        },
    )
    query_resp = client.post(
        "/api/knowledge-base/query",
        json={
            "query": "docling parser",
            "knowledge_base_id": "docs",
        },
    )

    assert ingest_resp.status_code == 200
    assert ingest_resp.json()["used_docling"] is False
    assert ingest_resp.json()["chunk_count"] >= 1

    assert query_resp.status_code == 200
    assert query_resp.json()["hits"]
    assert query_resp.json()["hits"][0]["citation"]["source_path"] == str(source_file)


def test_knowledge_base_router_query_debug(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "rag_store.json"
    monkeypatch.setattr(kb_router_module, "_STORE", HybridSearchStore(store_path))

    app = FastAPI()
    app.include_router(kb_router_module.router)
    client = TestClient(app)

    client.post(
        "/api/knowledge-base/ingest",
        json={
            "document_name": "debug-a.md",
            "content": "alpha beta gamma",
        },
    )
    client.post(
        "/api/knowledge-base/ingest",
        json={
            "document_name": "debug-b.md",
            "content": "beta delta epsilon",
        },
    )

    debug_resp = client.post(
        "/api/knowledge-base/query/debug",
        json={
            "query": "beta",
            "top_k": 2,
            "debug_k": 5,
        },
    )

    assert debug_resp.status_code == 200
    payload = debug_resp.json()
    assert payload["status"] == "ok"
    assert payload["bm25_ranking"]
    assert payload["vector_ranking"]
    assert payload["fused_ranking"]
    assert payload["fused_ranking"][0]["final_rank"] == 1


def test_knowledge_base_router_chunking_config(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "rag_store.json"
    monkeypatch.setattr(kb_router_module, "_STORE", HybridSearchStore(store_path))

    app = FastAPI()
    app.include_router(kb_router_module.router)
    client = TestClient(app)

    base_text = " ".join([f"token{i}" for i in range(120)])
    ingest_resp = client.post(
        "/api/knowledge-base/ingest",
        json={
            "document_name": "chunked.txt",
            "content": base_text,
            "chunking": {
                "strategy": "fixed",
                "chunk_size": 60,
                "overlap": 10,
            },
        },
    )

    assert ingest_resp.status_code == 200
    assert ingest_resp.json()["chunk_count"] >= 2


def test_knowledge_base_router_query_rewrite(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "rag_store.json"
    monkeypatch.setattr(kb_router_module, "_STORE", HybridSearchStore(store_path))

    app = FastAPI()
    app.include_router(kb_router_module.router)
    client = TestClient(app)

    client.post(
        "/api/knowledge-base/ingest",
        json={
            "document_name": "topic.md",
            "content": "Mini-Agent supports BM25 and RRF hybrid retrieval.",
        },
    )

    query_resp = client.post(
        "/api/knowledge-base/query",
        json={
            "query": "它怎么做？",
            "conversation": ["我们在讨论 Mini-Agent 的混合检索方案"],
            "top_k": 3,
        },
    )

    assert query_resp.status_code == 200
    payload = query_resp.json()
    assert payload["query_rewrite"]["rewritten"] is True
    assert "Mini-Agent" in payload["query_rewrite"]["rewritten_query"]
    assert payload["hits"]


def test_knowledge_base_router_query_rewrite_can_disable(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "rag_store.json"
    monkeypatch.setattr(kb_router_module, "_STORE", HybridSearchStore(store_path))

    app = FastAPI()
    app.include_router(kb_router_module.router)
    client = TestClient(app)

    client.post(
        "/api/knowledge-base/ingest",
        json={
            "document_name": "topic.md",
            "content": "Mini-Agent supports BM25 and RRF hybrid retrieval.",
        },
    )

    query_resp = client.post(
        "/api/knowledge-base/query",
        json={
            "query": "它怎么做？",
            "conversation": ["我们在讨论 Mini-Agent 的混合检索方案"],
            "enable_query_rewrite": False,
            "top_k": 3,
        },
    )

    assert query_resp.status_code == 200
    payload = query_resp.json()
    assert payload["query_rewrite"]["rewritten"] is False
    assert payload["query_rewrite"]["rewritten_query"] == "它怎么做？"


def test_knowledge_base_router_admin_rebuild_and_cleanup(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "rag_store.json"
    monkeypatch.setattr(kb_router_module, "_STORE", HybridSearchStore(store_path))

    app = FastAPI()
    app.include_router(kb_router_module.router)
    client = TestClient(app)

    client.post(
        "/api/knowledge-base/ingest",
        json={
            "document_name": "admin.md",
            "content": "hybrid retrieval and citation",
            "knowledge_base_id": "ops",
        },
    )

    rebuild_resp = client.post(
        "/api/knowledge-base/admin/rebuild",
        json={"knowledge_base_id": "ops"},
    )
    assert rebuild_resp.status_code == 200
    rebuild_payload = rebuild_resp.json()
    assert rebuild_payload["affected_chunks"] >= 1
    assert rebuild_payload["affected_documents"] == 1

    cleanup_resp = client.request(
        "DELETE",
        "/api/knowledge-base/admin/cleanup",
        json={"knowledge_base_id": "ops"},
    )
    assert cleanup_resp.status_code == 200
    cleanup_payload = cleanup_resp.json()
    assert cleanup_payload["removed_chunks"] >= 1

    query_resp = client.post(
        "/api/knowledge-base/query",
        json={"query": "hybrid", "knowledge_base_id": "ops", "top_k": 3},
    )
    assert query_resp.status_code == 200
    assert query_resp.json()["hits"] == []


def test_knowledge_base_router_config_endpoint(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "rag_store.json"
    monkeypatch.setattr(kb_router_module, "_STORE", HybridSearchStore(store_path))

    app = FastAPI()
    app.include_router(kb_router_module.router)
    client = TestClient(app)

    resp = client.get("/api/knowledge-base/config")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert "query_top_k_default" in payload
    assert "ingest_max_content_chars" in payload


def test_knowledge_base_router_ingest_content_guardrail(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "rag_store.json"
    monkeypatch.setattr(kb_router_module, "_STORE", HybridSearchStore(store_path))

    limited_settings = replace(kb_router_module._SETTINGS, ingest_max_content_chars=20)
    monkeypatch.setattr(kb_router_module, "_SETTINGS", limited_settings)

    app = FastAPI()
    app.include_router(kb_router_module.router)
    client = TestClient(app)

    ingest_resp = client.post(
        "/api/knowledge-base/ingest",
        json={
            "document_name": "too-large.md",
            "content": "x" * 21,
        },
    )

    assert ingest_resp.status_code == 400
    assert "content too large" in ingest_resp.json()["detail"]


def test_knowledge_base_router_ingest_job_lifecycle(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "rag_store.json"
    monkeypatch.setattr(kb_router_module, "_STORE", HybridSearchStore(store_path))

    app = FastAPI()
    app.include_router(kb_router_module.router)
    client = TestClient(app)

    create_resp = client.post(
        "/api/knowledge-base/ingest/jobs",
        json={
            "mode": "text",
            "process_now": False,
            "text": {
                "document_name": "job.md",
                "content": "queued job ingestion",
                "knowledge_base_id": "jobs",
            },
        },
    )
    assert create_resp.status_code == 200
    create_payload = create_resp.json()
    job_id = create_payload["job"]["job_id"]
    assert create_payload["job"]["status"] == "queued"

    run_resp = client.post(f"/api/knowledge-base/ingest/jobs/{job_id}/run")
    assert run_resp.status_code == 200
    run_payload = run_resp.json()
    assert run_payload["job"]["status"] == "succeeded"
    assert run_payload["job"]["result"]["chunk_count"] >= 1

    get_resp = client.get(f"/api/knowledge-base/ingest/jobs/{job_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["job"]["status"] == "succeeded"

    summary_resp = client.get("/api/knowledge-base/ingest/jobs")
    assert summary_resp.status_code == 200
    assert summary_resp.json()["counts"]["succeeded"] >= 1


def test_knowledge_base_router_ingest_job_retry(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "rag_store.json"
    store = HybridSearchStore(store_path)
    monkeypatch.setattr(kb_router_module, "_STORE", store)

    limited_settings = replace(kb_router_module._SETTINGS, ingest_job_max_retries=0)
    monkeypatch.setattr(kb_router_module, "_SETTINGS", limited_settings)

    attempts = {"count": 0}
    original_ingest = store.ingest_text

    def flaky_ingest(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("synthetic failure")
        return original_ingest(*args, **kwargs)

    monkeypatch.setattr(store, "ingest_text", flaky_ingest)

    app = FastAPI()
    app.include_router(kb_router_module.router)
    client = TestClient(app)

    create_resp = client.post(
        "/api/knowledge-base/ingest/jobs",
        json={
            "mode": "text",
            "process_now": True,
            "text": {
                "document_name": "retry.md",
                "content": "retry path",
                "knowledge_base_id": "jobs",
            },
        },
    )
    assert create_resp.status_code == 200
    create_payload = create_resp.json()
    job_id = create_payload["job"]["job_id"]
    assert create_payload["job"]["status"] == "failed"
    assert "synthetic failure" in create_payload["job"]["error"]

    retry_resp = client.post(f"/api/knowledge-base/ingest/jobs/{job_id}/retry")
    assert retry_resp.status_code == 200
    retry_payload = retry_resp.json()
    assert retry_payload["job"]["status"] == "succeeded"
    assert retry_payload["job"]["attempts"] == 2
