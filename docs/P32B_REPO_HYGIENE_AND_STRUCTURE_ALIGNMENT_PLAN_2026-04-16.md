# P32b Repo Hygiene And Structure Alignment Plan

Date: 2026-04-16
Status: active
Scope: repo hygiene / active-doc sync / commit slicing / physical-logical structure alignment

Execution note (2026-04-16): the original `P32` realignment line materially corrected the physical tree, and later `P33b / P34 / P36 / P37` slices continued landing on top of that structure. The current repo problem is no longer "where should new code live?" The current problem is that the worktree and active docs still need a hygiene closeout so the maintained repository story matches the already-landed physical structure.

## Goal

Close the second-pass `P32` hygiene loop so that:

- active guidance documents teach the current structure rather than an older execution phase
- current maintained docs stop pointing at deleted module/test names except where a file is explicitly historical
- the dirty worktree has an explicit commit-slicing plan instead of one giant mixed backlog
- future work can start from one truthful repo map instead of reconstructing it from scattered phase logs

This is not another feature sprint.
It is a repo-hygiene and structure-story closeout above the already-landed physical refactor.

## Why This Slice Exists

The codebase already moved or removed the biggest structural misleaders:

- `code_agent/` was collapsed into `agent_core/`
- `agent.py` and `turn_context.py` moved under `agent_core/`
- transport clients moved out of TUI/application into `transport/`
- browser `WebUI / OpenWebUI` and legacy channel trees were removed from the active repo
- `P33b / P34 / P36 / P37` landed follow-up work on the new structure

But the current repo still shows hygiene drift:

- top-level active indexes still point to `P30` as the execution anchor
- current phase status still presents `P33` as the active line
- current guidance docs do not yet reflect that `P33b / P34 / P36 / P37` are completed
- some maintained reference docs still mention renamed tests such as `tests/test_main_agent_gateway_use_cases.py`
- the dirty worktree mixes structure, docs, and later feature slices without a current commit plan

## Locked Decisions

### 1. Do not mass-rewrite historical execution logs

Historical task docs may keep old paths and names when they are part of traceable execution history.

This slice should correct:

- active indexes
- active guides
- current repo maps
- currently maintained references

It should not erase historical development evidence just to make old logs look current.

### 2. Active guidance must only teach maintained ownership

Any document that presents current architecture, current execution focus, or current repository shape must point to maintained:

- paths
- package ownership
- plan anchors
- test names

### 3. Commit slicing must follow ownership, not convenience

The current worktree should be closed through narrow, non-overlapping slices such as:

- active docs/index sync
- physical-structure deletion/move closure
- later feature lines (`P33b / P34 / P36 / P37`) if they are committed separately

Do not bundle "repo hygiene" and "all remaining product work" into one catch-all commit.

## Audit Baseline (2026-04-16)

Current code/test/script search shows:

- no active source/test/script references remain for:
  - `main_agent_gateway_use_cases`
  - `session_remote_service`
  - `tui.gateway_client`
  - `mini_agent.code_agent`
- remaining stale references are concentrated in doc/index surfaces and historical logs
- the physical repo tree is now broadly aligned with the framework skeleton:
  - `src/apps/desktop_ui/` exists
  - `src/apps/agent_studio_gateway/` remains the maintained gateway host
  - `src/apps/qqbot_channel/` remains the active remote adapter app

This means the highest-value second-pass cleanup is documentation, index, and commit hygiene.

## Planned Slices

### P32b.1 Active Doc And Index Correction

Goals:

- create one explicit `P32b` closeout doc
- repoint current execution anchors to `P32b`
- sync `README`, development guides, and doc indexes to current post-`P37` reality
- fix maintained references to renamed tests/modules where those references are meant to guide present work

### P32b.2 Active Vs Historical Boundary Cleanup

Goals:

- make it obvious which docs are active guidance and which are historical trace
- keep old path names only inside explicitly historical or phase-log contexts
- avoid presenting old phase logs as the current implementation source of truth

### P32b.3 Commit Slicing And Hygiene Closeout

Current preferred commit slices:

1. `docs/index hygiene`
   - `README*`
   - `DEVELOPMENT_INDEX`
   - `DOCS_INDEX`
   - `DEVELOPMENT_GUIDE*`
   - `REFACTOR_TASKS`
   - `MINIAGENT_DEV_HABIT_LEDGER`
   - `P32b` plan + planning files
2. `physical structure closure`
   - legacy tree deletions
   - canonical package/export ownership sync
   - test/script path cleanup directly tied to the structural move/delete story
3. `post-structure feature lines`
   - `P33b`
   - `P34`
   - `P36`
   - `P37`
   if they need separate feature-oriented commits

## Acceptance

This slice is successful when:

- active current-guidance docs no longer claim `P30` or `P33` is the current execution anchor
- current repo maps and guides match the maintained physical tree
- stale maintained references to deleted module/test names are corrected or clearly marked historical
- the repo has an explicit commit-slicing plan for the dirty worktree
- focused doc/link validation remains green after the sync
