# Runtime 模块开发索引

**版本**: v11.10
**创建时间**: 2026-05-11
**状态**: 设计文档补全完成

---

## 文档结构

```
v11.10_runtime/
├── README.md                    # 本文件 - 开发索引
├── 01_handlers.md               # 请求处理器
├── 02_orchestration.md          # 编排服务
├── 03_live_control.md           # 实时控制
└── 04_read_models.md            # 读模型
```

---

## 模块概述

Runtime 模块是 Mini-Agent 的运行时服务层，负责：

```
┌─────────────────────────────────────────────────────────────────┐
│                        Runtime Layer                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Handlers Layer                         │   │
│  │  SessionCreationHandler, SessionRunControlHandler,       │   │
│  │  SessionAgentRuntimeHandler, SessionMemoryHandler        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 Orchestration Layer                      │   │
│  │  SessionHydrationCoordinator, SessionRuntimeLifecycle,  │   │
│  │  SessionRestoreHandler, SessionRuntimePolicyCoordinator │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  Live Control Layer                      │   │
│  │  RuntimeSessionRunControlStore, KernelStateRegistry,     │   │
│  │  SessionInterruptHandler, SessionPendingApprovalService │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Read Models Layer                      │   │
│  │  SessionReadModelBuilder, SessionSnapshotBuilder,        │   │
│  │  RunProjectionBuilder, SessionDiagnostics                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心组件

| 组件 | 职责 |
|------|------|
| `MainAgentRuntimeManager` | 运行时管理器主类 |
| `RuntimeSessionRunControlStore` | Run 控制存储 |
| `SessionHandlers` | 各类请求处理器 |
| `SessionOrchestrators` | 会话编排服务 |

---

## 文件位置

```
src/mini_agent/runtime/
├── __init__.py
├── main_agent_runtime_manager.py
│
├── handlers/                  # 请求处理器
│   ├── session_creation_handler.py
│   ├── session_run_control_handler.py
│   ├── session_agent_runtime_handler.py
│   ├── session_memory_handler.py
│   ├── session_skill_handler.py
│   ├── session_mcp_control_handler.py
│   ├── session_context_policy_handler.py
│   ├── session_runtime_policy_handler.py
│   └── session_command_coordinator.py
│
├── orchestration/             # 编排服务
│   ├── session_hydration_coordinator.py
│   ├── session_runtime_lifecycle_handler.py
│   ├── session_restore_handler.py
│   ├── session_runtime_policy_coordinator.py
│   └── main_agent_runtime_assembly_mixin.py
│
├── live_control/              # 实时控制
│   ├── run_control_store.py
│   ├── kernel_state_registry.py
│   ├── session_interrupt_handler.py
│   ├── session_cancel_service.py
│   ├── session_pending_approval_service.py
│   ├── session_turn_scope_handler.py
│   └── session_transcript_state_handler.py
│
├── read_models/               # 读模型
│   ├── session_read_model_builder.py
│   ├── session_snapshot_builder.py
│   ├── run_projection_builder.py
│   ├── session_diagnostics.py
│   ├── session_payload_codec.py
│   └── session_model_identity_codec.py
│
└── support/                   # 支撑层
    ├── interaction_surface.py
    ├── sandbox_state.py
    ├── tooling.py
    └── workspace_path_utils.py
```

---

## 相关文档

- [Runtime 模块说明](../../project-documentation/03_runtime模块.md)
- [Application 层](../v11.9_application/README.md)
- [Session 模块](../../project-documentation/03_workspace_session模块.md)