# Mini-Agent QQ Bot 渠道

这个目录是 Mini-Agent 当前唯一保留的 QQ 渠道运行实现。

定位很明确：

- 基于官方 `qq-official-bot` SDK
- 作为 QQ 协议桥接层存在
- 通过网关调用 Mini-Agent 的共享会话与应用服务
- 不再维护第二套 QQ 会话真相

## 当前职责

- 接收 QQ 消息
- 维护最小化的会话绑定状态：
  - `conversation key`
  - 绑定的 `session_id`
  - 当前 `workspace`
  - `dry_run`
  - 渠道显示名
- 将普通消息转发到网关 `GET /api/v1/agent/chat/stream`
- 将 `/session` `/model` `/memory` `/skill` `/approve` 等命令转发到共享会话接口

## 环境变量

必填：

- `QQBOT_APPID`
- `QQBOT_SECRET`

常用：

- `MINI_AGENT_GATEWAY_BASE`
- `QQBOT_GATEWAY_AUTH_TOKEN`
- `QQBOT_NAME`
- `QQBOT_DEFAULT_WORKSPACE`
- `QQBOT_DEFAULT_DRY_RUN`
- `QQBOT_ALLOWED_WORKSPACE_ROOTS`
- `QQBOT_MAX_MESSAGE_CHARS`
- `QQBOT_MAX_REPLY_CHUNK_SIZE`

## 启动

```powershell
Copy-Item .\.env.example .\.env
npm install
npm run start
```

更常见的项目级启动方式仍然是：

```powershell
uv run mini qq
```

## Smoke

当前 QQ 渠道的合成 smoke 已迁到这个目录：

```powershell
npm run smoke
```

它会验证：

- `workspace` 允许/拒绝边界
- 现行 `agent/chat/stream` 转发契约
- 会话绑定
- `reset` 控制接口

## 说明

- `.env.example` 只做模板，不会自动加载
- 当前唯一运行路径是 `src/apps/qqbot_channel`
- 历史 QQ TypeScript channel 包与旧 Python OneBot 适配器已不再作为活跃实现保留
