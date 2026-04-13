# Task Plan

## Latest Sync: 2026-04-13 P31.2 Thin Application Seam Hardening Landed

## Current Execution Slice: P31.3 Desktop Runtime Host Integration Prep (2026-04-13)

### Why This Slice Is Next

- the thin `application service seam` is now landed enough for the desktop path to build on
- the shared top interaction owner is no longer only expressed as `gateway`-owned behavior
- the next useful move is therefore no longer naming correction
- it is host/bootstrap preparation for DesktopUI

### What Just Landed

- canonical shared service is now `MainAgentSurfaceService`
- surface-neutral chat flow types now exist:
  - `SurfaceChatExecutionRequest`
  - `SurfaceChatExecutionResult`
  - `SurfaceChatStreamEvent`
  - `SurfaceChatFlowHandler`
- execution helpers are now also surface-oriented:
  - `AgentTurnExecutionHandler`
  - `AgentRouteExecutionHandler`
- gateway now resolves its shared top service through `_main_agent_surface_service()`
- compatibility aliases remain in place only where they reduce immediate breakage during the transition

### Scope

- prepare the desktop host/bootstrap slice on top of the corrected seam
- keep gateway as the first DesktopUI transport/backend
- avoid slipping new business logic back into gateway route handlers

### Out Of Scope

- no DesktopUI visual shell yet in this planning sync
- no browser Studio revival
- no remote-adapter expansion

### Acceptance

- active planning now treats `P31.2` as landed
- the next implementation anchor is DesktopUI host/bootstrap prep instead of more gateway naming churn

### Status

- in_progress

## Latest Sync: 2026-04-13 P31 DesktopUI(PySide6) Decision Freeze

## Current Execution Slice: P31 DesktopUI(PySide6) Seam-First Kickoff (2026-04-13)

### Why This Slice Is Next

- the user chose the desktop-window direction instead of reviving browser-first work as the primary graphical path
- the recommended option is now frozen as:
  - separate `PySide6 DesktopUI`
  - not TUI-to-desktop mapping
  - not browser `WebUI` mainline continuation
- the current codebase is close to reusable enough for DesktopUI work
- but one drift risk still remains:
  - the shared top orchestration is still named/shaped too much around `gateway`
- if UI work starts before that thin seam is corrected, the desktop path is likely to inherit transport-owned semantics as if they were the real service boundary

### Scope

- freeze `DesktopUI(PySide6)` as the canonical third maintained entrance
- downgrade browser `WebUI` to paused compatibility/prototype status
- record the execution rule:
  - first thin `application service seam` hardening
  - then reuse the existing gateway transport for DesktopUI
- define the implementation order so the next code slice does not drift

### Out Of Scope

- no browser Studio revival
- no TUI-to-Qt renderer wrapper
- no WeChat / Feishu work
- no large gateway rewrite
- no DesktopUI coding slice yet beyond planning/architecture sync

### Files In Scope

- `docs/P31_DESKTOPUI_PYSIDE6_TASK_PLAN_2026-04-13.md`
- `docs/ARCHITECTURE.md`
- `docs/FRAMEWORK_SKELETON.md`
- `docs/DEVELOPMENT_INDEX.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Freeze the third main graphical entrance as `DesktopUI(PySide6)`.
2. Record that browser `WebUI` is now a paused compatibility/prototype path rather than the canonical mainline.
3. Record the seam-first decision:
   - first thin `application service seam`
   - then DesktopUI on top of the existing gateway transport

### Acceptance

- architecture docs no longer present browser `WebUI` as the primary graphical mainline
- the execution order is explicit and does not encourage direct UI work on top of gateway-owned orchestration names
- the next coding slice is clearly identified as seam-first rather than UI-first

### Status

- in_progress

## Latest Sync: 2026-04-13 P30.5 Near-Close + Remote Interaction Scope Correction

## Current Execution Slice: P30 Remote Interaction Active Scope Freeze (2026-04-13)

### Why This Slice Is Next

- `P30.5` has now reached a natural stop point:
  - shared interaction binding is converged
  - runtime live-state write paths are aligned
  - even the lower-level direct-call guardrail is now in place
- the next useful planning correction is scope, not a new implementation hotspot
- `P30.5` is now near-closed
- and the user clarified an important delivery constraint:
  - `WeChat` is not part of the current actual implementation plan
  - it should be treated only as future extension
- that means the active remote entrance path should be documented as:
  - `QQ` = current concrete implementation
  - `WeChat / Feishu` = future extension targets only

### Scope

- correct the active plan so it does not accidentally elevate `WeChat` into the current delivery roadmap
- freeze the remote entrance wording as:
  - `QQ` active
  - `WeChat / Feishu` future extension only
- keep the architecture open for future remote-adapter reuse without turning those adapters into active implementation commitments

### Out Of Scope

- no `WeChat` implementation work
- no `Feishu` implementation work
- no `WebUI` work while browser delivery remains paused

### Files In Scope

- `docs/ARCHITECTURE.md`
- `docs/FRAMEWORK_SKELETON.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `docs/P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Freeze `P30.5` as near-closed unless a fresh shared-entrance drift appears.
2. Remove the mistaken implication that `WeChat` is the next active implementation slice.
3. Record the correct current delivery scope for `Remote Interaction`.

### Acceptance

- active planning explicitly treats `P30.5` as near-closed
- active remote delivery scope is documented as `QQ` only
- `WeChat / Feishu` remain future extension targets, not active execution slices

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 Interaction-Surface Direct-Call Guardrail

## Current Execution Slice: P30.5 Interaction-Surface Direct-Call Guardrail (2026-04-13)

### Why This Slice Is Next

- after the runtime live-state convergence cut, the active production callers were already clean
- but one low-level guardrail was still missing:
  - `resolve_interaction_surface(None, "qqbot")`
  - still returned the old surface fallback shape
- that no longer broke current production paths
- but it still left a future footgun for any new direct caller

### Scope

- harden `resolve_interaction_surface(...)` itself for:
  - missing explicit `surface`
  - concrete remote `channel_type`
- add direct regression coverage for that exact case
- confirm broader session/gateway/channel regressions still stay green

### Out Of Scope

- no new session/read-model policy change
- no entrance contract rewrite
- no persistence schema change

### Files In Scope

- `src/mini_agent/runtime/interaction_surface.py`
- `tests/test_interaction_surface.py`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Make `resolve_interaction_surface(...)` resolve remote `channel_type` as the concrete surface when explicit `surface` is absent.
2. Add a direct regression test for `surface=None, channel_type=\"qqbot\"`.
3. Re-run focused and broader binding/session regressions.

### Acceptance

- `resolve_interaction_surface(None, \"qqbot\")` resolves to remote `qq`
- current higher-level shared binding behavior remains unchanged
- broader regressions remain green

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 Runtime Live-State Remote Binding Convergence

## Current Execution Slice: P30.5 Runtime Live-State Remote Binding Convergence (2026-04-13)

### Why This Slice Is Next

- after the shared interaction-binding seam and the default-surface precedence fix landed, one deeper drift point still remained
- some runtime/application layers were still writing session projection or transcript state through older surface-only normalization
- that meant a request shape like:
  - missing explicit `surface`
  - remote `channel_type="qqbot"` / `qq`
- could still be recorded too low in the stack with old fallback semantics instead of the shared remote binding result

### Scope

- reuse shared interaction binding inside runtime live-state mutation paths
- make remote alias + missing-surface handling consistent for:
  - session projection binding
  - transcript message writes
  - activity transcript writes
  - remote conversation binding lookup
  - gateway agent execution metadata shaping
- lock the behavior with focused runtime/session regression tests

### Out Of Scope

- no entrance taxonomy rewrite
- no persisted snapshot schema change
- no new remote adapter feature work

### Files In Scope

- `src/mini_agent/runtime/session_live_state_handler.py`
- `src/mini_agent/application/gateway_agent_execution_handler.py`
- `src/mini_agent/application/remote_conversation_binding_service.py`
- `tests/test_session_service.py`
- `tests/test_channel_ingress_use_cases.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Reuse shared interaction binding inside runtime live-state surface/message/activity writes.
2. Reuse the same binding seam in remote conversation binding lookup and gateway execution metadata shaping.
3. Add regression coverage for remote alias + missing-surface cases.
4. Re-run focused session/gateway/channel regression coverage.

### Acceptance

- remote requests with `channel_type=qq*` and no explicit `surface` are recorded as `qq`, not `api`
- session projection, transcript messages, and activity transcript entries stay aligned on the same resolved remote surface
- remote alias binding reuse remains stable across channel ingress and gateway/runtime paths
- focused plus broader regression coverage remains green

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 Default-Surface Override Fix For Remote Bindings

## Current Execution Slice: P30.5 Default-Surface Override Fix For Remote Bindings (2026-04-13)

### Why This Slice Is Next

- after the shared interaction-binding convergence landed, one follow-up audit revealed a real remaining bug
- `SessionSurfaceBinding.from_request(...)` still pre-applied `default_surface`
- that meant:
  - requests without explicit `surface`
  - but with remote `channel_type`
  - could still be forced to `"tui"` before the shared resolver saw them
- that is not just duplication; it is wrong ownership of precedence

### Scope

- stop `SessionSurfaceBinding.from_request(...)` from overriding remote channel inference with the caller default
- let the shared interaction resolver decide precedence in the intended order:
  - explicit surface
  - channel type
  - default surface
- lock the behavior with direct session-service and remote-session-service tests

### Out Of Scope

- no change to local create-session defaults
- no change to persisted session projection semantics
- no surface taxonomy rewrite

### Files In Scope

- `src/mini_agent/application/session_service.py`
- `tests/test_session_service.py`
- `tests/test_session_remote_service.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Remove pre-resolution default-surface overriding in `SessionSurfaceBinding.from_request(...)`.
2. Add direct coverage for remote channel winning over `default_surface="tui"`.
3. Re-run session/gateway/TUI regression coverage.

### Acceptance

- request bindings with `channel_type=qq*` and no explicit surface resolve to remote `qq`, not `tui`
- local default-surface behavior still works when no remote channel is present
- focused plus broader session/gateway/TUI regressions remain green

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 Shared Interaction Binding Convergence

## Current Execution Slice: P30.5 Shared Interaction Binding Convergence (2026-04-13)

### Why This Slice Is Next

- after the `P30.7` re-audit, the next useful work was no longer manager decomposition by inertia
- the more immediate drift risk was smaller but more dangerous:
  - chat entry requests already normalized `surface/channel_type` through one shared path
  - shared-session mutation/control requests still had their own raw binding handling
  - the TUI gateway client had a third, even thinner but different normalization path
- that kind of split invites silent entrance drift on:
  - remote alias handling
  - trimmed binding metadata
  - default-surface semantics

### Scope

- add one shared interaction-binding normalization seam
- rewire application shared-session bindings through that seam
- rewire the TUI gateway client binding payloads through that seam
- preserve the current rule that missing `surface` should stay unset unless a real source/default exists

### Out Of Scope

- no session truth redesign
- no remote adapter behavior redesign
- no `origin_surface` / `active_surface` semantic rewrite

### Files In Scope

- `src/mini_agent/runtime/interaction_surface.py`
- `src/mini_agent/application/interaction_request_adapter.py`
- `src/mini_agent/application/session_service.py`
- `src/mini_agent/tui/gateway_client.py`
- `tests/test_interaction_surface.py`
- `tests/test_interaction_request_adapter.py`
- `tests/test_session_service.py`
- `tests/test_tui_gateway_client.py`
- `tests/test_session_remote_service.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Add one shared normalized interaction-binding helper.
2. Rewire chat/application binding construction to consume the same helper.
3. Rewire shared-session operation bindings and the TUI gateway client through the same helper.
4. Lock alias/default behavior with focused tests, then re-run broader session/gateway/TUI regressions.

### Acceptance

- chat and shared-session operations no longer normalize interaction bindings through separate local rules
- TUI gateway payloads no longer preserve raw adapter aliases like `qqbot` while the runtime expects normalized `qq`
- empty surface inputs do not get forced into fake values for session mutations
- focused plus broader gateway/session/TUI regressions stay green

### Status

- completed

## Latest Sync: 2026-04-13 P30.7ap Runtime Manager Re-Audit + Natural Stop Check

## Current Execution Slice: P30.7ap Runtime Manager Re-Audit + Natural Stop Check (2026-04-13)

### Why This Slice Is Next

- after the three post-audit behavior cuts landed, the next question was no longer "what should we extract next?"
- the better question was "has `P30.7` reached a natural stop?"
- without that explicit re-audit, it would be too easy to keep refactoring by inertia instead of by ownership need

### Scope

- re-scan the runtime manager method surface after the recent extractions
- distinguish:
  - long but acceptable composition wiring
  - thin facade methods with parameter-heavy signatures
  - any remaining mixed-responsibility hotspots
- remove any truly dead residual helper shells found during the audit

### Out Of Scope

- no new large extraction track in this slice
- no runtime behavior redesign
- no contract changes

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Re-quantify current runtime-manager method distribution.
2. Re-check the remaining larger methods against their current bodies.
3. Remove any dead residual helper shells if they are truly unused.
4. Record whether `P30.7` should continue or naturally stop here.

### Acceptance

- `P30.7` continuation is justified by ownership evidence, not inertia
- dead residual helper shells are removed if found
- active notes clearly state whether runtime-manager decomposition should pause

### Status

- completed

## Latest Sync: 2026-04-13 P30.7ao Lineage Registry Helper Extraction

## Current Execution Slice: P30.7ao Lineage Registry Helper Extraction (2026-04-13)

### Why This Slice Is Next

- after the model-selection and derived-session cuts, the remaining manager-owned hotspot from the audit was lineage graph mutation
- the runtime manager still owned:
  - lineage root resolution
  - node registration/update rules
  - node removal routing
- that logic was runtime-private and cohesive enough for one small helper extraction

### Scope

- move lineage registration/removal rules into a dedicated runtime lineage helper
- keep the existing `runtime._session_lineage` store object visible for current test and debug seams
- keep manager behavior unchanged outside of delegation to the helper

### Out Of Scope

- no lineage DTO changes
- no persistence schema changes
- no session ancestry behavior redesign

### Files In Scope

- `src/mini_agent/runtime/session_lineage_registry.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Add one runtime lineage helper around `SessionLineageStore`.
2. Rewire manager registration/removal flows through the helper.
3. Preserve the existing `_session_lineage` observation seam.
4. Re-run lineage/derived-session plus broader runtime/session/TUI verification.

### Acceptance

- lineage graph mutation rules no longer live inline in `MainAgentRuntimeManager`
- existing lineage behavior and test seams remain intact
- runtime/session/TUI verification remains green

### Status

- completed

## Latest Sync: 2026-04-13 P30.7an Derived Session Creation Extraction

## Current Execution Slice: P30.7an Derived Session Creation Extraction (2026-04-13)

### Why This Slice Is Next

- after the model-selection cut, `create_derived_session(...)` was the clearest remaining manager method still assembling a non-trivial runtime payload inline
- it was still deciding:
  - how to inherit the parent session's selected model
  - how to inherit context/sandbox state
  - how to shape lineage metadata for the child
- that belongs with session creation/registry + hydration code, not the outer runtime facade

### Scope

- move derived-session payload assembly into the hydration builder
- move derived-session creation orchestration into the session registry handler
- keep parent lookup under the manager's `_store_lock`
- unify direct `create_session(...)` session-id allocation with the existing allocator

### Out Of Scope

- no derived-session behavior redesign
- no delegation UX changes
- no lineage schema changes

### Files In Scope

- `src/mini_agent/runtime/session_hydration_builder.py`
- `src/mini_agent/runtime/session_registry_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Add one hydration-builder method for derived-session payload inheritance.
2. Add one registry-handler method for derived-session creation.
3. Rewire manager `create_derived_session(...)` into lock + parent lookup + delegation only.
4. Reuse the runtime session-id allocator for direct `create_session(...)`.
5. Re-run derived-session/delegation plus broader runtime/session/TUI verification.

### Acceptance

- `MainAgentRuntimeManager.create_derived_session(...)` no longer assembles inherited payload state inline
- derived-session creation now lives with session registry/hydration code
- direct session creation uses the same allocator path as the rest of runtime session creation
- runtime/session/TUI verification remains green

### Status

- completed

## Latest Sync: 2026-04-13 P30.7am Model Selection Request Resolution Extraction

## Current Execution Slice: P30.7am Model Selection Request Resolution Extraction (2026-04-13)

### Why This Slice Is Next

- the runtime hotspot audit identified `update_session_model_selection(...)` as the smallest remaining operator-facing method that still owned real request semantics
- specifically, the manager was still deciding:
  - whether `provider_source` was missing
  - how to infer it
  - how to convert inference failure into operator-facing `400` responses
- that belongs with model-selection request semantics, not the outer runtime coordinator

### Scope

- move `provider_source` inference and request normalization into the model-selection handler
- let the runtime manager stop interpreting model-selection requests locally
- keep session lookup, runtime application, and operator-visible behavior unchanged

### Out Of Scope

- no model registry redesign
- no session rebuild behavior changes
- no DTO or gateway contract changes

### Files In Scope

- `src/mini_agent/runtime/session_model_selection_handler.py`
- `src/mini_agent/runtime/session_operator_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Add one model-selection handler entrypoint that resolves/infers a concrete request identity.
2. Rewire operator model-selection updates through that handler-owned resolution path.
3. Remove manager-local `provider_source` inference.
4. Re-run focused plus broader runtime/session/TUI verification.

### Acceptance

- `MainAgentRuntimeManager.update_session_model_selection(...)` no longer infers `provider_source` itself
- model-selection request resolution lives with the model-selection handler
- inferred-source behavior and failure semantics remain green in runtime/session/TUI verification

### Status

- completed

## Latest Sync: 2026-04-13 P30.7al Runtime Hotspot Audit

## Current Execution Slice: P30.7al Runtime Hotspot Audit (2026-04-13)

### Why This Slice Is Next

- after removing the obvious file-top residue from `MainAgentRuntimeManager`, the next risk was refactoring by line count instead of by ownership
- before opening another implementation slice, the runtime manager needed a fresh audit to separate:
  - long-but-acceptable composition wiring
  - genuinely mixed remaining behavior hotspots

### Scope

- inspect the current runtime manager method surface after the persistence + session-state extractions
- compare the remaining larger methods against already-extracted runtime handlers
- identify which remaining logic still belongs outside the manager
- record any correctness inconsistencies exposed by the audit

### Out Of Scope

- no runtime behavior changes in this slice
- no new handler extraction yet
- no API contract changes

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/runtime/session_registry_handler.py`
- `src/mini_agent/runtime/session_operator_handler.py`
- `src/mini_agent/runtime/session_model_selection_handler.py`
- `src/mini_agent/application/session_service.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Quantify the current runtime-manager method surface instead of judging by file size alone.
2. Inspect the remaining larger methods against adjacent handlers to identify real boundary leaks.
3. Record the recommended next cut order and any small correctness inconsistencies.

### Acceptance

- the next `P30.7` cut is chosen by ownership/hotspot evidence instead of file geography
- long composition methods that are structurally acceptable are explicitly ruled out
- real remaining hotspots are written down in priority order

### Status

- completed

## Latest Sync: 2026-04-13 P30.7ak Session State Model Extraction

## Current Execution Slice: P30.7ak Session State Model Extraction (2026-04-13)

### Why This Slice Is Next

- after the runtime persistence cut, the most obvious remaining file-top residue in `MainAgentRuntimeManager` was the `MainAgentSession*` state cluster
- unlike the persistence wrapper, these types were referenced broadly across runtime collaborators
- that made them a real architectural boundary concern:
  - the shared session state of the runtime was still physically anchored inside the outer runtime facade
- once persistence had already moved out cleanly, this became the natural second cut

### Scope

- move the runtime session state dataclasses out of `main_agent_runtime_manager.py`
- establish one dedicated shared state module for:
  - session state
  - projection state
  - transcript state and entries
  - runtime host state
  - lineage state
- rewire runtime/application imports to use the new shared state module directly

### Out Of Scope

- no session behavior redesign
- no DTO/schema changes
- no new session abstraction beyond relocating the existing shared types

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/runtime/session_state.py`
- `src/mini_agent/runtime/__init__.py`
- `src/mini_agent/application/session_service.py`
- runtime collaborator modules importing `MainAgentSession*`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Create a dedicated runtime session-state module.
2. Move `MainAgentSession*` models out of `main_agent_runtime_manager.py`.
3. Rewire runtime/application modules to import shared session-state types from the new module.
4. Re-run static checks plus runtime/session/TUI verification bundles and the readiness walkthrough.

### Acceptance

- `MainAgentRuntimeManager` no longer physically owns the shared session-state model definitions
- runtime collaborators import shared session-state types from one dedicated module
- runtime/session/TUI verification remains green after the type relocation

### Status

- completed

## Latest Sync: 2026-04-13 P30.7aj Runtime Persistence Extraction

## Current Execution Slice: P30.7aj Runtime Persistence Extraction (2026-04-13)

### Why This Slice Is Next

- after the latest `P30.7` audit, the remaining runtime-manager thickness at the file top was no longer one large behavior blob
- it was two different kinds of residue:
  - the gateway-managed persistence wrapper
  - the session-state dataclass cluster
- the persistence wrapper was the safer next cut because:
  - it was effectively private to `MainAgentRuntimeManager`
  - it already had a coherent responsibility boundary
  - extracting it would reduce file-top ownership clutter without forcing a broad type-import migration in the same slice

### Scope

- move the runtime session persistence wrapper out of `main_agent_runtime_manager.py`
- keep persistence behavior unchanged:
  - session record save/load/delete
  - shared transcript sidecar persistence
  - metadata registry updates
- rewire runtime-manager composition to use the extracted persistence module

### Out Of Scope

- no session-state dataclass extraction in this slice
- no persistence schema changes
- no application or gateway contract changes

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/runtime/session_runtime_persistence.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Extract `_MainAgentRuntimePersistence` into a dedicated runtime persistence module.
2. Rewire manager bootstrap to depend on the extracted module.
3. Re-run focused runtime/session/TUI verification and the readiness walkthrough.
4. Record the result and identify the next remaining top-of-file hotspot.

### Acceptance

- `MainAgentRuntimeManager` no longer embeds the runtime session persistence wrapper implementation
- persistence behavior remains unchanged for save/load/delete plus transcript sidecars
- runtime/session/TUI verification stays green after the extraction

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI-CLI Model Use Request Convergence

## Current Execution Slice: P30.5 TUI-CLI Model Use Request Convergence (2026-04-13)

### Why This Slice Is Next

- after the remote memory mutation cut, `model use` was the clearest remaining operator request that still duplicated catalog-validation logic across terminal entrances
- `TUI` and `CLI` were both still deciding:
  - usage validity
  - provider existence
  - model existence inside the selected provider
- that is smaller than the earlier remote command shells, but it is still avoidable entrance duplication

### Scope

- add one shared helper that resolves `/model use` requests against a provider catalog snapshot
- rewire `TUI` and `CLI` model-use handling to consume that helper
- keep runtime/gateway ownership of actual selection application unchanged

### Out Of Scope

- no model registry redesign
- no remote model response contract changes
- no TUI model panel redesign

### Files In Scope

- `src/mini_agent/commands/execution.py`
- `src/mini_agent/commands/__init__.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/cli_interactive.py`
- `tests/test_command_execution_service.py`
- `tests/test_tui_app.py`
- `tests/test_cli_submission_loop.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Add one shared `model use` catalog-resolution helper in the shared command layer.
2. Replace duplicated `provider/model` validation in `TUI`.
3. Replace duplicated `provider/model` validation in `CLI`.
4. Re-run focused and broader regressions, then record the cut.

### Acceptance

- `TUI` and `CLI` no longer keep separate catalog-resolution logic for `/model use`
- shared tests lock the helper contract for:
  - success
  - usage
  - provider missing
  - model missing
- related TUI/CLI regressions remain green

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI Remote Memory Mutation Convergence

## Current Execution Slice: P30.5 TUI Remote Memory Mutation Convergence (2026-04-13)

### Why This Slice Is Next

- the previous remote memory cut intentionally stopped at the read-heavy branches
- that left the last clearly thicker `TUI` memory mutation shell in:
  - `memory promote`
  - `memory save`
- these branches were no longer carrying unique business meaning
- they were mostly carrying their own execute/error/render wrappers

### Scope

- rewire remote/local `memory promote` and `memory save` through the shared memory execution helper
- strengthen fake-gateway mutation behavior so remote memory mutation tests reflect real transcript/result shapes more closely
- re-run broader `TUI` regression coverage after the convergence cut

### Out Of Scope

