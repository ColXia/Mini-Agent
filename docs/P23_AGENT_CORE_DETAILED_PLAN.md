# P23 Agent-Core 细化开发总方案（终端优先）

> 状态: Active
> 开始日期: 2026-04-07
> 目标: 以“核心能力可用、性能稳定、架构清晰、未来可升级”为准则，完成 Mini-Agent 轻量内核强化。
> 约束: 不做兼容壳，不重复造轮子，优先接线现有模块。

## 1. 背景与问题定义

当前 Mini-Agent 已具备可用主链（CLI/TUI/Headless + code-agent loop + model registry + gateway），但仍存在一个核心短板：

- `agent_core` 多个能力模块（session/delegation/routing/cron/browser）已经实现，但主链接线不足，运行时“能力存在但未被系统性消费”。

本阶段不追求和 codex/gemini/opencode/extracted-src 同级功能规模，目标是完成“轻量但强”的内核收敛。

## 2. 开发准则（本阶段强约束）

1. 核心能力优先，不做界面装饰性开发。
2. 无兼容壳，直接硬接线到主运行时。
3. 单一真实来源：同一能力只保留一条主链实现。
4. 性能与可靠性并重：每个里程碑都要有回归测试。
5. 可演进：新增能力必须可继续扩展为多 agent/多运行时模式。

## 3. 目标架构（P23 结束时）

1. 运行时编排主干统一
- 主链统一通过 runtime manager + agent_core policy 执行。

2. 会话生命周期可控
- 会话 reset 策略（none/daily/idle/both）进入主链。
- reset 行为可观测、可配置、可测试。

3. 任务/回合执行可治理
- submission loop/scheduler/coordinator 的状态在 CLI/TUI/Gateway 行为一致。

4. 多能力接线可扩展
- delegation/routing 等 agent_core 能力以“增量接线”方式进入主链，而不是平行新实现。

## 4. 任务分解（P23.x）

## P23.1 会话生命周期硬接线（已完成）

目标:
- 将 `agent_core.session.lifecycle` 直接接入 `MainAgentRuntimeManager`。

交付:
- runtime manager 会话复用时执行 lifecycle 检查与自动 reset。
- runtime diagnostics 暴露 reset 策略与自动 reset 计数。
- gateway runtime policy 支持环境变量配置 reset 策略。

验收:
- 相关用例与矩阵测试通过。

## P23.2 CLI/TUI 会话策略对齐（已完成）

目标:
- CLI/TUI 与 Gateway 使用一致的 session reset 语义。

交付:
- 终端侧会话在复用/切换时应用统一生命周期规则。
- 保持交互体验可预期（reset 时给出系统提示，不隐式吞消息）。

## P23.3 Delegation 主链接线（已完成）

目标:
- 以最小可用方式把 `agent_core.delegation` 接入主流程。

交付:
- 至少完成单一受控委派入口，明确 owner/write-scope 合约。
- 提供失败回落与可观测事件。

## P23.4 Routing 主链接线（已完成）

目标:
- 让 `agent_core.routing` 从“库能力”变为“运行时入口能力”。

交付:
- 在主链引入 route 解析与命中策略。
- 提供基本命中统计和 fallback 行为。

## P23.5 稳定性与性能收敛（已完成）

目标:
- 保证核心路径长会话下稳定、无明显劣化。

交付:
- 补充关键回归测试（会话重置、并发、取消、中断恢复）。
- 补充最小性能基线（p95 延迟、消息规模阈值下无异常）。

## P23.6 QQ/TUI 共用会话与接管链路（已完成）

目标:
- 让 QQ Bot 与 TUI 成为同一条主会话的两个 surface。
- 让 TUI 逐步转为“操作台/可视化后台”，而不是只看本地私有会话。
- 为后续“离开电脑后用 QQ 继续、回到电脑后在 TUI 接手”提供稳定主链。

设计原则:
- 只复用现有 `channel -> gateway -> main_agent_runtime_manager` 主链。
- 不新增第二套远程会话存储；共享会话信息直接挂在 runtime session 上。
- 先补后端契约，再接 QQ `/continue`，最后接 TUI 远程会话消费。

共享会话模型:
- `origin_surface`: 首次创建该会话的来源面，首期取值为 `tui|qq|api`
- `active_surface`: 当前接管面，首期由最近一次显式接管或最新输入面决定
- `reply_enabled`: 当前是否允许“远端自动回包”；QQ 输入时为 `true`，TUI 接管后切为 `false`
- `channel_type` / `conversation_id` / `sender_id`: 远端会话绑定信息，供 QQ 回溯与 `/continue` 使用
- `transcript`: 运行时维护的消息快照，不依赖 TUI 本地状态；首期至少记录 `role/content/surface/created_at`

