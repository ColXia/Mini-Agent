# P26 Memory Runtime Task Plan

> Status: Active
> Date: 2026-04-10
> Scope: turn the P26 architecture report into an implementation plan for durable global memory, workspace memory, session-aware runtime memory, and RAG integration

## 1. Goal

Refine Mini-Agent memory into a clean runtime architecture that stays lightweight but is ready for:

- durable cross-workspace user memory
- durable workspace/project memory
- workspace/session-aware task memory
- explicit RAG / KB grounding
- future integration with tools, skills, MCP, and richer runtime orchestration

The target is not feature inflation. The target is a clear ownership model and one stable integration seam.

## 2. Guardrails

- Keep TUI/CLI as the primary operator surfaces.
- Do not introduce a second competing durable memory system.
- Reuse the existing `MemoryService` orchestrator instead of adding parallel top-level services.
- Keep RAG and memory distinct: RAG stores source material, memory stores distilled reusable conclusions.
- Avoid compatibility shells when direct refactor is cleaner.
- Keep test isolation strict; do not leak to real `~/.mini-agent` state during tests.

## 3. Target Architecture

### Plane G1: Global durable memory

Owns:

- user profile
- user preferences
- cross-workspace operating conventions

Storage:

- `~/.mini-agent/global/USER.md`
- `~/.mini-agent/global/AGENT.md`

### Plane W1: Workspace durable memory

Owns:

- project architecture facts
- stable repo decisions
- workspace-local notes

Storage:

- `<workspace>/MEMORY.md`
- `<workspace>/memory/YYYY-MM-DD.md`

### Plane W2: Workspace runtime task memory

Owns:

- active task decomposition
- temporary working state
- transient intermediate conclusions

Implementation direction:

- persisted workspace runtime store
- session-namespaced
- not a second durable truth source

### Plane K1: RAG / knowledge base

Owns:

- source chunks
- explicit retrieval
- citations / provenance

Current implementation direction:

- keep the lightweight hybrid store as the main path for now
- vectorization remains a future enhancement, not a prerequisite

## 4. Implementation Phases

### Phase 1: Correct global vs workspace boundary

Status:

- completed

Tasks:

- move `USER.md` ownership to a real global path
- keep workspace durable notes in `MEMORY.md` and daily files
- make `MemoryService.profile()` resolve global user memory
- keep workspace profile access explicit, not implicit
- add a real `UserProfileTurnContextProvider`
- wire the provider into the default runtime context chain
- add isolated tests for global memory path usage

Acceptance:

- no new profile facts are written into workspace `USER.md`
- global profile facts are automatically available in turn-context preparation
- existing workspace note behavior remains unchanged

### Phase 2: Add workspace-aware session-search context

Status:

- completed

Tasks:

- extend session-search retrieval to filter by stable workspace identity
- add a `SessionSearchTurnContextProvider`
- keep retrieval on-demand and bounded
- avoid polluting every turn with large transcript chunks

Acceptance:

- session-search context only pulls from the active workspace
- multi-workspace history does not bleed into unrelated turns

### Phase 3: Strengthen durable-memory refresh and promotion

Status:

- completed

Tasks:

- add automatic or trigger-based consolidated-memory refresh
- formalize promotion rules from runtime/task state into durable memory
- ensure KB hits are distilled before promotion

Acceptance:

- durable memory stays small, human-readable, and reusable
- raw KB chunks are not copied into durable memory verbatim

### Phase 4: Land persisted workspace runtime task memory

Status:

- completed

Tasks:

- give `MemoriaEngine` a persisted workspace-backed store
- add logical namespaces:
  - `session:<session_id>`
  - `workspace:shared`
- connect retrieval through the existing turn-context seam
- add promotion hooks into global/workspace durable memory

Acceptance:

- runtime task memory survives restart
- session-local state does not contaminate sibling sessions
- `MemoriaEngine` remains runtime task memory, not durable truth

### Phase 5: Operator controls and RAG-memory integration

Status:

- completed

Tasks:

