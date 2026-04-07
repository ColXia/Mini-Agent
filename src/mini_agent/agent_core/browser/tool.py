"""Agent-facing browser tool baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from mini_agent.agent_core.browser.cdp import (
    BrowserActCommand,
    BrowserActResult,
    BrowserNavigationPolicy,
    BrowserScreenshot,
    BrowserTab,
    CdpClient,
)
from mini_agent.agent_core.browser.chrome import BrowserProfile, BrowserProfileState, ChromeLifecycleManager


@dataclass(frozen=True)
class BrowserProfileStatus:
    """Compact profile status for browser_profiles output."""

    name: str
    cdp_url: str
    running: bool
    healthy: bool
    pid: int | None = None


BrowserClientFactory = Callable[[BrowserProfileState], CdpClient]


class AgentBrowserToolkit:
    """Lean browser tool interface for agent-core runtime wiring."""

    def __init__(
        self,
        *,
        lifecycle: ChromeLifecycleManager | None = None,
        navigation_policy: BrowserNavigationPolicy | None = None,
        client_factory: BrowserClientFactory | None = None,
    ) -> None:
        self.lifecycle = lifecycle or ChromeLifecycleManager()
        self.navigation_policy = navigation_policy or BrowserNavigationPolicy()
        self._client_factory = client_factory
        self._clients: dict[str, CdpClient] = {}

    def register_profile(
        self,
        *,
        name: str,
        cdp_url: str,
        headless: bool = True,
        user_data_dir: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> BrowserProfileState:
        profile = BrowserProfile(
            name=name,
            cdp_url=cdp_url,
            headless=headless,
            user_data_dir=user_data_dir,
            metadata=dict(metadata or {}),
        )
        return self.lifecycle.register_profile(profile)

    async def browser_profiles(self) -> tuple[BrowserProfileStatus, ...]:
        statuses: list[BrowserProfileStatus] = []
        for state in self.lifecycle.list_profiles():
            healthy = await self.lifecycle.health(state.profile.name)
            latest = self.lifecycle.get_profile(state.profile.name) or state
            statuses.append(
                BrowserProfileStatus(
                    name=latest.profile.name,
                    cdp_url=latest.profile.cdp_url,
                    running=latest.running,
                    healthy=healthy,
                    pid=latest.pid,
                )
            )
        return tuple(statuses)

    async def browser_tabs(self, profile_name: str) -> tuple[BrowserTab, ...]:
        state = await self.lifecycle.ensure_running(profile_name)
        client = self._client_for(state)
        return await client.list_tabs()

    async def browser_navigate(self, profile_name: str, url: str) -> str:
        state = await self.lifecycle.ensure_running(profile_name)
        client = self._client_for(state)
        return await client.navigate(url=url, policy=self.navigation_policy)

    async def browser_screenshot(
        self,
        profile_name: str,
        *,
        full_page: bool = False,
        image_format: str = "png",
        quality: int = 85,
    ) -> BrowserScreenshot:
        state = await self.lifecycle.ensure_running(profile_name)
        client = self._client_for(state)
        return await client.capture_screenshot(
            full_page=full_page,
            image_format=image_format,
            quality=quality,
        )

    async def browser_act(
        self,
        profile_name: str,
        command: BrowserActCommand | dict[str, object],
    ) -> BrowserActResult:
        state = await self.lifecycle.ensure_running(profile_name)
        client = self._client_for(state)
        normalized = self._coerce_action(command)
        return await client.act(normalized)

    async def stop_profile(self, profile_name: str) -> BrowserProfileState:
        state = await self.lifecycle.stop(profile_name)
        self._clients.pop(self._profile_key(profile_name), None)
        return state

    def _client_for(self, state: BrowserProfileState) -> CdpClient:
        key = self._profile_key(state.profile.name)
        client = self._clients.get(key)
        if client is not None:
            return client

        if self._client_factory is not None:
            client = self._client_factory(state)
        else:
            client = CdpClient(navigation_policy=self.navigation_policy)
        self._clients[key] = client
        return client

    @staticmethod
    def _coerce_action(command: BrowserActCommand | dict[str, object]) -> BrowserActCommand:
        if isinstance(command, BrowserActCommand):
            return command
        if not isinstance(command, dict):
            raise TypeError("browser action must be BrowserActCommand or dict payload.")
        return BrowserActCommand(
            kind=str(command.get("kind", "")).strip(),
            selector=(str(command.get("selector")).strip() if command.get("selector") is not None else None),
            text=(str(command.get("text")) if command.get("text") is not None else None),
            key=(str(command.get("key")).strip() if command.get("key") is not None else None),
            milliseconds=(int(command["milliseconds"]) if command.get("milliseconds") is not None else None),
        )

    @staticmethod
    def _profile_key(name: str) -> str:
        return name.strip().lower()
