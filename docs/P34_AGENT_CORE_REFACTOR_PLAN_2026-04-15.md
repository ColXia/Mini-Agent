# P34 Agent-Core Refactor Plan

Date: 2026-04-15
Status: completed
Scope: agent-core runtime contract / execution decomposition / headless boundary / context modularization

Execution note (2026-04-16): `P32` cleaned physical ownership and boundary naming, and `P33/P33b` stabilized the model/runtime/provider side. `P34` should now be treated as completed historical planning, with later landing detail carried in `task_plan.md`, `progress.md`, and `findings.md`.

## Goal

Upgrade `agent_core` so it remains:

- usable as the current shared runtime kernel
- easier to evolve without centralizing every concern into `Agent`
- more explicit about runtime contracts and side effects
- more headless and reusable across `CLI / TUI / Desktop / Remote`
- safer for future work on streaming, delegation, memory, and tool execution

This slice is not a new feature sprint.
It is a structural hardening sprint for the current core.

## Why This Slice Exists

The current `agent_core` already has real strengths:

- one unified kernel bootstrap path
- a clear outer submission loop plus inner planner/executor loop
- a strong turn-context preparation subsystem
- injected model routing and failover instead of model logic embedded in `Agent`
- workable approval, sandbox, skill, and MCP integration

But the current implementation also shows a clear next risk class:

- `src/mini_agent/agent_core/engine.py` has become a god object
- `src/mini_agent/agent_core/context/turn_context.py` is both the strongest subsystem and the second large hotspot
- runtime attachments still depend on dynamic `setattr(...)`
- turn-scoped policy override still mutates type shape
- console rendering still leaks into core runtime execution
- message summarization still has semantically unsafe history rewriting
- declarative tool metadata is ahead of actual runtime execution behavior

Those are no longer `P33` provider/runtime-truth problems.
They are core-kernel maintenance problems.

## Locked Decisions

### 1. `P33` and `P33b` stay locked as runtime/model foundation

`P34` does not reopen:

- provider registry truth
- protocol binding ownership
- native streaming foundation
- exact-vs-automatic route intent
- provider governance and discovery integrity

Those are now upstream runtime foundations.

### 2. Framework skeleton stays locked

`P34` must stay aligned with `docs/FRAMEWORK_SKELETON.md`.

This means:

- no surface-specific logic moves into `agent_core`
- no session truth moves into entrances
- no adapter-owned runtime forks

### 3. Two-layer execution model remains correct

The current split remains the maintained shape:

- outer submission/scheduler loop
- inner planner/executor loop

`P34` may refine responsibilities inside those layers, but it should not replace the model with a new architecture family.

### 4. Turn context remains provider-based and ephemeral

`P34` may modularize the subsystem, but it should not remove:

- provider-based preparation
- per-turn curation
- ephemeral prompt injection
- diagnostics visibility

### 5. Approval and runtime policy remain declarative

`P34` should strengthen typed contracts around approval/runtime policy.
It should not regress into ad-hoc approval checks spread across surfaces.

### 6. No big-bang rewrite

The implementation strategy must stay slice-by-slice:

- narrow cuts
- passing targeted tests after each cut
- behavior-preserving refactors first
- semantic corrections only when the seam is ready

### 7. Parallel tool execution is not a mandatory first cut

The current mismatch between declarative tool metadata and execution behavior is real, but `P34` should not force speculative parallel execution before the coordinator boundary is explicit.

## Current State Diagnosis

### Strengths to preserve

- `agent_core/kernel.py` is already a strong composition root
- `FailoverLLMClient` is correctly injected instead of baked into the core
- `AgentSubmissionLoop` already models queueing, interruption, approval waiting, and progress publication well
- turn-context preparation has good provider, ranking, curation, and diagnostics mechanics
- approval and runtime-policy layering is already good enough to preserve

### Main structural weaknesses

- `Agent` mixes:
  - planning/execution
  - tool authorization and invocation
  - summarization/history mutation
  - memory automation and runtime task memory
  - console output and telemetry
- `turn_context.py` mixes:
  - provider implementations
  - ranking and curation
  - formatting
  - diagnostics
  - policy interpretation
- dynamic runtime attachments weaken contracts:
  - `runtime_route`
  - `skill_runtime`
  - `skill_catalog_loader`
  - `kernel_diagnostics`
  - `tool_approval_handler`
- `_turn_policy_override(...)` still mutates `execution_policy` into a plain dict
- summarization still writes assistant execution summaries back as `role="user"`
- tool metadata exposes `concurrency_safe`, but actual execution remains strictly sequential

