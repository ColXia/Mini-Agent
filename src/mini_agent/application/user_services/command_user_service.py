"""User-facing command facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_agent.application.use_cases.command_application_service import CommandApplicationService


@dataclass(slots=True)
class CommandUserService:
    """Thin user-service facade for shared command entrypoints."""

    application_service: CommandApplicationService | None = None
    command_runtime: Any = None

    def _application(self) -> CommandApplicationService:
        if self.application_service is None:
            self.application_service = CommandApplicationService(command_runtime=self.command_runtime)
        return self.application_service

    async def list_commands(self) -> Any:
        return await self._application().list_commands()

    async def describe_command(self, command_name: str) -> Any:
        return await self._application().describe_command(command_name)

    async def complete_command(self, prefix: str) -> Any:
        return await self._application().complete_command(prefix)

    async def dispatch_command(self, raw_command: str, **kwargs: Any) -> Any:
        return await self._application().dispatch_command(raw_command, **kwargs)


__all__ = ["CommandUserService"]
