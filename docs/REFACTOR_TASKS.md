# Mini-Agent Refactor Tasks (OSS Adopt Plan)

> **鐘舵€?*: 鉁?娲昏穬
> **鏈€鍚庢洿鏂?*: 2026-04-12
> **褰撳墠闃舵**: P30 surface/session correction 缁х画鎺ㄨ繘
> **鏂囨。绱㈠紩**: [DOCS_INDEX.md](./DOCS_INDEX.md)

> Note (P18 hard refactor): historical phase records keep old module paths for traceability.
> Active runtime path is single-host v1 only (`src/apps/agent_studio_gateway/main.py`, `/api/v1/*`).
> Stage normalization (2026-04-07): P18 closeout baseline frozen; P19 kickoff + Stage-C docs + ops alerting slices landed.
> Session boundary update (2026-04-14 P32.34): `src/mini_agent/session/store.py` and `tests/test_session_store_persistence.py` were removed. Current session truth is the runtime-owned `session_state/session_runtime_persistence` path; `mini_agent.session` now exposes only persistence, projections, and conversation binding.
> Current hygiene closeout line (2026-04-16): `docs/P32B_REPO_HYGIENE_AND_STRUCTURE_ALIGNMENT_PLAN_2026-04-16.md`.

## Index
- OSS implementation index: `docs/OSS_REFERENCE_INDEX.md`
- Published development index: `docs/DEVELOPMENT_INDEX.md`
- Current execution anchor: `docs/P32B_REPO_HYGIENE_AND_STRUCTURE_ALIGNMENT_PLAN_2026-04-16.md`
- Framework skeleton lock: `docs/FRAMEWORK_SKELETON.md`
- Dev habit and mistake ledger: `docs/MINIAGENT_DEV_HABIT_LEDGER.md`
- API v1 contract skeleton: `docs/API_V1_CONTRACT_SKELETON.md`
- Archived P18 route deletion backlog: `docs/archive/P18_ROUTE_DELETION_BACKLOG.md`
- Archived P18 closeout baseline evidence: `docs/archive/P18_CLOSEOUT_BASELINE_2026-04-07.md`
- Archived P18 hard-refactor execution plan: `docs/archive/P18_HARD_REFACTOR_EXECUTION_PLAN.md`
- Archived P19 rollout prep contract: `docs/archive/P19_AGENT_TEAM_ROLLOUT_CONTRACT.md`
- Archived P19 team-mode alert policy: `docs/archive/P19_TEAM_MODE_ALERT_POLICY.md`
- Archived P19 Stage-C adoption tracking: `docs/archive/P19_STAGEC_ADOPTION_TRACKING.md`
- Archived P19 canary cadence: `docs/archive/P19_TEAM_MODE_CANARY_CADENCE.md`
- Archived P19 weekly readiness template: `docs/archive/P19_WEEKLY_RELEASE_READINESS_TEMPLATE.md`
- Archived GitHub upload scope (2026-04-07): `docs/archive/GITHUB_UPLOAD_SCOPE_2026-04-07.md`
- Archived cross-device handoff (2026-04-07): `docs/archive/CROSS_DEVICE_HANDOFF_2026-04-07.md`
- Session boundary audit (2026-04-12): `docs/P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md`
- Session hard-refactor plan (2026-04-12): `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`
- Historical transformation plan (source-study only): `docs/TRANSFORMATION_PLAN.md`
- Transformation guardrails (mini): `docs/TRANSFORMATION_PLAN_LITE_ADDENDUM.md`
- Archived external OSS index bridge: `docs/archive/EXTERNAL_OSS_INDEX.md`

Mini execution contract:
- `Mini` = full-strength core capabilities with lean architecture.
- Not a feature downgrade; only non-core platform complexity is deferred.

Framework guardrail update (2026-04-13):
- future refactor work must obey `docs/FRAMEWORK_SKELETON.md`
- that document now freezes:
  - entrance model
  - layer ownership
  - repository mapping
  - no-go drift patterns

## External Sources Reviewed
- `openclaw-main` (gateway/session/memory/plugin/sandbox/acp docs)
- `hermes-agent-main` (ACP deployment and runtime shape)
- `codex-main` + `codex-sdk` (thread persistence, resume, approval/sandbox model)
- `gemini-cli-main` (session retention/checkpoint, ACP mode, MCP discovery model)
- `cc-switch-main` (MCP unified schema, multi-client mapping, atomic config writes)

## Adoption Matrix

| Capability | Source | Adopt Type | Effort | Risk | Impact | Mini-Agent Target |
| --- | --- | --- | --- | --- | --- | --- |
| Persistent session + resume + retention | OpenClaw + Gemini + Codex SDK | Direct (Now) | M | M | High | `mini_agent/core/*`, `gateway/routers/sessions.py`, `mini_agent/cli_interactive.py`, `mini_agent/acp/*` |
| Session pruning/compaction triggers | OpenClaw | Borrow (Mid) | M | M | High | `mini_agent/agent_core/engine.py`, new `mini_agent/session/pruning.py` |
| ACP session lifecycle and binding model | OpenClaw ACP + Gemini ACP | Direct (Now) | M | M | High | `mini_agent/acp/__init__.py`, ACP state layer |
| Gateway singleton lock + pairing/auth guard | OpenClaw gateway-lock/pairing/security | Direct (Now) | M | H | High | `gateway/core/app.py`, `src/apps/agent_studio_gateway/main.py`, `gateway/security/*` |
| MCP config normalization (stdio/http/sse), allow/deny/trust | Gemini MCP + CC Switch | Direct (Now) | M | M | High | `mini_agent/tools/mcp_loader.py`, `src/mini_agent/config.py`, `src/mini_agent/config/mcp*.json` |
| MCP cross-client import/export mapping | CC Switch | Borrow (Mid) | M | M | Med | new `mini_agent/tools/mcp_profile_sync.py` |
| Sandbox + approval layered policy | OpenClaw + Codex | Borrow (Mid) | L | H | High | `mini_agent/tools/bash_tool.py`, runtime policy layer, CLI/ACP config |
| Plugin capability registry (provider/channel/tool/hook) | OpenClaw plugin internals | Direct (Now) | L | H | Med | `mini_agent/plugins/*` |
| Memory split (long-term + daily notes + retrieval) | OpenClaw memory model | Direct (Now) | M | M | Med | `mini_agent/tools/note_tool.py`, `mini_agent/runtime/tooling.py` |
| Config write safety (atomic + schema migration) | CC Switch | Direct (Now) | S | L | Med | config read/write utilities |

## P2 Continuation (Must Finish First)

### P2.1 Critical structural fixes
- [x] Restore `mini_agent/session/store.py` real implementation (current file is invalid self-import stub).
- [x] Unify session imports so launcher/gateway/ACP use one canonical session module.
- [x] Fix tool init duplication in gateway chat path (`initialize_base_tools` + `add_workspace_tools` double add issue).
- [x] Add `mcp-example.json` compatibility check (UTF-8 / UTF-8-SIG parser path) and keep strict JSON validation test.

### P2.2 Test and CI baseline completion
- [x] Add gateway/session router tests (`/api/chat`, `/api/chat/stream`, `/api/sessions/*`).
- [x] Add minimal CI command script for stable local set:
  - `pytest -q -k "not integration and not llm and not llm_clients"`
- [x] Enforce `mcp-example.json` parse check in test suite.

## P3 Session Kernel Refactor (High Priority)
- [x] Create `mini_agent/session/` package (state model, store interface, retention policy).
- [x] Add persistent storage backend (JSONL transcript + metadata index; SQLite optional as adapter).
- [x] Implement resume/list/delete/reset/checkpoint APIs shared by CLI/Gateway/ACP.
- [x] Add retention config (`max_age`, `max_count`) and cleanup command.
- [x] Add migration path from in-memory session store.

## P4 ACP + Gateway Control Plane Refactor
- [x] Migrate ACP runtime to non-deprecated startup path (replace direct `AgentSideConnection` path).
- [x] Introduce explicit ACP session states: `new/running/cancelled/closed/expired`.
- [x] Add gateway lock (single instance per host:port), clear error on port conflict.
- [x] Add basic gateway auth token mode for non-local access.
- [x] Define conversation-to-session binding model for channel and ACP workflows.

## P5 MCP and Config Refactor
- [x] Split MCP into `discovery`, `registry`, `executor`, `lifecycle` modules.
- [x] Add server-level policy: `allow/exclude/trust/timeout`.
- [x] Support resource discovery/read entry points (align with Gemini/OpenClaw style).
- [x] Add import/export mappers for Codex/Gemini/Claude MCP config formats.
- [x] Add atomic write + rollback for config updates.

