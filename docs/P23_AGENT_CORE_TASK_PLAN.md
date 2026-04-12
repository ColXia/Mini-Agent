# P23 Agent-Core 开发任务计划（执行清单）

> 状态: Active  
> 维护方式: 每完成一项即更新勾选和验证证据  
> 原则: 先主链、后增强；先可用、后优化；不保留兼容壳

## P23.1 会话生命周期接线（已完成）

- [x] 在 `MainAgentRuntimeManager` 接入 `SessionLifecycleManager`
- [x] 支持会话复用时自动 reset（基于 lifecycle policy）
- [x] diagnostics 增加 lifecycle 观测字段
- [x] gateway policy 解析支持 reset 环境变量
- [x] 补单元测试与矩阵测试

验证命令:
- [x] `pytest tests/test_main_agent_gateway_use_cases.py tests/test_p19_runtime_matrix.py -q`
- [x] `pytest tests -k "agent_core or code_agent or cli_unified_mode or tui_app or main_agent_gateway_use_cases or p19_runtime_matrix" -q`

## P23.2 终端会话策略对齐（已完成）

- [x] 将 CLI/TUI 会话复用行为对齐到同一 lifecycle policy
- [x] reset 触发时增加明确系统提示
- [x] 补 TUI/CLI 回归测试与 shared runtime 单测

验收标准:
- 同一策略下，Gateway 与 CLI/TUI 行为一致
- 不出现“静默 reset”导致的交互歧义

验证命令:
- [x] `pytest tests/test_cli_submission_loop.py tests/test_tui_app.py tests/test_session_lifecycle_runtime.py -q`
- [x] `pytest tests/test_main_agent_gateway_use_cases.py tests/test_p19_runtime_matrix.py tests/test_agent_studio_gateway_studio_router.py -q`

## P23.3 Delegation 主链接线（已完成）

- [x] 在主流程引入最小 delegation 执行入口
- [x] 明确委派任务 owner 与写入边界
- [x] 失败回落到主 agent 执行路径
- [x] 输出委派事件（started/completed/failed）

验收标准:
- 至少 1 条端到端 delegation 用例可跑通
- 失败后可稳定回落，无死锁/悬挂

验证命令:
- [x] `pytest tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_api_v1.py tests/test_p19_runtime_matrix.py -q`
- [x] `pytest tests/test_cli_submission_loop.py tests/test_tui_app.py tests/test_agent_studio_gateway_studio_router.py -q`

## P23.4 Routing 主链接线（已完成）

- [x] 将 `agent_core.routing` 接入主请求分发
- [x] 加入 route fallback 与基础命中统计
- [x] 补 routing 回归测试

验收标准:
- 路由命中行为可预测
- fallback 生效且可观测

验证命令:
- [x] `pytest tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_studio_router.py tests/test_agent_studio_gateway_api_v1.py -q`
- [x] `pytest tests -k "agent_core or code_agent or cli_unified_mode or tui_app or main_agent_gateway_use_cases or p19_runtime_matrix or cli_submission_loop or agent_studio_gateway_api_v1 or agent_studio_gateway_studio_router" -q`

## P23.5 稳定性和性能收敛（已完成）

- [x] 增加中长会话稳定性回归
- [x] 增加取消/中断/恢复回归
- [x] 记录关键路径性能基线（至少 p95）

验收标准:
- 核心回归集持续通过
- 无明显性能退化或稳定性回退

验证命令:
- [x] `pytest tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_studio_router.py tests/test_agent_studio_gateway_api_v1.py -q`
- [x] `python scripts/p23_runtime_baseline.py --runs 60 --workspace .`
- [x] `pytest tests -k "agent_core or code_agent or cli_unified_mode or tui_app or main_agent_gateway_use_cases or p19_runtime_matrix or cli_submission_loop or agent_studio_gateway_api_v1 or agent_studio_gateway_studio_router" -q`

## P23.6 QQ/TUI 共用会话与接管链路（已完成）

- [x] 为 `MainAgentRuntimeManager` 增加共享会话元数据，至少包含 `origin_surface`、`active_surface`、`channel_type`、`conversation_id`、`sender_id`、`reply_enabled`
- [x] 为主会话增加最近消息快照能力，支持 `QQ /continue` 和 TUI 后续接管展示
- [x] `channel/message` 进入主链时写入来源面元数据，不再丢失 QQ 会话绑定信息
- [x] 新增主会话详情 / 最近消息 / 接管接口，作为 TUI 远程接管的唯一后端入口
- [x] QQ Bot 增加 `/continue`，可拉取同一共享会话最近 10 条消息
- [x] TUI 后续改为消费共享会话接口，作为远程任务的可视化后台，而不是另造第二套远程会话系统

