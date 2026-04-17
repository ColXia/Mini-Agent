# Mini-Agent v11.1 Run / Attachment / Checkpoint / Journal Design

> Status: discussion baseline
> Date: 2026-04-17
> Scope: run state machine / attachment contract / checkpoint policy / execution journal schema boundary
> Related:
> - [V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md](./V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md)
> - [V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md](./V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md)
> - [V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md](./V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md)
> - [V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md](./V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md)
> - [AGENT_CORE_RUNTIME_SEAMS.md](./AGENT_CORE_RUNTIME_SEAMS.md)

## 1. Purpose

This document freezes the second kernel-design slice under `v11.1`.

It answers four practical questions:

- how one `Run` should be modeled as a formal execution unit
- how `WorkspaceAttachment` and `SessionAttachment` should be represented without collapsing boundaries
- where checkpoints should be written and what they are allowed to recover
- how `ExecutionJournal` should differ from transcript and logger output

This document is meant to be implementation-guiding.
It is not just a discussion note.

## 2. Why This Slice Matters

After `AgentProfile / AgentInstance / Run / Attachment / Checkpoint / ExecutionJournal` were locked as first-class objects, the next instability point is no longer object naming.

The next instability point is execution semantics.

If this layer remains vague:

- `Session` will continue absorbing active execution truth
- `Agent` will continue acting like profile, instance, controller, and run host at the same time
- interrupt, approval, resume, cancel, and recovery will continue targeting different truth objects
- logger, transcript, and checkpoint will keep bleeding into one another

So this slice exists to lock the execution truth of the kernel.

## 3. Run Must Use `status + phase`, Not One State Field

`v11.1` freezes a dual-state rule for `Run`.

`status` answers:

- can this run continue
- can the operator act on it
- is it terminal

`phase` answers:

- where inside the execution pipeline the run currently is

One state field is not enough because the kernel and the operator ask different questions.

Examples:

- a run may be `status=waiting` while `phase=awaiting_approval`
- a run may be `status=running` while `phase=executing_tools`
- a run may be `status=paused` while `phase=planning`
- a run may be `status=failed` while `phase=committing_effects`

Without the dual-state model, user surfaces and runtime recovery logic will keep overloading the same field with incompatible meanings.

## 4. Run Status Contract

Recommended `Run.status` values:

- `queued`
- `running`
- `waiting`
- `paused`
- `completed`
- `cancelled`
- `failed`

Meaning:

- `queued`: created but not yet started
- `running`: actively progressing inside the kernel
- `waiting`: blocked on an external decision or awaited dependency
- `paused`: explicitly interrupted or suspended, resumable by policy
- `completed`: terminal success
- `cancelled`: terminal operator or policy stop
- `failed`: terminal non-success due to runtime or policy failure

Rules:

- only `completed / cancelled / failed` are terminal
- only `queued / running / waiting / paused` are resumable candidates
- `waiting` is external-dependency wait
- `paused` is explicit suspension, not passive waiting

## 5. Run Phase Contract

Recommended `Run.phase` values:

- `created`
- `binding`
- `resolving_capabilities`
- `preparing_context`
- `planning`
- `awaiting_approval`
- `executing_tools`
- `committing_effects`
- `writing_reply`
- `post_turn`
- `terminal`

Meaning:

- `created`: run object exists but formal execution has not started
- `binding`: workspace and session attachments are being established
- `resolving_capabilities`: capability snapshot is being resolved
- `preparing_context`: session/workspace/global/recovery context is being assembled outside core and normalized for core consumption
- `planning`: model turn planning or response planning is in progress
- `awaiting_approval`: execution is blocked on user or policy approval
- `executing_tools`: approved tool execution is in progress
- `committing_effects`: side effects or runtime mutation facts are being committed to durable truth
- `writing_reply`: assistant-visible reply is being appended to session truth
- `post_turn`: memory automation, runtime writeback, or end-of-turn housekeeping is running
- `terminal`: run has ended and is not progressing further

