# Mini-Agent v11.1 Agent / Workspace Execution Architecture

> Status: discussion baseline
> Date: 2026-04-17
> Scope: agent-core / workspace / session / tool / skill / memory / permission / runtime boundary redesign
> Supersedes: chat-only discussion drafts for `v11` / `v11.1`
> Related:
> - [ARCHITECTURE.md](./ARCHITECTURE.md)
> - [FRAMEWORK_SKELETON.md](./FRAMEWORK_SKELETON.md)
> - [AGENT_CORE_RUNTIME_SEAMS.md](./AGENT_CORE_RUNTIME_SEAMS.md)
> - [P34_AGENT_CORE_REFACTOR_PLAN_2026-04-15.md](./P34_AGENT_CORE_REFACTOR_PLAN_2026-04-15.md)
> - [V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md](./V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md)
> - [V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md](./V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md)
> - [V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md](./V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md)
> - [V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md](./V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md)
> - [V11_1_USER_SURFACE_ARCHITECTURE_2026-04-17.md](./V11_1_USER_SURFACE_ARCHITECTURE_2026-04-17.md)

## 1. Purpose

This document freezes the current `v11.1` discussion baseline for Mini-Agent after the latest architecture re-evaluation.

It is meant to answer one practical question:

- how should `Agent`, `Workspace`, `Session`, `Tool`, `Skill`, `Memory`, `Permission`, `MCP`, and `RAG` relate so the project can keep iterating without drifting back into another monolithic core

This document is not yet an execution plan.
It is the architecture contract that later execution plans should target.

## 2. Final Assumptions Locked By This Version

The following assumptions are explicitly locked in `v11.1`:

- `Agent` is portable and is not owned by a single workspace
- all real execution happens while attached to a workspace
- `DefaultWorkspace` is a full workspace, not a degraded pseudo-workspace
- the main model system serves agent only and is not part of the workspace/session ownership chain
- `Tool` belongs to agent capability, not to workspace ownership
- tool execution must still bind to the current workspace runtime before it can run
- permission and approval control are externalized and must not be hidden inside tool implementations
- `Skill` uses three layers: `internal / global / workspace`
- `Memory` uses three layers: `session / workspace / global`
- `MCP` is fully externalized and does not belong to the core or inner ring
- `RAG` is a workspace-side feature; agent only owns the ability to consume it
- child-agent design is postponed and is not a driver for current architecture

## 3. One-Sentence Definition

Mini-Agent `v11.1` adopts:

`Portable Agent + Full Workspace World + Workspace-Bound Execution + External Policy Control`

This means:

- agent owns capability
- workspace owns the durable execution world
- session owns task state
- runtime binds tools to the current workspace execution environment
- policy decides what is allowed, denied, or approval-gated

## 4. Core Principles

### 4.1 Agent owns capability

Agent is the long-lived capability bearer.
Its identity and built-in capabilities must not be redefined every time it changes workspace.

### 4.2 Workspace owns the execution world

Workspace is where files, workspace memory, local skills, archives, artifacts, and knowledge assets live.
The system should treat `DefaultWorkspace` and project workspaces as the same class of object with different manifests and policies.

### 4.3 Session owns task truth

Session is the task container.
It carries messages, short-term task memory, approvals for the task, and task-local policy overrides.

### 4.4 Capability and control must stay separate

Agent may know how to read a file, write a file, run shell, or execute code.
That does not mean every current run is allowed to do so.

The system must keep:

- capability ownership
- execution environment binding
- permission judgment

as separate concerns.

### 4.5 Every run is attached to a workspace

There is no formal "no workspace" run state in `v11.1`.
If the user is not inside a project workspace, the run still happens in `DefaultWorkspace`.

## 5. First-Class Entities

`v11.1` fixes the following first-class entities:

- `AgentProfile`
- `AgentInstance`
- `Workspace`
- `WorkspaceRuntime`
- `Session`
- `Run`
- `CapabilitySnapshot`

## 6. Entity Definitions

### 6.1 AgentProfile

Static identity and built-in capability definition.

Owns:

- agent id
- role / identity / static policy hints
- built-in tool catalog
- built-in internal skills
- default model routing intent
- stable behavior defaults

Does not own:

- current run state
- current workspace attachment
- current session state

### 6.2 AgentInstance

Persistent execution subject.

Owns:

- kernel execution state
- checkpoint cursor
- execution journal cursor
- interrupt / resume / cancel state
- pending approval wait state
- active run metadata
- current attachment metadata

Does not own:

- workspace filesystem implementation
- workspace knowledge implementation
- full session records
- MCP / RAG implementation details

