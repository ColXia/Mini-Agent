export type ModeKey = "workspace" | "knowledge_base" | "channel" | "novel_studio" | "assets" | "studio_ops";

export type ChatMessageRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: ChatMessageRole;
  content: string;
  time: string;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  message_count: number;
  token_usage: number;
  workspace_dir: string;
  updated_at: string;
}

export interface ChannelMessageResponse extends ChatResponse {}

export interface KnowledgeCitationSpan {
  chunk_index?: number | null;
  char_start?: number | null;
  char_end?: number | null;
}

export interface KnowledgeCitation {
  source_id?: string | null;
  chunk_id?: string | null;
  doc_id?: string | null;
  title?: string | null;
  source_path?: string | null;
  url?: string | null;
  page?: number | null;
  span?: KnowledgeCitationSpan | null;
}

export interface KnowledgeQueryRewrite {
  original_query: string;
  rewritten_query: string;
  rewritten: boolean;
  reason: string;
}

export interface KnowledgeQueryHit {
  chunk_id: string;
  document_name: string;
  content: string;
  metadata: Record<string, unknown>;
  score: number;
  bm25_score: number;
  vector_score: number;
  citation: KnowledgeCitation;
}

export interface KnowledgeQueryResponse {
  status: string;
  query: string;
  original_query: string;
  query_rewrite: KnowledgeQueryRewrite;
  knowledge_base_id: string;
  hits: KnowledgeQueryHit[];
}

export interface KnowledgeDebugRankingItem {
  chunk_id: string;
  document_name: string;
  bm25_rank: number;
  vector_rank: number;
  bm25_score: number;
  vector_score: number;
  citation: KnowledgeCitation;
  rrf_score?: number;
  final_rank?: number;
}

export interface KnowledgeDebugResponse {
  status: string;
  original_query: string;
  query_rewrite: KnowledgeQueryRewrite;
  query: string;
  knowledge_base_id: string;
  top_k: number;
  rrf_k: number;
  bm25_ranking: KnowledgeDebugRankingItem[];
  vector_ranking: KnowledgeDebugRankingItem[];
  fused_ranking: KnowledgeDebugRankingItem[];
}

export interface KnowledgeChunkingPayload {
  strategy?: "paragraph" | "sentence" | "fixed";
  chunk_size?: number;
  overlap?: number;
}

export interface KnowledgeIngestResponse {
  status: string;
  document_name: string;
  knowledge_base_id: string;
  chunk_count: number;
  source_path?: string;
  used_docling?: boolean;
}

export interface KnowledgeMaintenanceResponse {
  status: string;
  duration_ms: number;
  knowledge_base_id: string | null;
  affected_chunks?: number;
  affected_documents?: number;
  removed_chunks?: number;
  removed_documents?: number;
}

export interface KnowledgeStatsResponse {
  status: string;
  knowledge_base_id: string | null;
  chunk_count: number;
  document_count: number;
  store_path: string;
}

export interface KnowledgeConfigResponse {
  status: string;
  [key: string]: unknown;
}

export interface NovelChapter {
  chapter: number;
  title: string;
  summary: string;
  draft_exists?: boolean;
  final_exists?: boolean;
}

export interface NovelAsset {
  asset_type: "covers" | "illustrations" | "audio";
  name: string;
  path: string;
  url: string;
}

export interface ChapterVersion {
  version_id: string;
  chapter: number;
  final: boolean;
  source: string;
  content_length: number;
  created_at: string;
  note?: string;
  tags?: string[];
}

export interface StudioProviderSummary {
  id: string;
  name: string;
  api_type: string;
  api_base: string;
  api_key_masked: string;
  models: string[];
  model_display_names: Record<string, string>;
  enabled: boolean;
  priority: number;
  timeout: number;
  headers: Record<string, string>;
  catalog_path: string;
  health_status: string;
  breaker_state: string;
  selected_count: number;
  error_rate: number;
  consecutive_failures: number;
}

export interface StudioProviderListResponse {
  catalog_path: string;
  provider_count: number;
  items: StudioProviderSummary[];
}

export interface StudioProviderHealth {
  provider_id: string;
  status: string;
  breaker_state: string;
  selected_count: number;
  total_requests: number;
  total_successes: number;
  total_failures: number;
  consecutive_failures: number;
  error_rate: number;
  last_selected_at?: string | null;
  last_success_at?: string | null;
  last_failure_at?: string | null;
  last_failure_reason?: string | null;
}

export interface StudioProviderPayload {
  id?: string;
  name: string;
  api_type: string;
  api_base: string;
  api_key: string;
  models: string[];
  model_display_names?: Record<string, string>;
  model_id?: string;
  model_display_name?: string;
  auto_discover_models?: boolean;
  selected_model_id?: string;
  enabled: boolean;
  priority: number;
  timeout: number;
  headers: Record<string, string>;
}

export interface StudioProviderModelSummary {
  model_id: string;
  display_name: string;
  is_default: boolean;
  context_window?: number | null;
  learned_token_limit?: number | null;
}

export interface StudioProviderModelDiscoveryPayload {
  api_type: string;
  api_base: string;
  api_key: string;
}

export interface StudioProviderModelDiscoveryResponse {
  models: StudioProviderModelSummary[];
  latest_model_id?: string | null;
}

export interface StudioModelProviderSummary {
  source: "custom" | "preset" | string;
  provider_id: string;
  provider_name: string;
  api_type: string;
  api_base: string;
  default_model_id?: string | null;
  models: StudioProviderModelSummary[];
  enabled: boolean;
  priority: number;
}

export interface StudioModelListResponse {
  items: StudioModelProviderSummary[];
}

export interface StudioMemoryNote {
  timestamp: string;
  category: string;
  content: string;
  path: string;
}

export interface StudioMemorySummary {
  workspace_dir: string;
  memory_root: string;
  long_term_file: string;
  daily_dir: string;
  daily_files: string[];
  notes_count: number;
  categories: string[];
}

export interface StudioMemorySearchResponse {
  workspace_dir: string;
  query: string;
  limit: number;
  total: number;
  items: StudioMemoryNote[];
}

export interface StudioMemoryDailyResponse {
  workspace_dir: string;
  day: string;
  path: string;
  note_count: number;
  content: string;
  items: StudioMemoryNote[];
}

export interface StudioRuntimeDiagnostics {
  mode: "single_main" | "team" | string;
  active_sessions: number;
  max_active_sessions: number;
  available_session_slots: number;
  reserved_team_slots: number;
  workspace_application_required: boolean;
  team_saturation_rejections: number;
  team_workspace_conflict_rejections: number;
  main_workspace_dir?: string | null;
}
