# Mini-Agent Dev Log (2026-04-04)

## 1. Goals for This Cycle
- Close out prior P10 infrastructure work to avoid system-level faults.
- Record a traceable development log with validation evidence.
- Pivot from observability scaling to Agent design development (P11 kickoff).

## 2. Infrastructure Closure Status

### 2.1 P10 hardening items verified as landed
- Export queue persistence snapshot with `checksum_sha256` integrity gate.
- Worker bootstrap failure handling marks job `failed` immediately (no fake-running stuck state).
- Export cancel, restart replay, throughput controls, metrics, and metrics history paths are implemented and covered.

### 2.2 Validation run in this cycle
- `pytest -q tests/test_agent_execution_policy.py tests/test_acp.py tests/test_gateway_routers.py tests/test_gateway_security.py`
  - Result: `29 passed`
- `pytest -q tests/test_agent_execution_policy.py tests/test_acp.py`
  - Result: `9 passed`
- `pytest -q tests/test_gateway_routers.py tests/test_session_store_persistence.py tests/test_gateway_security.py`
  - Result: `27 passed`
- `pytest -q tests/test_agent_execution_policy.py tests/test_acp.py tests/test_gateway_routers.py tests/test_session_store_persistence.py tests/test_gateway_security.py`
  - Result: `38 passed`
- `pytest -q tests/test_gateway_routers.py tests/test_gateway_security.py tests/test_session_store_persistence.py`
  - Result: `28 passed`
- `pytest -q tests/test_agent_execution_policy.py tests/test_acp.py tests/test_gateway_routers.py tests/test_session_store_persistence.py tests/test_gateway_security.py`
  - Result: `39 passed`
- `pytest -q tests/test_gateway_routers.py tests/test_session_store_persistence.py tests/test_gateway_security.py`
  - Result: `30 passed`
- `pytest -q tests/test_agent_execution_policy.py tests/test_acp.py tests/test_gateway_routers.py tests/test_session_store_persistence.py tests/test_gateway_security.py`
  - Result: `41 passed`
- `python scripts/test_stable.py`
  - Result: `172 passed, 25 deselected`

Conclusion: stable suite passes and no blocking system-level regression was found.

## 3. Agent Design Pivot (P11.1 landed)

### 3.1 Execution policy model (hard refactor, no compatibility shell)
- Added runtime models in `mini_agent/agent.py`:
  - `AgentExecutionPolicy`
  - `StepExecutionState`
- Added policy input:
  - `max_tool_calls_per_step`
- Added per-step execution counters:
  - `requested_tool_calls`
  - `executed_tool_calls`
  - `truncated_tool_calls`

### 3.2 Runtime guardrails and telemetry
- Tool-call budget truncation event:
  - `step.tool_calls_truncated`
- Per-step completion event:
  - `step.completed`

### 3.3 Runtime wiring (CLI, Gateway, ACP)
- Config and examples:
  - `mini_agent/config.py`
  - `mini_agent/config/config.yaml`
  - `mini_agent/config/config-example.yaml`
- Runtime constructor wiring:
  - `mini_agent/cli_interactive.py`
  - `gateway/routers/chat.py`
  - `mini_agent/acp/__init__.py`

### 3.4 Test coverage
- Added `tests/test_agent_execution_policy.py` for:
  - Agent loop budget truncation behavior
  - Agent unlimited mode behavior
  - ACP turn behavior with same budget policy

### 3.5 P11.2 run-loop split landed
- Refactored `Agent.run` to use explicit planner/executor/transition phases:
  - planner: `_plan_step(...)`
  - executor: `_execute_tool_calls(...)`
  - transition contracts: `StepPlan`, `StepOutcome`, `StepTransition`
- Added shared timing finalization path:
  - `_finalize_step_timing(...)`
- Added transition-level tests:
  - planner failure transition
  - executor complete transition

### 3.6 P11.3 failure envelope and metrics wiring landed
- Added structured step failure envelope:
  - `StepFailureEnvelope` with `error_type`, `recoverable`, `retryable`
  - `step.failed` event payload now includes failure envelope
- Added run-level metrics model:
  - `RunExecutionMetrics`
  - terminal run events now include `metrics` payload
- Added test coverage:
  - failure envelope assertions
  - `run.failed` metrics payload assertions

### 3.7 P11.4 policy surfaces landed
- Exposed execution policy in session inspection APIs:
  - `/api/sessions`
  - `/api/sessions/{session_id}/history`
- Exposed execution policy in chat response surfaces:
  - `POST /api/chat`
  - `GET /api/chat/stream` done payload
