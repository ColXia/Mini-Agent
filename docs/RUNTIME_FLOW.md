# Runtime Flow And Boundaries

> **状态**: ✅ 活跃
> **最后更新**: 2026-04-06
> **文档索引**: [DOCS_INDEX.md](./DOCS_INDEX.md)

Updated: 2026-04-06

## Module Boundaries
- `mini_agent/runtime/tooling.py`
  - Owns tool assembly.
  - `add_workspace_tools`: adds workspace-scoped tools (`bash`, file tools, note tool, user modeling tool).
  - `initialize_shared_tools`: adds shared tools (skills + MCP), not tied to a workspace.
  - `initialize_agent_tools`: combines workspace + shared tools for a full agent session.
- `mini_agent/cli.py`
  - Owns command-line entry and process orchestration.
  - Uses `mini_agent/runtime/tooling.py` directly for tool initialization.
- `mini_agent/cli_interactive.py`
  - Owns interactive UX and session loop.
  - Delegates tool assembly to `mini_agent/runtime/tooling.py`.
- `mini_agent/acp/__init__.py`
  - Owns ACP protocol adaptation.
  - Uses shared tools as base, then injects workspace tools per ACP session.
- `mini_agent/tools/*`
  - Own concrete tool execution logic.
  - No dependency on CLI or ACP layers.

## Session Lifecycle
1. Entry point loads `Config`.
2. Runtime builds toolset:
   - Workspace tools for local file/shell scope.
   - Shared tools for MCP + skills.
3. Agent is created with system prompt + tools + workspace.
4. Each turn:
   - Append user message.
   - LLM response may include text, thinking, and tool calls.
   - Tool calls execute and append tool results.
   - Continue until stop reason (`end_turn`, `max_turn_requests`, `cancelled`, `refusal`).
5. MCP connections are cleaned up on shutdown.

## ACP Turn Flow
1. `prompt(sessionId, prompt)` arrives.
2. If session missing, ACP auto-creates session state internally.
3. Append user content into agent messages.
4. `_run_turn` executes iterative LLM + tool loop.
5. Push updates back via ACP `session_update`.

## Memory Core Flow (P12+)
1. Session start: load memory snapshot (frozen snapshot mode).
   - GEMINI.md hierarchical files (JIT discovery).
   - MEMORY.md active index (≤200 lines).
   - Memoria engine retrieves STM + LTM.
   - FTS5 session search (optional LLM summarization).
   - User model (Honcho) loaded.
2. During session: memory tools write to disk (no prompt cache invalidation).
   - Runtime note tool resolves memory anchor via hierarchical discovery.
   - `record_note` supports optional `topic` tag for structured self-save.
   - Writes to MEMORY.md and/or daily log (`memory/YYYY-MM-DD.md`).
   - `user_modeling` manages USER.md profile entries via builtin provider.
   - Entry operations: add (`conclude`), replace, remove, profile, search.
   - Session transcript index is updated for search retrieval.
3. Session retrieval path:
   - `GET /api/v1/agent/sessions` for active-session inspection under the v1 contract.
   - Legacy `/api/sessions/search` route was hard-deleted in P18.
4. Consolidated-memory relevance path:
   - Public relevance endpoint is deferred after P18 hard cut.
   - Consolidated-memory relevance remains internal runtime capability until next API contract phase.
5. Session end: trigger consolidation (Phase 1 extraction).
6. Consolidation scheduler applies lease/retry controls:
   - phase1 lease window (default 3600s), retry backoff (default 3600s)
   - bounded per-run jobs (default 8)
7. Background or manual trigger: phase2 global consolidation merge with watermark tracking.

