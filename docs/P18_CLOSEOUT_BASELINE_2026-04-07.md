# P18 Closeout Baseline (2026-04-07)

> Status: active baseline
> Last updated: 2026-04-07
> Scope: single-host v1 release freeze evidence

## 1. Purpose

Freeze a reproducible regression baseline for the post-P18 architecture:

- single backend host (`apps/agent_studio_gateway/main.py`)
- API contract on `/api/v1/*`
- Studio Ops + OpenWebUI adapter compatibility

## 2. Baseline Command (Deterministic Gate)

Run from repo root:

```powershell
python scripts/release_gate.py --start-local-gateway --studio-token studio-smoke-token
```

## 3. Baseline Result

- Result: PASS
- Report:
  - `workspace/release_gate/release_gate_deterministic_20260407T050810Z.md`
- Verification highlights:
  - OpenWebUI verify (unit + positioning + frontend contract client) passed
  - Studio Ops token smoke passed
  - Stable suite passed: `410 passed, 32 deselected`

## 4. Optional Extended Gate (No-Dry-Run)

Extended command (includes real OpenWebUI no-dry-run smoke):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_release_gate_openwebui.ps1
```

Recent evidence:

- PASS sample:
  - `workspace/release_gate/release_gate_20260407T023035Z.md`
- Flaky samples (external model/provider instability):
  - `workspace/release_gate/release_gate_20260407T025127Z.md`
  - `workspace/release_gate/release_gate_20260407T030059Z.md`

Interpretation:

- no-dry-run failures are currently treated as external-path volatility, not local contract regression, when deterministic gate remains PASS.