- Persisted policy metadata in session store:
  - active and inactive session records now both report policy fields
- Added coverage:
  - gateway router policy field assertions
  - session store persistence policy assertions

### 3.8 P11.5 shared planner/executor facade landed
- Extracted reusable planner/executor facade in `mini_agent/agent.py`:
  - shared loop: `_run_planner_executor_loop(...)`
  - turn entry point: `run_turn(...)`
  - facade contracts: `PlannerExecutorHooks`, `TurnExecutionResult`, `TurnStopReason`
- Moved ACP turn execution to shared facade:
  - removed duplicated ACP-local planner/executor loop
  - wired ACP streaming updates through facade callbacks
  - ACP session agent now uses `console_output=False` to prevent stdio protocol pollution
- Added coverage:
  - `tests/test_agent_execution_policy.py` now covers facade hooks + stop-reason mapping
  - `tests/test_acp.py` remains passing on ACP path

### 3.9 P11.6 step-failure trend aggregation landed
- Added observability trend endpoint for `step.failed` telemetry:
  - `GET /api/observability/failures/step-trends`
  - bucketed counters: `total/planner/executor/recoverable/retryable/unique_runs`
  - ranked breakdown: `top_error_types`
  - filters: `run_id_prefix`, `since_utc`
- Added endpoint implementation and aggregation helpers:
  - `gateway/routers/observability.py`
- Added router coverage:
  - `tests/test_gateway_routers.py`
  - includes invalid `since_utc` -> `400` guard path

### 3.10 P11.7 policy-drift detector landed
- Added configured-vs-runtime policy diagnostics in session core:
  - `configured_max_steps`
  - `configured_max_tool_calls_per_step`
  - `policy_drift`
  - `policy_drift_fields`
- Added configured policy persistence for inactive-session diagnostics:
  - metadata key: `configured_execution_policy`
- Added store-level coverage:
  - `tests/test_session_store_persistence.py`

### 3.11 P11.8 policy-drift session surfaces landed
- Extended session inspection APIs with drift diagnostics flags:
  - `/api/sessions`
  - `/api/sessions/{session_id}/history`
- Added gateway router coverage for drift-true and drift-false scenarios:
  - `tests/test_gateway_routers.py`

### 3.12 P11.9 step-failure trend filters landed
- Extended step-failure trend endpoint with targeted filtering:
  - endpoint: `GET /api/observability/failures/step-trends`
  - added params: `phase`, `error_type`
  - `error_type` matching is case-insensitive
- Added router coverage:
  - `tests/test_gateway_routers.py`
  - includes phase-only and error_type-only filter assertions

### 3.13 P11.10 policy-drift chat surfaces landed
- Extended chat response surfaces with drift diagnostics:
  - `POST /api/chat`
  - `GET /api/chat/stream` done payload
- Added fields:
  - `configured_max_steps`
  - `configured_max_tool_calls_per_step`
  - `policy_drift`
  - `policy_drift_fields`
- Added router coverage:
  - `tests/test_gateway_routers.py`
  - includes dry-run defaults and drift=true assertions

### 3.14 P11.11 drift-health counters landed
- Extended observability health diagnostics with drift counters:
  - endpoint: `GET /api/observability/health`
  - fields: `policy_drift_active_sessions`, `policy_drift_sessions`, `policy_drift_ratio`
- Updated health implementation to rely on `session_store.list_records(...)` for accurate active/total and drift counts.
- Added router coverage for drift counter behavior:
  - `tests/test_gateway_routers.py`

### 3.15 P11.12 session drift-filter landed
- Added session-list filtering for policy drift triage:
  - endpoint: `GET /api/sessions`
  - query param: `policy_drift` (`true`/`false`)
- Added router coverage:
  - `tests/test_gateway_routers.py`
  - includes drift=true and drift=false filter assertions

## 4. Planning Docs Updated
- Updated `docs/REFACTOR_TASKS.md`
  - Marked P11 as active.
  - Updated stable baseline to `173 passed, 25 deselected`.
- Updated `docs/DEVELOPMENT_INDEX.md`
  - Status moved to `P10 done / P11 in progress`.
  - Published P11.1/P11.2/P11.3/P11.4/P11.5/P11.6/P11.7/P11.8/P11.9/P11.10/P11.11/P11.12 execution index and next queue.

## 5. Next Step Queue (P11.13 start)
1. Add drift summary fields to run/session listings for faster triage.
2. Add trend response context fields (`matched_failures`, `filtered_out_failures`) for dashboards.
3. Add health diagnostics drilldown field for top drifted session IDs.
