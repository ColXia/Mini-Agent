# MiniAgent Dev Habit Ledger

> **状态**: ✅ 活跃
> **最后更新**: 2026-04-06
> **维护者**: Codex execution discipline
> **文档索引**: [DOCS_INDEX.md](./DOCS_INDEX.md)

Updated: 2026-04-07
Scope: Hard-refactor execution constraints, mistake prevention, and operational guardrails.

## 1. Core Habits (Must Follow)

| ID | Habit | Constraint | Verification |
| --- | --- | --- | --- |
| H-01 | Single source of truth for architecture | All changes must map to active phase doc (`P18_HARD_REFACTOR_EXECUTION_PLAN.md`) | PR checklist + task link |
| H-02 | No compatibility shell | Any fallback/legacy adapter is blocked unless explicitly approved | Code review gate |
| H-03 | Contract-first API change | Router changes require DTO/contract update first | Contract test |
| H-04 | One frontend + one backend in dev | Repeated startup must fail fast with PID/port message | Startup script guard |
| H-05 | One main-agent runtime | No duplicated runtime creation paths | Runtime manager assert |
| H-06 | Channel ingress normalization | QQ/WeChat must enter one canonical use-case | Integration test |
| H-07 | Small, atomic slices | Each change must include scope boundary and rollback note | Dev log entry |
| H-08 | Immediate post-change validation | Syntax/build/smoke checks are mandatory before handoff | Local check report |
| H-09 | Language-specific validation commands | Python/TypeScript validation commands must not be mixed in one invocation | Validation checklist |

## 2. Mistake and Error Log

| Date | ID | Stage | Mistake / Error | Impact | Root Cause | Preventive Rule | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-04-06 | E-001 | Runtime startup | Studio path bypassed CLI single-instance lock | Duplicate process risk, operational confusion | Lock only implemented in one entry path | Add instance lock in Studio gateway startup and startup script pre-check | Fixed |
| 2026-04-06 | E-002 | Frontend serving | JS served with `text/plain` caused blank page | WebUI rendered blank | Missing/incorrect MIME mapping on static hosting path | Force `.js/.mjs` MIME to `application/javascript` and smoke-check headers | Fixed |
| 2026-04-06 | E-003 | Dev workflow | Split-mode startup used during runtime validation without strict process control | Difficult process state tracking | No unified startup discipline for current goal | Default to single-host flow and enforce duplicate-start failure | Fixed |
| 2026-04-06 | E-004 | UI quality | Mixed/garbled multilingual text in UI | Poor UX and debugging noise | Encoding/history residue + inconsistent copy source | Centralize UI copy review and run text sanity pass before build | In progress |
| 2026-04-06 | E-005 | Test execution | Parallel test runs against the same app conflicted on instance lock | False-negative test failures | Ran lock-sensitive suites concurrently | Run Studio Gateway tests serially or isolate lock key/port per worker | Fixed |
| 2026-04-06 | E-006 | Code hygiene | Garbled/unterminated string literal broke startup compile | Runtime blocked until manual fix | Mixed-encoding text edit without immediate syntax check | Always run `py_compile` immediately after editing backend Python files | Fixed |
| 2026-04-06 | E-007 | Validation workflow | Used `py_compile` against a `.ts` file, causing false-failure noise | Slowed validation loop and obscured real status | Cross-language command mixing during quick parallel checks | Keep Python compile checks Python-only; use `npm run build`/`tsc` for TS | Fixed |
| 2026-04-06 | E-008 | Dev manager logs | `dev logs` crashed on Windows console encoding (`UnicodeEncodeError`) | Broke log inspection command during active dev | Direct print of UTF-8 log lines to GBK terminal | Add safe-print fallback (`errors=replace`) for log output path | Fixed |
| 2026-04-06 | E-009 | Test isolation | Dev-manager tests touched user-level state paths and leaked stale log lines | Confusing status/log output in later manual checks | Tests used default `~/.mini-agent/studio-dev` root | Force test-only state root under tmp path for all manager tests | Fixed |
| 2026-04-06 | E-010 | Runtime architecture | Legacy gateway/orchestrator startup entries remained callable after v1 host migration | Multiple backend host startup paths could reappear | Migration completed features before deleting old runtime entrypoints | Hard-remove legacy entry modules and block standalone subprogram host startup | Fixed |
| 2026-04-06 | E-011 | CLI UX | Duplicate `mini-agent dev up` surfaced full Python traceback | Noisy output and harder operator control | `run_dev_command` propagated manager `RuntimeError` directly | Catch runtime errors in dev command path and print concise user-facing error with exit code 1 | Fixed |
| 2026-04-06 | E-012 | Test workflow | Gateway v1 TestClient suites failed while local dev backend held instance lock | Lock-sensitive tests produced false negatives | Ran backend-lock tests while real host process occupied same lock key/port | Enforce pre-test `dev down` for lock-sensitive suites or isolate lock host/port in test env | Fixed |
| 2026-04-07 | E-013 | Core runtime design | Started to implement parallel runtime capabilities before full module inventory, risking duplicate bootstraps | Higher maintenance burden and inconsistent behavior across surfaces | Capability assumptions were made from partial scan results | Run code-level inventory first, then enforce single shared bootstrap entrypoint for CLI/TUI/Gateway | Fixed |

## 3. Hard-Refactor Guardrails

1. Any new module must be mapped to P18 phase and task ID.
2. Any change crossing router/service/runtime boundaries must include interface contract updates.
3. When deleting legacy code, delete tests or rewrite tests in the same slice.
4. No merge of half-migrated route paths (old + new concurrent behavior) without explicit exception.

## 4. Session Start Checklist (For Codex)

1. Confirm active phase and target task IDs.
2. Confirm write scope and delete scope.
3. Confirm validation commands for this slice.
4. Confirm process model impact (frontend/backend/runtime/channel).
5. Update this ledger when a new mistake pattern appears.

## 5. Session End Checklist (For Codex)

1. Mark finished tasks in execution plan.
2. Record new mistakes and preventive rules (if any).
3. Report verification evidence (build/test/smoke/ports).
4. Ensure no unmanaged background process remains.