## P6 Safety and Runtime Policy Layer
- [x] Introduce three-level policy model:
  - sandbox mode (where tool runs)
  - tool policy (what tools are callable)
  - elevated exec (host escape gate)
- [x] Add runtime execution/access modes (`plan` / `build`, `default` / `full-access`) for CLI surfaces.
- [x] Add `security audit` style command for config risk checks.

## P7 Plugin and Memory Evolution
- [x] Introduce plugin capability registration boundaries (provider/channel/tool/hook).
  - `mini_agent/plugins/registry.py`
  - `tests/test_plugin_registry.py`
- [x] Convert memory from single note file to:
  - `MEMORY.md` (long-term)
  - `memory/YYYY-MM-DD.md` (daily context)
  - `mini_agent/tools/note_tool.py`
  - `mini_agent/runtime/tooling.py`
  - `tests/test_note_tool.py`, `tests/test_session_integration.py`, `tests/test_integration.py`
- [x] Add hybrid memory retrieval (keyword + embedding optional).
  - keyword ranking enabled by default
  - embedding ranking enabled when optional embedding provider is supplied

## P8 Observability and Operations
- [x] Add structured run events (session/tool/latency/error) and replayable logs.
  - event journal: `~/.mini-agent/log/agent_run_*.events.jsonl`
  - replay command: `mini-agent replay-log --file <events.jsonl>`
  - implementation: `mini_agent/logger.py`, `mini_agent/agent_core/engine.py`
- [x] Add `doctor` command for environment and MCP diagnostics.
  - command: `mini-agent doctor`
  - implementation: `mini_agent/ops/doctor.py`, `mini_agent/cli.py`
- [x] Add startup self-check for config, workspace, permissions, and MCP reachability.
  - gateway boot check: `mini_agent/cli.py`
  - CLI boot check: `mini_agent/cli_interactive.py`

## P9 Observability Hardening and API Exposure
- [x] Add run-event retention and rotation policy for long-running deployments.
  - config: `src/mini_agent/config.py` + `src/mini_agent/config/config*.yaml` (`observability.*`)
  - logger retention: `mini_agent/logger.py` (`EventLogRetentionPolicy`, `prune_logs`)
  - runtime wiring: `mini_agent/cli_interactive.py`, `gateway/routers/chat.py`, `mini_agent/acp/__init__.py`
  - command: `mini-agent prune-logs`
  - tests: `tests/test_logger_retention.py`
- [x] Add gateway/API-level observability surfaces for event replay and health checks.
  - router: `gateway/routers/observability.py`
  - endpoints:
    - `GET /api/observability/health`
    - `GET /api/observability/runs`
    - `GET /api/observability/runs/{run_id}/events`
    - `GET /api/observability/runs/{run_id}/replay`
  - gateway wiring: `gateway/core/app.py`, `gateway/routers/__init__.py`
  - tests: `tests/test_gateway_routers.py`
- [x] Extend `doctor` with optional MCP handshake probes and actionable remediation hints.
  - command flag: `mini-agent doctor --mcp-handshake`
  - implementation: `mini_agent/ops/doctor.py`, `mini_agent/tools/mcp/registry.py`, `mini_agent/cli.py`
  - report output now includes `Hint:` remediation lines for warn/fail findings
  - tests: `tests/test_doctor.py`
- [x] Add run-event export interfaces for external analysis pipelines.
  - endpoint: `GET /api/observability/runs/{run_id}/export`
  - formats: `jsonl`, `json`, `csv`
  - implementation: `gateway/routers/observability.py`
  - tests: `tests/test_gateway_routers.py`
- [x] Add auth/rate-limit guardrails for observability endpoints in multi-tenant deployments.
  - token envs: `MINI_AGENT_OBSERVABILITY_TOKEN`, `MINI_AGENT_OBSERVABILITY_AUTH_STRICT`
  - rate-limit envs: `MINI_AGENT_OBSERVABILITY_RATE_LIMIT_PER_MIN`, `MINI_AGENT_OBSERVABILITY_RATE_LIMIT_WINDOW_SECONDS`
  - implementation: `gateway/security/observability.py`, `gateway/routers/observability.py`
  - tests: `tests/test_gateway_routers.py`, `tests/test_gateway_security.py`
- [x] Add endpoint-level filtering enhancements for large run-event archives.
  - runs filters: `run_id_prefix`, `updated_after`
  - event filters: `event_type`, `level`, `contains`
  - implementation: `gateway/routers/observability.py`
  - tests: `tests/test_gateway_routers.py`

## P10 Observability Compatibility and Scale
- [x] Add event schema versioning and compatibility checks for downstream consumers.
  - event journal schema field: `schema_version`
  - compatibility API: `AgentLogger.check_event_schema_compatibility(...)`
  - compatibility gates:
    - CLI: `mini-agent replay-log --expected-schema-version <x.y.z>`
    - Gateway: `expected_schema_version` on events/replay/export endpoints
  - implementation: `mini_agent/logger.py`, `mini_agent/cli.py`, `gateway/routers/observability.py`
  - tests: `tests/test_event_schema.py`, `tests/test_logger_events.py`, `tests/test_gateway_routers.py`
- [x] Add asynchronous export jobs for very large run archives.
  - endpoints:
    - `POST /api/observability/exports`
    - `GET /api/observability/exports/{job_id}`
    - `GET /api/observability/exports/{job_id}/download`
  - implementation: `gateway/routers/observability.py`
  - job behavior: in-memory queue + background worker + artifact output (`jsonl/json/csv`)
  - tests: `tests/test_gateway_routers.py`
- [x] Add observability endpoint auth integration with gateway token policy profiles.
  - auth profile env: `MINI_AGENT_OBSERVABILITY_AUTH_PROFILE` (`inherit_gateway` / `observability_only` / `gateway_only`)
  - gateway state wiring: `gateway/core/app.py` (`gateway_auth_token`, `gateway_auth_strict`)
  - implementation: `gateway/security/observability.py`
  - tests: `tests/test_gateway_security.py`
- [x] Add event schema migration tooling for legacy logs without `schema_version`.
  - migration API:
    - `AgentLogger.list_event_log_files(...)`
    - `AgentLogger.migrate_event_schema_file(...)`
  - CLI command:
    - `mini-agent migrate-event-logs --path ~/.mini-agent/log`
    - supports `--dry-run`, `--no-backup`, `--target-schema-version`, `--no-recursive`
  - implementation: `mini_agent/logger.py`, `mini_agent/cli.py`
  - tests: `tests/test_event_schema.py`
- [x] Add export-job persistence (filesystem metadata) for process restart recovery.
  - metadata path: `<log_dir>/exports/jobs/exp_*.json`
  - behavior: load persisted jobs on demand; queued/running jobs on restart marked failed
  - implementation: `gateway/routers/observability.py`
  - tests: `tests/test_gateway_routers.py`
- [x] Add export job cleanup/retention command for ops workflows.
  - command: `mini-agent prune-export-jobs`
  - args: `--path`, `--max-age-hours`, `--max-jobs`
  - implementation: `mini_agent/cli.py`, `gateway/routers/observability.py`
- [x] Add export-job observability metrics endpoint (queue depth / failure ratio / avg duration).
  - endpoint: `GET /api/observability/exports/metrics`
  - implementation: `gateway/routers/observability.py`
  - tests: `tests/test_gateway_routers.py`
- [x] Add export worker concurrency and queue backpressure controls.
  - envs:
    - `MINI_AGENT_OBSERVABILITY_EXPORT_MAX_CONCURRENCY`
    - `MINI_AGENT_OBSERVABILITY_EXPORT_MAX_QUEUE`
  - behavior: queued scheduling with bounded concurrency + queue-full rejection (`429`)
  - implementation: `gateway/routers/observability.py`
  - tests: `tests/test_gateway_routers.py`
- [x] Add export job cancel API (`cancel queued/running`) with deterministic status transitions.
  - endpoint: `POST /api/observability/exports/{job_id}/cancel`
  - behavior:
    - queued -> `cancelled` immediately
    - running -> `cancel_requested=true`, worker exits to `cancelled`
  - implementation: `gateway/routers/observability.py`
  - tests: `tests/test_gateway_routers.py`
