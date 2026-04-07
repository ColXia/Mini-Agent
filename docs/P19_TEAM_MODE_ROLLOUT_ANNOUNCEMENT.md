# P19 Team-Mode Rollout Announcement

> Status: active  
> Publish date: 2026-04-07  
> Audience: operators, workspace owners, support, integration maintainers

## Summary

Team-mode rollout is now available as an opt-in runtime profile for Mini-Agent deployments that need bounded concurrent workspace sessions.

This release keeps `single_main` as the default production mode and introduces a documented path to enable, validate, and roll back team mode safely.

## What Is New

1. Team-mode runtime policy (`MINI_AGENT_RUNTIME_MODE=team`) with bounded concurrency (`MINI_AGENT_TEAM_MAX_AGENTS`).
2. Runtime diagnostics exposed in:
   - `/api/v1/system/health`
   - `/api/v1/ops/diagnostics/runtime`
3. New Stage-B guardrail counters:
   - `team_saturation_rejections`
   - `team_workspace_conflict_rejections`
4. Promotion policy enforcement:
   - deterministic gate is mandatory
   - no-dry-run gate is advisory

## What Is Not Changing

1. `single_main` remains the default runtime mode.
2. Existing `/api/v1/*` schema remains additive/backward compatible.
3. Rollback to `single_main` is always supported.

## Enablement

Use the operator runbook for exact commands and checks:

- [P19_TEAM_MODE_OPERATOR_RUNBOOK.md](./P19_TEAM_MODE_OPERATOR_RUNBOOK.md)

Minimum release readiness sequence:

1. `python scripts/p19_runtime_matrix.py`
2. `python scripts/release_gate.py --start-local-gateway --studio-token <token>`
3. `python scripts/release_promotion_checklist.py --studio-token <token> --skip-advisory`
4. `python scripts/check_deterministic_gate_artifact.py`

## Support Scope

Support includes:

1. Runtime mode switch guidance (`single_main` <-> `team`).
2. Diagnostics interpretation for saturation/conflict counters.
3. Deterministic gate/promotion readiness troubleshooting.

Out of scope for this announcement:

1. Automatic advisory no-dry-run CI execution with external model credentials.
2. Dashboard alerting policy automation for guardrail counters (planned follow-up).

## References

1. [P19_AGENT_TEAM_ROLLOUT_CONTRACT.md](./P19_AGENT_TEAM_ROLLOUT_CONTRACT.md)
2. [P19_TEAM_MODE_OPERATOR_RUNBOOK.md](./P19_TEAM_MODE_OPERATOR_RUNBOOK.md)
3. [P19_TEAM_MODE_SUPPORT_FAQ.md](./P19_TEAM_MODE_SUPPORT_FAQ.md)

