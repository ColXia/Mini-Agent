# Memory 模块开发索引

**版本**: v11.15
**创建时间**: 2026-05-11
**状态**: 设计文档索引

---

## 模块概述

Memory 模块负责 Mini-Agent 的记忆系统：

- 工作记忆
- 短期记忆
- 长期记忆
- 记忆检索

---

## 核心组件

| 组件 | 职责 |
|------|------|
| `MemoryStore` | 记忆存储 |
| `WorkingMemory` | 工作记忆 |
| `ShortTermMemory` | 短期记忆 |
| `LongTermMemory` | 长期记忆 |
| `SessionSearchIndex` | 会话搜索索引 |

---

## 文件位置

```
src/mini_agent/memory/
├── __init__.py
├── store.py                     # 记忆存储
├── working.py                   # 工作记忆
├── short_term.py                # 短期记忆
├── long_term.py                 # 长期记忆
├── session_search.py            # 会话搜索
└── relevance.py                 # 相关性检索
```

---

## 相关文档

- [Session 模块](../v11.11_session/README.md)
- [Agent Core 模块](../v11.7_agent_core/README.md)
