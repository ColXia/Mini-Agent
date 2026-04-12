# Mini-Agent 项目目录结构

> **最后更新**: 2026-04-06
> **布局**: 标准 src 布局

---

## 📁 目录结构概览

```
Mini-Agent/
├── src/                          # 源代码目录（标准 src 布局）
│   ├── mini_agent/              # 核心库
│   │   ├── agent.py            # Agent 核心实现
│   │   ├── cli.py              # 统一 CLI 入口
│   │   ├── cli_interactive.py  # 交互式会话
│   │   ├── config.py           # 配置管理
│   │   ├── logger.py           # 日志模块
│   │   ├── retry.py            # 重试机制
│   │   │
│   │   ├── core/               # 核心模块
│   │   │   └── session.py      # 会话管理
│   │   │
│   │   ├── memory/             # 记忆核心（P12）
│   │   │   ├── engram.py
│   │   │   ├── memoria_engine.py
│   │   │   ├── memory_files.py
│   │   │   ├── session_search.py
│   │   │   ├── consolidation.py
│   │   │   ├── relevance.py
│   │   │   └── user_modeling.py
│   │   │
│   │   ├── model_manager/      # 模型管理（P13）
│   │   │   ├── provider.py
│   │   │   ├── model_mapper.py
│   │   │   ├── runtime.py
│   │   │   ├── circuit_breaker.py
│   │   │   ├── health_monitor.py
│   │   │   ├── failover.py
│   │   │   ├── error_classifier.py
│   │   │   └── rectifier.py
│   │   │
│   │   ├── code_agent/         # 编程代理（P14）
│   │   │   ├── agent_loop.py
│   │   │   ├── context.py
│   │   │   ├── scheduler.py
│   │   │   ├── coordinator.py
│   │   │   ├── sandbox/
│   │   │   ├── tools/
│   │   │   ├── permissions/
│   │   │   └── mcp_client.py
│   │   │
│   │   ├── agent_core/         # 智能体核心（P15）
│   │   │   ├── routing.py
│   │   │   ├── delegation.py
│   │   │   ├── skills/
│   │   │   ├── cron/
│   │   │   ├── session/
│   │   │   ├── browser/
│   │   │   └── security/
│   │   │
│   │   ├── tools/              # 工具集
│   │   │   ├── bash_tool.py
│   │   │   ├── file_tools.py
│   │   │   ├── note_tool.py
│   │   │   ├── user_modeling.py
│   │   │   ├── docling_parse.py
│   │   │   ├── knowledge_base.py
│   │   │   ├── web_search.py
│   │   │   └── mcp/
│   │   │
│   │   ├── llm/                # LLM 客户端
│   │   │   ├── openai_client.py
│   │   │   ├── anthropic_client.py
│   │   │   └── gemini_client.py
│   │   │
│   │   ├── runtime/            # 运行时
│   │   │   ├── tooling.py
│   │   │   └── main_agent_runtime_manager.py
│   │   │
│   │   ├── session/            # 会话管理
│   │   │   ├── persistence.py
│   │   │   └── state.py
│   │   │
│   │   ├── application/        # 应用层
│   │   │   ├── main_agent_gateway_use_cases.py
│   │   │   ├── studio_ops_use_cases.py
│   │   │   └── novel_service_use_cases.py
│   │   │
│   │   ├── interfaces/         # 接口层
│   │   │   ├── agent.py
│   │   │   ├── novel.py
│   │   │   ├── channel.py
│   │   │   ├── system.py
│   │   │   └── ops.py
│   │   │
│   │   ├── launcher/           # 启动器
│   │   ├── config/             # 配置文件
│   │   ├── schema/             # 数据模型
│   │   ├── security/           # 安全模块
│   │   ├── plugins/            # 插件系统
│   │   ├── skills/             # 技能库
│   │   ├── dev/                # 开发工具
│   │   ├── ops/                # 运维工具
│   │   └── utils/              # 工具函数
│   │
│   ├── gateway/                # Gateway 核心
│   │   ├── core/               # 核心功能
│   │   ├── routers/            # API 路由
│   │   └── security/           # 安全策略
│   │
│   ├── apps/                   # 应用
│   │   └── agent_studio_gateway/
│   │
│   ├── channels/               # 渠道实现
│   │   ├── qqbot/
│   │   └── wechat/
│   │
│   └── subprograms/            # 子程序
│       ├── novel_generator/
│       ├── document_parser/
│       ├── knowledge_base/
│       └── memory_manager/
│
├── tests/                      # 测试代码
│   ├── test_*.py
│   └── ...
│
├── docs/                       # 文档
│   ├── DOCS_INDEX.md          # 文档索引
│   ├── DEVELOPMENT_GUIDE_CN.md
│   ├── PRODUCTION_GUIDE_CN.md
│   ├── REFACTOR_TASKS.md
│   ├── TRANSFORMATION_PLAN.md
│   └── archive/               # 历史文档
│
├── scripts/                    # 脚本
│   └── test_stable.py
│
├── examples/                   # 示例
│
├── workspace/                  # 工作区
│
├── third_party/               # 第三方代码
│
├── README.md                  # 项目介绍
├── TASKS.md                   # 开发任务表
├── HABITS.md                  # 开发习惯文档
├── LICENSE                    # 许可证
├── pyproject.toml             # 项目配置
├── MANIFEST.in                # 打包清单
└── uv.lock                    # 依赖锁定
```

