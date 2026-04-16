# P23 终端真实使用测试准备（TUI/CLI）

> 状态: Active  
> 更新时间: 2026-04-08

## 1. 范围与目标

- 范围: `TUI/CLI/Headless` 终端主链。
- 移除范围: 浏览器 `WebUI/OpenWebUI` 已删除，不再属于验收面。
- 目标: 终端主链门禁已通过；当前进入以 `TUI` 为主入口的真实使用修边角阶段，持续通过门禁、清单和 walkthrough 约束质量。

## 2. 前置条件

- 至少一种预设供应商密钥可用（系统环境变量优先，其次 `.env.local`）：
  - `OPENAI_API_KEY`
  - `ANTHROPIC_API_KEY`
  - `GEMINI_API_KEY`
  - `MINIMAX_API_KEY`
- `.env.local.example` 仅模板，不参与加载。

## 3. 自动化门禁（推荐）

执行：

```powershell
python scripts/terminal_readiness_gate.py
```

说明：

- 包含 `CLI 可启动性 + 终端主链目标测试 + 全量回归 + P23 baseline`。
- 报告默认输出到 `workspace/readiness/terminal_readiness_<utc>.md`。

可选：启用真实 LLM 链路的 headless 冒烟：

```powershell
python scripts/terminal_readiness_gate.py --run-live-headless
```

可选：运行 TUI 交互清单走查（`/session`、`/model`、`/workflow`、`/cancel`、`/tasks`）：

```powershell
python scripts/tui_manual_checklist.py
```

- 报告默认输出到 `workspace/readiness/tui_manual_checklist_<utc>.md`。

可选：运行 prompt_toolkit 驱动的 TUI 真实交互走查（多行输入、滚动、slash command、workflow、cancel）：

```powershell
python scripts/tui_interaction_walkthrough.py
```

- 报告默认输出到 `workspace/readiness/tui_interaction_walkthrough_<utc>.md`。

## 4. 手工验收清单（真实使用）

1. CLI 单次任务：
   - `mini-agent --mode headless --prompt "请用一句话回复 READY" --output-format json`
   - 期望：返回 `ok=true` 且输出可读。
2. CLI 交互模式：
   - `mini-agent --mode cli`
   - 验证：正常提交任务、可中断、可继续下一轮。
3. TUI 模式：
   - `mini-agent --mode tui`
   - 验证：会话切换、`/tasks` 状态刷新、`/cancel` 后恢复、`/workflow` 可执行。
4. 模型管理：
   - 在 `/models` 验证“自定义在上、预设在下”以及可切换默认模型。

## 5. 当前基线（2026-04-08）

- 全量测试：`511 passed, 16 skipped`
- 警告收敛：
  - FastAPI `on_event` 已迁移为 `lifespan`
  - `asyncio.iscoroutinefunction` 弃用路径已清理

## 6. 2026-04-08 TUI 验收补充

- 主界面布局预期：左侧为对话/输入主工作区，右侧为 `Threads -> Models -> Status` 的紧凑侧栏。
- 状态展示预期：启动/初始化噪音不混入聊天消息流；当前回合的 `thinking/tool/shell` 活动以紧凑时间线块显示在主对话区，同时在右侧 `Status` 仅保留运行态、任务、视图、模型与过滤摘要，不重复堆叠 thread 标题。
- Thinking 展示预期：主对话区优先显示 `starting/planning/drafting/ready` 这类短阶段标签，不把 `step x:` 工程细节直接堆给用户。
- 模型切换预期：应用模型后，焦点标记与当前默认模型标记应落在同一模型条目上。
- 模型侧栏预期：默认展示 `Active + focus + Providers + Models` 的紧凑摘要结构，而不是全量长列表堆叠。
- 对话区预期：用户、Mini-Agent、System、Activity 消息按独立消息块显示，不混成连续日志行。
- 回复排版预期：assistant 多段正文、列表、空行在主对话区保留分段，不压平成单段长文本。
- 回复层级预期：assistant 的标题、列表、引用、代码块在主对话区具备可区分的视觉层级，不再全部以同一种正文样式堆叠。
- 代码块呈现预期：assistant 代码块使用独立的边框起止行（如 `+ code: <lang>` / `+ end code`）与缩进正文，形成稳定的“块感”，避免和普通段落混排。
- Threads 侧栏预期：按“标题 + live 标记 / 运行态与计数 / 最近消息预览”结构化展示，保持固定三行摘要；预览应清理 markdown 符号，并把 activity 转成可读动作摘要，不回退为生硬统计拼接行。
- Shell 活动预期：折叠态显示 `cmd` 与 `out` 摘要，展开态显示完整输出块，不把纯技术字段挤占主摘要。
- 工具活动预期：`read-file/search/grep/bash` 等工具完成后默认收叠为单行摘要；展开后再看详细输入与输出。
- 工具类型样式预期：`thinking/shell/read/search/write` 等活动在主对话区使用可区分的类型样式，便于快速判断当前 agent 正在做什么。
- 活动时间线节奏预期：最近一条活动在主对话区使用更醒目的前缀与颜色，较早活动自动减弱，保证“当前正在做什么”一眼可见，同时保留完整操作轨迹。
- 活动交互预期：`F4` 或 `/activity [toggle|expand|collapse]` 可切换主对话区活动输出的展开状态。
- 对话启动预期：fresh session 聊天区默认保持干净，不注入启动提示或技能发现等内部信息。
- 对话渲染预期：消息区使用稳定的消息视图而不是只读日志框；窄窗口下仍需自动换行。
- 历史滚动预期：`PgUp/PgDn` 可翻阅聊天历史，`Ctrl+End` 可回到 live tail，状态区显示 `live/history`。
- 终端兼容预期：消息分隔符与 CLI banner 在非 UTF-8 Windows 终端下自动回退到 ASCII，避免出现 Unicode 乱码。
- 输入区预期：使用多行 composer；`Enter` 发送，`Esc+Enter` 换行。
- 输入区尺寸预期：composer 保持比旧版更高的默认高度，长提示词不应被压成单行输入体验。
- 侧栏交互预期：不显示“看起来可滚动但实际不可用”的假滚动条。

