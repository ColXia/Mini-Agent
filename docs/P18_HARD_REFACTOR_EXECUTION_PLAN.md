# P18 Hard Refactor Execution Plan (No Compatibility Shell)

> **状态**: ✅ 活跃
> **最后更新**: 2026-04-06
> **维护者**: Mini-Agent Core Refactor
> **当前状态**: 已完成
> **文档索引**: [DOCS_INDEX.md](./DOCS_INDEX.md)

## 1. Hard Constraints

This track is a hard refactor.

1. No compatibility shell, no dual-path compatibility bridge.
2. One backend host process only.
3. One main agent runtime only.
4. Novel generation is a subprogram with its own agent profile, managed by the main backend.
5. QQ Bot and WeChat Bot route to main agent only.
6. Frontend and backend are split for hot development, but process management must enforce one frontend and one backend.

## 2. Target Architecture

### 2.1 Runtime topology

1. `studio-web` (frontend dev/build app).
2. `studio-api` (single backend host, unified API surface).
3. `main-agent` runtime (single active runtime in host process).
4. `novel-agent-profile` (separate config/profile, invoked by backend service layer).
5. `channel-ingress` (QQ/WeChat adapters -> main-agent entry).

### 2.2 Backend layering (mandatory interface layer)

1. Router Layer: request parsing, auth, response envelope only.
2. Interface Layer: DTOs/contracts/use-case ports. No infra logic.
3. Application Layer: use-cases/orchestration.
4. Domain Layer: session/agent/channel domain logic.
5. Infrastructure Layer: provider, persistence, channel adapters.

## 3. Structural Decisions

### 3.1 Frontend/Backend split

1. Frontend consumes `/api/v1/*` only.
2. Frontend must not import backend internals or rely on private payloads.
3. Vite dev server proxies only one backend target.

### 3.2 Agent boundaries

1. `main-agent`: workspace chat, system tasks, QQ/WeChat ingress.
2. `novel-agent-profile`: novel-specific prompt/tools/memory/provider policy.
3. Novel operations are triggered through backend use-cases, not direct channel routing.

### 3.3 Hard-cut migration rule

1. Replace old routes/modules directly.
2. Remove deprecated modules after replacement in the same phase.
3. Do not keep fallback compatibility handlers.

## 4. Execution Backlog

## P18.0 Architecture Baseline and Contract Freeze

- [x] Freeze API namespace to `/api/v1/*`.
- [x] Publish API contract skeleton (OpenAPI + typed DTOs).
- [x] Define strict response envelope and error code taxonomy.
- [x] Mark old ad-hoc routes for deletion list.

## P18.1 Interface Layer Introduction (Hard Cut)

- [x] Add interface modules for `agent`, `novel`, `channel`, `system`, `ops`.
- [x] Move Studio Ops router input/output models into interface DTOs (`mini_agent/interfaces/ops.py`).
- [x] Move main-agent router orchestration to application use-cases (`mini_agent/application/main_agent_gateway_use_cases.py`).
- [x] Move remaining router input/output models into interface DTOs.
- [x] Remove direct infra calls from remaining routers (`apps/agent_studio_gateway/studio_router.py` -> `mini_agent/application/studio_ops_use_cases.py`).
- [x] Add contract tests for interface DTO stability.

## P18.2 Main-Agent Runtime Consolidation

- [x] Build single runtime manager for main-agent lifecycle (`mini_agent/runtime/main_agent_runtime_manager.py`).
- [x] Enforce single active main-agent instance/session in host process (`MainAgentRuntimePolicy(mode=single_main)`).
- [x] Move existing workspace chat/session/stream flows to main-agent use-case path.
- [x] Pin current production mode to `single_main` + main workspace, while reserving `team` mode policy toggle for future multi-workspace/multi-agent rollout.
- [x] Delete legacy duplicate runtime entry points (`gateway/main.py`, `gateway/run.py`, `mini_agent/launcher/gateway.py`, `mini_agent/launcher/orchestrator.py` hard-removed; standalone `subprograms/*/main.py` host startup hard-disabled).

