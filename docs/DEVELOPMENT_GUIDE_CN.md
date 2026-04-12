# 开发指南

> 状态：active
> 最后更新：2026-04-12
> 当前模式：terminal-first（`TUI / CLI / headless`）

## 1. 本文档说明

这份指南描述的是 Mini-Agent 当前真实的开发状态，
不再沿用早期上游 demo 阶段已经失真的安装与接入说明。

适用场景：

- 本地开发环境准备
- 统一命令入口使用
- 供应商与模型配置
- skills / MCP 开发边界
- 测试与仓库卫生规范

## 2. 当前架构快照

当前开发中最重要的三层是：

1. 用户面
- TUI
- CLI
- headless 终端执行
- 可选 QQ 渠道

2. 应用与运行时层
- session application services
- command execution services
- runtime orchestration
- gateway use cases

3. 核心能力层
- agent core
- model manager
- memory
- RAG
- skills
- MCP
- session persistence / projection

当前必须遵守的架构规则：

- `Session` 是唯一真相源
- 各 surface 只是操作 session
- 渠道不是 session owner

详见 [`P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`](./P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md)。

## 3. 仓库结构

```text
src/mini_agent/                 核心运行时、TUI、CLI、命令、memory、models
src/apps/agent_studio_gateway/  Gateway / API Host
src/apps/qqbot_channel/         可选 QQ bot 渠道应用
scripts/                        冒烟、走查、发布、维护脚本
tests/                          自动化测试
docs/                           活跃文档与历史归档
workspace/                      本地运行产物、冒烟输出、缓存
```

说明：

- 内置 skills 位于 [`../src/mini_agent/skills`](../src/mini_agent/skills)
- 项目采用 `src/` 布局，不应再写成旧的 `mini_agent/` 根布局
- 旧的 `git submodule` skills 初始化流程不再是当前仓库事实

## 4. 本地环境准备

### 必需

```bash
uv sync
```

### 供应商密钥

预设供应商读取以下官方环境变量：

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `MINIMAX_API_KEY`

本地回退文件：

- `.env.local`

模板文件：

- `.env.local.example`
- 该文件只作参考，不参与程序加载

### 可选渠道依赖

如果要使用 QQ 渠道应用，需要安装其 Node.js 依赖：

```bash
cd src/apps/qqbot_channel
npm install
```

## 5. 主要命令入口

统一终端入口：

```bash
uv run mini
uv run mini-agent
```

常用模式：

```bash
uv run mini-agent --mode tui
uv run mini-agent --mode cli
uv run mini-agent --prompt "hello"
```

Gateway / 渠道流程：

```bash
uv run mini-agent serve --port 8008
uv run mini-agent stack up
uv run mini qq
```

供应商与模型管理：

```bash
uv run mini-agent provider list
uv run mini-agent provider add --help
uv run mini-agent models --list-presets
uv run mini-agent models minimax --latest
```

诊断命令：

```bash
uv run mini-agent doctor
uv run mini-agent security-audit
```

## 6. 供应商与模型

### 预设供应商

预设供应商由环境变量或 `.env.local` 激活，
不是通过 git submodule，也不是通过外部 skills 仓库接入。

### 自定义供应商

自定义供应商持久化到：

- `~/.mini-agent/providers.json`

它们通过统一模型注册表进入 TUI / CLI / gateway。

## 7. Skills 与 MCP

### Skills

内置 skills 已经随仓库打包：

- [`../src/mini_agent/skills`](../src/mini_agent/skills)
- [`../src/mini_agent/skills/README.md`](../src/mini_agent/skills/README.md)

不要再把它写成“通过 git submodule 初始化 Claude Skills”。
这已经属于历史文档漂移。

### MCP

MCP 通过统一运行时和命令面接入。
某次本地运行到底启用了哪些 MCP server，取决于本地 MCP 配置与依赖安装情况。

## 8. 测试

常用命令：

```bash
uv run pytest
uv run pytest tests/test_markdown_links.py -q
uv run pytest tests/test_command_execution_service.py -q
```

规范：

- 正式测试放在 `tests/`
- 可执行走查 / 冒烟 runner 放在 `scripts/`
- 不要把一次性的本地探针留在仓库根目录

## 9. 仓库卫生规则

- 历史文档移入 `docs/archive/`
- 活跃文档保留在 `docs/`
- 测试归 `tests/`
- 可复用脚本归 `scripts/`
- 定期清理被忽略但实际堆积的探针文件和缓存目录
- 文档中不要把“参考项目”写成“运行依赖”

## 10. 相关文档

- [`./DEVELOPMENT_INDEX.md`](./DEVELOPMENT_INDEX.md)
- [`./DOCS_INDEX.md`](./DOCS_INDEX.md)
- [`./P28_BUILTIN_SKILL_REALIGNMENT_PLAN.md`](./P28_BUILTIN_SKILL_REALIGNMENT_PLAN.md)
- [`./P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md`](./P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md)
- [`./P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`](./P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md)
