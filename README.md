# Mini-Agent

English | [中文](./README_CN.md)

Mini-Agent is a terminal-first agent platform focused on real TUI / CLI / headless usage.
It combines a shared session-runtime core with provider/model management, memory and RAG wiring,
bundled skills, MCP integration, and an optional gateway + Remote Interaction workflow currently carried by the QQ adapter.

## Current Status

- Primary entrances: `CLI`, `TUI`, `Desktop`, `Remote`
- Default local workflows: `TUI`, `CLI`, `headless`
- Optional runtime stack: gateway + active QQ remote adapter
- Browser `WebUI` / `OpenWebUI`: removed
- Current architecture direction: post-`P37` structure-aligned baseline with active repo-hygiene closeout (`P32b`)

## Dependency vs Reference

### Real runtime dependencies

Mini-Agent currently depends on:

- `Python >= 3.10`
- `uv` for environment and command execution
- Python packages declared in [pyproject.toml](./pyproject.toml), including:
  - `pydantic`
  - `pyyaml`
  - `httpx`
  - `requests`
  - `mcp`
  - `tiktoken`
  - `prompt-toolkit`
  - `openai`
  - `anthropic`
  - `fastapi`
  - `uvicorn`
  - `python-dotenv`
- Optional Node.js dependencies for the active QQ remote adapter app in [`src/apps/qqbot_channel/package.json`](./src/apps/qqbot_channel/package.json):
  - `dotenv`
  - `qq-official-bot`

### Bundled, not external dependencies

These are shipped in-repo and do not require `git submodule` setup:

- bundled skills under [`src/mini_agent/skills`](./src/mini_agent/skills)
- project scripts under [`scripts/`](./scripts)
- tests under [`tests/`](./tests)

### Reference projects only

The project studies and borrows ideas from external agent projects, but does not directly depend on them at runtime.
These are references, not install-time dependencies:

- `codex`
- `gemini-cli`
- `opencode`
- local `extracted-src` comparisons

See [`docs/OSS_REFERENCE_INDEX.md`](./docs/OSS_REFERENCE_INDEX.md) for the actual mapping.

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/ColXia/Mini-Agent.git
cd Mini-Agent
uv sync
```

### 2. Configure provider keys

Preset providers read official environment variable names first, then `.env.local`.

Supported preset keys:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `MINIMAX_API_KEY`

Local development fallback:

```bash
cp .env.local.example .env.local
```

Then fill in only the keys you actually use.

Priority is:

1. system environment variables
2. local `.env.local`

### 3. Run Mini-Agent

```bash
uv run mini
```

Useful entrypoints:

```bash
uv run mini-agent --mode tui
uv run mini-agent --mode cli
uv run mini-agent --prompt "hello"
uv run mini-agent serve --port 8008
uv run mini-agent stack up
uv run mini qq
```

## Model and Provider Setup

Preset providers:

- discovered from official API key env vars
- can auto-discover available model lists
- support switching in `/model` or the TUI `models` panel

Custom providers:

- persisted to `~/.mini-agent/providers.json`
- configured through `provider add` / Studio ops flows
- shown above preset providers in the unified model registry

Useful commands:

```bash
uv run mini-agent provider list
uv run mini-agent provider add --help
uv run mini-agent models --list-presets
uv run mini-agent models minimax --latest
```

## Repository Layout

```text
src/mini_agent/                 Core runtime, commands, TUI, agent, memory, models
src/apps/agent_studio_gateway/  Gateway / API host
src/apps/desktop_ui/            DesktopUI bootstrap / packaging app
src/apps/qqbot_channel/         Optional QQ remote adapter app
scripts/                        Walkthroughs, smoke scripts, maintenance helpers
tests/                          Automated test suite
docs/                           Active and archived project documentation
workspace/                      Runtime output and local test artifacts
```

## Skills and MCP

- Builtin skills are bundled in-repo under [`src/mini_agent/skills`](./src/mini_agent/skills)
- Workspace/custom skills are managed through `/skill ...` commands
- MCP support is integrated through the runtime and command surfaces
- Common project docs for this area:
  - [`docs/P28_BUILTIN_SKILL_REALIGNMENT_PLAN.md`](./docs/P28_BUILTIN_SKILL_REALIGNMENT_PLAN.md)
  - [`src/mini_agent/skills/README.md`](./src/mini_agent/skills/README.md)

## Testing

```bash
uv run pytest
uv run pytest tests/test_markdown_links.py -q
uv run mini-agent --help
uv run mini-agent doctor
```

## Related Docs

- [`docs/DOCS_INDEX.md`](./docs/DOCS_INDEX.md)
- [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)
- [`docs/DEVELOPMENT_GUIDE.md`](./docs/DEVELOPMENT_GUIDE.md)
- [`docs/DEVELOPMENT_GUIDE_CN.md`](./docs/DEVELOPMENT_GUIDE_CN.md)
- [`docs/DEVELOPMENT_INDEX.md`](./docs/DEVELOPMENT_INDEX.md)
- [`docs/OSS_REFERENCE_INDEX.md`](./docs/OSS_REFERENCE_INDEX.md)

## Notes

- The old `git submodule`-based skill setup is no longer the current project path.
- The old `config.yaml`-only README flow is outdated; env vars + `.env.local` are the active preset-provider path.
- Historical docs and old devlogs are kept under [`docs/archive/`](./docs/archive/).