验收标准:
- QQ 发起的任务在主 runtime 内形成可识别的共享会话，列表中可看到来源与当前活动面
- TUI 接管后，会话活动面切换为 `tui`，后续 TUI 输入不再走 QQ 自动回包语义
- QQ 发送 `/continue` 时，能拿到同一会话最近 10 条有效上下文
- 所有新增能力都基于现有 gateway/runtime/channel 主链实现，不新增平行消息栈

验证命令:
- [x] `pytest tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py -q`
- [x] `pytest tests/test_agent_studio_gateway_integration_flows.py -q`

## 运行约束（全阶段）

- [ ] 任何新增能力必须直接接主链，不得新增平行实现
- [ ] 任一里程碑必须具备可执行验证命令
- [ ] 文档与代码同批更新，不允许“代码变了文档没跟上”

## P23.7 Turn-Context Integration Seam (completed)
- [x] Add one unified turn-context provider interface for ephemeral per-turn context injection
- [x] Ensure prepared context is removed after the turn so long-lived transcript history stays clean
- [x] Pass the same turn-context shape through local submission-loop and gateway direct-turn execution
- [x] Expose compact `prepared_context` summaries in `loop.turn.completed`
- [x] Land the first concrete provider using workspace memory/note retrieval

Verification:
- [x] `pytest tests/test_agent_turn_context.py tests/test_agent_execution_policy.py tests/test_code_agent_loop.py tests/test_cli_submission_loop.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_core_kernel.py -q`
- [x] `python -m compileall src/mini_agent/agent.py src/mini_agent/turn_context.py src/mini_agent/runtime/tooling.py src/mini_agent/agent_core/kernel.py src/mini_agent/code_agent/scheduler.py src/mini_agent/code_agent/agent_loop.py src/mini_agent/application/main_agent_gateway_use_cases.py`

## P23.8 Knowledge-Base Turn-Context Provider (completed)
- [x] Reuse the existing lightweight-RAG stack (`HybridSearchStore` + `rewrite_query`) through the turn-context seam
- [x] Add `KnowledgeBaseTurnContextProvider` that prepares ephemeral retrieval context per turn (historical step, removed later in P23.25)
- [x] Support metadata-driven `knowledge_base_id` selection and follow-up query rewrite using recent conversation lines
- [x] Support router-compatible store path fallback while remaining safe no-op when the KB store is absent
- [x] Wire the provider into runtime/kernel bootstrap alongside workspace memory context
- [x] Add focused tests for retrieval, rewrite behavior, metadata-selected KB, and store-path fallback

Verification:
- [x] `pytest tests/test_agent_turn_context.py -q`
- [x] `pytest tests/test_code_agent_loop.py tests/test_agent_execution_policy.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_core_kernel.py tests/test_cli_submission_loop.py -q`
- [x] `python -m compileall src/mini_agent/turn_context.py src/mini_agent/runtime/tooling.py src/mini_agent/agent_core/__init__.py tests/test_agent_turn_context.py`

## P23.9 Operator-Visible Prepared Context (completed)
- [x] Reuse the existing `prepared_context` payload from `loop.turn.completed` instead of introducing a second observability event
- [x] Add shared display helpers for compact prepared-context summary/detail rendering
- [x] Surface prepared context in CLI as a compact `[context]` block with item previews
- [x] Surface prepared context in TUI `Status` and as a collapsed internal `/context` transcript block
- [x] Keep prepared-context transcript entries out of `Threads` preview so operator visibility does not pollute session navigation
- [x] Persist the latest prepared-context summary in TUI session state
- [x] Add focused CLI/TUI tests for prepared-context surfacing

Verification:
- [x] `pytest tests/test_cli_submission_loop.py tests/test_tui_app.py tests/test_agent_turn_context.py tests/test_code_agent_loop.py -q`
- [x] `python -m compileall src/mini_agent/cli_interactive.py src/mini_agent/tui/app.py src/mini_agent/turn_context.py tests/test_cli_submission_loop.py tests/test_tui_app.py`

