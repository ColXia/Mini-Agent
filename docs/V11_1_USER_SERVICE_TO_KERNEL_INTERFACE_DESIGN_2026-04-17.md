# Mini-Agent v11.1 User Service To Kernel Interface Design

> Status: discussion baseline
> Date: 2026-04-17
> Scope: user service boundary / application service split / runtime port direction / surface-to-kernel interaction contract
> Related:
> - [V11_1_USER_SURFACE_ARCHITECTURE_2026-04-17.md](./V11_1_USER_SURFACE_ARCHITECTURE_2026-04-17.md)
> - [V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md](./V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md)
> - [V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md](./V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md)
> - [V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md](./V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md)
> - [V11_1_MODULE_OWNERSHIP_AND_MIGRATION_DIRECTION_2026-04-17.md](./V11_1_MODULE_OWNERSHIP_AND_MIGRATION_DIRECTION_2026-04-17.md)
> - [V11_1_TRANSPORT_DTO_AND_READ_MODEL_CONTRACT_2026-04-17.md](./V11_1_TRANSPORT_DTO_AND_READ_MODEL_CONTRACT_2026-04-17.md)
> - [V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md](./V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md)
> - [ARCHITECTURE.md](./ARCHITECTURE.md)
> - [FRAMEWORK_SKELETON.md](./FRAMEWORK_SKELETON.md)

## 1. Purpose

This document freezes the fourth `v11.1` architecture slice:

- how user-facing services, application-layer services, and runtime/kernel ports should connect

It answers one practical question:

- once the kernel truth objects are clear, what should TUI, Desktop, Remote, and the shared command subsystem actually call

This document is important because the project already has useful application-layer code, but the target interface shape is still not fully frozen.

## 2. Why This Slice Matters

The previous slices already locked:

- kernel truth objects
- run / attachment / checkpoint / journal execution truth
- run control and agent-instance lifecycle truth

The next instability point is interface drift between:

- user surfaces
- user services
- application services
- runtime manager / runtime ports

If this slice is not explicitly locked:

- surfaces will keep reaching into runtime objects directly
- `MainAgentSurfaceService` may continue growing into a new monolith
- session-centric compatibility APIs will silently redefine the target architecture
- model selection and run control will keep leaking back into session-owned pathways

So this slice exists to define the maintained interface chain from user surfaces down to the kernel.

## 3. Current Repo Pressure

Current repo already contains useful pieces:

- `src/mini_agent/application/main_agent_surface_service.py`
- `src/mini_agent/application/session_service.py`
- `src/mini_agent/application/session_runtime_port.py`

These are valuable, but they still reflect an earlier session-centric runtime framing.

Examples:

- `MainAgentSurfaceService` is already acting as a shared cross-surface gateway
- `SessionApplicationService` is already a real application-layer service, but it still exposes many operations through session as the main carrier
- `SessionRuntimePort` is still a session-centered port, while later target architecture needs clearer `agent / run / workspace / model` service faces

This document does not reject these files.
It repositions them as transitional structures that should evolve toward the target interface model.

## 4. Maintained Interface Topology

`v11.1` now freezes the following interface stack:

```text
User Surfaces
  - TUI
  - Desktop
  - Remote Interaction

Shared Interaction Subsystem
  - Command Subsystem

User Service Layer
  - AgentUserService
  - WorkspaceUserService
  - ModelUserService
  - CommandUserService

Application / Use-Case Layer
  - AgentApplicationService
  - RunControlApplicationService
  - SessionTaskService
  - WorkspaceApplicationService
  - ModelBindingApplicationService
  - CommandApplicationService

Runtime / Kernel Ports
  - AgentRuntimePort
  - RunRuntimePort
  - WorkspaceRuntimePort
  - ModelRuntimePort
  - SessionTaskPort

Runtime / Core
  - AgentInstance / Run Kernel
  - WorkspaceRuntime
  - ModelPool + AgentModelService
  - Permission / Approval / Context / Memory / Skill subsystems
```

Core rule:

- surfaces do not talk to runtime/core directly
- surfaces talk to user services
- user services orchestrate application services
- application services talk to explicit runtime ports

## 5. User Service Layer Is The Stable Surface Contract

The user service layer is the stable contract that TUI, Desktop, and Remote should rely on.

It exists to:

- keep surfaces thin
- expose user-facing modules instead of internal runtime topology
- absorb compatibility differences across TUI/Desktop/Remote
- avoid direct runtime-manager dependency in surfaces

