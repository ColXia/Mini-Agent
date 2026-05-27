# Interfaces 模块开发索引

**版本**: v11.19
**创建时间**: 2026-05-11
**状态**: 设计文档索引

---

## 模块概述

Interfaces 模块定义 Mini-Agent 的公共接口：

- Agent 接口
- Session 接口
- Tool 接口
- Transport 数据模型

---

## 核心组件

| 组件 | 职责 |
|------|------|
| `MainAgentSessionDetail` | 会话详情模型 |
| `MainAgentSessionSummary` | 会话摘要模型 |
| `ToolExecutionRequest` | 工具执行请求 |
| `TransportMessage` | 传输消息 |

---

## 文件位置

```
src/mini_agent/interfaces/
├── __init__.py
├── agent.py                     # Agent 接口
├── session.py                   # Session 接口
├── tool.py                      # Tool 接口
└── transport.py                 # Transport 数据模型
```

---

## 相关文档

- [Application 模块](../v11.9_application/README.md)
- [User Interface 模块](../v11.8_user_interface/README.md)