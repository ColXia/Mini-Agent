# Task Plan

## Latest Sync: 2026-04-16 P40.15 Runtime Snapshot Default-Session Contract

## Current Execution Slice: P40.15 Runtime Snapshot Default-Session Contract (2026-04-16)

### Why This Slice Is Next

- after `P40.14`, the remaining runtime bucket still recommended `runtime-session-contract`, but most of that residue had become mixed adoption/deletion work
- `session_snapshot.py` was the one clearly independent seam left:
  - it had a tiny DTO contract drift
  - it did not require reopening `session_operator_handler.py` or `main_agent_runtime_manager.py`
- the honest next move was therefore to land the missing default-session snapshot field rather than force a larger mixed runtime commit

### Scope

- land the snapshot DTO contract update:
  - `src/mini_agent/runtime/session_snapshot.py`
- extend focused builder coverage:
  - `tests/test_runtime_session_snapshot_builder.py`
- verify adjacent snapshot import/export surfaces still pass

### Acceptance

- runtime snapshot DTOs preserve `is_default`
- live-session snapshot building preserves `is_default`
- persisted-record snapshot building preserves `is_default`
- focused tests and adjacent snapshot regressions are green

### Status

- completed

### Implementation Notes

- landed commit:
  - `8b60c23`
  - `p40: land runtime snapshot default-session contract`
- focused verification:
  - `uv run ruff check src/mini_agent/runtime/session_snapshot.py tests/test_runtime_session_snapshot_builder.py`
  - result: `All checks passed!`
  - `uv run pytest tests/test_runtime_session_snapshot_builder.py tests/test_runtime_session_snapshot_handler.py -q`
  - result: `4 passed`
  - adjacent snapshot surface checks:
    - `uv run pytest tests/test_main_agent_surface_service.py -k "can_import_local_session_snapshot or can_export_shared_session_snapshot or import_session_snapshot_can_register_lineage_child or import_session_snapshot_rejects_duplicate_session_id" -q`
    - result: `4 passed, 72 deselected`
- post-commit residual snapshot from `python scripts/worktree_slice_report.py`:
  - total dirty paths: `147 -> 146`
  - `runtime-session-contract`: `17 -> 16`
- important boundary result:
  - the runtime bucket no longer has another obviously independent DTO/compatibility seam of similar size
  - the remaining residue is now dominated by mixed adoption/deletion work across:
    - `main_agent_runtime_manager.py`
    - `session_operator_handler.py`
    - legacy handler deletions
    - staged `interaction` extraction
    - staged skill/model-selection support extractions

### Next Likely Seam

- current recommended next slice still reports `runtime-session-contract`, but a stricter audit now says:
  - no more clean runtime-only micro-slice is obvious
  - the next honest move is either:
    - a bounded cross-bucket adoption slice spanning runtime + tracked replacements
    - or closing the blocking upstream buckets first:
      - `surface-transport-orchestration` for `interaction/`
      - `agent-core-and-cli-surface` for skill command support
      - `model-runtime-substrate` for session model-selection support

## Latest Sync: 2026-04-16 P40.14 Runtime Memory Command Compatibility Bridge

## Current Execution Slice: P40.14 Runtime Memory Command Compatibility Bridge (2026-04-16)

### Why This Slice Is Next

- after `P40.13`, the remaining runtime residue still contained one more clean compatibility seam before the larger operator/manager convergence:
  - `src/mini_agent/runtime/session_memory_command_handler.py`
- this seam was still narrow enough to land honestly because the underlying shared memory command owner had already been landed in `P40.6`
- the real unfinished part was compatibility:
  - keep the newer `MemoryCommandService` wrapper
  - restore old runtime command/constructor expectations so the handler can land independently

### Scope

- land the compatibility bridge for:
  - `src/mini_agent/runtime/session_memory_command_handler.py`
- land focused regression coverage:
  - `tests/test_runtime_session_memory_command_handler.py`
- verify adjacent runtime-memory behavior without reopening operator/manager adoption

### Acceptance

- runtime memory handler supports both:
  - `MemoryCommandRequest`
  - legacy `RuntimeSessionMemoryCommand`
- handler supports both:
  - injected shared `MemoryCommandService`
  - legacy constructor wiring through runtime backend / save-note / save-profile callables
- runtime memory results still update session diagnostics and preserve current user-facing payload shape
- focused tests and adjacent runtime-memory regressions are green

### Status

- completed

### Implementation Notes

- landed commit:
  - `1f3d4a8`
  - `p40: land runtime memory command compatibility bridge`
- focused verification:
  - `uv run ruff check src/mini_agent/runtime/session_memory_command_handler.py tests/test_runtime_session_memory_command_handler.py`
  - result: `All checks passed!`
  - `uv run pytest tests/test_runtime_session_memory_command_handler.py -q`
  - result: `3 passed`
  - adjacent runtime-memory checks:
    - `uv run pytest tests/test_main_agent_surface_service.py -k "manage_session_memory_reports_runtime_entries_and_can_promote_note_and_shared or manage_session_memory_can_save_distilled_note_and_profile" -q`
    - result: `2 passed, 74 deselected`
    - `uv run pytest tests/test_command_execution_service.py -k "builds_memory_list_from_runtime_state or runs_workspace_memory_mutations" -q`
    - result: `2 passed, 21 deselected`
- post-commit residual snapshot from `python scripts/worktree_slice_report.py`:
  - total dirty paths: `148 -> 147`
  - `runtime-session-contract`: `18 -> 17`
- important boundary result:
  - runtime/session residue is now even less about missing shared owners
  - it is mostly:
    - `main_agent_runtime_manager.py`
    - `session_operator_handler.py`
    - `session_snapshot.py`
    - legacy handler deletions / interaction extraction cleanup

### Next Likely Seam

- current recommended next slice remains `runtime-session-contract`
- the next honest cut now needs a stricter adoption/deletion audit:
  - likely `session_snapshot.py` compatibility if it can stand alone
  - otherwise reopen `session_operator_handler.py` and `main_agent_runtime_manager.py` only with a deliberately bounded adoption slice

## Latest Sync: 2026-04-16 P40.13 Runtime Live-State Compatibility Bridge

## Current Execution Slice: P40.13 Runtime Live-State Compatibility Bridge (2026-04-16)

### Why This Slice Is Next

- after `P40.12`, `session_live_state_handler.py` was the next narrow compatibility seam inside the remaining runtime cluster
- the handler had two clean-clone / adoption problems that could be fixed without reopening the manager rewrite:
  - it imported the still-untracked `mini_agent.interaction` package directly
  - it had removed older pending-approval / recovery / reset entrypoints that some runtime paths still expected
- the right fix was compatibility bridging, not re-bundling the old inline implementation or forcing the new manager wiring to land at the same time

### Scope

- land the live-state compatibility bridge:
  - `src/mini_agent/runtime/session_live_state_handler.py`
- land focused regression coverage:
  - `tests/test_runtime_session_live_state_handler.py`
- keep broader operator/manager adoption out of this cut

### Acceptance

- live-state owner tolerates staged `interaction` extraction through fallback imports
- legacy pending-approval / recovery / reset entrypoints are restored as wrappers over the extracted support owners
- newer support-owner injection still works and is preferred when supplied
- focused tests and adjacent recovery-surface regressions are green

### Status

- completed

### Implementation Notes

- landed commit:
  - `b62672f`
  - `p40: land runtime live-state compatibility bridge`
- focused verification:
  - `uv run ruff check src/mini_agent/runtime/session_live_state_handler.py tests/test_runtime_session_live_state_handler.py`
  - result: `All checks passed!`
  - `uv run pytest tests/test_runtime_session_live_state_handler.py tests/test_runtime_session_pending_approval_state_handler.py tests/test_runtime_session_recovery_reset_handler.py -q`
  - result: `10 passed`
  - adjacent recovery checks:
    - `uv run pytest tests/test_main_agent_surface_service.py -k "persisted_interrupted_session_exposes_recovery_snapshot_after_restart or restarted_shared_session_keeps_recovery_until_next_turn_consumes_it" -q`
    - result: `2 passed, 74 deselected`
- post-commit residual snapshot from `python scripts/worktree_slice_report.py`:
  - total dirty paths: `149 -> 148`
  - `runtime-session-contract`: `19 -> 18`
- important boundary result:
  - live session mutation ownership now supports both extracted support owners and older runtime expectations
  - this removed another reason to reopen `main_agent_runtime_manager.py` too early

## Latest Sync: 2026-04-16 P40.12 Runtime Contract Compatibility Utilities Landing

## Current Execution Slice: P40.12 Runtime Contract Compatibility Utilities Landing (2026-04-16)

### Why This Slice Is Next

- after `P40.11`, the remaining `runtime-session-contract` residue was no longer another honest support-file bundle
- the next narrow cut had to reduce compatibility risk inside the still-modified runtime files without reopening the broader manager/operator adoption line
- `session_agent_runtime_handler.py` and adjacent runtime package seams were the healthiest first target because they could be made dual-compatible with:
  - old manager wiring
  - newer extracted support wiring
- this slice also let us tighten one clean-clone edge without forcing the pending `session_live_state_handler.py` and `session_memory_command_handler.py` adoption work into the same commit

### Scope

- land runtime compatibility utilities around the agent-runtime seam:
  - `src/mini_agent/runtime/session_agent_runtime_handler.py`
  - `src/mini_agent/runtime/sandbox_state.py`
  - `src/mini_agent/runtime/__init__.py`
- land focused regression coverage:
  - `tests/test_runtime_session_agent_runtime_handler.py`
  - `tests/test_sandbox_state.py`
  - `tests/test_runtime_package_exports.py`
- keep `main_agent_runtime_manager.py`, `session_live_state_handler.py`, and operator adoption out of this cut

### Acceptance

- `RuntimeSessionAgentRuntimeHandler` supports both:
  - explicit `agent_messages(...)` wiring and legacy `agent.messages`
  - explicit `refresh_runtime_projection(...)` wiring and legacy sandbox-diagnostics builder wiring
- sandbox diagnostics read the maintained runtime-service owner instead of only legacy direct attributes
- runtime package exports keep the new contracts importable without forcing the larger manager slice
- focused tests and lint are green

### Status

- completed

### Implementation Notes

- landed commit:
  - `b308e11`
  - `p40: land runtime contract compatibility utilities`
- focused verification:
  - `uv run pytest tests/test_runtime_session_agent_runtime_handler.py tests/test_sandbox_state.py tests/test_runtime_package_exports.py -q`
  - result: `5 passed`
  - `uv run ruff check src/mini_agent/runtime/session_agent_runtime_handler.py src/mini_agent/runtime/sandbox_state.py src/mini_agent/runtime/__init__.py tests/test_runtime_session_agent_runtime_handler.py tests/test_sandbox_state.py tests/test_runtime_package_exports.py`
  - result: `All checks passed!`
  - adjacent old-manager checks:
    - `uv run pytest tests/test_main_agent_surface_service.py -k "can_update_shared_session_runtime_policy or control_session_mcp_reload_rebuilds_session_agent or control_session_mcp_list_records_operator_snapshot" -q`
    - result: `3 passed`
- post-commit residual snapshot from `python scripts/worktree_slice_report.py`:
  - total dirty paths: `154 -> 149`
  - `runtime-session-contract`: `24 -> 19`
- important boundary result:
  - the remaining runtime residue is now more clearly a compatibility/adoption story than a missing-utility story
  - the most promising next narrow seam is:
    - `session_live_state_handler.py` compatibility bridging
  - after that:
    - `session_memory_command_handler.py` compatibility bridging

### Next Likely Seam

- current recommended next slice remains `runtime-session-contract`
- the next honest cut should continue compatibility bridging before reopening the larger manager/operator convergence:
  - `session_live_state_handler.py`
  - then likely `session_memory_command_handler.py`

## Latest Sync: 2026-04-16 P40.11 Runtime MCP Control Support Landing

## Current Execution Slice: P40.11 Runtime MCP Control Support Landing (2026-04-16)

### Why This Slice Is Next

- after `P40.10`, the remaining runtime control residue still had one support seam that could be landed honestly without reopening the broader operator/manager adoption line:
  - `src/mini_agent/runtime/session_mcp_control_handler.py`
  - `src/mini_agent/tools/mcp/command_service.py`
  - their focused tests
- this seam stayed narrower than the remaining adoption work because:
  - the handler and command service are both still untracked support files
  - focused tests cover them directly
  - the broader `session_operator_handler.py` and `main_agent_runtime_manager.py` diffs are still mixed with manager/runtime adoption

### Scope

- land the shared MCP control support layer:
  - `src/mini_agent/tools/mcp/command_service.py`
  - `src/mini_agent/runtime/session_mcp_control_handler.py`
- land focused regression coverage:
  - `tests/test_runtime_session_mcp_control_handler.py`
  - `tests/test_mcp_command_service_feedback.py`
- keep operator/manager adoption out of this cut

### Acceptance

- runtime and local MCP control semantics have maintained shared owners for:
  - action validation
  - reload conflict behavior
  - snapshot-based summary/details formatting
  - local MCP reload success/warm-reload text
- focused MCP support tests and lint are green

### Status

- completed

### Implementation Notes

- landed commit:
  - `9942b26`
  - `p40: land runtime mcp control support`
- focused verification:
  - `uv run pytest tests/test_runtime_session_mcp_control_handler.py tests/test_mcp_command_service_feedback.py -q`
  - result: `6 passed`
  - `uv run ruff check src/mini_agent/tools/mcp/command_service.py src/mini_agent/runtime/session_mcp_control_handler.py tests/test_runtime_session_mcp_control_handler.py tests/test_mcp_command_service_feedback.py`
  - result: `All checks passed!`
- post-commit residual snapshot from `python scripts/worktree_slice_report.py`:
  - total dirty paths: `158 -> 154`
  - `runtime-session-contract`: `26 -> 24`
  - `unmatched_count`: `6 -> 5`
- important boundary result:
  - the remaining runtime residue is now even more honestly concentrated in modified adoption files rather than missing support modules
  - the remaining runtime cluster is primarily:
    - `main_agent_runtime_manager.py`
    - `session_operator_handler.py`
    - `session_agent_runtime_handler.py`
    - `session_live_state_handler.py`
    - `session_memory_command_handler.py`
    - legacy handler deletions and their adoption cleanup

### Next Likely Seam

- current recommended next slice remains `runtime-session-contract`
- but the next honest cut is no longer another support-file landing
- it now has to be a compatibility/adoption slice across the modified runtime files, likely split around:
  - manager/live-state compatibility
  - operator/agent-runtime adoption
  - legacy handler deletion closure

## Latest Sync: 2026-04-16 P40.10 Runtime Control Support Modules Landing

## Current Execution Slice: P40.10 Runtime Control Support Modules Landing (2026-04-16)

### Why This Slice Is Next

- after `P40.9`, the broader `runtime-session-contract` residue was still too mixed to land as one operator/manager commit
- the next honest narrow cut was the still-untracked support module group that had already stabilized under focused tests:
  - `runtime_policy_service.py`
  - `session_admin_handler.py`
  - `session_agent_control_handler.py`
  - `session_control_models.py`
- these files were support owners, not manager adoption
- landing them first reduced the dirty-tree chaos without forcing the remaining modified runtime files into the same commit

### Scope

- land the support modules:
  - `src/mini_agent/runtime/runtime_policy_service.py`
  - `src/mini_agent/runtime/session_admin_handler.py`
  - `src/mini_agent/runtime/session_agent_control_handler.py`
  - `src/mini_agent/runtime/session_control_models.py`
- land focused tests:
  - `tests/test_runtime_policy_service.py`
  - `tests/test_runtime_session_admin_handler.py`
  - `tests/test_runtime_session_agent_control_handler.py`
- keep manager/operator adoption out of this cut

### Acceptance

- runtime policy planning/feedback has a dedicated shared owner
- session admin mutations have a dedicated shared owner
- session agent-control semantics have a dedicated shared owner
- focused support tests and lint are green

### Status

- completed

### Implementation Notes

- landed commit:
  - `ec1e1c6`
  - `p40: land runtime control support modules`
- focused verification:
  - `uv run pytest tests/test_runtime_policy_service.py tests/test_runtime_session_admin_handler.py tests/test_runtime_session_agent_control_handler.py -q`
  - result: `10 passed`
  - `uv run ruff check src/mini_agent/runtime/runtime_policy_service.py src/mini_agent/runtime/session_admin_handler.py src/mini_agent/runtime/session_agent_control_handler.py src/mini_agent/runtime/session_control_models.py tests/test_runtime_policy_service.py tests/test_runtime_session_admin_handler.py tests/test_runtime_session_agent_control_handler.py`
  - result: `All checks passed!`
- post-commit residual snapshot from `python scripts/worktree_slice_report.py`:
  - total dirty paths: `165 -> 158`
  - `runtime-session-contract`: `33 -> 26`
- important boundary result:
  - the runtime control area no longer depends on a pile of untracked support modules for policy/admin/agent-control semantics
  - the remaining runtime residue is more clearly an adoption/compatibility problem, not a missing-module problem

### Next Likely Seam

- after this cut, the next clean support candidate inside runtime control was the isolated MCP support layer
- broader operator/manager convergence still remained too mixed for the immediate next commit

## Latest Sync: 2026-04-16 P40.9 Runtime Interrupt / Pending-Approval Support Landing

## Current Execution Slice: P40.9 Runtime Interrupt / Pending-Approval Support Landing (2026-04-16)

### Why This Slice Is Next

- after closing docs and landing the smaller memory/runtime support cuts, `runtime-session-contract` was still the recommended next slice
- a stricter audit of the remaining dirty runtime files showed that the larger `operator/control` convergence line was still mixed:
  - `session_operator_handler.py` now depends on new context/skill/model/runtime-policy services from other still-dirty slices
  - `main_agent_runtime_manager.py` still bundles broader manager adoption that would reopen already-separated runtime support lines
- the safest honest next move was therefore to cut the most independent sub-slice inside the runtime control area first:
  - cancel semantics
  - pending-approval resolution semantics
  - pending-approval state normalization
  - shared control-error wording

### Scope

- land the interrupt/approval support helpers:
  - `src/mini_agent/runtime/session_cancel_service.py`
  - `src/mini_agent/runtime/session_control_error_service.py`
  - `src/mini_agent/runtime/session_pending_approval_service.py`
  - `src/mini_agent/runtime/session_pending_approval_state_handler.py`
- rewire the maintained interrupt owner to the extracted shared services:
  - `src/mini_agent/runtime/session_interrupt_handler.py`
- add focused runtime regressions for the extracted semantics:
  - `tests/test_runtime_session_error_services.py`
  - `tests/test_runtime_session_pending_approval_state_handler.py`
  - `tests/test_runtime_session_interrupt_handler.py`

### Acceptance

- cancel semantics have one shared owner for:
  - no-running-turn detail
  - not-cancellable detail
  - requested summary/status/transcript text
- pending-approval resolution has one shared owner for:
  - token resolution
  - restart-recovery conflict detail
  - waiter validation
  - approve/deny transcript text
- pending-approval state normalization/mutation is covered directly by focused tests
- the narrowed slice lands without dragging in the broader manager/operator adoption line

### Status

- completed

### Implementation Notes

- landed commit:
  - `e4176ab`
  - `p40: land runtime interrupt approval support`
- focused verification:
  - `uv run pytest tests/test_runtime_policy_service.py tests/test_runtime_session_admin_handler.py tests/test_runtime_session_agent_control_handler.py tests/test_runtime_session_agent_runtime_handler.py tests/test_runtime_session_error_services.py tests/test_runtime_session_mcp_control_handler.py tests/test_runtime_session_operator_handler.py tests/test_runtime_session_pending_approval_state_handler.py -q`
  - result: `22 passed`
  - `uv run ruff check src/mini_agent/runtime/runtime_policy_service.py src/mini_agent/runtime/session_admin_handler.py src/mini_agent/runtime/session_agent_control_handler.py src/mini_agent/runtime/session_cancel_service.py src/mini_agent/runtime/session_control_error_service.py src/mini_agent/runtime/session_control_models.py src/mini_agent/runtime/session_mcp_control_handler.py src/mini_agent/runtime/session_pending_approval_service.py src/mini_agent/runtime/session_pending_approval_state_handler.py src/mini_agent/runtime/session_interrupt_handler.py src/mini_agent/runtime/session_operator_handler.py src/mini_agent/runtime/session_agent_runtime_handler.py src/mini_agent/runtime/session_live_state_handler.py src/mini_agent/runtime/__init__.py tests/test_runtime_policy_service.py tests/test_runtime_session_admin_handler.py tests/test_runtime_session_agent_control_handler.py tests/test_runtime_session_agent_runtime_handler.py tests/test_runtime_session_error_services.py tests/test_runtime_session_mcp_control_handler.py tests/test_runtime_session_operator_handler.py tests/test_runtime_session_pending_approval_state_handler.py`
  - result: `All checks passed!`
  - `uv run pytest tests/test_runtime_session_interrupt_handler.py tests/test_runtime_session_error_services.py tests/test_runtime_session_pending_approval_state_handler.py -q`
  - result: `7 passed`
  - `uv run ruff check src/mini_agent/runtime/session_cancel_service.py src/mini_agent/runtime/session_pending_approval_service.py src/mini_agent/runtime/session_pending_approval_state_handler.py src/mini_agent/runtime/session_interrupt_handler.py tests/test_runtime_session_interrupt_handler.py tests/test_runtime_session_error_services.py tests/test_runtime_session_pending_approval_state_handler.py`
  - result: `All checks passed!`
- post-commit residual snapshot from `python scripts/worktree_slice_report.py`:
  - total dirty paths: `172 -> 165`
  - `runtime-session-contract`: `40 -> 33`
- important boundary result:
  - the runtime interrupt/approval semantics are now landable independently of the broader operator/manager convergence
  - the remaining runtime residue is more honestly concentrated in:
    - `main_agent_runtime_manager.py`
    - `session_operator_handler.py`
    - `session_agent_runtime_handler.py`
    - `session_live_state_handler.py`
    - deleted legacy handler cleanup plus the still-untracked operator/control support files

### Next Likely Seam

- keep `runtime-session-contract` as the next recommended slice, but continue narrowing inside it
- the next honest candidate is now the broader `operator/control` support layer only if it can be landed without reopening:
  - `agent_core` skill command support
  - model-selection support adoption
  - full runtime-manager convergence
- if that still proves mixed, split again rather than bundling the manager rewrite

## Latest Sync: 2026-04-16 P40.8 Historical Architecture Docs Landing

## Current Execution Slice: P40.8 Historical Architecture Docs Landing (2026-04-16)

### Why This Slice Is Next

- after `P40.7`, the remaining `docs-planning-governance` residue was no longer modified active docs
- it had narrowed cleanly to 9 untracked historical/reference docs that were already referenced by:
  - `docs/DOCS_INDEX.md`
  - `docs/DEVELOPMENT_INDEX.md`
  - planning-memory files
- leaving them untracked would keep the repo in a misleading state:
  - index docs pointed to files that did not exist in git
  - planning memory referred to docs that a clean clone could not open

### Scope

- land the remaining 9 referenced untracked docs:
  - `docs/AGENT_CORE_RUNTIME_SEAMS.md`
  - `docs/P32_PROJECT_STRUCTURE_REALIGNMENT_PLAN_2026-04-13.md`
  - `docs/P33_LLM_RUNTIME_UPGRADE_PLAN_2026-04-14.md`
  - `docs/P33B_RUNTIME_TRUTH_AND_PROVIDER_GOVERNANCE_PLAN_2026-04-15.md`
  - `docs/P34_AGENT_CORE_REFACTOR_PLAN_2026-04-15.md`
  - `docs/P36_SESSION_RUNTIME_CONTRACT_CONSOLIDATION_PLAN_2026-04-15.md`
  - `docs/P37_TUI_SURFACE_ORCHESTRATION_CONVERGENCE_PLAN_2026-04-15.md`
  - `docs/POST_P36_RUNTIME_SURFACE_EVALUATION_2026-04-15.md`
  - `docs/POST_P37_TUI_SURFACE_EVALUATION_2026-04-16.md`
- normalize obvious status drift in the historical plan docs before landing:
  - completed historical plans should not still present as `active`
  - maintained seam/reference docs may remain active if they still define live ownership truth

### Acceptance

- all 9 referenced docs exist in git
- historical plan docs no longer claim to be active when later slices have already completed them
- `docs-planning-governance` fully disappears from the dirty-worktree classifier

### Status

- completed

### Implementation Notes

- audit result:
  - these 9 docs were not stray scratch files
  - they were already referenced by repo indexes and planning-memory files
- status normalization applied before landing:
  - `P32`, `P33`, `P33b`, and `P34` now read as completed historical planning
  - `AGENT_CORE_RUNTIME_SEAMS.md` remains active because it documents maintained live seam ownership
  - `P36`, `P37`, and both post-evaluation docs were already marked completed and needed no semantic status correction
- landed commit:
  - `16a7e0c`
  - `p40: land historical architecture docs`
- post-commit residual snapshot from `python scripts/worktree_slice_report.py`:
  - total dirty paths: `172`
  - `agent-core-and-cli-surface`: `62`
  - `surface-transport-orchestration`: `42`
  - `runtime-session-contract`: `40`
  - `developer-tooling-smokes`: `9`
  - `interfaces-apps`: `7`
  - `model-runtime-substrate`: `6`
- important structural result:
  - `docs-planning-governance` is now closed
  - the classifier no longer reports a docs bucket
  - the recommended next slice has advanced to `runtime-session-contract`

### Next Likely Seam

- with docs now closed, the next safest anti-chaos slice is:
  - `runtime-session-contract`
- after that, current classifier order is:
  - `surface-transport-orchestration`
  - `agent-core-and-cli-surface`

## Latest Sync: 2026-04-16 P40.7 Active Doc Truth Sync

## Current Execution Slice: P40.7 Active Doc Truth Sync (2026-04-16)

### Why This Slice Is Next

- after `P40.6`, the safest anti-chaos slice was the active portion of `docs-planning-governance`
- the modified active docs were no longer harmless status drift:
  - four of them had real mojibake/encoding corruption inside current diffs
  - several others already carried legitimate path/ownership updates from the recent refactors
- the right move was therefore to repair and land the active-doc truth layer first, before mixing in the still-untracked historical plan/evaluation docs

### Scope

- repair the confirmed corrupted active docs:
  - `docs/P23_AGENT_CORE_DETAILED_PLAN.md`
  - `docs/P23_AGENT_CORE_TASK_PLAN.md`
  - `docs/OSS_REFERENCE_INDEX.md`
  - `docs/RUNTIME_FLOW.md`
- preserve legitimate active-doc truth updates already present in the dirty tree:
  - `studio_router` -> `ops_router`
  - turn-context / execution-policy / engine path realignment
  - `code_agent/*` -> `agent_core/*` reference shifts where the repo has already converged
  - QQ-only / browser-removed surface truth in runtime docs
- land the full modified active-doc set as one narrow slice
- keep the 9 untracked historical plan/evaluation docs out of this cut

### Acceptance

- the modified active docs are readable again and no longer contain the confirmed mojibake corruption
- active docs reflect the current physical/logical ownership truth instead of stale pre-refactor paths
- `docs-planning-governance` is reduced to the separate untracked historical-doc residue only

### Status

- completed

### Implementation Notes

- repaired and re-landed the corrupted active docs while preserving real refactor updates:
  - `P23` detailed/task docs restored to readable Chinese and kept the current gateway/test/path naming
  - `OSS_REFERENCE_INDEX.md` now points at the maintained `agent_core/*`, `plugins/*`, and modern interaction/runtime targets without corrupted headers or upstream paths
  - `RUNTIME_FLOW.md` now cleanly reflects:
    - `ops_router`
    - bootstrap provider-registry fallback
    - runtime request-policy / rectifier defaults
    - `agent_core` execution/context ownership
    - browser WebUI retirement and QQ-only active remote-adapter truth
- landed only the modified active-doc slice:
  - commit: `66476e5`
  - message: `p40: sync active docs truth`
- post-commit residual snapshot from `python scripts/worktree_slice_report.py`:
  - total dirty paths: `181`
  - `agent-core-and-cli-surface`: `62`
  - `surface-transport-orchestration`: `42`
  - `runtime-session-contract`: `40`
  - `developer-tooling-smokes`: `9`
  - `docs-planning-governance`: `9`
  - `model-runtime-substrate`: `6`
- important boundary result:
  - `docs-planning-governance` now contains only the 9 untracked historical plan/evaluation docs
  - the previously modified active docs are no longer part of the dirty-tree story

### Next Likely Seam

- current recommended next slice remains `docs-planning-governance`, but it is now a narrower second-stage docs cut:
  - land or explicitly archive the 9 untracked historical plan/evaluation docs
- after docs are fully closed, reopen code-bearing slices conservatively based on current classifier size/mix:
  - `runtime-session-contract`
  - `surface-transport-orchestration`
  - `agent-core-and-cli-surface`


## Latest Sync: 2026-04-16 P40.6 Memory Governance Support Landing

## Current Execution Slice: P40.6 Memory Governance Support Landing (2026-04-16)

### Why This Slice Is Next

- after `P40.5`, the smallest remaining code-bearing anti-chaos slice was the residual `memory-governance` bundle
- that bundle was no longer speculative cleanup:
  - committed runtime and command surfaces already imported the still-untracked memory governance helpers
  - committed CLI/TUI and runtime flows already depended on those helpers for `/memory`, runtime diagnostics, and KB toggle semantics
- the honest next move was therefore to land the missing support layer itself, not to reopen larger runtime or TUI bundles

### Scope

- land the remaining memory-governance support files:
  - `src/mini_agent/memory/command_service.py`
  - `src/mini_agent/memory/diagnostics.py`
  - `src/mini_agent/memory/runtime_backend.py`
  - `src/mini_agent/tools/knowledge_base_control_service.py`
- carry the one required compatibility test import update:
  - `tests/test_knowledge_base_tool.py`
- keep broader runtime/control/TUI adoption work out of this cut

### Acceptance

- committed code no longer depends on untracked memory-governance support modules
- `/memory` command semantics, runtime diagnostics shaping, runtime-memory backend access, and KB toggle semantics all exist as maintained repo code
- focused local-command, runtime-diagnostics, CLI, and TUI regressions for these seams are green

### Status

- completed

### Implementation Notes

- this slice closes the remaining memory-governance clean-clone gap by landing the shared support layer that committed code already imports:
  - `MemoryCommandService` now owns shared `/memory` semantics for local and runtime surfaces
  - `build_memory_diagnostics(...)` and related formatting/selectors now live in maintained memory diagnostics code
  - `WorkspaceRuntimeMemoryBackend` now provides the workspace-scoped runtime-memory adapter from the memory package itself
  - `KnowledgeBaseControlService` now owns shared KB status/toggle semantics across local and runtime control paths
- the only required test-surface change in this slice was the maintained import path update in `tests/test_knowledge_base_tool.py`
- focused verification for this slice:
  - `python -m pytest tests/test_command_execution_service.py tests/test_runtime_session_diagnostics_service.py tests/test_knowledge_base_tool.py`
  - result: `33 passed`
  - `python -m pytest tests/test_cli_submission_loop.py -k test_run_interactive_session_memory_promote_and_save_commands`
  - result: `1 passed`
  - `python -m pytest tests/test_tui_app.py -k "test_tui_remote_memory_shared_commands_route_through_gateway or test_tui_remote_memory_mutation_commands_route_through_gateway"`
  - result: `2 passed`
  - `ruff check src/mini_agent/memory/command_service.py src/mini_agent/memory/diagnostics.py src/mini_agent/memory/runtime_backend.py src/mini_agent/tools/knowledge_base_control_service.py tests/test_knowledge_base_tool.py tests/test_command_execution_service.py tests/test_runtime_session_diagnostics_service.py`
  - result: `All checks passed!`
- landed commit:
  - `0dea687` `p40: land memory governance support`
- post-commit residual snapshot from `python scripts/worktree_slice_report.py`:
  - total dirty paths: `191`
  - `agent-core-and-cli-surface`: `62`
  - `surface-transport-orchestration`: `42`
  - `runtime-session-contract`: `40`
  - `docs-planning-governance`: `19`
  - `memory-governance`: `0` (closed)

### Next Likely Seam

- with `memory-governance` now closed, the next safest anti-chaos slice is again the non-code status/documentation residue:
  - `docs-planning-governance`
- after that, reopen code-bearing slices conservatively in this order:
  - `runtime-session-contract`
  - `surface-transport-orchestration`
  - `agent-core-and-cli-surface`

## Latest Sync: 2026-04-16 P40.5 Runtime Session Orchestration Support Landing

## Current Execution Slice: P40.5 Runtime Session Orchestration Support Landing (2026-04-16)

### Why This Slice Is Next

- after `P40.4`, the next honest runtime seam is the orchestration support layer above the already-landed data-shaping support
- this is still narrower than the full `main_agent_runtime_manager.py` convergence line
- the key support targets in this layer are:
  - session access/default-session planning
  - session creation + lifecycle bootstrap compatibility
  - session registry/persistence orchestration
  - hydration coordination
  - managed-store cleanup/persistence
  - recovery reset helpers
  - shared workspace-path normalization
- a stricter audit found the same boundary rule as the previous slice:
  - some of these handlers are already used by committed runtime code
  - others are only referenced by the still-dirty manager rewrite
  - so this slice must preserve old constructor wiring while landing the new support seams

### Scope

- land the runtime session orchestration support files:
  - `session_access_handler.py`
  - `session_creation_handler.py`
  - `session_catalog_handler.py`
  - `session_registry_handler.py`
  - `session_hydration_coordinator.py`
  - `session_managed_store_handler.py`
  - `session_recovery_reset_handler.py`
  - `session_runtime_lifecycle_handler.py`
  - `workspace_path_utils.py`
  - `session_lifecycle.py`
- keep `main_agent_runtime_manager.py` and the broader control/operator/runtime-handler convergence out of this cut
- add focused support tests for access/creation/catalog/registry/snapshot plus the new support modules

### Acceptance

- the runtime session orchestration support layer lands independently of the broader manager rewrite
- clean-clone compatibility is preserved for older runtime wiring:
  - legacy access-handler construction still works
  - legacy creation-handler lifecycle wiring still works
  - legacy `enforce_capacity(len(sessions))` registry wiring still works
- focused runtime orchestration support tests and adjacent runtime-surface regressions are green

### Status

- completed

### Implementation Notes

- key compatibility corrections inside this slice:
  - `RuntimeSessionAccessHandler` now preserves legacy team-session selection when default-session support is not wired, while also supporting explicit default-session routing when `resolve_main_workspace(...)` is provided
  - `RuntimeSessionCreationHandler` now supports both the new `bootstrap_session_lifecycle(...)` seam and the older `build_session_key + lifecycle_bootstrap` path
  - `RuntimeSessionRegistryHandler` now supports both zero-arg and legacy one-arg `enforce_capacity(...)` wiring
  - `RuntimeSessionCatalogHandler` now tolerates the staged `interaction` extraction through a compatibility import and shares workspace-key normalization through `workspace_path_utils.py`
- new support modules landed in this slice:
  - `session_hydration_coordinator.py`
  - `session_managed_store_handler.py`
  - `session_recovery_reset_handler.py`
  - `session_runtime_lifecycle_handler.py`
  - `workspace_path_utils.py`
- focused verification target for this slice:
  - `tests/test_runtime_session_access_handler.py`
  - `tests/test_runtime_session_creation_handler.py`
  - `tests/test_runtime_session_catalog_handler.py`
  - `tests/test_runtime_session_registry_handler.py`
  - `tests/test_runtime_session_snapshot_handler.py`
  - `tests/test_runtime_session_hydration_coordinator.py`
  - `tests/test_runtime_managed_session_store_handler.py`
  - `tests/test_runtime_session_recovery_reset_handler.py`
  - `tests/test_runtime_session_lifecycle_handler.py`
  - `tests/test_runtime_workspace_path_utils.py`
  - `tests/test_session_lifecycle_runtime.py`
- adjacent runtime-surface verification in this slice:
  - snapshot import/export regressions in `tests/test_main_agent_surface_service.py`
  - catalog dedupe regression in `tests/test_main_agent_surface_service.py`
- landed commit:
  - `5151b4c` `p40: land runtime session orchestration support`
- post-commit residual snapshot from `python scripts/worktree_slice_report.py`:
  - total dirty paths: `196`
  - `runtime-session-contract`: `40`
  - `agent-core-and-cli-surface`: `62`
  - `surface-transport-orchestration`: `42`
  - `docs-planning-governance`: `19`
  - `memory-governance`: `5`

### Next Likely Seam

- after this orchestration support layer lands, the remaining runtime residue is more concentrated in:
  - `main_agent_runtime_manager.py`
  - operator/control handlers
  - agent-runtime/pending-approval/control services
- that remaining runtime bundle is now riskier to cut honestly than the still-small `memory-governance` residue
- current recommended next code slice:
  - `memory-governance`

## Latest Sync: 2026-04-16 P40.4 Runtime Session Data-Shaping Support Landing

## Current Execution Slice: P40.4 Runtime Session Data-Shaping Support Landing (2026-04-16)

### Why This Slice Is Next

- after `P40.3`, the next honest runtime seam is not the full manager/handler convergence
- the safer cut is the session data-shaping support layer directly above the already-landed runtime substrate:
  - diagnostics
  - hydration payloads
  - runtime state hydration
  - persistence metadata shaping
  - read-model shaping
  - snapshot export compatibility
- a stricter audit found one important boundary rule for this cut:
  - these files are already instantiated by committed `main_agent_runtime_manager.py`
  - but that committed manager still uses older constructor wiring and older helper methods
  - so this slice must preserve backward compatibility rather than forcing the full manager diff into the same commit

### Scope

- land the narrowed runtime session support files:
  - `session_diagnostics_service.py`
  - `session_hydration_builder.py`
  - `session_runtime_state_hydrator.py`
  - `session_state.py`
  - `session_persistence_record_builder.py`
  - `session_read_model_builder.py`
  - `session_snapshot_builder.py`
  - `session_restore_handler.py`
- keep the broader `main_agent_runtime_manager.py` adoption out of this cut
- add focused compatibility regressions so old manager wiring and new support seams both remain valid

### Acceptance

- the narrowed runtime session support layer is committed independently of the broader manager rewrite
- clean-clone compatibility is preserved for the committed runtime manager:
  - legacy constructor arguments still work
  - legacy `apply_stored_recovery` and snapshot-export paths still work
  - staged `interaction` extraction is not required for this slice to import cleanly
- focused runtime support tests and adjacent default-session regressions are green

### Status

- completed

### Implementation Notes

- key compatibility corrections inside this slice:
  - `RuntimeSessionDiagnosticsService` now supports both explicit support-callables and legacy agent-attribute fallbacks
  - `RuntimeSessionStateHydrator` now supports both explicit support-callables and legacy payload-normalizer wiring
  - `RuntimeSessionPersistenceRecordBuilder` now supports both support-callables and legacy agent-attribute fallbacks
  - `RuntimeSessionReadModelBuilder` keeps legacy snapshot-export methods as compatibility wrappers over the extracted `RuntimeSessionSnapshotBuilder`
  - `RuntimeSessionRestoreHandler` now accepts both the new `bootstrap_session_lifecycle(...)` seam and the older `build_session_key + lifecycle_bootstrap` wiring
  - runtime files that reference `normalize_channel_type` now tolerate the staged `interaction` extraction by falling back to `runtime.interaction_surface`
- focused verification target for this slice:
  - `tests/test_runtime_session_diagnostics_service.py`
  - `tests/test_runtime_session_state_hydrator.py`
  - `tests/test_runtime_session_snapshot_builder.py`
  - `tests/test_runtime_session_persistence_record_builder.py`
  - `tests/test_runtime_session_read_model_builder.py`
  - `tests/test_runtime_session_restore_handler.py`
  - `tests/test_session_projection.py`
  - `tests/test_interface_dto_contracts.py`
  - `tests/test_p19_runtime_matrix.py`
  - four default-session regression tests in `tests/test_main_agent_surface_service.py`
- landed commit:
  - `19a66bd` `p40: land runtime session data shaping support`
- post-commit residual snapshot from `python scripts/worktree_slice_report.py`:
  - total dirty paths: `212`
  - `runtime-session-contract`: `56`
  - `agent-core-and-cli-surface`: `62`
  - `surface-transport-orchestration`: `42`
  - `docs-planning-governance`: `19`
  - `memory-governance`: `5`

### Next Likely Seam

- after this support layer lands, reopen the next runtime adoption seam above it:
  - `session_hydration_coordinator`
  - `session_registry_handler`
  - `session_snapshot_handler`
- if that seam proves mixed again, fall back to the remaining `memory-governance` residue before reopening more runtime orchestration

## Latest Sync: 2026-04-16 P40.3 Runtime Support Substrate Landing

## Current Execution Slice: P40.3 Runtime Support Substrate Landing (2026-04-16)

### Why This Slice Is Next

- after `P40.2`, the next anti-chaos target is the large `runtime-session-contract` residue
- a stricter audit showed that the safest next cut is not the whole runtime manager line
- it is the runtime support substrate underneath that line:
  - contracts
  - payload codec
  - model identity codec
  - agent support helpers
- one part of that substrate is already a clean-clone integrity risk:
  - committed `main_agent_runtime_policy_loader.py` imports `main_agent_runtime_contracts.py`
  - but `main_agent_runtime_contracts.py` is still untracked

### Scope

- land the narrow runtime support substrate files:
  - `main_agent_runtime_contracts.py`
  - `session_agent_support.py`
  - `session_model_identity_codec.py`
  - `session_payload_codec.py`
- land the focused tests for those seams
- keep manager/handler adoption for a later slice

### Acceptance

- committed runtime policy loading no longer depends on an untracked contracts module
- the runtime support substrate exists as maintained repo code rather than floating in the dirty tree
- focused substrate tests and `ruff` are green

### Status

- in_progress

### Implementation Notes

- this slice is intentionally upstream-only, similar to an earlier substrate-first landing:
  - support substrate first
  - broader runtime-manager adoption later
- current focused verification target:
  - `tests/test_main_agent_runtime_policy_loader.py`
  - `tests/test_runtime_session_agent_support.py`
  - `tests/test_runtime_session_model_identity_codec.py`
  - `tests/test_runtime_session_payload_codec.py`

### Next Likely Seam

- after this substrate lands, reopen one narrower adoption seam above it:
  - `session_diagnostics_service / state / persistence / read-model` support adoption
  - or the broader runtime-manager/handler convergence line if it can be kept honest

## Latest Sync: 2026-04-16 P40.2 Memory Core Landing

## Current Execution Slice: P40.2 Memory Core Landing (2026-04-16)

### Why This Slice Is Next

- the new `P40` guardrail report identified `memory-governance` as the safest first code-bearing residual line
- a stricter follow-up audit found a more urgent issue than ordinary dirty-tree size:
  - already-committed `agent_core` files import `mini_agent.memory` modules that are still only present as untracked files
- that means a clean clone is not yet self-consistent on the memory/runtime path
- the next move must therefore land the minimum `memory` core needed to close those imports honestly

### Scope

- land the missing `mini_agent.memory` core modules required by committed `agent_core` and workspace-memory surfaces
- keep broader `memory command service / diagnostics / runtime-session / TUI` adoption out of this cut
- verify the landed memory core against focused memory + `agent_core` context/post-turn tests

### Acceptance

- committed `agent_core` no longer depends on untracked `mini_agent.memory` modules
- the landed slice includes the minimum helper modules those imports need transitively
- focused `memory` and adjacent `agent_core` tests are green

### Status

- in_progress

### Implementation Notes

- missing-core import closure currently requires at least:
  - `automation.py`
  - `service.py`
  - `memoria_runtime.py`
  - `runtime_task_memory.py`
  - `knowledge_base_grounding.py`
  - `promotion.py`
  - `quality.py`
  - `paths.py`
- optional later-line files intentionally kept out for now:
  - `command_service.py`
  - `diagnostics.py`
  - `runtime_backend.py`
  - broader runtime/TUI adoption files
- focused validation target for this slice:
  - `tests/test_memory_core_baseline.py`
  - `tests/test_memory_service.py`
  - `tests/test_memoria_runtime.py`
  - `tests/test_memory_automation.py`
  - `tests/test_memory_real_use_flow.py`
  - `tests/test_agent_core_post_turn.py`
  - `tests/test_agent_core_turn_context.py`

### Next Likely Seam

- after this memory-core closure, reopen the remaining `memory-governance` adjuncts only if still necessary:
  - diagnostics / command-service adoption
  - or the larger `runtime-session-contract` residual line

## Latest Sync: 2026-04-16 P40 Iteration Guardrails Baseline

## Current Execution Slice: P40.1 Iteration Guardrails Baseline (2026-04-16)

### Why This Slice Is Next

- `P39.1` and `P39.2` are already landed as real commits
- the project is technically runnable, but the residual dirty worktree is still large enough to invite mixed follow-up commits
- the user explicitly wants the repo brought back to a clear, iterable state rather than continuing feature work blindly
- the safest immediate move is therefore a guardrail baseline:
  - sync planning-memory to post-`P39` truth
  - classify the remaining dirty tree honestly
  - lock the next landing order in repo-visible artifacts

### Scope

- mark `P39` as completed in planning-memory
- add one maintained dirty-worktree slice report tool
- add one formal guardrail plan for the residual worktree
- keep this slice read-only with respect to product/runtime behavior

### Acceptance

- `P39` is no longer described as the active slice
- the repo contains one repeatable command for current dirty-tree classification
- the next landing order is explicit instead of living only in session memory
- temp status-noise files are kept out of the active worktree story

### Status

- in_progress

### Implementation Notes

- new guardrail artifacts in this slice:
  - `docs/P40_ITERATION_GUARDRAILS_PLAN_2026-04-16.md`
  - `scripts/worktree_slice_report.py`
- measured post-`P39` residual snapshot from `python scripts/worktree_slice_report.py`:
  - total dirty paths: `250`
  - `runtime-session-contract`: `75`
  - `agent-core-and-cli-surface`: `62`
  - `surface-transport-orchestration`: `42`
  - `docs-planning-governance`: `26`
  - `memory-governance`: `17`
- current next landing order is intentionally conservative:
  1. `docs-planning-governance`
  2. `memory-governance`
  3. `runtime-session-contract`
  4. `surface-transport-orchestration`
  5. `agent-core-and-cli-surface`

### Next Likely Seam

- after `P40.1`, reopen the first real code-bearing residual line from the classified buckets
- current leading candidate:
  - `memory-governance`
  - because it improves physical/logical ownership without dragging the broader `runtime / tui` mixed surfaces into the same commit

## Latest Sync: 2026-04-16 P39 Kernel / Model-Runtime Mixed Boundary Slice

## Current Execution Slice: P39 Kernel / Model-Runtime Mixed Boundary Slice (2026-04-16)

### Why This Slice Is Next

- `P38` round-1 active-baseline closure is now committed as its own checkpoint
- the highest-value deferred work is the still-mixed `kernel / model-runtime` boundary
- keeping that work unclassified any longer would invite another phase-fake commit
- the user explicitly chose to reopen this deferred line as its own slice

### Scope

- audit the real dependency closure of the dirty-tree `kernel / model-runtime` work
- decide the minimum honest slice boundary
- write the active plan for landing or reducing that mixed bundle

### Acceptance

- the mixed boundary is explicitly restated as a new post-`P38` slice
- the minimum dependency bundle is named in concrete files and behaviors
- the next implementation order is clear enough to start landing the slice honestly

### Status

- completed

### Implementation Notes

- first-pass diff audit already confirms that the current line is a true mixed bundle, not a pure `kernel` adoption:
  - `src/mini_agent/agent_core/kernel.py`
  - `src/mini_agent/model_manager/runtime.py`
  - `src/mini_agent/model_manager/failover.py`
  - `src/mini_agent/model_manager/bootstrap.py`
  - `src/mini_agent/llm/protocol_binding.py`
  - `tests/test_agent_core_kernel.py`
- current audit focus:
  - config/config_loader injection
  - runtime config migration to `runtime.retry / request_policy / rectifier`
  - route-intent and route-requirement propagation
  - bootstrap-provider fallback truth
  - request-policy / rectifier binding
  - protocol execution profile + streaming failover
  - richer route diagnostics and capability truth
- formal plan added:
  - `docs/P39_KERNEL_MODEL_RUNTIME_BOUNDARY_PLAN_2026-04-16.md`
- focused validation already confirms that the current dirty-tree line is technically coherent enough to continue from:
  - upstream substrate suite:
    - `91 passed`
  - downstream kernel-consumer suite:
    - `118 passed`
- landed commits:
  - `771fc6f` `p39: land runtime protocol substrate`
  - `8e9a37d` `p39: close kernel consumer boundary`
- current `P39.1` working set is now narrowed to the upstream substrate files only:
  - `src/mini_agent/llm/__init__.py`
  - `src/mini_agent/model_manager/__init__.py`
  - `src/mini_agent/config.py`
  - `src/mini_agent/config/config-example.yaml`
  - `src/mini_agent/model_manager/bootstrap.py`
  - `src/mini_agent/model_manager/provider.py`
  - `src/mini_agent/model_manager/preset_providers.py`
  - `src/mini_agent/model_manager/model_discovery.py`
  - `src/mini_agent/model_manager/model_registry_service.py`
  - `src/mini_agent/model_manager/runtime.py`
  - `src/mini_agent/model_manager/failover.py`
  - `src/mini_agent/llm/protocol_binding.py`
  - `src/mini_agent/llm/base.py`
  - `src/mini_agent/llm/llm_wrapper.py`
  - `src/mini_agent/llm/openai_client.py`
  - `src/mini_agent/llm/anthropic_client.py`
- current `P39.1` test set is also narrowed and does not require `kernel.py` yet:
  - routing / failover / config / registry / protocol / streaming / CLI models tests
- additional adjacent validation is also green:
  - `tests/test_config_local_env.py tests/test_llm.py tests/test_llm_clients.py`
  - result: `14 passed, 9 skipped`
- current `P39.1` status:
  - implementation slice is coherent and ready to be cut as the first post-`P38` mixed-boundary commit
  - `P39.1` should now be treated as materially complete once this commit lands

### Next Likely Seam

- open a new post-`P39` anti-chaos slice rather than extending `P39` by inertia
- current recommended follow-up:
  - establish dirty-tree classification + guardrail tooling first

## Latest Sync: 2026-04-16 P38 Round-1 Narrow Commit Finalization

## Current Execution Slice: P38 Round-1 Narrow Commit Finalization (2026-04-16)

### Why This Slice Is Next

- the round-1 closure report is already complete
- the maintained active baseline is already restored and re-verified
- leaving the round-1 slice uncommitted would keep closure state ambiguous inside the larger dirty tree
- the safest next move is therefore the explicit narrow `P38` commit, not automatic widening into round-2 work

### Scope

- commit only the round-1 closure slice
- keep mixed `P33b / P34 / P36 / P37` dirty-tree work out of this boundary
- preserve the restored active baseline as one honest checkpoint

### Acceptance

- the round-1 closure files are committed as one narrow slice
- the commit boundary excludes mixed `kernel / model-runtime` and wider repo-hygiene work
- the next work can reopen from an explicit new line instead of an implicit carry-over backlog

### Status

- completed

### Implementation Notes

- re-verified before finalizing the slice:
  - `uv run pytest -q`
  - result: `1161 passed, 15 skipped`
  - maintained active-path `ruff` perimeter: `All checks passed!`
- locked round-1 commit contents to:
  - `tests/test_cli_tui_command.py`
  - `findings.md`
  - `progress.md`
  - `task_plan.md`
  - `docs/P38_FIRST_CLOSURE_PLAN_2026-04-16.md`
  - `docs/P38_FIRST_CLOSURE_ROUND1_REPORT_2026-04-16.md`
  - `docs/PROJECT_COMPLETENESS_EVALUATION_2026-04-16.md`

### Next Likely Seam

- choose the next explicit line after the round-1 checkpoint:
  - wider round-2 closure
  - honest mixed `kernel / model-runtime` slice
  - or a targeted product-polish line such as `DesktopUI`

## Latest Sync: 2026-04-16 P38 Round-1 Closure Report

## Current Execution Slice: P38 Round-1 Closure Report (2026-04-16)

### Why This Slice Is Next

- the project-level evaluation showed that the architecture is mostly landed
- the current repo problem is now closure quality rather than missing structure
- the user requested the first concrete closure plan before execution
- the current baseline still has:
  - one full-suite failure
  - active entrance contract drift
  - red lint baseline
  - mixed dirty-tree slice risk

### Scope

- finalize the round-1 closure result
- decide whether to stop at the restored narrow baseline or widen the perimeter
- record the closure outcome and deferred backlog explicitly

### Acceptance

- a formal round-1 closeout report exists
- the closure stopping point is explicit
- deferred work is named instead of silently folding back into the same slice

### Status

- completed

### Implementation Notes

- formal plan added:
  - `docs/P38_FIRST_CLOSURE_PLAN_2026-04-16.md`
- `P38.1` result:
  - updated `tests/test_cli_tui_command.py` for the current `run_tui(...)` contract
  - targeted regression: `155 passed`
  - full suite: `1161 passed, 15 skipped`
- `P38.2` result:
  - the maintained active-path perimeter `ruff` command is already green
  - current repo-wide lint debt is therefore mostly outside the round-1 active baseline
- `P38.4` result:
  - round 1 is now explicitly closed at the narrow restored baseline
  - closeout report added:
    - `docs/P38_FIRST_CLOSURE_ROUND1_REPORT_2026-04-16.md`
  - wider repo hygiene and mixed `kernel / model-runtime` work remain deferred on purpose

### Next Likely Seam

- choose the next explicit post-round-1 path:
  - commit the narrow `P38` closure slice
  - or reopen a wider closure/mixed-boundary line deliberately rather than by drift

## Latest Sync: 2026-04-16 Overall Project Completeness Evaluation

## Current Execution Slice: Overall Project Completeness Evaluation (2026-04-16)

### Why This Slice Is Next

- the user requested a whole-project judgment rather than another local refactor decision
- phase docs now claim multiple major lines are materially complete
- before reopening more development, the repo needed one explicit answer to:
  - what is already implemented
  - what is still only partially complete
  - how far the current codebase is from a truly closed baseline

### Scope

- compare expected product/architecture shape against the current codebase
- inspect:
  - active architecture docs
  - current entrance and subsystem implementation
  - project-wide automated validation state
- produce one explicit evaluation covering:
  - overall completion
  - maturity by subsystem
  - expected-vs-actual gaps

### Acceptance

- a formal whole-project evaluation report exists
- current maturity is grounded in code and validation, not just phase-doc claims
- the next work can be prioritized from real remaining gaps rather than intuition

### Status

- completed

### Implementation Notes

- evaluation report added:
  - `docs/PROJECT_COMPLETENESS_EVALUATION_2026-04-16.md`
- key full-worktree validation result:
  - `uv run pytest -q` -> `1160 passed, 15 skipped, 1 failed`
  - `uv run ruff check src tests` -> `57` findings
- main conclusion:
  - architecture is mostly landed
  - product baseline is usable
  - release/polish closure is not yet complete

### Next Likely Seam

- prioritize closure work over new large architecture lines:
  - fix the remaining contract drift surfaced by the failing suite
  - reduce repo hygiene and lint debt
  - close mixed `kernel / model-runtime` boundary work honestly
  - improve `DesktopUI / Remote` parity only after core closure stays stable

## Latest Sync: 2026-04-16 Strict Kernel Boundary Evaluation

## Current Execution Slice: Strict Kernel Boundary Evaluation (2026-04-16)

### Why This Slice Is Next

- `P34.1` and `P34.2` are already landed
- the next tempting move in the dirty tree is direct `kernel` adoption of the new `agent_core`
- that move looked superficially like the next `P34` step, but the dependency closure needed a stricter audit before any commit choice
- the main risk is a phase-fake commit:
  - labeling a mixed `kernel + runtime-governance + protocol-binding` bundle as core-only refactor work

### Scope

- inspect the current `kernel` diff and its real dependency closure
- classify the implicated files into:
  - pure `P34`
  - `P33b` runtime/provider-governance
  - mixed / not cheaply separable
- decide whether the current `kernel` is:
  - cuttable now
  - reducible to a phase-pure subset
  - or should be deferred until a combined bundle is ready

### Acceptance

- the current `kernel` adoption status is explicitly classified
- the minimum honest dependency bundle is understood
- the next implementation move can be chosen without hiding provider/bootstrap/protocol work under a misleading `P34` label

### Status

- completed

### Implementation Notes

- inspected current `kernel` and closure:
  - `src/mini_agent/agent_core/kernel.py`
  - `src/mini_agent/model_manager/runtime.py`
  - `src/mini_agent/model_manager/failover.py`
  - `src/mini_agent/model_manager/bootstrap.py`
  - `src/mini_agent/llm/protocol_binding.py`
  - `src/mini_agent/runtime/tooling.py`
  - `src/mini_agent/runtime/turn_context_provider_builder.py`
- strict conclusion:
  - current `kernel` is not phase-honest as a pure `P34` slice
  - it now embeds `P33b` route-intent, bootstrap-provider, capability-truth, request-policy, and rectifier/runtime-governance behavior
  - the minimum honest adoption is therefore a combined `P34 + P33b` bundle
  - a pure `P34` next step would require reducing the kernel diff first

### Next Likely Seam

- decide between:
  - combined `P34 + P33b` kernel adoption when the remaining runtime-governance slice is ready
  - or a reduced pure-`P34` kernel cut that keeps only typed binding / engine adoption without changing routing and failover semantics

## Latest Sync: 2026-04-16 P34.2 Turn-Scoped Policy Contract Hardening

## Current Execution Slice: P34.2 Turn-Scoped Policy Contract Hardening (2026-04-16)

### Why This Slice Is Next

- `P34.1` already landed the new `agent_core` package and compatibility shims
- the next honest `P34` cut had to stay inside core-runtime maintenance rather than reopen `P33b` model/provider work
- current dirty-tree `kernel` adoption is still entangled with provider bootstrap, protocol binding, and streaming/runtime-truth changes
- the cleaner next seam was therefore `P34.2`:
  - harden turn-scoped execution policy application inside the scheduler
  - stop mutating `execution_policy` shape as part of scheduler fallback behavior
  - keep turn budget overrides working without dragging `kernel` or provider surfaces into the same commit

### Scope

- tighten `src/mini_agent/agent_core/execution/scheduler.py`
- make the typed policy-override path explicit through `override_execution_policy(...)`
- remove the legacy scheduler behavior that rewrote `agent.execution_policy`
- update focused scheduler/loop tests to validate:
  - typed policy shape is preserved for override-capable agents
  - fallback agents still receive temporary `max_steps / max_tool_calls_per_step` overrides

### Acceptance

- `TurnScheduler` no longer rewrites `agent.execution_policy` into a plain dict
- turn-scoped max-step and max-tool-call overrides still work
- focused scheduler/policy regression tests pass
- the slice lands as one narrow `P34` commit without bundling `kernel`, provider, or session-surface changes

### Status

- completed

### Implementation Notes

- landed commit slice:
  - `972bbf6`
  - `p34: harden typed turn policy override path`
- core change:
  - `src/mini_agent/agent_core/execution/scheduler.py`
  - added an explicit `TurnPolicyOverridable` contract
  - fallback scheduler policy application now only touches `max_steps` and `max_tool_calls_per_step`
  - scheduler no longer mutates `execution_policy` on agents that do not own a typed override contract
- focused test updates:
  - `tests/test_agent_core_execution_loop.py`
  - override-capable observed agents now keep `AgentExecutionPolicy` shape during one turn
  - fallback agents keep their legacy `execution_policy` object untouched while still honoring temporary run limits
- focused verification stayed green before commit:
  - `uv run pytest tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_policy.py -q`
  - result: `25 passed`
  - `git diff --cached --check`
  - result: clean

### Next Likely Seam

- `P34.2` is now materially complete
- the next honest `P34` seam is still likely one of:
  - a later `kernel` adoption cut once the required `P33b` provider/bootstrap pieces can be bundled honestly
  - another core-only cleanup that does not reopen provider/runtime-surface coupling

## Latest Sync: 2026-04-16 P34.1 Agent-Core Runtime Package Landing

## Current Execution Slice: P34.1 Agent-Core Runtime Package + Legacy Compatibility Shims (2026-04-16)

### Why This Slice Is Next

- `P32b` was materially complete, so the next honest cut had to come from a real feature/refactor bucket
- the biggest remaining coherent bucket was `P34 agent_core`
- the direct-import rewrite already living in the dirty tree was too coupled to `P33b / P36 / P37`
- the safer first `P34` landing was:
  - introduce the new `agent_core` runtime package as the real implementation
  - keep legacy `mini_agent.agent / turn_context / code_agent` entrypoints alive as compatibility shims
  - avoid dragging `kernel`, provider bootstrap, or session-surface migration into the same commit

### Scope

- land the new `agent_core` execution/context/history/runtime-binding implementation package
- add compatibility shims for:
  - `src/mini_agent/agent.py`
  - `src/mini_agent/turn_context.py`
  - key `src/mini_agent/code_agent/*` package surfaces
- add backward-compatible schema support so legacy buffered `LLMResponse` callers can still feed the new core
- land focused `agent_core` tests without reopening the broader `kernel / provider / session / TUI` migration lines

### Acceptance

- the repo contains a maintained `agent_core` runtime implementation instead of keeping the new core only in the dirty tree
- legacy import surfaces still resolve and point at the new core contracts where needed
- the new core can accept legacy buffered completion payload shapes
- focused `agent_core` execution/context/history/runtime-binding tests pass
- the slice lands as one narrow `P34` commit without bundling later runtime/session or TUI convergence work

### Status

- completed

### Implementation Notes

- landed commit slice:
  - `d48f3c0`
  - `p34: land agent_core runtime with compatibility shims`
- core implementation landed:
  - `src/mini_agent/agent_core/engine.py`
  - `src/mini_agent/agent_core/runtime_bindings.py`
  - `src/mini_agent/agent_core/presentation.py`
  - `src/mini_agent/agent_core/post_turn.py`
  - `src/mini_agent/agent_core/history/**`
  - `src/mini_agent/agent_core/context/**`
  - `src/mini_agent/agent_core/execution/**`
- compatibility bridge landed:
  - `src/mini_agent/agent.py`
  - `src/mini_agent/turn_context.py`
  - `src/mini_agent/code_agent/__init__.py`
  - `src/mini_agent/code_agent/context_compression.py`
  - `src/mini_agent/code_agent/permissions/__init__.py`
  - `src/mini_agent/code_agent/sandbox/__init__.py`
  - `src/mini_agent/code_agent/tools/__init__.py`
- schema/runtime compatibility landed:
  - `src/mini_agent/schema/schema.py`
  - `src/mini_agent/schema/__init__.py`
  - legacy `LLMResponse` now remains available on top of the new completion event model
- focused verification stayed green before commit:
  - `uv run pytest tests/test_agent_core_compatibility_shims.py tests/test_agent_core_runtime_bindings.py tests/test_agent_core_context_compaction.py tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_policy.py tests/test_agent_core_execution_permissions.py tests/test_agent_core_execution_tools.py tests/test_agent_core_execution_sandbox.py tests/test_agent_core_execution_mcp_client.py tests/test_agent_core_execution_minimal_workflow.py tests/test_agent_core_turn_context.py tests/test_agent_core_history_summarization.py tests/test_agent_core_presentation.py tests/test_agent_core_post_turn.py tests/test_agent_core_exports.py -q`
  - result: `105 passed`
  - `git diff --cached --check`
  - result: clean

### Next Likely Seam

- `P34.1` is now materially landed as the runtime-package introduction cut
- the next honest `P34` seam is likely one of:
  - direct `kernel` adoption of the new typed runtime-binding surface
  - replacing remaining legacy import sites once the dependent `P33b` bootstrap/runtime-truth pieces are explicitly bundled
  - a narrower `P34` command/context support cut if it can stay separate from `P36` session-service convergence

## Latest Sync: 2026-04-16 P32b Final Doc And History Boundary Closure

## Current Execution Slice: P32b Final Active-vs-Historical Doc Sync (2026-04-16)

### Why This Slice Is Next

- the dirty-tree classification after `2b3bae2` showed that residual `P32b` had become a minority slice
- the only honest remaining hygiene work was one last docs/history boundary closeout
- the main risk was no longer missing documentation updates
- it was accidentally bundling later `P33b / P34 / P36 / P37` structure stories into a hygiene commit

### Scope

- sync active architecture/contributor docs to the already-landed `QQ-only remote adapter + browser removed` reality
- add one explicit remote-interaction architecture lock doc for the `P32` result
- mark historical/session-boundary docs so old channel/browser references stay as evidence, not as live implementation guidance
- keep future-structure docs and garbled mixed docs out of the commit boundary

### Acceptance

- active docs no longer present browser `WebUI / OpenWebUI` as paused-but-active surfaces
- active docs describe `Remote Interaction` with `QQ` as the only current adapter path
- historical `P29 / P30 / P31` docs make their historical status explicit where old channel/browser references remain
- the slice lands as one narrow docs-only closeout commit

### Status

- completed

### Implementation Notes

- landed commit slice:
  - `d6343bc`
  - `docs: close p32b remote and browser boundary sync`
- updated active/current docs:
  - `docs/ARCHITECTURE.md`
  - `docs/FRAMEWORK_SKELETON.md`
  - `docs/CONTRIBUTING.md`
  - `docs/CONTRIBUTING_CN.md`
- updated historical-boundary docs:
  - `docs/P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md`
  - `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`
  - `docs/P30_SESSION_TRUTH_BOUNDARY_MAP_2026-04-13.md`
  - `docs/P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`
  - `docs/P31_DESKTOPUI_PYSIDE6_TASK_PLAN_2026-04-13.md`
- added explicit lock doc:
  - `docs/P32_REMOTE_INTERACTION_ARCHITECTURE_LOCK_2026-04-14.md`
- commit-boundary decision:
  - kept mixed future-structure docs and encoding-damaged historical docs out of this hygiene slice

### Next Likely Seam

- treat `P32b` as materially complete
- reopen the next commit from its real feature bucket rather than from repo-hygiene surface area
- highest remaining buckets are still:
  - `P34` agent-core physical realignment
  - `P36` runtime/session contract work
  - `P33b` model/provider governance
  - `P37` residual TUI surface work

## Latest Sync: 2026-04-16 Post-2b3bae2 Dirty Worktree Classification

## Current Execution Slice: P32b Remaining Dirty Tree Classification (2026-04-16)

### Why This Slice Is Next

- the second focused `P32b` closure slice is now committed as `2b3bae2`
- the repo is still heavily dirty outside that commit boundary
- the immediate risk is no longer missing one more quick cleanup
- it is accidentally mixing later `P33b / P34 / P36 / P37` feature work back into a hygiene commit

### Scope

- classify the remaining dirty worktree by likely phase ownership
- identify what can still honestly count as residual `P32b`
- define the safest next commit boundary after `2b3bae2`

### Acceptance

- the remaining dirty files are grouped into clear commit buckets
- residual `P32b` scope is narrower than the total dirty tree
- the next recommended slice can be chosen without reopening already-landed hygiene commits

### Status

- completed

### Implementation Notes

- coarse remaining-worktree bucket counts:
  - `p32b_hygiene_docs`: `14`
  - `p33b_model_provider`: `37`
  - `p34_agent_core`: `128`
  - `p36_runtime_session`: `109`
  - `p37_tui_surface`: `30`
  - `cross_cutting_misc`: `42`
- safe residual `P32b` candidates are now mostly:
  - active/historical doc-boundary sync
  - repo-metadata hygiene such as `.gitignore` only if it supports the hygiene story directly
- the large remaining code buckets should not be swept into another hygiene commit:
  - `agent_core` / `code_agent` collapse and transport realignment belong to `P34`
  - `llm` / `model_manager` / provider-governance work belongs to `P33b`
  - `runtime` / `memory` / session contract work belongs to `P36`
  - TUI command/projector/orchestration work belongs to `P37`

### Next Likely Seam

- if continuing `P32b`, cut one last narrow docs/history/repo-metadata slice only
- otherwise stop the hygiene line here and reopen the next commit from its real feature bucket rather than from the dirty-tree surface area

## Latest Sync: 2026-04-16 P32b Physical Structure Closure

## Current Execution Slice: P32b Gateway Host Alignment And Browser Surface Removal (2026-04-16)

### Why This Slice Is Next

- the first `P32b` docs/index hygiene slice already landed as `4064fe6`
- the next highest-value repo-hygiene drift was no longer in active docs
- it was in the physical tree still carrying an unmaintained browser `agent_studio` surface while the maintained host story had already moved to `agent_studio_gateway`
- the gateway host itself also still mixed composition, main-agent routes, and ops concerns too tightly in one file

### Scope

- remove the obsolete browser `src/apps/agent_studio/` tree
- realign `src/apps/agent_studio_gateway/` so `main.py` is the maintained host/composition root
- split gateway route/auth ownership into maintained support files
- update the directly affected app/session/novel owners plus active walkthrough/test harnesses that still reflected older signatures
- keep this slice separate from unrelated later feature lines already present elsewhere in the dirty worktree

### Acceptance

- the repo no longer presents the removed browser studio as a maintained active surface
- gateway host bootstrapping and route ownership are separated into maintained files under `agent_studio_gateway`
- active walkthroughs and focused tests pass against the current service/runtime contracts
- the slice lands as one narrow `P32b` physical-structure closure commit

### Status

- completed

### Implementation Notes

- landed commit slice:
  - `2b3bae2`
  - `p32b: align gateway host with browser surface removal`
- structural closeout:
  - deleted `src/apps/agent_studio/**`
  - added `composition.py`, `main_agent_router.py`, `ops_auth.py`, and `ops_router.py`
  - reduced `agent_studio_gateway/main.py` to the maintained transport/composition entry
- active harness alignment:
  - walkthrough and readiness scripts now target `MainAgentSurfaceService` + `SessionApplicationService`
  - current `ChannelIngressUseCases` constructor expectations were aligned
  - TUI walkthroughs now tolerate the current app signature variants and use `DummyOutput()` safely on Windows
- focused verification stayed green before commit:
  - `uv run pytest tests/test_agent_studio_gateway_api_v1.py tests/test_agent_studio_gateway_ops_router.py tests/test_agent_studio_gateway_ops_auth.py tests/test_agent_studio_gateway_integration_flows.py tests/test_channel_novel_action_handler.py tests/test_operations_memory_use_cases.py tests/test_operations_provider_use_cases.py tests/test_config_bootstrap.py tests/test_main_agent_runtime_policy_loader.py tests/test_main_agent_surface_service.py tests/test_novel_service_use_cases.py tests/test_p19_runtime_matrix.py tests/test_channel_ingress_use_cases.py tests/test_session_feedback_service.py tests/test_session_recovery_feedback_service.py tests/test_session_package_exports.py tests/test_channel_ingress_gateway_walkthrough.py tests/test_shared_session_gateway_walkthrough.py tests/test_terminal_readiness_gate.py tests/test_tui_readiness_walkthroughs.py -q`
  - result: `163 passed`
  - `git diff --cached --check`
  - result: clean

### Next Likely Seam

- classify the remaining dirty worktree into:
  - residual active-doc / historical-boundary `P32b` cleanup
  - later feature-oriented lines already living outside this commit boundary
- do not reopen the just-landed gateway/browser hygiene slice by bundling unrelated `P33b-P37` work into one catch-all commit

## Latest Sync: 2026-04-16 P32b Repo Hygiene And Structure Alignment

## Current Execution Slice: P32b Active Doc/Index Sync + Commit Slicing (2026-04-16)

### Why This Slice Is Next

- `P37` is now materially complete
- the repo already carries large physical-structure churn from `P32` through `P37`
- active guidance docs still point to earlier anchors such as `P30` and stale active status such as `P33`
- current code no longer shows active old-path references, which means the highest-value next work is repo hygiene rather than another feature extraction

### Scope

- create one explicit `P32b` repo-hygiene plan
- sync active indexes, README, and guides to the current execution reality
- keep historical phase logs traceable without mass-rewriting them into fake current docs
- define commit slices for the still-dirty worktree

### Acceptance

- active docs no longer teach `P30` or `P33` as the current execution anchor
- maintained docs stop pointing to deleted current module/test names
- the repo has an explicit `P32b` hygiene and commit-slicing anchor
- focused link/doc validation remains green after the sync

### Status

- completed

### Implementation Notes

- audit baseline:
  - no active source/test/script refs remain for `main_agent_gateway_use_cases`, `session_remote_service`, `tui.gateway_client`, or `mini_agent.code_agent`
  - remaining drift is concentrated in doc/index surfaces and current guidance docs
- planned first closeout slice:
  - `README*`
  - `DEVELOPMENT_INDEX`
  - `DOCS_INDEX`
  - `DEVELOPMENT_GUIDE*`
  - `REFACTOR_TASKS`
  - `MINIAGENT_DEV_HABIT_LEDGER`
  - `P32b` plan + planning files
- first landed commit slice:
  - `4064fe6`
  - `docs: sync p32b repo hygiene execution anchors`
- second landed commit slice:
  - `2b3bae2`
  - `p32b: align gateway host with browser surface removal`
- third landed commit slice:
  - `d6343bc`
  - `docs: close p32b remote and browser boundary sync`

## Latest Sync: 2026-04-16 Post-P37 TUI Surface Evaluation

## Current Execution Slice: Post-P37 Evaluation (2026-04-16)

### Why This Slice Is Next

- `P37.1` and `P37.2` are complete
- `P37.3` has now extracted the main heavy TUI operator-command families:
  - approval
  - runtime policy
  - context
  - memory
  - KB
  - MCP
  - skill
  - model
- before forcing another tail cleanup, the right next step is to evaluate whether the remaining TUI weight still belongs to the same `P37` problem statement

### Scope

- inspect the remaining post-`P37.3` TUI command/surface tails
- separate true remaining `P37` hotspots from harmless residual surface glue
- end with one clear recommendation:
  - continue `P37`
  - or treat `P37` as materially complete

### Acceptance

- the repo has an explicit post-`P37` assessment grounded in current code
- the next step is chosen from current reality instead of continuing extraction inertia

### Status

- completed

### Implementation Notes

- post-`P37` evaluation report landed in:
  - `docs/POST_P37_TUI_SURFACE_EVALUATION_2026-04-16.md`
- main conclusion:
  - `P37` should now be treated as materially complete
  - the remaining larger TUI tail is mostly `session` lifecycle/surface orchestration, not another clean `P37.3` command-family seam
  - `sandbox` is already too small to justify another extraction

### Next Likely Seam

- do not continue `P37.3` by default
- if another TUI architecture line is needed, scope it from a fresh problem statement such as:
  - session-surface lifecycle/mutation orchestration
  - prompt/recovery/resume surface flow cleanup
  - broader TUI composition-root slimming

## Latest Sync: 2026-04-16 P37.3 Model Command Coordinator

## Current Execution Slice: P37.3 TUI Operator Command Orchestration Split (2026-04-16)

### Why This Slice Is Next

- `P37.2` is now materially complete:
  - shared local/remote turn state transitions were extracted
  - shared local/remote turn outcome semantics were extracted
  - remote stream/event consumption was extracted
- the next remaining structural pressure in `tui/app.py` is no longer turn execution
- it is operator-command orchestration, especially where local runtime flow and remote gateway flow still mix inside the same command handlers
- the safest kickoff cut is approval command orchestration because:
  - the local and remote command paths already share real semantics
  - the branch is cohesive and testable
  - it does not require moving the whole command dispatcher in one step

### Scope

- continue extracting narrow maintained TUI command coordinators
- move mixed local-vs-remote operator-command orchestration out of `tui/app.py`
- preserve current:
  - command text
  - feedback wording
  - local/gateway routing behavior
  - existing runtime/session helper ownership

### Acceptance

- extracted command families no longer live as one mixed local-vs-remote branch inside `tui/app.py`
- focused unit coverage exists for each extracted command owner
- existing `tests/test_tui_app.py` command paths remain green after each narrow cut

### Status

- in_progress

### Implementation Notes

- `P37.3` kickoff cut landed as:
  - added `src/mini_agent/tui/session_approval_command_coordinator.py`
  - `MiniAgentTuiApp` now delegates local-vs-remote approval command orchestration through that maintained coordinator
  - modal rendering and remote stream approval event handling remain in `tui/app.py`
  - added focused unit coverage in `tests/test_tui_approval_command_coordinator.py`
- `P37.3` second cut landed as:
  - added `src/mini_agent/tui/session_runtime_policy_command_coordinator.py`
  - `MiniAgentTuiApp` now delegates local-vs-remote runtime-policy command orchestration through that maintained coordinator
  - runtime-policy apply helpers remain in `tui/app.py`
  - added focused unit coverage in `tests/test_tui_runtime_policy_command_coordinator.py`
- `P37.3` third cut landed as:
  - added `src/mini_agent/tui/session_context_command_coordinator.py`
  - `MiniAgentTuiApp` now delegates context command orchestration through that maintained coordinator
  - context planner, local command execution, and remote update helpers remain in `tui/app.py`
  - added focused unit coverage in `tests/test_tui_context_command_coordinator.py`
- `P37.3` fourth cut landed as:
  - added `src/mini_agent/tui/session_memory_command_coordinator.py`
  - `MiniAgentTuiApp` now delegates memory command orchestration through that maintained coordinator
  - memory command planning and execution helpers remain in `tui/app.py`
  - added focused unit coverage in `tests/test_tui_memory_command_coordinator.py`
- `P37.3` fifth cut landed as:
  - added `src/mini_agent/tui/session_kb_command_coordinator.py`
  - `MiniAgentTuiApp` now delegates KB command orchestration through that maintained coordinator
  - remote KB execution helper and local KB toggle details remain in `tui/app.py`
  - added focused unit coverage in `tests/test_tui_kb_command_coordinator.py`
- `P37.3` sixth cut landed as:
  - added `src/mini_agent/tui/session_mcp_command_coordinator.py`
  - `MiniAgentTuiApp` now delegates MCP command orchestration through that maintained coordinator
  - remote control helper and local MCP reload runtime-rebuild details remain in `tui/app.py`
  - added focused unit coverage in `tests/test_tui_mcp_command_coordinator.py`
- `P37.3` seventh cut landed as:
  - added `src/mini_agent/tui/session_skill_command_coordinator.py`
  - `MiniAgentTuiApp` now delegates skill command orchestration through that maintained coordinator
  - remote skill request/response helpers and local skill-result application remain in `tui/app.py`
  - added focused unit coverage in `tests/test_tui_skill_command_coordinator.py`
- `P37.3` eighth cut landed as:
  - added `src/mini_agent/tui/session_model_command_coordinator.py`
  - `MiniAgentTuiApp` now delegates model command orchestration through that maintained coordinator
  - model-selection, discovery, filter, and limit helpers remain in `tui/app.py`
  - added focused unit coverage in `tests/test_tui_model_command_coordinator.py`

### Next Likely Seam

- continue `P37.3` with the next narrow command-family owner
- best remaining candidates:
  - command-dispatcher tail cleanup only if another real hotspot remains after model
  - otherwise a short post-`P37.3` evaluation to decide whether `P37` is materially complete
- keep the next cut narrow and behavior-preserving; do not reopen turn-flow ownership

## Latest Sync: 2026-04-16 P37.2 Remote Turn Stream Coordinator

## Current Execution Slice: P37.2 Local Vs Remote Turn Execution Split (2026-04-16)

### Why This Slice Is Next

- `P37.1` already removed one concentrated remote projection mutation block from `tui/app.py`
- the next remaining TUI hotspot is the parallel local/remote turn execution flow:
  - `_run_chat_turn(...)`
  - `_run_remote_chat_turn(...)`
- the safest first `P37.2` cut is not to rewrite both flows
- it is to extract the shared session/task state transitions they both still own inline

### Scope

- extract narrow maintained owners around local vs remote turn execution
- move shared state and outcome semantics out of `tui/app.py`
- move remote stream/event consumption out of the main remote turn method
- keep local live reply behavior and recovery semantics unchanged

### Acceptance

- local and remote turn execution no longer each own their shared busy/task/running-state transition block inline
- local and remote turn execution no longer each own their shared completion/failure classification inline
- remote stream/event consumption no longer lives as one large direct loop inside `_run_remote_chat_turn(...)`
- focused unit coverage exists for the extracted TUI turn owners
- `tests/test_tui_app.py` remains green after the extraction

### Status

- completed

### Implementation Notes

- `P37.2` first cut landed as:
  - added `src/mini_agent/tui/session_turn_state_coordinator.py`
  - `MiniAgentTuiApp` now delegates shared local/remote turn session-task state transitions through that maintained coordinator
  - added focused unit coverage in `tests/test_tui_turn_state_coordinator.py`
- `P37.2` second cut landed as:
  - added `src/mini_agent/tui/session_turn_outcome_coordinator.py`
  - `MiniAgentTuiApp` now delegates shared local/remote turn completion and failure classification through that maintained coordinator
  - success-path stream finalization remains in `tui/app.py`, so the extraction stays above outcome semantics and below stream mechanics
  - added focused unit coverage in `tests/test_tui_turn_outcome_coordinator.py`
- `P37.2` third cut landed as:
  - added `src/mini_agent/tui/session_remote_turn_stream_coordinator.py`
  - `MiniAgentTuiApp` now delegates remote stream consumption and event dispatch through that maintained coordinator
  - final reply flush/sync and outcome application remain in `tui/app.py`, so the extraction stays below turn orchestration and above raw gateway iteration
  - added focused unit coverage in `tests/test_tui_remote_turn_stream_coordinator.py`

### Next Likely Seam

- `P37.2` is now materially complete
- the next architecture slice should move to `P37.3` operator-command orchestration split
- likely first `P37.3` targets:
  - approval command orchestration
  - runtime-policy and context command flow
  - remote/local command success/error normalization still mixed into `tui/app.py`

## Latest Sync: 2026-04-15 P37.1 Remote Session Projection Service Kickoff

## Current Execution Slice: P37.1 Remote Session Projection Service (2026-04-15)

### Why This Slice Is Next

- post-`P36` evaluation showed the next main structural pressure is in `tui/app.py`, not in runtime/session support seams
- one especially concentrated hotspot is remote session sync:
  - remote summary/detail payloads are still applied directly inside the main TUI app class
  - transport-payload-to-projection mapping still shares ownership with UI orchestration
- the safest first `P37` cut is therefore narrow:
  - extract a maintained remote session projector
  - keep current behavior
  - add focused unit coverage for the extracted owner

### Scope

- start `P37` by extracting remote `summary/detail/messages` projection application from `tui/app.py`
- keep network calls and TUI session selection flow where they are for now
- avoid mixing this kickoff with local/remote turn execution surgery

### Acceptance

- remote session projection mapping has one maintained TUI-facing owner
- `tui/app.py` no longer directly owns the main remote `summary/detail/messages` mutation block
- focused regression coverage exists for the extracted projector

### Status

- completed

### Implementation Notes

- formal `P37` line is defined in:
  - `docs/P37_TUI_SURFACE_ORCHESTRATION_CONVERGENCE_PLAN_2026-04-15.md`
- `P37.1` kickoff landed as:
  - added `src/mini_agent/tui/session_remote_projector.py`
  - `MiniAgentTuiApp` now delegates remote session `summary/detail/messages` projection application through that maintained TUI projector
  - added focused projector unit coverage in `tests/test_tui_remote_projector.py`

### Next Likely Seam

- continue with `P37.2` local-vs-remote turn execution split
- keep the next cut narrow:
  - identify the shared lifecycle between `_run_chat_turn(...)` and `_run_remote_chat_turn(...)`
  - avoid mixing that work with command-family extraction in the same slice

## Latest Sync: 2026-04-15 Post-P36 Runtime/Surface Evaluation Kickoff

## Current Execution Slice: Post-P36 Evaluation (2026-04-15)

### Why This Slice Is Next

- `P36` is now materially complete:
  - common runtime/session reads sit behind maintained support seams
  - projection refresh/writeback paths are more consolidated
  - runtime-facing tests now share maintained contract carriers
- the next step should not be another blind cleanup slice
- it should be a fresh evaluation of current reality:
  - what structural pressure still exists after `P36`
  - whether the next work belongs in runtime/session behavior, surface/operator ergonomics, or some other line

### Scope

- audit the current post-`P36` runtime/session/surface shape from code, not only from the completed plan
- identify the remaining hotspots that still matter operationally or architecturally
- separate real maintained-contract debt from harmless local complexity
- end with a concrete recommendation:
  - no immediate follow-up
  - a narrow `P36x` / `P37` runtime-session line
  - or a different next milestone outside `P36`

### Acceptance

- the project has an explicit post-`P36` assessment grounded in current code paths
- any next milestone recommendation is driven by real remaining pressure, not refactor inertia

### Status

- completed

### Implementation Notes

- post-`P36` evaluation report landed in:
  - `docs/POST_P36_RUNTIME_SURFACE_EVALUATION_2026-04-15.md`
- main conclusion:
  - `P36` should be treated as complete
  - the next meaningful architectural pressure is concentrated in `src/mini_agent/tui/app.py`, not in the maintained runtime/session support seams
  - `MainAgentRuntimeManager` remains large but currently behaves more like a composition root than a hidden behavior hotspot

### Next Likely Seam

- if the next milestone is architecture-oriented, it should likely be a new TUI/surface orchestration line rather than a `P36` continuation
- likely next focus:
  - remote session projection syncing
  - local/remote turn execution convergence
  - TUI command/runtime interaction split

## Latest Sync: 2026-04-15 P36.3 Runtime Session Tail Fixture Adoption Extension

## Current Execution Slice: P36.3 Surface/Test Contract Cleanup (2026-04-15)

### Why This Slice Is Next

- `P36.1` is now landed:
  - common runtime-facing agent reads moved behind maintained payload/support seams
  - read-model, diagnostics, snapshot, persistence, and hydration consumers no longer repeat as much raw `getattr(...)` logic
  - the immediate codec binding regression has been fixed and the focused runtime/surface bundle is green
- `P36.2` is now materially cleaned up:
  - runtime/session and TUI refresh/writeback paths have been converged onto maintained runtime owners
  - the local prepared-context turn-result split path has been removed
- the next remaining friction is now primarily in tests:
  - `CLI / TUI / Surface` verification still carried separate ad hoc runtime-agent doubles
  - runtime-facing tests still pay repeated setup cost for the same contract shape
  - the maintained runtime/session contract should now have a matching maintained test carrier

### Scope

- continue `P36` by aligning runtime-facing tests around one maintained contract carrier
- prefer a small shared test double over scattered per-file wrappers
- start with the highest-frequency surface files:
  - `tests/test_cli_submission_loop.py`
  - `tests/test_tui_app.py`
  - `tests/test_main_agent_surface_service.py`
- keep the carrier narrow and contract-oriented; do not build a giant fake runtime framework

### Acceptance

- the main `CLI / TUI / Surface` verification line reuses one maintained runtime-facing test carrier
- tests need less ad hoc runtime-services / route / prepared-context / KB plumbing
- the next `P36.3` cuts can extend the same shared carrier or adjacent shared fixtures into runtime/session handler tests

### Status

- completed

### Implementation Notes

- the formal `P36` line is defined in:
  - `docs/P36_SESSION_RUNTIME_CONTRACT_CONSOLIDATION_PLAN_2026-04-15.md`
- `P36.1` completed:
  - `RuntimeSessionPayloadCodec` now owns live-agent read helpers for messages, tokens, prepared context, and memory/runtime-task payloads
  - `RuntimeSessionAgentSupport` is now the maintained runtime-facing read seam above those helpers
  - read-model, snapshot, diagnostics, persistence, hydrator, and runtime-manager consumers were migrated to that seam
- first `P36.2` cut now landed:
  - `session_agent_runtime_handler.py` rebuild flow refreshes projection diagnostics through `RuntimeSessionStateHydrator.refresh_session_diagnostics(...)`
  - `session_recovery_reset_handler.py` reset flow uses the same shared refresh entry
  - focused regression coverage now exists for rebuild-triggered and reset-triggered projection refresh behavior
- second `P36.2` cut now landed:
  - `RuntimeSessionStateHydrator` now owns `refresh_runtime_projection(...)` for synchronized live-runtime projection refresh
  - runtime-policy reconfigure and local agent-control flows now use that shared live refresh path instead of mutating projection fields piecemeal
- third `P36.2` cut now landed:
  - `RuntimeSessionOperatorHandler` now normalizes operator-side `context_policy` writeback through the maintained payload seam
  - detached runtime-policy fallback now normalizes and stores local sandbox diagnostics through the same maintained payload seam
- fourth `P36.2` cut now landed:
  - `RuntimeSessionModelIdentityCodec` now owns selected/pending identity reads and writes for projection-shaped objects, not only full runtime sessions
  - TUI local identity helpers and remote model-identity payload normalization now reuse that maintained codec instead of maintaining a parallel surface-local contract
- fifth `P36.2` cut now landed:
  - `src/mini_agent/tui/app.py` now owns a narrow local `refresh/capture` projection seam mirroring the runtime hydrator split
  - TUI local KB helpers and payload normalization now reuse the maintained runtime owners instead of parallel surface-local contracts
  - local context snapshot refresh, local context writeback, local KB toggles, and local runtime-policy reconfigure now converge on that shared local refresh path
- sixth `P36.2` cut now landed:
  - local scheduler/chat turn-result prepared-context writeback now flows through one maintained local helper instead of separate payload/diagnostics setters
  - local prepared-context feedback now reads the final synchronized projection instead of the raw completion payload
  - omission of prepared-context diagnostics from a local completion payload no longer drops the TUI projection if the live agent already has current diagnostics
- `P36.3` kickoff now landed:
  - added `tests/runtime_contract_fixtures.py` with one shared runtime-facing agent carrier
  - `tests/test_cli_submission_loop.py`, `tests/test_tui_app.py`, and `tests/test_main_agent_surface_service.py` now reuse that carrier in their main runtime-facing test paths
- `P36.3` second cut now landed:
  - `tests/runtime_contract_fixtures.py` now also owns shared session/runtime fixture helpers for policy, sandbox, projection, runtime, and session state carriers
  - runtime/session handler tests now reuse those shared carrier helpers instead of rebuilding the same `SimpleNamespace(...)` shapes inline
- `P36.3` third cut now landed:
  - `tests/runtime_contract_fixtures.py` now also owns narrow lineage/transcript carrier helpers for record/snapshot tests
  - snapshot/persistence/payload/diagnostics/control tests now reuse the maintained fixture line instead of rebuilding session/projection/runtime shells inline
- `P36.3` fourth cut now landed:
  - `tests/test_runtime_session_model_identity_codec.py` now reuses the shared runtime-facing agent/session/projection helpers
  - `tests/test_runtime_session_operator_handler.py` now reuses the maintained session/projection helpers instead of rebuilding its runtime-facing session shell inline
- `P36.3` fifth cut now landed:
  - `tests/test_runtime_session_admin_handler.py`, `tests/test_runtime_session_mcp_control_handler.py`, and `tests/test_runtime_session_pending_approval_state_handler.py` now reuse the maintained session/projection/runtime/transcript helpers
  - the extraction stayed narrow:
    - handler dependency stubs remain local to each test file
    - only repeated session/runtime carrier shells moved behind the shared fixture line
- `P36.3` sixth cut now landed:
  - `tests/test_runtime_session_recovery_reset_handler.py`, `tests/test_runtime_session_lifecycle_handler.py`, and `tests/test_runtime_session_hydration_coordinator.py` now also reuse the maintained session/transcript shell helpers where that contract shape is the real subject under test
  - the remaining inline `SimpleNamespace(...)` usage in `tests/test_runtime_session_*` is now mostly:
    - domain-local payload rows
    - handler dependency/service stubs
    - tiny one-off lifecycle/policy wrappers
- `P36.3` acceptance is now materially met:
  - the runtime-facing test line has one maintained fixture carrier for the repeated session/runtime contract shapes
  - further extraction would mostly chase local test payloads rather than real maintained runtime contracts

### Next Likely Seam

- `P36.3` no longer has meaningful shared-carrier debt
- the next step should be a fresh post-`P36` evaluation or a new scoped follow-up only if a concrete runtime/session contract problem appears

## Latest Sync: 2026-04-15 P34.8 Final Agent-Facade Slimming And Architecture Lock

## Current Execution Slice: Post-P34 Agent-Core Follow-up Evaluation (2026-04-15)

### Why This Slice Is Next

- `P34.8` is now complete:
  - obsolete engine wrappers have been removed
  - the `agent_core` seam contract is now documented explicitly
  - top-level seam exports are now part of the public reference surface
- `P34` as a whole is now complete:
  - runtime bindings hardened
  - turn-scoped policy hardened
  - tool execution extracted
  - history summarization extracted
  - presentation boundary extracted
  - turn-context hotspot decomposed
  - post-turn side effects extracted
  - final facade/doc lock landed
- the next step should not be more blind agent-core surgery
- it should be a fresh follow-up evaluation:
  - what real remaining pain points still exist in `agent_core`
  - whether the next line belongs to runtime behavior, operator ergonomics, or a new architecture slice outside `P34`

### Scope

- audit the now-completed `P34` result against real next development needs
- avoid reopening the completed `P34` slices without a new problem statement
- identify whether the next work belongs in:
  - runtime behavior
  - surface/operator experience
  - model/runtime/provider follow-up
  - or a new `agent_core` line with a fresh scoped plan

### Acceptance

- the next task starts from explicit current-state understanding instead of continuing refactor inertia
- any new architecture line is scoped from current reality, not from outdated pre-`P34` assumptions

### Status

- in_progress

### Implementation Notes

- `P34.8` landed as:
  - removed obsolete thin wrappers from `src/mini_agent/agent_core/engine.py`
  - added `docs/AGENT_CORE_RUNTIME_SEAMS.md`
  - updated `docs/ARCHITECTURE.md`
  - updated `docs/FRAMEWORK_SKELETON.md`
  - updated `src/mini_agent/agent_core/__init__.py`
- targeted verification for the `P34.8` slice:
  - `uv run ruff check src/mini_agent/agent_core/engine.py src/mini_agent/agent_core/post_turn.py src/mini_agent/agent_core/__init__.py tests/test_agent_core_history_summarization.py tests/test_agent_core_presentation.py tests/test_agent_core_exports.py docs/AGENT_CORE_RUNTIME_SEAMS.md`
  - `uv run pytest tests/test_agent_core_history_summarization.py tests/test_agent_core_presentation.py tests/test_agent_core_post_turn.py tests/test_agent_core_exports.py tests/test_agent_core_kernel.py tests/test_agent_core_execution_policy.py tests/test_agent_core_execution_tools.py tests/test_agent_core_execution_loop.py tests/test_agent_core_streaming.py tests/test_memory_automation.py -q`
  - result: `65 passed`

### Next Likely Seam

- the next seam should be chosen from a fresh post-`P34` evaluation, not by extending the completed refactor line mechanically

## Latest Sync: 2026-04-15 Follow-up Model Configuration And Supply Defect Patch

## Current Execution Slice: Follow-up Model Configuration And Supply Defect Patch (2026-04-15)

### Why This Slice Is Next

- `P33b.6` closed the main runtime/provider truth line
- but one follow-up audit still found three practical gaps in the model configuration / supply seam:
  - custom provider `headers` and `timeout` were configurable but not fully consumed at runtime
  - runtime preset supply still re-triggered preset discovery and could drop Ollama on transient probe failures
  - `mini-agent models` did not load `.env.local`, unlike the main config bootstrap path

### Scope

- finish runtime propagation for custom provider transport knobs:
  - `headers`
  - `timeout`
- separate runtime preset supply from live inventory discovery
- keep enabled Ollama runtime supply stable from persisted state without requiring a fresh successful probe
- make CLI preset/model inspection load `.env.local` before env-based preset resolution
- add focused regression coverage only for these follow-up defects

### Acceptance

- routed runtime clients receive configured custom headers and timeout
- runtime preset catalog no longer performs fresh discovery while building executable supply
- enabled Ollama with persisted state remains runnable during transient probe failures
- `mini-agent models --list-presets` sees keys from `.env.local`

### Status

- completed

### Implementation Notes

- transport binding now carries route headers + timeout into protocol execution profiles and SDK client construction
- runtime preset catalog now rebuilds executable preset supply from:
  - current env-resolved preset connection info
  - persisted preset model state
  instead of depending on a fresh discovery pass
- Ollama runtime fallback is intentionally narrow:
  - only enabled local preset
  - only when persisted runtime state already exists
- CLI model inspection now loads `.env.local` through the same bootstrap helper used by config loading

### Next Likely Seam

- current model configuration / supply seam is now at a usable level for:
  - preset providers
  - custom OpenAI-compatible providers
  - custom Anthropic-compatible providers
- the next work should be a fresh evaluation, not more blind patching:
  - whether provider governance needs a `P33c`
  - whether remaining work is now operator ergonomics rather than core runtime correctness

## Latest Sync: 2026-04-15 P33b.6 Route Observability And Diagnostics

## Current Execution Slice: P33b.6 Route Observability And Diagnostics (2026-04-15)

### Why This Slice Is Next

- `P33b.5` already corrected the runtime/provider contract story
- but one operator-facing gap still remained:
  - agent-routing diagnostics existed
  - model/provider routing truth did not
  - bootstrap and candidate-selection reasoning still disappeared before operators could inspect it
- the next safe correction therefore needed to stay narrow:
  - do not redesign logging
  - do not reinterpret existing agent-routing counters
  - only make the latest model-route decision chain inspectable end to end

### Scope

- add one lightweight model-route diagnostics recorder in `runtime.py`
- record latest routed or pinned model-route attempt, including explicit-route failures
- preserve the existing `/api/v1/ops/diagnostics/routing` agent-routing counters while extending the contract with parallel model-route state
- propagate bootstrap selection diagnostics from `Config -> LLMConfig -> BootstrapLLMSettings -> runtime`
- enrich kernel route diagnostics with:
  - route intent
  - selection reason
  - fallback reason
  - candidate chain summary
- add focused regression coverage across:
  - runtime
  - kernel
  - surface service
  - ops router
  - config bootstrap

### Acceptance

- `/api/v1/ops/diagnostics/routing` still reports the existing agent-routing stats unchanged
- operators can also inspect latest model/provider route truth from the same diagnostics surface
- runtime records candidate-chain and failure snapshots for routed and pinned resolution paths
- kernel diagnostics can explain why the active model route won and whether bootstrap policy influenced it
- bootstrap selection reason/policy survive into runtime diagnostics instead of being dropped during config bootstrap

### Status

- completed

### Implementation Notes

- runtime now maintains a lightweight model-route snapshot + resolution counter
- snapshots capture:
  - resolution kind
  - catalog source/path
  - route intent
  - requested identity
  - selected provider/model
  - mapping mode
  - candidate list
  - breaker gating
  - capability truth/confidence/source
  - bootstrap selection diagnostics
  - failure text for rejected routes
- `MainAgentRoutingDiagnostics` now carries:
  - existing agent-routing counters
  - `model_route_resolutions`
  - `latest_model_route`
- kernel route diagnostics now merge the richer runtime snapshot so active route inspection is not limited to the selected model id alone

### Next Likely Seam

- `P33b` planned runtime/provider truth slices are now functionally complete
- the next follow-up should start from higher-level evaluation:
  - whether a `P33c` line is needed
  - whether provider-governance work should move to rollout/ops ergonomics instead of core runtime truth

## Latest Sync: 2026-04-15 P33b.5 Provider Contract Tightening

## Current Execution Slice: P33b.5 Provider Contract Tightening (2026-04-15)

### Why This Slice Is Next

- `P33b.4` already made bootstrap choice explicit
- but one contract mismatch still remained across provider config and operations surfaces:
  - custom provider `source` was real
  - custom provider `api_type` was not
  - runtime only maintains `openai` and `anthropic` execution families
- that meant some write/setup surfaces still suggested a broader provider protocol story than the runtime actually honors

### Scope

- tighten custom-provider protocol-family contract to the maintained runtime families only:
  - `openai`
  - `anthropic`
- stop public ops/setup request DTOs from accepting removed fake protocol families such as `custom`
- preserve compatibility for existing local catalogs by normalizing legacy `api_type: custom` to `openai`
- remove the last route-selector default that still treated `custom` like a maintained runtime family

### Acceptance

- public provider setup/update surfaces no longer advertise or accept fake runtime protocol families
- legacy stored custom-provider catalogs with `api_type: custom` still load as OpenAI-compatible instead of breaking
- runtime/provider/ops layers tell the same story:
  - provider source may be `custom` or `preset`
  - provider protocol family is maintained as `openai` or `anthropic`

### Status

- completed

### Implementation Notes

- removed `ProviderAPIType.CUSTOM` from the maintained runtime-family enum
- added canonical provider-api-type normalization with:
  - public-surface rejection for removed `custom`
  - legacy catalog compatibility mapping from `custom` -> `openai`
- tightened ops request DTO validation for:
  - provider upsert
  - provider setup model discovery
- narrowed discovery/setup protocol mapping to maintained families only
- removed the last route-selector default that still listed `custom` as a supported runtime family

### Next Likely Seam

- `P33b.6 Route Observability And Diagnostics`
- the remaining governance gap is explanation quality:
  - route and bootstrap decisions are now more honest
  - but operators still cannot inspect enough of the candidate/ranking/fallback story from one surface

## Latest Sync: 2026-04-15 P33b.4 Bootstrap Provider Governance

## Current Execution Slice: P33b.4 Bootstrap Provider Governance (2026-04-15)

### Why This Slice Is Next

- `P33b.3` already fixed discovery integrity, but startup preset selection was still governed by hidden enumeration order:
  - `detect_preset_providers()` collected configured presets in provider-dict order
  - `get_first_available_preset()` still took the first detected candidate
- that meant multi-key bootstrap remained deterministic only by accident, not by explicit policy
- the next correction needed to make startup selection:
  - explicit
  - inspectable
  - preference-aware
  - safe around enabled local providers such as Ollama

### Scope

- add one bootstrap preset-selection policy seam in `preset_providers.py`
- support explicit bootstrap preference via env/configurable selection input
- replace enumeration-order choice with stable bootstrap-priority ordering
- preserve the existing cloud-first / Ollama-opt-in default behavior, but make it policy-driven rather than positional
- expose bootstrap diagnostics for:
  - selected provider
  - why it won
  - what alternatives were present

### Acceptance

- multi-key startup no longer depends on provider dictionary order
- explicit bootstrap preference wins when available
- Ollama remains opt-in and does not silently take over when cloud presets are also configured
- bootstrap selection diagnostics are available to callers instead of being implicit inside config bootstrap

### Status

- completed

### Implementation Notes

- added a dedicated bootstrap selection result type and candidate policy seam
- bootstrap ordering now uses:
  - explicit preferred provider
  - explicit bootstrap priority
  - stable provider-id tie-break
- selected preset payload now carries bootstrap diagnostics fields for future surfaces/logging

### Next Likely Seam

- `P33b.5 Provider Contract Tightening`
- the next governance gap is still contract honesty:
  - config/ops/runtime protocol stories remain broader and looser than the actually maintained runtime execution families

## Latest Sync: 2026-04-15 P33b.3 Discovery Integrity And Cache Scope

## Current Execution Slice: P33b.3 Discovery Integrity And Cache Scope (2026-04-15)

### Why This Slice Is Next

- `P33b.2` already corrected capability truth, but discovery ownership was still unsafe in two concrete places:
  - discovery cache scope was too coarse and could mix different endpoints under one provider-type cache entry
  - custom discovery could still overwrite configured inventory with a smaller discovered list
- those risks sit directly underneath runtime/provider truth:
  - stale or cross-endpoint cache results can misrepresent actual available inventory
  - destructive discovery writeback can erase intentional operator-configured models

### Scope

- make discovery cache endpoint-aware instead of provider-type-only
- normalize cache scope around provider type, effective base URL, and protocol flavor
- change custom-provider discovery writeback from destructive replacement to non-destructive merge
- keep current recommendation/default behavior, but stop accidental model-list shrinkage

### Acceptance

- discovery results from different compatible endpoints no longer share one cache entry by accident
- custom discovery no longer removes configured models just because one refresh returns fewer models
- newly discovered models can still enrich the provider inventory without losing existing configured metadata
- focused discovery/registry/runtime regressions remain green

### Status

- completed

### Implementation Notes

- `ModelDiscoveryCache` now scopes cache files by:
  - provider type
  - normalized base URL
  - protocol flavor
- custom discovery now merges:
  - existing configured models
  - newly discovered models
  - existing metadata/limits
  - discovered metadata/context updates
- configured inventory remains preserved even when discovery returns a partial subset

### Next Likely Seam

- `P33b.4 Bootstrap Provider Governance`
- the next runtime-governance gap is still bootstrap determinism:
  - preset provider choice remains too order-driven instead of policy-driven and inspectable

## Latest Sync: 2026-04-15 P33b.2 Capability Truth Grading

## Current Execution Slice: P33b.2 Capability Truth Grading (2026-04-15)

### Why This Slice Is Next

- `P33b.1` already separated exact route intent from automatic fallback
- the next unsafe runtime contract was capability optimism:
  - discovery without capability evidence still wrote most provider models as if tools/thinking support were confirmed
  - routing then treated those guessed-true flags like real truth
- before discovery-integrity or bootstrap-governance work continues, runtime capability truth needs to become honest:
  - explicit support
  - explicit non-support
  - unknown without guessed confirmation

### Scope

- stop defaulting discovered models to implicit tool/thinking support without evidence
- persist graded capability truth and confidence into model metadata
- update routed ranking so:
  - known unsupported remains filtered when capability is required
  - confirmed support outranks unknown
  - unknown outranks known unsupported on preference-only paths
- expose chosen-route capability truth through kernel diagnostics

### Acceptance

- runtime no longer treats missing capability evidence as confirmed support
- discovery metadata preserves capability truth/confidence instead of only guessed booleans
- route selection prefers confirmed support over unknown when tools are required
- chosen route diagnostics can show whether capability support was confirmed or unknown

### Status

- completed

### Implementation Notes

- capability discovery now emits:
  - `supports_tools`
  - `supports_tools_truth`
  - `supports_tools_confidence`
  - `supports_tools_source`
  - `supports_thinking`
  - `supports_thinking_truth`
  - `supports_thinking_confidence`
  - `supports_thinking_source`
- missing evidence now stays `unknown` instead of collapsing to `true`
- route scoring now distinguishes:
  - confirmed required tool support
  - unknown required tool support
  - supported vs unknown vs unsupported thinking preference

### Next Likely Seam

- `P33b.3 Discovery Integrity And Cache Scope`
- the next runtime-truth problem is discovery ownership and cache identity:
  - discovery results are still too coarse per endpoint/profile
  - custom discovery can still overwrite configured inventory too aggressively

## Latest Sync: 2026-04-15 P33b.1 Route Intent Hardening

## Current Execution Slice: P33b.1 Route Intent Hardening (2026-04-15)

### Why This Slice Is Next

- the new `P33b` line starts with the highest-risk remaining runtime contract gap:
  - operator/runtime can still disagree about whether a requested model was explicit or only a routing hint
- the dangerous behavior was narrow and concrete:
  - pinned provider/model requests were already strict
  - but automatic routing still allowed an explicit `requested_model` to silently degrade into `fallback_default`
- before capability grading or provider-governance work continues, the route contract needs to become honest:
  - explicit requests fail
  - automatic routes may still fall back

### Scope

- add an explicit route-intent seam to provider model mapping and routed runtime resolution
- make explicit requested-model routing reject silent provider-default fallback
- preserve existing automatic fallback behavior for genuinely automatic routing
- keep pinned provider/model selection semantics unchanged and strict
- add focused regression coverage at runtime and kernel boundaries

### Acceptance

- explicit `requested_model` routing no longer silently resolves to a provider default when no provider can match it
- automatic routed selection still may use `fallback_default`
- wrong provider/model pinning still fails loudly
- kernel passes explicit route intent when a caller explicitly supplies `requested_model` without a pinned provider

### Status

- completed

### Implementation Notes

- added `RouteIntent` support to the model-mapper and routed-runtime seam
- added `requested_model_route_intent` override support to `AgentKernelBuildOptions`
- default kernel behavior now treats non-pinned `requested_model` as explicit unless a caller deliberately overrides the intent back to automatic

### Next Likely Seam

- `P33b.2 Capability Truth Grading`
- the next runtime-honesty problem is capability optimism:
  - tool/thinking support currently looks more certain than the evidence actually warrants

## Latest Sync: 2026-04-15 P33b Runtime Truth And Provider Governance Planning

## Current Execution Slice: P33b Runtime Truth And Provider Governance Planning (2026-04-15)

### Why This Slice Is Next

- original `P33.1` through `P33.8` are now effectively landed as the runtime-upgrade baseline
- the remaining model/runtime issues are no longer protocol-foundation gaps
- they are governance and truth-model problems around:
  - route intent
  - capability evidence
  - discovery integrity
  - bootstrap provider selection
  - provider contract honesty
- keeping those follow-up issues under the original `P33` tail would keep blurring:
  - completed baseline runtime upgrade work
  - new second-stage provider/runtime governance work

### Scope

- create a dedicated `P33b` successor plan for runtime truth and provider governance
- freeze original `P33` as the completed foundation line
- define the next upgrade slices for:
  - exact-vs-automatic route intent
  - capability truth grading
  - discovery cache/inventory integrity
  - bootstrap preset governance
  - provider contract tightening
  - route observability

### Acceptance

- `P33b` exists as a separate active plan doc instead of staying mixed into the old `P33` tail
- the new line is explicitly framed as second-stage runtime/provider governance work
- the next implementation anchor is clear and narrow enough to start immediately

### Status

- completed

### Canonical Plan Doc

- `docs/P33B_RUNTIME_TRUTH_AND_PROVIDER_GOVERNANCE_PLAN_2026-04-15.md`

### Next Likely Seam

- `P33b.1 Route Intent Hardening`
- make exact provider/model requests fail loudly instead of silently falling back to provider defaults
- keep automatic route selection free to fall back only on explicitly automatic paths

## Latest Sync: 2026-04-15 P33.22 CLI Command Config-Load Helper Consolidation

## Current Execution Slice: P33.22 CLI Command Config-Load Helper Consolidation (2026-04-15)

### Why This Slice Is Next

- `P33.21` concentrated real config loading at entry/composition seams
- but the maintained CLI command surface still repeated the same thin pattern in several places:
  - raw `load_entry_config()` calls
  - identical `Failed to load configuration` banner handling
- the remaining duplication was now shallow enough that one tiny CLI-only helper could improve readability without pushing config ownership back down into shared runtime/core layers

### Scope

- add one private CLI-only config-load helper in `cli.py`
- rewire repeated CLI command branches to that helper
- keep headless mode's custom structured error output intact
- preserve the silent default-log-dir fallback in `prune-export-jobs`

### Acceptance

- repeated CLI command entrypoints no longer inline the same `load_entry_config()` + banner branch
- the helper remains CLI-surface-local rather than becoming a shared runtime/core abstraction
- headless error output and export-prune fallback semantics remain unchanged
- focused CLI regression coverage remains green

### Status

- completed

### Next Likely Seam

- inspect whether `cli_interactive.run_interactive_session(...)` startup config/self-check failure handling should stay session-local, or whether one tiny CLI-session helper would clarify startup ownership without blurring the boundary between command entry and interactive-session bootstrap

## Latest Sync: 2026-04-15 Worktree Hygiene / Slice Classification Audit

## Current Execution Slice: Worktree Hygiene / Slice Classification Audit (2026-04-15)

### Why This Slice Is Next

- the repo-local cache/noise cleanup is already done
- but the remaining dirty tree still spans large real refactor work, so starting new development without classifying it would risk mixing:
  - late `P32` structure/boundary work
  - active `P33` LLM/runtime/config work
  - docs/test sync
- the user explicitly asked for state entry and hygiene before resuming new feature work

### Scope

- verify whether any additional ignored trash remains safe to remove
- classify the remaining tracked/untracked changes into coherent slice groups
- identify cross-slice hotspot files that should not be split by directory alone
- recommend a practical commit/handoff order before new development resumes

### Acceptance

- no further obvious removable repo-noise remains besides intentionally preserved local runtime/config state
- remaining changes are grouped into commit-safe buckets with rationale
- suspicious leftovers and cross-slice hotspots are called out explicitly

### Status

- completed

### Recommended Grouping

1. hygiene guardrail only
   - `.gitignore` boundary fix plus the already removed repo-local caches/noise
2. legacy browser / remote-channel retirement
   - `src/apps/agent_studio/*`
   - `src/apps/open_webui/*`
   - `src/channels/*`
   - `src/gateway/channels/*`
   - aligned scripts/tests/docs
3. `P32` structure / runtime / session / transport realignment
   - `agent_core`
   - `application`
   - `interaction`
   - `runtime`
   - `session`
   - `transport`
   - `novel`
   - gateway host/composition realignment
4. memory shared-service extraction
   - `src/mini_agent/memory/*`
   - related runtime/command integration
   - aligned memory tests
5. `P33` LLM runtime / config upgrade
   - `config*`
   - `llm/*`
   - `model_manager/*`
   - config-injection touches in CLI/TUI/kernel/gateway composition
   - `scripts/ollama_live_smoke.py`
   - aligned runtime tests/docs
6. docs sync last
   - `README*`
   - architecture/dev guides
   - `task_plan.md`
   - `progress.md`
   - `findings.md`

### Cross-Slice Hotspots

- do not split these mechanically by directory:
  - `src/mini_agent/cli.py`
  - `src/mini_agent/cli_interactive.py`
  - `src/mini_agent/tui/app.py`
  - `src/mini_agent/runtime/main_agent_runtime_manager.py`
  - `src/apps/agent_studio_gateway/main.py`
  - `src/apps/agent_studio_gateway/composition.py`
  - `tests/test_main_agent_surface_service.py`
  - `tests/test_tui_app.py`
- these files carry both late `P32` ownership extractions and active `P33` config/runtime tightening, so staging must follow slice semantics rather than folder boundaries

## Latest Sync: 2026-04-15 P33.21 Entry Config Loader Consolidation

## Current Execution Slice: P33.21 Entry Config Loader Consolidation (2026-04-15)

### Why This Slice Is Next

- `P33.20` removed the last hidden helper-local config discovery from the active CLI path
- after that cut, `Config.load()` ownership was finally concentrated at entry/composition seams
- but those seams still repeated the same thin patterns:
  - direct entry `Config.load()` calls
  - inline noninteractive loader wrappers for TUI/runtime/kernel wiring
- before moving on, that duplication needed one explicit maintained helper without pushing config discovery back down into shared runtime/core layers

### Scope

- add tiny shared entry/bootstrap config helpers
- rewire active CLI/TUI/gateway entry/composition paths to those helpers
- prove the active `src` tree no longer keeps scattered direct `Config.load()` sites outside the helper module

### Acceptance

- active entry/composition code no longer repeats raw `Config.load()` or inline noninteractive loader lambdas
- surfaces still choose interactive vs noninteractive setup behavior explicitly
- focused CLI/TUI/gateway regression coverage remains green

### Status

- completed

### Next Likely Seam

- evaluate whether repeated CLI operator-command `load_entry_config()` + error-report branches should stay surface-local, or whether a tiny CLI-only helper would improve readability without re-centralizing bootstrap behavior across surfaces

## Latest Sync: 2026-04-15 P33.20 Headless / CLI Helper Config Boundary Closure

## Current Execution Slice: P33.20 Headless / CLI Helper Config Boundary Closure (2026-04-15)

### Why This Slice Is Next

- `P33.19` removed the duplicate interactive CLI config-load hop
- but one surface-local fallback still remained:
  - `cli_interactive.build_agent(...)` could still rediscover config on its own
  - headless mode still depended on that helper-local fallback
- before moving on, that last exception needed to be removed so the active CLI path matched the same ownership rule as kernel/runtime/TUI/gateway

### Scope

- require explicit injected config for `cli_interactive.build_agent(...)`
- move headless config loading to the actual CLI entry seam
- update CLI submission-loop regression coverage to prove the new seam

### Acceptance

- `cli_interactive.build_agent(...)` no longer performs hidden config discovery
- headless mode explicitly loads config before the async execution helper runs
- focused CLI/kernel/TUI/gateway regression coverage remains green

### Status

- completed

### Next Likely Seam

- evaluate whether the remaining entry/composition `Config.load()` sites should stay intentionally duplicated by surface, or whether a tiny shared entry-bootstrap helper would improve clarity without smearing responsibilities back across surfaces

## Latest Sync: 2026-04-15 P33.19 CLI Interactive Config Reuse Cleanup

## Current Execution Slice: P33.19 CLI Interactive Config Reuse Cleanup (2026-04-15)

### Why This Slice Is Next

- `P33.18` left config discovery only at entry/composition seams
- but the interactive CLI flow still loaded config for startup checks and then could rediscover it again during the first agent bootstrap
- that duplication was shallow, but it was still unnecessary once the entry already had a chosen config

### Scope

- reuse the already loaded CLI interactive config during the first agent bootstrap
- keep surface-local helper behavior intact for callers that do not preload config
- update CLI submission-loop doubles to accept the explicit config seam

### Acceptance

- interactive CLI startup no longer performs the first agent bootstrap through a second config discovery hop
- CLI submission-loop regression coverage remains green

### Status

- completed

### Next Likely Seam

- decide whether the remaining entry/composition `Config.load()` sites should stay as-is, or whether a tiny shared entry bootstrap helper would improve clarity without over-centralizing surface responsibilities

## Latest Sync: 2026-04-15 P33.14 Config Loader Responsibility Split

## Current Execution Slice: P33.14 Config Loader Responsibility Split (2026-04-15)

### Why This Slice Is Next

- the recent `P33` cuts clarified runtime truth
- but `Config.from_yaml(...)` was still structurally muddy and mixed env absorption, bootstrap fallback, and every section parser in one place
- before pushing further on config/runtime ownership, that loader seam needed to be made explicit

### Scope

- split `Config.from_yaml(...)` into explicit helper steps
- separate YAML validation, bootstrap LLM resolution, runtime parsing, and other section parsing
- add loader-focused regression for invalid root shape and disabled interactive bootstrap

### Acceptance

- `Config.from_yaml(...)` becomes orchestration rather than a monolithic parser
- invalid non-mapping config roots fail with a clear error
- `allow_interactive_setup=False` does not trigger first-launch bootstrap
- focused regression stays green

### Status

- completed

## Latest Sync: 2026-04-15 P33.13 Protocol-Binding / Rectifier Residual Env Fallback Removal

## Current Execution Slice: P33.13 Protocol-Binding / Rectifier Residual Env Fallback Removal (2026-04-15)

### Why This Slice Is Next

- `P33.12` moved active request-policy and rectifier defaults into `config.runtime`
- but rectifier still kept a local env-fallback helper, which left one hidden policy-discovery path alive
- before moving on, that residual path needed to be removed and the active `src` runtime profile-construction paths needed one final audit

### Scope

- audit active `src` callers of protocol-profile construction
- remove `rectifier.py` env-fallback behavior
- prove via tests that protocol binding and direct rectifier defaults no longer read env toggles

### Acceptance

- active `src` runtime has no side-path protocol-profile construction outside the unified runtime seam
- `rectify_openai_request(...)` and `rectify_anthropic_request(...)` no longer read env by default
- focused regression stays green

### Status

- completed

## Latest Sync: 2026-04-15 P33.12 Runtime Request-Policy / Rectifier Ownership Realignment

## Current Execution Slice: P33.12 Runtime Request-Policy / Rectifier Ownership Realignment (2026-04-15)

### Why This Slice Is Next

- `P33.11` moved retry into `config.runtime`
- but active request-policy defaults and rectifier defaults were still partly owned by protocol/profile env fallbacks
- that would leave hidden runtime policy truth below the config boundary unless corrected now

### Scope

- add explicit runtime config ownership for request-policy defaults
- add explicit runtime config ownership for rectifier defaults
- pass those defaults through kernel -> failover -> protocol binding
- stop the hot runtime path from reading request-policy env vars directly inside protocol binding
- update focused config/binding/kernel regression coverage

### Acceptance

- active runtime request-policy defaults come from `config.runtime.request_policy`
- active runtime rectifier defaults come from `config.runtime.rectifier`
- protocol binding keeps provider-aware defaults but no longer owns hidden hot-path env policy
- focused regression stays green

### Status

- completed

## Latest Sync: 2026-04-15 P33.11 Runtime Retry Config Boundary Realignment

## Current Execution Slice: P33.11 Runtime Retry Config Boundary Realignment (2026-04-15)

### Why This Slice Is Next

- `P33.10` narrowed routing input to bootstrap-only config
- but retry policy still sat under `config.llm`, which kept one runtime-policy concern attached to the bootstrap subtree
- that would keep teaching the wrong ownership model unless it was corrected now

### Scope

- add an explicit runtime config subtree for retry ownership
- remove retry from `LLMConfig`
- update maintained YAML examples to `runtime.retry`
- reject legacy top-level `retry:` instead of silently carrying compatibility
- verify kernel retry bootstrap now reads runtime-owned config

### Acceptance

- retry is no longer owned by `config.llm`
- active config shape uses `runtime.retry`
- legacy top-level `retry:` is rejected with a clear migration error
- focused config/kernel regression stays green

### Status

- completed

## Latest Sync: 2026-04-15 P33.10 Bootstrap-Only Route Boundary Narrowing

## Current Execution Slice: P33.10 Bootstrap-Only Route Boundary Narrowing (2026-04-15)

### Why This Slice Is Next

- `P33.1` behavior was already mostly landed, but one important interface seam was still teaching the old ownership story
- runtime routing helpers still accepted the whole `Config` object even though only bootstrap route input was needed
- that had to be narrowed before continuing later runtime closure work, otherwise `config.llm` could drift back in through interface shape alone

### Scope

- extract one minimal bootstrap route input model from loaded config
- rewire routing APIs to accept bootstrap-only input instead of full config
- remove config-shaped dependency from session model-selection identity resolution
- keep retry/runtime policy ownership unchanged
- update active runtime-flow docs and focused regression coverage

### Acceptance

- routing APIs no longer accept the full config object as a route source
- bootstrap fallback remains supported through a synthetic bootstrap provider path
- session model-selection identity resolution no longer depends on runtime config
- focused routing/kernel regression suites stay green

### Status

- completed

## Latest Sync: 2026-04-15 P33.9 Gemini Active Runtime Residual Cleanup

## Current Execution Slice: P33.9 Gemini Active Runtime Residual Cleanup (2026-04-15)

### Why This Slice Is Next

- `P33.1` locked the decision that Gemini is removed from active runtime scope
- after `P33.8` live validation, the remaining runtime drift was no longer architectural uncertainty
- it was stale Gemini support still living in:
  - provider enums
  - model discovery
  - model registry discovery mapping
  - ops provider setup/discovery
- that drift needed to be removed before continuing the next runtime closure slice

### Scope

- remove Gemini from active runtime/provider enums and default routing support
- remove Gemini model-discovery endpoint/fallback/fetch branches
- stop advertising Gemini in active model-manager exports
- reject Gemini in active provider setup/discovery flows instead of silently mapping it
- keep unrelated historical/reference Gemini material untouched

### Acceptance

- active runtime/provider config no longer treats Gemini as a maintained protocol
- model discovery no longer knows a Gemini endpoint or fallback catalog
- ops discovery returns an explicit unsupported-provider error for Gemini
- targeted runtime + ops regression suites stay green

### Status

- completed

## Latest Sync: 2026-04-15 P33.8 Ollama Local Provider Integration Live Validation

## Current Execution Slice: P33.8 Ollama Local Provider Integration Live Validation (2026-04-15)

### Why This Slice Is Next

- `P33.1` through `P33.7` were landed in sequence first, so the runtime seam was finally stable enough for a maintained local provider path
- the correct next step was therefore not more protocol cleanup
- it was to add `Ollama` on top of the corrected:
  - registry truth
  - routing seam
  - protocol binding
  - request-policy ownership

### Scope

- add `Ollama` as a maintained local preset/provider source
- support no-auth local operation without requiring a user-supplied fake API key
- discover local models from Ollama's maintained endpoints
- keep the runtime protocol-centric:
  - default Anthropic-compatible path
  - optional OpenAI-compatible override
- avoid surprising startup drift by requiring explicit local enablement

### Acceptance

- Ollama can be enabled and routed without fake external API-key requirements
- discovered Ollama models flow through the same provider/model registry path
- runtime can resolve `preset-ollama` like other maintained providers
- explicit enablement avoids silently hijacking existing cloud/bootstrap startup behavior

### Follow-up Validation Focus

- verify session-scoped selection can target `preset-ollama`
- verify local `CLI / TUI` surfaces rebuild correctly onto the Ollama preset route
- tighten operator feedback when Ollama is enabled but the local daemon is unavailable
- validate one real streamed prompt and one real tool-call turn against the local Ollama daemon
- close any loopback/proxy transport defects revealed by live-machine execution

### Status

- completed

## Latest Sync: 2026-04-15 P33.7 Request Policy / Protocol Parameter Upgrade

## Current Execution Slice: P33.7 Request Policy / Protocol Parameter Upgrade (2026-04-15)

### Why This Slice Is Next

- `P33.6` made route capability requirements explicit, but request defaults were still drifting across:
  - protocol binding
  - rectifier options
  - protocol clients
- that meant one important runtime seam was still not honest:
  - who owns request policy for one bound provider/model route
- before adding `P33.8 Ollama`, that ownership needed to be made explicit and testable

### Scope

- define one explicit bound request-policy object
- move effective request defaults into the binding/profile layer
- narrow rectifier ownership back to payload normalization only
- rewire OpenAI / Anthropic clients to consume request policy instead of client-owned defaults

### Acceptance

- protocol clients are no longer the long-term owner of request defaults
- request policy is inspectable on the bound execution profile
- rectifier is no longer the owner of thinking-budget / output-token defaults
- focused protocol/request-policy regression stays green

### Status

- completed

## Latest Sync: 2026-04-14 P33.3 Rich Response Model Upgrade

## Current Execution Slice: P33.3 Rich Response Model Upgrade (2026-04-14)

### Why This Slice Is Next

- `P33.2` cleaned the execution boundary, but the response contract was still too thin for the next runtime upgrades:
  - buffered completions were represented as one flattened response object
  - the runtime had no canonical event model shared by both buffered and future native streaming output
- that meant `P33.4 Native Streaming` would otherwise need to redesign both:
  - protocol client output
  - agent/application consumption contracts
- the cleaner move was to normalize the response seam first so streaming can become an execution upgrade, not another contract rewrite

### Scope

- introduce a canonical normalized completion model:
  - `LLMCompletionResult`
- introduce a canonical normalized event model:
  - `LLMStreamEvent`
  - `LLMStreamEventType`
- make buffered completions representable as normalized event streams
- update protocol clients, failover, logger, and agent execution to consume the richer completion contract
- keep this slice intentionally buffered-only:
  - do not yet implement provider-native streaming transport

### Acceptance

- protocol clients return `LLMCompletionResult` instead of the old thin response contract
- buffered completions can be synthesized into normalized events
- normalized event lists can be aggregated back into a buffered completion result
- agent/logger/test surfaces consume the new completion model without reintroducing protocol-specific parsing

### Status

- completed

## Latest Sync: 2026-04-14 P33.2 Protocol Boundary Hardening

## Current Execution Slice: P33.2 Protocol Boundary Hardening (2026-04-14)

### Why This Slice Is Next

- `P33.1` fixed the runtime truth source, but one important seam was still dirty:
  - provider compatibility policy still leaked into the protocol wrapper/client layer
- the clearest example was `llm_wrapper.py`, which still decided:
  - MiniMax endpoint suffix rewriting
  - provider/domain-aware base URL normalization
- protocol clients also still carried provider-shaped assumptions:
  - MiniMax-flavored defaults
  - inline request tweaks coupled to endpoint flavor
- if this seam stayed mixed, later work on:
  - native streaming
  - request policy
  - Ollama
  would keep building on a muddy boundary

### Scope

- introduce an explicit protocol execution profile/binding layer
- move provider compatibility rules out of `LLMClient` wrapper code
- stop letting OpenAI / Anthropic protocol clients decide provider compatibility details
- keep this cut intentionally narrow:
  - do not redesign the full response model yet
  - do not implement native streaming yet

### Acceptance

- `LLMClient` becomes a thin protocol-dispatch facade
- MiniMax-compatible endpoint normalization moves into explicit binding logic
- protocol clients consume already-bound execution profiles
- provider-specific compatibility rules stop living inside protocol wrapper/client branching

### Status

- completed

## Latest Sync: 2026-04-14 P33.1 Registry Truth Consolidation

## Current Execution Slice: P33.1 Registry Truth Consolidation (2026-04-14)

### Why This Slice Is Next

- the runtime truth direction was already decided in `P33`, but the hot path still had one unresolved contradiction:
  - `config.llm` still participated directly in runtime route selection
- that meant the code was still teaching two owners for runtime provider/model truth:
  - provider registry
  - direct config fallback
- `Gemini` also still remained visible in active preset/runtime-facing UX even after the design decision to remove it from active scope

### Scope

- make runtime route selection resolve through the registry path only
- downgrade `config.llm` to bootstrap-only behavior by synthesizing one runtime bootstrap provider when the registry is empty
- stop using `config.llm.provider` and `config.llm.model` as implicit hot-path routing preferences when the registry already exists
- remove `Gemini` from active preset/runtime-facing setup and CLI UX

### Acceptance

- routed LLM settings never return a direct `config` route in the hot path
- empty-registry startup resolves through a synthetic bootstrap provider entry
- provider/session model selection defaults come from provider registry state instead of `config.llm.model`
- active preset/runtime-facing CLI/config flows no longer advertise `Gemini`

### Status

- completed

## Latest Sync: 2026-04-14 P33 LLM Runtime Upgrade Planning

## Current Execution Slice: P33 LLM Runtime Upgrade Planning (2026-04-14)

### Why This Slice Is Next

- the model runtime is now stable enough to inspect as its own seam instead of treating it as support glue
- the current runtime works, but several design debts are now visible:
  - `config.llm` is still a peer truth source beside the provider registry
  - protocol execution and provider compatibility policy are still partly mixed
  - streaming is still not provider-native
  - model discovery/latest selection is still partly heuristic
- the user has now explicitly locked several runtime decisions:
  - no need for one native SDK per brand
  - `Gemini` should leave active runtime scope
  - `MiniMax` stays in the `anthropic` compatibility family
  - route capability growth should stay limited to `tools / thinking / context_window`
  - `Ollama` should be considered as a real local provider path

### Scope

- define the canonical truth direction for runtime model/provider ownership
- define the next upgrade plan for:
  - protocol boundary cleanup
  - native streaming
  - discovery/latest selection
  - capability-aware routing
  - request-policy parameterization
  - Ollama local integration
- record the plan in a dedicated design doc before implementation

### Acceptance

- the project has one explicit LLM runtime upgrade plan doc
- the correct truth model is written down clearly
- Ollama integration direction is decided at design level
- the next implementation slice is narrowed to one concrete first cut instead of another broad runtime rewrite

### Canonical Plan Doc

- `docs/P33_LLM_RUNTIME_UPGRADE_PLAN_2026-04-14.md`

### Status

- completed

## Latest Sync: 2026-04-14 P32.61 Shared Remote Recovery Feedback Semantics

## Current Execution Slice: P32.61 Shared Remote Recovery Feedback Semantics (2026-04-14)

### Why This Slice Is Next

- after the Remote Interaction architecture lock, the next remaining boundary drift was smaller but real:
  - `QQ` still hand-built shared-session recovery/status wording for `/status` and `/continue`
- that wording was not adapter-only glue; it encoded shared runtime/session semantics:
  - route ownership
  - restart interruption state
  - lost approvals after restart
  - resume hint
  - skill-reload pending state
- if left in `QQ`, every future Remote Interaction adapter would be tempted to clone it

### Scope

- add one shared owner for remote recovery/status feedback semantics
- export the shared text through session summary/detail read models
- rewire `QQ` to prefer the shared payload and keep only adapter-local recent-message formatting

### Acceptance

- primary shared-session recovery/status wording no longer lives only in `QQ`
- session detail/summary transport payload carries shared remote recovery text
- `QQ` `/status` and `/continue` prefer the shared payload instead of defining shared semantics locally
- focused regression around projection round-trip and restart recovery remains green

### Status

- completed

## Latest Sync: 2026-04-14 P32.60 Remote Interaction / QQ Architecture Lock

## Current Execution Slice: P32.60 Remote Interaction / QQ Architecture Lock (2026-04-14)

### Why This Slice Is Next

- the active architecture docs already said the right thing in principle:
  - entrances are `CLI / TUI / DesktopUI / Remote Interaction`
- but the repo still physically carried multiple drift sources:
  - `interaction` normalization still treated `WeChat / Feishu / WebUI` as active aliases
  - legacy Python and TypeScript channel trees still lived in the active source tree
  - tests and smoke paths still taught a fake multi-channel active model
- that meant future work could keep drifting back into:
  - `QQ` as a fifth entrance
  - dormant remote adapters treated like maintained paths
  - parallel channel abstractions reappearing in design discussions

### Scope

- lock interaction normalization to one active remote adapter: `QQ`
- keep `Remote Interaction` as the fourth product entrance
- delete legacy non-QQ channel trees from the active repo
- delete obsolete QQ/WeChat combined smoke/test surfaces
- sync active architecture / plan docs so the physical repo and the written design match

### Acceptance

- active code resolves only `QQ` as an active remote adapter
- `Remote Interaction` remains the entrance-level abstraction
- old `src/channels/*`, `src/mini_agent/channels/*`, and `src/gateway/channels/*` trees are removed
- active docs no longer teach `QQ` as a peer entrance or keep dormant non-QQ trees as live paths
- focused regression for interaction, channel ingress, session binding, and runtime stack remains green

### Status

- completed

## Latest Sync: 2026-04-14 P32.59 Shared Runtime-Policy Feedback / Response Semantics

## Current Execution Slice: P32.59 Shared Runtime-Policy Feedback / Response Semantics (2026-04-14)

### Why This Slice Is Next

- after `P32.58`, the next real cross-surface semantic leak was runtime-policy feedback
- the runtime-policy plan/execution rules already lived in:
  - `src/mini_agent/runtime/runtime_policy_service.py`
- but the user-facing success/failure/unchanged feedback still leaked across surfaces:
  - `TUI` handwrote unchanged / failed / updated command feedback
  - `QQ` handwrote shared-session runtime-policy success text
- the honest owner was the existing runtime-policy service, not another surface helper

### Scope

- extend the runtime-policy service with shared feedback semantics
- carry that shared feedback through the shared runtime-policy response
- rewire `TUI` and `QQ` to consume the shared semantics while preserving TUI-local session-title display ownership

### Acceptance

- runtime-policy success/unchanged/failure wording no longer lives only in `TUI`
- shared-session runtime-policy responses carry shared feedback fields
- `QQ` remote formatting becomes thinner by preferring shared response details
- `TUI` keeps local status-bar ownership for its display title instead of trusting remote transport labels

### Status

- completed

## Latest Sync: 2026-04-14 P32.58 Shared MCP Local Reload Feedback Semantics

## Current Execution Slice: P32.58 Shared MCP Local Reload Feedback Semantics (2026-04-14)

### Why This Slice Is Next

- after `P32.57`, the next similar but smaller shared-semantic seam was local `mcp reload`
- `McpCommandService` already owned:
  - action validation
  - reload execution
  - result payload and status semantics
- but the follow-up local runtime rebuild feedback still leaked into surfaces:
  - `CLI` kept its own reload-success line
  - `TUI` kept its own local warm-reload prefix
- this did not justify a large new abstraction, but it did justify returning the remaining feedback ownership to the `MCP` command owner

### Scope

- keep `MCP` execution flow unchanged
- add a thin shared owner for local reload feedback semantics
- rewire `CLI` and `TUI` to consume it

### Acceptance

- `CLI` no longer handwrites the local MCP reload success line
- `TUI` no longer handwrites the local MCP warm-reload prefix
- the remaining local MCP reload feedback semantics live with `tools.mcp`

### Status

- completed

## Latest Sync: 2026-04-14 P32.57 Shared Skill Runtime-Reload Feedback Semantics

## Current Execution Slice: P32.57 Shared Skill Runtime-Reload Feedback Semantics (2026-04-14)

### Why This Slice Is Next

- after `P32.56`, the next real cross-surface drift was no longer session feedback
- local `skill` mutation success already had one owner in:
  - `src/mini_agent/commands/execution.py`
- but the follow-up runtime-reload semantics still lived in two surfaces:
  - `src/mini_agent/cli_interactive.py`
  - `src/mini_agent/tui/app.py`
- the duplicated ownership was not just wording:
  - mutation -> busy-summary mapping
  - mutation -> warm-reload prefix mapping
  - mutation -> CLI reload success/failure messaging
- that made `skill` mutation/reload behavior a real shared semantic seam, not just surface polish

### Scope

- extract one shared owner for local skill runtime-reload feedback semantics
- rewire `CLI` and `TUI` to consume it
- keep execution mechanics separate:
  - `CLI` still rebuilds its current agent
  - `TUI` still queues or warms session runtime as needed

### Acceptance

- `CLI` no longer owns handwritten mutation -> reload success/failure text
- `TUI` no longer owns handwritten mutation -> busy/warm/status descriptor logic
- shared skill reload semantics live under `agent_core.skills`

### Status

- completed

## Latest Sync: 2026-04-14 P30.5 Residual Hotspot Audit

## Current Execution Slice: P30.5 Residual Hotspot Audit (2026-04-14)

### Why This Slice Is Next

- after landing shared `/memory`, `/model`, and `/context` planning seams, the remaining question was no longer "what else can be extracted"
- the real question became "what should deliberately stay in the surface layer so `P30.5` does not drift into extraction for its own sake"

### Audit Outcome

- `CLI`
  - the remaining inline branch in [cli_interactive.py](d:\file\Mini-Agent\src\mini_agent\cli_interactive.py) is `workflow`
  - keep it local:
    - it is entrance-specific workflow launch orchestration
    - it is not duplicated across another terminal entrance
    - extracting it now would not reduce shared-entrance drift
- `TUI`
  - keep [SessionCommandPlan](d:\file\Mini-Agent\src\mini_agent\tui\app.py):
    - it bundles cursor movement, focus switching, and remote lifecycle actions tied to the TUI session list
    - this is surface orchestration, not shared command semantics
  - keep [KbCommandPlan](d:\file\Mini-Agent\src\mini_agent\tui\app.py):
    - the parse surface is tiny (`status|on|off`)
    - the real shared owner already exists in `LocalOperatorCommandService.execute_kb(...)`
    - extraction would save little and add more indirection than value
  - keep [McpCommandPlan](d:\file\Mini-Agent\src\mini_agent\tui\app.py):
    - the parse surface is also tiny (`status|list|reload`)
    - the high-complexity part is local runtime rebuild / remote control dispatch, which is already rightly surface-owned
  - keep [SkillCommandPlan](d:\file\Mini-Agent\src\mini_agent\tui\app.py) and [RemoteSkillCommandPlan](d:\file\Mini-Agent\src\mini_agent\tui\app.py):
    - shared request parsing already lives in `prepare_skill_request(...)`
    - the remaining TUI plan objects mostly carry surface transport/routing metadata

### Structural Conclusion

- `P30.5` is now effectively in a keep state rather than an extraction state
- the current remaining `CommandPlan` objects in `TUI` are mostly:
  - surface orchestration
  - transport mapping
  - cursor/focus/view concerns
- those are not the same class of drift that `/memory`, `/model`, and `/context` represented

### Recommended Next Step

- stop further `P30.5` plan extraction unless a fresh duplication hotspot appears
- shift effort back to:
  - higher-value core capability work
  - clearer boundary audits at larger module seams

### Status

- completed

## Latest Sync: 2026-04-14 P30.5 CLI-TUI Shared Context Command Plan Convergence

## Current Execution Slice: P30.5 CLI-TUI Shared Context Command Plan Convergence (2026-04-14)

### Why This Slice Is Next

- after landing the shared `/memory` and `/model` planning seams, the next remaining terminal drift was `/context`
- `CLI` still normalized `brief/full` aliases inline before calling the shared execution service
- `TUI` still owned its own `ContextCommandPlan` even though the actual `/context` execution semantics already lived in the shared command layer
- the honest owner for `/context` planning is `src/mini_agent/commands/execution.py`, because both `CLI` and `TUI` need the same action normalization and side-effect classification

### Scope

- move `ContextCommandPlan` into the shared command execution layer
- add one shared `prepare_context_command_plan(...)` helper
- rewire:
  - `src/mini_agent/cli_interactive.py`
  - `src/mini_agent/tui/app.py`
  to consume the same shared `/context` planning seam

### Acceptance

- `CLI` no longer normalizes `/context brief|full` inline
- `TUI` no longer owns a second surface-local `ContextCommandPlan`
- `/context` action normalization and mutate/refresh classification are shared by default across terminal entrances

### Status

- completed

## Latest Sync: 2026-04-14 P30.5 CLI-TUI Shared Model Command Plan Convergence

## Current Execution Slice: P30.5 CLI-TUI Shared Model Command Plan Convergence (2026-04-14)

### Why This Slice Is Next

- after landing the shared `/memory` planning seam, the next clear entrance drift was local `/model`
- `CLI` still kept a handwritten `show/list/use` branch in `src/mini_agent/cli_interactive.py`
- `TUI` already had a local `ModelCommandPlan`, but it still lived inside the surface instead of the shared command layer
- the honest owner for `/model` planning is `src/mini_agent/commands/execution.py`, because `CLI` and `TUI` both need the same action normalization and request shaping

### Scope

- move `ModelCommandPlan` into the shared command execution layer
- add one shared `prepare_model_command_plan(...)` helper
- rewire:
  - `src/mini_agent/cli_interactive.py`
  - `src/mini_agent/tui/app.py`
  to consume the same shared `/model` planning seam

### Acceptance

- `CLI` no longer keeps a handwritten `show/list/use` `/model` branch
- `TUI` no longer owns a second surface-local `ModelCommandPlan`
- `/model` action normalization is shared by default across terminal entrances

### Status

- completed

## Latest Sync: 2026-04-14 P30.5 CLI-TUI Shared Memory Command Plan Convergence

## Current Execution Slice: P30.5 CLI-TUI Shared Memory Command Plan Convergence (2026-04-14)

### Why This Slice Is Next

- after the earlier `TUI` command-plan work and the shared `/skill` request seam, the next obvious entrance drift was local `/memory`
- `CLI` still kept a large handwritten `/memory` branch in `src/mini_agent/cli_interactive.py`
- `TUI` already had a structured `MemoryCommandPlan`, but that plan still lived inside the surface instead of the shared command layer
- the honest owner for `/memory` command parsing is `src/mini_agent/commands/execution.py`, because both `CLI` and `TUI` need the same action normalization, usage handling, and request shaping

### Scope

- move `MemoryCommandPlan` into the shared command execution layer
- add one shared `prepare_memory_command_plan(...)` helper
- rewire:
  - `src/mini_agent/cli_interactive.py`
  - `src/mini_agent/tui/app.py`
  to consume that same shared `/memory` planning seam

### Acceptance

- `CLI` no longer keeps a long action-by-action `/memory` branch
- `TUI` no longer owns a second surface-local `/memory` parser shell
- `/memory` action normalization, usage handling, and mutation classification are shared by default across terminal entrances

### Status

- completed

## Latest Sync: 2026-04-14 P32.46 Memory Command Core Consolidation

## Current Execution Slice: P32.46 Memory Command Core Consolidation (2026-04-14)

### Why This Slice Is Next

- after `P32.45`, the next real boundary issue was not inside `MainAgentRuntimeManager`
- `/memory` command semantics were still duplicated across:
  - `src/mini_agent/runtime/session_memory_command_handler.py`
  - `src/mini_agent/commands/execution.py`
- that duplication meant the actual escaped owner was no longer runtime-local
- the honest shared owner is `mini_agent.memory`, because both runtime and local operator flows execute the same memory-command business rules

### Scope

- extract one shared `/memory` command core into `src/mini_agent/memory/`
- move the workspace runtime-memory backend adapter out of `runtime/` and into the `memory/` package
- rewire:
  - `RuntimeSessionMemoryCommandHandler`
  - `LocalOperatorCommandService.execute_memory_action(...)`
  to thin wrappers around the shared owner

### Acceptance

- runtime and local memory command flows use one shared owner for action semantics, selector resolution, durable reads, and mutation payload shaping
- `runtime/session_memory_command_handler.py` becomes an HTTP/runtime wrapper rather than a second business implementation
- `commands/execution.py` no longer reimplements the `/memory` action family inline

### Status

- completed

## Latest Sync: 2026-04-14 P32.45 Runtime Manager Boundary Audit

## Current Execution Slice: P32.45 Runtime Manager Boundary Audit (2026-04-14)

### Why This Slice Is Next

- after `P32.44`, the next candidate was the largest remaining runtime owner:
  - `src/mini_agent/runtime/main_agent_runtime_manager.py`
- the question was whether it still hides a real mixed business boundary, or whether it is simply the maintained runtime port façade with internal service assembly

### Scope

- audit `src/mini_agent/runtime/main_agent_runtime_manager.py`
- compare its public surface to `session_runtime_port.py`
- inspect whether the `_initialize_*` phases are:
  - real escaped shared owners that should move out
  - or one-time internal graph assembly for the runtime façade
- perform only tiny cleanup if a low-risk dead helper is found

### Acceptance

- a clear keep/split decision is recorded for `MainAgentRuntimeManager`
- if kept, the reasons are documented so later cleanup does not drift into composition-only file splitting
- any dead code found during the audit is removed

### Status

- completed

## Latest Sync: 2026-04-14 P32.44 Tooling / Turn-Context Builder Split

## Current Execution Slice: P32.44 Tooling / Turn-Context Builder Split (2026-04-14)

### Why This Slice Is Next

- after `P32.43`, the next audit pass checked `transport` and `runtime` for real ownership leaks
- `transport` currently reads honestly as:
  - low-level gateway transport in `gateway_client.py`
  - typed session facade in `remote_session_client.py`
- the more honest split target was `src/mini_agent/runtime/tooling.py`
- that file still combined:
  - runtime policy + tool bootstrap
  - skill path resolution
  - turn-context provider assembly

### Scope

- keep transport intact and record that keep decision implicitly in the slice findings
- extract runtime skill path resolution into a dedicated owner
- extract turn-context provider assembly into a dedicated owner
- rewire kernel / skill-support / tests to the new ownership layout

### Acceptance

- `runtime/tooling.py` no longer owns turn-context provider assembly
- skill path resolution no longer lives inside the general tooling bootstrap module
- focused kernel / turn-context / runtime-policy regressions remain green

### Status

- completed

## Latest Sync: 2026-04-14 P32.43 Gateway Ops Auth Split / Interaction Adapter Audit

## Current Execution Slice: P32.43 Gateway Ops Auth Split / Interaction Adapter Audit (2026-04-14)

### Why This Slice Is Next

- after `P32.42`, the next likely cleanup candidates were:
  - `src/mini_agent/application/interaction_request_adapter.py`
  - gateway-side transport/composition naming around ops auth
- the goal was to avoid fake cleanup:
  - keep `interaction_request_adapter` if it is still a truthful single owner
  - only cut code if a real ownership leak remained

### Scope

- audit `src/mini_agent/application/interaction_request_adapter.py`
- inspect gateway ops auth placement across:
  - `src/apps/agent_studio_gateway/ops_router.py`
  - `src/apps/agent_studio_gateway/main.py`
  - `src/apps/agent_studio_gateway/composition.py`
- if router-local auth had become shared composition policy, extract it into a dedicated gateway auth module

### Acceptance

- `interaction_request_adapter.py` has a clear keep/split decision recorded
- gateway ops auth no longer lives inside the ops router module if it is shared outside the router
- gateway ops and main-agent API regressions remain green

### Status

- completed

## Latest Sync: 2026-04-14 P32.42 SessionSurfaceBinding Alias Removal

## Current Execution Slice: P32.42 SessionSurfaceBinding Alias Removal (2026-04-14)

### Why This Slice Is Next

- after P32.41, one low-risk but misleading naming target was explicitly identified
- SessionSurfaceBinding was not a real owner
- it was only an alias of ApplicationInteractionBinding
- leaving that alias in place would keep teaching an extra fake abstraction in the application layer

### Scope

- remove SessionSurfaceBinding from the codebase and package exports
- replace remaining callers with ApplicationInteractionBinding
- run session/surface/gateway regressions to confirm the alias removal is behavior-neutral

### Acceptance

- SessionSurfaceBinding no longer exists as an exported or maintained application name
- tests use ApplicationInteractionBinding directly where binding semantics are being asserted
- session/surface/gateway regressions remain green

### Status

- completed

## Latest Sync: 2026-04-14 P32.41 Session Service / Naming-Debt Audit

## Current Execution Slice: P32.41 Session Service / Naming-Debt Audit (2026-04-14)

### Why This Slice Is Next

- after `P32.40`, the next question was whether `SessionApplicationService` still hides a real mixed boundary
- at the same time, several runtime/application filenames still look close enough to create naming confusion even if the ownership is correct

### Scope

- audit `src/mini_agent/application/session_service.py`
- inspect naming relationships among:
  - `session_lifecycle.py`
  - `session_runtime_lifecycle_handler.py`
  - `session_runtime_port.py`
  - `surface_service_types.py`
  - `main_agent_runtime_policy_loader.py`
  - `SessionSurfaceBinding`

### Acceptance

- a clear keep/split decision is recorded for `SessionApplicationService`
- naming-debt items are separated into:
  - real near-term cleanup candidates
  - accurate names that should remain as-is for now

### Status

- completed

## Latest Sync: 2026-04-14 P32.40 Surface Chat Flow / Surface Service Boundary Audit

## Current Execution Slice: P32.40 Surface Chat Flow / Surface Service Boundary Audit (2026-04-14)

### Why This Slice Is Next

- after `P32.39`, the next obvious large application owners were:
  - `src/mini_agent/application/surface_chat_flow_handler.py`
  - `src/mini_agent/application/main_agent_surface_service.py`
- both sit on major user-facing paths, so splitting them carelessly would create churn across gateway/TUI/client contracts
- the goal of this slice is to verify whether they are true mixed owners or intentional facade/flow owners

### Scope

- audit `SurfaceChatFlowHandler` for:
  - request chat flow
  - stream chat flow
  - dry-run handling
  - turn finalization
- audit `MainAgentSurfaceService` for:
  - public surface facade responsibility
  - interaction binding / workspace resolution
  - orchestration composition
  - session operation pass-through methods

### Acceptance

- a clear keep/split decision is recorded for both owners
- if the answer is keep, the reasons are documented so later cleanup does not drift into facade-splitting

### Status

- completed

## Latest Sync: 2026-04-14 P32.39 Route Resolution / Delegation Execution Split

## Current Execution Slice: P32.39 Route Resolution / Delegation Execution Split (2026-04-14)

### Why This Slice Is Next

- after `P32.38`, the next candidate worth auditing was `src/mini_agent/application/agent_route_execution_handler.py`
- the audit showed an asymmetric result:
  - route resolution + routing diagnostics still belong together
  - delegated child-turn execution + fallback behavior do not
- the mixed owner was not the routing table itself
- it was the way one application owner still combined:
  - route parsing/resolution
  - route diagnostics bookkeeping
  - delegated child-session execution
  - fallback back to the main agent

### Scope

- keep `AgentRouteExecutionHandler` as the route-resolution and route-diagnostics owner
- extract delegated child-turn execution and fallback into a dedicated application owner
- rewire `MainAgentSurfaceService` to compose both owners explicitly
- add focused handler-level regression coverage for the new delegation owner

### Acceptance

- `AgentRouteExecutionHandler` no longer directly owns delegated child-turn execution
- delegation fallback behavior still works with the same external contract
- surface/gateway routing regressions remain green

### Status

- completed

## Latest Sync: 2026-04-14 P32.38 Channel Ingress / Novel Action Ownership Split

## Current Execution Slice: P32.38 Channel Ingress / Novel Action Ownership Split (2026-04-14)

### Why This Slice Is Next

- after `P32.37`, the next real ownership leak showed up in the remote interaction application seam
- `ChannelIngressUseCases` was still mixing:
  - remote message ingress and conversation binding
  - feature-specific `/novel ...` command parsing
  - feature-specific novel action dispatch
- under the current architecture, remote ingress should stay a surface entry owner, not a feature-command owner

### Scope

- extract channel-facing novel command parsing/dispatch into a dedicated application owner
- keep `ChannelIngressUseCases` focused on:
  - remote message ingress
  - conversation/session binding lookup
  - forwarding regular chat messages into main-agent chat
- update gateway composition and tests to wire the new owner explicitly

### Acceptance

- `ChannelIngressUseCases` no longer directly parses or dispatches novel actions
- channel-facing `/novel ...` behavior still works through the dedicated owner
- focused channel/gateway regressions remain green

### Status

- completed

## Latest Sync: 2026-04-14 P32.37 Session Control Ownership Split

## Current Execution Slice: P32.37 Session Control Ownership Split (2026-04-14)

### Why This Slice Is Next

- after `P32.36`, the next suspicious runtime boundary was no longer `session_operator_handler.py`
- the audit showed `RuntimeSessionOperatorHandler` is still a legitimate command-orchestration facade:
  - it routes one session operator surface
  - it coordinates transcript/persist/locking behavior
  - it does not pretend to own the underlying business domains
- the real mixed owner was `src/mini_agent/runtime/session_control_handler.py`
- that file still mixed:
  - agent context controls
  - knowledge-base toggles
  - MCP inspection/reload controls

### Scope

- keep `RuntimeSessionOperatorHandler` intact as the operator-command facade
- split the old mixed session control owner into:
  - `RuntimeSessionAgentControlHandler`
  - `RuntimeSessionMcpControlHandler`
- extract shared control command models/routing into `session_control_models.py`
- rewire runtime composition and operator dispatch to the new owners
- add focused handler-level regression coverage

### Acceptance

- MCP control no longer lives in the same runtime owner as context/KB control
- `RuntimeSessionOperatorHandler` remains only a coordination facade, not a fake business owner
- live surface/service/gateway regressions remain green

### Status

- completed

## Latest Sync: 2026-04-14 P32.36 Recovery-State Ownership Completion

## Current Execution Slice: P32.36 Recovery-State Ownership Completion (2026-04-14)

### Why This Slice Is Next

- after `P32.35`, recovery/reset ownership was improved but not fully closed
- `apply_stored_recovery(...)` still lived in `session_hydration_builder.py`
- that method mutates recovery projection state, so it belongs with the recovery owner rather than the hydration payload builder

### Scope

- move `apply_stored_recovery(...)` into `RuntimeSessionRecoveryResetHandler`
- remove the mutation from `RuntimeSessionHydrationBuilder`
- rewire restore assembly to use the recovery owner directly
- add focused regression coverage for the apply path

### Acceptance

- recovery projection state apply/clear/build/reset all live under one runtime owner
- hydration builder no longer mutates recovery state directly
- restore/runtime/session regressions remain green

### Status

- completed

## Latest Sync: 2026-04-14 P32.35 Runtime Pending-Approval and Recovery/Reset Extraction

## Current Execution Slice: P32.35 Runtime Pending-Approval and Recovery/Reset Extraction (2026-04-14)

### Why This Slice Is Next

- after `P32.34`, the next honest mixed-owner target was `src/mini_agent/runtime/session_live_state_handler.py`
- unlike `RuntimeSessionMemoryCommandHandler`, this file really mixed distinct runtime concerns:
  - surface binding
  - transcript/activity mutation
  - pending approval state
  - recovery/reset cleanup
- the right next cut was to extract the non-live-state concerns while keeping transcript/binding together

### Scope

- extract pending-approval normalization/mutation into a dedicated runtime owner
- extract recovery-context + runtime-reset cleanup into a dedicated runtime owner
- keep `RuntimeSessionLiveStateHandler` focused on:
  - surface binding
  - transcript/activity recording
  - turn running-state flags
- rewire runtime manager composition and regression tests to the new seams

### Acceptance

- `RuntimeSessionLiveStateHandler` no longer owns approval-state or recovery/reset behavior
- runtime manager wiring uses explicit owners for:
  - pending approval state
  - recovery/reset
- focused runtime/session/gateway regressions remain green

### Status

- completed

## Latest Sync: 2026-04-14 P32.34 Session Package Public-Surface Hard Refactor

## Current Execution Slice: P32.34 Session Package Public-Surface Hard Refactor (2026-04-14)

### Why This Slice Is Next

- `P32.33` confirmed that `mini_agent.session.store` was no longer the live runtime session truth
- keeping that module exported from `mini_agent.session` would keep teaching the wrong architecture
- the right next cut is a hard package-surface correction, not another large-file split

### Scope

- remove `SessionStore` / `SessionState` / `session_store` from `mini_agent.session`
- delete `src/mini_agent/session/store.py`
- replace legacy store tests with:
  - session package public-surface regression coverage
  - direct `SessionPersistence` contract coverage
- update active structure docs so the current session boundary is explicit

### Acceptance

- `mini_agent.session` exports only live owners:
  - persistence
  - projections
  - conversation binding
- no live source/test path imports the deleted legacy store surface
- targeted session/runtime/gateway regressions remain green

### Status

- completed

## Latest Sync: 2026-04-14 P32.33 Session Store Canonical Ownership Audit

## Current Execution Slice: P32.33 Session Store Canonical Ownership Audit (2026-04-14)

### Why This Slice Is Next

- after `P32.32`, the next suspicious structure problem was no longer just a large file
- it was a package-level ownership contradiction:
  - `src/mini_agent/session/__init__.py` still presents `SessionStore` / `SessionState` as canonical
  - the live runtime already uses `MainAgentSessionState` plus runtime-owned persistence/hydration handlers
- the goal of this slice is to verify whether `mini_agent.session.store` is still active infrastructure or a misleading second session truth

### Scope

- audit all live `src/` imports of:
  - `SessionStore`
  - `SessionState`
  - `session_store`
- compare `session/store.py` responsibilities against:
  - `runtime/session_state.py`
  - `runtime/session_runtime_persistence.py`
  - `runtime/session_managed_store_handler.py`
- decide whether the next hard refactor should target:
  - `session/store.py` public positioning
  - or another runtime module instead

### Acceptance

- a clear keep/demote/delete direction is recorded for `SessionStore`
- the real session truth is explicitly named in active docs
- the next physical-structure cut is chosen based on ownership, not line count

### Status

- completed

## Latest Sync: 2026-04-14 P32 Runtime Session Memory Command Boundary Audit

## Current Execution Slice: P32.32 Runtime Session Memory Command Boundary Audit (2026-04-14)

### Why This Slice Is Next

- after `P32.31`, the next suspicious large owner in the physical-structure cleanup was:
  - `src/mini_agent/runtime/session_memory_command_handler.py`
- unlike `OperationsUseCases`, this module sits in a valid runtime domain, so the question is not "can it be split" but "should it be split"
- the audit goal is to avoid another fake cleanup that only produces thin shells and weaker ownership

### Scope

- inspect the command families handled by `RuntimeSessionMemoryCommandHandler`
- verify how it is composed into runtime/session operator flows
- check maintained tests that exercise runtime memory, durable memory, and mutation paths
- decide whether this is a real mixed-responsibility module or one cohesive command-domain owner

### Acceptance

- a clear keep/split decision is recorded
- if the answer is "keep", the concrete reasons are documented
- if any smaller future-safe cleanup exists, it is recorded separately from a hard split

### Status

- completed

## Latest Sync: 2026-04-14 P32 Operations Provider/Memory Use-Case Split

## Current Execution Slice: P32.31 Operations Provider/Memory Use-Case Split (2026-04-14)

### Why This Slice Is Next

- after `P32.30`, the next high-value physical-structure target was explicitly identified
- `src/mini_agent/application/operations_use_cases.py` still mixed:
  - provider/model admin flows
  - memory admin flows
  - path/policy resolution helpers
- unlike some other large modules, this was a real ownership blend, not just file size
### Scope

- extract shared path/policy resolution into a dedicated application helper
- split provider/model operations into their own application use-case module
- split memory operations into their own application use-case module
- rewire gateway ops transport to inject/use the separated dependencies
- replace the old mixed `OperationsUseCases` surface instead of keeping a compatibility shell

### Acceptance

- `application/` no longer exposes one mixed ops owner for provider/model + memory
- gateway ops routes keep the same HTTP contract while depending on separated use-case owners
- tests cover the split at unit and gateway-contract levels
- active docs record the new ownership so future cleanup does not drift back

### Status

- completed

## Latest Sync: 2026-04-14 P32 Operations/Memory Boundary Audit After Catalog Path Consolidation

## Current Execution Slice: P32.30 Operations/Memory Boundary Audit After Catalog Path Consolidation (2026-04-14)

### Why This Slice Is Next

- after `P32.29`, one small runtime cleanup still remained:
  - `RuntimeSessionCatalogHandler` still owned its own workspace path-key helper instead of using the shared runtime path seam
- once that was cleaned, the next question was no longer runtime-manager residue
- it was "which of the remaining large modules is actually mixing responsibilities, and which is just large?"

### Scope

- unify `RuntimeSessionCatalogHandler` path-key logic to `workspace_path_utils.py`
- audit:
  - `OperationsUseCases`
  - `RuntimeSessionMemoryCommandHandler`
- record which one is the real next refactor target

### Acceptance

- session catalog dedupe logic uses the shared workspace path seam
- the next meaningful post-`P32.29` target is explicitly identified
- active docs capture the conclusion so later slices do not drift

### Status

- completed

## Latest Sync: 2026-04-14 P32 Application Managed Session Turn Extraction

## Current Execution Slice: P32.29 Application Managed Session Turn Extraction (2026-04-14)

### Why This Slice Is Next

- after the runtime-side cleanup, the next worthwhile physical-structure issue moved back up into `application/`
- `session_service.py` still co-located two different responsibilities:
  - `SessionApplicationService`
  - `ManagedSessionTurn`
- `ManagedSessionTurn` is not the service itself
- it is an application-layer turn lease / scoped session object, and keeping it inside the service file made the service module look broader than it really is

### Scope

- move `ManagedSessionTurn` into its own application module
- update application orchestrators and exports to import it from the new canonical home
- keep `SessionApplicationService` focused on session-facing application operations

### Acceptance

- `SessionApplicationService` no longer physically owns the `ManagedSessionTurn` type
- application turn/chat executors import the turn lease from its dedicated module
- focused application/runtime/gateway regression remains green

### Status

- completed

## Latest Sync: 2026-04-14 P32 Runtime Session Snapshot Builder Extraction

## Current Execution Slice: P32.28 Runtime Session Snapshot Builder Extraction (2026-04-14)

### Why This Slice Is Next

- after `P32.27`, `RuntimeSessionReadModelBuilder` still mixed two adjacent but distinct responsibilities:
  - summary/detail/message/recovery read models
  - snapshot export construction
- that made the read-model builder broader than its name and ownership suggested
- snapshot export already had a routing owner in `RuntimeSessionSnapshotHandler`, so the natural next cut was a dedicated snapshot builder seam

### Scope

- extract `build_session_snapshot(...)` and `build_session_snapshot_from_record(...)` into `RuntimeSessionSnapshotBuilder`
- wire snapshot export routing through the new builder
- leave summary/detail/recovery read-model logic in `RuntimeSessionReadModelBuilder`

### Acceptance

- snapshot export no longer lives inside `RuntimeSessionReadModelBuilder`
- snapshot handler consumes a dedicated snapshot builder seam
- focused runtime/surface/session/gateway regression remains green

### Status

- completed

## Latest Sync: 2026-04-14 P32 Runtime Workspace Path Utility Consolidation

## Current Execution Slice: P32.27 Runtime Workspace Path Utility Consolidation (2026-04-14)

### Why This Slice Is Next

- after `P32.26`, the runtime-manager boundary audit showed the remaining suspicious residue was no longer large orchestration logic
- it was small duplicated utility ownership:
  - workspace-path normalization existed in multiple runtime places
  - `MainAgentRuntimeManager` still kept a `_normalize_surface(...)` pass-through shell over `normalize_surface_label(...)`
- leaving that in place would keep the manager artificially noisy even after the bigger orchestration cuts landed

### Scope

- extract shared workspace-path normalization into `runtime/workspace_path_utils.py`
- rewire runtime manager and lifecycle helpers to consume the shared path seam
- remove manager-local surface/workspace utility wrappers that no longer carry real ownership

### Acceptance

- runtime workspace path normalization has one canonical owner
- `MainAgentRuntimeManager` no longer owns path/surface helper shells
- focused runtime/surface/gateway regression remains green

### Status

- completed

## Latest Sync: 2026-04-14 P32 Runtime Session Hydration Coordinator Extraction

## Current Execution Slice: P32.26 Runtime Session Hydration Coordinator Extraction (2026-04-14)

### Why This Slice Is Next

- after `P32.25`, `main_agent_runtime_manager.py` still held two restore/hydrate private entrypoints:
  - persisted-record -> hydration payload
  - hydration payload -> managed session registration/persistence
- those methods were not really manager-specific orchestration
- they were the glue between restore logic and the managed session store boundary

### Scope

- extract a dedicated `RuntimeSessionHydrationCoordinator`
- let it own:
  - persisted-record restore routing
  - hydrated-session insertion into the managed session map
  - lineage registration
  - optional persistence after snapshot/derived hydration
- remove the manager-local restore/hydrate private methods

### Acceptance

- persisted restore / hydrate glue no longer lives as private manager methods
- session registry / managed-store callbacks use the explicit hydration seam
- focused runtime/surface/session/gateway regression remains green

### Status

- completed

## Latest Sync: 2026-04-14 P32 Runtime Session Agent Support Seam Extraction

## Current Execution Slice: P32.25 Runtime Session Agent Support Seam Extraction (2026-04-14)

### Why This Slice Is Next

- after `P32.24`, `main_agent_runtime_manager.py` still visibly owned one more cohesive helper cluster:
  - agent construction for selected/default identities
  - knowledge-base enable/apply inspection
  - sandbox-diagnostics to runtime-policy override translation
  - runtime config loading
- those helpers were used by creation, restore, control, hydration, and runtime-rebuild paths
- they belong to runtime-owned support assembly, not to the top-level manager orchestration surface

### Scope

- extract runtime-local agent/config/KB helpers into `RuntimeSessionAgentSupport`
- rewire creation, hydration, control, restore, and agent-runtime assembly to consume that seam
- add focused regression coverage for:
  - default vs selected agent build routing
  - KB state inspection/apply behavior
  - runtime config loader injection

### Acceptance

- agent/config/KB helper logic no longer lives inside `MainAgentRuntimeManager`
- runtime handlers consume an explicit support seam instead of manager helper methods
- focused runtime/surface/session/gateway regression remains green

### Status

- completed

## Latest Sync: 2026-04-14 P32 Runtime Session Model Identity Codec Extraction

## Current Execution Slice: P32.24 Runtime Session Model Identity Codec Extraction (2026-04-14)

### Why This Slice Is Next

- after `P32.23`, another cohesive helper cluster still lived inside `main_agent_runtime_manager.py`
- it owned selected/pending model identity normalization and route translation for session model selection
- those helpers are real runtime session model-identity logic, but not manager orchestration

### Scope

- extract selected/pending model identity helpers into `RuntimeSessionModelIdentityCodec`
- rewire hydration, read-model, model-selection, restore, operator, and agent-runtime assembly to consume the codec seam
- add focused codec regression coverage

### Acceptance

- selected/pending model identity helper logic no longer lives inside `MainAgentRuntimeManager`
- runtime services consume an explicit model-identity seam instead of manager helper methods
- focused runtime/surface/session/gateway regression remains green

### Status

- completed

## Latest Sync: 2026-04-14 P32 Runtime Session Payload Codec Extraction

## Current Execution Slice: P32.23 Runtime Session Payload Codec Extraction (2026-04-14)

### Why This Slice Is Next

- after `P32.22`, one large chunk of non-manager behavior still lived inside `main_agent_runtime_manager.py`
- it was the payload/message/token normalization logic used by:
  - persistence
  - hydration
  - read-model building
  - runtime restore
- those helpers were cohesive, but they were not manager orchestration

### Scope

- extract runtime payload/message/token helpers into a dedicated `RuntimeSessionPayloadCodec`
- rewire runtime diagnostics, hydration, read-model, restore, and agent-runtime handlers to consume the codec seam
- add focused codec tests for message restoration/serialization and token-state restoration

### Acceptance

- payload/message/token normalization no longer lives inside `MainAgentRuntimeManager`
- runtime services consume a dedicated codec seam instead of manager static methods
- focused runtime/surface/session/gateway regression remains green

### Status

- completed

## Latest Sync: 2026-04-14 P32 Runtime Contracts Extraction

## Current Execution Slice: P32.22 Runtime Contracts Extraction (2026-04-14)

### Why This Slice Is Next

- after the `application / session / channel` seam cleanup, the next clean runtime cut was not deeper behavior
- it was the contract surface itself:
  - `MainAgentRuntimeMode`
  - `MainAgentRuntimePolicy`
  - `MainAgentRuntimeDiagnostics`
- those types still lived inside `main_agent_runtime_manager.py`, which forced pure policy-loading code to import the manager module just to access runtime contracts

### Scope

- move runtime contracts into a dedicated runtime contracts module
- update policy loader, runtime package exports, and active tests to import contracts from the new canonical home
- keep `MainAgentRuntimeManager` focused on orchestration behavior rather than contract ownership

### Acceptance

- runtime policy/config code no longer imports the manager module just to access runtime contracts
- `main_agent_runtime_contracts.py` becomes the canonical owner of runtime mode/policy/diagnostics types
- focused runtime/gateway/surface regression remains green

### Status

- completed

## Latest Sync: 2026-04-14 P32 Main-Agent Surface Runtime Dependency Removal

## Current Execution Slice: P32.21 Main-Agent Surface Runtime Dependency Removal (2026-04-14)

### Why This Slice Is Next

- after `P32.19` and `P32.20`, `MainAgentSurfaceService` had already been narrowed to `SessionApplicationService`
- but its constructor still carried a direct `runtime_manager` dependency that the service no longer actually used
- keeping that parameter around would preserve a fake dependency in the public shape of the service

### Scope

- remove the unused `runtime_manager` dependency from `MainAgentSurfaceService`
- update gateway composition and surface-service tests to construct the service through `SessionApplicationService` only
- keep runtime-touching test helpers explicit by reaching through the injected session service instead of the surface API

### Acceptance

- `MainAgentSurfaceService` no longer imports or accepts `SessionRuntimePort`
- gateway composition constructs the surface service from the shared session service seam only
- focused surface/session/channel/gateway regression remains green

### Status

- completed

## Latest Sync: 2026-04-14 P32 Channel Ingress / Conversation Binding Port Extraction

## Current Execution Slice: P32.20 Channel Ingress / Conversation Binding Port Extraction (2026-04-14)

### Why This Slice Is Next

- after `P32.19`, the next obvious shared-boundary leak was in `ChannelIngressUseCases`
- it still depended on the concrete `ConversationBindingService` type and still encoded binding assembly assumptions in the application service boundary
- that kept remote/session reachability logic from reading like a session-owned seam

### Scope

- add a session-owned `ConversationBindingPort`
- make `ChannelIngressUseCases` depend on the port instead of the concrete binding service
- update gateway composition and tests to inject the port implementation explicitly

### Acceptance

- `ChannelIngressUseCases` no longer imports the concrete binding service type
- composition owns the concrete binding-service assembly and injects it through the port seam
- focused channel/gateway/surface/session regression remains green

### Status

- completed

## Latest Sync: 2026-04-14 P32 Main-Agent Surface / Session Service Ownership Extraction

## Current Execution Slice: P32.19 Main-Agent Surface / Session Service Ownership Extraction (2026-04-14)

### Why This Slice Is Next

- after `P32.18`, the biggest remaining `application / runtime / session` ownership leak was no longer naming
- `MainAgentSurfaceService` still constructed `SessionApplicationService` internally, which blurred a boundary we had already started cleaning in `P32.6`
- that meant host-owned assembly was partly leaking back into an application service, making the layering story harder to trust

### Scope

- make `MainAgentSurfaceService` consume an explicit injected `SessionApplicationService`
- move session-service assembly ownership into gateway composition
- update surface-service tests to follow the explicit seam and add a focused injection proof

### Acceptance

- `MainAgentSurfaceService` no longer creates `SessionApplicationService` internally
- gateway composition owns runtime-manager, session-service, and surface-service assembly as separate seams
- focused surface/session/gateway regression remains green

### Status

- completed

## Latest Sync: 2026-04-14 P32 Agent-Core Engine And Turn-Context Test Surface Realignment

## Current Execution Slice: P32.18 Agent-Core Engine / Turn-Context / Policy Test Naming Realignment (2026-04-14)

### Why This Slice Is Next

- after `P32.17`, most execution-focused test surfaces were already aligned, but the most visible engine-facing tests still carried older naming:
  - `tests/test_agent.py`
  - `tests/test_agent_turn_context.py`
  - `tests/test_agent_execution_policy.py`
- that still made the current regression surface look split between generic root-era naming and the now-canonical `agent_core` tree

### Scope

- rename the remaining engine-facing tests to `agent_core`-consistent names
- update current docs and validation references to the renamed test surfaces
- keep the change narrow to naming and references, without changing runtime behavior

### Acceptance

- engine-facing regression surfaces use `agent_core` naming
- current docs no longer instruct developers to run the removed old test paths
- focused engine/kernel regression stays green

### Status

- completed

## Latest Sync: 2026-04-14 P32 Agent-Core Naming Consistency Sweep

## Current Execution Slice: P32.17 Agent-Core Naming Consistency And Test Surface Realignment (2026-04-14)

### Why This Slice Is Next

- after `P32.1`, the physical `agent_core` tree was largely unified, but a few strong naming leaks still remained:
  - the self-improvement skill engine still lived at `agent_core/self_improve.py` instead of under the `skills/` domain it belongs to
  - execution-focused tests still carried `test_code_agent_*` names even though `code_agent/` had already been removed
  - one execution primitive still exported `CodeAgentMCPClient`, keeping the deleted old-core name alive in current APIs
- that left the tree structurally cleaner than before, but still not semantically self-consistent

### Scope

- move self-improvement skill ownership into `agent_core/skills/`
- rename execution-focused tests to `agent_core`-consistent names
- remove remaining live `CodeAgent*` naming from current agent-core execution exports
- update active docs and terminal readiness scripts to current paths

### Acceptance

- `src/mini_agent/agent_core/skills/self_improve.py` is the canonical home of the self-improvement engine
- current source/tests/scripts no longer reference the removed `code_agent` package as a live execution owner
- execution test names reflect `agent_core` ownership
- focused execution/kernel regression stays green

### Status

- completed

## Latest Sync: 2026-04-14 P32 Gateway Ops Transport Dependency Pattern Unification

## Current Execution Slice: P32.16 Gateway Ops Transport DI Pattern Unification (2026-04-14)

### Why This Slice Is Next

- after `P32.13`/`P32.14`/`P32.15`, most gateway transport and host concerns were already split cleanly, but one inconsistency still remained:
  - `src/apps/agent_studio_gateway/main_agent_router.py` already used explicit injected dependencies and a router factory
  - `src/apps/agent_studio_gateway/ops_router.py` still behaved like a module-global singleton router with hidden service ownership
- that meant the gateway transport layer still taught two different patterns for the same responsibility
- the next correct cut was to make ops transport follow the same dependency-injected router-factory pattern as the main-agent transport

### Scope

- introduce an explicit ops-router dependency object
- make `ops_router.py` export `create_ops_router(...)` instead of a module-global router singleton
- keep host-owned service construction in `src/apps/agent_studio_gateway/main.py`
- update gateway tests to patch the host-owned operations use-case assembly instead of transport-module globals

### Acceptance

- `src/apps/agent_studio_gateway/ops_router.py` owns only ops HTTP contract translation plus router-factory wiring
- `src/apps/agent_studio_gateway/main.py` owns `GATEWAY_OPERATIONS_USE_CASES` and mounts `create_ops_router(...)`
- gateway transport routers now use one consistent DI/factory pattern across main-agent and ops surfaces
- focused gateway regression stays green

### Status

- completed

## Latest Sync: 2026-04-13 P32 Gateway Static Host Extraction

## Current Execution Slice: P32.15 Studio Static Host / SPA Fallback Extraction (2026-04-13)

### Why This Slice Is Next

- after `P32.14`, `main.py` had become much thinner, but it still directly owned the browser-hosting details:
  - workspace file mount
  - Studio dist resolution
  - `/assets` mounting
  - root index route
  - SPA fallback route
  - dist-missing fallback response
- that kept frontend hosting policy mixed into the gateway entrypoint

### Scope

- add a dedicated static-host module for Studio/browser serving
- move dist resolution and SPA fallback route registration out of `main.py`
- keep the gateway entrypoint as a thin assembly module

### Acceptance

- `src/apps/agent_studio_gateway/static_host.py` owns Studio static hosting and SPA fallback wiring
- `src/apps/agent_studio_gateway/main.py` only assembles the host and calls the static-host configurator
- focused static-host and gateway regression stays green

### Status

- completed

## Latest Sync: 2026-04-13 P32 Gateway Composition Extraction

## Current Execution Slice: P32.14 Runtime / Service Composition Builder Extraction (2026-04-13)

### Why This Slice Is Next

- after `P32.13`, `main.py` already stopped owning most HTTP transport, but it still directly owned:
  - runtime-manager construction
  - surface-service construction
  - channel-ingress construction
  - bootstrap error formatting / SSE helpers / workspace resolution
  - gateway startup/shutdown lifecycle cleanup
- that meant the entry module was thinner, but still not a clean host entrypoint

### Scope

- add an explicit gateway composition module for runtime/service/lifecycle wiring
- make `main.py` instantiate settings + composition and then just assemble the host
- move health/runtime diagnostics building onto the composition object
- update tests to patch the composition object instead of old module-level caches

### Acceptance

- `src/apps/agent_studio_gateway/composition.py` is the canonical runtime/service wiring home
- `src/apps/agent_studio_gateway/main.py` reads as a thin entry/assembly module
- focused gateway API + runtime matrix regression stays green

### Status

- completed

## Latest Sync: 2026-04-13 P32 Main-Agent Transport Router Extraction

## Current Execution Slice: P32.13 Gateway Main-Agent HTTP Transport Extraction (2026-04-13)

### Why This Slice Is Next

- after `P32.12`, `main.py` no longer owned the novel cluster, but it still carried the whole main-agent HTTP/SSE contract surface:
  - `/api/v1/system/health`
  - `/api/v1/ops/diagnostics/*`
  - `/api/v1/agent/*`
  - `/api/v1/channel/message`
- that meant the composition root still doubled as a route business layer
- the next correct cut was to move protocol translation out of `main.py` while keeping service/runtime wiring in the composition root

### Scope

- add a dedicated gateway transport router for main-agent/session/channel routes
- make `main.py` mount that router instead of declaring those endpoints inline
- keep external API paths and test contracts stable

### Acceptance

- `src/apps/agent_studio_gateway/main_agent_router.py` owns the main-agent HTTP/SSE transport contract
- `src/apps/agent_studio_gateway/main.py` keeps composition, lifecycle, static mounting, and service wiring only
- existing gateway API regression remains green

### Status

- completed

## Latest Sync: 2026-04-13 P32 Novel Transport / Runtime Ownership Realignment

## Current Execution Slice: P32.12 Novel Transport Extraction From Gateway Main (2026-04-13)

### Why This Slice Is Next

- after `P32.11`, `ops` transport naming was corrected, but `src/apps/agent_studio_gateway/main.py` still owned a large novel-only cluster:
  - profile/env parsing
  - project path helpers
  - chapter history/version helpers
  - novel use-case factory wiring
  - `/api/v1/novel/*` route handlers
- leaving that cluster in the composition root kept teaching the wrong ownership story:
  - `main.py` looked like a second business layer
  - the existing `subprograms/novel_generator/gateway/router.py` stayed stale and duplicated
  - `mini_agent.novel` still lacked a canonical runtime wiring home

### Scope

- move novel runtime wiring into `src/mini_agent/novel/runtime.py`
- upgrade `src/subprograms/novel_generator/gateway/router.py` into the maintained novel HTTP transport
- mount the subprogram router from `src/apps/agent_studio_gateway/main.py`
- keep `/api/v1/novel/*` external contracts and channel novel-action behavior stable

### Acceptance

- `src/apps/agent_studio_gateway/main.py` no longer owns novel-specific route handlers or wiring helpers
- `src/subprograms/novel_generator/gateway/router.py` is the maintained novel transport surface
- `src/mini_agent/novel/runtime.py` is the canonical runtime wiring home for novel use cases
- focused regression for gateway novel endpoints and channel novel dispatch stays green

### Status

- completed

## Latest Sync: 2026-04-13 P32 Gateway Ops Router Neutralization

## Current Execution Slice: P32.11 Ops Router Naming Realignment (2026-04-13)

### Why This Slice Is Next

- after `P32.10`, the service seam was already neutralized, but the gateway transport file still advertised paused `Studio` ownership:
  - `src/apps/agent_studio_gateway/ops_router.py`
  - `tests/test_agent_studio_gateway_ops_router.py`
- that is smaller than the previous ownership cuts, but it still matters because transport/module names teach where future code gets added
- if left unchanged, the repo would still imply that `/api/v1/ops` is a Studio-private route set instead of a maintained shared ops transport surface

### Scope

- rename `studio_router.py` to `ops_router.py`
- rename internal auth and route symbols from `studio_*` to `ops_*`
- keep `/api/v1/ops` external contracts and existing auth env behavior stable
- sync active docs and focused tests to the new router name

### Acceptance

- gateway ops transport file path is `src/apps/agent_studio_gateway/ops_router.py`
- maintained tests point at `tests/test_agent_studio_gateway_ops_router.py`
- gateway composition imports `ops_router` / `_require_ops_auth`
- focused regression stays green after the rename

### Status

- completed

## Latest Sync: 2026-04-13 P32 Session/Novel Ownership + Operations Seam Neutralization

## Current Execution Slice: P32.9-P32.10 Shared Ownership Realignment (2026-04-13)

### Why This Slice Is Next

- `P32.8` cleaned up transport ownership, but two misleading ownership pockets still remained:
  - remote conversation binding still looked application-owned even though it is session-domain reachability state
  - `StudioOpsUseCases` still made a shared provider/memory service look like one surface's private backend
- leaving those names in place would keep teaching the wrong repository story:
  - `session` would look incomplete as the canonical remote binding home
  - `application` would still look partially owned by the paused browser/Studio surface
- the right next cut is therefore another hard physical ownership correction, not a new feature slice

### Scope

- move remote conversation binding service into `src/mini_agent/session/`
- extract novel profile/service ownership out of `src/mini_agent/application/` into `src/mini_agent/novel/`
- rename the shared provider/memory ops seam to surface-neutral ownership
- keep `/api/v1/ops` transport contracts stable while correcting internal ownership and names

### Acceptance

- `session/` is the obvious home for remote conversation binding lookup/persistence service code
- `novel/` is the obvious home for novel-specific profile/use-case code
- `application/` no longer advertises a Studio-owned shared ops service
- focused regression for gateway ops, channel ingress, and novel paths stays green

### Status

- completed

## Latest Sync: 2026-04-13 DesktopUI Freeze And Service-Layer Return

## Current Execution Slice: Application Service Seam Hardening Return (2026-04-13)

### Why This Slice Is Next

- DesktopUI has crossed the minimum usable threshold:
  - it can launch
  - it can attach/start local gateway
  - it can create/select/fork sessions
  - it can stream replies and show operator activity
- the latest閻喍姹夐懕鏃囩殶 also confirmed the current bottleneck is no longer "missing frontend shell"
- the bigger risk is now architectural:
  - core/service seams are still not reduced enough
  - frontend polishing can easily start compensating for backend boundary debt
  - that would make later CLI / TUI / DesktopUI / Remote convergence harder, not easier
- so the right move is:
  - freeze DesktopUI at the current first-usable cut
  - return to service-layer / application-layer refactor
  - continue strengthening the core before spending more effort on front-end polish

### What This Decision Means

- DesktopUI is **not** abandoned
- DesktopUI is now treated as:
  - first usable graphical shell
  - paused for deeper visual/interaction polishing
  - limited to break-fix only until the core/service layer is in a better state
- active development focus returns to:
  - shared application services
  - gateway/use-case seam reduction
  - surface-neutral orchestration
  - runtime/session/service boundary cleanup

### Scope

- continue shrinking transport-owned orchestration out of gateway-facing layers
- keep `MainAgentSurfaceService` and adjacent shared application services as the canonical top seam
- reduce duplicated or surface-specific orchestration still living in:
  - gateway route composition
  - TUI-side application behavior
  - remote-adapter convenience paths
- prefer service/core correctness over new frontend affordances

### Out Of Scope

- no more DesktopUI visual polishing for now
- no DesktopUI feature expansion beyond break-fix
- no browser WebUI revival

### Acceptance

- the next refactor slices clearly improve service-layer boundaries
- shared behaviors move toward one application/service implementation instead of per-surface copies
- DesktopUI / TUI / remote adapters remain consumers of the same service seam rather than regaining business ownership

### Next Concrete Targets

- continue reducing `MainAgentGatewayUseCases` toward transport composition instead of top-level orchestration ownership
- audit remaining surface-shared flows that still branch in surface adapters before reaching the application layer
- prioritize seams that affect all entrances:
  - session lifecycle
  - turn execution orchestration
  - model / approval / control routing
  - remote-binding normalization

### What Just Landed In This Slice

- canonical service implementation now lives in:
  - src/mini_agent/application/main_agent_surface_service.py
- shared service callable aliases now live in:
  - src/mini_agent/application/surface_service_types.py
- legacy src/mini_agent/application/main_agent_gateway_use_cases.py is now only a thin compatibility export
- gateway app composition no longer keeps _MAIN_AGENT_USE_CASES
- targeted regression passed:
  - uv run pytest tests/test_main_agent_surface_service.py tests/test_agent_studio_gateway_api_v1.py
  - result: 95 passed

### Refactor Focus After This Cut

- application binding is now the shared normalization seam for session operators and remote binding lookups

- runtime policy / lifecycle policy loading has now been moved out of gateway main into a shared runtime loader seam

- keep shrinking remaining gateway-* naming/ownership that still represents shared application behavior instead of transport behavior
- inspect whether the next safest slice is:
  - session lifecycle service extraction
  - model / approval / control application routing cleanup
  - remote-binding normalization at the application seam

### Status

- in_progress

## Latest Sync: 2026-04-13 P31.4 Desktop Session Ops And Activity Shell

## Current Execution Slice: P31.4 Desktop Core Shell Expansion (2026-04-13)

### Why This Slice Is Next

- the DesktopUI path now has a real executable bootstrap
- local gateway ownership is no longer ambiguous for the desktop entrance
- the next useful move is therefore no longer host bootstrapping
- it is shell quality and operator flow shaping on top of the working host connection

### What Just Landed

- `mini-agent desktop` is now a real CLI entrance
- DesktopUI now has:
  - local gateway attach/start supervision
  - a minimal `PySide6` bootstrap path
  - a first working window that reads:
    - runtime health
    - session list
    - session detail
    - managed gateway log excerpts
- DesktopUI now also has the first actual operator path:
  - create/select session
  - main conversation area
  - prompt composer
  - streamed assistant reply rendering
  - activity pane updates from gateway stream events
- DesktopUI now also has first operator controls beyond chatting:
  - session-scoped model switch
  - approval dialog handling
  - minimal command palette
- DesktopUI now also has first session-operator controls:
  - rename selected session
  - share / unshare selected session
  - fork selected session
  - compact selected session
- DesktopUI has now absorbed the first閻喍姹夐懕鏃囩殶 corrections:
  - `New Session` follows current runtime capacity constraints more naturally by creating a blank derived session when a current session already exists
  - desktop client timeout budget is no longer unrealistically low for operator actions
  - layout pressure is being pushed back toward the center conversation area
- DesktopUI activity rendering is no longer only a raw append-only log:
  - stream events are normalized into structured operator activity entries
  - the activity pane now renders those entries as compact cards
- the desktop refresh path now avoids duplicate session-detail loads while restoring selection
- runtime entrance normalization now includes `desktop` as a first-class local surface
- the DesktopUI bootstrap still reuses the existing local gateway transport instead of inventing a second backend seam

### Scope

- improve the DesktopUI shell from bootstrap-grade to first operator-usable shell
- keep session truth in the shared runtime/gateway layer
- continue building DesktopUI as a real separate frontend rather than a TUI wrapper
- harden first-use operator ergonomics before widening into richer desktop-only affordances

### Out Of Scope

- no browser-first WebUI revival
- no direct session ownership inside DesktopUI
- no remote-channel expansion in this slice

### Acceptance

- DesktopUI shell grows beyond bootstrap-only visibility
- session/work activity presentation becomes more usable
- DesktopUI keeps consuming shared gateway contracts without adding backend ownership drift
- session operations remain thin UI calls over shared gateway/session APIs instead of creating desktop-owned state

### Remaining Focus In This Slice

- keep improving conversation/task rendering quality
- add more runtime/session controls only when they can still reuse existing shared contracts
- avoid drifting into desktop-owned backend semantics while the shell grows
- keep using閻喍姹夐懕鏃囩殶 findings to tighten shell behavior before adding richer desktop-only features

### Status

- in_progress

## Latest Sync: 2026-04-13 P31.2 Thin Application Seam Hardening Landed

## Current Execution Slice: P31.3 Desktop Runtime Host Integration Prep (2026-04-13)

### Why This Slice Is Next

- the thin `application service seam` is now landed enough for the desktop path to build on
- the shared top interaction owner is no longer only expressed as `gateway`-owned behavior
- the next useful move is therefore no longer naming correction
- it is host/bootstrap preparation for DesktopUI

### What Just Landed

- canonical shared service is now `MainAgentSurfaceService`
- surface-neutral chat flow types now exist:
  - `SurfaceChatExecutionRequest`
  - `SurfaceChatExecutionResult`
  - `SurfaceChatStreamEvent`
  - `SurfaceChatFlowHandler`
- execution helpers are now also surface-oriented:
  - `AgentTurnExecutionHandler`
  - `AgentRouteExecutionHandler`
- gateway now resolves its shared top service through `_main_agent_surface_service()`
- compatibility aliases remain in place only where they reduce immediate breakage during the transition

### Scope

- prepare the desktop host/bootstrap slice on top of the corrected seam
- keep gateway as the first DesktopUI transport/backend
- avoid slipping new business logic back into gateway route handlers

### Out Of Scope

- no DesktopUI visual shell yet in this planning sync
- no browser Studio revival
- no remote-adapter expansion

### Acceptance

- active planning now treats `P31.2` as landed
- the next implementation anchor is DesktopUI host/bootstrap prep instead of more gateway naming churn

### Status

- in_progress

## Latest Sync: 2026-04-13 P31 DesktopUI(PySide6) Decision Freeze

## Current Execution Slice: P31 DesktopUI(PySide6) Seam-First Kickoff (2026-04-13)

### Why This Slice Is Next

- the user chose the desktop-window direction instead of reviving browser-first work as the primary graphical path
- the recommended option is now frozen as:
  - separate `PySide6 DesktopUI`
  - not TUI-to-desktop mapping
  - not browser `WebUI` mainline continuation
- the current codebase is close to reusable enough for DesktopUI work
- but one drift risk still remains:
  - the shared top orchestration is still named/shaped too much around `gateway`
- if UI work starts before that thin seam is corrected, the desktop path is likely to inherit transport-owned semantics as if they were the real service boundary

### Scope

- freeze `DesktopUI(PySide6)` as the canonical third maintained entrance
- downgrade browser `WebUI` to paused compatibility/prototype status
- record the execution rule:
  - first thin `application service seam` hardening
  - then reuse the existing gateway transport for DesktopUI
- define the implementation order so the next code slice does not drift

### Out Of Scope

- no browser Studio revival
- no TUI-to-Qt renderer wrapper
- no WeChat / Feishu work
- no large gateway rewrite
- no DesktopUI coding slice yet beyond planning/architecture sync

### Files In Scope

- `docs/P31_DESKTOPUI_PYSIDE6_TASK_PLAN_2026-04-13.md`
- `docs/ARCHITECTURE.md`
- `docs/FRAMEWORK_SKELETON.md`
- `docs/DEVELOPMENT_INDEX.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Freeze the third main graphical entrance as `DesktopUI(PySide6)`.
2. Record that browser `WebUI` is now a paused compatibility/prototype path rather than the canonical mainline.
3. Record the seam-first decision:
   - first thin `application service seam`
   - then DesktopUI on top of the existing gateway transport

### Acceptance

- architecture docs no longer present browser `WebUI` as the primary graphical mainline
- the execution order is explicit and does not encourage direct UI work on top of gateway-owned orchestration names
- the next coding slice is clearly identified as seam-first rather than UI-first

### Status

- in_progress

## Latest Sync: 2026-04-13 P30.5 Near-Close + Remote Interaction Scope Correction

## Current Execution Slice: P30 Remote Interaction Active Scope Freeze (2026-04-13)

### Why This Slice Is Next

- `P30.5` has now reached a natural stop point:
  - shared interaction binding is converged
  - runtime live-state write paths are aligned
  - even the lower-level direct-call guardrail is now in place
- the next useful planning correction is scope, not a new implementation hotspot
- `P30.5` is now near-closed
- and the user clarified an important delivery constraint:
  - `WeChat` is not part of the current actual implementation plan
  - it should be treated only as future extension
- that means the active remote entrance path should be documented as:
  - `QQ` = current concrete implementation
  - `WeChat / Feishu` = future extension targets only

### Scope

- correct the active plan so it does not accidentally elevate `WeChat` into the current delivery roadmap
- freeze the remote entrance wording as:
  - `QQ` active
  - `WeChat / Feishu` future extension only
- keep the architecture open for future remote-adapter reuse without turning those adapters into active implementation commitments

### Out Of Scope

- no `WeChat` implementation work
- no `Feishu` implementation work
- no `WebUI` work while browser delivery remains paused

### Files In Scope

- `docs/ARCHITECTURE.md`
- `docs/FRAMEWORK_SKELETON.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `docs/P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Freeze `P30.5` as near-closed unless a fresh shared-entrance drift appears.
2. Remove the mistaken implication that `WeChat` is the next active implementation slice.
3. Record the correct current delivery scope for `Remote Interaction`.

### Acceptance

- active planning explicitly treats `P30.5` as near-closed
- active remote delivery scope is documented as `QQ` only
- `WeChat / Feishu` remain future extension targets, not active execution slices

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 Interaction-Surface Direct-Call Guardrail

## Current Execution Slice: P30.5 Interaction-Surface Direct-Call Guardrail (2026-04-13)

### Why This Slice Is Next

- after the runtime live-state convergence cut, the active production callers were already clean
- but one low-level guardrail was still missing:
  - `resolve_interaction_surface(None, "qqbot")`
  - still returned the old surface fallback shape
- that no longer broke current production paths
- but it still left a future footgun for any new direct caller

### Scope

- harden `resolve_interaction_surface(...)` itself for:
  - missing explicit `surface`
  - concrete remote `channel_type`
- add direct regression coverage for that exact case
- confirm broader session/gateway/channel regressions still stay green

### Out Of Scope

- no new session/read-model policy change
- no entrance contract rewrite
- no persistence schema change

### Files In Scope

- `src/mini_agent/runtime/interaction_surface.py`
- `tests/test_interaction_surface.py`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Make `resolve_interaction_surface(...)` resolve remote `channel_type` as the concrete surface when explicit `surface` is absent.
2. Add a direct regression test for `surface=None, channel_type=\"qqbot\"`.
3. Re-run focused and broader binding/session regressions.

### Acceptance

- `resolve_interaction_surface(None, \"qqbot\")` resolves to remote `qq`
- current higher-level shared binding behavior remains unchanged
- broader regressions remain green

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 Runtime Live-State Remote Binding Convergence

## Current Execution Slice: P30.5 Runtime Live-State Remote Binding Convergence (2026-04-13)

### Why This Slice Is Next

- after the shared interaction-binding seam and the default-surface precedence fix landed, one deeper drift point still remained
- some runtime/application layers were still writing session projection or transcript state through older surface-only normalization
- that meant a request shape like:
  - missing explicit `surface`
  - remote `channel_type="qqbot"` / `qq`
- could still be recorded too low in the stack with old fallback semantics instead of the shared remote binding result

### Scope

- reuse shared interaction binding inside runtime live-state mutation paths
- make remote alias + missing-surface handling consistent for:
  - session projection binding
  - transcript message writes
  - activity transcript writes
  - remote conversation binding lookup
  - gateway agent execution metadata shaping
- lock the behavior with focused runtime/session regression tests

### Out Of Scope

- no entrance taxonomy rewrite
- no persisted snapshot schema change
- no new remote adapter feature work

### Files In Scope

- `src/mini_agent/runtime/session_live_state_handler.py`
- `src/mini_agent/application/gateway_agent_execution_handler.py`
- `src/mini_agent/application/remote_conversation_binding_service.py`
- `tests/test_session_service.py`
- `tests/test_channel_ingress_use_cases.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Reuse shared interaction binding inside runtime live-state surface/message/activity writes.
2. Reuse the same binding seam in remote conversation binding lookup and gateway execution metadata shaping.
3. Add regression coverage for remote alias + missing-surface cases.
4. Re-run focused session/gateway/channel regression coverage.

### Acceptance

- remote requests with `channel_type=qq*` and no explicit `surface` are recorded as `qq`, not `api`
- session projection, transcript messages, and activity transcript entries stay aligned on the same resolved remote surface
- remote alias binding reuse remains stable across channel ingress and gateway/runtime paths
- focused plus broader regression coverage remains green

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 Default-Surface Override Fix For Remote Bindings

## Current Execution Slice: P30.5 Default-Surface Override Fix For Remote Bindings (2026-04-13)

### Why This Slice Is Next

- after the shared interaction-binding convergence landed, one follow-up audit revealed a real remaining bug
- `SessionSurfaceBinding.from_request(...)` still pre-applied `default_surface`
- that meant:
  - requests without explicit `surface`
  - but with remote `channel_type`
  - could still be forced to `"tui"` before the shared resolver saw them
- that is not just duplication; it is wrong ownership of precedence

### Scope

- stop `SessionSurfaceBinding.from_request(...)` from overriding remote channel inference with the caller default
- let the shared interaction resolver decide precedence in the intended order:
  - explicit surface
  - channel type
  - default surface
- lock the behavior with direct session-service and remote-session-service tests

### Out Of Scope

- no change to local create-session defaults
- no change to persisted session projection semantics
- no surface taxonomy rewrite

### Files In Scope

- `src/mini_agent/application/session_service.py`
- `tests/test_session_service.py`
- `tests/test_session_remote_service.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Remove pre-resolution default-surface overriding in `SessionSurfaceBinding.from_request(...)`.
2. Add direct coverage for remote channel winning over `default_surface="tui"`.
3. Re-run session/gateway/TUI regression coverage.

### Acceptance

- request bindings with `channel_type=qq*` and no explicit surface resolve to remote `qq`, not `tui`
- local default-surface behavior still works when no remote channel is present
- focused plus broader session/gateway/TUI regressions remain green

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 Shared Interaction Binding Convergence

## Current Execution Slice: P30.5 Shared Interaction Binding Convergence (2026-04-13)

### Why This Slice Is Next

- after the `P30.7` re-audit, the next useful work was no longer manager decomposition by inertia
- the more immediate drift risk was smaller but more dangerous:
  - chat entry requests already normalized `surface/channel_type` through one shared path
  - shared-session mutation/control requests still had their own raw binding handling
  - the TUI gateway client had a third, even thinner but different normalization path
- that kind of split invites silent entrance drift on:
  - remote alias handling
  - trimmed binding metadata
  - default-surface semantics

### Scope

- add one shared interaction-binding normalization seam
- rewire application shared-session bindings through that seam
- rewire the TUI gateway client binding payloads through that seam
- preserve the current rule that missing `surface` should stay unset unless a real source/default exists

### Out Of Scope

- no session truth redesign
- no remote adapter behavior redesign
- no `origin_surface` / `active_surface` semantic rewrite

### Files In Scope

- `src/mini_agent/runtime/interaction_surface.py`
- `src/mini_agent/application/interaction_request_adapter.py`
- `src/mini_agent/application/session_service.py`
- `src/mini_agent/tui/gateway_client.py`
- `tests/test_interaction_surface.py`
- `tests/test_interaction_request_adapter.py`
- `tests/test_session_service.py`
- `tests/test_tui_gateway_client.py`
- `tests/test_session_remote_service.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Add one shared normalized interaction-binding helper.
2. Rewire chat/application binding construction to consume the same helper.
3. Rewire shared-session operation bindings and the TUI gateway client through the same helper.
4. Lock alias/default behavior with focused tests, then re-run broader session/gateway/TUI regressions.

### Acceptance

- chat and shared-session operations no longer normalize interaction bindings through separate local rules
- TUI gateway payloads no longer preserve raw adapter aliases like `qqbot` while the runtime expects normalized `qq`
- empty surface inputs do not get forced into fake values for session mutations
- focused plus broader gateway/session/TUI regressions stay green

### Status

- completed

## Latest Sync: 2026-04-13 P30.7ap Runtime Manager Re-Audit + Natural Stop Check

## Current Execution Slice: P30.7ap Runtime Manager Re-Audit + Natural Stop Check (2026-04-13)

### Why This Slice Is Next

- after the three post-audit behavior cuts landed, the next question was no longer "what should we extract next?"
- the better question was "has `P30.7` reached a natural stop?"
- without that explicit re-audit, it would be too easy to keep refactoring by inertia instead of by ownership need

### Scope

- re-scan the runtime manager method surface after the recent extractions
- distinguish:
  - long but acceptable composition wiring
  - thin facade methods with parameter-heavy signatures
  - any remaining mixed-responsibility hotspots
- remove any truly dead residual helper shells found during the audit

### Out Of Scope

- no new large extraction track in this slice
- no runtime behavior redesign
- no contract changes

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Re-quantify current runtime-manager method distribution.
2. Re-check the remaining larger methods against their current bodies.
3. Remove any dead residual helper shells if they are truly unused.
4. Record whether `P30.7` should continue or naturally stop here.

### Acceptance

- `P30.7` continuation is justified by ownership evidence, not inertia
- dead residual helper shells are removed if found
- active notes clearly state whether runtime-manager decomposition should pause

### Status

- completed

## Latest Sync: 2026-04-13 P30.7ao Lineage Registry Helper Extraction

## Current Execution Slice: P30.7ao Lineage Registry Helper Extraction (2026-04-13)

### Why This Slice Is Next

- after the model-selection and derived-session cuts, the remaining manager-owned hotspot from the audit was lineage graph mutation
- the runtime manager still owned:
  - lineage root resolution
  - node registration/update rules
  - node removal routing
- that logic was runtime-private and cohesive enough for one small helper extraction

### Scope

- move lineage registration/removal rules into a dedicated runtime lineage helper
- keep the existing `runtime._session_lineage` store object visible for current test and debug seams
- keep manager behavior unchanged outside of delegation to the helper

### Out Of Scope

- no lineage DTO changes
- no persistence schema changes
- no session ancestry behavior redesign

### Files In Scope

- `src/mini_agent/runtime/session_lineage_registry.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Add one runtime lineage helper around `SessionLineageStore`.
2. Rewire manager registration/removal flows through the helper.
3. Preserve the existing `_session_lineage` observation seam.
4. Re-run lineage/derived-session plus broader runtime/session/TUI verification.

### Acceptance

- lineage graph mutation rules no longer live inline in `MainAgentRuntimeManager`
- existing lineage behavior and test seams remain intact
- runtime/session/TUI verification remains green

### Status

- completed

## Latest Sync: 2026-04-13 P30.7an Derived Session Creation Extraction

## Current Execution Slice: P30.7an Derived Session Creation Extraction (2026-04-13)

### Why This Slice Is Next

- after the model-selection cut, `create_derived_session(...)` was the clearest remaining manager method still assembling a non-trivial runtime payload inline
- it was still deciding:
  - how to inherit the parent session's selected model
  - how to inherit context/sandbox state
  - how to shape lineage metadata for the child
- that belongs with session creation/registry + hydration code, not the outer runtime facade

### Scope

- move derived-session payload assembly into the hydration builder
- move derived-session creation orchestration into the session registry handler
- keep parent lookup under the manager's `_store_lock`
- unify direct `create_session(...)` session-id allocation with the existing allocator

### Out Of Scope

- no derived-session behavior redesign
- no delegation UX changes
- no lineage schema changes

### Files In Scope

- `src/mini_agent/runtime/session_hydration_builder.py`
- `src/mini_agent/runtime/session_registry_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Add one hydration-builder method for derived-session payload inheritance.
2. Add one registry-handler method for derived-session creation.
3. Rewire manager `create_derived_session(...)` into lock + parent lookup + delegation only.
4. Reuse the runtime session-id allocator for direct `create_session(...)`.
5. Re-run derived-session/delegation plus broader runtime/session/TUI verification.

### Acceptance

- `MainAgentRuntimeManager.create_derived_session(...)` no longer assembles inherited payload state inline
- derived-session creation now lives with session registry/hydration code
- direct session creation uses the same allocator path as the rest of runtime session creation
- runtime/session/TUI verification remains green

### Status

- completed

## Latest Sync: 2026-04-13 P30.7am Model Selection Request Resolution Extraction

## Current Execution Slice: P30.7am Model Selection Request Resolution Extraction (2026-04-13)

### Why This Slice Is Next

- the runtime hotspot audit identified `update_session_model_selection(...)` as the smallest remaining operator-facing method that still owned real request semantics
- specifically, the manager was still deciding:
  - whether `provider_source` was missing
  - how to infer it
  - how to convert inference failure into operator-facing `400` responses
- that belongs with model-selection request semantics, not the outer runtime coordinator

### Scope

- move `provider_source` inference and request normalization into the model-selection handler
- let the runtime manager stop interpreting model-selection requests locally
- keep session lookup, runtime application, and operator-visible behavior unchanged

### Out Of Scope

- no model registry redesign
- no session rebuild behavior changes
- no DTO or gateway contract changes

### Files In Scope

- `src/mini_agent/runtime/session_model_selection_handler.py`
- `src/mini_agent/runtime/session_operator_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Add one model-selection handler entrypoint that resolves/infers a concrete request identity.
2. Rewire operator model-selection updates through that handler-owned resolution path.
3. Remove manager-local `provider_source` inference.
4. Re-run focused plus broader runtime/session/TUI verification.

### Acceptance

- `MainAgentRuntimeManager.update_session_model_selection(...)` no longer infers `provider_source` itself
- model-selection request resolution lives with the model-selection handler
- inferred-source behavior and failure semantics remain green in runtime/session/TUI verification

### Status

- completed

## Latest Sync: 2026-04-13 P30.7al Runtime Hotspot Audit

## Current Execution Slice: P30.7al Runtime Hotspot Audit (2026-04-13)

### Why This Slice Is Next

- after removing the obvious file-top residue from `MainAgentRuntimeManager`, the next risk was refactoring by line count instead of by ownership
- before opening another implementation slice, the runtime manager needed a fresh audit to separate:
  - long-but-acceptable composition wiring
  - genuinely mixed remaining behavior hotspots

### Scope

- inspect the current runtime manager method surface after the persistence + session-state extractions
- compare the remaining larger methods against already-extracted runtime handlers
- identify which remaining logic still belongs outside the manager
- record any correctness inconsistencies exposed by the audit

### Out Of Scope

- no runtime behavior changes in this slice
- no new handler extraction yet
- no API contract changes

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/runtime/session_registry_handler.py`
- `src/mini_agent/runtime/session_operator_handler.py`
- `src/mini_agent/runtime/session_model_selection_handler.py`
- `src/mini_agent/application/session_service.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Quantify the current runtime-manager method surface instead of judging by file size alone.
2. Inspect the remaining larger methods against adjacent handlers to identify real boundary leaks.
3. Record the recommended next cut order and any small correctness inconsistencies.

### Acceptance

- the next `P30.7` cut is chosen by ownership/hotspot evidence instead of file geography
- long composition methods that are structurally acceptable are explicitly ruled out
- real remaining hotspots are written down in priority order

### Status

- completed

## Latest Sync: 2026-04-13 P30.7ak Session State Model Extraction

## Current Execution Slice: P30.7ak Session State Model Extraction (2026-04-13)

### Why This Slice Is Next

- after the runtime persistence cut, the most obvious remaining file-top residue in `MainAgentRuntimeManager` was the `MainAgentSession*` state cluster
- unlike the persistence wrapper, these types were referenced broadly across runtime collaborators
- that made them a real architectural boundary concern:
  - the shared session state of the runtime was still physically anchored inside the outer runtime facade
- once persistence had already moved out cleanly, this became the natural second cut

### Scope

- move the runtime session state dataclasses out of `main_agent_runtime_manager.py`
- establish one dedicated shared state module for:
  - session state
  - projection state
  - transcript state and entries
  - runtime host state
  - lineage state
- rewire runtime/application imports to use the new shared state module directly

### Out Of Scope

- no session behavior redesign
- no DTO/schema changes
- no new session abstraction beyond relocating the existing shared types

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/runtime/session_state.py`
- `src/mini_agent/runtime/__init__.py`
- `src/mini_agent/application/session_service.py`
- runtime collaborator modules importing `MainAgentSession*`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Create a dedicated runtime session-state module.
2. Move `MainAgentSession*` models out of `main_agent_runtime_manager.py`.
3. Rewire runtime/application modules to import shared session-state types from the new module.
4. Re-run static checks plus runtime/session/TUI verification bundles and the readiness walkthrough.

### Acceptance

- `MainAgentRuntimeManager` no longer physically owns the shared session-state model definitions
- runtime collaborators import shared session-state types from one dedicated module
- runtime/session/TUI verification remains green after the type relocation

### Status

- completed

## Latest Sync: 2026-04-13 P30.7aj Runtime Persistence Extraction

## Current Execution Slice: P30.7aj Runtime Persistence Extraction (2026-04-13)

### Why This Slice Is Next

- after the latest `P30.7` audit, the remaining runtime-manager thickness at the file top was no longer one large behavior blob
- it was two different kinds of residue:
  - the gateway-managed persistence wrapper
  - the session-state dataclass cluster
- the persistence wrapper was the safer next cut because:
  - it was effectively private to `MainAgentRuntimeManager`
  - it already had a coherent responsibility boundary
  - extracting it would reduce file-top ownership clutter without forcing a broad type-import migration in the same slice

### Scope

- move the runtime session persistence wrapper out of `main_agent_runtime_manager.py`
- keep persistence behavior unchanged:
  - session record save/load/delete
  - shared transcript sidecar persistence
  - metadata registry updates
- rewire runtime-manager composition to use the extracted persistence module

### Out Of Scope

- no session-state dataclass extraction in this slice
- no persistence schema changes
- no application or gateway contract changes

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/runtime/session_runtime_persistence.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Extract `_MainAgentRuntimePersistence` into a dedicated runtime persistence module.
2. Rewire manager bootstrap to depend on the extracted module.
3. Re-run focused runtime/session/TUI verification and the readiness walkthrough.
4. Record the result and identify the next remaining top-of-file hotspot.

### Acceptance

- `MainAgentRuntimeManager` no longer embeds the runtime session persistence wrapper implementation
- persistence behavior remains unchanged for save/load/delete plus transcript sidecars
- runtime/session/TUI verification stays green after the extraction

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI-CLI Model Use Request Convergence

## Current Execution Slice: P30.5 TUI-CLI Model Use Request Convergence (2026-04-13)

### Why This Slice Is Next

- after the remote memory mutation cut, `model use` was the clearest remaining operator request that still duplicated catalog-validation logic across terminal entrances
- `TUI` and `CLI` were both still deciding:
  - usage validity
  - provider existence
  - model existence inside the selected provider
- that is smaller than the earlier remote command shells, but it is still avoidable entrance duplication

### Scope

- add one shared helper that resolves `/model use` requests against a provider catalog snapshot
- rewire `TUI` and `CLI` model-use handling to consume that helper
- keep runtime/gateway ownership of actual selection application unchanged

### Out Of Scope

- no model registry redesign
- no remote model response contract changes
- no TUI model panel redesign

### Files In Scope

- `src/mini_agent/commands/execution.py`
- `src/mini_agent/commands/__init__.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/cli_interactive.py`
- `tests/test_command_execution_service.py`
- `tests/test_tui_app.py`
- `tests/test_cli_submission_loop.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Add one shared `model use` catalog-resolution helper in the shared command layer.
2. Replace duplicated `provider/model` validation in `TUI`.
3. Replace duplicated `provider/model` validation in `CLI`.
4. Re-run focused and broader regressions, then record the cut.

### Acceptance

- `TUI` and `CLI` no longer keep separate catalog-resolution logic for `/model use`
- shared tests lock the helper contract for:
  - success
  - usage
  - provider missing
  - model missing
- related TUI/CLI regressions remain green

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI Remote Memory Mutation Convergence

## Current Execution Slice: P30.5 TUI Remote Memory Mutation Convergence (2026-04-13)

### Why This Slice Is Next

- the previous remote memory cut intentionally stopped at the read-heavy branches
- that left the last clearly thicker `TUI` memory mutation shell in:
  - `memory promote`
  - `memory save`
- these branches were no longer carrying unique business meaning
- they were mostly carrying their own execute/error/render wrappers

### Scope

- rewire remote/local `memory promote` and `memory save` through the shared memory execution helper
- strengthen fake-gateway mutation behavior so remote memory mutation tests reflect real transcript/result shapes more closely
- re-run broader `TUI` regression coverage after the convergence cut

### Out Of Scope

- no memory API redesign
- no new memory abstraction layer
- no gateway contract changes

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Rewire `memory promote` through `_execute_memory_command_plan(...)`.
2. Rewire `memory save` through `_execute_memory_command_plan(...)`.
3. Add focused remote mutation tests and make fake gateway mutation transcripts more truthful.
4. Re-run `ruff` plus the full `test_tui_app.py` suite and record the result.

### Acceptance

- `memory promote` and `memory save` no longer keep custom execute/render shells in `TUI`
- focused remote mutation tests cover gateway-backed `promote` / `save`
- `test_tui_app.py` stays green after the cut

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI Remote Memory Read-Path Convergence

## Current Execution Slice: P30.5 TUI Remote Memory Read-Path Convergence (2026-04-13)

### Why This Slice Is Next

- after remote context convergence, `memory` was the clearest remaining thick remote command family in `TUI`
- the highest duplication was concentrated in repeated:
  - run action
  - unpack `result`
  - append feedback
  - set status
  - error rendering
- the safest first cut was the remote/read-heavy side of memory, not the more stateful mutation flows

### Scope

- centralize repeated memory command execution/rendering in `TUI`
- cover read-heavy memory actions first
- preserve command behavior and response content

### Out Of Scope

- no remote memory mutation redesign for `promote` / `save` in this slice
- no memory contract redesign
- no gateway API changes

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Add one shared memory result/execution helper in `TUI`.
2. Rewire repeated read-heavy memory actions through that helper.
3. Re-run focused remote memory regressions plus broader memory checks.
4. Record the remaining mutation hotspot explicitly.

### Acceptance

- remote/read-heavy memory actions no longer each carry their own full try/result/render shell
- focused remote memory tests stay green
- active notes identify what still remains in `memory`

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI Remote Context Request Convergence

## Current Execution Slice: P30.5 TUI Remote Context Request Convergence (2026-04-13)

### Why This Slice Is Next

- after remote control dispatch convergence, remote `context` still had one clear split-brain shape
- the shared command service already validated and normalized context-update intent
- but `TUI` remote handling still re-parsed raw args to rebuild the remote request
- that meant the entrance still owned a second copy of part of the command meaning

### Scope

- let shared `execute_context(...)` produce structured remote update request data
- let `TUI` remote context updates consume that structured request directly
- align remote context binding metadata with the rest of the remote request paths

### Out Of Scope

- no remote memory convergence in this slice
- no context read-only (`show` / `stats`) redesign
- no gateway contract redesign

### Files In Scope

- `src/mini_agent/commands/execution.py`
- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Extend shared context execution payloads with structured remote-request data.
2. Add one remote context update dispatcher in `TUI`.
3. Remove TUI-side remote arg re-parsing for include/exclude/budget/reset.
4. Lock the new request shape with focused tests.

### Acceptance

- remote context updates no longer rebuild request structure from raw args inside `TUI`
- remote context requests now carry aligned binding metadata
- focused tests prove both include and budget requests are structured correctly

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI Remote Control Dispatch Convergence

## Current Execution Slice: P30.5 TUI Remote Control Dispatch Convergence (2026-04-13)

### Why This Slice Is Next

- after removing the worst remote busy-conflict forks, `TUI` still repeated remote control request orchestration
- the duplication was concentrated in:
  - remote request assembly
  - gateway error-detail handling
  - post-control remote detail sync
- `mcp_*` and context-control were still close enough to count as parallel entrance shells

### Scope

- centralize remote control dispatch for `TUI`
- reuse one request/error/sync path for remote `mcp` and remote context-control
- align remote context-control with the same binding payload style already used by remote `mcp`

### Out Of Scope

- no KB remote-control convergence in this slice
- no local command-path redesign
- no gateway contract redesign

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Add one remote control dispatch helper in `TUI`.
2. Rewire remote context-control through that helper.
3. Rewire remote `mcp` through that helper.
4. Update focused tests for the aligned binding payload and remote-control regressions.

### Acceptance

- remote `mcp` and remote context-control share one dispatch/error/sync seam
- remote context-control now carries the same remote binding metadata style as the other remote control commands
- focused regressions stay green after the helper extraction

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI Remote Control Conflict Convergence

## Current Execution Slice: P30.5 TUI Remote Control Conflict Convergence (2026-04-13)

### Why This Slice Is Next

- after remote `skill` and remote approval convergence, the next visible `TUI` drift point was remote control conflict handling
- `TUI` still kept local `busy` branches for:
  - `compact`
  - `drop_memories`
  - `mcp reload`
- but the shared session-control path already owns the canonical busy-conflict rule

### Scope

- remove local remote-session busy prechecks for `context-control` and `mcp reload`
- reuse shared gateway conflict detail for remote control failures
- keep local busy handling unchanged

### Out Of Scope

- no full remote `mcp` command convergence in this slice
- no local context-control redesign
- no gateway contract redesign

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Centralize remote control error-detail rendering in `TUI`.
2. Remove remote-only busy special casing for `compact` / `drop_memories` / `mcp reload`.
3. Update fake gateway control behavior to simulate shared busy conflicts.
4. Re-run focused remote control regressions.

### Acceptance

- remote busy conflicts for context-control and `mcp reload` are now decided by the shared gateway/runtime path
- `TUI` no longer keeps separate busy wording forks for those remote commands
- focused tests prove the gateway is called before the conflict is surfaced

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI Remote Approval Convergence

## Current Execution Slice: P30.5 TUI Remote Approval Convergence (2026-04-13)

### Why This Slice Is Next

- after the remote `skill` cut, the next obvious `TUI` command-shell hotspot was remote approval handling
- `TUI` was still deciding too much approval meaning locally for gateway-backed sessions:
  - whether anything is pending
  - whether restart loss should be surfaced
  - whether one pending approval should auto-select a token
  - whether multiple pending approvals should force a token
- those rules already belong to the shared runtime approval path

### Scope

- remove remote approval-selection semantics from `TUI`
- let the shared gateway/runtime approval path decide token resolution and restart-loss conflicts
- keep local approval behavior unchanged

### Out Of Scope

- no local approval redesign
- no remote MCP/context-control convergence in this slice
- no gateway contract redesign

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Split remote approval handling from local approval handling inside `TUI`.
2. Remove remote local-precheck logic for pending/restart-loss/token selection.
3. Normalize remote gateway error detail rendering for approval failures.
4. Update fake gateway and focused tests to follow shared approval semantics.

### Acceptance

- remote `TUI` approval no longer chooses tokens locally
- remote restart-loss and multiple-pending behavior now come from the shared gateway/runtime path
- focused approval tests verify the new command boundary explicitly

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 TUI Remote Skill Convergence

## Current Execution Slice: P30.5 TUI Remote Skill Convergence (2026-04-13)

### Why This Slice Is Next

- the `P30.5` audit identified `TUI` remote command handling as the main remaining entrance-convergence hotspot
- within that hotspot, `skill` was the safest first cut:
  - local `TUI` already routes skill semantics through the shared command service
  - remote `TUI` still owned a large action-by-action command shell
- this made remote `TUI` look too much like a second command executor

### Scope

- collapse the remote `skill` action tree in `TUI`
- move argument-shape validation, command naming, and response rendering into narrower helpers
- keep user-visible behavior stable while reducing command-shell duplication

### Out Of Scope

- no remote approval convergence in this slice
- no remote MCP/context-control convergence in this slice
- no gateway contract redesign

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`

### Task Breakdown

1. Introduce one normalized remote skill command plan for `TUI`.
2. Replace the remote `if/elif` action tree with table-driven parse + execute + render helpers.
3. Lock the mutation-sync path so uninstall/rollback refresh behavior does not drift.
4. Re-run focused TUI skill checks.

### Acceptance

- remote `TUI` skill handling no longer owns a long action-by-action branch tree
- usage/unknown-action handling is centralized for remote skill commands
- remote skill mutation sync behavior is explicit and tested

### Status

- completed

## Latest Sync: 2026-04-13 P30.5 Shared Entrance Command Convergence Audit

## Current Execution Slice: P30.5 Shared Entrance Command Convergence Audit (2026-04-13)

### Why This Slice Is Next

- `P30.4` is now effectively closed from a remote-adapter boundary perspective
- the next drift risk is no longer `QQ`
- the real question is whether `CLI / TUI / Remote Interaction` are actually reusing the same command semantics, or whether one of them is quietly regrowing a second command executor
- before cutting more code, we need one written audit so the next implementation step aims at the correct hotspot

### Scope

- inspect the current shared command core
- compare how `CLI`, `TUI`, and the remote path consume it
- identify which surface still owns too much command meaning
- record the recommended first `P30.5` implementation cuts

### Out Of Scope

- no new command-service abstraction in this slice
- no QQ feature work in this slice
- no TUI refactor yet

### Files In Scope

- `src/mini_agent/commands/router.py`
- `src/mini_agent/commands/execution.py`
- `src/mini_agent/cli_interactive.py`
- `src/mini_agent/tui/app.py`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Confirm what shared command parsing/execution already exists.
2. Compare `CLI` usage of the shared layer versus `TUI` usage.
3. Re-evaluate whether `QQ` is still the main convergence target.
4. Write the next implementation target into the active plan.

### Acceptance

- active notes explicitly state that `P30.5` starts from entrance-command convergence, not more QQ cleanup
- the docs identify the main remaining hotspot correctly
- the next implementation cut is narrowed to the most drift-prone surface

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 QQ Tail Cleanup + Closure Check

## Current Execution Slice: P30.4 QQ Tail Cleanup + Closure Check (2026-04-13)

### Why This Slice Is Next

- after the approval, runtime-policy, and MCP thinning cuts, the remaining QQ questions were no longer about major business-logic ownership
- what remained was:
  - one small UX bug in `/status`
  - one small wording inconsistency in `/cancel`
  - and the need to decide whether `P30.4` could now close cleanly

### Scope

- avoid duplicate replies when `/status` probes shared-session binding but falls back to local status
- reuse shared cancel-conflict wording for `/cancel`
- record the resulting boundary judgment for `P30.4`

### Out Of Scope

- no further remote binding redesign
- no stream/presenter redesign
- no additional QQ feature work in this slice

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Make shared-session binding checks optionally silent for read-only status probing.
2. Remove QQ-local cancel wording drift by reusing shared gateway detail.
3. Reconfirm whether the remaining QQ logic is adapter-appropriate.
4. Sync the closure judgment into active notes.

### Acceptance

- `/status` no longer double-replies when no shared session is bound
- `/cancel` now reflects the shared conflict detail instead of a QQ-local wording fork
- active notes explicitly state that `P30.4` is ready to close

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 QQ Runtime Policy + MCP Command Thinning

## Current Execution Slice: P30.4 QQ Runtime Policy + MCP Command Thinning (2026-04-13)

### Why This Slice Is Next

- after the approval-command cut, the remaining low-cost adapter semantics were concentrated in:
  - `/plan` `/build` `/default` `/full_access`
  - `/mcp status|list|reload`
  - `/compact` `/drop_memories`
- the problem was smaller than approval, but still visible:
  - runtime-policy commands still derived behavior from command-name branching
  - control commands still encoded command-to-action meaning locally
  - `/mcp reload` still had a QQ-local busy special case instead of reusing shared control errors

### Scope

- move runtime-policy command meaning into QQ dispatch metadata instead of handler-owned command-name checks
- move `/compact` and `/drop_memories` action identity into dispatch metadata
- keep `/mcp` as a thin subcommand router but remove QQ-local busy special casing
- surface shared gateway/runtime error details consistently for policy/control commands

### Out Of Scope

- no shared command catalog JS runtime integration
- no gateway API redesign
- no WeChat adapter changes in this slice

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Extend QQ command-entry metadata to carry runtime-policy payloads.
2. Rewire `/plan` `/build` `/default` `/full_access` to use dispatch metadata.
3. Rewire `/compact` and `/drop_memories` to use dispatch metadata.
4. Thin `/mcp` to subcommand-to-action mapping plus shared error detail forwarding.
5. Re-run QQ static checks and focused runtime-policy / MCP gateway regressions.

### Acceptance

- QQ runtime-policy commands no longer decide behavior by branching on command names
- QQ control commands carry less command-specific meaning in handler bodies
- `/mcp reload` busy/error behavior comes from shared control handling instead of QQ-local wording

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 QQ Approval Command Thinning

## Current Execution Slice: P30.4 QQ Approval Command Thinning (2026-04-13)

### Why This Slice Is Next

- after thinning QQ request assembly, command dispatch, model selection, skill, memory, and context updates, the strongest remaining adapter-owned business semantic was `/approve` / `/deny`
- the QQ handler was still:
  - fetching session detail itself
  - deciding between live and recovery-lost approvals
  - auto-selecting a token when there was only one pending approval
  - and formatting multi-token guidance locally
- that logic already exists in shared runtime approval handling, so keeping it in QQ would just recreate a second approval-selection policy at the surface edge

### Scope

- remove QQ-local pending-approval inspection before resolving approvals
- let the shared gateway/runtime approval path own:
  - missing-approval conflict handling
  - restart-lost approval messaging
  - single-token implicit selection
  - multi-token conflict guidance
- keep QQ responsible only for command input capture and remote reply formatting

### Out Of Scope

- no approval API redesign
- no TUI approval-command rewrite in this slice
- no stream/presenter changes for remote activity or approval events

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Remove QQ-local approval detail fetch and token-selection branching.
2. Route `/approve` and `/deny` directly to the shared approval endpoint with an optional token.
3. Reuse shared gateway/runtime error detail for lost approvals, missing approvals, and multi-token conflicts.
4. Re-run focused QQ and approval-flow verification.

### Acceptance

- QQ no longer owns approval-selection semantics
- shared runtime is the single authority for pending-approval resolution behavior
- remote approval behavior stays stable while adapter logic gets thinner

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 QQ Memory + Context Command Thinning

## Current Execution Slice: P30.4 QQ Memory + Context Command Thinning (2026-04-13)

### Why This Slice Is Next

- after shrinking QQ `/skill`, the next remaining thick command handlers were `/memory` and `/context`
- both handlers still carried long action-specific branch trees even though the shared runtime already owns most of the real validation and mutation semantics
- this made the QQ adapter look too much like a second command executor instead of a remote payload router

### Scope

- reduce QQ `/memory` to a thinner action-to-payload translation layer
- reduce QQ `/context` update commands to a thinner payload-routing layer
- keep local-only detail rendering for `context show` and `context stats`
- keep user-visible behavior stable while moving more validation weight back to the shared runtime/gateway path

### Out Of Scope

- no gateway API redesign
- no TUI/CLI command changes
- no shared command parser rewrite in this slice

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Replace the large QQ `/memory` action tree with thinner payload mapping.
2. Let the shared session memory handler own more missing-argument and selector validation.
3. Replace the QQ `/context` update branch tree with thinner payload routing.
4. Keep only `show` / `stats` rendering local in QQ for prepared-context inspection.
5. Re-run QQ adapter static verification.

### Acceptance

- QQ `/memory` is materially thinner and less action-semantic-heavy
- QQ `/context` update actions are thinner and rely more on shared runtime validation
- adapter-local command logic is reduced without changing the shared command contract

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 QQ Skill Command Thinning

## Current Execution Slice: P30.4 QQ Skill Command Thinning (2026-04-13)

### Why This Slice Is Next

- after moving shared model-selection disambiguation out of QQ, the next thick adapter spot was `/skill`
- the QQ handler still carried a long action-by-action branch tree even though the shared runtime skill handler already owned most of the real validation and mutation semantics
- the catalog also already exposed `uninstall` and `rollback` for QQ, but the live QQ handler had not caught up

### Scope

- reduce QQ `/skill` to a thinner payload-routing layer
- keep only minimal action-shape checks in the adapter
- defer missing-argument and mutation validation back to the shared session skill handler
- align QQ `/skill` with the catalog by supporting `uninstall` and `rollback`

### Out Of Scope

- no new gateway endpoint
- no shared command-parser redesign
- no change to TUI/CLI `/skill` behavior

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Add one small gateway-error detail formatter for QQ command replies.
2. Replace the long `/skill` action branch tree with a thinner action-to-payload mapping.
3. Let the shared session skill handler own more of the usage/validation path.
4. Align QQ `/skill` with the command catalog for `uninstall` and `rollback`.
5. Re-run QQ adapter static verification.

### Acceptance

- QQ `/skill` is materially thinner and less action-semantic-heavy
- QQ now supports the same catalog-declared `skill uninstall` / `skill rollback` actions
- shared runtime skill validation is now more authoritative than adapter-local branching

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 Shared Model-Selection Source Inference

## Current Execution Slice: P30.4 Shared Model-Selection Source Inference (2026-04-13)

### Why This Slice Is Next

- after the QQ command-scope cleanup, one especially meaningful piece of model-routing logic still lived in the QQ adapter
- `QQ /model use` still fetched the model catalog and decided:
  - whether a provider existed
  - whether a provider id was ambiguous
  - whether a model existed under that provider
- that is already model-routing semantics, not just channel adaptation

### Scope

- add one shared model-selection resolver that can infer `provider_source` when the provider/model pair is uniquely resolvable
- allow shared-session model selection requests to omit `provider_source`
- simplify QQ `/model use` so it forwards `provider_id + model_id` and relies on shared resolution

### Out Of Scope

- no change to TUI/CLI `/model` syntax
- no change to the selected/queued model response shape
- no catalog redesign

### Files In Scope

- `src/mini_agent/model_manager/runtime.py`
- `src/mini_agent/interfaces/agent.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/tui/gateway_client.py`
- `src/apps/qqbot_channel/bot.mjs`
- `tests/test_model_routing_runtime.py`
- `tests/test_main_agent_surface_service.py`
- `tests/test_interface_dto_contracts.py`
- `tests/test_session_remote_service.py`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Add one shared resolver for session-scoped model selection identity.
2. Let shared-session model-selection requests omit `provider_source`.
3. Resolve the missing source in shared runtime before model-selection execution.
4. Remove QQ-side provider/model catalog disambiguation from `/model use`.
5. Add focused tests for unique inference and ambiguous-source rejection.

### Acceptance

- QQ no longer owns provider-source disambiguation for `/model use`
- shared runtime can resolve a unique provider/model pair into a complete session model-selection identity
- ambiguous provider/model pairs now fail from shared logic instead of adapter-local logic

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 QQ Command Scope Dispatch Thinning

## Current Execution Slice: P30.4 QQ Command Scope Dispatch Thinning (2026-04-13)

### Why This Slice Is Next

- after the QQ request-helper thinning cut, one structural smell still remained in the adapter
- shared-session dependency was being enforced ad hoc inside many individual QQ command handlers
- that worked, but it kept one entrance-level routing rule scattered across the handler bodies instead of declaring it at the command-dispatch seam

### Scope

- make QQ command dispatch explicitly distinguish between:
  - local adapter commands
  - shared-session-scoped commands
- move the repeated shared-session binding guard from handlers into the command registry / dispatch path
- keep the concrete command behavior unchanged

### Out Of Scope

- no remote command semantic redesign
- no gateway/application API change
- no cross-surface command unification in this slice

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Add one QQ command-entry helper with `requiresSharedSession` metadata.
2. Mark shared-session-scoped QQ commands explicitly in the registry.
3. Enforce the shared-session guard once in command dispatch.
4. Remove the repeated per-handler guard where dispatch now owns it.
5. Sync the active refactor notes.

### Acceptance

- QQ command dispatch now explicitly models local vs shared-session command scope
- repeated `ensureSharedSessionBound(...)` checks are reduced in handler bodies
- behavior remains unchanged while the adapter boundary becomes clearer

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 QQ Adapter Request Helper Thinning

## Current Execution Slice: P30.4 QQ Adapter Request Helper Thinning (2026-04-13)

### Why This Slice Is Next

- after the remote binding state-thinning cut, the next useful `P30.4` cleanup was inside the active QQ adapter request path
- several QQ shared-session mutation commands were still hand-assembling the same remote mutation envelope again and again
- that duplication was small, but it kept the adapter thicker than it needs to be and made the thin-adapter boundary easier to erode later
- WeChat was reviewed in the same pass and intentionally left alone because its current gateway assembly is still below the duplication threshold

### Scope

- extract thin QQ-local helpers for shared-session mutation payload assembly
- reuse them across the QQ shared-session mutation commands
- keep the change inside the adapter file instead of inventing a new shared remote business layer

### Out Of Scope

- no remote command redesign
- no gateway/application contract changes
- no forced WeChat symmetry refactor

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Add one QQ sender-id helper.
2. Add one QQ shared-session mutation payload helper.
3. Add one QQ shared-session POST-envelope helper for gateway mutation endpoints.
4. Rewire the repeated QQ mutation commands to use those helpers.
5. Record why WeChat was intentionally left unchanged in this slice.

### Acceptance

- QQ shared-session mutation commands no longer hand-assemble the same remote mutation envelope repeatedly
- helper extraction stays inside the QQ adapter and does not create a new business layer
- the code record explicitly states that WeChat was reviewed and left unchanged on purpose

### Status

- completed

## Latest Sync: 2026-04-13 P30.4 Remote Binding State Thinning

## Current Execution Slice: P30.4 Remote Binding State Thinning (2026-04-13)

### Why This Slice Is Next

- after the naming tightening, the next useful `P30.4` step is to keep shrinking adapter-local state itself
- QQ still stored one per-conversation display field that was actually global process configuration
- WeChat binding state still exposed an unused `metadata` field in the binding contract even though the active implementation did not need it

### Scope

- remove obviously redundant per-conversation state from the QQ adapter
- remove unused metadata from the remote conversation binding contract
- keep remote behavior unchanged while making adapter-local state thinner and clearer

### Out Of Scope

- no new remote commands
- no gateway/application contract redesign
- no cross-channel feature additions

### Files In Scope

- `src/apps/qqbot_channel/bot.mjs`
- `src/channels/types/src/index.ts`
- `docs/P30_SESSION_TRUTH_BOUNDARY_MAP_2026-04-13.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Rename the QQ adapter local map to binding-oriented terminology.
2. Drop per-conversation `botName` state and use the global configured bot name directly.
3. Remove unused `metadata` from `RemoteConversationBindingState`.
4. Sync the boundary map so QQ/WeChat cached fields match the live code.
5. Re-run remote adapter static verification.

### Acceptance

- QQ per-conversation cache no longer stores global bot display config
- remote binding contract is thinner and closer to actual live use
- remote adapter static checks remain green

### Status

- completed

## Latest Sync: 2026-04-13 P30.3 Operator-Flow State Split

## Current Execution Slice: P30.3 Operator-Flow State Split (2026-04-13)

### Why This Slice Is Next

- after the supplemental cache split, one obvious mixed area still remained inside TUI state composition
- `pending_model_*` and `pending_skill_reload*` were still living on `TuiSessionProjectionState`
- those fields drive local operator flow, and even when they mirror gateway detail they are still weaker than shared session projection semantics inside the TUI

### Scope

- add one dedicated TUI-local operator-flow state bucket
- move pending model-selection and pending skill-reload state there
- keep shared DTOs and runtime/session contracts unchanged

### Out Of Scope

- no gateway/session DTO redesign
- no runtime pending-model redesign
- no remote adapter changes in this slice

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `docs/P30_SESSION_TRUTH_BOUNDARY_MAP_2026-04-13.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Introduce `TuiSessionOperatorState`.
2. Move pending model-selection state into that slice.
3. Move pending skill-reload state into that slice.
4. Keep summary projection rendering working by mapping operator state back into `SessionSummaryProjection`.
5. Re-run focused and broader TUI/session verification.

### Acceptance

- `TuiSession` is now composed as projection/operator/runtime/view for TUI-owned state
- TUI no longer stores pending model / skill-reload flow on projection itself
- TUI model queueing and skill-reload flows still work

### Status

- completed

## Latest Sync: 2026-04-13 P30.3 Supplemental Cache Split + P30.4 Naming Tightening

## Current Execution Slice: P30.3 Supplemental Cache Split + P30.4 Naming Tightening (2026-04-13)

### Why This Slice Is Next

- the framework skeleton and session-truth boundary map are now locked
- one `P30.3` tightening cut already landed in code:
  - TUI sync / recovery summaries moved under `TuiSessionSupplementalState`
- but the active docs and dev records still described those fields as if they belonged to projection proper
- remote adapters also still carried one especially misleading name:
  - `SessionState`
  - even though the corrected architecture treats that object as adapter-side conversation binding metadata only

### Scope

- sync active docs and dev records to the landed `supplemental` split
- tighten remote adapter naming away from fake session ownership semantics
- keep behavior unchanged while making boundaries harder to misunderstand

### Out Of Scope

- no new session lifecycle behavior
- no remote command redesign
- no new transport/API surface

### Files In Scope

- `docs/P30_SESSION_TRUTH_BOUNDARY_MAP_2026-04-13.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `src/channels/types/src/index.ts`
- `src/channels/wechat/src/channel.ts`
- `src/channels/wechat/src/conversation_binding_store.ts`
- `src/channels/wechat/src/index.ts`
- `src/apps/qqbot_channel/bot.mjs`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Update the boundary map so `supplemental` is documented as a distinct TUI-local cache layer.
2. Update the active P30 execution notes to reflect that `P30.3` is now a tightening phase.
3. Rename the remote adapter-side `SessionState` contract to a conversation-binding name.
4. Keep the active QQ adapter wording aligned with the same thin-binding semantics.
5. Re-run focused Python and TypeScript verification.

### Acceptance

- active docs no longer describe remote summary caches as projection truth
- remote adapter cache types no longer present themselves as canonical session models
- TUI/session and remote/channel checks still pass

### Status

- completed

## Latest Sync: 2026-04-13 P30.2 Session Truth Boundary Lock

## Current Execution Slice: P30.2 Session Truth Boundary Lock (2026-04-13)

### Why This Slice Is Next

- the framework skeleton is now locked, but implementation can still drift unless current state ownership is frozen in writing
- the earlier audit correctly identified TUI and remote adapters as ownership risk zones
- current code has already improved beyond that audit baseline, so the next honest step is:
  - document the current ownership precisely
  - freeze the cache contract
  - use that map as the input for the next real code moves

### Scope

- classify current TUI state fields into:
  - session projection/cache
  - runtime handle
  - view-only state
- classify remote adapter state into:
  - binding convenience
  - delivery/operator preference
  - display metadata
  - accidental domain-risk cache
- define the explicit allowed cache contract for entrances and remote adapters

### Out Of Scope

- no TUI state moves yet
- no remote adapter storage rewrite yet
- no command-system convergence yet

### Files In Scope

- `docs/P30_SESSION_TRUTH_BOUNDARY_MAP_2026-04-13.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `docs/DEVELOPMENT_INDEX.md`
- `src/mini_agent/tui/app.py`
- `src/apps/qqbot_channel/bot.mjs`
- `src/channels/types/src/index.ts`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Audit current TUI state structures and classify each field group.
2. Audit current remote adapter caches and classify their ownership.
3. Write one explicit boundary map document.
4. Add ownership annotations at the key code structures.
5. Re-anchor the P30 plan to this new boundary map.

### Acceptance

- one explicit ownership map exists for TUI and remote adapters
- current code comments now reinforce the intended ownership at the key structs
- `P30.3` and `P30.4` can proceed without rediscovering boundary assumptions

### Status

- completed

## Latest Sync: 2026-04-13 Framework Skeleton Lock

## Current Execution Slice: Framework Skeleton Lock (2026-04-13)

### Why This Slice Is Next

- recent work proved the project can still drift while implementing correct local fixes
- the architecture direction is now broadly right, but the repository still needs one explicit skeleton contract
- without a frozen skeleton, future work can keep repeating the same pattern:
  - solve one real bug
  - then accidentally re-expand the wrong boundary elsewhere

### Scope

- lock one canonical framework skeleton document for the current refactor stage
- freeze:
  - the four-entrance product model
  - the layer stack
  - repository ownership
  - dependency direction
  - no-go drift patterns
- re-anchor active development docs to that skeleton

### Out Of Scope

- no new runtime behavior in this slice
- no new remote feature work in this slice
- no package moves yet unless they are required to document the skeleton honestly

### Files In Scope

- `docs/FRAMEWORK_SKELETON.md`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_INDEX.md`
- `docs/REFACTOR_TASKS.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Define the canonical framework skeleton as an active document.
2. Freeze repository ownership by layer and directory.
3. Write the dependency and no-go drift rules explicitly.
4. Re-anchor development and refactor docs to the new skeleton.
5. Record the new execution guardrail in planning files.

### Acceptance

- one active skeleton document exists and is referenced by the main architecture docs
- entrances, layers, and directory ownership are explicit
- future work has a clear answer for where new code belongs
- the project has an explicit written guardrail against repeating the same boundary drift

### Status

- completed

## Latest Sync: 2026-04-13 Remote Interaction Binding Centralization

## Current Execution Slice: P30.4a Remote Conversation Binding Centralization (2026-04-13)

### Why This Slice Is Next

- the architecture is now explicitly `CLI / TUI / WebUI / Remote Interaction`
- so the next step should strengthen the shared remote entrance, not continue a QQ-specific branch
- current code still leaves `conversation -> session_id` binding in multiple channel-local places:
  - active QQ adapter keeps an in-memory map
  - WeChat keeps a file-backed channel session store
  - Python already has `ConversationBindingStore`, but the active ingress path does not really use it
- that means remote adapters still behave like partial session owners instead of thin channel bridges

### Scope

- centralize remote `conversation -> session_id` binding in the shared application ingress path
- reuse the existing Python `ConversationBindingStore` instead of inventing a second remote binding system
- make `/api/v1/channel/message` able to reuse an existing remote session without the adapter explicitly sending `session_id`
- persist the resolved binding after successful shared chat turns

### Out Of Scope

- no full QQ/WeChat/Feishu adapter rewrite in this slice
- no remote command UX redesign in this slice
- no attempt yet to remove every channel-local convenience field such as workspace defaults

### Files In Scope

- `src/mini_agent/application/channel_ingress_use_cases.py`
- `src/mini_agent/session/binding.py`
- `src/apps/agent_studio_gateway/main.py`
- `scripts/channel_ingress_gateway_walkthrough.py`
- `tests/test_channel_ingress_gateway_walkthrough.py`
- `tests/test_agent_studio_gateway_api_v1.py`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Task Breakdown

1. Define one shared remote binding helper around `ConversationBindingStore`.
2. Resolve remote session binding inside `ChannelIngressUseCases` when `session_id` is absent.
3. Persist the returned binding after successful remote chat turns.
4. Update readiness walkthrough/tests so remote reuse no longer depends on adapter-supplied `session_id`.
5. Re-run targeted gateway/channel verification and record the outcome.

### Acceptance

- remote ingress can continue an existing session with only `channel_type + conversation_id`
- the application layer becomes the canonical remote binding path
- channel adapters are no longer required to be the source of truth for `session_id` reuse
- no new remote-specific session subsystem is introduced

### Status

- completed

## Latest Sync: 2026-04-13 Explicit Derived Session Commands

## Current Execution Slice: P23.29 Explicit Task Fork Commands (2026-04-13)

### Why This Slice Is Next

- runtime lineage now exists for import/restore and real `/delegate` child sessions
- but operators still had no explicit way to fork a focused child task/session themselves
- that meant the new derived-session seam existed in runtime, but not yet in user-facing execution flow

### Scope

- add one explicit derived-session creation API on top of the existing runtime lineage path
- expose it in TUI as `/fork [task_prompt]`
- expose one canonical alias form in TUI as `/task new [task_prompt]`
- when a prompt is supplied, switch into the child session and run the first turn there through the existing chat path

### Out Of Scope

- no new lineage browsing UI yet
- no QQ/CLI parity for explicit fork in this slice
- no new child-session ownership/reply-binding semantics beyond the existing derived-session defaults

### Files In Scope

- `src/mini_agent/interfaces/agent.py`
- `src/mini_agent/interfaces/__init__.py`
- `src/mini_agent/application/session_service.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `src/mini_agent/application/session_remote_service.py`
- `src/mini_agent/tui/gateway_client.py`
- `src/apps/agent_studio_gateway/main.py`
- `src/mini_agent/commands/catalog.json`
- `src/mini_agent/tui/app.py`
- `tests/test_main_agent_surface_service.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P23_AGENT_CORE_TASK_PLAN.md`

### Task Breakdown

1. Add one explicit gateway/application request for derived child-session creation.
2. Reuse the existing runtime `create_derived_session(...)` path instead of adding a second fork implementation.
3. Wire `/fork` and `/task new` into the TUI command dispatcher and command catalog.
4. Reuse the existing remote chat path for the child session's optional first task.
5. Add focused regressions for explicit derived-session API use and TUI command behavior.

### Acceptance

- explicit operator task forking creates a real child session with lineage
- the forked child is immediately inspectable/resumable as a normal session
- `/fork <prompt>` and `/task new <prompt>` both land on the same runtime-derived session path
- no fake local-only child-task subsystem is introduced

## Latest Sync: 2026-04-13 Delegation-Derived Session Lineage

## Current Execution Slice: P23.28 Delegation-Derived Session Lineage (2026-04-13)

### Why This Slice Is Next

- runtime lineage now exists for imported and restored sessions
- but explicit `/delegate` execution still did not create a real child session
- that meant one of the most natural lineage-producing behaviors in the product still collapsed back into:
  - one parent reply string
  - with no durable child task session
- the next honest move was therefore to make delegation produce a real derived session

### Scope

- add one runtime/application path for creating derived sessions from a parent session
- make `/delegate` run inside a derived child session instead of an untracked ephemeral worker
- preserve child lineage, transcript, activity, and inherited runtime configuration
- include child-session identifiers in delegation results/events

### Out Of Scope

- no new task-fork CLI/TUI command yet
- no lineage browsing UI yet
- no multi-level delegation UX redesign yet

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/application/session_service.py`
- `src/mini_agent/application/gateway_route_execution_handler.py`
- `src/mini_agent/agent_core/delegation.py`
- `tests/test_main_agent_surface_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P23_AGENT_CORE_TASK_PLAN.md`

### Execution Steps

1. Add a runtime/application derived-session creation path that inherits parent runtime configuration.
2. Rewire `/delegate` to execute in a derived child session.
3. Keep fallback-to-parent behavior, but leave the failed child session as an inspectable task record.
4. Expose `child_session_id` in delegation payloads for future UI/CLI use.
5. Re-run delegation-focused and broader runtime/session verification bundles.

### Acceptance Criteria

- `/delegate` creates a real child session
- child sessions carry lineage to the parent session
- child sessions keep their own transcript/activity history
- fallback still works without losing the failed child task record
- broader runtime/session verification remains green

### Status

- completed

## Latest Sync: 2026-04-13 Session Lineage Runtime Integration

## Current Execution Slice: P23.27 Session Lineage Runtime Integration (2026-04-13)

### Why This Slice Is Next

- the agent-core session package already had `SessionLineageStore`
- but it was completely disconnected from the real runtime path
- that meant the codebase had the beginnings of lineage support without any runtime truth using it
- this was the right next strengthening slice because it improves:
  - snapshot import/export semantics
  - persisted restore correctness
  - future session derivation features such as delegation, compression, and task forks

### Scope

- add runtime-private lineage state to managed sessions
- connect lineage into:
  - new session creation
  - runtime snapshot import/export
  - persistence metadata save/load
  - persisted session restore
- reuse the existing `SessionLineageStore` instead of inventing a second lineage tracker

### Out Of Scope

- no TUI/CLI/WebUI rendering yet
- no public DTO expansion for lineage browsing
- no new session forking UX yet

### Files In Scope

- `src/mini_agent/agent_core/session/lineage.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/runtime/session_creation_handler.py`
- `src/mini_agent/runtime/session_hydration_builder.py`
- `src/mini_agent/runtime/session_persistence_record_builder.py`
- `src/mini_agent/runtime/session_read_model_builder.py`
- `src/mini_agent/runtime/session_registry_handler.py`
- `src/mini_agent/runtime/session_snapshot.py`
- `src/mini_agent/runtime/session_snapshot_handler.py`
- `tests/test_agent_core_session.py`
- `tests/test_main_agent_surface_service.py`
- `docs/P23_AGENT_CORE_TASK_PLAN.md`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add runtime-private lineage state plus store registration/removal hooks.
2. Persist lineage through record save/load and runtime snapshot import/export.
3. Rehydrate lineage on persisted restore and imported sessions.
4. Add focused regressions for child import and restart restore semantics.
5. Re-run focused plus broader runtime/session/TUI verification bundles.

### Acceptance Criteria

- managed sessions keep stable lineage metadata internally
- exported/imported runtime snapshots preserve lineage
- persisted restores rehydrate lineage instead of dropping it
- the existing `SessionLineageStore` becomes part of runtime truth
- focused and broad verification stay green

### Status

- completed

## Latest Sync: 2026-04-13 Agent Kernel Bootstrap Diagnostics

## Current Execution Slice: P23.26 Agent Kernel Bootstrap Diagnostics (2026-04-13)

### Why This Slice Is Next

- after the runtime-boundary cleanup, the next high-value agent-core gap was bootstrap observability
- the unified kernel already built:
  - route
  - runtime policy
  - tools
  - skills
  - MCP
  - turn-context providers
- but runtime surfaces still had no single kernel-level self-description
- one practical problem also remained:
  - skills/MCP bootstrap failures were often tolerated silently
  - which meant the agent could still run, but operators had no consistent way to understand what failed during startup

### Scope

- add one unified `kernel_diagnostics` payload on built agents
- surface route/policy/tool/skill/MCP/turn-context bootstrap state there
- keep skills/MCP bootstrap non-fatal, but record failure diagnostics instead of silently losing observability

### Out Of Scope

- no TUI/CLI rendering changes yet
- no runtime/session persistence changes
- no bootstrap behavior redesign beyond diagnostics capture

### Files In Scope

- `src/mini_agent/runtime/tooling.py`
- `src/mini_agent/agent_core/kernel.py`
- `tests/test_agent_core_kernel.py`
- `docs/P23_AGENT_CORE_TASK_PLAN.md`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Extend runtime tool bootstrap helpers to return structured diagnostics alongside tools and skill runtime.
2. Build one kernel-level diagnostics payload covering route, runtime policy, tools, skills, MCP, and turn-context providers.
3. Attach that payload to built agents as `agent.kernel_diagnostics`.
4. Add focused regressions for diagnostics presence and non-fatal skills/MCP bootstrap failures.
5. Re-run agent-core focused and broader runtime/CLI/TUI/gateway bundles.

### Acceptance Criteria

- built agents expose a unified `kernel_diagnostics` payload
- skills/MCP bootstrap failures remain non-fatal but become observable
- focused and broader regression bundles remain green

### Status

- completed

## Latest Sync: 2026-04-13 Managed Session Require-Helper Cleanup

## Current Execution Slice: P30.7ai Managed Session Require-Helper Cleanup (2026-04-13)

### Why This Slice Is Next

- after the runtime-boundary audit, the remaining medium-sized operator facade methods were judged structurally acceptable
- they were not hiding business logic
- but they still repeated one small boundary pattern many times:
  - load or restore a managed session under `_store_lock`
  - raise `404` when no live or persisted session exists
- this was a worthwhile small cleanup because it improves consistency without pushing the architecture further than needed

### Scope

- add one private `_require_managed_session_unlocked(...)` helper in the runtime manager
- reuse it across the repeated restore-or-404 facade entrypoints
- keep cancel/approval and delete semantics untouched

### Out Of Scope

- no new handler extraction
- no operator-surface redesign
- no semantic changes to persisted/live session handling

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add `_require_managed_session_unlocked(...)` on top of the existing `_load_managed_session_unlocked(...)`.
2. Replace repeated load+404 blocks in the identical facade paths.
3. Re-run broad runtime/session/TUI bundle and readiness walkthrough.

### Acceptance Criteria

- repeated restore-or-404 boilerplate is centralized
- behavior remains unchanged across session/operator entrypoints
- broad verification remains green

### Status

- completed

## Latest Sync: 2026-04-13 Runtime Manager Composition Root Cleanup

## Current Execution Slice: P30.7ah Runtime Manager Composition Root Cleanup (2026-04-13)

### Why This Slice Is Next

- after snapshot-import cleanup, the biggest remaining runtime-manager hotspot was no longer a business flow
- it was the composition root itself:
  - `__init__`
  - one long block wiring persistence, diagnostics, hydration, read-side services, runtime mutation services, and boundary handlers
- the issue here was not missing extraction
- it was readability and dependency-order clarity
- so the right move was:
  - keep the same collaborators
  - keep the same ownership
  - but split the wiring into a few internal initialization stages

### Scope

- reorganize `MainAgentRuntimeManager.__init__` into a small set of private initialization methods
- preserve dependency order and behavior
- avoid introducing a new external composition abstraction

### Out Of Scope

- no behavior changes
- no new handler layer
- no contract changes for callers

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Collapse `__init__` into a minimal composition entrypoint.
2. Split the wiring into internal stages:
   - runtime core
   - runtime support services
   - session model services
   - session runtime services
   - session boundary services
3. Re-run static checks, broad runtime/session/TUI bundle, and readiness walkthrough.

### Acceptance Criteria

- `__init__` becomes a small readable composition entrypoint
- dependency order remains valid
- broad verification remains green

### Status

- completed

## Latest Sync: 2026-04-13 Snapshot Import Command Surface Cleanup

## Current Execution Slice: P30.7ag Snapshot Import Command Surface Cleanup (2026-04-13)

### Why This Slice Is Next

- after the transcript/turn-recording cleanup, `import_session_snapshot(...)` still stood out in the runtime manager
- the remaining thickness was no longer orchestration logic
- it was mostly:
  - a very large parameter surface
  - plus manager-local construction of `RuntimeSessionSnapshotImportCommand(...)`
- the registry/snapshot layer already speaks in terms of the import command object
- so the honest next move was to let the runtime-manager boundary speak that same language too

### Scope

- change `MainAgentRuntimeManager.import_session_snapshot(...)` to accept a `RuntimeSessionSnapshotImportCommand`
- update direct test/script callers to construct that command explicitly
- keep snapshot import behavior unchanged

### Out Of Scope

- no snapshot schema changes
- no new handler abstraction
- no import/export behavior redesign

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_main_agent_surface_service.py`
- `scripts/shared_session_gateway_walkthrough.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Collapse the runtime-manager snapshot-import boundary onto `RuntimeSessionSnapshotImportCommand`.
2. Update helper/test/script call sites to construct the command object directly.
3. Re-run focused import/export regressions plus the broader runtime/session/TUI bundle and walkthrough.

### Acceptance Criteria

- runtime manager no longer exposes a large kwargs-style snapshot-import signature
- test/script callers compile against the command-object contract
- snapshot import/export/recovery behavior remains green in focused and broad verification

### Status

- completed

## Latest Sync: 2026-04-13 Turn Recording Surface Consolidation

## Current Execution Slice: P30.7af Turn Recording Surface Consolidation (2026-04-13)

### Why This Slice Is Next

- after the registry/operator/cancel-approval cuts, the remaining session transcript surface in the runtime manager was mostly thin already
- one notable orchestration fragment still lived inline:
  - `record_turn(...)`
- the manager was still assembling a two-message transcript write itself even though the real mutation owner was already:
  - `RuntimeSessionTurnScopeHandler`
- this made the transcript surface a good low-risk follow-up:
  - it reduces one more piece of manager-local mutation sequencing
  - without inventing another abstraction or changing the public runtime surface

### Scope

- extend `RuntimeSessionTurnScopeHandler` with a first-class `record_turn(...)` helper
- rewire runtime-manager transcript wrappers into thinner facade-style delegation
- add focused regression coverage for direct `record_turn(...)` persistence

### Out Of Scope

- no transcript schema changes
- no session-service API redesign
- no new recording-specific handler

### Files In Scope

- `src/mini_agent/runtime/session_turn_scope_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_main_agent_surface_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add `record_turn(...)` onto the existing turn-scope handler beside `record_message(...)`.
2. Rewire runtime-manager transcript wrappers to delegate directly and remove leftover inline response variables.
3. Add a focused direct-runtime regression for `record_turn(...)`.
4. Re-run focused transcript/session/TUI regression bundles.

### Acceptance Criteria

- runtime manager no longer assembles the user+assistant transcript pair inline for `record_turn(...)`
- transcript persistence behavior stays stable for direct runtime calls
- focused runtime/session/TUI regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Cancel / Approval Operator-Surface Follow-Up

## Current Execution Slice: P30.7ae Cancel / Approval Operator-Surface Follow-Up (2026-04-13)

### Why This Slice Is Next

- after the session-operator extraction, two obvious operator-facing branches still lived inline in the runtime manager:
  - `cancel_session_turn(...)`
  - `resolve_pending_approval(...)`
- both were already using the extracted interrupt domain handler
- what remained inline was mostly:
  - active-vs-persisted existence handling
  - transcript recording
  - approval waiter finalization ordering

### Scope

- extend the session-operator handler to own cancel/approval orchestration too
- keep manager-side `_store_lock` ownership
- preserve existing transcript ordering and approval-finalization behavior

### Out Of Scope

- no redesign of interrupt domain rules
- no change to approval transport contracts
- no session-persistence changes

### Files In Scope

- `src/mini_agent/runtime/session_operator_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Extend the operator handler with cancel/approval orchestration methods.
2. Rewire runtime manager cancel/approval entrypoints into thin lock+lookup+delegate shells.
3. Re-run focused cancel/approval regressions plus broad runtime/gateway/TUI bundles.

### Acceptance Criteria

- runtime manager no longer owns the full orchestration body for cancel/approval session commands
- transcript ordering and approval waiter finalization remain stable
- shared-session walkthrough and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Session Operator Handler Extraction

## Current Execution Slice: P30.7ad Session Operator Handler Extraction (2026-04-13)

### Why This Slice Is Next

- after session-registry orchestration moved out, the next remaining runtime-manager hot spot was the operator-command surface
- the manager still owned bulky orchestration for:
  - `control_session_context(...)`
  - `update_session_context_policy(...)`
  - `manage_session_memory(...)`
  - `manage_session_skills(...)`
  - `update_session_model_selection(...)`
  - `update_session_runtime_policy(...)`
- those methods were mostly composing already-extracted business handlers rather than owning new business logic

### Scope

- add one operator-command handler in the runtime layer
- move command-surface orchestration and transport-response shaping into it
- keep the existing lower-level handlers as the business owners

### Out Of Scope

- no command behavior redesign
- no API contract changes
- no session-truth migration

### Files In Scope

- `src/mini_agent/runtime/session_operator_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a runtime operator handler that composes the existing control/context/memory/skill/model/policy handlers.
2. Move command orchestration and response shaping into that handler.
3. Rewire runtime manager command entrypoints to thin delegation shells.
4. Preserve existing operator-visible semantics and monkeypatch seams during extraction.
5. Re-run focused and broad shared-session/gateway/TUI bundles.

### Acceptance Criteria

- runtime manager no longer owns the full orchestration body for the main session operator commands
- command behavior and response payloads stay stable
- MCP cleanup monkeypatchability and command metadata semantics stay preserved
- broad regression bundles and walkthroughs stay green

### Status

- completed

## Latest Sync: 2026-04-13 Session Registry Handler Extraction

## Current Execution Slice: P30.7ac Session Registry Handler Extraction (2026-04-13)

### Why This Slice Is Next

- after the direct-wiring cleanup, the next obvious runtime-manager thickness was no longer forwarding glue
- it was registry orchestration:
  - `get_or_create_session(...)`
  - `create_session(...)`
  - `import_session_snapshot(...)`
  - plus the adjacent read/export shells that all operate on the same session registry truth
- these paths were cohesive enough to move together because they all coordinate:
  - active session map
  - persisted records
  - lifecycle refresh
  - restore/hydrate entry
  - catalog-backed read surfaces

### Scope

- add one registry-focused runtime handler
- move session acquire/create/import/export/list/detail/recent orchestration into that handler
- keep `MainAgentRuntimeManager` as the store-lock owner and outer facade only

### Out Of Scope

- no command-surface behavior changes
- no persistence schema changes
- no new session truth model

### Files In Scope

- `src/mini_agent/runtime/session_registry_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a registry handler that composes the existing access/creation/snapshot/catalog handlers.
2. Move session acquire/create/import/export/list/detail/recent orchestration into it.
3. Rewire runtime manager to delegate those flows while keeping `_store_lock` at the manager boundary.
4. Re-run focused and broad shared-session/gateway/TUI regression bundles.

### Acceptance Criteria

- runtime manager no longer owns the full orchestration body for get/create/import/export/list/detail/recent session registry operations
- session registry behavior still reuses the existing lower-level handlers instead of rebuilding parallel logic
- shared-session walkthrough and broad runtime/gateway bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Runtime Manager Direct-Wiring Cleanup

## Current Execution Slice: P30.7ab Runtime Manager Direct-Wiring Cleanup (2026-04-13)

### Why This Slice Is Next

- after the handler/builder extraction wave, `MainAgentRuntimeManager` still kept a noticeable amount of leftover forwarding code
- these helpers no longer owned business logic:
  - diagnostics calls were forwarded back into `RuntimeSessionDiagnosticsService`
  - read-model calls were forwarded back into `RuntimeSessionReadModelBuilder`
  - runtime-memory helpers were forwarded back into `RuntimeTaskMemoryBackendAdapter`
- keeping those forwarding layers around was making the runtime boundary look thinner than it really was without actually reducing coupling

### Scope

- rewire runtime-manager dependencies directly to the already extracted services/builders/handlers
- preserve capture/restore persistence semantics by routing agent-runtime rebuilds through `RuntimeSessionTurnScopeHandler`
- delete manager-local forwarding helpers that are no longer needed

### Out Of Scope

- no new handler abstraction
- no command-surface behavior changes
- no persistence schema changes

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Reorder runtime-manager wiring so extracted collaborators can reference each other directly.
2. Replace pure forwarding callbacks with direct service/builder methods where signatures allow it.
3. Keep lambda adapters only where keyword-only callback signatures still need shaping.
4. Delete the now-dead manager helper layer.
5. Re-run focused and broad runtime/gateway/TUI regression bundles.

### Acceptance Criteria

- runtime manager no longer keeps pure forwarding helpers for read models, diagnostics, or runtime-memory backend access
- extracted collaborators are wired together directly from `__init__`
- prepared-context capture/restore still persists through the existing turn-scope seam
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 TUI Gateway Client Payload Shaping Consolidation

## Current Execution Slice: P30.7aa TUI Gateway Client Payload Shaping Consolidation (2026-04-13)

### Why This Slice Is Next

- after reusing `SessionSurfaceBinding` across session-facing services, one more duplication cluster of the same family still remained in the TUI client
- `TuiGatewayClient` was repeatedly rebuilding:
  - session interaction context payloads
  - create-session payloads
  - chat request/query payloads
- unlike the earlier service-layer slice, this should be solved locally inside the client to avoid cross-layer coupling

### Scope

- add lightweight local payload helpers inside `TuiGatewayClient`
- reuse them across repeated session-context/create/chat payload shapes
- add focused client payload tests

### Out Of Scope

- no gateway API changes
- no TUI behavior redesign
- no reuse of application-layer binding types inside the TUI layer

### Files In Scope

- `src/mini_agent/tui/gateway_client.py`
- `tests/test_tui_gateway_client.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a local TUI gateway session-binding helper.
2. Reuse it across repeated session-context payloads.
3. Reuse shared payload helpers for create-session and chat flows.
4. Re-run focused and broad TUI/gateway regression bundles.

### Acceptance Criteria

- repeated session-context payload normalization no longer lives inline in each client method
- async/sync create-session paths share one payload helper
- `run_chat(...)` and `stream_chat_events(...)` share one chat payload helper
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Session Surface Binding Reuse Across Services

## Current Execution Slice: P30.7z Session Surface Binding Reuse Across Services (2026-04-13)

### Why This Slice Is Next

- after unifying chat-entry request adaptation, there was still one smaller duplication cluster in session-facing services
- both `SessionApplicationService` and `RemoteSessionService` were manually unpacking the same interaction-context fields:
  - `surface`
  - `channel_type`
  - `conversation_id`
  - `sender_id`
- the existing `SessionSurfaceBinding` was already present, so the next good move was to promote that existing type rather than invent another abstraction

### Scope

- extend `SessionSurfaceBinding` with shared adapter helpers
- reuse it across:
  - `SessionApplicationService`
  - `RemoteSessionService`
- add one focused regression check for the binding contract

### Out Of Scope

- no new runtime-manager behavior
- no gateway-client API redesign
- no attempt to abstract operation-specific business fields

### Files In Scope

- `src/mini_agent/application/session_service.py`
- `src/mini_agent/application/session_remote_service.py`
- `tests/test_session_service.py`
- `tests/test_session_remote_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Promote `SessionSurfaceBinding` into a reusable adapter with request/value constructors.
2. Reuse it across session-service runtime-manager forwarding.
3. Reuse it across remote-service gateway-client forwarding.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- session-facing services no longer manually rebuild the same interaction-context kwargs repeatedly
- create-session async/sync remote payloads share one normalization helper
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Interaction Request Adapter Extraction + Channel Smoke Repair

## Current Execution Slice: P30.7y Interaction Request Adapter Extraction + Channel Smoke Repair (2026-04-13)

### Why This Slice Is Next

- after thinning the gateway use case, the remaining application-layer duplication was no longer a large orchestration cluster
- instead, two entrances were still hand-building similar internal chat requests:
  - gateway chat entrypoints
  - channel-ingress forwarding
- in parallel, the repo smoke layer exposed stale assumptions around prebuilt Node artifacts for the WeChat channel

### Scope

- add one shared application-layer request adapter for normalized interaction binding and chat-request construction
- rewire gateway and channel-ingress to use that seam
- run real-use smoke flows and repair any repo-level smoke blockers uncovered there

### Out Of Scope

- no new route/delegation semantics
- no session-service redesign
- no remote-channel feature expansion

### Files In Scope

- `src/mini_agent/application/interaction_request_adapter.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `src/mini_agent/application/channel_ingress_use_cases.py`
- `tests/test_interaction_request_adapter.py`
- `scripts/qq_wechat_smoke.py`
- `src/channels/types/package.json`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a shared interaction request adapter.
2. Move gateway and channel-ingress request construction onto that seam.
3. Run gateway/channel walkthroughs and API integration smoke.
4. Repair any repo-level smoke blockers exposed by `qq_wechat_smoke.py`.

### Acceptance Criteria

- gateway and channel-ingress no longer hand-build duplicated interaction request shapes
- focused adapter regression coverage exists
- gateway/channel walkthroughs stay green
- `scripts/qq_wechat_smoke.py` passes on the current repo state

### Status

- completed

## Latest Sync: 2026-04-13 Gateway Route Execution Handler Extraction

## Current Execution Slice: P30.7x Gateway Route Execution Handler Extraction (2026-04-13)

### Why This Slice Is Next

- after extracting chat-flow orchestration and main-route execution hooks, `MainAgentGatewayUseCases` still owned the routed execution shell:
  - parse `/delegate`
  - resolve message route
  - track routing diagnostics
  - execute delegation and fallback
- that kept route/delegation behavior mixed into the top-level gateway use case instead of giving it one application seam

### Scope

- extract a dedicated gateway route-execution handler for:
  - delegation-command parsing
  - route resolution and diagnostics bookkeeping
  - delegation execution
  - delegation failure fallback to the main agent
  - delegation payload / supplemental event shaping
- rewire `MainAgentGatewayUseCases` to delegate route execution and routing diagnostics to that handler

### Out Of Scope

- no chat-flow behavior redesign
- no session-service API redesign
- no change to delegation-manager semantics

### Files In Scope

- `src/mini_agent/application/gateway_route_execution_handler.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `tests/test_main_agent_surface_service.py`
- `tests/test_session_service.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated gateway route-execution handler.
2. Move route parsing, route bookkeeping, and delegation fallback into that handler.
3. Rewire `MainAgentGatewayUseCases` to use the new seam for diagnostics and routed execution.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- `MainAgentGatewayUseCases` no longer owns route/delegation execution internals
- routing diagnostics still report the same counters
- delegation success/failure/fallback behavior remains unchanged
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Gateway Agent Execution Handler Extraction

## Current Execution Slice: P30.7w Gateway Agent Execution Handler Extraction (2026-04-13)

### Why This Slice Is Next

- after chat-flow extraction, `MainAgentGatewayUseCases` still carried the low-level execution cluster for the main route:
  - `_run_agent_once(...)`
  - approval hook construction
  - activity hook construction
  - tool activity preview / output formatting helpers
- that kept agent-execution details mixed into the route coordinator instead of giving them a dedicated application seam

### Scope

- extract a dedicated gateway agent-execution handler for:
  - one-shot main-route agent execution
  - runtime approval hook injection/restoration
  - runtime activity hook construction
  - tool-call preview and output formatting helpers
- rewire `MainAgentGatewayUseCases` to call that handler for main-route and delegation-fallback execution

### Out Of Scope

- no route-table behavior changes
- no delegation-manager behavior changes
- no session turn lifecycle redesign

### Files In Scope

- `src/mini_agent/application/gateway_agent_execution_handler.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `tests/test_main_agent_surface_service.py`
- `tests/test_session_service.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated gateway agent-execution handler.
2. Move single-turn execution + approval/activity hooks into that handler.
3. Rewire main-route and delegation-fallback execution to use the new seam.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- `MainAgentGatewayUseCases` no longer owns approval/activity hook construction inline
- main-route execution behavior remains unchanged
- delegation fallback still uses the same main-agent execution semantics
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Gateway Chat Flow Handler Extraction

## Current Execution Slice: P30.7v Gateway Chat Flow Handler Extraction (2026-04-13)

### Why This Slice Is Next

- after turn-scope extraction, the next duplicated orchestration cluster lived in `MainAgentGatewayUseCases`:
  - `run_chat(...)`
  - `stream_chat_events(...)`
- both paths still repeated the same high-level flow:
  - validate / prepare turn
  - execute routed chat work
  - capture prepared context when the main route handled the turn
  - clear recovery when needed
  - record assistant reply
  - shape final response / SSE tail

### Scope

- extract a dedicated gateway chat-flow handler for:
  - dry-run response / stream handling
  - turn preparation with bootstrap error shaping
  - non-streaming chat orchestration
  - streaming chat orchestration with heartbeat / delta / done framing
- keep route resolution, approval/activity hooks, and delegation execution in `MainAgentGatewayUseCases` for this slice

### Out Of Scope

- no routing logic redesign
- no approval/activity hook redesign
- no delegation behavior changes

### Files In Scope

- `src/mini_agent/application/gateway_chat_flow_handler.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `tests/test_main_agent_surface_service.py`
- `tests/test_session_service.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated gateway chat-flow handler.
2. Move shared `run_chat` / `stream_chat_events` orchestration into that handler.
3. Rewire `MainAgentGatewayUseCases` to provide only the routed execution callback.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- `run_chat(...)` no longer owns the full turn/response orchestration inline
- `stream_chat_events(...)` no longer owns the duplicated prepare/heartbeat/finalize shell inline
- route/delegation/approval behavior remains unchanged
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-13 Turn Scope Orchestration Extraction

## Current Execution Slice: P30.7u Turn Scope Orchestration Extraction (2026-04-13)

### Why This Slice Is Next

- after the command-shell follow-up, the next remaining orchestration-heavy cluster was the managed chat-turn scope itself
- `ManagedSessionTurn.__aenter__ / __aexit__` still directly orchestrated:
  - surface binding
  - pending model application
  - pending skill reload application
  - recovery-context lookup
  - running-state transitions
  - user-message recording
  - exit-time cleanup
- that made turn-scope lifecycle another cross-layer implementation detail instead of a dedicated runtime seam

### Scope

- extract a dedicated runtime turn-scope handler
- move enter/exit turn orchestration and turn-scope helper mutations behind that seam
- rewire `ManagedSessionTurn` and manager helper wrappers to use the new runtime turn-scope boundary

### Out Of Scope

- no gateway transport changes
- no chat routing/delegation redesign
- no approval semantics changes

### Files In Scope

- `src/mini_agent/runtime/session_turn_scope_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/application/session_service.py`
- `tests/test_session_service.py`
- `tests/test_main_agent_surface_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated runtime turn-scope handler.
2. Move enter/exit turn orchestration and turn-scoped mutation helpers behind that handler.
3. Rewire `ManagedSessionTurn` plus the manager helper wrappers to use the shared runtime turn-scope seam.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- managed turn enter/exit orchestration no longer lives inline in `ManagedSessionTurn`
- manager helper methods for turn-scope state delegate to the extracted runtime seam
- chat/recovery/activity/approval flows remain green

### Status

- completed

## Latest Sync: 2026-04-13 Skill + Model Command Shell Follow-Up

## Current Execution Slice: P30.7t Skill + Model Command Shell Follow-Up (2026-04-13)

### Why This Slice Is Next

- after the initial command coordinator extraction, two manager methods still had uneven command-shell treatment:
  - `manage_session_skills(...)` only used the coordinator for transcript recording after the success path
  - `update_session_model_selection(...)` still owned a fully inline lock/mutate/persist block
- that left command-entry orchestration only partially unified

### Scope

- finish moving the skill success mutation path onto the shared command shell
- move model selection onto the same locked command-execution seam
- allow the command coordinator to support result-dependent touch/persist behavior so queued vs applied flows can stay unchanged

### Out Of Scope

- no transcript behavior changes for model selection
- no model-selection semantics redesign
- no skill reload queue redesign

### Files In Scope

- `src/mini_agent/runtime/session_command_coordinator.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_main_agent_surface_service.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Extend the command coordinator to support result-dependent touch/persist decisions.
2. Rewire skill mutation success flow to use the shared coordinator instead of manual lock/record code.
3. Rewire model selection to the same shared coordinator while preserving queued/applied behavior.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- skill mutation success no longer manually records/persists inside the manager
- model selection no longer owns a bespoke lock/mutate/persist block
- queued/applied model semantics remain unchanged
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-12 Session Command Coordinator Extraction

## Current Execution Slice: P30.7s Session Command Coordinator Extraction (2026-04-12)

### Why This Slice Is Next

- after the earlier handler extractions, `MainAgentRuntimeManager` still repeated the same command-entry orchestration pattern in several places:
  - load session
  - acquire session runtime lock
  - execute command mutation
  - append command transcript
  - touch and persist
- that duplication kept the manager thicker than necessary even after the business logic had already moved into dedicated handlers

### Scope

- add one shared command coordinator for the command-entry shell
- centralize:
  - locked execution of session command mutations
  - command transcript append wiring
  - touch/persist sequencing after command execution
- rewire command-oriented manager entrypoints to use that seam where it fits cleanly

### Out Of Scope

- no transport/API contract changes
- no new compatibility wrappers
- no redesign of skill queueing or model selection semantics in this slice

### Files In Scope

- `src/mini_agent/runtime/session_command_coordinator.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_main_agent_surface_service.py`
- `tests/test_session_service.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated runtime session command coordinator.
2. Rewire command-oriented manager methods to use the shared locked-execution and transcript flow.
3. Finish the remaining runtime-policy command path so it no longer keeps command mutation logic under `_store_lock`.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- manager no longer repeats the same lock/transcript/persist shell across the extracted command handlers
- `update_session_runtime_policy(...)` follows the same command orchestration seam as the other extracted command flows
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-12 Session Agent-Runtime Handler Extraction

## Current Execution Slice: P30.7r Session Agent-Runtime Handler Extraction (2026-04-12)

### Why This Slice Is Next

- after session catalog extraction, the next manager-owned cluster was agent runtime rebuild / reconfiguration orchestration
- `MainAgentRuntimeManager` still directly owned:
  - agent rebuild for selected model identity
  - runtime policy reconfiguration against the live agent
  - pending model-selection application
  - pending skill-reload application
  - workspace skill-reload queue marking
- that meant the manager was still mixing orchestration with agent-host mutation logic

### Scope

- extract agent runtime rebuild / reconfiguration into a dedicated handler
- centralize:
  - desired/effective runtime policy inspection
  - live-agent runtime policy reconfigure
  - rebuild with selected identity
  - pending model-selection application
  - pending skill-reload application
  - workspace skill-reload queue mutation
- keep `MainAgentRuntimeManager` responsible only for:
  - lock boundaries
  - transcript/persistence orchestration
  - higher-level response shaping

### Out Of Scope

- no model-selection plan redesign
- no skill-command routing redesign
- no transport/API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_agent_runtime_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_main_agent_surface_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated agent-runtime handler.
2. Move rebuild/policy/pending-apply/workspace-reload logic behind that seam.
3. Rewire manager and dependent runtime handlers to use the new seam.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- manager no longer contains inline rebuild / runtime reconfigure helper cluster
- runtime-policy, model-selection, and pending skill-reload behavior stay unchanged
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-12 Session Catalog Handler Extraction

## Current Execution Slice: P30.7q Session Catalog Handler Extraction (2026-04-12)

### Why This Slice Is Next

- after session live-state extraction, the next manager-owned cluster was session catalog / metadata routing
- `MainAgentRuntimeManager` still directly owned:
  - latest workspace active-session lookup
  - latest workspace persisted-record lookup
  - human-readable title allocation
  - list/detail/recent-message read routing
  - session summary dedupe rules
  - rename/share metadata mutations
- that kept the manager responsible for both orchestration and session directory/catalog semantics

### Scope

- extract session catalog / metadata handling into a dedicated handler
- centralize:
  - latest active/persisted workspace lookup
  - title allocation for new/restored sessions
  - list/detail/message read routing
  - remote-channel summary dedupe
  - rename/share metadata mutation rules
- keep `MainAgentRuntimeManager` responsible only for:
  - lock boundaries
  - invoking the catalog handler
  - persistence and registry updates

### Out Of Scope

- no session restore redesign
- no live-state mutation redesign
- no transport/API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_catalog_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_main_agent_surface_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated session catalog handler.
2. Move title allocation, latest-workspace lookup, list/detail/message read routing, dedupe, and rename/share behind that seam.
3. Rewire access/creation/read/mutation entrypoints to use the handler.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- manager no longer contains inline session catalog helper cluster
- title-hint, dedupe, list/detail/message, and rename/share behavior stay unchanged
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-12 Session Live-State Handler Extraction

## Current Execution Slice: P30.7p Session Live-State Handler Extraction (2026-04-12)

### Why This Slice Is Next

- after session creation was extracted, the next manager-heavy cluster was live session state mutation
- `MainAgentRuntimeManager` still directly owned a large set of closely related write-path logic:
  - surface binding
  - turn start / finish markers
  - transcript append
  - activity aggregation
  - pending approval tracking
  - recovery-context clearing/building
  - runtime reset state clearing
- that left the manager still acting like both:
  - orchestration coordinator
  - and low-level live session state machine

### Scope

- extract live session state mutation into a dedicated handler
- centralize:
  - surface/channel binding semantics
  - transcript append helpers
  - turn lifecycle flags
  - activity transcript aggregation
  - pending approval normalization/storage cleanup
  - recovery context mutation
  - runtime reset state cleanup
- keep `MainAgentRuntimeManager` responsible only for:
  - lock / orchestration boundaries
  - invoking the live-state handler
  - persistence

### Out Of Scope

- no read-model redesign
- no snapshot/restore redesign
- no transport/API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_live_state_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated handler for live session state / transcript mutations.
2. Move surface, turn, message, activity, approval, recovery, and reset state mutation behind that seam.
3. Rewire manager entrypoints and injected runtime dependencies to use the extracted handler.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- manager no longer contains the inline live session mutation helper cluster
- transcript/surface/pending-approval semantics stay unchanged
- recovery and reset flows stay green across restart scenarios
- focused and broad regression bundles stay green

### Status

- completed

## Latest Sync: 2026-04-12 Session Creation Handler Extraction

## Current Execution Slice: P30.7o Session Creation Handler Extraction (2026-04-12)

### Why This Slice Is Next

- after session-access extraction, the next obvious duplication left in `MainAgentRuntimeManager` was brand-new session construction
- both:
  - `get_or_create_session(...)` create-new branch
  - `create_session(...)`
  were still rebuilding the same runtime session shape inline:
  - build a fresh agent
  - bootstrap lifecycle state
  - assemble `MainAgentSessionState`
  - derive knowledge-base / sandbox / selected-model projection fields
  - register and persist
- that duplication kept session creation as another manager-owned implementation detail instead of a reusable runtime seam

### Scope

- extract brand-new session creation into a dedicated handler
- centralize:
  - title normalization/allocation
  - surface/channel normalization
  - fresh agent bootstrap
  - lifecycle bootstrap
  - initial projection assembly
  - selected-model projection seeding
- keep `MainAgentRuntimeManager` responsible only for:
  - outer policy/capacity gatekeeping
  - invoking the creation handler
  - session registry insertion
  - persistence

### Out Of Scope

- no restore/import hydration redesign
- no session-access policy redesign
- no transport/API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_creation_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Add a dedicated creation handler for brand-new runtime sessions.
2. Move shared title/surface/channel normalization and state assembly behind that handler.
3. Rewire `get_or_create_session(...)` and `create_session(...)` to use the same creation seam.
4. Re-run focused and broad regression bundles.

### Acceptance Criteria

- manager no longer contains duplicated inline new-session construction
- `create_session(...)` and `get_or_create_session(...)` share one creation path
- title-hint, surface, shared-session, and persisted-restart behavior stay unchanged
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7n Session Model Selection Handler Extraction (2026-04-12)

### Why This Slice Is Next

- after `/memory` and `/skill` command extraction, the next obvious stateful branch still embedded in `MainAgentRuntimeManager` was model selection
- `update_session_model_selection(...)` still mixed:
  - request normalization
  - busy vs idle selection semantics
  - queued vs immediate-apply response shaping
  - pending-selection application rules
- this was the next clean step toward making the manager a pure runtime orchestrator

### Scope

- extract model-selection decision logic into a dedicated handler
- move busy/idle/queued/apply-now semantics and pending-selection eligibility behind that handler seam
- keep `MainAgentRuntimeManager` responsible only for:
  - session lookup
  - lock envelope
  - applying the chosen state mutations
  - optional agent rebuild
  - persistence
  - response wrapping
- sync the shared-session walkthrough script to the already-live grouped session state shape

### Out Of Scope

- no runtime policy / approval-mode extraction yet
- no model catalog redesign
- no transport/API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_model_selection_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `scripts/shared_session_gateway_walkthrough.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a dedicated model-selection handler with request normalization and plan generation.
2. Move busy/idle/queued/apply-now semantics and pending-apply eligibility behind that handler.
3. Rewire `MainAgentRuntimeManager` to apply the returned plan and keep only orchestration responsibilities.
4. Re-run model-related runtime/gateway/TUI bundles plus the shared-session walkthrough.

### Acceptance Criteria

- manager no longer contains the inline busy/idle model-selection branch
- pending-selection application delegates to the same extracted handler seam
- model-selection transport behavior remains unchanged across immediate and queued flows
- walkthrough and regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7m Session Skill Command Handler Extraction (2026-04-12)

### Why This Slice Is Next

- after `/memory` command extraction, the next large behavior-heavy branch still embedded in `MainAgentRuntimeManager` was `/skill`
- that branch mixed:
  - skill catalog availability handling
  - read action routing (`list` / `active` / `show` / `search`)
  - workspace policy/install mutation routing
  - reload queue metadata formatting
  - final command transcript naming
- the manager was still doing both runtime orchestration and skill command formatting work

### Scope

- extract session-skill command routing into a dedicated handler
- move read/mutation payload assembly and command metadata construction behind that handler
- keep `MainAgentRuntimeManager` responsible only for:
  - session lookup
  - busy/lock envelope
  - reload queue orchestration
  - transcript append
  - persistence
  - response wrapping
- fix the stale action whitelist so implemented `uninstall` / `rollback` paths are actually reachable

### Out Of Scope

- no `/model` command decomposition yet
- no skill runtime redesign
- no transport/API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_skill_command_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_main_agent_surface_service.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a dedicated session-skill command handler with explicit read/mutation routing.
2. Move skill catalog availability handling, result assembly, and command naming behind that handler.
3. Rewire `MainAgentRuntimeManager.manage_session_skills(...)` to keep only orchestration responsibilities.
4. Add focused regression coverage for `uninstall` / `rollback`.
5. Verify with focused and broad runtime/gateway/TUI regression bundles.

### Acceptance Criteria

- manager no longer contains the large inline `/skill` branch
- skill action validation/routing lives in a dedicated runtime module
- `uninstall` / `rollback` are accepted by the same runtime entrypoint that already advertises them
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7l Session Memory Command Handler Extraction (2026-04-12)

### Why This Slice Is Next

- after the lifecycle/policy extraction, the biggest remaining behavior-heavy branch still embedded in `MainAgentRuntimeManager` was `/memory` command handling
- that branch mixed several different responsibilities:
  - action validation and routing
  - runtime selector resolution
  - durable/runtime memory read payload assembly
  - mutation result formatting
  - while the manager also still owned lock/transcript/persist flow around it
- this was the first clean step in command-handler decomposition without changing transport behavior

### Scope

- extract session-memory command routing into a dedicated handler
- move read/mutation result assembly and selector resolution behind that handler seam
- keep `MainAgentRuntimeManager` responsible only for:
  - session lookup
  - busy/lock envelope
  - transcript append
  - persistence
  - response wrapping

### Out Of Scope

- no `/skill` command decomposition yet
- no `/model` command decomposition yet
- no memory semantics or API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_memory_command_handler.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a dedicated session-memory command handler with explicit action groups.
2. Move `/memory` read/mutation routing and payload assembly behind that handler.
3. Rewire `MainAgentRuntimeManager.manage_session_memory(...)` to keep only orchestration responsibilities.
4. Verify with focused and broad runtime/gateway/TUI regression bundles.

### Acceptance Criteria

- manager no longer contains the large inline `/memory` command branch
- memory action validation/routing lives in a dedicated runtime module
- lock/busy/transcript/persist behavior stays unchanged
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7k Lifecycle / Policy Coordination Extraction (2026-04-12)

### Why This Slice Is Next

- after persistence internals extraction, the next broad responsibility cluster still centered in the manager was lifecycle/policy coordination:
  - main-workspace guardrails
  - single-main active-workspace admission checks
  - team saturation/workspace-conflict counters
  - session lifecycle refresh/reset counters
  - runtime diagnostics payload assembly for those counters
- this was the next major non-I/O, non-hydration concern suitable for extraction

### Scope

- extract a dedicated runtime policy/lifecycle coordinator for:
  - workspace guardrails
  - capacity guardrails
  - conflict/saturation counters
  - lifecycle refresh/reset counting
  - diagnostics payload construction
- rewire manager wrappers and entry flows to delegate to that coordinator
- keep outer behavior and transport contracts unchanged

### Out Of Scope

- no session-lifecycle model redesign
- no transport/API contract changes
- no command-handler decomposition yet

### Files In Scope

- `src/mini_agent/runtime/session_runtime_policy_coordinator.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a runtime policy/lifecycle coordinator service.
2. Move lifecycle refresh/expired-session/counter logic behind that coordinator.
3. Rewire workspace/capacity guardrail entry flows to delegate to the coordinator.
4. Verify with focused and broad regression bundles.

### Acceptance Criteria

- manager no longer owns lifecycle/counter state directly
- workspace/capacity guardrail logic delegates to a shared coordinator
- runtime diagnostics counter payload comes from the coordinator
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7j Persistence Wrapper Internals Extraction (2026-04-12)

### Why This Slice Is Next

- after the runtime-memory backend adapter cut, the next non-orchestrator responsibility still living inline was persistence-wrapper internals:
  - metadata registry read/write details
  - shared transcript file path/read/write/delete details
- `_MainAgentRuntimePersistence` was already acting as a wrapper, but it still carried the low-level JSON/file logic itself

### Scope

- extract helper modules for:
  - runtime metadata registry access
  - shared transcript file storage
- rewire `_MainAgentRuntimePersistence` to compose those helpers instead of owning the file/JSON logic inline
- keep persistence wrapper behavior unchanged

### Out Of Scope

- no `SessionPersistence` redesign
- no persistence format changes
- no application/session-service API changes

### Files In Scope

- `src/mini_agent/runtime/session_persistence_metadata_registry.py`
- `src/mini_agent/runtime/session_shared_transcript_store.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a runtime metadata registry helper.
2. Add a shared transcript store helper.
3. Rewire `_MainAgentRuntimePersistence` to compose both helpers.
4. Verify with focused and broad regression bundles.

### Acceptance Criteria

- `_MainAgentRuntimePersistence` no longer implements metadata JSON read/write inline
- `_MainAgentRuntimePersistence` no longer implements shared transcript path/read/write/delete inline
- persistence wrapper behavior remains unchanged while composition boundaries get clearer
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7i Runtime-Memory Backend Adapter Extraction (2026-04-12)

### Why This Slice Is Next

- after diagnostics extraction, the next infrastructure-heavy dependency still rooted in the manager was direct `WorkspaceMemoriaRuntime` access:
  - snapshot/export paths
  - hydration restore paths
  - reset/delete cleanup
  - `/memory` runtime-memory command flows
- this left the manager coupled to a concrete memory backend in multiple different styles

### Scope

- extract a dedicated runtime-memory backend adapter around `WorkspaceMemoriaRuntime`
- rewire:
  - hydration/read-model snapshot and restore paths
  - reset/delete cleanup paths
  - runtime-memory command operations (`show`, `shared show`, `shared clear`, runtime promotions)
- reduce manager backend access methods to delegation wrappers

### Out Of Scope

- no `WorkspaceMemoriaRuntime` redesign
- no memory semantics changes
- no application/session-service API changes

### Files In Scope

- `src/mini_agent/runtime/session_runtime_memory_backend_adapter.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a shared runtime-memory backend adapter.
2. Rewire snapshot/restore/hydrator integrations through the adapter.
3. Rewire manager runtime-memory command flows and cleanup paths through the adapter.
4. Verify with focused and broad regression bundles.

### Acceptance Criteria

- `MainAgentRuntimeManager` no longer directly instantiates `WorkspaceMemoriaRuntime`
- hydration/read-model/runtime-memory command paths share the same backend adapter seam
- manager runtime-memory backend methods become wrappers only
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7h Session Diagnostics Service Extraction (2026-04-12)

### Why This Slice Is Next

- after extracting the runtime-state hydrator, diagnostics were the next shared concern still anchored in the manager:
  - memory diagnostics were used by hydration, runtime capture flows, and read-model builders
  - sandbox diagnostics were used by hydration, persistence refresh, and read-model builders
- this made diagnostics a better candidate for extraction than another surface-specific cut

### Scope

- extract a dedicated diagnostics service for:
  - memory diagnostics from live sessions
  - memory diagnostics from persisted records
  - sandbox diagnostics from live sessions
  - sandbox diagnostics from persisted records
- rewire hydration builder, runtime-state hydrator, and read-model builder through that service
- reduce manager diagnostics methods to delegation wrappers

### Out Of Scope

- no memory system redesign
- no sandbox backend redesign
- no application/session-service API changes

### Files In Scope

- `src/mini_agent/runtime/session_diagnostics_service.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a shared session diagnostics service module.
2. Rewire hydration/read-model/runtime-state hydrator dependencies to use that service.
3. Reduce manager diagnostics methods to delegation wrappers.
4. Verify with focused and broad regression bundles.

### Acceptance Criteria

- memory/sandbox diagnostics implementations no longer live inline in `MainAgentRuntimeManager`
- hydration and read-model code depend on a shared diagnostics service instead of manager-owned implementations
- manager diagnostics methods become boundary wrappers only
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7g Session Runtime State Hydrator Extraction (2026-04-12)

### Why This Slice Is Next

- after hydration unification, the shared `_hydrate_session_unlocked(...)` path still mixed runtime-state substeps:
  - runtime task-memory restore
  - workspace-shared runtime-memory merge
  - prepared-context restore onto the live agent
  - diagnostics refresh
- those are not session assembly anymore; they are runtime-state synchronization concerns

### Scope

- extract a dedicated runtime-state hydrator for:
  - post-build runtime-memory restore
  - prepared-context restore/capture
  - diagnostics refresh
- rewire the shared hydration helper to delegate these substeps
- keep manager wrapper methods as boundary methods while moving implementation out

### Out Of Scope

- no runtime-memory storage redesign
- no `SessionPersistence` redesign
- no application/session-service API changes

### Files In Scope

- `src/mini_agent/runtime/session_runtime_state_hydrator.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a dedicated runtime-state hydrator module.
2. Move prepared-context restore/capture and diagnostics refresh behind that hydrator seam.
3. Move shared hydration post-build runtime-memory restore behind that hydrator seam.
4. Verify with focused and broad regression bundles.

### Acceptance Criteria

- `_hydrate_session_unlocked(...)` no longer directly restores runtime-memory payloads or prepared-context state
- prepared-context restore/capture implementations no longer live inline in `MainAgentRuntimeManager`
- runtime-state synchronization lives in `session_runtime_state_hydrator.py`
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7f Session Hydration Unification (2026-04-12)

### Why This Slice Is Next

- after extracting restore/load seams, the next visible duplication was hydration assembly itself:
  - `import_session_snapshot(...)` still rebuilt a session inline
  - `_restore_persisted_session_unlocked(...)` now used extracted restore payloads, but still ran a similar runtime assembly flow
- this left two near-parallel paths for:
  - build agent
  - apply runtime policy
  - restore messages/tokens
  - apply KB state
  - assemble session state
  - restore runtime memory/context

### Scope

- replace the restore-specific builder with a hydration builder that covers both:
  - persisted record restore
  - imported snapshot hydration
- extract a shared `_hydrate_session_unlocked(...)` runtime assembly flow
- route `import_session_snapshot(...)` and `_restore_persisted_session_unlocked(...)` through that shared hydration path

### Out Of Scope

- no runtime-memory persistence redesign yet
- no `SessionPersistence` redesign
- no application/session-service API changes

### Files In Scope

- `src/mini_agent/runtime/session_hydration_builder.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Replace the restore builder with a hydration builder that can normalize both record and snapshot inputs.
2. Extract a shared runtime hydration helper for agent/session assembly.
3. Rewire import and restore flows to use that shared hydration path.
4. Verify with focused and broad runtime/gateway/TUI regression bundles.

### Acceptance Criteria

- `import_session_snapshot(...)` no longer hand-assembles hydrated runtime sessions inline
- `_restore_persisted_session_unlocked(...)` and import snapshot both delegate to a shared hydration helper
- hydration-specific normalization and transcript import live in `session_hydration_builder.py`
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7e Runtime Restore/Load Boundary Extraction (2026-04-12)

### Why This Slice Is Next

- after extracting the runtime persistence save builder, the remaining mixed seam was restore/load:
  - `MainAgentRuntimeManager._restore_persisted_session_unlocked(...)` still mixed runtime orchestration with pure state reconstruction
  - `_MainAgentRuntimePersistence.load_session_record(...)` still mixed storage reads with runtime-record normalization and transcript attachment
- this kept the manager too aware of persisted-record shape and left persistence load less clean than persistence save

### Scope

- extract a dedicated runtime restore builder for:
  - transcript import from persisted records
  - persisted-record restore payload normalization
  - reconstructed session-state assembly
- extract a persistence loader for runtime-record filtering and shared-transcript attachment
- rewire read-model construction to use the extracted transcript-import seam

### Out Of Scope

- no runtime-memory restore redesign yet
- no `SessionPersistence` redesign
- no public API or transport contract changes

### Files In Scope

- `src/mini_agent/runtime/session_restore_builder.py`
- `src/mini_agent/runtime/session_persistence_loader.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Extract transcript import and persisted-record normalization into a restore builder.
2. Move reconstructed `MainAgentSessionState` assembly behind that builder seam.
3. Extract persisted-record load/list normalization into a persistence loader.
4. Verify with focused and broad runtime/gateway/TUI regression bundles.

### Acceptance Criteria

- persisted-record transcript import no longer lives inline in `MainAgentRuntimeManager`
- `_restore_persisted_session_unlocked(...)` delegates state assembly to a dedicated restore builder
- `_MainAgentRuntimePersistence.load_session_record(...)` and list filtering delegate record normalization to a dedicated loader
- focused and broad regression bundles stay green

### Status

- completed

## Current Execution Slice: P30.7d Runtime Persistence Record Builder Extraction (2026-04-12)

### Why This Slice Is Next

- after extracting the runtime read-model builder, the next mixed runtime seam was persistence save:
  - `_MainAgentRuntimePersistence.save_session(...)` still assembled metadata records inline
  - it also refreshed sandbox diagnostics itself, which is runtime-state work rather than storage work
- this kept persistence from being a clean storage boundary

### Scope

- extract runtime persistence record/transcript serialization into a dedicated builder module
- move sandbox-diagnostics refresh back to runtime manager before persistence is called
- keep `_MainAgentRuntimePersistence` focused on file and metadata I/O

### Out Of Scope

- no persisted-record restore extractor yet
- no `SessionPersistence` redesign
- no public API changes

### Files In Scope

- `src/mini_agent/runtime/session_persistence_record_builder.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Add a persistence record builder for transcript-entry serialization and runtime metadata-record assembly.
2. Inject that builder into `_MainAgentRuntimePersistence`.
3. Move sandbox refresh to `_persist_session_unlocked(...)`.
4. Verify with focused runtime/gateway/session regression bundles and ruff.

### Acceptance Criteria

- `_MainAgentRuntimePersistence.save_session(...)` no longer assembles the large metadata record inline
- persistence no longer calls `collect_sandbox_diagnostics(...)` directly
- runtime manager refreshes sandbox diagnostics before delegating persistence save
- focused regression bundle stays green

### Status

- completed

## Current Execution Slice: P30.7c Runtime Session Read-Model Builder Extraction (2026-04-12)

### Why This Slice Is Next

- after the runtime session state composition cut, the next obvious mixed responsibility inside `MainAgentRuntimeManager` was read-model construction:
  - summary/detail/snapshot builders still lived inside the runtime coordinator
  - recovery/message/pending-approval projection helpers were still bundled beside execution logic
- the grouped session state made field ownership explicit, so we could now extract the builder layer without first untangling flat-field ambiguity

### Scope

- extract runtime session summary/detail/snapshot construction into a dedicated builder module
- move the related recovery/message/pending-approval read-model helpers behind that builder seam
- keep runtime manager behavior unchanged by delegating to the new builder

### Out Of Scope

- no persistence save/load extraction yet
- no application-layer lease/session interface narrowing yet
- no transport/API contract changes

### Files In Scope

- `src/mini_agent/runtime/session_read_model_builder.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Introduce a dedicated runtime session read-model builder with injected normalization/diagnostic callbacks.
2. Move summary/detail/snapshot plus recovery/message/pending-approval read-model construction into that module.
3. Reduce runtime manager methods to delegation shells.
4. Run focused runtime/gateway/TUI/API regression bundles.

### Acceptance Criteria

- read-model construction no longer lives as large inline builder bodies inside `MainAgentRuntimeManager`
- runtime manager delegates to an extracted builder module for session summary/detail/snapshot assembly
- focused regression bundle stays green

### Status

- completed

## Current Execution Slice: P30.7b Runtime Session State Composition Cut (2026-04-12)

### Why This Slice Is Next

- after the projection-boundary cleanup, the next biggest runtime seam was still the session state object itself:
  - `MainAgentSessionState` still mixed projection/session truth, runtime host handles, and transcript state in one flat dataclass
- leaving that flat shape in place would keep:
  - `MainAgentRuntimeManager` field ownership blurry
  - `SessionService` tied to a god-object session state
  - future persistence/projection extraction harder than necessary

### Scope

- split `MainAgentSessionState` into grouped sub-state buckets:
  - `projection`
  - `runtime`
  - `transcript_state`
- migrate runtime-manager access paths onto those grouped buckets
- migrate `SessionService.ManagedSessionTurn` onto the grouped buckets
- update focused runtime/gateway tests that inspect internal session state directly

### Out Of Scope

- no persistence extractor yet
- no projection-builder extractor yet
- no public application interface narrowing yet

### Files In Scope

- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/application/session_service.py`
- `tests/test_main_agent_surface_service.py`
- `tests/test_session_service.py`
- `tests/test_p19_runtime_matrix.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Introduce grouped runtime session sub-state dataclasses.
2. Update session construction paths to populate grouped state explicitly.
3. Migrate runtime-manager and session-service field access to explicit grouped state.
4. Run focused runtime/gateway/session regression bundles.

### Acceptance Criteria

- `MainAgentSessionState` no longer stores runtime host, projection, and transcript fields flat on one object
- runtime/session-service code paths use explicit grouped state access
- focused runtime/gateway/session bundles stay green

### Status

- completed

## Current Execution Slice: P30.7a Session Projection Boundary Cleanup (2026-04-12)

### Why This Slice Is Next

- the runtime/session scan showed two adjacent boundary leaks that were cheap to fix before the bigger runtime-state split:
  - `src/mini_agent/session/projection.py` still mixed shared transport read models with terminal-only presentation state
  - both session projection code and runtime manager still widened summary -> detail payloads through `summary.__dict__`
- leaving those in place would keep the upcoming runtime decomposition tied to:
  - terminal-specific concerns in a shared session module
  - brittle dataclass-internal spreading that fights future `slots=True` tightening

### Scope

- move terminal-only `TerminalSessionProjection` out of the shared session projection module
- introduce an explicit `SessionDetailProjection.from_summary(...)` constructor
- route runtime-manager detail builders through the explicit constructor
- update TUI/tests to the new terminal projection location

### Out Of Scope

- no `MainAgentSessionState` grouped-state split yet
- no gateway/session-service API redesign yet
- no behavior changes to session semantics or TUI rendering

### Files In Scope

- `src/mini_agent/session/projection.py`
- `src/mini_agent/session/__init__.py`
- `src/mini_agent/tui/session_projection.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_session_projection.py`
- `progress.md`
- `findings.md`
- `task_plan.md`

### Execution Steps

1. Remove the terminal presentation model from the generic session projection module.
2. Add an explicit detail-projection constructor from summary state.
3. Update runtime/TUI callsites to use the explicit builder instead of `summary.__dict__`.
4. Verify focused session/TUI/runtime regression bundles.

### Acceptance Criteria

- `mini_agent.session.projection` only contains shared session read models, not terminal presentation DTOs
- no summary -> detail construction in the touched session/runtime paths relies on `summary.__dict__`
- TUI still renders terminal session metadata correctly through the new terminal-specific module
- focused regression bundle stays green

### Status

- completed

## Current Execution Slice: P30.2/P30.3 TUI Session State Composition Cut (2026-04-12)

### Why This Slice Is Next

- `P30.1` locked the four-entrance surface contract, but TUI still kept session projection, runtime handles, and view-only state inside one wide `TuiSession`
- that kept the same old boundary leak alive inside the developer surface:
  - remote session projection fields looked like local runtime truth
  - runtime handles were mixed with persisted UI state
  - follow-up refactors would still be operating on one ambiguous struct

### Scope

- split `TuiSession` into grouped state buckets:
  - `projection`
  - `runtime`
  - `view`
- migrate the first bounded set of callsites to the new grouped structure:
  - UI state save/load
  - remote summary/detail application
  - submission-loop attach/shutdown
  - runtime reset and chat-scroll state handling
- add focused regression coverage that locks the new grouped state contract

### Out Of Scope

- no gateway/session-service redesign in this slice
- no QQ adapter binding redesign in this slice
- no full `app.py` callsite migration in one pass

### Files In Scope

- `src/mini_agent/tui/app.py`
- `tests/test_tui_app.py`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Execution Steps

1. Introduce grouped `TuiSession` sub-state dataclasses for projection/runtime/view concerns.
2. Move the most failure-prone save/load, projection-sync, runtime-loop, and chat-view helpers onto the grouped state.
3. Add focused tests that lock alias compatibility and nested-state behavior.
4. Verify the TUI regression bundle and the already-landed P30.1 shared-session bundles.

### Acceptance Criteria

- `TuiSession` is no longer defined as one flat wide bag of mixed concerns
- UI persistence/restoration reads from view state only
- remote summary/detail writes flow into projection state
- local submission-loop lifecycle writes flow into runtime state
- existing shared-session behavior remains stable in focused regression bundles

### Status

- completed

## Current Execution Slice: P30.1 Code Guardrails - Four-Entrance Interaction Surface Contract (2026-04-12)

### Why This Slice Is Next

- architecture wording is corrected, but runtime/application code still accepted free-form `surface/channel_type` pairs without one shared boundary model
- that left room for future drift where product entrances and concrete channel adapters get mixed again
- we needed one code-level seam to classify:
  - user entrance (`cli/tui/webui/remote`)
  - concrete remote channel adapter (`qq/wechat/feishu`)

### Scope

- add a shared interaction-surface resolver
- wire gateway/chat and channel-ingress flows through the resolver
- wire runtime surface binding through the same resolver while preserving current `qq` session behavior
- add focused tests for the new classification seam

### Out Of Scope

- no API schema expansion in this slice
- no session ownership redesign in this slice
- no WebUI/remote channel feature expansion in this slice

### Files In Scope

- `src/mini_agent/runtime/interaction_surface.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `src/mini_agent/application/channel_ingress_use_cases.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_interaction_surface.py`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Execution Steps

1. Add a shared resolver for surface/channel normalization and entrance classification.
2. Route gateway and channel-ingress request normalization through that resolver.
3. Route runtime surface binding through the same resolver without changing existing `qq/tui` semantics.
4. Verify with focused tests around interaction classification + gateway/channel contracts.

### Acceptance Criteria

- one shared resolver exists for entrance/channel classification
- gateway/application/runtime paths use the same resolver instead of ad hoc string handling
- existing `qq` session behavior remains stable in focused regression bundles

### Status

- completed

## Current Execution Slice: P30 Four-Entrance Architecture Correction Sync (2026-04-12)

### Why This Slice Is Next

- the previous P30 wording still flattened the product entrances into `CLI / TUI / WebUI / QQ`
- the corrected design is now clearer:
  - the user-side product has four entrances:
    - `CLI`
    - `TUI`
    - `WebUI`
    - `Remote Interaction`
  - `QQ / WeChat / Feishu` are concrete channel adapters under the remote entrance
- if this is not corrected first, later refactor work will keep mixing product entrances with implementation adapters

### Scope

- rewrite the active architecture wording around the four-entrance model
- update the P30 correction doc and executable task plan
- re-anchor working notes so follow-up refactor work starts from the corrected taxonomy

### Out Of Scope

- no runtime behavior change in this slice
- no new channel feature work
- no WebUI implementation restart in this slice

### Files In Scope

- `docs/ARCHITECTURE.md`
- `docs/P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `docs/DEVELOPMENT_INDEX.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

### Execution Steps

1. Rewrite the active architecture doc so the entrance model is `CLI / TUI / WebUI / Remote Interaction`.
2. Clarify that `QQ / WeChat / Feishu` are remote-channel adapters, not peer product entrances.
3. Update the P30 refactor plan so the next cuts follow the corrected entrance taxonomy.
4. Sync the working notes so later implementation slices do not drift back to the old wording.

### Acceptance Criteria

- active architecture docs no longer list `QQ` as a peer product entrance
- the remote entrance and its adapter sub-layer are explicit
- the P30 execution order is updated to start from the four-entrance boundary lock

### Status

- completed

## Current Execution Slice: P30.1 QQ Channel Hard Consolidation (2026-04-12)

### Why This Slice Is Next

- the active architecture already locks `QQ` as a transport/adapter only surface under `P30`
- the repo still contains parallel historical QQ paths:
  - `src/apps/qqbot_channel` as the actual runtime path
  - `src/channels/qqbot` as a separate Node/TypeScript channel package
  - `src/mini_agent/channels/qqbot.py` as an older Python OneBot adapter
- leaving those paths alive keeps the canonical architecture blurry and invites the exact session-ownership drift we are trying to remove

### Scope

- keep `src/apps/qqbot_channel` as the only QQ runtime implementation
- keep `qq-official-bot` as the external SDK dependency
- migrate smoke coverage and active references to that one path
- delete historical QQ implementations and update active docs/tests/scripts accordingly

### Out Of Scope

- no new QQ feature expansion
- no second QQ protocol implementation
- no compatibility shell for the deleted historical paths

### Files In Scope

- `src/apps/qqbot_channel/*`
- `src/channels/qqbot/*`
- `src/mini_agent/channels/qqbot.py`
- `scripts/qq_wechat_smoke.py`
- `tests/test_channels.py`
- active docs that still reference the removed QQ paths

### Execution Steps

1. Refactor `src/apps/qqbot_channel` into the only supported QQ adapter path and keep its runtime surface thin.
2. Add or migrate QQ smoke coverage onto the app path.
3. Delete `src/channels/qqbot` and the legacy Python QQ adapter.
4. Remove/update tests, scripts, and active docs that still point to removed paths.
5. Run focused verification for QQ runtime and docs/test hygiene.

### Acceptance Criteria

- repo has exactly one live QQ implementation path: `src/apps/qqbot_channel`
- QQ runtime still uses `qq-official-bot`
- smoke/testing no longer depends on `src/channels/qqbot` or `mini_agent.channels.qqbot`
- active docs describe QQ only as the optional adapter app bound to the shared gateway/session services

### Status

- completed

## Current Execution Slice: P30 Surface / Session Refactor Task Planning (2026-04-12)

### Why This Slice Is Next

- the architectural correction in `P30` is now written, but still too high-level to steer implementation safely
- after the latest discussion, the most important correction is explicit:
  - sessions must not be cut apart by `CLI / TUI / WebUI / QQ`
  - surfaces only operate sessions
  - QQ is a channel adapter reusing shared semantics, not a session owner and not a TUI-owned subtype
- before more refactor code starts, that correction needs to become an executable task plan

### Scope

- turn the P30 architecture correction into concrete implementation phases
- define the next recommended execution order
- sync `task_plan.md` and doc indexes so the refactor entry point is explicit

### Out Of Scope

- no production code changes in this slice
- no runtime behavior changes
- no new session surface features

### Files In Scope

- `docs/P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`
- `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- `task_plan.md`
- `docs/DEVELOPMENT_INDEX.md`
- `docs/DOCS_INDEX.md`

### Execution Steps

1. Convert the P30 architecture correction into concrete phases and acceptance criteria.
2. Define the next recommended implementation order.
3. Register the new task-plan doc in active indexes.
4. Re-anchor `task_plan.md` so P30 is the next structural execution entry.

### Acceptance Criteria

- one executable P30 task-plan doc exists
- `task_plan.md` points to the P30 execution track
- development indexes expose the new refactor entry point

### Status

- completed

## Current Execution Slice: P29.3e Local Skill Command Convergence (2026-04-12)

### Why This Slice Is Next

- P29.3a through P29.3d proved the shared local command seam can carry:
  - status-style commands
  - local session/workspace toggles
  - prepared-context policy mutation
  - heavyweight memory execution semantics
- the next duplicated command family had to be `skill` because:
  - local `skill` still had one of the largest duplicated branches in TUI and CLI
  - it mixes catalog reads, workspace policy mutation, and runtime-reload handoff
  - leaving it split would keep the operator-command boundary half-finished

### Scope

- extend the shared local operator command service with local `skill` semantics
- route TUI local `skill` execution through that shared service
- keep TUI/CLI surface-specific runtime reload orchestration outside the shared seam
- add focused regression for shared local `skill` list/show/install/mode behavior

### Out Of Scope

- no remote shared-session `skill` transport rewrite in this slice
- no `model` command convergence yet
- no QQ command execution convergence yet

### Files In Scope

- `src/mini_agent/commands/execution.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/cli_interactive.py`
- `tests/test_command_execution_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Add shared local `skill` execution semantics with typed results.
2. Route CLI local `/skill` execution through the shared service.
3. Route TUI local `/skill` execution through the shared service.
4. Add focused regression for shared `skill` list/show/install/mode behavior.
5. Re-run the focused command/TUI/CLI/readiness bundle.

### Acceptance Criteria

- TUI and CLI local `skill` behavior no longer lives in duplicated ad hoc execution branches
- local `skill` catalog/policy/mutation semantics are shared even if final reload messaging still differs
- runtime reload ownership remains surface-specific instead of leaking back into the shared execution seam

### Status

- completed

## Current Execution Slice: P29.3d Local Memory Command Convergence (2026-04-12)

### Why This Slice Is Next

- P29.3a established the shared local command execution seam with `mcp` and `sandbox`
- P29.3b extended that seam to `kb`
- P29.3c proved the seam can carry real local mutation semantics with `context`
- the next command family had to be `memory` because:
  - it still carried the largest duplicated local operator branch in both TUI and CLI
  - it mixes read-only diagnostics with real workspace/runtime mutations
  - leaving it split would keep session-boundary repair incomplete

### Scope

- extend the shared local operator command service with local `memory` semantics
- route TUI local memory execution through that shared service
- route CLI local memory execution through that shared service
- unify shared `/memory show` argument parsing between TUI and CLI

### Out Of Scope

- no remote shared-session memory transport rewrite in this slice
- no `skill` or `model` command convergence yet
- no QQ command execution convergence yet

### Files In Scope

- `src/mini_agent/commands/execution.py`
- `src/mini_agent/commands/__init__.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/cli_interactive.py`
- `tests/test_command_execution_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Add shared local `memory` execution semantics with typed results.
2. Route CLI local `/memory` execution through the shared service.
3. Route TUI local `/memory` execution through the shared service.
4. Add focused regression for shared memory parsing and mutation behavior.
5. Re-run the focused command/TUI/CLI/readiness bundle.

### Acceptance Criteria

- TUI and CLI local `memory` behavior no longer lives in duplicated ad hoc execution branches
- local `memory` read/mutation semantics are shared even if final surface feedback still differs
- shared `/memory show` parsing no longer exists in two separate helpers

### Status

- completed

## Current Execution Slice: P29.3c Local Context Command Convergence (2026-04-12)

### Why This Slice Is Next

- P29.3a already proved the shared command execution seam with `mcp` and `sandbox`
- P29.3b extended that seam to local `kb`
- the next best candidate was `context` because:
  - it exists on both TUI and CLI
  - it contains real local state mutation semantics
  - but it is still smaller and safer than `memory`

### Scope

- extend the shared local operator command service with local `context` semantics
- route local `context` handling in TUI and CLI through that service
- keep remote shared-session context mutation transport unchanged in this slice

### Out Of Scope

- no remote context transport rewrite
- no `/memory` migration yet
- no QQ command execution convergence yet

### Files In Scope

- `src/mini_agent/commands/execution.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/cli_interactive.py`
- `tests/test_command_execution_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Add shared local `context` execution semantics with typed results.
2. Route CLI local `/context` handling through the shared service.
3. Route TUI local `/context` handling through the shared service while keeping remote update transport unchanged.
4. Re-run focused TUI/CLI/command/readiness regression bundles.

### Acceptance Criteria

- TUI and CLI local `context` behavior no longer lives in separate ad hoc branches
- local context validation, budget parsing, source-list normalization, and reset semantics are shared
- readiness walkthroughs still pass, including the local `context reset` behavior

### Status

- completed

## Current Execution Slice: P29.3b Local KB Command Convergence (2026-04-12)

### Why This Slice Is Next

- P29.3a already proved the shared command execution seam with:
  - `mcp`
  - `sandbox`
- the next best command family was `kb` because:
  - it exists in both TUI and CLI
  - it still had duplicated local validation and toggle semantics
  - it is more stateful than `sandbox` but still much smaller than `context` or `memory`

### Scope

- extend the shared local operator command service with local `kb` semantics
- route local `kb status|on|off` through that shared service in TUI and CLI
- keep remote shared-session `kb` handling unchanged in this slice

### Out Of Scope

- no remote `kb` command rewrite
- no `/context` or `/memory` migration yet
- no QQ-side command execution unification yet

### Files In Scope

- `src/mini_agent/commands/execution.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/cli_interactive.py`
- `tests/test_command_execution_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Add shared local `kb` execution semantics with typed results.
2. Route TUI local `kb` handling through the shared service.
3. Route CLI local `kb` handling through the shared service.
4. Re-run focused TUI/CLI/command/readiness regression bundles.

### Acceptance Criteria

- TUI and CLI local `kb` behavior no longer lives in separate ad hoc branches
- local `kb` status/toggle semantics are shared even if final rendering still differs by surface
- focused regression includes direct service tests for shared `kb` semantics

### Status

- completed

## Current Execution Slice: P29.3a Local Operator Command Service First Cut (2026-04-12)

### Why This Slice Is Next

- P29.1a already unified session read truth
- P29.2a and P29.2b already moved session mutation ownership out of raw gateway/TUI transport paths
- the next remaining drift surface is command execution:
  - command syntax/help/catalog are shared
  - command behavior still lives separately in TUI and CLI
- the safest first cut is not the whole command surface at once
  - start with low-coupling operator commands
  - avoid entangling active session execution flow while the command seam is still being extracted

### Scope

- introduce a shared local operator command execution service
- migrate one stable, high-value command slice through it:
  - `mcp`
  - `sandbox`
- keep remote shared-session command branches unchanged in this slice

### Out Of Scope

- no full `/context` or `/memory` migration yet
- no QQ command execution unification yet
- no session execution-stream rewrite

### Files In Scope

- `src/mini_agent/commands/execution.py`
- `src/mini_agent/commands/__init__.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/cli_interactive.py`
- `tests/test_command_execution_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Add a shared local operator command execution service with typed results.
2. Route local `mcp` command handling in TUI/CLI through it.
3. Route local `sandbox status` handling in TUI/CLI through it.
4. Re-run focused TUI/CLI/command/readiness regression bundles.

### Acceptance Criteria

- TUI and CLI local `mcp` command semantics no longer live in separate ad hoc branches
- TUI and CLI local `sandbox status` semantics no longer live in separate ad hoc branches
- focused regression includes direct tests for the new shared command execution seam

### Status

- completed

## Current Execution Slice: P29.2b TUI Remote Session Service Convergence (2026-04-12)

### Why This Slice Is Next

- P29.1a already unified session read models
- P29.2a already extracted gateway-side session mutation and turn ownership
- the next highest-value leak was still in TUI:
  - remote shared-session mutations still called `gateway_client` directly
  - TUI still owned raw transport-shape assumptions for model/policy/context/memory/skill/control flows

### Scope

- add one typed client-side remote session service for TUI
- move remote session mutation/control flows in TUI off raw `gateway_client` calls
- make TUI consume typed DTOs for remote session mutation results
- add focused regression coverage for the new remote service seam

### Out Of Scope

- no remote `run_chat` execution-path rewrite in this slice
- no CLI migration yet
- no shared command execution service yet

### Files In Scope

- `src/mini_agent/application/session_remote_service.py`
- `src/mini_agent/application/__init__.py`
- `src/mini_agent/tui/app.py`
- `tests/test_session_remote_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Add a typed remote session service over the TUI gateway client.
2. Route TUI remote session CRUD/control/mutation flows through that service.
3. Replace raw dict assumptions in TUI with typed DTO handling where those flows now use the service.
4. Re-run focused TUI/session/gateway regression bundles.

### Acceptance Criteria

- TUI no longer calls raw `gateway_client` methods for remote session mutation/control flows
- remote model/runtime-policy/context/memory/skill/approval/control actions go through `RemoteSessionService`
- focused regression remains green with explicit coverage for the new typed remote service seam

### Status

- completed

## Current Execution Slice: P29.2a Session Application Service Extraction (2026-04-12)

### Why This Slice Is Next

- P29.1a already made session read models explicit
- the next highest-value boundary repair is removing gateway/use-case ownership of runtime session internals
- the main leakage point was turn scaffolding:
  - `session.lock`
  - surface binding
  - pending model/skill application
  - turn start/finish
  - session transcript mutation

### Scope

- add a shared `session_service`
- move session read/mutation wrappers into that service
- move gateway chat/stream turn scoping behind a managed service-owned turn lease
- remove direct `MainAgentSessionState` and `session.lock` usage from gateway use cases

### Out Of Scope

- no full runtime-manager decomposition yet
- no TUI local runtime-host extraction yet
- no behavior redesign of approvals/delegation/activity streams

### Files In Scope

- `src/mini_agent/application/session_service.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `src/mini_agent/application/__init__.py`
- `tests/test_session_service.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Introduce `SessionApplicationService` and a managed turn lease.
2. Route session CRUD/detail/control wrappers through the service.
3. Route gateway `run_chat` / `stream_chat_events` through the service-owned turn lease.
4. Verify gateway/shared-session/TUI/readiness regression bundles remain green.

### Acceptance Criteria

- `MainAgentGatewayUseCases` no longer imports `MainAgentSessionState`
- `MainAgentGatewayUseCases` no longer locks `session.lock` directly
- gateway session mutations and turn scaffolding go through the shared service
- focused and readiness-adjacent regression bundles stay green

### Status

- completed

## Current Execution Slice: P29.1a Shared Session Projection Seam (2026-04-12)

### Why This Slice Is Next

- the P29 audit and hard-refactor plan are already written
- the safest first structural cut is to unify session read-model assembly before moving behavior
- runtime and TUI still each infer session truth in their own way, which is the immediate risk surface

### Scope

- add shared session projection models under `src/mini_agent/session/`
- route runtime session summary/detail DTO assembly through those projections
- route TUI session summary/detail display semantics through the same projection seam
- add focused regression coverage for transport and terminal projection behavior

### Out Of Scope

- no session behavior rewrite yet
- no gateway/service ownership extraction yet
- no compatibility shell or parallel session abstraction

### Files In Scope

- `src/mini_agent/session/projection.py`
- `src/mini_agent/session/__init__.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/tui/app.py`
- `tests/test_session_projection.py`
- `task_plan.md`
- `progress.md`
- `findings.md`

### Execution Steps

1. Define shared session transport and terminal projections.
2. Refactor runtime summary/detail builders to emit DTOs from shared projections.
3. Refactor TUI session read/display helpers to consume shared projections.
4. Run focused and readiness-adjacent regression bundles.

### Acceptance Criteria

- runtime session DTO assembly uses shared projection objects
- TUI session display helpers use shared projection semantics
- focused regression and readiness-adjacent tests stay green

### Status

- completed

## Current Execution Slice: P29 Session Boundary Hard-Refactor Planning (2026-04-12)

### Why This Slice Is Next

- the audit is finished
- the project now has a written problem statement and evidence anchors
- the next failure risk is no longer "unknown architecture smell"; it is implementing more work before the session boundary is repaired

### Scope

- translate the P29 audit into a concrete hard-refactor execution plan
- define the target boundaries, refactor phases, first implementation slice, and acceptance strategy
- sync development index and working logs so future implementation follows the same plan

### Out Of Scope

- no runtime behavior change in this planning slice
- no partial compatibility layers
- no new session-facing feature work

### Files In Scope

- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/DEVELOPMENT_INDEX.md`
- `docs/REFACTOR_TASKS.md`
- `docs/P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md`
- `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`

### Execution Steps

1. Define the target boundary model for session, runtime, application service, and surfaces.
2. Define the phased hard-refactor sequence.
3. Lock the first implementation slice so coding can start without re-arguing structure.
4. Sync planning/index docs to mark P29 as the active architecture-repair track.

### Acceptance Criteria

- a formal P29 implementation plan exists
- the first implementation slice is explicit and testable
- development docs point to the P29 audit and implementation plan

### Status

- in_progress

## Current Execution Slice: P29 Session Boundary And Ownership Audit (2026-04-12)

### Why This Slice Is Next

- the latest session unification work exposed a deeper architecture problem than one isolated bug
- the active risk is now boundary collapse:
  - no single session owner
  - surface/runtime/persistence responsibilities mixed together
  - command semantics duplicated by surface
- continuing feature work on top of that shape would compound the refactor cost

### Scope

- perform a code-level audit of session / gateway / TUI / CLI / QQ boundaries
- identify duplicated ownership, cross-layer leakage, orphan abstractions, and overloaded services
- record a hard-refactor direction before more session-facing features are added

### Out Of Scope

- no functional refactor in this slice
- no compatibility shell work
- no new feature delivery on top of the current session stack

### Files In Scope

- `task_plan.md`
- `findings.md`
- `progress.md`
- `docs/P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md`
- session / runtime / TUI / CLI / gateway / QQ source files for inspection

### Execution Steps

1. Audit canonical session ownership across Python runtime, TUI, CLI, and QQ/channel surfaces.
2. Audit command execution ownership across TUI / CLI / QQ.
3. Identify stale, duplicate, or orphaned abstractions still exported as active APIs.
4. Record a hard-refactor plan centered on boundary repair before more session work continues.

### Acceptance Criteria

- one written report exists with concrete boundary findings and evidence
- task planning files reflect that P29 is now the active architecture slice
- the next refactor direction is explicit enough to guide hard restructuring

### Status

- completed

## Current Execution Slice: P24 Demo Baseline Acceptance Lock (2026-04-11)

### Why This Slice Is Next

- the Windows sandbox baseline is now strong enough for the current single-host demo target
- deeper sandbox work such as CPU/time quotas or non-Windows native backends is not a current blocker
- the active top-level goal is still one stable, reviewable demo path centered on `TUI / CLI / QQ / gateway`

### Scope

- freeze sandbox work at the current "good enough for demo" baseline unless a real blocker appears
- turn the current runtime into one explicit demo-acceptance path instead of opening another subsystem branch
- use the existing readiness scripts and command checklist as the primary acceptance seam
- only fix issues that materially affect:
  - local TUI/CLI use
  - shared-session QQ/gateway handoff
  - session/model/memory/KB/skill operator continuity

### Out Of Scope

- no additional sandbox backend work unless a concrete real-use failure appears
- no WebUI restart
- no new marketplace / remote package-management workflow in this slice

### Files In Scope

- `task_plan.md`
- `progress.md`
- `findings.md`
- `docs/DEVELOPMENT_INDEX.md`
- `docs/P24_REAL_USE_COMMAND_ACCEPTANCE_CHECKLIST.md`
- readiness / walkthrough docs as needed

### Execution Steps

1. Record that sandbox is intentionally paused at the current baseline.
2. Re-anchor the active phase to P24 demo-baseline acceptance.
3. Keep the command-level and scripted acceptance docs aligned with the live runtime surface.
4. Use the next implementation slice only for demo-blocking gaps discovered from that acceptance path.

### Acceptance Criteria

- project docs clearly show sandbox is no longer the active track
- current active track is explicitly "demo-baseline acceptance"
- acceptance docs include the live sandbox-status operator seam now present in CLI/TUI
- future work resumes from demo-critical gaps, not optional sandbox expansion

### Status

- in_progress

### Current Audit State

- completed in this slice:
  - command catalog / unified entry preflight
  - scripted TUI checklist
  - scripted TUI interaction walkthrough
  - scripted shared-session walkthrough
  - scripted channel-ingress walkthrough
  - targeted readiness regression bundle
  - live headless JSON prompt against a real configured model
  - runtime stack lifecycle validation (`qq status/down/up/logs`)
  - full regression while a real local gateway/qq demo stack was already running
- remaining high-value unverified item:
  - live external QQ roundtrip acceptance on the real bot path

### 2026-04-11 Demo Readiness Note

- real-use acceptance exposed one genuine demo/test isolation bug:
  - if the local gateway runtime stack is already running on `127.0.0.1:8008`
  - gateway `TestClient` suites fail because the gateway lifespan instance lock also blocks pytest startup
- the fix is now explicit in test bootstrap:
  - pytest defaults `MINI_AGENT_STUDIO_ENABLE_INSTANCE_LOCK=0`
  - real runtime lock behavior remains unchanged for normal app startup
- this keeps both sides correct:
  - the demo runtime still has single-instance protection
  - regression tests can run on the same workstation while the demo stack is up

## Current Execution Slice: Windows Sandbox Resource Caps And Persistence Recovery (2026-04-11)

### Why This Slice Is Next

- sandbox status visibility is already wired through TUI / CLI / gateway session payloads
- the next worthwhile hardening step is adding real native child-process resource caps instead of only more reporting
- one regression also surfaced during the status-plumbing slice:
  - shared-session persistence silently stopped writing metadata because sandbox diagnostics were computed through an invalid class-method call

### Scope

- keep the existing Windows restricted-token + job-object launch path
- add conservative Windows job caps for:
  - active process count
  - per-process memory
- plumb the cap values from runtime security config into sandbox manager/backend selection
- surface the cap values through sandbox diagnostics and `/sandbox status`
- fix the shared-session persistence regression so restart/import/export flows continue to work

### Out Of Scope

- no Linux/macOS native sandbox backend in this slice
- no AppContainer migration
- no aggressive CPU / wall-clock throttling yet

### Files In Scope

- `src/mini_agent/config.py`
- `src/mini_agent/config/config-example.yaml`
- `src/mini_agent/runtime/tooling.py`
- `src/mini_agent/code_agent/sandbox/manager.py`
- `src/mini_agent/code_agent/sandbox/windows.py`
- `src/mini_agent/runtime/sandbox_state.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `tests/test_code_agent_sandbox.py`
- `tests/test_security_policy.py`

### Execution Steps

1. Add security config fields for Windows sandbox process-count and per-process-memory caps.
2. Pass those values through runtime tooling into the sandbox manager/backend.
3. Apply real job-object limit flags for active-process and process-memory caps.
4. Expose the cap values through sandbox diagnostics and `/sandbox status`.
5. Fix the shared-session persistence regression introduced by sandbox diagnostics persistence.
6. Re-run focused sandbox, TUI/CLI, and gateway/session persistence tests.

### Acceptance Criteria

- Windows restricted child processes run under conservative job caps by default
- operators can disable/override the caps through config
- `/sandbox status` reports the effective cap values honestly
- shared-session persistence, restart recovery, snapshot, and gateway flows remain green

### Status

- completed and verified

### Verification

- `uv run pytest tests/test_code_agent_sandbox.py tests/test_security_policy.py -q`
- `uv run pytest tests/test_bash_tool.py tests/test_agent_core_execution_policy.py tests/test_code_agent_permissions.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_surface_service.py -q -k "sandbox or approval or bash or security or session or snapshot"`
- `uv run pytest tests/test_command_catalog.py tests/test_interface_dto_contracts.py tests/test_cli_submission_loop.py -q`
- `uv run pytest tests/test_tui_app.py -q -k "sandbox or status_panel or prompt_input_slash_completer_suggests_command_candidates"`
- `uv run pytest tests/test_main_agent_surface_service.py -q -k "session or snapshot or model or mcp"`

## Current Execution Slice: Windows Low-Integrity Restricted Launch Finalization (2026-04-11)

### Why This Slice Is Next

- the native restricted launch path is already real and the token/job baseline is tighter
- one honest remaining gap is integrity labeling:
  - the child should run at low integrity instead of inheriting the caller integrity level
  - token mandatory policy should be reported from the real backend state instead of being implied by older assumptions

### Scope

- keep the existing Windows restricted-token native launch path
- explicitly apply a low-integrity label to the restricted primary token before process creation
- surface the effective mandatory-policy bits through sandbox env and metadata
- verify the launched child really runs at low integrity on Windows
- keep manager-side selection metadata aligned with the backend's real restriction state

### Out Of Scope

- no attempt to force-write token mandatory policy when the host privilege context does not allow it
- no AppContainer migration in this slice
- no new process-count / memory / CPU job caps yet

### Files In Scope

- `src/mini_agent/code_agent/sandbox/windows.py`
- `src/mini_agent/code_agent/sandbox/manager.py`
- `tests/test_code_agent_sandbox.py`

### Execution Steps

1. Apply low integrity to the restricted primary token.
2. Expose integrity level and mandatory-policy bits through sandbox env and metadata.
3. Keep `SandboxManager` preview metadata sourced from the same backend helper instead of hardcoded values.
4. Add Windows-only verification that the launched child token really carries `WinLowLabelSid`.
5. Re-run focused sandbox, bash, approval, and smoke tests.

### Acceptance Criteria

- Windows restricted child processes run at low integrity
- sandbox metadata/env report integrity and mandatory-policy state honestly
- focused sandbox, bash, approval, and gateway/TUI smoke tests remain green

### Status

- completed and verified

### Verification

- `uv run pytest tests/test_code_agent_sandbox.py tests/test_bash_tool.py -q`
- `uv run pytest tests/test_security_policy.py tests/test_agent_core_execution_policy.py tests/test_code_agent_permissions.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_surface_service.py -q -k "approval or bash or security"`

## Current Execution Slice: Windows Token / Job Restriction Tightening (2026-04-11)

### Why This Slice Is Next

- the native Windows restricted-process launch is now real, but the first launch slice still used a minimal restricted token and minimal job settings
- the next clean improvement is to tighten the launched process baseline further without breaking ordinary CLI workloads

### Scope

- keep the existing restricted-process launch path
- additionally tighten the Windows sandbox baseline by:
  - disabling a curated set of high-privilege builtin groups when creating the restricted token
  - enabling job-object `DIE_ON_UNHANDLED_EXCEPTION`
  - enabling a conservative set of job UI restrictions
- expose the tightened restriction flags through sandbox metadata/env so runtime diagnostics stay honest
- add focused regression coverage for the new metadata defaults

### Out Of Scope

- no AppContainer migration in this slice
- no low-integrity label / token mandatory-policy rewrite in this slice
- no child-process-count cap in this slice, to avoid breaking normal command execution

### Files In Scope

- `src/mini_agent/code_agent/sandbox/windows.py`
- `src/mini_agent/code_agent/sandbox/manager.py`
- `tests/test_code_agent_sandbox.py`

### Execution Steps

1. Add a curated disabled-SID list for high-privilege builtin groups.
2. Apply those deny-only SID restrictions when building the restricted token.
3. Add job-object `DIE_ON_UNHANDLED_EXCEPTION` and UI restriction flags.
4. Expose the new restriction state through sandbox metadata/env.
5. Add focused regression coverage and re-run sandbox/approval tests.

### Acceptance Criteria

- Windows restricted launch still works after the tighter token/job settings
- selection/transform metadata now exposes the added restriction flags
- focused sandbox, bash, and approval regressions remain green

### Status

- completed and verified

### Verification

- `uv run pytest tests/test_code_agent_sandbox.py tests/test_bash_tool.py -q`
- `uv run pytest tests/test_security_policy.py tests/test_agent_core_execution_policy.py tests/test_code_agent_permissions.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_surface_service.py -q -k "approval or bash or security"`

## Current Execution Slice: Windows Native Restricted-Process Launch (2026-04-11)

### Why This Slice Is Next

- the previous sandbox slices made Windows policy selection honest, but execution still stopped at command transform + metadata
- `windows_restricted_token` existed as a backend name without a true restricted-process launch path
- the next correct step is to turn that backend into a real runtime boundary for Windows shell execution

### Scope

- implement native Windows process launch using:
  - restricted token
  - job object with kill-on-close semantics
  - inherited stdio pipes
- keep the existing policy/transform path as the pre-launch validation layer
- route `BashTool` Windows execution through the native launcher when the active sandbox backend is `windows_restricted_token`
- add focused regression coverage for:
  - native restricted-process launch
  - `BashTool` native-launch branch selection
  - end-to-end `SandboxManager + BashTool` execution on Windows

### Out Of Scope

- no AppContainer backend in this slice
- no Linux/macOS process sandbox backend in this slice
- no finer-grained Windows token ACL tuning beyond the initial restricted-token + job-object baseline

### Files In Scope

- `src/mini_agent/code_agent/sandbox/windows.py`
- `src/mini_agent/code_agent/sandbox/manager.py`
- `src/mini_agent/tools/bash_tool.py`
- `tests/test_code_agent_sandbox.py`
- `tests/test_bash_tool.py`

### Execution Steps

1. Add a Windows native process adapter compatible with the current `BashTool` expectations.
2. Launch PowerShell under a restricted token via `CreateProcessAsUser`.
3. Bind the launched process to a job object with kill-on-close.
4. Route Windows `BashTool` execution through the native launcher when the selected backend is `windows_restricted_token`.
5. Add focused tests for direct launch, branch selection, and end-to-end manager integration.

### Acceptance Criteria

- Windows sandbox backend launches a real restricted child process instead of only transforming command text
- `BashTool` uses the native launcher under the Windows restricted backend
- end-to-end Windows sandbox execution returns stdout correctly
- existing approval/security tests remain green

### Status

- completed and verified

### Verification

- `uv run pytest tests/test_code_agent_sandbox.py tests/test_bash_tool.py -q`
- `uv run pytest tests/test_security_policy.py tests/test_agent_core_execution_policy.py tests/test_code_agent_permissions.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_surface_service.py -q -k "approval or bash or security"`

## Current Execution Slice: Sandbox Auto-Edit Mutation Tiering (2026-04-11)

### Why This Slice Is Next

- the previous tightening made `auto-edit` safer, but also made it less practical for normal coding work because all mutations required approval
- Mini-Agent still needs one middle mode between `suggest` and `full-auto`
- the clean boundary is not "all writes vs no writes"; it is:
  - ordinary workspace file editing
  - durable/system mutations such as skill install/uninstall, long-term memory writes, and shell execution

### Scope

- keep `auto-edit` able to execute ordinary `write_file` / `edit_file` mutations without approval
- keep durable/system mutations on the explicit approval path:
  - `record_note`
  - `user_modeling`
  - `install_skill*`
  - `uninstall_skill`
  - `rollback_skill`
  - shell execution remains approval-gated
- preserve `tool_exclude` precedence over any `auto-edit` allow rule
- update config-example wording so the profile semantics match runtime behavior

### Out Of Scope

- no OS-level sandbox backend work in this slice
- no new approval UI
- no change to `suggest` or `full-auto` top-level semantics

### Files In Scope

- `src/mini_agent/runtime/tooling.py`
- `src/mini_agent/config/config-example.yaml`
- `tests/test_security_policy.py`

### Execution Steps

1. Add specific `auto-edit` allow rules only for `write_file` and `edit_file`.
2. Leave durable/system mutation tools on the default ASK path.
3. Lock rule ordering so `tool_exclude` still wins.
4. Add focused regression tests for the new tiered behavior.

### Acceptance Criteria

- `auto-edit` allows ordinary workspace file edits without approval
- durable/system mutations still require approval
- `tool_exclude` still overrides the `auto-edit` allow rules
- `full-auto` remains unchanged

### Status

- completed and verified

### Verification

- `uv run pytest tests/test_security_policy.py tests/test_code_agent_permissions.py tests/test_agent_core_execution_policy.py tests/test_code_agent_tools.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_surface_service.py -q -k approval`
- `uv run pytest tests/test_security_audit.py tests/test_bash_tool.py tests/test_code_agent_sandbox.py -q`

## Current Execution Slice: Sandbox Default-Mutation Approval Tightening (2026-04-11)

### Why This Slice Is Next

- workspace file boundaries and elevated bash approval are now real, but the default `auto-edit` approval profile still leaves one trust gap
- `build_approval_engine(...)` currently lets `WRITE` and `EDIT` tool kinds run without confirmation under `auto-edit`
- that means the runtime default is still wider than the hardened file/shell boundary now implies
- the next clean step is to keep read-only behavior frictionless while putting state-changing actions back behind explicit approval

### Scope

- remove the implicit `WRITE` / `EDIT` allow rules from the `auto-edit` runtime approval profile
- keep `full-auto` unchanged as the explicit autonomous mode
- keep read-only default-allow behavior unchanged
- update security-audit messaging so `elevated_exec=require_approval` reflects the now-live approval plumbing instead of stale pre-implementation wording
- add focused regression coverage for the tightened mutation-approval boundary

### Out Of Scope

- no redesign of approval-token UX in TUI / CLI / gateway
- no new OS-level sandbox backend
- no permission split finer than the current declarative tool kinds in this slice

### Files In Scope

- `src/mini_agent/runtime/tooling.py`
- `src/mini_agent/security/audit.py`
- `src/mini_agent/config/config-example.yaml`
- `tests/test_security_policy.py`
- `tests/test_security_audit.py`

### Execution Steps

1. Remove the `auto-edit` default allow rules for `ToolKind.WRITE` and `ToolKind.EDIT`.
2. Keep read-only and `full-auto` behavior unchanged.
3. Update audit wording/severity for `elevated_exec=require_approval`.
4. Add focused tests proving:
   - `auto-edit` now asks for write/edit mutations
   - read-only tools still auto-allow
   - `full-auto` still bypasses approval
   - security-audit wording matches the live approval flow

### Acceptance Criteria

- `auto-edit` no longer silently allows workspace mutations by default
- read-only tools still execute without approval prompts
- `full-auto` still allows autonomous mutations
- audit output no longer claims approval plumbing is missing when it is already implemented

### Status

- completed and verified

### Verification

- `uv run pytest tests/test_security_policy.py tests/test_security_audit.py tests/test_code_agent_permissions.py tests/test_agent_core_execution_policy.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_surface_service.py -q -k approval`
- `uv run pytest tests/test_bash_tool.py tests/test_code_agent_sandbox.py -q`

## Current Execution Slice: Sandbox Hardening And Real Approval Wiring (2026-04-11)

### Why This Slice Is Next

- current sandboxing is usable as a lightweight guardrail, but it is not yet a coherent operator-trust boundary
- `bash` already passes through runtime policy and sandbox transform hooks
- however, file tools still allow absolute-path access outside the workspace
- `elevated_exec=require_approval` currently blocks elevated shell outright instead of routing through the live approval system
- network policy primitives exist, but runtime config does not yet wire them into the active sandbox manager

### Scope

- add hard workspace-boundary enforcement for `read_file`, `write_file`, and `edit_file`
- make `elevated_exec=require_approval` participate in the existing approval flow instead of being a dead-end block
- extend security config/runtime wiring so network policy can be configured and reaches the active sandbox manager
- keep the current TUI/CLI/gateway approval UX and reuse the existing approval event path

### Out Of Scope

- no new container/AppContainer/job-object subsystem in this slice
- no Linux/macOS sandbox backend in this slice
- no redesign of the full tool permission model outside the targeted shell/file/network boundary fixes

### Files In Scope

- `src/mini_agent/tools/file_tools.py`
- `src/mini_agent/security/policy.py`
- `src/mini_agent/runtime/tooling.py`
- `src/mini_agent/config.py`
- `src/mini_agent/config/config-example.yaml`
- `src/mini_agent/code_agent/sandbox/manager.py`
- `src/mini_agent/code_agent/sandbox/network.py`
- `src/mini_agent/agent_core/engine.py`
- focused tests under:
  - `tests/test_security_policy.py`
  - `tests/test_code_agent_sandbox.py`
  - `tests/test_agent_core_execution_policy.py`
  - `tests/test_bash_tool.py`

### Execution Steps

1. Add one canonical workspace-boundary resolver for file tools and reject paths outside the workspace root.
2. Extend runtime security policy so elevated shell commands can surface as approval-required rather than hard-block-only.
3. Reuse the existing tool approval flow inside `Agent` for elevated bash execution.
4. Add security config fields for network policy and wire them into `SandboxManager`.
5. Add focused regression coverage for:
   - file-tool workspace escape rejection
   - elevated shell approval-required path
   - configured network allowlist/block behavior through runtime tooling

### Acceptance Criteria

- absolute or traversal-based file-tool paths outside the active workspace are rejected consistently
- `elevated_exec=require_approval` no longer dead-ends; the agent can request approval and continue after approval
- configured network policy reaches the active sandbox manager and blocks disallowed domains in workspace sandbox mode
- focused tests prove the new boundary behavior directly

### Status

- completed and verified

### Verification

- `uv run pytest tests/test_file_tools_workspace_boundary.py tests/test_security_policy.py tests/test_agent_core_execution_policy.py tests/test_bash_tool.py tests/test_code_agent_sandbox.py tests/test_code_agent_permissions.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_surface_service.py -q -k "approval or security or bash"`
- `uv run pytest tests/test_config_local_env.py tests/test_single_instance.py tests/test_cli_stack_command.py tests/test_provider_config.py -q`
- `uv run pytest tests/test_agent_core_kernel.py tests/test_agent_core_engine_live.py tests/test_security_audit.py -q`

## Current Stage Override: Demo Baseline (2026-04-11)

The active top-level goal has moved beyond the original P26-only execution thread.
Mini-Agent is now in a demo-baseline phase focused on showing one coherent end-to-end operator experience.

### Stage Goal

Ship one stable, reviewable demo path built around the existing core:

- TUI / CLI as the primary operator surface
- gateway + QQ shared-session handoff as the remote extension path
- unified model / session / memory / KB / skill controls on the same runtime seam
- no new parallel subsystem added just for demo polish

### Demo-Critical Capabilities To Lock

- stable local TUI conversation loop
- stable shared-session loop: QQ -> gateway -> runtime -> TUI takeover / continue
- model switching and session persistence
- KB explicit toggle and lightweight RAG usage
- memory inspection / promotion / workspace-session integration
- skill discovery / policy control / runtime reload visibility
- basic local MCP operator seam (`/mcp status|list|reload`) on top of the existing runtime integration

### Explicit Skill Boundary For This Stage

What is already in scope:

- builtin + workspace skill discovery
- workspace-level skill policy (`all` / `allowlist` + allow/deny mutation)
- policy-aware runtime filtering for prompt injection, `get_skill(...)`, and turn-context hints
- local + shared operator controls via `/skill ...`

What is not yet a finished capability:

- agent-autonomous skill installation from marketplace / URL / package
- persisted remote skill source registration workflow
- rollback / source-ledger / package validation beyond local path + inline workspace install
- remote shared-session MCP control and MCP tool-name collision handling

### Immediate Next Slice

1. lock the demo script and walkthrough around the currently real capabilities
2. keep polishing operator visibility and recovery semantics only where they improve demo reliability
3. treat marketplace/package-style skill installation as a post-demo slice; local path install and agent-authored inline install are now available

### Builtin Skill Direction Lock: 2026-04-11

The builtin skill target is now explicitly fixed to a MiniMax-first bundled catalog instead of the older Anthropic-style example bundle currently vendored in `src/mini_agent/skills/`.

Primary doc:

- `docs/P28_BUILTIN_SKILL_REALIGNMENT_PLAN.md`

Target bundled layers:

- Core Development:
  - `frontend-dev`
  - `fullstack-dev`
  - `android-native-dev`
  - `ios-application-dev`
  - `flutter-dev`
  - `react-native-dev`
  - `shader-dev`
  - `mcp-builder`
  - `webapp-testing`
  - `skill-creator`
- Documents And Office:
  - `minimax-docx`
  - `minimax-pdf`
  - `pptx-generator`
  - `minimax-xlsx`
- Multimodal And Creative:
  - `minimax-multimodal-toolkit`
  - `gif-sticker-maker`
  - `vision-analysis`
  - `minimax-music-gen`
- Optional Entertainment / Demo:
  - `buddy-sings`
  - `minimax-music-playlist`
  - `minimax-novel-demo`

Execution priority for that migration:

1. [completed] replace the four builtin document skills
2. [completed] add the first MiniMax-first development / multimodal skills (`frontend-dev`, `fullstack-dev`, `vision-analysis`, `gif-sticker-maker`)
3. [completed] archive product-misaligned Anthropic example skills from the default builtin bundle
4. [completed] expand to the next mobile / shader / music tier:
   - `android-native-dev`
   - `ios-application-dev`
   - `flutter-dev`
   - `react-native-dev`
   - `shader-dev`
   - `minimax-music-gen`
5. [completed] expand the optional / demo tier:
   - `buddy-sings`
   - `minimax-music-playlist`
   - both now exist as real builtin skills layered on top of the existing MiniMax music/toolkit path
6. future follow-up:
   - reassess the final builtin catalog after real demo usage
   - trim any optional/demo skills that prove noisy or low-value in default discovery
7. [completed] add bundled-skill trigger audit + Chinese prompt trigger hardening:
   - `scripts/skill_trigger_audit.py`
   - repo-level Chinese prompt trigger regression tests
   - metadata-driven trigger keyword matching in skill ranking
8. [completed] validate real model-side skill loading and tune progressive-disclosure behavior:
   - added `scripts/skill_live_probe.py`
   - hardened live probe cleanup/startup around MCP cancellation and LLM client shutdown
   - tightened system prompt / metadata prompt / relevant-skill turn-context guidance
   - shortened overly rich tier-1 skill descriptions that were causing "mention skill without loading" behavior
   - latest live probe baseline: `4/4` expected skills loaded through real `get_skill(...)` calls

### Notes

- This stage override is intentional and should be treated as the current execution priority over older single-topic slices below.
- Existing P26/P27 work remains valid and is now considered supporting infrastructure for the demo baseline.

## Goal
Turn the P26 memory architecture report into the live runtime direction for Mini-Agent:

- separate true global durable memory from workspace durable memory
- make global user profile memory available automatically in turn context
- prepare the codebase for workspace-aware session search and future persisted `MemoriaEngine`
- keep the system lightweight, explicit, and non-duplicated

Primary doc:

- `docs/P26_MEMORY_RUNTIME_TASK_PLAN.md`

## Phases
- [completed] Re-audit the existing memory/runtime/session code and confirm the first correct landing slice.
- [completed] Write the detailed P26 implementation plan into project docs.
- [completed] Land Phase 1 core boundary correction:
  - add real global-memory path resolution
  - switch `MemoryService.profile()` to global scope
  - keep workspace note memory unchanged
  - add `UserProfileTurnContextProvider`
  - wire it into default runtime context providers
- [completed] Land Phase 2 workspace-aware session-search context retrieval:
  - add stable `workspace_anchor_dir` into session-search indexing/filtering
  - add `SessionSearchTurnContextProvider`
  - filter prepared session-history hits to the active workspace anchor
  - exclude the current session by default to avoid transcript echo
  - pass gateway shared-session store into kernel turn-context wiring
- [completed] Add focused regression coverage for global profile storage and turn-context injection.
- [completed] Land Phase 3 consolidated-memory refresh and promotion policy:
  - make consolidation workspace-aware instead of sweeping all session history into one workspace
  - add `MemoryService.consolidated_refresh_status()` and `refresh_consolidated_memory()`
  - auto-refresh consolidated memory on demand from the consolidated-memory turn-context provider
  - reject raw KB/tool payloads from durable consolidated-memory promotion
- [completed] Land Phase 4 persisted workspace runtime `MemoriaEngine` with session namespaces:
  - add persisted workspace-scoped runtime task memory under `~/.mini-agent/state/workspaces/<hash>/...`
  - isolate namespaces as `session:<session_id>` and `workspace:shared`
  - wire retrieval through `RuntimeTaskMemoryTurnContextProvider`
  - add conservative post-turn runtime task-memory writeback
  - add explicit promotion hooks into workspace durable notes and global profile memory
- [completed] Land Phase 5 operator-facing memory diagnostics and RAG-memory policy controls:
  - expose shared `memory_diagnostics` in runtime/gateway session summaries/details/snapshots
  - add gateway session memory actions (`status/show/runtime/refresh/promote_note/promote_profile`)
  - add `/memory` inspection/control commands to TUI and CLI
  - surface compact memory summary in TUI status sidebar

## Constraints
- TUI/CLI remain the primary surfaces; WebUI stays paused.
- Do not introduce a second parallel durable memory system.
- Reuse `MemoryService` as the top-level orchestrator.
- Keep RAG/KB separate from memory ownership.
- Avoid compatibility shells when direct refactor is cleaner.
- Keep tests isolated from real `~/.mini-agent` user state.

## Open Decisions
- Whether workspace session-search context should be always-available but usually `no_match`, or only mounted when session-search stats indicate usable history.
- Whether global `AGENT.md` should become runtime-readable in the same phase as user profile, or wait until durable global conventions need separate retrieval.
- Whether Phase 3 consolidation refresh should be automatic on write, scheduled, or operator-triggered first.

## Errors Encountered
- Historical `tests/test_memory_automation.py` content contained broken non-ASCII literals and became a syntax-level blocker during collection.
  - Resolution: rewrite the test file into stable ASCII fixtures and stub the extraction helpers directly so the tests verify writeback behavior instead of brittle encoding artifacts.

## Latest Update
- [completed] Phase 1 is now landed and verified:
  - global durable profile path now resolves through `MINI_AGENT_GLOBAL_MEMORY_ROOT` or `~/.mini-agent/global`
  - `MemoryService.profile()` / `search_profile()` / `add_profile_fact()` now target global user memory
  - workspace profile access remains available explicitly through `workspace_profile()` methods
  - `UserModelingTool` now defaults to global profile memory
  - runtime turn-context wiring now includes `user_profile`
- [completed] Phase 2 is now landed and verified:
  - session-search indexing now persists stable `workspace_anchor_dir`
  - same-anchor filtering works across nested workspace paths under one repo root
  - runtime turn-context wiring now includes `session_search`
  - session-search provider retries with keyword-focused lookup when the raw natural-language query is too strict for FTS matching
  - gateway kernel bootstrap now passes its shared-session store path into turn-context providers
- [completed] Phase 3 is now landed and verified:
  - consolidation state is now namespaced per workspace anchor, preventing cross-workspace `MEMORY.md` pollution
  - `MemoryService` can now report whether consolidated memory is fresh and refresh it on demand
  - consolidated-memory turn-context preparation now auto-refreshes when workspace session history is newer than the consolidated section
  - promotion policy now rejects raw tool / KB payloads so only distilled assistant/user conclusions enter consolidated durable memory
- [completed] Phase 4 is now landed and verified:
  - `WorkspaceMemoriaRuntime` now persists runtime task memory per workspace anchor under `~/.mini-agent/state/workspaces/<hash>`
  - runtime task memory namespaces are isolated as `session:<session_id>` and `workspace:shared`
  - `TurnRuntimeTaskMemory` now stores one compact per-turn summary into session runtime memory after successful turns
  - `RuntimeTaskMemoryTurnContextProvider` now feeds persisted runtime task memory back into the prepared-context seam
  - explicit promotion hooks now exist for runtime task memory -> workspace durable note and runtime task memory -> global profile
- [completed] Phase 5 is now landed and verified:
  - runtime session summaries/details/snapshots now carry one shared `memory_diagnostics` payload for local and remote operators
  - gateway now exposes `POST /api/v1/agent/sessions/{session_id}/memory` for diagnostics, refresh, and promotion actions
  - TUI now supports `/memory status|show|runtime|refresh|promote ...` for local and shared sessions
  - CLI interactive now supports the same `/memory` command family for local sessions
- [completed] Phase 5 operator ergonomics follow-up is now landed and verified:
  - `/memory promote` now accepts `latest`, numeric selectors like `1`, or exact `engram_id`
  - `/memory list` now exposes selector-oriented runtime-memory previews directly
  - runtime previews now enumerate session runtime entries so selector choice is visible to operators
  - explicit `/memory save note <text>` and `/memory save profile <text>` now preserve the KB -> memory confirmation boundary
  - KB-confirmed note saves are categorized as `kb_confirmed`, while manual workspace notes default to `operator_note`
  - QQ shared sessions now expose the same memory control seam through `/memory status|show|list|refresh|promote|save`
- [completed] Phase 5 runtime-memory portability follow-up is now landed and verified:
  - session snapshot/import/export now also carries explicit `workspace_shared_runtime_memory_payload`
  - `workspace:shared` restore semantics are now non-destructive merge-by-content instead of replace-by-snapshot
  - gateway import/export and TUI share/unshare now preserve portable workspace-shared runtime memory without clobbering sibling session facts
  - session reset/delete semantics remain unchanged: `workspace:shared` is still workspace-owned and never cleared by session reset
- [completed] Phase 5 runtime-memory boundary/promotion-policy follow-up is now landed and verified:
  - post-turn runtime writeback still defaults to `session:<session_id>` only
  - runtime writeback now evaluates whether the latest assistant conclusion is a `workspace:shared` candidate
  - candidate state is surfaced in `last_runtime_task_memory` diagnostics instead of auto-promoting silently
  - operators can now use `/memory promote shared <selector>` across local/shared surfaces
  - shared promotion now prefers the distilled candidate text over the raw session summary when available
- [completed] Phase 5 runtime-memory retrieval-boundary follow-up is now landed and verified:
  - `RuntimeTaskMemoryTurnContextProvider` no longer includes `workspace:shared` unconditionally
  - shared runtime memory is now injected only when the query itself looks workspace-scoped, or when session hits are insufficient
  - this keeps `workspace:shared` as a supplemental workspace layer instead of competing with current task/session memory
- Verification:
  - `uv run pytest tests/test_memory_service.py tests/test_user_modeling.py tests/test_memory_automation.py tests/test_agent_core_turn_context.py tests/test_session_search.py tests/test_session_store_persistence.py tests/test_agent_core_kernel.py tests/test_main_agent_surface_service.py tests/test_agent_studio_gateway_api_v1.py -q`
  - `uv run python -m compileall src/mini_agent/memory/paths.py src/mini_agent/memory/builtin_memory.py src/mini_agent/memory/service.py src/mini_agent/memory/automation.py src/mini_agent/memory/session_search.py src/mini_agent/session/persistence.py src/mini_agent/core/session.py src/mini_agent/tools/user_modeling.py src/mini_agent/agent_core/context/turn_context.py src/mini_agent/runtime/tooling.py src/mini_agent/agent_core/kernel.py src/apps/agent_studio_gateway/main.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_memory_service.py tests/test_main_agent_surface_service.py tests/test_agent_studio_gateway_api_v1.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_interface_dto_contracts.py -q`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/application/main_agent_gateway_use_cases.py src/apps/agent_studio_gateway/main.py src/mini_agent/tui/gateway_client.py src/mini_agent/tui/app.py src/mini_agent/cli_interactive.py`
  - `uv run pytest tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_interface_dto_contracts.py tests/test_agent_studio_gateway_api_v1.py -q`
  - inline `compileall` verification for updated memory/runtime/TUI/CLI modules

## Current Execution Slice: P26 Reset/Delete Semantics Hardening

### Why This Slice Is Next

- current `reset/delete/clear` behavior is not yet a true session reset
- `WorkspaceMemoriaRuntime` persists session-scoped runtime task memory, but session lifecycle resets do not clear the corresponding `session:<session_id>` namespace
- gateway, TUI, and CLI each reset different subsets of state, so the same user intent currently produces different residual state

### Scope

- add explicit runtime-memory namespace cleanup APIs to `WorkspaceMemoriaRuntime`
- make gateway `reset/delete` clear runtime task memory for the target session
- make lifecycle-driven idle reset use the same cleanup semantics
- align TUI local `clear/delete` with the same reset contract
- align CLI `/clear` with the same reset contract
- clear stale local restored/resume state when a session is intentionally reset

### Out Of Scope

- no new memory layer
- no storage-topology rewrite
- no snapshot/import-export payload redesign in this slice
- no command-system expansion in this slice

### Files In Scope

- `src/mini_agent/memory/memoria_runtime.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/cli_interactive.py`
- `tests/test_memoria_runtime.py`
- `tests/test_main_agent_surface_service.py`
- `tests/test_tui_app.py`
- `tests/test_cli_submission_loop.py`

### Execution Steps

1. Add namespace cleanup helpers to `WorkspaceMemoriaRuntime`.
2. Strengthen gateway reset helpers so ephemeral runtime state and token counters are reset consistently.
3. Wire runtime-memory cleanup into gateway `reset_session`, `delete_session`, and lifecycle auto-reset.
4. Wire the same semantics into local TUI clear/delete paths.
5. Wire the same semantics into CLI `/clear`.
6. Add focused regression coverage for namespace cleanup and reset/delete behavior.

### Acceptance Criteria

- after gateway `reset`, the session transcript, pending approval state, prepared-context state, and `session:<id>` runtime memory are all cleared together
- after gateway `delete`, persisted runtime task memory for that session is removed even if the session was inactive and only existed on disk
- after TUI local `clear/delete`, restored resume state does not rehydrate old context unexpectedly
- after CLI `/clear`, `cli-session` runtime task memory is cleared and token/prepared-context state resets cleanly
- focused regression tests cover the cleanup behavior directly

### Risks To Watch

- deleting the wrong namespace would silently destroy sibling session state in the same workspace
- gateway delete of inactive sessions must resolve the persisted `workspace_dir` before cleanup
- TUI reset must not erase user-visible long-term session metadata that should survive a clear, only transient runtime state

### Status

- completed and verified
- verification:
  - `uv run python -m compileall src/mini_agent/memory/memoria_runtime.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/tui/app.py src/mini_agent/cli_interactive.py tests/test_memoria_runtime.py tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_cli_submission_loop.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_cli_submission_loop.py -q`
  - result: `171 passed`

## Current Execution Slice: P26 Snapshot / Import / Export Runtime-Memory Parity

### Why This Slice Is Next

- session-scoped runtime task memory now has correct reset/delete semantics
- but `snapshot/import/export` still does not carry the actual `session:<session_id>` runtime task memory payload
- this leaves a continuity gap for:
  - local TUI -> gateway share
  - gateway -> local TUI unshare
  - future snapshot-based migration / restore flows

### Scope

- extend session snapshot/import DTOs to carry session-scoped runtime task memory payload
- add export/import helpers on `WorkspaceMemoriaRuntime`
- make gateway session snapshot export include session runtime task memory
- make gateway session import restore that runtime task memory under the effective destination session id
- make TUI share/unshare preserve runtime task memory through the snapshot contract
- clear old local runtime namespace after successful share migration when the session id changes

### Out Of Scope

- no redesign of workspace-shared runtime memory semantics
- no new durable memory plane
- no operator command expansion in this slice
- no vector RAG work

### Files In Scope

- `src/mini_agent/interfaces/agent.py`
- `src/mini_agent/memory/memoria_runtime.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `src/mini_agent/tui/app.py`
- `tests/test_main_agent_surface_service.py`
- `tests/test_tui_app.py`
- `tests/test_agent_studio_gateway_api_v1.py`

### Execution Steps

1. Add export/import helpers for session runtime-memory payloads.
2. Extend snapshot/import DTOs with a dedicated runtime-memory field.
3. Wire runtime manager export/import to that field.
4. Wire TUI share/unshare to preserve the payload and clean up old local namespace after successful migration.
5. Add focused tests for import/export/share/unshare parity.

### Acceptance Criteria

- exporting a shared session includes its session-scoped runtime task memory payload
- importing a session snapshot restores that runtime task memory into the destination session namespace
- local TUI share migrates session runtime task memory to gateway instead of leaving it only under the old local namespace
- TUI unshare restores runtime task memory back to the local workspace runtime store
- focused tests verify the parity behavior directly

### Status

- completed and verified
- verification:
  - `uv run python -m compileall src/mini_agent/interfaces/agent.py src/mini_agent/memory/memoria_runtime.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/application/main_agent_gateway_use_cases.py src/mini_agent/tui/app.py tests/test_memoria_runtime.py tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py -q`
- result: `181 passed`

## Current Execution Slice: P26 Workspace-Shared Runtime-Memory Portability

### Why This Slice Is Next

- `session:<session_id>` snapshot parity is now correct
- but `workspace:shared` still had no explicit snapshot/import/export contract
- leaving it implicit was acceptable only while all flows stayed on one machine and one state root
- the next clean step is to make workspace-shared runtime memory portable without letting one session snapshot overwrite workspace-owned shared state

### Scope

- extend session snapshot/import DTOs with an explicit workspace-shared runtime-memory payload
- add workspace-shared snapshot/restore helpers on `WorkspaceMemoriaRuntime`
- define restore semantics as non-destructive merge, not replace
- wire gateway export/import and TUI share/unshare through the same payload
- add focused regression coverage for merge-safe restore behavior

### Out Of Scope

- no session reset/delete change for `workspace:shared`
- no new durable memory plane
- no promotion-policy redesign in this slice
- no vector RAG work

### Files In Scope

- `src/mini_agent/interfaces/agent.py`
- `src/mini_agent/memory/memoria_runtime.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/tui/app.py`
- `tests/test_memoria_runtime.py`
- `tests/test_main_agent_surface_service.py`
- `tests/test_tui_app.py`
- `tests/test_agent_studio_gateway_api_v1.py`
- `tests/test_interface_dto_contracts.py`

### Execution Steps

1. Add explicit DTO payload support for workspace-shared runtime memory.
2. Add workspace-shared snapshot/restore helpers to `WorkspaceMemoriaRuntime`.
3. Make restore semantics merge by content so imports do not clobber existing shared workspace facts.
4. Wire gateway import/export and TUI share/unshare through the new payload.
5. Add focused regression tests for merge-safe import/export/share/unshare behavior.

### Acceptance Criteria

- snapshot export includes `workspace_shared_runtime_memory_payload`
- import restores workspace-shared runtime memory without deleting existing target shared facts
- TUI share/unshare preserve workspace-shared runtime memory through the same snapshot contract
- session reset/delete still leaves `workspace:shared` untouched
- focused tests directly verify merge-safe restore semantics

### Status

- completed and verified
- verification:
  - `uv run python -m compileall src/mini_agent/interfaces/agent.py src/mini_agent/memory/memoria_runtime.py src/mini_agent/application/main_agent_gateway_use_cases.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/tui/app.py tests/test_memoria_runtime.py tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py -q`
- result: `186 passed`

## Current Execution Slice: P26 Workspace-Shared Boundary / Promotion Policy

### Why This Slice Is Next

- portability for `workspace:shared` is now correct
- but runtime still lacked an integrated strategy for:
  - when facts should remain `session:<id>`
  - when a fact is suitable for `workspace:shared`
  - how operators should promote such facts without silently duplicating task-local noise into workspace-shared memory

### Scope

- keep automatic writeback defaulting to `session:<id>`
- add one conservative `workspace:shared` candidate evaluation path on post-turn writeback
- surface candidate status through runtime diagnostics
- add explicit `/memory promote shared <selector>` control across local/shared surfaces
- prefer distilled candidate text when promoting into `workspace:shared`

### Out Of Scope

- no automatic promotion into `workspace:shared`
- no durable-memory auto-promotion changes
- no new memory plane
- no vector RAG work

### Files In Scope

- `src/mini_agent/memory/promotion.py`
- `src/mini_agent/memory/runtime_task_memory.py`
- `src/mini_agent/memory/memoria_runtime.py`
- `src/mini_agent/memory/diagnostics.py`
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/mini_agent/cli_interactive.py`
- `src/mini_agent/tui/app.py`
- `src/apps/qqbot_channel/bot.mjs`
- `src/mini_agent/commands/catalog.json`
- `tests/test_memoria_runtime.py`
- `tests/test_main_agent_surface_service.py`
- `tests/test_tui_app.py`
- `tests/test_cli_submission_loop.py`

### Execution Steps

1. Add one shared policy helper for evaluating `workspace:shared` candidates.
2. Annotate session runtime-memory writeback with candidate metadata instead of auto-promoting.
3. Make `promote_session_memory_to_workspace_shared(...)` use the distilled candidate text when available.
4. Add `/memory promote shared <selector>` across gateway, CLI, TUI, and QQ.
5. Add focused regression coverage for candidate detection and shared promotion behavior.

### Acceptance Criteria

- automatic runtime writeback still lands only in `session:<id>`
- diagnostics show whether the latest runtime writeback is a `workspace:shared` candidate
- `promote shared` works across local and shared surfaces
- shared promotion uses a distilled workspace-level conclusion instead of the raw `task: ... | latest: ...` envelope when possible
- `workspace:shared` remains explicit runtime state, not a silent second durable-memory write path

### Status

- completed and verified
- verification:
  - `uv run python -m compileall src/mini_agent/memory/promotion.py src/mini_agent/memory/runtime_task_memory.py src/mini_agent/memory/memoria_runtime.py src/mini_agent/memory/diagnostics.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/cli_interactive.py src/mini_agent/tui/app.py tests/test_memoria_runtime.py tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_cli_submission_loop.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py -q`
  - `node --check src/apps/qqbot_channel/bot.mjs`
  - result: `206 passed`

## Current Execution Slice: P26 Workspace-Shared Retrieval Boundary

### Why This Slice Is Next

- promotion and portability semantics are now clear
- but retrieval still let `workspace:shared` participate too eagerly
- that risked letting workspace-shared facts compete with current task/session memory even when the query was clearly session-local

### Scope

- keep session runtime memory as the primary runtime retrieval source
- let `workspace:shared` participate only when:
  - the query itself carries workspace/shared/runtime scope signals, or
  - session hits are insufficient for the configured session budget
- expose the chosen shared-retrieval reason in prepared-context metadata

### Out Of Scope

- no change to writeback semantics
- no automatic durable-memory promotion
- no new memory plane

### Files In Scope

- `src/mini_agent/memory/promotion.py`
- `src/mini_agent/agent_core/context/turn_context.py`
- `tests/test_memoria_runtime.py`
- `tests/test_agent_core_turn_context.py`
- `tests/test_main_agent_surface_service.py`
- `tests/test_tui_app.py`
- `tests/test_cli_submission_loop.py`

### Execution Steps

1. Add a reusable workspace-scope signal helper.
2. Gate `workspace:shared` retrieval inside `RuntimeTaskMemoryTurnContextProvider`.
3. Record whether shared retrieval was used because of query scope, fallback, or suppression.
4. Add focused tests for suppression and fallback behavior.

### Acceptance Criteria

- session-local runtime memory remains primary when it already covers the current query
- `workspace:shared` still helps when the query is workspace-scoped or session hits are sparse
- prepared-context metadata explains why shared retrieval was or was not included

### Status

- completed and verified
- verification:
  - `uv run python -m compileall src/mini_agent/memory/promotion.py src/mini_agent/agent_core/context/turn_context.py tests/test_memoria_runtime.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_agent_core_turn_context.py tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_cli_submission_loop.py -q`
  - result: `204 passed`

## Latest Sync: 2026-04-10 Workspace-Shared Operator Surface + Explicit KB Grounding Boundary

- [completed] `workspace:shared` now has an independent operator surface across gateway/TUI/CLI/QQ:
  - `/memory shared list`
  - `/memory shared show <selector>`
  - `/memory shared clear`
- [completed] explicit memory/RAG linkage now follows a stricter confirmation boundary:
  - KB-grounded turns now annotate runtime task memory with explicit grounding metadata
  - automatic workspace durable-note and daily-note writeback is suppressed for KB-grounded turns
  - explicit workspace durable-note promotion now uses `kb_confirmed` when the source runtime memory is KB-grounded
  - explicit `/memory save note ...` now surfaces KB grounding details when prepared KB context is present
- [completed] KB-grounding operator visibility is now aligned across gateway/TUI/CLI:
  - runtime-memory preview rendering now uses one shared diagnostics formatter instead of per-surface custom strings
  - KB-grounded preview items now show explicit badges plus compact `kb / hits / query / refs` operator lines
  - `shared show` now renders the same `Knowledge Base: grounded` detail block across local and remote memory surfaces
- [completed] session runtime-memory inspection is now operator-complete across gateway/TUI/CLI/QQ:
  - `memory show brief|full` still serves diagnostics
  - `memory show <selector>` now resolves and renders one concrete session runtime-memory entry
  - session and workspace-shared runtime-memory surfaces are now symmetric at the operator command layer
- [completed] durable memory is now browsable through the same `/memory` command family:
  - `memory profile [query]` exposes global profile browsing/search
  - `memory notes [query]` exposes workspace durable-note browsing/search
  - `memory daily <YYYY-MM-DD>` exposes workspace daily-memory inspection
  - gateway request contracts now carry explicit `query` / `day` fields for durable-memory actions
- [completed] consolidated memory is now inspectable through the same `/memory` command family:
  - `memory consolidated` / `memory consolidated show` exposes consolidated snapshot inspection
  - `memory consolidated search <query>` exposes ranked consolidated-memory lookup
  - consolidated-memory read surfaces now align across gateway/TUI/CLI/QQ without changing explicit refresh semantics
- Verification:
  - `uv run python -m compileall src/mini_agent/memory/diagnostics.py src/mini_agent/interfaces/agent.py src/mini_agent/application/main_agent_gateway_use_cases.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/cli_interactive.py src/mini_agent/tui/gateway_client.py src/mini_agent/tui/app.py tests/test_tui_app.py tests/test_main_agent_surface_service.py tests/test_cli_submission_loop.py tests/test_command_catalog.py`
  - `uv run pytest tests/test_tui_app.py tests/test_main_agent_surface_service.py tests/test_cli_submission_loop.py tests/test_command_catalog.py tests/test_memoria_runtime.py tests/test_memory_automation.py tests/test_interface_dto_contracts.py tests/test_agent_studio_gateway_api_v1.py tests/test_memory_service.py tests/test_memory_relevance.py -q`
  - `node --check src/apps/qqbot_channel/bot.mjs`
  - result: `242 passed`

## Latest Sync: 2026-04-10 Cross-Layer Memory Overview / Export

- [completed] `/memory` now has a human-facing cross-layer summary:
  - `memory overview` shows runtime task memory, durable memory, and consolidated memory in one operator-facing block
  - overview rendering reuses one shared diagnostics seam instead of per-surface summaries
- [completed] `/memory` now has an explicit export path:
  - `memory export [jsonl|markdown]` exports workspace durable notes directly from the main memory command family
  - gateway request contracts now carry explicit `export_format`
- [completed] the new overview/export surface is aligned across gateway, TUI, CLI, and QQ
- [completed] `memory overview` now also exposes session/workspace linkage explicitly:
  - `Session Context` shows `session id`
  - `workspace anchor`
  - session/shared runtime namespaces
  - prepared sources now sit under that same session/workspace context block
- Verification:
  - `uv run pytest tests/test_tui_app.py tests/test_main_agent_surface_service.py tests/test_cli_submission_loop.py tests/test_command_catalog.py tests/test_interface_dto_contracts.py -q`
  - `node --check src/apps/qqbot_channel/bot.mjs`
  - result: `203 passed`
  - `uv run pytest tests/test_tui_app.py tests/test_main_agent_surface_service.py tests/test_cli_submission_loop.py -q`
  - result: `190 passed`

## Latest Sync: 2026-04-10 KB Call-Decision + Memory Writeback Quality

- [completed] KB use remains explicit and now has stronger call-decision guidance instead of passive retrieval:
  - `knowledge_base` tool description now calls out README/spec/API/design/manual retrieval more directly
  - system prompt guidance now tells the agent to prefer KB first for document-grounded requests and to use concrete noun-heavy KB queries
- [completed] memory writeback quality is now stricter for low-signal operator chatter:
  - added shared low-signal filtering in `src/mini_agent/memory/quality.py`
  - durable auto-memory writeback skips low-signal control turns
  - runtime task-memory writeback skips the same low-signal control turns so transient session memory stays cleaner too
- [completed] real-use validation now has a dedicated integration test skeleton:
  - `tests/test_memory_real_use_flow.py` verifies workspace/session boundary behavior
  - the same test also verifies that KB-grounded facts still require explicit confirmation before promotion into durable memory
- Verification:
  - `uv run pytest tests/test_memory_automation.py tests/test_memoria_runtime.py tests/test_knowledge_base_tool.py tests/test_memory_real_use_flow.py -q`
  - result: `31 passed`
  - `uv run pytest tests/test_memory_service.py tests/test_memoria_runtime.py tests/test_agent_core_turn_context.py tests/test_memory_automation.py tests/test_session_search.py tests/test_knowledge_base_tool.py tests/test_main_agent_surface_service.py tests/test_memory_real_use_flow.py -q`
  - result: `103 passed`

## Latest Sync: 2026-04-12 Runtime-Policy + Session-Control Handler Extraction

- [completed] `MainAgentRuntimeManager` runtime-policy routing is now extracted into a dedicated handler:
  - added `src/mini_agent/runtime/session_runtime_policy_handler.py`
  - manager now delegates runtime-policy normalization, effective/current policy resolution, busy-session rejection, and local-session fallback diagnostics to that handler
- [completed] session-control routing is now extracted into a dedicated handler:
  - added `src/mini_agent/runtime/session_control_handler.py`
  - manager now delegates `compact` / `drop_memories` / `kb_on` / `kb_off` / `mcp_status` / `mcp_list` / `mcp_reload`
  - manager keeps only orchestration responsibilities: load session, acquire lock, append transcript entry, persist
- [completed] the runtime-policy regression surfaced a real test seam problem and was corrected without adding a compatibility shell:
  - shared-session detail read models rebuild sandbox diagnostics from the live agent, not only from `session.projection`
  - `_SelectableAgent` test doubles now expose minimal runtime-policy state so readback assertions match the real diagnostics path
- [completed] MCP inspection/reload monkeypatchability is preserved during the extraction:
  - handler dependencies are injected through manager-owned lambdas so existing monkeypatch-based tests still observe the runtime module seam
- Verification:
  - `uv run pytest tests/test_main_agent_surface_service.py -k "runtime_policy or control_session" -q`
  - result: `8 passed`
  - `uv run ruff check src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_runtime_policy_handler.py src/mini_agent/runtime/session_control_handler.py tests/test_main_agent_surface_service.py`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_runtime_policy_handler.py src/mini_agent/runtime/session_control_handler.py tests/test_main_agent_surface_service.py`
  - `uv run pytest tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py tests/test_session_service.py tests/test_p19_runtime_matrix.py -q`
  - result: `203 passed`
  - `uv run pytest tests/test_interaction_surface.py tests/test_channel_ingress_gateway_walkthrough.py tests/test_session_projection.py tests/test_shared_session_gateway_walkthrough.py -q`
  - result: `11 passed`

## Latest Sync: 2026-04-12 Context-Policy Handler Extraction

- [completed] shared-session prepared-context policy routing is now extracted into a dedicated handler:
  - added `src/mini_agent/runtime/session_context_policy_handler.py`
  - manager now delegates `include` / `exclude` / `budget` / `reset`
- [completed] the extracted handler now owns:
  - action normalization and validation
  - busy-session rejection
  - source-list normalization
  - budget coercion and minimum bounds
  - transcript command/summary/details rendering
  - response assembly for `MainAgentSessionContextResponse`
- [completed] `MainAgentRuntimeManager.update_session_context_policy(...)` now keeps only orchestration responsibilities:
  - load session
  - acquire runtime lock
  - append command transcript
  - persist session
  - return handler-built response
- [completed] regression coverage for the new seam is stronger than before:
  - existing include-policy persistence test still verifies next-turn propagation
  - added explicit `budget -> reset` coverage
  - added explicit busy-session rejection coverage
- Verification:
  - `uv run pytest tests/test_main_agent_surface_service.py -k "context_policy or update_session_context or context_update" -q`
  - result: `3 passed`
  - `uv run ruff check src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_context_policy_handler.py tests/test_main_agent_surface_service.py`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_context_policy_handler.py tests/test_main_agent_surface_service.py`
  - `uv run pytest tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py tests/test_session_service.py tests/test_p19_runtime_matrix.py -q`
  - result: `205 passed`
  - `uv run pytest tests/test_interaction_surface.py tests/test_channel_ingress_gateway_walkthrough.py tests/test_session_projection.py tests/test_shared_session_gateway_walkthrough.py -q`
  - result: `11 passed`

## Latest Sync: 2026-04-12 Interrupt Handler Extraction

- [completed] shared-session interrupt routing is now extracted into a dedicated handler:
  - added `src/mini_agent/runtime/session_interrupt_handler.py`
  - manager now delegates running-turn cancellation and pending-approval resolution
- [completed] the extracted interrupt handler now owns:
  - cancel-turn validation
  - cancel-event triggering
  - pending-approval waiter cancellation during `/cancel`
  - pending-approval token resolution
  - restart-recovery approval conflict messaging
  - approval transcript command/summary/details rendering
  - approval response assembly and waiter finalization hook
- [completed] `MainAgentRuntimeManager` now keeps only outer orchestration for cancel/approval commands:
  - load active managed session
  - distinguish missing session vs persisted-but-not-resumable session
  - append command transcript
  - persist session
  - return handler-built response
- Verification:
  - `uv run pytest tests/test_main_agent_surface_service.py -k "cancel_session or approval or pending_approval" -q`
  - result: `3 passed`
  - `uv run ruff check src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_interrupt_handler.py tests/test_main_agent_surface_service.py`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_interrupt_handler.py tests/test_main_agent_surface_service.py`
  - `uv run pytest tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py tests/test_session_service.py tests/test_p19_runtime_matrix.py -q`
  - result: `205 passed`
  - `uv run pytest tests/test_interaction_surface.py tests/test_channel_ingress_gateway_walkthrough.py tests/test_session_projection.py tests/test_shared_session_gateway_walkthrough.py -q`
  - result: `11 passed`

## Latest Sync: 2026-04-12 Snapshot Handler Extraction

- [completed] runtime snapshot import/export coordination is now extracted into a dedicated handler:
  - added `src/mini_agent/runtime/session_snapshot_handler.py`
  - manager now delegates snapshot import gatekeeping and snapshot export source resolution
- [completed] the extracted snapshot handler now owns:
  - imported snapshot `session_id` collision checks
  - imported snapshot auto-id allocation handoff
  - snapshot hydration payload construction
  - export-time selection between live managed session and persisted record
  - consistent `404` handling for missing snapshot exports
- [completed] `MainAgentRuntimeManager` import/export methods now keep only orchestration responsibilities:
  - acquire store lock
  - prepare import environment / persistence lookups through injected closures
  - hydrate imported payload into a live session
  - return handler-selected live or persisted snapshot export
- [completed] regression coverage for the new seam is explicit:
  - duplicate imported `session_id` now has a dedicated test
  - persisted-record export path now has a dedicated test
  - existing runtime-task-memory and workspace-shared-memory export tests still validate live export payloads
- Verification:
  - `uv run pytest tests/test_main_agent_surface_service.py -k "import_session_snapshot or export_session or persisted_export" -q`
  - result: `3 passed`
  - `uv run ruff check src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_snapshot_handler.py tests/test_main_agent_surface_service.py`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_snapshot_handler.py tests/test_main_agent_surface_service.py`
  - `uv run pytest tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py tests/test_session_service.py tests/test_p19_runtime_matrix.py -q`
  - result: `207 passed`
  - `uv run pytest tests/test_interaction_surface.py tests/test_channel_ingress_gateway_walkthrough.py tests/test_session_projection.py tests/test_shared_session_gateway_walkthrough.py -q`
  - result: `11 passed`

## Latest Sync: 2026-04-12 Restore / Hydrate Handler Extraction

- [completed] persisted-record restore and payload hydration coordination is now extracted into a dedicated handler:
  - added `src/mini_agent/runtime/session_restore_handler.py`
  - manager now delegates both `record -> hydration payload` preparation and `payload -> live session state` hydration
- [completed] the extracted restore handler now owns:
  - persisted transcript import handoff
  - stored recovery snapshot handoff
  - record-hydration payload construction
  - agent rebuild for selected model identity
  - runtime-policy reconfigure attempt during restore
  - agent message/token restoration
  - effective KB-enabled state resolution
  - lifecycle bootstrap for restored sessions
  - session-state construction + stored-recovery application
  - runtime-state hydration and selected-model fallback identity
- [completed] `MainAgentRuntimeManager` now keeps only the outer restore/hydrate orchestration:
  - resolve `now_utc`
  - check in-memory existing session
  - register newly hydrated sessions into `_sessions`
  - decide whether imported sessions should persist immediately
- [completed] focused validation reuses real recovery flows rather than synthetic seams:
  - interrupted persisted session recovery after restart
  - restarted shared session recovery context consumption
  - runtime restart survival
  - latest persisted shared-session restore
  - snapshot import/export still green
- Verification:
  - `uv run pytest tests/test_main_agent_surface_service.py -k "persisted_interrupted_session or restarted_shared_session or survives_runtime_restart or restores_latest_persisted_shared_session or import_session_snapshot or export_session or persisted_export" -q`
  - result: `7 passed`
  - `uv run ruff check src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_restore_handler.py tests/test_main_agent_surface_service.py`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_restore_handler.py tests/test_main_agent_surface_service.py`
  - `uv run pytest tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py tests/test_session_service.py tests/test_p19_runtime_matrix.py -q`
  - result: `207 passed`
  - `uv run pytest tests/test_interaction_surface.py tests/test_channel_ingress_gateway_walkthrough.py tests/test_session_projection.py tests/test_shared_session_gateway_walkthrough.py -q`
  - result: `11 passed`

## Latest Sync: 2026-04-12 Session-Access Handler Extraction

- [completed] `get_or_create_session(...)` branch selection is now extracted into a dedicated handler:
  - added `src/mini_agent/runtime/session_access_handler.py`
  - manager now delegates selection among:
    - active in-memory session reuse by explicit `session_id`
    - team-mode same-workspace active-session reuse without `session_id`
    - persisted-session restore by explicit `session_id`
    - latest persisted same-workspace session restore without `session_id`
    - new session creation
- [completed] the extracted handler now owns:
  - request normalization for surface/channel/conversation/sender/title-hint inputs
  - workspace-mismatch routing for active and persisted candidates
  - team-mode capacity enforcement at the create-new boundary
  - carry-forward flags such as `apply_title_hint_if_missing` for restored sessions
- [completed] `MainAgentRuntimeManager.get_or_create_session(...)` now keeps only orchestration responsibilities:
  - call handler to choose path
  - refresh/touch/persist reused sessions
  - call restore path for persisted sessions
  - instantiate a brand-new session only when the handler says `create_new`
- [completed] focused validation covers the branchy parts directly:
  - human-readable title hints
  - title-hint application on new shared sessions
  - latest persisted shared-session restore
  - team-mode reuse and capacity guardrails
  - single-main workspace guardrail
- [completed] minor repo hygiene:
  - removed unused `asyncio` import from `tests/test_p19_runtime_matrix.py` so lint can include that file cleanly
- Verification:
  - `uv run pytest tests/test_main_agent_surface_service.py -k "assigns_human_readable_session_title_hints or chat_applies_session_title_hint_on_new_shared_session or restores_latest_persisted_shared_session or team_mode or single_main_workspace_only or max_active_sessions or survives_runtime_restart or get_or_create_session" -q`
  - result: `9 passed`
  - `uv run ruff check src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_access_handler.py tests/test_main_agent_surface_service.py tests/test_p19_runtime_matrix.py`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_access_handler.py tests/test_main_agent_surface_service.py tests/test_p19_runtime_matrix.py`
  - `uv run pytest tests/test_main_agent_surface_service.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py tests/test_session_service.py tests/test_p19_runtime_matrix.py -q`
  - result: `207 passed`
  - `uv run pytest tests/test_interaction_surface.py tests/test_channel_ingress_gateway_walkthrough.py tests/test_session_projection.py tests/test_shared_session_gateway_walkthrough.py -q`
  - result: `11 passed`





## Latest Sync: 2026-04-13 Binding + Lifecycle Boundary Cleanup

- [completed] Step `3`: gateway/TUI residual binding cleanup
  - `cancel` moved onto `MainAgentSessionCancelRequest`
  - TUI remote operator calls now share one binding helper
  - gateway client binding payloads now normalize through `ApplicationInteractionBinding`
- [completed] Step `2`: runtime session lifecycle boundary cleanup
  - added `src/mini_agent/runtime/session_runtime_lifecycle_handler.py`
  - creation/restore handlers now take unified lifecycle bootstrap callback
  - session-registry lifecycle refresh now routes through the extracted lifecycle handler
- [completed] Verification for both slices
  - focused regression tests green
  - broader application/runtime/TUI/gateway suite green: `245 passed`
- [next] Continue manager shrink only where the boundary is still materially mixed
  - inspect whether session operator orchestration still leaks storage/runtime/live-state concerns together
  - prefer another explicit handler extraction only if it removes a real semantic seam instead of producing a thin pass-through shell

## Latest Sync: 2026-04-13 Managed Store Boundary

- [completed] Extract managed session store seam
  - added `src/mini_agent/runtime/session_managed_store_handler.py`
  - active/persisted lookup, delete cleanup, persistence, id allocation, and expiry removal no longer live inline in manager
- [completed] Rewired runtime manager + registry + operator entrypoints to use the managed store seam
- [completed] Verification green
  - focused: `8 passed`
  - broader runtime/gateway/TUI regression: `222 passed`
- [next] Candidate next shrink slice
  - inspect the remaining session admin mutation cluster
  - likely target: `rename/shared/reset/set_active_surface` orchestration so manager no longer mixes lock scope with live-state mutation details

## Latest Sync: 2026-04-13 Session Admin Boundary

- [completed] Extract session admin mutation seam
  - added `src/mini_agent/runtime/session_admin_handler.py`
  - manager admin methods now delegate rename/shared/reset/active-surface mutation details
- [completed] Lifecycle reset path unified through `session_runtime_lifecycle_handler.py`
- [completed] Verification green
  - focused: `9 passed`
  - broader runtime/gateway/TUI regression: `225 passed`
- [next] Reassess remaining manager surface before the next cut
  - confirm whether any real semantic cluster still mixes with manager wiring
  - if yes, prefer one more explicit seam
  - if no, stop shrinking and return focus to agent-core feature work

## Latest Sync: 2026-04-13 Runtime Manager Stop Point

- [completed] Reassessed remaining `MainAgentRuntimeManager` surface after recent extractions
- [decision] No further shrink cut is justified right now
  - remaining responsibilities are mostly valid facade/composition concerns
  - next possible extractions would likely be thin shells
- [next] Shift effort back to agent-core capability work on top of the now-stabler service backbone

## Latest Sync: 2026-04-13 P32 Project Structure Realignment

## Current Execution Slice: P32.1 Agent-Core Tree Realignment (2026-04-13)

### Why This Slice Is Next

- the logical architecture has been stabilized enough that the remaining drift is now physical
- the repo tree still tells the wrong story:
  - `agent_core/` and `code_agent/` look like two peer cores
  - `agent.py` and `turn_context.py` still sit at the package root even though they are agent-kernel concerns
  - `core/session.py` still advertises a historical packaging model that no longer matches the current session architecture
- if this is not corrected now, future work on memory / RAG / MCP / remote / DesktopUI will keep landing on a misleading physical skeleton

### Scope

- lock the project-structure realignment plan in docs
- land the first hard-realignment cut for the visible agent kernel tree
- unify:
  - `Agent`
  - turn context
  - former `code_agent` execution pieces
  under one `agent_core` tree

### Out Of Scope

- no broad runtime/service rewrite in this slice
- no `core/session.py` move yet if it would complicate the first cut
- no new user-facing features

### Acceptance

- repo no longer presents `code_agent` as a peer core after the first cut
- `Agent` and turn-context ownership become physically obvious from the tree
- focused tests for agent-core, CLI/TUI/runtime imports, and execution paths stay green

### Canonical Plan Doc

- `docs/P32_PROJECT_STRUCTURE_REALIGNMENT_PLAN_2026-04-13.md`

### Status

- in_progress

### P32.1 Status Update (2026-04-13)

- first hard-realignment cut is now landed
- completed in this cut:
  - `src/mini_agent/agent_core/engine.py` -> `src/mini_agent/agent_core/engine.py`
  - `src/mini_agent/agent_core/context/turn_context.py` -> `src/mini_agent/agent_core/context/turn_context.py`
  - `src/mini_agent/code_agent/context.py` -> `src/mini_agent/agent_core/context/loop_context.py`
  - `src/mini_agent/code_agent/context_compression.py` -> `src/mini_agent/agent_core/context/context_compaction.py`
  - remaining `code_agent/*` runtime primitives -> `src/mini_agent/agent_core/execution/*`
- old peer `code_agent` source tree is now removed from active source ownership
- next structural target remains:
  - `core/session.py` cleanup and session packaging realignment
- verification:
  - `uv run pytest -q`
  - result: `918 passed, 15 skipped`
  - targeted `ruff check` on the realignment slice
  - result: all green

### P32.2 Status Update (2026-04-13)

- second hard-realignment cut is now landed for historical session packaging
- completed in this cut:
  - `src/mini_agent/core/session.py` -> `src/mini_agent/session/store.py`
  - `src/mini_agent/session/__init__.py` now exports `SessionState`, `SessionStore`, `session_store`
  - `src/mini_agent/core/` removed
  - store tests now import from `mini_agent.session`
- structural outcome:
  - `agent_core/session` is no longer semantically polluted by storage concerns
  - the session storage/search API now sits under the canonical `session/` package
- next structural targets remain naming-debt cleanup and service-boundary tightening, not more fake-core packaging

### P32.3 Status Update (2026-04-13)

- third realignment cut is now landed for shared application-layer naming cleanup
- completed in this cut:
  - `src/mini_agent/application/gateway_agent_execution_handler.py` -> `src/mini_agent/application/agent_turn_execution_handler.py`
  - `src/mini_agent/application/gateway_route_execution_handler.py` -> `src/mini_agent/application/agent_route_execution_handler.py`
  - `src/mini_agent/application/gateway_chat_flow_handler.py` -> `src/mini_agent/application/surface_chat_flow_handler.py`
  - removed `src/mini_agent/application/main_agent_gateway_use_cases.py`
  - removed `MainAgentGatewayUseCases` export in favor of `MainAgentSurfaceService`
  - removed `to_gateway_chat_execution_request(...)` in favor of `to_surface_chat_execution_request(...)`
- structural outcome:
  - shared application orchestration no longer presents gateway transport naming as if it were the business owner
  - the canonical top-level application entry is now `MainAgentSurfaceService`
- verification:
  - `uv run pytest tests/test_interaction_request_adapter.py tests/test_main_agent_surface_service.py tests/test_shared_session_gateway_walkthrough.py tests/test_channel_ingress_gateway_walkthrough.py -q`
  - result: `79 passed`
  - targeted `ruff check` on the application realignment slice
  - result: all green


### P32.3.1 Test Surface Rename Update (2026-04-13)

- renamed `tests/test_main_agent_gateway_use_cases.py` -> `tests/test_main_agent_surface_service.py`
- updated `scripts/terminal_readiness_gate.py` to the canonical test path
- verification:
  - `uv run pytest tests/test_main_agent_surface_service.py -q`
  - result: `74 passed`
  - `uv run pytest tests/test_terminal_readiness_gate.py -q`
  - result: `8 passed`
  - `uv run pytest -q`
  - result: `918 passed, 15 skipped`

### P32.4 Boundary Audit Notes (2026-04-13)

- audited remaining boundaries across `application / runtime / session`
- current highest-value residual seams are:
  - `application` still imports interaction binding normalization from `runtime.interaction_surface`
  - `SessionApplicationService` still depends directly on concrete runtime types (`MainAgentRuntimeManager`, `MainAgentSessionState`, `RuntimeSessionTurnScopeHandler`)
  - `RemoteSessionService` is still an application-layer facade over a transport-shaped `gateway_client`
- recommended next cleanup order:
  1. move `interaction_surface` normalization into a shared non-runtime module
  2. introduce a slimmer runtime port for `SessionApplicationService`
  3. decide whether `RemoteSessionService` should remain application-owned or move behind a transport/client seam

### P32.5 Interaction Surface Extraction (2026-04-13)

- moved `src/mini_agent/runtime/interaction_surface.py` -> `src/mini_agent/interaction/surface.py`
- added canonical shared export package:
  - `src/mini_agent/interaction/__init__.py`
- updated application/runtime/tests imports to `mini_agent.interaction`
- removed the old runtime-local module instead of keeping a compatibility shim
- verification:
  - `uv run pytest tests/test_interaction_surface.py tests/test_interaction_request_adapter.py tests/test_main_agent_surface_service.py tests/test_p19_runtime_matrix.py -q`
  - result: `86 passed`
  - `uv run pytest -q`
  - result: `918 passed, 15 skipped`
  - targeted `ruff check` on the interaction extraction slice
  - result: all green
- architectural outcome:
  - interaction binding normalization is now a shared cross-layer module
  - `application` no longer depends on a runtime-owned interaction normalization source
- next recommended seam:
  - define a slimmer runtime port for `SessionApplicationService`

## 2026-04-13 P32.6 Session Runtime Port Realignment

- [completed] added `src/mini_agent/application/session_runtime_port.py` as the application-facing runtime seam
- [completed] rewired `SessionApplicationService` to consume runtime ports instead of concrete runtime manager/session/turn-scope classes
- [completed] rewired `MainAgentSurfaceService` constructor typing to the shared runtime port
- [completed] added boundary-friendly projection properties to `src/mini_agent/runtime/session_state.py`
- [completed] added a structural seam test that uses a fake runtime port
- Verification:
  - `uv run pytest tests/test_session_service.py tests/test_main_agent_surface_service.py tests/test_interaction_surface.py tests/test_interaction_request_adapter.py -q`
  - result: `90 passed`
  - `uv run pytest -q`
  - result: `919 passed, 15 skipped`
  - targeted `ruff check` on the seam slice
  - result: all green
- Next likely seam:
  - `RemoteSessionService` still looks transport-shaped around `gateway_client`

## 2026-04-13 P32.7 Remote Session Transport Port Realignment

- [completed] added `src/mini_agent/application/remote_session_transport_port.py` as the explicit transport seam for `RemoteSessionService`
- [completed] rewired `RemoteSessionService` to depend on `RemoteSessionTransportPort` instead of a loosely named `gateway_client` object
- [completed] updated shared exports and TUI wiring to pass `session_transport=self.gateway_client`
- [completed] updated remote-session tests to the new seam naming
- Verification:
  - `uv run pytest tests/test_session_remote_service.py tests/test_tui_app.py tests/test_tui_gateway_client.py -q`
  - result: `129 passed`
  - `uv run pytest -q`
  - result: `919 passed, 15 skipped`
  - `uv run ruff check src/mini_agent/application src/mini_agent/tui/app.py tests/test_session_remote_service.py tests/test_session_service.py tests/test_main_agent_surface_service.py`
  - result: all green
- Structural outcome:
  - `RemoteSessionService` still remains a client-side facade, but its dependency is now expressed as a transport port rather than a gateway-specific implementation detail

## 2026-04-13 P32.8 Transport Client Packaging Realignment

- [completed] moved client-side remote session and gateway clients into `src/mini_agent/transport/`
- [completed] renamed `RemoteSessionService` -> `RemoteSessionClient`
- [completed] renamed `TuiGatewayClient` -> `GatewayClient`
- [completed] rewired TUI/Desktop to import from the shared transport package
- [completed] renamed transport-related tests to match the new ownership
- Verification:
  - `uv run pytest tests/test_transport_remote_session_client.py tests/test_transport_gateway_client.py tests/test_tui_app.py tests/test_desktop_app.py -q`
  - result: `131 passed`
  - `uv run pytest -q`
  - result: `919 passed, 15 skipped`
  - targeted `ruff check` on the transport realignment slice
  - result: all green
- Outcome:
  - `application/` now holds shared use cases only
  - local gateway/session clients now live in a transport-owned package that TUI/Desktop can share cleanly

## 2026-04-15 Agent-Core Core Analysis

- [completed] audited the current `agent_core` implementation as a runtime kernel, not just the `Agent` class
- [completed] traced the main execution path from kernel bootstrap to submission loop, turn scheduler, planner/executor loop, tool execution, turn-context injection, and post-turn memory hooks
- [completed] reviewed current contract coverage through:
  - `tests/test_agent_core_kernel.py`
  - `tests/test_agent_core_execution_loop.py`
  - `tests/test_agent_core_turn_context.py`
- current architectural conclusion:
  - the runtime assembly path is already usable and more mature than the physical tree size alone suggests
  - the strongest subsystem is turn-context preparation plus runtime bootstrap diagnostics
  - the largest remaining debt is concentration of behavior inside `agent_core/engine.py` and `context/turn_context.py`
- current highest-value refactor order:
  1. split `Agent` into planner/executor, history/summarization, and runtime side-effect services
  2. replace dynamic `setattr(...)` runtime attachments with typed runtime capability objects
  3. remove type mutation in turn-scoped scheduler overrides
  4. separate console rendering from core runtime execution
  5. decide whether concurrency-safe tools should actually execute in parallel

## 2026-04-15 P34 Agent-Core Refactor Planning

- [completed] created the active `P34` plan document:
  - `docs/P34_AGENT_CORE_REFACTOR_PLAN_2026-04-15.md`
- `P34` is now defined as the structural hardening line for `agent_core` after `P32` ownership cleanup and `P33/P33b` model/runtime governance work
- locked first implementation recommendation:
  1. `P34.1` runtime binding contract hardening
  2. `P34.2` turn-scoped policy contract hardening
- later planned slices:
  - tool execution coordinator extraction
  - history/summarization semantics correction
  - headless presentation boundary
  - turn-context package decomposition
  - post-turn side-effect extraction
  - final `Agent` facade slimming

## 2026-04-15 P34.1 P34.2 Runtime Binding + Policy Contract Hardening

- [completed] added typed runtime binding owner:
  - `src/mini_agent/agent_core/runtime_bindings.py`
- [completed] rewired `Agent` to own explicit runtime bindings and explicit runtime mutation helpers:
  - runtime bindings
  - runtime services
  - tool approval handler override
  - typed execution policy override
- [completed] rewired kernel runtime attachment away from ad-hoc `setattr(...)`:
  - `src/mini_agent/agent_core/kernel.py`
- [completed] rewired submission-loop approval bridge binding to an explicit helper:
  - `src/mini_agent/agent_core/execution/agent_loop.py`
- [completed] rewired surface turn execution approval injection to an explicit helper context:
  - `src/mini_agent/application/agent_turn_execution_handler.py`
- [completed] removed scheduler type mutation for turn-scoped policy override:
  - `src/mini_agent/agent_core/execution/scheduler.py`
- [completed] added regression coverage:
  - `tests/test_agent_core_kernel.py`
  - `tests/test_agent_core_execution_loop.py`
  - `tests/test_agent_core_execution_policy.py`
- verification:
  - `uv run ruff check src/mini_agent/agent_core/runtime_bindings.py src/mini_agent/agent_core/engine.py src/mini_agent/agent_core/kernel.py src/mini_agent/agent_core/execution/agent_loop.py src/mini_agent/agent_core/execution/scheduler.py src/mini_agent/application/agent_turn_execution_handler.py src/mini_agent/runtime/tooling.py tests/test_agent_core_kernel.py tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_policy.py`
  - result: all green
  - `uv run pytest tests/test_agent_core_kernel.py tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_policy.py tests/test_runtime_session_model_identity_codec.py -q`
  - result: `37 passed`
  - `uv run pytest tests/test_main_agent_surface_service.py tests/test_cli_submission_loop.py -q`
  - result: `106 passed`
- broader sweep:
  - `uv run pytest -q`
  - result: `1069 passed, 15 skipped, 6 failed`
  - note: remaining failures are in unrelated walkthrough/TUI/runtime snapshot surfaces, not in the `P34.1/P34.2` slice

## 2026-04-15 P34.3 Tool Execution Coordinator Extraction

- [completed] extracted shared tool approval request contract:
  - `src/mini_agent/agent_core/execution/tool_approval.py`
- [completed] extracted dedicated tool authorization/execution coordinator:
  - `src/mini_agent/agent_core/execution/tool_execution_coordinator.py`
- [completed] rewired `Agent` to own the coordinator and delegate the old inline tool-execution cluster through thin compatibility wrappers:
  - `src/mini_agent/agent_core/engine.py`
- [completed] updated the execution package exports so the new seam is part of the canonical `agent_core.execution` surface:
  - `src/mini_agent/agent_core/execution/__init__.py`
- [completed] preserved current execution semantics for:
  - empty tool-call steps returning `StepTransition.COMPLETE`
  - approval round-trips before execution
  - runtime-policy-mediated bash approval
  - best-effort cancellation during running tools
  - per-tool message append and hook emission
- verification:
  - `uv run ruff check src/mini_agent/agent_core/engine.py src/mini_agent/agent_core/execution/tool_approval.py src/mini_agent/agent_core/execution/tool_execution_coordinator.py src/mini_agent/agent_core/execution/__init__.py tests/test_agent_core_execution_policy.py tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_tools.py tests/test_agent_core_execution_permissions.py`
  - result: all green
  - `uv run pytest tests/test_agent_core_execution_policy.py tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_tools.py tests/test_agent_core_execution_permissions.py tests/test_main_agent_surface_service.py -q`
  - result: `114 passed`
- next likely seam:
  - `P34.4` history and summarization semantics correction

## 2026-04-15 P34.4 History And Summarization Semantics Correction

- [completed] extracted dedicated history compaction and summarization service:
  - `src/mini_agent/agent_core/history/summarization.py`
  - `src/mini_agent/agent_core/history/__init__.py`
- [completed] rewired `Agent` history summarization to the extracted service:
  - `src/mini_agent/agent_core/engine.py`
- [completed] replaced fake-user summary writeback with an explicit internal summary representation:
  - role: `assistant`
  - name: `__mini_agent_history_summary__`
  - content prefix: `[Internal Assistant Summary]`
- [completed] added compatibility handling for older summary history:
  - legacy `[Assistant Execution Summary]` fake-user messages are normalized into the new internal assistant summary shape during compaction
  - already compacted internal summaries are preserved instead of being redundantly re-summarized
- [completed] added focused regression coverage:
  - `tests/test_agent_core_history_summarization.py`
- verification:
  - `uv run ruff check src/mini_agent/agent_core/engine.py src/mini_agent/agent_core/history/__init__.py src/mini_agent/agent_core/history/summarization.py tests/test_agent_core_history_summarization.py`
  - result: all green
  - `uv run pytest tests/test_agent_core_history_summarization.py tests/test_agent_core_execution_policy.py tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_tools.py tests/test_agent_core_execution_permissions.py tests/test_main_agent_surface_service.py -q`
  - result: `117 passed`
- next likely seam:
  - `P34.5` headless core presentation boundary

## 2026-04-15 P34.5 Headless Core Presentation Boundary

- [completed] extracted presentation ownership out of the core runtime path:
  - `src/mini_agent/agent_core/presentation.py`
- [completed] rewired `Agent` to depend on a semantic presenter instead of direct ANSI/console formatting:
  - `src/mini_agent/agent_core/engine.py`
- [completed] rewired adjacent extracted services to the same presenter seam:
  - `src/mini_agent/agent_core/execution/tool_execution_coordinator.py`
  - `src/mini_agent/agent_core/history/summarization.py`
- [completed] preserved compatibility for current surfaces while making headless execution explicit:
  - `console_output=True` now uses `AnsiConsoleAgentRuntimePresenter`
  - `console_output=False` now uses `NullAgentRuntimePresenter`
  - custom presenters can be injected directly into `Agent`
- [completed] added focused regression coverage:
  - `tests/test_agent_core_presentation.py`
- verification:
  - `uv run ruff check src/mini_agent/agent_core/engine.py src/mini_agent/agent_core/presentation.py src/mini_agent/agent_core/execution/tool_execution_coordinator.py src/mini_agent/agent_core/history/summarization.py tests/test_agent_core_history_summarization.py tests/test_agent_core_presentation.py`
  - result: all green
  - `uv run pytest tests/test_agent_core_presentation.py tests/test_agent_core_history_summarization.py tests/test_agent_core_execution_policy.py tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_tools.py tests/test_agent_core_execution_permissions.py tests/test_main_agent_surface_service.py -q`
  - result: `119 passed`
- next likely seam:
  - `P34.6` turn-context package decomposition

## 2026-04-16 P32b OpenWebUI Legacy Release Surface Slice

- [completed] cut a narrow `P32b` hygiene slice for the removed OpenWebUI surface instead of bundling it into the broader dirty worktree
- [completed] removed the remaining active OpenWebUI release-path assets:
  - `src/apps/open_webui/*`
  - `scripts/ci/open_webui_smoke.py`
  - `scripts/ci/open_webui_verify.py`
  - `tests/test_open_webui_*`
- [completed] aligned active release entrypoints with the current architecture:
  - simplified `.github/workflows/ci.yml` release handoff to deterministic gate + advisory summary only
  - removed OpenWebUI advisory startup/report artifact handling from CI
  - updated `scripts/ci/release_gate.py`
  - updated `scripts/ci/release_promotion_checklist.py`
  - updated `src/mini_agent/dev/release_promotion_checklist.py`
- [completed] cleaned script index guidance so archive/current replacements no longer point at removed OpenWebUI flows:
  - `scripts/README.md`
  - `scripts/ci/README.md`
  - `scripts/archive/README.md`
- verification:
  - `uv run pytest tests/test_release_promotion_checklist.py -q`
  - result: `3 passed`
  - `uv run python scripts/ci/release_gate.py --help`
  - result: exit `0`
  - `uv run python scripts/ci/release_promotion_checklist.py --help`
  - result: exit `0`
  - `git diff --cached --check`
  - result: clean
- commit:
  - `127bc9c`
  - `p32b: remove openwebui legacy release surface`
- next likely hygiene slice:
  - `agent_studio` frontend tree removal plus the minimum host/doc cleanup required to keep that deletion self-consistent

## 2026-04-16 P32b Legacy Channel Tree Removal Slice

- [completed] cut a second narrow `P32b` hygiene slice for deleted remote-channel legacy trees
- [completed] removed the remaining legacy channel trees and their dedicated smoke/test surface:
  - `src/channels/types/*`
  - `src/channels/wechat/*`
  - `src/gateway/channels/*`
  - `src/mini_agent/channels/*`
  - `scripts/qq_wechat_smoke.py`
  - `tests/test_channels.py`
- [completed] confirmed the current active repo already treats these paths as historical removals in active indexes:
  - `docs/DEVELOPMENT_INDEX.md`
  - `docs/REFACTOR_TASKS.md`
- verification:
  - `rg -n "mini_agent\\.channels|src/channels/wechat|src/gateway/channels|qq_wechat_smoke|test_channels\\.py|channels/types" src tests scripts -g '!scripts/archive/**'`
  - result: no active source/test/script references
  - `uv run pytest tests/test_markdown_links.py -q`
  - result: `1 passed`
  - `git diff --cached --check`
  - result: clean
- commit:
  - `c6ca8bb`
  - `p32b: drop legacy channel trees`
- next likely hygiene slice:
  - `agent_studio` frontend removal plus the minimum gateway-host alignment needed to keep browser-static hosting out of the active tree
