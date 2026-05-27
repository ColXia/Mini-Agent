# Security 模块开发索引

**版本**: v11.14
**创建时间**: 2026-05-11
**状态**: 设计文档索引

---

## 模块概述

Security 模块负责 Mini-Agent 的安全策略：

- 运行时策略引擎
- 沙箱管理
- 网络访问控制
- 审批流程

---

## 核心组件

| 组件 | 职责 |
|------|------|
| `RuntimePolicyEngine` | 运行时策略引擎 |
| `SandboxMode` | 沙箱模式 |
| `NetworkAccessMode` | 网络访问模式 |
| `ApprovalProfile` | 审批配置 |

---

## 文件位置

```
src/mini_agent/security/
├── __init__.py
├── policy.py                    # 运行时策略
├── sandbox.py                   # 沙箱管理
└── approval.py                  # 审批流程
```

---

## 相关文档

- [Tools 模块](../v11.13_tools/README.md)
- [Agent Core 模块](../v11.7_agent_core/README.md)
