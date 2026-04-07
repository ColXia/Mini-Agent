"""Lightweight offline evaluation for local hybrid RAG retrieval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mini_agent.rag import HybridSearchStore


def _load_dataset(dataset_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        payload = line.strip()
        if not payload:
            continue
        item = json.loads(payload)
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains_any(text: str, candidates: list[str]) -> bool:
    normalized = _normalize_text(text)
    return any(_normalize_text(item) in normalized for item in candidates if item)


def evaluate(
    *,
    store_path: Path,
    dataset_path: Path,
    top_k: int,
) -> dict[str, Any]:
    store = HybridSearchStore(store_path)
    cases = _load_dataset(dataset_path)
    if not cases:
        raise ValueError("dataset is empty")

    topk_hit_count = 0
    citation_coverage_sum = 0.0
    case_results: list[dict[str, Any]] = []

    for index, case in enumerate(cases, start=1):
        query = str(case.get("question") or case.get("query") or "").strip()
        if not query:
            continue
        kb_id = str(case.get("knowledge_base_id") or "default")
        expected = case.get("expected_chunks") or case.get("expected") or []
        expected_chunks = [str(item) for item in expected if str(item or "").strip()]

        result = store.query(query=query, knowledge_base_id=kb_id, top_k=top_k)
        hits = list(result.hits)

        text_pool = [
            " ".join(
                [
                    hit.content,
                    hit.document_name,
                    str(hit.citation.get("source_path") or ""),
                    str(hit.citation.get("title") or ""),
                ]
            )
            for hit in hits
        ]
        topk_hit = bool(expected_chunks) and any(
            _contains_any(text, expected_chunks) for text in text_pool
        )
        if topk_hit:
            topk_hit_count += 1

        cited = [
            hit
            for hit in hits
            if hit.citation.get("chunk_id") and hit.citation.get("title")
        ]
        coverage = (len(cited) / len(hits)) if hits else 0.0
        citation_coverage_sum += coverage

        case_results.append(
            {
                "case": index,
                "query": query,
                "knowledge_base_id": kb_id,
                "topk_hit": topk_hit,
                "citation_coverage": round(coverage, 4),
                "hit_count": len(hits),
            }
        )

    effective_total = len(case_results)
    if effective_total == 0:
        raise ValueError("dataset has no valid cases")

    return {
        "dataset": str(dataset_path),
        "store_path": str(store_path),
        "top_k": top_k,
        "cases": effective_total,
        "topk_hit_rate": round(topk_hit_count / effective_total, 4),
        "citation_coverage": round(citation_coverage_sum / effective_total, 4),
        "results": case_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate local lightweight RAG retrieval"
    )
    parser.add_argument(
        "--store", required=True, help="Path to local hybrid store JSON"
    )
    parser.add_argument("--dataset", required=True, help="Path to JSONL eval dataset")
    parser.add_argument("--top-k", type=int, default=5, help="Top-k retrieval cutoff")
    args = parser.parse_args()

    report = evaluate(
        store_path=Path(args.store).expanduser(),
        dataset_path=Path(args.dataset).expanduser(),
        top_k=max(1, int(args.top_k)),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