## P23.10 Additional Turn-Context Provider Types (completed)
- [x] Reuse the existing consolidated-memory retriever through the same turn-context seam
- [x] Add `ConsolidatedMemoryTurnContextProvider` for ranked long-lived memory hints
- [x] Add `SkillCatalogTurnContextProvider` for lightweight relevant-skill hints
- [x] Add `MCPToolCatalogTurnContextProvider` for active MCP capability hints from registered connections
- [x] Keep all new provider output on the same `prepared_context` operator surface used by CLI/TUI
- [x] Share builtin-skills path resolution between runtime tool bootstrap and turn-context bootstrap so skills discovery cannot drift

Verification:
- [x] `pytest tests/test_agent_turn_context.py -q`
- [x] `pytest tests/test_code_agent_loop.py tests/test_cli_submission_loop.py tests/test_tui_app.py tests/test_agent_core_kernel.py -q`
- [x] `pytest tests/test_agent_core_skills.py tests/test_mcp_policy.py -q`
- [x] `python -m compileall src/mini_agent/turn_context.py src/mini_agent/runtime/tooling.py src/mini_agent/agent_core/__init__.py tests/test_agent_turn_context.py`

## P23.11 Prepared-Context Quality Controls (completed)
- [x] Add one centralized curation pass before prepared context is injected into the turn
- [x] Deduplicate cross-provider items by normalized content and prefer higher-priority sources on collision
- [x] Enforce shared item and character budgets so multi-provider turns stay lightweight
- [x] Keep all curation reporting on the existing `prepared_context` summary payload instead of introducing a second observability path
- [x] Surface curation details in existing operator-facing prepared-context summary/detail rendering

Verification:
- [x] `pytest tests/test_agent_turn_context.py tests/test_cli_submission_loop.py tests/test_tui_app.py tests/test_code_agent_loop.py -q`
- [x] `pytest tests/test_agent_core_kernel.py tests/test_agent_execution_policy.py tests/test_agent_core_skills.py tests/test_mcp_policy.py -q`
- [x] `python -m compileall src/mini_agent/turn_context.py src/mini_agent/agent.py tests/test_agent_turn_context.py`

## P23.12 Provider Readiness And Operator Context Policy (completed)
- [x] Allow turn-context providers to expose readiness instead of only silent no-op behavior
- [x] Record provider statuses (`used/no_match/filtered/unavailable/failed`) on the existing `prepared_context` summary payload
- [x] Support metadata-driven `prepared_context_policy` include/exclude filtering and budget overrides
- [x] Expose lightweight `/context` controls in CLI and TUI
- [x] Persist per-session context policy in TUI and surface its summary in `Status`

Verification:
- [x] `pytest tests/test_agent_turn_context.py tests/test_cli_submission_loop.py tests/test_tui_app.py tests/test_code_agent_loop.py -q`
- [x] `pytest tests/test_agent_core_kernel.py tests/test_agent_execution_policy.py tests/test_agent_core_skills.py tests/test_mcp_policy.py -q`
- [x] `python -m compileall src/mini_agent/turn_context.py src/mini_agent/agent.py src/mini_agent/cli_interactive.py src/mini_agent/tui/app.py tests/test_agent_turn_context.py tests/test_cli_submission_loop.py tests/test_tui_app.py`

## P23.13 Provider Tuning And Runtime Context Diagnostics (completed)
- [x] Add provider-local `ranking_score` metadata and let prepared-context curation use both source weight and item relevance
- [x] Explain prepared-context selection decisions in operator-visible CLI/TUI detail views
- [x] Add `/context show brief|full` so operators can choose compact or fully explained detail
- [x] Accumulate cross-turn prepared-context diagnostics in the agent runtime instead of creating a parallel stats subsystem
- [x] Expose persisted `/context stats` in CLI and TUI on top of the existing `prepared_context` seam
- [x] Ensure lifecycle reset / clear semantics also clear prepared-context diagnostics

Verification:
- [x] `pytest tests/test_agent_turn_context.py tests/test_code_agent_loop.py tests/test_cli_submission_loop.py tests/test_tui_app.py -q`
- [x] `pytest tests/test_agent_core_kernel.py tests/test_agent_execution_policy.py tests/test_agent_core_skills.py tests/test_mcp_policy.py -q`
- [x] `pytest tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_api_v1.py -q`
- [x] `python -m compileall src/mini_agent/turn_context.py src/mini_agent/agent.py src/mini_agent/code_agent/agent_loop.py src/mini_agent/cli_interactive.py src/mini_agent/tui/app.py tests/test_agent_turn_context.py tests/test_code_agent_loop.py tests/test_cli_submission_loop.py tests/test_tui_app.py`

