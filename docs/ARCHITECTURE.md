# Mini-Agent Architecture

> Status: active
> Last updated: 2026-04-13
> Product entrance model: `CLI / TUI / DesktopUI / Remote Interaction`
> Current implementation focus: terminal-first delivery plus `DesktopUI(PySide6)` planning, with `QQ` as the only active remote-channel path; `WeChat / Feishu` remain future extension targets and browser `WebUI` is now a paused compatibility/prototype path rather than the canonical third entrance
> Framework skeleton lock: [`FRAMEWORK_SKELETON.md`](./FRAMEWORK_SKELETON.md)

## 1. Architectural Position

Mini-Agent is a shared agent platform with four user-side entrances:

- `CLI`
- `TUI`
- `DesktopUI`
- `Remote Interaction`

`Remote Interaction` is a product entrance, not a single bot implementation.
Its concrete channel adapters conceptually include:

- `QQ bot`
- `WeChat bot`
- `Feishu bot`

Current delivery scope:

- `QQ bot` is the active implementation path
- `WeChat bot` is future extension only
- `Feishu bot` is future extension only
- `DesktopUI (PySide6)` is the planned graphical mainline
- browser `WebUI` is paused as a compatibility/prototype path

At the same time:

- `headless` is a runtime mode, not a fifth user entrance
- `gateway` is the shared host / access path, not a user entrance
- channel adapters are protocol bridges, not session owners

## 2. Core Rule

The most important rule remains unchanged:

- `Session` is the single source of truth
- entrances do not own sessions
- channel adapters do not own sessions
- every entrance operates sessions through shared application services

See:

- [`P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md`](./P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md)
- [`P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`](./P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md)
- [`P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`](./P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md)
- [`FRAMEWORK_SKELETON.md`](./FRAMEWORK_SKELETON.md)

## 3. Layering

### User entrance layer

- `CLI`: the canonical base interaction surface
- `TUI`: the developer-facing visual terminal surface
- `DesktopUI`: the primary end-user graphical surface
- `Remote Interaction`: the remote conversational entrance

### Remote channel adapter sub-layer

- `QQ adapter` (active path)
- `WeChat adapter` (future extension)
- `Feishu adapter` (future extension)

This sub-layer exists under the remote entrance and is not parallel to the four entrances themselves.

### Interface / transport layer

- terminal input/output adapters
- browser HTTP / WebSocket API
- gateway HTTP API
- remote channel ingress / egress adapters

This layer translates protocols and presentation contracts.
It must not become a second business layer.

### Application service layer

- session service
- chat / turn service
- command execution service
- model service
- memory / RAG / skill / MCP application services
- workspace and approval services

This is the shared service layer used by all four entrances.

### Runtime orchestration layer

- runtime manager
- submission loop
- approvals / cancellation / recovery
- diagnostics and health handling

### Core capability layer

- agent core
- model manager
- memory
- RAG
- skills
- MCP
- session and workspace domain contracts

### Infrastructure layer

- persistence stores
- LLM clients
- channel SDKs
- browser runtimes
- local filesystem / workspace state

## 4. Current Runtime Topology

```text
CLI / TUI / DesktopUI / Remote Interaction
                 |
                 v
        interface / transport adapters
                 |
                 v
      shared application services
                 |
                 v
      runtime orchestration
                 |
                 v
agent / models / memory / RAG / skills / MCP
                 |
                 v
session persistence + workspace state + external integrations
```

Remote path detail:

```text
Remote Interaction
       |
       v
QQ / WeChat / Feishu adapters
       |
       v
gateway ingress + shared application services
       |
       v
same session truth and runtime contracts
```

## 5. Repository Mapping

```text
src/mini_agent/
  agent_core/          agent-core domain and orchestration pieces
  application/         shared use cases and application services
  code_agent/          tool loop, scheduler, sandbox, MCP client, context
  commands/            shared operator command semantics
  memory/              global/workspace memory runtime
  rag/                 knowledge-base and retrieval path
  model_manager/       preset/custom providers and unified model registry
  runtime/             runtime manager and execution wiring
  session/             session persistence, projections, search
  tui/                 TUI surface
  desktop/             DesktopUI surface state and view-model helpers

src/apps/agent_studio_gateway/
  shared gateway host and browser/remote API routes

src/apps/desktop_ui/
  PySide6 desktop bootstrap and packaging entry

src/apps/qqbot_channel/
  active QQ remote-channel adapter app

src/apps/agent_studio/
  paused browser compatibility/prototype path; not the canonical graphical mainline

src/channels/wechat/
  future-extension WeChat integration code; not part of the current delivery roadmap
```

Planned but not yet landed as a first-class maintained path:

- `DesktopUI (PySide6)` as the canonical maintained graphical path
- `WeChat remote-channel adapter` as a maintained product path
- `Feishu remote-channel adapter`
- browser `WebUI` only if revived later as an optional compatibility surface on the same shared service contract

## 6. Configuration Model

### Provider configuration

Preset providers:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `MINIMAX_API_KEY`

Priority:

1. system environment variables
2. local `.env.local`

Custom providers:

- persisted in `~/.mini-agent/providers.json`

### Channel configuration

Remote-channel adapters are allowed to hold:

- channel credentials
- conversation-to-session bindings
- delivery preferences
- channel display metadata

They must not persist a second session truth model.

## 7. Architectural Clarifications

### Why there is still an API layer

Yes, the project still needs an API layer, but it belongs to the interface / transport layer.
It exists to expose the shared application services to:

- DesktopUI
- remote-channel adapters
- optional external integrations

It must not duplicate business rules that belong in the application layer.

### What CLI and TUI relationship means

- `CLI` is the base interaction entrance and the lowest-complexity operator path
- `TUI` is a richer visual entrance that should reuse CLI command semantics and the same application services

### What the remote entrance means

The remote entrance is not "QQ mode in TUI".
It is a separate product entrance whose concrete implementations are channel adapters such as:

- `QQ`
- `WeChat`
- `Feishu`

Those adapters may reuse the same commands and services, but they must stay thin.

### What DesktopUI means now

- `DesktopUI` is not a browser-first Studio continuation
- `DesktopUI` is not a wrapper around the current TUI renderer
- `DesktopUI` should reuse the same application/runtime/session truth through a thin local gateway transport in the first delivery slices
- if browser Studio remains in the repo, it should be treated as paused compatibility/prototype material rather than the mainline UX direction

## 8. Current Non-Goals

- surface-owned session truth
- channel-specific business logic forks
- treating `headless` as an independent user product entrance
- treating one concrete channel adapter as the definition of the whole remote entrance
- documenting reference projects as runtime dependencies

## 9. Architecture References

- [`./DEVELOPMENT_GUIDE.md`](./DEVELOPMENT_GUIDE.md)
- [`./DEVELOPMENT_INDEX.md`](./DEVELOPMENT_INDEX.md)
- [`./RUNTIME_FLOW.md`](./RUNTIME_FLOW.md)
- [`./OSS_REFERENCE_INDEX.md`](./OSS_REFERENCE_INDEX.md)
