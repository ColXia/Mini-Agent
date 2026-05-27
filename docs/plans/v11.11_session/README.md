# Session 模块开发索引

**版本**: v11.11
**创建时间**: 2026-05-11
**状态**: 设计文档补全完成

---

## 文档结构

```
v11.11_session/
├── README.md                    # 本文件 - 开发索引
├── 01_state_records.md          # 会话状态记录
├── 02_persistence.md            # 持久化存储
├── 03_lineage.md                # 会话血缘追踪
├── 04_bindings.md               # 会话绑定
├── 05_projections.md            # 读模型投影
└── 06_lifecycle.md              # 生命周期管理
```

---

## 模块概述

Session 模块负责 Mini-Agent 的会话状态管理和持久化：

```
┌─────────────────────────────────────────────────────────────────┐
│                        Session Layer                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   State Records                          │   │
│  │  MainAgentSessionState, MainAgentSessionProjectionState │   │
│  │  MainAgentSessionRuntimeHostState, TranscriptState      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Persistence Layer                      │   │
│  │  SessionPersistence, MainAgentRuntimePersistence,       │   │
│  │  RuntimeSessionPersistenceRecordBuilder                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Lineage Tracking                       │   │
│  │  SessionLineageStore, RuntimeSessionLineageRegistry,    │   │
│  │  SessionLineageNode                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Bindings Layer                         │   │
│  │  ConversationBindingStore, ConversationBindingService,  │   │
│  │  ConversationBindingPort                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Projections Layer                      │   │
│  │  SessionSummaryProjection, SessionDetailProjection,     │   │
│  │  SessionMessageProjection, SessionRecoveryProjection    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Lifecycle Layer                        │   │
│  │  SessionLifecycleManager, SessionLifecyclePolicy,       │   │
│  │  SessionLifecycleState, SessionResetMode                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心组件

| 组件 | 职责 |
|------|------|
| `MainAgentSessionState` | 会话状态主记录 |
| `SessionPersistence` | 文件系统持久化 |
| `SessionLineageStore` | 会话血缘图 |
| `ConversationBindingService` | 对话-会话绑定 |
| `SessionSummaryProjection` | 会话摘要投影 |
| `SessionLifecycleManager` | 生命周期管理 |

---

## 文件位置

```
src/mini_agent/session/
├── __init__.py                  # 模块标记
├── store_records.py             # 会话状态记录
├── persistence.py               # 持久化存储
├── lineage.py                   # 血缘追踪
├── bindings.py                  # 会话绑定
├── projections.py               # 读模型投影
└── recovery_feedback.py         # 恢复反馈

src/mini_agent/agent_core/session/
├── __init__.py
├── session_key.py               # 会话键模型
├── lineage.py                   # 血缘节点存储
└── lifecycle.py                 # 生命周期管理
```

---

## 相关文档

- [Workspace & Session 模块说明](../../project-documentation/03_workspace_session模块.md)
- [Runtime 模块](../v11.10_runtime/README.md)
- [Agent Core 模块](../v11.7_agent_core/README.md)