## Model Manager Flow (P12+)
1. Provider catalog is validated and normalized (`mini_agent/model_manager/provider.py`).
2. Runtime routing (`mini_agent/model_manager/runtime.py`) loads optional catalog path (`MINI_AGENT_PROVIDER_CATALOG_PATH`) and builds an ordered provider candidate chain.
3. Model mapper (`mini_agent/model_manager/model_mapper.py`) resolves requested model -> provider model (`exact` / `partial` / `fallback_default`) and ranks providers by mapping quality + priority.
4. Circuit breaker core (`mini_agent/model_manager/circuit_breaker.py`) is used for provider-level gating.
   - states: `closed` / `open` / `half_open`
   - transitions: failure-threshold open, timeout half-open probe, half-open success close
5. Failover executor (`mini_agent/model_manager/failover.py`) runs per-request provider fallback:
   - preferred provider first, then global fallback providers
   - error classification (`mini_agent/model_manager/error_classifier.py`) drives failover behavior
   - per-attempt success/failure updates health monitor + breaker stats
6. Runtime entrypoints (`mini_agent/cli_interactive.py`, `src/apps/agent_studio_gateway/main.py`, `mini_agent/acp/__init__.py`) build `FailoverLLMClient` with the candidate chain.
7. Ops APIs (`src/apps/agent_studio_gateway/ops_router.py`) expose:
   - `GET /api/v1/ops/providers`
   - `GET /api/v1/ops/providers/{provider_id}/health`
   - `GET /api/v1/system/health`
8. If the provider registry is empty, runtime synthesizes one bootstrap provider from the minimal `config.llm` route input and still routes through the same registry selector path.
9. Request rectifier (`mini_agent/model_manager/rectifier.py`) normalizes provider payloads before outbound requests:
   - OpenAI request normalization (reasoning details cleanup + optional MiniMax thinking budget)
   - Anthropic request normalization (thinking signature cleanup + optional budget + cache-control injection)
   - protocol conversion helpers (OpenAI <-> Anthropic, OpenAI -> Gemini minimal mapping)
10. Rectifier is applied in runtime LLM clients:
   - `mini_agent/llm/openai_client.py`
   - `mini_agent/llm/anthropic_client.py`
11. Rectifier/runtime health counters are exposed via system health:
   - `GET /api/v1/system/health`
   - fields: request counts, budget/cache/signature mutation counts, conversion counts.
12. Active runtime request-policy and rectifier defaults are loaded from `config.runtime` and passed into protocol binding/profile creation:
   - retry: `config.runtime.retry`
   - request policy: `config.runtime.request_policy`
   - rectifier defaults: `config.runtime.rectifier`

## Code Agent Loop Flow (P14+)
1. Submission loop receives events over `asyncio.Queue`:
   - `user_input`, `interrupt`, `exec_approval`, `compact`, `drop_memories`
   - implementation: `mini_agent/agent_core/execution/agent_loop.py`
2. Turn context snapshot is captured at submission time:
   - immutable per-turn policy (`max_steps`, `max_tool_calls_per_step`)
   - isolated from later config mutation
   - implementation: `mini_agent/agent_core/context/loop_context.py`
3. Scheduler executes one turn with explicit state transitions:
   - `validating` -> `scheduled` -> `executing` -> (`completed` | `interrupted` | `errored`)
   - implementation: `mini_agent/agent_core/execution/scheduler.py`
4. Interrupt events trigger immediate cancel dispatch to running turn while retaining queued audit events.

## Code Agent Sandbox Flow (P14 T2.2)
1. `SandboxManager` selects backend at runtime:
   - `sandbox_mode=workspace` + Windows -> `windows_restricted_token`
   - `sandbox_mode=unrestricted` or non-Windows -> passthrough (`none`)
   - implementation: `mini_agent/agent_core/execution/sandbox/manager.py`
2. Command transform path for Windows-restricted backend:
   - elevated-command checks (e.g. `Start-Process -Verb RunAs`, execution-policy mutations, privileged service/registry/host shutdown paths)
   - domain-level network checks (`allow_all` / `deny_all` / `allowlist` / `blocklist`)
   - workspace-root `cwd` boundary validation
   - implementation: `mini_agent/agent_core/execution/sandbox/windows.py`, `mini_agent/agent_core/execution/sandbox/network.py`
