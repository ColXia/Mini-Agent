# CI Scripts

> Last updated: 2026-04-12

This folder contains release-gate, checklist, and CI-oriented validation scripts.

## Included here

- `release_gate.py`
- `release_promotion_checklist.py`
- `check_deterministic_gate_artifact.py`
- `open_webui_verify.py`
- `open_webui_smoke.py`
- `studio_ops_smoke.py`
- `p19_runtime_matrix.py`
- `p19_weekly_rollout_review.py`

## Placement rule

- If a script mainly exists for CI, release handoff, promotion checklists, or historical rollout reporting, it belongs here.
- If a script is part of daily operator/developer local workflows, keep it in `scripts/`.
- If a script is obsolete or misleading, archive it under `scripts/archive/`.
