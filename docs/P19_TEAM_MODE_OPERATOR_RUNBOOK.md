# P19 Team-Mode Operator Runbook

> Status: active  
> Last updated: 2026-04-07  
> Scope: `single_main` <-> `team` runtime operations, smoke checks, rollback

## 1. Purpose

This runbook defines a safe operator workflow for:

1. Enabling `team` mode intentionally.
2. Validating runtime capacity/guardrails.
3. Rolling back to `single_main` quickly when needed.

Production default remains `single_main`.

## 2. Runtime Controls

Environment variables used by runtime policy:

- `MINI_AGENT_RUNTIME_MODE`: `single_main` (default) or `team`
- `MINI_AGENT_MAIN_WORKSPACE`: absolute main workspace path
- `MINI_AGENT_TEAM_MAX_AGENTS`: max concurrent sessions in `team` mode

## 3. Enable Team Mode (PowerShell)

From repo root:

```powershell
$env:MINI_AGENT_RUNTIME_MODE = "team"
$env:MINI_AGENT_MAIN_WORKSPACE = "C:/Users/Conli/Mini-Agent"
$env:MINI_AGENT_TEAM_MAX_AGENTS = "4"
$env:MINI_AGENT_STUDIO_API_KEYS = "studio-ops-token"
python -m uvicorn apps.agent_studio_gateway.main:app --host 127.0.0.1 --port 8008
```

Expected health diagnostics (`/api/v1/system/health`):

- `runtime.mode = "team"`
- `runtime.max_active_sessions = MINI_AGENT_TEAM_MAX_AGENTS`
- `runtime.team_saturation_rejections >= 0`
- `runtime.team_workspace_conflict_rejections >= 0`

## 4. Rollback to Single-Main (PowerShell)

Stop gateway, then restart with:

```powershell
$env:MINI_AGENT_RUNTIME_MODE = "single_main"
$env:MINI_AGENT_MAIN_WORKSPACE = "C:/Users/Conli/Mini-Agent"
$env:MINI_AGENT_TEAM_MAX_AGENTS = "4"
$env:MINI_AGENT_STUDIO_API_KEYS = "studio-ops-token"
python -m uvicorn apps.agent_studio_gateway.main:app --host 127.0.0.1 --port 8008
```

Expected health diagnostics:

- `runtime.mode = "single_main"`
- `runtime.max_active_sessions = 1`

## 5. Operator Validation Recipe

Run in order:

1. Runtime matrix:
```powershell
python scripts/p19_runtime_matrix.py
```
2. Deterministic release gate (mandatory):
```powershell
python scripts/release_gate.py --start-local-gateway --studio-token studio-smoke-token
```
3. Promotion checklist decision:
```powershell
python scripts/release_promotion_checklist.py --studio-token studio-smoke-token --skip-advisory
python scripts/check_deterministic_gate_artifact.py
```

Promotion may proceed only when:

- deterministic gate artifact exists and is `Overall: PASS`
- promotion decision is `READY`

## 6. Diagnostics Interpretation

Counters exposed in `/api/v1/system/health` and `/api/v1/ops/diagnostics/runtime`:

- `team_saturation_rejections`:
  - increments when `team` mode reaches `max_active_sessions` and rejects new session creation.
- `team_workspace_conflict_rejections`:
  - increments when the same `session_id` is reused against another workspace and request is rejected.

Suggested response:

1. If saturation grows quickly, increase `MINI_AGENT_TEAM_MAX_AGENTS` conservatively or reduce concurrent intake.
2. If workspace conflicts grow, check client session/workspace binding logic and retry behavior.
3. If either counter spikes after release, rollback to `single_main` and re-run deterministic gate before re-enable.

## 7. Evidence Paths

- Runtime matrix reports: `workspace/p19_matrix/p19_runtime_matrix_*.md`
- Deterministic gate reports: `workspace/release_gate/release_gate_deterministic_*.md`
- Promotion checklist reports: `workspace/release_promotion/release_promotion_*.md`

