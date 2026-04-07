import type {
  KnowledgeChunkingPayload,
  KnowledgeConfigResponse,
  KnowledgeDebugResponse,
  KnowledgeIngestResponse,
  KnowledgeMaintenanceResponse,
  KnowledgeQueryResponse,
  KnowledgeStatsResponse
} from "../types";
import { appendOptionalQuery, request } from "./client";

export interface KnowledgeIngestTextPayload {
  document_name: string;
  content: string;
  knowledge_base_id?: string;
  metadata?: Record<string, unknown>;
  chunking?: KnowledgeChunkingPayload;
}

export interface KnowledgeIngestFilePayload {
  path: string;
  document_name?: string;
  output_format?: string;
  enable_ocr?: boolean;
  knowledge_base_id?: string;
  metadata?: Record<string, unknown>;
  chunking?: KnowledgeChunkingPayload;
}

export interface KnowledgeQueryPayload {
  query: string;
  knowledge_base_id?: string;
  top_k?: number;
  conversation?: string[];
  enable_query_rewrite?: boolean;
}

export interface KnowledgeQueryDebugPayload extends KnowledgeQueryPayload {
  debug_k?: number;
}

export interface KnowledgeMaintenancePayload {
  knowledge_base_id?: string;
}

export async function ingestKnowledgeText(payload: KnowledgeIngestTextPayload): Promise<KnowledgeIngestResponse> {
  return request<KnowledgeIngestResponse>("/api/knowledge-base/ingest", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function ingestKnowledgeFile(payload: KnowledgeIngestFilePayload): Promise<KnowledgeIngestResponse> {
  return request<KnowledgeIngestResponse>("/api/knowledge-base/ingest/file", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function queryKnowledge(payload: KnowledgeQueryPayload): Promise<KnowledgeQueryResponse> {
  return request<KnowledgeQueryResponse>("/api/knowledge-base/query", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function queryKnowledgeDebug(payload: KnowledgeQueryDebugPayload): Promise<KnowledgeDebugResponse> {
  return request<KnowledgeDebugResponse>("/api/knowledge-base/query/debug", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function getKnowledgeStats(knowledgeBaseId?: string): Promise<KnowledgeStatsResponse> {
  const path = appendOptionalQuery("/api/knowledge-base/stats", { knowledge_base_id: knowledgeBaseId });
  return request<KnowledgeStatsResponse>(path);
}

export async function getKnowledgeConfig(): Promise<KnowledgeConfigResponse> {
  return request<KnowledgeConfigResponse>("/api/knowledge-base/config");
}

export async function rebuildKnowledgeIndex(payload: KnowledgeMaintenancePayload): Promise<KnowledgeMaintenanceResponse> {
  return request<KnowledgeMaintenanceResponse>("/api/knowledge-base/admin/rebuild", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function cleanupKnowledgeIndex(payload: KnowledgeMaintenancePayload): Promise<KnowledgeMaintenanceResponse> {
  return request<KnowledgeMaintenanceResponse>("/api/knowledge-base/admin/cleanup", {
    method: "DELETE",
    body: JSON.stringify(payload)
  });
}
