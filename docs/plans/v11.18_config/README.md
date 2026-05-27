# Config 模块开发索引

**版本**: v11.18
**创建时间**: 2026-05-11
**状态**: 设计文档索引

---

## 模块概述

Config 模块负责 Mini-Agent 的配置管理：

- 配置加载
- 配置验证
- 配置合并
- 环境变量处理

---

## 核心组件

| 组件 | 职责 |
|------|------|
| `ConfigLoader` | 配置加载器 |
| `ConfigValidator` | 配置验证器 |
| `ConfigMerger` | 配置合并器 |
| `EnvResolver` | 环境变量解析器 |

---

## 文件位置

```
src/mini_agent/config/
├── __init__.py
├── loader.py                    # 配置加载器
├── validator.py                 # 配置验证器
├── merger.py                    # 配置合并器
└── env.py                       # 环境变量处理
```

---

## 相关文档

- [LLM 模块](../v11.16_llm/README.md)
- [Security 模块](../v11.14_security/README.md)