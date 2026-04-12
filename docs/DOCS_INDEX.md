# Mini-Agent 文档索引

> **最后更新**: 2026-04-08
> **当前阶段**: TUI 主入口真实使用修边角阶段
> **文档版本**: v2.1

---

## 📋 快速导航

### 新手入门
| 文档 | 说明 | 状态 |
|------|------|------|
| [README.md](../README.md) | 项目介绍和快速开始 | ✅ 活跃 |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | 系统架构说明 | ✅ 活跃 |
| [DEVELOPMENT_GUIDE_CN.md](./DEVELOPMENT_GUIDE_CN.md) | 开发指南（中文） | ✅ 活跃 |
| [PRODUCTION_GUIDE_CN.md](./PRODUCTION_GUIDE_CN.md) | 生产部署指南（中文） | ✅ 活跃 |

### 核心规划
| 文档 | 说明 | 状态 |
|------|------|------|
| [DEVELOPMENT_INDEX.md](./DEVELOPMENT_INDEX.md) | 开发索引（已发布） | ✅ 活跃 |
| [REFACTOR_TASKS.md](./REFACTOR_TASKS.md) | 重构任务清单 | ✅ 活跃 |
| [P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md](./P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md) | P29 session boundary audit | ✅ active |
| [P29_SESSION_HARD_REFACTOR_PLAN.md](./P29_SESSION_HARD_REFACTOR_PLAN.md) | P29 session hard-refactor plan | ✅ active |
| [P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md](./P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md) | Surface/session architecture correction | active |
| [P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md](./P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md) | Surface/session refactor task plan | active |
| [TRANSFORMATION_PLAN.md](./TRANSFORMATION_PLAN.md) | 深度改造方案 v2 | ✅ 活跃 |
| [P18_HARD_REFACTOR_EXECUTION_PLAN.md](./P18_HARD_REFACTOR_EXECUTION_PLAN.md) | P18 硬重构执行计划 | ✅ 活跃 |

### 终端当前主线
| 文档 | 说明 | 状态 |
|------|------|------|
| [P23_TERMINAL_REAL_USE_READINESS.md](./P23_TERMINAL_REAL_USE_READINESS.md) | 终端真实使用门禁、清单与走查入口 | ✅ 活跃 |

### API 与契约
| 文档 | 说明 | 状态 |
|------|------|------|
| [API_V1_CONTRACT_SKELETON.md](./API_V1_CONTRACT_SKELETON.md) | API v1 契约骨架 | ✅ 活跃 |
| [RUNTIME_FLOW.md](./RUNTIME_FLOW.md) | 运行时流程说明 | ✅ 活跃 |

### 参考文档
| 文档 | 说明 | 状态 |
|------|------|------|
| [OSS_REFERENCE_INDEX.md](./OSS_REFERENCE_INDEX.md) | OSS 参考索引 | ✅ 活跃 |
| [MINIAGENT_DEV_HABIT_LEDGER.md](./MINIAGENT_DEV_HABIT_LEDGER.md) | 开发习惯与错误账本 | ✅ 活跃 |

### 开发日志
| 文档 | 说明 | 状态 |
|------|------|------|
| [devlog_2026-04-07.md](./devlog_2026-04-07.md) | 最新开发日志 | ✅ 活跃 |
| [devlog_2026-04-05.md](./devlog_2026-04-05.md) | 上一轮开发日志 | ✅ 活跃 |
| [archive/](./archive/) | 历史开发日志 | 📦 归档 |

---

## 📁 文档分类

### 1. 用户文档
面向使用 Mini-Agent 的用户：

```
├── README.md                    # 项目介绍
├── ARCHITECTURE.md              # 架构说明
├── docs/
│   ├── DEVELOPMENT_GUIDE_CN.md  # 开发指南
│   └── PRODUCTION_GUIDE_CN.md   # 生产部署指南
```

### 2. 开发文档
面向参与 Mini-Agent 开发的贡献者：

```
├── docs/
│   ├── DEVELOPMENT_INDEX.md              # 开发索引
│   ├── REFACTOR_TASKS.md                 # 重构任务
│   ├── P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md
│   ├── P29_SESSION_HARD_REFACTOR_PLAN.md
│   ├── P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md
│   ├── P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md
│   ├── TRANSFORMATION_PLAN.md            # 改造方案
│   ├── P18_HARD_REFACTOR_EXECUTION_PLAN.md
│   ├── API_V1_CONTRACT_SKELETON.md       # API 契约
│   ├── RUNTIME_FLOW.md                   # 运行时流程
│   ├── OSS_REFERENCE_INDEX.md            # OSS 参考
│   ├── MINIAGENT_DEV_HABIT_LEDGER.md     # 开发习惯
│   ├── devlog_2026-04-07.md              # 最新日志
│   └── devlog_2026-04-05.md              # 上一轮日志
```

### 3. 历史文档
已完成阶段的历史记录：

```
├── docs/
│   └── archive/
│       ├── DEVLOG_MVP1-6.md              # MVP 阶段日志
│       ├── DEVLOG_ITERATIONS*.md         # 迭代日志
│       ├── AGILE_DEVELOPMENT_PLAN.md     # 敏捷开发方案（已完成）
│       └── ...                           # 其他历史文档
```

---

## 🏷️ 文档状态标识

| 标识 | 含义 |
|------|------|
| ✅ 活跃 | 当前正在使用和维护的文档 |
| 🔄 更新中 | 正在更新的文档 |
| 📦 归档 | 历史文档，仅供参考 |
| ⚠️ 过时 | 内容已过时，待更新或删除 |
| 🚧 草稿 | 正在编写中的草稿文档 |

