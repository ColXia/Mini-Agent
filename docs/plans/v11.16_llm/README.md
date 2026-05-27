# LLM 模块开发索引

**版本**: v11.16
**创建时间**: 2026-05-11
**状态**: 设计文档索引

---

## 模块概述

LLM 模块负责 Mini-Agent 的大语言模型集成：

- 模型提供者管理
- API 客户端
- 流式响应
- Token 计数

---

## 核心组件

| 组件 | 职责 |
|------|------|
| `ModelProvider` | 模型提供者 |
| `LLMClient` | LLM 客户端 |
| `StreamHandler` | 流式处理器 |
| `TokenCounter` | Token 计数器 |

---

## 文件位置

```
src/mini_agent/llm/
├── __init__.py
├── provider.py                  # 模型提供者
├── client.py                    # LLM 客户端
├── stream.py                    # 流式处理
└── tokens.py                    # Token 计数
```

---

## 相关文档

- [Agent Core 模块](../v11.7_agent_core/README.md)
- [Config 模块](../v11.18_config/README.md)
