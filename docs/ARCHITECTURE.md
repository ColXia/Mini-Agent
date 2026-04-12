# Mini-Agent Architecture

> Status: active
> Last updated: 2026-04-12
> Primary delivery mode: terminal-first (`TUI / CLI / headless`)

## 1. Architectural Position

Mini-Agent is currently a terminal-first agent platform.

The active product and development reality is:

- `TUI`, `CLI`, and `headless` are the primary surfaces
- gateway is the shared API/runtime host
- QQ is an optional remote channel adapter
- WebUI is paused as the primary product surface

## 2. Core Rule

The most important current rule is:

- `Session` is the single source of truth
- surfaces do not own sessions
- channels do not own sessions
- surfaces and channels operate sessions through shared application services

See:

- [`P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md`](./P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md)
- [`P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`](./P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md)
- [`P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`](./P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md)

## 3. Layering

### Surface layer

- `TUI`
- `CLI`
- `headless terminal execution`
- optional browser/admin surfaces
- remote channels such as `QQ`

### Transport / adapter layer

- terminal adapters
- gateway HTTP API
- QQ bot adapter
- compatibility adapters such as OpenWebUI-facing paths when enabled

### Application layer

- session service
- shared command execution services
- main gateway use cases
- channel ingress use cases
- studio ops use cases

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
- session persistence / projection / search

## 4. Current Runtime Topology

```text
TUI / CLI / headless
        |
        v
shared commands + application services
        |
        v
runtime orchestration
        |
        v
agent / models / memory / RAG / skills / MCP
        |
        v
session persistence + transcripts + workspace state
```

Optional remote path:

```text
QQ channel
   |
   v
gateway adapter
   |
   v
same application services and session contracts
```

## 5. Repository Mapping

```text
src/mini_agent/
  agent_core/          agent-core domain and orchestration pieces
  application/         use cases and shared application services
  code_agent/          tool loop, scheduler, sandbox, MCP client, context
  commands/            shared operator command semantics
  memory/              global/workspace memory runtime
  rag/                 knowledge-base and retrieval path
  model_manager/       preset/custom providers and unified model registry
  runtime/             runtime manager and execution wiring
  session/             session persistence, projections, search
  tui/                 terminal UI surface
  tools/               runtime tools

src/apps/agent_studio_gateway/
  shared API host and gateway routes

src/apps/qqbot_channel/
  optional QQ channel app
```

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

### Other config assets

The repo still contains config assets under [`../src/mini_agent/config`](../src/mini_agent/config),
but the active preset-provider path is env-first rather than README-level `config.yaml` setup.

## 7. Skills and MCP

- builtin skills are bundled in-repo under [`../src/mini_agent/skills`](../src/mini_agent/skills)
- workspace skills are layered on top of the builtin catalog
- MCP is integrated through runtime policy, registry, and command surfaces
- the project no longer treats an external skill submodule as the default runtime model

## 8. Current Non-Goals

- WebUI-first product flow
- surface-owned session truth
- channel-specific business logic forks
- documenting reference projects as runtime dependencies

## 9. Architecture References

- [`./DEVELOPMENT_GUIDE.md`](./DEVELOPMENT_GUIDE.md)
- [`./DEVELOPMENT_INDEX.md`](./DEVELOPMENT_INDEX.md)
- [`./RUNTIME_FLOW.md`](./RUNTIME_FLOW.md)
- [`./OSS_REFERENCE_INDEX.md`](./OSS_REFERENCE_INDEX.md)
