# Task Plan

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
- `uv run pytest tests/test_bash_tool.py tests/test_agent_execution_policy.py tests/test_code_agent_permissions.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py -q -k "sandbox or approval or bash or security or session or snapshot"`
- `uv run pytest tests/test_command_catalog.py tests/test_interface_dto_contracts.py tests/test_cli_submission_loop.py -q`
- `uv run pytest tests/test_tui_app.py -q -k "sandbox or status_panel or prompt_input_slash_completer_suggests_command_candidates"`
- `uv run pytest tests/test_main_agent_gateway_use_cases.py -q -k "session or snapshot or model or mcp"`

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
- `uv run pytest tests/test_security_policy.py tests/test_agent_execution_policy.py tests/test_code_agent_permissions.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py -q -k "approval or bash or security"`

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
- `uv run pytest tests/test_security_policy.py tests/test_agent_execution_policy.py tests/test_code_agent_permissions.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py -q -k "approval or bash or security"`

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
- `uv run pytest tests/test_security_policy.py tests/test_agent_execution_policy.py tests/test_code_agent_permissions.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py -q -k "approval or bash or security"`

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

- `uv run pytest tests/test_security_policy.py tests/test_code_agent_permissions.py tests/test_agent_execution_policy.py tests/test_code_agent_tools.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py -q -k approval`
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

- `uv run pytest tests/test_security_policy.py tests/test_security_audit.py tests/test_code_agent_permissions.py tests/test_agent_execution_policy.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py -q -k approval`
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
- `src/mini_agent/agent.py`
- focused tests under:
  - `tests/test_security_policy.py`
  - `tests/test_code_agent_sandbox.py`
  - `tests/test_agent_execution_policy.py`
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

- `uv run pytest tests/test_file_tools_workspace_boundary.py tests/test_security_policy.py tests/test_agent_execution_policy.py tests/test_bash_tool.py tests/test_code_agent_sandbox.py tests/test_code_agent_permissions.py -q`
- `uv run pytest tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py -q -k "approval or security or bash"`
- `uv run pytest tests/test_config_local_env.py tests/test_single_instance.py tests/test_cli_stack_command.py tests/test_provider_config.py -q`
- `uv run pytest tests/test_agent_core_kernel.py tests/test_agent.py tests/test_security_audit.py -q`

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
  - `uv run pytest tests/test_memory_service.py tests/test_user_modeling.py tests/test_memory_automation.py tests/test_agent_turn_context.py tests/test_session_search.py tests/test_session_store_persistence.py tests/test_agent_core_kernel.py tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_api_v1.py -q`
  - `uv run python -m compileall src/mini_agent/memory/paths.py src/mini_agent/memory/builtin_memory.py src/mini_agent/memory/service.py src/mini_agent/memory/automation.py src/mini_agent/memory/session_search.py src/mini_agent/session/persistence.py src/mini_agent/core/session.py src/mini_agent/tools/user_modeling.py src/mini_agent/turn_context.py src/mini_agent/runtime/tooling.py src/mini_agent/agent_core/kernel.py src/apps/agent_studio_gateway/main.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_memory_service.py tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_api_v1.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_interface_dto_contracts.py -q`
  - `uv run python -m compileall src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/application/main_agent_gateway_use_cases.py src/apps/agent_studio_gateway/main.py src/mini_agent/tui/gateway_client.py src/mini_agent/tui/app.py src/mini_agent/cli_interactive.py`
  - `uv run pytest tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_interface_dto_contracts.py tests/test_agent_studio_gateway_api_v1.py -q`
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
- `tests/test_main_agent_gateway_use_cases.py`
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
  - `uv run python -m compileall src/mini_agent/memory/memoria_runtime.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/tui/app.py src/mini_agent/cli_interactive.py tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py -q`
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
- `tests/test_main_agent_gateway_use_cases.py`
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
  - `uv run python -m compileall src/mini_agent/interfaces/agent.py src/mini_agent/memory/memoria_runtime.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/application/main_agent_gateway_use_cases.py src/mini_agent/tui/app.py tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py -q`
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
- `tests/test_main_agent_gateway_use_cases.py`
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
  - `uv run python -m compileall src/mini_agent/interfaces/agent.py src/mini_agent/memory/memoria_runtime.py src/mini_agent/application/main_agent_gateway_use_cases.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/tui/app.py tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py -q`
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
- `tests/test_main_agent_gateway_use_cases.py`
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
  - `uv run python -m compileall src/mini_agent/memory/promotion.py src/mini_agent/memory/runtime_task_memory.py src/mini_agent/memory/memoria_runtime.py src/mini_agent/memory/diagnostics.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/cli_interactive.py src/mini_agent/tui/app.py tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py -q`
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
- `src/mini_agent/turn_context.py`
- `tests/test_memoria_runtime.py`
- `tests/test_agent_turn_context.py`
- `tests/test_main_agent_gateway_use_cases.py`
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
  - `uv run python -m compileall src/mini_agent/memory/promotion.py src/mini_agent/turn_context.py tests/test_memoria_runtime.py`
  - `uv run pytest tests/test_memoria_runtime.py tests/test_agent_turn_context.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_cli_submission_loop.py -q`
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
  - `uv run python -m compileall src/mini_agent/memory/diagnostics.py src/mini_agent/interfaces/agent.py src/mini_agent/application/main_agent_gateway_use_cases.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/cli_interactive.py src/mini_agent/tui/gateway_client.py src/mini_agent/tui/app.py tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py`
  - `uv run pytest tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py tests/test_memoria_runtime.py tests/test_memory_automation.py tests/test_interface_dto_contracts.py tests/test_agent_studio_gateway_api_v1.py tests/test_memory_service.py tests/test_memory_relevance.py -q`
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
  - `uv run pytest tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py tests/test_command_catalog.py tests/test_interface_dto_contracts.py -q`
  - `node --check src/apps/qqbot_channel/bot.mjs`
  - result: `203 passed`
  - `uv run pytest tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_cli_submission_loop.py -q`
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
  - `uv run pytest tests/test_memory_service.py tests/test_memoria_runtime.py tests/test_agent_turn_context.py tests/test_memory_automation.py tests/test_session_search.py tests/test_knowledge_base_tool.py tests/test_main_agent_gateway_use_cases.py tests/test_memory_real_use_flow.py -q`
  - result: `103 passed`
