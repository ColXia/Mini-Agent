"""Ops HTTP transport router for provider and memory management contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, Depends, Query

from mini_agent.application.operations_memory_use_cases import MemoryOperationsUseCases
from mini_agent.application.operations_provider_use_cases import ProviderOperationsUseCases
from mini_agent.interfaces import (
    StudioModelDiscoverRequest,
    StudioModelListResponse,
    StudioModelProviderSummary,
    StudioModelSelectionRequest,
    StudioMemoryDailyResponse,
    StudioMemorySearchResponse,
    StudioMemorySummaryResponse,
    StudioProviderDeleteResponse,
    StudioProviderHealthResponse,
    StudioProviderListResponse,
    StudioProviderModelDiscoveryRequest,
    StudioProviderModelDiscoveryResponse,
    StudioProviderSummary,
    StudioProviderUpsertRequest,
)


@dataclass(frozen=True, slots=True)
class OpsRouterDependencies:
    get_memory_operations_use_cases: Callable[[], MemoryOperationsUseCases]
    get_provider_operations_use_cases: Callable[[], ProviderOperationsUseCases]
    require_ops_auth: Callable[..., Any]


def create_ops_router(deps: OpsRouterDependencies) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/ops",
        tags=["Ops"],
        dependencies=[Depends(deps.require_ops_auth)],
    )

    @router.get("/providers", response_model=StudioProviderListResponse)
    async def list_ops_providers(catalog_path: str | None = Query(None)) -> StudioProviderListResponse:
        return deps.get_provider_operations_use_cases().list_providers(catalog_path)

    @router.get("/models", response_model=StudioModelListResponse)
    async def list_ops_models(catalog_path: str | None = Query(None)) -> StudioModelListResponse:
        return deps.get_provider_operations_use_cases().list_models(catalog_path=catalog_path)

    @router.post("/models/discover", response_model=StudioModelProviderSummary)
    async def discover_ops_models(
        payload: StudioModelDiscoverRequest,
        catalog_path: str | None = Query(None),
    ) -> StudioModelProviderSummary:
        return deps.get_provider_operations_use_cases().discover_models(
            payload=payload,
            catalog_path=catalog_path,
        )

    @router.patch("/models/selection", response_model=StudioModelProviderSummary)
    async def select_ops_model(
        payload: StudioModelSelectionRequest,
        catalog_path: str | None = Query(None),
    ) -> StudioModelProviderSummary:
        return deps.get_provider_operations_use_cases().select_model(
            payload=payload,
            catalog_path=catalog_path,
        )

    @router.post("/providers/model-discovery", response_model=StudioProviderModelDiscoveryResponse)
    async def discover_provider_models_for_setup(
        payload: StudioProviderModelDiscoveryRequest,
    ) -> StudioProviderModelDiscoveryResponse:
        return deps.get_provider_operations_use_cases().discover_provider_models(payload=payload)

    @router.post("/providers", response_model=StudioProviderSummary)
    async def create_ops_provider(
        payload: StudioProviderUpsertRequest,
        catalog_path: str | None = Query(None),
    ) -> StudioProviderSummary:
        return deps.get_provider_operations_use_cases().create_provider(
            payload=payload,
            catalog_path=catalog_path,
        )

    @router.put("/providers/{provider_id}", response_model=StudioProviderSummary)
    async def update_ops_provider(
        provider_id: str,
        payload: StudioProviderUpsertRequest,
        catalog_path: str | None = Query(None),
    ) -> StudioProviderSummary:
        return deps.get_provider_operations_use_cases().update_provider(
            provider_id=provider_id,
            payload=payload,
            catalog_path=catalog_path,
        )

    @router.delete("/providers/{provider_id}", response_model=StudioProviderDeleteResponse)
    async def delete_ops_provider(
        provider_id: str,
        catalog_path: str | None = Query(None),
    ) -> StudioProviderDeleteResponse:
        return deps.get_provider_operations_use_cases().delete_provider(
            provider_id=provider_id,
            catalog_path=catalog_path,
        )

    @router.get("/providers/{provider_id}/health", response_model=StudioProviderHealthResponse)
    async def get_ops_provider_health(
        provider_id: str,
        catalog_path: str | None = Query(None),
    ) -> StudioProviderHealthResponse:
        return deps.get_provider_operations_use_cases().get_provider_health(
            provider_id=provider_id,
            catalog_path=catalog_path,
        )

    @router.get("/memory/summary", response_model=StudioMemorySummaryResponse)
    async def ops_memory_summary(workspace_dir: str | None = Query(None)) -> StudioMemorySummaryResponse:
        return deps.get_memory_operations_use_cases().get_memory_summary(workspace_dir=workspace_dir)

    @router.get("/memory/search", response_model=StudioMemorySearchResponse)
    async def ops_memory_search(
        query: str = Query(default="", min_length=0),
        limit: int = Query(default=20, ge=1, le=200),
        workspace_dir: str | None = Query(None),
    ) -> StudioMemorySearchResponse:
        return deps.get_memory_operations_use_cases().search_memory(
            query=query,
            limit=limit,
            workspace_dir=workspace_dir,
        )

    @router.get("/memory/daily/{day}", response_model=StudioMemoryDailyResponse)
    async def ops_memory_daily(
        day: str,
        workspace_dir: str | None = Query(None),
    ) -> StudioMemoryDailyResponse:
        return deps.get_memory_operations_use_cases().get_memory_daily(
            day=day,
            workspace_dir=workspace_dir,
        )

    return router