## Target Architecture

### A. Core facade model

`Agent` should remain the recognizable runtime facade, but it should become thinner.

Target responsibilities for `Agent`:

- own conversation state
- coordinate one turn execution
- delegate sub-behaviors to explicit services

Responsibilities to move behind services:

- tool execution coordination
- history compaction / summarization
- post-turn side effects
- console/presentation output

### B. Typed runtime bindings

Runtime assembly should stop depending on dynamic attribute injection.

Target shape:

- one explicit runtime-binding object or equivalent typed contract
- clear ownership for:
  - route diagnostics
  - skill runtime
  - skill catalog access
  - approval bridge
  - kernel diagnostics

### C. Execution decomposition

The execution core should separate:

1. planning loop
2. tool execution coordinator
3. post-turn automation
4. history management

This does not require turning the runtime into a large service graph.
It requires shrinking the number of unrelated reasons for `engine.py` to change.

### D. Headless core boundary

Core runtime execution should not own ANSI or terminal presentation logic.

Target pattern:

- core emits structured execution information
- surfaces decide how to render it
- compatibility bridge may remain temporarily for CLI/TUI migration

### E. Turn-context package decomposition

Turn-context should become a package-level subsystem with explicit ownership areas:

- provider implementations
- curation and ranking
- formatting
- diagnostics
- policy helpers

### F. History and summary semantics

Compaction/summarization should remain possible, but stored summaries must stop pretending to be fresh user input.

### G. Tool execution contract completion

The runtime should make one explicit choice:

- either keep sequential execution and document that metadata is advisory only
- or introduce bounded parallelism for truly safe tool classes

The current silent mismatch should end.

## Non-Goals

`P34` is not intended to:

- reopen provider routing or provider governance design
- redesign session/application/runtime ownership
- add a new user entrance or bring browser UI back
- introduce a brand-new agent architecture family
- fully redesign cross-platform sandboxing
- force parallel tool execution before coordinator boundaries are in place

## Detailed Upgrade Plan

## P34.1 Runtime Binding Contract Hardening

### Objective

Replace dynamic runtime attachment patterns with explicit typed runtime bindings.

### Changes

- introduce a typed runtime-binding model for agent-core runtime assembly
- stop assigning runtime surfaces through ad-hoc `setattr(...)`
- make approval bridge ownership explicit rather than a dynamic field mutation
- keep diagnostics reachable through typed runtime state rather than hidden dynamic fields

### Likely touch points

- `src/mini_agent/agent_core/kernel.py`
- `src/mini_agent/agent_core/execution/agent_loop.py`
- new `src/mini_agent/agent_core/*runtime_bindings*.py` or equivalent contract file
- tests covering kernel/bootstrap and submission-loop contract behavior

### Acceptance

- runtime bootstrap no longer relies on dynamic `setattr(...)` for core bindings
- submission loop uses an explicit approval bridge contract
- kernel and loop tests pass without compatibility regressions

## P34.2 Turn-Scoped Policy Contract Hardening

### Objective

Remove type mutation from turn-scoped execution policy override.

### Changes

- stop rewriting `agent.execution_policy` into a plain dict
- introduce a typed turn policy application path
- keep `max_steps` and `max_tool_calls_per_step` override behavior unchanged
- make scheduler-to-agent execution policy flow explicit

### Likely touch points

- `src/mini_agent/agent_core/execution/scheduler.py`
- `src/mini_agent/agent_core/engine.py`
- `tests/test_agent_core_execution_loop.py`
- `tests/test_agent_core_execution_policy.py`

### Acceptance

- `TurnScheduler` no longer changes the type shape of `agent.execution_policy`
- turn overrides still work for max-steps and max-tool-call budgets
- targeted scheduler/policy tests stay green

## P34.3 Tool Execution Coordinator Extraction

### Objective

Move authorization + invocation flow out of the main `Agent` class.

### Changes

- extract tool authorization and execution sequencing into a dedicated coordinator/service
- preserve current approval, runtime-policy, and logging behavior
- keep current sequential execution first unless the seam is ready for bounded parallel reads
- define where `concurrency_safe` will actually matter

### Likely touch points

- `src/mini_agent/agent_core/engine.py`
- `src/mini_agent/agent_core/execution/tools/*`
- new `src/mini_agent/agent_core/execution/*coordinator*.py` or equivalent
- tool execution and approval regression tests

### Acceptance

- `Agent` no longer directly owns the entire tool authorization/execution body
- current tool behavior and approval round-trips remain intact
- concurrency policy is documented in code and tests

### Status Update (2026-04-15)

