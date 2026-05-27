# Tools 模块开发索引

**版本**: v11.13
**创建时间**: 2026-05-11
**状态**: 设计文档补全完成

---

## 文档结构

```
v11.13_tools/
├── README.md                    # 本文件 - 开发索引
├── 01_contracts.md              # 工具契约
├── 02_registry.md               # 工具注册表
├── 03_permission.md             # 权限引擎
├── 04_file_tools.md             # 文件工具
├── 05_bash_tool.md              # Shell 工具
└── 06_mcp_tools.md              # MCP 工具
```

---

## 模块概述

Tools 模块负责 Mini-Agent 的工具系统：

```
┌─────────────────────────────────────────────────────────────────┐
│                        Tools Layer                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Contracts Layer                        │   │
│  │  ToolSpec, ToolBinding, ToolPolicy, ToolGrant            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Registry Layer                         │   │
│  │  ToolRegistry, shared_tool_registry                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Permission Layer                       │   │
│  │  PermissionEngine, PermissionRequest, OutsideZonePolicy  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Core Tools                             │   │
│  │  ReadTool, WriteTool, EditTool, BashTool                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   MCP Tools                              │   │
│  │  MCPRegistry, MCPExecutor, MCPLifecycle                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心组件

| 组件 | 职责 |
|------|------|
| `ToolSpec` | 工具规格定义 |
| `ToolRegistry` | 工具注册表 |
| `PermissionEngine` | 权限引擎 |
| `ReadTool` | 文件读取工具 |
| `WriteTool` | 文件写入工具 |
| `EditTool` | 文件编辑工具 |
| `BashTool` | Shell 执行工具 |

---

## 文件位置

```
src/mini_agent/tools/
├── __init__.py
├── base.py                      # Tool, ToolResult 基类
├── contracts.py                 # 工具契约
├── registry.py                  # 工具注册表
├── permission_engine.py         # 权限引擎
├── file_tools.py                # 文件工具
├── bash_tool.py                 # Shell 工具
├── skill_tool.py                # 技能工具
├── skill_loader.py              # 技能加载器
├── knowledge_base.py            # 知识库工具
├── web_search.py                # Web 搜索工具
├── mcp_loader.py                # MCP 加载器
└── mcp/
    ├── __init__.py
    ├── registry.py              # MCP 注册表
    ├── executor.py              # MCP 执行器
    ├── lifecycle.py             # MCP 生命周期
    ├── discovery.py             # MCP 发现
    ├── types.py                 # MCP 类型
    └── naming.py                # MCP 命名
```

---

## 相关文档

- [Agent Core 模块](../v11.7_agent_core/README.md)
- [Workspace 模块](../v11.12_workspace/README.md)
- [Security 模块](../v11.14_security/README.md)
