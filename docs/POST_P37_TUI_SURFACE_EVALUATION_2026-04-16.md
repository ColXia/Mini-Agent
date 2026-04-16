# Post-P37 TUI Surface Evaluation

Date: 2026-04-16
Status: completed
Scope: evaluate the real post-`P37` TUI/surface state and decide whether `P37` should continue

## Executive Summary

`P37` should now be treated as materially complete.

The biggest `P37` pressure points that justified the line have been addressed:

- remote session projection syncing now has a maintained owner
- local vs remote turn execution now has maintained TUI-facing owners
- the main heavy operator command families no longer live as flat mixed branches inside `tui/app.py`

`src/mini_agent/tui/app.py` is still large, but the remaining weight is no longer concentrated in the specific `P37` problem statement.
The strongest leftover pressure now looks more like broader surface/lifecycle orchestration than another high-value repetition of the same `P37.3` command-family cut.

Recommended next step:

- do not keep extending `P37` just to extract smaller and smaller command wrappers
- treat `P37` as complete enough for planning purposes
- if another TUI line is needed later, scope it from a fresh problem statement rather than continuing `P37.3` by inertia

## What P37 Changed

`P37` established maintained TUI-facing owners for the main surface orchestration hotspots:

- remote projection:
  - `TuiRemoteSessionProjector`
- local vs remote turn flow:
  - `TuiSessionTurnStateCoordinator`
  - `TuiSessionTurnOutcomeCoordinator`
  - `TuiRemoteTurnStreamCoordinator`
- operator command families:
  - `TuiSessionApprovalCommandCoordinator`
  - `TuiSessionRuntimePolicyCommandCoordinator`
  - `TuiSessionContextCommandCoordinator`
  - `TuiSessionMemoryCommandCoordinator`
  - `TuiSessionKbCommandCoordinator`
  - `TuiSessionMcpCommandCoordinator`
  - `TuiSessionSkillCommandCoordinator`
  - `TuiSessionModelCommandCoordinator`

That means the previous dominant `P37` drift risks are now materially reduced:

- fewer mixed local/runtime/network branches in `tui/app.py`
- clearer reuse points for focused command tests
- less pressure to test every command path only through the full TUI app shell

## Residual Pressure

### 1. `session` command flow is still broad, but it is a different class of problem

`_handle_session_command(...)` is still one of the larger remaining command methods.
However, it no longer looks like the same kind of backlog item as the `P37.3` command families that were just extracted.

Why it is different:

- it mixes session selection, creation, sharing, rename, delete, and UI activation
- it is more tightly coupled to surface lifecycle and session-list state mutation
- several subflows already have their own dedicated helpers

Implication:

- this is not a strong argument for “one more `P37.3` command coordinator”
- if revisited later, it should probably be scoped as a session-surface/lifecycle slice, not as leftover command-family convergence

### 2. `sandbox` command flow is already too small to justify another extraction

`_handle_sandbox_command(...)` is now a short wrapper around shared diagnostics execution and feedback rendering.

Implication:

- extracting it would mostly create a thin shell
- that would add files without removing meaningful architectural risk

### 3. `tui/app.py` remains large, but for broader reasons than the P37 target

`tui/app.py` still owns substantial surface behavior:

- session lifecycle and selection
- local runtime warm/shutdown flows
- prompt submission and recovery
- presentation-layer view state
- remaining session mutation and UI command tails

Implication:

- file size alone should not trigger more `P37` cuts
- the next worthwhile TUI refactor, if any, should start from one of those broader stories explicitly

## Recommendation

### Treat P37 as materially complete

The `P37` exit criteria are now functionally met:

- remote projection sync is no longer one large direct block in `tui/app.py`
- local and remote turn execution read through maintained owners instead of parallel monoliths
- operator command paths are materially easier to test outside the full app class

### Do not force a tail cleanup without a stronger problem statement

The remaining candidate cuts are now low-leverage compared with the earlier `P37` slices.

Specifically:

- `session` is broader than a command-family cleanup
- `sandbox` is too small
- the dispatcher tail no longer shows the same concentrated drift risk that justified the earlier extractions

### If another TUI milestone is needed later

It should likely be framed as a new line, for example:

- session-surface lifecycle and mutation orchestration
- prompt/recovery/resume surface flow cleanup
- broader TUI composition/root slimming

Not:

- “continue P37.3 until every command has its own wrapper”

## Validation Context

Latest focused verification after the final `P37.3` command extraction:

- `uv run ruff check src/mini_agent/tui/app.py src/mini_agent/tui/session_model_command_coordinator.py tests/test_tui_model_command_coordinator.py tests/test_tui_app.py`
- `uv run pytest tests/test_tui_model_command_coordinator.py tests/test_tui_skill_command_coordinator.py tests/test_tui_mcp_command_coordinator.py tests/test_tui_kb_command_coordinator.py tests/test_tui_memory_command_coordinator.py tests/test_tui_context_command_coordinator.py tests/test_tui_runtime_policy_command_coordinator.py tests/test_tui_approval_command_coordinator.py tests/test_tui_remote_turn_stream_coordinator.py tests/test_tui_turn_outcome_coordinator.py tests/test_tui_turn_state_coordinator.py tests/test_tui_remote_projector.py tests/test_tui_app.py -q`
- result: `186 passed`
