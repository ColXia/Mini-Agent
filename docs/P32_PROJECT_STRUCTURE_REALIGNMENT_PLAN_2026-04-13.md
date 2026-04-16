# P32 Project Structure Realignment Plan

> Status: completed
> Last updated: 2026-04-16
> Goal: realign the physical repository structure with the already-frozen logical architecture so the codebase stops presenting multiple fake "cores"

Execution note (2026-04-16): treat `P32` as materially completed for planning purposes. Residual repo-hygiene cleanup continues separately in later guardrail/worktree slices, but this plan is now a historical record rather than an active execution line.

## 1. Why This Slice Exists

The current logical architecture is already largely stable:

- `CLI / TUI / DesktopUI / Remote Interaction`
- shared `application` service layer
- shared `runtime` orchestration layer
- shared capability modules such as `memory / rag / model_manager / tools / skills / mcp`

However, the physical tree still reflects earlier exploratory stages:

- `agent_core/` and `code_agent/` both look like independent "core" homes
- `turn_context.py` lives at the package root even though it is agent-core context logic
- `agent.py` lives at the package root even though it is the actual agent engine
- `core/session.py` is a historical residue whose name no longer matches the current session architecture
- some modules still carry `gateway_*` naming even after the shared service seam was corrected

## 2. Core Decision

The repository should be reorganized by real ownership, not by historical implementation order.

The target rule is:

- one visible `agent_core` tree for agent-kernel concerns
- `application` stays the shared use-case seam
- `runtime` stays managed-session/runtime orchestration
- shared capability modules stay outside `agent_core`

That means:

- `code_agent/` should stop existing as a peer "core"
- `Agent`, turn context, execution loop, approvals, sandbox, tool-runtime wiring, and MCP execution helpers should live under `agent_core/`
- `memory / rag / model_manager / tools / session / security` remain separate shared capability or platform modules unless their responsibility is truly agent-kernel local

## 3. Target Physical Shape

### First target cut

```text
src/mini_agent/
  agent_core/
    engine.py
    context/
      __init__.py
      turn_context.py
      loop_context.py
      context_compaction.py
    execution/
      __init__.py
      agent_loop.py
      scheduler.py
      coordinator.py
      minimal_workflow.py
      output_masking.py
      approvals/
      sandbox/
      tools/
      mcp/
```

### Later cleanup cuts

Later cuts will remove or rename:

- `core/session.py`
- misleading `gateway_*` application modules where ownership is no longer gateway-specific
- surface-specific `application/*` names where the code is already shared
- overlapping naming between `agent_core/skills` and bundled `skills/`
- overlapping naming between `agent_core/security` and platform `security/`

## 4. Execution Order

### Phase 1: unify the visible agent kernel tree

- move `agent.py` -> `agent_core/engine.py`
- move `turn_context.py` -> `agent_core/context/turn_context.py`
- move `code_agent/context.py` -> `agent_core/context/loop_context.py`
- move `code_agent/context_compression.py` -> `agent_core/context/context_compaction.py`
- move the rest of `code_agent/` into `agent_core/execution/`
- update imports across source and tests
- delete the old `code_agent/` package once all references are moved

### Phase 2: clean historical session packaging

- move `core/session.py` into the canonical `session/` area
- remove the `core/` package if it becomes empty
- make `agent_core/session` mean only session-domain policy/lineage/lifecycle, not storage

### Phase 3: naming debt cleanup

- rename `gateway_*` application modules to surface-neutral names where the code is already shared
- review `security` and `skills` naming to reduce semantic collisions

## 5. Rules For This Refactor

- prefer hard moves over long-lived compatibility shells
- only keep ultra-thin temporary adapters if a single-cut removal would create disproportionate repo churn
- update imports immediately in the same slice
- run focused tests after each cut before moving to the next package family
- update architecture/progress docs as physical ownership changes land

## 6. Acceptance

This slice is successful when:

- the repo no longer presents `agent_core` and `code_agent` as competing top-level cores
- `Agent` and turn-context logic clearly live under `agent_core`
- import paths and tests are green after the first cut
- future work can place agent-kernel code by ownership without guessing

## 7. Status Updates

### P32.46 landed

- revisited the earlier `P32.32` keep decision for runtime memory commands after comparing runtime and local operator flows side by side
- identified the real boundary leak as cross-surface duplication, not runtime-only file size:
  - `src/mini_agent/runtime/session_memory_command_handler.py`
  - `src/mini_agent/commands/execution.py`
  were both maintaining the same `/memory` command semantics
- added:
  - `src/mini_agent/memory/command_service.py`
  - `src/mini_agent/memory/runtime_backend.py`
- updated:
  - `src/mini_agent/runtime/session_memory_command_handler.py`
  - `src/mini_agent/commands/execution.py`
  - `src/mini_agent/runtime/session_operator_handler.py`
  - `src/mini_agent/runtime/main_agent_runtime_manager.py`
- removed:
  - `src/mini_agent/runtime/session_runtime_memory_backend_adapter.py`
- verification:
  - `uv run ruff check src/mini_agent/memory/command_service.py src/mini_agent/memory/runtime_backend.py src/mini_agent/commands/execution.py src/mini_agent/runtime/session_memory_command_handler.py src/mini_agent/runtime/session_operator_handler.py src/mini_agent/runtime/main_agent_runtime_manager.py`
  - result: all green
  - `uv run pytest tests/test_command_execution_service.py tests/test_main_agent_surface_service.py tests/test_agent_studio_gateway_api_v1.py tests/test_tui_app.py tests/test_session_service.py tests/test_runtime_managed_session_store_handler.py tests/test_session_lifecycle_runtime.py tests/test_cli_submission_loop.py -q`
  - result: `262 passed`
- architectural outcome:
  - `/memory` semantics now have one explicit owner under `mini_agent.memory`
  - runtime and local command surfaces are back to wrapper/facade roles instead of dual business implementations
### P32.45 audited and kept

- audited `src/mini_agent/runtime/main_agent_runtime_manager.py`
- audit outcome:
  - keep it intact for now
  - it still reads as the maintained runtime port façade for the application layer
  - its `_initialize_*` phases are private internal graph assembly, not escaped shared-owner utilities
  - its public methods mostly provide lock-consistent delegation into already-split runtime handlers
- low-risk cleanup:
  - removed an unused private helper from `src/mini_agent/runtime/main_agent_runtime_manager.py`
- verification:
  - `uv run ruff check src/mini_agent/runtime/main_agent_runtime_manager.py tests/test_session_service.py tests/test_main_agent_surface_service.py`
  - result: all green
  - `uv run pytest tests/test_session_service.py tests/test_main_agent_surface_service.py -q`
  - result: `81 passed`
- architectural outcome:
  - `MainAgentRuntimeManager` should not be split merely because it is large
  - later runtime cleanup should continue targeting real escaped owners or mixed business domains, not composition-heavy façades

### P32.44 landed

- audited `transport/gateway_client.py` and `transport/remote_session_client.py`
- audit outcome:
  - keep both intact for now
  - they still read as an honest low-level transport + typed session facade pair
- identified a better real ownership leak in runtime bootstrap:
  - `src/mini_agent/runtime/tooling.py` still combined:
    - tool/bootstrap and runtime-policy helpers
    - skill path resolution
    - turn-context provider assembly
- added:
  - `src/mini_agent/runtime/skill_path_resolver.py`
  - `src/mini_agent/runtime/turn_context_provider_builder.py`
- updated:
  - `src/mini_agent/runtime/tooling.py`
  - `src/mini_agent/agent_core/kernel.py`
  - `src/mini_agent/commands/skill_support.py`
  - `tests/test_agent_core_turn_context.py`
- verification:
  - `uv run ruff check src/mini_agent/runtime/skill_path_resolver.py src/mini_agent/runtime/turn_context_provider_builder.py src/mini_agent/runtime/tooling.py src/mini_agent/agent_core/kernel.py src/mini_agent/commands/skill_support.py tests/test_agent_core_turn_context.py`
  - result: all green
  - `uv run pytest tests/test_agent_core_turn_context.py tests/test_agent_core_kernel.py tests/test_security_policy.py tests/test_docling_parse_tool.py tests/test_knowledge_base_tool.py -q`
  - result: `62 passed`
- architectural outcome:
  - `tooling.py` now tells a narrower, truer story
  - skill path resolution has one shared runtime home
  - turn-context provider assembly is no longer hidden inside the tool bootstrap module

### P32.43 landed

- audited `src/mini_agent/application/interaction_request_adapter.py`
- audit outcome:
  - keep it intact for now
  - it still reads as one truthful application adapter over normalized interaction binding
  - it does not currently hide a second business domain
- identified a better real boundary leak in gateway transport:
  - `src/apps/agent_studio_gateway/ops_router.py` still hosted ops auth helpers even though the same auth policy was reused by:
    - `src/apps/agent_studio_gateway/main.py`
    - `src/apps/agent_studio_gateway/composition.py`
- added:
  - `src/apps/agent_studio_gateway/ops_auth.py`
- updated:
  - `src/apps/agent_studio_gateway/ops_router.py`
  - `src/apps/agent_studio_gateway/main.py`
- added focused regression coverage:
  - `tests/test_agent_studio_gateway_ops_auth.py`
