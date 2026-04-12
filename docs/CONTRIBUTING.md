# Contributing Guide

This repository is currently developed as a terminal-first agent project.

## Before You Contribute

- Read [README.md](../README.md) and [docs/DEVELOPMENT_GUIDE.md](./DEVELOPMENT_GUIDE.md)
- Check [docs/ARCHITECTURE.md](./ARCHITECTURE.md) for current boundaries
- Treat `docs/archive/` as historical reference only
- Prefer TUI / CLI / headless workflows; WebUI is currently paused

## Getting Started

1. Clone the repository you will contribute to.
   ```bash
   git clone <your-fork-or-origin-url> mini-agent
   cd mini-agent
   ```
2. Install dependencies.
   ```bash
   uv sync
   ```
3. Run a quick health check.
   ```bash
   uv run mini-agent --help
   uv run pytest tests/test_markdown_links.py -q
   ```

## Development Rules

- Keep changes scoped to the task at hand
- Do not mix cleanup, refactor, and feature work without documenting why
- Prefer real runtime behavior over compatibility shells unless compatibility is required
- Update docs when runtime behavior or architecture changes
- Keep active docs and archived docs clearly separated
- Do not commit local secrets, `.env.local`, runtime state, or workspace artifacts

## Tests

- Put automated tests in `tests/`
- Put reusable helper scripts in `scripts/`
- Do not leave ad hoc probe files in `src/` or the repo root
- Run the smallest relevant test set first, then broader verification if needed

Examples:

```bash
uv run pytest tests/test_config_local_env.py tests/test_preset_providers.py -q
uv run pytest tests/test_command_execution_service.py -q
python scripts/test_stable.py
```

## Documentation

When your change affects behavior, also check whether these need updates:

- [README.md](../README.md)
- [README_CN.md](../README_CN.md)
- [docs/DOCS_INDEX.md](./DOCS_INDEX.md)
- [docs/DEVELOPMENT_INDEX.md](./DEVELOPMENT_INDEX.md)
- [docs/REFACTOR_TASKS.md](./REFACTOR_TASKS.md)

## Pull Requests

Before opening a PR, make sure:

- the change has a clear purpose
- tests relevant to the change have been run
- docs are updated where needed
- unrelated generated files and caches are not included
- the summary explains both what changed and why

## Commit Style

Recommended prefixes:

- `feat`: new capability
- `fix`: bug fix
- `refactor`: structural change without intended behavior change
- `docs`: documentation updates
- `test`: test-only changes
- `chore`: maintenance and tooling

## Questions

If something is unclear, prefer clarifying the current code and active docs before copying older patterns from historical files.