# Mini-Agent Open WebUI Adapter

This app provides an OpenAI-compatible API layer for Open WebUI and forwards requests to Mini-Agent Gateway.

Flow:
- Open WebUI -> `/v1/models`, `/v1/chat/completions`
- Adapter (`src/apps/open_webui`) -> Mini-Agent Gateway `/api/v1/agent/chat`

## 0. Positioning

- OpenWebUI adapter is an optional compatibility entry only.
- Main product flow remains Studio + Gateway `/api/v1/*`.
- WebUI/OpenWebUI is currently paused as a primary surface in the terminal-first roadmap.
- Do not couple main business logic to OpenWebUI-only endpoints.

## 1. Local Run (adapter only)

From repo root `C:/Users/Conli/Mini-Agent`:

```powershell
uv pip install --python .\.venv\Scripts\python.exe -e . -r .\src\apps\open_webui\requirements.txt
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn apps.open_webui.main:app --host 127.0.0.1 --port 8010 --reload
```

Health:
- `http://127.0.0.1:8010/health`

## 2. Configure Open WebUI

Set Open WebUI to use:
- Base URL: `http://127.0.0.1:8010/v1`
- API Key: one of `MINI_AGENT_OPENWEBUI_API_KEYS`

## 3. Docker Compose

1) Copy env template:

```powershell
Copy-Item .\src\apps\open_webui\.env.example .\src\apps\open_webui\.env
```

2) Start adapter + Open WebUI (use existing external gateway):

```powershell
docker compose -f .\src\apps\open_webui\docker-compose.yml up -d
```

3) If you also want compose to start gateway:

```powershell
docker compose -f .\src\apps\open_webui\docker-compose.yml --profile with-gateway up -d
```

Open WebUI:
- `http://127.0.0.1:3000`

## 4. Key Environment Variables

- `MINI_AGENT_GATEWAY_URL`
  - Gateway base URL for adapter forwarding.
- `MINI_AGENT_GATEWAY_AUTH_TOKEN`
  - Optional gateway bearer token.
- `MINI_AGENT_OPENWEBUI_API_KEYS`
  - Comma-separated tokens accepted by adapter auth.
- `MINI_AGENT_OPENWEBUI_DEFAULT_MODEL`
  - Default model returned to Open WebUI.
- `MINI_AGENT_OPENWEBUI_MODELS`
  - Comma-separated model list for `/v1/models`.

## 5. Real-Endpoint Smoke Check

After adapter and gateway are up, run:

```powershell
.\.venv\Scripts\python.exe .\scripts\open_webui_verify.py

.\.venv\Scripts\python.exe .\scripts\open_webui_verify.py `
  --run-smoke `
  --adapter-base-url http://127.0.0.1:8010 `
  --api-key mini-agent-openwebui-token

.\.venv\Scripts\python.exe -m pytest -q .\tests\test_open_webui_adapter.py .\tests\test_open_webui_main.py
.\.venv\Scripts\python.exe .\scripts\open_webui_smoke.py `
  --adapter-base-url http://127.0.0.1:8010 `
  --api-key mini-agent-openwebui-token `
  --dry-run
```

Unified release gate (the old PowerShell helper is archived under `scripts/archive/`):

```powershell
.\.venv\Scripts\python.exe .\scripts\release_gate.py `
  --start-local-gateway `
  --openwebui-run-smoke `
  --openwebui-no-dry-run `
  --openwebui-adapter-base-url http://127.0.0.1:8010 `
  --openwebui-api-key mini-agent-openwebui-token `
  --studio-token studio-smoke-token
```

Common overrides:

```powershell
.\.venv\Scripts\python.exe .\scripts\release_gate.py `
  --start-local-gateway `
  --openwebui-run-smoke `
  --openwebui-no-dry-run `
  --openwebui-adapter-base-url http://127.0.0.1:8010 `
  --openwebui-api-key mini-agent-openwebui-token `
  --openwebui-timeout 300 `
  --studio-token studio-smoke-token
```

Smoke check covers:
- `/health`
- `/v1/models`
- `/v1/chat/completions` (non-stream + stream)
- session continuity on same `conversation_id`

Use `--no-dry-run` only when gateway LLM credentials are fully configured.

## 6. Deployment Guardrails

- Always set non-empty `MINI_AGENT_OPENWEBUI_API_KEYS` in non-local environments.
- If `MINI_AGENT_GATEWAY_URL` is not local (`127.0.0.1/localhost`), set `MINI_AGENT_GATEWAY_AUTH_TOKEN`.
- Keep `MINI_AGENT_OPENWEBUI_DEFAULT_MODEL` inside `MINI_AGENT_OPENWEBUI_MODELS`.
- Keep `MINI_AGENT_OPENWEBUI_PRIMARY_API_KEY` included in `MINI_AGENT_OPENWEBUI_API_KEYS`.
- Check `GET /health`:
  - `guardrail_warning_count` should be `0` before production rollout.
