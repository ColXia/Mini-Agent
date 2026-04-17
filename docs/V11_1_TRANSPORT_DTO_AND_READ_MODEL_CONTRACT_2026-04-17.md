# Mini-Agent v11.1 Transport DTO And Read-Model Contract

> Status: discussion baseline
> Date: 2026-04-17
> Scope: transport boundary / DTO ownership / internal projection ownership / read-model contract / raw-payload compatibility rule
> Related:
> - [API_V1_CONTRACT_SKELETON.md](./API_V1_CONTRACT_SKELETON.md)
> - [V11_1_USER_SERVICE_TO_KERNEL_INTERFACE_DESIGN_2026-04-17.md](./V11_1_USER_SERVICE_TO_KERNEL_INTERFACE_DESIGN_2026-04-17.md)
> - [V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md](./V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md)
> - [V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md](./V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md)
> - [V11_1_MODULE_OWNERSHIP_AND_MIGRATION_DIRECTION_2026-04-17.md](./V11_1_MODULE_OWNERSHIP_AND_MIGRATION_DIRECTION_2026-04-17.md)
> - [FRAMEWORK_SKELETON.md](./FRAMEWORK_SKELETON.md)

## 1. Purpose

This document freezes the sixth `v11.1` architecture slice:

- the contract between runtime read models, interface DTOs, and transport payloads

It answers one practical question:

- how should Mini-Agent represent user-facing data once it leaves kernel/runtime truth and becomes something that surfaces or transports consume

This slice matters because the project already has all three shapes in the repo:

- core/runtime truth
- internal projection/read models
- external transport DTOs

But the boundaries between them still need to be frozen more explicitly.

## 2. The Four Shape Rule

`v11.1` now freezes a four-shape rule:

- `Core Truth Object`
- `Internal Projection / Read Model`
- `Interface DTO`
- `Raw Transport Payload`

These four shapes are not interchangeable.

The architecture must stop treating them as if they were all just different names for the same object.

## 3. Shape Definitions

### 3.1 Core Truth Object

Core truth objects are the real owners of durable or runtime truth.

Examples:

- `AgentInstance`
- `Run`
- `RunControlState`
- `ApprovalWait`
- `Checkpoint`
- `ExecutionJournal`
- `Session`
- `Workspace`

Properties:

- authoritative
- not transport-shaped
- not surface-shaped
- may contain semantics that should never be exposed directly

### 3.2 Internal Projection / Read Model

Internal projections are runtime/application-side shaped views built from truth objects.

Examples already present in repo:

- `SessionSummaryProjection`
- `SessionDetailProjection`
- `SessionMessageProjection`
- `SessionPendingApprovalProjection`
- `SessionRecoveryProjection`

Properties:

- derived, not authoritative
- stable enough for shared application/runtime use
- shaped for reading and presentation
- still internal to the repo architecture

### 3.3 Interface DTO

Interface DTOs are the canonical transport-facing typed contract.

Examples already present in repo:

- `MainAgentSessionSummary`
- `MainAgentSessionDetail`
- `MainAgentSessionMessage`
- `MainAgentSessionPendingApproval`
- `MainAgentSessionRecoverySnapshot`

Properties:

- typed
- stable contract at the API/transport boundary
- surface-safe and transport-safe
- should not leak internal runtime truth details

### 3.4 Raw Transport Payload

Raw transport payloads are untyped dictionaries, JSON maps, or protocol-specific envelopes moving through clients/transports.

Examples already present in repo:

- `RemoteSessionTransportPort` returning `dict[str, Any]`
- generic JSON responses before DTO validation
- SSE chunk payloads before client-side normalization

Properties:

- compatibility-oriented
- transport-specific
- not authoritative
- should be normalized into DTOs quickly

## 4. The Required Conversion Chain

The maintained conversion chain should be:

```text
Core Truth
  -> Internal Projection / Read Model
  -> Interface DTO
  -> Raw Transport Serialization
```

And for clients:

```text
Raw Transport Payload
  -> Interface DTO
  -> Surface View Model
```

Critical rule:

- transport must not become the place where business truth is reconstructed from scratch

## 5. Current Repo Interpretation

Current repo already shows the right pieces:

- `src/mini_agent/runtime/session_read_model_builder.py`
  - builds internal session projections
- `src/mini_agent/interfaces/agent.py`
  - defines canonical typed transport DTOs
- `src/mini_agent/transport/session_transport_port.py`
  - still uses raw `dict[str, Any]` contracts

This means the current architecture is part-correct, but not fully frozen.

The missing frozen rule is:

- `dict[str, Any]` is a transport compatibility shape, not the target service contract shape

## 6. Ownership Rules

`agent_core/` and `runtime/` own:

- truth objects
- runtime control objects
- internal projection assembly inputs

`session/` and `runtime/` may jointly own:

- projection builders
- read-model assembly helpers

`interfaces/` owns:

- transport-facing DTOs

`transport/` owns:

- serialization / deserialization
- protocol client normalization
- payload exchange mechanics

Critical rule:

- `interfaces/` owns DTOs
- `transport/` does not own the meaning of those DTOs

## 7. DTOs Must Not Become Truth Objects

The project must now explicitly reject a very common drift pattern:

- taking a DTO class and treating it as if it were the real domain or runtime truth object

Examples of what must not happen:

- `MainAgentSessionSummary` becoming the real owner of session runtime truth
- `MainAgentSessionPendingApproval` becoming the only approval truth object
- API response envelopes becoming the main source of execution-state interpretation

