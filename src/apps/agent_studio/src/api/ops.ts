import type {
  StudioMemoryDailyResponse,
  StudioMemorySearchResponse,
  StudioMemorySummary,
  StudioRuntimeDiagnostics,
  StudioModelListResponse,
  StudioModelProviderSummary,
  StudioProviderModelDiscoveryPayload,
  StudioProviderModelDiscoveryResponse,
  StudioProviderHealth,
  StudioProviderListResponse,
  StudioProviderPayload,
  StudioProviderSummary
} from "../types";
import { appendOptionalQuery, request } from "./client";

export async function listStudioProviders(catalogPath?: string): Promise<StudioProviderListResponse> {
  const path = appendOptionalQuery("/api/v1/ops/providers", { catalog_path: catalogPath });
  return request<StudioProviderListResponse>(path);
}

export async function createStudioProvider(
  payload: StudioProviderPayload,
  catalogPath?: string
): Promise<StudioProviderSummary> {
  const path = appendOptionalQuery("/api/v1/ops/providers", { catalog_path: catalogPath });
  return request<StudioProviderSummary>(path, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateStudioProvider(
  providerId: string,
  payload: StudioProviderPayload,
  catalogPath?: string
): Promise<StudioProviderSummary> {
  const path = appendOptionalQuery(`/api/v1/ops/providers/${encodeURIComponent(providerId)}`, {
    catalog_path: catalogPath
  });
  return request<StudioProviderSummary>(path, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export async function deleteStudioProvider(
  providerId: string,
  catalogPath?: string
): Promise<{ status: string; provider_id: string; catalog_path: string }> {
  const path = appendOptionalQuery(`/api/v1/ops/providers/${encodeURIComponent(providerId)}`, {
    catalog_path: catalogPath
  });
  return request<{ status: string; provider_id: string; catalog_path: string }>(path, {
    method: "DELETE"
  });
}

export async function getStudioProviderHealth(providerId: string, catalogPath?: string): Promise<StudioProviderHealth> {
  const path = appendOptionalQuery(`/api/v1/ops/providers/${encodeURIComponent(providerId)}/health`, {
    catalog_path: catalogPath
  });
  return request<StudioProviderHealth>(path);
}

export async function getStudioMemorySummary(workspaceDir?: string): Promise<StudioMemorySummary> {
  const path = appendOptionalQuery("/api/v1/ops/memory/summary", { workspace_dir: workspaceDir });
  return request<StudioMemorySummary>(path);
}

export async function searchStudioMemory(
  query: string,
  options?: { workspace_dir?: string; limit?: number }
): Promise<StudioMemorySearchResponse> {
  const path = appendOptionalQuery("/api/v1/ops/memory/search", {
    query,
    workspace_dir: options?.workspace_dir,
    limit: options?.limit
  });
  return request<StudioMemorySearchResponse>(path);
}

export async function getStudioMemoryDaily(day: string, workspaceDir?: string): Promise<StudioMemoryDailyResponse> {
  const path = appendOptionalQuery(`/api/v1/ops/memory/daily/${encodeURIComponent(day)}`, {
    workspace_dir: workspaceDir
  });
  return request<StudioMemoryDailyResponse>(path);
}

export async function getStudioRuntimeDiagnostics(): Promise<StudioRuntimeDiagnostics> {
  return request<StudioRuntimeDiagnostics>("/api/v1/ops/diagnostics/runtime");
}

export async function discoverStudioProviderModels(
  payload: StudioProviderModelDiscoveryPayload
): Promise<StudioProviderModelDiscoveryResponse> {
  return request<StudioProviderModelDiscoveryResponse>("/api/v1/ops/providers/model-discovery", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function listStudioModels(catalogPath?: string): Promise<StudioModelListResponse> {
  const path = appendOptionalQuery("/api/v1/ops/models", { catalog_path: catalogPath });
  return request<StudioModelListResponse>(path);
}

export async function discoverStudioModels(
  payload: { source: string; provider_id: string },
  catalogPath?: string
): Promise<StudioModelProviderSummary> {
  const path = appendOptionalQuery("/api/v1/ops/models/discover", { catalog_path: catalogPath });
  return request<StudioModelProviderSummary>(path, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function selectStudioModel(
  payload: { source: string; provider_id: string; model_id: string },
  catalogPath?: string
): Promise<StudioModelProviderSummary> {
  const path = appendOptionalQuery("/api/v1/ops/models/selection", { catalog_path: catalogPath });
  return request<StudioModelProviderSummary>(path, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}