---

## 📖 阅读建议

### 新用户
1. 阅读 [README.md](../README.md) 了解项目
2. 阅读 [ARCHITECTURE.md](../ARCHITECTURE.md) 理解架构
3. 按照 [DEVELOPMENT_GUIDE_CN.md](./DEVELOPMENT_GUIDE_CN.md) 开始开发

### 贡献者
1. 阅读 [DEVELOPMENT_INDEX.md](./DEVELOPMENT_INDEX.md) 了解当前状态
2. 查看 [REFACTOR_TASKS.md](./REFACTOR_TASKS.md) 了解任务
3. 参考 [MINIAGENT_DEV_HABIT_LEDGER.md](./MINIAGENT_DEV_HABIT_LEDGER.md) 避免常见错误

### 运维人员
1. 阅读 [PRODUCTION_GUIDE_CN.md](./PRODUCTION_GUIDE_CN.md)
2. 参考 [RUNTIME_FLOW.md](./RUNTIME_FLOW.md) 了解运行时流程
3. 查看 [API_V1_CONTRACT_SKELETON.md](./API_V1_CONTRACT_SKELETON.md) 了解 API

---

## 🔗 相关链接

- **MiniMax API**: https://platform.minimax.io/docs
- **MiniMax-M2**: https://github.com/MiniMax-AI/MiniMax-M2
- **Anthropic API**: https://docs.anthropic.com/claude/reference
- **Claude Skills**: https://github.com/anthropics/skills
- **MCP Servers**: https://github.com/modelcontextprotocol/servers

---

## 📝 文档维护

### 更新规则
1. 每次重大变更后更新相关文档
2. 在文档顶部添加状态标识和更新日期
3. 将完成的阶段性文档移至 `archive/` 目录
4. 保持本索引文档与实际文档同步

### 命名规范
- 用户文档：`README.md`, `ARCHITECTURE.md` (根目录)
- 开发文档：`DEVELOPMENT_*.md`, `PRODUCTION_*.md`
- 规划文档：`*_PLAN.md`, `*_INDEX.md`
- 日志文档：`devlog_YYYY-MM-DD.md`, `DEVLOG_*.md`
- 归档文档：移至 `archive/` 目录

---

**维护者**: Mini-Agent Core Team
**反馈**: 如发现文档问题，请提交 Issue

## 2026-04-07 Normalization Addendum

- P18 closeout baseline evidence: [P18_CLOSEOUT_BASELINE_2026-04-07.md](./P18_CLOSEOUT_BASELINE_2026-04-07.md)
- P19 rollout prep contract: [P19_AGENT_TEAM_ROLLOUT_CONTRACT.md](./P19_AGENT_TEAM_ROLLOUT_CONTRACT.md)
- Historical-only scope: `docs/archive/*` is for traceability and must not be used as active execution scope.

## 2026-04-07 P19 Ops Addendum

- Team-mode operator runbook: [P19_TEAM_MODE_OPERATOR_RUNBOOK.md](./P19_TEAM_MODE_OPERATOR_RUNBOOK.md)
- Release promotion checklist runner: `scripts/release_promotion_checklist.py`
- Deterministic artifact guard: `scripts/check_deterministic_gate_artifact.py`
- P19 rollout announcement: [P19_TEAM_MODE_ROLLOUT_ANNOUNCEMENT.md](./P19_TEAM_MODE_ROLLOUT_ANNOUNCEMENT.md)
- P19 support FAQ: [P19_TEAM_MODE_SUPPORT_FAQ.md](./P19_TEAM_MODE_SUPPORT_FAQ.md)
- P19 team-mode alert policy: [P19_TEAM_MODE_ALERT_POLICY.md](./P19_TEAM_MODE_ALERT_POLICY.md)
- P19 Stage-C adoption tracking: [P19_STAGEC_ADOPTION_TRACKING.md](./P19_STAGEC_ADOPTION_TRACKING.md)
- P19 canary cadence: [P19_TEAM_MODE_CANARY_CADENCE.md](./P19_TEAM_MODE_CANARY_CADENCE.md)
- P19 weekly readiness template: [P19_WEEKLY_RELEASE_READINESS_TEMPLATE.md](./P19_WEEKLY_RELEASE_READINESS_TEMPLATE.md)
- GitHub upload scope: [GITHUB_UPLOAD_SCOPE_2026-04-07.md](./GITHUB_UPLOAD_SCOPE_2026-04-07.md)
- Cross-device handoff: [CROSS_DEVICE_HANDOFF_2026-04-07.md](./CROSS_DEVICE_HANDOFF_2026-04-07.md)

## 2026-04-07 Phase Update

- Current phase: `P20` detailed development phase (active).
- Focus: feature refinement, end-to-end stabilization, and full-regression readiness.

## 2026-04-07 P23 Addendum

- Agent-core detailed plan: [P23_AGENT_CORE_DETAILED_PLAN.md](./P23_AGENT_CORE_DETAILED_PLAN.md)
- Agent-core task plan: [P23_AGENT_CORE_TASK_PLAN.md](./P23_AGENT_CORE_TASK_PLAN.md)

## 2026-04-08 Terminal Readiness Addendum

- Terminal real-use readiness: [P23_TERMINAL_REAL_USE_READINESS.md](./P23_TERMINAL_REAL_USE_READINESS.md)
- One-command gate script: `scripts/terminal_readiness_gate.py`
- QQ/TUI shared-session manual runbook: [P23_QQ_TUI_SHARED_SESSION_RUNBOOK.md](./P23_QQ_TUI_SHARED_SESSION_RUNBOOK.md)
