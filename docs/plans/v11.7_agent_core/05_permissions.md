# 权限与审批系统开发文档

**模块**: agent_core/execution/permissions
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

权限与审批系统负责：

- 权限策略定义
- 权限决策评估
- 审批缓存
- 审批流程管理

---

## 二、核心数据结构

### 2.1 PermissionDecision

```python
class PermissionDecision(str, Enum):
    """Decision modes for permission checks."""

    ALLOW = "allow"   # 允许
    DENY = "deny"     # 拒绝
    ASK = "ask"       # 询问用户
```

### 2.2 PermissionRule

```python
@dataclass(frozen=True)
class PermissionRule:
    """Ordered permission rule matched against tool metadata."""

    tool_pattern: str = "*"                    # 工具名称模式
    decision: PermissionDecision = PermissionDecision.ASK
    kind: ToolKind | None = None               # 工具类型
    reason: str | None = None                  # 原因

    def matches(self, invocation: ToolInvocation) -> bool:
        """Check if rule matches the invocation."""
        if self.kind is not None and invocation.attributes.kind != self.kind:
            return False
        return fnmatch.fnmatch(invocation.tool_name, self.tool_pattern)
```

### 2.3 PermissionPolicy

```python
@dataclass(frozen=True)
class PermissionPolicy:
    """Layered ask/allow/deny policy with optional unrestricted bypass."""

    default_decision: PermissionDecision = PermissionDecision.ASK
    rules: tuple[PermissionRule, ...] = field(default_factory=tuple)
    full_auto: bool = False

    @staticmethod
    def full_auto_policy() -> "PermissionPolicy":
        """Create a policy that allows everything."""
        return PermissionPolicy(default_decision=PermissionDecision.ALLOW, full_auto=True)

    @staticmethod
    def strict_policy() -> "PermissionPolicy":
        """Create a policy that asks for everything."""
        return PermissionPolicy(default_decision=PermissionDecision.ASK)

    def evaluate_invocation(self, invocation: ToolInvocation) -> PermissionDecision:
        """Evaluate the decision for a tool invocation."""
        if self.full_auto:
            return PermissionDecision.ALLOW

        # 按顺序匹配规则
        for rule in self.rules:
            if rule.matches(invocation):
                return rule.decision

        # 只读工具默认允许
        if invocation.attributes.is_read_only:
            return PermissionDecision.ALLOW

        return self.default_decision

    def can_escalate(self, invocation: ToolInvocation) -> bool:
        """Check if the invocation can be escalated."""
        return invocation.attributes.kind in {
            ToolKind.WRITE,
            ToolKind.EDIT,
            ToolKind.DELETE,
            ToolKind.EXECUTE,
            ToolKind.NETWORK,
            ToolKind.DELEGATE,
        }
```

### 2.4 ApprovalOutcome

```python
@dataclass(frozen=True)
class ApprovalOutcome:
    """Approval decision payload."""

    decision: PermissionDecision
    reason: str
    requires_confirmation: bool = False
    from_cache: bool = False
    cache_key: str | None = None
    can_escalate: bool = False
    escalated: bool = False
```

---

## 三、ApprovalEngine

### 3.1 职责

审批引擎管理权限决策：

1. 策略评估
2. 缓存管理
3. 用户决策记录

### 3.2 实现

```python
class ApprovalEngine:
    """Policy + cache based approval decision engine."""

    def __init__(
        self,
        policy: PermissionPolicy | None = None,
        *,
        cache: ApprovalCache | None = None,
    ) -> None:
        self.policy = policy or PermissionPolicy.strict_policy()
        self.cache = cache or ApprovalCache()

    def evaluate(self, invocation: ToolInvocation) -> ApprovalOutcome:
        """Evaluate the approval decision for an invocation."""
        decision = self.policy.evaluate_invocation(invocation)
        cache_key = invocation_fingerprint(invocation)

        if decision == PermissionDecision.ALLOW:
            return ApprovalOutcome(
                decision=PermissionDecision.ALLOW,
                reason="allowed_by_policy",
                requires_confirmation=False,
                cache_key=cache_key,
            )

        if decision == PermissionDecision.DENY:
            return ApprovalOutcome(
                decision=PermissionDecision.DENY,
                reason="denied_by_policy",
                requires_confirmation=False,
                cache_key=cache_key,
            )

        # 检查缓存
        cached = self.cache.get(cache_key)
        if cached is not None:
            return ApprovalOutcome(
                decision=cached,
                reason="from_cache",
                requires_confirmation=False,
                from_cache=True,
                cache_key=cache_key,
            )

        return ApprovalOutcome(
            decision=PermissionDecision.ASK,
            reason="requires_user_approval",
            requires_confirmation=True,
            cache_key=cache_key,
            can_escalate=self.policy.can_escalate(invocation),
        )

    def record_user_decision(
        self,
        invocation: ToolInvocation,
        decision: PermissionDecision,
    ) -> ApprovalOutcome:
        """Record a user decision and cache it."""
        cache_key = invocation_fingerprint(invocation)
        self.cache.set(cache_key, decision)
        return ApprovalOutcome(
            decision=decision,
            reason="user_decision",
            requires_confirmation=False,
            from_cache=False,
            cache_key=cache_key,
        )
```

