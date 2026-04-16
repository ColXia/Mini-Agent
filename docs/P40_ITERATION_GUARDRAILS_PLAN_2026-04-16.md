# P40 Iteration Guardrails Plan

Date: 2026-04-16
Scope: establish an executable anti-chaos baseline after `P39` so continued development stays sliceable, reviewable, and physically aligned.

## Why This Slice Exists

`P39.1` and `P39.2` are now landed as real commits:

- `771fc6f` `p39: land runtime protocol substrate`
- `8e9a37d` `p39: close kernel consumer boundary`

The repo is technically usable for controlled iteration, but it is still carrying a very dirty residual worktree across `runtime / tui / memory / tests / docs`.
That means the main risk is no longer “missing architecture”.
The main risk is falling back into mixed, phase-fake commits and losing track of which residual bucket should land next.

## P40 Objective

Create one small but maintained guardrail layer that:

- syncs planning-memory to the real post-`P39` state
- classifies the remaining dirty worktree into honest slices
- gives future turns one repeatable command instead of ad hoc path-counting
- locks a recommended landing order so later work does not drift back into a catch-all backlog

## Guardrails

- Do not reopen `P39`; treat it as completed.
- Do not bundle `runtime`, `tui`, `memory`, and compatibility deletions into one follow-up commit.
- Prefer one coherent slice at a time, even if the residual tree remains large after this pass.
- Keep the classification tool read-only; it should help decisions, not mutate the repo.

## Current Residual Shape

Use the maintained report command:

```powershell
python scripts/worktree_slice_report.py
```

This slice should keep the report current enough to answer:

1. what buckets are still dirty
2. which bucket is the safest next landing target
3. whether new work has started mixing previously separated areas again

Current measured snapshot on 2026-04-16:

- total dirty paths: `250`
- status counts:
  - modified: `91`
  - deleted: `49`
  - untracked: `110`
- largest classified buckets:
  - `runtime-session-contract`: `75`
  - `agent-core-and-cli-surface`: `62`
  - `surface-transport-orchestration`: `42`
  - `docs-planning-governance`: `26`
  - `memory-governance`: `17`
- current report recommendation:
  - `docs-planning-governance`
  - because planning/doc sync is the safest first anti-chaos slice
  - after that, the next code-bearing target should be `memory-governance`

## Recommended Next Landing Order

1. `docs-planning-governance`
   - sync `task_plan.md`, `progress.md`, `findings.md`, and current execution docs to post-`P39` truth
2. `memory-governance`
   - land the canonical `mini_agent.memory` ownership residue before more outer-surface work piles on top
3. `runtime-session-contract`
   - continue only after the memory ownership line is explicit
4. `surface-transport-orchestration`
   - keep the TUI/transport residue as its own surface-oriented line
5. `agent-core-and-cli-surface`
   - only after the outer runtime/surface buckets stop shifting underneath it

## Acceptance

`P40.1` should be considered complete when:

- a repeatable dirty-worktree slice report exists in the repo
- planning-memory names `P39` as completed rather than active
- the next recommended landing order is explicit in repo-visible docs
- temporary status-noise files do not keep reappearing in the active worktree story