- verification:
  - `uv run ruff check src/apps/agent_studio_gateway/ops_auth.py src/apps/agent_studio_gateway/ops_router.py src/apps/agent_studio_gateway/main.py tests/test_agent_studio_gateway_ops_auth.py tests/test_agent_studio_gateway_ops_router.py tests/test_agent_studio_gateway_api_v1.py`
  - result: all green
  - `uv run pytest tests/test_agent_studio_gateway_ops_auth.py tests/test_agent_studio_gateway_ops_router.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `35 passed`
- architectural outcome:
  - `interaction_request_adapter.py` is explicitly a keep decision
  - `ops_router.py` now owns transport routes only
  - shared ops auth policy has one honest home inside the gateway package

### P32.42 landed

- completed the low-risk naming cleanup identified by P32.41
- removed the misleading SessionSurfaceBinding alias from:
  - src/mini_agent/application/session_service.py
  - src/mini_agent/application/__init__.py
- updated binding assertions in:
  - 	ests/test_session_service.py
- verification:
  - uv run ruff check src/mini_agent/application/session_service.py src/mini_agent/application/__init__.py src/mini_agent/application/interaction_request_adapter.py tests/test_session_service.py
  - result: all green
  - uv run pytest tests/test_session_service.py tests/test_main_agent_surface_service.py tests/test_agent_studio_gateway_api_v1.py -q
  - result: 102 passed
- architectural outcome:
  - ApplicationInteractionBinding is now the only maintained application binding abstraction
  - the application layer no longer presents a second fake binding name for the same type


### P32.41 audited and kept

- completed an audit-only slice for:
  - src/mini_agent/application/session_service.py
  - selected runtime/application naming-debt candidates
- audit outcome for session_service.py:
  - keep it intact for now
  - it still reads as one session-application owner rather than a mixed business-domain module
  - its responsibilities still fit together:
    - session CRUD/mutation wrappers through the runtime port
    - request binding normalization for session-scoped operations
    - managed turn preparation for chat and derived chat
- naming-debt outcome:
  - keep these names for now because the ownership is distinct and active:
    - session_lifecycle.py
    - session_runtime_lifecycle_handler.py
    - session_runtime_port.py
    - surface_service_types.py
    - main_agent_runtime_policy_loader.py
  - record one cleaner near-term target instead:
    - SessionSurfaceBinding as a misleading alias of ApplicationInteractionBinding
- architectural outcome:
  - SessionApplicationService should not be split just because it is broad
  - near-term naming cleanup should focus on misleading aliases before renaming active cross-surface owners


### P32.40 audited and kept

- completed a boundary audit for:
  - `src/mini_agent/application/surface_chat_flow_handler.py`
  - `src/mini_agent/application/main_agent_surface_service.py`
- audit outcome:
  - keep both modules intact for now
- reasons for keeping `surface_chat_flow_handler.py`:
  - request chat, stream chat, and dry-run branches are still one cohesive chat-turn flow
  - turn preparation, execution wrapping, finalization, and SSE chunking belong to the same lifecycle owner
  - splitting now would likely create `run` / `stream` / `dry_run` forwarding shells around one flow contract
- reasons for keeping `main_agent_surface_service.py`:
  - it is the maintained application-facing fa莽ade used by gateway and clients
  - its breadth comes from the public surface it exposes, not from hidden business-domain mixing
  - it composes lower-level owners explicitly rather than owning their internals
- architectural outcome:
  - both files are large but currently honest
  - the next physical-structure cuts should keep preferring real ownership leaks over fa莽ade-size cleanup

### P32.39 landed

- completed the next application-boundary cleanup after `P32.38`
- audited `src/mini_agent/application/agent_route_execution_handler.py` and kept:
  - route resolution
  - routing diagnostics bookkeeping
- extracted the real separate owner:
  - delegated child-turn execution + fallback behavior
- added:
  - `src/mini_agent/application/agent_delegation_execution_handler.py`
- updated:
  - `src/mini_agent/application/agent_route_execution_handler.py`
  - `src/mini_agent/application/main_agent_surface_service.py`
  - `src/mini_agent/application/__init__.py`
- added focused regression coverage:
  - `tests/test_agent_delegation_execution_handler.py`
- verification:
  - `uv run ruff check src/mini_agent/application/agent_delegation_execution_handler.py src/mini_agent/application/agent_route_execution_handler.py src/mini_agent/application/main_agent_surface_service.py src/mini_agent/application/__init__.py tests/test_agent_delegation_execution_handler.py`
  - result: all green
  - `uv run pytest tests/test_agent_delegation_execution_handler.py tests/test_main_agent_surface_service.py -q`
  - result: `77 passed`
  - `uv run pytest tests/test_agent_studio_gateway_api_v1.py tests/test_agent_studio_gateway_integration_flows.py -q`
  - result: `23 passed`
- architectural outcome:
  - `AgentRouteExecutionHandler` now tells the truth more clearly:
    - route resolution
    - routing diagnostics
    - route-to-executor dispatch
  - delegation execution/fallback now has an explicit application owner instead of hiding inside the route owner

### P32.38 landed

- completed the next application-boundary cleanup after `P32.37`
- identified `src/mini_agent/application/channel_ingress_use_cases.py` as a real mixed owner because it still combined:
  - remote conversation ingress and binding
  - feature-specific `/novel ...` command parsing
  - feature-specific novel action dispatch
- added:
  - `src/mini_agent/application/channel_novel_action_handler.py`
- updated:
  - `src/mini_agent/application/channel_ingress_use_cases.py`
  - `src/apps/agent_studio_gateway/composition.py`
  - `src/mini_agent/application/__init__.py`
- added focused regression coverage:
  - `tests/test_channel_novel_action_handler.py`
- verification:
  - `uv run ruff check src/mini_agent/application/channel_novel_action_handler.py src/mini_agent/application/channel_ingress_use_cases.py src/mini_agent/application/__init__.py src/apps/agent_studio_gateway/composition.py tests/test_channel_novel_action_handler.py tests/test_channel_ingress_use_cases.py tests/test_agent_studio_gateway_api_v1.py`
  - result: all green
  - `uv run pytest tests/test_channel_novel_action_handler.py tests/test_channel_ingress_use_cases.py tests/test_agent_studio_gateway_api_v1.py tests/test_agent_studio_gateway_integration_flows.py -q`
  - result: `31 passed`
- architectural outcome:
  - `ChannelIngressUseCases` is back to being a remote-entry owner
  - channel-facing novel action behavior now has its own explicit application owner instead of hiding inside ingress orchestration

### P32.37 landed

- completed the next runtime-boundary cleanup after `P32.36`
- kept `src/mini_agent/runtime/session_operator_handler.py` intact after audit:
  - it is still the real session operator-command facade
  - it coordinates locking, transcript recording, and persistence around one command surface
- split the old mixed `src/mini_agent/runtime/session_control_handler.py` into:
  - `src/mini_agent/runtime/session_control_models.py`
  - `src/mini_agent/runtime/session_agent_control_handler.py`
  - `src/mini_agent/runtime/session_mcp_control_handler.py`
- removed `src/mini_agent/runtime/session_control_handler.py`
- rewired `src/mini_agent/runtime/main_agent_runtime_manager.py` and `src/mini_agent/runtime/session_operator_handler.py` to compose the new owners explicitly
- added focused regression coverage:
  - `tests/test_runtime_session_agent_control_handler.py`
  - `tests/test_runtime_session_mcp_control_handler.py`
- verification:
  - `uv run ruff check src/mini_agent/runtime/session_control_models.py src/mini_agent/runtime/session_agent_control_handler.py src/mini_agent/runtime/session_mcp_control_handler.py src/mini_agent/runtime/session_operator_handler.py src/mini_agent/runtime/main_agent_runtime_manager.py tests/test_runtime_session_agent_control_handler.py tests/test_runtime_session_mcp_control_handler.py`
  - result: all green
  - `uv run pytest tests/test_runtime_session_agent_control_handler.py tests/test_runtime_session_mcp_control_handler.py tests/test_main_agent_surface_service.py -q`
  - result: `81 passed`
  - `uv run pytest tests/test_session_service.py tests/test_p19_runtime_matrix.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `29 passed`
- architectural outcome:
  - MCP operational control no longer shares a runtime owner with agent context/KB control
  - `RuntimeSessionOperatorHandler` remains a legitimate orchestration facade rather than a fake business owner

### P32.36 landed

- completed the recovery-state ownership follow-up after `P32.35`
- moved `apply_stored_recovery(...)` out of `src/mini_agent/runtime/session_hydration_builder.py`
- added the recovery-state mutation to:
  - `src/mini_agent/runtime/session_recovery_reset_handler.py`
- rewired `src/mini_agent/runtime/main_agent_runtime_manager.py` so restore assembly now uses the recovery owner directly
- added regression coverage to `tests/test_runtime_session_recovery_reset_handler.py` for stored-recovery apply behavior
- verification:
  - `uv run ruff check src/mini_agent/runtime/session_recovery_reset_handler.py src/mini_agent/runtime/session_hydration_builder.py src/mini_agent/runtime/main_agent_runtime_manager.py tests/test_runtime_session_recovery_reset_handler.py`
  - result: all green
  - `uv run pytest tests/test_runtime_session_recovery_reset_handler.py tests/test_runtime_session_hydration_coordinator.py tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_p19_runtime_matrix.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `110 passed`
- architectural outcome:
  - recovery projection state apply/clear/build/reset now lives under one runtime owner
  - hydration builder is closer to a true payload/session-state builder again

### P32.35 landed

- extracted two real runtime owners out of `src/mini_agent/runtime/session_live_state_handler.py`
- added:
  - `src/mini_agent/runtime/session_pending_approval_state_handler.py`
  - `src/mini_agent/runtime/session_recovery_reset_handler.py`
- updated `src/mini_agent/runtime/session_live_state_handler.py` so it now focuses on:
  - surface binding
  - transcript/activity mutation
  - turn running-state flags
- rewired `src/mini_agent/runtime/main_agent_runtime_manager.py` to use explicit seams for:
  - pending approval normalization/state mutation
  - recovery-context building/clearing
  - runtime reset cleanup
- added focused regression coverage:
  - `tests/test_runtime_session_pending_approval_state_handler.py`
  - `tests/test_runtime_session_recovery_reset_handler.py`
- verification:
  - `uv run ruff check src/mini_agent/runtime/session_live_state_handler.py src/mini_agent/runtime/session_pending_approval_state_handler.py src/mini_agent/runtime/session_recovery_reset_handler.py src/mini_agent/runtime/main_agent_runtime_manager.py tests/test_runtime_session_pending_approval_state_handler.py tests/test_runtime_session_recovery_reset_handler.py`
  - result: all green
  - `uv run pytest tests/test_runtime_session_pending_approval_state_handler.py tests/test_runtime_session_recovery_reset_handler.py tests/test_runtime_session_admin_handler.py tests/test_runtime_session_lifecycle_handler.py tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_p19_runtime_matrix.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `114 passed`
