# Mini-Agent 架构说明

> **状态**: ✅ 活跃
> **最后更新**: 2026-04-06
> **文档索引**: [docs/DOCS_INDEX.md](docs/DOCS_INDEX.md)

Updated: 2026-04-06

> **注意**: 本文档描述的是当前版本的架构。深度改造方案 (v2) 请参阅 `docs/TRANSFORMATION_PLAN.md`。

## 启动模式

Mini-Agent 支持两种启动模式：

### 1. Gateway 模式 (默认)

完整服务模式，启动 Gateway、子程序、渠道和 WebUI。

```bash
# 启动所有服务
mini-agent

# 指定端口
mini-agent --port 8080

# 禁用 WebUI
mini-agent --no-webui

# 禁用渠道
mini-agent --no-channels

# 开发模式 (自动重载)
mini-agent --reload
```

### 2. CLI 模式

交互式终端模式，直接与 Agent 对话。

```bash
# 交互式会话
mini-agent cli

# 执行单次任务
mini-agent cli --task "创建一个 README 文件"

# 指定工作目录
mini-agent cli --workspace D:\my_project
```

## 子命令

```bash
# 列出可用子程序
mini-agent list subprograms

# 列出可用渠道
mini-agent list channels

# 列出所有
mini-agent list all

# 启动特定服务
mini-agent start gateway
mini-agent start novel
```

## 目录结构

### 当前版本

```
Mini-Agent/
├── mini_agent/                    # 核心库
│   ├── agent.py                   # Agent 核心实现
│   ├── cli.py                     # 统一 CLI 入口
│   ├── cli_interactive.py         # 交互式会话
│   ├── config.py                  # 配置管理
│   ├── core/                      # 核心模块
│   │   └── session.py             # 会话管理
│   ├── launcher/                  # 启动器模块
│   │   ├── scanner.py             # 子程序/渠道扫描器
│   │   ├── gateway.py             # Gateway 启动器
│   │   └── orchestrator.py        # 服务编排器
│   ├── llm/                       # LLM 客户端
│   ├── tools/                     # 工具集
│   └── schema/                    # 数据模型
│
├── gateway/                       # Gateway 核心
│   ├── core/                      # 核心功能
│   ├── channels/                  # Channel 抽象接口
│   └── routers/                   # API 路由
│
├── channels/                      # 渠道实现
│   ├── types/                     # TypeScript 类型定义
│   ├── qqbot/                     # QQ Bot 渠道
│   └── wechat/                    # 微信渠道 (预留)
│
├── subprograms/                   # 子程序
│   └── novel_generator/           # 小说生成器
│
└── apps/                          # 旧目录 (兼容保留)
```

### 改造后目标结构 (详见 `docs/TRANSFORMATION_PLAN.md`)

```
Mini-Agent/
├── mini_agent/
│   ├── model_manager/             # [新增] 模型管理(CC Switch提取)
│   ├── memory/                    # [重构] 记忆核心(五源融合)
│   ├── code_agent/                # [新增] 编程代理(三源融合)
│   ├── agent_core/                # [重构] 智能体核心(OpenClaw+Hermes)
│   ├── channels/                  # [精简] QQ + WeChat
│   ├── llm/                       # [扩展] 多客户端
│   ├── tools/                     # [扩展] 新工具集
│   └── launcher/
├── gateway/                       # [增强]
├── subprograms/                   # [扩展] 新子程序
├── apps/                          # [扩展] Open WebUI集成
└── workspace/
```

## 服务架构

```
┌─────────────────────────────────────────────────────────────┐
│                    mini-agent (统一入口)                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────────┐         ┌─────────────────────────┐  │
│   │  Gateway 模式   │         │      CLI 模式           │  │
│   │  (默认)         │         │   (mini-agent cli)      │  │
│   └────────┬────────┘         └────────────┬────────────┘  │
│            │                               │                │
│            ▼                               ▼                │
│   ┌─────────────────┐         ┌─────────────────────────┐  │
│   │ • Gateway 核心   │         │ • 交互式 Agent 会话     │  │
│   │ • 子程序扫描器   │         │ • 启动 Gateway          │  │
│   │ • 渠道管理器     │         │ • 启动渠道              │  │
│   │ • WebUI 服务     │         │ • 管理子程序            │  │
│   └─────────────────┘         └─────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 添加新子程序

1. 在 `subprograms/` 下创建目录
2. 添加 `manifest.json` 描述文件
3. 实现功能模块

```json
// subprograms/my_subprogram/manifest.json
{
  "name": "my-subprogram",
  "version": "0.1.0",
  "description": "My custom subprogram",
  "enabled": true,
  "router_module": "subprograms.my_subprogram.router:router",
  "config": {
    "mount_path": "/api/my-subprogram"
  }
}
```

## 添加新渠道

1. 在 `channels/` 下创建目录
2. 添加 `manifest.json` 描述文件
3. 实现 `IChannel` 接口

```typescript
// channels/my_channel/src/channel.ts
import { IChannel } from "@mini-agent/channel-types";

export class MyChannel implements IChannel {
  getChannelType(): string { return "my-channel"; }
  async start(): Promise<void> { /* ... */ }
  async stop(): Promise<void> { /* ... */ }
  // ...
}
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/chat` | POST | 发送消息 |
| `/api/chat/stream` | GET | SSE 流式响应 |
| `/api/sessions` | GET | 列出会话 |
| `/api/novel/*` | * | 小说生成器 API |

## 配置

配置文件位于 `mini_agent/config/config.yaml`：

```yaml
api_key: "YOUR_API_KEY"
api_base: "https://api.minimax.io"
model: "MiniMax-M2.5"
max_steps: 100

tools:
  enable_file_tools: true
  enable_bash: true
  enable_mcp: true
  enable_skills: true
```
