# P36 Session Runtime Contract Consolidation Plan

Date: 2026-04-15
Status: completed
Scope: session/runtime/support seam consolidation above the completed `P35` core line

Execution note (2026-04-15): `P35` locked the maintained `agent_core` runtime seams and established `runtime_bindings` plus `runtime_services` as typed truth. The next meaningful work is no longer more `agent_core` decomposition. It is the consolidation of the session/runtime/surface layer that still reads agent state too directly and refreshes projection state too diffusely.

Execution status (2026-04-15):

- `P36.1` landed:
  - maintained live-agent read helpers now sit in `RuntimeSessionPayloadCodec` / `RuntimeSessionAgentSupport`
  - read-model, snapshot, diagnostics, persistence, and hydration readers were migrated onto that seam
  - the follow-up `normalize_context_policy_payload(...)` binding regression was corrected
- `P36.2` has started with a narrow first cut:
  - live-agent rebuild and runtime-reset paths now refresh projection diagnostics through the shared hydrator path instead of bespoke partial rewrites
- `P36.2` has now extended that path to additional live mutations:
  - runtime-policy reconfigure and local agent-control flows now refresh live KB / memory / sandbox projection state through a shared runtime-owned entry point
- `P36.2` has also extended the maintained normalization story into operator writeback:
  - operator-side `context_policy` storage now uses the maintained payload normalization seam
  - detached runtime-policy fallback now stores normalized sandbox diagnostics instead of bypassing the maintained payload contract
- `P36.2` now also reuses the maintained model-identity owner across runtime and TUI:
  - `RuntimeSessionModelIdentityCodec` now handles selected/pending projection-shape reads and writes
  - TUI session sync and local identity helpers now reuse that codec instead of keeping a parallel identity contract
- `P36.2` now also extends the refresh/normalization seam across the remaining high-traffic TUI-local runtime paths:
  - TUI local KB helpers now reuse `RuntimeSessionAgentSupport`
  - TUI payload normalization now reuses `RuntimeSessionPayloadCodec`
  - local context snapshot refresh, local context-policy writeback, local KB toggles, and local runtime-policy reconfigure now converge on one TUI-local `refresh/capture` projection path instead of separate field rewrites
- `P36.2` now also removes the remaining split local prepared-context turn-result path in TUI:
  - local scheduler/chat turn completion now records prepared-context payloads and diagnostics through one maintained local writeback helper
  - prepared-context command feedback now reads final synchronized projection state rather than raw completion payloads
  - omission of diagnostics from local completion payloads no longer forces the TUI projection back to empty when the attached agent already has current prepared-context diagnostics
- `P36.3` has now started with a narrow shared test-carrier cut:
  - `tests/runtime_contract_fixtures.py` now defines one maintained runtime-facing agent test double aligned with the contract introduced by `P35` and expanded by `P36.1`
  - the main `CLI / TUI / Surface` verification line now reuses that carrier instead of maintaining three separate ad hoc runtime-services / route / prepared-context / KB stories
- `P36.3` now also extends that shared fixture line into runtime/session handler tests:
  - `tests/runtime_contract_fixtures.py` now defines narrow shared helpers for session/projection/runtime/policy/sandbox carrier shapes
  - runtime/session handler tests now reuse maintained contract-shaped fixtures instead of repeatedly rebuilding the same `SimpleNamespace(...)` shells inline
- `P36.3` now also extends the same fixture line into record/snapshot/diagnostics tests:
  - `tests/runtime_contract_fixtures.py` now defines narrow lineage/transcript carrier helpers alongside the session/runtime helpers
  - snapshot/persistence/payload/diagnostics/control tests now reuse the maintained fixture line instead of rebuilding the same record/session shells inline
- `P36.3` now also extends the shared fixture line into runtime/session identity and control tests:
  - model-identity and operator-handler tests now reuse the maintained runtime/session/projection helpers instead of bespoke carrier shells
  - admin, MCP-control, and pending-approval tests now reuse the same maintained session/projection/runtime/transcript helpers
  - remaining inline `SimpleNamespace(...)` usage inside `tests/test_runtime_session_*` is now much more concentrated in domain-local payload rows, handler dependency stubs, or tiny lifecycle/hydration shells rather than repeated runtime contract carriers
- `P36.3` has now also closed the remaining worthwhile tail cleanup:
  - recovery-reset, lifecycle, and hydration-coordinator tests now reuse the maintained session shell where that shared carrier matches the maintained contract
  - the remaining inline wrappers are now mostly local test payloads or dependency stubs, not a missing shared runtime/session carrier seam
- `P36` exit criteria are now materially satisfied:
  - the common runtime/session reads are behind maintained support seams
  - projection refresh/writeback paths are materially more consolidated
  - runtime-facing surfaces and tests now depend much less on raw agent/session internals

## Goal

Upgrade the session/runtime layer so it becomes:

- more explicit about what session-facing code is allowed to read from a live agent
- less dependent on repeated `getattr(...)` reach-through patterns
- more consistent when refreshing projection state after runtime mutations
- easier to keep aligned across `CLI / TUI / Surface / Runtime Manager`
- easier to test without per-file fake agents reinventing partial runtime shape

This is not a new feature sprint.
It is a contract-consolidation sprint above the now-completed `P35` core seams.

## Why This Slice Exists

`P35` solved the most dangerous follow-up problems inside `agent_core`:

- runtime binding truth is now typed
- tool execution owns its own runtime contract
- prepared turn-context orchestration is extracted
- history compaction semantics are tightened
- approval binding failure is explicit
- runtime consumers for sandbox/runtime policy now use the runtime-services contract

But the next structural friction is still visible one layer up:

- session/runtime code still reaches into `session.runtime.agent` for many read concerns
- multiple helpers still reconstruct token usage, message snapshots, KB state, prepared context, and diagnostics in parallel
- projection refreshes after rebuilds and local mutations are still spread across handlers
- tests often need custom fake agents because the maintained read contract is not narrow enough yet

Those are no longer `P35` problems.
They are session/runtime contract problems.

## Locked Decisions

### 1. `P35` core seams remain locked

`P36` does not reopen:

- `runtime_bindings` vs `runtime_services` ownership
- tool execution seam ownership
- turn-context orchestration ownership
- post-turn side-effect ownership
- `Agent` facade slimming decisions

### 2. `runtime_services` remains the typed service truth

Policy, sandbox, approval, and approval-handler service reads should continue to treat `runtime_services` as authoritative.

`P36` may add support/read helpers above that truth.
It should not invent a competing service-truth layer.

### 3. Session projection remains derived state

`session.projection` is an operator/read-model surface.
It is not the new source of truth for live runtime state.

`P36` should make projection refreshes more explicit.
It should not invert the relationship and make projection authoritative over the runtime.

### 4. Local and remote surfaces must stay aligned

`P36` should reduce local reach-through without creating a local-only runtime story that diverges from remote/session surfaces.

### 5. No big-bang runtime-manager rewrite

This line should stay slice-by-slice:

- narrow support-seam expansions
- targeted migrations
- passing focused tests after each cut

## Current State Diagnosis

### Strengths to preserve

- `RuntimeSessionAgentSupport` already owns agent build/config/KB helper behavior
- `RuntimeSessionPayloadCodec` already owns serialization and token normalization primitives
- `RuntimeSessionDiagnosticsService` already owns sandbox and memory diagnostics composition
- `SessionRuntimePolicyService` already owns runtime-policy planning semantics

### Main structural weaknesses

- read-side agent access is still broader than it should be
- token usage / token limit / message snapshot reads are still field-oriented instead of seam-oriented
- prepared-context and memory diagnostic reads still depend on direct agent shape in several places
- projection refresh logic after rebuilds, toggles, and operator actions is still distributed
- test doubles still need to mimic ad hoc agent internals instead of one maintained runtime-facing contract

## Target Architecture

### A. Session runtime support seam

The maintained runtime support layer should explicitly own the common read-side agent contract used by runtime and surfaces.

Target read concerns:

- token usage
- token limit
- serialized message snapshot access
- knowledge-base enabled truth
- route/model identity
- effective runtime policy
- prepared-context state and diagnostics
- memory automation and runtime-task-memory diagnostics

### B. Projection refresh consolidation

Projection updates after these events should use a more explicit shared path:

- agent rebuild
- runtime policy change
- knowledge-base toggle
- local control actions
- turn completion and post-turn refresh

### C. Test/runtime carrier unification

Fake agents used by runtime/surface tests should align around the maintained session/runtime support contract instead of each file growing its own partial runtime behavior.

## Planned Slices

### P36.1 Runtime Agent Support Expansion

Likely files:

- `src/mini_agent/runtime/session_agent_support.py`
- `src/mini_agent/runtime/session_payload_codec.py`
- `src/mini_agent/runtime/session_diagnostics_service.py`
- `src/mini_agent/runtime/session_model_identity_codec.py`

Goals:

- add explicit helpers for the most common runtime-facing agent reads
- reduce repeated field-by-field reads in downstream callers
- keep compatibility with current `Agent` facade and lightweight test doubles

Acceptance:

- at least the high-frequency read concerns above are available through maintained helper/service paths
- downstream runtime/surface readers can stop repeating the same `getattr(...)` logic

### P36.2 Projection Refresh Path Consolidation

Likely files:

- `src/mini_agent/runtime/session_runtime_state_hydrator.py`
- `src/mini_agent/runtime/session_read_model_builder.py`
- `src/mini_agent/runtime/session_operator_handler.py`
- `src/mini_agent/tui/app.py`

Goals:

- identify the repeated projection refresh patterns
- move them behind clearer runtime-owned refresh logic
- preserve current operator-visible behavior while reducing drift risk

Acceptance:

- local runtime mutations no longer need multiple bespoke refresh snippets to keep projection state coherent
- projection refresh logic reads like a maintained path instead of scattered field updates

### P36.3 Surface/Test Contract Cleanup

Likely files:

- targeted surface/runtime test files
- any small shared fake runtime carrier/helper that proves useful

Goals:

- align runtime-facing tests with the maintained session/runtime contract
- reduce ad hoc fake-agent shape differences between CLI, TUI, and surface tests

Acceptance:

- test doubles for runtime-facing code rely on the maintained contract shape
- adding new session/runtime tests should require less one-off fake-agent plumbing

## Verification Strategy

After each slice:

- run focused `pytest` coverage for touched runtime/surface areas
- run `ruff check` on touched files
- prefer proving contract behavior with narrow regression tests instead of broad repo-wide runs

Likely verification targets:

- `tests/test_main_agent_surface_service.py`
- `tests/test_tui_app.py`
- `tests/test_cli_submission_loop.py`
- `tests/test_runtime_policy_service.py`
- `tests/test_sandbox_state.py`
- runtime/session handler test files touched by the slice

## Out Of Scope

This line should not absorb:

- provider/runtime supply redesign
- new `agent_core` execution architecture
- new surface feature work unrelated to runtime contract consolidation
- broad persistence redesign unless directly required by projection/runtime contract cleanup

## Exit Criteria

`P36` should be considered complete when:

- the most common session/runtime agent reads are owned by maintained support seams
- projection refreshes are materially less duplicated
- runtime-facing surfaces depend less on raw agent internals
- tests no longer need widespread bespoke fake-agent shapes for basic runtime state access
