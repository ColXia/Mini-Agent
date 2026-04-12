# P19 Team-Mode Support FAQ

> Status: active  
> Last updated: 2026-04-07  
> Scope: external support responses for team-mode rollout

## 1. Is team mode enabled by default?

No. Default remains `single_main`. Team mode is opt-in via `MINI_AGENT_RUNTIME_MODE=team`.

## 2. How do we switch from single_main to team mode?

Set:

1. `MINI_AGENT_RUNTIME_MODE=team`
2. `MINI_AGENT_MAIN_WORKSPACE=<absolute path>`
3. `MINI_AGENT_TEAM_MAX_AGENTS=<N>`

Then restart gateway. Use the runbook:

- [P19_TEAM_MODE_OPERATOR_RUNBOOK.md](./P19_TEAM_MODE_OPERATOR_RUNBOOK.md)

## 3. How do we roll back quickly if issues appear?

1. Stop gateway.
2. Set `MINI_AGENT_RUNTIME_MODE=single_main`.
3. Restart gateway.
4. Re-run deterministic gate and confirm `Overall: PASS`.

## 4. Which checks are mandatory before promotion?

Mandatory:

1. Deterministic release gate pass.
2. Deterministic artifact guard pass.
3. Promotion checklist decision is `READY`.

Advisory only:

1. no-dry-run OpenWebUI external path checks.

## 5. Why can promotion be READY when no-dry-run is skipped or warning?

Because policy defines no-dry-run as advisory. It is tracked for signal quality, but it does not block release if deterministic mandatory checks pass.

## 6. What does `team_saturation_rejections` mean?

The runtime rejected requests because active team sessions reached `max_active_sessions`.

Action:

1. Verify workload burst pattern.
2. Tune `MINI_AGENT_TEAM_MAX_AGENTS` conservatively.
3. Re-check latency and stability under load.

## 7. What does `team_workspace_conflict_rejections` mean?

A request attempted to reuse a `session_id` on a different workspace and was rejected.

Action:

1. Fix caller-side session/workspace binding.
2. Check retry logic to avoid cross-workspace session reuse.

## 8. Where can I inspect current runtime diagnostics?

1. `GET /api/v1/system/health`
2. `GET /api/v1/ops/diagnostics/runtime`

## 9. What evidence files should support attach to incidents?

1. `workspace/release_gate/release_gate_deterministic_*.md`
2. `workspace/release_promotion/release_promotion_*.md`
3. `workspace/p19_matrix/p19_runtime_matrix_*.md`

## 10. What if deterministic artifact validation fails in CI?

The release handoff job is expected to fail. Operators should:

1. Re-run promotion checklist.
2. Ensure deterministic report is generated.
3. Confirm report has `Overall: PASS`.

