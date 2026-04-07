"""Lightweight hybrid retrieval store (BM25 + hash-vector cosine)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any
from uuid import uuid4


TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+")
REWRITE_HINT_PATTERN = re.compile(
    r"\b(it|this|that|they|them|he|she|former|latter)\b|这(个|些|里|块)|那(个|些|里|块)|它|他|她|前者|后者",
    re.IGNORECASE,
)


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokenize(text: str) -> list[str]:
    return [item.lower() for item in TOKEN_PATTERN.findall(text or "")]


def rewrite_query(
    query: str,
    conversation: list[str] | None = None,
    *,
    max_history_lines: int = 3,
) -> dict[str, Any]:
    """Lightweight query rewrite for follow-up questions.

    The rule keeps standalone questions unchanged and only rewrites
    short/ambiguous follow-ups by prepending concise recent context.
    """

    original_query = str(query or "").strip()
    history = [
        str(line or "").strip()
        for line in (conversation or [])
        if str(line or "").strip()
    ]
    if not original_query or not history:
        return {
            "original_query": original_query,
            "rewritten_query": original_query,
            "rewritten": False,
            "reason": "no_history",
        }

    tokens = _tokenize(original_query)
    has_reference = bool(REWRITE_HINT_PATTERN.search(original_query))
    very_short = len(tokens) <= 4
    should_rewrite = has_reference or very_short
    if not should_rewrite:
        return {
            "original_query": original_query,
            "rewritten_query": original_query,
            "rewritten": False,
            "reason": "standalone",
        }

    context_lines = history[-max(1, int(max_history_lines)) :]
    context = " ".join(context_lines)
    rewritten_query = f"{context} {original_query}".strip()
    return {
        "original_query": original_query,
        "rewritten_query": rewritten_query,
        "rewritten": True,
        "reason": "followup_context_appended",
    }


def _chunk_fixed(normalized: str, *, chunk_size: int, overlap: int) -> list[str]:
    step = max(1, chunk_size - max(0, overlap))
    chunks: list[str] = []
    for start in range(0, len(normalized), step):
        part = normalized[start : start + chunk_size].strip()
        if part:
            chunks.append(part)
    return chunks


def _chunk_by_blocks(blocks: list[str], *, chunk_size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for block in blocks:
        if len(block) >= chunk_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_chunk_fixed(block, chunk_size=chunk_size, overlap=overlap))
            continue

        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = block

    if current:
        chunks.append(current)

    return chunks


def _chunk_by_sentences(normalized: str, *, chunk_size: int, overlap: int) -> list[str]:
    pieces = [
        item.strip()
        for item in re.split(r"(?<=[。！？.!?])\s+|\n+", normalized)
        if item and item.strip()
    ]
    if not pieces:
        pieces = [normalized]
    return _chunk_by_blocks(pieces, chunk_size=chunk_size, overlap=overlap)


def _chunk_text(
    content: str,
    chunk_size: int = 700,
    overlap: int = 120,
    strategy: str = "paragraph",
) -> list[str]:
    normalized = (content or "").strip()
    if not normalized:
        return []

    if strategy == "fixed":
        return _chunk_fixed(normalized, chunk_size=chunk_size, overlap=overlap)
    if strategy == "sentence":
        return _chunk_by_sentences(normalized, chunk_size=chunk_size, overlap=overlap)

    blocks = [
        item.strip()
        for item in re.split(r"\n\s*\n", normalized)
        if item and item.strip()
    ]
    if not blocks:
        blocks = [normalized]
    return _chunk_by_blocks(blocks, chunk_size=chunk_size, overlap=overlap)


def _default_chunk_profile(source_type: str | None) -> dict[str, Any]:
    suffix = str(source_type or "").lower()
    if suffix in {".py", ".ts", ".tsx", ".js", ".json", ".yaml", ".yml"}:
        return {"strategy": "fixed", "chunk_size": 500, "overlap": 80}
    if suffix in {".md", ".txt", ".rst"}:
        return {"strategy": "paragraph", "chunk_size": 700, "overlap": 120}
    return {"strategy": "sentence", "chunk_size": 650, "overlap": 100}


def _resolve_chunk_config(
    *,
    chunk_size: int | None,
    overlap: int | None,
    chunk_strategy: str | None,
    source_type: str | None,
) -> dict[str, Any]:
    profile = _default_chunk_profile(source_type)
    size = int(chunk_size if chunk_size is not None else profile["chunk_size"])
    overlap_value = int(overlap if overlap is not None else profile["overlap"])
    strategy = str(chunk_strategy or profile["strategy"]).lower().strip()

    if size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap_value < 0:
        raise ValueError("overlap must be non-negative")
    if overlap_value >= size:
        raise ValueError("overlap must be smaller than chunk_size")
    if strategy not in {"paragraph", "sentence", "fixed"}:
        raise ValueError("chunk_strategy must be paragraph, sentence, or fixed")

    return {
        "chunk_size": size,
        "overlap": overlap_value,
        "chunk_strategy": strategy,
        "source_type": source_type,
    }


def _tf(tokens: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for token in tokens:
        result[token] = result.get(token, 0) + 1
    return result


def _hash_vector(tokens: list[str], dimension: int = 256) -> list[float]:
    if dimension <= 0:
        raise ValueError("dimension must be positive")
    vector = [0.0] * dimension
    for token in tokens:
        slot = hash(token) % dimension
        vector[slot] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm > 0:
        vector = [value / norm for value in vector]
    return vector


def _cosine(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    return sum(a * b for a, b in zip(vec_a, vec_b))


@dataclass(frozen=True)
class QueryHit:
    """Single retrieval hit returned by hybrid search."""

    chunk_id: str
    document_name: str
    content: str
    metadata: dict[str, Any]
    score: float
    bm25_score: float
    vector_score: float
    citation: dict[str, Any]


@dataclass(frozen=True)
class QuerySummary:
    """Query result envelope."""

    query: str
    knowledge_base_id: str
    hits: tuple[QueryHit, ...]


@dataclass(frozen=True)
class IngestSummary:
    """Ingest result envelope."""

    document_name: str
    knowledge_base_id: str
    chunk_count: int


class HybridSearchStore:
    """Minimal persistent store for hybrid retrieval."""

    def __init__(self, store_path: str | Path) -> None:
        self._store_path = Path(store_path).expanduser().resolve()
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        self._chunks: list[dict[str, Any]] = []
        self._load()

    @property
    def store_path(self) -> Path:
        return self._store_path

    def ingest_text(
        self,
        *,
        document_name: str,
        content: str,
        knowledge_base_id: str = "default",
        metadata: dict[str, Any] | None = None,
        chunk_size: int | None = None,
        overlap: int | None = None,
        chunk_strategy: str | None = None,
        source_type: str | None = None,
        vector_dimension: int = 256,
    ) -> IngestSummary:
        name = str(document_name or "").strip()
        if not name:
            raise ValueError("document_name must not be empty")
        normalized_content = str(content or "").strip()
        if not normalized_content:
            raise ValueError("content must not be empty")

        kb_id = str(knowledge_base_id or "default").strip() or "default"
        chunking = _resolve_chunk_config(
            chunk_size=chunk_size,
            overlap=overlap,
            chunk_strategy=chunk_strategy,
            source_type=source_type,
        )
        payload_meta = dict(metadata or {})
        doc_hash = hashlib.sha1(f"{kb_id}:{name}".encode("utf-8")).hexdigest()[:16]
        payload_meta.setdefault("doc_id", f"doc_{doc_hash}")
        payload_meta.setdefault("source_id", name)
        payload_meta.setdefault("title", name)
        payload_meta.setdefault("document_name", name)
        payload_meta.setdefault("ingested_at", _utc_iso_now())
        payload_meta.setdefault("chunking", chunking)

        chunks = _chunk_text(
            normalized_content,
            chunk_size=chunking["chunk_size"],
            overlap=chunking["overlap"],
            strategy=chunking["chunk_strategy"],
        )
        if not chunks:
            raise ValueError("no chunk can be produced from content")

        created = 0
        for idx, chunk_text in enumerate(chunks):
            tokens = _tokenize(chunk_text)
            if not tokens:
                continue
            item = {
                "chunk_id": f"ch_{uuid4().hex[:16]}",
                "knowledge_base_id": kb_id,
                "document_name": name,
                "chunk_index": idx,
                "content": chunk_text,
                "metadata": dict(payload_meta),
                "tokens": tokens,
                "term_freq": _tf(tokens),
                "token_count": len(tokens),
                "vector": _hash_vector(tokens, dimension=vector_dimension),
                "created_at": _utc_iso_now(),
            }
            self._chunks.append(item)
            created += 1

        self._save()
        return IngestSummary(
            document_name=name, knowledge_base_id=kb_id, chunk_count=created
        )

    def query(
        self,
        *,
        query: str,
        knowledge_base_id: str = "default",
        top_k: int = 5,
        rrf_k: int = 60,
        max_candidates: int | None = None,
        bm25_k1: float = 1.2,
        bm25_b: float = 0.75,
    ) -> QuerySummary:
        query_text = str(query or "").strip()
        if not query_text:
            raise ValueError("query must not be empty")
        kb_id = str(knowledge_base_id or "default").strip() or "default"

        candidates = [
            item for item in self._chunks if item.get("knowledge_base_id") == kb_id
        ]
        if not candidates:
            return QuerySummary(query=query_text, knowledge_base_id=kb_id, hits=())

        query_tokens = _tokenize(query_text)
        if not query_tokens:
            return QuerySummary(query=query_text, knowledge_base_id=kb_id, hits=())

        candidates = self._cap_candidates(
            candidates=candidates,
            query_tokens=query_tokens,
            max_candidates=max_candidates,
        )

        score_details = self._score_candidates(
            candidates=candidates,
            query_tokens=query_tokens,
            rrf_k=rrf_k,
            bm25_k1=bm25_k1,
            bm25_b=bm25_b,
        )
        top = score_details["fused"][: max(1, int(top_k))]
        hits = tuple(
            QueryHit(
                chunk_id=item["chunk_id"],
                document_name=item["document_name"],
                content=item["content"],
                metadata=dict(item.get("metadata", {})),
                score=float(score),
                bm25_score=float(
                    score_details["bm25_scores"].get(item["chunk_id"], 0.0)
                ),
                vector_score=float(
                    score_details["vector_scores"].get(item["chunk_id"], 0.0)
                ),
                citation=self._build_citation(item),
            )
            for score, item in top
        )
        return QuerySummary(query=query_text, knowledge_base_id=kb_id, hits=hits)

    def query_debug(
        self,
        *,
        query: str,
        knowledge_base_id: str = "default",
        top_k: int = 5,
        debug_k: int = 20,
        rrf_k: int = 60,
        max_candidates: int | None = None,
        bm25_k1: float = 1.2,
        bm25_b: float = 0.75,
    ) -> dict[str, Any]:
        query_text = str(query or "").strip()
        if not query_text:
            raise ValueError("query must not be empty")
        kb_id = str(knowledge_base_id or "default").strip() or "default"

        candidates = [
            item for item in self._chunks if item.get("knowledge_base_id") == kb_id
        ]
        if not candidates:
            return {
                "query": query_text,
                "knowledge_base_id": kb_id,
                "top_k": top_k,
                "rrf_k": rrf_k,
                "bm25_ranking": [],
                "vector_ranking": [],
                "fused_ranking": [],
            }

        query_tokens = _tokenize(query_text)
        if not query_tokens:
            return {
                "query": query_text,
                "knowledge_base_id": kb_id,
                "top_k": top_k,
                "rrf_k": rrf_k,
                "bm25_ranking": [],
                "vector_ranking": [],
                "fused_ranking": [],
            }

        candidates = self._cap_candidates(
            candidates=candidates,
            query_tokens=query_tokens,
            max_candidates=max_candidates,
        )

        score_details = self._score_candidates(
            candidates=candidates,
            query_tokens=query_tokens,
            rrf_k=rrf_k,
            bm25_k1=bm25_k1,
            bm25_b=bm25_b,
        )

        bm25_rank_lookup = score_details["bm25_rank_lookup"]
        vector_rank_lookup = score_details["vector_rank_lookup"]

        def _item_payload(
            item: dict[str, Any], rrf_score: float | None = None
        ) -> dict[str, Any]:
            chunk_id = item["chunk_id"]
            payload = {
                "chunk_id": chunk_id,
                "document_name": item["document_name"],
                "bm25_rank": bm25_rank_lookup[chunk_id],
                "vector_rank": vector_rank_lookup[chunk_id],
                "bm25_score": float(score_details["bm25_scores"].get(chunk_id, 0.0)),
                "vector_score": float(
                    score_details["vector_scores"].get(chunk_id, 0.0)
                ),
                "citation": self._build_citation(item),
            }
            if rrf_score is not None:
                payload["rrf_score"] = float(rrf_score)
            return payload

        debug_limit = max(1, int(debug_k))
        fused_limit = max(debug_limit, int(top_k))

        bm25_payload = [
            _item_payload(item) for item in score_details["bm25_rank"][:debug_limit]
        ]
        vector_payload = [
            _item_payload(item) for item in score_details["vector_rank"][:debug_limit]
        ]
        fused_payload = [
            _item_payload(item, rrf_score=score)
            for score, item in score_details["fused"][:fused_limit]
        ]

        for rank, item in enumerate(fused_payload, start=1):
            item["final_rank"] = rank

        return {
            "query": query_text,
            "knowledge_base_id": kb_id,
            "top_k": int(top_k),
            "rrf_k": int(rrf_k),
            "bm25_ranking": bm25_payload,
            "vector_ranking": vector_payload,
            "fused_ranking": fused_payload,
        }

    def stats(self, knowledge_base_id: str | None = None) -> dict[str, Any]:
        kb_id = str(knowledge_base_id).strip() if knowledge_base_id else None
        source = (
            self._chunks
            if not kb_id
            else [
                item for item in self._chunks if item.get("knowledge_base_id") == kb_id
            ]
        )
        documents = {
            f"{item.get('knowledge_base_id')}::{item.get('document_name')}"
            for item in source
        }
        return {
            "knowledge_base_id": kb_id,
            "chunk_count": len(source),
            "document_count": len(documents),
            "store_path": str(self._store_path),
        }

    def rebuild(
        self,
        *,
        knowledge_base_id: str | None = None,
        vector_dimension: int = 256,
    ) -> dict[str, Any]:
        kb_id = str(knowledge_base_id).strip() if knowledge_base_id else None
        touched = 0
        documents: set[str] = set()
        for item in self._chunks:
            if kb_id and item.get("knowledge_base_id") != kb_id:
                continue
            content = str(item.get("content") or "")
            tokens = _tokenize(content)
            item["tokens"] = tokens
            item["term_freq"] = _tf(tokens)
            item["token_count"] = len(tokens)
            item["vector"] = _hash_vector(tokens, dimension=vector_dimension)
            item["rebuilt_at"] = _utc_iso_now()
            touched += 1
            documents.add(
                f"{item.get('knowledge_base_id', 'default')}::{item.get('document_name', '')}"
            )

        self._save()
        return {
            "knowledge_base_id": kb_id,
            "affected_chunks": touched,
            "affected_documents": len(documents),
        }

    def cleanup(self, *, knowledge_base_id: str | None = None) -> dict[str, Any]:
        kb_id = str(knowledge_base_id).strip() if knowledge_base_id else None
        before = len(self._chunks)
        before_docs = {
            f"{item.get('knowledge_base_id', 'default')}::{item.get('document_name', '')}"
            for item in self._chunks
            if not kb_id or item.get("knowledge_base_id") == kb_id
        }

        if kb_id:
            self._chunks = [
                item for item in self._chunks if item.get("knowledge_base_id") != kb_id
            ]
        else:
            self._chunks = []

        removed_chunks = before - len(self._chunks)
        self._save()
        return {
            "knowledge_base_id": kb_id,
            "removed_chunks": removed_chunks,
            "removed_documents": len(before_docs),
        }

    def _load(self) -> None:
        if not self._store_path.exists():
            self._chunks = []
            return
        try:
            payload = json.loads(self._store_path.read_text(encoding="utf-8"))
        except Exception:
            self._chunks = []
            return
        chunks = payload.get("chunks", []) if isinstance(payload, dict) else []
        self._chunks = [item for item in chunks if isinstance(item, dict)]

    def _save(self) -> None:
        payload = {
            "updated_at": _utc_iso_now(),
            "chunks": self._chunks,
        }
        self._store_path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def _cap_candidates(
        self,
        *,
        candidates: list[dict[str, Any]],
        query_tokens: list[str],
        max_candidates: int | None,
    ) -> list[dict[str, Any]]:
        if max_candidates is None:
            return candidates
        limit = max(1, int(max_candidates))
        if len(candidates) <= limit:
            return candidates

        query_token_set = set(query_tokens)

        def _priority(item: dict[str, Any]) -> tuple[int, int]:
            token_set = set(item.get("tokens", []))
            overlap = len(token_set & query_token_set)
            token_count = int(item.get("token_count", 0) or 0)
            return (overlap, token_count)

        ranked = sorted(candidates, key=_priority, reverse=True)
        return ranked[:limit]

    def _build_citation(self, item: dict[str, Any]) -> dict[str, Any]:
        metadata = item.get("metadata", {})
        page = metadata.get("page")
        if page is None:
            page = metadata.get("page_number")
        span = metadata.get("span")
        if not isinstance(span, dict):
            span = {
                "chunk_index": item.get("chunk_index"),
                "char_start": None,
                "char_end": None,
            }
        return {
            "source_id": metadata.get("source_id") or item.get("document_name"),
            "chunk_id": item.get("chunk_id"),
            "doc_id": metadata.get("doc_id"),
            "title": metadata.get("title") or item.get("document_name"),
            "source_path": metadata.get("source_path"),
            "url": metadata.get("url") or metadata.get("source_url"),
            "page": page,
            "span": span,
        }

    def _score_candidates(
        self,
        *,
        candidates: list[dict[str, Any]],
        query_tokens: list[str],
        rrf_k: int,
        bm25_k1: float,
        bm25_b: float,
    ) -> dict[str, Any]:
        avg_len = sum(item.get("token_count", 0) for item in candidates) / max(
            1, len(candidates)
        )
        doc_freq: dict[str, int] = {}
        for item in candidates:
            unique_tokens = set(item.get("term_freq", {}).keys())
            for token in unique_tokens:
                doc_freq[token] = doc_freq.get(token, 0) + 1

        bm25_scores: dict[str, float] = {}
        total_docs = len(candidates)
        for item in candidates:
            term_freq = item.get("term_freq", {})
            doc_len = float(item.get("token_count", 0) or 0)
            score = 0.0
            for token in query_tokens:
                freq = float(term_freq.get(token, 0) or 0)
                if freq <= 0:
                    continue
                df = float(doc_freq.get(token, 0) or 0)
                idf = math.log(1 + ((total_docs - df + 0.5) / (df + 0.5)))
                denom = freq + bm25_k1 * (
                    1 - bm25_b + bm25_b * (doc_len / max(1.0, avg_len))
                )
                score += idf * ((freq * (bm25_k1 + 1)) / max(1e-9, denom))
            bm25_scores[item["chunk_id"]] = score

        query_vec = _hash_vector(query_tokens)
        vector_scores = {
            item["chunk_id"]: _cosine(item.get("vector", []), query_vec)
            for item in candidates
        }

        bm25_rank = sorted(
            candidates, key=lambda x: bm25_scores.get(x["chunk_id"], 0.0), reverse=True
        )
        vector_rank = sorted(
            candidates,
            key=lambda x: vector_scores.get(x["chunk_id"], 0.0),
            reverse=True,
        )

        bm25_rank_lookup = {
            item["chunk_id"]: idx + 1 for idx, item in enumerate(bm25_rank)
        }
        vector_rank_lookup = {
            item["chunk_id"]: idx + 1 for idx, item in enumerate(vector_rank)
        }

        scored: list[tuple[float, dict[str, Any]]] = []
        for item in candidates:
            chunk_id = item["chunk_id"]
            rrf_score = (1.0 / (rrf_k + bm25_rank_lookup[chunk_id])) + (
                1.0 / (rrf_k + vector_rank_lookup[chunk_id])
            )
            scored.append((rrf_score, item))

        return {
            "bm25_scores": bm25_scores,
            "vector_scores": vector_scores,
            "bm25_rank": bm25_rank,
            "vector_rank": vector_rank,
            "bm25_rank_lookup": bm25_rank_lookup,
            "vector_rank_lookup": vector_rank_lookup,
            "fused": sorted(scored, key=lambda x: x[0], reverse=True),
        }