### 6.3 Workspace

Full durable execution world.

Owns:

- workspace id
- root directory
- workspace kind
- file tree
- workspace memory
- workspace skills
- workspace-level configuration
- workspace permission policy
- session records and archive
- local artifacts
- knowledge / retrieval assets when enabled

Recommended manifest field:

```text
workspace_id
title
root_dir
kind = default | project
runtime_policy
permission_policy
rag_config
created_at
updated_at
```

### 6.4 WorkspaceRuntime

Integrated workspace execution environment.

Owns:

- workspace mount / root boundary
- file access boundary
- shell execution
- code execution
- process supervision
- network / resource restrictions
- mutation ledger
- diff and snapshot hooks
- recovery support

Supported backends may include:

- `direct`
- `container_mounted`
- `isolated_copy`

but these are backend choices, not different architecture models.

### 6.5 Session

Workspace-bound task container.

Owns:

- session id
- workspace id
- title / state / timestamps
- messages
- session memory
- current task scratchpad
- task-level approvals
- task-local policy overrides
- archive summary

Rule:

- every session belongs to exactly one workspace

### 6.6 Run

Single execution unit.

Owns:

- run id
- agent instance id
- workspace id
- session id
- current step state
- current status
- capability snapshot pointer / hash
- trace / journal association

### 6.7 CapabilitySnapshot

Resolved capability set for one run.

Owns:

- resolved tools
- resolved tool policies
- resolved skills
- visible memory scopes
- enabled external capabilities
- agent model binding
- agent model capability profile
- workspace runtime mode
- approval profile
- context policy

This object is critical because run-time execution should consume a stable snapshot instead of repeatedly resolving dynamic state from many sources mid-run.

## 7. Truth Domains

`v11.1` does not use a single catch-all truth owner.
It uses multiple truth domains.

### 7.1 Agent truth

Owned by `AgentProfile + AgentInstance`

- static identity
- built-in capability
- kernel execution state
- active run state

### 7.2 Workspace truth

Owned by `Workspace`

- filesystem state
- workspace memory
- workspace skills
- workspace archive
- workspace policy
- workspace knowledge assets

### 7.3 Session truth

Owned by `Session`

- task messages
- task-local working state
- task approvals
- task summary

### 7.4 Surface truth

Owned only locally by CLI/TUI/Desktop/Remote presentation layers

- cursor
- drafts
- selection
- layout state
- temporary local rendering state

Surface truth must never be treated as shared truth.

## 8. Execution Topology

```text
AgentProfile
    |
    v
AgentInstance -----> StateStore
    |
    | attached to
    v
Session ------ belongs to ------> Workspace
                                  |
                                  v
                           WorkspaceRuntime
                                  |
                                  v
                            PermissionEngine
                                  |
                                  v
                             ToolExecution

ContextAssembler + MemoryResolver + SkillResolver + ExternalCapabilityBroker
                                  |
                                  v
                           CapabilitySnapshot
                                  |
                                  v
                              Run / Kernel
```

## 9. Tool System

## 9.1 Core statement

Tools belong to agent capability.
They are not workspace-owned assets.

However:

- tools do not execute "in the abstract"
- they only execute after being bound to the current workspace runtime and current policy result

## 9.2 Tool objects

Recommended objects:

- `ToolSpec`
- `ToolBinding`
- `ToolPolicy`
- `ToolGrant`

### ToolSpec

Static tool definition.

Recommended fields:

- `tool_name`
- `namespace`
- `description`
- `operation_kind`
- `requires_workspace_runtime`
- `supports_outside_workspace`
- `supports_mutation_tracking`
- `default_risk_level`
- `input_schema`
- `output_schema`

Example tool names:

- `core.file.read`
- `core.file.write`
- `core.file.edit`
- `core.shell.exec`
- `core.code.run`

### ToolBinding

Execution binding for the current run.

Recommended fields:

- `tool_name`
- `workspace_id`
- `runtime_id`
- `resolved_path_scope`
- `resolved_exec_backend`
- `resolved_limits`
- `binding_valid_until`

### ToolPolicy

Permission result returned by the external policy system.

Recommended fields:

- `decision = allow | deny | approval_required`
- `path_policy`
- `network_policy`
- `resource_policy`
- `timeout_override`
- `mutation_tracking_mode`
- `reason`

### ToolGrant

Temporary grant produced by approval or policy.

Recommended fields:

- `grant_id`
- `tool_name`
- `workspace_id`
- `session_id`
- `run_id`
- `granted_scope`
- `expires_at`
- `grant_source`

## 9.3 File / shell / code execution