Rules:

- `phase` may move forward only in kernel-defined order
- `phase=terminal` requires terminal `status`
- workspace or session switching inside a non-terminal run is forbidden

## 6. Valid Status / Phase Pairing

Recommended pairings:

- `queued + created`
- `running + binding`
- `running + resolving_capabilities`
- `running + preparing_context`
- `running + planning`
- `waiting + awaiting_approval`
- `running + executing_tools`
- `running + committing_effects`
- `running + writing_reply`
- `running + post_turn`
- `paused + planning`
- `paused + executing_tools`
- `completed + terminal`
- `cancelled + terminal`
- `failed + terminal`

Disallowed patterns:

- `completed + planning`
- `failed + executing_tools` as an active state after finalization
- `waiting + writing_reply`
- `queued + terminal`

The point is not to create an infinite matrix.
The point is to stop status/phase combinations that hide inconsistent runtime truth.

## 7. Recommended Run Lifecycle

Nominal path:

1. `queued + created`
2. `running + binding`
3. `running + resolving_capabilities`
4. `running + preparing_context`
5. `running + planning`
6. either:
7. `waiting + awaiting_approval`
8. resume to `running + executing_tools`
9. `running + committing_effects`
10. `running + writing_reply`
11. `running + post_turn`
12. `completed + terminal`

Failure path:

1. any active phase may transition to `failed + terminal`

Cancel path:

1. any non-terminal active phase may transition to `cancelled + terminal`

Interrupt path:

1. `running + planning` may become `paused + planning`
2. `running + executing_tools` may become `paused + executing_tools`
3. resume returns to `running + <same-or-rebuilt phase>`

Approval path:

1. `running + planning`
2. `waiting + awaiting_approval`
3. approval granted returns to `running + executing_tools`
4. approval denied may continue to `running + writing_reply` with refusal or may become `cancelled + terminal` by policy

## 8. Run Field-Level Contract

Required identity fields:

- `run_id`
- `agent_instance_id`
- `agent_profile_id`
- `workspace_id`
- `session_id`
- `trigger_source`

Required execution-state fields:

- `status`
- `phase`
- `step_index`
- `waiting_reason`
- `interrupt_state`
- `terminal_reason`

Required binding fields:

- `workspace_attachment_id`
- `session_attachment_id`
- `capability_snapshot_id`

Required recovery fields:

- `active_checkpoint_id`
- `last_checkpoint_seq`
- `journal_stream_id`
- `restorable`

Required time fields:

- `created_at`
- `started_at`
- `updated_at`
- `ended_at`

Optional diagnostics fields:

- `last_error_code`
- `last_error_summary`
- `last_model_request_id`
- `last_tool_batch_id`
- `last_mutation_ledger_seq`

Should not be embedded directly:

- session transcript content
- workspace file contents
- live tool objects
- live provider clients
- async runtime primitives

## 9. Attachment Design Principle

Attachment objects must remain lightweight and reference-based.

They describe:

- what the run is bound to
- under which constraints the binding is valid

They must not become hidden containers for the full workspace or full session payload.

This rule is critical because the project explicitly wants:

- portable agent
- workspace-bound execution
- session-bound task truth

If attachment objects become payload containers, the boundary collapses again.

## 10. WorkspaceAttachment Contract

`WorkspaceAttachment` is the execution-world binding.

Required fields:

- `workspace_attachment_id`
- `workspace_id`
- `workspace_kind`
- `root_dir`
- `runtime_backend`
- `runtime_ref`
- `boundary_manifest_hash`
- `permission_table_ref`
- `outside_zone_policy_ref`
- `mutation_ledger_ref`
- `mounted_at`

Optional fields:

- `snapshot_strategy`
- `network_policy_ref`
- `resource_policy_ref`
- `attachment_note`

Owns:

- execution root and boundary reference
- workspace runtime mode
- mutation-ledger binding
- policy references required for tool execution

