# Post-P36 Runtime/Surface Evaluation

Date: 2026-04-15
Status: completed
Scope: evaluate the real post-`P36` state and recommend the next architecture line, if any

## Executive Summary

`P36` should currently be treated as complete.

The post-`P36` codebase does not show a strong need for more runtime/session contract cleanup in the same line.
The biggest remaining structural pressure is now concentrated in `TUI / surface orchestration`, not in the maintained runtime/session support seams that `P36` targeted.

The recommended next step is:

- do not reopen `P36` for more small support/codec/fixture cleanup
- do not start a big-bang runtime-manager rewrite
- if a new milestone is needed, open a new TUI/surface orchestration line focused on local-vs-remote convergence and projection ownership

## What Looks Healthy After P36

- The maintained runtime/session read seams are now explicit:
  - `RuntimeSessionAgentSupport`
  - `RuntimeSessionPayloadCodec`
  - `RuntimeSessionStateHydrator`
- Projection refresh/writeback logic is materially more consolidated than before `P36`.
- Runtime-facing test carriers are now maintained and shared instead of repeated ad hoc in many files.
- The application/surface API layer is comparatively thin:
  - `MainAgentSurfaceService` mostly delegates to chat/session handlers
  - `SessionApplicationService` mostly adapts request DTOs into runtime operations

## Main Findings

### 1. Runtime manager is large, but mostly as a composition root

`src/mini_agent/runtime/main_agent_runtime_manager.py` is still large at roughly 1116 lines.
That matters for maintenance cost, but current code inspection suggests the file is no longer the main correctness risk.

Current shape:

- large initialization/composition blocks wire many smaller handlers together
- most late methods are thin:
  - acquire lock
  - resolve/require session
  - delegate to a handler
  - return transport data

Implication:

- file size alone should not trigger a new runtime-manager refactor line
- if touched later, the right goal is probably composition-root slimming, not behavior extraction for its own sake

### 2. Session operator handler is still broad, but coherent

`src/mini_agent/runtime/session_operator_handler.py` is still large at roughly 772 lines.
It coordinates several operator command families:

- session control
- approvals
- context policy
- memory
- skills
- model selection
- runtime policy

This is still a real hotspot, but it currently reads like one orchestration boundary rather than multiple hidden subsystems.

Implication:

- this file is not the best immediate next refactor target unless command scope grows materially again
- its current pressure is secondary compared with TUI/surface orchestration

### 3. TUI is now the dominant structural hotspot

`src/mini_agent/tui/app.py` remains the strongest post-`P36` architectural pressure point.

Observed indicators:

- file size is roughly 9455 lines
- about 61 direct `runtime.agent` touches
- about 273 projection-field touches
- many paired local/remote pathways:
  - `_apply_remote_*`
  - `_sync_remote_*`
  - `_run_remote_*`
  - `_dispatch_remote_*`

This is not just UI rendering volume.
The class still owns several distinct responsibilities at once:

- local runtime control
- remote session synchronization
- turn execution
- streaming event handling
- approval handling
- session projection writeback
- command feedback and UI state updates
- resume/recovery behavior

Two especially important examples:

- remote projection application still directly mutates many fields in `_apply_remote_session_summary(...)` and `_apply_remote_session_detail(...)`
- local and remote turn execution are parallel high-complexity flows in `_run_chat_turn(...)` and `_run_remote_chat_turn(...)`

Implication:

- the biggest remaining drift risk is now local-vs-remote TUI behavior divergence
- the next worthwhile architecture line should likely sit here, not deeper in runtime/session codecs

### 4. Test gravity supports the same conclusion

The largest relevant tests remain concentrated around surface/TUI behavior:

- `tests/test_tui_app.py`: about 5001 lines
- `tests/test_main_agent_surface_service.py`: about 4245 lines
- `tests/test_cli_submission_loop.py`: about 1823 lines

Implication:

- future regression cost is likely to be highest where TUI/surface orchestration changes
- improving the TUI architecture should also improve test maintainability and future sliceability

## Recommendation

### Do not open a P36 follow-up by default

The project does not currently show enough remaining runtime/session contract debt to justify a `P36x` continuation.

Specifically:

- maintained read seams exist
- maintained refresh/writeback seams exist
- shared runtime-facing test carriers exist
- remaining inline/local complexity is now mostly outside the original `P36` problem statement

### Recommended next milestone direction

If the next architecture milestone is opened, it should be a new TUI/surface orchestration line.

Suggested focus:

1. Extract remote session projection syncing from `tui/app.py`
2. Split local-vs-remote turn execution into narrower strategy/service owners
3. Reduce direct TUI-owned projection mutation by introducing a maintained TUI session projector/update seam
4. Keep `P36` runtime/session seams locked; reuse them rather than reopening them

## Candidate Follow-up Shape

One possible follow-up line could look like:

### P37.1 TUI Remote Session Projection Service

Move remote summary/detail/message application out of `tui/app.py` into a maintained TUI-facing projector/service.

Goals:

- one owner for transport-payload-to-TUI-session mapping
- fewer direct projection field rewrites in the main app class

### P37.2 TUI Turn Execution Split

Separate local and remote turn execution into smaller orchestration units while preserving current behavior.

Goals:

- reduce duplication between `_run_chat_turn(...)` and `_run_remote_chat_turn(...)`
- keep shared task/projection/feedback lifecycle rules explicit

### P37.3 TUI Operator Command Surface Split

Extract command families that still mix UI handling with local/remote runtime execution:

- runtime policy
- context control
- memory
- skills
- approvals
- KB / MCP controls

Goals:

- make command behavior easier to test independently from full app rendering
- reduce `tui/app.py` change blast radius

## What Not To Do Next

- do not reopen `P36` just to remove the last few direct projection writes
- do not start a big-bang rewrite of `MainAgentRuntimeManager`
- do not assume the next problem is still inside `runtime/session` just because those files were the previous focus

## Validation Context

Current validation baseline from the completed `P36` line:

- focused runtime/session/surface bundle remains green
- latest recorded bundle result: `294 passed`