- no memory API redesign
- no new memory abstraction layer
- no gateway contract changes

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Rewire `memory promote` through `_execute_memory_command_plan(...)`.
2. Rewire `memory save` through `_execute_memory_command_plan(...)`.
3. Add focused remote mutation tests and make fake gateway mutation transcripts more truthful.
4. Re-run `ruff` plus the full `test_tui_app.py` suite and record the result.

### Acceptance

- `memory promote` and `memory save` no longer keep custom execute/render shells in `TUI`
- focused remote mutation tests cover gateway-backed `promote` / `save`
- `test_tui_app.py` stays green after the cut

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI Remote Memory Read-Path Convergence

## Current Execution Slice: P30.5 TUI Remote Memory Read-Path Convergence (2026-04-13)

### Why This Slice Is Next

- after remote context convergence, `memory` was the clearest remaining thick remote command family in `TUI`
- the highest duplication was concentrated in repeated:
  - run action
  - unpack `result`
  - append feedback
  - set status
  - error rendering
- the safest first cut was the remote/read-heavy side of memory, not the more stateful mutation flows

### Scope

- centralize repeated memory command execution/rendering in `TUI`
- cover read-heavy memory actions first
- preserve command behavior and response content

### Out Of Scope

- no remote memory mutation redesign for `promote` / `save` in this slice
- no memory contract redesign
- no gateway API changes

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Add one shared memory result/execution helper in `TUI`.
2. Rewire repeated read-heavy memory actions through that helper.
3. Re-run focused remote memory regressions plus broader memory checks.
4. Record the remaining mutation hotspot explicitly.

### Acceptance

- remote/read-heavy memory actions no longer each carry their own full try/result/render shell
- focused remote memory tests stay green
- active notes identify what still remains in `memory`

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI Remote Context Request Convergence

## Current Execution Slice: P30.5 TUI Remote Context Request Convergence (2026-04-13)

### Why This Slice Is Next

- after remote control dispatch convergence, remote `context` still had one clear split-brain shape
- the shared command service already validated and normalized context-update intent
- but `TUI` remote handling still re-parsed raw args to rebuild the remote request
- that meant the entrance still owned a second copy of part of the command meaning

### Scope

- let shared `execute_context(...)` produce structured remote update request data
- let `TUI` remote context updates consume that structured request directly
- align remote context binding metadata with the rest of the remote request paths

### Out Of Scope

- no remote memory convergence in this slice
- no context read-only (`show` / `stats`) redesign
- no gateway contract redesign

### Files In Scope

- `src/mini_agent/commands/execution.py`
- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Extend shared context execution payloads with structured remote-request data.
2. Add one remote context update dispatcher in `TUI`.
3. Remove TUI-side remote arg re-parsing for include/exclude/budget/reset.
4. Lock the new request shape with focused tests.

### Acceptance

- remote context updates no longer rebuild request structure from raw args inside `TUI`
- remote context requests now carry aligned binding metadata
- focused tests prove both include and budget requests are structured correctly

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI Remote Control Dispatch Convergence

## Current Execution Slice: P30.5 TUI Remote Control Dispatch Convergence (2026-04-13)

### Why This Slice Is Next

- after removing the worst remote busy-conflict forks, `TUI` still repeated remote control request orchestration
- the duplication was concentrated in:
  - remote request assembly
  - gateway error-detail handling
  - post-control remote detail sync
- `mcp_*` and context-control were still close enough to count as parallel entrance shells

### Scope

- centralize remote control dispatch for `TUI`
- reuse one request/error/sync path for remote `mcp` and remote context-control
- align remote context-control with the same binding payload style already used by remote `mcp`

### Out Of Scope

- no KB remote-control convergence in this slice
- no local command-path redesign
- no gateway contract redesign

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Add one remote control dispatch helper in `TUI`.
2. Rewire remote context-control through that helper.
3. Rewire remote `mcp` through that helper.
4. Update focused tests for the aligned binding payload and remote-control regressions.

### Acceptance

- remote `mcp` and remote context-control share one dispatch/error/sync seam
- remote context-control now carries the same remote binding metadata style as the other remote control commands
- focused regressions stay green after the helper extraction

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI Remote Control Conflict Convergence

## Current Execution Slice: P30.5 TUI Remote Control Conflict Convergence (2026-04-13)

### Why This Slice Is Next

- after remote `skill` and remote approval convergence, the next visible `TUI` drift point was remote control conflict handling
- `TUI` still kept local `busy` branches for:
  - `compact`
  - `drop_memories`
  - `mcp reload`
- but the shared session-control path already owns the canonical busy-conflict rule

### Scope

- remove local remote-session busy prechecks for `context-control` and `mcp reload`
- reuse shared gateway conflict detail for remote control failures
- keep local busy handling unchanged

### Out Of Scope

- no full remote `mcp` command convergence in this slice
- no local context-control redesign
- no gateway contract redesign

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Centralize remote control error-detail rendering in `TUI`.
2. Remove remote-only busy special casing for `compact` / `drop_memories` / `mcp reload`.
3. Update fake gateway control behavior to simulate shared busy conflicts.
4. Re-run focused remote control regressions.

### Acceptance

- remote busy conflicts for context-control and `mcp reload` are now decided by the shared gateway/runtime path
- `TUI` no longer keeps separate busy wording forks for those remote commands
- focused tests prove the gateway is called before the conflict is surfaced

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI Remote Approval Convergence

## Current Execution Slice: P30.5 TUI Remote Approval Convergence (2026-04-13)

### Why This Slice Is Next

- after the remote `skill` cut, the next obvious `TUI` command-shell hotspot was remote approval handling
- `TUI` was still deciding too much approval meaning locally for gateway-backed sessions:
  - whether anything is pending
  - whether restart loss should be surfaced
  - whether one pending approval should auto-select a token
  - whether multiple pending approvals should force a token
- those rules already belong to the shared runtime approval path

### Scope

- remove remote approval-selection semantics from `TUI`
- let the shared gateway/runtime approval path decide token resolution and restart-loss conflicts
- keep local approval behavior unchanged

### Out Of Scope

- no local approval redesign
- no remote MCP/context-control convergence in this slice
- no gateway contract redesign

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Split remote approval handling from local approval handling inside `TUI`.
2. Remove remote local-precheck logic for pending/restart-loss/token selection.
3. Normalize remote gateway error detail rendering for approval failures.
4. Update fake gateway and focused tests to follow shared approval semantics.

### Acceptance

- remote `TUI` approval no longer chooses tokens locally
- remote restart-loss and multiple-pending behavior now come from the shared gateway/runtime path
- focused approval tests verify the new command boundary explicitly

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI Remote Skill Convergence

## Current Execution Slice: P30.5 TUI Remote Skill Convergence (2026-04-13)

### Why This Slice Is Next

- the `P30.5` audit identified `TUI` remote command handling as the main remaining entrance-convergence hotspot
- within that hotspot, `skill` was the safest first cut:
  - local `TUI` already routes skill semantics through the shared command service
  - remote `TUI` still owned a large action-by-action command shell
- this made remote `TUI` look too much like a second command executor

### Scope

- collapse the remote `skill` action tree in `TUI`
- move argument-shape validation, command naming, and response rendering into narrower helpers
- keep user-visible behavior stable while reducing command-shell duplication

### Out Of Scope

- no remote approval convergence in this slice
- no remote MCP/context-control convergence in this slice
- no gateway contract redesign

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Introduce one normalized remote skill command plan for `TUI`.
2. Replace the remote `if/elif` action tree with table-driven parse + execute + render helpers.
3. Lock the mutation-sync path so uninstall/rollback refresh behavior does not drift.
4. Re-run focused TUI skill checks.

### Acceptance

- remote `TUI` skill handling no longer owns a long action-by-action branch tree
- usage/unknown-action handling is centralized for remote skill commands
- remote skill mutation sync behavior is explicit and tested

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 Shared Entrance Command Convergence Audit

## Current Execution Slice: P30.5 Shared Entrance Command Convergence Audit (2026-04-13)

### Why This Slice Is Next

- `P30.4` is now effectively closed from a remote-adapter boundary perspective
- the next drift risk is no longer `QQ`
- the real question is whether `CLI / TUI / Remote Interaction` are actually reusing the same command semantics, or whether one of them is quietly regrowing a second command executor
- before cutting more code, we need one written audit so the next implementation step aims at the correct hotspot

### Scope

- inspect the current shared command core
- compare how `CLI`, `TUI`, and the remote path consume it
- identify which surface still owns too much command meaning
- record the recommended first `P30.5` implementation cuts

### Out Of Scope

- no new command-service abstraction in this slice
- no QQ feature work in this slice
- no TUI refactor yet

### Files In Scope

- `src/mini_agent/commands/router.py`
- `src/mini_agent/commands/execution.py`
- `src/mini_agent/cli_interactive.py`
- `src/mini_agent/tui/app.py`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Confirm what shared command parsing/execution already exists.
2. Compare `CLI` usage of the shared layer versus `TUI` usage.
3. Re-evaluate whether `QQ` is still the main convergence target.
4. Write the next implementation target into the active plan.

### Acceptance

- active notes explicitly state that `P30.5` starts from entrance-command convergence, not more QQ cleanup
- the docs identify the main remaining hotspot correctly
- the next implementation cut is narrowed to the most drift-prone surface

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 QQ Tail Cleanup + Closure Check

## Current Execution Slice: P30.4 QQ Tail Cleanup + Closure Check (2026-04-13)

### Why This Slice Is Next

- after the approval, runtime-policy, and MCP thinning cuts, the remaining QQ questions were no longer about major business-logic ownership
- what remained was:
  - one small UX bug in `/status`
  - one small wording inconsistency in `/cancel`
  - and the need to decide whether `P30.4` could now close cleanly

### Scope

- avoid duplicate replies when `/status` probes shared-session binding but falls back to local status
- reuse shared cancel-conflict wording for `/cancel`
- record the resulting boundary judgment for `P30.4`

### Out Of Scope

- no further remote binding redesign
- no stream/presenter redesign
- no additional QQ feature work in this slice

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Make shared-session binding checks optionally silent for read-only status probing.
2. Remove QQ-local cancel wording drift by reusing shared gateway detail.
3. Reconfirm whether the remaining QQ logic is adapter-appropriate.
4. Sync the closure judgment into active notes.

### Acceptance

- `/status` no longer double-replies when no shared session is bound
- `/cancel` now reflects the shared conflict detail instead of a QQ-local wording fork
- active notes explicitly state that `P30.4` is ready to close

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 QQ Runtime Policy + MCP Command Thinning

## Current Execution Slice: P30.4 QQ Runtime Policy + MCP Command Thinning (2026-04-13)

### Why This Slice Is Next

- after the approval-command cut, the remaining low-cost adapter semantics were concentrated in:
  - `/plan` `/build` `/default` `/full_access`
  - `/mcp status|list|reload`
  - `/compact` `/drop_memories`
- the problem was smaller than approval, but still visible:
  - runtime-policy commands still derived behavior from command-name branching
  - control commands still encoded command-to-action meaning locally
  - `/mcp reload` still had a QQ-local busy special case instead of reusing shared control errors

### Scope

- move runtime-policy command meaning into QQ dispatch metadata instead of handler-owned command-name checks
- move `/compact` and `/drop_memories` action identity into dispatch metadata
- keep `/mcp` as a thin subcommand router but remove QQ-local busy special casing
- surface shared gateway/runtime error details consistently for policy/control commands

### Out Of Scope

- no shared command catalog JS runtime integration
- no gateway API redesign
- no WeChat adapter changes in this slice

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Extend QQ command-entry metadata to carry runtime-policy payloads.
2. Rewire `/plan` `/build` `/default` `/full_access` to use dispatch metadata.
3. Rewire `/compact` and `/drop_memories` to use dispatch metadata.
4. Thin `/mcp` to subcommand-to-action mapping plus shared error detail forwarding.
5. Re-run QQ static checks and focused runtime-policy / MCP gateway regressions.

### Acceptance

- QQ runtime-policy commands no longer decide behavior by branching on command names
- QQ control commands carry less command-specific meaning in handler bodies
- `/mcp reload` busy/error behavior comes from shared control handling instead of QQ-local wording

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 QQ Approval Command Thinning

## Current Execution Slice: P30.4 QQ Approval Command Thinning (2026-04-13)

### Why This Slice Is Next

- after thinning QQ request assembly, command dispatch, model selection, skill, memory, and context updates, the strongest remaining adapter-owned business semantic was `/approve` / `/deny`
- the QQ handler was still:
  - fetching session detail itself
  - deciding between live and recovery-lost approvals
  - auto-selecting a token when there was only one pending approval
  - and formatting multi-token guidance locally
- that logic already exists in shared runtime approval handling, so keeping it in QQ would just recreate a second approval-selection policy at the surface edge

### Scope

- remove QQ-local pending-approval inspection before resolving approvals
- let the shared gateway/runtime approval path own:
  - missing-approval conflict handling
  - restart-lost approval messaging
  - single-token implicit selection
  - multi-token conflict guidance
- keep QQ responsible only for command input capture and remote reply formatting

### Out Of Scope

- no approval API redesign
- no TUI approval-command rewrite in this slice
- no stream/presenter changes for remote activity or approval events

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Remove QQ-local approval detail fetch and token-selection branching.
2. Route `/approve` and `/deny` directly to the shared approval endpoint with an optional token.
3. Reuse shared gateway/runtime error detail for lost approvals, missing approvals, and multi-token conflicts.
4. Re-run focused QQ and approval-flow verification.

### Acceptance

- QQ no longer owns approval-selection semantics
- shared runtime is the single authority for pending-approval resolution behavior
- remote approval behavior stays stable while adapter logic gets thinner

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 QQ Memory + Context Command Thinning

## Current Execution Slice: P30.4 QQ Memory + Context Command Thinning (2026-04-13)

### Why This Slice Is Next

- after shrinking QQ `/skill`, the next remaining thick command handlers were `/memory` and `/context`
- both handlers still carried long action-specific branch trees even though the shared runtime already owns most of the real validation and mutation semantics
- this made the QQ adapter look too much like a second command executor instead of a remote payload router

### Scope

- reduce QQ `/memory` to a thinner action-to-payload translation layer
- reduce QQ `/context` update commands to a thinner payload-routing layer
- keep local-only detail rendering for `context show` and `context stats`
- keep user-visible behavior stable while moving more validation weight back to the shared runtime/gateway path

### Out Of Scope

- no gateway API redesign
- no TUI/CLI command changes
- no shared command parser rewrite in this slice

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Replace the large QQ `/memory` action tree with thinner payload mapping.
2. Let the shared session memory handler own more missing-argument and selector validation.
3. Replace the QQ `/context` update branch tree with thinner payload routing.
4. Keep only `show` / `stats` rendering local in QQ for prepared-context inspection.
5. Re-run QQ adapter static verification.

### Acceptance

- QQ `/memory` is materially thinner and less action-semantic-heavy
- QQ `/context` update actions are thinner and rely more on shared runtime validation
- adapter-local command logic is reduced without changing the shared command contract

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 QQ Skill Command Thinning

## Current Execution Slice: P30.4 QQ Skill Command Thinning (2026-04-13)

### Why This Slice Is Next

- after moving shared model-selection disambiguation out of QQ, the next thick adapter spot was `/skill`
- the QQ handler still carried a long action-by-action branch tree even though the shared runtime skill handler already owned most of the real validation and mutation semantics
- the catalog also already exposed `uninstall` and `rollback` for QQ, but the live QQ handler had not caught up

### Scope

- reduce QQ `/skill` to a thinner payload-routing layer
- keep only minimal action-shape checks in the adapter
- defer missing-argument and mutation validation back to the shared session skill handler
- align QQ `/skill` with the catalog by supporting `uninstall` and `rollback`

### Out Of Scope

- no new gateway endpoint
- no shared command-parser redesign
- no change to TUI/CLI `/skill` behavior

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Add one small gateway-error detail formatter for QQ command replies.
2. Replace the long `/skill` action branch tree with a thinner action-to-payload mapping.
3. Let the shared session skill handler own more of the usage/validation path.
4. Align QQ `/skill` with the command catalog for `uninstall` and `rollback`.
5. Re-run QQ adapter static verification.

### Acceptance

- QQ `/skill` is materially thinner and less action-semantic-heavy
- QQ now supports the same catalog-declared `skill uninstall` / `skill rollback` actions
- shared runtime skill validation is now more authoritative than adapter-local branching

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 Shared Model-Selection Source Inference

## Current Execution Slice: P30.4 Shared Model-Selection Source Inference (2026-04-13)

### Why This Slice Is Next

- after the QQ command-scope cleanup, one especially meaningful piece of model-routing logic still lived in the QQ adapter
- `QQ /model use` still fetched the model catalog and decided:
  - whether a provider existed
  - whether a provider id was ambiguous
  - whether a model existed under that provider
- that is already model-routing semantics, not just channel adaptation

### Scope

- add one shared model-selection resolver that can infer `provider_source` when the provider/model pair is uniquely resolvable
- allow shared-session model selection requests to omit `provider_source`
- simplify QQ `/model use` so it forwards `provider_id + model_id` and relies on shared resolution

### Out Of Scope

- no change to TUI/CLI `/model` syntax
- no change to the selected/queued model response shape
- no catalog redesign

### Files In Scope

- `src/mini_agent/model_manager/runtime.py`
- `src/mini_agent/interfaces/agent.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/tui/gateway_client.py`
- `src/apps/qqbot_channel/bot.mjs`
- `tests/test_model_routing_runtime.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `tests/test_interface_dto_contracts.py`
- `tests/test_session_remote_service.py`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Add one shared resolver for session-scoped model selection identity.
2. Let shared-session model-selection requests omit `provider_source`.
3. Resolve the missing source in shared runtime before model-selection execution.
4. Remove QQ-side provider/model catalog disambiguation from `/model use`.
5. Add focused tests for unique inference and ambiguous-source rejection.

### Acceptance

- QQ no longer owns provider-source disambiguation for `/model use`
- shared runtime can resolve a unique provider/model pair into a complete session model-selection identity
- ambiguous provider/model pairs now fail from shared logic instead of adapter-local logic

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 QQ Command Scope Dispatch Thinning

## Current Execution Slice: P30.4 QQ Command Scope Dispatch Thinning (2026-04-13)

### Why This Slice Is Next

- after the QQ request-helper thinning cut, one structural smell still remained in the adapter
- shared-session dependency was being enforced ad hoc inside many individual QQ command handlers
- that worked, but it kept one entrance-level routing rule scattered across the handler bodies instead of declaring it at the command-dispatch seam

### Scope

- make QQ command dispatch explicitly distinguish between:
  - local adapter commands
  - shared-session-scoped commands
- move the repeated shared-session binding guard from handlers into the command registry / dispatch path
- keep the concrete command behavior unchanged

### Out Of Scope

- no remote command semantic redesign
- no gateway/application API change
- no cross-surface command unification in this slice

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Add one QQ command-entry helper with `requiresSharedSession` metadata.
2. Mark shared-session-scoped QQ commands explicitly in the registry.
3. Enforce the shared-session guard once in command dispatch.
4. Remove the repeated per-handler guard where dispatch now owns it.
5. Sync the active refactor notes.

### Acceptance

- QQ command dispatch now explicitly models local vs shared-session command scope
- repeated `ensureSharedSessionBound(...)` checks are reduced in handler bodies
- behavior remains unchanged while the adapter boundary becomes clearer

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 QQ Adapter Request Helper Thinning

## Current Execution Slice: P30.4 QQ Adapter Request Helper Thinning (2026-04-13)

### Why This Slice Is Next

- after the remote binding state-thinning cut, the next useful `P30.4` cleanup was inside the active QQ adapter request path
- several QQ shared-session mutation commands were still hand-assembling the same remote mutation envelope again and again
- that duplication was small, but it kept the adapter thicker than it needs to be and made the thin-adapter boundary easier to erode later
- WeChat was reviewed in the same pass and intentionally left alone because its current gateway assembly is still below the duplication threshold

### Scope

- extract thin QQ-local helpers for shared-session mutation payload assembly
- reuse them across the QQ shared-session mutation commands
- keep the change inside the adapter file instead of inventing a new shared remote business layer

### Out Of Scope

- no remote command redesign
- no gateway/application contract changes
- no forced WeChat symmetry refactor

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Add one QQ sender-id helper.
2. Add one QQ shared-session mutation payload helper.
3. Add one QQ shared-session POST-envelope helper for gateway mutation endpoints.
4. Rewire the repeated QQ mutation commands to use those helpers.
5. Record why WeChat was intentionally left unchanged in this slice.

### Acceptance

- QQ shared-session mutation commands no longer hand-assemble the same remote mutation envelope repeatedly
- helper extraction stays inside the QQ adapter and does not create a new business layer
- the code record explicitly states that WeChat was reviewed and left unchanged on purpose

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 Remote Binding State Thinning

## Current Execution Slice: P30.4 Remote Binding State Thinning (2026-04-13)

### Why This Slice Is Next

- after the naming tightening, the next useful `P30.4` step is to keep shrinking adapter-local state itself
- QQ still stored one per-conversation display field that was actually global process configuration
- WeChat binding state still exposed an unused `metadata` field in the binding contract even though the active implementation did not need it

### Scope

- remove obviously redundant per-conversation state from the QQ adapter
- remove unused metadata from the remote conversation binding contract
- keep remote behavior unchanged while making adapter-local state thinner and clearer

### Out Of Scope

- no new remote commands
- no gateway/application contract redesign
- no cross-channel feature additions

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `src/channels/types/src/index.ts`
- `docs/P30_SESSION_TRUTH_BOUNDARY_MAP_2026-04-13.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Rename the QQ adapter local map to binding-oriented terminology.
2. Drop per-conversation `botName` state and use the global configured bot name directly.
3. Remove unused `metadata` from `RemoteConversationBindingState`.
4. Sync the boundary map so QQ/WeChat cached fields match the live code.
5. Re-run remote adapter static verification.

### Acceptance

- QQ per-conversation cache no longer stores global bot display config
- remote binding contract is thinner and closer to actual live use
- remote adapter static checks remain green

### Status

- completed

## Latest Sync: 2026-04-13 P30.3 Operator-Flow State Split

## Current Execution Slice: P30.3 Operator-Flow State Split (2026-04-13)

### Why This Slice Is Next

- after the supplemental cache split, one obvious mixed area still remained inside TUI state composition
- `pending_model_*` and `pending_skill_reload*` were still living on `TuiSessionProjectionState`
- those fields drive local operator flow, and even when they mirror gateway detail they are still weaker than shared session projection semantics inside the TUI

### Scope

- add one dedicated TUI-local operator-flow state bucket
- move pending model-selection and pending skill-reload state there
- keep shared DTOs and runtime/session contracts unchanged

### Out Of Scope

- no gateway/session DTO redesign
- no runtime pending-model redesign
- no remote adapter changes in this slice

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `docs/P30_SESSION_TRUTH_BOUNDARY_MAP_2026-04-13.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Introduce `TuiSessionOperatorState`.
2. Move pending model-selection state into that slice.
3. Move pending skill-reload state into that slice.
4. Keep summary projection rendering working by mapping operator state back into `SessionSummaryProjection`.
5. Re-run focused and broader TUI/session verification.

### Acceptance

- `TuiSession` is now composed as projection/operator/runtime/view for TUI-owned state
- TUI no longer stores pending model / skill-reload flow on projection itself
- TUI model queueing and skill-reload flows still work

### Status

- completed

## Latest Sync: 2026-04-13 P30.3 Supplemental Cache Split + P30.4 Naming Tightening

## Current Execution Slice: P30.3 Supplemental Cache Split + P30.4 Naming Tightening (2026-04-13)

### Why This Slice Is Next

- the framework skeleton and session-truth boundary map are now locked
- one `P30.3` tightening cut already landed in code:
  - TUI sync / recovery summaries moved under `TuiSessionSupplementalState`
- but the active docs and dev records still described those fields as if they belonged to projection proper
- remote adapters also still carried one especially misleading name:
  - `SessionState`
  - even though the corrected architecture treats that object as adapter-side conversation binding metadata only

### Scope

- sync active docs and dev records to the landed `supplemental` split
- tighten remote adapter naming away from fake session ownership semantics
- keep behavior unchanged while making boundaries harder to misunderstand

### Out Of Scope

- no new session lifecycle behavior
- no remote command redesign
- no new transport/API surface

### Files In Scope

- `docs/P30_SESSION_TRUTH_BOUNDARY_MAP_2026-04-13.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `src/channels/types/src/index.ts`
- `src/channels/wechat/src/channel.ts`
- `src/channels/wechat/src/conversation_binding_store.ts`
- `src/channels/wechat/src/index.ts`
- `src/apps/qqbot_channel/bot.mjs`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Update the boundary map so `supplemental` is documented as a distinct TUI-local cache layer.
2. Update the active P30 execution notes to reflect that `P30.3` is now a tightening phase.
3. Rename the remote adapter-side `SessionState` contract to a conversation-binding name.
4. Keep the active QQ adapter wording aligned with the same thin-binding semantics.
5. Re-run focused Python and TypeScript verification.

