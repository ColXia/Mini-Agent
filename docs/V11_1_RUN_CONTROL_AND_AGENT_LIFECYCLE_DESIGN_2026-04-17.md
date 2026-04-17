# Mini-Agent v11.1 Run Control And Agent Lifecycle Design

> Status: discussion baseline
> Date: 2026-04-17
> Scope: run control plane / approval wait / interrupt vs cancel / resume semantics / agent-instance lifecycle
> Related:
> - [V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md](./V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md)
> - [V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md](./V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md)
> - [V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md](./V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md)
> - [AGENT_CORE_RUNTIME_SEAMS.md](./AGENT_CORE_RUNTIME_SEAMS.md)

## 1. Purpose

This document freezes the third kernel-design slice under `v11.1`.

It answers five practical questions:

- who owns execution control truth
- how interrupt, cancel, resume, approve, and deny should be modeled
- whether pending approval is a list-shaped session detail or a first-class run-control object
- which control facts are durable and which are only in-process runtime bridges
- how `AgentInstance` lifecycle should relate to run control without collapsing back into session-owned execution

This document is still architecture baseline, not an execution plan.
Its purpose is to stop the control plane from drifting back into session runtime state.

## 2. Why This Slice Matters

The first two slices locked:

- kernel truth objects
- run / attachment / checkpoint / journal execution truth

The next instability point is control truth.

If this slice is not explicitly locked:

- `Session` will continue to act like the executor because user surfaces naturally operate through session-centric UX
- `cancel_event`, pending approvals, approval waiters, and busy state will remain mixed into session runtime storage
- interrupt and cancel will continue being treated as the same thing
- recovery will keep depending on ephemeral process objects instead of durable run-control truth

So this slice exists to define the maintained control-plane boundary.

## 3. Current Code Pressure

Current code already shows the problem:

- `src/mini_agent/runtime/session_state.py` stores `cancel_event`, `pending_approvals`, and `pending_approval_waiters` directly under session runtime state
- `src/mini_agent/runtime/session_interrupt_handler.py` performs cancel and approval operations against session-owned structures
- `src/mini_agent/runtime/session_live_state_handler.py` marks turn start/finish by mutating session-owned cancel and approval fields
- `src/mini_agent/agent_core/execution/tool_execution_coordinator.py` expects approval and cancel signaling to exist, but it should not force session to become the owner
- `src/mini_agent/agent_core/execution/scheduler.py` currently maps cancellation into an interrupted scheduler state, showing that interrupt/cancel semantics are still partially conflated

This does not mean the existing code is wrong.
It means the next maintained boundary must explicitly separate:

- durable control truth
- in-process control bridges
- session projection

## 4. Control-Plane Truth Split

`v11.1` now freezes the following split:

- `Run` remains the formal execution truth owner
- `RunControlState` owns durable control state for the active run
- `ApprovalWait` owns one durable approval-blocking record
- `RunControlRuntime` owns in-process local control primitives only
- `Session` may project control state to user surfaces, but does not own control truth

This is the core statement of the third slice.

## 5. RunControlState

`RunControlState` is the durable control view for one run.

It should be treated as run-owned control truth, not as a session-side convenience bag.

Owns:

- current control mode
- last control command
- active wait kind
- active approval wait reference
- interrupt requested flag
- cancel requested flag
- resumable flag
- last control transition timestamps

Does not own:

- session transcript
- workspace attachment payload
- async waiters
- event-loop objects
- live tool task handles

Practical meaning:

- `RunControlState` answers "what control state this run is currently in"

## 6. Recommended RunControlState Fields

Required fields:

- `run_id`
- `control_mode`
- `active_wait_kind`
- `active_wait_id`
- `interrupt_requested`
- `cancel_requested`
- `resumable`
- `last_command`
- `last_command_source`
- `last_command_at`
- `control_updated_at`

Optional fields:

- `force_stop_requested`
- `last_resume_token`
- `last_pause_reason`
- `last_cancel_reason`
- `last_approval_token`

Recommended `control_mode` values:

- `normal`
- `interrupt_requested`
- `paused`
- `approval_wait`
- `resume_requested`
- `cancel_requested`
- `terminal`

Recommended `active_wait_kind` values:

- `none`
- `approval`
- `external_dependency`

