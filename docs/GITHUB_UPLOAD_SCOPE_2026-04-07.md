# GitHub Upload Scope (2026-04-07)

> Status: active
> Purpose: define safe upload range for current P19 progress sync

## 1. Recommended Upload Scope (Core)

Upload these paths first (recommended for cross-device continuation):

- `.github/`
- `docs/`
- `scripts/`
- `src/`
- `tests/`
- `examples/` (if needed by your workflow/demo)
- `.gitignore`
- `.gitmodules`
- `LICENSE`
- `MANIFEST.in`
- `pyproject.toml`
- `README.md`
- `HABITS.md`
- `TASKS.md`
- `uv.lock`

## 2. Optional Upload Scope

Upload only when required:

- `third_party/AI_NovelGenerator/` (large external dependency mirror)

If this is managed as submodule on your side, prefer:

1. upload `.gitmodules`
2. sync submodule pointers
3. clone with `git submodule update --init --recursive`

## 3. Do Not Upload

Keep local-only artifacts out of GitHub:

- `.venv/`
- `.ruff_cache/`
- `.pytest_cache/`
- `.mypy_cache/`
- `.claude/`
- `workspace/`
- `*.log`
- local secret files (`config.yaml`, `mcp.json`, `.env*` with real keys)
- frontend cache (`*.tsbuildinfo`)
- local runtime memory snapshots (`src/memory/*.md`)
- local smoke artifacts (`src/smoke_test*`)

## 4. Suggested Staging Commands

Core scope staging:

```powershell
git add .github docs scripts src tests examples .gitignore .gitmodules LICENSE MANIFEST.in pyproject.toml README.md HABITS.md TASKS.md uv.lock
```

If anything sensitive/local is accidentally staged, remove it before commit:

```powershell
git restore --staged src/apps/agent_studio_gateway/.env src/apps/qqbot_channel/.env
git restore --staged src/apps/agent_studio/tsconfig.app.tsbuildinfo src/apps/agent_studio/tsconfig.node.tsbuildinfo
git restore --staged src/memory/*.md src/smoke_test*
```

Optional extra:

```powershell
git add third_party/AI_NovelGenerator
```

## 5. Pre-Push Safety Checks

```powershell
git status --short
git diff --cached --name-only
```

Recommended quick scan before push:

```powershell
rg -n --hidden --glob '!workspace/**' --glob '!.venv/**' --glob '!.git/**' "sk-|api[_-]?key|token"
git diff --cached --name-only | rg "\.env$|\.tsbuildinfo$|^src/memory/|^src/smoke_test"
```

If the second command returns any lines, clean staging first and re-check.