---

## 四、ApprovalCache

### 4.1 职责

审批缓存存储用户决策，避免重复询问：

- TTL 过期
- 最大条目限制
- LRU 淘汰

### 4.2 实现

```python
@dataclass
class _CacheEntry:
    decision: PermissionDecision
    expires_at: datetime


class ApprovalCache:
    """Small in-memory approval cache keyed by invocation fingerprint."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 1800,   # 30 分钟
        max_entries: int = 512,
    ) -> None:
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.max_entries = max(8, int(max_entries))
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> PermissionDecision | None:
        """Get cached decision if not expired."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= _utc_now():
            self._entries.pop(key, None)
            return None
        return entry.decision

    def set(self, key: str, decision: PermissionDecision) -> None:
        """Cache a decision with TTL."""
        # LRU 淘汰
        if len(self._entries) >= self.max_entries:
            oldest_key = min(
                self._entries,
                key=lambda item: self._entries[item].expires_at,
            )
            self._entries.pop(oldest_key, None)

        self._entries[key] = _CacheEntry(
            decision=decision,
            expires_at=_utc_now() + timedelta(seconds=self.ttl_seconds),
        )

    def clear(self) -> None:
        """Clear all cached decisions."""
        self._entries.clear()
```

---

## 五、决策流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     Approval Decision Flow                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 接收工具调用                                                │
│     │                                                           │
│     ▼                                                           │
│  2. 策略评估 (policy.evaluate_invocation)                       │
│     │                                                           │
│     ├── ALLOW ──► 返回允许                                      │
│     │                                                           │
│     ├── DENY ──► 返回拒绝                                       │
│     │                                                           │
│     └── ASK                                                     │
│         │                                                       │
│         ▼                                                       │
│  3. 检查缓存 (cache.get)                                        │
│     │                                                           │
│     ├── 命中 ──► 返回缓存决策                                   │
│     │                                                           │
│     └── 未命中                                                   │
│         │                                                       │
│         ▼                                                       │
│  4. 返回需要用户审批                                            │
│     │                                                           │
│     ▼                                                           │
│  5. 用户决策                                                    │
│     │                                                           │
│     ├── 批准 ──► 缓存并执行                                     │
│     └── 拒绝 ──► 缓存并拒绝                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 六、策略示例

### 6.1 完全自动模式

```python
policy = PermissionPolicy.full_auto_policy()
# 所有工具调用自动允许
```

### 6.2 严格模式

```python
policy = PermissionPolicy.strict_policy()
# 所有非只读工具需要审批
```

### 6.3 自定义规则

```python
policy = PermissionPolicy(
    default_decision=PermissionDecision.ASK,
    rules=(
        PermissionRule(
            tool_pattern="read*",
            decision=PermissionDecision.ALLOW,
            reason="Read operations are safe",
        ),
        PermissionRule(
            tool_pattern="bash",
            decision=PermissionDecision.ASK,
            kind=ToolKind.EXECUTE,
            reason="Shell commands require approval",
        ),
        PermissionRule(
            tool_pattern="delete*",
            decision=PermissionDecision.DENY,
            reason="Delete operations are disabled",
        ),
    ),
)
```

---

## 七、文件位置

```
src/mini_agent/agent_core/execution/permissions/
├── __init__.py
├── policy.py                # 权限策略
└── approval.py              # 审批引擎
```

---

## 八、验收标准

- [x] PermissionPolicy 支持规则匹配
- [x] ApprovalEngine 支持缓存
- [x] 支持用户决策记录
- [x] 支持 TTL 过期

---

## 九、依赖关系

- 依赖: tools/attributes.py
- 被依赖: tool_execution_coordinator.py
