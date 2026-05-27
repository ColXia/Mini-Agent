# 上下文系统开发文档

**模块**: agent_core/context
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

上下文系统负责：

- ContextAssembler - 上下文组装
- TurnContext - 回合上下文
- ContextCompaction - 上下文压缩
- 上下文提供者管理

---

## 二、核心数据结构

### 2.1 ContextSourceKind

```python
class ContextSourceKind(str, Enum):
    """Kinds of context sources."""

    SYSTEM = "system"       # 系统提示
    SKILL = "skill"         # 技能上下文
    MEMORY = "memory"       # 记忆上下文
    WORKSPACE = "workspace" # 工作区上下文
    SESSION = "session"     # 会话上下文
    USER = "user"           # 用户输入
```

### 2.2 ContextSection

```python
@dataclass(frozen=True, slots=True)
class ContextSection:
    """A single section in the assembled context."""

    source_kind: ContextSourceKind
    source_id: str
    title: str
    content: str
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None

    def to_prompt(self) -> str:
        """Generate prompt representation of this section."""
```

### 2.3 AssembledContext

```python
@dataclass(frozen=True, slots=True)
class AssembledContext:
    """Assembled context for agent prompt."""

    workspace_id: str
    session_id: str
    run_id: str
    sections: tuple[ContextSection, ...] = ()
    total_chars: int = 0
    assembly_timestamp: datetime | None = None

    @property
    def section_count(self) -> int:
        """Return the number of sections."""

    def get_sections_by_kind(self, kind: ContextSourceKind) -> list[ContextSection]:
        """Get all sections of a specific kind."""

    def to_prompt(self, *, include_headers: bool = True) -> str:
        """Generate the full prompt from all sections."""
```

### 2.4 TurnContextItem

```python
@dataclass(frozen=True, slots=True)
class TurnContextItem:
    """One turn-scoped context item."""

    provider_name: str
    content: str
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 2.5 TurnContextProvider

```python
class TurnContextProvider(Protocol):
    """Protocol for turn context providers."""

    @property
    def name(self) -> str:
        """Provider name."""

    async def provide(self, context: RuntimeTurnContext) -> list[TurnContextItem]:
        """Provide context items for the turn."""
```

---

## 三、ContextAssembler

### 3.1 职责

ContextAssembler 从多个来源组装上下文：

1. 系统提示
2. 技能上下文
3. 记忆上下文
4. 工作区状态
5. 会话状态
6. 用户输入

### 3.2 实现

```python
@dataclass(slots=True)
class ContextAssembler:
    """Assembler for agent context from multiple sources."""

    def add_system_prompt(self, content: str) -> ContextSection:
        """Add system prompt section."""

    def add_skill_context(self, skill_name: str, instructions: str) -> ContextSection:
        """Add skill context section."""

    def add_memory_context(self, content: str) -> ContextSection:
        """Add memory context section."""

    def add_workspace_context(self, content: str) -> ContextSection:
        """Add workspace context section."""

    def add_session_context(self, content: str) -> ContextSection:
        """Add session context section."""

    def add_user_context(self, content: str) -> ContextSection:
        """Add user input section."""

    def assemble(
        self,
        *,
        workspace_id: str,
        session_id: str,
        run_id: str,
    ) -> AssembledContext:
        """Assemble all sections into final context."""
```

---

## 四、LayeredContextCompactor

### 4.1 职责

上下文压缩器管理消息历史大小：

1. Token 预算控制
2. 工具输出截断
3. 消息合并
4. 敏感信息遮蔽

### 4.2 实现

```python
@dataclass(frozen=True)
class CompressionStats:
    """Compression metrics for one compaction pass."""

    original_messages: int
    compressed_messages: int
    original_tokens: int
    compressed_tokens: int
    masked_messages: int = 0
    snipped_messages: int = 0
    merged_messages: int = 0


@dataclass(frozen=True)
class ContextCompressionResult:
    """Compaction output payload."""

    messages: tuple[Message, ...]
    stats: CompressionStats


