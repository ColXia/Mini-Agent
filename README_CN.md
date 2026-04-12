# Mini-Agent

[English](./README.md) | 中文

Mini-Agent 是一个以终端为主入口的 Agent 平台，当前重点是 `TUI / CLI / headless` 的真实可用性。
它整合了统一的会话与运行时内核、模型与供应商管理、记忆与 RAG、内置 skills、MCP 能力，以及可选的 gateway + QQ 渠道工作流。

## 当前状态

- 主用户面：`TUI`、`CLI`、`headless`
- 可选运行栈：gateway + QQ bot
- WebUI：当前暂停，不是主开发目标
- 当前架构主线：`P30` 会话中心化重构

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
- QQ 渠道的可选 Node.js 依赖，位于 [`src/apps/qqbot_channel/package.json`](./src/apps/qqbot_channel/package.json)：
  - `dotenv`
  - `qq-official-bot`

### 仓库内置，不算外部依赖

这些内容已经随仓库提供，不需要 `git submodule`：

- [`src/mini_agent/skills`](./src/mini_agent/skills) 下的内置 skills
- [`scripts/`](./scripts) 下的脚本
- [`tests/`](./tests) 下的测试

### 仅参考，不是运行依赖

项目在设计和实现上参考过外部 Agent 项目，但它们不是当前仓库的运行时依赖：

- `codex`
- `gemini-cli`
- `opencode`
- 本地 `extracted-src` 对照工程

实际映射见 [`docs/OSS_REFERENCE_INDEX.md`](./docs/OSS_REFERENCE_INDEX.md)。

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
src/mini_agent/                 核心运行时、命令系统、TUI、agent、memory、models
src/apps/agent_studio_gateway/  Gateway / API Host
src/apps/qqbot_channel/         可选 QQ 渠道应用
scripts/                        走查、冒烟、维护脚本
tests/                          自动化测试
docs/                           活跃文档与历史归档
workspace/                      本地运行产物与测试输出
```

## Skills 与 MCP

- 内置 skills 位于 [`src/mini_agent/skills`](./src/mini_agent/skills)
- 工作区 / 自定义 skills 通过 `/skill ...` 管理
- MCP 通过统一运行时与命令面接入
- 相关文档：
  - [`docs/P28_BUILTIN_SKILL_REALIGNMENT_PLAN.md`](./docs/P28_BUILTIN_SKILL_REALIGNMENT_PLAN.md)
  - [`src/mini_agent/skills/README.md`](./src/mini_agent/skills/README.md)

## 测试

```bash
uv run pytest
uv run pytest tests/test_markdown_links.py -q
uv run mini-agent --help
uv run mini-agent doctor
```

## 相关文档

- [`docs/DOCS_INDEX.md`](./docs/DOCS_INDEX.md)
- [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)
- [`docs/DEVELOPMENT_GUIDE.md`](./docs/DEVELOPMENT_GUIDE.md)
- [`docs/DEVELOPMENT_GUIDE_CN.md`](./docs/DEVELOPMENT_GUIDE_CN.md)
- [`docs/DEVELOPMENT_INDEX.md`](./docs/DEVELOPMENT_INDEX.md)
- [`docs/OSS_REFERENCE_INDEX.md`](./docs/OSS_REFERENCE_INDEX.md)

## 说明

- 旧的 `git submodule` skills 初始化流程已不是当前主路径。
- 旧 README 中只讲 `config.yaml` 的方式已经过时；当前预设供应商主路径是环境变量 + `.env.local`。
- 历史文档和旧开发日志已归入 [`docs/archive/`](./docs/archive/)。
