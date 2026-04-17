"""Application service for shared command discovery, completion, and dispatch."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any


def _require_command_runtime(runtime: Any) -> Any:
    if runtime is None:
        raise RuntimeError("Command runtime is not configured.")
    return runtime


@dataclass(slots=True)
class CommandApplicationService:
    """Owns command-facing application logic above shared command runtimes."""

    command_runtime: Any = None

    async def list_commands(self) -> Any:
        return await self._invoke_first(("list_commands", "catalog"))

    async def describe_command(self, command_name: str) -> Any:
        return await self._invoke_first(("describe_command", "describe"), command_name)

    async def complete_command(self, prefix: str) -> Any:
        return await self._invoke_first(("complete_command", "complete"), prefix)

    async def dispatch_command(self, raw_command: str, **kwargs: Any) -> Any:
        return await self._invoke_first(("dispatch_command", "execute_command"), raw_command, **kwargs)

    async def _invoke_first(self, names: tuple[str, ...], *args: Any, **kwargs: Any) -> Any:
        runtime = _require_command_runtime(self.command_runtime)
        for name in names:
            if hasattr(runtime, name):
                target = getattr(runtime, name)
                result = target(*args, **kwargs)
                if inspect.isawaitable(result):
                    return await result
                return result
        available = ", ".join(names)
        raise RuntimeError(f"Command runtime does not implement any of: {available}")


__all__ = ["CommandApplicationService"]