It must not become:

- the owner of durable truth
- a second runtime manager
- a generic "do everything" surface bus

## 6. AgentUserService

`AgentUserService` is the primary user-facing service.

It should be the main user-side anchor because the user primarily interacts with the agent, not with raw runtime internals.

Owns user-facing operations such as:

- current agent summary
- current agent instance state
- active run summary
- execution entrypoints
- run control actions
- approval action entrypoints
- agent-oriented diagnostics that are meaningful to users

Recommended command set:

- `get_current_agent()`
- `get_agent_runtime_summary()`
- `submit_message(...)`
- `start_run(...)`
- `interrupt_run(...)`
- `resume_run(...)`
- `cancel_run(...)`
- `approve_wait(...)`
- `deny_wait(...)`

Must not own:

- workspace durable truth
- model catalog truth
- session archive truth

But it may orchestrate:

- session task selection
- workspace attachment preparation
- model capability resolution for display

## 7. WorkspaceUserService

`WorkspaceUserService` is the user-facing environment service.

Owns:

- current workspace summary
- workspace list / open / create / switch
- workspace policy summaries
- workspace memory / skill / archive browse entrypoints
- workspace runtime health summaries

Recommended command set:

- `list_workspaces()`
- `get_current_workspace()`
- `open_workspace(...)`
- `create_workspace(...)`
- `switch_workspace(...)`
- `get_workspace_memory_summary(...)`
- `get_workspace_skill_summary(...)`
- `get_workspace_runtime_summary(...)`

Critical rule:

- workspace switching is environment orchestration
- it does not redefine agent ownership
- if a run is active, switch logic must respect run-control and attachment rules instead of silently rebinding live execution

## 8. ModelUserService

`ModelUserService` is the user-facing main-model service for the agent side.

Owns:

- current agent model binding display
- model candidate listing
- capability fact display
- main model binding change
- provider/model diagnostics relevant to user decisions

Recommended command set:

- `get_current_model_binding()`
- `list_model_candidates()`
- `set_agent_model_binding(...)`
- `probe_model_capabilities(...)`
- `get_model_binding_diagnostics()`

Critical rule:

- this service talks to the agent-facing main model system
- it does not make `Session` the owner of main model binding
- it does not make `Workspace` the owner of main model binding

Compatibility note:

- current session-centric model selection interfaces may remain temporarily in the repo
- but they should be treated as compatibility shims, not as the target architecture baseline

## 9. CommandUserService

`CommandUserService` is the shared user-facing command entry service.

Owns:

- `/` command parsing entry
- command dispatch
- command discoverability metadata
- command completion metadata
- command feedback contract for surfaces

Recommended command set:

- `parse_command(...)`
- `execute_command(...)`
- `list_commands(...)`
- `complete_command(...)`
- `describe_command(...)`

Critical rule:

- command semantics are shared
- surfaces may render command UX differently
- surfaces must not redefine command meaning independently

## 10. Application Layer Beneath User Services

The user service layer should sit above explicit application/use-case services.

These services are not presentation modules.
They are shared business orchestration modules.

Recommended split:

- `AgentApplicationService`
- `RunControlApplicationService`
- `SessionTaskService`
- `WorkspaceApplicationService`
- `ModelBindingApplicationService`
- `CommandApplicationService`

## 11. AgentApplicationService

This service owns shared agent-facing use cases.

Owns:

- agent summary assembly
- active run summary assembly
- submit-message to run-entry orchestration
- run-start use cases
- read models combining agent instance, run, workspace attachment, and model binding

Must talk to:

- `AgentRuntimePort`
- `RunRuntimePort`
- `SessionTaskPort`
- `ModelRuntimePort`

It should not reach directly into surface state.

## 12. RunControlApplicationService

This service owns operator-facing run control use cases.

Owns:

- interrupt use case
- resume use case
- cancel use case
- approve / deny use case
- control-state query

This service must resolve control targets against:

- `run_id`
- `approval_wait_id` or approval token

Compatibility rule:

- if a request arrives with `session_id`, this service may resolve the active run from that session
- but control truth remains run-owned

## 13. SessionTaskService

This service owns task/session use cases.

Owns:

- create / list / rename / fork / archive session
- session read models
- session transcript access
- session task memory access
- session-local context policy operations

Important:

- session remains a real business subdomain
- but it is no longer the universal carrier for all agent/workspace/model/control operations