Does not own:

- session transcript
- session approvals
- task-local scratchpad
- workspace durable content payload

Rule:

- one run uses exactly one `WorkspaceAttachment`
- switching workspace requires ending or suspending the current run and starting a new attachment flow

## 11. SessionAttachment Contract

`SessionAttachment` is the task-container binding.

Required fields:

- `session_attachment_id`
- `session_id`
- `workspace_id`
- `transcript_ref`
- `session_memory_ref`
- `approval_scope_ref`
- `context_policy_ref`
- `lineage_ref`
- `attached_at`

Optional fields:

- `task_summary_ref`
- `recovery_context_ref`
- `operator_override_ref`
- `attachment_note`

Owns:

- references to task truth and task-local context
- approval scope reference for the current task container
- task-level policy override references

Does not own:

- workspace root
- workspace runtime backend
- file boundary
- main model selection truth

Rule:

- one run uses exactly one `SessionAttachment`
- session switching inside an active run is forbidden

## 12. Attachment Establishment Order

Recommended order:

1. allocate `Run`
2. build `WorkspaceAttachment`
3. build `SessionAttachment`
4. resolve `CapabilitySnapshot`
5. write first durable checkpoint
6. start active execution phases

This order matters because:

- tools cannot safely execute before workspace binding is valid
- approvals cannot be interpreted correctly before session scope exists
- capability snapshot should resolve against a real attachment state, not abstract intent

## 13. Checkpoint Principle

`Checkpoint` is not a full-memory dump.

`Checkpoint` is a safe resume anchor that captures the minimum durable truth required to continue execution from a known boundary.

This means:

- checkpoints must be cheap enough to write repeatedly
- checkpoints must be explicit enough to recover a run deterministically
- checkpoints must not store live runtime objects

## 14. Checkpoint Types

Recommended checkpoint classes:

- `bootstrap`
- `pre_side_effect`
- `post_side_effect`
- `waiting`
- `terminal`

Meaning:

- `bootstrap`: first durable anchor after attachment and capability resolution
- `pre_side_effect`: last safe restore point before mutation-producing execution
- `post_side_effect`: restore point after durable mutation facts are committed
- `waiting`: restore point before waiting on approval or explicit external dependency
- `terminal`: final run anchor after success, cancel, or failure is committed

## 15. Checkpoint Write Points

Recommended checkpoint write points:

- after `WorkspaceAttachment` and `SessionAttachment` are valid
- after `CapabilitySnapshot` is resolved
- before any mutation-producing tool batch
- after tool batch result and mutation facts are durably committed
- before entering `waiting + awaiting_approval`
- after approval result is committed if it changes execution branch
- after assistant reply is durably appended to session truth
- on transition to terminal state

This is stricter than a naive "checkpoint every step" rule.
The important boundaries are not abstract loop steps.
The important boundaries are recoverability and side-effect safety.

## 16. What a Checkpoint Must Store

Required checkpoint fields:

- `checkpoint_id`
- `run_id`
- `agent_instance_id`
- `checkpoint_seq`
- `checkpoint_type`
- `status`
- `phase`
- `step_index`
- `workspace_attachment_id`
- `session_attachment_id`
- `capability_snapshot_hash`
- `journal_offset`
- `waiting_reason`
- `resume_token` or equivalent restore locator
- `created_at`
- `schema_version`

Optional payloads:

- `last_model_turn_ref`
- `last_tool_batch_ref`
- `last_mutation_ledger_seq`
- `recovery_context_ref`
- `error_ref`

Must not store:

- API keys
- live clients
- process handles
- file handles
- async tasks

## 17. Recovery and Rollback Semantics

Recommended recovery rule:

- resume from the latest committed checkpoint that is marked recoverable

Recommended rollback interpretation:

- `Kernel Rollback`: restore run state only
- `Mutation Rollback`: restore controlled workspace mutations if runtime backend supports it
- `Workspace Snapshot Rollback`: restore wider workspace state only when workspace runtime exposes this ability explicitly