- [x] Add export metrics history endpoint (time-bucketed counters for SRE dashboards).
  - endpoint: `GET /api/observability/exports/metrics/history`
  - dimensions: `jobs_created`, `jobs_completed`, `jobs_failed`, `jobs_cancelled`, `average_duration_seconds`
  - implementation: `gateway/routers/observability.py`
  - tests: `tests/test_gateway_routers.py`
- [x] Add filesystem-backed queued-job replay worker (resume queued jobs after restart).
  - env: `MINI_AGENT_OBSERVABILITY_EXPORT_REPLAY_ON_RESTART`
  - behavior: persisted queued/running jobs can be replayed as queued on restart when enabled
  - implementation: `gateway/routers/observability.py`
  - tests: `tests/test_gateway_routers.py`
- [x] Add export queue persistence compaction (metadata snapshot + checksum) to reduce metadata churn.
  - snapshot file: `<log_dir>/exports/jobs/snapshot.json`
  - checksum: per-job `sha256` over compact metadata payload
  - load behavior: snapshot-first integrity validation; checksum mismatch blocks restore of tampered job metadata
  - implementation: `gateway/routers/observability.py`
  - tests: `tests/test_gateway_routers.py`

## P11 Agent Runtime Design Refactor (Now Active)
- [x] Add explicit agent execution policy model (no compatibility shim).
  - runtime models: `AgentExecutionPolicy`, `StepExecutionState`
  - implementation: `mini_agent/agent_core/engine.py`
- [x] Add per-step tool-call budget and deterministic truncation guard.
  - policy key: `max_tool_calls_per_step`
  - telemetry events: `step.tool_calls_truncated`, `step.completed`
  - implementation: `mini_agent/agent_core/engine.py`
- [x] Wire policy through CLI/Gateway/ACP runtime constructors.
  - `mini_agent/cli_interactive.py`
  - `gateway/routers/chat.py`
  - `mini_agent/acp/__init__.py`
- [x] Add unit tests for Agent loop and ACP turn budget behavior.
  - `tests/test_agent_core_execution_policy.py`
- [x] Split `Agent.run` into planner/executor/state transition units with explicit contracts.
  - planner contract: `StepPlan`
  - transition contract: `StepOutcome`, `StepTransition`
  - implementation: `mini_agent/agent_core/engine.py`
- [x] Add transition-level unit tests for planner failure and executor completion paths.
  - `tests/test_agent_core_execution_policy.py`
- [x] Add step-level failure envelope (`error_type`, `recoverable`, `retryable`) and wire run metrics payload.
  - models: `StepFailureEnvelope`, `RunExecutionMetrics`
  - events: `step.failed`, `run.failed(metrics)`
  - implementation: `mini_agent/agent_core/engine.py`
- [x] Add failure-envelope and metrics event coverage.
  - `tests/test_agent_core_execution_policy.py`
- [x] Expose agent execution policy in session/gateway inspection APIs.
  - session surfaces: `/api/sessions`, `/api/sessions/{session_id}/history`
  - chat surfaces: `/api/chat` and `GET /api/chat/stream` done payload
  - implementation: `mini_agent/session/store.py`, `mini_agent/session/persistence.py`, `gateway/routers/sessions.py`, `gateway/routers/chat.py`
- [x] Add gateway/session policy-surface coverage.
  - `tests/test_gateway_routers.py`
  - `tests/test_session_store_persistence.py`
- [x] Extract reusable planner/executor facade for ACP/Gateway parity.
  - shared runtime loop: `_run_planner_executor_loop(...)`, `run_turn(...)`
  - callback hooks: `PlannerExecutorHooks` (`on_step_plan`, `on_tool_call_start`, `on_tool_call_result`)
  - turn contract: `TurnExecutionResult`, `TurnStopReason`
  - ACP turn path now delegates to shared planner/executor facade
  - implementation: `mini_agent/agent_core/engine.py`, `mini_agent/acp/__init__.py`
- [x] Add shared-facade hook and stop-reason coverage.
  - `tests/test_agent_core_execution_policy.py`
  - `tests/test_acp.py`
- [x] Add step-failure trend aggregation endpoint for observability dashboards.
  - endpoint: `GET /api/observability/failures/step-trends`
  - dimensions: bucketed `total/planner/executor/recoverable/retryable/unique_runs` + `top_error_types`
  - filters: `run_id_prefix`, `since_utc`
  - implementation: `gateway/routers/observability.py`
- [x] Add step-failure trend endpoint coverage.
  - `tests/test_gateway_routers.py`
- [x] Add policy-drift detector (`configured_policy` vs `runtime_policy`) in session diagnostics.
  - diagnostics fields: `configured_max_steps`, `configured_max_tool_calls_per_step`, `policy_drift`, `policy_drift_fields`
  - persisted metadata now stores `configured_execution_policy` for inactive-session drift diagnostics
  - implementation: `mini_agent/session/store.py`, `mini_agent/session/persistence.py`
- [x] Extend policy-drift diagnostics into gateway/session inspection payload flags.
  - `/api/sessions` and `/api/sessions/{session_id}/history` now expose drift diagnostics fields
  - implementation: `gateway/routers/sessions.py`
  - tests: `tests/test_gateway_routers.py`, `tests/test_session_store_persistence.py`
- [x] Add trend endpoint support for `phase` and `error_type` query filters for targeted SRE dashboards.
  - endpoint: `GET /api/observability/failures/step-trends`
  - added filters: `phase`, `error_type` (case-insensitive)
  - implementation: `gateway/routers/observability.py`
  - tests: `tests/test_gateway_routers.py`
- [x] Expose policy-drift diagnostics in chat response surfaces (`/api/chat` + stream done payload).
  - fields: `configured_max_steps`, `configured_max_tool_calls_per_step`, `policy_drift`, `policy_drift_fields`
  - implementation: `gateway/routers/chat.py`
  - tests: `tests/test_gateway_routers.py`
- [x] Add drift-focused health counters to observability diagnostics for quick operator triage.
  - endpoint: `GET /api/observability/health`
  - counters: `policy_drift_active_sessions`, `policy_drift_sessions`, `policy_drift_ratio`
  - implementation: `gateway/routers/observability.py`
  - tests: `tests/test_gateway_routers.py`
- [x] Add session-list filtering options for `policy_drift=true/false` triage workflows.
  - endpoint: `GET /api/sessions`
  - query filter: `policy_drift` (`true`/`false`)
  - implementation: `gateway/routers/sessions.py`
  - tests: `tests/test_gateway_routers.py`
- [x] Add drift summary surfaces in run/session listings for faster triage.
  - run listing (`GET /api/observability/runs`) now includes:
    - `policy_drift_active_sessions`, `policy_drift_sessions`, `policy_drift_ratio`
  - session listing (`GET /api/sessions`) now includes:
    - `policy_drift_field_count`, `policy_drift_summary`
  - implementation: `gateway/routers/observability.py`, `gateway/routers/sessions.py`
  - tests: `tests/test_gateway_routers.py`
- [x] Add trend response context counters for filtered dashboard views.
  - endpoint: `GET /api/observability/failures/step-trends`
  - fields: `matched_failures`, `filtered_out_failures`
  - implementation: `gateway/routers/observability.py`
  - tests: `tests/test_gateway_routers.py`
- [x] Add health diagnostics drilldown field for top drifted session IDs.
  - endpoint: `GET /api/observability/health`
  - field: `top_policy_drift_session_ids`
  - implementation: `gateway/routers/observability.py`
  - tests: `tests/test_gateway_routers.py`

## P12 Memory Core (Mini Kickoff)
- [x] Add mini STM/LTM memory core baseline.
  - `mini_agent/memory/engram.py`
  - `mini_agent/memory/memoria_engine.py`
  - tests: `tests/test_memory_core_baseline.py`
- [x] Add memory file discovery and append baseline (`GEMINI.md` / `MEMORY.md`).
  - `mini_agent/memory/memory_files.py`
  - `mini_agent/memory/__init__.py`
  - tests: `tests/test_memory_core_baseline.py`
- [x] Add MemoryTool self-save integration in runtime tool path.
  - hierarchical anchor discovery via `discover_memory_layout(...)`
  - `record_note` supports optional `topic` tag for structured recall
  - implementation: `mini_agent/tools/note_tool.py`
  - tests: `tests/test_note_tool.py`