These three are all agent core tools, but execution must go through `WorkspaceRuntime`.

Rules:

- file tools default to attached workspace scope
- shell executes with attached workspace working directory
- code execution runs inside the attached workspace runtime mode
- access outside the attached workspace is a separate policy decision

## 10. Workspace Zone Model

Because `DefaultWorkspace` is a full workspace, `v11.1` uses a simpler zone model:

- `Attached Workspace Zone`
- `Outside Zone`

### 10.1 Attached Workspace Zone

The currently attached workspace root and all managed assets inside it.

This attached workspace may be:

- a default workspace
- or a project workspace

### 10.2 Outside Zone

Everything outside the attached workspace root.

This zone should be more restrictive by default and must be explicitly judged by policy.

## 11. Permission Engine

Permission control must be externalized as a first-class system.

Recommended component:

- `PermissionEngine`

Inputs:

- agent profile / instance
- workspace manifest
- session record
- run metadata
- tool request
- target paths
- execution mode

Outputs:

- `allow`
- `deny`
- `approval_required`
- `constraint_rewrite`

`constraint_rewrite` is required, not optional.

It must support outcomes such as:

- allow but force container mode
- allow read but deny write
- allow shell but disable network
- allow write only inside whitelisted directories
- allow execution but shorten timeout

## 12. Skill System

`v11.1` fixes a three-layer skill model:

- `Internal Skills`
- `Global Skills`
- `Workspace Skills`

### 12.1 Internal Skills

Owned by agent as stable built-ins.

Properties:

- core capability
- version-controlled
- not overrideable by global or workspace layers

Suggested namespace:

- `core.*`

### 12.2 Global Skills

System- or user-level shared extension skills.

Properties:

- reusable across workspaces
- not part of the core inner kernel
- mounted during capability resolution

Suggested namespace:

- `global.*`

### 12.3 Workspace Skills

Workspace-local learned or curated skills.

Properties:

- workspace-local only
- do not promote automatically to global
- do not override internal skills

Suggested namespace:

- `ws.*`

### 12.4 Skill resolution rules

This is not an override chain.
It is an assembly chain.

Rules:

- internal is reserved
- global is shared extension
- workspace is local extension
- resolver outputs a `ResolvedSkillSet`

## 13. Memory System

`v11.1` fixes a three-layer memory model:

- `Session Memory`
- `Workspace Memory`
- `Global Memory`

### 13.1 Session Memory

Task-local working memory.

Includes:

- scratchpad
- current task facts
- current recovery hints
- local working state

### 13.2 Workspace Memory

Workspace-local experience memory.

Includes:

- project experience
- local durable lessons
- workspace-specific learned facts

### 13.3 Global Memory

User-level long-term preference or learning memory.

Includes:

- user preferences
- cross-workspace durable habits
- high-confidence general facts

### 13.4 Recommended read / write rules

Read order:

- session
- workspace
- global

Default write target:

- session

Promotion rules:

- session -> workspace: allowed via explicit summarization / curation
- workspace -> global: not automatic
- session -> global: not automatic

## 14. RAG Position

RAG is a workspace-side feature, not an agent-core built-in subsystem.

Meaning:

- workspace may configure it
- `ContextAssembler` may consume it
- agent only needs the ability to use retrieved context
- core should not depend on concrete RAG implementation

## 15. MCP Position

MCP is fully externalized.

Meaning:

- MCP does not belong to core
- MCP does not belong to the inner ring
- agent should only depend on an `ExternalCapabilityBroker`
- MCP is only one backend implementation behind that broker

Core should not know:

- MCP sessions
- MCP lifecycle
- MCP protocol details

## 16. Child-Agent Status

Child-agent design is explicitly postponed in `v11.1`.

Implications:

- child-agent inheritance matrices are not part of the current contract
- multi-agent design should not drive current boundaries
- existing delegation code may remain, but it is not the architectural anchor for this version

## 17. CapabilitySnapshot Design

This object is the stable resolved capability set used by one run.

Recommended sources:

- `AgentProfile`
- `AgentInstance`
- global skill registry
- workspace skill registry
- memory resolver
- external capability broker
- permission engine
- workspace runtime
- session overrides

Recommended refresh points:

- before run start
- before resume
- after approval grant
- after workspace switch
- after capability registry changes

## 18. ContextAssembler Position

Context assembly lives outside core.

Recommended sources:

- session context
- workspace context
- global memory context
- recovery context
- capability context

Core should consume the result through a `ContextProvider`, not own the assembly policy.

## 19. Run / Checkpoint / Journal / Rollback

### 19.1 Checkpoint points

Recommended checkpoint boundaries:

- run start
- before model output commit
- before tool call
- after tool result
- before approval request
- after approval result
- before resume
- run end

### 19.2 Execution journal

Kernel-side journal records:

- model steps
- tool steps
- approvals
- interrupts
- resumes
- failures
- finish states

### 19.3 Mutation ledger

Workspace-runtime-side ledger records:

- written files
- edited files
- deleted files
- command execution summaries
- snapshots
- reversibility metadata

### 19.4 Rollback levels

Recommended rollback levels:

- `Kernel Rollback`
- `Mutation Rollback`
- `Workspace Snapshot Rollback`

Kernel rollback restores execution state only.

Mutation rollback restores controlled file changes.

Workspace snapshot rollback restores the attached workspace world.

## 20. Workspace Switching and Agent Migration

### 20.1 Agent portability

Agent may move between workspaces.

### 20.2 Migration must be explicit

Recommended sequence:

1. detach current workspace
2. flush or suspend active run
3. attach target workspace
4. bind target workspace runtime
5. open or create session in target workspace
6. refresh capability snapshot

### 20.3 Session does not drift across workspaces

Session always belongs to one workspace.
When agent changes workspace, it must bind to a session in the target workspace rather than dragging the old session across workspace boundaries.

## 21. Recommended Repository Mapping

Recommended future target:

```text
src/mini_agent/
  agent_core/
    agent_profile.py
    agent_instance.py
    kernel.py
    run_state.py
    checkpoint.py
    journal.py
    tool_spec.py
    skill_contract.py
    capability_snapshot.py
    ports.py

  runtime/
    agent_attachment.py
    workspace_attachment.py
    session_attachment.py
    run_supervisor.py
    approval_runtime.py
    recovery_coordinator.py

  workspace_runtime/
    runtime.py
    permission_engine.py
    mutation_ledger.py
    snapshot_service.py
    sandbox_backend.py
    path_policy.py

  skills/
    internal/
    global_registry.py
    workspace_registry.py
    resolver.py

  memory/
    session_store.py
    workspace_store.py
    global_store.py
    resolver.py

  rag/
    workspace_knowledge_service.py

  external_capabilities/
    broker.py
    mcp/
```

## 22. Current Discussion Outcomes (2026-04-17)

The following boundary choices are now the current `v11.1` discussion baseline.

### 22.1 ToolGrant scope

- the system keeps the current two-level permission shape:
  - default permission is `run-scoped`
  - full permission may be `session-scoped`
- this is user-controlled policy; agent only consumes the result
- permissions that cross the attached workspace boundary stay strictly `run-scoped`

### 22.2 Global Memory write threshold

- global memory may rise only with explicit user authorization
- there is no automatic promotion path from session/workspace memory into global memory in `v11.1`

### 22.3 Workspace Skills generation and governance

- workspace skills are only created when the user explicitly asks to create them
- there is no automatic learning / self-growth implementation for workspace skills in `v11.1`
- creation may still use session and workspace content as source material, but the result remains local to that workspace until the user migrates it manually

### 22.4 Outside Zone default read policy

- outside-zone read is allowed by default
- outside-zone modify/write requires explicit user approval
- outside-zone delete is denied by default
- a first protected blacklist should be introduced for system-level / OS-protected path ranges
- later versions may add whitelist / blacklist refinement, but `v11.1` starts with:
  - read allowed
  - modify approval-required
  - delete denied

### 22.5 Whether `workspace_runtime/` should be a dedicated module

- yes, `workspace_runtime/` should become a dedicated maintained module
- workspace-bound execution is now treated as foundational infrastructure, not as scattered runtime/tool detail

## 23. Final Baseline Statement

`v11.1` is considered aligned if the project follows these outcomes:

- `DefaultWorkspace` is treated as a full workspace of kind `default`
- every formal run occurs inside an attached workspace
- agent remains portable across workspaces
- tool capability stays agent-owned
- tool execution is bound to workspace runtime
- permission stays externalized
- skills are resolved from `internal / global / workspace`
- memory is resolved from `session / workspace / global`
- the main model system serves agent and remains separate from workspace/session ownership
- MCP remains outside the core
- RAG remains a workspace-side feature
- child-agent design remains postponed
- runs consume a stable `CapabilitySnapshot`
- rollback remains explicitly layered

## 24. Immediate Next Architecture Step

If this document is accepted, the next recommended design slice is:

- `v11.2 Capability System Object Design`

That slice should formalize:

- `ToolSpec`
- `ToolBinding`
- `ToolPolicy`
- `ToolGrant`
- `SkillResolver`
- `MemoryResolver`
- `CapabilitySnapshot`
