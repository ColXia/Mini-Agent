# Agent-Core Runtime Seams

> Status: active
> Last updated: 2026-04-15
> Scope: lock the maintained internal seams of `mini_agent.agent_core` after `P34`

## 1. Purpose

This document records the maintained runtime seams inside `agent_core`.

It exists to prevent the core from drifting back into:

- one giant `engine.py`
- surface-owned runtime behavior
- hidden side effects embedded in the `Agent` facade
- new features being added to whichever helper method is easiest to reach

## 2. Facade Rule

`Agent` remains the recognizable runtime facade, but its role is now intentionally narrow.

`Agent` is allowed to own:

- conversation state and message history
- turn lifecycle orchestration
- runtime binding accessors
- high-level state transitions between planner, executor, and terminal turn result

`Agent` should not become the direct owner again of:

- tool authorization/execution internals
- history summarization internals
- turn-context provider/ranking/diagnostics internals
- terminal presentation formatting logic
- post-turn memory/runtime writeback internals

## 3. Maintained Seams

### Runtime bindings

File:

- `src/mini_agent/agent_core/runtime_bindings.py`

Owned responsibility:

- typed runtime attachment state for the agent core
- route, skill-runtime, catalog-loader, and kernel-diagnostics bindings
- typed runtime service state for approval, policy, sandbox, and approval-handler wiring

Compatibility rule:

- `Agent` exposes `runtime_bindings` and `runtime_services` as the typed truth
- helper binders may still mirror legacy attributes, but the contract objects remain authoritative

### Tool execution coordinator

Files:

- `src/mini_agent/agent_core/execution/tool_execution_coordinator.py`
- `src/mini_agent/agent_core/execution/tool_approval.py`

Owned responsibility:

- tool invocation construction
- approval requests
- authorization checks
- interrupt-aware tool execution
- batch tool-call execution outcome

Compatibility rule:

- `AgentToolExecutionCoordinator` should depend on an explicit runtime contract, not direct reach-through into arbitrary `Agent` fields

### History compaction service

Files:

- `src/mini_agent/agent_core/history/summarization.py`

Owned responsibility:

- safe history compaction
- internal summary-message representation
- summary generation and normalization

### Presentation boundary

Files:

- `src/mini_agent/agent_core/presentation.py`

Owned responsibility:

- structured runtime presentation hooks
- ANSI console compatibility presenter
- headless/null presenter behavior

### Turn-context subsystem

Files:

- `src/mini_agent/agent_core/context/turn_context.py`
- `src/mini_agent/agent_core/context/turn_context_types.py`
- `src/mini_agent/agent_core/context/turn_context_policy.py`
- `src/mini_agent/agent_core/context/turn_context_curation.py`
- `src/mini_agent/agent_core/context/turn_context_diagnostics.py`
- `src/mini_agent/agent_core/context/turn_context_preparation.py`
- `src/mini_agent/agent_core/context/turn_context_providers.py`

Owned responsibility:

- per-turn prepared context
- preparation orchestration and provider execution
- provider readiness and preparation
- policy normalization/filtering
- ranking, dedupe, and budget curation
- diagnostics and operator formatting

Compatibility rule:

- external imports continue to use `turn_context.py`
- implementation ownership lives in the split sibling modules

### Post-turn side-effect service

Files:

- `src/mini_agent/agent_core/post_turn.py`

Owned responsibility:

- post-turn memory automation invocation
- post-turn runtime task-memory writeback invocation
- missing-turn-anchor handling for those two flows
- failure payload/logging continuity for those two flows

## 4. Engine Contract

`src/mini_agent/agent_core/engine.py` is now expected to read like an orchestrator.

The maintained flow is:

1. prepare one turn
2. run planner/executor loop
3. map loop terminal state to `TurnStopReason`
4. delegate post-turn side effects
5. return `TurnExecutionResult`

When adding new behavior, the default question should be:

- does this belong in `Agent` orchestration
- or does it belong in an existing seam

If it does not clearly belong in `Agent`, prefer extending the owned seam instead of adding another inline helper to `engine.py`.

## 5. Allowed Future Growth

Safe future changes:

- add provider implementations inside the turn-context subsystem
- improve tool execution behavior inside the tool coordinator seam
- refine post-turn memory behavior inside `post_turn.py`
- improve summary behavior inside the history seam
- add alternate presenters without changing core runtime ownership

Unsafe future drift:

- surface-specific printing inside `engine.py`
- new memory/runtime side effects added directly after `run_turn()`
- provider ranking/policy logic moved back into `turn_context.py` as one hotspot
- tool approval logic reintroduced directly inside `Agent`

## 6. Reference Paths

- `src/mini_agent/agent_core/engine.py`
- `src/mini_agent/agent_core/runtime_bindings.py`
- `src/mini_agent/agent_core/execution/tool_execution_coordinator.py`
- `src/mini_agent/agent_core/history/summarization.py`
- `src/mini_agent/agent_core/presentation.py`
- `src/mini_agent/agent_core/context/turn_context.py`
- `src/mini_agent/agent_core/post_turn.py`
- `docs/P34_AGENT_CORE_REFACTOR_PLAN_2026-04-15.md`