3. Sandbox metadata is attached for runtime/tool diagnostics:
   - env keys: `MINI_AGENT_SANDBOX_BACKEND`, `MINI_AGENT_SANDBOX_RESTRICTED_TOKEN`, `MINI_AGENT_SANDBOX_WORKSPACE`, `MINI_AGENT_SANDBOX_NETWORK_MODE`
   - return payload includes backend metadata (`readable_roots`, `writable_roots`, `network_mode`)

## Declarative Tool Flow (P14 T2.3)
1. Legacy runtime tools are mapped into schema-first contracts:
   - contract fields: `name`, `description`, `schema`, `attributes`, `executor`
   - implementation: `mini_agent/agent_core/execution/tools/builder.py`
2. Per-call invocation builds validated execution objects:
   - JSON-schema required/type checks
   - confirmation signal for write/edit/delete/execute classes
   - tool location extraction for permission/sandbox integration
   - implementation: `mini_agent/agent_core/execution/tools/invocation.py`
3. Extended attributes keep behavior explicit and compact:
   - `kind`, `is_read_only`, `destructive`, `interrupt_behavior`, `max_result_size_chars`
   - implementation: `mini_agent/agent_core/execution/tools/attributes.py`
4. Runtime adapter path keeps current executor interface while using declarative contracts:
   - `Tool` -> `DeclarativeTool` registry
   - `DeclarativeTool` -> runtime `Tool` adapter
   - implementation: `mini_agent/agent_core/execution/tools/runtime_adapter.py`

## Coordinator Flow (P14 T2.4)
1. Coordinator accepts worker tasks with explicit stage and ownership metadata:
   - `WorkerTask(task_id, stage, prompt, owner, metadata)`
   - implementation: `mini_agent/agent_core/execution/coordinator.py`
2. Stage execution follows fixed pipeline order:
   - `research -> synthesis -> implementation -> verification`
   - same-stage tasks run with bounded concurrency (`max_concurrent_workers`)
3. Progress events are emitted to the coordinator bus:
   - stage events: `coordinator.stage.started`, `coordinator.stage.completed`, `coordinator.stage.skipped`
   - worker events: `coordinator.worker.started`, `coordinator.worker.completed`
4. Failure strategy:
   - default `stop_on_failure=true` short-circuits later stages
   - skipped stage summaries are emitted for observability and debugging

## Context Management Flow (P14 T2.5)
1. Layered compactor receives full turn message history:
   - implementation: `mini_agent/agent_core/context/context_compaction.py`
2. Compression stages:
   - snip old tool outputs to tail lines (`snip_tail_lines`, keeping recent tool outputs untouched)
   - mask irrelevant old tool outputs based on active query (`ToolOutputMasker`)
   - merge adjacent assistant messages (microcompact)
   - reverse token-budget selection (newest-first retention with system/user anchors)
3. Output contract:
   - compacted message tuple + `CompressionStats`
   - fields: original/compressed counts, token counts, masked/snipped/merged counters
4. Masking behavior:
   - implementation: `mini_agent/agent_core/execution/output_masking.py`
   - older tool outputs can be replaced by short placeholders to reduce context noise

## MCP Client Flow (P14 T2.6)
1. Code-agent MCP client discovers server definitions from `mcp.json`:
   - implementation: `mini_agent/agent_core/execution/mcp_client.py`
2. Connection lifecycle reuses MCP transport stack (`stdio`/`sse`/`streamable_http`) via existing registry layer.
3. Runtime surfaces:
   - list available MCP tools per server
   - invoke tools by explicit `server_name + tool_name`
4. Declarative wrapper path:
   - MCP runtime tools are wrapped into namespaced declarative contracts (`mcp_<server>_<tool>`)
   - implementation: `mini_agent/agent_core/execution/mcp_tools.py`