## 7. Durable Control Truth Versus Runtime Control Bridge

The project must explicitly separate durable control truth from in-process bridge objects.

Durable control truth:

- run status
- run phase
- run control mode
- approval wait record
- control events in journal

In-process runtime bridge:

- cancellation event or token
- pause signal
- approval future / waiter
- active tool-task interrupt hooks
- in-memory command bus or channel

This split is mandatory.

Without it, future work will keep trying to persist process objects or use session memory as if it were the kernel control truth.

## 8. RunControlRuntime

`RunControlRuntime` is an in-process bridge object.

It exists only to help the current runtime host deliver control commands to the executing run.

Owns:

- cancel signal primitive
- pause signal primitive
- one live approval waiter
- active tool-interrupt bridge references
- local command queue or equivalent

Does not own:

- durable state
- operator-visible truth
- session transcript
- recovery truth

Practical meaning:

- if the process dies, `RunControlRuntime` disappears
- recovery must rebuild it from durable `Run + RunControlState + ApprovalWait`, not from persisted process state

## 9. Interrupt And Cancel Are Not The Same Operation

`v11.1` now freezes a strict distinction:

- `interrupt` means "cooperatively pause this run and preserve resumability when possible"
- `cancel` means "terminate this run and move toward terminal state"

Why this matters:

- a user may want to stop a long-running tool temporarily and continue later
- a user may want to abandon the run entirely
- recovery semantics differ between a paused run and a cancelled run

Current code uses cancellation signaling as the main interrupt path.
That is acceptable as an implementation bridge for now, but it must not remain the architectural truth model.

## 10. Control Commands

The maintained operator-facing control commands are:

- `interrupt`
- `resume`
- `cancel`
- `approve`
- `deny`

Command targeting rule:

- `interrupt / resume / cancel` target `run_id`
- `approve / deny` target `approval_wait_id` or approval token under a run

User surfaces may issue commands from a session-centric UX, but the control service must resolve them against run-owned control truth.

## 11. Interrupt Semantics

Recommended interrupt semantics:

- interrupt is cooperative
- interrupt should be acknowledged at safe control boundaries
- interrupt should not silently become cancel unless policy explicitly escalates it

Nominal flow:

1. operator issues `interrupt`
2. `RunControlState.control_mode` becomes `interrupt_requested`
3. journal records `control.interrupt_requested`
4. run reaches safe boundary
5. run status/phase transition to paused state
6. `RunControlState.control_mode` becomes `paused`
7. checkpoint is written if resumable
8. journal records `control.interrupt_acknowledged`

Recommended pause targets:

- `running + planning` -> `paused + planning`
- `running + executing_tools` -> `paused + executing_tools`

## 12. Resume Semantics

Resume is allowed only when:

- run is non-terminal
- run is marked resumable
- active wait state has been cleared or is intentionally resumable

Nominal flow:

1. operator issues `resume`
2. `RunControlState.control_mode` becomes `resume_requested`
3. journal records `control.resume_requested`
4. runtime rebuilds `RunControlRuntime`
5. kernel resumes from latest recoverable checkpoint
6. `RunControlState.control_mode` returns to `normal`
7. journal records `control.resume_acknowledged`

Critical rule:

- resume targets an existing run
- it is not equivalent to "send a new user message"

If a recovery strategy decides the only safe path is a new user message, that is not true resume.
That is recovery by follow-up turn.

## 13. Cancel Semantics

Cancel is terminal intent.

Nominal flow:

1. operator issues `cancel`
2. `RunControlState.cancel_requested` becomes true
3. `RunControlState.control_mode` becomes `cancel_requested`
4. journal records `control.cancel_requested`
5. runtime attempts cooperative stop
6. if needed, workspace runtime may escalate according to policy
7. run transitions to `cancelled + terminal`
8. terminal checkpoint is written
9. journal records `terminal.cancelled`

Critical rule:

- `cancel` must never return to `running`

## 14. ApprovalWait

`ApprovalWait` is a first-class durable wait object.

It is not just a loose dict inside session runtime state.

Owns:

- approval token or wait id
- `run_id`
- `session_id`
- `workspace_id`
- tool name
- tool arguments summary
- approval kind
- policy reason
- cache key
- escalation permission
- wait state
- decision result
- created / resolved timestamps

