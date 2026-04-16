# Mini-Agent Framework Skeleton

> Status: active
> Last updated: 2026-04-16
> Purpose: lock the new framework skeleton so later implementation stays aligned and does not drift back into surface-owned logic or adapter-specific forks

## 1. Intent

This document is the canonical skeleton contract for the current Mini-Agent refactor.

It freezes four things:

- the product entrance model
- layer ownership
- repository ownership
- forbidden drift patterns

If a change conflicts with this document, the change should be realigned before more code is added.

## 2. Canonical Product Skeleton

Mini-Agent has four user-facing entrances:

1. `CLI`
2. `TUI`
3. `DesktopUI`
4. `Remote Interaction`

Clarifications:

- `Remote Interaction` is a product entrance
- the current active remote adapter is `QQ` only
- future remote adapters are not kept as active codepaths until explicitly reintroduced
- `DesktopUI (PySide6)` is the canonical graphical mainline
- browser `WebUI / OpenWebUI` are removed
- `gateway` is a shared host / transport path, not a product entrance
- `headless` is a runtime mode, not a product entrance

## 3. Canonical Layer Stack

The framework skeleton is:

1. User entrance layer
   - `CLI`
   - `TUI`
   - `DesktopUI`
   - `Remote Interaction`
2. Remote adapter sub-layer
   - `QQ adapter` (active path)
   - future remote adapters only after a new architecture decision
3. Interface / transport layer
   - terminal IO adapters
   - HTTP / SSE / WebSocket API
   - remote ingress / egress adapters
   - DTOs and response envelopes
4. Application service layer
   - session use cases
   - chat / turn orchestration
   - command execution services
   - model / memory / RAG / skill / MCP orchestration seams
5. Runtime orchestration layer
   - managed session lifecycle
   - submission loop coordination
   - approvals / cancellation / recovery
   - runtime diagnostics
6. Core capability layer
   - agent core
   - code-agent loop
   - memory
   - RAG
   - skills
   - MCP
   - model manager
   - session / workspace domain contracts
7. Infrastructure layer
   - persistence
   - LLM clients
   - SDK bindings
   - filesystem
   - external services

## 4. Repository Ownership Map

### Shared platform core

`src/mini_agent/`

- `application/`
  - shared use cases and orchestration seams
  - the main place where surface-independent interaction behavior should live
- `runtime/`
  - managed-session runtime lifecycle and execution coordination
- `session/`
  - persistence, projections, binding records, lineage-related contracts
- `agent_core/`
  - agent-core domain structures and kernel-level behavior
- `code_agent/`
  - tool loop, scheduler, sandbox, MCP client, context handling
- `memory/`
  - global and workspace memory runtime
- `rag/`
  - lightweight knowledge-base integration and retrieval ownership
- `model_manager/`
  - preset/custom provider registry and model selection
- `skills/`
  - skill loading, policy, workspace enablement
- `tools/`
  - tool implementations and tool wiring helpers
- `commands/`
  - shared command catalog, parse semantics, and shared execution contracts
- `interfaces/`
  - API / gateway / remote-facing DTO contracts
- `tui/`
  - TUI rendering, input, operator state, and TUI-specific interaction handling
- `desktop/`
  - DesktopUI state, controller helpers, and surface-specific view models

### Product / adapter apps

`src/apps/`

- `agent_studio_gateway/`
  - shared host and transport composition root
  - `/api/v1/*` lives here
- `desktop_ui/`
  - `PySide6` desktop app bootstrap and packaging entry
- `qqbot_channel/`
  - active remote adapter app
  - thin channel glue only

### Transitional / legacy paths

- historical channel trees under `src/channels/*`, `src/mini_agent/channels/*`, and `src/gateway/channels/*` are removed from the active codebase
- future remote adapters must start as new app-path implementations under `src/apps/`, not by reviving legacy channel trees

## 5. Dependency Rules

The allowed direction is:

`entrances/apps -> interfaces/application/commands -> runtime -> core capability -> infrastructure`

More concretely:

- surface code may call shared application services
- surface code may render projections and DTOs
- surface code must not become the owner of session truth
- route handlers and bot handlers may translate protocol payloads
- route handlers and bot handlers must not become business-rule owners
- application services may orchestrate runtime and domain services
- runtime code may depend on session/core capability modules
- core capability modules must not depend on TUI, DesktopUI, or concrete remote adapters

Composition-root exception:

- app entrypoints may wire lower-layer objects together
- that does not authorize business logic to move into app handlers

## 6. Session / Workspace / Lineage Model

The canonical truth model is:

- `Session` is the core conversation / task unit
- `Workspace` is the operational scope that groups sessions and workspace-level state
- derived sessions form lineage for delegation, forks, and task branches
- entrances operate sessions
- entrances do not own sessions