## Permission Flow (P14 T2.7)
1. Permission policy resolves ask/allow/deny decisions:
   - ordered rules by tool pattern and optional tool kind
   - read-only defaults to allow unless overridden
   - implementation: `mini_agent/agent_core/execution/permissions/policy.py`
2. Approval engine evaluates invocation with cache key:
   - fingerprint = tool name + arguments + kind
   - cache hit can auto-allow/deny repeated identical operations
   - implementation: `mini_agent/agent_core/execution/permissions/approval.py`
3. Escalation path:
   - denied high-impact tool classes (`write/edit/delete/execute/network/delegate`) can request escalation to user confirmation
4. Decision envelope:
   - `ApprovalOutcome` includes decision reason and flags (`from_cache`, `can_escalate`, `escalated`)

## Agent-Core Routing Flow (P15 T3.1)
1. Route table stores scoped bindings:
   - `peer`, `parent`, `wildcard`, `guild`, `roles`, `team`, `account`, `channel`, `default`
   - implementation: `mini_agent/agent_core/routing.py`
2. Resolver applies deterministic priority order to one `RoutingContext`.
3. Cache path:
   - repeated identical routing contexts are served from resolver cache (`max_cache_entries`)
   - cache hit returns the same route with `from_cache=true`
4. Fallback:
   - if no bindings match, resolver returns explicit default route record

## Agent-Core Skills Flow (P15 T3.2)
1. Skill discovery scans multiple sources:
   - `builtin` skills directory
   - optional `workspace` skills directory
   - optional plugin skill directories
   - optional remote-registered skills
   - implementation: `mini_agent/agent_core/skills/loader.py`
2. Source conflict resolution:
   - same skill name uses source-priority override via registry
   - implementation: `mini_agent/agent_core/skills/registry.py`
3. Progressive disclosure tiers:
   - Tier 1: metadata prompt (`name`, `description`, source)
   - Tier 2: full instructions (`SKILL.md` body)
   - Tier 3: helper files (`references/templates/scripts/assets`) with root-bound safe read
4. Eligibility gate:
   - checks requirements for OS/binaries/environment variables
   - implementation: `mini_agent/agent_core/skills/eligibility.py`
5. Runtime bridge:
   - exposes `get_skill`, `list_skills`, `get_skills_metadata_prompt` for existing skill tool contract
   - wiring: `mini_agent/tools/skill_tool.py`

## Agent-Core Cron Flow (P15 T3.3)
1. Job registration:
   - supports `at`, `every`, `cron` schedule types
   - implementation: `mini_agent/agent_core/cron/scheduler.py`
2. Tick phase:
   - detects due jobs
   - applies grace-window late-run handling
   - enqueues runs into bounded queue (overflow counted as dropped)
3. Run phase:
   - executes queued jobs via isolated executor contract
   - implementation: `mini_agent/agent_core/cron/isolated_run.py`
4. Delivery phase:
   - routes run outcomes to `none` / `announce` / `webhook` delivery modes
   - implementation: `mini_agent/agent_core/cron/delivery.py`
5. End-to-end orchestration:
   - `tick`, `run_pending`, `tick_and_run` for scheduler loop integration

## Agent-Core Delegation Flow (P15 T3.4)
1. Delegation manager accepts subtask contract:
   - `DelegationTask` -> `DelegationRequest` -> `DelegationResult`
   - implementation: `mini_agent/agent_core/delegation.py`
2. Isolation and safety controls:
   - depth guard: child depth is `parent_depth + 1` and must not exceed `max_depth`
   - concurrent batch guard: bounded by `max_concurrent`
   - blocked tool filtering for child allowlists (`delegate`, `clarify`, `memory`, `send_message`)
3. Progress and state management:
   - progress events: `delegation.task.started`, `delegation.task.completed`
   - global state snapshot/restore (`total_started/completed/failed`, active task ids)
4. Hook bridge:
   - optional delegation hook supports memory/provider sync (`delegated_task`, summary/error)