---

## 🎯 目录职责

### src/ - 源代码目录
采用标准 src 布局，所有源代码都在 `src/` 目录下：
- **mini_agent/** - 核心库，包含所有核心功能模块
- **gateway/** - Gateway 服务
- **apps/** - 应用程序
- **channels/** - 消息渠道（QQ/WeChat）
- **subprograms/** - 子程序服务

### tests/ - 测试代码
所有测试代码独立于源代码，便于：
- 清晰的代码组织
- 独立的测试运行
- 更好的项目结构

### docs/ - 文档
所有项目文档集中管理：
- 用户文档
- 开发文档
- API 文档
- 历史文档归档

### scripts/ - 脚本
开发和部署脚本：
- 测试脚本
- 构建脚本
- 部署脚本

### workspace/ - 工作区
运行时工作目录：
- 会话数据
- 日志文件
- 缓存文件

---

## 📦 核心模块说明

### mini_agent/core/
核心模块，包含会话管理等基础功能。

### mini_agent/memory/ (P12)
记忆核心模块，实现：
- Memoria 引擎（STM/LTM）
- 会话搜索（FTS5）
- 用户建模
- 两阶段记忆巩固

### mini_agent/model_manager/ (P13)
模型管理模块，实现：
- Provider 配置
- 模型映射和路由
- 熔断器
- 健康监控
- 故障转移
- 请求整流

### mini_agent/code_agent/ (P14)
编程代理模块，实现：
- Agent 事件循环
- Windows 沙箱
- 声明式工具系统
- 多 Agent 协调器
- 上下文管理
- MCP 客户端
- 权限系统

### mini_agent/agent_core/ (P15)
智能体核心模块，实现：
- 8 级路由
- 技能平台
- 定时任务
- 浏览器控制
- DM 配对安全
- 会话管理
- 子 Agent 委托

### mini_agent/tools/
工具集，包含：
- 文件操作
- Bash 执行
- MCP 工具
- Skills
- 文档解析（Docling）
- 知识库（MaxKB）
- 网页搜索

### mini_agent/llm/
LLM 客户端，支持：
- OpenAI
- Anthropic
- Gemini
- MiniMax

---

## 🔧 配置文件

### pyproject.toml
项目配置文件，定义：
- 项目元数据
- 依赖关系
- 构建配置
- 测试配置
- 包发现规则（src 布局）

### MANIFEST.in
打包清单，指定打包时包含的额外文件。

### uv.lock
依赖锁定文件，确保依赖版本一致性。

---

## 📚 相关文档

- [README.md](../README.md) - 项目介绍
- [TASKS.md](../TASKS.md) - 开发任务表
- [HABITS.md](../HABITS.md) - 开发习惯文档
- [DOCS_INDEX.md](DOCS_INDEX.md) - 文档索引

---

**维护者**: Mini-Agent Core Team
**布局标准**: Python src Layout (PEP 517/518)
