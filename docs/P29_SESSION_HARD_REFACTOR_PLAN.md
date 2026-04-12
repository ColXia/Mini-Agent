# P29 Session Boundary Hard-Refactor Plan

> Status: Active
> Date: 2026-04-12
> Basis: `docs/P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md`
> Goal: repair session ownership, command ownership, and surface/runtime boundaries without introducing a compatibility shell

## 1. Goal

Turn the current session stack into a clean, layered architecture with:

- one canonical session domain model
- one shared session application service
- thin surfaces for TUI / CLI / gateway / QQ
- a smaller, focused runtime core
- explicit projections for persistence, transport, and UI

This is not a UI polish slice and not a feature-expansion slice.
It is a structural repair slice required before more session-facing features continue.

## 2. Hard Constraints

- No compatibility shell unless a direct cut is genuinely impossible.
- Do not add new session behavior on top of the current mixed model.
- Prefer deletion / replacement over keeping parallel abstractions alive.
- Keep TUI/CLI as primary operator surfaces.
- WebUI remains paused.
- Keep real runtime behavior testable through focused regression, not only document intent.

## 3. Non-Goals

- No new major feature delivery during the first P29 slices.
- No new remote channel type expansion.
- No redesign of agent-core, memory, or tools beyond what is necessary to restore clean boundaries.
- No UI redesign as a primary objective.

## 4. Target Boundary Model

### 4.1 Canonical session domain

Owns:

- session identity
- workspace binding
- source/origin metadata
- active surface metadata
- share policy
- lifecycle state
- runtime policy
- model selection state
- approval queue
- recovery state
- transcript metadata

Does not own:

- TUI scroll state
- prompt-toolkit panel state
- local loop objects
- HTTP DTO formatting
- human-readable response prose

### 4.2 Session application service

Owns:

- create / load / select / rename / share / unshare / reset / delete
- submit / cancel / resume turn
- update model / policy / context
- operator actions
  - memory
  - skill
  - MCP
  - KB
- surface-safe projections for TUI / gateway / QQ / CLI

Does not own:

- prompt-toolkit rendering
- FastAPI routing
- QQ SDK event handling

### 4.3 Runtime executor layer

Owns:

- local agent runtime construction
- submission loop lifecycle
- turn execution
- cancellation / approval waiters
- runtime diagnostics gathering

Does not own:

- command parsing
- response formatting
- UI state

### 4.4 Surface adapters

TUI / CLI / gateway / QQ each become adapters that:

- parse local input/events
- call the session application service
- render returned projections/results

They do not infer runtime truth from object shape.

## 5. Canonical Module Direction

### Keep as canonical foundations

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
  - but split aggressively over time
- `src/mini_agent/session/persistence.py`
  - as the low-level persistence primitive
- `src/mini_agent/commands/catalog.py`
  - as shared syntax/help metadata
- `src/apps/qqbot_channel/bot.mjs`
  - as the current QQ runtime path

### Transition to new canonical seams

- new `mini_agent/session/*` session-domain and projection modules
- new `mini_agent/application/session_service.py` or equivalent
- new `mini_agent/commands/service.py` for shared command semantics
- new terminal-local runtime host module for TUI + CLI reuse

### Candidates to retire after migration

- `src/mini_agent/core/session.py`
- `src/mini_agent/session/binding.py`
- `src/channels/qqbot/src/*`
- `src/channels/wechat/src/*` if not on the active path
- `src/gateway/channels/base.py`

Retirement should happen only after the active path is fully re-homed.

## 6. Phase Plan

## Phase P29.1: Canonical Session Contract Extraction

### Objective

Define one canonical session domain model and stop surfaces from inventing their own domain truth.

### Tasks

- add a new session-domain module under `src/mini_agent/session/`
- define:
  - canonical session aggregate
  - recovery state model
  - model-selection state model
  - approval state model
- define explicit projection models:
  - transport projection
  - terminal projection
  - persistence projection
- add mappers from runtime state to those projections

### First Cut Deliverable

The first code cut in P29 should be:

- create shared session projection models and mapping helpers
- stop TUI summary/detail rendering from reading ad hoc session fields directly
- keep behavior unchanged while replacing field-by-field surface reads with projection reads

### Why This First

- lowest-risk structural cut with immediate leverage
- turns implicit field coupling into explicit mapping seams
- reduces the chance of another "surface overwrote runtime truth" bug

### Acceptance

- TUI/gateway session summaries are built from shared projection code
- no behavior change in current readiness tests
- no new session fields added directly to TUI as part of feature work

### Implementation Status (2026-04-12)

- completed first cut:
  - added `src/mini_agent/session/projection.py`
  - runtime summary/detail DTO assembly now flows through shared projection objects
  - TUI remote payload parsing and terminal session-display semantics now flow through shared projection objects