## Agent-Core Session Flow (P15 T3.5)
1. Session-key normalization:
   - canonical key model `agent:<id>:<channel>:<peer_kind>:<peer_id>[:thread:<thread_id>]`
   - parser, thread inheritance, and deterministic key slug generation
   - implementation: `mini_agent/agent_core/session/session_key.py`
2. Session-key lookup:
   - index supports full key, prefix/contains partial query, slug query, and peer-id shortcut
   - ambiguous partial matches are rejected with typed error to avoid unsafe implicit routing
3. Lifecycle policy:
   - reset modes: `none`, `daily`, `idle`, `both`
   - lifecycle manager APIs: `bootstrap`, `should_reset`, `touch`, `reset`, `ensure_active`
   - implementation: `mini_agent/agent_core/session/lifecycle.py`
4. Lineage graph:
   - root + child linkage for delegation/reset/compression ancestry tracking
   - chain-to-root traversal and cycle prevention guard
   - implementation: `mini_agent/agent_core/session/lineage.py`

## Agent-Core Browser Flow (P15 T3.6)
1. Chrome lifecycle baseline:
   - profile registration and runtime states (`running`, `pid`, health timestamps)
   - lifecycle APIs: `register_profile`, `start`, `stop`, `ensure_running`, `health`
   - implementation: `mini_agent/agent_core/browser/chrome.py`
2. CDP operation baseline:
   - navigation with policy guard (`allow_schemes`, domain allow/block, private-host restrictions)
   - tab listing and screenshot capture with typed payload contract
   - action baseline (`click`, `type`, `press`, `wait`) via runtime evaluation
   - implementation: `mini_agent/agent_core/browser/cdp.py`
3. Tool interface baseline:
   - agent-facing APIs: `browser_profiles`, `browser_tabs`, `browser_navigate`, `browser_screenshot`, `browser_act`
   - profile auto-start and per-profile CDP client binding
   - implementation: `mini_agent/agent_core/browser/tool.py`

## Agent-Core Pairing Security Flow (P15 T3.7)
1. Pairing challenge store:
   - per-channel JSON persistence with lock-file coordination
   - 8-char human-friendly setup code (`A-Z` + `2-9`, ambiguous chars removed)
   - request TTL pruning (`1h`) and max pending cap (`3`)
   - implementation: `mini_agent/agent_core/security/pairing.py`
2. Pairing approval path:
   - code verification consumes pending challenge
   - approved sender id promoted into channel `allow_from` store
3. DM/group policy resolver:
   - DM policies: `open`, `disabled`, `allowlist`, `pairing`
   - group policies: `open`, `disabled`, `allowlist` (optional fallback to DM allowlist)
   - policy decisions return typed access outcome (`allowed`, `require_pairing`, reason)
   - implementation: `mini_agent/agent_core/security/policy.py`

## Tools Docling Parse Flow (P16 T4.1)
1. Tool-layer parse facade:
   - input contract: document path + `output_format` + optional `enable_ocr`
   - output contract: typed parse payload (`source_path`, `content`, metadata, `used_docling`)
   - implementation: `mini_agent/tools/docling_parse.py`
2. Runtime execution path:
   - adapter path: delegate binary parsing to injected Docling adapter
   - fallback path: deterministic text fallback for local no-dependency execution
   - batch path: process multiple files with per-item success/error envelope
3. Subprogram exposure:
   - standalone service entry: `subprograms/document_parser/main.py`
   - gateway endpoints: `/api/document-parser/parse`, `/api/document-parser/parse/batch`, `/formats`, `/health`
   - router: `subprograms/document_parser/gateway/router.py`

## Tools Knowledge-Base Flow (P16 T4.2)
1. Built-in retrieval baseline:
   - lightweight hybrid store (`BM25 + hash-vector + RRF`)
   - shared runtime store resolution for workspace-aware KB access
   - implementation: `mini_agent/tools/knowledge_base.py`
2. Tool exposure:
   - `knowledge_base_query` tool for explicit grounded retrieval during an agent turn