## 7. 2026-04-09 Gate Update

- `python scripts/terminal_readiness_gate.py --run-live-headless` now runs the real headless smoke before targeted/full regression and runtime baseline.
- Live mode now uses a lighter default for `p23_runtime_baseline` (`--runs 20`) unless overridden.
- Live headless reports now include a `Live Headless Context` section summarizing:
  - whether the headless JSON contract still exposes `prepared_context_diagnostics`
  - cross-turn diagnostics summary captured during the smoke run
  - the last prepared-context selection summary plus source/provider coverage
- If live headless smoke exits successfully but no longer emits `prepared_context_diagnostics`, the readiness gate now reports `FAIL` instead of a false-green pass.
- `python scripts/terminal_readiness_gate.py` now also runs these scripted TUI readiness checks by default:
  - `python scripts/tui_manual_checklist.py`
  - `python scripts/tui_interaction_walkthrough.py`
- `python scripts/terminal_readiness_gate.py` now also runs this scripted shared-session gateway readiness check by default:
  - `python scripts/shared_session_gateway_walkthrough.py`
- `python scripts/terminal_readiness_gate.py` now also runs this scripted channel-ingress gateway readiness check by default:
  - `python scripts/channel_ingress_gateway_walkthrough.py`
- Those scripted walkthroughs now cover `/context include|exclude|budget|show|stats|reset`, so operator-visible context controls are part of the default readiness contract instead of optional side checks.
- The shared-session walkthrough covers qq-origin metadata, TUI takeover, remote activity transcript visibility, shared context controls, remote cancel, import/export roundtrip, and restart persistence.
- The shared-session walkthrough now also covers interrupted-after-restart recovery snapshots, so restart safety is no longer limited to “session still exists”.
- The channel-ingress walkthrough covers the real `channel ingress -> gateway -> shared session` chain: session reuse, metadata persistence, `/continue`-style recent transcript visibility, activity retention, and TUI takeover.
- You can skip the scripted TUI walkthroughs explicitly for faster local runs:

```powershell
python scripts/terminal_readiness_gate.py --skip-tui-checklist --skip-tui-walkthrough --skip-shared-session-walkthrough --skip-channel-ingress-walkthrough
```

- Quick real-use validation is now available via:

```powershell
python scripts/terminal_readiness_gate.py --run-live-headless --skip-baseline
```

- You can override the benchmark count explicitly:

```powershell
python scripts/terminal_readiness_gate.py --baseline-runs 37
```

## 8. 2026-04-09 Shared-Session Remote Approval Update

- Gateway-managed shared sessions now expose live pending tool approvals through the main session detail contract.
- New remote approval API:

```powershell
POST /api/v1/agent/sessions/{session_id}/approval
```

- TUI shared sessions now support:

```text
/approve [token]
/deny [token]
```

- QQ bot shared sessions now support:

```text
/approve [token]
/deny [token]
```

