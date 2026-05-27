# Agent Core 模块开发索引

**版本**: v11.7
**创建时间**: 2026-05-11
**状态**: 设计文档补全完成

---

## 文档结构

```
v11.7_agent_core/
├── README.md                    # 本文件 - 开发索引
├── 01_contracts.md              # 合约系统 (Profile/Instance/Run)
├── 02_engine.md                  # Agent 引擎核心
├── 03_execution_loop.md          # 执行循环与状态机
├── 04_tool_execution.md         # 工具执行协调器
├── 05_permissions.md             # 权限与审批系统
├── 06_context_system.md          # 上下文系统
├── 07_skills.md                  # 技能系统
├── 08_session.md                 # 会话管理
├── 09_model_binding.md           # 模型绑定 (引用 v11.6 文档)
└── 10_cli_commands.md            # CLI 命令
```

---

## 模块概述

Agent Core 是 Mini-Agent 的核心运行时模块，负责：

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Core Layer                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Engine (Agent 类)                                       │   │
│  │  - 执行循环 (run_turn, run)                              │   │
│  │  - 状态管理 (messages, tokens)                           │   │
│  │  - 钩子系统 (hooks)                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Contracts (合约系统)                                    │   │
│  │  - AgentProfile (静态配置)                               │   │
│  │  - AgentInstance (运行时实例)                             │   │
│  │  - Run (执行单元)                                        │   │
│  │  - Checkpoint (检查点)                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Execution (执行系统)                                    │   │
│  │  - AgentLoop (提交循环)                                  │   │
│  │  - ToolExecutionCoordinator (工具执行协调)               │   │
│  │  - Permissions (权限系统)                                │   │
│  │  - Sandbox (沙箱执行)                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Context (上下文系统)                                    │   │
│  │  - TurnContext (回合上下文)                              │   │
│  │  - ContextAssembler (上下文组装)                         │   │
│  │  - ContextCompaction (上下文压缩)                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Skills (技能系统)                                       │   │
│  │  - SkillRegistry (技能注册表)                            │   │
│  │  - SkillLoader (技能加载器)                              │   │
│  │  - SkillEligibility (技能资格检查)                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Session (会话系统)                                      │   │
│  │  - Lifecycle (生命周期管理)                              │   │
│  │  - Lineage (血缘追踪)                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 开发阶段

### Phase 0: 合约系统 (P0)

| 任务 | 文档 | 状态 |
|------|------|------|
| AgentProfile 数据结构 | [01_contracts.md](01_contracts.md) | 待开发 |
| AgentInstance 生命周期 | [01_contracts.md](01_contracts.md) | 待开发 |
| Run 执行单元 | [01_contracts.md](01_contracts.md) | 待开发 |
| Checkpoint 检查点 | [01_contracts.md](01_contracts.md) | 待开发 |

### Phase 1: 引擎核心 (P0)

| 任务 | 文档 | 状态 |
|------|------|------|
| Agent 类核心实现 | [02_engine.md](02_engine.md) | 待开发 |
| 执行策略配置 | [02_engine.md](02_engine.md) | 待开发 |
| 钩子系统 | [02_engine.md](02_engine.md) | 待开发 |

### Phase 2: 执行循环 (P0)

| 任务 | 文档 | 状态 |
|------|------|------|
| AgentLoop 状态机 | [03_execution_loop.md](03_execution_loop.md) | 待开发 |
| Step 执行流程 | [03_execution_loop.md](03_execution_loop.md) | 待开发 |
| 错误处理与恢复 | [03_execution_loop.md](03_execution_loop.md) | 待开发 |

### Phase 3: 工具执行 (P1)

| 任务 | 文档 | 状态 |
|------|------|------|
| ToolExecutionCoordinator | [04_tool_execution.md](04_tool_execution.md) | 待开发 |
| 工具调用流程 | [04_tool_execution.md](04_tool_execution.md) | 待开发 |
| MCP 工具集成 | [04_tool_execution.md](04_tool_execution.md) | 待开发 |

### Phase 4: 权限系统 (P1)

| 任务 | 文档 | 状态 |
|------|------|------|
| ApprovalEngine | [05_permissions.md](05_permissions.md) | 待开发 |
| 权限策略配置 | [05_permissions.md](05_permissions.md) | 待开发 |
| 审批流程 | [05_permissions.md](05_permissions.md) | 待开发 |

### Phase 5: 上下文系统 (P1)

| 任务 | 文档 | 状态 |
|------|------|------|
| TurnContext 服务 | [06_context_system.md](06_context_system.md) | 待开发 |
| ContextAssembler | [06_context_system.md](06_context_system.md) | 待开发 |
| ContextCompaction | [06_context_system.md](06_context_system.md) | 待开发 |

### Phase 6: 技能系统 (P2)

| 任务 | 文档 | 状态 |
|------|------|------|
| SkillRegistry | [07_skills.md](07_skills.md) | 待开发 |
| SkillLoader | [07_skills.md](07_skills.md) | 待开发 |
| SkillEligibility | [07_skills.md](07_skills.md) | 待开发 |

### Phase 7: 会话系统 (P2)

| 任务 | 文档 | 状态 |
|------|------|------|
| SessionLifecycle | [08_session.md](08_session.md) | 待开发 |
| SessionLineage | [08_session.md](08_session.md) | 待开发 |

---

## 相关文档

- [模型绑定设计](../v11.6_agent_model_binding_plan.md) - Agent 模型绑定与故障转移
- [模型服务设计](../v11.6_model_service_plan.md) - 模型侧设计
- [Agent Core 模块说明](../../project-documentation/03_agent_core模块.md) - 模块概述

---

## 文件命名规范

### 源码结构

```
src/mini_agent/agent_core/
├── __init__.py
├── engine.py                 # Agent 引擎
├── kernel.py                 # 内核构建器
├── routing.py                # 路由表
├── delegation.py             # 子 Agent 委派
├── presentation.py           # 运行时呈现器
├── runtime_bindings.py       # 运行时绑定
├── post_turn.py              # 回合后副作用
│
├── contracts/                # 合约定义
│   ├── agent_profile.py
│   ├── agent_instance.py
│   ├── run.py
│   ├── checkpoint.py
│   ├── execution_journal.py
│   └── attachments.py
│
├── execution/                # 执行引擎
│   ├── agent_loop.py
│   ├── coordinator.py
│   ├── tool_execution_coordinator.py
│   ├── permissions/
│   ├── sandbox/
│   └── tools/
│
├── context/                  # 上下文管理
│   ├── turn_context.py
│   ├── context_assembler.py
│   └── context_compaction.py
│
├── skills/                   # 技能系统
│   ├── registry.py
│   ├── loader.py
│   └── eligibility.py
│
├── session/                  # 会话管理
│   ├── lifecycle.py
│   └── lineage.py
│
├── browser/                  # 浏览器集成
├── cron/                     # 定时任务
├── security/                 # 安全模块
└── history/                  # 历史记录
```

### 测试文件

```
tests/agent_core/
├── test_contracts.py
├── test_engine.py
├── test_execution_loop.py
├── test_tool_execution.py
├── test_permissions.py
├── test_context_system.py
├── test_skills.py
└── test_session.py
```
