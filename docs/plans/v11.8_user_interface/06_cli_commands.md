# CLI 命令开发文档

**模块**: commands
**优先级**: P2
**预估时间**: 已实现，文档补全

---

## 一、功能概述

CLI 命令负责：

- 命令行入口
- 命令解析
- 命令执行
- 自动补全

---

## 二、技术栈

- **Click** - CLI 框架
- **prompt_toolkit** - 交互式输入

---

## 三、命令结构

### 3.1 主命令

```python
# src/mini_agent/commands/cli.py

@click.group()
@click.version_option()
def cli():
    """Mini-Agent CLI."""
    pass


@cli.command()
@click.option("--workspace", "-w", default=".", help="Workspace directory")
@click.option("--session", "-s", help="Session ID")
@click.option("--model", "-m", help="Model ID")
def chat(workspace: str, session: str | None, model: str | None):
    """Start interactive chat."""
    from mini_agent.tui.app import MiniAgentTuiApp

    app = MiniAgentTuiApp(
        workspace_dir=Path(workspace),
        session_id=session,
        model_id=model,
    )
    app.run()


@cli.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8008)
@click.option("--workspace", "-w", required=True)
def desktop(host: str, port: int, workspace: str):
    """Launch desktop UI."""
    from mini_agent.desktop.app import launch_desktop_ui

    return launch_desktop_ui(
        host=host,
        port=port,
        workspace=Path(workspace),
    )


@cli.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8008)
@click.option("--workspace", "-w", required=True)
def gateway(host: str, port: int, workspace: str):
    """Start gateway server."""
    from mini_agent.gateway.server import run_gateway

    run_gateway(host=host, port=port, workspace=Path(workspace))
```

---

## 四、命令解析

### 4.1 命令解析器

```python
# src/mini_agent/commands/parser.py

@dataclass
class CommandParseResult:
    """Result of command parsing."""

    type: str  # "chat" | "command" | "unknown"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    content: str | None = None
    error: str | None = None


class CommandDispatcher:
    """Dispatch parsed commands to handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, command: str, handler: CommandHandler) -> None:
        self._handlers[command] = handler

    def parse(self, text: str) -> CommandParseResult:
        """Parse command text."""
        text = text.strip()
        if not text:
            return CommandParseResult(type="unknown", error="Empty input")

        if not text.startswith("/"):
            return CommandParseResult(type="chat", content=text)

        parts = text[1:].split()
        if not parts:
            return CommandParseResult(type="unknown", error="Empty command")

        command = parts[0].lower()
        args = parts[1:]

        return CommandParseResult(
            type="command",
            command=command,
            args=args,
        )

    async def dispatch(
        self,
        result: CommandParseResult,
        context: CommandContext,
    ) -> CommandExecutionResult:
        """Dispatch to appropriate handler."""
        if result.type == "chat":
            return await self._handle_chat(result.content, context)

        if result.type == "command":
            handler = self._handlers.get(result.command)
            if handler:
                return await handler.execute(result.args, context)
            return CommandExecutionResult(
                success=False,
                error=f"Unknown command: {result.command}",
            )

        return CommandExecutionResult(
            success=False,
            error=result.error,
        )
```

---

## 五、命令执行

### 5.1 命令处理器

```python
# src/mini_agent/commands/execution.py

@dataclass
class CommandContext:
    """Context for command execution."""

    session_state: MainAgentSessionState
    transport_binding: TransportBinding
    workspace_dir: Path


@dataclass
class CommandExecutionResult:
    """Result of command execution."""

    success: bool
    output: str | None = None
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class CommandHandler(Protocol):
    """Protocol for command handlers."""

    async def execute(
        self,
        args: list[str],
        context: CommandContext,
    ) -> CommandExecutionResult: ...
```

### 5.2 内置命令处理器