Practical meaning:

- `ApprovalWait` answers "what exactly is currently waiting for approval under this run"

## 15. Baseline Approval Cardinality

Baseline `v11.1` rule:

- one active run may have at most one active blocking `ApprovalWait`

Why this is the recommended baseline:

- current run model is single active run per agent instance
- current tool execution is effectively sequential at the approval boundary
- allowing many concurrent active approval waits would force broader control-plane complexity too early

Important nuance:

- historical approval records may be many
- session projection may still show a collection for compatibility or archived recovery information
- but the active kernel blocking truth should be one `ApprovalWait` at a time in baseline `v11.1`

## 16. Approval Resolution Semantics

Approval flow:

1. kernel creates `ApprovalWait`
2. run transitions to `waiting + awaiting_approval`
3. `RunControlState.control_mode` becomes `approval_wait`
4. checkpoint is written
5. journal records `control.approval_wait_created`
6. operator issues `approve` or `deny`
7. `ApprovalWait` becomes resolved
8. journal records `control.approval_wait_resolved`
9. run either returns to `running + executing_tools` or branches to refusal / cancel policy

Critical rule:

- approval resolution targets the wait object, not raw session fields

## 17. Approval Recovery Rule

If the process restarts while approval is pending:

- durable truth may preserve that an approval wait existed
- live waiter object is gone
- direct in-process continuation is not guaranteed

So the architecture rule should be:

- `ApprovalWait` is durable
- approval waiter future is not durable
- restart may require safe re-evaluation rather than blindly resuming the old live approval point

This matches the current repo direction where restart-time pending approvals may need recovery handling instead of direct continuation.

## 18. AgentInstance Lifecycle

`AgentInstance` lifecycle must remain separate from session lifecycle.

Recommended `AgentInstance.lifecycle_state` values:

- `cold`
- `ready`
- `attached`
- `running`
- `waiting`
- `paused`
- `migrating`
- `errored`
- `retired`

Meaning:

- `cold`: created but not hydrated
- `ready`: hydrated and reusable, with no active run
- `attached`: prepared for a workspace/session context but not running
- `running`: has one active run progressing
- `waiting`: has one active run blocked on approval or external dependency
- `paused`: has one active run interrupted and resumable
- `migrating`: explicit detach/attach transition between workspaces
- `errored`: instance-level fault requires intervention
- `retired`: no longer reusable

## 19. AgentInstance Lifecycle Rules

Rules:

- session lifecycle changes do not directly redefine agent lifecycle
- active run state drives most instance lifecycle transitions
- instance lifecycle may cache attachment summary, but formal attachment truth remains on the active run
- one instance cannot be `running` and `migrating` at the same time
- migration with active non-suspended run is forbidden

Recommended mapping:

- no active run and usable -> `ready`
- attached but idle -> `attached`
- active run normal -> `running`
- active run approval wait -> `waiting`
- active run interrupted -> `paused`
- explicit detach/attach workflow -> `migrating`

## 20. Control Events That Must Be Journaled

Recommended journal events for this slice:

- `control.interrupt_requested`
- `control.interrupt_acknowledged`
- `control.resume_requested`
- `control.resume_acknowledged`
- `control.cancel_requested`
- `control.approval_wait_created`
- `control.approval_wait_resolved`
- `control.control_mode_changed`
- `instance.lifecycle_changed`

This gives recovery and audit a truthful control-plane event history.

## 21. Session Projection Rule

Session may project:

- whether there is an active run
- whether the run is waiting for approval
- whether the run is paused
- what user-facing command choices are available

Session must not own:

- primary cancel token
- primary approval truth
- primary control mode truth

Practical implication for current repo:

- `session.projection.busy` should become a projection of active run truth
- `session.runtime.cancel_event` should not remain the conceptual truth owner
- `session.runtime.pending_approvals` should become a projection or compatibility cache, not the primary truth source

## 22. Immediate Direction For Current Repo

This document implies the following later refactor direction:

- move primary control truth out of `session.runtime`
- keep session handlers as surface-facing adapters or projection handlers
- introduce run-owned control models before further widening session-runtime helpers
- separate interrupt and cancel semantics in the maintained contract even if current implementation temporarily shares signaling paths

This is not the code change itself.
It is the rulebook that later code change should follow.