- [x] Add FTS5-first session search baseline with router diagnostics hooks.
  - core index: `mini_agent/memory/session_search.py` (`fts5` + `like` fallback)
  - persistence integration: `mini_agent/session/persistence.py` (save/delete/cleanup sync)
  - store API: `mini_agent/session/store.py` (`search_sessions`, `session_search_stats`)
  - gateway endpoint: `GET /api/sessions/search`
  - observability health diagnostics:
    - `session_search_backend`, `session_search_indexed_sessions`, `session_search_indexed_messages`
  - implementation: `gateway/routers/sessions.py`, `gateway/routers/observability.py`
  - tests: `tests/test_session_search.py`, `tests/test_session_store_persistence.py`, `tests/test_gateway_routers.py`
- [x] Add bounded two-phase consolidation baseline (phase1/phase2/scheduler + CLI).
  - phase1 extraction + artifact store: `mini_agent/memory/consolidation_phase1.py`
  - phase2 merge + watermark: `mini_agent/memory/consolidation_phase2.py`
  - scheduler lease/backoff skeleton: `mini_agent/memory/consolidation_scheduler.py`
  - pipeline facade: `mini_agent/memory/consolidation.py`
  - CLI entry: `mini-agent consolidate-memory`
  - tests: `tests/test_memory_consolidation.py`
- [x] Add consolidated-memory relevance retrieval baseline (side-query ranking + drift check).
  - relevance ranker: `mini_agent/memory/relevance.py`
  - persistence/store integration:
    - `mini_agent/session/persistence.py`
    - `mini_agent/session/store.py`
  - gateway endpoint: `GET /api/sessions/memory/relevance`
  - implementation: `gateway/routers/sessions.py`
  - tests: `tests/test_memory_relevance.py`, `tests/test_session_store_persistence.py`, `tests/test_gateway_routers.py`
- [x] Add user modeling baseline (provider abstraction + builtin profile provider + tool surface).
  - provider interface: `mini_agent/memory/memory_provider.py`
  - builtin provider: `mini_agent/memory/builtin_memory.py`
  - user modeling tool: `mini_agent/tools/user_modeling.py`
  - runtime wiring: `mini_agent/runtime/tooling.py`
  - tests: `tests/test_user_modeling.py`, `tests/test_note_tool.py`
- [x] Add provider config minimal schema/normalization baseline (P13 T1.1).
  - provider config model + catalog:
    - `mini_agent/model_manager/provider.py`
    - `mini_agent/model_manager/__init__.py`
  - capabilities:
    - custom provider schema (`id/name/api_type/api_base/api_key/models/...`)
    - validation + normalization (`api_base`, `models`, `headers`, `timeout`)
    - redacted output for safe diagnostics
  - tests: `tests/test_provider_config.py`
- [x] Add provider proxy-routing baseline with model mapping (P13 T1.2).
  - mapper + selector:
    - `mini_agent/model_manager/model_mapper.py`
    - `mini_agent/model_manager/runtime.py`
  - capabilities:
    - request-model to provider-model mapping (exact/partial/default fallback)
    - enabled-provider selection by mapping quality + priority
    - runtime catalog route fallback to existing `config.llm` path when unavailable
  - runtime wiring:
    - `mini_agent/cli_interactive.py`
    - `gateway/routers/chat.py`
    - `mini_agent/acp/__init__.py`
  - tests: `tests/test_model_mapper.py`, `tests/test_model_routing_runtime.py`
- [x] Add three-state circuit-breaker baseline with hot-update behavior (P13 T1.3).
  - core implementation:
    - `mini_agent/model_manager/circuit_breaker.py`
  - capabilities:
    - states: `closed` / `open` / `half_open`
    - transitions: threshold-open, timeout-probe, half-open success-close, half-open failure-reopen
    - hot-update config without state reset
    - statistics: consecutive failure count, success/failure timestamps, error-rate snapshot
  - tests: `tests/test_circuit_breaker.py`
- [x] Add provider health monitoring baseline (P13 T1.4).
  - core implementation:
    - `mini_agent/model_manager/health_monitor.py`
    - `mini_agent/model_manager/runtime.py`
  - dashboard APIs:
    - `gateway/routers/model_manager.py`
    - `gateway/core/app.py`
    - `gateway/routers/__init__.py`
  - capabilities:
    - provider health snapshots (`status/error_rate/consecutive_failures`)
    - provider stats view with breaker + redacted config
    - runtime route/success/failure counters
  - tests: `tests/test_health_monitor.py`, `tests/test_model_manager_router.py`
- [x] Add provider failover baseline with error classification (P13 T1.5).
  - core implementation:
    - `mini_agent/model_manager/error_classifier.py`
    - `mini_agent/model_manager/failover.py`
  - routing/runtime integration:
    - `mini_agent/model_manager/model_mapper.py`
    - `mini_agent/model_manager/runtime.py`
    - `mini_agent/cli_interactive.py`
    - `gateway/routers/chat.py`
    - `mini_agent/acp/__init__.py`
  - capabilities:
    - ordered provider candidate chain (preferred-first + global fallback)
    - breaker-aware candidate filtering
    - per-request provider failover with failure aggregation
    - automatic health/breaker success-failure reporting
  - tests: `tests/test_model_failover.py`, `tests/test_error_classifier.py`, `tests/test_model_routing_runtime.py`
- [x] Add request rectifier baseline with protocol conversion helpers (P13 T1.6).
  - core implementation:
    - `mini_agent/model_manager/rectifier.py`
  - integration:
    - `mini_agent/llm/openai_client.py`
    - `mini_agent/llm/anthropic_client.py`
    - `mini_agent/model_manager/__init__.py`
  - capabilities:
    - thinking signature normalization (strip invalid/unsupported signatures by default)
    - optional thinking budget injection (`MINI_AGENT_THINKING_BUDGET_TOKENS`)
    - cache-control injection for Anthropic-compatible payload blocks
    - protocol conversion helpers:
      - OpenAI -> Anthropic
      - Anthropic -> OpenAI
      - OpenAI -> Gemini (minimal content mapping)
    - runtime counters:
      - total/openai/anthropic rectified-request counts
      - thinking budget injection count
      - cache injection count
      - thinking signature strip count
      - protocol conversion counts
  - observability integration:
    - `gateway/routers/observability.py` (`GET /api/observability/health`)
  - tests: `tests/test_request_rectifier.py`
- [x] Add agent-core execution submission-loop baseline with turn snapshot isolation (P14 T2.1).
  - core implementation:
    - `mini_agent/agent_core/context/loop_context.py`
    - `mini_agent/agent_core/execution/scheduler.py`
    - `mini_agent/agent_core/execution/agent_loop.py`
    - `mini_agent/agent_core/execution/__init__.py`
  - capabilities:
    - queue-based event channel (`UserInput`, `Interrupt`, `ExecApproval`, `Compact`, `DropMemories`)
    - per-turn immutable context snapshot with independent policy
    - scheduler state transitions (`validating` -> `scheduled` -> `executing` -> terminal)
    - immediate interrupt dispatch (cancel event) + queued interrupt audit event
  - tests: `tests/test_agent_core_execution_loop.py`
- [x] Add Windows sandbox baseline with restricted-token policy guards (P14 T2.2).
  - core implementation:
    - `mini_agent/agent_core/execution/sandbox/network.py`
    - `mini_agent/agent_core/execution/sandbox/windows.py`
    - `mini_agent/agent_core/execution/sandbox/manager.py`
    - `mini_agent/agent_core/execution/sandbox/__init__.py`
    - `mini_agent/agent_core/execution/__init__.py`
  - capabilities:
    - domain-level network policy modes (`allow_all`, `deny_all`, `allowlist`, `blocklist`)
    - elevated command blocking baseline (`RunAs`, execution policy mutation, service/registry/shutdown paths)
    - workspace `cwd` boundary validation for sandboxed execution
    - sandbox metadata/env injection (`MINI_AGENT_SANDBOX_*`) for downstream runtime visibility
    - backend selector (`workspace + windows => windows_restricted_token`; otherwise passthrough)
  - tests: `tests/test_agent_core_execution_sandbox.py`
- [x] Add declarative tool system baseline with runtime adapter path (P14 T2.3).
  - core implementation:
    - `mini_agent/agent_core/execution/tools/attributes.py`
    - `mini_agent/agent_core/execution/tools/invocation.py`
    - `mini_agent/agent_core/execution/tools/builder.py`
    - `mini_agent/agent_core/execution/tools/runtime_adapter.py`
    - `mini_agent/agent_core/execution/tools/__init__.py`
    - `mini_agent/agent_core/execution/__init__.py`
  - capabilities:
    - schema-first `DeclarativeTool` contract (`name/description/schema/kind/attributes`)
    - invocation-time schema validation + execution confirmation strategy
    - tool location extraction + output size cap for stable context usage
    - runtime adapter for legacy `Tool` execution path without compatibility shell layering
    - inferred attributes for existing built-in tools (`read/write/edit/bash/...`) to speed adoption
  - tests: `tests/test_agent_core_execution_tools.py`