- add TUI/CLI visibility for memory source usage
- add operator commands for memory status and diagnostics
- integrate KB/RAG and memory promotion with explicit policy

Acceptance:

- operators can tell what memory layer contributed context
- KB can be enabled without passive prompt bloat

## 5. Current Slice

This implementation slice currently covers Phase 1 through Phase 5:

- real global-memory path resolution
- `MemoryService` global profile boundary
- `UserProfileTurnContextProvider`
- workspace-aware session-search retrieval via stable `workspace_anchor_dir`
- `SessionSearchTurnContextProvider`
- workspace-scoped consolidated-memory refresh status via `MemoryService.consolidated_refresh_status()`
- on-demand consolidated-memory refresh via `MemoryService.refresh_consolidated_memory()`
- workspace-scoped consolidation state directories to avoid cross-workspace contamination
- promotion-policy filtering so raw KB/tool payloads are not copied into durable consolidated memory
- persisted workspace runtime task memory via `WorkspaceMemoriaRuntime`
- namespace isolation for `session:<session_id>` and `workspace:shared`
- conservative post-turn runtime task-memory writeback via `TurnRuntimeTaskMemory`
- runtime task-memory retrieval through `RuntimeTaskMemoryTurnContextProvider`
- explicit promotion hooks from runtime task memory into workspace durable memory and global profile memory
- operator-facing `memory_diagnostics` across runtime/gateway session summaries/details/snapshots
- gateway session memory actions for diagnostics, refresh, and runtime-memory promotion
- TUI `/memory` commands and compact memory sidebar summary
- CLI interactive `/memory` commands for local inspection/control
- selector-aware runtime-memory promotion using exact `engram_id`, numeric preview indices, or `latest`
- selector-oriented `/memory list` alias for operator-facing runtime-memory previews
- explicit operator-driven durable-memory saves via `/memory save note <text>` and `/memory save profile <text>`
- `kb_confirmed` note categorization when manual durable-memory confirmation follows KB-grounded context
- QQ shared-session `/memory` controls routed through the same gateway memory seam
- explicit workspace-shared runtime-memory snapshot/import/export support through `workspace_shared_runtime_memory_payload`
- merge-safe workspace-shared runtime-memory restore semantics so shared workspace facts are preserved during import/share/unshare
- conservative `workspace:shared` candidate detection on post-turn runtime writeback
- explicit `/memory promote shared <selector>` across local/shared operator surfaces
- retrieval gating so `workspace:shared` participates only for workspace-scoped queries or session-hit fallback
- regression coverage for global-profile, workspace-session history, consolidated refresh, and promotion boundaries

## 6. Risks

- old assumptions may still exist in tests or docs that treat workspace `USER.md` as the active profile source
- global-memory tests must stay isolated from real user state
- phase 2 must use stable workspace identity, not mutable cwd semantics

## 7. Recommended Order From Here

1. Keep expanding real-use validation around manual memory confirmation and session/workspace boundaries.
2. Keep KB-to-memory promotion explicit and distilled as future integration expands.
3. Treat vector RAG as a future enhancement instead of changing the current lightweight ownership model.

## 8. Detailed Next Slice: Reset/Delete Semantics Hardening

Status:

- completed and verified on 2026-04-10

### Objective

Make `reset/delete/clear` mean the same thing across gateway, TUI, and CLI:

- clear transcript/runtime state
- clear prepared-context state
- clear pending recovery/approval state
- clear persisted session-scoped runtime task memory for that session

### Problem Statement

The architecture already has persisted workspace runtime task memory under:

- `session:<session_id>`
- `workspace:shared`

But current session reset flows do not consistently clear the `session:<session_id>` namespace.
That creates a semantic mismatch where the operator believes the session was cleared, while runtime retrieval may still surface old task memory.

### Implementation Plan

#### Step A: Runtime-memory cleanup primitives

- extend `WorkspaceMemoriaRuntime` with explicit namespace cleanup helpers
- minimum helpers:
  - `clear_namespace(namespace)`
  - `clear_session_namespace(session_id)`
- implementation should delete only the namespace file for the target namespace
- `workspace:shared` must remain untouched by session reset/delete