This is how the project keeps session truth without letting it swallow the whole architecture.

## 14. WorkspaceApplicationService

This service owns environment-side use cases.

Owns:

- workspace validation
- workspace creation/open
- workspace switching orchestration
- workspace-level summaries and inventories
- runtime-boundary preparation for future attachment flows

It should not become:

- the owner of main agent model binding
- the owner of run control truth

## 15. ModelBindingApplicationService

This service owns main model binding use cases for the agent side.

Owns:

- resolve main model candidates
- set agent default binding
- set agent-instance binding override if that concept is later supported
- expose capability facts to user services

Critical rule:

- session may participate in context for a run
- session does not own main model binding

This service is the explicit architectural correction for the earlier session-centric model pathway.

## 16. CommandApplicationService

This service owns shared command use cases.

Owns:

- command grammar execution
- command-to-service routing
- command result normalization
- cross-surface command semantics

It should route into:

- `AgentUserService`
- `WorkspaceUserService`
- `ModelUserService`
- `SessionTaskService`
- `RunControlApplicationService`

This keeps command semantics centralized without making command parsing the owner of runtime truth.

## 17. Runtime Port Direction

The runtime port layer should stop exposing only session-centered protocols.

Target runtime-port family:

- `AgentRuntimePort`
- `RunRuntimePort`
- `WorkspaceRuntimePort`
- `ModelRuntimePort`
- `SessionTaskPort`

Current repo note:

- `SessionRuntimePort` is useful as a transitional port
- but it should no longer define the long-term architecture alone

## 18. Transitional Mapping For Current Repo

Current files can be mapped as follows:

- `MainAgentSurfaceService` -> transitional cross-surface facade
- `SessionApplicationService` -> transitional `SessionTaskService`-leaning application service
- `SessionRuntimePort` -> transitional session/task runtime port

Recommended target direction:

- keep `MainAgentSurfaceService` thin
- do not let it absorb new business modules directly
- move user-facing responsibilities toward explicit `AgentUserService / WorkspaceUserService / ModelUserService / CommandUserService`
- move shared orchestration toward explicit application services instead of widening session runtime paths

## 19. Compatibility Rules For Existing Session-Centric APIs

The current repo already has session-centric operations such as:

- cancel session turn
- respond to approval by session
- update session model selection

`v11.1` freezes the following interpretation:

- session-centric control APIs are compatibility forms, not target truth forms
- a session-centric cancel call should resolve the active run and then cancel the run
- a session-centric approval call should resolve the active approval wait under the run
- a session-centric model-selection call should be treated as transitional and later migrated toward agent-level main-model binding

This rule allows the repo to keep working while preventing compatibility endpoints from becoming target architecture.

## 20. Surface Integration Rule

All primary surfaces must integrate through the same user-service contracts.

Examples:

- TUI may show denser run and approval details
- Desktop may show cleaner module pages and control affordances
- Remote may expose a narrower set of controls

But all of them should still rely on the same service-level operations and truth mapping.

This avoids:

- TUI-only semantics
- Desktop-only hidden business logic
- Remote-specific shadow runtime flows

## 21. Query / Command Split Recommendation

User services should expose two kinds of APIs:

- query-oriented read models
- command-oriented mutations or control actions

Examples:

- query: `get_agent_runtime_summary()`
- query: `list_model_candidates()`
- query: `get_workspace_runtime_summary()`
- command: `submit_message(...)`
- command: `interrupt_run(...)`
- command: `set_agent_model_binding(...)`
- command: `switch_workspace(...)`

This recommendation matters because mixing reads and writes into one generic surface method usually recreates hidden service monoliths.

## 22. Anti-Drift Rules

The following are now explicitly disallowed:

- surfaces calling runtime manager directly as their main architecture path
- widening `MainAgentSurfaceService` into a new all-purpose business monolith
- treating `SessionRuntimePort` as the final interface model for all future work
- putting main model binding back under session ownership
- adding run-control truth directly into surface state or session projection state
- letting each surface invent its own command semantics

## 23. Immediate Direction For Current Repo

The current repo should treat the following as the near-term direction:

- preserve current application layer, but narrow its conceptual ownership
- treat `SessionApplicationService` as the session/task branch, not the final user-service map
- introduce explicit user-service modules before continuing major surface expansion
- migrate control and model operations toward run-owned and agent-owned truth even if compatibility routes still mention session externally

This document is not the implementation plan.
It is the interface rulebook that later implementation should follow.
