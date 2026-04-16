# P30 Surface / Session Refactor Task Plan

> Status: Active
> Date: 2026-04-12
> Basis:
> - `docs/P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md`
> - `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`
> - `docs/P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`
> Goal: execute the corrected session-centric architecture without letting any user entrance regain ownership of session truth
> Update 2026-04-14 (`P32.60`): the active repo now carries only the QQ remote adapter path. References to `WeChat / Feishu` in this plan are future-contract notes, not active implementation targets.

## 1. Core Execution Rule

All refactor work in this track must preserve one invariant:

- `Session` is the single source of truth
- `CLI`, `TUI`, `DesktopUI`, and `Remote Interaction` only operate on that truth
- the active concrete remote adapter is `QQ`; future adapters, if approved later, still belong under the remote entrance rather than beside it
- entrance and channel caches may exist, but they must never become domain truth

## 2. Target Outcome

After P30:

- the four-entrance product model is explicit and stable
- session ownership is fully detached from entrances
- TUI is reduced to visual/operator state plus references to runtime/session projections
- remote channels keep only conversation binding and delivery state
- the canonical DesktopUI direction is explicit
- runtime/application/transport boundaries are easier to evolve without reintroducing multi-owner session bugs

## 3. Phase Plan

## Phase P30.1: Four-Entrance Boundary Lock

### Objective

Make the entrance model explicit so implementation stops drifting between product entrances and concrete adapters.

### Tasks

- define the canonical four-entrance model:
  - `CLI`
  - `TUI`
  - `DesktopUI`
  - `Remote Interaction`
- define the remote channel adapter sub-layer:
  - active: `QQ`
  - future only after explicit reactivation: other remote adapters
- define what is not an entrance:
  - `headless`
  - `gateway`
  - concrete adapter runtimes
- map current modules into:
  - entrance
  - remote adapter
  - interface / transport
  - application
  - runtime
  - core capability

### Primary Files

- `docs/ARCHITECTURE.md`
- `docs/P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`
- `docs/DEVELOPMENT_INDEX.md`
- `task_plan.md`

### Acceptance

- active docs no longer flatten `QQ` into the product entrance list
- the remote entrance and its adapter sub-layer are documented explicitly
- `headless` is documented as runtime mode rather than user entrance

## Phase P30.2: Session Truth Boundary Lock

### Objective

Identify and eliminate the remaining places where entrance-local structures behave like session ownership.

### Tasks

- audit every field on `TuiSession` and classify it as:
  - session projection
  - runtime handle
  - view-only state
- audit remote-channel session caches and classify them as:
  - conversation binding
  - delivery cache
  - accidental domain state
- define a strict contract for what an entrance or channel adapter is allowed to cache

### Primary Files

- `docs/P30_SESSION_TRUTH_BOUNDARY_MAP_2026-04-13.md`
- `src/mini_agent/tui/app.py`
- `src/apps/qqbot_channel/bot.mjs`
- `src/mini_agent/application/session_service.py`
- `src/mini_agent/application/channel_ingress_use_cases.py`
- `src/mini_agent/session/projection.py`

### Acceptance

- one written mapping exists for TUI and remote-channel state ownership
- no ambiguous field remains undocumented
- the next implementation cuts can delete or move fields without rediscovering ownership rules

### Status Note

- ownership mapping landed in `docs/P30_SESSION_TRUTH_BOUNDARY_MAP_2026-04-13.md`
- this phase now acts as the frozen input for `P30.3` and `P30.4`
- the global default-session rule is now part of the frozen boundary too:
  - sessions are not owned by `CLI` / `TUI` / `DesktopUI` / remote adapters
  - `session_id` resolution now follows:
    - explicit session id
    - entrance-local remembered previous session id
    - runtime-owned global default session
  - the default session lives at the main workspace and is recreated on demand
  - entrance-side fallback code must not invent a new local `Session 1`

## Phase P30.3: TUI Session Model Split

### Objective

Turn `TuiSession` into a composition of:

- session projection/cache
- runtime handle bundle
- TUI-only view state

### Tasks

- split `TuiSession` fields into separate dataclasses or equivalent narrow structs
- remove duplicated session-truth fields from TUI-only state where possible
- make local/remote session rendering consume shared session projections consistently
- ensure model, pending approval, recovery, and share state remain projection-driven

### Primary Files