#### Step B: Gateway reset/delete alignment

- strengthen `MainAgentRuntimeManager._reset_agent_messages(...)`
  - reset ephemeral runtime state
  - reset token counters
  - clear prepared-context residue consistently with local TUI semantics
- add one internal helper that clears runtime task memory for a session using the session workspace path
- wire cleanup into:
  - `reset_session(...)`
  - `delete_session(...)`
  - `_refresh_session_lifecycle_unlocked(...)` when lifecycle policy triggers reset
- for persisted-but-inactive sessions, resolve `workspace_dir` from the stored record before deleting the runtime namespace

#### Step C: TUI local reset/delete alignment

- update `_reset_session_runtime_state(...)` so it also clears:
  - session runtime task memory namespace
  - `restored_agent_messages`
  - `pending_resume_agent_messages`
  - pending resume metadata that would otherwise rehydrate stale state
- update local `_delete_session(...)` to clear runtime task memory before dropping the session

#### Step D: CLI local clear alignment

- make CLI `/clear` clear `cli-session` runtime task memory
- align the local reset helper with gateway/TUI on token and prepared-context cleanup

#### Step E: Verification

- add direct runtime-memory cleanup tests
- add gateway reset/delete regression coverage
- add TUI clear/delete stale-state regression coverage
- add CLI `/clear` cleanup regression coverage if practical

### Acceptance Criteria

- session reset no longer leaves `session:<session_id>` runtime memory behind
- session delete removes persisted runtime task memory even when only the persisted record exists
- local TUI clear does not silently restore old session context later
- CLI `/clear` resets both in-memory conversation state and persisted runtime task memory

### Non-Goals

- no redesign of snapshot import/export payloads in this slice
- no new memory planes
- no command-system expansion

### Verification

- `uv run python -m compileall src/mini_agent/memory/memoria_runtime.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/tui/app.py src/mini_agent/cli_interactive.py tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py`
- `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py -q`
- result: `171 passed`

## 9. Detailed Next Slice: Snapshot / Import / Export Runtime-Memory Parity

Status:

- completed and verified on 2026-04-10

### Objective

Make session snapshot-based flows preserve `session:<session_id>` runtime task memory instead of only transcript and prepared-context metadata.

### Problem Statement

Current snapshot/import/export semantics preserve:

- transcript
- agent messages
- context policy
- prepared-context summaries
- memory diagnostics

But they do not preserve the actual session-scoped runtime task memory payload.
That means share/unshare and other snapshot-based flows still lose working-memory continuity even though normal restart persistence is already correct.

### Implementation Plan

#### Step A: Runtime-memory snapshot helpers

- extend `WorkspaceMemoriaRuntime` with helpers to:
  - export a session runtime-memory payload
  - import/restore a session runtime-memory payload into a destination session namespace
- payload should preserve the underlying `MemoriaEngine` data, not just a lossy preview list

#### Step B: DTO contract extension

- extend `MainAgentSessionImportRequest`
- extend `MainAgentSessionSnapshot`
- add a dedicated session runtime-memory field so the contract is explicit instead of overloading `memory_diagnostics`

#### Step C: Gateway import/export wiring

- `export_session_snapshot(...)` should include the session runtime-memory payload
- `import_session_snapshot(...)` should restore it under the effective session id chosen by the runtime
- if import chooses a new session id, runtime-memory payload must follow the new id rather than staying tied to the source id

#### Step D: TUI share/unshare parity

- local share should send session runtime-memory payload to gateway
- after a successful share migration, old local namespace should be cleared when the session id changes
- unshare should restore the runtime-memory payload locally before returning control to local TUI state

#### Step E: Verification

- gateway import/export tests
- TUI share/unshare parity tests
- API contract test updates where snapshot/import fields are asserted

### Acceptance Criteria

- snapshot export includes session runtime-memory payload
- import restores session runtime-memory payload into the destination session namespace
- local-to-remote share and remote-to-local unshare preserve session runtime memory
- no orphaned old local runtime namespace remains after successful share migration to a new session id

