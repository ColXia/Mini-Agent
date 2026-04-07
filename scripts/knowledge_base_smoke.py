"""Local smoke check for knowledge-base router core flows."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mini_agent.rag import HybridSearchStore
from subprograms.knowledge_base.gateway import router as kb_router_module


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kb_smoke_") as tmp_dir:
        temp_root = Path(tmp_dir)
        store_path = temp_root / "smoke_store.json"
        source_file = temp_root / "smoke_note.md"
        source_file.write_text("# Smoke\n\nHybrid retrieval check.", encoding="utf-8")

        kb_router_module._STORE = HybridSearchStore(store_path)

        app = FastAPI()
        app.include_router(kb_router_module.router)
        client = TestClient(app)

        ingest_text = client.post(
            "/api/knowledge-base/ingest",
            json={
                "document_name": "smoke.txt",
                "content": "Mini-Agent hybrid retrieval smoke run.",
                "knowledge_base_id": "smoke",
            },
        )
        ingest_file = client.post(
            "/api/knowledge-base/ingest/file",
            json={
                "path": str(source_file),
                "knowledge_base_id": "smoke",
            },
        )
        query = client.post(
            "/api/knowledge-base/query",
            json={
                "query": "hybrid retrieval",
                "knowledge_base_id": "smoke",
                "top_k": 3,
            },
        )
        debug = client.post(
            "/api/knowledge-base/query/debug",
            json={
                "query": "hybrid retrieval",
                "knowledge_base_id": "smoke",
                "top_k": 3,
                "debug_k": 5,
            },
        )
        stats = client.get(
            "/api/knowledge-base/stats", params={"knowledge_base_id": "smoke"}
        )
        health = client.get("/api/knowledge-base/health")

        report = {
            "ingest_text": ingest_text.status_code,
            "ingest_file": ingest_file.status_code,
            "query": query.status_code,
            "debug": debug.status_code,
            "stats": stats.status_code,
            "health": health.status_code,
            "query_hit_count": len(query.json().get("hits", []))
            if query.status_code == 200
            else 0,
            "debug_fused_count": len(debug.json().get("fused_ranking", []))
            if debug.status_code == 200
            else 0,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))

        expected_ok = {
            "ingest_text",
            "ingest_file",
            "query",
            "debug",
            "stats",
            "health",
        }
        if any(report[key] != 200 for key in expected_ok):
            return 1
        if report["query_hit_count"] < 1 or report["debug_fused_count"] < 1:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
