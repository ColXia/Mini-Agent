# Anti-Duplication System Inventory (2026-04-07)

Purpose: avoid repeated development by confirming what is already implemented in code and what only needs wiring.

## 1. Already Implemented (Reuse Directly)

- Unified terminal entry (`auto` / `tui` / `cli` / `headless`):
  - `src/mini_agent/cli.py:937`
  - `src/mini_agent/cli.py:1759`
- TUI model panel with list/filter/discover/apply:
  - `src/mini_agent/tui/app.py:638`
  - `src/mini_agent/tui/app.py:754`
  - `src/mini_agent/tui/app.py:777`
- Unified model registry (custom + preset, custom first):
  - `src/mini_agent/model_manager/model_registry_service.py:242`
  - `src/mini_agent/model_manager/model_registry_service.py:291`
- `/api/v1/ops/models` contracts (list/discover/select):
  - `src/apps/agent_studio_gateway/studio_router.py:76`
  - `src/apps/agent_studio_gateway/studio_router.py:81`
  - `src/apps/agent_studio_gateway/studio_router.py:89`
- Preset key flow (official env vars + `.env.local` + first-run one-time setup):
  - `src/mini_agent/config.py:40`
  - `src/mini_agent/config.py:155`
  - `src/mini_agent/config.py:224`
- Runtime provider routing + breaker + failover:
  - `src/mini_agent/model_manager/runtime.py:223`
  - `src/mini_agent/model_manager/failover.py:53`
- Agent execution and code-agent workflow baseline:
  - `src/mini_agent/agent.py:1022`
  - `src/mini_agent/code_agent/agent_loop.py:59`
  - `src/mini_agent/code_agent/scheduler.py:71`
  - `src/mini_agent/code_agent/coordinator.py:90`

## 2. Do Not Rebuild (Mandatory Reuse Entrypoints)

- Do not rebuild terminal routing: reuse `run_unified_terminal_mode` in `src/mini_agent/cli.py`.
- Do not rebuild model center: reuse `ModelRegistryService`.
- Do not rebuild model ops API: reuse `StudioOpsUseCases` + `studio_router`.
- Do not rebuild provider schema/validation: reuse `ProviderConfig` / `ProviderCatalog`.
- Do not rebuild failover chain: reuse `FailoverLLMClient`.
- Do not rebuild scheduler/coordinator primitives: reuse `AgentSubmissionLoop` + `TurnScheduler` + `MiniCoordinator`.

## 3. Wiring Gaps (Wire Only, No Rewrite)

- Gateway currently mounts `studio_router` + `knowledge_base_router` only:
  - `src/apps/agent_studio_gateway/main.py:582`
  - `src/apps/agent_studio_gateway/main.py:583`
- `document_parser` and `memory_manager` routers exist but are not mounted in gateway main:
  - `src/subprograms/document_parser/gateway/router.py`
  - `src/subprograms/memory_manager/gateway/router.py`
- Standalone subprogram hosts are intentionally deprecated in hard-refactor mode:
  - `src/subprograms/knowledge_base/main.py`
  - `src/subprograms/document_parser/main.py`
  - `src/subprograms/memory_manager/main.py`

## 4. Risk Notes

- ACP package is currently deleted in working tree:
  - `src/mini_agent/acp/__init__.py`
  - `src/mini_agent/acp/server.py`
- Any ACP test or wiring decision must follow current branch intent before restoration.

## 5. Execution Rule for Next Iterations

Before writing new modules for TUI/CLI/agent/runtime:

1. Check existing runtime and registry entrypoints.
2. Confirm test evidence for the target capability.
3. Implement as integration/wiring first, not replacement.