- `src/mini_agent/tui/app.py`
- `src/mini_agent/session/projection.py`
- `src/mini_agent/application/session_remote_service.py`
- `tests/test_tui_app.py`
- `tests/test_session_projection.py`

### Acceptance

- TUI no longer mixes domain truth, runtime handles, and view state in one wide struct
- session switching, share state, and recovery rendering still work
- no TUI-only field is treated as canonical session truth

### Status Note

- the projection/runtime/view split already existed in live code
- the latest tightening slice moved remote sync/recovery summary fields into:
  - `TuiSessionSupplementalState`
- the current tightening slice moved TUI-local pending model / skill-reload state into:
  - `TuiSessionOperatorState`
- `P30.3` is therefore now in the "narrow and enforce the split" stage rather than the "invent the split" stage

## Phase P30.4: Remote Channel Adapter Normalization

### Objective

Reduce remote-adapter state to channel binding plus delivery/runtime convenience only, and lock the active QQ adapter to the same remote entrance contract.

### Tasks

- replace implicit channel-side session ownership assumptions with explicit binding semantics
- ensure channel state stores only:
  - conversation key
  - resolved session id
  - reply and follow preferences
  - channel display metadata
- move any business logic that mutates session truth back through application services
- define one target adapter contract that any future remote adapter must follow
- keep QQ on the thin-adapter path without keeping dormant non-QQ adapter code in the active tree

### Primary Files

