# P38 First Closure Plan

Date: 2026-04-16
Status: completed
Scope: round-1 closure / active-path stability / hygiene baseline / honest commit slicing

Execution note (2026-04-16): the project-level evaluation now shows that Mini-Agent is no longer missing its main architecture. The current problem is closure quality: one remaining full-suite failure, active-path contract drift, red lint baseline, and a still-mixed dirty worktree that can easily produce phase-fake commits if we keep developing without a closure pass.

## Goal

Finish the first closure round so the codebase returns to a controlled, trustworthy baseline before more feature work continues.

The target end state for round 1 is:

- full test suite back to green
- active runtime paths free of obvious contract drift
- active-path lint baseline materially improved and explicitly bounded
- the current dirty worktree sliced honestly instead of treated as one giant mixed backlog
- the next round can start from a cleaner baseline rather than from partially-closed refactor residue

This is not a new feature sprint.
It is the first structured closeout pass after the major architecture lines have landed.

## Why This Slice Exists

The current project evaluation shows a very specific shape:

- architecture is mostly landed
- shared core/session/model/memory/runtime paths are materially real
- TUI/CLI/gateway are usable
- but the repository is not yet release-clean

Concrete evidence:

- `uv run pytest -q`
  - result: `1160 passed, 15 skipped, 1 failed`
- `uv run ruff check src tests`
  - result: `57` findings
- the current failing suite point is an active entrance contract drift:
  - `cli.run_tui_mode(...)` now passes `config_loader=...`
  - the test stub in `tests/test_cli_tui_command.py` still expects the older `run_tui(...)` signature
- the current dirty tree still mixes:
  - repo hygiene leftovers
  - model/runtime-governance closure
  - agent-core/kernel adoption residue
  - entrance-level polish

That means the next highest-value work is no longer "invent more structure".
It is to close the most important open loops cleanly.

## Locked Decisions

### 1. Round 1 closure is not full-repo perfection

This round should prioritize active product/runtime paths first.

That means:

- fix active contract drift
- restore green validation
- improve active-path lint baseline

It does not require immediately cleaning every historical/example/non-critical path in the repo.

### 2. Full-suite green takes priority over broad polish

If there is a choice between:

- getting the suite fully green again
- or doing wider style/hygiene cleanup first

the suite wins.

### 3. No phase-fake commits during closure

The current `kernel` area remains a mixed boundary.

Round 1 closure must not accidentally bundle:

- `P34` core-only cleanup
- and `P33b` model/runtime-governance work

under one misleading commit story.

### 4. Active-path lint must be bounded explicitly

The current `ruff` failures include paths that are not equally important to the maintained runtime baseline.

Round 1 should define one explicit active-path lint perimeter and clean that perimeter first.

### 5. Keep closure slices narrow and serial

This round should be closed through small slices such as:

1. contract drift repair
2. active-path hygiene/lint baseline
3. boundary/commit slicing
4. verification and closeout recording

Not through one giant cleanup commit.

## Audit Baseline (2026-04-16)

### Current strongest positive signals

- full test surface is overwhelmingly green
- `agent_core`, `runtime/session`, `model_manager`, `memory`, `gateway`, `transport`, `TUI`, and `Desktop` all have real test coverage
- architecture docs and code direction are materially aligned

### Current strongest blocking signals

- one full-suite failure remains
- `ruff` is still red
- active entrance contract drift exists
- the dirty tree remains too mixed to commit casually
- `kernel` closure is still not phase-honest as a pure core slice

## Planned Slices

### P38.1 Active Entrance Contract Closure

Goals:

- fix the current red test caused by active entrance contract drift
- re-check nearby `CLI / TUI / Desktop / gateway` runtime entry contracts for low-cost mismatches
- make the current entrance signatures internally consistent again

Likely touch points:

- `src/mini_agent/cli.py`
- `src/mini_agent/tui/app.py`
- `tests/test_cli_tui_command.py`
- nearby entrance tests only if the same contract drift appears

Acceptance:

- current full-suite failure is resolved
- active entrance contract is explicit and consistent
- no new entrance-level breakage is introduced during the repair

Execution status (2026-04-16):

- completed
- repaired the active `CLI -> TUI` contract test drift in:
  - [test_cli_tui_command.py](/d:/file/Mini-Agent/tests/test_cli_tui_command.py)
- strengthened the test so it now asserts the injected `config_loader` contract explicitly
- verification:
  - `uv run pytest tests/test_cli_tui_command.py tests/test_cli_unified_mode.py tests/test_tui_app.py -q`
  - result: `155 passed`
  - `uv run pytest -q`
  - result: `1161 passed, 15 skipped`

### P38.2 Active-Path Hygiene Baseline

Goals:

- define the active lint perimeter for the maintained runtime/product path
- clean the highest-signal lint debt inside that perimeter
- avoid spending round-1 closure energy on low-value peripheral cleanup first

Preferred active-path perimeter:

- `src/mini_agent/agent_core/`
- `src/mini_agent/runtime/`
- `src/mini_agent/model_manager/`
- `src/mini_agent/llm/`
- `src/mini_agent/transport/`
- `src/mini_agent/tui/`
- `src/mini_agent/desktop/`
- `src/mini_agent/application/`
- `src/mini_agent/interfaces/`
- `src/mini_agent/cli.py`
- `src/mini_agent/cli_interactive.py`
- `src/apps/agent_studio_gateway/`
- active tests around those areas

