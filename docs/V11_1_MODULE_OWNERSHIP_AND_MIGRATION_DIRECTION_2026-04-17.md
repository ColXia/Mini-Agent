# Mini-Agent v11.1 Module Ownership And Migration Direction

> Status: discussion baseline
> Date: 2026-04-17
> Scope: physical module ownership / target repo placement / transitional module interpretation / migration direction
> Related:
> - [FRAMEWORK_SKELETON.md](./FRAMEWORK_SKELETON.md)
> - [V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md](./V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md)
> - [V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md](./V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md)
> - [V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md](./V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md)
> - [V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md](./V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md)
> - [V11_1_USER_SERVICE_TO_KERNEL_INTERFACE_DESIGN_2026-04-17.md](./V11_1_USER_SERVICE_TO_KERNEL_INTERFACE_DESIGN_2026-04-17.md)
> - [V11_1_CONCRETE_MODULE_TREE_2026-04-17.md](./V11_1_CONCRETE_MODULE_TREE_2026-04-17.md)
> - [V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md](./V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md)

## 1. Purpose

This document freezes the fifth `v11.1` architecture slice:

- physical module ownership and migration direction

It answers one practical question:

- once the logical architecture is corrected, where should those responsibilities actually live in the repository

This slice matters because architecture drift often returns through physical structure drift first.

## 2. Core Position

`v11.1` now freezes the following position:

- logical ownership and physical ownership must match closely enough that new work naturally lands in the right place

This does not mean the repo must be rewritten immediately.
It means:

- target ownership should be explicit
- transitional modules should be named as transitional
- future work should stop deepening the wrong module owners

## 3. Primary Physical Ownership Map

The maintained high-level repo ownership should be:

- `agent_core/`
- `runtime/`
- `application/`
- `session/`
- `workspace_runtime/`
- `model_manager/`
- `commands/`
- `interfaces/`
- `tui/`
- `desktop/`
- `transport/`

This is not a full repo listing.
It is the ownership map that most directly matters for the current architecture redesign.

## 4. `agent_core/` Ownership

`src/mini_agent/agent_core/` owns:

- kernel truth objects
- run execution semantics
- run control truth models
- capability resolution contracts
- execution journal contracts
- checkpoint contracts
- agent-instance lifecycle semantics

`agent_core/` must not own:

- TUI view state
- desktop UI state
- remote adapter glue
- workspace durable implementation details
- provider-specific transport clients

Practical rule:

- if a change is defining what `AgentInstance / Run / RunControl / Checkpoint / Journal` mean, it belongs here

## 5. `runtime/` Ownership

`src/mini_agent/runtime/` owns:

- runtime orchestration
- managed execution hosting
- approval/cancel/recovery runtime bridging
- projection building for active runtime state
- runtime-specific service coordination

`runtime/` is where:

- in-process execution bridges live
- runtime manager and handlers live
- session-facing compatibility orchestration may temporarily live

`runtime/` must not become:

- the owner of kernel truth semantics
- the owner of surface-specific UX behavior

Practical rule:

- if a change is about how the host process coordinates live execution around the kernel, it belongs here

## 6. `application/` Ownership

`src/mini_agent/application/` should become the stable shared use-case layer.

Target ownership inside `application/`:

- user-facing service contracts
- shared use-case orchestration
- surface-neutral facades
- explicit runtime-port interfaces

Recommended target sub-ownership:

- `application/user_services/`
- `application/use_cases/`
- `application/ports/`
- `application/facades/`

This does not mean these folders must be created immediately.
It means future growth should conceptually follow this structure.

## 7. `session/` Ownership

`src/mini_agent/session/` owns:

- session domain contracts
- session persistence
- session read models
- session lineage / archive / binding records

`session/` must not continue expanding into:

- run control truth
- main model binding truth
- workspace runtime truth

Practical rule:

- if the object is task truth or transcript truth, it can live here
- if the object is active execution truth, it should not be reintroduced here

## 8. `workspace_runtime/` Ownership

`v11.1` explicitly recommends a dedicated `workspace_runtime/` module.

Target ownership:

- workspace execution boundary
- mounted execution mode
- outside-zone handling
- mutation ledger
- snapshot / diff / reversibility hooks
- workspace-side execution services

This module is especially important because the current architecture now clearly distinguishes:

- workspace as durable world
- workspace runtime as execution environment

Those should not remain implicit across unrelated runtime helpers forever.

## 9. `model_manager/` Ownership

`src/mini_agent/model_manager/` continues to own:

- provider registry
- model pool
- agent-facing model binding
- capability facts
- probing / discovery / provider governance

Critical rule:

- main model binding remains model-system ownership
- it must not drift into `session/`
- it must not drift into `workspace_runtime/`

## 10. `commands/` Ownership

`src/mini_agent/commands/` owns:

- canonical command grammar
- command catalog
- command parsing semantics
- cross-surface command metadata

It should not own:

- surface rendering
- runtime truth
- session truth

This module is the natural physical home of the shared command subsystem.

## 11. `interfaces/` Ownership

`src/mini_agent/interfaces/` owns:

- transport-facing DTOs
- response envelopes
- user-service-facing shape contracts exposed to gateway/transport layers

It must not become:

- a second business-logic layer
- a place for runtime truth objects

Practical rule:

- DTOs live here
- core truth objects do not

## 12. `tui/`, `desktop/`, `transport/` Ownership

`tui/` owns:

- TUI rendering
- operator interaction state
- TUI-local presentation decisions

`desktop/` owns:

- desktop windowing
- view models
- desktop-local controllers and native affordances

`transport/` owns:

- gateway / protocol client / transport glue
- host-side transport helpers

All three must stay out of:

- kernel truth
- run control truth
- session truth ownership
- model-system ownership

## 13. Current Transitional Module Interpretation

Current repo modules should now be interpreted as follows:

- `application/main_agent_surface_service.py`
  - transitional cross-surface facade
  - useful and still valid
  - not the final monolithic home for all future user-facing behavior
- `application/session_service.py`
  - transitional session/task application service
  - should not be treated as the final owner of all agent/workspace/model/control use cases
- `application/session_runtime_port.py`
  - transitional runtime-port seam
  - still useful
  - not the final architecture shape for all user-service to runtime interaction
- `runtime/main_agent_runtime_manager.py`
  - runtime orchestration anchor
  - should keep shrinking toward real orchestration rather than silently reabsorbing truth ownership

## 14. Recommended Physical Growth Direction

The recommended growth direction is:

1. keep existing transitional modules working
2. stop deepening them as if they were the final ownership model
3. introduce new modules under the correct ownership line
4. gradually move logic by responsibility instead of by file-size anxiety

This means:

- do not big-bang rewrite `MainAgentRuntimeManager`
- do not big-bang split `SessionApplicationService` just because its name is broad
- but also do not continue adding clearly agent-owned or model-owned or run-control-owned behavior there forever

## 15. Recommended New Module Landing Rules

If the new work is about:

- agent/run truth: land near `agent_core/`
- live runtime orchestration: land near `runtime/`
- user-facing orchestration or shared use cases: land near `application/`
- task truth: land near `session/`
- workspace execution world: land near `workspace_runtime/`
- main model supply/binding/capabilities: land near `model_manager/`
- command grammar or command metadata: land near `commands/`
- DTOs or transport envelopes: land near `interfaces/`
- rendering and local UI behavior: land near `tui/` or `desktop/`

This rule should be used before implementation, not after code has already drifted.

## 16. Transitional Naming Rule

When a module remains in a useful but transitional position, the team should treat it as:

- stable enough to keep using
- not authoritative enough to absorb every new concern

This is especially true for:

- `MainAgentSurfaceService`
- `SessionApplicationService`
- `SessionRuntimePort`

They are transition owners, not destination owners.

## 17. Anti-Drift Rules

The following are now explicitly disallowed:

- adding kernel truth objects into `interfaces/` or surface folders
- adding user-surface rendering logic into `runtime/` or `agent_core/`
- adding main model binding truth into `session/`
- keeping workspace execution semantics scattered without moving toward `workspace_runtime/`
- treating large transitional files as proof they are the right permanent owner

## 18. Immediate Direction For Current Repo

The near-term direction should be:

- preserve current seams
- use new docs as ownership guidance before more real implementation
- prefer landing new behavior in the correct target ownership line even if compatibility shims remain elsewhere
- gradually realign the physical repo toward the corrected logical architecture instead of waiting for one big rewrite

This document is not a migration checklist.
It is the ownership rulebook that later migration plans should follow.