Implications:

- there are no separate `CLI sessions`, `TUI sessions`, `DesktopUI sessions`, or `QQ sessions` as truth models
- remote conversation binding is a way to reach a session, not a second session system
- session projections may differ by surface, but session identity and lifecycle remain shared

## 7. Surface Role Definitions

### CLI

- the minimal and canonical operator entrance
- the base command interaction model
- the simplest path for scripting, debugging, and recovery

### TUI

- the developer-facing visual terminal frontend
- reuses shared command semantics and shared session/application services
- owns rendering and operator interaction state only

### DesktopUI

- the primary end-user graphical frontend
- built as a separate `PySide6` surface, not a TUI wrapper
- shares the same application layer as CLI and TUI
- should start on the shared local gateway transport after the thin application-seam correction lands

### Remote Interaction

- the remote conversational entrance
- implemented by thin channel adapters
- must reuse shared application behavior instead of duplicating runtime/session logic

## 8. Remote Adapter Contract

Remote adapters are allowed to own:

- channel credentials
- channel SDK integration
- inbound event normalization
- outbound delivery formatting
- conversation binding hints
- delivery preferences
- channel-local display metadata

Remote adapters must not own:

- session truth
- chat execution rules
- memory / RAG / skill / model business logic
- command execution semantics as a separate parallel system
- a second persistence model for shared session lifecycle

The target pattern is:

`remote channel -> transport adapter -> shared application services -> shared runtime/session truth`

## 8.5 DesktopUI Contract

DesktopUI is allowed to own:

- desktop window composition
- view state
- native desktop affordances such as dialogs, tray, notifications, drag/drop, and file pickers
- local gateway supervisor behavior

DesktopUI must not own:

- session truth
- runtime execution rules
- separate model/memory/skill business semantics
- a second command system

The target first-delivery pattern is:

`DesktopUI -> local gateway transport -> shared application services -> shared runtime/session truth`

## 9. Command Skeleton Rule

Command support should be layered as follows:

- command catalog and canonical forms live in `src/mini_agent/commands/`
- surfaces may adapt presentation and input UX
- execution semantics should land in shared application/runtime services by default

That means:

- do not reimplement command meaning independently in TUI, CLI, and remote adapters unless the gap is temporary and documented
- if a command changes shared behavior, the default implementation target is not the surface file

## 10. API Skeleton Rule

The maintained API host is:

- `src/apps/agent_studio_gateway/main.py`
- namespace: `/api/v1/*`

Rules:

- the API layer exposes shared application services
- the API layer translates HTTP/SSE contracts
- the API layer does not become a second business layer

## 11. Freeze Rules

The following are hard no-go areas unless the architecture is explicitly revised first:

- adding new surface-owned session truth
- adding new channel-owned session truth
- copying business logic from application/runtime into route handlers or bot handlers
- treating a concrete remote adapter as if it defines the whole remote entrance
- adding new maintained product behavior to `src/channels/*`
- treating compatibility adapters as canonical product entrances
- expanding remote work without reference to the same shared application seams

## 12. Where New Code Goes

When adding a feature, use this routing guide:

- TUI layout / rendering / prompt UX:
  - `src/mini_agent/tui/*`
- CLI prompt / command UX:
  - `src/mini_agent/cli.py`
  - `src/mini_agent/cli_interactive.py`
  - shared command behavior first in `src/mini_agent/commands/*`
- session lifecycle / reuse / share / lineage:
  - `src/mini_agent/application/*`
  - `src/mini_agent/runtime/*`
  - `src/mini_agent/session/*`
- remote conversation resume / binding / takeover:
  - shared logic in `src/mini_agent/application/*` and `src/mini_agent/session/*`
  - channel glue only in `src/apps/*_channel/*`
- model / memory / RAG / skill / MCP behavior:
  - the corresponding core module plus one application seam if the behavior is surface-shared
- gateway transport routes:
  - `src/apps/agent_studio_gateway/*`
## 13. Current Development Order

With the skeleton locked, the next execution order is:

1. continue `P30` with this skeleton as the guardrail
2. finish session truth boundary cleanup
3. split TUI view state from runtime/session ownership
4. normalize remote adapters under the shared remote contract
5. do not reintroduce browser WebUI/OpenWebUI compatibility shells

## 14. References

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [P32_REMOTE_INTERACTION_ARCHITECTURE_LOCK_2026-04-14.md](./P32_REMOTE_INTERACTION_ARCHITECTURE_LOCK_2026-04-14.md)
- [P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md](./P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md)
- [P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md](./P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md)
- [P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md](./P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md)