3. Subprogram exposure:
   - standalone service entry: `subprograms/knowledge_base/main.py`
   - gateway endpoints: `/api/knowledge-base/query`, `/api/knowledge-base/ingest`, `/api/knowledge-base/stats`, `/health`
   - router: `subprograms/knowledge_base/gateway/router.py`

## Tools Web Search Flow (P16 T4.3)
1. Provider adapter model:
   - built-in providers: `searxng`, `brave`, `google`, `duckduckgo`
   - provider override supports deterministic local stubs for tests
2. Search merge pipeline:
   - engine-priority execution with bounded `limit`
   - cross-engine URL dedupe and stable rank assignment
   - per-engine errors captured without hard-failing whole search request
   - implementation: `mini_agent/tools/web_search.py`
3. Tool exposure:
   - `web_search` tool contract (`query`, `limit`, optional engine order)
   - output envelope includes `hits`, `errors`, and `engines_used`

## Subprogram Memory Manager Flow (P16 T4.4)
1. Subprogram entry:
   - standalone service: `subprograms/memory_manager/main.py`
   - mounted router: `subprograms/memory_manager/gateway/router.py`
2. Memory source model:
   - reuses existing markdown memory layout (`MEMORY.md` + `memory/YYYY-MM-DD.md`)
   - store abstraction: `mini_agent.tools.note_tool.MarkdownMemoryStore`
3. API contracts:
   - summary: `/api/memory/summary`
   - append: `/api/memory/append`
   - search: `/api/memory/search`
   - export: `/api/memory/export` (`jsonl` / `markdown`)

## Gateway Ops Flow (P17 T5.2)
1. Gateway contract mounting:
   - `src/apps/agent_studio_gateway/main.py` mounts `ops_router` under `/api/v1/ops/*`.
2. Ops auth boundary:
   - route-level auth is controlled by `MINI_AGENT_STUDIO_API_KEYS`.
   - when token list is non-empty, `/api/v1/ops/*` requires:
     - `Authorization: Bearer <token>` or
     - `x-api-key: <token>`
   - when token list is empty, auth gate is open for local development.
3. Path permission boundary:
   - `workspace_dir` and `catalog_path` must stay within allowed roots.
   - default allowed roots:
     - repository root
     - `workspace/` root
   - optional extension via `MINI_AGENT_STUDIO_ALLOWED_ROOTS` (comma-separated).
4. Provider contract path:
   - provider catalog path resolution order:
     - explicit query `catalog_path`
     - env `MINI_AGENT_PROVIDER_CATALOG_PATH`
     - fallback `workspace/providers.json`
   - provider management endpoints:
     - `GET /api/v1/ops/providers`
     - `POST /api/v1/ops/providers`
     - `PUT /api/v1/ops/providers/{provider_id}`
     - `DELETE /api/v1/ops/providers/{provider_id}`
   - health endpoint:
     - `GET /api/v1/ops/providers/{provider_id}/health`
   - catalog updates are normalized and persisted with atomic file replacement.
5. Memory contract path:
   - memory root resolution supports optional `workspace_dir`.
   - memory browse endpoints:
     - `GET /api/v1/ops/memory/summary`
     - `GET /api/v1/ops/memory/search`
     - `GET /api/v1/ops/memory/daily/{day}`
   - daily endpoint validates `YYYY-MM-DD` and returns explicit `400`/`404` on invalid or missing targets.
6. Current consumer surfaces:
   - CLI / TUI / Desktop / remote adapters consume the same `/api/v1/ops/*` contract
   - browser Studio assets were removed and are no longer part of this flow

## Novel Transport Flow (P32.12)
1. Gateway contract mounting:
   - `src/apps/agent_studio_gateway/main.py` mounts `subprograms.novel_generator.gateway.router` under `/api/v1/novel/*`.
2. Contract ownership:
   - request DTOs live in `src/mini_agent/interfaces/novel.py`.
