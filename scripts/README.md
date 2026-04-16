# Scripts

> Last updated: 2026-04-12
> Purpose: keep active helper scripts discoverable and push stale launchers out of the main surface.

## Active helpers

- `setup-config.ps1`
  - Windows bootstrap for `.env.local`-based provider configuration.
- `setup-config.sh`
  - POSIX bootstrap for `.env.local`-based provider configuration.
- `start_runtime_stack.ps1`
  - Thin convenience wrapper around `uv run mini-agent stack up`.
- `test_stable.py`
  - Curated stable pytest entry used for quick regression checks.

## Active validation and walkthrough scripts

- Smoke, walkthrough, readiness, and acceptance helpers remain in `scripts/` when they are still used by CI, release checks, or manual runtime verification.
- Examples include `ollama_live_smoke.py`, `shared_session_gateway_walkthrough.py`, `terminal_readiness_gate.py`, `tui_interaction_walkthrough.py`, and `workspace_memory_acceptance.py`.

## CI / release scripts

- CI-oriented and release-oriented scripts now live under [`ci/`](./ci/).
- Examples include `ci/release_gate.py`, `ci/release_promotion_checklist.py`, `ci/studio_ops_smoke.py`, and `ci/p19_runtime_matrix.py`.

## Archived launchers

- Legacy or broken startup helpers are moved to [`archive/`](./archive/).
- If a script points to outdated paths, hard-coded personal directories, or a paused surface, it should not stay in the active `scripts/` root.

## Maintenance rule

- Prefer current product entrypoints such as `uv run mini`, `uv run mini-agent ...`, and `uv run mini-agent stack ...`.
- Archive historical helpers instead of leaving misleading one-click scripts in the active path.