class LayeredContextCompactor:
    """Small, strong context compactor for agent execution turns."""

    def __init__(
        self,
        *,
        token_budget: int,
        keep_recent_tool_messages: int = 2,
        snip_tail_lines: int = 30,
        masker: ToolOutputMasker | None = None,
    ) -> None:
        self.token_budget = max(200, int(token_budget))
        self.keep_recent_tool_messages = max(0, int(keep_recent_tool_messages))
        self.snip_tail_lines = max(1, int(snip_tail_lines))
        self.masker = masker or ToolOutputMasker()

    def compact(
        self,
        messages: list[Message],
        *,
        query: str | None = None,
        enable_masking: bool = True,
    ) -> ContextCompressionResult:
        """Compact messages to fit within token budget."""
```

### 4.3 压缩策略

```
┌─────────────────────────────────────────────────────────────────┐
│                    Compression Strategy                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 保留系统消息                                                │
│     │                                                           │
│     ▼                                                           │
│  2. 截断工具输出                                                │
│     ├── 保留最近 N 条完整工具消息                               │
│     └── 其他工具消息只保留最后 N 行                              │
│     │                                                           │
│     ▼                                                           │
│  3. 遮蔽敏感信息                                                │
│     ├── API 密钥                                                │
│     ├── 密码                                                    │
│     └── Token                                                   │
│     │                                                           │
│     ▼                                                           │
│  4. 合并相邻消息                                                │
│     │                                                           │
│     ▼                                                           │
│  5. 检查 Token 预算                                            │
│     ├── 超出 → 继续压缩                                        │
│     └── 未超出 → 返回结果                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、TurnContext 提供者

### 5.1 内置提供者

| 提供者 | 说明 |
|--------|------|
| UserProfileTurnContextProvider | 用户配置信息 |
| WorkspaceMemoryContextProvider | 工作区记忆 |
| SessionSearchTurnContextProvider | 会话搜索 |
| SkillCatalogTurnContextProvider | 技能目录 |
| MCPToolCatalogTurnContextProvider | MCP 工具目录 |
| ConsolidatedMemoryTurnContextProvider | 合并记忆 |
| RuntimeTaskMemoryTurnContextProvider | 运行时任务记忆 |
| RuntimeRecoveryTurnContextProvider | 运行时恢复 |

### 5.2 提供者接口

```python
class TurnContextProvider(Protocol):
    """Protocol for turn context providers."""

    @property
    def name(self) -> str:
        """Provider name."""

    async def provide(self, context: RuntimeTurnContext) -> list[TurnContextItem]:
        """Provide context items for the turn."""
```

---

## 六、Token 估算

```python
def estimate_tokens(messages: Iterable[Message]) -> int:
    """Estimate message tokens with `cl100k_base` fallback."""
    items = list(messages)
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        return sum(_message_token_count(encoding, msg) for msg in items)
    except Exception:
        # 回退到字符估算
        total_chars = 0
        for msg in items:
            total_chars += len(str(msg.content))
            if msg.thinking:
                total_chars += len(msg.thinking)
            if msg.tool_calls:
                total_chars += len(str(msg.tool_calls))
        return int(total_chars / 2.5)
```

---

## 七、文件位置

```
src/mini_agent/agent_core/context/
├── __init__.py
├── context_assembler.py         # 上下文组装器
├── context_compaction.py        # 上下文压缩
├── turn_context.py              # 回合上下文服务
├── turn_context_types.py        # 类型定义
├── turn_context_providers.py    # 提供者实现
├── turn_context_policy.py       # 策略配置
├── turn_context_curation.py     # 内容筛选
├── turn_context_diagnostics.py  # 诊断工具
├── turn_context_preparation.py  # 准备服务
├── turn_context_provider_builder.py  # 提供者构建器
└── loop_context.py              # 循环上下文
```

---

## 八、验收标准

- [x] ContextAssembler 支持多来源组装
- [x] LayeredContextCompactor 支持 Token 预算
- [x] 支持工具输出截断
- [x] 支持敏感信息遮蔽
- [x] 支持多种上下文提供者

---

## 九、依赖关系

- 依赖: schema/, utils/
- 被依赖: engine.py
