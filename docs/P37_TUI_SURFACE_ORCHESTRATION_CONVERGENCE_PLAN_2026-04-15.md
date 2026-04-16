# P37 TUI Surface Orchestration Convergence Plan

Date: 2026-04-15
Status: completed
Scope: reduce TUI-local orchestration thickness after the completed `P36` runtime/session contract line

Execution note (2026-04-15): post-`P36` evaluation showed that the next meaningful structural pressure is no longer in the runtime/session support seams. It is concentrated in `src/mini_agent/tui/app.py`, especially where local runtime flow and remote session flow are handled in parallel and where remote payloads are applied directly onto TUI session projection state.
Execution note (2026-04-16): post-`P37` evaluation indicates that the main `P37` target has now been met materially enough to treat the line as complete. Remaining TUI pressure is broader surface/lifecycle weight rather than another high-value repetition of the same command-family extraction pattern.

## Goal

Make the TUI easier to evolve without re-opening runtime/session truth seams.

The desired end state is:

- less direct projection writeback logic inside `tui/app.py`
- clearer ownership for remote session payload syncing
- clearer ownership for local vs remote turn execution
- lower regression blast radius for operator commands and session sync behavior

This is not a UI redesign sprint.
It is a TUI/surface orchestration convergence sprint above the completed `P36` line.

## Why This Slice Exists

After `P36`:

- runtime/session read helpers are maintained
- projection refresh paths are materially more consolidated
- runtime-facing tests share maintained contract carriers

But one large structural hotspot remains:

- `src/mini_agent/tui/app.py` still owns:
  - local runtime orchestration
  - remote session sync
  - projection updates from transport payloads
  - approval/update/control feedback loops
  - parallel local/remote command flows

That now looks like the highest-value follow-up seam.

## Locked Decisions

### 1. Do not reopen P36 ownership

`P37` should reuse:

- `RuntimeSessionAgentSupport`
- `RuntimeSessionPayloadCodec`
- `RuntimeSessionStateHydrator`
- the completed `P36` runtime-facing test carriers

It should not rebuild a competing runtime/session support layer.

### 2. Keep TUI-local state derived and surface-owned

TUI-local session projection remains a surface cache.
`P37` may give that cache better owners.
It should not make TUI the new runtime truth.

### 3. Prefer service extraction over giant rewrites

The preferred shape is:

- narrow projector/service extraction
- focused tests
- small behavior-preserving moves

Not:

- big-bang `tui/app.py` replacement
- cross-layer transport/runtime redesign

## Planned Slices

### P37.1 Remote Session Projection Service

Goals:

- extract remote `summary/detail/messages` application from `tui/app.py`
- give transport-payload-to-TUI-session mapping one maintained owner
- reduce direct TUI app ownership of remote projection mutation

Likely files:

- `src/mini_agent/tui/app.py`
- `src/mini_agent/tui/session_remote_projector.py`
- focused TUI tests

Execution status:

- landed kickoff extraction:
  - added `TuiRemoteSessionProjector`
  - `MiniAgentTuiApp` now delegates remote summary/detail/message application through that projector
  - added focused unit coverage for the projector
  - focused verification:
    - `uv run ruff check src/mini_agent/tui/app.py src/mini_agent/tui/session_remote_projector.py tests/test_tui_remote_projector.py`
    - `uv run pytest tests/test_tui_remote_projector.py tests/test_tui_app.py -q`
    - result: `146 passed`

### P37.2 Local vs Remote Turn Execution Split

Goals:

- reduce duplication and drift between:
  - `_run_chat_turn(...)`
  - `_run_remote_chat_turn(...)`
- preserve current behavior while moving shared lifecycle rules behind narrower owners

Execution status:

- first cut landed:
  - added `TuiSessionTurnStateCoordinator`
  - `MiniAgentTuiApp` now delegates shared local/remote turn session-task state transitions through that coordinator
  - focused verification:
    - `uv run ruff check src/mini_agent/tui/app.py src/mini_agent/tui/session_turn_state_coordinator.py tests/test_tui_turn_state_coordinator.py`
    - `uv run pytest tests/test_tui_turn_state_coordinator.py tests/test_tui_remote_projector.py tests/test_tui_app.py -q`
    - result: `148 passed`
- second cut landed:
  - added `TuiSessionTurnOutcomeCoordinator`
  - `MiniAgentTuiApp` now delegates shared local/remote turn completion and failure classification through that coordinator
  - success-path stream finalization still stays in `tui/app.py`
  - focused verification:
    - `uv run ruff check src/mini_agent/tui/app.py src/mini_agent/tui/session_turn_outcome_coordinator.py tests/test_tui_turn_outcome_coordinator.py tests/test_tui_turn_state_coordinator.py tests/test_tui_remote_projector.py`
    - `uv run pytest tests/test_tui_turn_outcome_coordinator.py tests/test_tui_turn_state_coordinator.py tests/test_tui_remote_projector.py tests/test_tui_app.py -q`
    - result: `150 passed`