### Acceptance

- active docs no longer describe remote summary caches as projection truth
- remote adapter cache types no longer present themselves as canonical session models
- TUI/session and remote/channel checks still pass

### Status

- completed

## Latest Sync: 2026-04-13 P30.2 Session Truth Boundary Lock

## Current Execution Slice: P30.2 Session Truth Boundary Lock (2026-04-13)

### Why This Slice Is Next

- the framework skeleton is now locked, but implementation can still drift unless current state ownership is frozen in writing
- the earlier audit correctly identified TUI and remote adapters as ownership risk zones
- current code has already improved beyond that audit baseline, so the next honest step is:
  - document the current ownership precisely
  - freeze the cache contract
  - use that map as the input for the next real code moves

### Scope

- classify current TUI state fields into:
  - session projection/cache
  - runtime handle
  - view-only state
- classify remote adapter state into:
  - binding convenience
  - delivery/operator preference
  - display metadata
  - accidental domain-risk cache
- define the explicit allowed cache contract for entrances and remote adapters

### Out Of Scope

- no TUI state moves yet
- no remote adapter storage rewrite yet
- no command-system convergence yet

### Files In Scope

- `docs/P30_SESSION_TRUTH_BOUNDARY_MAP_2026-04-13.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `docs/DEVELOPMENT_INDEX.md`
- `src/mini_agent/tui/app.py`
- `src/apps/qqbot_channel/bot.mjs`
- `src/channels/types/src/index.ts`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Audit current TUI state structures and classify each field group.
2. Audit current remote adapter caches and classify their ownership.
3. Write one explicit boundary map document.
4. Add ownership annotations at the key code structures.
5. Re-anchor the P30 plan to this new boundary map.

### Acceptance

- one explicit ownership map exists for TUI and remote adapters
- current code comments now reinforce the intended ownership at the key structs
- `P30.3` and `P30.4` can proceed without rediscovering boundary assumptions

### Status

- completed

## Latest Sync: 2026-04-13 Framework Skeleton Lock

## Current Execution Slice: Framework Skeleton Lock (2026-04-13)

### Why This Slice Is Next

- recent work proved the project can still drift while implementing correct local fixes
- the architecture direction is now broadly right, but the repository still needs one explicit skeleton contract
- without a frozen skeleton, future work can keep repeating the same pattern:
  - solve one real bug
  - then accidentally re-expand the wrong boundary elsewhere

### Scope

- lock one canonical framework skeleton document for the current refactor stage
- freeze:
  - the four-entrance product model
  - the layer stack
  - repository ownership
  - dependency direction
  - no-go drift patterns
- re-anchor active development docs to that skeleton

### Out Of Scope

- no new runtime behavior in this slice
- no new remote feature work in this slice
- no package moves yet unless they are required to document the skeleton honestly

### Files In Scope

- `docs/FRAMEWORK_SKELETON.md`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_INDEX.md`
- `docs/REFACTOR_TASKS.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Define the canonical framework skeleton as an active document.
2. Freeze repository ownership by layer and directory.
3. Write the dependency and no-go drift rules explicitly.
4. Re-anchor development and refactor docs to the new skeleton.
5. Record the new execution guardrail in planning files.

### Acceptance

- one active skeleton document exists and is referenced by the main architecture docs
- entrances, layers, and directory ownership are explicit
- future work has a clear answer for where new code belongs
- the project has an explicit written guardrail against repeating the same boundary drift

### Status

- completed

## Latest Sync: 2026-04-13 Remote Interaction Binding Centralization

## Current Execution Slice: P30.4a Remote Conversation Binding Centralization (2026-04-13)

### Why This Slice Is Next

- the architecture is now explicitly `CLI / TUI / WebUI / Remote Interaction`
- so the next step should strengthen the shared remote entrance, not continue a QQ-specific branch
- current code still leaves `conversation -> session_id` binding in multiple channel-local places:
  - active QQ adapter keeps an in-memory map
  - WeChat keeps a file-backed channel session store
  - Python already has `ConversationBindingStore`, but the active ingress path does not really use it
- that means remote adapters still behave like partial session owners instead of thin channel bridges

### Scope

- centralize remote `conversation -> session_id` binding in the shared application ingress path
- reuse the existing Python `ConversationBindingStore` instead of inventing a second remote binding system
- make `/api/v1/channel/message` able to reuse an existing remote session without the adapter explicitly sending `session_id`
- persist the resolved binding after successful shared chat turns

### Out Of Scope

- no full QQ/WeChat/Feishu adapter rewrite in this slice
- no remote command UX redesign in this slice
- no attempt yet to remove every channel-local convenience field such as workspace defaults

### Files In Scope

- `src/mini_agent/application/channel_ingress_use_cases.py`
- `src/mini_agent/session/binding.py`
- `src/apps/agent_studio_gateway/main.py`
- `scripts/channel_ingress_gateway_walkthrough.py`
- `tests/test_channel_ingress_gateway_walkthrough.py`
- `tests/test_agent_studio_gateway_api_v1.py`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Define one shared remote binding helper around `ConversationBindingStore`.
2. Resolve remote session binding inside `ChannelIngressUseCases` when `session_id` is absent.
3. Persist the returned binding after successful remote chat turns.
4. Update readiness walkthrough/tests so remote reuse no longer depends on adapter-supplied `session_id`.
5. Re-run targeted gateway/channel verification and record the outcome.

### Acceptance

- remote ingress can continue an existing session with only `channel_type + conversation_id`
- the application layer becomes the canonical remote binding path
- channel adapters are no longer required to be the source of truth for `session_id` reuse
- no new remote-specific session subsystem is introduced

### Status

- completed

## Latest Sync: 2026-04-13 Explicit Derived Session Commands

## Current Execution Slice: P23.29 Explicit Task Fork Commands (2026-04-13)

### Why This Slice Is Next

- runtime lineage now exists for import/restore and real `/delegate` child sessions
- but operators still had no explicit way to fork a focused child task/session themselves
- that meant the new derived-session seam existed in runtime, but not yet in user-facing execution flow

### Scope

- add one explicit derived-session creation API on top of the existing runtime lineage path
- expose it in TUI as `/fork [task_prompt]`
- expose one canonical alias form in TUI as `/task new [task_prompt]`
- when a prompt is supplied, switch into the child session and run the first turn there through the existing chat path

### Out Of Scope

- no new lineage browsing UI yet
- no QQ/CLI parity for explicit fork in this slice
- no new child-session ownership/reply-binding semantics beyond the existing derived-session defaults

### Files In Scope

- `src/mini_agent/interfaces/agent.py`
- `src/mini_agent/interfaces/__init__.py`
- `src/mini_agent/application/session_service.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `src/mini_agent/application/session_remote_service.py`
- `src/mini_agent/tui/gateway_client.py`
- `src/apps/agent_studio_gateway/main.py`
- `src/mini_agent/commands/catalog.json`
- `src/mini_agent/tui/app.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P23_AGENT_CORE_TASK_PLAN.md`

### Task Breakdown

1. Add one explicit gateway/application request for derived child-session creation.
2. Reuse the existing runtime `create_derived_session(...)` path instead of adding a second fork implementation.
3. Wire `/fork` and `/task new` into the TUI command dispatcher and command catalog.
4. Reuse the existing remote chat path for the child session's optional first task.
5. Add focused regressions for explicit derived-session API use and TUI command behavior.

### Acceptance

- explicit operator task forking creates a real child session with lineage
- the forked child is immediately inspectable/resumable as a normal session
- `/fork <prompt>` and `/task new <prompt>` both land on the same runtime-derived session path
- no fake local-only child-task subsystem is introduced

## Latest Sync: 2026-04-13 Delegation-Derived Session Lineage

## Current Execution Slice: P23.28 Delegation-Derived Session Lineage (2026-04-13)

### Why This Slice Is Next

- runtime lineage now exists for imported and restored sessions
- but explicit `/delegate` execution still did not create a real child session
- that meant one of the most natural lineage-producing behaviors in the product still collapsed back into:
  - one parent reply string
  - with no durable child task session
- the next honest move was therefore to make delegation produce a real derived session

### Scope

- add one runtime/application path for creating derived sessions from a parent session
- make `/delegate` run inside a derived child session instead of an untracked ephemeral worker
- preserve child lineage, transcript, activity, and inherited runtime configuration
- include child-session identifiers in delegation results/events

### Out Of Scope

- no new task-fork CLI/TUI command yet
- no lineage browsing UI yet
- no multi-level delegation UX redesign yet

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/application/session_service.py`
- `src/mini_agent/application/gateway_route_execution_handler.py`
- `src/mini_agent/agent_core/delegation.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P23_AGENT_CORE_TASK_PLAN.md`

### Execution Steps

1. Add a runtime/application derived-session creation path that inherits parent runtime configuration.
2. Rewire `/delegate` to execute in a derived child session.
3. Keep fallback-to-parent behavior, but leave the failed child session as an inspectable task record.
4. Expose `child_session_id` in delegation payloads for future UI/CLI use.
5. Re-run delegation-focused and broader runtime/session verification bundles.

### Acceptance Criteria

- `/delegate` creates a real child session
- child sessions carry lineage to the parent session
- child sessions keep their own transcript/activity history
- fallback still works without losing the failed child task record
- broader runtime/session verification remains green

### Status

- completed

## Latest Sync: 2026-04-13 Session Lineage Runtime Integration

## Current Execution Slice: P23.27 Session Lineage Runtime Integration (2026-04-13)

### Why This Slice Is Next

- the agent-core session package already had `SessionLineageStore`
- but it was completely disconnected from the real runtime path
- that meant the codebase had the beginnings of lineage support without any runtime truth using it
- this was the right next strengthening slice because it improves:
  - snapshot import/export semantics
  - persisted restore correctness
  - future session derivation features such as delegation, compression, and task forks

### Scope

- add runtime-private lineage state to managed sessions
- connect lineage into:
  - new session creation
  - runtime snapshot import/export
  - persistence metadata save/load
  - persisted session restore
- reuse the existing `SessionLineageStore` instead of inventing a second lineage tracker

### Out Of Scope

- no TUI/CLI/WebUI rendering yet
- no public DTO expansion for lineage browsing
- no new session forking UX yet

### Files In Scope

- `src/mini_agent/agent_core/session/lineage.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/runtime/session_creation_handler.py`
- `src/mini_agent/runtime/session_hydration_builder.py`
- `src/mini_agent/runtime/session_persistence_record_builder.py`
- `src/mini_agent/runtime/session_read_model_builder.py`
- `src/mini_agent/runtime/session_registry_handler.py`
- `src/mini_agent/runtime/session_snapshot.py`
- `src/mini_agent/runtime/session_snapshot_handler.py`
- `tests/test_agent_core_session.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `docs/P23_AGENT_CORE_TASK_PLAN.md`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add runtime-private lineage state plus store registration/removal hooks.
2. Persist lineage through record save/load and runtime snapshot import/export.
3. Rehydrate lineage on persisted restore and imported sessions.
4. Add focused regressions for child import and restart restore semantics.
5. Re-run focused plus broader runtime/session/TUI verification bundles.

### Acceptance Criteria

- managed sessions keep stable lineage metadata internally
- exported/imported runtime snapshots preserve lineage
- persisted restores rehydrate lineage instead of dropping it
- the existing `SessionLineageStore` becomes part of runtime truth
- focused and broad verification stay green

### Status

- completed

## Latest Sync: 2026-04-13 Agent Kernel Bootstrap Diagnostics

## Current Execution Slice: P23.26 Agent Kernel Bootstrap Diagnostics (2026-04-13)

### Why This Slice Is Next

- after the runtime-boundary cleanup, the next high-value agent-core gap was bootstrap observability
- the unified kernel already built:
  - route
  - runtime policy
  - tools
  - skills
  - MCP
  - turn-context providers
- but runtime surfaces still had no single kernel-level self-description
- one practical problem also remained:
  - skills/MCP bootstrap failures were often tolerated silently
  - which meant the agent could still run, but operators had no consistent way to understand what failed during startup

### Scope

- add one unified `kernel_diagnostics` payload on built agents
- surface route/policy/tool/skill/MCP/turn-context bootstrap state there
- keep skills/MCP bootstrap non-fatal, but record failure diagnostics instead of silently losing observability

### Out Of Scope

- no TUI/CLI rendering changes yet
- no runtime/session persistence changes
- no bootstrap behavior redesign beyond diagnostics capture

### Files In Scope

- `src/mini_agent/runtime/tooling.py`
- `src/mini_agent/agent_core/kernel.py`
- `tests/test_agent_core_kernel.py`
- `docs/P23_AGENT_CORE_TASK_PLAN.md`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Extend runtime tool bootstrap helpers to return structured diagnostics alongside tools and skill runtime.
2. Build one kernel-level diagnostics payload covering route, runtime policy, tools, skills, MCP, and turn-context providers.
3. Attach that payload to built agents as `agent.kernel_diagnostics`.
4. Add focused regressions for diagnostics presence and non-fatal skills/MCP bootstrap failures.
5. Re-run agent-core focused and broader runtime/CLI/TUI/gateway bundles.

### Acceptance Criteria

- built agents expose a unified `kernel_diagnostics` payload
- skills/MCP bootstrap failures remain non-fatal but become observable
- focused and broader regression bundles remain green

### Status

- completed

## Latest Sync: 2026-04-13 Managed Session Require-Helper Cleanup

## Current Execution Slice: P30.7ai Managed Session Require-Helper Cleanup (2026-04-13)

### Why This Slice Is Next

- after the runtime-boundary audit, the remaining medium-sized operator facade methods were judged structurally acceptable
- they were not hiding business logic
- but they still repeated one small boundary pattern many times:
  - load or restore a managed session under `_store_lock`
  - raise `404` when no live or persisted session exists
- this was a worthwhile small cleanup because it improves consistency without pushing the architecture further than needed

### Scope

- add one private `_require_managed_session_unlocked(...)` helper in the runtime manager
- reuse it across the repeated restore-or-404 facade entrypoints
- keep cancel/approval and delete semantics untouched

### Out Of Scope

- no new handler extraction
- no operator-surface redesign
- no semantic changes to persisted/live session handling

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add `_require_managed_session_unlocked(...)` on top of the existing `_load_managed_session_unlocked(...)`.
2. Replace repeated load+404 blocks in the identical facade paths.
3. Re-run broad runtime/session/TUI bundle and readiness walkthrough.

### Acceptance Criteria

- repeated restore-or-404 boilerplate is centralized
- behavior remains unchanged across session/operator entrypoints
- broad verification remains green

### Status

- completed

## Latest Sync: 2026-04-13 Runtime Manager Composition Root Cleanup

## Current Execution Slice: P30.7ah Runtime Manager Composition Root Cleanup (2026-04-13)

### Why This Slice Is Next

- after snapshot-import cleanup, the biggest remaining runtime-manager hotspot was no longer a business flow
- it was the composition root itself:
  - `__init__`
  - one long block wiring persistence, diagnostics, hydration, read-side services, runtime mutation services, and boundary handlers
- the issue here was not missing extraction
- it was readability and dependency-order clarity
- so the right move was:
  - keep the same collaborators
  - keep the same ownership
  - but split the wiring into a few internal initialization stages

### Scope

- reorganize `MainAgentRuntimeManager.__init__` into a small set of private initialization methods
- preserve dependency order and behavior
- avoid introducing a new external composition abstraction

### Out Of Scope

- no behavior changes
- no new handler layer
- no contract changes for callers

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Collapse `__init__` into a minimal composition entrypoint.
2. Split the wiring into internal stages:
   - runtime core
   - runtime support services
   - session model services
   - session runtime services
   - session boundary services
3. Re-run static checks, broad runtime/session/TUI bundle, and readiness walkthrough.

### Acceptance Criteria

- `__init__` becomes a small readable composition entrypoint
- dependency order remains valid
- broad verification remains green

### Status

- completed

## Latest Sync: 2026-04-13 Snapshot Import Command Surface Cleanup

## Current Execution Slice: P30.7ag Snapshot Import Command Surface Cleanup (2026-04-13)

### Why This Slice Is Next

- after the transcript/turn-recording cleanup, `import_session_snapshot(...)` still stood out in the runtime manager
- the remaining thickness was no longer orchestration logic
- it was mostly:
  - a very large parameter surface
  - plus manager-local construction of `RuntimeSessionSnapshotImportCommand(...)`
- the registry/snapshot layer already speaks in terms of the import command object
- so the honest next move was to let the runtime-manager boundary speak that same language too

### Scope

- change `MainAgentRuntimeManager.import_session_snapshot(...)` to accept a `RuntimeSessionSnapshotImportCommand`
- update direct test/script callers to construct that command explicitly
- keep snapshot import behavior unchanged

### Out Of Scope

- no snapshot schema changes
- no new handler abstraction
- no import/export behavior redesign

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `scripts/shared_session_gateway_walkthrough.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Collapse the runtime-manager snapshot-import boundary onto `RuntimeSessionSnapshotImportCommand`.
2. Update helper/test/script call sites to construct the command object directly.
3. Re-run focused import/export regressions plus the broader runtime/session/TUI bundle and walkthrough.

### Acceptance Criteria

- runtime manager no longer exposes a large kwargs-style snapshot-import signature
- test/script callers compile against the command-object contract
- snapshot import/export/recovery behavior remains green in focused and broad verification

### Status

- completed

## Latest Sync: 2026-04-13 Turn Recording Surface Consolidation

## Current Execution Slice: P30.7af Turn Recording Surface Consolidation (2026-04-13)

### Why This Slice Is Next

- after the registry/operator/cancel-approval cuts, the remaining session transcript surface in the runtime manager was mostly thin already
- one notable orchestration fragment still lived inline:
  - `record_turn(...)`
- the manager was still assembling a two-message transcript write itself even though the real mutation owner was already:
  - `RuntimeSessionTurnScopeHandler`
- this made the transcript surface a good low-risk follow-up:
  - it reduces one more piece of manager-local mutation sequencing
  - without inventing another abstraction or changing the public runtime surface

### Scope

- extend `RuntimeSessionTurnScopeHandler` with a first-class `record_turn(...)` helper
- rewire runtime-manager transcript wrappers into thinner facade-style delegation
- add focused regression coverage for direct `record_turn(...)` persistence

### Out Of Scope

- no transcript schema changes
- no session-service API redesign
- no new recording-specific handler

### Files In Scope

- `src/mini_agent/runtime/session_turn_scope_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add `record_turn(...)` onto the existing turn-scope handler beside `record_message(...)`.
2. Rewire runtime-manager transcript wrappers to delegate directly and remove leftover inline response variables.
3. Add a focused direct-runtime regression for `record_turn(...)`.
4. Re-run focused transcript/session/TUI regression bundles.

### Acceptance Criteria

- runtime manager no longer assembles the user+assistant transcript pair inline for `record_turn(...)`
- transcript persistence behavior stays stable for direct runtime calls
- focused runtime/session/TUI regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Cancel / Approval Operator-Surface Follow-Up

## Current Execution Slice: P30.7ae Cancel / Approval Operator-Surface Follow-Up (2026-04-13)

### Why This Slice Is Next

- after the session-operator extraction, two obvious operator-facing branches still lived inline in the runtime manager:
  - `cancel_session_turn(...)`
  - `resolve_pending_approval(...)`
- both were already using the extracted interrupt domain handler
- what remained inline was mostly:
  - active-vs-persisted existence handling
  - transcript recording
  - approval waiter finalization ordering

### Scope

- extend the session-operator handler to own cancel/approval orchestration too
- keep manager-side `_store_lock` ownership
- preserve existing transcript ordering and approval-finalization behavior

### Out Of Scope

- no redesign of interrupt domain rules
- no change to approval transport contracts
- no session-persistence changes

### Files In Scope

- `src/mini_agent/runtime/session_operator_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Extend the operator handler with cancel/approval orchestration methods.
2. Rewire runtime manager cancel/approval entrypoints into thin lock+lookup+delegate shells.
3. Re-run focused cancel/approval regressions plus broad runtime/gateway/TUI bundles.

### Acceptance Criteria

- runtime manager no longer owns the full orchestration body for cancel/approval session commands
- transcript ordering and approval waiter finalization remain stable
- shared-session walkthrough and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Session Operator Handler Extraction

## Current Execution Slice: P30.7ad Session Operator Handler Extraction (2026-04-13)

### Why This Slice Is Next

- after session-registry orchestration moved out, the next remaining runtime-manager hot spot was the operator-command surface
- the manager still owned bulky orchestration for:
  - `control_session_context(...)`
  - `update_session_context_policy(...)`
  - `manage_session_memory(...)`
  - `manage_session_skills(...)`
  - `update_session_model_selection(...)`
  - `update_session_runtime_policy(...)`
- those methods were mostly composing already-extracted business handlers rather than owning new business logic

### Scope

- add one operator-command handler in the runtime layer
- move command-surface orchestration and transport-response shaping into it
- keep the existing lower-level handlers as the business owners

### Out Of Scope

- no command behavior redesign
- no API contract changes
- no session-truth migration

### Files In Scope

- `src/mini_agent/runtime/session_operator_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a runtime operator handler that composes the existing control/context/memory/skill/model/policy handlers.
2. Move command orchestration and response shaping into that handler.
3. Rewire runtime manager command entrypoints to thin delegation shells.
4. Preserve existing operator-visible semantics and monkeypatch seams during extraction.
5. Re-run focused and broad shared-session/gateway/TUI bundles.

### Acceptance Criteria

- runtime manager no longer owns the full orchestration body for the main session operator commands
- command behavior and response payloads stay stable
- MCP cleanup monkeypatchability and command metadata semantics stay preserved
- broad regression bundles and walkthroughs stay green

### Status

- completed

## Latest Sync: 2026-04-13 Session Registry Handler Extraction

## Current Execution Slice: P30.7ac Session Registry Handler Extraction (2026-04-13)

### Why This Slice Is Next

- after the direct-wiring cleanup, the next obvious runtime-manager thickness was no longer forwarding glue
- it was registry orchestration:
  - `get_or_create_session(...)`
  - `create_session(...)`
  - `import_session_snapshot(...)`
  - plus the adjacent read/export shells that all operate on the same session registry truth
- these paths were cohesive enough to move together because they all coordinate:
  - active session map
  - persisted records
  - lifecycle refresh
  - restore/hydrate entry
  - catalog-backed read surfaces

### Scope

- add one registry-focused runtime handler
- move session acquire/create/import/export/list/detail/recent orchestration into that handler
- keep `MainAgentRuntimeManager` as the store-lock owner and outer facade only

### Out Of Scope

- no command-surface behavior changes
- no persistence schema changes
- no new session truth model

### Files In Scope

