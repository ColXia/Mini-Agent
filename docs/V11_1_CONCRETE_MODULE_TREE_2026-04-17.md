# Mini-Agent v11.1 Concrete Module Tree

> Status: discussion baseline
> Date: 2026-04-17
> Scope: concrete target tree / first-batch modules / file-level ownership / transitional module mapping
> Related:
> - [V11_1_MODULE_OWNERSHIP_AND_MIGRATION_DIRECTION_2026-04-17.md](./V11_1_MODULE_OWNERSHIP_AND_MIGRATION_DIRECTION_2026-04-17.md)
> - [V11_1_USER_SERVICE_TO_KERNEL_INTERFACE_DESIGN_2026-04-17.md](./V11_1_USER_SERVICE_TO_KERNEL_INTERFACE_DESIGN_2026-04-17.md)
> - [V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md](./V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md)
> - [V11_1_TRANSPORT_DTO_AND_READ_MODEL_CONTRACT_2026-04-17.md](./V11_1_TRANSPORT_DTO_AND_READ_MODEL_CONTRACT_2026-04-17.md)
> - [V11_1_ARCHITECTURE_MIGRATION_EXECUTION_ORDER_2026-04-17.md](./V11_1_ARCHITECTURE_MIGRATION_EXECUTION_ORDER_2026-04-17.md)
> - [FRAMEWORK_SKELETON.md](./FRAMEWORK_SKELETON.md)

## 1. Purpose

This document freezes the `v11.1` concrete module tree.

It answers one practical question:

- if the corrected `v11.1` architecture is real, what exact directories and files should later implementation land in

This document is not a mass-rewrite instruction.
It is the concrete landing map for future code changes.

## 2. Design Rule

The concrete tree is split into two layers:

- `Target Tree`
- `First-Batch Tree`

Why:

- the target tree shows the long-term ownership shape
- the first-batch tree shows what Stage 1-3 migration is actually allowed to create next

This avoids two failure modes:

- pretending the whole repo must be moved immediately
- or staying so abstract that new code still lands in the wrong files

## 3. Top-Level Target Tree

The maintained top-level target tree under `src/mini_agent/` should be:

```text
agent_core/
application/
commands/
desktop/
interfaces/
memory/
model_manager/
ops/
rag/
runtime/
session/
skills/
tools/
transport/
tui/
workspace_runtime/
```

Notes:

- `workspace_runtime/` is a new target module and should become real
- existing unrelated folders may remain in the repo
- this tree only names the architecture-critical ownership lines

## 4. `agent_core/` Concrete Target Tree

Recommended concrete target shape:

```text
agent_core/
  __init__.py
  engine.py
  kernel.py
  runtime_bindings.py
  contracts/
    __init__.py
    agent_profile.py
    agent_instance.py
    run.py
    attachments.py
    capability_snapshot.py
    checkpoint.py
    execution_journal.py
    run_control_state.py
    approval_wait.py
  execution/
  context/
  history/
  session/
  skills/
  presentation.py
  post_turn.py
```

Meaning:

- existing maintained seams stay where they are
- new kernel-truth objects should stop being invented ad hoc in unrelated runtime files
- future `AgentInstance / Run / RunControl / ApprovalWait / Checkpoint / Journal` work should land in `agent_core/contracts/`

## 5. `application/` Concrete Target Tree

Recommended concrete target shape:

```text
application/
  __init__.py
  facades/
    __init__.py
    main_agent_surface_service.py
  user_services/
    __init__.py
    agent_user_service.py
    workspace_user_service.py
    model_user_service.py
    command_user_service.py
  use_cases/
    __init__.py
    agent_application_service.py
    run_control_application_service.py
    session_task_service.py
    workspace_application_service.py
    model_binding_application_service.py
    command_application_service.py
  ports/
    __init__.py
    agent_runtime_port.py
    run_runtime_port.py
    workspace_runtime_port.py
    model_runtime_port.py
    session_task_port.py
    session_runtime_port.py
  support/
    __init__.py
    interaction_request_adapter.py
    managed_session_turn.py
    surface_service_types.py
  legacy/
    __init__.py
    session_service.py
```

