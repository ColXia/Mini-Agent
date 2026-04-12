# Mini-Agent 文档索引

> 最后更新：2026-04-12
> 当前阶段：P30 surface/session correction + terminal-first delivery
> 文档版本：v2.2

---

## 快速入口

### 新用户
- [README.md](../README.md)
- [README_CN.md](../README_CN.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [DEVELOPMENT_GUIDE.md](./DEVELOPMENT_GUIDE.md)
- [DEVELOPMENT_GUIDE_CN.md](./DEVELOPMENT_GUIDE_CN.md)

### 活跃开发文档
- [DEVELOPMENT_INDEX.md](./DEVELOPMENT_INDEX.md)
- [REFACTOR_TASKS.md](./REFACTOR_TASKS.md)
- [P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md](./P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md)
- [P29_SESSION_HARD_REFACTOR_PLAN.md](./P29_SESSION_HARD_REFACTOR_PLAN.md)
- [P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md](./P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md)
- [P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md](./P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md)
- [P23_TERMINAL_REAL_USE_READINESS.md](./P23_TERMINAL_REAL_USE_READINESS.md)
- [P24_REAL_USE_COMMAND_ACCEPTANCE_CHECKLIST.md](./P24_REAL_USE_COMMAND_ACCEPTANCE_CHECKLIST.md)
- [P25_MEMORY_CORE_TASK_PLAN.md](./P25_MEMORY_CORE_TASK_PLAN.md)
- [P26_MEMORY_RAG_WORKSPACE_ARCHITECTURE_REPORT.md](./P26_MEMORY_RAG_WORKSPACE_ARCHITECTURE_REPORT.md)
- [P28_BUILTIN_SKILL_REALIGNMENT_PLAN.md](./P28_BUILTIN_SKILL_REALIGNMENT_PLAN.md)
- [OSS_REFERENCE_INDEX.md](./OSS_REFERENCE_INDEX.md)

### 用户与运维文档
- [PRODUCTION_GUIDE.md](./PRODUCTION_GUIDE.md)
- [PRODUCTION_GUIDE_CN.md](./PRODUCTION_GUIDE_CN.md)
- [API_V1_CONTRACT_SKELETON.md](./API_V1_CONTRACT_SKELETON.md)
- [RUNTIME_FLOW.md](./RUNTIME_FLOW.md)

### 历史归档
- [archive/README.md](./archive/README.md)
- 历史 devlog、handoff、upload scope、旧 README 副本均已归档到 `docs/archive/`
- 已完成的 `P18 / P19` 阶段计划、baseline、rollout runbook 也已下沉到 `docs/archive/`
- 一次性分析报告和环境特定索引也已按需下沉到 `docs/archive/`

---

## 文档分层

### 活跃文档

保留在 `docs/` 根目录的文档应该满足至少一项：

- 当前阶段仍在直接使用
- 当前运行方式仍依赖它的说明
- 当前架构或任务计划仍以它为依据

### 历史文档

以下类型优先归档到 `docs/archive/`：

- 完结阶段的开发日志
- 已完成阶段的执行计划、baseline、rollout/runbook 套件
- 一次性的 handoff / upload / snapshot 说明
- 已被新文档替代的旧 README / 旧指南
- 已完成整理任务的过程性报告

---

## 当前文档事实

- 当前主交互面是 `TUI / CLI / headless`
- WebUI 当前暂停，不是主开发目标
- skills 为仓库内置，不再走 `git submodule` 初始化
- 参考项目与运行依赖必须分开描述

---

## 相关链接

- [Bundled skills catalog](../src/mini_agent/skills/README.md)
- [MiniMax API](https://platform.minimax.io/docs)
- [MCP Servers](https://github.com/modelcontextprotocol/servers)

---

## 维护规则

- 改动 README / 开发指南时，同步检查 `DEVELOPMENT_INDEX.md` 与本索引
- 新增一次性文档时，优先判断是否应直接进入 `docs/archive/`
- 不要把历史文档继续挂在“活跃文档”入口