- third cut landed:
  - added `TuiRemoteTurnStreamCoordinator`
  - `MiniAgentTuiApp` now delegates remote stream consumption and event dispatch through that coordinator
  - turn outcome ownership and final reply/sync orchestration still stay in `tui/app.py`
  - focused verification:
    - `uv run ruff check src/mini_agent/tui/app.py src/mini_agent/tui/session_remote_turn_stream_coordinator.py tests/test_tui_remote_turn_stream_coordinator.py tests/test_tui_app.py`
    - `uv run pytest tests/test_tui_remote_turn_stream_coordinator.py tests/test_tui_turn_outcome_coordinator.py tests/test_tui_turn_state_coordinator.py tests/test_tui_remote_projector.py tests/test_tui_app.py -q`
    - result: `154 passed`

### P37.3 TUI Operator Command Orchestration Split

Goals:

- reduce mixed UI/runtime/network ownership for:
  - approvals
  - runtime policy
  - context commands
  - memory/skill/KB/MCP command flows

Execution status:

- kickoff cut landed:
  - added `TuiSessionApprovalCommandCoordinator`
  - `MiniAgentTuiApp` now delegates local-vs-remote approval command orchestration through that coordinator
  - modal rendering and remote stream approval event handling still stay in `tui/app.py`
  - focused verification:
    - `uv run ruff check src/mini_agent/tui/app.py src/mini_agent/tui/session_approval_command_coordinator.py tests/test_tui_approval_command_coordinator.py tests/test_tui_app.py`
    - `uv run pytest tests/test_tui_approval_command_coordinator.py tests/test_tui_remote_turn_stream_coordinator.py tests/test_tui_turn_outcome_coordinator.py tests/test_tui_turn_state_coordinator.py tests/test_tui_remote_projector.py tests/test_tui_app.py -q`
    - result: `158 passed`
- second cut landed:
  - added `TuiSessionRuntimePolicyCommandCoordinator`
  - `MiniAgentTuiApp` now delegates local-vs-remote runtime-policy command orchestration through that coordinator
  - runtime-policy apply helpers still stay in `tui/app.py`
  - focused verification:
    - `uv run ruff check src/mini_agent/tui/app.py src/mini_agent/tui/session_runtime_policy_command_coordinator.py tests/test_tui_runtime_policy_command_coordinator.py tests/test_tui_approval_command_coordinator.py tests/test_tui_app.py`
    - `uv run pytest tests/test_tui_runtime_policy_command_coordinator.py tests/test_tui_approval_command_coordinator.py tests/test_tui_remote_turn_stream_coordinator.py tests/test_tui_turn_outcome_coordinator.py tests/test_tui_turn_state_coordinator.py tests/test_tui_remote_projector.py tests/test_tui_app.py -q`
    - result: `161 passed`
- third cut landed:
  - added `TuiSessionContextCommandCoordinator`
  - `MiniAgentTuiApp` now delegates context command orchestration through that coordinator
  - context planner, local command execution, and remote update helpers still stay in `tui/app.py`
  - focused verification:
    - `uv run ruff check src/mini_agent/tui/app.py src/mini_agent/tui/session_context_command_coordinator.py tests/test_tui_context_command_coordinator.py tests/test_tui_app.py`
    - `uv run pytest tests/test_tui_context_command_coordinator.py tests/test_tui_runtime_policy_command_coordinator.py tests/test_tui_approval_command_coordinator.py tests/test_tui_remote_turn_stream_coordinator.py tests/test_tui_turn_outcome_coordinator.py tests/test_tui_turn_state_coordinator.py tests/test_tui_remote_projector.py tests/test_tui_app.py -q`
    - result: `164 passed`
- fourth cut landed:
  - added `TuiSessionMemoryCommandCoordinator`
  - `MiniAgentTuiApp` now delegates memory command orchestration through that coordinator
  - memory command planning and execution helpers still stay in `tui/app.py`
  - focused verification:
    - `uv run ruff check src/mini_agent/tui/app.py src/mini_agent/tui/session_memory_command_coordinator.py tests/test_tui_memory_command_coordinator.py tests/test_tui_app.py`
    - `uv run pytest tests/test_tui_memory_command_coordinator.py tests/test_tui_context_command_coordinator.py tests/test_tui_runtime_policy_command_coordinator.py tests/test_tui_approval_command_coordinator.py tests/test_tui_remote_turn_stream_coordinator.py tests/test_tui_turn_outcome_coordinator.py tests/test_tui_turn_state_coordinator.py tests/test_tui_remote_projector.py tests/test_tui_app.py -q`
    - result: `167 passed`