Meaning:

- `main_agent_surface_service.py` remains useful, but should conceptually become a facade
- `session_service.py` remains useful, but should conceptually become a legacy/transitional session-task carrier
- new user-facing entry modules should stop landing flat in `application/`

Important:

- the repo does not need to physically move all existing files at once
- but new files should follow this ownership line

## 6. `runtime/` Concrete Target Tree

Recommended concrete target shape:

```text
runtime/
  __init__.py
  main_agent_runtime_manager.py
  orchestration/
    __init__.py
    session_runtime_lifecycle_handler.py
    session_hydration_coordinator.py
    session_restore_handler.py
    session_runtime_policy_coordinator.py
  live_control/
    __init__.py
    session_interrupt_handler.py
    session_pending_approval_state_handler.py
    session_pending_approval_service.py
    session_cancel_service.py
    session_live_state_handler.py
  read_models/
    __init__.py
    session_read_model_builder.py
    session_snapshot_builder.py
    session_payload_codec.py
    session_model_identity_codec.py
  handlers/
    __init__.py
    session_access_handler.py
    session_admin_handler.py
    session_agent_control_handler.py
    session_agent_runtime_handler.py
    session_catalog_handler.py
    session_creation_handler.py
    session_memory_command_handler.py
    session_mcp_control_handler.py
    session_operator_handler.py
    session_registry_handler.py
  support/
    __init__.py
    tooling.py
    sandbox_state.py
    workspace_path_utils.py
    interaction_surface.py
```

Meaning:

- `runtime/` remains runtime-host orchestration land
- the flat runtime tree can remain temporarily
- but future moves should align toward `orchestration / live_control / read_models / handlers / support`

## 7. `session/` Concrete Target Tree

Recommended concrete target shape:

```text
session/
  __init__.py
  projections.py
  persistence.py
  store_records.py
  lineage.py
  recovery_feedback.py
  bindings.py
```

Meaning:

- `session/` owns task truth and task read models
- it should not absorb run control or main model binding

## 8. `workspace_runtime/` Concrete Target Tree

Recommended concrete target shape:

```text
workspace_runtime/
  __init__.py
  boundary.py
  runtime_modes.py
  workspace_executor.py
  outside_zone_policy.py
  permission_table.py
  mutation_ledger.py
  snapshot_store.py
  adapters/
    __init__.py
    direct_executor.py
    container_mounted_executor.py
    isolated_copy_executor.py
```

Meaning:

- this is the physical home for workspace-bound execution world ownership
- do not continue scattering workspace execution semantics across unrelated runtime helpers forever

## 9. `model_manager/` Concrete Target Tree

Recommended concrete target shape:

```text
model_manager/
  __init__.py
  registry/
  runtime/
  providers/
  discovery/
  capabilities/
  bindings/
```

Meaning:

- main model binding and capability facts stay here
- they do not move into session, runtime live control, or workspace runtime

## 10. `interfaces/` Concrete Target Tree

Recommended concrete target shape:

```text
interfaces/
  __init__.py
  common.py
  system.py
  agent.py
  session.py
  run.py
  workspace.py
  model.py
  channel.py
  ops.py
  novel.py
```

Interpretation:

- current flat DTO layout is fine
- future DTO families should expand beyond session-only worldview
- DTOs remain transport-facing types, not truth owners

## 11. `transport/` Concrete Target Tree

Recommended concrete target shape:

```text
transport/
  __init__.py
  gateway_client.py
  gateway_error.py
  remote_session_client.py
  remote_stream_error_service.py
  session_transport_port.py
  clients/
    __init__.py
    remote_agent_client.py
    remote_workspace_client.py
    remote_model_client.py
  support/
    __init__.py
    response_normalizer.py
    stream_payloads.py
```

Meaning:

- low-level transport ports may still exchange raw payload maps
- typed DTO normalization should happen quickly in transport clients

## 12. `commands/` Concrete Target Tree

Recommended concrete target shape:

```text
commands/
  __init__.py
  catalog.py
  parser.py
  execution.py
  metadata.py
  completions.py
```

Meaning:

- command grammar and metadata stay shared
- do not bury shared command semantics inside TUI, Desktop, or Remote

