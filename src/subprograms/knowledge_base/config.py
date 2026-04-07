"""Runtime configuration for knowledge-base lightweight RAG."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
from typing import Any


def _env_int(name: str, default: int, *, min_value: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        value = int(default)
    else:
        value = int(str(raw).strip())
    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be >= {min_value}")
    return value


@dataclass(frozen=True)
class KnowledgeBaseSettings:
    """Settings for knowledge-base router and store defaults."""

    store_path: Path
    query_top_k_default: int
    query_top_k_max: int
    query_debug_k_default: int
    query_debug_k_max: int
    query_rrf_k: int
    query_max_candidates: int
    ingest_chunk_size: int
    ingest_chunk_overlap: int
    ingest_chunk_strategy: str
    ingest_max_content_chars: int
    ingest_job_max_retries: int
    ingest_job_max_records: int

    @classmethod
    def from_env(cls) -> "KnowledgeBaseSettings":
        store_path = Path(
            os.getenv(
                "MINI_AGENT_RAG_STORE_PATH",
                "workspace/rag/light_hybrid_store.json",
            )
        ).expanduser()
        top_k_default = _env_int("MINI_AGENT_RAG_TOP_K_DEFAULT", 5, min_value=1)
        top_k_max = _env_int("MINI_AGENT_RAG_TOP_K_MAX", 20, min_value=1)
        debug_default = _env_int("MINI_AGENT_RAG_DEBUG_K_DEFAULT", 20, min_value=1)
        debug_max = _env_int("MINI_AGENT_RAG_DEBUG_K_MAX", 100, min_value=1)
        query_rrf_k = _env_int("MINI_AGENT_RAG_RRF_K", 60, min_value=1)
        max_candidates = _env_int("MINI_AGENT_RAG_MAX_CANDIDATES", 1200, min_value=1)
        chunk_size = _env_int("MINI_AGENT_RAG_CHUNK_SIZE", 700, min_value=1)
        chunk_overlap = _env_int("MINI_AGENT_RAG_CHUNK_OVERLAP", 120, min_value=0)
        ingest_max_chars = _env_int(
            "MINI_AGENT_RAG_INGEST_MAX_CHARS", 250000, min_value=1
        )
        job_max_retries = _env_int(
            "MINI_AGENT_RAG_INGEST_JOB_MAX_RETRIES", 1, min_value=0
        )
        job_max_records = _env_int(
            "MINI_AGENT_RAG_INGEST_JOB_MAX_RECORDS", 500, min_value=1
        )
        chunk_strategy = (
            os.getenv("MINI_AGENT_RAG_CHUNK_STRATEGY", "paragraph").strip().lower()
        )

        if top_k_default > top_k_max:
            raise ValueError("MINI_AGENT_RAG_TOP_K_DEFAULT must be <= TOP_K_MAX")
        if debug_default > debug_max:
            raise ValueError("MINI_AGENT_RAG_DEBUG_K_DEFAULT must be <= DEBUG_K_MAX")
        if chunk_overlap >= chunk_size:
            raise ValueError(
                "MINI_AGENT_RAG_CHUNK_OVERLAP must be smaller than CHUNK_SIZE"
            )
        if chunk_strategy not in {"paragraph", "sentence", "fixed"}:
            raise ValueError(
                "MINI_AGENT_RAG_CHUNK_STRATEGY must be paragraph, sentence, or fixed"
            )

        return cls(
            store_path=store_path,
            query_top_k_default=top_k_default,
            query_top_k_max=top_k_max,
            query_debug_k_default=debug_default,
            query_debug_k_max=debug_max,
            query_rrf_k=query_rrf_k,
            query_max_candidates=max_candidates,
            ingest_chunk_size=chunk_size,
            ingest_chunk_overlap=chunk_overlap,
            ingest_chunk_strategy=chunk_strategy,
            ingest_max_content_chars=ingest_max_chars,
            ingest_job_max_retries=job_max_retries,
            ingest_job_max_records=job_max_records,
        )

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["store_path"] = str(self.store_path)
        return payload
