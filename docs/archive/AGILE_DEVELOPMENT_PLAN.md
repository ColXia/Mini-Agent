# Mini-Agent 敏捷开发方案

> Created: 2026-04-05
> Status: All MVPs & Iterations 1-10 Completed - Project Complete
> Approach: MVP First, Iterate Later

---

## 一、敏捷开发原则

1. **核心功能优先** - 先打通主链路，再增强稳定性
2. **最小可用** - 每个 MVP 都能独立运行和验证
3. **迭代增强** - MVP 打通后逐步增加高级功能
4. **移交友好** - 详细记录开发过程，便于接手

---

## 二、MVP 规划

### MVP1: 多模型可用 (1周) - ✅ 完成

**目标**: 用户能配置多个 Provider，Agent 能正常调用

**实现状态**:
- [x] Provider 配置模型 (`provider.py`) - 已存在
- [x] 熔断器 (`circuit_breaker.py`) - 已存在
- [x] 健康监控 (`health_monitor.py`) - 已存在
- [x] 故障转移 (`failover.py`) - 已存在
- [x] 错误分类 (`error_classifier.py`) - 已存在
- [x] 模型映射 (`model_mapper.py`) - 已存在
- [x] 请求整流 (`rectifier.py`) - 已存在
- [x] 运行时路由 (`runtime.py`) - 已存在
- [x] CLI provider 命令 - 已添加

**验收标准**: ✅ 通过
```bash
mini-agent provider add --name "openai" --url "..." --key "sk-..."
mini-agent provider list
# Agent 能正常调用任一 Provider
```

**开发日志**: `docs/DEVLOG_MVP1.md`

---

### MVP2: 记忆增强 (1周) - ✅ 完成

**目标**: Agent 有更好的记忆检索能力

**实现状态**:
- [x] FTS5 全文搜索 (`session_search.py`)
- [x] MEMORY.md 发现和追加 (`memory_files.py`)
- [x] Memoria 记忆引擎 (`memoria_engine.py`)
- [x] 记忆巩固管道 (`consolidation.py`)
- [x] 相关性检索 (`relevance.py`)
- [x] 单元测试覆盖

**验收标准**: ✅ 通过
```python
from mini_agent.memory import SessionSearchIndex, discover_memory_layout
index = SessionSearchIndex(Path("~/.mini-agent/sessions"))
hits = index.search(query="deterministic planner", limit=10)
```

**开发日志**: `docs/DEVLOG_MVP2.md`

---

### MVP3: 编程代理基础 (1.5周) - ✅ 完成

**目标**: Agent 能安全执行代码

**实现状态**:
- [x] Windows 沙箱 (`sandbox/windows.py`)
- [x] 网络策略 (`sandbox/network.py`)
- [x] 声明式工具 (`tools/builder.py`)
- [x] 协调器 (`coordinator.py`)
- [x] 权限系统 (`permissions/`)
- [x] 上下文压缩 (`context_compression.py`)
- [x] 调度器 (`scheduler.py`)
- [x] 单元测试覆盖

**验收标准**: ✅ 通过
```python
from mini_agent.code_agent import WindowsRestrictedSandbox, DeclarativeTool
# 沙箱安全执行命令
# 声明式工具构建
```

**开发日志**: `docs/DEVLOG_MVP3.md`

---

### MVP4: 智能体核心 (1.5周) - ✅ 完成

**目标**: Agent 有路由和调度能力

**实现状态**:
- [x] 路由系统 (`routing.py`)
- [x] 定时任务 (`cron/`)
- [x] 技能加载 (`skills/`)
- [x] 委托管理 (`delegation.py`)
- [x] 浏览器控制 (`browser/`)
- [x] 会话管理 (`session/`)
- [x] 安全配对 (`security/`)
- [x] 单元测试覆盖

**验收标准**: ✅ 通过
```python
from mini_agent.agent_core import AgentRouteTable, AgentCronScheduler, AgentSkillLoader
# 路由、调度、技能加载
```

**开发日志**: `docs/DEVLOG_MVP4.md`

---

### MVP5: 技能平台 (1周) - ✅ 完成

**目标**: Agent 能加载和使用技能

**实现状态**:
- [x] 技能加载器 (`loader.py`)
- [x] 技能注册表 (`registry.py`)
- [x] 资格检查 (`eligibility.py`)
- [x] 运行时桥接
- [x] 工具集成
- [x] 单元测试覆盖

**验收标准**: ✅ 通过
```python
from mini_agent.tools.skill_loader import SkillLoader
loader = SkillLoader(skills_dir="skills")
skill = loader.get_skill("my_skill")
```

**开发日志**: `docs/DEVLOG_MVP5.md`

---

### MVP6: 渠道完善 (1周) - ✅ 完成

**目标**: QQ/微信渠道可用

**实现状态**:
- [x] 渠道基类 (`base.py`)
- [x] QQ Bot 适配器 (`qqbot.py`)
- [x] 微信适配器 (`wechat.py`)
- [x] 单元测试覆盖

