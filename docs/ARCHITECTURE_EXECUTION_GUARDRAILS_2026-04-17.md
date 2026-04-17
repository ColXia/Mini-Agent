# Architecture Execution Guardrails

Date: 2026-04-17

Purpose: lock the active execution rule for future Mini-Agent development so new feature work does not slide back into surface-owned business logic.

## 1. Hard rule

- `CLI / TUI / DesktopUI / Remote` are entrances, not business owners.
- Surface files may own presentation, local input UX, and ephemeral view state.
- Shared interaction behavior must default to `mini_agent.application` or `mini_agent.runtime`.
- HTTP routes, gateway clients, and channel adapters translate protocol payloads; they do not own business rules.
- Composition roots may wire objects together; they do not authorize business logic to live in entrypoints.

## 2. Layer placement guide

### Surface layer

Allowed:

- widget state, focus, selection, temporary drafts, loading flags
- text formatting, badges, layout, rendering adapters
- collecting user input and calling transport/application APIs
- local optimistic UI updates that do not become truth

Not allowed:

- deciding session ownership truth
- deciding shared runtime policy truth
- compensating for backend policy drift by rewriting shared rules inside UI code
- implementing cross-surface behavior as one surface's private fallback

### Interface / transport layer

Allowed:

- DTO validation and protocol translation
- HTTP / SSE / terminal / remote adapter shaping
- auth, envelope, serialization, stream framing

Not allowed:

- becoming a second application service layer
- hiding business rules in routers, clients, or adapter helpers

### Application service layer

Owns:

- shared use cases across entrances
- session/chat/model/memory/workspace operations
- cross-surface interaction rules
- request normalization that should behave the same for multiple entrances

### Runtime orchestration layer

Owns:

- session lifecycle and recovery
- runtime mode/access policy decisions
- cancellation, approvals, retry/recovery orchestration
- runtime diagnostics and execution-state transitions

## 3. Fast decision checklist

Before landing a change, ask:

1. Does this mutate `session`, `runtime policy`, `model binding`, `memory`, or `workspace` truth?
   If yes, it does not belong in a surface file.
2. Would another entrance need the same behavior?
   If yes, default the implementation target to `application/` or `runtime/`.
3. Is this only about rendering, temporary local UX, or input collection?
   If yes, the surface can own it.
4. Is the surface compensating for a lower-layer inconsistency?
   If yes, treat that as a boundary bug and push the rule downward.

## 4. Recently closed leakage sample

### Desktop runtime-policy autofix

Former code path:

- [`src/mini_agent/desktop/window.py`](../src/mini_agent/desktop/window.py): `desktop_runtime_policy_autofix_plan(...)`
- [`src/mini_agent/desktop/window.py`](../src/mini_agent/desktop/window.py): `_ensure_desktop_runtime_policy_ready(...)`

Problem:

- the desktop surface inspects `origin_surface`, `active_surface`, `shared`, `approval_profile`, and `access_level`
- it then decides whether a local desktop session should be upgraded out of `plan` mode before send
- that is shared runtime-policy correction logic, not pure presentation logic

Resolution:

- the correction rule is moved into shared pre-turn runtime preparation
- `SessionApplicationService.prepare_chat_turn(...)` now asks the runtime layer to normalize send-time policy readiness before the turn starts
- DesktopUI no longer owns this correction path and only requests the shared send flow

### TUI remote-turn active-surface prewrite

Former code path:

- [`src/mini_agent/tui/session_turn_state_coordinator.py`](../src/mini_agent/tui/session_turn_state_coordinator.py): `begin_remote_turn(...)`

Problem:

- the TUI surface prewrote `projection.active_surface = "tui"` before the gateway/runtime path returned authoritative shared-session state
- that made the surface temporarily impersonate shared session truth instead of waiting for the shared path to report it

Resolution:

- remote-turn local state now marks only surface-local busy/running UX
- TUI no longer rewrites `active_surface` during remote turn startup
- authoritative surface ownership remains sourced from the shared gateway/runtime flow

### TUI dead context-policy mutators

Former code path:

- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_set_context_policy_sources(...)`
- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_set_context_policy_budget(...)`
- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_reset_context_policy(...)`

Problem:

- old surface-local helpers still encoded context-policy mutation logic directly in `app.py`
- they were no longer part of the active coordinator path, but they remained as a misleading fallback implementation

Resolution:

- the dead helpers are removed
- active context-policy mutation semantics remain owned by shared command/runtime services plus the maintained TUI coordinator path

### TUI coordinator adapter shims

Former code path:

- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_apply_local_session_runtime_policy_for_command(...)`
- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_apply_remote_session_runtime_policy_for_command(...)`
- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_refresh_context_snapshot_for_command(...)`
- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_run_context_command_result_for_coordinator(...)`

Problem:

- these helpers existed only to forward coordinator calls back into already-owned TUI app/runtime helpers
- they added another surface-local indirection layer without owning additional behavior or policy
- that extra layer made it easier for future changes to quietly grow new command semantics inside `app.py`

Resolution:

- the TUI coordinators now call the real app/runtime capabilities directly
- command orchestration still lives in dedicated coordinator modules
- `app.py` no longer keeps wrapper-only adapter methods for runtime-policy and context-command flow

### TUI skill/model coordinator pass-through shims

Former code path:

- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_run_remote_skill_action_for_coordinator(...)`
- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_run_local_skill_command_result_for_coordinator(...)`
- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_model_inventory_summary_for_coordinator(...)`
- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_apply_model_use_plan_for_coordinator(...)`

Problem:

- these helpers only unpacked coordinator-owned plans and then forwarded into already-owned app/service methods
- model switching also depended on a hidden `current_session` capture instead of the coordinator receiving the active session explicitly
- that pattern kept `app.py` as a shadow orchestration layer even though the actual command flow already lived in dedicated coordinators

Resolution:

- `TuiSessionSkillCommandCoordinator` now unpacks remote/local skill plans itself and calls the real runtime/local-command entrypoints directly
- `TuiSessionModelCommandCoordinator` now receives the active session explicitly for `/model use` flow and computes list summaries from injected provider/render sources
- `app.py` only wires shared capabilities into the coordinators and no longer owns these pass-through shims

### TUI KB/MCP command bridge shims

Former code path:

- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_run_kb_status_result_for_coordinator(...)`
- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_execute_remote_kb_command_for_coordinator(...)`
- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_run_local_kb_command_result_for_coordinator(...)`
- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_dispatch_remote_mcp_command_for_coordinator(...)`
- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_run_local_mcp_command_result_for_coordinator(...)`

Problem:

- `kb` status/toggle flow was still split between a dedicated coordinator and multiple app-local wrapper methods
- those methods mostly repackaged plan/session data before calling already-owned local or remote command services
- `mcp` remote flow had the same issue: the coordinator delegated action shaping back into `app.py` even though the command/action pair were already known
- local `mcp reload` still kept its runtime teardown/warmup sequence inside `app.py`, leaving the final heavy command bridge anchored to the surface layer

Resolution:

- `TuiSessionKbCommandCoordinator` now owns local KB status/toggle orchestration directly and calls injected local/remote capabilities without app-local pass-through shims
- `TuiSessionMcpCommandCoordinator` now builds remote `mcp_*` control dispatch directly from the resolved plan and runs local MCP commands through injected local command/runtime services
- the former local `mcp reload` teardown/warmup sequence is moved into shared runtime code via [`src/mini_agent/runtime/session_local_mcp_runtime_service.py`](../src/mini_agent/runtime/session_local_mcp_runtime_service.py)
- `app.py` now only wires the MCP command coordinator to shared local/remote capabilities and no longer owns MCP reload sequencing

### TUI local runtime rebuild duplication

Former code path:

- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_activate_session_model_selection(...)`
- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_apply_pending_session_skill_reload(...)`
- [`src/mini_agent/tui/app.py`](../src/mini_agent/tui/app.py): `_apply_local_skill_command_result(...)`

Problem:

- local `model switch`, local `skill reload`, and local `mcp reload` all depended on the same runtime rebuild sequence
- that shared sequence lived partly inside `app.py`, so surface code still owned snapshot capture, submission shutdown, runtime execution reset, and agent warmup ordering
- once multiple commands reused that flow, `app.py` became the de facto owner of a runtime orchestration rule that should be reusable below the surface

Resolution:

- the shared rebuild sequence now lives in [`src/mini_agent/runtime/session_local_agent_runtime_handler.py`](../src/mini_agent/runtime/session_local_agent_runtime_handler.py)
- local `mcp reload` continues to use [`src/mini_agent/runtime/session_local_mcp_runtime_service.py`](../src/mini_agent/runtime/session_local_mcp_runtime_service.py), but that service now delegates to the shared local runtime handler
- `app.py` still owns view-local reset details and command feedback, but runtime rebuild truth is now shared below the TUI surface

## 5. Execution rule for future work

- New feature slices should land core/application/runtime behavior first.
- Surface work should wire the existing lower-layer contract second.
- If a change starts in a surface for speed, it must be treated as temporary only when a follow-up boundary slice is already explicit.
- Do not accept "just this one UI autofix" as a permanent pattern.

This file is now part of the active development guardrail set together with:

- [`ARCHITECTURE.md`](./ARCHITECTURE.md)
- [`FRAMEWORK_SKELETON.md`](./FRAMEWORK_SKELETON.md)
- [`DEVELOPMENT_GUIDE.md`](./DEVELOPMENT_GUIDE.md)