- completed
- landed the first tool-execution seam as:
  - `src/mini_agent/agent_core/execution/tool_approval.py`
  - `src/mini_agent/agent_core/execution/tool_execution_coordinator.py`
- `src/mini_agent/agent_core/engine.py` now keeps only thin compatibility wrappers plus batch-state to `StepOutcome` mapping
- targeted verification:
  - `uv run ruff check src/mini_agent/agent_core/engine.py src/mini_agent/agent_core/execution/tool_approval.py src/mini_agent/agent_core/execution/tool_execution_coordinator.py src/mini_agent/agent_core/execution/__init__.py tests/test_agent_core_execution_policy.py tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_tools.py tests/test_agent_core_execution_permissions.py`
  - `uv run pytest tests/test_agent_core_execution_policy.py tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_tools.py tests/test_agent_core_execution_permissions.py tests/test_main_agent_surface_service.py -q`
  - result: `114 passed`
- next active slice:
  - `P34.4` history and summarization semantics correction

## P34.4 History And Summarization Semantics Correction

### Objective

Make history compaction explicit and semantically safe.

### Changes

- extract summarization/history mutation into a dedicated service
- stop writing execution summaries back as `role="user"`
- define a safer internal summary representation
- keep token-budget protection intact

### Likely touch points

- `src/mini_agent/agent_core/engine.py`
- `src/mini_agent/agent_core/context/context_compaction.py`
- new history/summarization service module
- engine and compaction tests

### Acceptance

- execution summaries are no longer injected as fake user turns
- compaction still reduces history size when limits are exceeded
- compaction behavior remains observable and test-covered

### Status Update (2026-04-15)

- completed
- landed the first dedicated history-compaction seam as:
  - `src/mini_agent/agent_core/history/summarization.py`
  - `src/mini_agent/agent_core/history/__init__.py`
- `src/mini_agent/agent_core/engine.py` now delegates history summarization and mutation to the extracted service
- safer summary representation is now:
  - `role="assistant"`
  - `name="__mini_agent_history_summary__"`
  - content prefixed with `[Internal Assistant Summary]`
- compatibility behavior:
  - legacy fake-user summary messages are normalized into the new internal summary shape during compaction
  - already compacted internal summary messages are preserved instead of being re-summarized as if they were raw execution turns
- targeted verification:
  - `uv run ruff check src/mini_agent/agent_core/engine.py src/mini_agent/agent_core/history/__init__.py src/mini_agent/agent_core/history/summarization.py tests/test_agent_core_history_summarization.py`
  - `uv run pytest tests/test_agent_core_history_summarization.py tests/test_agent_core_execution_policy.py tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_tools.py tests/test_agent_core_execution_permissions.py tests/test_main_agent_surface_service.py -q`
  - result: `117 passed`
- next active slice:
  - `P34.5` headless core presentation boundary

## P34.5 Headless Core Presentation Boundary

### Objective

Remove terminal presentation concerns from the core runtime path.

### Changes

- extract console/ANSI rendering from `Agent`
- keep structured hook/event output as the canonical execution signal
- add a temporary compatibility presenter bridge if needed for CLI/TUI
- make headless execution a first-class outcome of the core, not a side effect of suppressing output

### Likely touch points

- `src/mini_agent/agent_core/engine.py`
- `src/mini_agent/cli_interactive.py`
- `src/mini_agent/tui/`
- hook/event tests and live-engine regression surfaces

### Acceptance

- core runtime execution no longer depends on ANSI/console formatting helpers
- CLI/TUI still render equivalent operator feedback through an adapter/presenter layer
- headless execution remains stable

### Status Update (2026-04-15)

- completed
- landed the first presentation seam as:
  - `src/mini_agent/agent_core/presentation.py`
- rewired the core runtime path to presenter-owned output:
  - `src/mini_agent/agent_core/engine.py`
  - `src/mini_agent/agent_core/execution/tool_execution_coordinator.py`
  - `src/mini_agent/agent_core/history/summarization.py`
- compatibility behavior:
  - `console_output=True` now selects an ANSI console presenter bridge
  - `console_output=False` now selects a null presenter instead of relying on direct print guards inside core logic
  - custom presenters can be injected directly for alternate rendering or capture
- targeted verification:
  - `uv run ruff check src/mini_agent/agent_core/engine.py src/mini_agent/agent_core/presentation.py src/mini_agent/agent_core/execution/tool_execution_coordinator.py src/mini_agent/agent_core/history/summarization.py tests/test_agent_core_history_summarization.py tests/test_agent_core_presentation.py`
  - `uv run pytest tests/test_agent_core_presentation.py tests/test_agent_core_history_summarization.py tests/test_agent_core_execution_policy.py tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_tools.py tests/test_agent_core_execution_permissions.py tests/test_main_agent_surface_service.py -q`
  - result: `119 passed`