### Verification

- `uv run python -m compileall src/mini_agent/interfaces/agent.py src/mini_agent/memory/memoria_runtime.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/application/main_agent_gateway_use_cases.py src/mini_agent/tui/app.py tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py`
- `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py -q`
- result: `181 passed`

## 10. Detailed Next Slice: Workspace-Shared Runtime-Memory Portability

Status:

- completed and verified on 2026-04-10

### Objective

Make `workspace:shared` explicit in snapshot/import/export flows without allowing one session snapshot to overwrite workspace-owned shared runtime memory.

### Problem Statement

`workspace:shared` was already part of persisted runtime retrieval and diagnostics, but it had no explicit portability contract.
That left two problems:

- snapshot/import/export/share/unshare could not carry workspace-shared runtime memory explicitly
- naively treating workspace-shared payload like session-scoped payload would risk overwriting shared workspace facts collected by sibling sessions

### Implementation Plan

#### Step A: Explicit payload seam

- extend `MainAgentSessionImportRequest`
- extend `MainAgentSessionSnapshot`
- add `workspace_shared_runtime_memory_payload` as a dedicated field

#### Step B: Runtime helpers

- add `snapshot_workspace_shared_namespace_payload()`
- add `restore_workspace_shared_namespace_payload(...)`
- keep session restore behavior as replace
- define workspace-shared restore behavior as merge-by-content

#### Step C: Gateway wiring

- `export_session_snapshot(...)` includes the workspace-shared payload
- `import_session_snapshot(...)` restores the workspace-shared payload into the target workspace runtime store using non-destructive merge semantics

#### Step D: TUI share/unshare parity

- local TUI share includes the workspace-shared payload
- unshare restores the workspace-shared payload locally using the same merge semantics
- local session-id migration cleanup still applies only to `session:<id>`, not `workspace:shared`

#### Step E: Verification

- direct runtime merge test
- gateway import/export tests
- TUI share/unshare tests
- API/DTO contract assertions

### Acceptance Criteria

- snapshot/import/export contract exposes `workspace_shared_runtime_memory_payload`
- importing a snapshot does not erase existing workspace-shared runtime memory in the target workspace
- TUI share/unshare preserve workspace-shared runtime memory through the same explicit payload seam
- `workspace:shared` remains outside session reset/delete semantics

### Verification

- `uv run python -m compileall src/mini_agent/interfaces/agent.py src/mini_agent/memory/memoria_runtime.py src/mini_agent/application/main_agent_gateway_use_cases.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/tui/app.py tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py`
- `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py -q`
- result: `186 passed`

## 11. Recommended Order From Here

1. Formalize promotion and retrieval boundaries between `session:<id>` and `workspace:shared`.
2. Keep `workspace:shared` as workspace-owned runtime state, not a second durable-memory layer.
3. Treat future durable promotion into workspace notes/global profile as explicit policy on top of the runtime-memory seam.

## 12. Detailed Next Slice: Workspace-Shared Boundary / Promotion Policy

Status:

- completed and verified on 2026-04-10

### Objective

Make `workspace:shared` operationally usable without turning it into a silent auto-write path:

- session runtime writeback stays automatic
- workspace-shared promotion stays explicit
- runtime surfaces show when the latest session writeback looks like a workspace-shared candidate

### Problem Statement

Before this slice:

- `session:<id>` writeback was automatic
- `workspace:shared` existed and was portable
- but there was no integrated runtime strategy for what should remain session-local vs what should be considered workspace-shared

That left `workspace:shared` operator-visible but under-specified.

### Implementation Plan

#### Step A: Policy helper

- add one conservative helper for evaluating workspace-shared candidate text
- reject raw KB/tool payloads and require both:
  - workspace/domain scope signal
  - policy/convention signal

#### Step B: Post-turn writeback annotation

- keep post-turn runtime writeback landing in `session:<session_id>`
- annotate the saved session entry with:
  - `workspace_shared_candidate`
  - `workspace_shared_candidate_reason`
  - `workspace_shared_candidate_text`

#### Step C: Promotion path

