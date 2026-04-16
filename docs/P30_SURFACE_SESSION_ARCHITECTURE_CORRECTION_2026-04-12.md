# P30 Surface / Session Architecture Correction

> Status: Active
> Date: 2026-04-12
> Goal: lock the corrected architecture before the next refactor phase and GitHub release snapshot
> Update 2026-04-14 (`P32.60`): `Remote Interaction` is now physically hard-locked to one active adapter path (`src/apps/qqbot_channel/`); legacy WeChat/browser channel code was removed from the active tree to prevent drift

## 1. Core Correction

The session model must not be owned by any user entrance.

The canonical rule is:

- `Session` is an independent core object and the single source of truth
- `CLI`, `TUI`, `DesktopUI`, and `Remote Interaction` do not own sessions
- concrete remote adapters live under the remote entrance; the active repo currently carries only `QQ`
- every entrance only observes or operates sessions through shared application services

This explicitly corrects the old drift where surface-local state started behaving like session truth.

## 2. Canonical Entrance Model

The user-side product model is now explicitly:

1. `CLI`
2. `TUI`
3. `DesktopUI`
4. `Remote Interaction`

Important clarification:

- `Remote Interaction` is a product entrance category
- `QQ` is the only active remote adapter under that entrance today
- future remote adapters must be explicitly reintroduced instead of being kept as dormant active code
- `headless` is a runtime mode, not a fifth entrance
- `gateway` is a shared host / transport path, not a user entrance

## 3. Canonical Layering

The intended architecture is:

1. User entrance layer
   - `CLI`
   - `TUI`
   - `DesktopUI`
   - `Remote Interaction`
2. Remote channel adapter sub-layer
   - `QQ adapter`
   - future adapters only after explicit reactivation
3. Interface / transport layer
   - terminal input adapters
   - gateway HTTP API
   - remote ingress / egress adapters
4. Application layer
   - session application service
   - chat / operator / ops / workspace use cases
   - shared command execution services
   - model / memory / RAG / skill / MCP service seams
5. Runtime orchestration layer
   - local runtime host
   - submission loop
   - approvals / cancel / recovery
   - runtime diagnostics
6. Core capability layer
   - agent core
   - model manager
   - memory
   - RAG
   - skills
   - MCP
   - session / workspace domain and persistence contracts

The transport/API layer sits above application services, not below them.
It translates protocols. It must not carry business ownership.

## 4. Entrance Definitions

### CLI

- the minimal and canonical operator interface
- supports direct command and prompt interaction
- acts as the lowest-complexity surface for debugging, scripting, and fallback usage

### TUI

- the developer console / visual operator frontend
- reuses CLI command semantics
- adds session visibility, activity visibility, model controls, and operator state panels
- must not become the owner of session truth

### DesktopUI

- a graphical surface sharing the same application layer as CLI/TUI
- intended for richer interaction patterns such as file handling, provider setup, and end-user workflows
- is not allowed to fork the session model or business rules

### Remote Interaction

- a peer entrance alongside CLI/TUI/DesktopUI
- provides remote conversational access into the same shared session/application model
- is implemented by thin channel adapters rather than by duplicating business logic

### Remote channel adapters

Concrete adapters under `Remote Interaction` must:

- hold conversation-to-session bindings
- hold reply and delivery preferences
- hold channel-local display metadata
- call shared application services for real session work

They must not:

- invent channel-owned session truth
- reimplement turn execution rules
- fork memory / model / command business logic

## 5. Important Non-Goals

The architecture must not slide back into any of the following:

- "TUI sessions", "CLI sessions", "DesktopUI sessions", or "QQ sessions" as separate truth models
- treating `QQ` as if it defines the whole remote entrance
- treating remote interaction as a child subsystem of TUI
- DesktopUI reimplementing business rules instead of calling application services
- runtime managers returning directly to entrance-owned behavior logic

## 6. Current Project Assessment

The project direction is broadly correct, but the active wording and implementation still contain drift.

### Already aligned

- shared application services exist:
  - `src/mini_agent/application/session_service.py`
  - `src/mini_agent/application/main_agent_gateway_use_cases.py`
  - `src/mini_agent/application/channel_ingress_use_cases.py`
- shared transport DTO contracts exist:
  - `src/mini_agent/interfaces/*`
- shared local operator command semantics now exist:
  - `src/mini_agent/commands/execution.py`
- QQ has already been pushed toward a thin adapter path under:
  - `src/apps/qqbot_channel/*`

### Still misaligned

- active wording still over-flattens the entrance model into `CLI / TUI / DesktopUI / QQ`
  - that is too implementation-specific
  - the correct product definition is `CLI / TUI / DesktopUI / Remote Interaction`
- `src/mini_agent/tui/app.py`
  - `TuiSession` still mixes:
    - session-facing data
    - runtime handles
    - UI-only state
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
  - still acts as an oversized manager that mixes:
    - session storage
    - persistence
    - projections
    - operator action execution
    - runtime state transitions
- remote-channel architecture is still uneven:
  - active QQ adapter is in `src/apps/qqbot_channel`
  - older non-QQ channel trees were drift sources and should be removed instead of kept as "future but active-looking" code
  - future adapters should start as new app-path implementations only after a new architecture decision
- the Desktop direction is still in transition:
  - current codebase has a new desktop path plus shared gateway transport
  - but the canonical DesktopUI entrance contract is not yet fully consolidated on the new architecture

## 7. Refactor Rules For The Next Phase

The next refactor work on `main` should follow these rules:

1. Session truth stays centralized.
2. Entrances may cache projections, never domain ownership.
3. Remote channel adapters may cache bindings and delivery state, never session truth.
4. Desktop surfaces must use the same application services as terminal surfaces.
5. Interface/API adapters may translate protocols, but may not embed business logic.
6. Runtime orchestration must keep shrinking out of entrance code and oversized managers.
7. `Remote Interaction` must be treated as a first-class entrance, with concrete bots kept as thin implementations underneath it.

## 8. Immediate Development Focus

The next development focus after this GitHub snapshot should be:

1. lock the four-entrance product model in active docs and planning
2. finish separating TUI state, runtime handles, and session projections
3. keep `Remote Interaction` generic at the entrance level while keeping only `QQ` as the active adapter path in the codebase
4. clarify the canonical DesktopUI entrance versus remote/integration adapters
5. continue decomposing `MainAgentRuntimeManager`

## 9. Branching Intent

This snapshot is intended to:

- preserve the current project state for upcoming code submission
- publish the corrected four-entrance architecture plan to GitHub
- continue the hard refactor on `main` afterward
