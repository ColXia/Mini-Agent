# Workspace 模块开发索引

**版本**: v11.12
**创建时间**: 2026-05-11
**状态**: 设计文档补全完成

---

## 文档结构

```
v11.12_workspace/
├── README.md                    # 本文件 - 开发索引
├── 01_domain.md                 # 工作空间域模型
├── 02_boundary.md               # 边界管理
├── 03_permission.md             # 权限表
├── 04_mutation_ledger.md        # 变更账本
├── 05_snapshot_store.md         # 快照存储
├── 06_executor.md               # 工作空间执行器
├── 07_runtime_modes.md          # 运行时模式
├── 08_outside_zone.md           # 外部区域策略
└── 09_stack_manager.md          # 运行时栈管理器
```

---

## 模块概述

Workspace 模块负责 Mini-Agent 的工作空间管理：

```
┌─────────────────────────────────────────────────────────────────┐
│                        Workspace Layer                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Domain Layer                            │   │
│  │  WorkspaceKind, WorkspaceManifest, WorkspaceRecord       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Boundary Layer                         │   │
│  │  WorkspaceBoundary, MainAgentWorkspaceRuntimeAdapter     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Permission Layer                       │   │
│  │  WorkspacePermissionTable, WorkspacePermissionRule,      │   │
│  │  WorkspacePermissionDecision                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Execution Layer                        │   │
│  │  WorkspaceExecutor, WorkspaceRuntimeBundle,              │   │
│  │  WorkspacePathAccess, WorkspaceAccessScope                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Mutation Layer                          │   │
│  │  InMemoryMutationLedger, MutationRecord, MutationKind     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Snapshot Layer                         │   │
│  │  InMemoryWorkspaceSnapshotStore, WorkspaceRuntimeSnapshot │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Runtime Stack                          │   │
│  │  RuntimeStackManager, RuntimeStackStatus                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心组件

| 组件 | 职责 |
|------|------|
| `WorkspaceManifest` | 工作空间清单 |
| `WorkspaceBoundary` | 边界管理 |
| `WorkspacePermissionTable` | 权限表 |
| `WorkspaceExecutor` | 执行器 |
| `InMemoryMutationLedger` | 变更账本 |
| `InMemoryWorkspaceSnapshotStore` | 快照存储 |
| `RuntimeStackManager` | 运行时栈管理 |

---

## 文件位置

```
src/mini_agent/workspace/
├── __init__.py
└── domain.py                   # 域模型

src/mini_agent/workspace_runtime/
├── __init__.py
├── boundary.py                 # 边界管理
├── permission_table.py         # 权限表
├── mutation_ledger.py          # 变更账本
├── snapshot_store.py           # 快照存储
├── workspace_executor.py       # 执行器
├── runtime_modes.py            # 运行时模式
├── outside_zone_policy.py      # 外部区域策略
├── runtime_stack_manager.py    # 运行时栈管理
└── adapters/
    ├── __init__.py
    └── direct_executor.py      # 直接执行器适配
```

---

## 相关文档

- [Workspace & Session 模块说明](../../project-documentation/03_workspace_session模块.md)
- [Session 模块](../v11.11_session/README.md)
- [Runtime 模块](../v11.10_runtime/README.md)