- `src/apps/qqbot_channel/bot.mjs`
- `src/mini_agent/application/channel_ingress_use_cases.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `tests/test_channel_ingress_gateway_walkthrough.py`
- `tests/test_shared_session_gateway_walkthrough.py`

### Acceptance

- remote channels no longer behave like parallel session systems
- conversation-to-session binding is explicit and bounded
- session truth remains fully centralized
- channel additions do not require copying TUI logic

### Status Note

- active QQ shared-session mutation calls have now been thinned further through adapter-local helpers only
- QQ command dispatch now also declares shared-session-scoped commands explicitly instead of relying on repeated per-handler guards
- QQ dispatch metadata now also carries runtime-policy and simple control-command meaning, so `/plan`-style and `/compact`-style handlers no longer infer behavior from command names
- shared model-selection now infers a missing `provider_source` when the provider/model pair is uniquely resolvable, so QQ `/model use` no longer scans the catalog to route model selection
- QQ `/approve` and `/deny` no longer inspect pending approvals locally before routing; approval token selection and restart-loss conflicts now stay owned by the shared runtime approval path
- QQ `/mcp` remains a thin subcommand router, but busy/error wording now reuses the shared control path instead of keeping a QQ-local reload conflict branch
- QQ `/skill` now acts more like a thin payload router and less like an action-by-action skill command executor
- QQ `/memory` and `/context` update paths have also been reduced toward payload translation plus shared-runtime validation, with only local read-only context rendering kept in the adapter
- the remaining QQ logic is now mainly binding hints, local display formatting, and remote protocol handling; `P30.4` is ready to close from an architecture-boundary perspective
- non-QQ adapter trees were later removed from the active repo in `P32.60` so this contract stays locked in one physical path

## Phase P30.5: Shared Entrance Operation Convergence

### Objective

Keep reusing shared command/application semantics so entrance divergence stays in rendering and protocol only.

### Tasks

- continue moving entrance-owned operator behavior into shared execution/services where still duplicated
- align remote-channel command behavior with the same shared semantics where practical
- prevent new entrance-specific business logic from being added ad hoc
  - define a clean service seam usable by:
  - CLI
  - TUI
  - DesktopUI
  - remote adapters

### Primary Files

- `src/mini_agent/commands/*`
- `src/mini_agent/application/*`
- `src/mini_agent/tui/*`
- `src/mini_agent/cli_interactive.py`
- `src/apps/qqbot_channel/bot.mjs`

### Acceptance

- new entrance work mostly composes existing application/service seams
- command semantics are shared by default
- future remote-channel additions do not fork business rules

### Status Note

- `P30.5` has now started with an explicit convergence audit instead of jumping straight into another adapter refactor
- TUI `/memory` command flow now resolves into a structured command plan before execution, reducing surface-owned branching
- TUI `/model` command flow now follows the same pattern for catalog/use/filter/limit handling, keeping execution thinner and more testable
- shared `ModelCommandPlan` parsing now also lives in `src/mini_agent/commands/execution.py`
- CLI `/model` no longer keeps its own handwritten `show/list/use` branch and now resolves through the shared model-plan seam
- TUI `/model` now wraps that same shared model-plan helper for `list/use` plus its extended local model actions
- shared `ContextCommandPlan` parsing now also lives in `src/mini_agent/commands/execution.py`
- CLI `/context` no longer normalizes `brief/full` aliases inline and now resolves through the shared context-plan seam
- TUI `/context` now wraps that same shared context-plan helper for action normalization plus refresh/mutation flags
- the remaining `TUI`-local plan objects were audited after those cuts and are currently keep decisions rather than pending extractions:
  - `SessionCommandPlan`
  - `KbCommandPlan`
  - `McpCommandPlan`
  - `SkillCommandPlan`
  - `RemoteSkillCommandPlan`
- the remaining inline `CLI` `workflow` branch was also audited and is a keep decision because it is entrance-specific orchestration rather than shared command semantics
- TUI `/session` command flow now uses the same parse-then-execute shape for select/create/share/rename/delete paths, shrinking one more large entrance-owned branch
- TUI `/mcp` command flow now also resolves through a small command-plan seam, so action validation and usage handling stop living inline with local/remote execution branches
- TUI `/kb` command flow now also resolves through a small command-plan seam, so KB action validation and remote/local split stop living inline inside one handler
- TUI `/context` command flow now also resolves through a command-plan seam, which removes repeated local validation/render calls and isolates policy-mutation routing from display rendering
- TUI `/skill` command flow now also resolves through a shared skill-request seam, so local and remote handling no longer maintain separate action/usage parsing rules
- shared `/memory` command planning now also lives in `src/mini_agent/commands/execution.py` as a reusable `MemoryCommandPlan` seam
- CLI `/memory` no longer keeps its long action-by-action branch; it now consumes the same shared planning layer that `TUI` uses
- TUI `/memory` now wraps the shared planning helper instead of owning a second surface-local parser shell
- the audit confirmed that the shared command base already exists in:
  - `src/mini_agent/commands/router.py`
  - `src/mini_agent/commands/execution.py`
- `CLI` is partially converged already and is not the highest-risk entrance right now
- `QQ` is also no longer the primary hotspot after `P30.4`
- the main remaining drift risk is `TUI`, especially the remote-session command path that still behaves like a second command execution shell for:
  - approval
  - context control
  - context
  - memory
  - MCP
  - skill
  - model
- the first implementation cuts under `P30.5` should therefore start in `TUI`, not in `QQ`
- the preferred cut order is:
  - first: remote `skill` convergence
  - second: remote approval convergence
  - third: remote MCP/context-control convergence
- the first implementation cut has now landed:
  - remote `TUI` `skill` handling no longer uses one long action-by-action branch tree
  - parse/usage/result mapping are now centralized in narrower helpers
  - remote `uninstall` / `rollback` now also participate in the same mutation-sync path as the other remote skill mutations
- the second implementation cut has now landed too:
  - remote `TUI` approval no longer resolves pending-token behavior locally
  - restart-loss and multi-token approval conflicts now come from the shared gateway/runtime approval path
  - the fake gateway tests were updated so the test contract matches the shared approval semantics instead of the old TUI precheck behavior
- the third implementation cut has now landed:
  - remote `compact` / `drop_memories` / `mcp reload` no longer keep local busy-conflict gates in `TUI`
- the fifth implementation cut has now landed:
  - remote `context` updates no longer rebuild request structure from raw `args` inside `TUI`
  - shared command execution now exposes structured remote context-update intent directly
- the sixth implementation cut has now landed:
  - read-heavy remote `memory` actions now share one execution/render helper in `TUI`
  - the duplicated read-path command shell in `memory` is materially smaller
- the seventh implementation cut has now landed:
  - remote `memory promote` / `memory save` now also reuse the shared `TUI` memory execution helper
  - fake gateway memory mutation behavior now models transcript/result shapes more truthfully for regression coverage
  - broader regression also surfaced and fixed missing remote approval binding metadata forwarding in `TUI`
  - `TUI` no longer keeps a separate thick remote memory mutation shell
- the eighth implementation cut has now landed:
  - terminal `/model use` catalog validation is now shared between `TUI` and `CLI`
  - duplicated provider/model resolution logic was removed from both entrances in favor of one shared helper
  - runtime/gateway still own the actual model-selection application path
  - shared gateway/runtime control handling now owns those remote busy conflicts
  - remote control failure rendering now reuses shared gateway detail instead of a `Remote ... failed: Gateway HTTP ...` wording fork
- the fourth implementation cut has now landed:
  - remote `mcp` and remote context-control now share one remote control dispatch helper in `TUI`
  - remote context-control now forwards the same binding metadata style as the other remote control commands
  - request assembly, gateway error handling, and post-control sync are less duplicated at the surface layer
- the fifth implementation cut has now landed:
  - shared `execute_context(...)` now emits structured remote-update request data
  - remote `TUI` context updates now consume that structured request instead of re-parsing raw args
  - remote context binding metadata is now aligned with the rest of the remote request paths
- the sixth implementation cut has now landed:
  - `TUI` memory now has one shared execution/render helper for read-heavy command paths
  - the repeated result-unpack and feedback/status shell for many memory actions is materially smaller
  - the remaining memory hotspot is now more clearly concentrated in the mutation-heavy actions such as `promote` and `save`
- the next small convergence cut has now landed too:
  - shared interaction binding normalization now has one reusable seam in `src/mini_agent/interaction/surface.py`
  - chat bindings, shared-session application bindings, and the TUI gateway client now reuse the same alias/trim/default handling
  - remote aliases such as `qqbot` no longer survive in one request path while other paths already normalized them to `qq`
  - empty shared-session mutation requests still preserve the existing "no fake surface" behavior instead of being forced to `"api"`
- one more TUI command-convergence cut has now landed:
  - `memory` command handling in `TUI` now resolves to a structured `MemoryCommandPlan` before execution
  - usage/unknown-action/busy-guard behavior is centralized instead of being scattered across long per-action branches
  - the actual execution path continues to funnel through the shared `_execute_memory_command_plan(...)` helper
- one more follow-up correctness cut has now landed:
  - `SessionSurfaceBinding.from_request(...)` no longer pre-fills `default_surface` before shared resolution
  - remote requests with no explicit `surface` but with `channel_type=qq*` now resolve as remote `qq` instead of being accidentally forced to `tui`
  - this specifically tightens derived-session and other request paths that rely on `from_request(..., default_surface=\"tui\")`
- one more deeper runtime convergence cut has now landed after that:
  - runtime live-state mutation now also reuses the shared interaction-binding seam before writing projection or transcript state
  - remote alias + missing-surface cases therefore stay aligned not only at request entry, but also at the session-truth write path
  - the shared remote conversation binding service and gateway execution metadata shaping were tightened in the same pass so `qqbot` / `qq` semantics stay consistent one layer deeper too
- one final small guardrail cut has now landed on the same line:
  - `resolve_interaction_surface(...)` itself now resolves `surface=None + remote channel_type` to the concrete remote surface
  - current production code no longer depends on that old edge case, but the helper is now safer for any future direct caller too
- current recommendation after this sequence:
  - treat `P30.5` as near-closed unless a fresh shared-entrance drift appears
  - do not keep extracting or converging by inertia just because the current track is active
  - do not promote `WeChat` into the active implementation plan: current remote delivery remains `QQ` only
  - keep `WeChat / Feishu` as future extension targets under the same remote-entrance contract, but not as current execution slices

## Phase P30.6: Browser Surface Retirement

### Objective

Remove browser-surface ambiguity entirely so future work cannot drift back into WebUI/OpenWebUI revival.

### Tasks

- delete browser `agent_studio` assets from the active codebase
- delete `open_webui` compatibility/integration adapters from the active codebase
- remove browser static hosting from the gateway host
- rewrite active docs so the canonical entrance model is `CLI / TUI / DesktopUI / Remote Interaction`

### Primary Files

- `src/apps/agent_studio_gateway/*`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_INDEX.md`

### Acceptance

- browser `WebUI / OpenWebUI` no longer exist as active product paths
- browser compatibility adapters are no longer mistaken for product entrances
- future surface work targets `DesktopUI` instead of browser revival

## Phase P30.7: Runtime Manager Decomposition Continuation

### Objective

Continue shrinking `MainAgentRuntimeManager` so it stops acting as a mixed repository/service/executor/presenter.

### Tasks

- extract session record/persistence responsibilities
- extract transcript/activity recording responsibilities
- extract operator action helpers that do not belong in the runtime core
- keep runtime manager focused on lifecycle/execution coordination

### Primary Files

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/session/persistence.py`
- `src/mini_agent/session/projection.py`
- `src/mini_agent/application/session_service.py`
- related test files under `tests/test_session_*`

### Acceptance

- `MainAgentRuntimeManager` shrinks materially
- persistence/projection/operator formatting concerns move out to narrower modules
- runtime execution paths become easier to reason about

### Status Note

- the next `P30.7` continuation slice has now landed:
  - the gateway-managed runtime persistence wrapper was extracted from `main_agent_runtime_manager.py`
  - it now lives in `src/mini_agent/runtime/session_runtime_persistence.py` as `MainAgentRuntimePersistence`
  - save/load/delete semantics and shared transcript sidecars stayed unchanged through the move
- the follow-up `P30.7` slice has now landed too:
  - the shared runtime session-state dataclasses were extracted into `src/mini_agent/runtime/session_state.py`
  - runtime/application collaborators now import `MainAgentSession*` types from that shared state module instead of from the runtime manager
- the remaining `P30.7` cuts should now be driven by true behavior hotspots rather than by file-top residue alone
- the latest hotspot audit narrowed the next likely targets further:
  - `update_session_model_selection(...)` still owns provider-source inference before delegation
  - `create_derived_session(...)` still owns inherited snapshot payload assembly inline
  - lineage graph registration/removal still lives directly in the manager
- one smaller registry consistency issue was also identified:
  - `RuntimeSessionRegistryHandler.create_session(...)` still bypasses the runtime session-id allocator and generates `uuid4().hex` directly
- the first post-audit cut has now landed:
  - model-selection request resolution, including missing-`provider_source` inference, moved into `RuntimeSessionModelSelectionHandler`
  - `MainAgentRuntimeManager.update_session_model_selection(...)` is now thinner and no longer interprets model-selection request semantics locally
- the second post-audit cut has now landed:
  - `create_derived_session(...)` no longer assembles inherited child-session payload state inline in the manager
  - derived-session creation now routes through session registry + hydration code
  - direct `create_session(...)` now also reuses the runtime session-id allocator
- the third post-audit cut has now landed:
  - lineage graph registration/removal rules moved into a dedicated runtime lineage helper
  - the existing `_session_lineage` observation seam was preserved for tests/debugging
- the follow-up re-audit has now landed:
  - `main_agent_runtime_manager.py` is down to `1447` lines in the current worktree
  - the largest remaining methods are staged composition wiring, not major mixed-responsibility behavior
  - parameter-heavy operator entrypoints now read as acceptable thin facades
  - a few dead residual helper shells were removed during the audit
- current recommendation:
  - treat `P30.7` as naturally paused/near-closed for now
  - only reopen runtime-manager decomposition when a fresh behavior hotspot appears

## 4. Recommended Execution Order

1. `P30.1 Four-Entrance Boundary Lock`
2. `P30.2 Session Truth Boundary Lock`
3. `P30.3 TUI Session Model Split`
4. `P30.4 Remote Channel Adapter Normalization`
5. `P30.5 Shared Entrance Operation Convergence`
6. `P30.6 Browser Surface Retirement`
7. `P30.7 Runtime Manager Decomposition Continuation`

## 5. Guardrails

During P30 execution:

- do not introduce new entrance-owned session fields without classifying them
- do not let remote-channel code mutate session truth directly
- do not let Web/UI contracts bypass application services
- do not expand runtime-manager scope while trying to refactor it
- do not collapse the four-entrance product model back into concrete adapters

## 6. Immediate Next Cut

The most useful next implementation slice is:

- continue `P30.5 Shared Entrance Operation Convergence` in `TUI`
- next continue through any remaining remote command families that still keep thick per-action orchestration, with memory mutations now the clearest remaining hotspot
- then move to the next still-thick TUI remote command families if needed

because `P30.1` and `P30.2` are already locked, `P30.3` and `P30.4` are materially tightened already, and the next risk is semantic drift:

- `TUI` remote control/orchestration paths drifting into a second execution layer
- future entrances reusing `TUI` behavior instead of reusing shared command/application semantics
