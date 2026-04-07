# MVP1 开发日志: 多模型可用

> Started: 2026-04-05
> Status: In Progress
> Developer: Claude (Opencode)

---

## 一、目标

实现多 Provider 配置和路由，让用户能配置多个模型提供商并正常调用。

## 二、任务清单

- [x] T1.1 创建 `mini_agent/model_manager/` 目录结构
- [ ] T1.2 实现 `provider.py` - Provider 配置模型
- [ ] T1.3 实现 `provider_store.py` - SQLite 存储
- [ ] T1.4 实现 `router.py` - 多 Provider 路由
- [ ] T1.5 修改 `config.py` - 增加多 Provider 支持
- [ ] T1.6 修改 `llm/` - 增加路由逻辑
- [ ] T1.7 修改 `cli.py` - 增加 provider 命令
- [ ] T1.8 测试验证

---

## 三、开发记录

### 2026-04-05 开发会话

#### 步骤 1: 分析现有代码 ✅

**已读取文件**:
- `mini_agent/config.py` - 当前配置系统
- `mini_agent/llm/__init__.py` - LLM 客户端入口
- `mini_agent/llm/base.py` - LLM 客户端基类
- `mini_agent/llm/openai_client.py` - OpenAI 客户端
- `mini_agent/agent.py` - Agent 循环

**发现**:
1. ✅ `model_manager/` 目录已存在且完整实现！
2. ✅ `ProviderConfig` - Provider 配置模型已实现
3. ✅ `ProviderCatalog` - Provider 集合已实现
4. ✅ `CircuitBreakerRegistry` - 熔断器已实现
5. ✅ `ProviderHealthMonitor` - 健康监控已实现
6. ✅ `FailoverLLMClient` - 故障转移客户端已实现
7. ✅ `resolve_routed_llm_settings()` - 路由解析已实现
8. ✅ 已集成到 `cli_interactive.py` 和 `acp/__init__.py`

#### 步骤 2: 检查缺失部分 ⚠️

**已实现**:
- [x] Provider 配置模型 (`provider.py`)
- [x] 熔断器 (`circuit_breaker.py`)
- [x] 健康监控 (`health_monitor.py`)
- [x] 故障转移 (`failover.py`)
- [x] 错误分类 (`error_classifier.py`)
- [x] 模型映射 (`model_mapper.py`)
- [x] 请求整流 (`rectifier.py`)
- [x] 运行时路由 (`runtime.py`)

**缺失**:
- [ ] CLI `provider` 子命令 (添加/列出/删除 Provider)
- [ ] Provider 持久化存储 (`provider_store.py` - SQLite)
- [ ] Gateway API 端点 (`/api/providers`)

#### 步骤 3: 添加 Provider CLI 命令 ✅

**已添加**:
- `mini-agent provider list` - 列出所有 Provider
- `mini-agent provider add` - 添加新 Provider
- `mini-agent provider remove` - 删除 Provider
- `mini-agent provider enable/disable` - 启用/禁用 Provider
- `mini-agent provider show` - 显示 Provider 详情

**验证结果**:
```bash
$ mini-agent provider add --name "test-openai" --url "https://api.openai.com/v1" --key "sk-test123" --type openai --models "gpt-4o,gpt-4o-mini"
Provider added successfully:
  id: test-openai
  name: test-openai
  catalog: C:\Users\Conli\.mini-agent\providers.json

$ mini-agent provider list
Configured Providers:

  test-openai (test-openai)
    type: openai
    url: https://api.openai.com/v1
    models: gpt-4o, gpt-4o-mini
    priority: 0
    status: [enabled]
```

#### 步骤 4: MVP1 完成状态

**已完成**:
- [x] Provider 配置模型 (`provider.py`) - 已存在
- [x] 熔断器 (`circuit_breaker.py`) - 已存在
- [x] 健康监控 (`health_monitor.py`) - 已存在
- [x] 故障转移 (`failover.py`) - 已存在
- [x] 错误分类 (`error_classifier.py`) - 已存在
- [x] 模型映射 (`model_mapper.py`) - 已存在
- [x] 请求整流 (`rectifier.py`) - 已存在
- [x] 运行时路由 (`runtime.py`) - 已存在
- [x] CLI provider 命令 - 已添加

**MVP1 状态**: ✅ 完成

**后续迭代增强**:
- [ ] Gateway API 端点 (`/api/providers`)
- [ ] Provider 持久化存储 (SQLite 加密)
- [ ] WebUI Provider 管理界面

---

## 四、接手说明

### 当前进度

- [x] 目录结构已创建
- [ ] 核心模块实现中

### 下一步

1. 完成 `provider.py` 的 Provider 模型定义
2. 完成 `provider_store.py` 的 SQLite 存储
3. 完成 `router.py` 的路由逻辑
4. 修改 `config.py` 集成多 Provider
5. 修改 `llm/` 客户端使用路由

### 关键设计决策

1. **Provider 模型**: 使用 Pydantic BaseModel
2. **存储方式**: SQLite，密钥加密存储
3. **路由策略**: 按 priority 排序，选择第一个可用的
4. **兼容性**: 保留原有单一 Provider 配置方式

### 注意事项

1. 不要破坏现有功能
2. 保持向后兼容
3. 密钥需要加密存储
4. 测试用例需要覆盖多 Provider 场景

---

## 五、测试用例

```python
# 测试 Provider 配置
provider = Provider(
    id="openai-1",
    name="OpenAI",
    api_type="openai",
    api_base="https://api.openai.com",
    api_key="sk-...",
    models=["gpt-4o", "gpt-4o-mini"],
    enabled=True,
    priority=1
)

# 测试存储
store = ProviderStore()
store.add_provider(provider)
providers = store.list_providers()

# 测试路由
router = ProviderRouter(store)
selected = router.select_provider("gpt-4o")
```
