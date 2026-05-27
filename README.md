# Mini-Agent

English | [中文](./README_CN.md)

A terminal-first AI agent platform with TUI, CLI, headless, and desktop interfaces.
Built with a modular v11 architecture — agent engine, model management, memory/RAG,
tool system, MCP integration, and an optional HTTP gateway with remote interaction support.

## Current Status

- **Version**: v0.2.0 | **Architecture**: v11.1 | **License**: MIT
- **Tests**: 1723 passed, 17 skipped
- **Python**: >= 3.10

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/ColXia/Mini-Agent.git
cd Mini-Agent
uv sync
```

### 2. Configure a provider API key

Set at least one provider key (environment variable or `.env.local`):

```bash
cp .env.local.example .env.local
# Edit .env.local with your key(s)
```

Supported providers: **OpenAI**, **Anthropic**, **MiniMax**, **Gemini**, and custom OpenAI-compatible endpoints.

### 3. Run

```bash
uv run mini                # Auto-detect terminal: TUI if TTY, headless otherwise
uv run mini-agent --mode tui    # Force full-screen terminal UI
uv run mini-agent --prompt "hello"  # Single prompt, non-interactive
uv run mini-agent serve --port 8008  # Start HTTP API server
uv run mini-agent desktop        # Launch PySide6 desktop app (optional)
```

## Features

| Area | Capabilities |
|------|-------------|
| **Agent Engine** | Full execution loop, state machine, permission/approval engine, checkpoints & recovery |
| **Multi-Interface** | TUI (full-screen terminal), Desktop (PySide6), CLI (interactive), Headless (scripts/CI), HTTP API |
| **Model Management** | Multi-provider (OpenAI/Anthropic/MiniMax/Ollama), model pool, health monitoring, circuit breaker, auto-failover |
| **Tool System** | Shell execution, file read/write/edit, MCP protocol, knowledge base query, skill loading |
| **Memory System** | Working memory, short/long-term memory, auto-consolidation, relevance retrieval, session search |
| **RAG** | Built-in lightweight hybrid store: BM25 + vector similarity + RRF fusion |
| **Skills** | 18 built-in skills (Android/iOS/React/Flutter/Web/MCP/etc.), extensible via workspace skills |
| **Session Management** | Multi-session, rename/delete/clone/share, persistent storage |
| **Workspace** | File boundary control, mutation ledger, snapshot/rollback, stack management |
| **Remote Interaction** | QQ Bot adapter sharing the same session context as TUI |

## Architecture

```
┌─────────────────────────────────────────────┐
│  Surface Layer:  TUI  │  Desktop  │  CLI  │  HTTP API  │
├─────────────────────────────────────────────┤
│  Application Layer:  Use Cases  │  Ports  │  Facades  │
├─────────────────────────────────────────────┤
│  Agent Core:  Engine  │  Loop  │  Context  │  Permissions  │
├─────────────────────────────────────────────┤
│  Services:  Model  │  Memory  │  Tools  │  Skills  │  RAG  │
├─────────────────────────────────────────────┤
│  Infrastructure:  Runtime  │  Session  │  Workspace  │  LLM  │
└─────────────────────────────────────────────┘
```

See [`docs/project-documentation/`](./docs/project-documentation/) for detailed Chinese documentation.

## Repository Layout

```text
src/mini_agent/
  agent_core/         Agent engine, execution loop, permissions, context
  application/        Hexagonal ports/adapters, use cases, facades
  runtime/            Session handlers, orchestration, live control
  model_manager/      Model pool, registry, health monitoring, failover
  memory/             Working/short/long-term memory, consolidation
  tools/              Shell, file, MCP, knowledge base tools
  skills/             Bundled skills (18 categories)
  tui/                Full-screen terminal UI (prompt_toolkit)
  desktop/            PySide6 desktop application
  transport/          HTTP gateway client & remote clients
  llm/                Anthropic & OpenAI protocol adapters
  session/            Session persistence & projections
  workspace_runtime/  Workspace executor, snapshot store, stack manager
  interfaces/         Interface DTOs & contracts
  schema/             Core data models
  commands/           Command parsing, completion, metadata
  security/           Policy engine, audit, key store
  rag/                Lightweight hybrid retrieval (BM25 + vector)
  ops/                Health checks, diagnostics, observability
  config/             Configuration templates
  user_services/      User-facing service facades (in application/)
  utils/              Shared utilities
  dev/                Development tooling
src/apps/             Gateway server, desktop entry, QQ Bot adapter
src/subprograms/      Document parser, knowledge base, memory manager
tests/                301 test files, 1723 test cases
docs/                 Project docs, architecture plans, design records
```

## Testing

```bash
uv run pytest                    # Full suite (1723 tests)
uv run pytest tests/test_retry.py -v  # Specific module
uv run mini-agent doctor          # Runtime diagnostics
```

## Documentation

- **Chinese docs**: [`docs/project-documentation/`](./docs/project-documentation/)
- **Architecture**: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)
- **Development guide**: [`docs/DEVELOPMENT_GUIDE.md`](./docs/DEVELOPMENT_GUIDE.md)
- **API contract**: [`docs/API_V1_CONTRACT_SKELETON.md`](./docs/API_V1_CONTRACT_SKELETON.md)

## License

MIT — see [LICENSE](./LICENSE).