- add `/memory promote shared <selector>`
- support the same action through gateway/TUI/CLI/QQ
- when promoting, prefer the distilled candidate text over the raw session summary envelope

#### Step D: Diagnostics

- surface the workspace-shared candidate result in the existing runtime-memory diagnostics path
- keep one shared operator-facing reporting seam instead of adding a second subsystem

### Acceptance Criteria

- session runtime writeback remains automatic and session-scoped
- `workspace:shared` remains explicit and operator-controlled
- latest runtime writeback shows whether it is a shared candidate
- shared promotion stores the distilled workspace-level fact when available

### Verification

- `uv run python -m compileall src/mini_agent/memory/promotion.py src/mini_agent/memory/runtime_task_memory.py src/mini_agent/memory/memoria_runtime.py src/mini_agent/memory/diagnostics.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/cli_interactive.py src/mini_agent/tui/app.py tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py`
- `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py -q`
- `node --check src/apps/qqbot_channel/bot.mjs`
- result: `206 passed`

## 13. Detailed Next Slice: Workspace-Shared Retrieval Boundary

Status:

- completed and verified on 2026-04-10

### Objective

Keep `workspace:shared` useful but supplemental during turn-context retrieval:

- session runtime memory remains the primary active-task source
- workspace-shared memory only joins when the turn is workspace-scoped or session memory is too sparse

### Problem Statement

Even after promotion-policy cleanup, retrieval still treated `workspace:shared` too eagerly.
That blurred the intended boundary between:

- current task/session continuity
- workspace-level shared runtime conventions

### Implementation Plan

#### Step A: Shared-scope signal helper

- add one reusable helper for detecting workspace/runtime/shared scope in a query string

#### Step B: Provider gating

- query `session:<id>` first
- include `workspace:shared` only when:
  - the query itself has workspace/shared scope signals, or
  - session hits are below the configured session budget

#### Step C: Explain the decision

- add provider metadata describing whether shared retrieval was:
  - `query_scope`
  - `session_fallback`
  - `suppressed_by_session_hits`

### Acceptance Criteria

- shared runtime memory no longer competes with strong session-local hits by default
- shared runtime memory still helps on workspace-scoped questions
- fallback behavior still works when session-local hits are insufficient

### Verification

- `uv run python -m compileall src/mini_agent/memory/promotion.py src/mini_agent/turn_context.py tests/test_memoria_runtime.py`
- `uv run pytest tests/test_memoria_runtime.py tests/test_agent_turn_context.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py -q`
- result: `204 passed`

## 14. Follow-Up Slice: Workspace-Shared Independent Operator Surface

Status:

- completed and verified on 2026-04-10

### Objective

Make `workspace:shared` directly operable instead of diagnostics-only.

### Landed Behavior

- `/memory shared list`
- `/memory shared show <selector>`
- `/memory shared clear`
- behavior aligned across gateway, TUI, CLI, and QQ

### Verification

- `uv run pytest tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py -q`
- `node --check src/apps/qqbot_channel/bot.mjs`
- result: `181 passed`

## 15. Follow-Up Slice: Explicit KB Grounding / Manual Confirmation Boundary

Status:

- completed and verified on 2026-04-10

### Objective

Keep KB explicit while preventing silent durable-memory promotion from KB-grounded turns.

### Landed Behavior

- KB-grounded turns now annotate runtime task memory with:
  - `knowledge_base_query`
  - `knowledge_base_id`
  - `knowledge_base_hits`
  - `knowledge_base_refs`
- automatic workspace durable-note and daily-note writeback is suppressed for KB-grounded turns
- explicit runtime-memory promotion into workspace durable notes now uses `kb_confirmed` when KB grounding exists
- explicit `/memory save note ...` surfaces KB grounding details when KB prepared context is present

### Verification

- `uv run python -m compileall src/mini_agent/memory/knowledge_base_grounding.py src/mini_agent/memory/runtime_task_memory.py src/mini_agent/memory/operator_actions.py src/mini_agent/memory/memoria_runtime.py src/mini_agent/memory/automation.py src/mini_agent/memory/diagnostics.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/tui/app.py src/mini_agent/cli_interactive.py`
- `uv run pytest tests/test_memoria_runtime.py tests/test_memory_automation.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_command_catalog.py -q`
- `node --check src/apps/qqbot_channel/bot.mjs`
- result: `201 passed`