## P23.14 Readiness-Gate Context Diagnostics (completed)
- [x] Extend headless CLI JSON output so it emits `prepared_context` and `prepared_context_diagnostics`
- [x] Teach `scripts/terminal_readiness_gate.py` to capture and parse live headless JSON output
- [x] Add a dedicated `Live Headless Context` report section with contract status, diagnostics summary, last prepared-context summary, and source/provider coverage
- [x] Fail live readiness when headless smoke no longer emits `prepared_context_diagnostics`, avoiding false-green observability regressions
- [x] Add focused regression coverage for both headless JSON payloads and gate-report parsing/failure behavior

Verification:
- [x] `pytest tests/test_cli_unified_mode.py tests/test_cli_submission_loop.py tests/test_code_agent_loop.py tests/test_terminal_readiness_gate.py -q`
- [x] `python -m compileall src/mini_agent/cli.py scripts/terminal_readiness_gate.py tests/test_cli_submission_loop.py tests/test_terminal_readiness_gate.py`

## P23.15 Scripted TUI Real-Use Walkthroughs (completed)
- [x] Extend `scripts/tui_manual_checklist.py` so it covers `/context include|exclude|budget|show|stats|reset`
- [x] Extend `scripts/tui_interaction_walkthrough.py` so the same `/context ...` path is exercised through the live prompt-toolkit input flow
- [x] Update walkthrough fake agents to the current runtime `run_turn(..., turn_context=...)` contract to avoid drift from the real scheduler path
- [x] Run scripted TUI walkthroughs by default inside `scripts/terminal_readiness_gate.py`, while keeping explicit skip switches for fast local runs
- [x] Add focused regression coverage for walkthrough inclusion and gate default/skip behavior
- [x] Fold walkthrough/gate tests into the targeted readiness test bundle

Verification:
- [x] `pytest tests/test_tui_readiness_walkthroughs.py tests/test_terminal_readiness_gate.py -q`
- [x] `python scripts/tui_manual_checklist.py`
- [x] `python scripts/tui_interaction_walkthrough.py`
- [x] `python scripts/terminal_readiness_gate.py --run-live-headless --skip-full-tests --skip-baseline`
- [x] `python -m pytest tests/test_agent_core_kernel.py tests/test_code_agent_minimal_workflow.py tests/test_cli_unified_mode.py tests/test_cli_submission_loop.py tests/test_terminal_readiness_gate.py tests/test_tui_readiness_walkthroughs.py tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py -q`

## P23.16 Shared-Session Gateway Readiness Drill (completed)
- [x] Add `scripts/shared_session_gateway_walkthrough.py` to validate gateway-managed shared-session behavior without depending on a live QQ login
- [x] Cover qq-origin metadata, remote activity transcript visibility, TUI takeover, shared context controls, remote cancel, TUI import/export roundtrip, and restart persistence
- [x] Keep shared-session walkthrough fake agents aligned with the current `run_turn(..., turn_context=...)` runtime contract
- [x] Run the shared-session walkthrough by default inside `scripts/terminal_readiness_gate.py`, while keeping an explicit skip switch for fast local runs
- [x] Add focused regression coverage for the walkthrough itself and fold it into the targeted readiness test bundle

Verification:
- [x] `pytest tests/test_shared_session_gateway_walkthrough.py tests/test_terminal_readiness_gate.py -q`
- [x] `python scripts/shared_session_gateway_walkthrough.py`
- [x] `python -m pytest tests/test_agent_core_kernel.py tests/test_code_agent_minimal_workflow.py tests/test_cli_unified_mode.py tests/test_cli_submission_loop.py tests/test_shared_session_gateway_walkthrough.py tests/test_terminal_readiness_gate.py tests/test_tui_readiness_walkthroughs.py tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py -q`
- [x] `python scripts/terminal_readiness_gate.py --run-live-headless --skip-full-tests --skip-baseline`

## P23.17 Channel-Ingress Gateway Readiness Drill (completed)
- [x] Add `scripts/channel_ingress_gateway_walkthrough.py` to validate the real `ChannelIngressUseCases -> MainAgentGatewayUseCases -> MainAgentRuntimeManager` chain without depending on a live QQ login
- [x] Cover channel-created session reuse, metadata persistence, `/continue`-style recent transcript visibility, activity transcript retention, and TUI takeover on the same shared session
- [x] Reuse the existing shared-session/runtime contracts instead of adding a second synthetic channel-session subsystem
- [x] Run the channel-ingress walkthrough by default inside `scripts/terminal_readiness_gate.py`, while keeping an explicit skip switch for fast local runs
- [x] Add focused regression coverage for the walkthrough itself and fold it into the targeted readiness test bundle