- `src/mini_agent/runtime/session_registry_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a registry handler that composes the existing access/creation/snapshot/catalog handlers.
2. Move session acquire/create/import/export/list/detail/recent orchestration into it.
3. Rewire runtime manager to delegate those flows while keeping `_store_lock` at the manager boundary.
4. Re-run focused and broad shared-session/gateway/TUI regression bundles.

### Acceptance Criteria

- runtime manager no longer owns the full orchestration body for get/create/import/export/list/detail/recent session registry operations
- session registry behavior still reuses the existing lower-level handlers instead of rebuilding parallel logic
- shared-session walkthrough and broad runtime/gateway bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Runtime Manager Direct-Wiring Cleanup

## Current Execution Slice: P30.7ab Runtime Manager Direct-Wiring Cleanup (2026-04-13)

### Why This Slice Is Next

- after the handler/builder extraction wave, `MainAgentRuntimeManager` still kept a noticeable amount of leftover forwarding code
- these helpers no longer owned business logic:
  - diagnostics calls were forwarded back into `RuntimeSessionDiagnosticsService`
  - read-model calls were forwarded back into `RuntimeSessionReadModelBuilder`
  - runtime-memory helpers were forwarded back into `RuntimeTaskMemoryBackendAdapter`
- keeping those forwarding layers around was making the runtime boundary look thinner than it really was without actually reducing coupling

### Scope

- rewire runtime-manager dependencies directly to the already extracted services/builders/handlers
- preserve capture/restore persistence semantics by routing agent-runtime rebuilds through `RuntimeSessionTurnScopeHandler`
- delete manager-local forwarding helpers that are no longer needed

### Out Of Scope

- no new handler abstraction
- no command-surface behavior changes
- no persistence schema changes

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Reorder runtime-manager wiring so extracted collaborators can reference each other directly.
2. Replace pure forwarding callbacks with direct service/builder methods where signatures allow it.
3. Keep lambda adapters only where keyword-only callback signatures still need shaping.
4. Delete the now-dead manager helper layer.
5. Re-run focused and broad runtime/gateway/TUI regression bundles.

### Acceptance Criteria

- runtime manager no longer keeps pure forwarding helpers for read models, diagnostics, or runtime-memory backend access
- extracted collaborators are wired together directly from `__init__`
- prepared-context capture/restore still persists through the existing turn-scope seam
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 TUI Gateway Client Payload Shaping Consolidation

## Current Execution Slice: P30.7aa TUI Gateway Client Payload Shaping Consolidation (2026-04-13)

### Why This Slice Is Next

- after reusing `SessionSurfaceBinding` across session-facing services, one more duplication cluster of the same family still remained in the TUI client
- `TuiGatewayClient` was repeatedly rebuilding:
  - session interaction context payloads
  - create-session payloads
  - chat request/query payloads
- unlike the earlier service-layer slice, this should be solved locally inside the client to avoid cross-layer coupling

### Scope

- add lightweight local payload helpers inside `TuiGatewayClient`
- reuse them across repeated session-context/create/chat payload shapes
- add focused client payload tests

### Out Of Scope

- no gateway API changes
- no TUI behavior redesign
- no reuse of application-layer binding types inside the TUI layer

### Files In Scope

- `src/mini_agent/tui/gateway_client.py`
- `tests/test_tui_gateway_client.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a local TUI gateway session-binding helper.
2. Reuse it across repeated session-context payloads.
3. Reuse shared payload helpers for create-session and chat flows.
4. Re-run focused and broad TUI/gateway regression bundles.

### Acceptance Criteria

- repeated session-context payload normalization no longer lives inline in each client method
- async/sync create-session paths share one payload helper
- `run_chat(...)` and `stream_chat_events(...)` share one chat payload helper
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Session Surface Binding Reuse Across Services

## Current Execution Slice: P30.7z Session Surface Binding Reuse Across Services (2026-04-13)

### Why This Slice Is Next

- after unifying chat-entry request adaptation, there was still one smaller duplication cluster in session-facing services
- both `SessionApplicationService` and `RemoteSessionService` were manually unpacking the same interaction-context fields:
  - `surface`
  - `channel_type`
  - `conversation_id`
  - `sender_id`
- the existing `SessionSurfaceBinding` was already present, so the next good move was to promote that existing type rather than invent another abstraction

### Scope

- extend `SessionSurfaceBinding` with shared adapter helpers
- reuse it across:
  - `SessionApplicationService`
  - `RemoteSessionService`
- add one focused regression check for the binding contract

### Out Of Scope

- no new runtime-manager behavior
- no gateway-client API redesign
- no attempt to abstract operation-specific business fields

### Files In Scope

- `src/mini_agent/application/session_service.py`
- `src/mini_agent/application/session_remote_service.py`
- `tests/test_session_service.py`
- `tests/test_session_remote_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Promote `SessionSurfaceBinding` into a reusable adapter with request/value constructors.
2. Reuse it across session-service runtime-manager forwarding.
3. Reuse it across remote-service gateway-client forwarding.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- session-facing services no longer manually rebuild the same interaction-context kwargs repeatedly
- create-session async/sync remote payloads share one normalization helper
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Interaction Request Adapter Extraction + Channel Smoke Repair

## Current Execution Slice: P30.7y Interaction Request Adapter Extraction + Channel Smoke Repair (2026-04-13)

### Why This Slice Is Next

- after thinning the gateway use case, the remaining application-layer duplication was no longer a large orchestration cluster
- instead, two entrances were still hand-building similar internal chat requests:
  - gateway chat entrypoints
  - channel-ingress forwarding
- in parallel, the repo smoke layer exposed stale assumptions around prebuilt Node artifacts for the WeChat channel

### Scope

- add one shared application-layer request adapter for normalized interaction binding and chat-request construction
- rewire gateway and channel-ingress to use that seam
- run real-use smoke flows and repair any repo-level smoke blockers uncovered there

### Out Of Scope

- no new route/delegation semantics
- no session-service redesign
- no remote-channel feature expansion

### Files In Scope

- `src/mini_agent/application/interaction_request_adapter.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `src/mini_agent/application/channel_ingress_use_cases.py`
- `tests/test_interaction_request_adapter.py`
- `scripts/qq_wechat_smoke.py`
- `src/channels/types/package.json`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a shared interaction request adapter.
2. Move gateway and channel-ingress request construction onto that seam.
3. Run gateway/channel walkthroughs and API integration smoke.
4. Repair any repo-level smoke blockers exposed by `qq_wechat_smoke.py`.

### Acceptance Criteria

- gateway and channel-ingress no longer hand-build duplicated interaction request shapes
- focused adapter regression coverage exists
- gateway/channel walkthroughs stay green
- `scripts/qq_wechat_smoke.py` passes on the current repo state

### Status

- completed

## Latest Sync: 2026-04-13 Gateway Route Execution Handler Extraction

## Current Execution Slice: P30.7x Gateway Route Execution Handler Extraction (2026-04-13)

### Why This Slice Is Next

- after extracting chat-flow orchestration and main-route execution hooks, `MainAgentGatewayUseCases` still owned the routed execution shell:
  - parse `/delegate`
  - resolve message route
  - track routing diagnostics
  - execute delegation and fallback
- that kept route/delegation behavior mixed into the top-level gateway use case instead of giving it one application seam

### Scope

- extract a dedicated gateway route-execution handler for:
  - delegation-command parsing
  - route resolution and diagnostics bookkeeping
  - delegation execution
  - delegation failure fallback to the main agent
  - delegation payload / supplemental event shaping
- rewire `MainAgentGatewayUseCases` to delegate route execution and routing diagnostics to that handler

### Out Of Scope

- no chat-flow behavior redesign
- no session-service API redesign
- no change to delegation-manager semantics

### Files In Scope

- `src/mini_agent/application/gateway_route_execution_handler.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `tests/test_session_service.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated gateway route-execution handler.
2. Move route parsing, route bookkeeping, and delegation fallback into that handler.
3. Rewire `MainAgentGatewayUseCases` to use the new seam for diagnostics and routed execution.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- `MainAgentGatewayUseCases` no longer owns route/delegation execution internals
- routing diagnostics still report the same counters
- delegation success/failure/fallback behavior remains unchanged
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Gateway Agent Execution Handler Extraction

## Current Execution Slice: P30.7w Gateway Agent Execution Handler Extraction (2026-04-13)

### Why This Slice Is Next

- after chat-flow extraction, `MainAgentGatewayUseCases` still carried the low-level execution cluster for the main route:
  - `_run_agent_once(...)`
  - approval hook construction
  - activity hook construction
  - tool activity preview / output formatting helpers
- that kept agent-execution details mixed into the route coordinator instead of giving them a dedicated application seam

### Scope

- extract a dedicated gateway agent-execution handler for:
  - one-shot main-route agent execution
  - runtime approval hook injection/restoration
  - runtime activity hook construction
  - tool-call preview and output formatting helpers
- rewire `MainAgentGatewayUseCases` to call that handler for main-route and delegation-fallback execution

### Out Of Scope

- no route-table behavior changes
- no delegation-manager behavior changes
- no session turn lifecycle redesign

### Files In Scope

- `src/mini_agent/application/gateway_agent_execution_handler.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `tests/test_session_service.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated gateway agent-execution handler.
2. Move single-turn execution + approval/activity hooks into that handler.
3. Rewire main-route and delegation-fallback execution to use the new seam.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- `MainAgentGatewayUseCases` no longer owns approval/activity hook construction inline
- main-route execution behavior remains unchanged
- delegation fallback still uses the same main-agent execution semantics
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Gateway Chat Flow Handler Extraction

## Current Execution Slice: P30.7v Gateway Chat Flow Handler Extraction (2026-04-13)

### Why This Slice Is Next

- after turn-scope extraction, the next duplicated orchestration cluster lived in `MainAgentGatewayUseCases`:
  - `run_chat(...)`
  - `stream_chat_events(...)`
- both paths still repeated the same high-level flow:
  - validate / prepare turn
  - execute routed chat work
  - capture prepared context when the main route handled the turn
  - clear recovery when needed
  - record assistant reply
  - shape final response / SSE tail

### Scope

- extract a dedicated gateway chat-flow handler for:
  - dry-run response / stream handling
  - turn preparation with bootstrap error shaping
  - non-streaming chat orchestration
  - streaming chat orchestration with heartbeat / delta / done framing
- keep route resolution, approval/activity hooks, and delegation execution in `MainAgentGatewayUseCases` for this slice

### Out Of Scope

- no routing logic redesign
- no approval/activity hook redesign
- no delegation behavior changes

### Files In Scope

- `src/mini_agent/application/gateway_chat_flow_handler.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `tests/test_session_service.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated gateway chat-flow handler.
2. Move shared `run_chat` / `stream_chat_events` orchestration into that handler.
3. Rewire `MainAgentGatewayUseCases` to provide only the routed execution callback.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- `run_chat(...)` no longer owns the full turn/response orchestration inline
- `stream_chat_events(...)` no longer owns the duplicated prepare/heartbeat/finalize shell inline
- route/delegation/approval behavior remains unchanged
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Turn Scope Orchestration Extraction

## Current Execution Slice: P30.7u Turn Scope Orchestration Extraction (2026-04-13)

### Why This Slice Is Next

- after the command-shell follow-up, the next remaining orchestration-heavy cluster was the managed chat-turn scope itself
- `ManagedSessionTurn.__aenter__ / __aexit__` still directly orchestrated:
  - surface binding
  - pending model application
  - pending skill reload application
  - recovery-context lookup
  - running-state transitions
  - user-message recording
  - exit-time cleanup
- that made turn-scope lifecycle another cross-layer implementation detail instead of a dedicated runtime seam

### Scope

- extract a dedicated runtime turn-scope handler
- move enter/exit turn orchestration and turn-scope helper mutations behind that seam
- rewire `ManagedSessionTurn` and manager helper wrappers to use the new runtime turn-scope boundary

### Out Of Scope

- no gateway transport changes
- no chat routing/delegation redesign
- no approval semantics changes

### Files In Scope

- `src/mini_agent/runtime/session_turn_scope_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/application/session_service.py`
- `tests/test_session_service.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated runtime turn-scope handler.
2. Move enter/exit turn orchestration and turn-scoped mutation helpers behind that handler.
3. Rewire `ManagedSessionTurn` plus the manager helper wrappers to use the shared runtime turn-scope seam.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- managed turn enter/exit orchestration no longer lives inline in `ManagedSessionTurn`
- manager helper methods for turn-scope state delegate to the extracted runtime seam
- chat/recovery/activity/approval flows remain green

### Status

- completed

## Latest Sync: 2026-04-13 Skill + Model Command Shell Follow-Up

## Current Execution Slice: P30.7t Skill + Model Command Shell Follow-Up (2026-04-13)

### Why This Slice Is Next

- after the initial command coordinator extraction, two manager methods still had uneven command-shell treatment:
  - `manage_session_skills(...)` only used the coordinator for transcript recording after the success path
  - `update_session_model_selection(...)` still owned a fully inline lock/mutate/persist block
- that left command-entry orchestration only partially unified

### Scope

- finish moving the skill success mutation path onto the shared command shell
- move model selection onto the same locked command-execution seam
- allow the command coordinator to support result-dependent touch/persist behavior so queued vs applied flows can stay unchanged

### Out Of Scope

- no transcript behavior changes for model selection
- no model-selection semantics redesign
- no skill reload queue redesign

### Files In Scope

- `src/mini_agent/runtime/session_command_coordinator.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Extend the command coordinator to support result-dependent touch/persist decisions.
2. Rewire skill mutation success flow to use the shared coordinator instead of manual lock/record code.
3. Rewire model selection to the same shared coordinator while preserving queued/applied behavior.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- skill mutation success no longer manually records/persists inside the manager
- model selection no longer owns a bespoke lock/mutate/persist block
- queued/applied model semantics remain unchanged
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-12 Session Command Coordinator Extraction

## Current Execution Slice: P30.7s Session Command Coordinator Extraction (2026-04-12)

### Why This Slice Is Next

- after the earlier handler extractions, `MainAgentRuntimeManager` still repeated the same command-entry orchestration pattern in several places:
  - load session
  - acquire session runtime lock
  - execute command mutation
  - append command transcript
  - touch and persist
- that duplication kept the manager thicker than necessary even after the business logic had already moved into dedicated handlers

### Scope

- add one shared command coordinator for the command-entry shell
- centralize:
  - locked execution of session command mutations
  - command transcript append wiring
  - touch/persist sequencing after command execution
- rewire command-oriented manager entrypoints to use that seam where it fits cleanly

### Out Of Scope

- no transport/API contract changes
- no new compatibility wrappers
- no redesign of skill queueing or model selection semantics in this slice

### Files In Scope

- `src/mini_agent/runtime/session_command_coordinator.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `tests/test_session_service.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated runtime session command coordinator.
2. Rewire command-oriented manager methods to use the shared locked-execution and transcript flow.
3. Finish the remaining runtime-policy command path so it no longer keeps command mutation logic under `_store_lock`.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- manager no longer repeats the same lock/transcript/persist shell across the extracted command handlers
- `update_session_runtime_policy(...)` follows the same command orchestration seam as the other extracted command flows
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-12 Session Agent-Runtime Handler Extraction

## Current Execution Slice: P30.7r Session Agent-Runtime Handler Extraction (2026-04-12)

### Why This Slice Is Next

- after session catalog extraction, the next manager-owned cluster was agent runtime rebuild / reconfiguration orchestration
- `MainAgentRuntimeManager` still directly owned:
  - agent rebuild for selected model identity
  - runtime policy reconfiguration against the live agent
  - pending model-selection application
  - pending skill-reload application
  - workspace skill-reload queue marking
- that meant the manager was still mixing orchestration with agent-host mutation logic

### Scope

- extract agent runtime rebuild / reconfiguration into a dedicated handler
- centralize:
  - desired/effective runtime policy inspection
  - live-agent runtime policy reconfigure
  - rebuild with selected identity
  - pending model-selection application
  - pending skill-reload application
  - workspace skill-reload queue mutation
- keep `MainAgentRuntimeManager` responsible only for:
  - lock boundaries
  - transcript/persistence orchestration
  - higher-level response shaping

### Out Of Scope

- no model-selection plan redesign
- no skill-command routing redesign
- no transport/API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_agent_runtime_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated agent-runtime handler.
2. Move rebuild/policy/pending-apply/workspace-reload logic behind that seam.
3. Rewire manager and dependent runtime handlers to use the new seam.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- manager no longer contains inline rebuild / runtime reconfigure helper cluster
- runtime-policy, model-selection, and pending skill-reload behavior stay unchanged
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-12 Session Catalog Handler Extraction

## Current Execution Slice: P30.7q Session Catalog Handler Extraction (2026-04-12)

### Why This Slice Is Next

- after session live-state extraction, the next manager-owned cluster was session catalog / metadata routing
- `MainAgentRuntimeManager` still directly owned:
  - latest workspace active-session lookup
  - latest workspace persisted-record lookup
  - human-readable title allocation
  - list/detail/recent-message read routing
  - session summary dedupe rules
  - rename/share metadata mutations
- that kept the manager responsible for both orchestration and session directory/catalog semantics

### Scope

- extract session catalog / metadata handling into a dedicated handler
- centralize:
  - latest active/persisted workspace lookup
  - title allocation for new/restored sessions
  - list/detail/message read routing
  - remote-channel summary dedupe
  - rename/share metadata mutation rules
- keep `MainAgentRuntimeManager` responsible only for:
  - lock boundaries
  - invoking the catalog handler
  - persistence and registry updates

### Out Of Scope

- no session restore redesign
- no live-state mutation redesign
- no transport/API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_catalog_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated session catalog handler.
2. Move title allocation, latest-workspace lookup, list/detail/message read routing, dedupe, and rename/share behind that seam.
3. Rewire access/creation/read/mutation entrypoints to use the handler.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- manager no longer contains inline session catalog helper cluster
- title-hint, dedupe, list/detail/message, and rename/share behavior stay unchanged
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-12 Session Live-State Handler Extraction

## Current Execution Slice: P30.7p Session Live-State Handler Extraction (2026-04-12)

### Why This Slice Is Next

- after session creation was extracted, the next manager-heavy cluster was live session state mutation
- `MainAgentRuntimeManager` still directly owned a large set of closely related write-path logic:
  - surface binding
  - turn start / finish markers
  - transcript append
  - activity aggregation
  - pending approval tracking
  - recovery-context clearing/building
  - runtime reset state clearing
- that left the manager still acting like both:
  - orchestration coordinator
  - and low-level live session state machine

### Scope

- extract live session state mutation into a dedicated handler
- centralize:
  - surface/channel binding semantics
  - transcript append helpers
  - turn lifecycle flags
  - activity transcript aggregation
  - pending approval normalization/storage cleanup
  - recovery context mutation
  - runtime reset state cleanup
- keep `MainAgentRuntimeManager` responsible only for:
  - lock / orchestration boundaries
  - invoking the live-state handler
  - persistence

### Out Of Scope

- no read-model redesign
- no snapshot/restore redesign
- no transport/API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_live_state_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated handler for live session state / transcript mutations.
2. Move surface, turn, message, activity, approval, recovery, and reset state mutation behind that seam.
3. Rewire manager entrypoints and injected runtime dependencies to use the extracted handler.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- manager no longer contains the inline live session mutation helper cluster
- transcript/surface/pending-approval semantics stay unchanged
- recovery and reset flows stay green across restart scenarios
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-12 Session Creation Handler Extraction

## Current Execution Slice: P30.7o Session Creation Handler Extraction (2026-04-12)

### Why This Slice Is Next

- after session-access extraction, the next obvious duplication left in `MainAgentRuntimeManager` was brand-new session construction
- both:
  - `get_or_create_session(...)` create-new branch
  - `create_session(...)`
  were still rebuilding the same runtime session shape inline:
  - build a fresh agent
  - bootstrap lifecycle state
  - assemble `MainAgentSessionState`
  - derive knowledge-base / sandbox / selected-model projection fields
  - register and persist
- that duplication kept session creation as another manager-owned implementation detail instead of a reusable runtime seam

### Scope

- extract brand-new session creation into a dedicated handler
- centralize:
  - title normalization/allocation
  - surface/channel normalization
  - fresh agent bootstrap
  - lifecycle bootstrap
  - initial projection assembly
  - selected-model projection seeding
- keep `MainAgentRuntimeManager` responsible only for:
  - outer policy/capacity gatekeeping
  - invoking the creation handler
  - session registry insertion
  - persistence

### Out Of Scope

- no restore/import hydration redesign
- no session-access policy redesign
- no transport/API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_creation_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated creation handler for brand-new runtime sessions.
2. Move shared title/surface/channel normalization and state assembly behind that handler.
3. Rewire `get_or_create_session(...)` and `create_session(...)` to use the same creation seam.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- manager no longer contains duplicated inline new-session construction
- `create_session(...)` and `get_or_create_session(...)` share one creation path
- title-hint, surface, shared-session, and persisted-restart behavior stay unchanged
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7n Session Model Selection Handler Extraction (2026-04-12)

### Why This Slice Is Next

- after `/memory` and `/skill` command extraction, the next obvious stateful branch still embedded in `MainAgentRuntimeManager` was model selection
- `update_session_model_selection(...)` still mixed:
  - request normalization
  - busy vs idle selection semantics
  - queued vs immediate-apply response shaping
  - pending-selection application rules
- this was the next clean step toward making the manager a pure runtime orchestrator

### Scope

- extract model-selection decision logic into a dedicated handler
- move busy/idle/queued/apply-now semantics and pending-selection eligibility behind that handler seam
- keep `MainAgentRuntimeManager` responsible only for:
  - session lookup
  - lock envelope
  - applying the chosen state mutations
  - optional agent rebuild
  - persistence
  - response wrapping
- sync the shared-session walkthrough script to the already-live grouped session state shape

### Out Of Scope

- no runtime policy / approval-mode extraction yet
- no model catalog redesign
- no transport/API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_model_selection_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `scripts/shared_session_gateway_walkthrough.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a dedicated model-selection handler with request normalization and plan generation.
2. Move busy/idle/queued/apply-now semantics and pending-apply eligibility behind that handler.
3. Rewire `MainAgentRuntimeManager` to apply the returned plan and keep only orchestration responsibilities.
4. Re-run model-related runtime/gateway/TUI bundles plus the shared-session walkthrough.

### Acceptance Criteria

- manager no longer contains the inline busy/idle model-selection branch
- pending-selection application delegates to the same extracted handler seam
- model-selection transport behavior remains unchanged across immediate and queued flows
- walkthrough and regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7m Session Skill Command Handler Extraction (2026-04-12)

### Why This Slice Is Next

- after `/memory` command extraction, the next large behavior-heavy branch still embedded in `MainAgentRuntimeManager` was `/skill`
- that branch mixed:
  - skill catalog availability handling
  - read action routing (`list` / `active` / `show` / `search`)
  - workspace policy/install mutation routing
  - reload queue metadata formatting
  - final command transcript naming
- the manager was still doing both runtime orchestration and skill command formatting work

### Scope

- extract session-skill command routing into a dedicated handler
- move read/mutation payload assembly and command metadata construction behind that handler
- keep `MainAgentRuntimeManager` responsible only for:
  - session lookup
  - busy/lock envelope
  - reload queue orchestration
  - transcript append
  - persistence
  - response wrapping
- fix the stale action whitelist so implemented `uninstall` / `rollback` paths are actually reachable

### Out Of Scope

- no `/model` command decomposition yet
- no skill runtime redesign
- no transport/API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_skill_command_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a dedicated session-skill command handler with explicit read/mutation routing.
2. Move skill catalog availability handling, result assembly, and command naming behind that handler.
3. Rewire `MainAgentRuntimeManager.manage_session_skills(...)` to keep only orchestration responsibilities.
4. Add focused regression coverage for `uninstall` / `rollback`.
5. Verify with focused and broad runtime/gateway/TUI regression bundles.

### Acceptance Criteria

- manager no longer contains the large inline `/skill` branch
- skill action validation/routing lives in a dedicated runtime module
- `uninstall` / `rollback` are accepted by the same runtime entrypoint that already advertises them
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7l Session Memory Command Handler Extraction (2026-04-12)

### Why This Slice Is Next

- after the lifecycle/policy extraction, the biggest remaining behavior-heavy branch still embedded in `MainAgentRuntimeManager` was `/memory` command handling
- that branch mixed several different responsibilities:
  - action validation and routing
  - runtime selector resolution
  - durable/runtime memory read payload assembly
  - mutation result formatting
  - while the manager also still owned lock/transcript/persist flow around it
- this was the first clean step in command-handler decomposition without changing transport behavior

### Scope

- extract session-memory command routing into a dedicated handler
- move read/mutation result assembly and selector resolution behind that handler seam
- keep `MainAgentRuntimeManager` responsible only for:
  - session lookup
  - busy/lock envelope
  - transcript append
  - persistence
  - response wrapping

### Out Of Scope

- no `/skill` command decomposition yet
- no `/model` command decomposition yet
- no memory semantics or API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_memory_command_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a dedicated session-memory command handler with explicit action groups.
2. Move `/memory` read/mutation routing and payload assembly behind that handler.
3. Rewire `MainAgentRuntimeManager.manage_session_memory(...)` to keep only orchestration responsibilities.
4. Verify with focused and broad runtime/gateway/TUI regression bundles.

### Acceptance Criteria

- manager no longer contains the large inline `/memory` command branch
- memory action validation/routing lives in a dedicated runtime module
- lock/busy/transcript/persist behavior stays unchanged
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7k Lifecycle / Policy Coordination Extraction (2026-04-12)

### Why This Slice Is Next

- after persistence internals extraction, the next broad responsibility cluster still centered in the manager was lifecycle/policy coordination:
  - main-workspace guardrails
  - single-main active-workspace admission checks
  - team saturation/workspace-conflict counters
  - session lifecycle refresh/reset counters
  - runtime diagnostics payload assembly for those counters
- this was the next major non-I/O, non-hydration concern suitable for extraction

### Scope

- extract a dedicated runtime policy/lifecycle coordinator for:
  - workspace guardrails
  - capacity guardrails
  - conflict/saturation counters
  - lifecycle refresh/reset counting
  - diagnostics payload construction
- rewire manager wrappers and entry flows to delegate to that coordinator
- keep outer behavior and transport contracts unchanged

### Out Of Scope

- no session-lifecycle model redesign
- no transport/API contract changes
- no command-handler decomposition yet

### Files In Scope

- `src/mini_agent/runtime/session_runtime_policy_coordinator.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a runtime policy/lifecycle coordinator service.
2. Move lifecycle refresh/expired-session/counter logic behind that coordinator.
3. Rewire workspace/capacity guardrail entry flows to delegate to the coordinator.
4. Verify with focused and broad regression bundles.