## 13. First-Batch Tree

The following is the first-batch concrete tree for Stage 1-3.

This is the set of new module lines that can be created next without causing a fake big-bang rewrite.

```text
agent_core/
  contracts/
    __init__.py
    run_control_state.py
    approval_wait.py

application/
  user_services/
    __init__.py
    agent_user_service.py
    workspace_user_service.py
    model_user_service.py
    command_user_service.py
  use_cases/
    __init__.py
    run_control_application_service.py
  ports/
    __init__.py
    agent_runtime_port.py
    run_runtime_port.py
    workspace_runtime_port.py
    model_runtime_port.py
    session_task_port.py

workspace_runtime/
  __init__.py
  boundary.py
  mutation_ledger.py
  outside_zone_policy.py
```

Why this first batch:

- it matches Stage 1-3 migration order
- it gives run-control truth a landing zone
- it gives user services real file owners
- it creates the first real `workspace_runtime/` foothold
- it does not force immediate mass moves of working files

## 14. First-Batch File Responsibilities

`agent_core/contracts/run_control_state.py`

- durable run-owned control state model
- no session projection logic
- no asyncio/event-loop bridge logic

`agent_core/contracts/approval_wait.py`

- durable approval wait object
- no session UI projection logic
- no transport DTO logic

`application/user_services/agent_user_service.py`

- user-facing agent operations
- active run entry and run control entrypoints
- may orchestrate compatibility session lookup

`application/user_services/workspace_user_service.py`

- user-facing workspace summary and switching entrypoints
- no run control truth

`application/user_services/model_user_service.py`

- user-facing main model binding and capability display
- no session-owned main model truth

`application/user_services/command_user_service.py`

- command entry, dispatch, completion, description
- no runtime truth ownership

`application/use_cases/run_control_application_service.py`

- interrupt / resume / cancel / approve / deny use cases
- resolves control targets against run truth

`application/ports/agent_runtime_port.py`

- agent instance and agent summary runtime-facing contract

`application/ports/run_runtime_port.py`

- run query and run control runtime-facing contract

`application/ports/workspace_runtime_port.py`

- workspace environment and workspace-runtime summary contract

`application/ports/model_runtime_port.py`

- main model binding and capability contract

`application/ports/session_task_port.py`

- session task query and task-resolution contract

`workspace_runtime/boundary.py`

- workspace root and boundary rules

`workspace_runtime/mutation_ledger.py`

- mutable side-effect ledger contract

`workspace_runtime/outside_zone_policy.py`

- out-of-workspace read/write/delete policy baseline

## 15. Transitional Mapping For Existing Files

Current files should map to the target tree like this:

`application/main_agent_surface_service.py`

- keep as transitional facade
- do not keep expanding it as the permanent home of user-side logic

`application/session_service.py`

- keep as transitional session-task service
- stop adding clearly agent-owned, model-owned, or run-control-owned logic to it

`application/session_runtime_port.py`

- keep as transitional task/session runtime seam
- do not treat it as the final runtime-port family

`runtime/main_agent_runtime_manager.py`

- keep as orchestration anchor
- do not use file size as a reason for blind splitting
- do use new ports and truth objects to prevent re-expansion

## 16. What Should Not Be Created Yet

To avoid fake progress, the following should not be created immediately unless a real slice needs them:

- deep `agent_core/contracts/` full tree all at once
- full `runtime/` folder reshuffle
- full `interfaces/` DTO family split
- full `transport/clients/` split
- large `workspace_runtime/adapters/` backend matrix

Reason:

- the immediate goal is to create correct landing zones, not to simulate completion through empty trees

## 17. File-Creation Rule

For the next real implementation slices:

- if a new file is not in this concrete tree, it should be justified against this document before creation
- if a new concern clearly belongs in one of these target owners, do not land it in a transitional file just because that file is already large and convenient

## 18. Immediate Next Implementation Direction

The best immediate code step after this document is:

1. create first-batch files only
2. wire them in as compatibility-preserving seams
3. move one narrow behavior at a time behind the new owners

This document is not the migration itself.
It is the concrete tree map that later code work should follow.
