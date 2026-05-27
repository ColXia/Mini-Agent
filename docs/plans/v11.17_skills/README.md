# Skills 模块开发索引

**版本**: v11.17
**创建时间**: 2026-05-11
**状态**: 设计文档索引

---

## 模块概述

Skills 模块负责 Mini-Agent 的技能系统：

- 技能注册
- 技能加载
- 技能执行
- 技能验证

---

## 核心组件

| 组件 | 职责 |
|------|------|
| `SkillRegistry` | 技能注册表 |
| `SkillLoader` | 技能加载器 |
| `SkillExecutor` | 技能执行器 |
| `SkillValidator` | 技能验证器 |

---

## 文件位置

```
src/mini_agent/skills/
├── __init__.py
├── registry.py                  # 技能注册表
├── loader.py                    # 技能加载器
├── executor.py                  # 技能执行器
└── validator.py                 # 技能验证器
```

---

## 相关文档

- [Tools 模块](../v11.13_tools/README.md)
- [Agent Core 模块](../v11.7_agent_core/README.md)
