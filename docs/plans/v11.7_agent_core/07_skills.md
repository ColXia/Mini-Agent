# 技能系统开发文档

**模块**: agent_core/skills
**优先级**: P2
**预估时间**: 已实现，文档补全

---

## 一、功能概述

技能系统负责：

- SkillRegistry - 技能注册表
- SkillLoader - 技能加载器
- SkillEligibility - 技能资格检查
- 技能优先级解析

---

## 二、核心数据结构

### 2.1 SkillSource

```python
class SkillSource(str, Enum):
    """Skill source types."""

    BUILTIN = "builtin"     # 内置技能
    WORKSPACE = "workspace" # 工作区技能
    PLUGIN = "plugin"       # 插件技能
    REMOTE = "remote"       # 远程技能


SOURCE_PRIORITY: dict[SkillSource, int] = {
    SkillSource.BUILTIN: 10,
    SkillSource.PLUGIN: 20,
    SkillSource.WORKSPACE: 30,
    SkillSource.REMOTE: 40,
}
```

### 2.2 AgentSkill

```python
@dataclass(frozen=True)
class AgentSkill:
    """Canonical skill record used by agent-core runtime."""

    name: str
    description: str
    instructions: str
    source: SkillSource
    frontmatter: dict[str, Any]
    requirements: SkillRequirements
    eligibility: SkillEligibilityResult
    skill_file: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def root_dir(self) -> Path | None:
        """Get skill root directory."""

    def to_prompt(self) -> str:
        """Generate prompt representation."""
```

### 2.3 SkillTier1Metadata

```python
@dataclass(frozen=True)
class SkillTier1Metadata:
    """Tier-1 skill metadata exposed in system prompts."""

    name: str
    description: str
    source: SkillSource
    eligible: bool
    blocked_reason: str | None
    skill_key: str
    always: bool
    skill_file: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

---

## 三、SkillRegistry

### 3.1 职责

技能注册表管理技能的注册和查询：

- 按名称注册技能
- 按优先级解析冲突
- 列出可用技能

### 3.2 实现

```python
class SkillRegistry:
    """Registry resolving duplicate skills by source priority."""

    def __init__(self) -> None:
        self._skills: dict[str, AgentSkill] = {}

    def clear(self) -> None:
        """Clear all registered skills."""
        self._skills.clear()

    def register(self, skill: AgentSkill) -> None:
        """Register a skill, resolving conflicts by priority."""
        existing = self._skills.get(skill.name)
        if existing is None:
            self._skills[skill.name] = skill
            return

        # 按优先级解析冲突
        existing_priority = SOURCE_PRIORITY.get(existing.source, 0)
        incoming_priority = SOURCE_PRIORITY.get(skill.source, 0)
        if incoming_priority >= existing_priority:
            self._skills[skill.name] = skill

    def get(self, name: str) -> AgentSkill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def list(self, *, eligible_only: bool = False) -> list[AgentSkill]:
        """List all registered skills."""
        skills = list(self._skills.values())
        if eligible_only:
            skills = [s for s in skills if s.eligibility.eligible]
        return sorted(skills, key=lambda s: s.name)
```

---

## 四、AgentSkillLoader

### 4.1 职责

技能加载器从多个来源发现和加载技能：

1. 发现技能文件
2. 解析 Markdown 格式
3. 检查资格条件
4. 返回 AgentSkill 对象

### 4.2 技能文件格式

```markdown
---
name: code-review
description: Review code changes and provide feedback
requirements:
  tools:
    - read
    - bash
  model_capabilities:
    - extended_thinking
---

# Code Review Skill

You are a code reviewer. Your task is to:

1. Read the changed files
2. Analyze the code for potential issues
3. Provide constructive feedback

## Guidelines

- Focus on code quality, not style preferences
- Suggest concrete improvements
- Be respectful and constructive
```

### 4.3 实现

```python
class AgentSkillLoader:
    """Load skills from builtin/workspace/plugin/remote sources."""

    def __init__(
        self,
        *,
        builtin_dirs: list[Path] | None = None,
        workspace_dir: Path | None = None,
        plugin_dirs: list[Path] | None = None,
        eligibility_checker: SkillEligibilityChecker | None = None,
    ) -> None:
        self.builtin_dirs = builtin_dirs or []
        self.workspace_dir = workspace_dir
        self.plugin_dirs = plugin_dirs or []
        self.eligibility_checker = eligibility_checker or SkillEligibilityChecker()

    def discover(self) -> list[SkillTier1Metadata]:
        """Discover all available skills."""
        results = []
        # 发现内置技能
        for dir_path in self.builtin_dirs:
            results.extend(self._discover_in_dir(dir_path, SkillSource.BUILTIN))
        # 发现工作区技能
        if self.workspace_dir:
            results.extend(self._discover_in_dir(
                self.workspace_dir / ".mini-agent" / "skills",
                SkillSource.WORKSPACE,
            ))
        # 发现插件技能
        for dir_path in self.plugin_dirs:
            results.extend(self._discover_in_dir(dir_path, SkillSource.PLUGIN))
        return results

    def get_skill(self, name: str) -> AgentSkill | None:
        """Load a specific skill by name."""

    def load_tier2(self, name: str) -> str | None:
        """Load tier-2 skill instructions."""