**验收标准**: ✅ 通过
```bash
mini-agent --channel qqbot
# QQ 消息能正常收发
```

**开发日志**: `docs/DEVLOG_MVP6.md`

---

## 三、迭代增强路径

### 迭代 1: 稳定性增强 ✅ 完成

**实现状态**:
- [x] 熔断器 (`circuit_breaker.py`)
- [x] 故障转移 (`failover.py`)
- [x] 健康检查 (`health_monitor.py`)
- [x] 请求整流 (`rectifier.py`)

### 迭代 2: 记忆增强 ✅ 完成

**实现状态**:
- [x] Memoria STM/LTM (`memoria_engine.py`)
- [x] 两阶段巩固 (`consolidation.py`)
- [x] 用户画像 (`user_modeling.py`)

### 迭代 3: 编程增强 ✅ 完成

**实现状态**:
- [x] Coordinator 协调器 (`coordinator.py`)
- [x] 反向 Token 预算 (`context_compression.py`)
- [x] MCP 客户端 (`mcp_client.py`)

### 迭代 4: 智能体增强 ✅ 完成

**实现状态**:
- [x] 9 级路由 (`routing.py`)
- [x] 自学习技能 (`self_improve.py`) [新增]
- [x] 浏览器控制 (`browser/`)

**开发日志**: `docs/DEVLOG_ITERATIONS.md`

### 迭代 5: 性能优化 ✅ 完成

**实现状态**:
- [x] LRU 缓存层 (`utils/cache.py`)
- [x] 连接池 (`utils/concurrency.py`)
- [x] 请求批处理 (`utils/concurrency.py`)
- [x] 速率限制 (`utils/concurrency.py`)

### 迭代 6: 安全增强 ✅ 完成

**实现状态**:
- [x] 密钥加密存储 (`security/key_store.py`)
- [x] 审计日志增强 (`security/audit_log.py`)

### 迭代 7: 可观测性 ✅ 完成

**实现状态**:
- [x] Prometheus 指标 (`ops/metrics.py`)

**开发日志**: `docs/DEVLOG_ITERATIONS_5-7.md`

### 迭代 8: 分布式支持 ✅ 完成

**实现状态**:
- [x] 分布式缓存 (`utils/distributed_cache.py`)
- [x] 分布式锁 (`utils/distributed_lock.py`)
- [x] 服务发现 (`utils/service_discovery.py`)

### 迭代 9: 高可用 ✅ 完成

**实现状态**:
- [x] 健康检查端点 (`ops/health.py`)
- [x] 优雅关闭 (`ops/shutdown.py`)
- [x] 故障恢复 (`ops/recovery.py`)

### 迭代 10: 扩展性 ✅ 完成

**实现状态**:
- [x] 插件系统增强 (`plugins/loader.py`)
- [x] 自定义工具注册 (`plugins/loader.py`)
- [x] Webhook 支持 (`plugins/webhook.py`)

**开发日志**: `docs/DEVLOG_ITERATIONS_8-10.md`

---

## 四、开发日志索引

| 文档 | 状态 | 内容 |
|------|------|------|
| `docs/DEVLOG_MVP1.md` | ✅ 完成 | MVP1 多模型可用开发记录 |
| `docs/DEVLOG_MVP2.md` | ✅ 完成 | MVP2 记忆增强开发记录 |
| `docs/DEVLOG_MVP3.md` | ✅ 完成 | MVP3 编程代理开发记录 |
| `docs/DEVLOG_MVP4.md` | ✅ 完成 | MVP4 智能体核心开发记录 |
| `docs/DEVLOG_MVP5.md` | ✅ 完成 | MVP5 技能平台开发记录 |
| `docs/DEVLOG_MVP6.md` | ✅ 完成 | MVP6 渠道完善开发记录 |
| `docs/DEVLOG_ITERATIONS.md` | ✅ 完成 | 迭代增强开发记录 |

---

## 五、接手指南

### 当前状态

查看 `docs/DEVLOG_MVP1.md` 了解当前开发进度。

### 代码结构

```
mini_agent/
├── model_manager/      # [新增] MVP1 目标
├── memory/             # [待建] MVP2 目标
├── code_agent/         # [待建] MVP3 目标
├── agent_core/         # [待建] MVP4/5 目标
└── channels/           # [待完善] MVP6 目标
```

### 关键文件

| 文件 | 说明 |
|------|------|
| `mini_agent/config.py` | 配置系统，需要扩展多 Provider |
| `mini_agent/llm/` | LLM 客户端，需要增加路由 |
| `mini_agent/cli.py` | CLI 入口，需要增加 provider 命令 |

### 测试验证

```bash
# 添加 Provider
mini-agent provider add --name "test" --url "http://localhost:8080" --key "test-key"

# 列出 Provider
mini-agent provider list

# 测试调用
mini-agent cli --task "hello"
```
