# P19 Team-Mode Ops Alert Policy

> Status: active
> Last updated: 2026-04-07
> Scope: Studio Ops runtime diagnostics (`/api/v1/ops/diagnostics/runtime`)

## 1. Purpose

Define deterministic operator thresholds for team-mode rollout so saturation and workspace-conflict risks can be identified early and handled consistently.

## 2. Alert Signals

Runtime diagnostics fields used for policy evaluation:

- `active_sessions`
- `max_active_sessions`
- `team_saturation_rejections`
- `team_workspace_conflict_rejections`

Derived metric:

- capacity pressure ratio = `active_sessions / max_active_sessions`

## 3. Thresholds

### 3.1 Capacity pressure (`active_sessions / max_active_sessions`)

- `>= 0.95` -> `critical`
- `>= 0.80 and < 0.95` -> `watch`
- `< 0.80` -> `healthy`

### 3.2 Saturation rejections (`team_saturation_rejections`)

- `>= 5` -> `critical`
- `>= 1 and < 5` -> `warning`
- `0` -> `healthy`

### 3.3 Workspace conflict rejections (`team_workspace_conflict_rejections`)

- `>= 3` -> `critical`
- `>= 1 and < 3` -> `warning`
- `0` -> `healthy`

### 3.4 Overall level

Overall alert level is the highest severity across the three signals:

`healthy < watch < warning < critical`

## 4. Operator Actions

### 4.1 Critical

- Pause team-mode rollout expansion.
- Verify caller traffic shape and workspace routing.
- Increase bounded concurrency only after confirming workspace isolation and session reuse behavior.
- Run deterministic gate before resuming rollout:
  - `python scripts/release_gate.py --start-local-gateway --studio-token studio-smoke-token`

### 4.2 Warning

- Investigate source of rejection spikes (burst traffic, missing `session_id`, workspace contention).
- Keep rollout scope unchanged until counters flatten.
- Re-run runtime matrix when changing capacity-related configs:
  - `python scripts/p19_runtime_matrix.py`

### 4.3 Watch

- Continue rollout with closer observation.
- Monitor for trend escalation in subsequent smoke/gate windows.

### 4.4 Healthy

- No additional action required beyond normal gate cadence.

## 5. Studio Ops UX Mapping

Studio Ops frontend maps thresholds into an inline alert card in runtime diagnostics:

- file: `src/apps/agent_studio/src/components/StudioOpsMode.tsx`
- styles: `src/apps/agent_studio/src/styles.css`

The card shows:

- overall policy level
- signal-level severity chips
- per-signal value and operator hint

