# Schema 模块开发索引

**版本**: v11.20
**创建时间**: 2026-05-11
**状态**: 设计文档索引

---

## 模块概述

Schema 模块定义 Mini-Agent 的数据模型：

- Pydantic 模型
- 数据验证
- 序列化/反序列化
- 类型定义

---

## 核心组件

| 组件 | 职责 |
|------|------|
| `BaseModel` | 基础模型 |
| `Field` | 字段定义 |
| `Validator` | 验证器 |
| `SchemaRegistry` | 模式注册表 |

---

## 文件位置

```
src/mini_agent/schema/
├── __init__.py
├── base.py                      # 基础模型
├── fields.py                    # 字段定义
├── validators.py                # 验证器
└── registry.py                  # 模式注册表
```

---

## 相关文档

- [Interfaces 模块](../v11.19_interfaces/README.md)
- [Config 模块](../v11.18_config/README.md)