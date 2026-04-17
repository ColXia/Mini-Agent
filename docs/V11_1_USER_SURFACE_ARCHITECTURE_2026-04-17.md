# Mini-Agent v11.1 User Surface Architecture

> Status: discussion baseline
> Date: 2026-04-17
> Scope: user-facing surface topology, command subsystem, user service split
> Related:
> - [V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md](./V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md)
> - [V11_1_USER_SERVICE_TO_KERNEL_INTERFACE_DESIGN_2026-04-17.md](./V11_1_USER_SERVICE_TO_KERNEL_INTERFACE_DESIGN_2026-04-17.md)
> - [V11_1_MODULE_OWNERSHIP_AND_MIGRATION_DIRECTION_2026-04-17.md](./V11_1_MODULE_OWNERSHIP_AND_MIGRATION_DIRECTION_2026-04-17.md)
> - [V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md](./V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md)
> - [ARCHITECTURE.md](./ARCHITECTURE.md)
> - [FRAMEWORK_SKELETON.md](./FRAMEWORK_SKELETON.md)

## 1. Purpose

This document freezes the `v11.1` user-side architecture correction after the latest discussion.

Its purpose is to answer one practical question:

- how should Mini-Agent present its user-facing surfaces now that `agent / workspace / model / command` boundaries are becoming clearer

This document does not replace the deeper execution architecture.
It defines how user-facing surfaces should sit on top of the shared service and business layers.

## 2. Final Position

Mini-Agent should no longer be described as four fully parallel product entrances.

The corrected `v11.1` user-side topology is:

- `TUI`
- `Desktop`
- `Remote Interaction`

plus one shared interaction subsystem:

- `Command Subsystem`

This means:

- `TUI` is the main developer-facing surface
- `Desktop` is the main end-user-facing surface
- `Remote Interaction` is a remote extension surface that reuses the same command and agent semantics
- `CLI` is no longer treated as a primary product entrance in the architecture narrative
- instead, CLI semantics are absorbed into the shared command subsystem

## 3. Corrected Surface Model

## 3.1 Primary user surfaces

The primary user surfaces are:

- `TUI`
- `Desktop`
- `Remote Interaction`

They are the real presentation surfaces seen by users.

### TUI

- developer-oriented
- information-dense
- operational
- the closest local surface to the underlying command and runtime semantics

### Desktop

- user-oriented
- visual
- service-driven
- should present a structured product surface instead of exposing raw terminal density

### Remote Interaction

- remote conversational extension surface
- should reuse developer-facing command and agent semantics
- should not become an independent business-truth owner

## 3.2 Shared interaction subsystem

The shared interaction subsystem is:

- `Command Subsystem`

This subsystem owns:

- `/` command grammar
- command parsing
- command execution semantics
- command feedback semantics
- cross-surface command reuse

This is the correct home for what used to be informally called "CLI semantics".

## 3.3 CLI redefinition

`CLI` should now be described as:

- the direct shell-facing carrier of the command subsystem
- a low-level interaction form
- a debug / operator utility surface

It should no longer be the primary architectural description of a user product entrance.

In other words:

- CLI remains useful
- CLI remains supported
- but CLI is no longer the right top-level concept for product-surface design

## 4. Remote Interaction Relationship

Remote interaction should not be treated as "QQ mode inside TUI".

At the same time, it should not be framed as a fully separate product stack with its own business system.

The `v11.1` position is:

- `Remote Interaction` is a remote extension surface
- it is closer in semantics to the TUI/developer operational model than to the Desktop user model
- but it remains a distinct surface, not a TUI wrapper

That means:

- remote surfaces may reuse the same command semantics as TUI
- remote surfaces may reuse the same agent/workspace/model services as TUI and Desktop
- remote surfaces must not depend on TUI view-state or TUI presentation internals

Recommended wording:

- Remote Interaction is a remote extension surface that reuses shared command and agent semantics

## 5. User-Side Service Decomposition

The user side should be split by business responsibility, not by one monolithic frontend controller.

Recommended user service modules:

- `Agent User Service`
- `Workspace User Service`
- `Model User Service`
- `Command User Service`

## 5.1 Agent User Service

Owns the user-facing agent operations.

Typical responsibilities:

- current agent summary
- current agent runtime state
- current agent model binding display
- agent-level actions exposed to surfaces
- agent-oriented execution entrypoints

Important:

- this is the main user-side anchor
- user-side interaction should primarily face `agent`
- this service may internally orchestrate session/task services, but does not replace them

## 5.2 Workspace User Service

Owns the user-facing workspace operations.

Typical responsibilities:

- current workspace summary
- workspace switching
- workspace listing / creation / open
- workspace-level memory / skill / archive presentation
- workspace-level policy or runtime summaries

## 5.3 Model User Service

Owns the user-facing model operations.

Typical responsibilities:

- current agent model binding display
- list available agent model candidates
- switch agent main model
- show capability facts for the selected model
- expose model diagnostics relevant to the user

Important:

- this service talks to the agent model system
- it does not make session the owner of model binding
- it does not make workspace the owner of main agent model binding

## 5.4 Command User Service