- architectural outcome:
  - `RuntimeSessionLiveStateHandler` no longer teaches that approval-state and recovery/reset are just sub-parts of "live state"
  - runtime state mutation seams are now closer to the real domains they serve

### P32.34 landed

- hard-corrected the `mini_agent.session` package surface so it no longer exposes a fake second session core
- removed legacy public exports from `src/mini_agent/session/__init__.py`:
  - `SessionState`
  - `SessionStore`
  - `session_store`
- deleted `src/mini_agent/session/store.py`
- replaced the legacy store-only regression file with live-owner coverage:
  - added `tests/test_session_package_exports.py`
  - added `tests/test_session_persistence_contract.py`
  - removed `tests/test_session_store_persistence.py`
- verification:
  - `uv run ruff check src/mini_agent/session/__init__.py src/mini_agent/session/persistence.py tests/test_session_package_exports.py tests/test_session_persistence_contract.py`
  - result: all green
  - `uv run pytest tests/test_session_package_exports.py tests/test_session_persistence_contract.py tests/test_memory_relevance.py tests/test_memory_service.py tests/test_memory_consolidation.py -q`
  - result: `17 passed`
  - `uv run pytest tests/test_runtime_managed_session_store_handler.py tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_p19_runtime_matrix.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `107 passed`
- architectural outcome:
  - `mini_agent.session` now tells the truth about its real ownership:
    - persistence primitives
    - session projections
    - conversation binding
  - live runtime session truth remains explicitly in the `runtime/` tree

### P32.33 landed

- completed a package-boundary audit for:
  - `src/mini_agent/session/__init__.py`
  - `src/mini_agent/session/store.py`
- audit outcome:
  - `SessionStore` / `SessionState` are no longer the live runtime session truth
  - active runtime session ownership now sits in:
    - `src/mini_agent/runtime/session_state.py`
    - `src/mini_agent/runtime/session_runtime_persistence.py`
    - `src/mini_agent/runtime/session_managed_store_handler.py`
    - `src/mini_agent/runtime/main_agent_runtime_manager.py`
  - `mini_agent.session` still has active ownership, but it is mainly:
    - `SessionPersistence`
    - session read/transport projections
    - conversation binding services
  - the real structural problem is that `session/__init__.py` and `session/store.py` still present the old store/state as canonical public truth
- search evidence:
  - live `src/mini_agent` imports do not meaningfully consume `SessionStore`
  - maintained runtime/application/TUI/memory flows consume runtime session state plus `SessionPersistence`
  - `SessionStore` is currently exercised mainly by its own dedicated persistence tests
- architectural outcome:
  - the next meaningful `P32` cut should target the `mini_agent.session` public story itself
  - likely next step:
    - demote/rehome/remove `SessionStore` from the canonical session package surface
    - keep `mini_agent.session` focused on persistence, projections, and conversation binding

### P32.32 landed

- completed a code-level audit of `src/mini_agent/runtime/session_memory_command_handler.py`
- audit outcome:
  - do not split the module yet
  - unlike the former mixed `OperationsUseCases`, this file still owns one cohesive runtime command domain:
    - `/memory` runtime/session/shared reads
    - durable memory reads
    - memory mutations
- reasons for keeping it intact:
  - maintained tests exercise it as one stable command surface across CLI/TUI/gateway flows
  - major formatting helpers already live in `mini_agent.memory.diagnostics`
  - splitting right now would likely produce thin forwarding shells around the same diagnostics/session/backend state
- future split trigger should be behavior divergence, not raw line count:
  - durable read logic grows an independent policy/caching surface
  - mutation logic grows distinct retry/approval/persistence semantics
  - another caller needs a real subset seam
- architectural outcome:
  - the next physical-structure cuts should continue targeting real ownership leaks, not merely large files

### P32.31 landed

- replaced the mixed application ops owner with separated seams:
  - added `src/mini_agent/application/operations_path_policy.py`
  - added `src/mini_agent/application/operations_provider_use_cases.py`
  - added `src/mini_agent/application/operations_memory_use_cases.py`
  - removed `src/mini_agent/application/operations_use_cases.py`
- rewired gateway ops transport/host composition to use explicit separated dependencies:
  - `src/apps/agent_studio_gateway/main.py`
  - `src/apps/agent_studio_gateway/ops_router.py`
- split the unit regression surface to match the new ownership:
  - `tests/test_operations_provider_use_cases.py`
  - `tests/test_operations_memory_use_cases.py`
- verification:
  - `uv run pytest tests/test_operations_provider_use_cases.py tests/test_operations_memory_use_cases.py tests/test_agent_studio_gateway_ops_router.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `35 passed`
  - `uv run pytest tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_p19_runtime_matrix.py tests/test_agent_studio_gateway_api_v1.py tests/test_agent_studio_gateway_ops_router.py tests/test_operations_provider_use_cases.py tests/test_operations_memory_use_cases.py -q`
  - result: `118 passed`
  - targeted `ruff check` on the split slice
  - result: all green
- architectural outcome:
  - `application/` no longer presents one mixed owner for provider/model admin and memory admin
  - gateway ops transport now teaches the same explicit dependency pattern while depending on cleaner domain seams

### P32.30 landed

- updated `src/mini_agent/runtime/session_catalog_handler.py` so session-summary dedupe / conversation keys now use the canonical runtime workspace path seam from `src/mini_agent/runtime/workspace_path_utils.py`
- removed the catalog-local path-key helper
- completed a boundary-health audit for:
  - `src/mini_agent/application/operations_use_cases.py`
  - `src/mini_agent/runtime/session_memory_command_handler.py`
- audit outcome:
  - `OperationsUseCases` is the more meaningful next refactor target because it still mixes provider/model ops, memory ops, and path-policy helpers
  - `RuntimeSessionMemoryCommandHandler` is large but still coheres around one session-memory command domain
- verification:
  - `uv run pytest tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_agent_studio_gateway_api_v1.py tests/test_p19_runtime_matrix.py -q`
  - result: `104 passed`
  - targeted `ruff check` on the catalog/path slice
  - result: all green
- architectural outcome:
  - runtime workspace path ownership is more consistent
  - the next high-value physical-structure slice is now explicitly identified instead of guessed later

### P32.29 landed

- added `src/mini_agent/application/managed_session_turn.py` as the canonical owner of the application-layer turn lease object
- moved `ManagedSessionTurn` out of `src/mini_agent/application/session_service.py`
- updated application orchestrators and exports to import the turn lease from the new canonical module
- verification:
  - `uv run pytest tests/test_runtime_session_snapshot_builder.py tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_agent_studio_gateway_api_v1.py tests/test_p19_runtime_matrix.py -q`
  - result: `106 passed`
  - targeted `ruff check` on the application turn-lease slice
  - result: all green
- architectural outcome:
  - `SessionApplicationService` now reads more honestly as a service module
  - the application turn lease has an explicit owner instead of living as a sidecar type inside the service file

### P32.28 landed

- added `src/mini_agent/runtime/session_snapshot_builder.py` as the canonical owner of runtime snapshot export construction
- removed snapshot export building from `src/mini_agent/runtime/session_read_model_builder.py`
- rewired `src/mini_agent/runtime/main_agent_runtime_manager.py` and `src/mini_agent/runtime/session_snapshot_handler.py` to consume `RuntimeSessionSnapshotBuilder`
- added focused regression coverage in `tests/test_runtime_session_snapshot_builder.py`
- verification:
  - `uv run pytest tests/test_runtime_session_snapshot_builder.py tests/test_runtime_session_hydration_coordinator.py tests/test_runtime_workspace_path_utils.py tests/test_session_lifecycle_runtime.py tests/test_runtime_session_lifecycle_handler.py tests/test_runtime_session_agent_support.py tests/test_runtime_session_model_identity_codec.py tests/test_runtime_session_payload_codec.py tests/test_runtime_managed_session_store_handler.py tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_p19_runtime_matrix.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `126 passed`
  - targeted `ruff check` on the runtime snapshot-builder slice
  - result: all green
- architectural outcome:
  - snapshot export now has a dedicated builder owner instead of broadening the read-model builder
  - runtime read-model assembly and snapshot export assembly are more clearly separated

### P32.27 landed

- added `src/mini_agent/runtime/workspace_path_utils.py` as the canonical owner of runtime workspace-path normalization:
  - `workspace_path_key(...)`
  - `same_workspace_path(...)`
- updated `src/mini_agent/runtime/session_runtime_lifecycle_handler.py`, `src/mini_agent/runtime/session_lifecycle.py`, and `src/mini_agent/runtime/main_agent_runtime_manager.py` to consume the shared path seam
- removed manager-local helper shells for:
  - workspace path keying
  - same-workspace comparison
  - surface normalization pass-through
  - main-workspace policy pass-through
- added focused regression coverage in `tests/test_runtime_workspace_path_utils.py`
- updated `tests/test_session_lifecycle_runtime.py` to assert against the canonical workspace-path helper
- verification:
  - `uv run pytest tests/test_runtime_session_hydration_coordinator.py tests/test_runtime_workspace_path_utils.py tests/test_session_lifecycle_runtime.py tests/test_runtime_session_lifecycle_handler.py tests/test_runtime_session_agent_support.py tests/test_runtime_session_model_identity_codec.py tests/test_runtime_session_payload_codec.py tests/test_runtime_managed_session_store_handler.py tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_p19_runtime_matrix.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `124 passed`
  - targeted `ruff check` on the workspace-path/runtime-manager slice
  - result: all green
- architectural outcome:
  - the manager now owns less utility noise and more actual runtime assembly
  - workspace path normalization is now explicit shared runtime ownership instead of duplicated local helpers

### P32.26 landed