Critical rule:

- kernel rollback must not promise workspace rollback unless workspace runtime confirms it

This prevents the core from lying about recoverability.

## 18. ExecutionJournal Principle

`ExecutionJournal` is the authoritative execution fact stream.

It is separate from:

- `Session transcript`: user-visible task conversation truth
- generic logger output: diagnostics and operational telemetry

The project must stop using transcript or logger as a substitute for execution journal truth.

## 19. Journal Event Schema Baseline

Required event envelope fields:

- `event_seq`
- `event_type`
- `event_ts`
- `run_id`
- `agent_instance_id`
- `workspace_id`
- `session_id`
- `status`
- `phase`
- `step_index`
- `correlation_id`
- `causation_id`
- `payload`

Recommended event families:

- `control.*`
- `context.*`
- `model.*`
- `tool.*`
- `checkpoint.*`
- `terminal.*`

Examples:

- `control.run_created`
- `control.attachment_bound`
- `context.capability_snapshot_resolved`
- `context.context_prepared`
- `model.request_started`
- `model.response_received`
- `tool.batch_planned`
- `tool.started`
- `tool.finished`
- `control.approval_requested`
- `control.approval_decided`
- `checkpoint.committed`
- `terminal.interrupted`
- `terminal.resumed`
- `terminal.cancelled`
- `terminal.completed`
- `terminal.failed`

## 20. Journal Retention Boundary

Recommended retention rule:

- raw execution journal remains append-only for the run lifetime
- after run terminalization, journal stays durable with the archived run record unless explicit pruning policy removes it
- transcript summarization must not rewrite raw journal history
- logger rotation must not delete authoritative journal truth by accident

Compaction rule:

- operator-facing read models may derive compact summaries from journal
- raw journal should remain immutable or versioned as an audit source

## 21. Journal, Transcript, and Mutation Ledger Are Different

The system must maintain a three-way distinction:

- `ExecutionJournal`: what the kernel did
- `Session transcript`: what the user and agent said
- `Mutation ledger`: what changed in the workspace runtime

Typical relationship:

- one tool execution may produce one journal event set
- the same tool execution may produce one mutation-ledger record
- later assistant reply may summarize the result into transcript

These are related facts, but they are not interchangeable truth owners.

## 22. Interrupt / Approval / Cancel Handling

Recommended rule:

- interrupt changes `status`, not just a UI flag
- approval wait changes both `status` and `phase`
- cancel is a terminal transition on `Run`
- session should expose these states, but should not become their owner

Mappings:

- interrupt during planning: `running + planning` -> `paused + planning`
- interrupt during tools: `running + executing_tools` -> `paused + executing_tools`
- approval needed: `running + planning` -> `waiting + awaiting_approval`
- cancel from any active state: `*` -> `cancelled + terminal`
- unhandled error from any active state: `*` -> `failed + terminal`

## 23. Anti-Drift Rules For This Slice

The following are now explicitly disallowed:

- putting `cancel_event` or equivalent active-execution truth back into `Session` as the primary owner
- embedding attachment payloads with full workspace/session content
- using checkpoint as a dumping ground for arbitrary runtime objects
- treating transcript as if it were the authoritative execution history
- allowing active workspace/session rebinding inside a still-live run

## 24. Immediate Implementation Direction For Current Repo

This document implies the following later refactor direction for current code:

- `src/mini_agent/runtime/session_state.py` should gradually stop hosting primary active-run control truth
- `src/mini_agent/agent_core/engine.py` should continue shrinking toward orchestration facade behavior
- `src/mini_agent/agent_core/runtime_bindings.py` should remain a useful binding layer, but not the final durable truth model
- `src/mini_agent/runtime/main_agent_runtime_manager.py` should evolve toward registry/orchestration/projection ownership rather than absorbing execution-state truth

This is not an execution plan yet.
It is the contract that later execution plans should target.