## 16. Follow-Up Slice: KB Grounding Operator Visibility

Status:

- completed and verified on 2026-04-10

### Objective

Expose KB grounding consistently in runtime-memory previews and shared-entry details without letting gateway/TUI/CLI formatting drift apart.

### Landed Behavior

- runtime-memory preview rendering now reuses one shared diagnostics formatter across gateway, TUI, and CLI
- KB-grounded preview entries now show:
  - explicit badges
  - compact `kb / hits / query / refs` operator lines
- shared-entry detail rendering now also reuses one shared formatter, so `shared show` exposes the same grounding block across surfaces
- focused regression coverage now locks KB visibility in:
  - TUI local `/memory runtime` and `/memory shared show latest`
  - gateway session-memory `list` / `shared_show`
  - CLI interactive `/memory list` / `shared show`

### Verification

- `uv run python -m compileall src/mini_agent/memory/diagnostics.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/cli_interactive.py src/mini_agent/tui/app.py tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py`
- `uv run pytest tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py tests/test_memoria_runtime.py tests/test_memory_automation.py -q`
- result: `201 passed`

## 17. Follow-Up Slice: Session Runtime Entry Inspection

Status:

- completed and verified on 2026-04-10

### Objective

Make session-local runtime memory as inspectable as `workspace:shared`, while preserving the existing diagnostics-oriented `memory show brief|full` command.

### Landed Behavior

- `memory show brief|full` still renders memory diagnostics
- `memory show <selector>` now resolves one session runtime-memory entry and renders its full detail block
- session-entry detail now reuses the same runtime-entry formatting seam as shared-entry detail
- behavior is aligned across:
  - gateway session-memory API
  - TUI local/remote command handling
  - CLI interactive command handling
  - QQ shared-session command handling
- command catalog/examples now document `memory show latest`

### Verification

- `uv run python -m compileall src/mini_agent/cli_interactive.py src/mini_agent/tui/app.py src/mini_agent/runtime/main_agent_runtime_manager.py tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py`
- `uv run pytest tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py tests/test_memoria_runtime.py tests/test_memory_automation.py -q`
- `node --check src/apps/qqbot_channel/bot.mjs`
- result: `203 passed`

## 18. Follow-Up Slice: Durable-Memory Unified Command Surface

Status:

- completed and verified on 2026-04-10

### Objective

Bring durable memory into the same operator command seam as runtime memory, so profile facts and workspace notes can be inspected without leaving `/memory`.

### Landed Behavior

- added `memory profile [query]` for global profile browsing/search
- added `memory notes [query]` for workspace durable-note browsing/search
- added `memory daily <YYYY-MM-DD>` for workspace daily-memory inspection
- the new read actions are aligned across:
  - gateway session-memory API
  - TUI local/remote command handling
  - CLI interactive command handling
  - QQ shared-session command handling
- gateway memory request contracts now carry explicit `query` and `day` fields
- command catalog/examples now include the durable-memory commands

### Verification

- `uv run python -m compileall src/mini_agent/memory/diagnostics.py src/mini_agent/interfaces/agent.py src/mini_agent/application/main_agent_gateway_use_cases.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/cli_interactive.py src/mini_agent/tui/gateway_client.py src/mini_agent/tui/app.py tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py`
- `uv run pytest tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py tests/test_memoria_runtime.py tests/test_memory_automation.py tests/test_interface_dto_contracts.py tests/test_agent_studio_gateway_api_v1.py -q`
- `node --check src/apps/qqbot_channel/bot.mjs`
- result: `230 passed`

## 19. Follow-Up Slice: Consolidated-Memory Operator Surface

Status:

- completed and verified on 2026-04-10

### Objective

Expose consolidated memory directly through `/memory` so operators can inspect the current snapshot and run explicit relevance lookup without leaving the main memory command seam.