### Acceptance Criteria

- manager no longer owns lifecycle/counter state directly
- workspace/capacity guardrail logic delegates to a shared coordinator
- runtime diagnostics counter payload comes from the coordinator
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7j Persistence Wrapper Internals Extraction (2026-04-12)

### Why This Slice Is Next

- after the runtime-memory backend adapter cut, the next non-orchestrator responsibility still living inline was persistence-wrapper internals:
  - metadata registry read/write details
  - shared transcript file path/read/write/delete details
- `_MainAgentRuntimePersistence` was already acting as a wrapper, but it still carried the low-level JSON/file logic itself

### Scope

- extract helper modules for:
  - runtime metadata registry access
  - shared transcript file storage
- rewire `_MainAgentRuntimePersistence` to compose those helpers instead of owning the file/JSON logic inline
- keep persistence wrapper behavior unchanged

### Out Of Scope

- no `SessionPersistence` redesign
- no persistence format changes
- no application/session-service API changes

### Files In Scope

- `src/mini_agent/runtime/session_persistence_metadata_registry.py`
- `src/mini_agent/runtime/session_shared_transcript_store.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a runtime metadata registry helper.
2. Add a shared transcript store helper.
3. Rewire `_MainAgentRuntimePersistence` to compose both helpers.
4. Verify with focused and broad regression bundles.

### Acceptance Criteria

- `_MainAgentRuntimePersistence` no longer implements metadata JSON read/write inline
- `_MainAgentRuntimePersistence` no longer implements shared transcript path/read/write/delete inline
- persistence wrapper behavior remains unchanged while composition boundaries get clearer
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7i Runtime-Memory Backend Adapter Extraction (2026-04-12)

### Why This Slice Is Next

- after diagnostics extraction, the next infrastructure-heavy dependency still rooted in the manager was direct `WorkspaceMemoriaRuntime` access:
  - snapshot/export paths
  - hydration restore paths
  - reset/delete cleanup
  - `/memory` runtime-memory command flows
- this left the manager coupled to a concrete memory backend in multiple different styles

### Scope

- extract a dedicated runtime-memory backend adapter around `WorkspaceMemoriaRuntime`
- rewire:
  - hydration/read-model snapshot and restore paths
  - reset/delete cleanup paths
  - runtime-memory command operations (`show`, `shared show`, `shared clear`, runtime promotions)
- reduce manager backend access methods to delegation wrappers

### Out Of Scope

- no `WorkspaceMemoriaRuntime` redesign
- no memory semantics changes
- no application/session-service API changes

### Files In Scope

- `src/mini_agent/runtime/session_runtime_memory_backend_adapter.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a shared runtime-memory backend adapter.
2. Rewire snapshot/restore/hydrator integrations through the adapter.
3. Rewire manager runtime-memory command flows and cleanup paths through the adapter.
4. Verify with focused and broad regression bundles.

### Acceptance Criteria

- `MainAgentRuntimeManager` no longer directly instantiates `WorkspaceMemoriaRuntime`
- hydration/read-model/runtime-memory command paths share the same backend adapter seam
- manager runtime-memory backend methods become wrappers only
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7h Session Diagnostics Service Extraction (2026-04-12)

### Why This Slice Is Next

- after extracting the runtime-state hydrator, diagnostics were the next shared concern still anchored in the manager:
  - memory diagnostics were used by hydration, runtime capture flows, and read-model builders
  - sandbox diagnostics were used by hydration, persistence refresh, and read-model builders
- this made diagnostics a better candidate for extraction than another surface-specific cut

### Scope

- extract a dedicated diagnostics service for:
  - memory diagnostics from live sessions
  - memory diagnostics from persisted records
  - sandbox diagnostics from live sessions
  - sandbox diagnostics from persisted records
- rewire hydration builder, runtime-state hydrator, and read-model builder through that service
- reduce manager diagnostics methods to delegation wrappers

### Out Of Scope

- no memory system redesign
- no sandbox backend redesign
- no application/session-service API changes

### Files In Scope

- `src/mini_agent/runtime/session_diagnostics_service.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a shared session diagnostics service module.
2. Rewire hydration/read-model/runtime-state hydrator dependencies to use that service.
3. Reduce manager diagnostics methods to delegation wrappers.
4. Verify with focused and broad regression bundles.

### Acceptance Criteria

- memory/sandbox diagnostics implementations no longer live inline in `MainAgentRuntimeManager`
- hydration and read-model code depend on a shared diagnostics service instead of manager-owned implementations
- manager diagnostics methods become boundary wrappers only
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7g Session Runtime State Hydrator Extraction (2026-04-12)

### Why This Slice Is Next

- after hydration unification, the shared `_hydrate_session_unlocked(...)` path still mixed runtime-state substeps:
  - runtime task-memory restore
  - workspace-shared runtime-memory merge
  - prepared-context restore onto the live agent
  - diagnostics refresh
- those are not session assembly anymore; they are runtime-state synchronization concerns

### Scope

- extract a dedicated runtime-state hydrator for:
  - post-build runtime-memory restore
  - prepared-context restore/capture
  - diagnostics refresh
- rewire the shared hydration helper to delegate these substeps
- keep manager wrapper methods as boundary methods while moving implementation out

### Out Of Scope

- no runtime-memory storage redesign
- no `SessionPersistence` redesign
- no application/session-service API changes

### Files In Scope

- `src/mini_agent/runtime/session_runtime_state_hydrator.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a dedicated runtime-state hydrator module.
2. Move prepared-context restore/capture and diagnostics refresh behind that hydrator seam.
3. Move shared hydration post-build runtime-memory restore behind that hydrator seam.
4. Verify with focused and broad regression bundles.

### Acceptance Criteria

- `_hydrate_session_unlocked(...)` no longer directly restores runtime-memory payloads or prepared-context state
- prepared-context restore/capture implementations no longer live inline in `MainAgentRuntimeManager`
- runtime-state synchronization lives in `session_runtime_state_hydrator.py`
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7f Session Hydration Unification (2026-04-12)

### Why This Slice Is Next

- after extracting restore/load seams, the next visible duplication was hydration assembly itself:
  - `import_session_snapshot(...)` still rebuilt a session inline
  - `_restore_persisted_session_unlocked(...)` now used extracted restore payloads, but still ran a similar runtime assembly flow
- this left two near-parallel paths for:
  - build agent
  - apply runtime policy
  - restore messages/tokens
  - apply KB state
  - assemble session state
  - restore runtime memory/context

### Scope

- replace the restore-specific builder with a hydration builder that covers both:
  - persisted record restore
  - imported snapshot hydration
- extract a shared `_hydrate_session_unlocked(...)` runtime assembly flow
- route `import_session_snapshot(...)` and `_restore_persisted_session_unlocked(...)` through that shared hydration path

### Out Of Scope

- no runtime-memory persistence redesign yet
- no `SessionPersistence` redesign
- no application/session-service API changes

### Files In Scope

- `src/mini_agent/runtime/session_hydration_builder.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Replace the restore builder with a hydration builder that can normalize both record and snapshot inputs.
2. Extract a shared runtime hydration helper for agent/session assembly.
3. Rewire import and restore flows to use that shared hydration path.
4. Verify with focused and broad runtime/gateway/TUI regression bundles.

### Acceptance Criteria

- `import_session_snapshot(...)` no longer hand-assembles hydrated runtime sessions inline
- `_restore_persisted_session_unlocked(...)` and import snapshot both delegate to a shared hydration helper
- hydration-specific normalization and transcript import live in `session_hydration_builder.py`
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7e Runtime Restore/Load Boundary Extraction (2026-04-12)

### Why This Slice Is Next

- after extracting the runtime persistence save builder, the remaining mixed seam was restore/load:
  - `MainAgentRuntimeManager._restore_persisted_session_unlocked(...)` still mixed runtime orchestration with pure state reconstruction
  - `_MainAgentRuntimePersistence.load_session_record(...)` still mixed storage reads with runtime-record normalization and transcript attachment
- this kept the manager too aware of persisted-record shape and left persistence load less clean than persistence save

### Scope

- extract a dedicated runtime restore builder for:
  - transcript import from persisted records
  - persisted-record restore payload normalization
  - reconstructed session-state assembly
- extract a persistence loader for runtime-record filtering and shared-transcript attachment
- rewire read-model construction to use the extracted transcript-import seam

### Out Of Scope

- no runtime-memory restore redesign yet
- no `SessionPersistence` redesign
- no public API or transport contract changes

### Files In Scope

- `src/mini_agent/runtime/session_restore_builder.py`
- `src/mini_agent/runtime/session_persistence_loader.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Extract transcript import and persisted-record normalization into a restore builder.
2. Move reconstructed `MainAgentSessionState` assembly behind that builder seam.
3. Extract persisted-record load/list normalization into a persistence loader.
4. Verify with focused and broad runtime/gateway/TUI regression bundles.

### Acceptance Criteria

- persisted-record transcript import no longer lives inline in `MainAgentRuntimeManager`
- `_restore_persisted_session_unlocked(...)` delegates state assembly to a dedicated restore builder
- `_MainAgentRuntimePersistence.load_session_record(...)` and list filtering delegate record normalization to a dedicated loader
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7d Runtime Persistence Record Builder Extraction (2026-04-12)

### Why This Slice Is Next

- after extracting the runtime read-model builder, the next mixed runtime seam was persistence save:
  - `_MainAgentRuntimePersistence.save_session(...)` still assembled metadata records inline
  - it also refreshed sandbox diagnostics itself, which is runtime-state work rather than storage work
- this kept persistence from being a clean storage boundary

### Scope

- extract runtime persistence record/transcript serialization into a dedicated builder module
- move sandbox-diagnostics refresh back to runtime manager before persistence is called
- keep `_MainAgentRuntimePersistence` focused on file and metadata I/O

### Out Of Scope

- no persisted-record restore extractor yet
- no `SessionPersistence` redesign
- no public API changes

### Files In Scope

- `src/mini_agent/runtime/session_persistence_record_builder.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a persistence record builder for transcript-entry serialization and runtime metadata-record assembly.
2. Inject that builder into `_MainAgentRuntimePersistence`.
3. Move sandbox refresh to `_persist_session_unlocked(...)`.
4. Verify with focused runtime/gateway/session regression bundles and ruff.

### Acceptance Criteria

- `_MainAgentRuntimePersistence.save_session(...)` no longer assembles the large metadata record inline
- persistence no longer calls `collect_sandbox_diagnostics(...)` directly
- runtime manager refreshes sandbox diagnostics before delegating persistence save
- focused regression bundle stays green

### Status

- completed

## Current Execution Slice: P30.7c Runtime Session Read-Model Builder Extraction (2026-04-12)

### Why This Slice Is Next

- after the runtime session state composition cut, the next obvious mixed responsibility inside `MainAgentRuntimeManager` was read-model construction:
  - summary/detail/snapshot builders still lived inside the runtime coordinator
  - recovery/message/pending-approval projection helpers were still bundled beside execution logic
- the grouped session state made field ownership explicit, so we could now extract the builder layer without first untangling flat-field ambiguity

### Scope

- extract runtime session summary/detail/snapshot construction into a dedicated builder module
- move the related recovery/message/pending-approval read-model helpers behind that builder seam
- keep runtime manager behavior unchanged by delegating to the new builder

### Out Of Scope

- no persistence save/load extraction yet
- no application-layer lease/session interface narrowing yet
- no transport/API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_read_model_builder.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Introduce a dedicated runtime session read-model builder with injected normalization/diagnostic callbacks.
2. Move summary/detail/snapshot plus recovery/message/pending-approval read-model construction into that module.
3. Reduce runtime manager methods to delegation shells.
4. Run focused runtime/gateway/TUI/API regression bundles.

### Acceptance Criteria

- read-model construction no longer lives as large inline builder bodies inside `MainAgentRuntimeManager`
- runtime manager delegates to an extracted builder module for session summary/detail/snapshot assembly
- focused regression bundle stays green

### Status

- completed

## Current Execution Slice: P30.7b Runtime Session State Composition Cut (2026-04-12)

### Why This Slice Is Next

- after the projection-boundary cleanup, the next biggest runtime seam was still the session state object itself:
  - `MainAgentSessionState` still mixed projection/session truth, runtime host handles, and transcript state in one flat dataclass
- leaving that flat shape in place would keep:
  - `MainAgentRuntimeManager` field ownership blurry
  - `SessionService` tied to a god-object session state
  - future persistence/projection extraction harder than necessary

### Scope

- split `MainAgentSessionState` into grouped sub-state buckets:
  - `projection`
  - `runtime`
  - `transcript_state`
- migrate runtime-manager access paths onto those grouped buckets
- migrate `SessionService.ManagedSessionTurn` onto the grouped buckets
- update focused runtime/gateway tests that inspect internal session state directly

### Out Of Scope

- no persistence extractor yet
- no projection-builder extractor yet
- no public application interface narrowing yet

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/application/session_service.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `tests/test_session_service.py`
- `tests/test_p19_runtime_matrix.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Introduce grouped runtime session sub-state dataclasses.
2. Update session construction paths to populate grouped state explicitly.
3. Migrate runtime-manager and session-service field access to explicit grouped state.
4. Run focused runtime/gateway/session regression bundles.

### Acceptance Criteria

- `MainAgentSessionState` no longer stores runtime host, projection, and transcript fields flat on one object
- runtime/session-service code paths use explicit grouped state access
- focused runtime/gateway/session bundles stay green

### Status

- completed

## Current Execution Slice: P30.7a Session Projection Boundary Cleanup (2026-04-12)

### Why This Slice Is Next

- the runtime/session scan showed two adjacent boundary leaks that were cheap to fix before the bigger runtime-state split:
  - `src/mini_agent/session/projection.py` still mixed shared transport read models with terminal-only presentation state
  - both session projection code and runtime manager still widened summary -> detail payloads through `summary.__dict__`
- leaving those in place would keep the upcoming runtime decomposition tied to:
  - terminal-specific concerns in a shared session module
  - brittle dataclass-internal spreading that fights future `slots=True` tightening

### Scope

- move terminal-only `TerminalSessionProjection` out of the shared session projection module
- introduce an explicit `SessionDetailProjection.from_summary(...)` constructor
- route runtime-manager detail builders through the explicit constructor
- update TUI/tests to the new terminal projection location

### Out Of Scope

- no `MainAgentSessionState` grouped-state split yet
- no gateway/session-service API redesign yet
- no behavior changes to session semantics or TUI rendering

### Files In Scope

- `src/mini_agent/session/projection.py`
- `src/mini_agent/session/__init__.py`
- `src/mini_agent/tui/session_projection.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_session_projection.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Remove the terminal presentation model from the generic session projection module.
2. Add an explicit detail-projection constructor from summary state.
3. Update runtime/TUI callsites to use the explicit builder instead of `summary.__dict__`.
4. Verify focused session/TUI/runtime regression bundles.

### Acceptance Criteria

- `mini_agent.session.projection` only contains shared session read models, not terminal presentation DTOs
- no summary -> detail construction in the touched session/runtime paths relies on `summary.__dict__`
- TUI still renders terminal session metadata correctly through the new terminal-specific module
- focused regression bundle stays green

### Status

- completed

## Current Execution Slice: P30.2/P30.3 TUI Session State Composition Cut (2026-04-12)

### Why This Slice Is Next

- `P30.1` locked the four-entrance surface contract, but TUI still kept session projection, runtime handles, and view-only state inside one wide `TuiSession`
- that kept the same old boundary leak alive inside the developer surface:
  - remote session projection fields looked like local runtime truth
  - runtime handles were mixed with persisted UI state
  - follow-up refactors would still be operating on one ambiguous struct

### Scope

- split `TuiSession` into grouped state buckets:
  - `projection`
  - `runtime`
  - `view`
- migrate the first bounded set of callsites to the new grouped structure:
  - UI state save/load
  - remote summary/detail application
  - submission-loop attach/shutdown
  - runtime reset and chat-scroll state handling
- add focused regression coverage that locks the new grouped state contract

### Out Of Scope

- no gateway/session-service redesign in this slice
- no QQ adapter binding redesign in this slice
- no full `app.py` callsite migration in one pass

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Execution Steps

1. Introduce grouped `TuiSession` sub-state dataclasses for projection/runtime/view concerns.
2. Move the most failure-prone save/load, projection-sync, runtime-loop, and chat-view helpers onto the grouped state.
3. Add focused tests that lock alias compatibility and nested-state behavior.
4. Verify the TUI regression bundle and the already-landed P30.1 shared-session bundles.

### Acceptance Criteria

- `TuiSession` is no longer defined as one flat wide bag of mixed concerns
- UI persistence/restoration reads from view state only
- remote summary/detail writes flow into projection state
- local submission-loop lifecycle writes flow into runtime state
- existing shared-session behavior remains stable in focused regression bundles

### Status

- completed

## Current Execution Slice: P30.1 Code Guardrails - Four-Entrance Interaction Surface Contract (2026-04-12)

### Why This Slice Is Next

- architecture wording is corrected, but runtime/application code still accepted free-form `surface/channel_type` pairs without one shared boundary model
- that left room for future drift where product entrances and concrete channel adapters get mixed again
- we needed one code-level seam to classify:
  - user entrance (`cli/tui/webui/remote`)
  - concrete remote channel adapter (`qq/wechat/feishu`)

### Scope

- add a shared interaction-surface resolver
- wire gateway/chat and channel-ingress flows through the resolver
- wire runtime surface binding through the same resolver while preserving current `qq` session behavior
- add focused tests for the new classification seam

### Out Of Scope

- no API schema expansion in this slice
- no session ownership redesign in this slice
- no WebUI/remote channel feature expansion in this slice

### Files In Scope

- `src/mini_agent/runtime/interaction_surface.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `src/mini_agent/application/channel_ingress_use_cases.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_interaction_surface.py`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Execution Steps

1. Add a shared resolver for surface/channel normalization and entrance classification.
2. Route gateway and channel-ingress request normalization through that resolver.
3. Route runtime surface binding through the same resolver without changing existing `qq/tui` semantics.
4. Verify with focused tests around interaction classification + gateway/channel contracts.

### Acceptance Criteria

- one shared resolver exists for entrance/channel classification
- gateway/application/runtime paths use the same resolver instead of ad hoc string handling
- existing `qq` session behavior remains stable in focused regression bundles

### Status

- completed

## Current Execution Slice: P30 Four-Entrance Architecture Correction Sync (2026-04-12)

### Why This Slice Is Next

- the previous P30 wording still flattened the product entrances into `CLI / TUI / WebUI / QQ`
- the corrected design is now clearer:
  - the user-side product has four entrances:
    - `CLI`
    - `TUI`
    - `WebUI`
    - `Remote Interaction`
  - `QQ / WeChat / Feishu` are concrete channel adapters under the remote entrance
- if this is not corrected first, later refactor work will keep mixing product entrances with implementation adapters

### Scope

- rewrite the active architecture wording around the four-entrance model
- update the P30 correction doc and executable task plan
- re-anchor working notes so follow-up refactor work starts from the corrected taxonomy

### Out Of Scope

- no runtime behavior change in this slice
- no new channel feature work
- no WebUI implementation restart in this slice

### Files In Scope

- `docs/ARCHITECTURE.md`
- `docs/P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `docs/DEVELOPMENT_INDEX.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Execution Steps

1. Rewrite the active architecture doc so the entrance model is `CLI / TUI / WebUI / Remote Interaction`.
2. Clarify that `QQ / WeChat / Feishu` are remote-channel adapters, not peer product entrances.
3. Update the P30 refactor plan so the next cuts follow the corrected entrance taxonomy.
4. Sync the working notes so later implementation slices do not drift back to the old wording.

### Acceptance Criteria

- active architecture docs no longer list `QQ` as a peer product entrance
- the remote entrance and its adapter sub-layer are explicit
- the P30 execution order is updated to start from the four-entrance boundary lock

### Status

- completed

## Current Execution Slice: P30.1 QQ Channel Hard Consolidation (2026-04-12)

### Why This Slice Is Next

- the active architecture already locks `QQ` as a transport/adapter only surface under `P30`
- the repo still contains parallel historical QQ paths:
  - `src/apps/qqbot_channel` as the actual runtime path
  - `src/channels/qqbot` as a separate Node/TypeScript channel package
  - `src/mini_agent/channels/qqbot.py` as an older Python OneBot adapter
- leaving those paths alive keeps the canonical architecture blurry and invites the exact session-ownership drift we are trying to remove

### Scope

- keep `src/apps/qqbot_channel` as the only QQ runtime implementation
- keep `qq-official-bot` as the external SDK dependency
- migrate smoke coverage and active references to that one path
- delete historical QQ implementations and update active docs/tests/scripts accordingly

### Out Of Scope

- no new QQ feature expansion
- no second QQ protocol implementation
- no compatibility shell for the deleted historical paths

### Files In Scope

- `src/apps/qqbot_channel/*`
- `src/channels/qqbot/*`
- `src/mini_agent/channels/qqbot.py`
- `scripts/qq_wechat_smoke.py`
- `tests/test_channels.py`
- active docs that still reference the removed QQ paths

### Execution Steps

1. Refactor `src/apps/qqbot_channel` into the only supported QQ adapter path and keep its runtime surface thin.
2. Add or migrate QQ smoke coverage onto the app path.
3. Delete `src/channels/qqbot` and the legacy Python QQ adapter.
4. Remove/update tests, scripts, and active docs that still point to removed paths.
5. Run focused verification for QQ runtime and docs/test hygiene.

### Acceptance Criteria

- repo has exactly one live QQ implementation path: `src/apps/qqbot_channel`
- QQ runtime still uses `qq-official-bot`
- smoke/testing no longer depends on `src/channels/qqbot` or `mini_agent.channels.qqbot`
- active docs describe QQ only as the optional adapter app bound to the shared gateway/session services

### Status

- completed

## Current Execution Slice: P30 Surface / Session Refactor Task Planning (2026-04-12)

### Why This Slice Is Next

- the architectural correction in `P30` is now written, but still too high-level to steer implementation safely
- after the latest discussion, the most important correction is explicit:
  - sessions must not be cut apart by `CLI / TUI / WebUI / QQ`
  - surfaces only operate sessions
  - QQ is a channel adapter reusing shared semantics, not a session owner and not a TUI-owned subtype
- before more refactor code starts, that correction needs to become an executable task plan

### Scope

- turn the P30 architecture correction into concrete implementation phases
- define the next recommended execution order
- sync `task_plan.md` and doc indexes so the refactor entry point is explicit

### Out Of Scope

- no production code changes in this slice
- no runtime behavior changes
- no new session surface features

### Files In Scope

- `docs/P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `docs/DEVELOPMENT_INDEX.md`
- `docs/DOCS_INDEX.md`

### Execution Steps

1. Convert the P30 architecture correction into concrete phases and acceptance criteria.
2. Define the next recommended implementation order.
3. Register the new task-plan doc in active indexes.
4. Re-anchor `task_plan.md` so P30 is the next structural execution entry.

### Acceptance Criteria

- one executable P30 task-plan doc exists
- `task_plan.md` points to the P30 execution track
- development indexes expose the new refactor entry point

### Status

- completed

## Current Execution Slice: P29.3e Local Skill Command Convergence (2026-04-12)

### Why This Slice Is Next

- P29.3a through P29.3d proved the shared local command seam can carry:
  - status-style commands
  - local session/workspace toggles
  - prepared-context policy mutation
  - heavyweight memory execution semantics
- the next duplicated command family had to be `skill` because:
  - local `skill` still had one of the largest duplicated branches in TUI and CLI
  - it mixes catalog reads, workspace policy mutation, and runtime-reload handoff
  - leaving it split would keep the operator-command boundary half-finished

### Scope

- extend the shared local operator command service with local `skill` semantics
- route TUI local `skill` execution through that shared service
- keep TUI/CLI surface-specific runtime reload orchestration outside the shared seam
- add focused regression for shared local `skill` list/show/install/mode behavior

### Out Of Scope

- no remote shared-session `skill` transport rewrite in this slice
- no `model` command convergence yet
- no QQ command execution convergence yet

### Files In Scope

- `src/mini_agent/commands/execution.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/cli_interactive.py`
- `tests/test_command_execution_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Add shared local `skill` execution semantics with typed results.
2. Route CLI local `/skill` execution through the shared service.
3. Route TUI local `/skill` execution through the shared service.
4. Add focused regression for shared `skill` list/show/install/mode behavior.
5. Re-run the focused command/TUI/CLI/readiness bundle.

