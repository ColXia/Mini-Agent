# P19 Agent-Team Rollout Contract (Prep)

> Status: prep-frozen
> Last updated: 2026-04-07
> Goal: enable team-mode rollout without breaking `single_main` default behavior

## 0. Kickoff Slice Delivered (2026-04-07)

- Runtime diagnostics added to `/api/v1/system/health`:
  - `mode`, `active_sessions`, `max_active_sessions`, `available_session_slots`, `reserved_team_slots`, `workspace_application_required`, `main_workspace_dir`
- Team-mode guardrail hardened:
  - requests without `session_id` now reuse existing workspace session to reduce accidental fan-out
- P19 deterministic matrix delivered:
  - `tests/test_p19_runtime_matrix.py`
  - `scripts/p19_runtime_matrix.py`
  - latest report: `workspace/p19_matrix/p19_runtime_matrix_20260407T050342Z.md` (`overall: PASS`)
- Ops diagnostics view/API extension delivered:
  - `GET /api/v1/ops/diagnostics/runtime`
  - Studio Ops frontend renders runtime counters (mode/capacity/slots/workspace policy)
- Stage-B guardrails diagnostics delivered:
  - queue saturation counter: `team_saturation_rejections`
  - workspace conflict counter: `team_workspace_conflict_rejections`
  - counters surfaced in both `/api/v1/system/health` and `/api/v1/ops/diagnostics/runtime`
- Release promotion checklist policy enforced:
  - `scripts/release_promotion_checklist.py`
  - deterministic gate = mandatory; no-dry-run gate = advisory
- Team-mode operator runbook published:
  - `docs/P19_TEAM_MODE_OPERATOR_RUNBOOK.md`
- Stage-C external docs published:
  - `docs/P19_TEAM_MODE_ROLLOUT_ANNOUNCEMENT.md`
  - `docs/P19_TEAM_MODE_SUPPORT_FAQ.md`
- Ops alert policy published and mapped to Studio diagnostics UI:
  - `docs/P19_TEAM_MODE_ALERT_POLICY.md`
  - `src/apps/agent_studio/src/components/StudioOpsMode.tsx`
  - `src/apps/agent_studio/src/styles.css`
- Stage-C adoption tracking and canary cadence docs delivered:
  - `docs/P19_STAGEC_ADOPTION_TRACKING.md`
  - `docs/P19_TEAM_MODE_CANARY_CADENCE.md`
  - `docs/P19_WEEKLY_RELEASE_READINESS_TEMPLATE.md`
  - weekly KPI script: `scripts/p19_weekly_rollout_review.py`
  - runtime trend + target bands + weekly delta aggregation:
    - `src/mini_agent/dev/p19_rollout_reporting.py`
    - runtime snapshot source: `scripts/studio_ops_smoke.py` + `scripts/release_gate.py`
  - mode split + remediation hints + JSON summary artifact:
    - weekly report sections: `Runtime Mode Split`, `Target Remediation Hints`
    - JSON artifact: `workspace/p19_rollout/p19_weekly_rollout_*.json`
- CI release handoff integration delivered:
  - `.github/workflows/ci.yml` -> `release-handoff` job (workflow_dispatch)
  - optional advisory branch via `run_advisory_no_dry_run` + `OPENWEBUI_ADVISORY_API_KEY`
  - optional strict weekly rollout review branch via `run_weekly_rollout_review_strict`
    - runs `scripts/p19_runtime_matrix.py`
    - runs `scripts/p19_weekly_rollout_review.py --window-days 7 --target-profile stage --strict --strict-targets`
  - deterministic-only fallback when advisory secret is unavailable
  - deterministic artifact guard: `scripts/check_deterministic_gate_artifact.py`
  - artifact upload includes runtime trend snapshots:
    - `workspace/release_gate/studio_ops_runtime_*.json`
- Validation:
  - `pytest -q tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_api_v1.py`
  - `pytest -q tests/test_deterministic_gate_artifact.py tests/test_release_promotion_checklist.py`
  - `python scripts/release_gate.py --start-local-gateway --studio-token studio-smoke-token`
  - `python scripts/release_promotion_checklist.py --studio-token studio-smoke-token --skip-advisory`
  - `python scripts/check_deterministic_gate_artifact.py`
  - `python scripts/p19_weekly_rollout_review.py --window-days 7 --target-profile stage --strict --strict-targets`
  - latest runtime snapshot: `workspace/release_gate/studio_ops_runtime_20260407T070735Z.json`
  - latest weekly rollout report: `workspace/p19_rollout/p19_weekly_rollout_20260407T070808Z.md` (`Overall: READY`, `Target Profile Status: PASS`)
  - latest promotion checklist: `workspace/release_promotion/release_promotion_20260407T055638Z.md` (`Decision: READY`)
  - latest deterministic gate report: `workspace/release_gate/release_gate_deterministic_20260407T055638Z.md` (`overall: PASS`)
  - stable suite snapshot: `413 passed, 32 deselected`

## 1. Non-Negotiables

1. `single_main` remains the production default.
2. `team` mode is opt-in only (explicit env/profile switch).
3. Existing `/api/v1/*` request/response contract stays backward-compatible.
4. P18 single-host process discipline remains unchanged.

## 2. Runtime Contract

### 2.1 Mode Switch

- Runtime policy source remains centralized in `MainAgentRuntimePolicy`.
- `MINI_AGENT_RUNTIME_MODE` accepted values:
  - `single_main` (default)
  - `team` (opt-in)

### 2.2 Session Ownership

- `single_main`:
  - one active runtime/session slot for main workspace.
- `team`:
  - bounded concurrent runtime sessions (`MINI_AGENT_TEAM_MAX_AGENTS`).
  - each session binds to one workspace context.

### 2.3 Isolation Boundaries

- session memory/history is isolated by runtime session id.
- workspace path policy remains enforced per session.
- no implicit cross-session memory/tool state sharing.

## 3. API and UX Contract

1. Existing chat/session endpoints keep current schema.
2. Additional team diagnostics fields must be additive only.
3. Studio frontend must render team metadata as optional fields.
4. No legacy route reintroduction.

## 4. Rollout Stages

1. Stage A (internal):
   - team mode behind env toggle only.
   - no frontend default changes.
2. Stage B (operator preview):
   - expose runtime mode in ops diagnostics.
   - add guardrails for queue saturation and workspace conflicts.
3. Stage C (general):
   - documented enablement flow.
   - stable regression + smoke profile for both modes.

## 5. Acceptance Criteria for P19 Implementation

1. `single_main` regression baseline remains PASS.
2. `team` mode can run bounded parallel sessions with deterministic limits.
3. session/workspace isolation tests pass.
4. Studio contract tests pass with/without team metadata.
5. docs and runbooks include rollback path to `single_main`.

## 6. Risks and Mitigations

- Risk: hidden coupling between session state and shared tools.
  - Mitigation: explicit runtime/session-scoped state holders + isolation tests.
- Risk: increased tail latency under parallel agent runs.
  - Mitigation: bounded concurrency and queue backpressure metrics.
- Risk: frontend assumptions about single active session.
  - Mitigation: optional metadata fields + contract smoke coverage.