- next active slice:
  - `P34.6` turn-context package decomposition

## P34.6 Turn-Context Package Decomposition

### Objective

Split the turn-context hotspot into a maintainable package structure without losing current behavior.

### Changes

- separate provider implementations from curation, formatting, diagnostics, and policy helpers
- keep the public import surface stable during the cut
- preserve provider readiness, failure capture, ranking, dedupe, and budget behavior
- make future provider additions safer and more local

### Likely touch points

- `src/mini_agent/agent_core/context/turn_context.py`
- new modules under `src/mini_agent/agent_core/context/`
- provider builder and turn-context tests

### Acceptance

- current turn-context behavior remains unchanged from a runtime perspective
- public imports remain stable or are migrated cleanly in one slice
- turn-context tests continue to cover provider behavior, curation, and diagnostics

### Status Update (2026-04-15)

- completed
- landed the turn-context package split as:
  - `src/mini_agent/agent_core/context/turn_context_types.py`
  - `src/mini_agent/agent_core/context/turn_context_policy.py`
  - `src/mini_agent/agent_core/context/turn_context_curation.py`
  - `src/mini_agent/agent_core/context/turn_context_diagnostics.py`
  - `src/mini_agent/agent_core/context/turn_context_providers.py`
- `src/mini_agent/agent_core/context/turn_context.py` now remains as a thin compatibility facade that preserves the public import surface
- compatibility behavior:
  - provider builder and existing runtime call sites continue importing from `turn_context.py`
  - provider readiness, policy filtering, ranking, dedupe, curation budgets, and diagnostics formatting remain behavior-preserving
  - internal helper ownership is now grouped by responsibility instead of living in one hotspot file
- targeted verification:
  - `uv run ruff check src/mini_agent/agent_core/context/turn_context.py src/mini_agent/agent_core/context/turn_context_types.py src/mini_agent/agent_core/context/turn_context_policy.py src/mini_agent/agent_core/context/turn_context_curation.py src/mini_agent/agent_core/context/turn_context_diagnostics.py src/mini_agent/agent_core/context/turn_context_providers.py src/mini_agent/runtime/turn_context_provider_builder.py tests/test_agent_core_turn_context.py tests/test_agent_core_kernel.py`
  - `uv run pytest tests/test_agent_core_turn_context.py tests/test_agent_core_kernel.py tests/test_memoria_runtime.py tests/test_memory_automation.py tests/test_memory_real_use_flow.py -q`
  - result: `60 passed`
- next active slice:
  - `P34.7` post-turn side-effect service extraction

## P34.7 Post-Turn Side-Effect Service Extraction

### Objective

Separate execution completion from memory/runtime side effects.

### Changes

- extract post-turn memory automation and runtime task memory recording from the core run loop
- define one explicit post-turn processing service
- keep the stop-reason-driven behavior unchanged

### Likely touch points

- `src/mini_agent/agent_core/engine.py`
- `src/mini_agent/memory/*`
- runtime task memory integration points

### Acceptance

- `Agent.run_turn()` becomes thinner after completion-state mapping
- post-turn side effects are owned by a dedicated service
- memory/runtime-task behavior remains covered and unchanged

### Status Update (2026-04-15)

- completed
- landed the first dedicated post-turn side-effect seam as:
  - `src/mini_agent/agent_core/post_turn.py`
- rewired the core turn-completion path to service-owned side effects:
  - `src/mini_agent/agent_core/engine.py`
- compatibility behavior:
  - `Agent` still keeps `last_memory_automation` and `last_runtime_task_memory` as the observable turn result state
  - existing constructor injection for `turn_memory_automation` and `turn_runtime_task_memory` remains unchanged
  - memory automation and runtime task-memory writeback still preserve:
    - missing-turn-anchor handling
    - failure payload semantics
    - logger event names
    - stop-reason-driven gating
- targeted verification:
  - `uv run ruff check src/mini_agent/agent_core/engine.py src/mini_agent/agent_core/post_turn.py tests/test_agent_core_post_turn.py tests/test_memory_automation.py src/mini_agent/agent_core/kernel.py`
  - `uv run pytest tests/test_agent_core_post_turn.py tests/test_memory_automation.py tests/test_memoria_runtime.py tests/test_memory_real_use_flow.py tests/test_agent_core_kernel.py tests/test_agent_core_streaming.py -q`
  - result: `41 passed`