- verification:
  - `191 passed` across the focused P29.1a regression bundle
- notable in-slice fix:
  - corrected one persisted-recovery boundary bug where projected approvals were accidentally fed back into raw recovery computation

## Phase P29.2: Session Application Service Extraction

### Objective

Move session operations out of surfaces and out of thin gateway scripts into one shared application service.

### Tasks

- extract one session application service
- move into it:
  - create
  - rename
  - share/unshare
  - reset/delete
  - cancel
  - model selection update
  - runtime policy update
  - context policy update
- gateway use cases call the service instead of touching runtime internals directly

### Acceptance

- `MainAgentGatewayUseCases` no longer imports `MainAgentSessionState`
- gateway use cases no longer lock `session.lock` directly
- TUI local session mutations use the same service contract where applicable

### Implementation Status (2026-04-12)

- completed first gateway-facing cut:
  - added `src/mini_agent/application/session_service.py`
  - added `ManagedSessionTurn` so session lock/lifecycle ownership now lives in the shared service
  - `MainAgentGatewayUseCases` no longer imports `MainAgentSessionState`
  - `MainAgentGatewayUseCases` no longer locks `session.lock` directly
- current boundary after this cut:
  - gateway still owns approval/activity/delegation orchestration
  - but session mutation and turn-scoping ownership are no longer embedded in gateway
- completed second TUI-facing cut:
  - added `src/mini_agent/application/session_remote_service.py`
  - TUI remote session mutation/control paths now go through the typed remote service instead of raw `gateway_client` mutation calls
  - remote DTO handling is now explicit for:
    - model selection
    - runtime policy
    - context policy
    - memory actions
    - skill actions
    - approvals
    - generic control actions
    - KB / MCP remote control commands
- current boundary after both cuts:
  - TUI still directly calls `gateway_client.run_chat(...)` for remote execution streaming/fallback
  - but remote session mutation/control semantics are no longer embedded in raw transport calls inside the TUI surface
- verification:
  - `194 passed` across the focused P29.1a + P29.2 regression bundle

## Phase P29.3: Shared Command Execution Service

### Objective

Unify command semantics, not only command syntax.

### Tasks

- add one command execution service behind the shared catalog/router
- move command behaviors out of:
  - `tui/app.py`
  - `cli_interactive.py`
  - duplicated QQ JS command logic where feasible
- define typed command result payloads

### Acceptance

- TUI and CLI command behavior is driven by the same execution layer
- per-surface divergence is limited to rendering, not business logic
- command regression tests can be shared more effectively

### Implementation Status (2026-04-12)

- completed first cut:
  - added `src/mini_agent/commands/execution.py`
  - introduced a shared local operator command execution service plus typed execution results
  - migrated local `mcp` and `sandbox status` command behavior in:
    - `src/mini_agent/tui/app.py`
    - `src/mini_agent/cli_interactive.py`
- completed second cut:
  - extended the same shared service with local `kb` command semantics
  - migrated local `kb status|on|off` behavior in:
    - `src/mini_agent/tui/app.py`
    - `src/mini_agent/cli_interactive.py`
- completed third cut:
  - extended the same shared service with local `context` command semantics
  - migrated local `context` behavior in:
    - `src/mini_agent/tui/app.py`
    - `src/mini_agent/cli_interactive.py`
  - covered:
    - `show`
    - `stats`
    - `include`
    - `exclude`
    - `budget`
    - `reset`
- completed fourth cut:
  - extended the same shared service with local `memory` execution semantics
  - migrated local `memory` execution in:
    - `src/mini_agent/tui/app.py`
    - `src/mini_agent/cli_interactive.py`
  - unified shared `/memory show` parsing so TUI and CLI no longer carry separate helpers
  - covered:
    - `status`
    - `show`
    - `list`
    - `overview`
    - `export`
    - `consolidated show|search`
    - `profile`
    - `notes`
    - `daily`
    - `runtime`
    - `shared list|show|clear`
    - `refresh`
    - `promote shared|note|profile`
    - `save note|profile`
- completed fifth cut:
  - extended the same shared service with local `skill` execution semantics
  - migrated local `skill` execution in:
    - `src/mini_agent/tui/app.py`
    - `src/mini_agent/cli_interactive.py`
  - covered:
    - `list`
    - `active`
    - `show`
    - `install`
    - `uninstall`
    - `rollback`
    - `search`
    - `mode`
    - `enable`
    - `disable`
    - `reset`
    - `refresh`
  - kept runtime reload orchestration surface-owned while sharing the command semantics and mutation payloads
