# Mini-Agent 开发任务表

> **最后更新**: 2026-05-27
> **当前阶段**: v11 架构基线完成 / 设计文档补全 / 待进入对齐收紧阶段
> **架构版本**: v11.1（已稳定），v11.2-v11.5（已完成），v11.6-v11.20（已实现，设计文档已补全）
> **暂停范围**: 无。搁置期（2026-04-19 ~ 2026-05-27）后恢复开发，现处于接手准备阶段。

> **在线文档**: 最新完整架构文档见 `docs/project-documentation/`

---

## 📋 当前状态

- **测试状态**: 1726 passed, 17 skipped, 3 failed（3个失败为桌面UI中文本地化导致测试断言未同步）
- **架构状态**: v11 分层架构（Schema → Config → Interfaces → Model Service → Agent Core → Application → User Interface）
- **运行时**: 单一主代理运行时 / 多 Session 支持
- **终端状态**: TUI/CLI/Headless/Desktop 四入口主线已打通
- **API 版本**: v1 (`/api/v1/*`)
- **源代码**: ~350+ .py 文件，24 个顶层包
- **关键模块全覆盖**: agent_core / application / runtime / session / workspace_runtime / model_manager / memory / tools / skills / tui / desktop / transport / llm / interfaces / schema / security / rag / ops

---

## 🎯 开发任务

### 已完成阶段（历史记录，已完成 ✅）

#### P18 硬重构（已完成 ✅）
单主机架构，无兼容层，API v1，单一主代理运行时。详见原始 TASKS.md 记录。

#### P19 轻量 RAG 系统（已完成 ✅）
BM25 + 向量检索 + RRF 融合，Hybrid Store 本地持久化，Docling 文档解析。

#### P20 预留（已完成 ✅）
前端知识库面板，OpenWebUI 定位收敛。

#### P21 终端交互重构（已完成 ✅）
独立 TUI 子系统，命令面板，模型注册服务接入，多 Surface 会话接管，Session 真源统一。

#### P22-P42 Desktop 产品化（已完成 ✅）
PySide6 桌面应用，多工作区（对话/模型/服务商/设置/会话/记忆），Provider 预设与验证流程，模型角色/功能绑定。

---

### v11 架构重构（已完成 ✅）

#### v11.1 架构硬切割（已完成 ✅）
- [x] 核心实体模型正式化（AgentProfile / AgentInstance / Workspace / Session / Run / CapabilitySnapshot）
- [x] 四大真源域分离（Agent Truth / Workspace Truth / Session Truth / Surface Truth）
- [x] runtime 模块硬切割（handlers / orchestration / live_control / read_models 四层）
- [x] application 包根标记化，去除便利导出
- [x] commands router 硬切割（parser / metadata / completions / execution 拆分）
- [x] package facades 硬切割，legacy novel/plugin 表面切割
- [x] workspace_runtime 边界硬切割（DirectWorkspaceExecutor, MutationLedger, SnapshotStore）
- [x] 设计文档补全（`docs/v11.1/` 4份核心设计文档）

#### v11.2-v11.5 模型核心、用户服务、上下文组装器（已完成 ✅）
- [x] Agent Kernel Contract 实现（AgentProfile / AgentInstance / Run / Checkpoint / ExecutionJournal）
- [x] Model Service 模型池与服务分离（ModelPool + AgentModelService）
- [x] User Services 层建立（Agent / Workspace / Model / Command 四个 UserService）
- [x] Context Assembler 上下文组装器完善
- [x] TUI port adapters 增强（完整 run control integration）
- [x] User service integration for TUI
- [x] Stage 2 control truth migration（cancel_event → run-owned control bridge）
- [x] `_safe_text` 提取到 shared `utils.text` 模块

#### v11.6-v11.20 设计文档与模块对齐（已完成 ✅）
对应模块均已实现，设计文档于 2026-05-27 补齐提交：

