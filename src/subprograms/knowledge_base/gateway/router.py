"""Knowledge-base API router (lightweight hybrid RAG baseline)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from time import perf_counter

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mini_agent.rag.lightweight_hybrid import HybridSearchStore, rewrite_query
from mini_agent.model_manager.feature_runtime import FeatureModelRuntime
from subprograms.knowledge_base.config import KnowledgeBaseSettings
from subprograms.knowledge_base.ingest_jobs import IngestJobQueue
from mini_agent.tools.docling_parse import DoclingParser


router = APIRouter(prefix="/api/knowledge-base", tags=["Knowledge Base"])

_SETTINGS = KnowledgeBaseSettings.from_env()
_STORE = HybridSearchStore(_SETTINGS.store_path)
_PARSER = DoclingParser()
_JOBS = IngestJobQueue(max_jobs=_SETTINGS.ingest_job_max_records)


def _configure_runtime_store() -> HybridSearchStore:
    try:
        embedding_provider = FeatureModelRuntime().get_embedding_provider()
    except Exception:
        embedding_provider = None
    _STORE.set_embedding_provider(embedding_provider)
    return _STORE


def _configure_runtime_parser() -> DoclingParser:
    try:
        ocr_adapter = FeatureModelRuntime().get_docling_ocr_adapter()
    except Exception:
        ocr_adapter = None
    _PARSER.set_ocr_adapter(ocr_adapter)
    return _PARSER


class QueryRequest(BaseModel):
    """Knowledge query request."""

    query: str = Field(min_length=1)
    knowledge_base_id: str | None = None
    top_k: int = Field(
        default=_SETTINGS.query_top_k_default, ge=1, le=_SETTINGS.query_top_k_max
    )
    conversation: list[str] | None = None
    enable_query_rewrite: bool = True


class QueryDebugRequest(BaseModel):
    """Knowledge query debug request."""

    query: str = Field(min_length=1)
    knowledge_base_id: str | None = None
    top_k: int = Field(
        default=_SETTINGS.query_top_k_default, ge=1, le=_SETTINGS.query_top_k_max
    )
    debug_k: int = Field(
        default=_SETTINGS.query_debug_k_default, ge=1, le=_SETTINGS.query_debug_k_max
    )
    conversation: list[str] | None = None
    enable_query_rewrite: bool = True


class ChunkConfig(BaseModel):
    """Chunking strategy for ingestion."""

    strategy: str | None = Field(default=_SETTINGS.ingest_chunk_strategy)
    chunk_size: int | None = Field(default=_SETTINGS.ingest_chunk_size, ge=1, le=4096)
    overlap: int | None = Field(default=_SETTINGS.ingest_chunk_overlap, ge=0, le=2048)


class MaintenanceRequest(BaseModel):
    """Maintenance request for rebuild/cleanup operations."""

    knowledge_base_id: str | None = None


def _ingest_text_impl(request: IngestTextRequest) -> dict[str, Any]:
    if len(request.content) > _SETTINGS.ingest_max_content_chars:
        raise ValueError(
            f"content too large: {len(request.content)} chars, limit={_SETTINGS.ingest_max_content_chars}"
        )
    chunking = request.chunking or ChunkConfig()
    store = _configure_runtime_store()
    result = store.ingest_text(
        document_name=request.document_name,
        content=request.content,
        knowledge_base_id=request.knowledge_base_id,
        metadata=request.metadata,
        chunk_size=chunking.chunk_size,
        overlap=chunking.overlap,
        chunk_strategy=chunking.strategy,
    )
    return {
        "document_name": result.document_name,
        "knowledge_base_id": result.knowledge_base_id,
        "chunk_count": result.chunk_count,
    }


def _ingest_file_impl(request: IngestFileRequest) -> dict[str, Any]:
    parser = _configure_runtime_parser()
    parsed = parser.parse_file(
        path=request.path,
        output_format=request.output_format,
        enable_ocr=request.enable_ocr,
    )
    if len(parsed.content) > _SETTINGS.ingest_max_content_chars:
        raise ValueError(
            f"content too large: {len(parsed.content)} chars, limit={_SETTINGS.ingest_max_content_chars}"
        )
    resolved_name = request.document_name or Path(parsed.source_path).name
    source_suffix = Path(parsed.source_path).suffix
    chunking = request.chunking or ChunkConfig()
    store = _configure_runtime_store()
    result = store.ingest_text(
        document_name=resolved_name,
        content=parsed.content,
        knowledge_base_id=request.knowledge_base_id,
        source_type=source_suffix,
        chunk_size=chunking.chunk_size,
        overlap=chunking.overlap,
        chunk_strategy=chunking.strategy,
        metadata={
            **(request.metadata or {}),
            "source_path": parsed.source_path,
            "output_format": parsed.output_format,
            "used_docling": parsed.used_docling,
        },
    )
    return {
        "document_name": result.document_name,
        "knowledge_base_id": result.knowledge_base_id,
        "chunk_count": result.chunk_count,
        "source_path": parsed.source_path,
        "used_docling": parsed.used_docling,
    }


def _run_job(job_id: str) -> dict[str, Any]:
    job = _JOBS.get_job(job_id)
    if job is None:
        raise KeyError(f"job not found: {job_id}")

    def _runner() -> dict[str, Any]:
        if job.kind == "text":
            return _ingest_text_impl(IngestTextRequest.model_validate(job.payload))
        if job.kind == "file":
            return _ingest_file_impl(IngestFileRequest.model_validate(job.payload))
        raise ValueError(f"unknown ingest job kind: {job.kind}")

    done = _JOBS.run_job(job_id=job_id, runner=_runner)
    return done.to_dict()


class IngestTextRequest(BaseModel):
    """Knowledge ingest request from raw content."""

    document_name: str = Field(min_length=1)
    content: str = Field(min_length=1)
    knowledge_base_id: str | None = None
    metadata: dict[str, Any] | None = None
    chunking: ChunkConfig | None = None


class IngestFileRequest(BaseModel):
    """Knowledge ingest request from local file path."""

    path: str = Field(min_length=1)
    document_name: str | None = None
    output_format: str = Field(default="markdown")
    enable_ocr: bool = False
    knowledge_base_id: str | None = None
    metadata: dict[str, Any] | None = None
    chunking: ChunkConfig | None = None


class IngestJobRequest(BaseModel):
    """Async ingest job request."""

    mode: str = Field(default="text")
    text: IngestTextRequest | None = None
    file: IngestFileRequest | None = None
    process_now: bool = True


@router.post("/query")
async def query_knowledge(request: QueryRequest) -> dict[str, Any]:
    try:
        rewrite_info = rewrite_query(request.query, request.conversation)
        query_text = (
            rewrite_info["rewritten_query"]
            if request.enable_query_rewrite
            else request.query
        )
        store = _configure_runtime_store()
        result = store.query(
            query=query_text,
            knowledge_base_id=request.knowledge_base_id,
            top_k=request.top_k,
            rrf_k=_SETTINGS.query_rrf_k,
            max_candidates=_SETTINGS.query_max_candidates,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"{type(exc).__name__}: {exc}"
        ) from exc

    return {
        "status": "ok",
        "query": result.query,
        "original_query": request.query,
        "query_rewrite": {
            **rewrite_info,
            "rewritten": bool(
                request.enable_query_rewrite and rewrite_info["rewritten"]
            ),
            "rewritten_query": query_text,
        },
        "knowledge_base_id": result.knowledge_base_id,
        "hits": [
            {
                "chunk_id": hit.chunk_id,
                "document_name": hit.document_name,
                "content": hit.content,
                "metadata": hit.metadata,
                "score": hit.score,
                "bm25_score": hit.bm25_score,
                "vector_score": hit.vector_score,
                "citation": hit.citation,
            }
            for hit in result.hits
        ],
    }


@router.post("/query/debug")
async def query_knowledge_debug(request: QueryDebugRequest) -> dict[str, Any]:
    try:
        rewrite_info = rewrite_query(request.query, request.conversation)
        query_text = (
            rewrite_info["rewritten_query"]
            if request.enable_query_rewrite
            else request.query
        )
        store = _configure_runtime_store()
        result = store.query_debug(
            query=query_text,
            knowledge_base_id=request.knowledge_base_id,
            top_k=request.top_k,
            debug_k=request.debug_k,
            rrf_k=_SETTINGS.query_rrf_k,
            max_candidates=_SETTINGS.query_max_candidates,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"{type(exc).__name__}: {exc}"
        ) from exc

    return {
        "status": "ok",
        "original_query": request.query,
        "query_rewrite": {
            **rewrite_info,
            "rewritten": bool(
                request.enable_query_rewrite and rewrite_info["rewritten"]
            ),
            "rewritten_query": query_text,
        },
        **result,
    }


@router.post("/ingest")
async def ingest_document(request: IngestTextRequest) -> dict[str, Any]:
    try:
        payload = _ingest_text_impl(request)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"{type(exc).__name__}: {exc}"
        ) from exc

    return {"status": "ok", **payload}


@router.post("/ingest/file")
async def ingest_document_file(request: IngestFileRequest) -> dict[str, Any]:
    try:
        payload = _ingest_file_impl(request)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"{type(exc).__name__}: {exc}"
        ) from exc

    return {"status": "ok", **payload}


@router.post("/ingest/jobs")
async def create_ingest_job(request: IngestJobRequest) -> dict[str, Any]:
    mode = str(request.mode or "").strip().lower()
    try:
        if mode == "text":
            if request.text is None:
                raise ValueError("text payload is required when mode=text")
            payload = request.text.model_dump()
        elif mode == "file":
            if request.file is None:
                raise ValueError("file payload is required when mode=file")
            payload = request.file.model_dump()
        else:
            raise ValueError("mode must be text or file")

        job = _JOBS.create_job(
            kind=mode,
            payload=payload,
            max_retries=_SETTINGS.ingest_job_max_retries,
        )
        if request.process_now:
            done = _run_job(job.job_id)
            return {"status": "ok", "job": done}
        return {"status": "ok", "job": job.to_dict()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"{type(exc).__name__}: {exc}"
        ) from exc


@router.get("/ingest/jobs/{job_id}")
async def get_ingest_job(job_id: str) -> dict[str, Any]:
    job = _JOBS.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return {"status": "ok", "job": job.to_dict()}


@router.post("/ingest/jobs/{job_id}/run")
async def run_ingest_job(job_id: str) -> dict[str, Any]:
    try:
        return {"status": "ok", "job": _run_job(job_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"{type(exc).__name__}: {exc}"
        ) from exc


@router.post("/ingest/jobs/{job_id}/retry")
async def retry_ingest_job(job_id: str) -> dict[str, Any]:
    job = _JOBS.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")

    def _runner() -> dict[str, Any]:
        current = _JOBS.get_job(job_id)
        if current is None:
            raise KeyError(f"job not found: {job_id}")
        if current.kind == "text":
            return _ingest_text_impl(IngestTextRequest.model_validate(current.payload))
        if current.kind == "file":
            return _ingest_file_impl(IngestFileRequest.model_validate(current.payload))
        raise ValueError(f"unknown ingest job kind: {current.kind}")

    try:
        done = _JOBS.retry_failed_job(job_id=job_id, runner=_runner)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"{type(exc).__name__}: {exc}"
        ) from exc
    return {"status": "ok", "job": done.to_dict()}


@router.get("/ingest/jobs")
async def ingest_jobs_summary() -> dict[str, Any]:
    return {"status": "ok", **_JOBS.summary()}


@router.get("/config")
async def config() -> dict[str, Any]:
    return {"status": "ok", **_SETTINGS.as_dict()}


@router.post("/admin/rebuild")
async def rebuild_index(request: MaintenanceRequest) -> dict[str, Any]:
    start = perf_counter()
    try:
        stats = _configure_runtime_store().rebuild(knowledge_base_id=request.knowledge_base_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"{type(exc).__name__}: {exc}"
        ) from exc

    elapsed_ms = int((perf_counter() - start) * 1000)
    return {"status": "ok", "duration_ms": elapsed_ms, **stats}


@router.delete("/admin/cleanup")
async def cleanup_index(request: MaintenanceRequest) -> dict[str, Any]:
    start = perf_counter()
    try:
        stats = _configure_runtime_store().cleanup(knowledge_base_id=request.knowledge_base_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"{type(exc).__name__}: {exc}"
        ) from exc

    elapsed_ms = int((perf_counter() - start) * 1000)
    return {"status": "ok", "duration_ms": elapsed_ms, **stats}


@router.get("/stats")
async def stats(knowledge_base_id: str | None = None) -> dict[str, Any]:
    return {"status": "ok", **_configure_runtime_store().stats(knowledge_base_id=knowledge_base_id)}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "knowledge-base"}
