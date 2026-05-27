# Application 层开发索引

**版本**: v11.9
**创建时间**: 2026-05-11
**状态**: 设计文档补全完成

---

## 文档结构

```
v11.9_application/
├── README.md                    # 本文件 - 开发索引
├── 01_ports.md                  # 端口定义
├── 02_use_cases.md              # 用例服务
├── 03_facades.md                # 门面服务
└── 04_user_services.md          # 用户服务
```

---

## 模块概述

Application 层采用**六边形架构**设计，遵循**依赖倒置原则**：

```
┌─────────────────────────────────────────────────────────────────┐
│                        Application Layer                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   User Services Layer                    │   │
│  │  WorkspaceUserService, AgentUserService, ModelUserService │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Use Cases Layer                       │   │
│  │  AgentApplicationService, RunControlApplicationService,  │   │
│  │  SessionTaskService, WorkspaceApplicationService         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                      Ports Layer                         │   │
│  │  AgentRuntimePort, RunRuntimePort, WorkspaceRuntimePort, │   │
│  │  ModelRuntimePort, SessionTaskPort                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 设计原则

1. **依赖倒置**: 上层依赖 Port 协议，而非具体实现
2. **单一职责**: 每个服务专注于单一领域
3. **开闭原则**: 通过 Port 扩展，不修改现有代码
4. **接口隔离**: Port 定义最小必要接口
5. **延迟初始化**: User Service 支持按需创建 Application Service

---

## 文件位置

```
src/mini_agent/application/
├── ports/                  # 端口层
│   ├── agent_runtime_port.py
│   ├── run_runtime_port.py
│   ├── workspace_runtime_port.py
│   ├── model_runtime_port.py
│   ├── session_agent_runtime_port.py
│   ├── session_task_port.py
│   └── session_task_runtime_port.py
│
├── use_cases/              # 用例层
│   ├── agent_application_service.py
│   ├── run_control_application_service.py
│   ├── session_task_service.py
│   ├── workspace_application_service.py
│   ├── model_binding_application_service.py
│   ├── command_application_service.py
│   └── agent_interaction_application_service.py
│
├── facades/                # 门面层
│   ├── surface_chat_flow_handler.py
│   ├── agent_turn_execution_handler.py
│   ├── agent_route_execution_handler.py
│   └── agent_delegation_execution_handler.py
│
├── user_services/          # 用户服务层
│   ├── agent_user_service.py
│   ├── workspace_user_service.py
│   ├── model_user_service.py
│   ├── command_user_service.py
│   └── service_assembly.py
│
└── support/                # 支撑层
    ├── interaction_request_adapter.py
    ├── managed_session_turn.py
    └── surface_service_types.py
```

---

## 相关文档

- [Application 层说明](../../project-documentation/03_application层.md)
- [Agent Core 模块](../v11.7_agent_core/README.md)