Verification:
- [x] `pytest tests/test_channel_ingress_gateway_walkthrough.py tests/test_terminal_readiness_gate.py tests/test_shared_session_gateway_walkthrough.py tests/test_tui_readiness_walkthroughs.py -q`
- [x] `python scripts/channel_ingress_gateway_walkthrough.py`
- [x] `python scripts/terminal_readiness_gate.py --skip-full-tests --skip-baseline`

## P23.18 Remote Recovery Snapshot And Resume Context (completed)
- [x] Add one shared-session `recovery` snapshot to summary/detail contracts instead of inventing a second remote recovery API
- [x] Preserve interrupted-before-restart state as recovery context (`interrupted after restart: ...`) for persisted shared sessions
- [x] Include compact recovery hints such as `last_activity`, `last_user_message`, and `last_assistant_message`
- [x] Surface the new recovery snapshot in TUI remote session rendering and QQ `/status` + `/continue`
- [x] Extend the shared-session readiness walkthrough to cover interrupted-after-restart recovery semantics

Verification:
- [x] `pytest tests/test_tui_app.py tests/test_main_agent_gateway_use_cases.py tests/test_shared_session_gateway_walkthrough.py tests/test_interface_dto_contracts.py -q`
- [x] `python scripts/shared_session_gateway_walkthrough.py`
- [x] `python scripts/terminal_readiness_gate.py --skip-full-tests --skip-baseline`
- [x] `node --check src/apps/qqbot_channel/bot.mjs`

## P23.19 Remote Approval Control For Shared Sessions (completed)
- [x] Reuse `Agent.tool_approval_handler` in gateway-managed shared sessions instead of inventing a second remote approval subsystem
- [x] Persist live `pending_approvals` on shared-session summaries/details and preserve interrupted approvals in recovery snapshots after restart
- [x] Add one gateway approval endpoint: `POST /api/v1/agent/sessions/{session_id}/approval`
- [x] Support remote `/approve [token]` and `/deny [token]` from TUI shared sessions
- [x] Support remote `/approve [token]` and `/deny [token]` from QQ bot shared sessions
- [x] Ensure remote `/cancel` also resolves approval waiters so approval-time turns do not hang indefinitely

## P23.20 Shared-Session Remote Model Parity (completed)
- [x] Persist session-scoped `selected_model_*` and `pending_model_*` fields on shared-session summary/detail/snapshot contracts
- [x] Rebuild gateway-managed shared-session agents with exact provider/model pinning instead of mutating only global registry defaults
- [x] Apply queued shared-session model changes on the next turn before execution starts
- [x] Add one gateway model endpoint: `POST /api/v1/agent/sessions/{session_id}/model`
- [x] Make remote TUI `/model apply|use ...` operate on the bound shared session and show the real selected/queued model
- [x] Add QQ `/model show|list|use ...` commands on top of the same shared-session model path

Verification:
- [x] `uv run pytest tests/test_interface_dto_contracts.py tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_api_v1.py tests/test_tui_app.py tests/test_shared_session_gateway_walkthrough.py tests/test_tui_readiness_walkthroughs.py -q`
- [x] `node --check src/apps/qqbot_channel/bot.mjs`
- [x] `uv run python scripts/shared_session_gateway_walkthrough.py`
- [x] `uv run python scripts/terminal_readiness_gate.py --skip-full-tests --skip-baseline`
- [ ] Real manual smoke deferred: live `QQ -> gateway -> TUI` shared-session `/model show|list|use` parity check on a real bot session

Verification:
- [x] `pytest tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py -q`
- [x] `pytest tests/test_shared_session_gateway_walkthrough.py -q`
- [x] `python scripts/shared_session_gateway_walkthrough.py`
- [x] `python scripts/terminal_readiness_gate.py --skip-full-tests --skip-baseline`
- [x] `node --check src/apps/qqbot_channel/bot.mjs`

## P23.20 Post-Restart Shared-Session Continuation Semantics (completed)
- [x] Persist structured recovery context on shared-session runtime state instead of only exposing passive interrupted summaries
- [x] Preserve interrupted recovery state across restart and TUI takeover until the next real continuation turn consumes it
- [x] Inject one-shot recovery metadata into the next post-restart turn through `turn_context.metadata["recovery"]`
- [x] Add `RuntimeRecoveryTurnContextProvider` so the model can see restart/lost-approval hints without polluting persistent transcript history
- [x] Update TUI and QQ operator guidance so lost approvals after restart instruct the operator to continue with a new message
- [x] Extend the shared-session walkthrough so it validates both persisted lost approvals and recovery metadata injection on the next turn