- added `src/mini_agent/runtime/session_hydration_coordinator.py` as the explicit owner of persisted restore / managed hydration coordination
- removed persisted restore / hydrate glue from `src/mini_agent/runtime/main_agent_runtime_manager.py`
- rewired managed-session-store and session-registry callbacks to consume `RuntimeSessionHydrationCoordinator`
- added focused seam regression coverage in `tests/test_runtime_session_hydration_coordinator.py`
- verification:
  - `uv run pytest tests/test_runtime_session_hydration_coordinator.py tests/test_runtime_session_agent_support.py tests/test_runtime_session_model_identity_codec.py tests/test_runtime_session_payload_codec.py tests/test_runtime_managed_session_store_handler.py tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_p19_runtime_matrix.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `116 passed`
  - targeted `ruff check` on the hydration/runtime-manager slice
  - result: all green
- architectural outcome:
  - persisted restore / hydrate flow now has a dedicated coordination seam instead of living as manager-private glue
  - `MainAgentRuntimeManager` continues shrinking toward true orchestration and public runtime entry ownership

### P32.25 landed

- added `src/mini_agent/runtime/session_agent_support.py` as the canonical owner of runtime-local agent/config/KB support helpers:
  - default / selected-identity agent build routing
  - knowledge-base enable/apply inspection
  - sandbox diagnostics -> runtime policy override extraction
  - runtime config loading
- removed that helper cluster from `src/mini_agent/runtime/main_agent_runtime_manager.py`
- rewired creation, hydration, model-selection, control, restore, and agent-runtime assembly to consume `RuntimeSessionAgentSupport`
- added focused seam regression coverage in `tests/test_runtime_session_agent_support.py`
- updated runtime/surface tests that patch config loading to target the new support seam instead of the manager module
- verification:
  - `uv run pytest tests/test_runtime_session_agent_support.py tests/test_runtime_session_model_identity_codec.py tests/test_runtime_session_payload_codec.py tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_p19_runtime_matrix.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `111 passed`
  - targeted `ruff check` on the runtime support slice
  - result: all green
- architectural outcome:
  - runtime-local agent/config/KB support is now an explicit seam instead of another manager helper knot
  - `MainAgentRuntimeManager` continues shrinking toward true orchestration/assembly ownership

### P32.19 landed

- `src/mini_agent/application/main_agent_surface_service.py` no longer constructs `SessionApplicationService` internally
- gateway composition now owns an explicit session-service assembly seam:
  - added `GatewayComposition.get_session_service()`
  - `get_surface_service()` now injects the shared session service
  - shutdown clears the session-service cache together with runtime/surface state
- updated `tests/test_main_agent_surface_service.py` to follow the explicit seam
- added a focused injection test proving session listing uses the injected service instead of hidden construction
- verification:
  - `uv run pytest tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_channel_ingress_use_cases.py tests/test_agent_studio_gateway_api_v1.py tests/test_agent_studio_gateway_integration_flows.py tests/test_p19_runtime_matrix.py -q`
  - result: `109 passed`
  - targeted `ruff check` on the surface/composition seam
  - result: all green
- architectural outcome:
- `MainAgentSurfaceService` now behaves like a true shared surface orchestrator
- host/composition owns service assembly again instead of leaking lower-level construction into the application service
- the next `application / session / channel` seam cuts can build on a clearer ownership story

### P32.20 landed

- added `src/mini_agent/session/conversation_binding_port.py` as the session-owned binding seam for remote conversation lookup/persistence
- updated `src/mini_agent/application/channel_ingress_use_cases.py` so `ChannelIngressUseCases` now depends on `ConversationBindingPort` instead of the concrete `ConversationBindingService`
- updated gateway composition and gateway/channel tests to inject the concrete binding service through the port seam
- added a focused seam regression in `tests/test_channel_ingress_use_cases.py` proving channel ingress can operate against a structural fake binding port
- verification:
  - `uv run pytest tests/test_channel_ingress_use_cases.py tests/test_agent_studio_gateway_api_v1.py tests/test_agent_studio_gateway_integration_flows.py tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_p19_runtime_matrix.py -q`
  - result: `110 passed`
  - targeted `ruff check` on the ingress/binding seam
  - result: all green
- architectural outcome:
- remote conversation binding now reads as a session-owned contract instead of an application-owned concrete helper
- gateway composition remains the concrete assembly owner
- application ingress orchestration depends on an explicit seam that is easier to extend for future remote channels

### P32.21 landed

- removed the unused direct runtime dependency from `src/mini_agent/application/main_agent_surface_service.py`
- `MainAgentSurfaceService` now depends on the injected session-service seam only
- updated gateway composition and surface-service tests to the narrower surface constructor
- runtime-touching test helpers now reach through `SessionApplicationService` explicitly instead of relying on a stale `_runtime_manager` field on the surface service
- verification:
  - `uv run pytest tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_channel_ingress_use_cases.py tests/test_agent_studio_gateway_api_v1.py tests/test_agent_studio_gateway_integration_flows.py tests/test_p19_runtime_matrix.py -q`
  - result: `110 passed`
  - targeted `ruff check` on the surface/composition seam
  - result: all green
- architectural outcome:
  - the surface service constructor now tells the truth about its real dependency boundary
  - callers and tests no longer get encouraged to treat runtime as part of the surface contract

### P32.22 landed

- added `src/mini_agent/runtime/main_agent_runtime_contracts.py` as the canonical owner of:
  - `MainAgentRuntimeMode`
  - `MainAgentRuntimePolicy`
  - `MainAgentRuntimeDiagnostics`
- removed those runtime contracts from `src/mini_agent/runtime/main_agent_runtime_manager.py`
- updated `src/mini_agent/runtime/main_agent_runtime_policy_loader.py` to depend on runtime contracts instead of the runtime manager module
- updated `src/mini_agent/runtime/__init__.py` lazy exports so runtime contracts resolve from their new owner
- updated active runtime/surface tests to import contracts from the new canonical module
- verification:
  - `uv run pytest tests/test_main_agent_runtime_policy_loader.py tests/test_p19_runtime_matrix.py tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `106 passed`
  - targeted `ruff check` on the runtime-contract slice
  - result: all green
- architectural outcome:
  - pure runtime policy/config code no longer imports `main_agent_runtime_manager.py` just to access declarative contracts
  - the manager now reads a little more like orchestration and a little less like a dumping ground for runtime-adjacent types

### P32.23 landed

- added `src/mini_agent/runtime/session_payload_codec.py` as the canonical owner of runtime payload/message/token normalization helpers
- removed payload/message/token codec helpers from `src/mini_agent/runtime/main_agent_runtime_manager.py`
- rewired runtime diagnostics, hydration, read-model, restore, and agent-runtime assembly to consume `RuntimeSessionPayloadCodec`
- added focused codec regression coverage in `tests/test_runtime_session_payload_codec.py`
- verification:
  - `uv run pytest tests/test_runtime_session_payload_codec.py tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_p19_runtime_matrix.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `106 passed`
  - targeted `ruff check` on the runtime payload codec slice
  - result: all green
- architectural outcome:
  - `MainAgentRuntimeManager` now owns less data-shaping residue and more actual orchestration
  - runtime payload/message/token translation is now explicit and reusable as a dedicated seam

### P32.24 landed