3. Runtime wiring ownership:
   - `src/mini_agent/novel/runtime.py` builds and caches `NovelServiceUseCases`.
4. Domain use-case ownership:
   - `src/mini_agent/novel/service.py` owns setup/write/finalize/cover/illustrate/chapter-history orchestration.
5. Shared ingress reuse:
   - `src/mini_agent/application/channel_novel_action_handler.py` consumes the same `get_novel_use_cases(...)` factory for `/novel ...` remote actions.
   - `ChannelIngressUseCases` delegates feature-specific novel commands to that owner instead of owning novel parsing/dispatch directly.

## Main-Agent Gateway Transport Flow (P32.13)
1. Host composition:
   - `src/apps/agent_studio_gateway/main.py` mounts the main-agent transport router.
2. Transport ownership:
   - `src/apps/agent_studio_gateway/main_agent_router.py` owns the maintained HTTP/SSE contract for:
     - `/api/v1/system/health`
     - `/api/v1/ops/diagnostics/*`
     - `/api/v1/agent/*`
     - `/api/v1/channel/message`
3. Composition ownership:
   - `src/apps/agent_studio_gateway/composition.py` owns:
     - runtime-manager construction
     - surface-service construction
     - channel-ingress construction
     - startup/shutdown cleanup
     - health/runtime diagnostics assembly
4. Workspace-file exposure:
   - `src/apps/agent_studio_gateway/main.py` mounts `/api/files`
   - browser static hosting and SPA fallback were removed together with browser WebUI
5. Service/runtime dependency injection:
   - the router consumes injected getters for:
     - health response
     - runtime diagnostics
     - `MainAgentSurfaceService`
     - `ChannelIngressUseCases`
6. Architectural effect:
   - composition stays in `composition.py`
   - host entry stays in `main.py`
   - protocol translation stays in the dedicated transport router
   - orchestration remains in `application` / `runtime`
   - Desktop/TUI/remote clients consume the same typed gateway contract

## Gateway Ops Transport Flow (P32.16)
1. Host assembly:
   - `src/apps/agent_studio_gateway/main.py` owns `GATEWAY_OPERATIONS_USE_CASES`.
   - `main.py` mounts `create_ops_router(OpsRouterDependencies(...))`.
2. Transport ownership:
   - `src/apps/agent_studio_gateway/ops_router.py` owns the maintained `/api/v1/ops/*` HTTP contract.
3. Dependency pattern:
   - `ops_router.py` consumes injected dependencies for:
     - operations use-case getter
     - ops auth dependency
   - this now matches the factory-based dependency pattern already used by `main_agent_router.py`
4. Architectural effect:
   - host-level service construction stays in `main.py`
   - protocol translation stays in `ops_router.py`
   - the gateway transport layer now has one consistent DI/factory ownership model
   - optional studio auth header from `VITE_STUDIO_API_KEY`.
7. Real-endpoint smoke path:
   - script: `scripts/ci/studio_ops_smoke.py`
   - verifies auth boundary, provider CRUD/health, memory summary/search/daily, and external path rejection.

## Remote Interaction Flow (QQ Active Path)
1. Shared channel-to-gateway contract:
   - the shared gateway contract carries:
     - `channel_type`
     - `conversation_id`
     - `sender_id`
     - optional `metadata`
   - gateway chat endpoint uses these fields for conversation binding (`channel|conversation|sender`).