- `GET /api/v1/agent/sessions/{session_id}` now surfaces:
  - `pending_approvals` for live waiting approvals
  - `recovery.pending_approvals` for approvals lost after restart
- Remote `/cancel` now resolves approval waiters too, so a session cannot remain hung forever while waiting for approval input.

## 9. 2026-04-09 Restart Recovery Continuation Update

- Interrupted shared sessions now keep a stronger recovery record after restart:
  - `recovery.state`
  - `recovery.summary`
  - `recovery.last_activity`
  - `recovery.last_user_message`
  - `recovery.last_assistant_message`
  - `recovery.pending_approvals`
- Recovery is no longer only a passive operator summary. The next real continuation turn now receives the same recovery payload once through `turn_context.metadata["recovery"]`.
- Lost approvals after restart now prefer an approval-focused summary such as `interrupted after restart: approval pending for shell`, while still preserving last activity and transcript hints.
- Taking over a restarted shared session from TUI does not immediately clear recovery state anymore. Recovery remains visible until the next successful continuation turn consumes it.
- TUI `/approve` against a lost-after-restart approval now tells the operator to send a new message to continue with recovery context.
- QQ `/status` and `/continue` now include the same resume hint when a shared session was interrupted by restart.

Recommended verification:

```powershell
pytest tests/test_agent_core_turn_context.py tests/test_main_agent_gateway_use_cases.py tests/test_tui_app.py tests/test_shared_session_gateway_walkthrough.py -q
python scripts/shared_session_gateway_walkthrough.py
python scripts/terminal_readiness_gate.py --skip-full-tests --skip-baseline
node --check src/apps/qqbot_channel/bot.mjs
```

## 10. 2026-04-09 Shared-Session Remote Context Update

- Shared-session detail/snapshot contracts now also carry:
  - `context_policy`
  - `last_prepared_context`
  - `prepared_context_diagnostics`
- New gateway endpoint:

```powershell
POST /api/v1/agent/sessions/{session_id}/context
```

- Remote TUI shared sessions now support the same prepared-context operator flow as local TUI:

```text
/context show [brief|full]
/context stats
/context include <source...>
/context exclude <source...>
/context budget <max_items> [max_total_chars] [max_items_per_source]
/context reset
```

- QQ bot bound to a shared session now supports the same `/context ...` command family.
- Shared-session share/unshare now preserves prepared-context state instead of dropping it during gateway import/export.
- Future shared-session turns now apply the persisted remote context policy through `turn_context.metadata["prepared_context_policy"]`, so remote operators are changing the real next-turn runtime behavior.

Recommended verification:

```powershell
pytest tests/test_interface_dto_contracts.py tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_api_v1.py tests/test_tui_app.py -q
pytest tests/test_shared_session_gateway_walkthrough.py tests/test_terminal_readiness_gate.py tests/test_tui_readiness_walkthroughs.py -q
python scripts/terminal_readiness_gate.py --skip-full-tests --skip-baseline
node --check src/apps/qqbot_channel/bot.mjs
```

## 11. 2026-04-09 Shared-Session Remote Model Parity

- Shared-session summary/detail/snapshot contracts now also carry:
  - `selected_model_source`
  - `selected_provider_id`
  - `selected_model_id`
  - `pending_model_source`
  - `pending_provider_id`
  - `pending_model_id`
- New gateway endpoints:

```powershell
GET  /api/v1/agent/models
POST /api/v1/agent/sessions/{session_id}/model
```

- Shared-session remote model switching is now session-scoped instead of only mutating global provider defaults.
- Idle shared-session switches rebuild that session agent immediately with the exact provider/model pin.
- Busy shared-session switches are persisted as queued state and apply automatically before the next real turn starts.
- Remote TUI shared sessions now show the real selected/queued model hint instead of `gateway-managed`.
- QQ bot bound to a shared session now supports:

```text
/model show
/model list
/model use <provider_id> <model_id>
```

- Shared-session share/unshare now preserves selected/pending model state during gateway import/export.
- The scripted shared-session walkthrough and readiness gate now cover remote model switching as part of the default shared-session readiness path.

Recommended verification:

```powershell
uv run pytest tests/test_interface_dto_contracts.py tests/test_main_agent_gateway_use_cases.py tests/test_agent_studio_gateway_api_v1.py tests/test_tui_app.py tests/test_shared_session_gateway_walkthrough.py tests/test_tui_readiness_walkthroughs.py -q
uv run python scripts/shared_session_gateway_walkthrough.py
uv run python scripts/terminal_readiness_gate.py --skip-full-tests --skip-baseline
node --check src/apps/qqbot_channel/bot.mjs
```
