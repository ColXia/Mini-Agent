# P19 Team-Mode Canary Cadence

> Status: active
> Last updated: 2026-04-07
> Scope: recurring single_main vs team checkpoint routine

## 1. Cadence

1. Daily canary checkpoint (workday cadence)
   - run runtime matrix once
   - run deterministic gate once
2. Weekly promotion checkpoint
   - run weekly rollout review dashboard
   - evaluate target profile bands (`dev/stage/prod`)
   - review advisory signals and rollback log

## 2. Daily Canary Commands

```powershell
python scripts/p19_runtime_matrix.py
python scripts/release_gate.py --start-local-gateway --studio-token studio-smoke-token
python scripts/check_deterministic_gate_artifact.py
```

Expected condition:

- latest matrix report `Overall: PASS`
- latest deterministic gate report `Overall: PASS`

## 3. Weekly Review Commands

```powershell
python scripts/release_promotion_checklist.py --studio-token studio-smoke-token --skip-advisory
python scripts/p19_weekly_rollout_review.py --window-days 7 --target-profile stage
```

When advisory validation is needed:

```powershell
python scripts/release_promotion_checklist.py --studio-token studio-smoke-token --advisory-api-key <key>
```

When using strict weekly quality gate:

```powershell
python scripts/p19_weekly_rollout_review.py --window-days 7 --target-profile stage --strict --strict-targets
```

Weekly outputs:

- `workspace/p19_rollout/p19_weekly_rollout_<utc>.md`
- `workspace/p19_rollout/p19_weekly_rollout_<utc>.json`

## 4. Escalation / Freeze Rules

Freeze rollout expansion when any of the following occurs:

- latest deterministic gate is not `PASS`
- latest matrix is not `PASS`
- weekly checklist overall is `ATTENTION`
- Ops alert policy reaches sustained `critical` signal

Reference policies:

- `docs/P19_TEAM_MODE_ALERT_POLICY.md`
- `docs/P19_STAGEC_ADOPTION_TRACKING.md`