## P18.3 Novel Subprogram Rebinding

- [x] Introduce `novel-agent-profile` configuration model.
- [x] Route novel actions through `NovelServiceUseCase` (`mini_agent/application/novel_service_use_cases.py`).
- [x] Isolate novel memory/tool profile from main-agent profile.
- [x] Remove direct coupling between UI handlers and novel internals.

## P18.4 Channel Unification (QQ/WeChat -> Main Agent)

- [x] Unify channel ingress payload schema.
- [x] Route QQ/WeChat traffic to main-agent use-case only.
- [x] Keep novel invocation as internal main-agent action.
- [x] Remove channel-specific bypass paths.

## P18.5 Frontend Refactor to Contract Client

- [x] Replace mixed API calls with single typed client layer.
- [x] Split UI modules by domain: workspace/novel/ops/channel (`apps/agent_studio/src/features/*`, `apps/agent_studio/src/components/ChannelMode.tsx`, `apps/agent_studio/src/api/*`).
- [x] Remove state coupling and implicit endpoint assumptions (`useWorkspaceChat` hook + domain API modules).
- [x] Add frontend contract smoke tests against `/api/v1/*` (`tests/test_agent_studio_frontend_contract_client.py`).

## P18.6 Process Management and Hot Dev Discipline

- [x] Provide `dev up/down/status/logs` one-command manager.
- [x] Enforce one-frontend/one-backend lock and clear conflict messages.
- [x] Add PID + port guardrails for both processes.
- [x] Standardize local dev env variables and startup profiles.

## P18.7 Hard Delete and Cleanup

- [x] Hard-cut Studio Ops legacy route prefix (`/api/studio/*` -> `/api/v1/ops/*`) without compatibility shim.
- [x] Hard-delete Studio Gateway legacy route set (`/api/health`, `/api/chat*`, `/api/sessions*`, `/api/novel/*`).
- [x] Delete remaining deprecated router paths and compatibility glue (`gateway/core/*`, `gateway/routers/*`, legacy gateway security auth/observability modules).
- [x] Delete duplicated service/controller code branches (legacy gateway app/router stack + obsolete router tests removed).
- [x] Delete unused frontend compatibility state/actions (frontend API/state hard split completed in P18.5, no legacy `src/api.ts` path remains).
- [x] Update docs to only reference new architecture in active execution/task docs (`P18` plan + `REFACTOR_TASKS` + runtime/docs links aligned to single-host stack).

## P18.8 Validation Gate

- [x] Add initial unit tests for main-agent use-cases (`tests/test_main_agent_gateway_use_cases.py`).
- [x] Extend unit tests for remaining use-cases and interface DTOs (`tests/test_studio_ops_use_cases.py`, `tests/test_agent_studio_frontend_contract_client.py`).
- [x] Integration tests for main-agent and novel-agent profile flows (`tests/test_agent_studio_gateway_integration_flows.py`).
- [x] Channel ingress regression tests (QQ/WeChat -> main-agent).
- [x] End-to-end dev profile test: one frontend + one backend only.

## 5. Definition of Done

1. Backend is one host process and one main-agent runtime.
2. Novel flow is profile-driven and managed through interface/application layer.
3. QQ/WeChat ingress path is unified to main-agent.
4. Frontend uses typed API contracts only.
5. No compatibility shell remains.

## 6. Non-Goals

1. No temporary compatibility wrappers.
2. No legacy endpoint preservation for convenience.
3. No mixed old/new orchestration path in production branch.

## 7. Immediate Start Order

1. P18.0 contract freeze.
2. P18.1 interface layer cut-in.
3. P18.2 runtime consolidation.
4. P18.3 novel profile rebinding.

## Closeout Addendum (2026-04-07)

- Baseline freeze evidence: `docs/P18_CLOSEOUT_BASELINE_2026-04-07.md`
- P19 prep contract: `docs/P19_AGENT_TEAM_ROLLOUT_CONTRACT.md`