```

---

## 五、SkillEligibility

### 5.1 职责

技能资格检查器验证技能是否可用：

- 检查工具依赖
- 检查模型能力
- 检查环境条件

### 5.2 实现

```python
@dataclass(frozen=True)
class SkillRequirements:
    """Skill requirements specification."""

    tools: tuple[str, ...] = ()
    model_capabilities: tuple[str, ...] = ()
    env_vars: tuple[str, ...] = ()
    min_context_tokens: int | None = None


@dataclass(frozen=True)
class SkillEligibilityResult:
    """Result of skill eligibility check."""

    eligible: bool
    blocked_reason: str | None = None
    missing_tools: tuple[str, ...] = ()
    missing_capabilities: tuple[str, ...] = ()
    missing_env_vars: tuple[str, ...] = ()


class SkillEligibilityChecker:
    """Check if skills are eligible for use."""

    def __init__(
        self,
        *,
        available_tools: set[str] | None = None,
        model_capabilities: set[str] | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> None:
        self.available_tools = available_tools or set()
        self.model_capabilities = model_capabilities or set()
        self.env_vars = env_vars or {}

    def check(self, requirements: SkillRequirements) -> SkillEligibilityResult:
        """Check if requirements are met."""
        missing_tools = tuple(
            tool for tool in requirements.tools
            if tool not in self.available_tools
        )
        missing_capabilities = tuple(
            cap for cap in requirements.model_capabilities
            if cap not in self.model_capabilities
        )
        missing_env_vars = tuple(
            var for var in requirements.env_vars
            if var not in self.env_vars
        )

        blocked_reasons = []
        if missing_tools:
            blocked_reasons.append(f"Missing tools: {', '.join(missing_tools)}")
        if missing_capabilities:
            blocked_reasons.append(f"Missing capabilities: {', '.join(missing_capabilities)}")
        if missing_env_vars:
            blocked_reasons.append(f"Missing env vars: {', '.join(missing_env_vars)}")

        return SkillEligibilityResult(
            eligible=not blocked_reasons,
            blocked_reason="; ".join(blocked_reasons) if blocked_reasons else None,
            missing_tools=missing_tools,
            missing_capabilities=missing_capabilities,
            missing_env_vars=missing_env_vars,
        )
```

---

## 六、技能来源优先级

```
┌─────────────────────────────────────────────────────────────────┐
│                    Skill Source Priority                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Priority 10: BUILTIN                                           │
│  ├── 系统内置技能                                               │
│  └── 最低优先级（可被覆盖）                                     │
│                                                                 │
│  Priority 20: PLUGIN                                            │
│  ├── 插件技能                                                   │
│  └── 可覆盖内置技能                                             │
│                                                                 │
│  Priority 30: WORKSPACE                                         │
│  ├── 工作区技能                                                 │
│  └── 可覆盖插件技能                                             │
│                                                                 │
│  Priority 40: REMOTE                                            │
│  ├── 远程技能                                                   │
│  └── 最高优先级                                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 七、文件位置

```
src/mini_agent/agent_core/skills/
├── __init__.py
├── registry.py              # SkillRegistry
├── loader.py                # AgentSkillLoader
├── eligibility.py           # SkillEligibilityChecker
├── policy.py                # 技能策略
├── install.py               # 技能安装
├── path_resolver.py         # 路径解析
├── command_service.py       # 命令服务
├── workspace_support.py     # 工作区支持
├── runtime_feedback.py      # 运行时反馈
└── self_improve.py          # 自我改进
```

---

## 八、验收标准

- [x] SkillRegistry 支持优先级解析
- [x] AgentSkillLoader 支持多来源
- [x] SkillEligibility 支持条件检查
- [x] 支持 Markdown 格式解析

---

## 九、依赖关系

- 无前置依赖
- 被依赖: engine.py, context/
