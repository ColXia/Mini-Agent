# Mini-Agent Studio 开发日志（2026-03-30）

## 目标

本轮目标是把 Mini-Agent 做成一个“可视化主工作台 + 小说生成子程序（Demo）”：

1. 通用模式下可与 Mini-Agent 连续对话，适合多任务开发场景。  
2. 小说生成仅作为子模块存在，支持反复查看、编辑、回滚、再生成。  
3. 资源（封面 / 插图 / 音频）可集中可视化预览。  

---

## Phase 1：基础可视化工作台

### 已完成

- 新增前端：`apps/agent_studio`（React + Vite，多模式 UI）
- 新增网关：`apps/agent_studio_gateway/main.py`（FastAPI）
- 新增一键启动脚本：`scripts/run_agent_studio.ps1`
- 新增模式化界面：
  - `Workspace`：通用 Agent 对话
  - `Novel Studio`：小说子程序
  - `Assets`：素材可视化浏览
- 网关打通小说工作流：
  - setup / write / finalize
  - chapter 读取与保存
  - cover / illustrations 生成
  - assets 列表查询

---

## Phase 2：交互与编辑增强（本次推进重点）

### 1) Workspace 增强：SSE 流式返回

已实现流式接口：`GET /api/chat/stream`

- 事件类型：
  - `session`
  - `status`
  - `heartbeat`
  - `delta`
  - `done`
  - `error`
- 前端新增 `Stream` 开关：`SSE / Classic`
- 默认使用 SSE，前端按 `delta` 增量更新消息气泡
- 保留原 `POST /api/chat`，用于非流式兼容

### 2) Novel Studio 增强：章节版本快照 + 对比

已实现章节历史与对比能力：

- 自动快照触发点：
  - `POST /api/novel/write` -> `source=generate_write`
  - `POST /api/novel/finalize` -> `source=finalize_step4`
  - `PUT /api/novel/chapter/{chapter}` -> `source=manual_save`
- 历史存储：`chapters/.history/chapter_{n}_{draft|final}.jsonl`
- 新增接口：
  - `GET /api/novel/chapter/{chapter}/versions`
  - `GET /api/novel/chapter/{chapter}/version/{version_id}`
  - `GET /api/novel/chapter/{chapter}/diff`
- 前端已支持：
  - 版本列表加载
  - 任意版本载入编辑器
  - 选择 from/to 进行 unified diff 对比

---

## Phase 3：回滚与交互可控性（追加推进）

### 1) 版本备注/标签

后端：

- 版本快照新增字段：`note`、`tags`
- 新增接口：`PATCH /api/novel/chapter/{chapter}/version/{version_id}`

前端：

- `Version Meta` 面板可编辑并保存备注/标签
- 编辑器保存时可附带 `Save Note / Save Tags`

### 2) 一键回滚

后端：

- 新增接口：`POST /api/novel/chapter/{chapter}/rollback`
- 依据 `version_id` 恢复章节文件，并自动写入 `source=rollback` 新快照

前端：

- 版本列表选中后可直接 `Rollback`
- 回滚结果立即回填编辑器，方便继续修改

### 3) Workspace 流式取消

前端新增 `Cancel Stream`：

- 仅在 `SSE` 流式发送中显示
- 使用 `AbortController` 中断当前请求
- 聊天气泡显示“已取消本次流式请求”

---

## 验证记录

### 编译/构建

- `python -m py_compile apps/agent_studio_gateway/main.py` ✅
- `npm run build`（目录：`apps/agent_studio`）✅

### 网关烟测（FastAPI TestClient）

- `/api/novel/setup`（dry-run）✅
- `/api/novel/write`（dry-run）✅
- `/api/novel/chapter/{n}` 保存 ✅
- `/api/novel/chapter/{n}/versions` ✅
- `/api/novel/chapter/{n}/diff` ✅
- `/api/chat/stream?dry_run=true`（SSE 事件序列）✅
- `/api/novel/chapter/{n}/version/{version_id}` PATCH（备注/标签）✅
- `/api/novel/chapter/{n}/rollback`（回滚）✅

---

## 当前状态

- 可视化主工作台可用。  
- 小说子程序可“生成 -> 编辑 -> 存档 -> 比较 -> 再编辑”。  
- Workspace 已支持流式交互体验。  

---

## 下一步建议（可继续推进）

1. 增加章节版本“标签/备注”（方便多人协作定位）。  
2. 增加“回滚到该版本”一键操作。  
3. 为 SSE 增加“取消请求”与超时反馈。  
4. 增加 Novel Studio 的 Markdown/富文本预览模式。  
5. 在通用工作台接入更多任务子程序入口（不止小说）。  
