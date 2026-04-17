# Development Guide

> Status: active
> Last updated: 2026-04-16
> Current mode: terminal-first (`TUI / CLI / headless`)
> Current execution anchor: [`P32B_REPO_HYGIENE_AND_STRUCTURE_ALIGNMENT_PLAN_2026-04-16.md`](./P32B_REPO_HYGIENE_AND_STRUCTURE_ALIGNMENT_PLAN_2026-04-16.md)

## 1. What This Guide Covers

This guide describes the current development reality of Mini-Agent.
It intentionally avoids the older upstream/demo setup language that no longer matches the repo.

Use this guide for:

- local setup
- command entrypoints
- provider/model configuration
- skill and MCP development boundaries
- test and repo hygiene expectations

## 2. Current Architecture Snapshot

Mini-Agent keeps the four-entrance product model:

1. Entrance layer
- `CLI`
- `TUI`
- `DesktopUI`
- `Remote Interaction` (currently implemented by the QQ adapter)
- `headless` remains a runtime mode, not a fifth entrance

2. Application / runtime layer
- session application services
- command execution services
- runtime orchestration
- surface service / gateway host composition

3. Core capability layer
- agent core
- model manager
- memory
- RAG
- skills
- MCP
- session persistence / projection

The active architecture rule is:

- `Session` is the source of truth
- surfaces operate sessions
- channels do not own sessions
- surfaces own presentation and local ephemeral UI state only
- shared interaction behavior must default to `application/` or `runtime/`, not surface files
- if the same rule would be needed by multiple entrances, do not land it in `tui/`, `desktop/`, or channel handlers first

See [`docs/P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`](./P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md).
Execution guardrail details and the current leakage checklist live in [`docs/ARCHITECTURE_EXECUTION_GUARDRAILS_2026-04-17.md`](./ARCHITECTURE_EXECUTION_GUARDRAILS_2026-04-17.md).
Current repo-hygiene closeout is tracked in [`docs/P32B_REPO_HYGIENE_AND_STRUCTURE_ALIGNMENT_PLAN_2026-04-16.md`](./P32B_REPO_HYGIENE_AND_STRUCTURE_ALIGNMENT_PLAN_2026-04-16.md).

## 3. Repository Layout

```text
src/mini_agent/                 core runtime, TUI, CLI, commands, memory, models
src/apps/agent_studio_gateway/  gateway / API host
src/apps/desktop_ui/            DesktopUI bootstrap / packaging app
src/apps/qqbot_channel/         optional QQ bot channel app
scripts/                        smoke, walkthrough, release, maintenance scripts
tests/                          automated test suite
docs/                           active documentation and archive
workspace/                      local outputs, smoke artifacts, caches
```

Notes:

- bundled skills live under [`../src/mini_agent/skills`](../src/mini_agent/skills)
- the project uses `src/` layout; do not document it as `mini_agent/` root layout anymore
- old `git submodule`-based skill setup is no longer the current repo contract

## 4. Local Setup

### Required

```bash
uv sync
```

### Provider keys

Preset providers read these official env vars:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `MINIMAX_API_KEY`

Maintained local provider:

- `MINI_AGENT_OLLAMA_ENABLED=1` (optional, for local Ollama)

Local fallback file:

- `.env.local`

Template only:

- `.env.local.example`
- this file is not loaded by the program

### Optional channel dependency

If you use the QQ channel app, install its Node.js dependencies:

```bash
cd src/apps/qqbot_channel
npm install
```

## 5. Main Commands

Unified terminal entry:

```bash
uv run mini
uv run mini-agent
```

Useful modes:

```bash
uv run mini-agent --mode tui
uv run mini-agent --mode cli
uv run mini-agent --prompt "hello"
```

Gateway and channel flows:

```bash
uv run mini-agent serve --port 8008
uv run mini-agent stack up
uv run mini qq
```

Provider and model operations:

```bash
uv run mini-agent provider list
uv run mini-agent provider add --help
uv run mini-agent models --list-presets
uv run mini-agent models minimax --latest
```

Diagnostics:

```bash
uv run mini-agent doctor
uv run mini-agent security-audit
```

## 6. Providers and Models

### Preset providers

Preset providers are activated from environment variables or `.env.local`.
They are not defined through git submodules or external skill repos.

### Custom providers

Custom providers are persisted to:

- `~/.mini-agent/providers.json`

They are managed through the unified model registry and surfaced in TUI / CLI / gateway.

## 7. Skills and MCP

### Skills

Builtin skills are bundled in-repo:

- [`../src/mini_agent/skills`](../src/mini_agent/skills)
- [`../src/mini_agent/skills/README.md`](../src/mini_agent/skills/README.md)

Do not describe them as "Claude Skills via git submodule".
That is now historical documentation drift.

### MCP

MCP is integrated through runtime configuration and command surfaces.
The exact MCP servers available in a local run depend on the local MCP config and installed tools.

## 8. Testing

Typical commands:

```bash
uv run pytest
uv run pytest tests/test_markdown_links.py -q
uv run pytest tests/test_command_execution_service.py -q
```

Keep test assets inside `tests/`.
Keep executable probes and walkthrough runners inside `scripts/`.
Do not leave one-off local probes in the repo root.

## 9. Repo Hygiene Rules

- move historical docs to `docs/archive/`
- keep active docs in `docs/`
- keep real tests in `tests/`
- keep reusable runners in `scripts/`
- clean ignored probe files and cache directories from the worktree regularly
- do not document reference projects as runtime dependencies

## 10. Related Docs

- [`./DEVELOPMENT_INDEX.md`](./DEVELOPMENT_INDEX.md)
- [`./DOCS_INDEX.md`](./DOCS_INDEX.md)
- [`./P32B_REPO_HYGIENE_AND_STRUCTURE_ALIGNMENT_PLAN_2026-04-16.md`](./P32B_REPO_HYGIENE_AND_STRUCTURE_ALIGNMENT_PLAN_2026-04-16.md)
- [`./P28_BUILTIN_SKILL_REALIGNMENT_PLAN.md`](./P28_BUILTIN_SKILL_REALIGNMENT_PLAN.md)
- [`./P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md`](./P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md)
- [`./P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`](./P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md)