### Acceptance Criteria

- TUI and CLI local `skill` behavior no longer lives in duplicated ad hoc execution branches
- local `skill` catalog/policy/mutation semantics are shared even if final reload messaging still differs
- runtime reload ownership remains surface-specific instead of leaking back into the shared execution seam

### Status

- completed

## Current Execution Slice: P29.3d Local Memory Command Convergence (2026-04-12)

### Why This Slice Is Next

- P29.3a established the shared local command execution seam with `mcp` and `sandbox`
- P29.3b extended that seam to `kb`
- P29.3c proved the seam can carry real local mutation semantics with `context`
- the next command family had to be `memory` because:
  - it still carried the largest duplicated local operator branch in both TUI and CLI
  - it mixes read-only diagnostics with real workspace/runtime mutations
  - leaving it split would keep session-boundary repair incomplete

### Scope

- extend the shared local operator command service with local `memory` semantics
- route TUI local memory execution through that shared service
- route CLI local memory execution through that shared service
- unify shared `/memory show` argument parsing between TUI and CLI

### Out Of Scope

- no remote shared-session memory transport rewrite in this slice
- no `skill` or `model` command convergence yet
- no QQ command execution convergence yet

### Files In Scope

- `src/mini_agent/commands/execution.py`
- `src/mini_agent/commands/__init__.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/cli_interactive.py`
- `tests/test_command_execution_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Add shared local `memory` execution semantics with typed results.
2. Route CLI local `/memory` execution through the shared service.
3. Route TUI local `/memory` execution through the shared service.
4. Add focused regression for shared memory parsing and mutation behavior.
5. Re-run the focused command/TUI/CLI/readiness bundle.

### Acceptance Criteria

- TUI and CLI local `memory` behavior no longer lives in duplicated ad hoc execution branches
- local `memory` read/mutation semantics are shared even if final surface feedback still differs
- shared `/memory show` parsing no longer exists in two separate helpers

### Status

- completed

## Current Execution Slice: P29.3c Local Context Command Convergence (2026-04-12)

### Why This Slice Is Next

- P29.3a already proved the shared command execution seam with `mcp` and `sandbox`
- P29.3b extended that seam to local `kb`
- the next best candidate was `context` because:
  - it exists on both TUI and CLI
  - it contains real local state mutation semantics
  - but it is still smaller and safer than `memory`

### Scope

- extend the shared local operator command service with local `context` semantics
- route local `context` handling in TUI and CLI through that service
- keep remote shared-session context mutation transport unchanged in this slice

### Out Of Scope

- no remote context transport rewrite
- no `/memory` migration yet
- no QQ command execution convergence yet

### Files In Scope

- `src/mini_agent/commands/execution.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/cli_interactive.py`
- `tests/test_command_execution_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Add shared local `context` execution semantics with typed results.
2. Route CLI local `/context` handling through the shared service.
3. Route TUI local `/context` handling through the shared service while keeping remote update transport unchanged.
4. Re-run focused TUI/CLI/command/readiness regression bundles.

### Acceptance Criteria

- TUI and CLI local `context` behavior no longer lives in separate ad hoc branches
- local context validation, budget parsing, source-list normalization, and reset semantics are shared
- readiness walkthroughs still pass, including the local `context reset` behavior

### Status

- completed

## Current Execution Slice: P29.3b Local KB Command Convergence (2026-04-12)

### Why This Slice Is Next

- P29.3a already proved the shared command execution seam with:
  - `mcp`
  - `sandbox`
- the next best command family was `kb` because:
  - it exists in both TUI and CLI
  - it still had duplicated local validation and toggle semantics
  - it is more stateful than `sandbox` but still much smaller than `context` or `memory`

### Scope

- extend the shared local operator command service with local `kb` semantics
- route local `kb status|on|off` through that shared service in TUI and CLI
- keep remote shared-session `kb` handling unchanged in this slice

### Out Of Scope

- no remote `kb` command rewrite
- no `/context` or `/memory` migration yet
- no QQ-side command execution unification yet

### Files In Scope

- `src/mini_agent/commands/execution.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/cli_interactive.py`
- `tests/test_command_execution_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Add shared local `kb` execution semantics with typed results.
2. Route TUI local `kb` handling through the shared service.
3. Route CLI local `kb` handling through the shared service.
4. Re-run focused TUI/CLI/command/readiness regression bundles.

### Acceptance Criteria

- TUI and CLI local `kb` behavior no longer lives in separate ad hoc branches
- local `kb` status/toggle semantics are shared even if final rendering still differs by surface
- focused regression includes direct service tests for shared `kb` semantics

### Status

- completed

## Current Execution Slice: P29.3a Local Operator Command Service First Cut (2026-04-12)

### Why This Slice Is Next

- P29.1a already unified session read truth
- P29.2a and P29.2b already moved session mutation ownership out of raw gateway/TUI transport paths
- the next remaining drift surface is command execution:
  - command syntax/help/catalog are shared
  - command behavior still lives separately in TUI and CLI
- the safest first cut is not the whole command surface at once
  - start with low-coupling operator commands
  - avoid entangling active session execution flow while the command seam is still being extracted

### Scope

- introduce a shared local operator command execution service
- migrate one stable, high-value command slice through it:
  - `mcp`
  - `sandbox`
- keep remote shared-session command branches unchanged in this slice

### Out Of Scope

- no full `/context` or `/memory` migration yet
- no QQ command execution unification yet
- no session execution-stream rewrite

### Files In Scope

- `src/mini_agent/commands/execution.py`
- `src/mini_agent/commands/__init__.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/cli_interactive.py`
- `tests/test_command_execution_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Add a shared local operator command execution service with typed results.
2. Route local `mcp` command handling in TUI/CLI through it.
3. Route local `sandbox status` handling in TUI/CLI through it.
4. Re-run focused TUI/CLI/command/readiness regression bundles.

### Acceptance Criteria

- TUI and CLI local `mcp` command semantics no longer live in separate ad hoc branches
- TUI and CLI local `sandbox status` semantics no longer live in separate ad hoc branches
- focused regression includes direct tests for the new shared command execution seam

### Status

- completed

## Current Execution Slice: P29.2b TUI Remote Session Service Convergence (2026-04-12)

### Why This Slice Is Next

- P29.1a already unified session read models
- P29.2a already extracted gateway-side session mutation and turn ownership
- the next highest-value leak was still in TUI:
  - remote shared-session mutations still called `gateway_client` directly
  - TUI still owned raw transport-shape assumptions for model/policy/context/memory/skill/control flows

### Scope

- add one typed client-side remote session service for TUI
- move remote session mutation/control flows in TUI off raw `gateway_client` calls
- make TUI consume typed DTOs for remote session mutation results
- add focused regression coverage for the new remote service seam

### Out Of Scope

- no remote `run_chat` execution-path rewrite in this slice
- no CLI migration yet
- no shared command execution service yet

### Files In Scope

- `src/mini_agent/application/session_remote_service.py`
- `src/mini_agent/application/__init__.py`
- `src/mini_agent/tui/app.py`
- `tests/test_session_remote_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Add a typed remote session service over the TUI gateway client.
2. Route TUI remote session CRUD/control/mutation flows through that service.
3. Replace raw dict assumptions in TUI with typed DTO handling where those flows now use the service.
4. Re-run focused TUI/session/gateway regression bundles.

### Acceptance Criteria

- TUI no longer calls raw `gateway_client` methods for remote session mutation/control flows
- remote model/runtime-policy/context/memory/skill/approval/control actions go through `RemoteSessionService`
- focused regression remains green with explicit coverage for the new typed remote service seam

### Status

- completed

## Current Execution Slice: P29.2a Session Application Service Extraction (2026-04-12)

### Why This Slice Is Next

- P29.1a already made session read models explicit
- the next highest-value boundary repair is removing gateway/use-case ownership of runtime session internals
- the main leakage point was turn scaffolding:
  - `session.lock`
  - surface binding
  - pending model/skill application
  - turn start/finish
  - session transcript mutation

### Scope

- add a shared `session_service`
- move session read/mutation wrappers into that service
- move gateway chat/stream turn scoping behind a managed service-owned turn lease
- remove direct `MainAgentSessionState` and `session.lock` usage from gateway use cases

### Out Of Scope

- no full runtime-manager decomposition yet
- no TUI local runtime-host extraction yet
- no behavior redesign of approvals/delegation/activity streams

### Files In Scope

- `src/mini_agent/application/session_service.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `src/mini_agent/application/__init__.py`
- `tests/test_session_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Introduce `SessionApplicationService` and a managed turn lease.
2. Route session CRUD/detail/control wrappers through the service.
3. Route gateway `run_chat` / `stream_chat_events` through the service-owned turn lease.
4. Verify gateway/shared-session/TUI/readiness regression bundles remain green.

### Acceptance Criteria

- `MainAgentGatewayUseCases` no longer imports `MainAgentSessionState`
- `MainAgentGatewayUseCases` no longer locks `session.lock` directly
- gateway session mutations and turn scaffolding go through the shared service
- focused and readiness-adjacent regression bundles stay green

### Status

- completed

## Current Execution Slice: P29.1a Shared Session Projection Seam (2026-04-12)

### Why This Slice Is Next

- the P29 audit and hard-refactor plan are already written
- the safest first structural cut is to unify session read-model assembly before moving behavior
- runtime and TUI still each infer session truth in their own way, which is the immediate risk surface

### Scope

- add shared session projection models under `src/mini_agent/session/`
- route runtime session summary/detail DTO assembly through those projections
- route TUI session summary/detail display semantics through the same projection seam
- add focused regression coverage for transport and terminal projection behavior

### Out Of Scope

- no session behavior rewrite yet
- no gateway/service ownership extraction yet
- no compatibility shell or parallel session abstraction

### Files In Scope

- `src/mini_agent/session/projection.py`
- `src/mini_agent/session/__init__.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/tui/app.py`
- `tests/test_session_projection.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Define shared session transport and terminal projections.
2. Refactor runtime summary/detail builders to emit DTOs from shared projections.
3. Refactor TUI session read/display helpers to consume shared projections.
4. Run focused and readiness-adjacent regression bundles.

### Acceptance Criteria

- runtime session DTO assembly uses shared projection objects
- TUI session display helpers use shared projection semantics
- focused regression and readiness-adjacent tests stay green

### Status

- completed

## Current Execution Slice: P29 Session Boundary Hard-Refactor Planning (2026-04-12)

### Why This Slice Is Next

- the audit is finished
- the project now has a written problem statement and evidence anchors
- the next failure risk is no longer "unknown architecture smell"; it is implementing more work before the session boundary is repaired

### Scope

- translate the P29 audit into a concrete hard-refactor execution plan
- define the target boundaries, refactor phases, first implementation slice, and acceptance strategy
- sync development index and working logs so future implementation follows the same plan

### Out Of Scope

- no runtime behavior change in this planning slice
- no partial compatibility layers
- no new session-facing feature work

### Files In Scope

- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/DEVELOPMENT_INDEX.md`
- `docs/REFACTOR_TASKS.md`
- `docs/P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Define the target boundary model for session, runtime, application service, and surfaces.
2. Define the phased hard-refactor sequence.
3. Lock the first implementation slice so coding can start without re-arguing structure.
4. Sync planning/index docs to mark P29 as the active architecture-repair track.

### Acceptance Criteria

- a formal P29 implementation plan exists
- the first implementation slice is explicit and testable
- development docs point to the P29 audit and implementation plan

### Status

- in_progress

## Current Execution Slice: P29 Session Boundary And Ownership Audit (2026-04-12)

### Why This Slice Is Next

- the latest session unification work exposed a deeper architecture problem than one isolated bug
- the active risk is now boundary collapse:
  - no single session owner
  - surface/runtime/persistence responsibilities mixed together
  - command semantics duplicated by surface
- continuing feature work on top of that shape would compound the refactor cost

### Scope

- perform a code-level audit of session / gateway / TUI / CLI / QQ boundaries
- identify duplicated ownership, cross-layer leakage, orphan abstractions, and overloaded services
- record a hard-refactor direction before more session-facing features are added

### Out Of Scope

- no functional refactor in this slice
- no compatibility shell work
- no new feature delivery on top of the current session stack

### Files In Scope

- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md`
- session / runtime / TUI / CLI / gateway / QQ source files for inspection

### Execution Steps

1. Audit canonical session ownership across Python runtime, TUI, CLI, and QQ/channel surfaces.
2. Audit command execution ownership across TUI / CLI / QQ.
3. Identify stale, duplicate, or orphaned abstractions still exported as active APIs.
4. Record a hard-refactor plan centered on boundary repair before more session work continues.

### Acceptance Criteria

- one written report exists with concrete boundary findings and evidence
- task planning files reflect that P29 is now the active architecture slice
- the next refactor direction is explicit enough to guide hard restructuring

### Status

- completed

## Current Execution Slice: P24 Demo Baseline Acceptance Lock (2026-04-11)

### Why This Slice Is Next

- the Windows sandbox baseline is now strong enough for the current single-host demo target
- deeper sandbox work such as CPU/time quotas or non-Windows native backends is not a current blocker
- the active top-level goal is still one stable, reviewable demo path centered on `TUI / CLI / QQ / gateway`

### Scope

- freeze sandbox work at the current "good enough for demo" baseline unless a real blocker appears
- turn the current runtime into one explicit demo-acceptance path instead of opening another subsystem branch
- use the existing readiness scripts and command checklist as the primary acceptance seam
- only fix issues that materially affect:
  - local TUI/CLI use
  - shared-session QQ/gateway handoff
  - session/model/memory/KB/skill operator continuity

### Out Of Scope

- no additional sandbox backend work unless a concrete real-use failure appears
- no WebUI restart
- no new marketplace / remote package-management workflow in this slice

### Files In Scope

- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/DEVELOPMENT_INDEX.md`
- `docs/P24_REAL_USE_COMMAND_ACCEPTANCE_CHECKLIST.md`
- readiness / walkthrough docs as needed

### Execution Steps

1. Record that sandbox is intentionally paused at the current baseline.
2. Re-anchor the active phase to P24 demo-baseline acceptance.
3. Keep the command-level and scripted acceptance docs aligned with the live runtime surface.
4. Use the next implementation slice only for demo-blocking gaps discovered from that acceptance path.

### Acceptance Criteria

- project docs clearly show sandbox is no longer the active track
- current active track is explicitly "demo-baseline acceptance"
- acceptance docs include the live sandbox-status operator seam now present in CLI/TUI
- future work resumes from demo-critical gaps, not optional sandbox expansion

### Status

- in_progress

### Current Audit State

- completed in this slice:
  - command catalog / unified entry preflight
  - scripted TUI checklist
  - scripted TUI interaction walkthrough
  - scripted shared-session walkthrough
  - scripted channel-ingress walkthrough
  - targeted readiness regression bundle
  - live headless JSON prompt against a real configured model
  - runtime stack lifecycle validation (`qq status/down/up/logs`)
  - full regression while a real local gateway/qq demo stack was already running
- remaining high-value unverified item:
  - live external QQ roundtrip acceptance on the real bot path

### 2026-04-11 Demo Readiness Note

- real-use acceptance exposed one genuine demo/test isolation bug:
  - if the local gateway runtime stack is already running on `127.0.0.1:8008`
  - gateway `TestClient` suites fail because the gateway lifespan instance lock also blocks pytest startup
- the fix is now explicit in test bootstrap:
  - pytest defaults `MINI_AGENT_STUDIO_ENABLE_INSTANCE_LOCK=0`
  - real runtime lock behavior remains unchanged for normal app startup
- this keeps both sides correct:
  - the demo runtime still has single-instance protection
  - regression tests can run on the same workstation while the demo stack is up

## Current Execution Slice: Windows Sandbox Resource Caps And Persistence Recovery (2026-04-11)

### Why This Slice Is Next

- sandbox status visibility is already wired through TUI / CLI / gateway session payloads
- the next worthwhile hardening step is adding real native child-process resource caps instead of only more reporting
- one regression also surfaced during the status-plumbing slice:
  - shared-session persistence silently stopped writing metadata because sandbox diagnostics were computed through an invalid class-method call

### Scope

- keep the existing Windows restricted-token + job-object launch path
- add conservative Windows job caps for:
  - active process count
  - per-process memory
- plumb the cap values from runtime security config into sandbox manager/backend selection
- surface the cap values through sandbox diagnostics and `/sandbox status`
- fix the shared-session persistence regression so restart/import/export flows continue to work

### Out Of Scope

- no Linux/macOS native sandbox backend in this slice
- no AppContainer migration
- no aggressive CPU / wall-clock throttling yet

### Files In Scope

- `src/mini_agent/config.py`
- `src/mini_agent/config/config-example.yaml`
- `src/mini_agent/runtime/tooling.py`
- `src/mini_agent/code_agent/sandbox/manager.py`
- `src/mini_agent/code_agent/sandbox/windows.py`
- `src/mini_agent/runtime/sandbox_state.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_code_agent_sandbox.py`
- `tests/test_security_policy.py`

### Execution Steps

1. Add security config fields for Windows sandbox process-count and per-process-memory caps.
2. Pass those values through runtime tooling into the sandbox manager/backend.
3. Apply real job-object limit flags for active-process and process-memory caps.
4. Expose the cap values through sandbox diagnostics and `/sandbox status`.
5. Fix the shared-session persistence regression introduced by sandbox diagnostics persistence.
6. Re-run focused sandbox, TUI/CLI, and gateway/session persistence tests.

### Acceptance Criteria

- Windows restricted child processes run under conservative job caps by default
- operators can disable/override the caps through config
- `/sandbox status` reports the effective cap values honestly
- shared-session persistence, restart recovery, snapshot, and gateway flows remain green

### Status

- completed and verified

### Verification

- `uv run pytest tests/test_code_agent_sandbox.py tests/test_security_policy.py -q`
- `uv run pytest tests/test_bash_tool.py tests/test_agent_execution_policy.py tests/test_code_agent_permissions.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py -q -k "sandbox or approval or bash or security or session or snapshot"`
- `uv run pytest tests/test_command_catalog.py tests/test_interface_dto_contracts.py tests/test_cli_submission_loop.py -q`
- `uv run pytest tests/test_tui_app.py -q -k "sandbox or status_panel or prompt_input_slash_completer_suggests_command_candidates"`
- `uv run pytest tests/test_main_agent_gateway_use_cases.py -q -k "session or snapshot or model or mcp"`

## Current Execution Slice: Windows Low-Integrity Restricted Launch Finalization (2026-04-11)

### Why This Slice Is Next

- the native restricted launch path is already real and the token/job baseline is tighter
- one honest remaining gap is integrity labeling:
  - the child should run at low integrity instead of inheriting the caller integrity level
  - token mandatory policy should be reported from the real backend state instead of being implied by older assumptions

### Scope

- keep the existing Windows restricted-token native launch path
- explicitly apply a low-integrity label to the restricted primary token before process creation
- surface the effective mandatory-policy bits through sandbox env and metadata
- verify the launched child really runs at low integrity on Windows
- keep manager-side selection metadata aligned with the backend's real restriction state

### Out Of Scope

- no attempt to force-write token mandatory policy when the host privilege context does not allow it
- no AppContainer migration in this slice
- no new process-count / memory / CPU job caps yet

### Files In Scope

- `src/mini_agent/code_agent/sandbox/windows.py`
- `src/mini_agent/code_agent/sandbox/manager.py`
- `tests/test_code_agent_sandbox.py`

### Execution Steps

1. Apply low integrity to the restricted primary token.
2. Expose integrity level and mandatory-policy bits through sandbox env and metadata.
3. Keep `SandboxManager` preview metadata sourced from the same backend helper instead of hardcoded values.
4. Add Windows-only verification that the launched child token really carries `WinLowLabelSid`.
5. Re-run focused sandbox, bash, approval, and smoke tests.

### Acceptance Criteria

- Windows restricted child processes run at low integrity
- sandbox metadata/env report integrity and mandatory-policy state honestly
- focused sandbox, bash, approval, and gateway/TUI smoke tests remain green

### Status

- completed and verified

### Verification

- `uv run pytest tests/test_code_agent_sandbox.py tests/test_bash_tool.py -q`
- `uv run pytest tests/test_security_policy.py tests/test_agent_execution_policy.py tests/test_code_agent_permissions.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py -q -k "approval or bash or security"`

## Current Execution Slice: Windows Token / Job Restriction Tightening (2026-04-11)

### Why This Slice Is Next

- the native Windows restricted-process launch is now real, but the first launch slice still used a minimal restricted token and minimal job settings
- the next clean improvement is to tighten the launched process baseline further without breaking ordinary CLI workloads

### Scope

- keep the existing restricted-process launch path
- additionally tighten the Windows sandbox baseline by:
  - disabling a curated set of high-privilege builtin groups when creating the restricted token
  - enabling job-object `DIE_ON_UNHANDLED_EXCEPTION`
  - enabling a conservative set of job UI restrictions
- expose the tightened restriction flags through sandbox metadata/env so runtime diagnostics stay honest
- add focused regression coverage for the new metadata defaults

### Out Of Scope

- no AppContainer migration in this slice
- no low-integrity label / token mandatory-policy rewrite in this slice
- no child-process-count cap in this slice, to avoid breaking normal command execution

### Files In Scope

- `src/mini_agent/code_agent/sandbox/windows.py`
- `src/mini_agent/code_agent/sandbox/manager.py`
- `tests/test_code_agent_sandbox.py`

### Execution Steps

1. Add a curated disabled-SID list for high-privilege builtin groups.
2. Apply those deny-only SID restrictions when building the restricted token.
3. Add job-object `DIE_ON_UNHANDLED_EXCEPTION` and UI restriction flags.
4. Expose the new restriction state through sandbox metadata/env.
5. Add focused regression coverage and re-run sandbox/approval tests.

### Acceptance Criteria

- Windows restricted launch still works after the tighter token/job settings
- selection/transform metadata now exposes the added restriction flags
- focused sandbox, bash, and approval regressions remain green

### Status

- completed and verified

### Verification

- `uv run pytest tests/test_code_agent_sandbox.py tests/test_bash_tool.py -q`
- `uv run pytest tests/test_security_policy.py tests/test_agent_execution_policy.py tests/test_code_agent_permissions.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py -q -k "approval or bash or security"`

## Current Execution Slice: Windows Native Restricted-Process Launch (2026-04-11)

### Why This Slice Is Next

- the previous sandbox slices made Windows policy selection honest, but execution still stopped at command transform + metadata
- `windows_restricted_token` existed as a backend name without a true restricted-process launch path
- the next correct step is to turn that backend into a real runtime boundary for Windows shell execution

### Scope

- implement native Windows process launch using:
  - restricted token
  - job object with kill-on-close semantics
  - inherited stdio pipes
- keep the existing policy/transform path as the pre-launch validation layer
- route `BashTool` Windows execution through the native launcher when the active sandbox backend is `windows_restricted_token`
- add focused regression coverage for:
  - native restricted-process launch
  - `BashTool` native-launch branch selection
  - end-to-end `SandboxManager + BashTool` execution on Windows

### Out Of Scope

- no AppContainer backend in this slice
- no Linux/macOS process sandbox backend in this slice
- no finer-grained Windows token ACL tuning beyond the initial restricted-token + job-object baseline

### Files In Scope

- `src/mini_agent/code_agent/sandbox/windows.py`
- `src/mini_agent/code_agent/sandbox/manager.py`
- `src/mini_agent/tools/bash_tool.py`
- `tests/test_code_agent_sandbox.py`
- `tests/test_bash_tool.py`

### Execution Steps

1. Add a Windows native process adapter compatible with the current `BashTool` expectations.
2. Launch PowerShell under a restricted token via `CreateProcessAsUser`.
3. Bind the launched process to a job object with kill-on-close.
4. Route Windows `BashTool` execution through the native launcher when the selected backend is `windows_restricted_token`.
5. Add focused tests for direct launch, branch selection, and end-to-end manager integration.

### Acceptance Criteria

- Windows sandbox backend launches a real restricted child process instead of only transforming command text
- `BashTool` uses the native launcher under the Windows restricted backend
- end-to-end Windows sandbox execution returns stdout correctly
- existing approval/security tests remain green

### Status

- completed and verified

### Verification

