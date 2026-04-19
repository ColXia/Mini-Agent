from __future__ import annotations

import asyncio

from mini_agent.commands.router import CommandDispatcher, parse_command_text


def test_parse_command_text_normalizes_aliases() -> None:
    invocation = parse_command_text(
        'drop-memories "keep latest"',
        surface="cli",
        aliases={"drop-memories": "drop_memories"},
    )

    assert invocation.surface == "cli"
    assert invocation.raw_name == "drop_memories"
    assert invocation.name == "drop_memories"
    assert invocation.args == ["keep latest"]
    assert invocation.joined_args() == "keep latest"


def test_command_dispatcher_routes_registered_handler() -> None:
    calls: list[tuple[str, list[str]]] = []

    async def _handler(invocation) -> None:  # noqa: ANN001
        calls.append((invocation.name, invocation.args))

    dispatcher = CommandDispatcher(surface="cli", aliases={"q": "exit"})
    dispatcher.register("exit", _handler, aliases=["quit", "q"])
    invocation = parse_command_text("q", surface="cli", aliases=dispatcher.aliases)

    handled = asyncio.run(dispatcher.dispatch(invocation))

    assert handled is True
    assert calls == [("exit", [])]
