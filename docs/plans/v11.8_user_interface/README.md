# 用户界面模块开发索引

**版本**: v11.8
**创建时间**: 2026-05-11
**状态**: 设计文档补全完成

---

## 文档结构

```
v11.8_user_interface/
├── README.md                    # 本文件 - 开发索引
├── 01_architecture.md           # UI 架构概述
├── 02_tui.md                    # 终端用户界面 (TUI)
├── 03_desktop.md                # 桌面应用 (Desktop)
├── 04_transport.md              # 传输层
├── 05_session_coordinators.md   # 会话协调器
└── 06_cli_commands.md           # CLI 命令
```

---

## 模块概述

用户界面模块负责 Mini-Agent 与用户的交互：

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interface Layer                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │      TUI        │  │    Desktop      │  │      CLI        │ │
│  │  (Terminal UI)  │  │   (PySide6)     │  │   (Click)       │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
│           │                    │                    │          │
│           └────────────────────┼────────────────────┘          │
│                                │                                │
│                                ▼                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Transport Layer                       │   │
│  │  - GatewayClient (HTTP)                                  │   │
│  │  - Remote Clients (Chat, Run, Session, etc.)            │   │
│  │  - Local Runtime Ports                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                │                                │
│                                ▼                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 Application Layer                         │   │
│  │  - User Services (Agent, Workspace, Model, Command)      │   │
│  │  - Application Services (RunControl, SessionTask, etc.)  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 开发阶段

### Phase 0: 架构设计 (P0)

| 任务 | 文档 | 状态 |
|------|------|------|
| UI 架构概述 | [01_architecture.md](01_architecture.md) | 待开发 |
| 传输层设计 | [04_transport.md](04_transport.md) | 待开发 |

### Phase 1: TUI 模块 (P0)

| 任务 | 文档 | 状态 |
|------|------|------|
| TUI 核心实现 | [02_tui.md](02_tui.md) | 待开发 |
| 会话协调器 | [05_session_coordinators.md](05_session_coordinators.md) | 待开发 |

### Phase 2: Desktop 模块 (P1)

| 任务 | 文档 | 状态 |
|------|------|------|
| Desktop 核心实现 | [03_desktop.md](03_desktop.md) | 待开发 |

### Phase 3: CLI 命令 (P2)

| 任务 | 文档 | 状态 |
|------|------|------|
| CLI 命令设计 | [06_cli_commands.md](06_cli_commands.md) | 待开发 |

---

## 相关文档

- [Application 层](../../project-documentation/03_application层.md) - 应用层设计
- [Agent Core 模块](../../project-documentation/03_agent_core模块.md) - Agent 核心

---

## 文件命名规范

### 源码结构

```
src/mini_agent/
├── tui/                          # 终端用户界面
│   ├── __init__.py
│   ├── app.py                    # TUI 主应用
│   ├── user_service_ports.py     # 用户服务端口
│   ├── local_agent_runtime_handler.py
│   ├── session_projection.py
│   ├── session_*_coordinator.py  # 会话协调器
│   └── gateway_transport_binding.py
│
├── desktop/                      # 桌面应用
│   ├── __init__.py
│   ├── app.py                    # Desktop 启动
│   ├── window.py                 # 主窗口
│   ├── gateway_supervisor.py     # Gateway 监管
│   ├── gateway_transport_binding.py
│   └── session_actions.py        # 会话操作
│
├── transport/                    # 传输层
│   ├── __init__.py
│   ├── gateway_client.py         # Gateway HTTP 客户端
│   ├── gateway_error.py          # 错误处理
│   ├── remote_*_client.py        # 远程客户端
│   └── *_transport_port.py       # 传输端口
│
└── commands/                     # CLI 命令
    ├── __init__.py
    ├── cli.py                    # CLI 入口
    ├── parser.py                 # 命令解析
    ├── execution.py              # 命令执行
    ├── completions.py            # 自动补全
    └── metadata.py               # 命令元数据
```

### 测试文件

```
tests/
├── tui/
│   └── test_*.py
├── desktop/
│   └── test_*.py
├── transport/
│   └── test_*.py
└── commands/
    └── test_*.py
```
