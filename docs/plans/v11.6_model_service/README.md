# 模型服务模块开发索引

**版本**: v11.6
**创建时间**: 2026-05-11
**状态**: 设计完成，待开发

---

## 文档结构

```
v11.6_model_service/
├── README.md                    # 本文件 - 开发索引
├── 01_provider_config.md        # Provider 配置管理
├── 02_model_registry.md         # 模型注册表
├── 03_model_configs.md          # 模型参数配置
├── 04_capability_probe.md       # 能力探测
├── 05_health_breaker.md         # 健康监控与熔断器
├── 06_token_stats.md            # Token 统计
├── 07_model_alias.md            # 模型别名与显示名称
├── 08_interfaces.md             # 接口定义
└── 09_cli_commands.md           # CLI 命令
```

---

## 开发阶段

### Phase 0: Provider 配置管理 (P0)

| 任务 | 文档 | 状态 |
|------|------|------|
| ProviderConfig 数据结构 | [01_provider_config.md](01_provider_config.md) | 待开发 |
| Provider 配置存储 | [01_provider_config.md](01_provider_config.md) | 待开发 |
| Provider 配置验证 | [01_provider_config.md](01_provider_config.md) | 待开发 |
| 环境变量检测 | [01_provider_config.md](01_provider_config.md) | 待开发 |

### Phase 1: 模型注册表 (P0)

| 任务 | 文档 | 状态 |
|------|------|------|
| ModelRegistry 数据结构 | [02_model_registry.md](02_model_registry.md) | 待开发 |
| 统一存储实现 | [02_model_registry.md](02_model_registry.md) | 待开发 |
| 配置导入导出 | [02_model_registry.md](02_model_registry.md) | 待开发 |

### Phase 2: 模型参数配置 (P1)

| 任务 | 文档 | 状态 |
|------|------|------|
| ModelParameterConfig 数据结构 | [03_model_configs.md](03_model_configs.md) | 待开发 |
| 参数配置存储 | [03_model_configs.md](03_model_configs.md) | 待开发 |
| 参数合并逻辑 | [03_model_configs.md](03_model_configs.md) | 待开发 |

### Phase 3: 能力探测 (P2)

| 任务 | 文档 | 状态 |
|------|------|------|
| 能力探测服务 | [04_capability_probe.md](04_capability_probe.md) | 待开发 |
| 能力缓存 | [04_capability_probe.md](04_capability_probe.md) | 待开发 |
| 上下文窗口配置 | [04_capability_probe.md](04_capability_probe.md) | 待开发 |

### Phase 4: 健康监控与熔断器 (P1)

| 任务 | 文档 | 状态 |
|------|------|------|
| 健康监控服务 | [05_health_breaker.md](05_health_breaker.md) | 待开发 |
| 熔断器实现 | [05_health_breaker.md](05_health_breaker.md) | 待开发 |
| 回调通知机制 | [05_health_breaker.md](05_health_breaker.md) | 待开发 |

### Phase 5: Token 统计 (P1)

| 任务 | 文档 | 状态 |
|------|------|------|
| Token 使用记录 | [06_token_stats.md](06_token_stats.md) | 待开发 |
| 成本估算 | [06_token_stats.md](06_token_stats.md) | 待开发 |
| 统计汇总 | [06_token_stats.md](06_token_stats.md) | 待开发 |

### Phase 6: 模型别名 (P2)

| 任务 | 文档 | 状态 |
|------|------|------|
| 别名解析器 | [07_model_alias.md](07_model_alias.md) | 待开发 |
| 显示名称映射 | [07_model_alias.md](07_model_alias.md) | 待开发 |

### Phase 7: 接口实现 (P0)

| 任务 | 文档 | 状态 |
|------|------|------|
| ModelBindingPort | [08_interfaces.md](08_interfaces.md) | 待开发 |
| ModelClientPort | [08_interfaces.md](08_interfaces.md) | 待开发 |
| ModelStatusPort | [08_interfaces.md](08_interfaces.md) | 待开发 |
| ModelCallbackPort | [08_interfaces.md](08_interfaces.md) | 待开发 |

---

## 相关文档

- [设计总览](../v11.6_model_service_plan.md) - 模型服务整体设计
- [Agent 模型绑定](../v11.6_agent_model_binding_plan.md) - Agent 侧设计
- [讨论记录](../v11.6_model_discussion_record.md) - 设计讨论记录

---

## 开发规范

### 文件命名

```
src/mini_agent/model_manager/
├── __init__.py
├── provider_config.py        # Provider 配置
├── model_registry.py         # 模型注册表
├── model_configs.py          # 模型参数配置
├── capability_probe.py       # 能力探测
├── health_monitor.py         # 健康监控
├── circuit_breaker.py        # 熔断器
├── token_stats.py            # Token 统计
├── model_alias.py            # 模型别名
├── interfaces.py             # 接口实现
└── views.py                  # 视图对象
```

### 测试文件

```
tests/model_manager/
├── test_provider_config.py
├── test_model_registry.py
├── test_model_configs.py
├── test_capability_probe.py
├── test_health_breaker.py
├── test_token_stats.py
├── test_model_alias.py
└── test_interfaces.py
```