```python
class HelpCommandHandler:
    """Handle /help command."""

    async def execute(
        self,
        args: list[str],
        context: CommandContext,
    ) -> CommandExecutionResult:
        return CommandExecutionResult(
            success=True,
            output=build_command_help_text(),
        )


class ClearCommandHandler:
    """Handle /clear command."""

    async def execute(
        self,
        args: list[str],
        context: CommandContext,
    ) -> CommandExecutionResult:
        context.session_state.messages.clear()
        return CommandExecutionResult(
            success=True,
            output="Messages cleared.",
        )


class ModelCommandHandler:
    """Handle /model command."""

    async def execute(
        self,
        args: list[str],
        context: CommandContext,
    ) -> CommandExecutionResult:
        if not args:
            # Show current model
            binding = await context.transport_binding.model_client.get_binding()
            return CommandExecutionResult(
                success=True,
                output=f"Current model: {binding.model_id}",
            )

        if args[0] == "list":
            models = await context.transport_binding.model_client.list_models()
            output = "\n".join(f"- {m.model_id}" for m in models)
            return CommandExecutionResult(success=True, output=output)

        if args[0] == "switch":
            if len(args) < 2:
                return CommandExecutionResult(
                    success=False,
                    error="Usage: /model switch <model_id>",
                )
            await context.transport_binding.model_client.update_binding(
                model_id=args[1],
            )
            return CommandExecutionResult(
                success=True,
                output=f"Switched to model: {args[1]}",
            )
```

---

## 六、自动补全

### 6.1 补全器

```python
# src/mini_agent/commands/completions.py

class CommandCompleter(Completer):
    """Completer for commands."""

    def __init__(self, context: CommandContext) -> None:
        self._context = context
        self._commands = [
            "help", "clear", "exit",
            "model", "session", "skill",
            "memory", "context", "mcp",
            "approval",
        ]

    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent,
    ) -> Iterable[Completion]:
        text = document.text_before_cursor

        if not text.startswith("/"):
            return

        # 命令补全
        if " " not in text:
            command_part = text[1:]
            for cmd in self._commands:
                if cmd.startswith(command_part):
                    yield Completion(
                        f"/{cmd}",
                        start_position=-len(text),
                        display=cmd,
                    )
            return

        # 参数补全
        parts = text[1:].split()
        command = parts[0]
        args = parts[1:]

        if command == "model":
            yield from self._complete_model(args, text)
        elif command == "session":
            yield from self._complete_session(args, text)
        elif command == "skill":
            yield from self._complete_skill(args, text)
```

---

## 七、命令元数据

### 7.1 命令描述

```python
# src/mini_agent/commands/metadata.py

COMMAND_METADATA: dict[str, CommandMetadata] = {
    "help": CommandMetadata(
        name="help",
        description="Show help information",
        usage="/help [command]",
        examples=["/help", "/help model"],
    ),
    "clear": CommandMetadata(
        name="clear",
        description="Clear message history",
        usage="/clear",
        examples=["/clear"],
    ),
    "model": CommandMetadata(
        name="model",
        description="Model management",
        usage="/model [list|switch|probe] [args]",
        examples=["/model", "/model list", "/model switch gpt-4o"],
    ),
    "session": CommandMetadata(
        name="session",
        description="Session management",
        usage="/session [list|new|switch|fork|delete] [args]",
        examples=["/session list", "/session new", "/session switch abc123"],
    ),
    "skill": CommandMetadata(
        name="skill",
        description="Skill management",
        usage="/skill [list|enable|disable] [args]",
        examples=["/skill list", "/skill enable code-review"],
    ),
    "memory": CommandMetadata(
        name="memory",
        description="Memory management",
        usage="/memory [list|search|add] [args]",
        examples=["/memory list", "/memory search query"],
    ),
    "exit": CommandMetadata(
        name="exit",
        description="Exit the application",
        usage="/exit",
        examples=["/exit"],
    ),
}


def build_command_help_text() -> str:
    """Build help text for all commands."""
    lines = ["Available commands:"]
    for name, meta in COMMAND_METADATA.items():
        lines.append(f"  /{name:<12} - {meta.description}")
    return "\n".join(lines)
```

---

## 八、文件位置

```
src/mini_agent/commands/
├── __init__.py
├── cli.py                # CLI 入口
├── parser.py             # 命令解析
├── execution.py          # 命令执行
├── completions.py        # 自动补全
└── metadata.py           # 命令元数据
```

---

## 九、验收标准

- [x] 支持命令行入口
- [x] 支持命令解析
- [x] 支持命令执行
- [x] 支持自动补全
- [x] 支持帮助信息

---

## 十、依赖关系

- 依赖: tui/, transport/
- 被依赖: 用户交互