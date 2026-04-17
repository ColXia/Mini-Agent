# Mini-Agent v11.1 Agent Kernel Contract Design

> Status: discussion baseline
> Date: 2026-04-17
> Scope: agent kernel contract / instance truth / run truth / attachment truth / checkpoint / execution journal
> Related:
> - [V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md](./V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md)
> - [V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md](./V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md)
> - [V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md](./V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md)
> - [V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md](./V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md)
> - [V11_1_USER_SURFACE_ARCHITECTURE_2026-04-17.md](./V11_1_USER_SURFACE_ARCHITECTURE_2026-04-17.md)
> - [AGENT_CORE_RUNTIME_SEAMS.md](./AGENT_CORE_RUNTIME_SEAMS.md)

## 1. Purpose

This document freezes the first design group after `v11.1`:

- the agent kernel contract

It answers one practical question:

- what are the real kernel-side objects that later user services, workspace services, model services, TUI, Desktop, and remote surfaces should talk to

This document exists because the project has already corrected the outer architecture baseline, but the inner runtime truth still needs a stricter contract.

## 2. Why This Slice Comes Before More User-Service Design

The next service split cannot stay stable unless the kernel truth is explicit first.

Without this contract, later modules will drift into one of the following failure modes:

- `Session` becomes the accidental owner of execution truth
- `Agent` becomes a giant object again and absorbs runtime, policy, and attachment state
- surfaces call whichever runtime helper is easiest to reach
- model switching, approval, interrupt, recovery, and workspace binding end up targeting different truth objects

So the first priority after `v11.1` is not another UI/service split.
The first priority is to define the kernel truth objects clearly enough that later services know which object they are operating on.

## 3. Current Code Pressure That Makes This Necessary

Current code already shows the pressure points:

- `src/mini_agent/agent_core/engine.py` still carries a large monolithic `Agent` facade that mixes capability, runtime loop, and runtime dependencies
- `src/mini_agent/runtime/session_state.py` still lets session runtime state directly host `agent`, `cancel_event`, and pending approval wait state
- `src/mini_agent/agent_core/runtime_bindings.py` already shows the right direction by externalizing runtime binding and service attachment, but it is not yet elevated into the full kernel contract
- `src/mini_agent/runtime/main_agent_runtime_manager.py` still carries too much orchestration pressure because the true kernel-side ownership line is not explicit enough

The purpose of this design is not to reject current code.
It is to stop future work from widening these seams again.

## 4. Kernel Truth Model

`v11.1` now freezes the following statement:

- `AgentProfile` defines what the agent is
- `AgentInstance` defines the persistent execution subject
- `Run` defines one formal execution unit
- `WorkspaceAttachment` and `SessionAttachment` define what the run is currently bound to
- `CapabilitySnapshot` defines the resolved capability view consumed by one run
- `Checkpoint` defines a recoverable kernel anchor
- `ExecutionJournal` defines the append-only execution fact stream

These objects are not optional implementation details.
They are the maintained runtime truth model.

## 5. First-Class Kernel Objects

## 5.1 AgentProfile

`AgentProfile` is the static identity and capability definition.

Owns:

- `agent_profile_id`
- stable role / identity metadata
- built-in tool catalog declaration
- built-in internal skill declaration
- default model-routing intent
- stable behavior defaults
- static capability hints such as approval, long-task, recovery, or background-execution support

Does not own:

- current workspace
- current session
- current run
- pending approvals
- checkpoint cursor
- journal cursor
- live provider clients

Practical meaning:

- `AgentProfile` answers "what this agent is by design"

## 5.2 AgentInstance

`AgentInstance` is the persistent execution subject.

Owns:

- `agent_instance_id`
- linked `agent_profile_id`
- lifecycle state
- current active `run_id` if any
- current attachment metadata
- checkpoint head
- journal head
- interrupt / resume / cancel state
- pending wait state such as approval or pause
- minimum durable instance metadata required for restore

Does not own:

- workspace filesystem implementation
- workspace memory implementation
- session transcript history
- MCP implementation
- RAG implementation
- model provider client objects

Practical meaning:

- `AgentInstance` answers "what this agent execution subject is doing now"

Locking rule:

- baseline `v11.1` design allows only one active run per `AgentInstance`

This restriction is intentional.
It avoids premature parallel-run complexity while the core boundary is still being normalized.

## 5.3 Run

`Run` is one formal execution unit.

Owns:

- `run_id`
- `agent_instance_id`
- `workspace_id`
- `session_id`
- trigger source
- current phase
- current status
- step cursor
- waiting reason
- capability snapshot reference
- checkpoint reference
- journal span / correlation id
- terminal result

Does not own:

- the whole session record
- workspace durable state
- agent identity definition
- live tool implementations

Practical meaning:

- `Run` answers "this concrete execution is currently at which step and in what state"

Locking rule:

- one `Run` binds to one workspace and one session for its whole lifetime
- cross-workspace transfer or cross-session rebinding may happen between runs, not inside one run

## 5.4 WorkspaceAttachment

`WorkspaceAttachment` expresses the execution-world binding.

Owns:

- `workspace_id`
- runtime root boundary
- `workspace_runtime_id` or equivalent binding reference
- outside-zone policy reference
- workspace permission-table reference
- execution mode such as `direct / container_mounted / isolated_copy`

Does not own:

- session messages
- task-local approvals
- session memory

Practical meaning:

- `WorkspaceAttachment` answers "which execution world this run is mounted into"

## 5.5 SessionAttachment

`SessionAttachment` expresses the task-context binding.

Owns:

- `session_id`
- transcript scope reference
- session-memory scope reference
- task approval scope reference
- task-local context provider reference
- session-local policy override reference

Does not own:

- workspace root
- file boundary
- sandbox runtime

Practical meaning:

- `SessionAttachment` answers "which task container this run is currently serving"

## 5.6 CapabilitySnapshot

`CapabilitySnapshot` is the resolved, stable runtime capability view used by one run.

Owns:

- resolved tools
- resolved tool grants / tool policies
- visible skill layers
- visible memory scopes
- enabled external capabilities
- bound agent model identity
- bound model capability profile
- workspace runtime mode
- approval profile
- context policy

Does not own:

- live tool objects
- live model clients
- session data
- workspace data content

Practical meaning:

- one run should consume one stable capability view instead of repeatedly recomputing dynamic state from multiple systems mid-run

## 5.7 Checkpoint

`Checkpoint` is the recoverable kernel anchor.

Owns:

- `checkpoint_id`
- `run_id`
- `agent_instance_id`
- step cursor
- phase / status
- attachment references
- capability snapshot hash or revision
- journal offset
- waiting reason
- minimum restartable state payload
- schema / version metadata

Does not own:

- live event-loop primitives
- live provider clients
- live tool objects
- process handles
- file handles
- secrets

Practical meaning:

- `Checkpoint` answers "where a run can safely resume from"

## 5.8 ExecutionJournal

`ExecutionJournal` is the append-only execution fact stream.

Records should cover:

- `run_created`
- `attachment_bound`
- `capability_snapshot_resolved`
- `context_prepared`
- `model_request_started`
- `model_response_received`
- `tool_batch_planned`
- `approval_requested`
- `approval_decided`
- `tool_started`
- `tool_finished`
- `checkpoint_committed`
- `interrupted`
- `resumed`
- `cancelled`
- `completed`
- `failed`

Practical meaning:

- `ExecutionJournal` is not user transcript
- `ExecutionJournal` is not generic logger output
- `ExecutionJournal` is the authoritative execution fact stream for recovery, replay, audit, and rollback-oriented reasoning

## 6. Truth-Domain Split

The project must stop using one catch-all owner for all runtime truth.

The maintained truth domains are:

- `AgentProfile + AgentInstance`: agent truth
- `Workspace`: durable execution-world truth
- `Session`: task truth
- `Run`: formal execution truth
- `CapabilitySnapshot`: resolved execution capability truth
- `Checkpoint + ExecutionJournal`: recovery and replay truth

This split is not cosmetic.
It prevents later modules from silently re-centralizing ownership in `Session` or `Agent`.

## 7. Required Relationship Model

The baseline relationship model is:

- one `AgentProfile` may back many `AgentInstance`
- one `AgentInstance` may produce many `Run` over time
- one `AgentInstance` has at most one active `Run` at a time in baseline `v11.1`
- one `Workspace` may contain many `Session`
- one `Session` may contain many `Run`
- one `Run` binds one `WorkspaceAttachment`
- one `Run` binds one `SessionAttachment`
- one `Run` consumes one primary `CapabilitySnapshot`
- one `Run` may create many `Checkpoint`
- one `Run` writes one append-only `ExecutionJournal`

## 8. Interrupt / Resume / Cancel / Approval Placement

`v11.1` freezes the following rule:

- interrupt targets `Run`
- resume targets `Run`
- cancel targets `Run`
- approval wait is a `Run` state
- `Session` may expose or display these states, but is not the owner of them

This means:

- user surfaces may trigger these actions from session-centric UX
- kernel truth must still resolve the action against `run_id`

This rule is necessary to stop user-facing modules from directly mutating session state as if session itself were the executor.

## 9. Persistence Rules

Should persist:

- `AgentProfile` static metadata
- minimal `AgentInstance` durable state
- `Run` lifecycle state and terminal result
- `CapabilitySnapshot` facts or hashable resolved payload
- `Checkpoint`
- `ExecutionJournal`
- `Session` transcript / task memory / summaries
- `Workspace` durable memory / skills / artifacts / archive

Should not persist as runtime truth:

- live `LLMClient`
- live tool objects
- `asyncio.Event`
- `asyncio.Lock`
- process handles
- SDK client internals
- raw secrets inside checkpoint payloads

## 10. Explicit Anti-Drift Rules

The following drift patterns are now explicitly disallowed:

- putting active execution truth back into `Session`
- expanding `Agent` until it again mixes profile, instance, attachment, run, and execution-service ownership
- letting user surfaces directly treat session mutation as execution control truth
- treating logger output as a substitute for checkpoint or journal truth
- letting workspace/session switching occur inside a still-active run

## 11. Impact On Later Service Design

This kernel contract directly determines the later user-side service split.

Examples:

- `AgentUserService` must primarily operate on `AgentInstance` and `Run`, not on raw session runtime state
- `WorkspaceUserService` should manage workspace resources, attachment preparation, and workspace runtime exposure, not own main agent execution truth
- `ModelUserService` should provide agent-facing model selection/binding interfaces that affect future capability resolution, not inject workspace/session ownership into the main model chain
- `CommandUserService` should route commands like interrupt/resume/approve/cancel to run-level operations even if the UX is session-centric

## 12. Phase-2 Discussion Entry

This document closes the first kernel-contract discussion group.

The next discussion group should deepen the following:

- `Run` state machine
- `WorkspaceAttachment` and `SessionAttachment` field-level contract
- `Checkpoint` write points and rollback semantics
- `ExecutionJournal` event schema and retention boundary

That next slice is now captured in:

- [V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md](./V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md)

It remains part of the `v11.1` discussion baseline.