- current boundary after this cut:
  - command syntax/help/catalog remain shared as before
  - one real shared execution seam now exists for local operator commands ranging from low to high coupling:
    - `skill`
    - `memory`
    - `context`
    - `kb`
    - `mcp`
    - `sandbox`
  - more stateful command families still remaining in surface code are now mainly:
    - parts of `model`
    - remote/shared-session command transport
- verification:
  - `153 passed` across the focused command/TUI/CLI/readiness/shared-session bundle

## Phase P29.4: Terminal Runtime Host Split

### Objective

Separate terminal-local runtime execution from terminal view state.

### Tasks

- introduce a local runtime host bundle for:
  - agent
  - submission loop
  - loop bus
  - cancel event
- introduce a separate TUI view-state model for:
  - scroll
  - panel expansion
  - cursor/focus
  - render cache
- reduce `TuiSession` to either:
  - a projection + runtime-handle reference + view-state reference
  - or remove `TuiSession` entirely in favor of composition
- reuse the same local runtime host seam in CLI

### Acceptance

- UI state changes can no longer affect session-domain truth
- local-vs-gateway execution route is decided by the application/runtime service, not by TUI field inspection

## Phase P29.5: Runtime Manager Decomposition

### Objective

Break the god object into stable role-based services.

### Target split

- session repository / persistence adapter
- session runtime executor
- session operator service
- session presentation mapper
- snapshot import/export service

### Acceptance

- `MainAgentRuntimeManager` shrinks materially
- operator subsystem formatting is no longer imported directly into the runtime executor core

## Phase P29.6: Channel Path Consolidation

### Objective

Remove parallel QQ/session abstractions and define one active channel path.

### Tasks

- explicitly declare `src/apps/qqbot_channel` as canonical or replace it with one consolidated alternative
- archive or remove duplicate QQ/channel stacks
- remove dead Python-side channel abstractions if they are no longer part of the active runtime
- converge conversation-to-session binding onto one canonical owner

### Acceptance

- one QQ path is active and documented
- one conversation-binding authority exists

## Phase P29.7: Persistence And DTO Hardening

### Objective

Stop using overloaded persistence payloads and weakly typed operator result contracts.

### Tasks

- separate generic session persistence from runtime-specific metadata projections
- define typed DTOs for:
  - memory actions
  - skill actions
  - MCP actions
  - session operator feedback
- keep human-readable details as explicit presentation fields, not hidden dict keys

### Acceptance

- fewer `dict[str, Any]` response envelopes
- DTO shape changes become testable and reviewable

## 7. Recommended Execution Order

1. `P29.1` Canonical session contract extraction
2. `P29.2` Session application service extraction
3. `P29.3` Shared command execution service
4. `P29.4` Terminal runtime host split
5. `P29.5` Runtime manager decomposition
6. `P29.6` Channel path consolidation
7. `P29.7` Persistence and DTO hardening

This order is intentional:

- first make truth explicit
- then centralize behavior
- then thin surfaces
- only then delete parallel systems

## 8. First Implementation Slice

### Slice Name

`P29.1a Shared Session Projection Seam`

### Scope

- add a shared session projection module
- map runtime session state to shared projection
- map persisted session record to shared projection
- use the projection in summary/detail render assembly
- use the projection in TUI summary/status/threads rendering where possible

### Explicitly Out Of Scope

- no new command behavior
- no channel deletion yet
- no lifecycle semantic changes
- no persistence rewrite yet

### Files Likely In Scope

- new `src/mini_agent/session/...`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/tui/app.py`
- related tests in:
  - `tests/test_tui_app.py`
  - `tests/test_main_agent_gateway_use_cases.py`
  - `tests/test_interface_dto_contracts.py`

### Acceptance

- shared projection exists and is used in at least one active read path
- the current targeted session/TUI/gateway regression bundle remains green
- the next slice can migrate more surface logic without redefining session truth again

## 9. Test Strategy

For every P29 slice:

- add focused unit tests for the new boundary
- keep the current targeted runtime/session bundle green
- do not rely only on TUI manual smoke

Baseline targeted bundle:

```bash
uv run pytest tests/test_tui_app.py tests/test_tui_readiness_walkthroughs.py tests/test_command_catalog.py tests/test_command_router.py tests/test_shared_session_gateway_walkthrough.py tests/test_channel_ingress_gateway_walkthrough.py tests/test_p19_runtime_matrix.py -q
```

Expand with additional focused suites per slice as the new modules land.

## 10. Exit Criteria For P29

P29 is considered structurally successful when:

- one canonical session model exists
- TUI/CLI/gateway/QQ no longer each own session semantics
- command semantics are shared across TUI/CLI at minimum
- `MainAgentRuntimeManager` is materially smaller and more focused
- duplicate legacy session/channel abstractions are retired or explicitly archived
