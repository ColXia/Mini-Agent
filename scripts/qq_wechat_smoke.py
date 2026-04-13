"""QQ + WeChat channel real-message smoke check.

This script spins up a local mock gateway, then validates:
1) QQ synthetic message flow via `src/apps/qqbot_channel/smoke_runner.mjs`
2) WeChat signed webhook GET/POST flows against a live channel process
3) hardening guardrails (workspace boundary, timestamp skew, body size, dedupe)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests


def _ensure(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


class _GatewayState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.next_session_id = 1
        self.sessions: dict[str, str] = {}
        self.request_log: list[dict[str, Any]] = []

    def alloc_session(self, key: str) -> str:
        with self.lock:
            existing = self.sessions.get(key)
            if existing:
                return existing
            session_id = f"smoke-session-{self.next_session_id:04d}"
            self.next_session_id += 1
            self.sessions[key] = session_id
            return session_id

    def record(self, entry: dict[str, Any]) -> None:
        with self.lock:
            self.request_log.append(entry)


class _GatewayHandler(BaseHTTPRequestHandler):
    state: _GatewayState
    expected_token: str

    def log_message(self, _format: str, *_args: Any) -> None:  # noqa: D401,ANN401
        # Keep smoke output compact and deterministic.
        return

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self, status: int, events: list[tuple[str, dict[str, Any]]]) -> None:
        parts: list[str] = []
        for event_name, payload in events:
            parts.append(f"event: {event_name}\n")
            parts.append(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n")
        body = "".join(parts).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _is_authorized(self) -> bool:
        expected = (self.expected_token or "").strip()
        if not expected:
            return True
        header = self.headers.get("Authorization", "")
        return header == f"Bearer {expected}"

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"invalid JSON body: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("request body must be a JSON object")
        return payload

    def _conversation_key(self, payload: dict[str, Any]) -> str:
        channel_type = str(payload.get("channel_type") or "unknown")
        conversation_id = str(payload.get("conversation_id") or "none")
        sender_id = str(payload.get("sender_id") or "none")
        return f"{channel_type}|{conversation_id}|{sender_id}"

    def _conversation_key_from_query(self, query: dict[str, list[str]]) -> str:
        channel_type = str((query.get("channel_type") or ["unknown"])[0] or "unknown")
        conversation_id = str((query.get("conversation_id") or ["none"])[0] or "none")
        sender_id = str((query.get("sender_id") or ["none"])[0] or "none")
        return f"{channel_type}|{conversation_id}|{sender_id}"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        authorized = self._is_authorized()
        query = parse_qs(parsed.query)

        if parsed.path == "/api/v1/system/health":
            if not authorized:
                self.state.record(
                    {"method": "GET", "path": parsed.path, "authorized": False, "status": 401}
                )
                self._send_json(401, {"error": "unauthorized"})
                return
            self.state.record(
                {"method": "GET", "path": parsed.path, "authorized": True, "status": 200}
            )
            self._send_json(200, {"status": "ok"})
            return

        if parsed.path == "/api/v1/agent/chat/stream":
            if not authorized:
                self.state.record(
                    {
                        "method": "GET",
                        "path": parsed.path,
                        "authorized": False,
                        "status": 401,
                        "kind": "chat",
                    }
                )
                self._send_json(401, {"error": "unauthorized"})
                return

            channel_type = str((query.get("channel_type") or ["unknown"])[0] or "unknown")
            message = str((query.get("message") or [""])[0] or "").strip()
            key = self._conversation_key_from_query(query)
            session_id = str((query.get("session_id") or [""])[0] or "").strip() or self.state.alloc_session(key)
            workspace_dir = str((query.get("workspace_dir") or [""])[0] or "")
            dry_run = str((query.get("dry_run") or ["false"])[0] or "").strip().lower() in {
                "1",
                "true",
                "on",
                "yes",
            }
            reply = f"smoke-reply[{channel_type}] {message}".strip()
            if dry_run:
                reply = f"{reply} [dry-run]".strip()

            self.state.record(
                {
                    "method": "GET",
                    "path": parsed.path,
                    "authorized": True,
                    "status": 200,
                    "kind": "chat",
                    "channel_type": channel_type,
                    "conversation_id": str((query.get("conversation_id") or [""])[0] or ""),
                    "sender_id": str((query.get("sender_id") or [""])[0] or ""),
                }
            )
            self._send_sse(
                200,
                [
                    ("session", {"session_id": session_id, "workspace_dir": workspace_dir}),
                    ("delta", {"chunk": reply}),
                    ("done", {"session_id": session_id, "reply": reply}),
                ],
            )
            return

        self.state.record({"method": "GET", "path": parsed.path, "authorized": authorized, "status": 404})
        self._send_text(404, "Not Found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        authorized = self._is_authorized()

        if parsed.path == "/api/v1/channel/message":
            if not authorized:
                self.state.record(
                    {"method": "POST", "path": parsed.path, "authorized": False, "status": 401}
                )
                self._send_json(401, {"error": "unauthorized"})
                return
            try:
                payload = self._read_json_body()
            except RuntimeError as exc:
                self.state.record(
                    {"method": "POST", "path": parsed.path, "authorized": True, "status": 400}
                )
                self._send_json(400, {"error": str(exc)})
                return

            key = self._conversation_key(payload)
            session_id = str(payload.get("session_id") or "").strip() or self.state.alloc_session(key)
            channel_type = str(payload.get("channel_type") or "unknown")
            message = str(payload.get("message") or "").strip()
            reply = f"smoke-reply[{channel_type}] {message}".strip()
            if bool(payload.get("dry_run")):
                reply = f"{reply} [dry-run]".strip()

            self.state.record(
                {
                    "method": "POST",
                    "path": parsed.path,
                    "authorized": True,
                    "status": 200,
                    "kind": "chat",
                    "channel_type": channel_type,
                    "conversation_id": str(payload.get("conversation_id") or ""),
                    "sender_id": str(payload.get("sender_id") or ""),
                }
            )
            self._send_json(
                200,
                {
                    "ok": True,
                    "data": {
                        "reply": reply,
                        "session_id": session_id,
                        "message_count": 1,
                        "token_usage": 0,
                        "workspace_dir": str(payload.get("workspace_dir") or ""),
                        "updated_at": "2026-04-06T00:00:00+00:00",
                    },
                    "error": None,
                },
            )
            return

        if parsed.path.startswith("/api/v1/agent/sessions/") and parsed.path.endswith("/reset"):
            if not authorized:
                self.state.record(
                    {"method": "POST", "path": parsed.path, "authorized": False, "status": 401}
                )
                self._send_json(401, {"error": "unauthorized"})
                return
            self.state.record(
                {"method": "POST", "path": parsed.path, "authorized": True, "status": 200}
            )
            session_id = parsed.path.split("/")[-2]
            self._send_json(
                200,
                {
                    "ok": True,
                    "data": {"status": "reset", "session_id": session_id},
                    "error": None,
                },
            )
            return

        self.state.record(
            {"method": "POST", "path": parsed.path, "authorized": authorized, "status": 404}
        )
        self._send_text(404, "Not Found")


def _start_mock_gateway(expected_token: str) -> tuple[ThreadingHTTPServer, threading.Thread, _GatewayState, str]:
    state = _GatewayState()
    handler = type("SmokeGatewayHandler", (_GatewayHandler,), {})
    handler.state = state
    handler.expected_token = expected_token
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    return server, thread, state, base_url


def _run_command(
    *,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: float,
) -> str:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = f"{result.stdout}\n{result.stderr}".strip()
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}\n{output}")
    return output


def _ensure_node_workspace_ready(
    *,
    package_dir: Path,
    timeout: float,
    require_dist: str | None = None,
) -> None:
    env = os.environ.copy()
    node_modules_dir = package_dir / "node_modules"
    if not node_modules_dir.exists():
        _run_command(
            cmd=[_node_bin("npm"), "ci"],
            cwd=package_dir,
            env=env,
            timeout=max(timeout, 180.0),
        )
    if require_dist is None:
        return
    dist_path = package_dir / require_dist
    if dist_path.exists():
        return
    _run_command(
        cmd=[_node_bin("npm"), "run", "build"],
        cwd=package_dir,
        env=env,
        timeout=max(timeout, 180.0),
    )


def _node_bin(name: str) -> str:
    if os.name != "nt":
        return name
    if name in {"npm", "npx"}:
        return f"{name}.cmd"
    if name == "node":
        return "node.exe"
    return name


def _wechat_sign(token: str, timestamp: str, nonce: str) -> str:
    raw = "".join(sorted([token, timestamp, nonce]))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _build_wechat_query(token: str, timestamp: str, nonce: str, echostr: str | None = None) -> str:
    params = {
        "signature": _wechat_sign(token, timestamp, nonce),
        "timestamp": timestamp,
        "nonce": nonce,
    }
    if echostr is not None:
        params["echostr"] = echostr
    return urlencode(params)


def _build_wechat_text_xml(*, to_user: str, from_user: str, msg_id: str, content: str) -> str:
    safe = content.replace("]]>", "]]]]><![CDATA[>")
    return (
        "<xml>"
        f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
        f"<CreateTime>{int(time.time())}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{safe}]]></Content>"
        f"<MsgId>{msg_id}</MsgId>"
        "</xml>"
    )


def _extract_xml_tag(xml: str, tag: str) -> str:
    cdata = re.search(rf"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>", xml, re.IGNORECASE | re.DOTALL)
    if cdata and cdata.group(1) is not None:
        return cdata.group(1).strip()
    plain = re.search(rf"<{tag}>(.*?)</{tag}>", xml, re.IGNORECASE | re.DOTALL)
    if plain and plain.group(1) is not None:
        return plain.group(1).strip()
    return ""


def _terminate_process(proc: subprocess.Popen[str]) -> str:
    if proc.poll() is None:
        proc.terminate()
        try:
            stdout, _ = proc.communicate(timeout=10)
            return stdout
        except subprocess.TimeoutExpired:
            proc.kill()
    stdout, _ = proc.communicate(timeout=5)
    return stdout


def _run_qq_smoke(
    *,
    repo_root: Path,
    gateway_base_url: str,
    gateway_auth_token: str,
    temp_dir: Path,
    workspace_root: Path,
    timeout: float,
) -> str:
    qq_workspace = (workspace_root / "qq_smoke_workspace").resolve()
    qq_workspace.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "MINI_AGENT_GATEWAY_BASE": gateway_base_url,
            "QQBOT_GATEWAY_AUTH_TOKEN": gateway_auth_token,
            "QQBOT_DEFAULT_WORKSPACE": str(qq_workspace),
            "QQBOT_DEFAULT_DRY_RUN": "true",
            "QQBOT_ALLOWED_WORKSPACE_ROOTS": str(qq_workspace),
            "QQBOT_SESSION_STORE_PATH": str((temp_dir / ".qqbot_smoke_sessions.json").resolve()),
            "QQBOT_MAX_MESSAGE_CHARS": "2000",
            "QQBOT_MAX_REPLY_CHUNK_SIZE": "900",
            "QQBOT_SMOKE_MESSAGE": "qq smoke hello",
        }
    )

    qq_dir = (repo_root / "src" / "apps" / "qqbot_channel").resolve()
    _ensure_node_workspace_ready(
        package_dir=qq_dir,
        timeout=timeout,
    )
    return _run_command(
        cmd=[_node_bin("npm"), "run", "smoke"],
        cwd=qq_dir,
        env=env,
        timeout=timeout,
    )


def _run_wechat_smoke(
    *,
    repo_root: Path,
    gateway_base_url: str,
    gateway_auth_token: str,
    temp_dir: Path,
    workspace_root: Path,
    webhook_port: int,
    webhook_path: str,
    wechat_token: str,
    max_body_bytes: int,
    max_timestamp_skew_seconds: int,
    timeout: float,
) -> dict[str, Any]:
    wechat_workspace = (workspace_root / "wechat_smoke_workspace").resolve()
    wechat_workspace.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "MINI_AGENT_GATEWAY_BASE": gateway_base_url,
            "WECHAT_GATEWAY_AUTH_TOKEN": gateway_auth_token,
            "WECHAT_TOKEN": wechat_token,
            "WECHAT_HOST": "127.0.0.1",
            "WECHAT_PORT": str(webhook_port),
            "WECHAT_PATH": webhook_path,
            "WECHAT_DEFAULT_WORKSPACE": str(wechat_workspace),
            "WECHAT_DEFAULT_DRY_RUN": "true",
            "WECHAT_SESSION_STORE_PATH": str((temp_dir / ".wechat_smoke_sessions.json").resolve()),
            "WECHAT_ALLOWED_WORKSPACE_ROOTS": str(wechat_workspace),
            "WECHAT_MAX_MESSAGE_CHARS": "2000",
            "WECHAT_MAX_RESPONSE_CHARS": "1000",
            "WECHAT_MAX_BODY_BYTES": str(max_body_bytes),
            "WECHAT_MAX_TIMESTAMP_SKEW_SECONDS": str(max_timestamp_skew_seconds),
            "WECHAT_DEDUPE_WINDOW_SIZE": "1000",
        }
    )

    wechat_dir = (repo_root / "src" / "channels" / "wechat").resolve()
    _ensure_node_workspace_ready(
        package_dir=wechat_dir,
        timeout=timeout,
        require_dist="dist/index.js",
    )
    proc = subprocess.Popen(  # noqa: S603
        [_node_bin("node"), "dist/index.js"],
        cwd=str(wechat_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    session = requests.Session()
    base_url = f"http://127.0.0.1:{webhook_port}{webhook_path}"
    startup_deadline = time.time() + timeout
    started = False

    try:
        while time.time() < startup_deadline:
            if proc.poll() is not None:
                output = _terminate_process(proc)
                raise RuntimeError(f"WeChat process exited before startup:\n{output}")

            ts = str(int(time.time()))
            nonce = f"n{int(time.time() * 1000) % 1000000000}"
            echostr = "wechat-smoke-echo"
            query = _build_wechat_query(wechat_token, ts, nonce, echostr=echostr)
            try:
                resp = session.get(f"{base_url}?{query}", timeout=2.0)
            except requests.RequestException:
                time.sleep(0.2)
                continue

            if resp.status_code == 200 and resp.text == echostr:
                started = True
                break
            time.sleep(0.2)

        _ensure(started, "WeChat channel did not become ready in time.")

        stale_ts = str(int(time.time()) - max(max_timestamp_skew_seconds + 120, 3600))
        stale_nonce = "stale-smoke"
        stale_query = _build_wechat_query(wechat_token, stale_ts, stale_nonce, echostr="stale")
        stale_resp = session.get(f"{base_url}?{stale_query}", timeout=timeout)
        _ensure(stale_resp.status_code == 401, "stale timestamp should be rejected with 401")

        def post_text(msg_id: str, content: str) -> requests.Response:
            ts = str(int(time.time()))
            nonce = f"n{int(time.time() * 1000) % 1000000000}"
            query = _build_wechat_query(wechat_token, ts, nonce)
            xml = _build_wechat_text_xml(
                to_user="mini-agent-app",
                from_user="smoke-user-001",
                msg_id=msg_id,
                content=content,
            )
            return session.post(
                f"{base_url}?{query}",
                data=xml.encode("utf-8"),
                headers={"Content-Type": "application/xml; charset=utf-8"},
                timeout=timeout,
            )

        first_resp = post_text("10001", "wechat smoke hello")
        _ensure(first_resp.status_code == 200, "wechat chat request failed")
        first_reply = _extract_xml_tag(first_resp.text, "Content")
        _ensure("smoke-reply[wechat]" in first_reply, "wechat chat reply missing gateway roundtrip content")

        dup_resp = post_text("10001", "wechat smoke hello")
        _ensure(dup_resp.status_code == 200, "wechat duplicate request should not fail")
        _ensure(dup_resp.text.strip() == "success", "wechat duplicate request should return success marker")

        reject_resp = post_text("10002", "/workspace C:/Windows")
        _ensure(reject_resp.status_code == 200, "wechat workspace command request failed")
        reject_reply = _extract_xml_tag(reject_resp.text, "Content")
        _ensure("Workspace rejected" in reject_reply, "wechat workspace boundary guardrail did not trigger")

        oversized_content = "x" * (max_body_bytes * 2)
        try:
            oversized_resp = post_text("10003", oversized_content)
            _ensure(
                400 <= oversized_resp.status_code < 600,
                f"wechat oversized body should be rejected, got {oversized_resp.status_code}",
            )
        except requests.RequestException:
            # Some runtime paths actively close the socket when oversized payload is detected.
            # This is still an acceptable hardening behavior for this smoke check.
            pass
        _ensure(proc.poll() is None, "wechat process exited after oversized-body guardrail check")

        return {
            "first_reply_length": len(first_reply),
            "duplicate_reply": dup_resp.text.strip(),
            "workspace_reject_reply": reject_reply,
        }
    finally:
        preexisting_code = proc.poll()
        output = _terminate_process(proc)
        if preexisting_code is not None and preexisting_code != 0:
            raise RuntimeError(f"WeChat process exited with code {preexisting_code}:\n{output}")


def run_smoke(args: argparse.Namespace) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    workspace_root = Path(args.workspace_root).resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    gateway_auth_token = (
        args.gateway_auth_token.strip()
        if args.gateway_auth_token is not None
        else (os.getenv("MINI_AGENT_GATEWAY_AUTH_TOKEN", "").strip() or "smoke-gateway-token")
    )

    gateway_server, gateway_thread, gateway_state, gateway_base_url = _start_mock_gateway(gateway_auth_token)
    print(f"[1/4] Mock gateway listening at {gateway_base_url}")

    with tempfile.TemporaryDirectory(prefix="qq_wechat_smoke_", dir=str(workspace_root)) as temp_dir_raw:
        temp_dir = Path(temp_dir_raw).resolve()
        try:
            print("[2/4] QQ synthetic flow smoke")
            qq_output = _run_qq_smoke(
                repo_root=repo_root,
                gateway_base_url=gateway_base_url,
                gateway_auth_token=gateway_auth_token,
                temp_dir=temp_dir,
                workspace_root=workspace_root,
                timeout=args.timeout,
            )
            _ensure('"status": "ok"' in qq_output, "QQ smoke runner did not return success payload")

            print("[3/4] WeChat webhook flow smoke")
            wechat_result = _run_wechat_smoke(
                repo_root=repo_root,
                gateway_base_url=gateway_base_url,
                gateway_auth_token=gateway_auth_token,
                temp_dir=temp_dir,
                workspace_root=workspace_root,
                webhook_port=args.wechat_port,
                webhook_path=args.wechat_path,
                wechat_token=args.wechat_token,
                max_body_bytes=args.max_body_bytes,
                max_timestamp_skew_seconds=args.max_timestamp_skew_seconds,
                timeout=args.timeout,
            )
        finally:
            gateway_server.shutdown()
            gateway_server.server_close()
            gateway_thread.join(timeout=5)

    print("[4/4] Validate gateway traffic coverage")
    chat_calls = [item for item in gateway_state.request_log if item.get("kind") == "chat"]
    channels_seen = {str(item.get("channel_type") or "") for item in chat_calls}
    _ensure("qq" in channels_seen, "gateway did not observe qq chat flow")
    _ensure("wechat" in channels_seen, "gateway did not observe wechat chat flow")
    if gateway_auth_token:
        _ensure(
            all(bool(item.get("authorized")) for item in chat_calls),
            "some channel chat requests were missing gateway auth header",
        )

    print("QQ + WeChat smoke check passed.")
    print(
        json.dumps(
            {
                "gateway_base_url": gateway_base_url,
                "chat_calls": len(chat_calls),
                "channels_seen": sorted(channels_seen),
                "wechat": wechat_result,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run QQ + WeChat channel smoke checks.")
    parser.add_argument(
        "--workspace-root",
        default=str((Path.cwd() / "workspace").resolve()),
        help="Workspace root used for temporary smoke assets.",
    )
    parser.add_argument(
        "--gateway-auth-token",
        default=None,
        help="Gateway auth token expected by mock gateway (defaults to env or smoke-gateway-token).",
    )
    parser.add_argument("--wechat-token", default="wechat-smoke-token", help="WeChat webhook token for signature check.")
    parser.add_argument("--wechat-port", type=int, default=18530, help="Temporary WeChat webhook port.")
    parser.add_argument("--wechat-path", default="/wechat/webhook", help="WeChat webhook path.")
    parser.add_argument("--max-body-bytes", type=int, default=2048, help="WeChat max body bytes for guardrail smoke.")
    parser.add_argument(
        "--max-timestamp-skew-seconds",
        type=int,
        default=600,
        help="WeChat timestamp skew guardrail used during smoke.",
    )
    parser.add_argument("--timeout", type=float, default=35.0, help="Timeout in seconds for each smoke stage.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        run_smoke(args)
    except Exception as exc:  # noqa: BLE001
        print(f"QQ + WeChat smoke check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