| 阶段 | 模块 | 设计文档 | 代码实现 |
|------|------|:--:|:--:|
| v11.6 | Model Service | `docs/plans/v11.6_model_service/` | `model_manager/` 20文件 ✅ |
| v11.7 | Agent Core | `docs/plans/v11.7_agent_core/` | `agent_core/` ~70文件 ✅ |
| v11.8 | User Interface | `docs/plans/v11.8_user_interface/` | `tui/` 19 + `desktop/` 6 + `transport/` 21 ✅ |
| v11.9 | Application | `docs/plans/v11.9_application/` | `application/` ~35文件 ✅ |
| v11.10 | Runtime | `docs/plans/v11.10_runtime/` | `runtime/` ~45文件 ✅ |
| v11.11 | Session | `docs/plans/v11.11_session/` | `session/` 7文件 ✅ |
| v11.12 | Workspace | `docs/plans/v11.12_workspace/` | `workspace_runtime/` 11 + `workspace/` 2 ✅ |
| v11.13 | Tools | `docs/plans/v11.13_tools/` | `tools/` 24文件 ✅ |
| v11.14 | Security | `docs/plans/v11.14_security/` | `security/` 5 + `agent_core/security/` ✅ |
| v11.15 | Memory | `docs/plans/v11.15_memory/` | `memory/` 25文件 ✅ |
| v11.16 | LLM | `docs/plans/v11.16_llm/` | `llm/` 6文件 ✅ |
| v11.17 | Skills | `docs/plans/v11.17_skills/` | `agent_core/skills/` + `skills/` ✅ |
| v11.18 | Config | `docs/plans/v11.18_config/` | `config/` + `config_bootstrap.py` ✅ |
| v11.19 | Interfaces | `docs/plans/v11.19_interfaces/` | `interfaces/` 8文件 ✅ |
| v11.20 | Schema | `docs/plans/v11.20_schema/` | `schema/` 2文件 ✅ |

---

## 📝 当前待解决事项

### 🔴 测试修复（高优先级）
- [ ] **3个失败测试**：`tests/test_desktop_window_helpers.py`
  - `test_render_conversation_html_separates_roles_and_escapes_content`
  - `test_render_activity_html_renders_cards_with_detail_and_preview`
  - `test_render_activity_html_supports_thinking_cards`
  - 原因：桌面 UI 中文本地化后（`desktop/window.py`），HTML 渲染标签从英文变为中文，但测试断言仍是英文字符串。需同步更新测试期望值。
  - 附加问题：部分中文标签存在编码异常（显示为乱码），需检查 `agent_core/presentation.py` 中的编码处理。

### 🟡 设计文档对齐（中优先级）
- [ ] v11.1 设计文档（`docs/v11.1/*.txt`）中提到的 v11.2 内核契约对象设计是否已完全落地，需要逐项核对
- [ ] `docs/plans/v11.13_tools/` ~ `docs/plans/v11.20_schema/` 的 README 仅为占位，需补充详细设计文档
- [ ] TASKS.md（本文档）与 `docs/project-documentation/08_变更日志.md` 中的版本信息需保持同步

### 🟢 下一步开发方向（待确认）
- 根据 `docs/project-documentation/08_变更日志.md` 路线图：
  - v11.2 模型服务边界优化（原计划 2026-05）
  - v11.3 Provider 配置改进（原计划 2026-05）
  - v11.4 模型别名系统（原计划 2026-06）
- 根据 v11.1 设计文档指向：v11.2 Agent Kernel Contract 对象设计
- 根据 `docs/plans/` 设计文档：v11.13-v11.20 模块文档补全 + 代码对齐收紧

---

## 🔧 开发规范

（同 HABITS.md，此处保留关键条目）

1. **单一真实来源**: 所有变更必须映射到活跃阶段文档
2. **无兼容层**: 任何回退/遗留适配器都被阻止
3. **契约优先**: 路由器变更必须先更新 DTO/契约
4. **小原子切片**: 每个变更必须包含范围边界和回滚说明
5. **即时验证**: 语法/构建/冒烟检查在移交前必须执行

### 测试命令
```powershell
# 运行全部测试
uv run pytest -q

# 运行指定模块测试
uv run pytest tests/test_desktop_window_helpers.py -v

# 快速语法检查
uv run ruff check src/
```

---

## 📚 相关文档

- **最新架构文档**: `docs/project-documentation/`
- **v11.1 设计文档**: `docs/v11.1/`
- **v11 设计规划**: `docs/plans/`
- **变更日志**: `docs/project-documentation/08_变更日志.md`
- **开发习惯**: `HABITS.md`
- **项目记忆**: `MEMORY.md`
- **进度记录**: `progress.md`
- **任务计划**: `task_plan.md`

---

## 📊 进度统计

- **已完成阶段**: P0-P42, v11.1-v11.20（代码实现）
- **测试通过率**: 1726/1746 (98.8%)，3个失败待修复
- **源代码规模**: ~350+ .py 文件，24 个顶层包
- **架构版本**: v11.1 稳定

---

**维护者**: Mini-Agent Core Team
**反馈**: 如发现问题，请提交 Issue
