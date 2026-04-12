"""Open WebUI adapter real-endpoint smoke check.

This script verifies OpenAI-compatible adapter endpoints against a live adapter
instance and (optionally) a live gateway behind it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import requests


def _resolve_api_key(cli_key: str | None) -> str:
    if cli_key and cli_key.strip():
        return cli_key.strip()

    primary = (os.getenv("MINI_AGENT_OPENWEBUI_PRIMARY_API_KEY") or "").strip()
    if primary:
        return primary

    raw = os.getenv("MINI_AGENT_OPENWEBUI_API_KEYS", "")
    for item in raw.split(","):
        token = item.strip()
        if token:
            return token
    raise RuntimeError("No API key found. Pass --api-key or set MINI_AGENT_OPENWEBUI_PRIMARY_API_KEY.")


def _normalize_base_url(raw: str) -> str:
    value = (raw or "").strip().rstrip("/")
    if not value:
        raise RuntimeError("adapter base url is empty.")
    return value


def _request_json(
    *,
    session: requests.Session,
    method: str,
    url: str,
    timeout: float,
    **kwargs: Any,
) -> dict[str, Any]:
    response = session.request(method=method, url=url, timeout=timeout, **kwargs)
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code} from {url}: {response.text}")
    try:
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Invalid JSON from {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object from {url}, got: {type(payload).__name__}")
    return payload


def _stream_chat_completion(
    *,
    session: requests.Session,
    url: str,
    payload: dict[str, Any],
    timeout: float,
) -> str:
    response = session.post(url=url, json=payload, timeout=timeout, stream=True)
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code} from stream endpoint: {response.text}")

    collected: list[str] = []
    saw_done = False
    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        if not raw_line.startswith("data: "):
            continue
        data = raw_line[6:]
        if data == "[DONE]":
            saw_done = True
            break
        chunk = json.loads(data)
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        text = delta.get("content")
        if text:
            collected.append(str(text))

    if not saw_done:
        raise RuntimeError("Stream response did not end with [DONE].")
    return "".join(collected)


def run_smoke(args: argparse.Namespace) -> None:
    base_url = _normalize_base_url(args.adapter_base_url)
    v1_base = f"{base_url}/v1"
    api_key = _resolve_api_key(args.api_key)
    model = (args.model or os.getenv("MINI_AGENT_OPENWEBUI_DEFAULT_MODEL") or "mini-agent").strip()
    conversation_id = args.conversation_id or f"smoke-{int(time.time())}"

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    )

    print(f"[1/5] GET {base_url}/health")
    health = _request_json(session=session, method="GET", url=f"{base_url}/health", timeout=args.timeout)
    if health.get("status") != "ok":
        raise RuntimeError(f"Adapter health is not ok: {health}")
    print(f"  health ok, guardrail_warning_count={health.get('guardrail_warning_count', 0)}")

    print(f"[2/5] GET {v1_base}/models")
    models = _request_json(session=session, method="GET", url=f"{v1_base}/models", timeout=args.timeout)
    model_ids = [str(item.get("id", "")) for item in models.get("data", []) if isinstance(item, dict)]
    if model not in model_ids:
        print(f"  requested model '{model}' not in model list, fallback to first available")
        if not model_ids:
            raise RuntimeError("No models returned by /v1/models.")
        model = model_ids[0]
    print(f"  models={model_ids}")

    print("[3/5] POST /v1/chat/completions (first turn)")
    first_payload = _request_json(
        session=session,
        method="POST",
        url=f"{v1_base}/chat/completions",
        timeout=args.timeout,
        json={
            "model": model,
            "messages": [{"role": "user", "content": "smoke test turn 1"}],
            "user": args.user,
            "metadata": {
                "conversation_id": conversation_id,
                "dry_run": bool(args.dry_run),
            },
            "stream": False,
        },
    )
    first_session_id = str(first_payload.get("session_id", "")).strip()
    if not first_session_id:
        raise RuntimeError(f"First completion missing session_id: {first_payload}")
    print(f"  session_id={first_session_id}")

    print("[4/5] POST /v1/chat/completions (same conversation, expect same session)")
    second_payload = _request_json(
        session=session,
        method="POST",
        url=f"{v1_base}/chat/completions",
        timeout=args.timeout,
        json={
            "model": model,
            "messages": [{"role": "user", "content": "smoke test turn 2"}],
            "user": args.user,
            "metadata": {
                "conversation_id": conversation_id,
                "dry_run": bool(args.dry_run),
            },
            "stream": False,
        },
    )
    second_session_id = str(second_payload.get("session_id", "")).strip()
    if second_session_id != first_session_id:
        raise RuntimeError(
            f"Session continuity failed: first={first_session_id}, second={second_session_id}"
        )
    print(f"  session continuity ok ({second_session_id})")

    print("[5/5] POST /v1/chat/completions (stream)")
    stream_reply = _stream_chat_completion(
        session=session,
        url=f"{v1_base}/chat/completions",
        timeout=args.timeout,
        payload={
            "model": model,
            "messages": [{"role": "user", "content": "smoke stream turn"}],
            "user": args.user,
            "metadata": {
                "conversation_id": conversation_id,
                "dry_run": bool(args.dry_run),
            },
            "stream": True,
        },
    )
    if not stream_reply.strip():
        raise RuntimeError("Stream completion returned empty content.")
    print(f"  stream reply length={len(stream_reply)}")
    print("Open WebUI smoke check passed.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real-endpoint smoke checks for Open WebUI adapter.")
    parser.add_argument(
        "--adapter-base-url",
        default=os.getenv("MINI_AGENT_OPENWEBUI_ADAPTER_BASE_URL", "http://127.0.0.1:8010"),
        help="Adapter base URL, e.g. http://127.0.0.1:8010",
    )
    parser.add_argument("--api-key", default=None, help="Adapter auth token. If omitted, resolve from env.")
    parser.add_argument("--model", default=None, help="Model id to request in chat completions.")
    parser.add_argument("--user", default="smoke-user", help="User id used for conversation key mapping.")
    parser.add_argument(
        "--conversation-id",
        default=None,
        help="Conversation id to test session continuity. Defaults to a timestamp-based id.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Pass metadata.dry_run=true to gateway (default: true).",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_false",
        dest="dry_run",
        help="Disable metadata.dry_run flag and run real LLM path.",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout in seconds.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        run_smoke(args)
    except Exception as exc:  # noqa: BLE001
        print(f"Open WebUI smoke check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