- [x] Add multi-agent coordinator baseline with staged worker contract (P14 T2.4).
  - core implementation:
    - `mini_agent/agent_core/execution/coordinator.py`
    - `mini_agent/agent_core/execution/__init__.py`
  - capabilities:
    - staged pipeline orchestration (`research -> synthesis -> implementation -> verification`)
    - worker task/result contract with explicit stage ownership metadata
    - progress channel events (`stage started/completed/skipped`, `worker started/completed`)
    - fail-fast stage short-circuit with skipped-stage accounting
    - bounded concurrency for same-stage worker execution
  - tests: `tests/test_agent_core_execution_coordinator.py`
- [x] Add context-management baseline with layered compaction and masking (P14 T2.5).
  - core implementation:
    - `mini_agent/agent_core/context/context_compaction.py`
    - `mini_agent/agent_core/execution/output_masking.py`
    - `mini_agent/agent_core/execution/__init__.py`
  - capabilities:
    - reverse token-budget selection from newest to oldest while preserving system/user anchors
    - snip compaction for old tool outputs (tail-line retention)
    - microcompact merge for adjacent assistant responses
    - query-aware tool output masking for irrelevant old outputs
    - compaction stats payload for observability/debug usage
  - tests: `tests/test_agent_core_context_compaction.py`
- [x] Add agent-core execution MCP client baseline with declarative wrapper path (P14 T2.6).
  - core implementation:
    - `mini_agent/agent_core/execution/mcp_client.py`
    - `mini_agent/agent_core/execution/mcp_tools.py`
    - `mini_agent/agent_core/execution/__init__.py`
  - capabilities:
    - MCP discovery/connect orchestration via existing MCP transport stack
    - active-server tool listing and direct invocation by `server_name + tool_name`
    - namespaced declarative MCP tool registry (`mcp_<server>_<tool>`)
    - conservative MCP tool attributes (`READ` for resource tools, `NETWORK` for remote execution tools)
    - deterministic aliasing to avoid cross-server tool name collisions
  - tests: `tests/test_agent_core_execution_mcp_client.py`
- [x] Add layered permission baseline with approval cache and escalation (P14 T2.7).
  - core implementation:
    - `mini_agent/agent_core/execution/permissions/policy.py`
    - `mini_agent/agent_core/execution/permissions/approval.py`
    - `mini_agent/agent_core/execution/permissions/__init__.py`
    - `mini_agent/agent_core/execution/__init__.py`
  - capabilities:
    - ordered ask/allow/deny policy rules (`tool_pattern`, optional `ToolKind`)
    - read-only default-allow guard and full-access bypass mode
    - invocation fingerprint cache for repeated approval decisions
    - escalation request path for denied high-impact tool classes
    - typed approval outcomes (`reason`, `from_cache`, `can_escalate`, `escalated`)
  - tests: `tests/test_agent_core_execution_permissions.py`
- [x] Add agent-core routing skeleton baseline with priority resolver (P15 T3.1).
  - core implementation:
    - `mini_agent/agent_core/routing.py`
    - `mini_agent/agent_core/__init__.py`
  - capabilities:
    - deterministic priority routing (`peer -> parent -> wildcard -> guild -> roles -> team -> account -> channel -> default`)
    - route bindings with explicit scope keys and fallback default route
    - resolver cache for repeated routing contexts (`max_cache_entries`)
  - tests: `tests/test_agent_core_routing.py`
- [x] Add skills-platform baseline with progressive disclosure and runtime bridge (P15 T3.2).
  - core implementation:
    - `mini_agent/agent_core/skills/loader.py`
    - `mini_agent/agent_core/skills/registry.py`
    - `mini_agent/agent_core/skills/eligibility.py`
    - `mini_agent/agent_core/skills/__init__.py`
    - `mini_agent/agent_core/__init__.py`
    - `mini_agent/tools/skill_tool.py`
  - capabilities:
    - SKILL.md parsing with YAML frontmatter extraction
    - multi-source discovery (`builtin`, `workspace`, `plugin`, `remote`) with source-priority conflict resolution
    - progressive disclosure tiers:
      - Tier 1 metadata listing for prompt injection
      - Tier 2 full instruction loading
      - Tier 3 helper-file listing/read with root-bound path safety
    - eligibility checks (`os`, required binaries, required env vars)
    - runtime bridge exposing `get_skill` / `list_skills` / metadata prompt contract
  - tests:
    - `tests/test_agent_core_skills.py`
    - `tests/test_skill_tool.py`
    - `tests/test_skill_loader.py`
    - `tests/test_markdown_links.py`
- [x] Add cron baseline with bounded queue and isolated execution skeleton (P15 T3.3).
  - core implementation:
    - `mini_agent/agent_core/cron/scheduler.py`
    - `mini_agent/agent_core/cron/isolated_run.py`
    - `mini_agent/agent_core/cron/delivery.py`
    - `mini_agent/agent_core/cron/__init__.py`
    - `mini_agent/agent_core/__init__.py`
  - capabilities:
    - schedule types: `at` / `every` / `cron` (five-field expression parser)
    - bounded queue with backpressure accounting (`dropped_runs`)
    - grace-window late-run skip and fast-forward behavior
    - isolated run executor contract with pluggable handler
    - delivery routing (`none` / `announce` / `webhook`) with typed outcome
    - tick-run cycle APIs (`tick`, `run_pending`, `tick_and_run`)
  - tests:
    - `tests/test_agent_core_cron.py`
- [x] Add sub-agent delegation baseline with bounded depth/concurrency controls (P15 T3.4).
  - core implementation:
    - `mini_agent/agent_core/delegation.py`
    - `mini_agent/agent_core/__init__.py`
  - capabilities:
    - delegation request/task/result contract for isolated sub-agent execution
    - max-depth guard (`parent_depth + 1`) with deterministic limit rejection
    - bounded parallel delegation batch execution (`max_concurrent`)
    - blocked tool filtering for child allowlists (`delegate/clarify/memory/send_message`)
    - global delegation state snapshot/restore and progress events
    - optional delegation hook callback for memory/provider integration
  - tests:
    - `tests/test_agent_core_delegation.py`
- [x] Add session baseline with key/lifecycle/lineage skeleton (P15 T3.5).
  - core implementation:
    - `mini_agent/agent_core/session/session_key.py`
    - `mini_agent/agent_core/session/lifecycle.py`
    - `mini_agent/agent_core/session/lineage.py`
    - `mini_agent/agent_core/session/__init__.py`
    - `mini_agent/agent_core/__init__.py`
  - capabilities:
    - canonical session-key model (`agent/channel/peer/thread`) with parser and deterministic slug
    - full/partial/slug session-key lookup index with ambiguous-query rejection
    - lifecycle reset policies (`none/daily/idle/both`) with `ensure_active`/`touch`/`reset`
    - lineage graph store with parent-child chain traversal and cycle guard
  - tests:
    - `tests/test_agent_core_session.py`
- [x] Add browser baseline with lifecycle/CDP/tool skeleton (P15 T3.6).
  - core implementation:
    - `mini_agent/agent_core/browser/chrome.py`
    - `mini_agent/agent_core/browser/cdp.py`
    - `mini_agent/agent_core/browser/tool.py`
    - `mini_agent/agent_core/browser/__init__.py`
    - `mini_agent/agent_core/__init__.py`
  - capabilities:
    - chrome profile lifecycle manager (`register/start/stop/health`) with pluggable handlers
    - navigation policy guard for CDP target creation (scheme/domain/private-host controls)
    - CDP baseline APIs: `navigate`, `list_tabs`, `capture_screenshot`, `act`
    - agent-facing browser toolkit: `browser_profiles`, `browser_tabs`, `browser_navigate`, `browser_screenshot`, `browser_act`
  - tests:
    - `tests/test_agent_core_browser.py`
