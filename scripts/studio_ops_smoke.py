"""Agent Studio Ops contract smoke check.

Validates `/api/v1/ops/*` provider and memory contract paths against a live
agent-studio-gateway instance.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

import requests

from mini_agent.tools.note_tool import MarkdownMemoryStore


def _pick_first_token(raw: str) -> str:
    for item in raw.split(","):
        token = item.strip()
        if token:
            return token
    return ""


def _resolve_token(cli_token: str | None) -> str:
    if cli_token and cli_token.strip():
        return cli_token.strip()
    return _pick_first_token(os.getenv("MINI_AGENT_STUDIO_API_KEYS", ""))


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


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


def _ensure(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_smoke(args: argparse.Namespace) -> None:
    base_url = args.base_url.rstrip("/")
    token = _resolve_token(args.token)
    expect_auth = bool(token) if args.expect_auth is None else bool(args.expect_auth)
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    catalog_path = f"workspace/studio_smoke/providers_{run_id}.json"
    workspace_dir = (Path(args.workspace_root).resolve() / f"studio_smoke_mem_{run_id}").resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)

    store = MarkdownMemoryStore(memory_root=str(workspace_dir))
    now = datetime.now()
    store.append_note(content="studio smoke long-term note", category="smoke", scope="long_term", now=now)
    store.append_note(content="studio smoke daily note", category="smoke", scope="daily", now=now)
    day = now.date().isoformat()

    unauth_session = requests.Session()
    auth_session = requests.Session()
    auth_session.headers.update(headers)

    print("[1/8] auth boundary check")
    providers_url = _join_url(base_url, "/api/v1/ops/providers")
    if expect_auth:
        no_auth_resp = unauth_session.get(
            providers_url,
            params={"catalog_path": catalog_path},
            timeout=args.timeout,
        )
        _ensure(no_auth_resp.status_code == 401, "expected 401 without studio token")
        print("  unauthorized request blocked (401)")
    else:
        print("  auth not enforced for this smoke run")

    print("[2/8] provider create/list/update/health/delete")
    created = _request_json(
        session=auth_session,
        method="POST",
        url=providers_url,
        timeout=args.timeout,
        params={"catalog_path": catalog_path},
        json={
            "name": f"Studio Smoke Provider {run_id}",
            "api_type": "openai",
            "api_base": "https://api.openai.example.com/v1",
            "api_key": f"sk-studio-smoke-{run_id}",
            "models": ["gpt-4o-mini"],
            "enabled": True,
            "priority": 1,
            "timeout": 30,
            "headers": {"x-smoke": "1"},
        },
    )
    provider_id = str(created.get("id", "")).strip()
    _ensure(bool(provider_id), "provider create response missing id")

    listed = _request_json(
        session=auth_session,
        method="GET",
        url=providers_url,
        timeout=args.timeout,
        params={"catalog_path": catalog_path},
    )
    item_ids = {str(item.get("id", "")) for item in listed.get("items", []) if isinstance(item, dict)}
    _ensure(provider_id in item_ids, f"created provider {provider_id} not found in list")

    updated = _request_json(
        session=auth_session,
        method="PUT",
        url=_join_url(base_url, f"/api/v1/ops/providers/{provider_id}"),
        timeout=args.timeout,
        params={"catalog_path": catalog_path},
        json={
            "name": f"Studio Smoke Provider {run_id} Updated",
            "api_type": "openai",
            "api_base": "https://api.openai.example.com/v1",
            "api_key": f"sk-studio-smoke-{run_id}",
            "models": ["gpt-4o-mini", "gpt-4.1-mini"],
            "enabled": False,
            "priority": 2,
            "timeout": 60,
            "headers": {"x-smoke": "2"},
        },
    )
    _ensure(updated.get("enabled") is False, "provider update did not apply enabled=false")

    health = _request_json(
        session=auth_session,
        method="GET",
        url=_join_url(base_url, f"/api/v1/ops/providers/{provider_id}/health"),
        timeout=args.timeout,
        params={"catalog_path": catalog_path},
    )
    _ensure(str(health.get("provider_id", "")) == provider_id, "provider health response id mismatch")

    deleted = _request_json(
        session=auth_session,
        method="DELETE",
        url=_join_url(base_url, f"/api/v1/ops/providers/{provider_id}"),
        timeout=args.timeout,
        params={"catalog_path": catalog_path},
    )
    _ensure(deleted.get("status") == "deleted", "provider delete failed")

    print("[3/8] runtime diagnostics")
    runtime_diag = _request_json(
        session=auth_session,
        method="GET",
        url=_join_url(base_url, "/api/v1/ops/diagnostics/runtime"),
        timeout=args.timeout,
    )
    _ensure(runtime_diag.get("mode") in {"single_main", "team"}, "runtime diagnostics missing mode")
    _ensure(int(runtime_diag.get("max_active_sessions", 0)) >= 1, "runtime max_active_sessions must be >= 1")
    _ensure(int(runtime_diag.get("reserved_team_slots", 0)) >= 1, "runtime reserved_team_slots must be >= 1")
    _ensure(
        int(runtime_diag.get("team_saturation_rejections", -1)) >= 0,
        "runtime team_saturation_rejections must be >= 0",
    )
    _ensure(
        int(runtime_diag.get("team_workspace_conflict_rejections", -1)) >= 0,
        "runtime team_workspace_conflict_rejections must be >= 0",
    )
    runtime_report_file = (args.runtime_report_file or "").strip()
    if runtime_report_file:
        runtime_report_path = Path(runtime_report_file).expanduser().resolve()
        runtime_report_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_report_path.write_text(
            json.dumps(
                {
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "run_id": run_id,
                    "base_url": base_url,
                    "runtime": runtime_diag,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"  runtime diagnostics snapshot: {runtime_report_path}")

    print("[4/8] memory summary")
    summary = _request_json(
        session=auth_session,
        method="GET",
        url=_join_url(base_url, "/api/v1/ops/memory/summary"),
        timeout=args.timeout,
        params={"workspace_dir": str(workspace_dir)},
    )
    _ensure(int(summary.get("notes_count", 0)) >= 2, "memory summary notes_count < 2")

    print("[5/8] memory search")
    search = _request_json(
        session=auth_session,
        method="GET",
        url=_join_url(base_url, "/api/v1/ops/memory/search"),
        timeout=args.timeout,
        params={"workspace_dir": str(workspace_dir), "query": "studio smoke", "limit": 20},
    )
    _ensure(int(search.get("total", 0)) >= 2, "memory search total < 2")

    print("[6/8] memory daily")
    daily = _request_json(
        session=auth_session,
        method="GET",
        url=_join_url(base_url, f"/api/v1/ops/memory/daily/{day}"),
        timeout=args.timeout,
        params={"workspace_dir": str(workspace_dir)},
    )
    _ensure(str(daily.get("day", "")) == day, "daily response day mismatch")
    _ensure(int(daily.get("note_count", 0)) >= 1, "daily note_count < 1")

    print("[7/8] path boundary checks")
    outside_catalog = auth_session.get(
        providers_url,
        params={"catalog_path": "C:/Windows/providers.json"},
        timeout=args.timeout,
    )
    _ensure(outside_catalog.status_code == 400, "external catalog_path should be rejected with 400")

    outside_workspace = auth_session.get(
        _join_url(base_url, "/api/v1/ops/memory/summary"),
        params={"workspace_dir": "C:/Windows"},
        timeout=args.timeout,
    )
    _ensure(outside_workspace.status_code == 400, "external workspace_dir should be rejected with 400")

    print("[8/8] smoke completed")
    print("Studio Ops smoke check passed.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run smoke checks for /api/v1/ops contracts.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("MINI_AGENT_STUDIO_GATEWAY_BASE_URL", "http://127.0.0.1:8008"),
        help="Agent Studio Gateway base URL.",
    )
    parser.add_argument("--token", default=None, help="Studio API token. Defaults to first MINI_AGENT_STUDIO_API_KEYS token.")
    parser.add_argument(
        "--expect-auth",
        dest="expect_auth",
        action="store_true",
        default=None,
        help="Expect unauthorized requests to be blocked (401).",
    )
    parser.add_argument(
        "--no-expect-auth",
        dest="expect_auth",
        action="store_false",
        help="Do not require auth boundary in this run.",
    )
    parser.add_argument(
        "--workspace-root",
        default=str((Path.cwd() / "workspace").resolve()),
        help="Root path used to build temporary smoke workspace.",
    )
    parser.add_argument(
        "--runtime-report-file",
        default=None,
        help="Optional output path for runtime diagnostics snapshot JSON.",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout seconds.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        run_smoke(args)
    except Exception as exc:  # noqa: BLE001
        print(f"Studio Ops smoke check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

