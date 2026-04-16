# Legacy Script Archive

> Archived: 2026-04-12

These scripts are kept only for historical reference. They are not current entrypoints.

## Archived items

- `run_agent_studio.ps1`
  - Old Studio/WebUI launcher. It points to pre-`src/` paths and no longer matches the terminal-first development path.
- `run_qqbot_channel.ps1`
  - Old QQ launcher with hard-coded personal filesystem paths.
- `run_wechat_channel.ps1`
  - Old WeChat launcher with hard-coded personal filesystem paths.
- `run_release_gate_openwebui.ps1`
  - Old OpenWebUI helper kept only because the browser/OpenWebUI adapter was removed from the active product path.

## Current replacements

- Runtime stack: `uv run mini-agent stack up` or `scripts/start_runtime_stack.ps1`
- Terminal entry: `uv run mini`
- Release gate: `python scripts/ci/release_gate.py --start-local-gateway`
- Promotion checklist: `python scripts/ci/release_promotion_checklist.py`
