# P19 Stage-C Adoption Tracking

> Status: active
> Last updated: 2026-04-07
> Scope: team-mode rollout KPI dashboard and weekly review workflow

## 1. Goal

Use deterministic evidence to decide whether team-mode rollout can safely expand.

## 2. KPI Dashboard (Weekly Window)

Data sources:

- `workspace/p19_matrix/p19_runtime_matrix_*.md`
- `workspace/release_gate/release_gate_deterministic_*.md`
- `workspace/release_promotion/release_promotion_*.md`
- `workspace/release_gate/studio_ops_runtime_*.json`

KPI definitions:

1. Matrix pass rate
   - formula: `matrix_pass_count / matrix_total`
   - target: `100%`
2. Deterministic gate pass rate
   - formula: `deterministic_pass_count / deterministic_total`
   - target: `100%`
3. Promotion READY rate
   - formula: `promotion_ready_count / promotion_total`
   - target: `100%`
4. Advisory WARN/FAIL count
   - formula: advisory statuses in `{WARN, FAIL}`
   - target: `0` (tracked, non-blocking by policy)
5. Advisory SKIP count
   - formula: advisory status `SKIP`
   - target: bounded by environment profile band
6. Runtime saturation counter (last)
   - source: latest `team_saturation_rejections` from runtime snapshot
   - target: bounded by environment profile band
7. Runtime workspace-conflict counter (last)
   - source: latest `team_workspace_conflict_rejections` from runtime snapshot
   - target: bounded by environment profile band

Environment target profiles:

- `dev`
  - matrix/deterministic/promotion pass rate: `>=95%`
  - advisory WARN/FAIL `<=2`, advisory SKIP `<=14`
  - saturation/conflict last `<=5 / <=3`
- `stage`
  - matrix/deterministic/promotion pass rate: `100%`
  - advisory WARN/FAIL `<=1`, advisory SKIP `<=7`
  - saturation/conflict last `<=2 / <=1`
- `prod`
  - matrix/deterministic/promotion pass rate: `100%`
  - advisory WARN/FAIL `=0`, advisory SKIP `<=2`
  - saturation/conflict last `=0 / =0`

## 3. Weekly Review Checklist

Required pass conditions:

- At least one matrix run in review window.
- At least one deterministic gate run in review window.
- Latest matrix report is `PASS`.
- Latest deterministic gate report is `PASS`.
- Latest promotion decision is `READY`.

## 4. Standard Command

Generate weekly tracking report:

```powershell
python scripts/p19_weekly_rollout_review.py --window-days 7
```

Optional strict mode (CI/manual guard use):

```powershell
python scripts/p19_weekly_rollout_review.py --window-days 7 --target-profile stage --strict --strict-targets
```

Default output:

- `workspace/p19_rollout/p19_weekly_rollout_<utc>.md`
- `workspace/p19_rollout/p19_weekly_rollout_<utc>.json`

Report sections include:

- runtime counter trends (`saturation/conflict`)
- runtime mode split (`single_main` / `team`)
- target remediation hints when profile status is `ATTENTION`
- previous-window KPI delta section

CI integration:

- `.github/workflows/ci.yml` `release-handoff` workflow_dispatch now supports optional strict review input:
  - `run_weekly_rollout_review_strict=true`
  - strict path runs matrix + `p19_weekly_rollout_review.py --target-profile stage --strict --strict-targets`

## 5. Decision Rule

- `READY`: all required checklist items are satisfied.
- `ATTENTION`: any required checklist item fails or evidence is missing.

## 6. Weekly Diff

Weekly report includes a `Weekly Delta vs Previous Window` section for:

- matrix / deterministic / promotion pass-rate deltas
- advisory WARN/FAIL and SKIP deltas
- runtime saturation/conflict last-value deltas