- fifth cut landed:
  - added `TuiSessionKbCommandCoordinator`
  - `MiniAgentTuiApp` now delegates KB command orchestration through that coordinator
  - remote KB execution helper and local KB toggle details still stay in `tui/app.py`
  - focused verification:
    - `uv run ruff check src/mini_agent/tui/app.py src/mini_agent/tui/session_kb_command_coordinator.py tests/test_tui_kb_command_coordinator.py tests/test_tui_app.py`
    - `uv run pytest tests/test_tui_kb_command_coordinator.py tests/test_tui_memory_command_coordinator.py tests/test_tui_context_command_coordinator.py tests/test_tui_runtime_policy_command_coordinator.py tests/test_tui_approval_command_coordinator.py tests/test_tui_remote_turn_stream_coordinator.py tests/test_tui_turn_outcome_coordinator.py tests/test_tui_turn_state_coordinator.py tests/test_tui_remote_projector.py tests/test_tui_app.py -q`
    - result: `172 passed`
- sixth cut landed:
  - added `TuiSessionMcpCommandCoordinator`
  - `MiniAgentTuiApp` now delegates MCP command orchestration through that coordinator
  - remote control helper and local MCP reload runtime-rebuild details still stay in `tui/app.py`
  - focused verification:
    - `uv run ruff check src/mini_agent/tui/app.py src/mini_agent/tui/session_mcp_command_coordinator.py tests/test_tui_mcp_command_coordinator.py tests/test_tui_app.py`
    - `uv run pytest tests/test_tui_mcp_command_coordinator.py tests/test_tui_kb_command_coordinator.py tests/test_tui_memory_command_coordinator.py tests/test_tui_context_command_coordinator.py tests/test_tui_runtime_policy_command_coordinator.py tests/test_tui_approval_command_coordinator.py tests/test_tui_remote_turn_stream_coordinator.py tests/test_tui_turn_outcome_coordinator.py tests/test_tui_turn_state_coordinator.py tests/test_tui_remote_projector.py tests/test_tui_app.py -q`
    - result: `176 passed`
- seventh cut landed:
  - added `TuiSessionSkillCommandCoordinator`
  - `MiniAgentTuiApp` now delegates skill command orchestration through that coordinator
  - remote skill request/response helpers and local skill-result application still stay in `tui/app.py`
  - focused verification:
    - `uv run ruff check src/mini_agent/tui/app.py src/mini_agent/tui/session_skill_command_coordinator.py tests/test_tui_skill_command_coordinator.py tests/test_tui_app.py`
    - `uv run pytest tests/test_tui_skill_command_coordinator.py tests/test_tui_mcp_command_coordinator.py tests/test_tui_kb_command_coordinator.py tests/test_tui_memory_command_coordinator.py tests/test_tui_context_command_coordinator.py tests/test_tui_runtime_policy_command_coordinator.py tests/test_tui_approval_command_coordinator.py tests/test_tui_remote_turn_stream_coordinator.py tests/test_tui_turn_outcome_coordinator.py tests/test_tui_turn_state_coordinator.py tests/test_tui_remote_projector.py tests/test_tui_app.py -q`
    - result: `180 passed`
- eighth cut landed:
  - added `TuiSessionModelCommandCoordinator`
  - `MiniAgentTuiApp` now delegates model command orchestration through that coordinator
  - model-selection, discovery, filter, and limit helpers still stay in `tui/app.py`
  - focused verification:
    - `uv run ruff check src/mini_agent/tui/app.py src/mini_agent/tui/session_model_command_coordinator.py tests/test_tui_model_command_coordinator.py tests/test_tui_app.py`
    - `uv run pytest tests/test_tui_model_command_coordinator.py tests/test_tui_skill_command_coordinator.py tests/test_tui_mcp_command_coordinator.py tests/test_tui_kb_command_coordinator.py tests/test_tui_memory_command_coordinator.py tests/test_tui_context_command_coordinator.py tests/test_tui_runtime_policy_command_coordinator.py tests/test_tui_approval_command_coordinator.py tests/test_tui_remote_turn_stream_coordinator.py tests/test_tui_turn_outcome_coordinator.py tests/test_tui_turn_state_coordinator.py tests/test_tui_remote_projector.py tests/test_tui_app.py -q`
    - result: `186 passed`

## Exit Criteria

`P37` should be considered complete when:

- remote session projection syncing no longer lives as a large direct-mutation block inside `tui/app.py`
- local vs remote turn execution reads like maintained orchestration instead of parallel monoliths
- operator-command paths in TUI are materially easier to test without full-app coupling
