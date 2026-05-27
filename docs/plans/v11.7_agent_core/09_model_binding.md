# 模型绑定设计文档

**模块**: agent_core (引用)
**优先级**: P0
**状态**: 已完成设计

---

## 一、文档引用

模型绑定设计文档位于：

- [v11.6_agent_model_binding_plan.md](../v11.6_agent_model_binding_plan.md)

---

## 二、核心内容摘要

### 2.1 Agent 模型绑定

```python
@dataclass
class AgentModelBinding:
    """Agent 模型绑定配置"""
    agent_id: str
    models: list[ModelBindingEntry]
    failover_enabled: bool = True

@dataclass
class ModelBindingEntry:
    """单个模型绑定条目"""
    config_id: str           # 模型配置 ID
    role: str                # primary / fallback_1 / fallback_2
    custom_name: str | None  # 自定义名称
    enabled: bool = True
```

### 2.2 故障转移策略

```python
@dataclass
class FailoverPolicy:
    """故障转移策略"""
    enabled: bool = True
    retry_before_failover: bool = True
    max_retries: int = 2
    failover_order: list[str] = []
    notify_user_on_failover: bool = True
```

### 2.3 上下文压缩

```python
@dataclass
class CompressionPolicy:
    """上下文压缩策略"""
    trigger_ratio: float = 0.8
    min_remaining_tokens: int = 2000
    compression_target: float = 0.5
    preserve_system_messages: bool = True
    preserve_recent_messages: int = 3
    preserve_tool_results: bool = True
    compression_method: str = "summarize"
```

---

## 三、开发任务

| 任务 | 状态 |
|------|------|
| AgentModelBinding 数据结构 | 待开发 |
| Agent 模型绑定存储 | 待开发 |
| 故障转移逻辑 | 待开发 |
| 错误处理逻辑 | 待开发 |
| 上下文压缩触发 | 待开发 |
| Agent 绑定 CLI 命令 | 待开发 |

---

## 四、依赖关系

- 依赖: v11.6_model_service (模型侧)
- 被依赖: engine.py