Verification:
- [x] `pytest tests/test_agent_turn_context.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_shared_session_gateway_walkthrough.py -q`
- [x] `pytest tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py tests/test_interface_dto_contracts.py tests/test_agent_turn_context.py tests/test_shared_session_gateway_walkthrough.py -q`
- [x] `python scripts/shared_session_gateway_walkthrough.py`
- [x] `python scripts/terminal_readiness_gate.py --skip-full-tests --skip-baseline`
- [x] `node --check src/apps/qqbot_channel/bot.mjs`

## P23.21 Shared-Session Remote Context Parity (completed)
- [x] Persist `context_policy`, `last_prepared_context`, and `prepared_context_diagnostics` on shared runtime sessions
- [x] Carry the same prepared-context state through gateway detail/export/import so share, unshare, and restart keep operator context controls intact
- [x] Add one gateway endpoint for remote prepared-context policy updates: `POST /api/v1/agent/sessions/{session_id}/context`
- [x] Route remote TUI `/context show|stats|include|exclude|budget|reset` through the shared-session gateway path
- [x] Add QQ bot parity for `/context show|stats|include|exclude|budget|reset`
- [x] Ensure future shared-session turns apply the persisted context policy through `turn_context.metadata["prepared_context_policy"]`

Verification:
- [x] `pytest tests/test_interface_dto_contracts.py tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_api_v1.py tests/test_tui_app.py -q`
- [x] `pytest tests/test_shared_session_gateway_walkthrough.py tests/test_terminal_readiness_gate.py tests/test_tui_readiness_walkthroughs.py -q`
- [x] `python scripts/terminal_readiness_gate.py --skip-full-tests --skip-baseline`
- [x] `node --check src/apps/qqbot_channel/bot.mjs`

## P23.22 TUI Token / Context Telemetry (completed)
- [x] Extend shared-session summary/detail/snapshot/import contracts with `token_usage` and `token_limit`
- [x] Persist and restore shared-session token telemetry through gateway runtime metadata
- [x] Carry token telemetry through local TUI persistence plus share/unshare flows
- [x] Add one unified local/remote session usage computation path in TUI instead of per-surface counters
- [x] Show compact token/context telemetry in the TUI header
- [x] Show token count and context-window usage bar in the TUI status panel

Verification:
- [x] `uv run pytest tests/test_interface_dto_contracts.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_agent_studio_gateway_api_v1.py -q`

## P23.23 Native Knowledge-Base Query Tool (completed)
- [x] Delete the legacy `maxkb_query.py` wrapper instead of keeping a compatibility shell
- [x] Add a native `knowledge_base_query` tool backed directly by the built-in lightweight RAG store
- [x] Share workspace-aware knowledge-base store resolution between turn-context retrieval and explicit tool retrieval
- [x] Register the KB query tool in the main runtime tool bootstrap so agent-core can use explicit grounded retrieval
- [x] Update active docs and focused tests to the new native KB tool contract

Verification:
- [x] `uv run pytest tests/test_knowledge_base_tool.py tests/test_knowledge_base_router.py tests/test_agent_turn_context.py tests/test_security_policy.py tests/test_code_agent_tools.py -q`

## P23.24 Lightweight External KB Mode (completed)
- [x] Keep `knowledge_base_query` enabled by default so the agent can autonomously pull grounded KB context when needed
- [x] Keep KB in explicit-tool mode instead of passive prepared-context mode
- [x] Update config examples, system prompt guidance, and active docs to the lightweight explicit-only behavior
- [x] Add focused tests for config parsing and KB tool bootstrap gating

Verification:
- [x] `uv run pytest tests/test_config_local_env.py tests/test_knowledge_base_tool.py tests/test_agent_turn_context.py tests/test_agent_core_kernel.py -q`

## P23.25 Passive KB Turn-Context Deletion (completed)
- [x] Hard-delete `KnowledgeBaseTurnContextProvider` instead of keeping a disabled-by-default implementation
- [x] Remove the passive KB config switch and all runtime export/registration paths
- [x] Delete passive KB provider tests and sync active docs so KB is documented as explicit-tool-only

Verification:
- [x] `uv run pytest tests/test_knowledge_base_tool.py tests/test_agent_turn_context.py tests/test_config_local_env.py tests/test_agent_core_kernel.py -q`