Owns the user-facing command entrypoints.

Typical responsibilities:

- `/` command parsing entry
- command autocomplete / discoverability integration
- command invocation
- command feedback formatting contract for surfaces

Important:

- this service keeps command semantics unified across TUI, Desktop, and Remote
- surfaces may render commands differently, but must not redefine their shared meaning independently

## 6. Business Logic Layer Beneath User Services

The user service layer is not the real business layer.

It should sit above a shared business logic layer.

Recommended split:

### User Service Layer

Surface-oriented orchestration.

Properties:

- stable APIs for TUI / Desktop / Remote
- composes multiple lower services
- organizes interactions around user-facing modules
- does not become the owner of truth

### Business Logic Layer

Shared use-case and orchestration layer.

Properties:

- agent application service
- session / task service
- workspace service
- model service
- approval service
- capability / context orchestration

This is where shared truth and durable interaction behavior should live.

## 7. Session Position In The User-Side Architecture

Session must not disappear just because the user-facing modules now focus more on agent/workspace/model.

The corrected `v11.1` position is:

- user-facing primary object: `Agent`
- user-facing environment object: `Workspace`
- user-facing resource object: `Model`
- task truth object beneath that: `Session`

So:

- session does not need to be the main top-level frontend module everywhere
- but session remains a real business subdomain
- agent-facing user operations may still internally create, switch, or resolve sessions through shared task/session services

This preserves task truth without forcing the whole product architecture to revolve visually around session as the first UI object.

## 8. Recommended Layered Topology

```text
Primary User Surfaces
  ├─ TUI
  ├─ Desktop
  └─ Remote Interaction

Shared Interaction Subsystem
  └─ Command Subsystem

User Service Layer
  ├─ Agent User Service
  ├─ Workspace User Service
  ├─ Model User Service
  └─ Command User Service

Business Logic Layer
  ├─ Agent Application Service
  ├─ Session / Task Service
  ├─ Workspace Service
  ├─ Model Service
  ├─ Approval Service
  └─ Capability / Context Orchestration

Runtime / Core Layer
  ├─ AgentInstance / Run Kernel
  ├─ WorkspaceRuntime
  ├─ ModelPool + AgentModelService
  ├─ Skill / Memory Resolvers
  └─ Permission Engine
```

## 9. Surface Responsibilities

## 9.1 TUI

Allowed to own:

- dense operator-facing rendering
- keyboard-first interaction
- developer workflows
- direct command entry affordances

Must not own:

- session truth
- agent truth
- workspace truth
- model truth
- separate command semantics

## 9.2 Desktop

Allowed to own:

- structured graphical flows
- user-friendly modules and pages
- native desktop affordances
- visual information architecture

Must not own:

- agent execution truth
- workspace truth
- main model-binding truth
- separate command semantics

## 9.3 Remote Interaction

Allowed to own:

- channel-specific formatting
- remote delivery
- remote event normalization
- lightweight remote command entry UX

Must not own:

- a second business system
- a second session truth system
- a second agent model system
- TUI-local rendering state

## 10. Recommended Frontend Module Shape

Because the user side now splits by business module, frontend surfaces should also tend toward modular screens or panels instead of one giant controller.

Recommended frontend module families:

- `Agent Panel / Agent Page`
- `Workspace Panel / Workspace Page`
- `Model Panel / Model Page`
- `Command Palette / Command Drawer / Slash Command Entry`

This applies differently by surface:

- TUI may expose these as panes or command-driven views
- Desktop may expose these as pages, tabs, drawers, or panes
- Remote may expose a smaller subset through command-led flows

## 11. Why This Is Better Than The Old Four-Entrance Story

This corrected model improves three things:

- it stops treating CLI as a product-level peer of the real user surfaces
- it gives TUI and Desktop the correct primary roles
- it makes command semantics a reusable subsystem instead of a surface-specific implementation accident

It also aligns better with the deeper `v11.1` boundary work:

- agent remains the main user-facing execution subject
- workspace remains the execution world
- model remains a separate dedicated block
- session remains a business truth subdomain rather than a mandatory top-level UI object

## 12. Non-Goals

This document does not:

- redesign the deep execution architecture
- redefine workspace runtime internals
- redefine the model block internals
- turn remote interaction into a TUI wrapper
- remove CLI support from the repository

## 13. Final Baseline

The user-side architecture is aligned with `v11.1` if the project follows these outcomes:

- the primary user surfaces are `TUI / Desktop / Remote Interaction`
- `CLI` is treated as a command-carrier form, not the main top-level product entrance concept
- command semantics are unified under a shared command subsystem
- user-side services are split into `agent / workspace / model / command`
- session remains a real business subdomain beneath the user-facing services
- remote interaction reuses shared semantics without reusing TUI view state
- TUI and Desktop remain separate presentation surfaces over shared services

## 14. Immediate Next Step

If this document is accepted, the next recommended slice is:

- `v11.1 user-service interface design`

That slice should define:

- `AgentUserService`
- `WorkspaceUserService`
- `ModelUserService`
- `CommandUserService`
- and the minimum surface-facing contracts they expose