- [x] Add DM pairing security baseline with store/policy skeleton (P15 T3.7).
  - core implementation:
    - `mini_agent/agent_core/security/pairing.py`
    - `mini_agent/agent_core/security/policy.py`
    - `mini_agent/agent_core/security/__init__.py`
    - `mini_agent/agent_core/__init__.py`
  - capabilities:
    - per-channel pairing store with file persistence and lock-file coordination
    - human-friendly 8-char pairing codes, 1-hour TTL pruning, max-pending guardrail
    - approval path that promotes paired sender ids into channel allowlist
    - dm/group policy resolver (`open/disabled/allowlist/pairing`) with pairing-store merge
  - tests:
    - `tests/test_agent_core_security_pairing.py`
- [x] Add Docling parse baseline with document-parser subprogram skeleton (P16 T4.1).
  - core implementation:
    - `mini_agent/tools/docling_parse.py`
    - `mini_agent/tools/__init__.py`
    - `subprograms/document_parser/manifest.json`
    - `subprograms/document_parser/main.py`
    - `subprograms/document_parser/gateway/router.py`
  - capabilities:
    - typed document parse facade with output modes (`markdown`/`html`/`json`)
    - binary parse adapter injection and text-file fallback for local no-dependency runs
    - batch parse endpoint with per-item success/error envelope
    - standalone subprogram service with `/api/document-parser` router skeleton
  - tests:
    - `tests/test_docling_parse_tool.py`
    - `tests/test_document_parser_router.py`
- [x] Add knowledge-base query baseline with knowledge-base subprogram skeleton (P16 T4.2).
  - core implementation:
    - `mini_agent/tools/knowledge_base.py`
    - `mini_agent/tools/__init__.py`
    - `subprograms/knowledge_base/manifest.json`
    - `subprograms/knowledge_base/main.py`
    - `subprograms/knowledge_base/gateway/router.py`
  - capabilities:
    - native knowledge-base query tool backed by the built-in lightweight RAG store
    - explicit `knowledge_base_query` tool plus gateway query/ingest endpoints
    - standalone knowledge-base subprogram exposing query/ingest/health endpoints
  - tests:
    - `tests/test_knowledge_base_tool.py`
    - `tests/test_knowledge_base_router.py`
- [x] Add multi-engine web-search baseline with provider adapter skeleton (P16 T4.3).
  - core implementation:
    - `mini_agent/tools/web_search.py`
    - `mini_agent/tools/__init__.py`
  - capabilities:
    - provider adapter model (`searxng` / `brave` / `google` / `duckduckgo`)
    - deterministic merge + URL dedupe + limit slicing across engines
    - typed search response envelope with per-engine error aggregation
  - tests:
    - `tests/test_web_search_tool.py`
- [x] Add memory-manager subprogram baseline with memory browse/search/export APIs (P16 T4.4).
  - core implementation:
    - `subprograms/memory_manager/manifest.json`
    - `subprograms/memory_manager/main.py`
    - `subprograms/memory_manager/gateway/router.py`
  - capabilities:
    - memory summary endpoint for `MEMORY.md` + daily note files
    - append/search/export endpoints on top of existing markdown memory model
    - export modes: `jsonl` and grouped `markdown`
  - tests:
    - `tests/test_memory_manager_router.py`
- [x] Historical browser-surface slice (P17 T5.1/T5.2).
  - historical note:
    - browser `WebUI / OpenWebUI` and the React `agent_studio` frontend were exploratory surfaces from an earlier phase
    - they were hard-removed from the active codebase in P32.35 and must not be used as current implementation targets
  - retained active code from that period:
    - `src/apps/agent_studio_gateway/main.py`
    - `src/apps/agent_studio_gateway/ops_router.py`
  - retained capabilities:
    - `/api/v1/ops/providers` CRUD + provider health contract
    - `/api/v1/ops/memory/*` operator APIs
    - route auth and allowed-root boundary checks
  - retained tests:
    - `tests/test_agent_studio_gateway_ops_router.py`
    - `tests/test_agent_studio_gateway_api_v1.py`
- [x] Add historical remote-channel completion baseline (P17 T5.3).
  - core implementation:
    - historical QQ package baseline later consolidated into `src/apps/qqbot_channel/`
    - historical non-QQ channel trees later removed in `P32.60`:
      - `src/channels/types/`
      - `src/channels/wechat/`
      - `src/mini_agent/channels/`
      - `src/gateway/channels/`
    - `scripts/archive/run_qqbot_channel.ps1`
    - `scripts/archive/run_wechat_channel.ps1`
  - capabilities retained today:
    - QQ forwards `channel_type/conversation_id/sender_id` to Gateway and reuses shared session/application semantics
    - terminal-first consolidation replaced per-channel launchers with `uv run mini-agent stack up` / `scripts/start_runtime_stack.ps1`
  - tests:
    - `tests/test_gateway_routers.py` (sender-specific conversation binding coverage)
- [x] Keep the active remote hardening slice on QQ only (P17 T5.3 hardening, locked by `P32.60`).
  - core implementation:
    - `src/apps/qqbot_channel/bot.mjs`
    - `src/apps/qqbot_channel/gateway_io.mjs`
    - `src/apps/qqbot_channel/guardrails.mjs`
    - `src/apps/qqbot_channel/smoke_runner.mjs`
    - `src/apps/qqbot_channel/.env.example`
  - capabilities:
    - gateway token passthrough for the active QQ remote adapter (`Authorization` bearer forwarding)
    - workspace boundary + message guardrails for remote runtime safety
    - QQ synthetic message smoke path (`processSmokeMessage`) for deterministic no-upstream validation
  - tests:
    - `npm run smoke --prefix src/apps/qqbot_channel`
    - `python scripts/test_stable.py`

## Current Baseline (Rechecked)
- [x] Stable test command passes: `317 passed, 30 deselected`
- [x] MCP Windows file-handle issue no longer reproduces in current stable set
- [x] ACP missing-session compatibility fix still effective
- [x] P4 control-plane slice completed and validated
- [x] P5 MCP/config slice completed and validated
- [x] P6 runtime safety/policy slice completed and validated
- [x] P7 plugin/memory slice completed and validated
- [x] P8 observability/operations slice completed and validated
- [x] P9 retention/rotation slice completed and validated
- [x] P9 API observability slice completed and validated
- [x] P9 doctor deep-probe slice completed and validated
- [x] P9 export/guardrails/filter slice completed and validated
- [x] P10 schema versioning/compatibility slice completed and validated
- [x] P10 async export scale slice completed and validated
- [x] P10 auth policy convergence slice completed and validated
- [x] P10 legacy schema migration tooling slice completed and validated
- [x] P10 export durability slice completed and validated
- [x] P10 export ops workflow slice completed and validated
- [x] P10 export queue metrics slice completed and validated
- [x] P10 export throughput control slice completed and validated
- [x] P10 export cancel/control-plane slice completed and validated
- [x] P10 export metrics-history slice completed and validated
- [x] P10 export restart-replay slice completed and validated
- [x] P10 export metadata compaction/checksum slice completed and validated
- [x] P11 execution-policy kickoff slice completed and validated
- [x] P11 planner/executor/transition split slice completed and validated
- [x] P11 step-failure-envelope/metrics slice completed and validated
- [x] P11 policy-surface exposure slice completed and validated
- [x] P11 shared planner/executor facade slice completed and validated
- [x] P11 step-failure trend aggregation slice completed and validated
- [x] P11 policy-drift detector slice completed and validated
- [x] P11 policy-drift session-surface slice completed and validated
- [x] P11 step-failure trend filter slice completed and validated
- [x] P11 policy-drift chat-surface slice completed and validated
- [x] P11 drift-health-counter slice completed and validated
- [x] P11 session drift-filter slice completed and validated
- [x] P11 drift-triage summary/context slice completed and validated
- [x] P12 mini memory-core kickoff slice completed and validated
- [x] P12 memory self-save integration slice completed and validated
- [x] P12 session-search baseline slice completed and validated
- [x] P12 two-phase consolidation baseline slice completed and validated
- [x] P12 relevance-memory-retrieval slice completed and validated
- [x] P12 user-modeling baseline slice completed and validated
- [x] P13 provider-config baseline slice completed and validated
- [x] P13 proxy-routing baseline slice completed and validated
- [x] P13 circuit-breaker baseline slice completed and validated
- [x] P13 health-monitoring baseline slice completed and validated
- [x] P13 failover baseline slice completed and validated
- [x] P13 request-rectifier baseline slice completed and validated
- [x] P14 event-loop baseline slice completed and validated
- [x] P14 Windows sandbox baseline slice completed and validated
- [x] P14 declarative tool-system baseline slice completed and validated
- [x] P14 multi-agent coordinator baseline slice completed and validated
- [x] P14 context-management baseline slice completed and validated
- [x] P14 MCP-client baseline slice completed and validated
- [x] P14 permission baseline slice completed and validated
- [x] P15 routing baseline slice completed and validated
- [x] P15 skills baseline slice completed and validated
- [x] P15 cron baseline slice completed and validated
- [x] P15 delegation baseline slice completed and validated
- [x] P15 session baseline slice completed and validated
- [x] P15 browser baseline slice completed and validated
- [x] P15 pairing baseline slice completed and validated
- [x] P16 docling baseline slice completed and validated
- [x] P16 maxkb baseline slice completed and validated
- [x] P16 web-search baseline slice completed and validated
- [x] P16 memory-manager baseline slice completed and validated
- [x] P17 historical browser-surface slices completed, later hard-removed in P32.35
- [x] P17 gateway ops router capabilities retained after browser-surface removal
- [x] P17 historical remote-channel baseline slice completed and validated
- [x] P17 active QQ remote hardening slice completed and validated

