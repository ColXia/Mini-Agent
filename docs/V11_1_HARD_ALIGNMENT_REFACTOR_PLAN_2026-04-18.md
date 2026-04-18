# Mini-Agent v11.1 Hard Alignment Refactor Plan

> Status: execution baseline
> Date: 2026-04-18
> Scope: hard refactor / physical-structure alignment / compatibility deletion / v11.1-only target state
> Related:
> - [V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md](./V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md)
> - [V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md](./V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md)
> - [V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md](./V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md)
> - [V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md](./V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md)
> - [V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md](./V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md)
> - [V11_1_USER_SURFACE_ARCHITECTURE_2026-04-17.md](./V11_1_USER_SURFACE_ARCHITECTURE_2026-04-17.md)
> - [V11_1_USER_SERVICE_TO_KERNEL_INTERFACE_DESIGN_2026-04-17.md](./V11_1_USER_SERVICE_TO_KERNEL_INTERFACE_DESIGN_2026-04-17.md)
> - [V11_1_TRANSPORT_DTO_AND_READ_MODEL_CONTRACT_2026-04-17.md](./V11_1_TRANSPORT_DTO_AND_READ_MODEL_CONTRACT_2026-04-17.md)
> - [V11_1_MODULE_OWNERSHIP_AND_MIGRATION_DIRECTION_2026-04-17.md](./V11_1_MODULE_OWNERSHIP_AND_MIGRATION_DIRECTION_2026-04-17.md)
> - [V11_1_CONCRETE_MODULE_TREE_2026-04-17.md](./V11_1_CONCRETE_MODULE_TREE_2026-04-17.md)

## 1. Purpose

This document replaces the previous compatibility-preserving migration posture with a new execution rule:

- `v11.1` is now the only target state
- compatibility retention is no longer a goal
- physical module structure must align with logical ownership

The project is no longer optimizing for old path continuity.
It is optimizing for architectural correctness and future iteration clarity.

## 2. Hard Refactor Position

The repo now follows these hard rules:

- no compatibility layer is preserved just because it already exists
- no bridge or shim is kept once the real owner can be created
- no session-centric semantics are retained for convenience if `v11.1` places truth elsewhere
- no physical module may continue acting as a temporary bucket after its permanent owner is known
- old runtime or surface paths may be deleted before all surfaces are rewired, as long as the rewrite target is explicit

In practical terms:

- delete first-class legacy owners
- build the real `v11.1` owners
- reconnect surfaces to the new owners

This is a hard rewrite strategy, not a compatibility migration strategy.

## 3. What `v11.1` Means Now

The maintained target state is:

- `AgentProfile + AgentInstance` own agent truth
- `Run` owns execution truth
- `Workspace + WorkspaceRuntime` own durable execution world and execution environment
- `Session` owns task truth only
- `ModelPool + AgentModelService` own the main model chain
- user surfaces call explicit user services only
- application services orchestrate runtime ports only
- transport DTOs are explicit and typed
- raw payloads stay in transport only

This means the repo must stop carrying the old shape:

- surface facade monoliths
- session-owned control semantics
- session-owned main model semantics
- root compatibility wrappers
- session-runtime god ports
- dict-heavy active service contracts

## 4. Current Mismatch Summary

The current repo already moved in the `v11.1` direction, but it is not yet physically or semantically aligned enough.

The main remaining mismatches are:

### 4.1 Kernel objects are incomplete

The codebase already has:

- `RunControlState`
- `ApprovalWait`

But it still does not have a fully materialized kernel object family for:

- `AgentProfile`
- `AgentInstance`
- `Run`
- `WorkspaceAttachment`
- `SessionAttachment`
- `CapabilitySnapshot`
- `Checkpoint`
- `ExecutionJournal`

This means the kernel truth model is still only partially objectized.

### 4.2 Runtime still carries too much history

`runtime/main_agent_runtime_manager.py` remains too broad.

It still acts as:

- runtime host
- attachment coordinator
- session registry operator
- control bridge
- persistence driver
- model-adjacent coordinator

Even if many truths already moved away from session, the runtime host is still too central and too legacy-shaped.

### 4.3 Session-compat paths still exist in real code

The repo still contains or still depends on:

- `application/legacy/*`
- `application/main_agent_surface_service.py`
- `application/session_service.py`
- `application/session_runtime_port.py`
- `model_manager/session_selection_service.py`
- root compatibility wrappers under `application/` and `runtime/`

Even when guarded or narrowed, these modules still encode the old worldview and physical clutter.

### 4.4 Workspace is not yet a strong first-class domain object

The repo already has `workspace_runtime/`, which is correct.

But workspace handling is still too descriptor- and path-driven in active code.
The `Workspace` domain itself is not yet explicit enough as a maintained owner.

### 4.5 Model block is directionally correct but not cleanly cut over

The repo already has:

- `model_manager/agent_model_service.py`
- `model_manager/agent_model_binding.py`

But session-shaped model selection semantics are still present in real active code through:

- `model_manager/session_selection_service.py`
- session-facing model compatibility flows in TUI, Desktop, runtime handlers, and legacy application owners

### 4.6 Memory and skill systems are usable but not fully v11.1-shaped

The repo already has real memory and workspace-skill behavior.

But it still does not present the final explicit object architecture implied by `v11.1`, especially around:

- memory layer ownership clarity
- promotion boundaries
- skill registry layering
- clear separation between core/internal, global, and workspace-local resolution objects

## 5. Hard Target Tree

The repo should converge to this architecture-critical top-level tree under `src/mini_agent/`:

```text
agent_core/
application/
commands/
desktop/
interfaces/
memory/
model_manager/
rag/
runtime/
session/
skills/
tools/
transport/
tui/
workspace_runtime/
```

The following principles are mandatory:

- `agent_core/` owns kernel truth objects and execution contracts
- `runtime/` owns host orchestration only
- `application/` owns user services, use cases, and typed runtime ports
- `session/` owns task truth only
- `workspace_runtime/` owns workspace-bound execution only
- `model_manager/` owns model supply and agent model binding only
- `commands/` owns shared command semantics only
- `interfaces/` owns DTOs only
- `tui/` and `desktop/` own presentation only

## 6. Deletion Policy

The following categories are now deletion candidates rather than preserved seams:

### 6.1 Compatibility module families

- `src/mini_agent/application/legacy/`
- root compatibility re-export files in `application/`
- root compatibility re-export files in `runtime/`
- lazy wrapper and shim tests whose only purpose is protecting compatibility wrappers

### 6.2 Transitional session-first service owners

- `application/main_agent_surface_service.py`
- `application/session_service.py`
- compatibility-only session routing methods kept on agent/model services

### 6.3 Session-owned main model semantics

- `model_manager/session_selection_service.py`
- all active imports that preserve session-owned interpretation of main chat model binding

### 6.4 Session-owned run control semantics

- any remaining code path where control truth is reconstructed from session projection instead of real run state

## 7. New Canonical Owners To Build First

Before reconnecting all surfaces, the following real owners must exist as actual maintained modules.

### 7.1 `agent_core/contracts/`

Required concrete files:

- `agent_profile.py`
- `agent_instance.py`
- `run.py`
- `attachments.py`
- `capability_snapshot.py`
- `checkpoint.py`
- `execution_journal.py`
- `run_control_state.py`
- `approval_wait.py`

### 7.2 `application/user_services/`

Required concrete files:

- `agent_user_service.py`
- `workspace_user_service.py`
- `model_user_service.py`
- `command_user_service.py`

No legacy facade is allowed to remain the real surface anchor after this rewrite.

### 7.3 `application/use_cases/`

Required maintained owners:

- `agent_application_service.py`
- `agent_interaction_application_service.py`
- `run_control_application_service.py`
- `session_task_service.py`
- `workspace_application_service.py`
- `model_binding_application_service.py`
- `command_application_service.py`

### 7.4 `application/ports/`

Required active ports:

- `agent_runtime_port.py`
- `run_runtime_port.py`
- `workspace_runtime_port.py`
- `model_runtime_port.py`
- `session_task_port.py`

`SessionRuntimePort` is not part of the target active family.

### 7.5 `workspace_runtime/`

Required maintained owners:

- `boundary.py`
- `runtime_modes.py`
- `workspace_executor.py`
- `outside_zone_policy.py`
- `permission_table.py`
- `mutation_ledger.py`
- `snapshot_store.py`

This line must become authoritative for workspace-bound execution.

### 7.6 `model_manager/`

Required maintained owners:

- provider registry and preset providers
- model registry / discovery / capability probing
- `agent_model_service.py`
- `agent_model_binding.py`
- adapter construction and route diagnostics

No session-owned main model file remains active after this cut.

## 8. Hard Refactor Sequence

The repo should now be rewritten in the following order.

This order replaces the old compatibility-first staging mindset.

### Stage H1: Freeze and prune

Goal:

- stop all further investment into compatibility and transitional owners

Actions:

- freeze `v11.1` docs as the only authority
- stop editing compatibility wrappers except to delete them
- identify every active import of legacy/session-compat owners
- remove wrapper-protection tests that only defend deprecated compatibility shells

Completion rule:

- the repo has a deletion list for all non-target owners

### Stage H2: Materialize full kernel truth objects

Goal:

- create the real kernel object family first

Actions:

- implement `AgentProfile`
- implement `AgentInstance`
- implement `Run`
- implement `WorkspaceAttachment`
- implement `SessionAttachment`
- implement `CapabilitySnapshot`
- implement `Checkpoint`
- implement `ExecutionJournal`
- keep `RunControlState` and `ApprovalWait` as part of this family, not as isolated islands

Completion rule:

- agent core truth is represented by actual maintained contracts, not only by docs and scattered runtime state

### Stage H3: Rewrite runtime around the kernel contracts

Goal:

- make `runtime/` a host/orchestration layer only

Actions:

- cut `main_agent_runtime_manager.py` down to host orchestration
- route active execution state through real `AgentInstance + Run`
- route checkpoint and journal write points through kernel contracts
- make session runtime a consumer of run truth, not a fallback owner of execution truth

Completion rule:

- `runtime/` no longer defines what execution truth means

### Stage H4: Hard cut the application layer

Goal:

- remove facade-first and session-first application architecture

Actions:

- delete `MainAgentSurfaceService` as an active architecture concept
- delete `SessionApplicationService` as an active architecture concept
- delete `SessionRuntimePort` from the active path
- make surfaces consume only explicit user services
- make user services consume only explicit use cases
- make use cases consume only explicit runtime ports

Completion rule:

- there is no active path from surfaces into runtime via compatibility facades

### Stage H5: Hard cut model ownership

Goal:

- eliminate session-owned main model semantics completely

Actions:

- delete `session_selection_service.py`
- remove session-facing main model binding logic from TUI/Desktop/runtime/gateway active flow
- make all main model reads and writes route through `AgentModelService`
- keep feature-model design out of this main chain

Completion rule:

- main model binding is purely agent-owned everywhere

### Stage H6: Strengthen workspace domain and workspace runtime

Goal:

- make workspace a real first-class world, not only a path argument

Actions:

- create a stronger workspace domain model
- make `DefaultWorkspace` explicit as a real workspace kind
- route file/shell/code execution through `workspace_runtime/`
- make outside-zone policy and permission table the active enforcement path
- bind run attachment to workspace runtime explicitly

Completion rule:

- no active tool execution path bypasses workspace runtime ownership

### Stage H7: Rebuild surfaces on the cleaned service contract

Goal:

- reconnect TUI/Desktop/Remote only after the lower architecture is clean

Actions:

- delete surface-local business logic that assumes legacy facades
- rebind TUI to the new user services and run DTOs
- rebind Desktop to the new user services and run DTOs
- keep Remote as a thin extension surface over the same services
- keep command semantics centralized in `commands/`

Completion rule:

- surface modules contain presentation logic and local UI state only

### Stage H8: Memory, skills, and command normalization

Goal:

- finish the remaining foundational side systems so they stop carrying old mixed ownership

Actions:

- align memory to explicit `session / workspace / global` ownership
- enforce no automatic global promotion
- align skills to explicit `internal / global / workspace` ownership
- keep workspace skill creation explicit only
- finish `commands/` as the single shared command subsystem

Completion rule:

- side systems no longer hide ownership ambiguity behind convenience helpers

### Stage H9: Delete all remaining non-target owners

Goal:

- finish the hard cut completely

Actions:

- delete legacy modules
- delete compatibility wrappers
- delete shim-only tests
- delete obsolete imports and old route forms
- rewrite docs and tests to the final tree only

Completion rule:

- the physical repo no longer narrates two architectures at once

## 9. Acceptance Criteria

The hard alignment rewrite is complete only if all of the following are true:

- no active source code imports `application.legacy`
- no active source code imports compatibility wrapper modules as first-class owners
- no active source code depends on `SessionRuntimePort`
- no active source code depends on `session_selection_service.py`
- no active source code treats session as owner of run control
- no active source code treats session as owner of main model binding
- surfaces depend only on user services and typed transport clients
- `agent_core/contracts/` contains the full `v11.1` kernel object family
- `workspace_runtime/` is the only owner of workspace-bound execution enforcement
- `model_manager/` is the only owner of the main agent model binding chain
- `interfaces/` exposes explicit `agent / run / workspace / model / session` DTO families
- the repo tree itself visually reflects the architecture without requiring a compatibility explanation

## 10. Commit Strategy

Because this is now a hard refactor, commit slicing should follow ownership replacement, not compatibility layering.

Recommended slices:

1. create full kernel contracts
2. rewrite runtime host to those contracts
3. delete old application facades and session-first ports
4. cut model ownership over to agent-only
5. strengthen workspace runtime and permissions
6. reconnect gateway, TUI, Desktop, and Remote
7. normalize memory/skills/commands
8. delete the remaining obsolete files and tests

Bad slice:

- "compat cleanup"

The repo should move by replacement of owners, not by another round of wrapper management.

## 11. Immediate Execution Recommendation

The best next implementation step under this new rule is:

1. open `Stage H2`
2. create the missing kernel contracts as real files
3. immediately start shrinking `runtime/main_agent_runtime_manager.py` around those contracts

Why:

- the repo already spent enough time on staged compatibility cleanup
- the biggest remaining architectural gap is still the missing concrete kernel object family
- until those objects are real, every later rewrite risks growing from the wrong owner again

## 12. Final Rule

From this point onward, the project does not ask:

- how do we preserve the current mixed architecture while migrating slowly

It asks:

- what code must remain so the repo is structurally and semantically equal to `v11.1`

Anything that does not serve that final state is now a deletion candidate.