Deferred by default in round 1 unless they block the maintained baseline:

- bundled skill/example trees with legacy style debt
- archive docs/assets
- non-critical long-tail helper paths

Acceptance:

- one explicit active-path lint command is green, or
- any remaining exceptions are small, documented, and clearly outside the maintained round-1 perimeter

Execution status (2026-04-16):

- baseline perimeter check completed
- result:
  - `uv run ruff check src/mini_agent/agent_core src/mini_agent/runtime src/mini_agent/model_manager src/mini_agent/llm src/mini_agent/transport src/mini_agent/tui src/mini_agent/desktop src/mini_agent/application src/mini_agent/interfaces src/mini_agent/cli.py src/mini_agent/cli_interactive.py src/apps/agent_studio_gateway tests/test_cli_tui_command.py tests/test_cli_unified_mode.py tests/test_tui_app.py tests/test_transport_gateway_client.py tests/test_transport_remote_session_client.py tests/test_transport_remote_stream_error_service.py tests/test_agent_studio_gateway_api_v1.py tests/test_agent_studio_gateway_integration_flows.py tests/test_desktop_app.py`
  - result: `All checks passed!`
- implication:
  - the remaining repo-wide `ruff` failures are currently outside the maintained round-1 active-path perimeter
  - they should be treated as later closure debt unless they are promoted back into the active baseline intentionally

### P38.3 Boundary And Commit-Slice Closure

Goals:

- prevent the dirty tree from collapsing back into a mixed catch-all backlog
- explicitly separate:
  - round-1 closure work
  - deferred mixed `kernel/model-runtime` work
  - later entrance/product polish

Main closure rule:

- do not land the current `kernel` adoption under a pure `P34` label unless the diff is reduced first

Expected outputs:

- explicit staging boundaries for round 1
- no accidental bundling of mixed `P33b + P34` semantics
- planning-memory sync with the chosen slice boundaries

Acceptance:

- round-1 touched files have one honest commit story
- deferred mixed-boundary work is clearly named and left out

Execution status (2026-04-16):

- preliminary round-1 slice boundary is now explicit
- current round-1 touched files are limited to:
  - [test_cli_tui_command.py](/d:/file/Mini-Agent/tests/test_cli_tui_command.py)
  - [findings.md](/d:/file/Mini-Agent/findings.md)
  - [progress.md](/d:/file/Mini-Agent/progress.md)
  - [task_plan.md](/d:/file/Mini-Agent/task_plan.md)
  - [P38_FIRST_CLOSURE_PLAN_2026-04-16.md](/d:/file/Mini-Agent/docs/P38_FIRST_CLOSURE_PLAN_2026-04-16.md)
- deferred from the closure slice for now:
  - mixed `kernel / model-runtime` dirty-tree work
  - wider repo-wide lint debt outside the active-path perimeter
  - broader entrance/product polish
- implication:
  - the current closure baseline can be advanced without pretending to close the larger mixed worktree in the same commit

### P38.4 Verification And Closeout Report

Goals:

- verify the closure round against code, not just intent
- produce one explicit end-of-round report

Target verification stack:

- `uv run pytest -q`
- active-path `ruff check`
- focused entrance smoke when cheap and deterministic:
  - CLI help / parser / TUI wiring tests
  - desktop bootstrap tests
  - gateway transport/client tests

Acceptance:

- test baseline is green
- active-path hygiene baseline is recorded
- closure outcome and next-round backlog are written down

Execution status (2026-04-16):

- completed
- formal closeout report added:
  - [P38_FIRST_CLOSURE_ROUND1_REPORT_2026-04-16.md](/d:/file/Mini-Agent/docs/P38_FIRST_CLOSURE_ROUND1_REPORT_2026-04-16.md)
- closure decision:
  - round 1 stops at the restored narrow active baseline
  - the closure perimeter is not widened automatically in the same pass
- final round-1 result:
  - full suite green
  - active-path perimeter lint green
  - narrow slice boundary explicit

## Non-Goals

Round 1 closure is not intended to:

- redesign `DesktopUI`
- expand the `QQ` remote adapter feature set
- finish full repo-wide lint cleanup in every bundled/example/archive path
- force the final `kernel` mixed-boundary adoption
- reopen completed architecture lines just because the worktree is still dirty

## Exit Criteria

Round 1 closure is successful when:

- the full suite is green again
- the known active entrance contract drift is closed
- the maintained active-path lint perimeter is materially cleaner and explicitly bounded
- the current dirty tree has a documented slice boundary for what is included vs deferred
- a round-1 closure outcome report exists

## Expected Outcome

If round 1 succeeds, the practical repo state should improve from:

- "architecture mostly landed, but closure still loose"

to:

- "architecture landed, baseline controlled, and next work can proceed without guessing which failures and mixed diffs still belong to the last refactor wave"

This should raise confidence in:

- day-to-day development
- commit honesty
- entrance stability
- later round-2 polish planning

## Round-2 Likely Backlog

After round 1, the most likely next closure candidates are:

1. mixed `kernel / model-runtime` honest landing or reduction
2. broader active-path lint debt beyond the first perimeter
3. `DesktopUI` product-depth improvement
4. remote operational polish for the `QQ` path
5. release-gate style deterministic recheck once the worktree is materially cleaner