## P18 Hard Refactor (Completed, No Compatibility Shell)

- [x] P18.0 Architecture baseline and API contract freeze
- [x] P18.1 Interface layer cut-in (router/application/domain/infra separation)
- [x] P18.2 Main-agent runtime consolidation (single active runtime)
- [x] P18.3 Novel subprogram rebinding to dedicated agent profile
- [x] P18.4 Channel unification (remote ingress -> main-agent only; QQ remains the active adapter)
- [x] P18.5 Frontend contract-client refactor (`/api/v1/*` only)
- [x] P18.6 Dev process manager hardening (one frontend + one backend)
- [x] P18.7 Hard delete legacy paths (no compatibility shell retained)
- [x] P18.8 Validation gate and release readiness

Details and execution order: `docs/archive/P18_HARD_REFACTOR_EXECUTION_PLAN.md`

## P19 Agent-Team Rollout (Kickoff)

- [x] Add runtime diagnostics surface to system health contract (`/api/v1/system/health`).
  - fields: `mode`, `active_sessions`, `max_active_sessions`, `available_session_slots`, `reserved_team_slots`, `workspace_application_required`, `main_workspace_dir`
  - implementation:
    - `src/mini_agent/runtime/main_agent_runtime_manager.py`
    - `src/mini_agent/interfaces/system.py`
    - `src/apps/agent_studio_gateway/main.py`
- [x] Add team-mode workspace-session reuse guardrail for requests without `session_id`.
  - behavior: reuse latest session for same workspace to prevent accidental workspace-local fan-out
  - implementation:
    - `src/mini_agent/runtime/main_agent_runtime_manager.py`
- [x] Add coverage for diagnostics and team concurrency guardrails.
  - tests:
    - `tests/test_main_agent_surface_service.py`
    - `tests/test_agent_studio_gateway_api_v1.py`
  - validation:
    - `pytest -q tests/test_main_agent_surface_service.py tests/test_agent_studio_gateway_api_v1.py`
    - `python scripts/test_stable.py`
- [x] Add deterministic P19 runtime matrix for `single_main` + `team` modes.
  - tests:
    - `tests/test_p19_runtime_matrix.py`
  - runner:
    - `scripts/ci/p19_runtime_matrix.py`
  - latest report:
    - `workspace/p19_matrix/p19_runtime_matrix_20260407T050342Z.md` (`overall: PASS`)
- [x] Expose team-mode runtime counters in Studio Ops/API diagnostics views.
  - API:
    - `GET /api/v1/ops/diagnostics/runtime`
  - implementation:
    - `src/apps/agent_studio_gateway/main.py`
    - historical browser-client mapping was removed in P32.35
  - smoke:
    - `scripts/ci/studio_ops_smoke.py` (`[3/8] runtime diagnostics`)
- [x] Define and enforce release promotion checklist policy.
  - policy:
    - deterministic gate = mandatory (blocking)
    - Remote no-dry-run = advisory (non-blocking, tracked)
  - implementation:
    - `scripts/ci/release_promotion_checklist.py`
    - `src/mini_agent/dev/release_promotion_checklist.py`
  - tests:
    - `tests/test_release_promotion_checklist.py`
  - latest evidence:
    - `workspace/release_promotion/release_promotion_20260407T055638Z.md` (`Decision: READY`)
    - `workspace/release_gate/release_gate_deterministic_20260407T055638Z.md` (`Overall: PASS`)
- [x] Stage-B guardrails: expose queue saturation/workspace conflict diagnostics in team-mode ops contract.
  - added diagnostics fields:
    - `team_saturation_rejections`
    - `team_workspace_conflict_rejections`
  - implementation:
    - `src/mini_agent/runtime/main_agent_runtime_manager.py`
    - `src/mini_agent/interfaces/system.py`
    - browser-client DTO/view wiring was removed in P32.35
    - `scripts/ci/studio_ops_smoke.py`
  - tests:
    - `tests/test_main_agent_surface_service.py`
    - `tests/test_agent_studio_gateway_api_v1.py`
    - `tests/test_agent_studio_gateway_ops_router.py`
    - `tests/test_p19_runtime_matrix.py`
  - latest deterministic gate:
    - `workspace/release_gate/release_gate_deterministic_20260407T055638Z.md` (`Overall: PASS`)
- [x] Team-mode operator runbook: publish enable/rollback steps and smoke recipe for `single_main` <-> `team`.
  - doc:
    - `docs/archive/P19_TEAM_MODE_OPERATOR_RUNBOOK.md`
  - includes:
    - mode switch envs (`MINI_AGENT_RUNTIME_MODE`, `MINI_AGENT_MAIN_WORKSPACE`, `MINI_AGENT_TEAM_MAX_AGENTS`)
    - rollback steps to `single_main`
    - runtime diagnostics interpretation and response guidance
- [x] Release automation integration: wire promotion checklist into CI/release handoff pipeline.
  - workflow:
    - `.github/workflows/ci.yml` (`release-handoff` workflow_dispatch job)
  - workflow_dispatch inputs:
    - `run_advisory_no_dry_run` (optional bool)
    - `advisory_adapter_base_url` (optional string)
    - `advisory_timeout` (optional string)
    - `run_weekly_rollout_review_strict` (optional bool)
  - checklist command paths:
    - deterministic + advisory (only when an external remote dry-run is explicitly configured)
    - deterministic-only fallback (default path):
      - `python scripts/ci/release_promotion_checklist.py --studio-token studio-release-handoff-token --skip-advisory`
  - artifact upload:
    - `workspace/release_promotion/release_promotion_*.md`
    - `workspace/release_gate/release_gate_deterministic_*.md`
    - `workspace/release_gate/release_gate_nodryrun_*.md` (advisory path)
    - `workspace/release_gate/studio_ops_runtime_*.json` (runtime trend snapshots)
    - `workspace/p19_matrix/p19_runtime_matrix_*.md` (strict weekly path)
    - `workspace/p19_rollout/p19_weekly_rollout_*.md` (strict weekly path)
    - `workspace/p19_rollout/p19_weekly_rollout_*.json` (strict weekly path)
  - optional strict weekly review path:
    - run matrix: `python scripts/ci/p19_runtime_matrix.py`
    - run strict review: `python scripts/ci/p19_weekly_rollout_review.py --window-days 7 --target-profile stage --strict --strict-targets`
- [x] Promotion policy hardening: add dedicated CI check failing on missing deterministic gate artifact.
  - script:
    - `scripts/ci/check_deterministic_gate_artifact.py`
  - validation module:
    - `src/mini_agent/dev/deterministic_gate_artifact.py`
  - tests:
    - `tests/test_deterministic_gate_artifact.py`
  - CI step:
    - `Validate Deterministic Gate Artifact (Required)` in `.github/workflows/ci.yml`
- [x] Stage-C docs: publish external-facing team-mode rollout announcement and support FAQ.
  - docs:
    - `docs/archive/P19_TEAM_MODE_ROLLOUT_ANNOUNCEMENT.md`
    - `docs/archive/P19_TEAM_MODE_SUPPORT_FAQ.md`
  - linked operator guidance:
    - `docs/archive/P19_TEAM_MODE_OPERATOR_RUNBOOK.md`