后端接口补充:
- `GET /api/v1/agent/sessions`
  返回会话摘要，增加 `origin_surface`、`active_surface`、`reply_enabled`、远端绑定字段
- `GET /api/v1/agent/sessions/{session_id}`
  返回单会话详情与最近消息快照
- `GET /api/v1/agent/sessions/{session_id}/messages?limit=10`
  返回最近消息列表，供 QQ `/continue` 使用
- `POST /api/v1/agent/sessions/{session_id}/takeover`
  将活动面切换到指定 surface；首期至少支持 `tui`

QQ 侧语义:
- 普通消息继续走 `POST /api/v1/channel/message`
- channel ingress 不再只传文本，要把 `channel_type/conversation_id/sender_id/surface=qq` 带进主会话
- `/continue` 不新建会话，只读取当前会话最近 10 条消息并发回 QQ
- TUI 接管后，不主动把 TUI 新回复回推 QQ；QQ 端如需续接，通过下一条 QQ 消息或 `/continue` 拉取上下文

TUI 侧语义:
- TUI 作为 operator console，后续通过共享会话接口展示远程来源会话
- 选中远程来源会话并“接管”后，写入 `active_surface=tui`
- TUI 发出的后续输入直接写入同一 `session_id`
- 首期先依赖摘要/详情/最近消息接口，后续再做实时刷新或事件镜像

实施顺序:
1. 扩 runtime session 元数据与 transcript
2. 扩 gateway/use case/session API
3. 接 QQ `/continue`
4. 接 TUI 远程会话展示与接管

验收:
- QQ 发起任务后，gateway 会话列表中可识别其为 `qq` 来源
- 同一会话可从 TUI 接管，接管后会话摘要的 `active_surface` 正确变化
- `/continue` 返回最近 10 条消息，不丢 `assistant` 回复
- 主链回归测试通过，且不引入第二套 session runtime

## 5. 配置契约（P23）

新增/使用环境变量:

- `MINI_AGENT_SESSION_RESET_MODE`
  可选: `none|daily|idle|both`
  默认: `none`

- `MINI_AGENT_SESSION_IDLE_SECONDS`
  正整数，`idle`/`both` 模式生效
  默认: `1800`

## 6. 风险与防线

1. 风险: reset 行为造成上下文意外丢失。
防线: 保留 system 首消息；诊断接口暴露 reset 计数；测试覆盖 idle 触发场景。

2. 风险: 策略增加后出现环境配置歧义。
防线: 非法值回落默认值，并在 diagnostics 反映实际生效策略。

3. 风险: 新增路径导致回归。
防线: 强制跑主链相关回归集合。

## 7. 本次已落地变更（P23.1 + P23.2 + P23.3 + P23.4 + P23.5）

代码:
- `src/mini_agent/runtime/main_agent_runtime_manager.py`
- `src/apps/agent_studio_gateway/main.py`
- `src/mini_agent/interfaces/system.py`
- `src/mini_agent/runtime/session_lifecycle.py`
- `src/mini_agent/runtime/__init__.py`
- `src/mini_agent/application/main_agent_gateway_use_cases.py`
- `src/mini_agent/cli_interactive.py`
- `src/mini_agent/tui/app.py`
- `src/mini_agent/interfaces/agent.py`
- `src/mini_agent/interfaces/system.py`
- `src/mini_agent/interfaces/__init__.py`
- `src/apps/agent_studio_gateway/main.py`
- `tests/test_main_agent_gateway_use_cases.py`
- `tests/test_p19_runtime_matrix.py`
- `tests/test_cli_submission_loop.py`
- `tests/test_tui_app.py`
- `tests/test_session_lifecycle_runtime.py`
- `tests/test_agent_studio_gateway_ops_router.py`
- `scripts/p23_runtime_baseline.py`
- `workspace/perf/p23_runtime_baseline_20260408T035025Z.md`

测试:
- `pytest tests/test_main_agent_gateway_use_cases.py tests/test_p19_runtime_matrix.py -q`
- `pytest tests/test_cli_submission_loop.py tests/test_tui_app.py tests/test_session_lifecycle_runtime.py -q`
- `pytest tests/test_main_agent_gateway_use_cases.py tests/test_p19_runtime_matrix.py tests/test_agent_studio_gateway_ops_router.py -q`
- `pytest tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_api_v1.py tests/test_p19_runtime_matrix.py -q`
- `pytest tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_ops_router.py tests/test_agent_studio_gateway_api_v1.py -q`
- `python scripts/p23_runtime_baseline.py --runs 60 --workspace .`
- `pytest tests -k "agent_core or code_agent or cli_unified_mode or tui_app or main_agent_gateway_use_cases or p19_runtime_matrix" -q`
