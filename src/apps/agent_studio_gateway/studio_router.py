"""Lean Studio ops router for provider and memory management contracts."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from mini_agent.application import StudioOpsUseCases
from mini_agent.interfaces import (
    StudioMemoryDailyResponse,
    StudioMemorySearchResponse,
    StudioMemorySummaryResponse,
    StudioProviderDeleteResponse,
    StudioProviderHealthResponse,
    StudioProviderListResponse,
    StudioProviderSummary,
    StudioProviderUpsertRequest,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT / "workspace"
_STUDIO_OPS_USE_CASES = StudioOpsUseCases(repo_root=REPO_ROOT, workspace_root=WORKSPACE_ROOT)


def _load_studio_api_keys() -> set[str]:
    raw = os.getenv("MINI_AGENT_STUDIO_API_KEYS", "")
    return {item.strip() for item in raw.split(",") if item and item.strip()}


def _extract_auth_token(authorization: str | None, x_api_key: str | None) -> str:
    if authorization:
        lower = authorization.lower()
        if lower.startswith("bearer "):
            token = authorization[7:].strip()
            if token:
                return token
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    return ""


async def _require_studio_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    allowed = _load_studio_api_keys()
    if not allowed:
        return
    token = _extract_auth_token(authorization, x_api_key)
    if token in allowed:
        return
    raise HTTPException(status_code=401, detail="Unauthorized. Provide valid Studio API token.")


router = APIRouter(
    prefix="/api/v1/ops",
    tags=["Ops"],
    dependencies=[Depends(_require_studio_auth)],
)


@router.get("/providers", response_model=StudioProviderListResponse)
async def list_studio_providers(catalog_path: str | None = Query(None)) -> StudioProviderListResponse:
    return _STUDIO_OPS_USE_CASES.list_providers(catalog_path)


@router.post("/providers", response_model=StudioProviderSummary)
async def create_studio_provider(
    payload: StudioProviderUpsertRequest,
    catalog_path: str | None = Query(None),
) -> StudioProviderSummary:
    return _STUDIO_OPS_USE_CASES.create_provider(payload=payload, catalog_path=catalog_path)


@router.put("/providers/{provider_id}", response_model=StudioProviderSummary)
async def update_studio_provider(
    provider_id: str,
    payload: StudioProviderUpsertRequest,
    catalog_path: str | None = Query(None),
) -> StudioProviderSummary:
    return _STUDIO_OPS_USE_CASES.update_provider(
        provider_id=provider_id,
        payload=payload,
        catalog_path=catalog_path,
    )


@router.delete("/providers/{provider_id}", response_model=StudioProviderDeleteResponse)
async def delete_studio_provider(
    provider_id: str,
    catalog_path: str | None = Query(None),
) -> StudioProviderDeleteResponse:
    return _STUDIO_OPS_USE_CASES.delete_provider(provider_id=provider_id, catalog_path=catalog_path)


@router.get("/providers/{provider_id}/health", response_model=StudioProviderHealthResponse)
async def get_studio_provider_health(
    provider_id: str,
    catalog_path: str | None = Query(None),
) -> StudioProviderHealthResponse:
    return _STUDIO_OPS_USE_CASES.get_provider_health(provider_id=provider_id, catalog_path=catalog_path)


@router.get("/memory/summary", response_model=StudioMemorySummaryResponse)
async def studio_memory_summary(workspace_dir: str | None = Query(None)) -> StudioMemorySummaryResponse:
    return _STUDIO_OPS_USE_CASES.get_memory_summary(workspace_dir=workspace_dir)


@router.get("/memory/search", response_model=StudioMemorySearchResponse)
async def studio_memory_search(
    query: str = Query(default="", min_length=0),
    limit: int = Query(default=20, ge=1, le=200),
    workspace_dir: str | None = Query(None),
) -> StudioMemorySearchResponse:
    return _STUDIO_OPS_USE_CASES.search_memory(query=query, limit=limit, workspace_dir=workspace_dir)


@router.get("/memory/daily/{day}", response_model=StudioMemoryDailyResponse)
async def studio_memory_daily(
    day: str,
    workspace_dir: str | None = Query(None),
) -> StudioMemoryDailyResponse:
    return _STUDIO_OPS_USE_CASES.get_memory_daily(day=day, workspace_dir=workspace_dir)