DTOs are representations.
They are not owners.

## 8. Projections Must Not Become Kernel Truth

Internal projections are closer to truth than DTOs, but they are still not truth owners.

For example:

- a `SessionSummaryProjection` may include busy state, pending approvals, and selected model display fields
- but that does not make the projection the owner of run control, approval truth, or model binding truth

This matters because projections are often the easiest place to add “just one more field”.
That is how hidden truth duplication begins.

## 9. Transport Payloads Must Normalize Quickly

`v11.1` now freezes a normalization rule:

- raw payloads should be normalized into interface DTOs as close to transport ingress as practical

This means:

- client code should not carry `dict[str, Any]` deep into user service logic
- remote adapters should not reason over arbitrary payload maps longer than necessary
- DTO validation should happen early

Current repo note:

- `RemoteSessionClient` already converts payloads into typed models
- that direction is correct
- `RemoteSessionTransportPort` still using raw dicts is acceptable as a transport port, but it should not become the wider service-contract pattern

## 10. Query Models Versus Command Results

`v11.1` recommends separating DTOs into:

- read/query DTOs
- command/mutation result DTOs

Examples of read/query DTOs:

- `MainAgentSessionSummary`
- `MainAgentSessionDetail`
- `MainAgentSessionMessage`

Examples of command/mutation DTOs:

- `MainAgentSessionMutationResponse`
- `MainAgentSessionApprovalResponse`
- `MainAgentSessionControlResponse`
- `MainAgentSessionRuntimePolicyResponse`

This split is useful because:

- read DTOs should emphasize stable presentation facts
- command DTOs should emphasize action result, applied state, and next-step guidance

## 11. Read Models Must Stay Surface-Neutral

Internal projections and interface DTOs should be surface-neutral by default.

This means:

- TUI may render more fields
- Desktop may hide or regroup fields
- Remote may expose a reduced subset

But the shared DTO/read-model meaning should remain the same.

What must not happen:

- TUI-only DTOs containing TUI rendering assumptions
- Desktop-only business DTOs that redefine shared semantics
- Remote-only payload semantics that bypass the shared model

## 12. Session-Centric DTO Reality And Correction

Current repo's main-agent DTOs are still strongly session-centered.

That is understandable historically, but `v11.1` freezes the following correction:

- session DTOs remain valid as task-facing transport DTOs
- but future agent/run/workspace/model-oriented DTO families should be allowed to emerge explicitly

Recommended future DTO families:

- `agent` DTOs for agent summary and instance state
- `run` DTOs for active execution and control state
- `workspace` DTOs for environment summaries
- `model` DTOs for binding and capability displays
- `session` DTOs for task truth and transcript views

This does not require immediate rewrite.
It simply stops the session DTO family from becoming the only representational worldview.

## 13. Pending Approval DTO Rule

Current transport DTO:

- `MainAgentSessionPendingApproval`

`v11.1` interpretation:

- this is a transport-facing approval view
- it is not the durable approval truth object
- the durable truth object is the run-owned `ApprovalWait`

This distinction is especially important for restart, recovery, and control semantics.

## 14. Recovery Snapshot DTO Rule

Current transport DTO:

- `MainAgentSessionRecoverySnapshot`

`v11.1` interpretation:

- this is a compact user-facing recovery view
- it is not the same as checkpoint truth
- it is not a substitute for execution journal

That means:

- recovery DTOs may summarize
- checkpoints restore
- journals explain

These are three different responsibilities.

## 15. API Contract Rule

The existing `API_V1_CONTRACT_SKELETON` rule remains valid:

- frontend consumes `/api/v1/*`
- router layer uses interface DTOs from `mini_agent/interfaces/*`

`v11.1` adds:

- DTOs must be derived from shared application/runtime read models
- raw transport shapes must not become the real contract
- contract expansion should follow corrected architecture domains, not only session history

## 16. Remote Transport Port Rule

Current `RemoteSessionTransportPort` is dict-shaped.

`v11.1` interpretation:

- this is acceptable as a low-level transport seam
- it is not the desired shape for higher service contracts

Recommended direction:

- keep transport ports raw and protocol-friendly if needed
- normalize immediately into DTOs in transport clients
- keep user services and application services typed

This preserves flexibility without spreading raw payload handling everywhere.

## 17. DTO Evolution Rule

When a new field needs to be exposed:

1. identify the truth owner first
2. decide whether it belongs in an internal projection
3. decide whether it belongs in a public DTO
4. only then add it to transport or client code

This order matters.

Bad pattern:

- "the surface wants a field, so add it to the response first and figure out ownership later"

That pattern recreates truth drift very quickly.

## 18. Anti-Drift Rules

The following are now explicitly disallowed:

- treating raw transport payloads as stable business contracts
- skipping DTO normalization and leaking `dict[str, Any]` into user services
- letting DTO classes become the owner of runtime truth
- letting projection classes become kernel truth
- using recovery DTOs as if they were checkpoints
- using approval DTOs as if they were approval-control truth

## 19. Immediate Direction For Current Repo

The near-term direction should be:

- keep existing interface DTO package as the typed transport contract
- continue using runtime/application read-model builders as the source for DTO assembly
- treat dict-shaped transport ports as low-level compatibility seams only
- gradually expand DTO families beyond session-only worldview as agent/run/workspace/model user services become real

This document is not an execution checklist.
It is the transport/read-model rulebook that later implementation should follow.