### Landed Behavior

- added `memory consolidated` and `memory consolidated show`
- added `memory consolidated search <query>`
- consolidated-memory detail/search rendering now uses one shared formatting seam across:
  - gateway session-memory API
  - TUI local/remote command handling
  - CLI interactive command handling
  - QQ shared-session command handling
- `/memory refresh` remains the explicit consolidated refresh trigger; the new consolidated commands are read-only surfaces

### Verification

- `uv run python -m compileall src/mini_agent/memory/diagnostics.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/cli_interactive.py src/mini_agent/tui/app.py tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py`
- `uv run pytest tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py tests/test_memoria_runtime.py tests/test_memory_automation.py tests/test_interface_dto_contracts.py tests/test_agent_studio_gateway_api_v1.py tests/test_memory_service.py tests/test_memory_relevance.py -q`
- `node --check src/apps/qqbot_channel/bot.mjs`
- result: `242 passed`

## 20. Follow-Up Slice: Cross-Layer Memory Overview / Export

Status:

- completed and verified on 2026-04-10

### Objective

Add one concise cross-layer operator summary plus one explicit export surface so memory inspection does not require hopping between several subcommands or APIs.

### Landed Behavior

- added `memory overview`
- added `memory export [jsonl|markdown]`
- `memory overview` summarizes:
  - session/workspace linkage through an explicit `Session Context` block
  - runtime task memory
  - durable memory
  - consolidated memory
  - latest writeback/prepared-source hints when available
- `memory export` now reuses `MemoryService.export_notes(...)` through the main operator seam
- gateway memory request contracts now carry explicit `export_format`
- overview/export rendering is aligned across:
  - gateway session-memory API
  - TUI local/remote command handling
  - CLI interactive command handling
  - QQ shared-session command handling

### Verification

- `uv run pytest tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py tests/test_interface_dto_contracts.py -q`
- `node --check src/apps/qqbot_channel/bot.mjs`
- result: `203 passed`
- `uv run pytest tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py -q`
- result: `190 passed`

## 21. Follow-Up Slice: KB Call-Decision Guidance + Low-Signal Memory Quality

Status:

- completed and verified on 2026-04-10

### Objective

Improve the quality of the existing RAG/memory seam without adding passive retrieval:

- make document-grounded KB use easier for the agent to choose correctly
- keep low-signal operator/control chatter out of both durable auto-memory and runtime task memory
- add one real-use integration test skeleton that exercises the intended memory boundary behavior

### Landed Behavior

- strengthened explicit KB guidance without changing the explicit-call policy:
  - `knowledge_base` tool description now more clearly covers README, spec, API, design, and manual retrieval cases
  - system prompt guidance now tells the agent to prefer KB first for document-grounded requests and to form concrete noun-heavy KB queries
- added one shared low-signal memory-quality helper:
  - `clean_memory_text(...)`
  - `is_low_signal_control_turn(...)`
- durable auto-memory writeback now skips low-signal control turns and records:
  - `skipped_reason="low_signal_control_turn"`
- runtime task-memory writeback now applies the same low-signal filter before storing session task memory
- added `tests/test_memory_real_use_flow.py` to validate:
  - workspace/session retrieval boundaries
  - explicit KB-confirmation boundary before durable-memory promotion

### Verification

- `uv run python -m compileall src/mini_agent/memory/quality.py src/mini_agent/memory/automation.py src/mini_agent/memory/runtime_task_memory.py src/mini_agent/tools/knowledge_base.py`
- `uv run pytest tests/test_memory_automation.py tests/test_memoria_runtime.py tests/test_knowledge_base_tool.py tests/test_memory_real_use_flow.py -q`
- result: `31 passed`
- `uv run pytest tests/test_memory_service.py tests/test_memoria_runtime.py tests/test_agent_turn_context.py tests/test_memory_automation.py tests/test_session_search.py tests/test_knowledge_base_tool.py tests/test_main_agent_gateway_use_cases.py tests/test_memory_real_use_flow.py -q`
- result: `103 passed`