- [x] Ops alerting policy: define thresholds and operator actions for team-mode diagnostics counters.
  - policy doc:
    - `docs/archive/P19_TEAM_MODE_ALERT_POLICY.md`
  - note:
    - historical browser UI mapping was removed in P32.35
    - retained active surfaces consume the same diagnostics via gateway contracts
  - alert levels:
    - `healthy`, `watch`, `warning`, `critical`
  - key thresholds:
    - capacity pressure (`active/max`) >= 0.80 -> watch, >= 0.95 -> critical
    - `team_saturation_rejections` >= 1 -> warning, >= 5 -> critical
    - `team_workspace_conflict_rejections` >= 1 -> warning, >= 3 -> critical
- [x] Stage-C adoption tracking: define rollout KPI dashboard and weekly review checklist.
  - docs:
    - `docs/archive/P19_STAGEC_ADOPTION_TRACKING.md`
  - automation/helper:
    - `scripts/ci/p19_weekly_rollout_review.py`
    - `src/mini_agent/dev/p19_rollout_reporting.py`
  - tests:
    - `tests/test_p19_rollout_reporting.py`
- [x] Team-mode canary cadence: formalize recurring `single_main` vs `team` matrix + deterministic gate review checkpoints.
  - doc:
    - `docs/archive/P19_TEAM_MODE_CANARY_CADENCE.md`
  - daily command bundle:
    - `python scripts/ci/p19_runtime_matrix.py`
    - `python scripts/ci/release_gate.py --start-local-gateway --studio-token studio-smoke-token`
    - `python scripts/ci/check_deterministic_gate_artifact.py`
- [x] Release readiness reporting: add weekly summary template for deterministic/advisory gate outcomes and rollback decision log.
  - template:
    - `docs/archive/P19_WEEKLY_RELEASE_READINESS_TEMPLATE.md`
  - generated weekly report now includes rollback decision log section:
    - `scripts/ci/p19_weekly_rollout_review.py`
- [x] Runtime counter trend snapshots: aggregate saturation/conflict counters into weekly rollout report.
  - runtime snapshot artifact source:
    - `scripts/ci/studio_ops_smoke.py` (`--runtime-report-file`)
    - `scripts/ci/release_gate.py` (auto-wires snapshot output)
  - aggregation:
    - `src/mini_agent/dev/p19_rollout_reporting.py`
  - surfaced in weekly report:
    - `## Runtime Counter Trends`
- [x] Environment target bands: define dev/stage/prod KPI bands for rollout operations.
  - implementation:
    - `src/mini_agent/dev/p19_rollout_reporting.py` (`RolloutTargetBands`, `evaluate_target_bands`)
  - CLI:
    - `scripts/ci/p19_weekly_rollout_review.py --target-profile <dev|stage|prod>`
  - docs:
    - `docs/archive/P19_STAGEC_ADOPTION_TRACKING.md`
- [x] Weekly delta section: compare current KPI window against previous window for faster triage.
  - weekly report section:
    - `## Weekly Delta vs Previous Window`
  - implementation:
    - `src/mini_agent/dev/p19_rollout_reporting.py`
    - `scripts/ci/p19_weekly_rollout_review.py`
  - CI strict weekly path updated:
    - `.github/workflows/ci.yml` (`--target-profile stage --strict --strict-targets`)
- [x] Runtime mode-split trend: expose single_main vs team counter view in weekly report.
  - weekly report section:
    - `## Runtime Mode Split`
  - implementation:
    - `src/mini_agent/dev/p19_rollout_reporting.py`
- [x] Target ATTENTION remediation hints: provide operator actions directly in weekly report output.
  - weekly report section:
    - `## Target Remediation Hints`
  - implementation:
    - `src/mini_agent/dev/p19_rollout_reporting.py` (`build_target_remediation_hints`)
- [x] Machine-readable weekly summary artifact: emit JSON alongside markdown weekly report.
  - script:
    - `scripts/ci/p19_weekly_rollout_review.py` (`--json-report-file`)
  - payload builder:
    - `src/mini_agent/dev/p19_rollout_reporting.py` (`build_weekly_rollout_payload`)
  - CI artifact upload:
    - `.github/workflows/ci.yml` (`workspace/p19_rollout/p19_weekly_rollout_*.json`)

## Next 3 Tasks To Start Immediately
1. Add per-KPI historical sparkline data points in JSON output for dashboard rendering.
2. Introduce `--target-profile auto` mode (derive profile from CI environment variable).
3. Add retention/cleanup helper for `workspace/p19_rollout/p19_weekly_rollout_*.{md,json}` artifacts.

## P12+ Deep Transformation (OSS Fusion Plan)

> Full details: `docs/TRANSFORMATION_PLAN.md`

### Adoption Matrix (Deep Fusion)

| Capability | Source | Adopt Type | Effort | Risk | Impact | Mini-Agent Target |
| --- | --- | --- | --- | --- | --- | --- |
| STM/LTM memory engine (Memoria) | `memoria-master` | Direct (Now) | L | M | Highest | `mini_agent/memory/memoria_engine.py` |
| Two-phase memory consolidation | `codex-main` (memories/) | Direct (Now) | L | M | High | `mini_agent/memory/consolidation.py` |
| GEMINI.md hierarchical memory | `gemini-cli-main` (context/) | Direct (Now) | M | M | High | `mini_agent/memory/memory_files.py` |
| FTS5 session search + summarization | `hermes-agent-main` (tools/) | Direct (Now) | M | M | High | `mini_agent/memory/session_search.py` |
| Relevance memory retrieval | `extracted-src` (memdir/) | Direct (Now) | M | M | High | `mini_agent/memory/relevance.py` |
| Custom Provider config (URL+key) | `cc-switch-main` (src-tauri/) | Direct (Now) | M | M | High | `mini_agent/model_manager/provider.py` |
| Circuit breaker + failover | `cc-switch-main` (proxy/) | Direct (Now) | M | L | High | `mini_agent/model_manager/circuit_breaker.py`, `mini_agent/model_manager/failover.py` |
| Request rectifier | `cc-switch-main` (proxy/) | Direct (Now) | M | M | Med | `mini_agent/model_manager/rectifier.py` |
| Agent event loop (submission loop) | `codex-main` (codex-rs/core/) | Direct (Now) | L | H | Highest | `mini_agent/agent_core/execution/agent_loop.py` |
| Windows sandbox (Restricted Token) | `codex-main` (sandboxing/) | Direct (Now) | L | H | High | `mini_agent/agent_core/execution/sandbox/windows.py` |
| DeclarativeTool pattern | `gemini-cli-main` (packages/core/tools/) | Direct (Now) | M | M | High | `mini_agent/agent_core/execution/tools/` |
| Coordinator multi-agent pattern | `extracted-src` (coordinator/) | Direct (Now) | L | H | High | `mini_agent/agent_core/execution/coordinator.py` |
| Reverse token budget compression | `gemini-cli-main` (context/) | Direct (Now) | M | M | High | `mini_agent/agent_core/context/context_compaction.py` |
| MCP full client (OAuth+3 transports) | `gemini-cli-main` (tools/mcp-client.ts) | Direct (Now) | L | M | High | `mini_agent/agent_core/execution/mcp_client.py` |
| 8-level binding routing | `openclaw-main` (src/routing/) | Direct (Now) | M | M | High | `mini_agent/agent_core/routing.py` |
| Skills platform (progressive disclosure) | `openclaw-main` + `hermes-agent-main` | Direct (Now) | M | M | High | `mini_agent/agent_core/skills/` |
| Cron + isolated agent execution | `openclaw-main` + `hermes-agent-main` | Direct (Now) | M | M | High | `mini_agent/agent_core/cron/` |
| Sub-agent delegation | `hermes-agent-main` (tools/delegate_tool.py) | Direct (Now) | M | M | High | `mini_agent/agent_core/delegation.py` |
| Browser CDP control | `openclaw-main` (extensions/browser/) | Direct (Now) | L | M | Med | `mini_agent/agent_core/browser/` |
| DM pairing security | `openclaw-main` (src/pairing/) | Direct (Now) | S | M | Med | `mini_agent/agent_core/security/pairing.py` |
| Self-learning skills | `hermes-agent-main` (tools/skill_manager/) | Direct (Now) | M | M | High | `mini_agent/agent_core/skills/self_improve.py` |

### Trim Decisions

| Excluded | Reason |
|----------|--------|
| 50+ Provider presets | Replaced with user-defined Provider (URL + key) |
| Cost calculation | No practical value |
| macOS/Linux sandbox | Windows only target |
| Multi-platform messaging | Active QQ remote adapter only |
| Feature flags / telemetry / session replay | Enterprise overhead |
| Voice transcription | Requires STT model, extra cost |
