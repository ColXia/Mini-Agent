"""Tests for P15 T3.6 browser baseline."""

from __future__ import annotations

import base64

import pytest

from mini_agent.agent_core import (
    AgentBrowserToolkit,
    BrowserActCommand,
    BrowserNavigationError,
    BrowserNavigationPolicy,
    BrowserProfile,
    CdpClient,
    ChromeLifecycleManager,
)


@pytest.mark.asyncio
async def test_chrome_lifecycle_register_start_health_stop():
    started: list[str] = []
    stopped: list[str] = []

    async def _start(profile: BrowserProfile):
        started.append(profile.name)
        return {"pid": 4321, "metadata": {"driver": "stub"}}

    async def _stop(state):  # noqa: ANN001
        stopped.append(state.profile.name)

    async def _health(state):  # noqa: ANN001
        return state.running

    manager = ChromeLifecycleManager(
        start_handler=_start,
        stop_handler=_stop,
        health_handler=_health,
    )
    manager.register_profile(BrowserProfile(name="default", cdp_url="http://127.0.0.1:9222"))

    started_state = await manager.start("default")
    assert started_state.running is True
    assert started_state.pid == 4321

    healthy = await manager.health("default")
    assert healthy is True
    latest = manager.get_profile("default")
    assert latest is not None
    assert latest.last_healthy_utc is not None

    stopped_state = await manager.stop("default")
    assert stopped_state.running is False
    assert started == ["default"]
    assert stopped == ["default"]


def test_navigation_policy_blocks_private_hosts_and_enforces_allowlist():
    policy = BrowserNavigationPolicy()
    assert policy.validate_url("https://example.com/path?q=1") == "https://example.com/path?q=1"

    with pytest.raises(BrowserNavigationError):
        policy.validate_url("http://127.0.0.1:9222/json/version")

    with pytest.raises(BrowserNavigationError):
        policy.validate_url("http://localhost:8000")

    allowlist = BrowserNavigationPolicy(allow_domains=("example.com",))
    assert allowlist.validate_url("https://docs.example.com/guide").startswith("https://docs.example.com")

    with pytest.raises(BrowserNavigationError):
        allowlist.validate_url("https://evil.com")


@pytest.mark.asyncio
async def test_cdp_client_navigate_tabs_screenshot_and_action():
    calls: list[tuple[str, dict[str, object]]] = []
    encoded = base64.b64encode(b"fake-image").decode("ascii")

    async def _transport(method: str, params: dict[str, object]) -> dict[str, object]:
        calls.append((method, dict(params)))
        if method == "Target.createTarget":
            return {"targetId": "tab-1"}
        if method == "Target.getTargets":
            return {
                "targetInfos": [
                    {
                        "targetId": "tab-1",
                        "title": "Example",
                        "url": "https://example.com",
                        "type": "page",
                        "attached": True,
                    }
                ]
            }
        if method == "Page.captureScreenshot":
            return {"data": encoded}
        if method == "Runtime.evaluate":
            return {"result": {"value": True}}
        return {}

    client = CdpClient(transport=_transport)
    target_id = await client.navigate(url="https://example.com")
    tabs = await client.list_tabs()
    screenshot = await client.capture_screenshot(full_page=True, image_format="jpeg", quality=80)
    action = await client.act(BrowserActCommand(kind="click", selector="#submit"))

    assert target_id == "tab-1"
    assert len(tabs) == 1
    assert tabs[0].target_id == "tab-1"
    assert screenshot.content == b"fake-image"
    assert screenshot.byte_size == len(b"fake-image")
    assert action.ok is True
    assert [item[0] for item in calls] == [
        "Target.createTarget",
        "Target.getTargets",
        "Page.captureScreenshot",
        "Runtime.evaluate",
    ]


@pytest.mark.asyncio
async def test_agent_browser_toolkit_auto_start_and_guarded_navigation():
    starts = 0
    captured: list[tuple[str, dict[str, object]]] = []
    encoded = base64.b64encode(b"shot").decode("ascii")

    async def _start(_profile):  # noqa: ANN001
        nonlocal starts
        starts += 1
        return {"pid": 1001}

    async def _transport(method: str, params: dict[str, object]) -> dict[str, object]:
        captured.append((method, dict(params)))
        if method == "Target.createTarget":
            return {"targetId": "tab-42"}
        if method == "Target.getTargets":
            return {
                "targetInfos": [
                    {
                        "targetId": "tab-42",
                        "title": "Mini-Agent",
                        "url": "https://example.com",
                        "type": "page",
                    }
                ]
            }
        if method == "Page.captureScreenshot":
            return {"data": encoded}
        return {"result": {"value": True}}

    manager = ChromeLifecycleManager(start_handler=_start)
    manager.register_profile(BrowserProfile(name="default", cdp_url="https://cdp.example.com"))

    toolkit = AgentBrowserToolkit(
        lifecycle=manager,
        navigation_policy=BrowserNavigationPolicy(allow_domains=("example.com",)),
        client_factory=lambda _state: CdpClient(transport=_transport),
    )

    target_id = await toolkit.browser_navigate("default", "https://example.com/page")
    tabs = await toolkit.browser_tabs("default")
    shot = await toolkit.browser_screenshot("default", full_page=True)
    act = await toolkit.browser_act(
        "default",
        {"kind": "type", "selector": "#q", "text": "mini-agent"},
    )
    profiles = await toolkit.browser_profiles()

    assert target_id == "tab-42"
    assert len(tabs) == 1
    assert shot.content == b"shot"
    assert act.ok is True
    assert len(profiles) == 1
    assert profiles[0].running is True
    assert profiles[0].healthy is True
    assert starts == 1

    with pytest.raises(BrowserNavigationError):
        await toolkit.browser_navigate("default", "http://127.0.0.1/internal")
