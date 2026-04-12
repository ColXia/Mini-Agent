# P30 Surface / Session Architecture Correction

> Status: Active
> Date: 2026-04-12
> Goal: lock the corrected architecture before the next refactor phase and GitHub release snapshot

## 1. Core Correction

The session model must not be owned by any user surface.

The canonical rule is:

- `Session` is an independent core object and the single source of truth
- `CLI`, `TUI`, `WebUI`, and `QQ` do not own sessions
- every surface only observes or operates sessions through shared application services

This explicitly corrects the old drift where surface-local state started behaving like session truth.

## 2. Canonical Layering

The intended architecture is:

1. Surface layer
   - `CLI`
   - `TUI`
   - `WebUI`
   - remote channels such as `QQ`
2. Transport / adapter layer
   - terminal input adapters
   - gateway HTTP API
   - OpenAI-compatible adapter
   - QQ bot adapter
3. Application layer
   - session application service
   - chat / operator / ops use cases
   - shared command execution services
4. Runtime orchestration layer
   - local runtime host
   - submission loop
   - approvals / cancel / recovery
   - runtime diagnostics
5. Core capability layer
   - agent core
   - model manager
   - memory
   - RAG
   - skills
   - MCP
   - session domain/projection/persistence contracts

The transport layer sits above application services, not below them.

## 3. Surface Definitions

### CLI

- the minimal and canonical operator interface
- supports direct command and prompt interaction
- acts as the lowest-complexity surface for debugging and fallback usage

### TUI

- the developer console / visual operator frontend
- reuses CLI command semantics
- adds session visibility, activity visibility, model controls, and operator state panels
- must not become the owner of session truth

### WebUI

- a browser surface that shares the same application layer as CLI/TUI
- intended for richer interaction patterns such as uploads, provider setup, and customer-facing workflows
- is not allowed to fork the session model

### QQ

- a channel adapter, not a session owner
- may reuse the same command semantics and application services used by CLI/TUI
- must only hold conversation-to-session bindings and channel-local delivery state
- must not introduce a second session truth

## 4. Important Non-Goals

The architecture must not slide back into any of the following:

- "TUI sessions", "CLI sessions", or "QQ sessions" as separate truth models
- QQ being treated as a child subsystem of TUI
- WebUI reimplementing business rules instead of calling application services
- runtime managers returning directly to surface-owned behavior logic

## 5. Current Project Assessment

The project direction is broadly correct, but the implementation is still in a transition state.

### Already aligned

- shared application services exist:
  - `src/mini_agent/application/session_service.py`
  - `src/mini_agent/application/main_agent_gateway_use_cases.py`
  - `src/mini_agent/application/channel_ingress_use_cases.py`
- shared transport DTO contracts exist:
  - `src/mini_agent/interfaces/*`
- shared local operator command semantics now exist:
  - `src/mini_agent/commands/execution.py`

### Still misaligned

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
- `src/apps/qqbot_channel/bot.mjs`
  - still carries channel-side session binding/cache logic that must remain only a binding/cache layer, not domain truth
- web direction is still split between:
  - Studio/operator web
  - Open WebUI compatibility adapter
  - a final canonical WebUI surface is not yet fully consolidated

## 6. Refactor Rules For The Next Phase

The next refactor work on `main` should follow these rules:

1. Session truth stays centralized.
2. Surface-local structs may cache projections, never domain ownership.
3. QQ/channel adapters may cache binding state, never session truth.
4. Web surfaces must use the same application services as terminal surfaces.
5. Transport adapters may translate protocols, but may not embed business logic.
6. Runtime orchestration must keep shrinking out of surface code and oversized managers.

## 7. Immediate Development Focus

The next development focus after this GitHub snapshot should be:

1. continue shrinking `TuiSession` toward view-state plus runtime/session references
2. continue decomposing `MainAgentRuntimeManager`
3. keep remote channel behavior bound to the same session/application contracts
4. clarify the canonical WebUI path versus compatibility adapters

## 8. Branching Intent

This snapshot is intended to:

- preserve the current project state for upcoming code submission
- publish the corrected architecture plan to GitHub
- continue the hard refactor on `main` afterward