- added `src/mini_agent/runtime/session_model_identity_codec.py` as the canonical owner of session model-identity normalization helpers
- removed selected/pending model identity helpers from `src/mini_agent/runtime/main_agent_runtime_manager.py`
- rewired hydration, read-model, model-selection, restore, operator, and agent-runtime assembly to consume `RuntimeSessionModelIdentityCodec`
- added focused codec regression coverage in `tests/test_runtime_session_model_identity_codec.py`
- verification:
  - `uv run pytest tests/test_runtime_session_model_identity_codec.py tests/test_runtime_session_payload_codec.py tests/test_main_agent_surface_service.py tests/test_session_service.py tests/test_p19_runtime_matrix.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `108 passed`
  - targeted `ruff check` on the runtime model-identity slice
  - result: all green
- architectural outcome:
  - session model identity is now explicit runtime-owned logic instead of another helper knot inside the manager
  - manager orchestration continues shrinking toward real coordination responsibility

### P32.1 landed

- `src/mini_agent/agent_core/engine.py` -> `src/mini_agent/agent_core/engine.py`
- `src/mini_agent/agent_core/context/turn_context.py` -> `src/mini_agent/agent_core/context/turn_context.py`
- `src/mini_agent/code_agent/context.py` -> `src/mini_agent/agent_core/context/loop_context.py`
- `src/mini_agent/code_agent/context_compression.py` -> `src/mini_agent/agent_core/context/context_compaction.py`
- remaining `code_agent/*` runtime primitives -> `src/mini_agent/agent_core/execution/*`

### P32.2 landed

- `src/mini_agent/core/session.py` -> `src/mini_agent/session/store.py`
- `src/mini_agent/core/` removed
- canonical store import path is now `mini_agent.session`
- `agent_core/session` now remains reserved for session-domain policy / lineage ownership only

### P32.3 landed

- `src/mini_agent/application/gateway_agent_execution_handler.py` -> `src/mini_agent/application/agent_turn_execution_handler.py`
- `src/mini_agent/application/gateway_route_execution_handler.py` -> `src/mini_agent/application/agent_route_execution_handler.py`
- `src/mini_agent/application/gateway_chat_flow_handler.py` -> `src/mini_agent/application/surface_chat_flow_handler.py`
- removed `src/mini_agent/application/main_agent_gateway_use_cases.py`
- removed `MainAgentGatewayUseCases` compatibility export; canonical shared orchestration entry is now `MainAgentSurfaceService`
- removed `ApplicationInteractionBinding.to_gateway_chat_execution_request(...)`; canonical projection is now `to_surface_chat_execution_request(...)`

### P32.5 landed

- `src/mini_agent/runtime/interaction_surface.py` -> `src/mini_agent/interaction/surface.py`
- added `src/mini_agent/interaction/__init__.py` as the canonical shared export package
- application/runtime/tests now import from `mini_agent.interaction`
- removed the old runtime-local module instead of leaving a compatibility shim


### P32.6 landed

- added `src/mini_agent/application/session_runtime_port.py` as the canonical application-facing runtime port
- `SessionApplicationService` now depends on `SessionRuntimePort` / `ManagedRuntimeSessionPort` / `SessionTurnScopePort` instead of importing:
  - `MainAgentRuntimeManager`
  - `MainAgentSessionState`
  - `RuntimeSessionTurnScopeHandler`
- enriched `src/mini_agent/runtime/session_state.py` with boundary-friendly session projection properties:
  - `agent`
  - `cancel_event`
  - `active_surface`
  - `origin_surface`
  - `channel_type`
  - `conversation_id`
  - `sender_id`
  - `context_policy`
  - `busy`
  - `running_state`
  - `pending_approvals`
  - `token_usage`
  - `message_count`
- `MainAgentSurfaceService` now takes the shared runtime port type instead of a concrete runtime-manager type
- added a structural seam test proving `SessionApplicationService` can operate against a fake runtime port without runtime concrete classes
- verification:
  - `uv run pytest tests/test_session_service.py tests/test_main_agent_surface_service.py tests/test_interaction_surface.py tests/test_interaction_request_adapter.py -q`
  - result: `90 passed`
  - `uv run pytest -q`
  - result: `919 passed, 15 skipped`
  - targeted `ruff check` on the seam slice
  - result: all green
- architectural outcome:
  - the application layer no longer imports runtime-owned concrete manager/session/turn-scope classes for normal session orchestration
  - runtime is still the implementation owner, but the boundary now reads as a port instead of a reach-through dependency

### P32.7 landed

- added `src/mini_agent/application/remote_session_transport_port.py` as the explicit transport seam for `RemoteSessionService`
- `RemoteSessionService` now depends on `RemoteSessionTransportPort` instead of a loosely named `gateway_client` object
- updated shared exports and TUI wiring to pass `session_transport=self.gateway_client`
- updated remote-session tests to the new seam naming
- verification:
  - `uv run pytest tests/test_session_remote_service.py tests/test_tui_app.py tests/test_tui_gateway_client.py -q`
  - result: `129 passed`
  - `uv run pytest -q`
  - result: `919 passed, 15 skipped`
  - targeted `ruff check` on the remote-session seam slice
  - result: all green
- architectural outcome:
  - the client-side remote session facade now depends on a named transport port instead of a gateway-specific implementation detail

### P32.8 landed

- moved client-side transport clients out of misleading ownership locations and into a canonical shared `transport/` package:
  - `src/mini_agent/application/session_remote_service.py` -> `src/mini_agent/transport/remote_session_client.py`
  - `src/mini_agent/application/remote_session_transport_port.py` -> `src/mini_agent/transport/session_transport_port.py`
  - `src/mini_agent/tui/gateway_client.py` -> `src/mini_agent/transport/gateway_client.py`
- corrected client naming to match true ownership:
  - `RemoteSessionService` -> `RemoteSessionClient`
  - `TuiGatewayClient` -> `GatewayClient`
- updated TUI/Desktop imports and wiring to the shared transport package
- renamed test files to the new transport ownership language:
  - `tests/test_session_remote_service.py` -> `tests/test_transport_remote_session_client.py`
  - `tests/test_tui_gateway_client.py` -> `tests/test_transport_gateway_client.py`
- verification:
  - `uv run pytest tests/test_transport_remote_session_client.py tests/test_transport_gateway_client.py tests/test_tui_app.py tests/test_desktop_app.py -q`
  - result: `131 passed`
  - `uv run pytest -q`
  - result: `919 passed, 15 skipped`
  - targeted `ruff check` on the transport realignment slice
  - result: all green
- architectural outcome:
  - client-side gateway/session facades no longer pretend to be application services or TUI-only utilities
  - TUI and Desktop now share an explicit transport package whose ownership matches the framework skeleton

### P32.9 landed

- moved remote conversation binding ownership into the canonical `session/` package:
  - `src/mini_agent/application/remote_conversation_binding_service.py` -> `src/mini_agent/session/conversation_binding_service.py`
- rewired `ChannelIngressUseCases`, gateway composition, walkthrough scripts, and tests to consume `ConversationBindingService` from `mini_agent.session`
- extracted novel-specific ownership out of `application/`:
  - `src/mini_agent/application/novel_agent_profile.py` -> `src/mini_agent/novel/profile.py`
  - `src/mini_agent/application/novel_service_use_cases.py` -> `src/mini_agent/novel/service.py`
- updated gateway composition and tests to consume the canonical `mini_agent.novel` package
- architectural outcome:
  - session binding is now visibly session-owned instead of looking like a gateway/application side utility
  - novel code no longer pollutes the shared application package with product-subdomain ownership

### P32.10 landed

- renamed the remaining surface-colored shared ops seam:
  - `src/mini_agent/application/studio_ops_use_cases.py` -> `src/mini_agent/application/operations_use_cases.py`
  - `StudioOpsUseCases` -> `OperationsUseCases`
- updated gateway composition and tests:
  - `src/apps/agent_studio_gateway/ops_router.py`
  - `src/apps/agent_studio_gateway/main.py`
  - `tests/test_operations_use_cases.py`
  - ops router/API tests now reference `_OPERATIONS_USE_CASES`
- verification:
  - `uv run pytest tests/test_operations_use_cases.py tests/test_agent_studio_gateway_ops_router.py tests/test_agent_studio_gateway_api_v1.py tests/test_channel_ingress_use_cases.py tests/test_novel_service_use_cases.py -q`
  - result: `42 passed`
  - `uv run ruff check src/mini_agent/application src/mini_agent/session src/mini_agent/novel src/apps/agent_studio_gateway tests/test_operations_use_cases.py tests/test_agent_studio_gateway_ops_router.py tests/test_agent_studio_gateway_api_v1.py tests/test_channel_ingress_use_cases.py tests/test_novel_service_use_cases.py`
  - result: all green
- architectural outcome:
  - the application layer keeps the shared provider/memory operations seam
  - but it no longer falsely advertises Studio/Web ownership in the service name

### P32.11 landed

- renamed the gateway-side ops transport module to match its real ownership:
  - `src/apps/agent_studio_gateway/ops_router.py` -> `src/apps/agent_studio_gateway/ops_router.py`

### P32.12 landed

- extracted the remaining novel-specific transport/runtime cluster out of the gateway composition root:
  - added `src/mini_agent/novel/runtime.py`
  - upgraded `src/subprograms/novel_generator/gateway/router.py` into the maintained novel HTTP transport
  - `src/apps/agent_studio_gateway/main.py` now mounts `novel_router` under `/api/v1/novel`
- removed gateway-main ownership of:
  - novel env/profile parsing
  - project path helpers
  - chapter history/version helper functions
  - novel use-case factory construction
  - `/api/v1/novel/*` route handlers
- reused the canonical interface layer instead of duplicating subprogram-local DTOs:
  - `src/subprograms/novel_generator/gateway/router.py` now consumes `mini_agent.interfaces`
- updated:
  - `src/mini_agent/novel/__init__.py`
  - `src/subprograms/novel_generator/manifest.json`
- verification:
  - `uv run pytest tests/test_agent_studio_gateway_api_v1.py tests/test_agent_studio_gateway_integration_flows.py tests/test_channel_ingress_use_cases.py tests/test_novel_service_use_cases.py -q`
  - result: `30 passed`
  - `uv run ruff check src/apps/agent_studio_gateway/main.py src/mini_agent/novel src/subprograms/novel_generator/gateway/router.py`
  - result: all green
- architectural outcome:
  - `main.py` returns further toward a true composition root
  - `mini_agent.novel` now visibly owns its runtime wiring
  - `subprograms/novel_generator` now visibly owns the novel HTTP transport surface

### P32.13 landed

- extracted the maintained main-agent HTTP/SSE contract out of the gateway composition root:
  - added `src/apps/agent_studio_gateway/main_agent_router.py`
  - moved transport handling for:
    - `/api/v1/system/health`
    - `/api/v1/ops/diagnostics/*`
    - `/api/v1/agent/*`
    - `/api/v1/channel/message`
- `src/apps/agent_studio_gateway/main.py` now mounts the main-agent router with injected dependencies:
  - runtime-manager getter
  - surface-service getter
  - channel-ingress getter
  - model-list helper
  - ops auth dependency
- verification:
  - `uv run pytest tests/test_agent_studio_gateway_api_v1.py tests/test_agent_studio_gateway_integration_flows.py tests/test_channel_ingress_use_cases.py tests/test_novel_service_use_cases.py -q`
  - result: `30 passed`
  - `uv run ruff check src/apps/agent_studio_gateway/main.py src/apps/agent_studio_gateway/main_agent_router.py src/mini_agent/novel src/subprograms/novel_generator/gateway/router.py`
  - result: all green
- architectural outcome:
  - `main.py` now reads more clearly as host composition + lifecycle wiring
  - the gateway鈥檚 maintained main-agent transport surface has an explicit home

### P32.14 landed

- extracted gateway runtime/service/lifecycle assembly into an explicit composition module:
  - added `src/apps/agent_studio_gateway/composition.py`
- moved gateway-owned assembly concerns out of `main.py`:
  - runtime-manager construction
  - surface-service construction
  - channel-ingress construction
  - health/runtime diagnostics assembly
  - instance-lock startup and shutdown cleanup
- `src/apps/agent_studio_gateway/main.py` is now primarily:
  - settings + composition initialization
  - FastAPI host assembly
  - static asset mounting
  - SPA fallback wiring
- updated:
  - `src/apps/agent_studio_gateway/main_agent_router.py`
  - `tests/test_agent_studio_gateway_api_v1.py`
  - `tests/test_p19_runtime_matrix.py`
- verification:
  - `uv run pytest tests/test_agent_studio_gateway_api_v1.py tests/test_agent_studio_gateway_integration_flows.py tests/test_channel_ingress_use_cases.py tests/test_novel_service_use_cases.py tests/test_p19_runtime_matrix.py -q`
  - result: `32 passed`
  - `uv run ruff check src/apps/agent_studio_gateway/main.py src/apps/agent_studio_gateway/composition.py src/apps/agent_studio_gateway/main_agent_router.py tests/test_agent_studio_gateway_api_v1.py tests/test_p19_runtime_matrix.py`
  - result: all green
- architectural outcome:
  - the gateway host now has an explicit composition seam instead of hidden module-global service assembly
  - tests and future refactors have a clearer place to target than `main.py` internals

### P32.15 landed

- extracted browser/static hosting out of the gateway entrypoint:
  - added `src/apps/agent_studio_gateway/static_host.py`
- moved Studio/browser host responsibilities out of `main.py`:
  - Studio dist resolution
  - `/api/files` mount
  - `/assets` mount
  - root index serving
  - SPA fallback
  - dist-missing fallback response
- updated:
  - `src/apps/agent_studio_gateway/main.py`
  - `tests/test_agent_studio_gateway_static_host.py`
- verification:
  - `uv run pytest tests/test_agent_studio_gateway_static_host.py tests/test_agent_studio_gateway_api_v1.py tests/test_agent_studio_gateway_integration_flows.py tests/test_p19_runtime_matrix.py -q`
  - result: `28 passed`
  - `uv run ruff check src/apps/agent_studio_gateway/main.py src/apps/agent_studio_gateway/static_host.py tests/test_agent_studio_gateway_static_host.py`
  - result: all green
- architectural outcome:
  - `main.py` now reads as a much cleaner host entrypoint
  - browser/static serving policy has an explicit ownership home instead of lingering in the assembly module
- renamed internal gateway-facing auth and route symbols to neutral ops language:
  - `_load_studio_api_keys` -> `_load_ops_api_keys`
  - `_require_studio_auth` -> `_require_ops_auth`
  - route handlers such as `list_studio_models(...)` -> `list_ops_models(...)`
- rewired gateway composition and tests:
  - `src/apps/agent_studio_gateway/main.py`
  - `tests/test_agent_studio_gateway_ops_router.py`
  - `tests/test_agent_studio_gateway_api_v1.py`
- updated active docs that point at the maintained gateway ops route file:
  - `docs/RUNTIME_FLOW.md`
  - `docs/DEVELOPMENT_INDEX.md`
  - `docs/FRAMEWORK_SKELETON.md`
- verification:
  - `uv run pytest tests/test_operations_use_cases.py tests/test_agent_studio_gateway_ops_router.py tests/test_agent_studio_gateway_api_v1.py tests/test_channel_ingress_use_cases.py tests/test_novel_service_use_cases.py -q`
  - result: `42 passed`
  - `uv run ruff check src/mini_agent/application src/mini_agent/session src/mini_agent/novel src/apps/agent_studio_gateway tests/test_operations_use_cases.py tests/test_agent_studio_gateway_ops_router.py tests/test_agent_studio_gateway_api_v1.py tests/test_channel_ingress_use_cases.py tests/test_novel_service_use_cases.py`
  - result: all green
- architectural outcome:
  - the gateway transport layer no longer carries a paused `Studio` frontend name as if that were the owner of `/api/v1/ops`

### P32.16 landed

- unified the gateway ops transport with the maintained dependency-injected router-factory pattern:
  - `src/apps/agent_studio_gateway/ops_router.py` now exports:
    - `OpsRouterDependencies`
    - `create_ops_router(...)`
- moved host-owned ops service construction explicitly into `src/apps/agent_studio_gateway/main.py`:
  - added `GATEWAY_OPERATIONS_USE_CASES = OperationsUseCases(...)`
  - `main.py` now mounts `create_ops_router(...)` with injected dependencies
- updated:
  - `src/apps/agent_studio_gateway/main.py`
  - `src/apps/agent_studio_gateway/ops_router.py`
  - `tests/test_agent_studio_gateway_ops_router.py`
  - `tests/test_agent_studio_gateway_api_v1.py`
- verification:
  - `uv run pytest tests/test_agent_studio_gateway_ops_router.py tests/test_agent_studio_gateway_api_v1.py tests/test_agent_studio_gateway_integration_flows.py tests/test_p19_runtime_matrix.py -q`
  - result: `35 passed`
  - `uv run ruff check src/apps/agent_studio_gateway/main.py src/apps/agent_studio_gateway/ops_router.py tests/test_agent_studio_gateway_ops_router.py tests/test_agent_studio_gateway_api_v1.py`
  - result: all green
  - `git diff --check -- src/apps/agent_studio_gateway/main.py src/apps/agent_studio_gateway/ops_router.py tests/test_agent_studio_gateway_ops_router.py tests/test_agent_studio_gateway_api_v1.py`
  - result: passed
- architectural outcome:
  - the gateway transport layer now uses one consistent DI/factory pattern across `main_agent_router.py` and `ops_router.py`
  - `main.py` keeps host-level assembly ownership instead of hiding transport-local service singletons

### P32.17 landed

- closed the next layer of agent-core naming drift after the initial tree move:
  - `src/mini_agent/agent_core/self_improve.py` -> `src/mini_agent/agent_core/skills/self_improve.py`
- aligned maintained execution API naming with the new ownership:
  - `CodeAgentMCPClient` -> `ExecutionMCPClient`
- renamed execution-focused tests so the current suite no longer advertises the removed `code_agent` package as a live owner:
  - `tests/test_code_agent_loop.py` -> `tests/test_agent_core_execution_loop.py`
  - `tests/test_code_agent_sandbox.py` -> `tests/test_agent_core_execution_sandbox.py`
  - `tests/test_code_agent_tools.py` -> `tests/test_agent_core_execution_tools.py`
  - `tests/test_code_agent_coordinator.py` -> `tests/test_agent_core_execution_coordinator.py`
  - `tests/test_code_agent_context_compaction.py` -> `tests/test_agent_core_context_compaction.py`
  - `tests/test_code_agent_mcp_client.py` -> `tests/test_agent_core_execution_mcp_client.py`
  - `tests/test_code_agent_minimal_workflow.py` -> `tests/test_agent_core_execution_minimal_workflow.py`
  - `tests/test_code_agent_permissions.py` -> `tests/test_agent_core_execution_permissions.py`
  - `tests/test_self_improve.py` -> `tests/test_agent_core_skills_self_improve.py`
- updated active docs and readiness tooling to current ownership paths
- verification:
  - `uv run pytest tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_sandbox.py tests/test_agent_core_execution_tools.py tests/test_agent_core_execution_coordinator.py tests/test_agent_core_context_compaction.py tests/test_agent_core_execution_mcp_client.py tests/test_agent_core_execution_minimal_workflow.py tests/test_agent_core_execution_permissions.py tests/test_agent_core_skills_self_improve.py tests/test_agent_core_kernel.py tests/test_terminal_readiness_gate.py -q`
  - result: `73 passed`
  - `uv run ruff check src/mini_agent/agent_core src/mini_agent/__init__.py scripts/terminal_readiness_gate.py tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_sandbox.py tests/test_agent_core_execution_tools.py tests/test_agent_core_execution_coordinator.py tests/test_agent_core_context_compaction.py tests/test_agent_core_execution_mcp_client.py tests/test_agent_core_execution_minimal_workflow.py tests/test_agent_core_execution_permissions.py tests/test_agent_core_skills_self_improve.py tests/test_agent_core_kernel.py`
  - result: all green
- architectural outcome:
  - `agent_core` now teaches a more consistent ownership model across source tree, exported APIs, and current regression surfaces

### P32.18 landed

- aligned the remaining engine-facing regression surfaces with the canonical `agent_core` tree:
  - `tests/test_agent.py` -> `tests/test_agent_core_engine_live.py`
  - `tests/test_agent_turn_context.py` -> `tests/test_agent_core_turn_context.py`
  - `tests/test_agent_execution_policy.py` -> `tests/test_agent_core_execution_policy.py`
- updated current docs and validation references to the new test names
- also synchronized current source-path references to:
  - `src/mini_agent/agent_core/engine.py`
  - `src/mini_agent/agent_core/context/turn_context.py`
- verification:
  - `uv run pytest tests/test_agent_core_turn_context.py tests/test_agent_core_execution_policy.py tests/test_agent_core_engine_live.py tests/test_agent_core_kernel.py -q`
  - result: `45 passed, 2 skipped`
  - `uv run ruff check tests/test_agent_core_turn_context.py tests/test_agent_core_execution_policy.py tests/test_agent_core_engine_live.py tests/test_agent_core_kernel.py`
  - result: all green
- architectural outcome:
  - the current high-signal regression entrypoints now reinforce the same `agent_core` ownership story as the source tree itself

### P32.47 landed

- audited the next real cross-surface ownership leak after `/model`:
  - runtime-policy mutation semantics were still split between:
    - `src/mini_agent/runtime/session_runtime_policy_handler.py`
    - `src/mini_agent/tui/app.py`
- the duplicated business logic was:
  - normalizing requested `approval_profile/access_level`
  - preferring attached-agent effective policy over stale diagnostics
  - rejecting updates while busy unless the session is waiting on approval
  - synthesizing local sandbox diagnostics when no live agent is attached
- added one shared owner:
  - `src/mini_agent/runtime/runtime_policy_service.py`
- removed the old runtime-only path:
  - `src/mini_agent/runtime/session_runtime_policy_handler.py`
- rewired:
  - `src/mini_agent/runtime/main_agent_runtime_manager.py`
  - `src/mini_agent/runtime/session_operator_handler.py`
  - `src/mini_agent/runtime/session_agent_runtime_handler.py`
  - `src/mini_agent/tui/app.py`
- added focused regression coverage:
  - `tests/test_tui_app.py::test_tui_runtime_policy_prefers_attached_agent_effective_policy`
- verification:
  - `uv run ruff check src/mini_agent/runtime/runtime_policy_service.py src/mini_agent/runtime/main_agent_runtime_manager.py src/mini_agent/runtime/session_operator_handler.py src/mini_agent/runtime/session_agent_runtime_handler.py src/mini_agent/tui/app.py tests/test_tui_app.py tests/test_main_agent_surface_service.py`
  - result: all green
  - `uv run pytest tests/test_tui_app.py tests/test_main_agent_surface_service.py -q`
  - result: `193 passed`
- architectural outcome:
  - runtime-policy semantics now have one honest shared owner
  - TUI no longer carries a second local runtime-policy state machine
  - attached local sessions now read effective policy from the live agent before falling back to cached diagnostics

### P32.48 landed

- audited the next cross-surface ownership leak after runtime-policy:
  - session KB toggle semantics were still duplicated between:
    - `src/mini_agent/commands/execution.py`
    - `src/mini_agent/runtime/session_agent_control_handler.py`
- the duplicated business logic was:
  - current enabled/disabled state normalization
  - applied vs already-enabled/already-disabled decisions
  - KB control transcript summary/details
- added one shared owner:
  - `src/mini_agent/tools/knowledge_base_control_service.py`
- rewired:
  - `src/mini_agent/commands/execution.py`
  - `src/mini_agent/runtime/session_agent_control_handler.py`
- added focused regression coverage:
  - `tests/test_runtime_session_agent_control_handler.py::test_agent_control_handler_reports_knowledge_base_already_disabled`
  - `tests/test_command_execution_service.py::test_local_operator_command_service_reports_kb_already_disabled`
- verification:
  - `uv run ruff check src/mini_agent/tools/knowledge_base_control_service.py src/mini_agent/commands/execution.py src/mini_agent/runtime/session_agent_control_handler.py tests/test_command_execution_service.py tests/test_runtime_session_agent_control_handler.py tests/test_tui_app.py tests/test_main_agent_surface_service.py tests/test_cli_submission_loop.py`
  - result: all green
  - `uv run pytest tests/test_command_execution_service.py tests/test_runtime_session_agent_control_handler.py tests/test_tui_app.py tests/test_main_agent_surface_service.py tests/test_cli_submission_loop.py -q`
  - result: `236 passed`
- architectural outcome:
  - KB session-control semantics now have one explicit owner
  - local command surfaces and runtime session controls are back to adapter roles

### P32.49 landed

- audited the next cross-surface ownership leak after `/kb`:
  - pending-approval token resolution and decision formatting were still split between:
    - `src/mini_agent/runtime/session_interrupt_handler.py`
    - `src/mini_agent/tui/app.py`
- the duplicated business logic was:
  - selecting a target approval by token
  - reporting `token not found` / `token required` / `restart pending` cases
  - formatting approve/deny command, summary, and transcript detail payloads
- added one shared owner:
  - `src/mini_agent/runtime/session_pending_approval_service.py`
- rewired:
  - `src/mini_agent/runtime/session_interrupt_handler.py`
  - `src/mini_agent/tui/app.py`
- added focused regression coverage:
  - `tests/test_tui_app.py::test_tui_local_approve_multiple_pending_requires_token`
- verification:
  - `uv run ruff check src/mini_agent/runtime/session_pending_approval_service.py src/mini_agent/runtime/session_interrupt_handler.py src/mini_agent/tui/app.py tests/test_tui_app.py tests/test_main_agent_surface_service.py`
  - result: all green
  - `uv run pytest tests/test_tui_app.py tests/test_main_agent_surface_service.py -q`
  - result: `194 passed`
- architectural outcome:
  - pending-approval token resolution now has one owner
  - local TUI and shared runtime no longer teach two different approval-selection state machines

### P32.50 landed

- audited `/cancel` after the previous deeper extractions and found a different shape than `/model` or approvals:
  - concrete interrupt mechanisms still legitimately differ between:
    - local TUI submission-loop interruption
    - managed runtime cancel-event interruption
- instead of forcing those execution paths into one fake abstraction, extracted the shared cancel semantics only:
  - added `src/mini_agent/runtime/session_cancel_service.py`
- rewired:
  - `src/mini_agent/runtime/session_interrupt_handler.py`
  - `src/mini_agent/tui/app.py`
- unified:
  - `cancellation requested` state/summary labels
  - transcript detail text for cancel commands
  - canonical runtime `no running turn` / `not cancellable` details
  - user-facing local `No running turn to cancel.` message source
- verification:
  - `uv run ruff check src/mini_agent/runtime/session_cancel_service.py src/mini_agent/runtime/session_interrupt_handler.py src/mini_agent/tui/app.py tests/test_tui_app.py tests/test_main_agent_surface_service.py tests/test_agent_studio_gateway_api_v1.py`
  - result: all green
  - `uv run pytest tests/test_tui_app.py tests/test_main_agent_surface_service.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `215 passed`
- architectural outcome:
  - cancel flows now share one semantic source without flattening the real distinction between local and managed interruption mechanisms

### P32.51 landed

- audited the next high-value multi-surface duplication after `/cancel`:
  - `compact/drop_memories` result normalization and formatting were duplicated across:
    - `src/mini_agent/runtime/session_agent_control_handler.py`
    - `src/mini_agent/tui/app.py`
    - `src/mini_agent/cli_interactive.py`
- the duplicated business logic was:
  - normalizing raw control payloads into applied/message/token/stats fields
  - generating shared summary/details text
  - generating surface-friendly success labels from the same result
- added one shared owner:
  - `src/mini_agent/agent_core/context/control_result_service.py`
- rewired:
  - `src/mini_agent/runtime/session_agent_control_handler.py`
  - `src/mini_agent/tui/app.py`
  - `src/mini_agent/cli_interactive.py`
- verification:
  - `uv run ruff check src/mini_agent/agent_core/context/control_result_service.py src/mini_agent/runtime/session_agent_control_handler.py src/mini_agent/tui/app.py src/mini_agent/cli_interactive.py tests/test_runtime_session_agent_control_handler.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_surface_service.py`
  - result: all green
  - `uv run pytest tests/test_runtime_session_agent_control_handler.py tests/test_tui_app.py tests/test_cli_submission_loop.py tests/test_main_agent_surface_service.py -q`
  - result: `221 passed`
- architectural outcome:
  - context-control result semantics now have one explicit owner
  - runtime, TUI local, and CLI interactive no longer teach three different formatting rules for the same control outcomes

### P32.52 landed

- audited the remaining remote session-control leak still sitting in `src/mini_agent/tui/app.py`:
  - TUI was still parsing raw gateway exception strings and locally re-teaching:
    - remote control busy mapping
    - remote approval failure summaries/status text
    - remote cancel idle detection
    - gateway `HTTP xxx:` detail extraction
- split that ownership back to the honest layers:
  - added transport-side gateway error normalization:
    - `src/mini_agent/transport/gateway_error.py`
  - added shared control-command busy/error semantics:
    - `src/mini_agent/runtime/session_control_error_service.py`
  - expanded pending-approval semantics to own their remote error labeling too:
    - `src/mini_agent/runtime/session_pending_approval_service.py`
  - expanded cancel semantics to recognize canonical idle-cancel detail:
    - `src/mini_agent/runtime/session_cancel_service.py`
- rewired:
  - `src/mini_agent/transport/gateway_client.py`
  - `src/mini_agent/transport/__init__.py`
  - `src/mini_agent/runtime/session_agent_control_handler.py`
  - `src/mini_agent/runtime/session_operator_handler.py`
  - `src/mini_agent/tools/mcp/command_service.py`
  - `src/mini_agent/tui/app.py`
- added focused regression coverage:
  - `tests/test_transport_gateway_error.py`
  - `tests/test_runtime_session_error_services.py`
  - `tests/test_tui_app.py::test_tui_remote_cancel_when_idle_uses_shared_cancel_detail`
- verification:
  - `uv run ruff check src/mini_agent/transport/gateway_error.py src/mini_agent/transport/gateway_client.py src/mini_agent/transport/__init__.py src/mini_agent/runtime/session_control_error_service.py src/mini_agent/runtime/session_agent_control_handler.py src/mini_agent/runtime/session_operator_handler.py src/mini_agent/runtime/session_pending_approval_service.py src/mini_agent/runtime/session_cancel_service.py src/mini_agent/tools/mcp/command_service.py src/mini_agent/tui/app.py tests/test_transport_gateway_error.py tests/test_runtime_session_error_services.py tests/test_tui_app.py`
  - result: all green
  - `uv run pytest tests/test_transport_gateway_error.py tests/test_runtime_session_error_services.py tests/test_tui_app.py tests/test_transport_gateway_client.py tests/test_main_agent_surface_service.py tests/test_runtime_session_agent_control_handler.py tests/test_runtime_session_mcp_control_handler.py -q`
  - result: `220 passed`
- architectural outcome:
  - transport now owns remote gateway failure normalization instead of TUI regex parsing
  - remote control/approval/cancel semantic mapping is now owned by the domain services that already own those concepts
  - TUI is back to assembling feedback/status from shared results instead of translating gateway protocol strings on its own

### P32.53 landed

- audited the next remote-surface drift after P32.52:
  - remote stream failures and desktop approval failures were still inconsistent with the new shared error semantics
  - desktop still leaked raw gateway exception strings across health/model/session/model-switch flows
  - TUI still had a few remaining remote command branches concatenating raw exceptions directly
- added one shared owner for stream-failure normalization:
  - `src/mini_agent/transport/remote_stream_error_service.py`
- rewired remote stream consumers to the shared service:
  - `src/mini_agent/tui/app.py`
  - `src/mini_agent/desktop/window.py`
- aligned desktop approval failures with existing shared owners instead of desktop-local wording:
  - `src/mini_agent/runtime/session_pending_approval_service.py`
  - `src/mini_agent/transport/gateway_error.py`
  - `src/mini_agent/desktop/window.py`
- normalized remaining remote exception display in desktop/TUI to use extracted gateway detail instead of raw `Gateway HTTP ...` text:
  - `src/mini_agent/desktop/window.py`
  - `src/mini_agent/tui/app.py`
- added focused regression coverage:
  - `tests/test_transport_remote_stream_error_service.py`
  - `tests/test_desktop_window_helpers.py::test_desktop_error_detail_uses_gateway_detail_without_http_prefix`
  - `tests/test_desktop_window_helpers.py::test_format_desktop_approval_failure_uses_shared_pending_approval_semantics`
  - `tests/test_tui_app.py::test_tui_remote_stream_exception_uses_normalized_detail`
- verification:
  - `uv run ruff check src/mini_agent/transport/remote_stream_error_service.py src/mini_agent/transport/__init__.py src/mini_agent/desktop/window.py src/mini_agent/tui/app.py tests/test_transport_remote_stream_error_service.py tests/test_desktop_window_helpers.py tests/test_tui_app.py`
  - result: all green
  - `uv run pytest tests/test_transport_remote_stream_error_service.py tests/test_desktop_window_helpers.py tests/test_tui_app.py tests/test_transport_gateway_error.py tests/test_runtime_session_error_services.py -q`
  - result: `139 passed`
- architectural outcome:
  - remote stream protocol failures now have one shared normalization path across TUI/Desktop
  - desktop approval failures now speak the same pending-approval semantics as TUI/runtime
  - desktop and remaining remote TUI flows no longer leak transport-level `Gateway HTTP ...` prefixes to users

### P32.54 landed

- audited the next user-facing drift after remote error normalization:
  - session mutation success feedback (`share/unshare/rename/delete/reset`) was still being hand-written in each surface
  - `TUI` and `desktop` were both formatting the same mutation outcomes separately
- added one shared session feedback owner:
  - `src/mini_agent/session/feedback_service.py`
- exported it from the session package:
  - `src/mini_agent/session/__init__.py`
- rewired surfaces to the shared mutation feedback semantics:
  - `src/mini_agent/tui/app.py`
  - `src/mini_agent/desktop/window.py`
- unified:
  - share success text
  - unshare success text
  - rename success text
  - delete success text
  - remote reset success text
- added focused regression coverage:
  - `tests/test_session_feedback_service.py`
- verification:
  - `uv run ruff check src/mini_agent/session/feedback_service.py src/mini_agent/session/__init__.py src/mini_agent/tui/app.py src/mini_agent/desktop/window.py tests/test_session_feedback_service.py tests/test_tui_app.py tests/test_desktop_window_helpers.py`
  - result: all green
  - `uv run pytest tests/test_session_feedback_service.py tests/test_tui_app.py tests/test_desktop_window_helpers.py -q`
  - result: `134 passed`
- architectural outcome:
  - session mutation feedback now has one explicit shared owner
  - `TUI` and `desktop` no longer teach separate success wording for the same share/rename/delete/reset outcomes

### P32.55 landed

- audited the next repeated feedback slice after session mutation feedback:
  - session-scoped model selection success states were still hand-formatted in `TUI` and `desktop`
  - the actual selection semantics already belonged to `src/mini_agent/model_manager/session_selection_service.py`
- extended the existing honest owner instead of adding another shell:
  - `src/mini_agent/model_manager/session_selection_service.py`
- added shared feedback semantics for:
  - queued model selection
  - applied model selection
  - already-selected model selection
  - already-queued model selection
- rewired:
  - `src/mini_agent/tui/app.py`
  - `src/mini_agent/desktop/window.py`
- added focused regression coverage:
  - `tests/test_session_model_selection_service.py`
- verification:
  - `uv run ruff check src/mini_agent/model_manager/session_selection_service.py src/mini_agent/tui/app.py src/mini_agent/desktop/window.py tests/test_session_model_selection_service.py tests/test_tui_app.py tests/test_desktop_window_helpers.py`
  - result: all green
  - `uv run pytest tests/test_session_model_selection_service.py tests/test_tui_app.py tests/test_desktop_window_helpers.py -q`
  - result: `134 passed`
- architectural outcome:
  - model-selection feedback is now owned by the same service that already owns model-selection state transitions
  - `TUI` and `desktop` no longer maintain separate success wording for queued/applied model selection outcomes

### P32.56 landed

- audited the next remaining surface-level wording drift after model-selection feedback cleanup:
  - `session create/fork` success text was still being hand-written separately in `TUI` and `desktop`
  - `TUI` still had a few session mutation failure branches leaking raw exception text instead of normalized gateway detail
- broadened the shared session feedback owner instead of introducing another wrapper:
  - `src/mini_agent/session/feedback_service.py`
- tightened the public session package export to the broader feedback concept:
  - `src/mini_agent/session/__init__.py`
- rewired shared session creation/fork feedback into both interactive surfaces:
  - `src/mini_agent/tui/app.py`
  - `src/mini_agent/desktop/window.py`
- unified:
  - root session creation success text
  - derived session creation success text
  - explicit fork success text
- normalized remaining TUI session command failures to extracted gateway detail:
  - create
  - fork
  - share
  - unshare
  - rename
  - delete
- added focused regression coverage:
  - `tests/test_session_feedback_service.py`
  - `tests/test_tui_app.py::test_tui_session_new_uses_shared_creation_feedback`
  - `tests/test_tui_app.py::test_tui_session_new_failure_uses_normalized_gateway_detail`
  - `tests/test_tui_app.py::test_tui_fork_failure_uses_normalized_gateway_detail`
- verification:
  - `uv run ruff check src/mini_agent/session/feedback_service.py src/mini_agent/session/__init__.py src/mini_agent/tui/app.py src/mini_agent/desktop/window.py tests/test_session_feedback_service.py tests/test_tui_app.py`
  - result: all green
  - `uv run pytest tests/test_session_feedback_service.py tests/test_tui_app.py tests/test_desktop_window_helpers.py -q`
  - result: `139 passed`
- architectural outcome:
  - session success/failure wording is now more consistently owned by shared semantic services instead of surface-local strings
  - `TUI` no longer leaks raw gateway transport prefixes in the remaining session command failure branches

### P32.57 landed

- audited the next real cross-surface drift after `P32.56`:
  - local `skill` mutation execution already shared one owner in `src/mini_agent/commands/execution.py`
  - but the follow-up runtime-reload semantics still lived in two surfaces:
    - `src/mini_agent/cli_interactive.py`
    - `src/mini_agent/tui/app.py`
  - the duplicated ownership included:
    - mutation -> busy summary mapping
    - mutation -> warm reload prefix mapping
    - mutation -> CLI reload success/failure messaging
- added one shared owner under the real skill boundary:
  - `src/mini_agent/agent_core/skills/runtime_feedback.py`
- rewired:
  - `src/mini_agent/cli_interactive.py`
  - `src/mini_agent/tui/app.py`
- added focused regression coverage:
  - `tests/test_agent_core_skills_runtime_feedback.py`
- verification:
  - `uv run ruff check src/mini_agent/agent_core/skills/runtime_feedback.py src/mini_agent/cli_interactive.py src/mini_agent/tui/app.py tests/test_agent_core_skills_runtime_feedback.py`
  - result: all green
  - `uv run pytest tests/test_agent_core_skills_runtime_feedback.py tests/test_cli_submission_loop.py tests/test_tui_app.py -q`
  - result: `161 passed`
- architectural outcome:
  - local skill mutation result semantics still belong to `commands/execution.py`
  - runtime-reload feedback semantics now also have one honest owner under `agent_core.skills`
  - `CLI` and `TUI` keep only their execution mechanics instead of re-teaching mutation -> reload descriptor mappings

### P32.58 landed

- audited the next adjacent but smaller seam after `P32.57`:
  - local `mcp reload` execution/result semantics were already owned by `src/mini_agent/tools/mcp/command_service.py`
  - but the remaining local runtime-rebuild feedback still leaked into surfaces:
    - `src/mini_agent/cli_interactive.py`
    - `src/mini_agent/tui/app.py`
- kept this as a thin correction instead of introducing a new large abstraction:
  - extended `src/mini_agent/tools/mcp/command_service.py`
  - added shared helpers for:
    - CLI local reload success wording
    - local warm-reload prefix generation
- rewired:
  - `src/mini_agent/cli_interactive.py`
  - `src/mini_agent/tui/app.py`
- added focused regression coverage:
  - `tests/test_mcp_command_service_feedback.py`
- verification:
  - `uv run ruff check src/mini_agent/tools/mcp/command_service.py src/mini_agent/cli_interactive.py src/mini_agent/tui/app.py tests/test_mcp_command_service_feedback.py`
  - result: all green
  - `uv run pytest tests/test_mcp_command_service_feedback.py tests/test_cli_submission_loop.py tests/test_tui_app.py tests/test_command_execution_service.py -q`
  - result: `183 passed`
- architectural outcome:
  - MCP operator semantics remain centered under `tools.mcp`
  - the remaining local reload feedback fragments are no longer owned by `CLI` / `TUI`
  - this slice intentionally stopped at the honest shared seam instead of over-extracting

### P32.59 landed

- audited the next cross-surface semantic leak after `P32.58`:
  - runtime-policy planning and execution already lived under:
    - `src/mini_agent/runtime/runtime_policy_service.py`
  - but the user-facing feedback still leaked across surfaces:
    - `src/mini_agent/tui/app.py` handwrote unchanged / failed / updated runtime-policy feedback
    - `src/apps/qqbot_channel/bot.mjs` handwrote shared-session runtime-policy success text
- extended the existing honest owner instead of adding another wrapper:
  - updated `src/mini_agent/runtime/runtime_policy_service.py`
  - added shared feedback helpers for:
    - updated summary/details/status text
    - unchanged summary/details/status text
    - failure summary/details/status text
- carried the shared feedback through the shared response contract:
  - updated `src/mini_agent/interfaces/agent.py`
  - updated `src/mini_agent/runtime/session_operator_handler.py`
- rewired:
  - `src/mini_agent/tui/app.py`
  - `src/apps/qqbot_channel/bot.mjs`
- added focused regression coverage:
  - `tests/test_runtime_policy_service.py`
  - updated `tests/test_tui_app.py`
  - updated `tests/test_main_agent_surface_service.py`
- verification:
  - `uv run ruff check src/mini_agent/runtime/runtime_policy_service.py src/mini_agent/runtime/session_operator_handler.py src/mini_agent/interfaces/agent.py src/mini_agent/tui/app.py tests/test_runtime_policy_service.py tests/test_tui_app.py tests/test_main_agent_surface_service.py`
  - result: all green
  - `uv run pytest tests/test_runtime_policy_service.py tests/test_tui_app.py tests/test_main_agent_surface_service.py tests/test_agent_studio_gateway_api_v1.py -q`
  - result: `234 passed`
- architectural outcome:
  - runtime-policy execution and runtime-policy feedback now share one honest owner
  - shared runtime-policy responses now export `summary / details / status_text`
  - the active `QQ` adapter is thinner because it can prefer shared response details
  - `TUI` correctly keeps local status-bar title ownership instead of reusing remote transport naming