2. Active QQ adapter source/runtime path:
   - single maintained runtime app: `src/apps/qqbot_channel/`
   - runtime entry: `src/apps/qqbot_channel/bot.mjs`
   - gateway transport helpers: `src/apps/qqbot_channel/gateway_io.mjs`
   - workspace/message guardrails: `src/apps/qqbot_channel/guardrails.mjs`
   - synthetic smoke: `src/apps/qqbot_channel/smoke_runner.mjs`
   - runtime app/orchestration: `uv run mini-agent stack up` or `scripts/start_runtime_stack.ps1`
   - gateway auth passthrough:
     - optional `Authorization: Bearer <token>` from `QQBOT_GATEWAY_AUTH_TOKEN` or `MINI_AGENT_GATEWAY_AUTH_TOKEN`
   - message handling:
     - normal text forwarding to `GET /api/v1/agent/chat/stream`
     - inbound message truncation guardrail (`QQBOT_MAX_MESSAGE_CHARS`)
     - outbound reply chunking guardrail (`QQBOT_MAX_REPLY_CHUNK_SIZE`)
     - `/workspace` path boundary enforcement (`QQBOT_ALLOWED_WORKSPACE_ROOTS`)
     - command set reusing shared session/application semantics
3. Remote adapter lock:
   - `QQ` is the only active remote adapter in the current repo
   - legacy `WeChat` / generic channel trees were removed from the active codebase in `P32.60`
   - future remote adapters must start as new app-path implementations after an explicit architecture decision
4. Channel startup status:
   - maintained local orchestrator: `uv run mini-agent stack up` or `scripts/start_runtime_stack.ps1`
   - legacy per-channel PowerShell launchers were archived to `scripts/archive/`
5. Active smoke path:
   - `npm run smoke --prefix src/apps/qqbot_channel`
   - validates QQ synthetic message roundtrip (`processSmokeMessage`) with workspace allow/reject checks

## Error Handling Strategy
- Tool bootstrap:
  - Skills and MCP loading are best-effort; failures do not crash startup.
- LLM call:
  - Retry policy handled by `RetryConfig`.
  - Terminal failure returns a refusal-like stop path and logs details.
- MCP execution:
  - Connection and execute phases have explicit timeouts.
  - Cleanup is centralized in `cleanup_mcp_connections()`.
- Bash process lifecycle:
  - On timeout or termination, process pipes are drained to avoid Windows transport leaks.
- Code-agent sandbox:
  - policy violations (elevation/network/cwd scope) fail fast with `PermissionError`.
- Declarative tool invocation:
  - schema mismatch or unknown fields fail fast with `ValueError`.
- Coordinator worker execution:
  - worker exceptions are captured as failed `WorkerResult` records.
- Context compaction:
  - compactor is deterministic and does not call external services.
- MCP client:
  - missing server/tool lookups return typed `ToolResult` errors without raising runtime exceptions.
- Permission engine:
  - unsupported escalation requests return explicit deny outcomes instead of raising exceptions.
- Agent-core routing:
  - unresolved contexts return a default route, avoiding hard failures in dispatch path.
- Agent-core skills:
  - malformed `SKILL.md` files are skipped without crashing discovery.
- Agent-core cron:
  - queue overflow and late-run misses are recorded in job state instead of hard-failing scheduler loop.
- Agent-core delegation:
  - runner exceptions are wrapped into failed delegation results and do not crash batch execution.
- Agent-core browser:
  - disallowed navigation targets fail fast via typed policy errors.
  - malformed screenshot payloads are rejected with explicit decode errors.
- Agent-core pairing security:
  - lock contention and pending-cap overflow fail with explicit typed errors.
  - expired pairing requests are pruned deterministically before approval checks.
- Docling parse tool:
  - unsupported extensions and missing files return explicit parse errors.
  - binary formats without adapter fail fast with typed availability error.
- MaxKB tools:
  - missing transport/config fail fast with typed client configuration error.
  - HTTP failure path returns explicit status + provider error details.
- Web-search tools:
  - unknown providers are reported in error list without aborting whole request.
  - provider-specific failures are isolated and surfaced with engine tag.
- Memory-manager subprogram:
  - invalid append scope and export format return explicit `400` errors.
  - operations remain file-backed and deterministic (no external dependency).

## Test Strategy Notes
- `live_api` tests are opt-in with env var `MINI_AGENT_RUN_LIVE_TESTS=1`.
- `integration` marker identifies multi-component/external-dependency tests.
- Default local run should be stable without external credentials.
