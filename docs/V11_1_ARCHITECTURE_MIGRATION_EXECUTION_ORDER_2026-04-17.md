# Mini-Agent v11.1 Architecture Migration Execution Order

> Status: discussion baseline
> Date: 2026-04-17
> Scope: migration order / dependency ordering / compatibility boundaries / staged rollout direction
> Related:
> - [V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md](./V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md)
> - [V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md](./V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md)
> - [V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md](./V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md)
> - [V11_1_USER_SERVICE_TO_KERNEL_INTERFACE_DESIGN_2026-04-17.md](./V11_1_USER_SERVICE_TO_KERNEL_INTERFACE_DESIGN_2026-04-17.md)
> - [V11_1_MODULE_OWNERSHIP_AND_MIGRATION_DIRECTION_2026-04-17.md](./V11_1_MODULE_OWNERSHIP_AND_MIGRATION_DIRECTION_2026-04-17.md)
> - [V11_1_TRANSPORT_DTO_AND_READ_MODEL_CONTRACT_2026-04-17.md](./V11_1_TRANSPORT_DTO_AND_READ_MODEL_CONTRACT_2026-04-17.md)
> - [ARCHITECTURE_EXECUTION_GUARDRAILS_2026-04-17.md](./ARCHITECTURE_EXECUTION_GUARDRAILS_2026-04-17.md)
> - [P32B_REPO_HYGIENE_AND_STRUCTURE_ALIGNMENT_PLAN_2026-04-16.md](./P32B_REPO_HYGIENE_AND_STRUCTURE_ALIGNMENT_PLAN_2026-04-16.md)

## 1. Purpose

This document freezes the seventh `v11.1` architecture slice:

- migration execution order

It answers one practical question:

- in what order should the repo evolve from the current mostly session-centric runtime/application shape toward the corrected `v11.1` architecture

This is not a ticket list.
It is the ordering rulebook.

## 2. Migration Principle

The migration principle is:

- freeze truth first
- add seams second
- shift ownership third
- remove compatibility last

This ordering matters because the project already has a lot of working code.
The goal is not to win a rewrite.
The goal is to move truth ownership without breaking the real runtime path.

## 3. What Must Not Happen

The following migration patterns are explicitly disallowed:

- big-bang rewrite of `MainAgentRuntimeManager`
- big-bang rewrite of all session APIs before run-owned replacements exist
- introducing new user-surface logic while kernel/service ownership is still moving underneath
- deleting compatibility session paths before agent/run/workspace/model service faces are usable
- adding more behavior into transitional owners during migration

## 4. Stage 0: Freeze Architecture Baseline

This stage is now materially done by the `v11.1` doc set.

Purpose:

- stop architectural ambiguity before code movement starts

Locked outputs:

- kernel truth contract
- run/attachment/checkpoint/journal contract
- run control and agent lifecycle contract
- user-service interface contract
- module ownership contract
- DTO/read-model contract

No major implementation migration should start before these contracts exist.

## 5. Stage 1: Add New Contracts Without Changing Behavior

First code-facing migration stage:

- introduce missing types, ports, and adapter seams
- do not yet rewrite the runtime behavior deeply

Examples:

- add run-owned control models
- add agent/run/workspace/model runtime ports alongside session-centric ports
- add new read-model families if needed
- add compatibility resolution helpers from `session_id -> active run`

Purpose:

- create landing zones for later moves
- avoid coupling every later change to one large rewrite branch

## 6. Stage 2: Move Control Truth Out Of Session Runtime

This is the first real truth-move stage.

Target:

- `cancel_event`, approval state, and related control truth stop being conceptually owned by `session.runtime`

Order:

1. introduce run-owned control state
2. introduce `ApprovalWait`
3. keep session projection fields as compatibility read models
4. switch handlers to resolve through run-owned control truth
5. leave session-facing APIs temporarily intact

Critical rule:

- do not delete session-facing compatibility yet
- first make session-facing paths resolve through the new truth owners

## 7. Stage 3: Introduce Explicit User-Service Layer

Once run/control truth has a real landing zone, introduce explicit user services.

Target services:

- `AgentUserService`
- `WorkspaceUserService`
- `ModelUserService`
- `CommandUserService`

Order:

1. create user-service shells over existing application/runtime paths
2. make surfaces depend on the new service contracts
3. keep `MainAgentSurfaceService` as a compatibility facade
4. stop adding new business modules directly into `MainAgentSurfaceService`

Purpose:

- stabilize the surface contract before deeper domain reshaping continues

## 8. Stage 4: Reposition `SessionApplicationService`

