# Cross-Device Handoff (2026-04-07)

> Status: active
> Goal: continue P19 development on another machine with minimal context loss

## 1. Current Progress Snapshot

- P19 Stage-C rollout engineering and docs are in active state.
- Weekly rollout reporting now includes:
  - runtime trend aggregation
  - environment target bands (`dev/stage/prod`)
  - previous-window delta
  - runtime mode split
  - remediation hints
  - JSON summary artifact
- CI `release-handoff` supports optional strict weekly review path.

## 2. Latest Evidence (for continuity)

- deterministic gate report:
  - `workspace/release_gate/release_gate_deterministic_20260407T055638Z.md`
- release gate smoke-only report with runtime snapshot:
  - `workspace/release_gate/release_gate_20260407T070735Z.md`
- runtime snapshot:
  - `workspace/release_gate/studio_ops_runtime_20260407T070735Z.json`
- weekly rollout (stage strict):
  - `workspace/p19_rollout/p19_weekly_rollout_20260407T072940Z.md`
  - `workspace/p19_rollout/p19_weekly_rollout_20260407T072940Z.json`
- weekly rollout (prod target check):
  - `workspace/p19_rollout/p19_weekly_rollout_20260407T073001Z.md`
  - `workspace/p19_rollout/p19_weekly_rollout_20260407T073001Z.json`

## 3. Bootstrap on New Device

```powershell
git clone <your-repo-url>
cd Mini-Agent
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Frontend build dependencies (if Studio frontend work continues):

```powershell
npm --prefix src/apps/agent_studio install
```

Create local secrets files from examples on the new device:

```powershell
Copy-Item src/apps/agent_studio_gateway/.env.example src/apps/agent_studio_gateway/.env
Copy-Item src/apps/qqbot_channel/.env.example src/apps/qqbot_channel/.env
```

Then fill real keys in local `.env` files (never commit them).

## 4. Quick Validation on New Device

```powershell
$env:PYTHONPATH='src'
pytest -q tests/test_p19_rollout_reporting.py tests/test_release_promotion_checklist.py tests/test_deterministic_gate_artifact.py
python scripts/p19_weekly_rollout_review.py --window-days 7 --target-profile stage --strict --strict-targets
```

## 5. Next Recommended Focus

1. Add KPI historical sparkline data points in weekly JSON payload.
2. Add `--target-profile auto` (derive from CI environment).
3. Add retention helper for `workspace/p19_rollout/p19_weekly_rollout_*.{md,json}`.

## 6. Upload Scope Reference

Before switching devices, follow:

- `docs/GITHUB_UPLOAD_SCOPE_2026-04-07.md`

Security reminder:

- if any real key was ever staged/committed, rotate it before or immediately after GitHub sync.
