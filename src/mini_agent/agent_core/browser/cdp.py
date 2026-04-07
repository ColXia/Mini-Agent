"""CDP operation baseline with navigation policy guard."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import inspect
import ipaddress
import json
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit


_MINIMAL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+M1sAAAAASUVORK5CYII="
)


class BrowserCdpError(RuntimeError):
    """Base browser CDP error."""


class BrowserNavigationError(BrowserCdpError):
    """Raised when navigation URL is blocked by policy."""


def _normalize_domain(value: str) -> str:
    return value.strip().lower().strip(".")


def _domain_matches(hostname: str, rule: str) -> bool:
    return hostname == rule or hostname.endswith(f".{rule}")


def _is_private_host(hostname: str) -> bool:
    lowered = hostname.lower()
    if lowered in {"localhost", "localhost.localdomain"}:
        return True
    if lowered.endswith(".local"):
        return True
    try:
        ip_value = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return (
        ip_value.is_private
        or ip_value.is_loopback
        or ip_value.is_link_local
        or ip_value.is_multicast
        or ip_value.is_reserved
        or ip_value.is_unspecified
    )


@dataclass(frozen=True)
class BrowserNavigationPolicy:
    """Navigation allow/block policy for browser URLs."""

    allow_schemes: tuple[str, ...] = ("http", "https")
    allow_domains: tuple[str, ...] = ()
    block_domains: tuple[str, ...] = ()
    allow_private_hosts: bool = False

    def normalized(self) -> "BrowserNavigationPolicy":
        schemes = tuple(sorted({_normalize_domain(item) for item in self.allow_schemes if item and item.strip()}))
        allow = tuple(sorted({_normalize_domain(item) for item in self.allow_domains if item and item.strip()}))
        blocked = tuple(sorted({_normalize_domain(item) for item in self.block_domains if item and item.strip()}))
        return BrowserNavigationPolicy(
            allow_schemes=schemes or ("http", "https"),
            allow_domains=allow,
            block_domains=blocked,
            allow_private_hosts=bool(self.allow_private_hosts),
        )

    def validate_url(self, raw_url: str) -> str:
        url = raw_url.strip()
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()
        policy = self.normalized()

        if not url:
            raise BrowserNavigationError("navigation URL must not be empty.")
        if scheme not in policy.allow_schemes:
            raise BrowserNavigationError(f"navigation scheme is not allowed: {scheme or '<missing>'}")
        if not host:
            raise BrowserNavigationError("navigation URL must include a hostname.")
        if not policy.allow_private_hosts and _is_private_host(host):
            raise BrowserNavigationError(f"navigation host is blocked by private-host policy: {host}")

        if policy.allow_domains and not any(_domain_matches(host, item) for item in policy.allow_domains):
            raise BrowserNavigationError(f"navigation host is not in allowlist: {host}")
        if policy.block_domains and any(_domain_matches(host, item) for item in policy.block_domains):
            raise BrowserNavigationError(f"navigation host is in blocklist: {host}")
        return url


@dataclass(frozen=True)
class BrowserTab:
    """One browser tab record from CDP target listing."""

    target_id: str
    title: str
    url: str
    type: str = "page"
    attached: bool = False


@dataclass(frozen=True)
class BrowserActCommand:
    """High-level action command translated into JavaScript eval."""

    kind: str
    selector: str | None = None
    text: str | None = None
    key: str | None = None
    milliseconds: int | None = None

    def __post_init__(self) -> None:
        kind = self.kind.strip().lower()
        if kind not in {"click", "type", "press", "wait"}:
            raise ValueError("browser action kind must be one of click/type/press/wait.")
        object.__setattr__(self, "kind", kind)
        if self.selector is not None:
            selector = self.selector.strip()
            object.__setattr__(self, "selector", selector or None)
        if self.text is not None:
            object.__setattr__(self, "text", str(self.text))
        if self.key is not None:
            key = self.key.strip()
            object.__setattr__(self, "key", key or None)
        if self.milliseconds is not None:
            object.__setattr__(self, "milliseconds", max(1, int(self.milliseconds)))
        self._validate()

    def _validate(self) -> None:
        if self.kind in {"click", "type"} and not self.selector:
            raise ValueError(f"browser action '{self.kind}' requires selector.")
        if self.kind == "press" and not self.key:
            raise ValueError("browser action 'press' requires key.")


@dataclass(frozen=True)
class BrowserActResult:
    """Action execution result."""

    ok: bool
    kind: str
    message: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowserScreenshot:
    """Screenshot payload."""

    content: bytes
    image_format: str
    byte_size: int


CdpTransport = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class CdpClient:
    """Lean CDP client contract for browser baseline."""

    def __init__(
        self,
        *,
        transport: CdpTransport | None = None,
        navigation_policy: BrowserNavigationPolicy | None = None,
    ) -> None:
        self._transport = transport
        self.navigation_policy = navigation_policy or BrowserNavigationPolicy()

    async def list_tabs(self) -> tuple[BrowserTab, ...]:
        payload = await self._send("Target.getTargets", {})
        target_infos = payload.get("targetInfos", [])
        if not isinstance(target_infos, list):
            return ()

        tabs: list[BrowserTab] = []
        for item in target_infos:
            if not isinstance(item, dict):
                continue
            target_id = str(item.get("targetId", "")).strip()
            if not target_id:
                continue
            tabs.append(
                BrowserTab(
                    target_id=target_id,
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    type=str(item.get("type", "page")),
                    attached=bool(item.get("attached", False)),
                )
            )
        return tuple(tabs)

    async def navigate(
        self,
        *,
        url: str,
        policy: BrowserNavigationPolicy | None = None,
    ) -> str:
        active_policy = policy or self.navigation_policy
        safe_url = active_policy.validate_url(url)
        payload = await self._send("Target.createTarget", {"url": safe_url})
        target_id = str(payload.get("targetId", "")).strip()
        if not target_id:
            raise BrowserCdpError("CDP navigate failed: missing targetId.")
        return target_id

    async def capture_screenshot(
        self,
        *,
        full_page: bool = False,
        image_format: str = "png",
        quality: int = 85,
    ) -> BrowserScreenshot:
        fmt = image_format.strip().lower()
        if fmt not in {"png", "jpeg"}:
            raise ValueError("image_format must be png or jpeg.")

        params: dict[str, Any] = {
            "format": fmt,
            "captureBeyondViewport": bool(full_page),
        }
        if fmt == "jpeg":
            params["quality"] = max(0, min(100, int(quality)))

        payload = await self._send("Page.captureScreenshot", params)
        encoded = str(payload.get("data", "")).strip()
        if not encoded:
            raise BrowserCdpError("CDP screenshot failed: missing base64 payload.")
        try:
            content = base64.b64decode(encoded, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise BrowserCdpError(f"CDP screenshot payload decode failed: {exc}") from exc
        return BrowserScreenshot(content=content, image_format=fmt, byte_size=len(content))

    async def act(self, command: BrowserActCommand) -> BrowserActResult:
        expression = self._action_expression(command)
        payload = await self._send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
                "userGesture": True,
            },
        )
        if isinstance(payload.get("exceptionDetails"), dict):
            details = payload["exceptionDetails"]
            text = str(details.get("text", "execution failed")).strip() or "execution failed"
            return BrowserActResult(ok=False, kind=command.kind, message=text, raw=payload)

        result_block = payload.get("result", {})
        value = result_block.get("value", True) if isinstance(result_block, dict) else True
        ok = bool(value)
        return BrowserActResult(ok=ok, kind=command.kind, message=("ok" if ok else "action returned false"), raw=payload)

    async def _send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._transport is None:
            return self._default_response(method, params)
        payload = await _maybe_await(self._transport(method, dict(params)))
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            raise TypeError("CDP transport must return dict payloads.")
        return dict(payload)

    @staticmethod
    def _default_response(method: str, _params: dict[str, Any]) -> dict[str, Any]:
        if method == "Target.getTargets":
            return {"targetInfos": []}
        if method == "Target.createTarget":
            return {"targetId": "tab-stub-1"}
        if method == "Page.captureScreenshot":
            return {"data": _MINIMAL_PNG_BASE64}
        if method == "Runtime.evaluate":
            return {"result": {"value": True}}
        return {}

    @staticmethod
    def _action_expression(command: BrowserActCommand) -> str:
        if command.kind == "click":
            selector = json.dumps(command.selector or "")
            return (
                "(() => {"
                f"const el = document.querySelector({selector});"
                "if (!el) return false;"
                "el.click();"
                "return true;"
                "})()"
            )
        if command.kind == "type":
            selector = json.dumps(command.selector or "")
            text = json.dumps(command.text or "")
            return (
                "(() => {"
                f"const el = document.querySelector({selector});"
                "if (!el) return false;"
                "el.focus();"
                f"el.value = {text};"
                "el.dispatchEvent(new Event('input', { bubbles: true }));"
                "el.dispatchEvent(new Event('change', { bubbles: true }));"
                "return true;"
                "})()"
            )
        if command.kind == "press":
            key = json.dumps(command.key or "")
            return (
                "(() => {"
                f"document.dispatchEvent(new KeyboardEvent('keydown', {{ key: {key}, bubbles: true }}));"
                "return true;"
                "})()"
            )
        wait_ms = max(1, int(command.milliseconds or 250))
        return f"(() => new Promise((resolve) => setTimeout(() => resolve(true), {wait_ms})))()"