- next active slice:
  - `P34.8` final agent-facade slimming and architecture lock

## P34.8 Final Agent-Facade Slimming And Architecture Lock

### Objective

Close the refactor by turning `Agent` into a thinner orchestrator with locked boundaries.

### Changes

- remove now-obsolete inline helper bodies after extractions land
- update docs and public architecture references
- add a small contract document or doc section that states the final `agent_core` runtime seams

### Acceptance

- `engine.py` is materially smaller and more obviously orchestrational
- current runtime tests remain green
- active docs teach the new core ownership correctly

### Status Update (2026-04-15)

- completed
- removed obsolete thin wrappers from:
  - `src/mini_agent/agent_core/engine.py`
- clarified the maintained history-application seam in:
  - `src/mini_agent/agent_core/engine.py`
- added one explicit agent-core seam contract document:
  - `docs/AGENT_CORE_RUNTIME_SEAMS.md`
- updated active architecture references to point at the locked seam model:
  - `docs/ARCHITECTURE.md`
  - `docs/FRAMEWORK_SKELETON.md`
- extended the public top-level `mini_agent.agent_core` export surface with the maintained seam types:
  - `src/mini_agent/agent_core/__init__.py`
- added focused compatibility/export coverage:
  - `tests/test_agent_core_exports.py`
  - updated `tests/test_agent_core_history_summarization.py`
  - updated `tests/test_agent_core_presentation.py`
- targeted verification:
  - `uv run ruff check src/mini_agent/agent_core/engine.py src/mini_agent/agent_core/post_turn.py src/mini_agent/agent_core/__init__.py tests/test_agent_core_history_summarization.py tests/test_agent_core_presentation.py tests/test_agent_core_exports.py docs/AGENT_CORE_RUNTIME_SEAMS.md`
  - `uv run pytest tests/test_agent_core_history_summarization.py tests/test_agent_core_presentation.py tests/test_agent_core_post_turn.py tests/test_agent_core_exports.py tests/test_agent_core_kernel.py tests/test_agent_core_execution_policy.py tests/test_agent_core_execution_tools.py tests/test_agent_core_execution_loop.py tests/test_agent_core_streaming.py tests/test_memory_automation.py -q`
  - result: `65 passed`
- program status:
  - `P34` is now complete as the planned agent-core structural hardening line
  - the next work should start from a fresh evaluation slice, not by reopening `P34` blindly

## Recommended Execution Order

The safest order is:

1. `P34.1` runtime binding contract hardening
2. `P34.2` turn-scoped policy contract hardening
3. `P34.3` tool execution coordinator extraction
4. `P34.4` history and summarization semantics correction
5. `P34.5` headless core presentation boundary
6. `P34.6` turn-context package decomposition
7. `P34.7` post-turn side-effect service extraction
8. `P34.8` final facade slimming and doc lock

## Recommended First Delivery Cut

The recommended first implementation slice is:

- `P34.1`
- `P34.2`

Reason:

- they are narrow
- they remove two obvious contract smells immediately
- they reduce future extraction risk for every later `P34` cut
- they should have the lowest behavior-change risk relative to the payoff

Status note (2026-04-15):

- `P34.1`
- `P34.2`
- `P34.3`
- `P34.4`
- `P34.5`
- `P34.6`
- `P34.7`
- `P34.8`

are now landed; `P34` is complete and the next recommended work should begin from a fresh post-`P34` evaluation.

## Verification Strategy

Each slice should run its own targeted tests first, then a broader runtime sweep.

Primary targeted suite:

- `uv run pytest tests/test_agent_core_kernel.py -q`
- `uv run pytest tests/test_agent_core_execution_loop.py -q`
- `uv run pytest tests/test_agent_core_execution_policy.py -q`
- `uv run pytest tests/test_agent_core_execution_tools.py -q`
- `uv run pytest tests/test_agent_core_turn_context.py -q`
- `uv run pytest tests/test_agent_core_streaming.py -q`

Rolling runtime sweep:

- `uv run pytest tests/test_cli_submission_loop.py tests/test_main_agent_surface_service.py -q`
- `uv run pytest -q`

## Success Criteria

`P34` should be considered successful when:

- `Agent` is no longer the owner of unrelated runtime concerns
- runtime bindings are explicit and typed
- scheduler no longer mutates policy type shape
- core execution is meaningfully more headless
- turn-context is easier to evolve without one giant hotspot file
- summarization/history semantics stop leaking false user intent
- active documentation teaches the corrected `agent_core` shape