- `uv run pytest tests/test_code_agent_sandbox.py tests/test_bash_tool.py -q`
- `uv run pytest tests/test_security_policy.py tests/test_agent_execution_policy.py tests/test_code_agent_permissions.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py -q -k "approval or bash or security"`

## Current Execution Slice: Sandbox Auto-Edit Mutation Tiering (2026-04-11)

### Why This Slice Is Next

- the previous tightening made `auto-edit` safer, but also made it less practical for normal coding work because all mutations required approval
- Mini-Agent still needs one middle mode between `suggest` and `full-auto`
- the clean boundary is not "all writes vs no writes"; it is:
  - ordinary workspace file editing
  - durable/system mutations such as skill install/uninstall, long-term memory writes, and shell execution

### Scope

- keep `auto-edit` able to execute ordinary `write_file` / `edit_file` mutations without approval
- keep durable/system mutations on the explicit approval path:
  - `record_note`
  - `user_modeling`
  - `install_skill*`
  - `uninstall_skill`
  - `rollback_skill`
  - shell execution remains approval-gated
- preserve `tool_exclude` precedence over any `auto-edit` allow rule
- update config-example wording so the profile semantics match runtime behavior

### Out Of Scope

- no OS-level sandbox backend work in this slice
- no new approval UI
- no change to `suggest` or `full-auto` top-level semantics

### Files In Scope

- `src/mini_agent/runtime/tooling.py`
- `src/mini_agent/config/config-example.yaml`
- `tests/test_security_policy.py`

### Execution Steps

1. Add specific `auto-edit` allow rules only for `write_file` and `edit_file`.
2. Leave durable/system mutation tools on the default ASK path.
3. Lock rule ordering so `tool_exclude` still wins.
4. Add focused regression tests for the new tiered behavior.

### Acceptance Criteria

- `auto-edit` allows ordinary workspace file edits without approval
- durable/system mutations still require approval
- `tool_exclude` still overrides the `auto-edit` allow rules
- `full-auto` remains unchanged

### Status

- completed and verified

### Verification

- `uv run pytest tests/test_security_policy.py tests/test_code_agent_permissions.py tests/test_agent_execution_policy.py tests/test_code_agent_tools.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py -q -k approval`
- `uv run pytest tests/test_security_audit.py tests/test_bash_tool.py tests/test_code_agent_sandbox.py -q`

## Current Execution Slice: Sandbox Default-Mutation Approval Tightening (2026-04-11)

### Why This Slice Is Next

- workspace file boundaries and elevated bash approval are now real, but the default `auto-edit` approval profile still leaves one trust gap
- `build_approval_engine(...)` currently lets `WRITE` and `EDIT` tool kinds run without confirmation under `auto-edit`
- that means the runtime default is still wider than the hardened file/shell boundary now implies
- the next clean step is to keep read-only behavior frictionless while putting state-changing actions back behind explicit approval

### Scope

- remove the implicit `WRITE` / `EDIT` allow rules from the `auto-edit` runtime approval profile
- keep `full-auto` unchanged as the explicit autonomous mode
- keep read-only default-allow behavior unchanged
- update security-audit messaging so `elevated_exec=require_approval` reflects the now-live approval plumbing instead of stale pre-implementation wording
- add focused regression coverage for the tightened mutation-approval boundary

### Out Of Scope

- no redesign of approval-token UX in TUI / CLI / gateway
- no new OS-level sandbox backend
- no permission split finer than the current declarative tool kinds in this slice

### Files In Scope

- `src/mini_agent/runtime/tooling.py`
- `src/mini_agent/security/audit.py`
- `src/mini_agent/config/config-example.yaml`
- `tests/test_security_policy.py`
- `tests/test_security_audit.py`

### Execution Steps

1. Remove the `auto-edit` default allow rules for `ToolKind.WRITE` and `ToolKind.EDIT`.
2. Keep read-only and `full-auto` behavior unchanged.
3. Update audit wording/severity for `elevated_exec=require_approval`.
4. Add focused tests proving:
   - `auto-edit` now asks for write/edit mutations
   - read-only tools still auto-allow
   - `full-auto` still bypasses approval
   - security-audit wording matches the live approval flow

### Acceptance Criteria

- `auto-edit` no longer silently allows workspace mutations by default
- read-only tools still execute without approval prompts
- `full-auto` still allows autonomous mutations
- audit output no longer claims approval plumbing is missing when it is already implemented

### Status

- completed and verified

### Verification

- `uv run pytest tests/test_security_policy.py tests/test_security_audit.py tests/test_code_agent_permissions.py tests/test_agent_execution_policy.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py -q -k approval`
- `uv run pytest tests/test_bash_tool.py tests/test_code_agent_sandbox.py -q`

## Current Execution Slice: Sandbox Hardening And Real Approval Wiring (2026-04-11)

### Why This Slice Is Next

- current sandboxing is usable as a lightweight guardrail, but it is not yet a coherent operator-trust boundary
- `bash` already passes through runtime policy and sandbox transform hooks
- however, file tools still allow absolute-path access outside the workspace
- `elevated_exec=require_approval` currently blocks elevated shell outright instead of routing through the live approval system
- network policy primitives exist, but runtime config does not yet wire them into the active sandbox manager

### Scope

- add hard workspace-boundary enforcement for `read_file`, `write_file`, and `edit_file`
- make `elevated_exec=require_approval` participate in the existing approval flow instead of being a dead-end block
- extend security config/runtime wiring so network policy can be configured and reaches the active sandbox manager
- keep the current TUI/CLI/gateway approval UX and reuse the existing approval event path

### Out Of Scope

- no new container/AppContainer/job-object subsystem in this slice
- no Linux/macOS sandbox backend in this slice
- no redesign of the full tool permission model outside the targeted shell/file/network boundary fixes

### Files In Scope

- `src/mini_agent/tools/file_tools.py`
- `src/mini_agent/security/policy.py`
- `src/mini_agent/runtime/tooling.py`
- `src/mini_agent/config.py`
- `src/mini_agent/config/config-example.yaml`
- `src/mini_agent/code_agent/sandbox/manager.py`
- `src/mini_agent/code_agent/sandbox/network.py`
- `src/mini_agent/agent.py`
- focused tests under:
  - `tests/test_security_policy.py`
  - `tests/test_code_agent_sandbox.py`
  - `tests/test_agent_execution_policy.py`
  - `tests/test_bash_tool.py`

### Execution Steps

1. Add one canonical workspace-boundary resolver for file tools and reject paths outside the workspace root.
2. Extend runtime security policy so elevated shell commands can surface as approval-required rather than hard-block-only.
3. Reuse the existing tool approval flow inside `Agent` for elevated bash execution.
4. Add security config fields for network policy and wire them into `SandboxManager`.
5. Add focused regression coverage for:
   - file-tool workspace escape rejection
   - elevated shell approval-required path
   - configured network allowlist/block behavior through runtime tooling

### Acceptance Criteria

- absolute or traversal-based file-tool paths outside the active workspace are rejected consistently
- `elevated_exec=require_approval` no longer dead-ends; the agent can request approval and continue after approval
- configured network policy reaches the active sandbox manager and blocks disallowed domains in workspace sandbox mode
- focused tests prove the new boundary behavior directly

### Status

- completed and verified

### Verification

- `uv run pytest tests/test_file_tools_workspace_boundary.py tests/test_security_policy.py tests/test_agent_execution_policy.py tests/test_bash_tool.py tests/test_code_agent_sandbox.py tests/test_code_agent_permissions.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py -q -k "approval or security or bash"`
- `uv run pytest tests/test_config_local_env.py tests/test_single_instance.py tests/test_cli_stack_command.py tests/test_provider_config.py -q`
- `uv run pytest tests/test_agent_core_kernel.py tests/test_agent.py tests/test_security_audit.py -q`

## Current Stage Override: Demo Baseline (2026-04-11)

The active top-level goal has moved beyond the original P26-only execution thread.
Mini-Agent is now in a demo-baseline phase focused on showing one coherent end-to-end operator experience.

### Stage Goal

Ship one stable, reviewable demo path built around the existing core:

- TUI / CLI as the primary operator surface
- gateway + QQ shared-session handoff as the remote extension path
- unified model / session / memory / KB / skill controls on the same runtime seam
- no new parallel subsystem added just for demo polish

### Demo-Critical Capabilities To Lock

- stable local TUI conversation loop
- stable shared-session loop: QQ -> gateway -> runtime -> TUI takeover / continue
- model switching and session persistence
- KB explicit toggle and lightweight RAG usage
- memory inspection / promotion / workspace-session integration
- skill discovery / policy control / runtime reload visibility
- basic local MCP operator seam (`/mcp status|list|reload`) on top of the existing runtime integration

### Explicit Skill Boundary For This Stage

What is already in scope:

- builtin + workspace skill discovery
- workspace-level skill policy (`all` / `allowlist` + allow/deny mutation)
- policy-aware runtime filtering for prompt injection, `get_skill(...)`, and turn-context hints
- local + shared operator controls via `/skill ...`

What is not yet a finished capability:

- agent-autonomous skill installation from marketplace / URL / package
- persisted remote skill source registration workflow
- rollback / source-ledger / package validation beyond local path + inline workspace install
- remote shared-session MCP control and MCP tool-name collision handling

### Immediate Next Slice

1. lock the demo script and walkthrough around the currently real capabilities
2. keep polishing operator visibility and recovery semantics only where they improve demo reliability
3. treat marketplace/package-style skill installation as a post-demo slice; local path install and agent-authored inline install are now available

### Builtin Skill Direction Lock: 2026-04-11

The builtin skill target is now explicitly fixed to a MiniMax-first bundled catalog instead of the older Anthropic-style example bundle currently vendored in `src/mini_agent/skills/`.

Primary doc:

- `docs/P28_BUILTIN_SKILL_REALIGNMENT_PLAN.md`

Target bundled layers:

- Core Development:
  - `frontend-dev`
  - `fullstack-dev`
  - `android-native-dev`
  - `ios-application-dev`
  - `flutter-dev`
  - `react-native-dev`
  - `shader-dev`
  - `mcp-builder`
  - `webapp-testing`
  - `skill-creator`
- Documents And Office:
  - `minimax-docx`
  - `minimax-pdf`
  - `pptx-generator`
  - `minimax-xlsx`
- Multimodal And Creative:
  - `minimax-multimodal-toolkit`
  - `gif-sticker-maker`
  - `vision-analysis`
  - `minimax-music-gen`
- Optional Entertainment / Demo:
  - `buddy-sings`
  - `minimax-music-playlist`
  - `minimax-novel-demo`

Execution priority for that migration:

1. [completed] replace the four builtin document skills
2. [completed] add the first MiniMax-first development / multimodal skills (`frontend-dev`, `fullstack-dev`, `vision-analysis`, `gif-sticker-maker`)
3. [completed] archive product-misaligned Anthropic example skills from the default builtin bundle
4. [completed] expand to the next mobile / shader / music tier:
   - `android-native-dev`
   - `ios-application-dev`
   - `flutter-dev`
   - `react-native-dev`
   - `shader-dev`
   - `minimax-music-gen`
5. [completed] expand the optional / demo tier:
   - `buddy-sings`
   - `minimax-music-playlist`
   - both now exist as real builtin skills layered on top of the existing MiniMax music/toolkit path
6. future follow-up:
   - reassess the final builtin catalog after real demo usage
   - trim any optional/demo skills that prove noisy or low-value in default discovery
7. [completed] add bundled-skill trigger audit + Chinese prompt trigger hardening:
   - `scripts/skill_trigger_audit.py`
   - repo-level Chinese prompt trigger regression tests
   - metadata-driven trigger keyword matching in skill ranking
8. [completed] validate real model-side skill loading and tune progressive-disclosure behavior:
   - added `scripts/skill_live_probe.py`
   - hardened live probe cleanup/startup around MCP cancellation and LLM client shutdown
   - tightened system prompt / metadata prompt / relevant-skill turn-context guidance
   - shortened overly rich tier-1 skill descriptions that were causing "mention skill without loading" behavior
   - latest live probe baseline: `4/4` expected skills loaded through real `get_skill(...)` calls

### Notes

- This stage override is intentional and should be treated as the current execution priority over older single-topic slices below.
- Existing P26/P27 work remains valid and is now considered supporting infrastructure for the demo baseline.

## Goal
Turn the P26 memory architecture report into the live runtime direction for Mini-Agent:

- separate true global durable memory from workspace durable memory
- make global user profile memory available automatically in turn context
- prepare the codebase for workspace-aware session search and future persisted `MemoriaEngine`
- keep the system lightweight, explicit, and non-duplicated

Primary doc:

- `docs/P26_MEMORY_RUNTIME_TASK_PLAN.md`

## Phases
- [completed] Re-audit the existing memory/runtime/session code and confirm the first correct landing slice.
- [completed] Write the detailed P26 implementation plan into project docs.
- [completed] Land Phase 1 core boundary correction:
  - add real global-memory path resolution
  - switch `MemoryService.profile()` to global scope
  - keep workspace note memory unchanged
  - add `UserProfileTurnContextProvider`
  - wire it into default runtime context providers
- [completed] Land Phase 2 workspace-aware session-search context retrieval:
  - add stable `workspace_anchor_dir` into session-search indexing/filtering
  - add `SessionSearchTurnContextProvider`
  - filter prepared session-history hits to the active workspace anchor
  - exclude the current session by default to avoid transcript echo
  - pass gateway shared-session store into kernel turn-context wiring
- [completed] Add focused regression coverage for global profile storage and turn-context injection.
- [completed] Land Phase 3 consolidated-memory refresh and promotion policy:
  - make consolidation workspace-aware instead of sweeping all session history into one workspace
  - add `MemoryService.consolidated_refresh_status()` and `refresh_consolidated_memory()`
  - auto-refresh consolidated memory on demand from the consolidated-memory turn-context provider
  - reject raw KB/tool payloads from durable consolidated-memory promotion
- [completed] Land Phase 4 persisted workspace runtime `MemoriaEngine` with session namespaces:
  - add persisted workspace-scoped runtime task memory under `~/.mini-agent/state/workspaces/<hash>/...`
  - isolate namespaces as `session:<session_id>` and `workspace:shared`
  - wire retrieval through `RuntimeTaskMemoryTurnContextProvider`
  - add conservative post-turn runtime task-memory writeback
  - add explicit promotion hooks into workspace durable notes and global profile memory
- [completed] Land Phase 5 operator-facing memory diagnostics and RAG-memory policy controls:
  - expose shared `memory_diagnostics` in runtime/gateway session summaries/details/snapshots
  - add gateway session memory actions (`status/show/runtime/refresh/promote_note/promote_profile`)
  - add `/memory` inspection/control commands to TUI and CLI
  - surface compact memory summary in TUI status sidebar

## Constraints
- TUI/CLI remain the primary surfaces; WebUI stays paused.
- Do not introduce a second parallel durable memory system.
- Reuse `MemoryService` as the top-level orchestrator.
- Keep RAG/KB separate from memory ownership.
- Avoid compatibility shells when direct refactor is cleaner.
- Keep tests isolated from real `~/.mini-agent` user state.

## Open Decisions
- Whether workspace session-search context should be always-available but usually `no_match`, or only mounted when session-search stats indicate usable history.
- Whether global `AGENT.md` should become runtime-readable in the same phase as user profile, or wait until durable global conventions need separate retrieval.
- Whether Phase 3 consolidation refresh should be automatic on write, scheduled, or operator-triggered first.

## Errors Encountered
- Historical `tests/test_memory_automation.py` content contained broken non-ASCII literals and became a syntax-level blocker during collection.
  - Resolution: rewrite the test file into stable ASCII fixtures and stub the extraction helpers directly so the tests verify writeback behavior instead of brittle encoding artifacts.

## Latest Update
- [completed] Phase 1 is now landed and verified:
  - global durable profile path now resolves through `MINI_AGENT_GLOBAL_MEMORY_ROOT` or `~/.mini-agent/global`
  - `MemoryService.profile()` / `search_profile()` / `add_profile_fact()` now target global user memory
  - workspace profile access remains available explicitly through `workspace_profile()` methods
  - `UserModelingTool` now defaults to global profile memory
  - runtime turn-context wiring now includes `user_profile`
- [completed] Phase 2 is now landed and verified:
  - session-search indexing now persists stable `workspace_anchor_dir`
  - same-anchor filtering works across nested workspace paths under one repo root
  - runtime turn-context wiring now includes `session_search`
  - session-search provider retries with keyword-focused lookup when the raw natural-language query is too strict for FTS matching
  - gateway kernel bootstrap now passes its shared-session store path into turn-context providers
- [completed] Phase 3 is now landed and verified:
  - consolidation state is now namespaced per workspace anchor, preventing cross-workspace `MEMORY.md` pollution
  - `MemoryService` can now report whether consolidated memory is fresh and refresh it on demand
  - consolidated-memory turn-context preparation now auto-refreshes when workspace session history is newer than the consolidated section
  - promotion policy now rejects raw tool / KB payloads so only distilled assistant/user conclusions enter consolidated durable memory
- [completed] Phase 4 is now landed and verified:
  - `WorkspaceMemoriaRuntime` now persists runtime task memory per workspace anchor under `~/.mini-agent/state/workspaces/<hash>`
  - runtime task memory namespaces are isolated as `session:<session_id>` and `workspace:shared`
  - `TurnRuntimeTaskMemory` now stores one compact per-turn summary into session runtime memory after successful turns
  - `RuntimeTaskMemoryTurnContextProvider` now feeds persisted runtime task memory back into the prepared-context seam
  - explicit promotion hooks now exist for runtime task memory -> workspace durable note and runtime task memory -> global profile
- [completed] Phase 5 is now landed and verified:
  - runtime session summaries/details/snapshots now carry one shared `memory_diagnostics` payload for local and remote operators
  - gateway now exposes `POST /api/v1/agent/sessions/{session_id}/memory` for diagnostics, refresh, and promotion actions
  - TUI now supports `/memory status|show|runtime|refresh|promote ...` for local and shared sessions
  - CLI interactive now supports the same `/memory` command family for local sessions
- [completed] Phase 5 operator ergonomics follow-up is now landed and verified:
  - `/memory promote` now accepts `latest`, numeric selectors like `1`, or exact `engram_id`
  - `/memory list` now exposes selector-oriented runtime-memory previews directly
  - runtime previews now enumerate session runtime entries so selector choice is visible to operators
  - explicit `/memory save note <text>` and `/memory save profile <text>` now preserve the KB -> memory confirmation boundary
  - KB-confirmed note saves are categorized as `kb_confirmed`, while manual workspace notes default to `operator_note`
  - QQ shared sessions now expose the same memory control seam through `/memory status|show|list|refresh|promote|save`
- [completed] Phase 5 runtime-memory portability follow-up is now landed and verified:
  - session snapshot/import/export now also carries explicit `workspace_shared_runtime_memory_payload`
  - `workspace:shared` restore semantics are now non-destructive merge-by-content instead of replace-by-snapshot
  - gateway import/export and TUI share/unshare now preserve portable workspace-shared runtime memory without clobbering sibling session facts
  - session reset/delete semantics remain unchanged: `workspace:shared` is still workspace-owned and never cleared by session reset
- [completed] Phase 5 runtime-memory boundary/promotion-policy follow-up is now landed and verified:
  - post-turn runtime writeback still defaults to `session:<session_id>` only
  - runtime writeback now evaluates whether the latest assistant conclusion is a `workspace:shared` candidate
  - candidate state is surfaced in `last_runtime_task_memory` diagnostics instead of auto-promoting silently
  - operators can now use `/memory promote shared <selector>` across local/shared surfaces
  - shared promotion now prefers the distilled candidate text over the raw session summary when available
- [completed] Phase 5 runtime-memory retrieval-boundary follow-up is now landed and verified:
  - `RuntimeTaskMemoryTurnContextProvider` no longer includes `workspace:shared` unconditionally
  - shared runtime memory is now injected only when the query itself looks workspace-scoped, or when session hits are insufficient
  - this keeps `workspace:shared` as a supplemental workspace layer instead of competing with current task/session memory
- Verification:
  - `uv run pytest tests/test_memory_service.py tests/test_user_modeling.py tests/test_memory_automation.py tests/test_agent_turn_context.py tests/test_session_search.py tests/test_session_store_persistence.py tests/test_agent_core_kernel.py tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_api_v1.py -q`
  - `uv run python -m compileall src/mini_agent/memory/paths.py src/mini_agent/memory/builtin_memory.py src/mini_agent/memory/service.py src/mini_agent/memory/automation.py src/mini_agent/memory/session_search.py src/mini_agent/session/persistence.py src/mini_agent/core/session.py src/mini_agent/tools/user_modeling.py src/mini_agent/turn_context.py src/mini_agent/runtime/tooling.py src/mini_agent/agent_core/kernel.py src/apps/agent_studio_gateway/main.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_memory_service.py tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_api_v1.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_interface_dto_contracts.py -q`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/application/main_agent_gateway_use_cases.py src/apps/agent_studio_gateway/main.py src/mini_agent/tui/gateway_client.py src/mini_agent/tui/app.py src/mini_agent/cli_interactive.py`
  - `uv run pytest tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_interface_dto_contracts.py tests/test_agent_studio_gateway_api_v1.py -q`
  - inline `compileall` verification for updated memory/runtime/TUI/CLI modules

## Current Execution Slice: P26 Reset/Delete Semantics Hardening

### Why This Slice Is Next

- current `reset/delete/clear` behavior is not yet a true session reset
- `WorkspaceMemoriaRuntime` persists session-scoped runtime task memory, but session lifecycle resets do not clear the corresponding `session:<session_id>` namespace
- gateway, TUI, and CLI each reset different subsets of state, so the same user intent currently produces different residual state

### Scope

- add explicit runtime-memory namespace cleanup APIs to `WorkspaceMemoriaRuntime`
- make gateway `reset/delete` clear runtime task memory for the target session
- make lifecycle-driven idle reset use the same cleanup semantics
- align TUI local `clear/delete` with the same reset contract
- align CLI `/clear` with the same reset contract
- clear stale local restored/resume state when a session is intentionally reset

### Out Of Scope

- no new memory layer
- no storage-topology rewrite
- no snapshot/import-export payload redesign in this slice
- no command-system expansion in this slice

### Files In Scope

- `src/mini_agent/memory/memoria_runtime.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/cli_interactive.py`
- `tests/test_memoria_runtime.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `tests/test_tui_app.py`
- `tests/test_cli_submission_loop.py`

### Execution Steps

1. Add namespace cleanup helpers to `WorkspaceMemoriaRuntime`.
2. Strengthen gateway reset helpers so ephemeral runtime state and token counters are reset consistently.
3. Wire runtime-memory cleanup into gateway `reset_session`, `delete_session`, and lifecycle auto-reset.
4. Wire the same semantics into local TUI clear/delete paths.
5. Wire the same semantics into CLI `/clear`.
6. Add focused regression coverage for namespace cleanup and reset/delete behavior.

### Acceptance Criteria

- after gateway `reset`, the session transcript, pending approval state, prepared-context state, and `session:<id>` runtime memory are all cleared together
- after gateway `delete`, persisted runtime task memory for that session is removed even if the session was inactive and only existed on disk
- after TUI local `clear/delete`, restored resume state does not rehydrate old context unexpectedly
- after CLI `/clear`, `cli-session` runtime task memory is cleared and token/prepared-context state resets cleanly
- focused regression tests cover the cleanup behavior directly

### Risks To Watch

- deleting the wrong namespace would silently destroy sibling session state in the same workspace
- gateway delete of inactive sessions must resolve the persisted `workspace_dir` before cleanup
- TUI reset must not erase user-visible long-term session metadata that should survive a clear, only transient runtime state

### Status

- completed and verified
- verification:
  - `uv run python -m compileall src/mini_agent/memory/memoria_runtime.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/tui/app.py src/mini_agent/cli_interactive.py tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py -q`
  - result: `171 passed`

## Current Execution Slice: P26 Snapshot / Import / Export Runtime-Memory Parity

### Why This Slice Is Next

- session-scoped runtime task memory now has correct reset/delete semantics
- but `snapshot/import/export` still does not carry the actual `session:<session_id>` runtime task memory payload
- this leaves a continuity gap for:
  - local TUI -> gateway share
  - gateway -> local TUI unshare
  - future snapshot-based migration / restore flows

### Scope

- extend session snapshot/import DTOs to carry session-scoped runtime task memory payload
- add export/import helpers on `WorkspaceMemoriaRuntime`
- make gateway session snapshot export include session runtime task memory
- make gateway session import restore that runtime task memory under the effective destination session id
- make TUI share/unshare preserve runtime task memory through the snapshot contract
- clear old local runtime namespace after successful share migration when the session id changes

