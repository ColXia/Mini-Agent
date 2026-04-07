"""Open WebUI OpenAI-compatible adapter app for Mini-Agent Gateway."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from apps.open_webui.adapter import (
    AdapterChatResult,
    OpenWebUIAdapter,
    OpenWebUIAdapterConfig,
    OpenWebUIAdapterError,
)


def _utc_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _normalize_api_keys(keys: tuple[str, ...]) -> set[str]:
    return {item.strip() for item in keys if item and item.strip()}


def _is_local_gateway_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "::1", "host.docker.internal"}


def _build_guardrail_warnings(
    *,
    config: OpenWebUIAdapterConfig,
    env: dict[str, str] | None = None,
) -> list[str]:
    source = env or {}
    warnings: list[str] = []
    allowed = _normalize_api_keys(config.adapter_api_keys)
    if not allowed:
        warnings.append(
            "adapter_auth_disabled: MINI_AGENT_OPENWEBUI_API_KEYS is empty; /v1 endpoints are public."
        )

    if not _is_local_gateway_url(config.gateway_base_url) and not config.gateway_auth_token:
        warnings.append(
            "gateway_auth_missing: non-local gateway configured without MINI_AGENT_GATEWAY_AUTH_TOKEN."
        )

    if config.default_model not in set(config.available_models):
        warnings.append(
            "default_model_not_listed: MINI_AGENT_OPENWEBUI_DEFAULT_MODEL is not in MINI_AGENT_OPENWEBUI_MODELS."
        )

    primary_key = (source.get("MINI_AGENT_OPENWEBUI_PRIMARY_API_KEY") or "").strip()
    if primary_key and allowed and primary_key not in allowed:
        warnings.append(
            "primary_key_not_allowed: MINI_AGENT_OPENWEBUI_PRIMARY_API_KEY is not included in MINI_AGENT_OPENWEBUI_API_KEYS."
        )

    if config.timeout_seconds > 300:
        warnings.append(
            "timeout_too_high: MINI_AGENT_OPENWEBUI_TIMEOUT_SECONDS > 300 may delay failure detection."
        )
    return warnings


class OpenAIMessage(BaseModel):
    """OpenAI chat message payload."""

    role: str
    content: str | list[dict[str, Any] | str] | dict[str, Any]


class ChatCompletionsRequest(BaseModel):
    """OpenAI chat completions request payload."""

    model: str | None = None
    messages: list[OpenAIMessage] = Field(default_factory=list)
    stream: bool = False
    user: str | None = None
    metadata: dict[str, Any] | None = None


class ModelsResponse(BaseModel):
    object: str
    data: list[dict[str, Any]]


def _require_adapter_auth(
    *,
    request: Request,
    config: OpenWebUIAdapterConfig,
    authorization: str | None,
    x_api_key: str | None,
) -> None:
    allowed = _normalize_api_keys(config.adapter_api_keys)
    if not allowed:
        return

    token = ""
    if authorization:
        lower = authorization.lower()
        if lower.startswith("bearer "):
            token = authorization[7:].strip()
    if not token and x_api_key:
        token = x_api_key.strip()
    if token and token in allowed:
        return
    raise HTTPException(status_code=401, detail="Unauthorized. Provide valid OpenWebUI adapter token.")


def _completion_payload(
    *,
    request_model: str,
    result: AdapterChatResult,
) -> dict[str, Any]:
    completion_id = f"chatcmpl-{uuid4().hex[:18]}"
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": _utc_timestamp(),
        "model": request_model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result.reply,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": max(0, result.token_usage),
            "total_tokens": max(0, result.token_usage),
        },
        "session_id": result.session_id,
    }


def _completion_stream(
    *,
    request_model: str,
    result: AdapterChatResult,
    chunk_size: int = 120,
):
    completion_id = f"chatcmpl-{uuid4().hex[:18]}"

    start_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": _utc_timestamp(),
        "model": request_model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant"},
                "finish_reason": None,
            }
        ],
    }
    yield f"data: {json.dumps(start_chunk, ensure_ascii=False)}\n\n"

    text = result.reply or ""
    for idx in range(0, len(text), max(1, int(chunk_size))):
        chunk = text[idx : idx + max(1, int(chunk_size))]
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": _utc_timestamp(),
            "model": request_model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": chunk},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    end_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": _utc_timestamp(),
        "model": request_model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }
        ],
    }
    yield f"data: {json.dumps(end_chunk, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def create_open_webui_adapter_app(
    *,
    config: OpenWebUIAdapterConfig | None = None,
    adapter: OpenWebUIAdapter | None = None,
) -> FastAPI:
    """Create Open WebUI adapter app."""
    resolved_config = config or OpenWebUIAdapterConfig.from_env(dict(os.environ))
    resolved_adapter = adapter or OpenWebUIAdapter(config=resolved_config)
    resolved_env = dict(os.environ)
    guardrail_warnings = _build_guardrail_warnings(config=resolved_config, env=resolved_env)

    app = FastAPI(
        title="Mini-Agent Open WebUI Adapter",
        version="0.1.0",
        description="OpenAI-compatible adapter for Open WebUI to connect Mini-Agent Gateway.",
    )
    app.state.openwebui_config = resolved_config
    app.state.openwebui_adapter = resolved_adapter
    app.state.openwebui_guardrail_warnings = tuple(guardrail_warnings)

    logger = logging.getLogger(__name__)
    for warning in guardrail_warnings:
        logger.warning("OpenWebUI adapter guardrail warning: %s", warning)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        warnings = list(app.state.openwebui_guardrail_warnings)
        return {
            "status": "ok",
            "gateway_base_url": resolved_config.gateway_base_url,
            "default_model": resolved_config.default_model,
            "guardrail_warning_count": len(warnings),
            "guardrail_warnings": warnings,
        }

    @app.get("/v1/models", response_model=ModelsResponse)
    async def list_models(
        request: Request,
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
    ) -> ModelsResponse:
        _require_adapter_auth(
            request=request,
            config=resolved_config,
            authorization=authorization,
            x_api_key=x_api_key,
        )
        models = resolved_adapter.list_models()
        return ModelsResponse(
            object="list",
            data=[
                {
                    "id": model_id,
                    "object": "model",
                    "owned_by": "mini-agent",
                }
                for model_id in models
            ],
        )

    @app.post("/v1/chat/completions")
    async def chat_completions(
        payload: ChatCompletionsRequest,
        request: Request,
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
    ):
        _require_adapter_auth(
            request=request,
            config=resolved_config,
            authorization=authorization,
            x_api_key=x_api_key,
        )

        if not payload.messages:
            raise HTTPException(status_code=400, detail="messages must not be empty.")

        try:
            result = resolved_adapter.chat(
                messages=[item.model_dump() for item in payload.messages],
                user=payload.user,
                metadata=payload.metadata,
            )
        except OpenWebUIAdapterError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        model_name = (payload.model or resolved_config.default_model).strip() or resolved_config.default_model
        if payload.stream:
            return StreamingResponse(
                _completion_stream(request_model=model_name, result=result),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        return JSONResponse(content=_completion_payload(request_model=model_name, result=result))

    return app


app = create_open_webui_adapter_app()
