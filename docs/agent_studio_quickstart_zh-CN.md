# Mini-Agent Studio 快速上手（中文）

## 1) 一键启动（推荐）

在项目根目录执行：

```powershell
.\scripts\run_agent_studio.ps1
```

启动后会打开两个窗口：

- 网关（FastAPI）：`http://127.0.0.1:8008`
- 前端（Vite）：`http://127.0.0.1:5174`

---

## 2) 手动启动（可选）

### 启动网关

```powershell
uv pip install --python .\.venv\Scripts\python.exe -r .\apps\agent_studio_gateway\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn apps.agent_studio_gateway.main:app --host 127.0.0.1 --port 8008 --reload
```

### 启动前端

```powershell
cd .\apps\agent_studio
npm install
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

---

## 3) 交互模式说明

### Workspace（通用模式）

用途：和 Mini-Agent 连续对话，处理通用开发任务。

操作：

1. 左侧切到 `Workspace`
2. `Workspace Path` 填你要让 Agent 工作的目录
3. `Dry Run=True` 时不消耗模型额度（便于流程调试）
4. `Stream` 可切换：
   - `SSE`：流式增量返回（推荐）
   - `Classic`：一次性返回
5. 在输入框发送任务

### Novel Studio（小说子程序 Demo）

用途：小说生成 + 反复编辑 + 版本对比。

建议顺序：

1. `Setup`：生成设定与目录
2. `Write`：生成章节草稿
3. `Load Draft`：加载到编辑器
4. 编辑后点 `Save`（会自动记录历史版本）
5. `Finalize`：生成终稿并刷新全局摘要
6. `Cover` / `Illustrations`：生成封面和插图

### Assets（素材预览）

用途：查看小说输出资源（封面 / 插图 / 音频）。

---

## 4) 章节版本与差异对比（新）

`Novel Studio` 底部 `Version Diff` 区域已支持：

1. 选择 `Track`：
   - `Draft`（草稿历史）
   - `Final`（终稿历史）
2. 点击 `Reload Versions`
3. 在 `From Version` / `To Version` 选择两个版本
4. 点击 `Compare` 查看 unified diff
5. 点击某个版本条目，可将该版本内容直接载入编辑器

历史数据写入：

`workspace/<project_dir>/chapters/.history/chapter_{n}_{draft|final}.jsonl`

---

## 5) 版本备注/标签与一键回滚（新增）

在 `Novel Studio -> Version Diff` 中：

1. 先点击一个版本条目（会自动加载内容到编辑器）
2. 在 `Version Meta` 里编辑：
   - `Note`：版本备注
   - `Tags`：逗号分隔标签
3. 点击 `Save Meta` 保存该版本元信息
4. 点击 `Rollback` 可一键回滚到该版本内容
   - 回滚后会自动再生成一个 `source=rollback` 的新版本快照

另外，编辑器上方新增 `Save Note / Save Tags`：

- 每次手动 `Save` 章节时可直接写入这次保存的备注与标签
- 方便后续版本筛选、回看和比对

---

## 6) Workspace 流式取消（新增）

在 `Workspace` 模式：

1. `Stream` 设为 `SSE`
2. 发送任务后，输入区会出现 `Cancel Stream`
3. 点击后会中断本次流式请求，当前消息标记为“已取消本次流式请求”

---

## 7) 主要输出目录

默认项目目录：

`C:/Users/Conli/Mini-Agent/workspace/mini-agent-novel-demo`

常见输出：

- 章节：`chapters/chapter_*.txt`
- 终稿：`chapters/final_chapter_*.txt`
- 封面：`covers/*.png`
- 插图：`illustrations/*.png`
- 版本历史：`chapters/.history/*.jsonl`

---

## 8) 常用排查

- 网关健康检查：`http://127.0.0.1:8008/api/v1/system/health`
- 前端请求失败：先确认 `VITE_API_BASE` 是否指向 `8008`
- 无法生成内容：确认已配置 `MINIMAX_API_KEY`
- 先做流程演练：可先开 `Dry Run=True`

---

## 9) QQ Bot 通讯渠道（新增）

已新增目录：

`apps/qqbot_channel`

快速启动：

```powershell
Copy-Item .\apps\qqbot_channel\.env.example .\apps\qqbot_channel\.env
# 编辑 .env，填入 QQBOT_APPID / QQBOT_SECRET
.\scripts\run_qqbot_channel.ps1
```

QQ 指令示例：

- `/help`
- `/status`
- `/workspace C:/Users/Conli/Mini-Agent`
- `/dryrun on`
- `/reset`

## 10) Studio Ops 鉴权与烟测（P17 T5.2 hardening）

当网关设置了 `MINI_AGENT_STUDIO_API_KEYS` 时：

```powershell
$env:VITE_STUDIO_API_KEY="<studio-token>"
cd .\apps\agent_studio
npm run dev
```

后端合同烟测：

```powershell
.\.venv\Scripts\python.exe .\scripts\studio_ops_smoke.py `
  --base-url http://127.0.0.1:8008 `
  --token <studio-token> `
  --expect-auth
```

---

## 11) New Dev Manager (`mini-agent dev`)

Use one command family to manage exactly one backend host + one frontend dev server:

```powershell
# Start dev stack (backend + frontend)
python -m mini_agent.cli dev up

# Check status
python -m mini_agent.cli dev status

# Tail logs
python -m mini_agent.cli dev logs --target all --lines 120

# Stop stack
python -m mini_agent.cli dev down --force
```

Profile commands:

```powershell
# Ensure default profile template and inspect effective env
python -m mini_agent.cli dev profile --profile single-main --init-profile --show-json

# Optional: switch to team-reserved profile (future multi-agent rollout)
python -m mini_agent.cli dev profile --profile team-reserved --init-profile --show-json
```
