# Mini-Agent

[English](./README.md) | 中文

Mini-Agent 是一个以终端为主入口的 Agent 平台，当前重点是 `TUI / CLI / headless` 的真实可用性。
它整合了统一的会话与运行时内核、模型与供应商管理、记忆与 RAG、内置 skills、MCP 能力，以及可选的 gateway + 远程交互工作流，当前远程适配器实现为 QQ。

## 当前状态

- **版本**: v0.2.0 | **架构**: v11.1 | **协议**: MIT
- **测试**: 1723 passed, 17 skipped
- **Python**: >= 3.10
- 主入口：`CLI`、`TUI`、`桌面端`（PySide6）、`远程侧`（QQ Bot）

## 依赖与参考的边界

### 真实运行依赖

Mini-Agent 当前真实依赖：

- `Python >= 3.10`
- `uv`
- [pyproject.toml](./pyproject.toml) 中声明的 Python 依赖，包括：
  - `pydantic`
  - `pyyaml`
  - `httpx`
  - `requests`
  - `mcp`
  - `tiktoken`
  - `prompt-toolkit`
  - `openai`
  - `anthropic`
  - `fastapi`
  - `uvicorn`
  - `python-dotenv`
- 当前 QQ 远程适配器的可选 Node.js 依赖，位于 [`src/apps/qqbot_channel/package.json`](./src/apps/qqbot_channel/package.json)：
  - `dotenv`
  - `qq-official-bot`

### 仓库内置，不算外部依赖

这些内容已经随仓库提供，不需要 `git submodule`：

- [`src/mini_agent/skills`](./src/mini_agent/skills) 下的内置 skills
- [`scripts/`](./scripts) 下的脚本
- [`tests/`](./tests) 下的测试

## 快速开始

### 1. 克隆并安装

```bash
git clone https://github.com/ColXia/Mini-Agent.git
cd Mini-Agent
uv sync
```

### 2. 配置供应商密钥

预设供应商优先读取系统环境变量，其次读取 `.env.local`。

支持的官方变量名：

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `MINIMAX_API_KEY`

本地开发可从模板复制：

```bash
cp .env.local.example .env.local
```

然后只填写你要用的 key。

优先级：

1. 系统环境变量
2. 本地 `.env.local`

### 3. 启动 Mini-Agent

```bash
uv run mini
```

常用入口：

```bash
uv run mini-agent --mode tui
uv run mini-agent --mode cli
uv run mini-agent --prompt "hello"
uv run mini-agent serve --port 8008
uv run mini-agent stack up
uv run mini qq
```

## 模型与供应商

预设供应商：

- 根据官方环境变量自动识别
- 可自动发现可用模型列表
- 可在 `/model` 或 TUI 的 `models` 面板中切换

自定义供应商：

- 持久化到 `~/.mini-agent/providers.json`
- 通过 `provider add` 或 Studio/gateway 流程创建
- 在统一模型注册表中显示在预设供应商之前

常用命令：

```bash
uv run mini-agent provider list
uv run mini-agent provider add --help
uv run mini-agent models --list-presets
uv run mini-agent models minimax --latest
```

## 仓库结构

```text
src/mini_agent/                 核心运行时（24个顶层包，~350+ .py 文件）
  agent_core/                    Agent 内核、引擎、执行循环、权限、上下文、Skills
  application/                   应用层（端口/用例/门面/用户服务）
  runtime/                       运行时（处理器/编排/实时控制/读模型）
  session/                       会话持久化与投影
  workspace_runtime/             工作区运行时与执行器
  model_manager/                 模型池、注册、健康监控、熔断
  memory/                        记忆系统（自动化/整合/提升/检索）
  tools/                         工具系统（Shell/文件/MCP/知识库）
  skills/                        内置技能与技能解析器
  tui/                           TUI 终端界面（Textual）
  desktop/                       PySide6 桌面应用
  transport/                     传输层（Gateway 客户端、远程客户端）
  llm/                           LLM 客户端（Anthropic/OpenAI）
  interfaces/                    接口定义与 DTO
  schema/                        数据模型与 Schema
  commands/                      命令解析/补全/元数据
  config/                        配置管理
  security/                      安全策略与审计
  rag/                           轻量 RAG（BM25+向量+RRF）
  ops/                           运维工具
  user_services/                 用户服务门面
  workspace/                     工作区领域模型
  utils/                         工具函数
  dev/                           开发工具
src/apps/agent_studio_gateway/  Gateway / API Host
src/apps/desktop_ui/            DesktopUI 启动入口
src/apps/qqbot_channel/         QQ 远程适配器（Node.js）
src/subprograms/                子程序（文档解析/知识库/记忆管理）
scripts/                        走查、冒烟、维护脚本
tests/                          自动化测试（1723 个用例）
docs/                           项目文档、设计文档、历史归档
  docs/project-documentation/   最新中文项目文档
  docs/plans/                   v11.6-v11.20 设计规划
  docs/v11.1/                   v11.1 架构设计文档
workspace/                      本地运行产物与测试输出
```

## Skills 与 MCP

- 内置 skills 位于 [`src/mini_agent/skills`](./src/mini_agent/skills)
- 工作区 / 自定义 skills 通过 `/skill ...` 管理
- MCP 通过统一运行时与命令面接入

## 测试

```bash
uv run pytest
uv run pytest tests/test_markdown_links.py -q
uv run mini-agent --help
uv run mini-agent doctor
```

## 相关文档

- **最新中文项目文档**: [`docs/project-documentation/`](./docs/project-documentation/)
- **架构设计**: [`docs/v11.1/`](./docs/v11.1/) | [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)
- **开发指南**: [`docs/DEVELOPMENT_GUIDE_CN.md`](./docs/DEVELOPMENT_GUIDE_CN.md)
- **API 契约**: [`docs/API_V1_CONTRACT_SKELETON.md`](./docs/API_V1_CONTRACT_SKELETON.md)

## 协议

MIT — 详见 [LICENSE](./LICENSE)。
