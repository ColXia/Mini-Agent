# P29 Session Boundary Audit (2026-04-12)

## Purpose

This audit was triggered by the latest session unification work.

The immediate bug was fixable, but the failure mode exposed a deeper architectural problem:

- session semantics are not owned by one boundary
- runtime state, UI state, transport state, and persistence state are mixed together
- multiple modules still behave as if they are the canonical session owner

This document records the current boundary failures and defines the hard-refactor direction.

## Executive Summary

The current runtime does not have one canonical session model.

Instead, the project currently has:

- a TUI-facing session model that also owns local runtime execution handles
- a gateway/runtime session model that also owns transcript, recovery, persistence, and operator actions
- a legacy core session store that is still exported as public API but is no longer the active runtime truth
- channel-side session stores in TypeScript / Node that keep separate conversation-to-session state
- an orphaned Python conversation binding store that is not part of the active path

This is the core reason session changes now ripple across TUI, gateway, QQ, persistence, and command behavior.

## Key Signals

- `src/mini_agent/tui/app.py`
  - ~335 methods
  - imports 22 internal modules
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
  - ~147 methods
  - imports 19 internal modules
- `src/mini_agent/cli_interactive.py`
  - still contains a large command-execution if/elif chain after the shared dispatcher bootstrap

These numbers do not prove a problem by themselves, but here they match the observed boundary collapse.

## Findings

### 1. Session Has No Single Source Of Truth

Current session models:

- `TuiSession` in `src/mini_agent/tui/app.py`
- `MainAgentSessionState` in `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `SessionState` / `SessionStore` in `src/mini_agent/core/session.py`
- TypeScript `SessionState` in `src/channels/types/src/index.ts`
- channel-local `MemorySessionStore` in `src/channels/qqbot/src/session_store.ts`
- ad hoc QQ session map in `src/apps/qqbot_channel/bot.mjs`
- `ConversationBindingStore` in `src/mini_agent/session/binding.py`

Concrete problem:

- `TuiSession` and `MainAgentSessionState` share many fields but are not projections of one canonical aggregate.
- `core/session.py` is still exported as a public core API, but the active runtime path uses `MainAgentRuntimeManager` + `SessionPersistence` directly.
- `session/binding.py` exists as another binding authority but is not part of the active path.

Impact:

- no one module can be trusted as the definitive owner of session identity and lifecycle
- field drift and semantic drift are inevitable
- integration bugs show up as "sync bugs" instead of obvious ownership violations

### 2. TUI Is Simultaneously View, Controller, Session Store, And Runtime Host

`TuiSession` currently mixes:

- surface/view state
  - scroll position
  - panel expansion state
  - render cache
- session domain state
  - selected model
  - knowledge-base toggle
  - context policy
  - approvals
  - recovery markers
- local runtime handles
  - `agent`
  - `submission_loop`
  - `loop_bus`
  - `cancel_event`
- remote sync mirrors
  - `remote_message_count`
  - `remote_updated_at`
  - `remote_recovery_summary`
  - `remote_last_activity_summary`

Concrete code smell:

- `busy` and `running_state` are both declared twice inside `TuiSession`, which is a symptom of uncontrolled model growth rather than one clean ownership model.

Concrete boundary failure:

- TUI decides whether a session is "gateway" or "local" by inspecting whether runtime handles are attached:
  - if `agent/submission_loop/loop_bus/cancel_event` exist, treat as local
  - otherwise treat as gateway

That means execution routing is currently a UI concern.

Impact:

- session execution semantics leak into the surface layer
- switching or syncing sessions can accidentally overwrite local runtime truth
- TUI bugs become session-domain bugs

### 3. Runtime Manager Is A God Object

`MainAgentRuntimeManager` currently owns all of the following:

- session creation / lookup / deletion
- session lifecycle state
- persistence
- transcript append logic
- recovery snapshot creation
- model selection updates
- runtime policy updates
- approval resolution
- memory commands
- skill commands
- MCP status / reload
- session summary/detail DTO construction
- snapshot export / import

It also imports presentation-formatting helpers directly:

- `format_memory_*`
- `format_skill_*`
- `format_mcp_*`

This means the runtime manager is not only a domain/runtime service.
It is also acting as:

- persistence adapter
- application service
- operator-command executor
- response presenter

Impact:

- low cohesion
- extremely high change blast radius
- domain behavior and response wording are coupled

### 4. Application Layer Is Too Thin And Leaks Runtime Internals

`MainAgentGatewayUseCases` is nominally an application-layer boundary, but in practice it:

- imports `MainAgentSessionState` directly
- locks the session directly with `async with session.lock`
- orchestrates turn flow step-by-step by calling many runtime-manager internals

This is not a stable use-case boundary.
It is a thin script around a god object plus direct state access.

Impact:

- runtime and application layers cannot evolve independently
- session concurrency policy is not encapsulated in one place
- transport/API concerns are too aware of runtime internals

### 5. Command System Is Unified Only At The Syntax Layer

The project does have shared command infrastructure:

- `src/mini_agent/commands/catalog.py`
- `src/mini_agent/commands/router.py`

But execution semantics are still fragmented:

- TUI registers commands and executes behavior inside `tui/app.py`
- CLI boots a dispatcher but still falls back to large in-file `if/elif` execution chains
- QQ bot reimplements command-catalog loading, tokenization, suggestions, and parsing in `bot.mjs`

This means the catalog/router currently unify:

- help
- usage
- parse shape

But not:

- execution semantics
- permission semantics
- lifecycle semantics
- command result contracts

Impact:

- same command can drift by surface
- fixes must be repeated across TUI / CLI / QQ
- command behavior is not a reusable service boundary

### 6. Channel Layer Has Parallel Implementations And No Clear Canonical Path

For QQ alone there are at least two competing paths:

- active runtime stack path:
  - `src/apps/qqbot_channel/bot.mjs`
- separate channel package path:
  - `src/channels/qqbot/src/*`

In addition, there is an older Python-side channel abstraction:

- `src/gateway/channels/base.py`

The active stack manager points to `src/apps/qqbot_channel`, not `src/channels/qqbot`.

Impact:

- canonical production path is unclear from the tree
- session and command behavior can diverge by implementation
- dead or semi-dead abstractions increase cognitive load and mislead new refactors

### 7. Session Persistence Contract Is Overloaded

`SessionPersistence` was designed as a generic session persistence primitive.

But `_MainAgentRuntimePersistence` now:

- uses `SessionPersistence`
- writes its own runtime-specific metadata into the same metadata file
- writes an extra shared transcript sidecar

At the same time, `MemoryService` also reads the same session store for retrieval/search.

So the session persistence layer is now serving:

- transcript persistence
- runtime session records
- memory indexing
- recovery import/export

without one explicit schema owner.

Impact:

- persistence is doing too much with too many consumers
- schema changes ripple into memory behavior and session recovery behavior

### 8. API Contracts For Operator Subsystems Are Too Loosely Typed

Examples:

- `MainAgentSessionMemoryResponse.result: dict[str, Any]`
- `MainAgentSessionSkillResponse.result: dict[str, Any]`

The runtime manager fills these with ad hoc payloads such as:

- `summary`
- `details`
- `items`
- `entry`
- `promotion`

This is effectively a presentation contract hidden inside an untyped dict.

Impact:

- surfaces couple to undocumented keys
- gateway responses are harder to evolve safely
- structured data and human-facing prose are not separated

### 9. Terminal Surfaces Rebuild The Same Local Runtime Stack Independently

Both TUI and CLI directly own local runtime construction:

- build agent kernel
- build submission loop
- own lifecycle runtime
- run local memory / runtime-memory operations

They are not thin surfaces over one shared terminal-session service.

Impact:

- session semantics diverge between TUI and CLI
- fixes must be implemented twice
- surface-specific state accidentally becomes runtime truth

### 10. Channel Ingress Still Mixes Product Domains

`ChannelIngressUseCases` currently handles:

- normal main-agent chat ingress
- internal `/novel ...` action parsing
- dispatch into the novel subsystem

This is a smaller issue than the session split, but it shows the same boundary pattern:

- ingress orchestration is mixed with product-specific command interpretation

Impact:

- channel ingress is not a clean adapter boundary
- unrelated subsystems remain entangled at the message entry seam

## Root Cause Pattern

The repeated pattern is:

1. add one feature at the surface layer
2. add just enough runtime state to support it
3. persist part of that state
4. expose it over gateway
5. mirror part of it back into another surface model

Over time this created:

- no canonical session aggregate
- no stable command execution service
- no clean distinction between:
  - domain state
  - runtime state
  - transport state
  - view state
  - persistence projection

## Recommended Target Boundaries

### A. One Canonical Session Aggregate

Create one session-domain aggregate that owns:

- identity
- workspace binding
- source/origin metadata
- sharing policy
- lifecycle state
- runtime policy
- selected model state
- recovery state
- approval queue
- transcript metadata

Everything else becomes a projection or adapter.

### B. Split View State Out Of TUI Session Data

TUI should keep a separate view model for:

- scroll position
- expanded/collapsed sections
- cursor/focus state
- render caches

It should not own execution-route truth.

### C. Introduce One Session Application Service

Extract a shared application service that owns:

- session create/select/reset/share
- turn submit/cancel/resume
- memory/skill/model/operator commands
- lifecycle resets

TUI/CLI/QQ/gateway should call this service rather than re-own behavior.

### D. Make Gateway And Terminal Surfaces Thin Adapters

- gateway should translate HTTP <-> application service
- TUI should translate UI events <-> application service
- CLI should translate shell input <-> application service
- QQ should translate bot events <-> application service

None of these surfaces should infer runtime ownership from attached object references.

### E. Split Runtime Manager By Role

Break `MainAgentRuntimeManager` into at least:

- session repository / persistence adapter
- session runtime executor
- session operator service
  - memory
  - skill
  - model
  - approval
  - MCP
- session presenter / DTO mapper
- snapshot import/export service

### F. Unify Command Semantics Server-Side

Keep the shared catalog/router for syntax help, but move execution semantics into one reusable command service.

Surfaces may still parse locally for UX, but they should all dispatch into the same command-execution layer.

### G. Collapse Channel Implementations

Choose one canonical QQ path and one canonical channel abstraction.

Everything else should be either:

- deleted
- archived
- explicitly marked legacy and out of runtime use

## Hard-Refactor Order

1. Freeze and document the active canonical paths.
   - canonical session runtime
   - canonical QQ path
   - canonical persistence shape
2. Extract one session application service and move command semantics into it.
3. Split TUI `TuiSession` into:
   - session projection
   - local runtime handle bundle
   - view state
4. Move gateway use cases to depend only on application service contracts, not `MainAgentSessionState`.
5. Split `MainAgentRuntimeManager` into smaller role-based services.
6. Remove or archive orphan session systems:
   - `mini_agent/core/session.py`
   - `mini_agent/session/binding.py`
   - unused channel abstractions / duplicate QQ path
7. Tighten interface DTOs so operator actions return typed payloads instead of `dict[str, Any]`.

## Immediate Recommendation

Do not continue adding more session behavior on top of the current structure.

The correct next step is a boundary-first hard refactor focused on:

- canonical session ownership
- shared command execution
- surface thinning

If we skip that and keep adding features, the next bug will likely appear as:

- another local-vs-remote session sync mismatch
- command behavior divergence by surface
- persistence/recovery drift
- approval or model state not matching the visible session

## Evidence Anchors

- TUI overloaded session and routing
  - `src/mini_agent/tui/app.py:489`
  - `src/mini_agent/tui/app.py:495`
  - `src/mini_agent/tui/app.py:522`
  - `src/mini_agent/tui/app.py:2333`
  - `src/mini_agent/tui/app.py:2346`
  - `src/mini_agent/tui/app.py:6526`
  - `src/mini_agent/tui/app.py:10271`
- Runtime manager overloaded responsibilities
  - `src/mini_agent/runtime/main_agent_runtime_manager.py:141`
  - `src/mini_agent/runtime/main_agent_runtime_manager.py:387`
  - `src/mini_agent/runtime/main_agent_runtime_manager.py:696`
  - `src/mini_agent/runtime/main_agent_runtime_manager.py:1539`
  - `src/mini_agent/runtime/main_agent_runtime_manager.py:2117`
  - `src/mini_agent/runtime/main_agent_runtime_manager.py:4223`
  - `src/mini_agent/runtime/main_agent_runtime_manager.py:4369`
  - `src/mini_agent/runtime/main_agent_runtime_manager.py:4837`
- Application layer leaking runtime internals
  - `src/mini_agent/application/main_agent_gateway_use_cases.py:117`
  - `src/mini_agent/application/main_agent_gateway_use_cases.py:331`
  - `src/mini_agent/application/main_agent_gateway_use_cases.py:349`
  - `src/mini_agent/application/main_agent_gateway_use_cases.py:369`
- CLI command semantics still in-surface
  - `src/mini_agent/cli_interactive.py:2003`
  - `src/mini_agent/cli_interactive.py:2058`
  - `src/mini_agent/cli_interactive.py:2088`
  - `src/mini_agent/cli_interactive.py:2185`
- Loose operator response contracts
  - `src/mini_agent/interfaces/agent.py:227`
  - `src/mini_agent/interfaces/agent.py:235`
  - `src/mini_agent/interfaces/agent.py:252`
  - `src/mini_agent/interfaces/agent.py:259`
- Duplicate / unclear QQ-channel path
  - `src/apps/qqbot_channel/bot.mjs:40`
  - `src/apps/qqbot_channel/bot.mjs:70`
  - `src/apps/qqbot_channel/bot.mjs:97`
  - `src/apps/qqbot_channel/bot.mjs:215`
  - `src/channels/qqbot/src/session_store.ts:18`
  - `src/channels/qqbot/src/session_store.ts:19`
  - `src/mini_agent/dev/runtime_stack_manager.py:75`
- Legacy / orphan session abstractions
  - `src/mini_agent/core/session.py:19`
  - `src/mini_agent/core/session.py:34`
  - `src/mini_agent/core/session.py:657`
  - `src/mini_agent/session/binding.py:23`
  - `src/mini_agent/session/binding.py:100`
