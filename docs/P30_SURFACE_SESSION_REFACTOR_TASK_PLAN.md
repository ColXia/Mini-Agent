# P30 Surface / Session Refactor Task Plan

> Status: Active
> Date: 2026-04-12
> Basis:
> - `docs/P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md`
> - `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`
> - `docs/P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`
> Goal: execute the corrected session-centric architecture without letting any user surface regain ownership of session truth

## 1. Core Execution Rule

All refactor work in this track must preserve one invariant:

- `Session` is the single source of truth
- `CLI`, `TUI`, `WebUI`, and `QQ` only operate on that truth
- channel and UI caches may exist, but they must never become domain truth

## 2. Target Outcome

After P30:

- session ownership is fully detached from surfaces
- TUI is reduced to visual/operator state plus references to runtime/session projections
- QQ keeps only conversation binding and delivery state
- the canonical WebUI direction is explicit
- runtime/application/transport boundaries are easier to evolve without reintroducing multi-owner session bugs

## 3. Phase Plan

## Phase P30.1: Session Truth Boundary Lock

### Objective

Identify and eliminate the remaining places where surface-local structures behave like session ownership.

### Tasks

- audit every field on `TuiSession` and classify it as:
  - session projection
  - runtime handle
  - view-only state
- audit QQ bot session cache and classify it as:
  - conversation binding
  - delivery cache
  - accidental domain state
- define a strict contract for what a surface is allowed to cache

### Primary Files

- `src/mini_agent/tui/app.py`
- `src/apps/qqbot_channel/bot.mjs`
- `src/mini_agent/application/session_service.py`
- `src/mini_agent/application/channel_ingress_use_cases.py`
- `src/mini_agent/session/projection.py`

### Acceptance

- one written mapping exists for TUI and QQ state ownership
- no ambiguous field remains undocumented
- the next implementation cuts can delete or move fields without rediscovering ownership rules

## Phase P30.2: TUI Session Model Split

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

## Phase P30.3: QQ / Channel Binding Normalization

### Objective

Reduce QQ state to channel binding plus delivery/runtime convenience only.

### Tasks

- replace implicit QQ-side session ownership assumptions with explicit binding semantics
- ensure channel state stores:
  - conversation key
  - resolved session id
  - reply/follow preferences
  - channel display metadata
- move any business logic that mutates session truth back through application services
- align QQ command routing with shared command/application semantics where feasible

### Primary Files

- `src/apps/qqbot_channel/bot.mjs`
- `src/mini_agent/application/channel_ingress_use_cases.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `tests/test_channel_ingress_gateway_walkthrough.py`
- `tests/test_shared_session_gateway_walkthrough.py`

### Acceptance

- QQ no longer behaves like a parallel session system
- conversation-to-session binding is explicit and bounded
- session truth remains fully centralized

## Phase P30.4: Runtime Manager Decomposition Continuation

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

## Phase P30.5: Canonical WebUI Path Clarification

### Objective

Stop the Web direction from drifting between operator web, customer web, and compatibility adapters.

### Tasks

- define whether `agent_studio` is:
  - operator WebUI
  - transitional WebUI
  - or the canonical browser surface
- define `open_webui` strictly as:
  - compatibility adapter
  - optional integration path
  - not the product WebUI
- document which browser surface should continue after terminal-first delivery

### Primary Files

- `src/apps/agent_studio/*`
- `src/apps/agent_studio_gateway/*`
- `src/apps/open_webui/*`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_INDEX.md`

### Acceptance

- one canonical WebUI direction is explicitly named
- compatibility adapters are no longer mistaken for product surfaces
- future browser work has a single target

## Phase P30.6: Shared Surface Operation Convergence

### Objective

Keep reusing shared command/application semantics so surface divergence stays in rendering and protocol only.

### Tasks

- continue moving surface-owned operator behavior into shared execution/services where still duplicated
- align channel-side command behavior with the same shared semantics where practical
- prevent new surface-specific business logic from being added ad hoc

### Primary Files

- `src/mini_agent/commands/*`
- `src/mini_agent/application/*`
- `src/mini_agent/tui/*`
- `src/mini_agent/cli_interactive.py`
- `src/apps/qqbot_channel/bot.mjs`

### Acceptance

- new surface work mostly composes existing application/service seams
- command semantics are shared by default
- future channel additions do not require copying TUI logic

## 4. Recommended Execution Order

1. `P30.1 Session Truth Boundary Lock`
2. `P30.2 TUI Session Model Split`
3. `P30.3 QQ / Channel Binding Normalization`
4. `P30.4 Runtime Manager Decomposition Continuation`
5. `P30.5 Canonical WebUI Path Clarification`
6. `P30.6 Shared Surface Operation Convergence`

## 5. Guardrails

During P30 execution:

- do not introduce new surface-owned session fields without classifying them
- do not let QQ/channel code mutate session truth directly
- do not let Web/UI contracts bypass application services
- do not expand runtime-manager scope while trying to refactor it

## 6. Immediate Next Cut

The most useful next implementation slice is:

- `P30.1 Session Truth Boundary Lock`

because it provides the ownership map required to safely execute all later cuts without repeating the earlier session-unification mistakes.