After user services exist, `SessionApplicationService` should be reinterpreted and narrowed.

Target role:

- `SessionTaskService`-leaning service

Order:

1. move new agent/workspace/model/control use cases elsewhere
2. keep session/task use cases in `SessionApplicationService`
3. optionally rename or wrap later

Critical rule:

- do not split it just because it is broad
- split by ownership shift, not by file-size discomfort

## 9. Stage 5: Expand Runtime Port Family

After application/user-service roles become clearer, expand runtime ports.

Target port family:

- `AgentRuntimePort`
- `RunRuntimePort`
- `WorkspaceRuntimePort`
- `ModelRuntimePort`
- `SessionTaskPort`

Migration rule:

- keep `SessionRuntimePort` as transitional
- stop treating it as the final contract
- route new capability through the correct new ports first

## 10. Stage 6: Establish `workspace_runtime/`

Once run ownership and service boundaries are clearer, establish the dedicated workspace runtime module.

Target ownership:

- execution boundary
- mounted runtime mode
- outside-zone handling
- mutation ledger
- reversibility hooks

Why not earlier:

- if introduced too early, it risks becoming another large undefined bucket
- it should be shaped after run/attachment/control semantics are frozen

## 11. Stage 7: Correct Model Binding Path

After services and ports exist, move main model binding fully toward agent-owned truth.

Order:

1. preserve current session-facing model-selection compatibility
2. add agent-facing model binding flow
3. resolve old session path through the new model-binding service where needed
4. deprecate the session-owned interpretation

Critical rule:

- this stage is about main model binding only
- feature-model systems remain separate and should not be mixed into this migration

## 12. Stage 8: Expand DTO Families Beyond Session-Only View

Once service and truth ownership are corrected, transport/read-model contracts can evolve more honestly.

Target DTO families:

- `agent`
- `run`
- `workspace`
- `model`
- `session`

Order:

1. keep current session DTOs working
2. introduce new DTO families for new services
3. do not force a full endpoint rewrite in one cut

Purpose:

- stop transport shape from staying permanently session-only

## 13. Stage 9: Surface Migration

Only after user-service and DTO layers are stable should the major surface migrations deepen.

Targets:

- TUI command and projection cleanup
- Desktop module wiring to explicit user services
- Remote interaction reuse of the same service contract

Critical rule:

- surface refactors should consume the corrected service contract
- they should not define the contract themselves

This stage is where large TUI/desktop cleanup becomes much safer.

## 14. Stage 10: Compatibility Reduction

Only after the new truth path is actively used should compatibility layers be reduced.

Possible removals later:

- session-centric control ownership assumptions
- session-owned model-binding interpretation
- raw dict-heavy transport patterns beyond low-level ports
- broad transitional surface facades if they no longer add value

Critical rule:

- compatibility is removed last
- not first

## 15. Recommended Parallelism

The following can overlap carefully:

- Stage 1 type/port introduction
- Stage 3 user-service shell introduction
- Stage 8 DTO family expansion

The following should not overlap aggressively:

- Stage 2 control truth migration
- Stage 6 workspace runtime establishment
- Stage 7 model-binding ownership correction

These three affect truth ownership directly and should stay narrow.

## 16. Testing Rule During Migration

During migration:

- keep behavior-compatible tests green first
- add seam tests for new ports/services
- only then move heavier integration coverage

Recommended test emphasis by stage:

- Stage 1: seam tests
- Stage 2: control/approval/cancel/recovery tests
- Stage 3: surface-service contract tests
- Stage 7: model-binding correctness tests
- Stage 9: TUI/Desktop integration tests

## 17. Commit Slicing Rule

Migration commits should follow ownership and stage boundaries.

Good slices:

- add new run-control models
- add new runtime ports
- add `AgentUserService` shell
- switch one compatibility path to new ownership
- add one DTO family

Bad slice:

- "architecture cleanup"

The migration should remain reviewable and reversible.

## 18. Current Repo Immediate Next Recommendation

The best immediate code-direction after the `v11.1` architecture freeze is:

1. Stage 1
2. then Stage 2
3. then Stage 3

In practical terms:

- first add missing contracts and ports
- then move control truth out of session runtime
- then stand up explicit user services

This is the narrowest route that reduces future drift fastest without forcing a rewrite.

## 19. Final Rule

When in doubt during migration, prefer this priority order:

1. preserve real runtime behavior
2. move truth ownership downward to the correct layer
3. keep compatibility at the boundary
4. remove compatibility only after the new path is real

This document is not a task board.
It is the ordering contract for future architecture migration work.
