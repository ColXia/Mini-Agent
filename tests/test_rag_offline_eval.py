"""Tests for offline RAG evaluation script."""

from __future__ import annotations

import json
from pathlib import Path

from mini_agent.rag.lightweight_hybrid import HybridSearchStore
from scripts.rag_offline_eval import evaluate


def test_rag_offline_eval_report(tmp_path: Path):
    store_path = tmp_path / "rag_store.json"
    dataset_path = tmp_path / "eval.jsonl"

    store = HybridSearchStore(store_path)
    store.ingest_text(
        document_name="doc.md",
        content="Mini-Agent supports BM25 and RRF hybrid retrieval.",
        knowledge_base_id="kb1",
    )

    dataset_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "question": "What retrieval does Mini-Agent use?",
                        "knowledge_base_id": "kb1",
                        "expected_chunks": ["BM25", "RRF"],
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "question": "What retrieval does Mini-Agent use?",
                        "knowledge_base_id": "kb1",
                        "expected_chunks": ["hybrid retrieval"],
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )

    report = evaluate(store_path=store_path, dataset_path=dataset_path, top_k=3)

    assert report["cases"] == 2
    assert report["topk_hit_rate"] >= 0.5
    assert report["citation_coverage"] == 1.0
    assert report["results"][0]["hit_count"] >= 1