### Out Of Scope

- no redesign of workspace-shared runtime memory semantics
- no new durable memory plane
- no operator command expansion in this slice
- no vector RAG work

### Files In Scope

- `src/mini_agent/interfaces/agent.py`
- `src/mini_agent/memory/memoria_runtime.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `src/mini_agent/tui/app.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `tests/test_tui_app.py`
- `tests/test_agent_studio_gateway_api_v1.py`

### Execution Steps

1. Add export/import helpers for session runtime-memory payloads.
2. Extend snapshot/import DTOs with a dedicated runtime-memory field.
3. Wire runtime manager export/import to that field.
4. Wire TUI share/unshare to preserve the payload and clean up old local namespace after successful migration.
5. Add focused tests for import/export/share/unshare parity.

### Acceptance Criteria

- exporting a shared session includes its session-scoped runtime task memory payload
- importing a session snapshot restores that runtime task memory into the destination session namespace
- local TUI share migrates session runtime task memory to gateway instead of leaving it only under the old local namespace
- TUI unshare restores runtime task memory back to the local workspace runtime store
- focused tests verify the parity behavior directly

### Status

- completed and verified
- verification:
  - `uv run python -m compileall src/mini_agent/interfaces/agent.py src/mini_agent/memory/memoria_runtime.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/application/main_agent_gateway_use_cases.py src/mini_agent/tui/app.py tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py -q`
- result: `181 passed`

## Current Execution Slice: P26 Workspace-Shared Runtime-Memory Portability

### Why This Slice Is Next

- `session:<session_id>` snapshot parity is now correct
- but `workspace:shared` still had no explicit snapshot/import/export contract
- leaving it implicit was acceptable only while all flows stayed on one machine and one state root
- the next clean step is to make workspace-shared runtime memory portable without letting one session snapshot overwrite workspace-owned shared state

### Scope

- extend session snapshot/import DTOs with an explicit workspace-shared runtime-memory payload
- add workspace-shared snapshot/restore helpers on `WorkspaceMemoriaRuntime`
- define restore semantics as non-destructive merge, not replace
- wire gateway export/import and TUI share/unshare through the same payload
- add focused regression coverage for merge-safe restore behavior

### Out Of Scope

- no session reset/delete change for `workspace:shared`
- no new durable memory plane
- no promotion-policy redesign in this slice
- no vector RAG work

### Files In Scope

- `src/mini_agent/interfaces/agent.py`
- `src/mini_agent/memory/memoria_runtime.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/tui/app.py`
- `tests/test_memoria_runtime.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `tests/test_tui_app.py`
- `tests/test_agent_studio_gateway_api_v1.py`
- `tests/test_interface_dto_contracts.py`

### Execution Steps

1. Add explicit DTO payload support for workspace-shared runtime memory.
2. Add workspace-shared snapshot/restore helpers to `WorkspaceMemoriaRuntime`.
3. Make restore semantics merge by content so imports do not clobber existing shared workspace facts.
4. Wire gateway import/export and TUI share/unshare through the new payload.
5. Add focused regression tests for merge-safe import/export/share/unshare behavior.

### Acceptance Criteria

- snapshot export includes `workspace_shared_runtime_memory_payload`
- import restores workspace-shared runtime memory without deleting existing target shared facts
- TUI share/unshare preserve workspace-shared runtime memory through the same snapshot contract
- session reset/delete still leaves `workspace:shared` untouched
- focused tests directly verify merge-safe restore semantics

### Status

- completed and verified
- verification:
  - `uv run python -m compileall src/mini_agent/interfaces/agent.py src/mini_agent/memory/memoria_runtime.py src/mini_agent/application/main_agent_gateway_use_cases.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/tui/app.py tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py -q`
- result: `186 passed`

## Current Execution Slice: P26 Workspace-Shared Boundary / Promotion Policy

### Why This Slice Is Next

- portability for `workspace:shared` is now correct
- but runtime still lacked an integrated strategy for:
  - when facts should remain `session:<id>`
  - when a fact is suitable for `workspace:shared`
  - how operators should promote such facts without silently duplicating task-local noise into workspace-shared memory

### Scope

- keep automatic writeback defaulting to `session:<id>`
- add one conservative `workspace:shared` candidate evaluation path on post-turn writeback
- surface candidate status through runtime diagnostics
- add explicit `/memory promote shared <selector>` control across local/shared surfaces
- prefer distilled candidate text when promoting into `workspace:shared`

### Out Of Scope

- no automatic promotion into `workspace:shared`
- no durable-memory auto-promotion changes
- no new memory plane
- no vector RAG work

### Files In Scope

- `src/mini_agent/memory/promotion.py`
- `src/mini_agent/memory/runtime_task_memory.py`
- `src/mini_agent/memory/memoria_runtime.py`
- `src/mini_agent/memory/diagnostics.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/cli_interactive.py`
- `src/mini_agent/tui/app.py`
- `src/apps/qqbot_channel/bot.mjs`
- `src/mini_agent/commands/catalog.json`
- `tests/test_memoria_runtime.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `tests/test_tui_app.py`
- `tests/test_cli_submission_loop.py`

### Execution Steps

1. Add one shared policy helper for evaluating `workspace:shared` candidates.
2. Annotate session runtime-memory writeback with candidate metadata instead of auto-promoting.
3. Make `promote_session_memory_to_workspace_shared(...)` use the distilled candidate text when available.
4. Add `/memory promote shared <selector>` across gateway, CLI, TUI, and QQ.
5. Add focused regression coverage for candidate detection and shared promotion behavior.

### Acceptance Criteria

- automatic runtime writeback still lands only in `session:<id>`
- diagnostics show whether the latest runtime writeback is a `workspace:shared` candidate
- `promote shared` works across local and shared surfaces
- shared promotion uses a distilled workspace-level conclusion instead of the raw `task: ... | latest: ...` envelope when possible
- `workspace:shared` remains explicit runtime state, not a silent second durable-memory write path

### Status

- completed and verified
- verification:
  - `uv run python -m compileall src/mini_agent/memory/promotion.py src/mini_agent/memory/runtime_task_memory.py src/mini_agent/memory/memoria_runtime.py src/mini_agent/memory/diagnostics.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/cli_interactive.py src/mini_agent/tui/app.py tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py -q`
  - `node --check src/apps/qqbot_channel/bot.mjs`
  - result: `206 passed`

## Current Execution Slice: P26 Workspace-Shared Retrieval Boundary

### Why This Slice Is Next

- promotion and portability semantics are now clear
- but retrieval still let `workspace:shared` participate too eagerly
- that risked letting workspace-shared facts compete with current task/session memory even when the query was clearly session-local

### Scope

- keep session runtime memory as the primary runtime retrieval source
- let `workspace:shared` participate only when:
  - the query itself carries workspace/shared/runtime scope signals, or
  - session hits are insufficient for the configured session budget
- expose the chosen shared-retrieval reason in prepared-context metadata

### Out Of Scope

- no change to writeback semantics
- no automatic durable-memory promotion
- no new memory plane

### Files In Scope

- `src/mini_agent/memory/promotion.py`
- `src/mini_agent/turn_context.py`
- `tests/test_memoria_runtime.py`
- `tests/test_agent_turn_context.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `tests/test_tui_app.py`
- `tests/test_cli_submission_loop.py`

### Execution Steps

1. Add a reusable workspace-scope signal helper.
2. Gate `workspace:shared` retrieval inside `RuntimeTaskMemoryTurnContextProvider`.
3. Record whether shared retrieval was used because of query scope, fallback, or suppression.
4. Add focused tests for suppression and fallback behavior.

### Acceptance Criteria

- session-local runtime memory remains primary when it already covers the current query
- `workspace:shared` still helps when the query is workspace-scoped or session hits are sparse
- prepared-context metadata explains why shared retrieval was or was not included

### Status

- completed and verified
- verification:
  - `uv run python -m compileall src/mini_agent/memory/promotion.py src/mini_agent/turn_context.py tests/test_memoria_runtime.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_agent_turn_context.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py -q`
  - result: `204 passed`

## Latest Sync: 2026-04-10 Workspace-Shared Operator Surface + Explicit KB Grounding Boundary

- [completed] `workspace:shared` now has an independent operator surface across gateway/TUI/CLI/QQ:
  - `/memory shared list`
  - `/memory shared show <selector>`
  - `/memory shared clear`
- [completed] explicit memory/RAG linkage now follows a stricter confirmation boundary:
  - KB-grounded turns now annotate runtime task memory with explicit grounding metadata
  - automatic workspace durable-note and daily-note writeback is suppressed for KB-grounded turns
  - explicit workspace durable-note promotion now uses `kb_confirmed` when the source runtime memory is KB-grounded
  - explicit `/memory save note ...` now surfaces KB grounding details when prepared KB context is present
- [completed] KB-grounding operator visibility is now aligned across gateway/TUI/CLI:
  - runtime-memory preview rendering now uses one shared diagnostics formatter instead of per-surface custom strings
  - KB-grounded preview items now show explicit badges plus compact `kb / hits / query / refs` operator lines
  - `shared show` now renders the same `Knowledge Base: grounded` detail block across local and remote memory surfaces
- [completed] session runtime-memory inspection is now operator-complete across gateway/TUI/CLI/QQ:
  - `memory show brief|full` still serves diagnostics
  - `memory show <selector>` now resolves and renders one concrete session runtime-memory entry
  - session and workspace-shared runtime-memory surfaces are now symmetric at the operator command layer
- [completed] durable memory is now browsable through the same `/memory` command family:
  - `memory profile [query]` exposes global profile browsing/search
  - `memory notes [query]` exposes workspace durable-note browsing/search
  - `memory daily <YYYY-MM-DD>` exposes workspace daily-memory inspection
  - gateway request contracts now carry explicit `query` / `day` fields for durable-memory actions
- [completed] consolidated memory is now inspectable through the same `/memory` command family:
  - `memory consolidated` / `memory consolidated show` exposes consolidated snapshot inspection
  - `memory consolidated search <query>` exposes ranked consolidated-memory lookup
  - consolidated-memory read surfaces now align across gateway/TUI/CLI/QQ without changing explicit refresh semantics
- Verification:
  - `uv run python -m compileall src/mini_agent/memory/diagnostics.py src/mini_agent/interfaces/agent.py src/mini_agent/application/main_agent_gateway_use_cases.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/cli_interactive.py src/mini_agent/tui/gateway_client.py src/mini_agent/tui/app.py tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py`
  - `uv run pytest tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py tests/test_memoria_runtime.py tests/test_memory_automation.py tests/test_interface_dto_contracts.py tests/test_agent_studio_gateway_api_v1.py tests/test_memory_service.py tests/test_memory_relevance.py -q`
  - `node --check src/apps/qqbot_channel/bot.mjs`
  - result: `242 passed`

## Latest Sync: 2026-04-10 Cross-Layer Memory Overview / Export

- [completed] `/memory` now has a human-facing cross-layer summary:
  - `memory overview` shows runtime task memory, durable memory, and consolidated memory in one operator-facing block
  - overview rendering reuses one shared diagnostics seam instead of per-surface summaries
- [completed] `/memory` now has an explicit export path:
  - `memory export [jsonl|markdown]` exports workspace durable notes directly from the main memory command family
  - gateway request contracts now carry explicit `export_format`
- [completed] the new overview/export surface is aligned across gateway, TUI, CLI, and QQ
- [completed] `memory overview` now also exposes session/workspace linkage explicitly:
  - `Session Context` shows `session id`
  - `workspace anchor`
  - session/shared runtime namespaces
  - prepared sources now sit under that same session/workspace context block
- Verification:
  - `uv run pytest tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py tests/test_interface_dto_contracts.py -q`
  - `node --check src/apps/qqbot_channel/bot.mjs`
  - result: `203 passed`
  - `uv run pytest tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py -q`
  - result: `190 passed`

## Latest Sync: 2026-04-10 KB Call-Decision + Memory Writeback Quality

- [completed] KB use remains explicit and now has stronger call-decision guidance instead of passive retrieval:
  - `knowledge_base` tool description now calls out README/spec/API/design/manual retrieval more directly
  - system prompt guidance now tells the agent to prefer KB first for document-grounded requests and to use concrete noun-heavy KB queries
- [completed] memory writeback quality is now stricter for low-signal operator chatter:
  - added shared low-signal filtering in `src/mini_agent/memory/quality.py`
  - durable auto-memory writeback skips low-signal control turns
  - runtime task-memory writeback skips the same low-signal control turns so transient session memory stays cleaner too
- [completed] real-use validation now has a dedicated integration test skeleton:
  - `tests/test_memory_real_use_flow.py` verifies workspace/session boundary behavior
  - the same test also verifies that KB-grounded facts still require explicit confirmation before promotion into durable memory
- Verification:
  - `uv run pytest tests/test_memory_automation.py tests/test_memoria_runtime.py tests/test_knowledge_base_tool.py tests/test_memory_real_use_flow.py -q`
  - result: `31 passed`
  - `uv run pytest tests/test_memory_service.py tests/test_memoria_runtime.py tests/test_agent_turn_context.py tests/test_memory_automation.py tests/test_session_search.py tests/test_knowledge_base_tool.py tests/test_main_agent_gateway_use_cases.py tests/test_memory_real_use_flow.py -q`
  - result: `103 passed`

## Latest Sync: 2026-04-12 Runtime-Policy + Session-Control Handler Extraction

- [completed] `MainAgentRuntimeManager` runtime-policy routing is now extracted into a dedicated handler:
  - added `src/mini_agent/runtime/session_runtime_policy_handler.py`
  - manager now delegates runtime-policy normalization, effective/current policy resolution, busy-session rejection, and local-session fallback diagnostics to that handler
- [completed] session-control routing is now extracted into a dedicated handler:
  - added `src/mini_agent/runtime/session_control_handler.py`
  - manager now delegates `compact` / `drop_memories` / `kb_on` / `kb_off` / `mcp_status` / `mcp_list` / `mcp_reload`
  - manager keeps only orchestration responsibilities: load session, acquire lock, append transcript entry, persist
- [completed] the runtime-policy regression surfaced a real test seam problem and was corrected without adding a compatibility shell:
  - shared-session detail read models rebuild sandbox diagnostics from the live agent, not only from `session.projection`
  - `_SelectableAgent` test doubles now expose minimal runtime-policy state so readback assertions match the real diagnostics path
- [completed] MCP inspection/reload monkeypatchability is preserved during the extraction:
  - handler dependencies are injected through manager-owned lambdas so existing monkeypatch-based tests still observe the runtime module seam
- Verification:
  - `uv run pytest tests/test_main_agent_gateway_use_cases.py -k "runtime_policy or control_session" -q`
  - result: `8 passed`
  - `uv run ruff check src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_runtime_policy_handler.py src/mini_agent/runtime/session_control_handler.py tests/test_main_agent_gateway_use_cases.py`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_runtime_policy_handler.py src/mini_agent/runtime/session_control_handler.py tests/test_main_agent_gateway_use_cases.py`
  - `uv run pytest tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py tests/test_session_service.py tests/test_p19_runtime_matrix.py -q`
  - result: `203 passed`
  - `uv run pytest tests/test_interaction_surface.py tests/test_channel_ingress_gateway_walkthrough.py tests/test_session_projection.py tests/test_shared_session_gateway_walkthrough.py -q`
  - result: `11 passed`

## Latest Sync: 2026-04-12 Context-Policy Handler Extraction

- [completed] shared-session prepared-context policy routing is now extracted into a dedicated handler:
  - added `src/mini_agent/runtime/session_context_policy_handler.py`
  - manager now delegates `include` / `exclude` / `budget` / `reset`
- [completed] the extracted handler now owns:
  - action normalization and validation
  - busy-session rejection
  - source-list normalization
  - budget coercion and minimum bounds
  - transcript command/summary/details rendering
  - response assembly for `MainAgentSessionContextResponse`
- [completed] `MainAgentRuntimeManager.update_session_context_policy(...)` now keeps only orchestration responsibilities:
  - load session
  - acquire runtime lock
  - append command transcript
  - persist session
  - return handler-built response
- [completed] regression coverage for the new seam is stronger than before:
  - existing include-policy persistence test still verifies next-turn propagation
  - added explicit `budget -> reset` coverage
  - added explicit busy-session rejection coverage
- Verification:
  - `uv run pytest tests/test_main_agent_gateway_use_cases.py -k "context_policy or update_session_context or context_update" -q`
  - result: `3 passed`
  - `uv run ruff check src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_context_policy_handler.py tests/test_main_agent_gateway_use_cases.py`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_context_policy_handler.py tests/test_main_agent_gateway_use_cases.py`
  - `uv run pytest tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py tests/test_session_service.py tests/test_p19_runtime_matrix.py -q`
  - result: `205 passed`
  - `uv run pytest tests/test_interaction_surface.py tests/test_channel_ingress_gateway_walkthrough.py tests/test_session_projection.py tests/test_shared_session_gateway_walkthrough.py -q`
  - result: `11 passed`

## Latest Sync: 2026-04-12 Interrupt Handler Extraction

- [completed] shared-session interrupt routing is now extracted into a dedicated handler:
  - added `src/mini_agent/runtime/session_interrupt_handler.py`
  - manager now delegates running-turn cancellation and pending-approval resolution
- [completed] the extracted interrupt handler now owns:
  - cancel-turn validation
  - cancel-event triggering
  - pending-approval waiter cancellation during `/cancel`
  - pending-approval token resolution
  - restart-recovery approval conflict messaging
  - approval transcript command/summary/details rendering
  - approval response assembly and waiter finalization hook
- [completed] `MainAgentRuntimeManager` now keeps only outer orchestration for cancel/approval commands:
  - load active managed session
  - distinguish missing session vs persisted-but-not-resumable session
  - append command transcript
  - persist session
  - return handler-built response
- Verification:
  - `uv run pytest tests/test_main_agent_gateway_use_cases.py -k "cancel_session or approval or pending_approval" -q`
  - result: `3 passed`
  - `uv run ruff check src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_interrupt_handler.py tests/test_main_agent_gateway_use_cases.py`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_interrupt_handler.py tests/test_main_agent_gateway_use_cases.py`
  - `uv run pytest tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py tests/test_session_service.py tests/test_p19_runtime_matrix.py -q`
  - result: `205 passed`
  - `uv run pytest tests/test_interaction_surface.py tests/test_channel_ingress_gateway_walkthrough.py tests/test_session_projection.py tests/test_shared_session_gateway_walkthrough.py -q`
  - result: `11 passed`

## Latest Sync: 2026-04-12 Snapshot Handler Extraction

- [completed] runtime snapshot import/export coordination is now extracted into a dedicated handler:
  - added `src/mini_agent/runtime/session_snapshot_handler.py`
  - manager now delegates snapshot import gatekeeping and snapshot export source resolution
- [completed] the extracted snapshot handler now owns:
  - imported snapshot `session_id` collision checks
  - imported snapshot auto-id allocation handoff
  - snapshot hydration payload construction
  - export-time selection between live managed session and persisted record
  - consistent `404` handling for missing snapshot exports
- [completed] `MainAgentRuntimeManager` import/export methods now keep only orchestration responsibilities:
  - acquire store lock
  - prepare import environment / persistence lookups through injected closures
  - hydrate imported payload into a live session
  - return handler-selected live or persisted snapshot export
- [completed] regression coverage for the new seam is explicit:
  - duplicate imported `session_id` now has a dedicated test
  - persisted-record export path now has a dedicated test
  - existing runtime-task-memory and workspace-shared-memory export tests still validate live export payloads
- Verification:
  - `uv run pytest tests/test_main_agent_gateway_use_cases.py -k "import_session_snapshot or export_session or persisted_export" -q`
  - result: `3 passed`
  - `uv run ruff check src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_snapshot_handler.py tests/test_main_agent_gateway_use_cases.py`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_snapshot_handler.py tests/test_main_agent_gateway_use_cases.py`
  - `uv run pytest tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py tests/test_session_service.py tests/test_p19_runtime_matrix.py -q`
  - result: `207 passed`
  - `uv run pytest tests/test_interaction_surface.py tests/test_channel_ingress_gateway_walkthrough.py tests/test_session_projection.py tests/test_shared_session_gateway_walkthrough.py -q`
  - result: `11 passed`

## Latest Sync: 2026-04-12 Restore / Hydrate Handler Extraction

- [completed] persisted-record restore and payload hydration coordination is now extracted into a dedicated handler:
  - added `src/mini_agent/runtime/session_restore_handler.py`
  - manager now delegates both `record -> hydration payload` preparation and `payload -> live session state` hydration
- [completed] the extracted restore handler now owns:
  - persisted transcript import handoff
  - stored recovery snapshot handoff
  - record-hydration payload construction
  - agent rebuild for selected model identity
  - runtime-policy reconfigure attempt during restore
  - agent message/token restoration
  - effective KB-enabled state resolution
  - lifecycle bootstrap for restored sessions
  - session-state construction + stored-recovery application
  - runtime-state hydration and selected-model fallback identity
- [completed] `MainAgentRuntimeManager` now keeps only the outer restore/hydrate orchestration:
  - resolve `now_utc`
  - check in-memory existing session
  - register newly hydrated sessions into `_sessions`
  - decide whether imported sessions should persist immediately
- [completed] focused validation reuses real recovery flows rather than synthetic seams:
  - interrupted persisted session recovery after restart
  - restarted shared session recovery context consumption
  - runtime restart survival
  - latest persisted shared-session restore
  - snapshot import/export still green
- Verification:
  - `uv run pytest tests/test_main_agent_gateway_use_cases.py -k "persisted_interrupted_session or restarted_shared_session or survives_runtime_restart or restores_latest_persisted_shared_session or import_session_snapshot or export_session or persisted_export" -q`
  - result: `7 passed`
  - `uv run ruff check src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_restore_handler.py tests/test_main_agent_gateway_use_cases.py`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_restore_handler.py tests/test_main_agent_gateway_use_cases.py`
  - `uv run pytest tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py tests/test_session_service.py tests/test_p19_runtime_matrix.py -q`
  - result: `207 passed`
  - `uv run pytest tests/test_interaction_surface.py tests/test_channel_ingress_gateway_walkthrough.py tests/test_session_projection.py tests/test_shared_session_gateway_walkthrough.py -q`
  - result: `11 passed`

## Latest Sync: 2026-04-12 Session-Access Handler Extraction

- [completed] `get_or_create_session(...)` branch selection is now extracted into a dedicated handler:
  - added `src/mini_agent/runtime/session_access_handler.py`
  - manager now delegates selection among:
    - active in-memory session reuse by explicit `session_id`
    - team-mode same-workspace active-session reuse without `session_id`
    - persisted-session restore by explicit `session_id`
    - latest persisted same-workspace session restore without `session_id`
    - new session creation
- [completed] the extracted handler now owns:
  - request normalization for surface/channel/conversation/sender/title-hint inputs
  - workspace-mismatch routing for active and persisted candidates
  - team-mode capacity enforcement at the create-new boundary
  - carry-forward flags such as `apply_title_hint_if_missing` for restored sessions
- [completed] `MainAgentRuntimeManager.get_or_create_session(...)` now keeps only orchestration responsibilities:
  - call handler to choose path
  - refresh/touch/persist reused sessions
  - call restore path for persisted sessions
  - instantiate a brand-new session only when the handler says `create_new`
- [completed] focused validation covers the branchy parts directly:
  - human-readable title hints
  - title-hint application on new shared sessions
  - latest persisted shared-session restore
  - team-mode reuse and capacity guardrails
  - single-main workspace guardrail
- [completed] minor repo hygiene:
  - removed unused `asyncio` import from `tests/test_p19_runtime_matrix.py` so lint can include that file cleanly
- Verification:
  - `uv run pytest tests/test_main_agent_gateway_use_cases.py -k "assigns_human_readable_session_title_hints or chat_applies_session_title_hint_on_new_shared_session or restores_latest_persisted_shared_session or team_mode or single_main_workspace_only or max_active_sessions or survives_runtime_restart or get_or_create_session" -q`
  - result: `9 passed`
  - `uv run ruff check src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_access_handler.py tests/test_main_agent_gateway_use_cases.py tests/test_p19_runtime_matrix.py`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_access_handler.py tests/test_main_agent_gateway_use_cases.py tests/test_p19_runtime_matrix.py`
  - `uv run pytest tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py tests/test_session_service.py tests/test_p19_runtime_matrix.py -q`
  - result: `207 passed`
  - `uv run pytest tests/test_interaction_surface.py tests/test_channel_ingress_gateway_walkthrough.py tests/test_session_projection.py tests/test_shared_session_gateway_walkthrough.py -q`
  - result: `11 passed`
