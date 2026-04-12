# Mini-Agent 深度改造方案书 v2

> **状态**: ✅ 活跃
> **创建日期**: 2026-04-05
> **最后更新**: 2026-04-06
> **当前阶段**: P0-P5 已完成
> **文档索引**: [DOCS_INDEX.md](./DOCS_INDEX.md)

---

## 一、项目概述

### 1.1 改造目标

将 Mini-Agent 从"单一 MiniMax 模型 Agent"升级为"多模型、多渠道、具备自学习能力和企业级编程代理的 AI 智能体中枢平台"，深度融合以下开源项目的核心能力：

| 来源项目 | 提取核心能力 | 融合定位 |
|---------|------------|---------|
| **Memoria** | STM/LTM 类人记忆引擎 | 记忆底层引擎 |
| **Codex** | Agent 事件循环、Windows 沙箱、两阶段记忆巩固 | 编程代理基础 |
| **Gemini CLI** | DeclarativeTool、MCP 完整客户端、GEMINI.md 层次记忆 | 工具系统 + 记忆文件 |
| **Hermes Agent** | 自学习技能、FTS5 会话搜索、子 Agent 委托、冻结快照 | 智能学习 + 检索 |
| **OpenClaw** | 8 级路由、技能平台、定时任务、浏览器控制、DM 配对 | 智能体核心 |
| **CC Switch** | 自定义 Provider、代理路由、熔断器、健康检查、请求整流 | 模型管理层 |
| **extracted-src** | Coordinator 协调器、多层权限、插件系统、相关性记忆检索 | 企业级编程代理增强 |

### 1.2 裁剪决策

| 裁剪项 | 原因 |
|--------|------|
| 50+ Provider 预设 | 改为 CC Switch 自定义配置模式，用户提供 URL+密钥 |
| 成本计算 | 无太多实际价值 |
| macOS/Linux 沙箱 | 仅保留 Windows Restricted Token 沙箱 |
| 多平台消息适配 | 仅 Windows 环境，不需要 Telegram/Discord/Slack |
| 特征标志/遥测/会话回放 | 企业级标准，增加开发成本 |
| 语音转录 | 需要 STT 模型，有额外成本 |

### 1.3 用户交互层

| 入口 | 说明 |
|------|------|
| **Open WebUI** | 主 Web 界面，增强集成 |
| **CLI 终端** | 交互式终端 + 单次任务模式 |
| **QQ / 微信** | 消息渠道接入 |

---

## 二、整体架构设计

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          用 户 交 互 层                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │   Open WebUI     │  │   CLI 终 端      │  │   QQ Bot / WeChat    │  │
│  │  (增强集成前端)   │  │ (交互式+单次任务) │  │   (消息渠道)          │  │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────┬───────────┘  │
│           └─────────────────────┼───────────────────────┘              │
│                                 │ HTTP / WebSocket                     │
├─────────────────────────────────┼───────────────────────────────────────┤
│                     Mini-Agent Gateway (核心网关)                        │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │   API 路由层      │  │   会话管理器      │  │   安全策略引擎        │  │
│  │  FastAPI Routers │  │  Session Manager │  │   Security Policy    │  │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────┬───────────┘  │
│           └─────────────────────┼───────────────────────┘              │
├─────────────────────────────────┼───────────────────────────────────────┤
│                         核 心 服 务 层                                   │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    Agent Core (智能体核心)                        │  │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐  │  │
│  │  │ 8级路由分发 │ │ 技能平台   │ │ 定时任务   │ │ 浏览器控制   │  │  │
│  │  │ (OpenClaw) │ │(OpenClaw+  │ │(OpenClaw+  │ │ (OpenClaw    │  │  │
│  │  │            │ │ Hermes)    │ │ Hermes)    │ │  CDP)        │  │  │
│  │  └────────────┘ └────────────┘ └────────────┘ └──────────────┘  │  │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐  │  │
│  │  │ DM配对安全  │ │ 会话管理   │ │ 子Agent    │ │ 用户画像     │  │  │
│  │  │ (OpenClaw) │ │(OpenClaw+  │ │ 委托       │ │ (Hermes      │  │  │
│  │  │            │ │ Hermes)    │ │ (Hermes)   │ │  Honcho)     │  │  │
│  │  └────────────┘ └────────────┘ └────────────┘ └──────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                   Memory Core (记忆核心)                          │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │  记忆接口层: MemoryTool自保存 | FTS5会话搜索 | 用户画像     │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │  记忆文件层: GEMINI.md层次文件 | MEMORY.md索引 | 每日日志   │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │  Memoria引擎: Working→STM→LTM | 寿命衰减 | 关联图DFS检索    │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │  后台巩固: Phase1并行提取 | Phase2全局consolidation         │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                 Model Manager (模型管理)                          │  │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐  │  │
│  │  │ 自定义     │ │ 代理路由   │ │ 熔断器     │ │ 健康检查     │  │  │
│  │  │ Provider   │ │ (CC Switch)│ │(三态热更新)│ │(失败计数)    │  │  │
│  │  └────────────┘ └────────────┘ └────────────┘ └──────────────┘  │  │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐                   │  │
│  │  │ 请求整流   │ │ 模型映射   │ │ 故障转移   │                   │  │
│  │  │(thinking/  │ │(请求模型→  │ │(错误分类+  │                   │  │
│  │  │ cache)     │ │ 实际模型)  │ │ 自动切换)  │                   │  │
│  │  └────────────┘ └────────────┘ └────────────┘                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                  Code Agent (编程代理)                            │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │  AgentLoop: Codex事件循环 + Gemini Scheduler状态机          │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │  工具层: DeclarativeTool(Gemini) + 40+属性Tool(extracted)   │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │  沙箱层: Windows Restricted Token 沙箱 (Codex)              │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │  多Agent协调: Coordinator模式 + 深度/并发限制 + 凭证路由    │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │  上下文管理: 反向Token预算 + 三层压缩 + 工具输出遮蔽        │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │  MCP客户端: 完整OAuth + 三传输 + 通知 (Gemini)              │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
├─────────────────────────────────┬───────────────────────────────────────┤
│                         工 具 与 渠 道 层                                │
│  ┌─────────────────────┐  ┌─────────────────────────────────────────┐  │
│  │    内置工具集        │  │              渠 道 层                     │  │
│  │  • 文件操作         │  │  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  • Bash执行         │  │  │   QQ Bot     │  │    WeChat        │  │  │
│  │  • MCP工具          │  │  │  (Node.js)   │  │   (预留实现)      │  │  │
│  │  • Skills           │  │  └──────────────┘  └──────────────────┘  │  │
│  │  • 文档解析(Docling) │  └─────────────────────────────────────────┘  │
│  │  • 知识库(MaxKB)    │                                                 │
│  │  • 网页搜索         │                                                 │
│  └─────────────────────┘                                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流图

```
用户请求
  │
  ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Open WebUI │     │   CLI 终端  │     │  QQ/WeChat  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │ HTTP/WebSocket
                           ▼
                  ┌────────────────┐
                  │  Gateway 网关   │
                  │  FastAPI Server│
                  └───────┬────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │ 会话管理  │ │ 安全策略  │ │ 路由分发  │
       └─────┬────┘ └─────┬────┘ └─────┬────┘
             │            │            │
             └────────────┼────────────┘
                          │
              ┌───────────▼───────────┐
              │    Agent Core         │
              │  (智能体核心循环)      │
              └───────────┬───────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │ Memory   │ │ Model    │ │ Skills   │
       │ Core     │ │ Manager  │ │ Platform │
       └─────┬────┘ └─────┬────┘ └─────┬────┘
             │            │            │
             │      ┌─────┴─────┐      │
             │      ▼           ▼      │
             │  Provider    Circuit    │
             │  (用户配置)  Breaker    │
             │                        │
             │            ┌───────────┤
             │            ▼           │
             │     ┌──────────┐       │
             │     │ LLM API  │       │
             │     │ 调用     │       │
             │     └──────────┘       │
             │                        │
             │    ┌───────────────────┤
             │    ▼                   │
             │ ┌──────────┐           │
             │ │Code Agent│ (编程任务) │
             │ │(可选)    │           │
             │ └──────────┘           │
             │                        │
             └────────────┬───────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  工具执行     │
                   │ (文件/Bash/  │
                   │  MCP/Skills) │
                   └──────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  响应返回     │
                   │ (流式/SSE)   │
                   └──────────────┘
```

---

## 三、逻辑设计

### 3.1 请求处理流程

```
1. 用户发起请求 (WebUI / CLI / QQ / WeChat)
   │
2. Gateway 接收请求，进行认证和限流
   │
3. 会话管理器解析 Session Key
   │  ├── 新建会话 → 生成 Session Key
   │  └── 已有会话 → 加载会话历史
   │
4. 路由分发器确定处理 Agent
   │  ├── 根据渠道 + 用户 + 群组 → 匹配绑定规则
   │  └── 8级优先级: peer → parent → wildcard → guild → roles → team → account → channel → default
   │
5. 加载记忆上下文
   │  ├── 从 GEMINI.md 层次文件加载项目/全局记忆
   │  ├── 从 MEMORY.md 加载活跃记忆索引
   │  ├── Memoria 引擎检索 STM + LTM
   │  ├── FTS5 搜索相关历史会话
   │  └── 加载用户画像 (Honcho)
   │
6. 模型管理器选择 Provider
   │  ├── 检查熔断器状态
   │  ├── 按优先级选择可用 Provider
   │  ├── 应用请求整流 (thinking signature / cache injection)
   │  └── 模型映射 (用户请求模型 → Provider 实际模型)
   │
7. Agent Core 执行 Agent Loop
   │  ├── 构建系统提示 (记忆 + 技能 + 上下文)
   │  ├── 调用 LLM
   │  ├── 解析工具调用
   │  ├── 执行工具 (权限检查 → 沙箱 → 执行)
   │  ├── 循环直到完成
   │  └── 更新记忆 (冻结快照模式)
   │
8. 响应返回
   │  ├── SSE 流式响应
   │  ├── 更新会话历史
   │  └── 触发后台记忆巩固 (如需要)
```

### 3.2 记忆系统逻辑

#### 记忆写入流程

```
Agent 调用 MemoryTool.save()
     │
     ▼
┌──────────────┐     ┌──────────────┐
│ 安全扫描      │────▶│ 写入主题文件  │
│(注入检测)     │     │ topics/xxx.md│
└──────────────┘     └──────┬───────┘
                            │
                            ▼
                     ┌──────────────┐
                     │ 更新         │
                     │ MEMORY.md    │
                     │ 索引(≤200行) │
                     └──────┬───────┘
                            │
                            ▼
                     ┌──────────────┐
                     │ 追加到       │
                     │ 每日日志     │
                     │ daily/       │
                     └──────────────┘
```

#### 记忆检索流程

```
Agent 需要上下文
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. JIT 发现 GEMINI.md 层次文件 (从当前路径向上遍历)          │
│ 2. 加载 MEMORY.md 活跃记忆索引                               │
│ 3. 相关性检索: 侧查询选择 top-5 相关记忆                     │
│ 4. Memoria 引擎: STM 相似度 + LTM DFS 关联检索              │
│ 5. FTS5 搜索历史会话 (可选 LLM 摘要)                         │
│ 6. 合并去重，注入系统提示                                    │
└─────────────────────────────────────────────────────────────┘
```

#### 后台巩固流程 (Codex 风格)

```
定时触发 / 会话结束时触发
     │
     ▼
Phase 1: 并行提取 (并发 ≤ 8)
├── 获取待处理会话 (租约机制, 3600s)
├── 使用轻量模型提取结构化记忆
├── 输出: raw_memory + rollout_summary + slug
└── 写入 raw_memories.md + rollout_summaries/
     │
     ▼
Phase 2: 全局 Consolidation (单实例)
├── 加载 top-N Stage 1 输出 (按使用次数+时间排序)
├── 计算选择 diff (added/retained/removed)
├── 使用强模型生成高层次记忆
├── 更新水位线，防止重复处理
└── 合并到 MEMORY.md 和主题文件
```

### 3.3 模型管理逻辑

#### Provider 配置管理

```
用户添加 Provider (CLI / WebUI / YAML)
     │
     ▼
┌─────────────────────────────────────────────────────┐
│  Provider {                                         │
│    id: "my-llm"                                     │
│    name: "我的模型"                                  │
│    api_type: "openai" | "anthropic" | "gemini"      │
│    api_base: "http://..."    ← 用户填写              │
│    api_key: "sk-..."         ← 用户填写              │
│    models: ["model-a", "model-b"]                    │
│    enabled: true                                     │
│    priority: 1                                       │
│    headers: {}                                       │
│    timeout: 60                                       │
│  }                                                  │
└─────────────────────────────────────────────────────┘
     │
     ▼
持久化到 SQLite / config.yaml
```

#### 请求代理流程

```
Agent 发起 LLM 请求
     │
     ▼
┌─────────────────────────────────────────────────────┐
│  1. 模型映射: 请求模型 → 匹配 Provider 可用模型      │
│  2. 按优先级排序可用 Provider                        │
│  3. 遍历 Provider 列表:                              │
│     ├── 检查熔断器状态                               │
│     │   ├── Closed → 正常发送                        │
│     │   ├── Open → 跳过, 尝试下一个                  │
│     │   └── HalfOpen → 允许探测请求                  │
│     ├── 应用请求整流 (thinking / cache)              │
│     ├── 发送请求                                     │
│     ├── 成功 → 更新熔断器 (success++)                │
│     └── 失败 → 分类错误类型                          │
│         ├── 可重试 → 尝试下一个 Provider             │
│         ├── 不可重试 → 直接返回错误                  │
│         └── 客户端中止 → 停止重试                    │
│  4. 所有 Provider 失败 → 返回聚合错误                │
└─────────────────────────────────────────────────────┘
```

#### 熔断器状态机

```
         ┌─────────┐
         │ Closed  │ ◀──── 成功达到 success_threshold
         │ (正常)  │
         └────┬────┘
              │ 失败达到 failure_threshold
              ▼
         ┌─────────┐
         │  Open   │ ──── timeout_seconds 后 ──→ HalfOpen
         │ (拒绝)  │
         └─────────┘
              │
              ▼
         ┌─────────┐
         │HalfOpen │ ── 失败 → Open
         │ (探测)  │ ── 成功 → Closed
         └─────────┘

配置项 (可热更新):
- failure_threshold: 4
- success_threshold: 2
- timeout_seconds: 60
- error_rate_threshold: 0.6
- min_requests: 10
```

### 3.4 编程代理逻辑

#### Agent Loop (Codex + Gemini)

```
┌─────────────────────────────────────────────────────┐
│  Submission Loop (Codex 事件通道)                    │
│  ├── UserInput → 创建 TurnContext                    │
│  ├── Interrupt → 中断当前执行                        │
│  ├── ExecApproval → 沙箱审批                         │
│  ├── Compact → 上下文压缩                            │
│  └── DropMemories → 丢弃记忆                         │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│  Scheduler 状态机 (Gemini)                           │
│  Validating → Scheduled → Executing → Completed     │
│                                       ↘ Errored     │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│  Turn 执行循环                                       │
│  1. 构建上下文 (记忆 + 技能 + 历史)                  │
│  2. 调用 LLM (通过 Model Manager)                    │
│  3. 流式解析响应                                     │
│  4. 检测工具调用                                     │
│     ├── 无工具调用 → 返回结果                        │
│     └── 有工具调用 → 执行工具层                      │
│  5. 工具执行:                                        │
│     ├── 权限检查 (多层权限)                           │
│     ├── 沙箱封装 (Windows Restricted Token)          │
│     ├── 执行 + 超时控制                              │
│     └── 结果返回 / 审批升级                          │
│  6. 结果注入上下文, 继续循环                          │
│  7. 检查终止条件 (max_turns / token_budget)          │
└─────────────────────────────────────────────────────┘
```

#### 工具系统 (DeclarativeTool)

```
ToolBuilder<TParams, TResult>
├── name: 工具名称
├── description: 工具描述
├── schema: JSON Schema (参数验证)
├── kind: Read | Edit | Delete | Execute | ...
├── isReadOnly: 是否只读 (决定并行策略)
└── build(params) → ToolInvocation

ToolInvocation
├── validate() → 参数验证
├── shouldConfirmExecute() → 是否需要用户确认
├── toolLocations() → 影响的文件位置
└── execute() → 执行结果

扩展属性 (extracted-src 40+):
├── isConcurrencySafe()
├── isDestructive()
├── interruptBehavior()
├── maxResultSizeChars
├── renderToolUseMessage()
└── shouldDefer / alwaysLoad (懒加载)
```

#### 多 Agent 协调 (Coordinator)

```
Coordinator 模式: Research → Synthesis → Implementation

1. 用户请求复杂任务
     │
     ▼
2. Coordinator Agent 分析任务
     │
     ▼
3. Research 阶段: 并行生成 Worker
   ├── Worker 1: 调研 A 方面
   ├── Worker 2: 调研 B 方面
   └── Worker 3: 调研 C 方面
     │ (深度限制=2, 并发限制=3)
     ▼
4. Synthesis 阶段: Coordinator 综合调研结果
   └── 生成实现规格说明书
     │
     ▼
5. Implementation 阶段: Worker 执行实现
   ├── Worker 1: 实现模块 A
   └── Worker 2: 实现模块 B
     │
     ▼
6. Verification 阶段: Worker 验证结果
     │
     ▼
7. 返回最终结果给用户

子 Agent 隔离:
- 独立会话, 无父级历史
- 受限工具集 (禁止 delegate/clarify/memory/send_message)
- 独立凭证路由 (可使用不同 Provider)
- 进度回调 (父级可见子级活动)
```

### 3.5 技能平台逻辑

```
技能来源:
├── 内置技能 (bundled/)
├── 工作区技能 (~/.mini-agent/workspace/skills/)
├── 插件技能 (已安装插件)
└── 远程注册表 (ClawHub 风格)

技能定义 (SKILL.md):
┌─────────────────────────────────────────────────────┐
│  ---                                                │
│  name: github                                       │
│  description: Interact with GitHub repositories     │
│  always: false                                      │
│  skillKey: GITHUB                                   │
│  requires:                                          │
│    bins: [gh]                                       │
│    env: [GITHUB_TOKEN]                              │
│  ---                                                │
│                                                     │
│  # Instructions...                                  │
└─────────────────────────────────────────────────────┘

渐进式披露 (3 级):
├── Tier 1: 技能列表 (仅元数据, 注入系统提示)
├── Tier 2: 完整指令 (Agent 按需加载)
└── Tier 3: 辅助文件 (references/, templates/, scripts/)

自学习技能 (Hermes):
├── 触发条件: 复杂任务成功(5+调用) / 克服错误 / 用户纠正
├── skill_manage 工具: create / patch / edit / delete
├── 模糊匹配补丁 (避免精确匹配失败)
└── 安全扫描 (注入检测, 失败回滚)

资格检查:
├── OS 兼容性
├── 二进制可用性 (hasBinary)
├── 环境变量存在性
└── Agent 级别白名单
```

### 3.6 定时任务逻辑

```
调度类型:
├── at: 一次性指定时间
├── every: 固定间隔 (带锚点)
└── cron: 标准 cron 表达式 (带时区, 可选抖动)

会话目标:
├── main: 在主会话中运行
├── isolated: 在独立会话中运行 (默认)
├── current: 在创建任务的会话中运行
└── session:{key}: 在指定会话中运行

负载类型:
├── systemEvent: 注入系统事件文本
└── agentTurn: 触发完整 Agent 轮次
    ├── message: 提示消息
    ├── model_override: 模型覆盖
    ├── thinking_level: 思考级别
    ├── timeout: 超时时间
    ├── tool_allowlist: 工具白名单
    └── light_context: 轻量上下文模式

传递路由:
├── none: 静默执行
├── announce: 通过消息渠道传递
├── webhook: HTTP POST 到指定 URL
└── [SILENT] 标记: Agent 响应 [SILENT] 时不传递

崩溃恢复:
├── advance_next_run() 在执行前推进下次运行时间
├── 快速前进逻辑: 错过执行时跳到下次, 不堆积
└── 宽限期: 错过时间在宽限期内则补执行
```

---

## 四、改造任务清单

### 阶段总览

| 阶段 | 任务数 | 预计周期 | 优先级 |
|------|--------|---------|--------|
| P0: 记忆核心 | 7 | 2-3 周 | 最高 |
| P1: 模型管理 | 6 | 1-2 周 | 高 |
| P2: 编程代理 | 7 | 2-3 周 | 高 |
| P3: 智能体核心 | 7 | 2-3 周 | 中 |
| P4: 工具与子程序 | 4 | 1-2 周 | 中 |
| P5: 前端与集成 | 3 | 1-2 周 | 中 |

---

### P0: 记忆核心 (2-3 周)

#### T0.1 Memoria STM/LTM 引擎

**目标**: 移植 Memoria 的 Working→STM→LTM 记忆生命周期管理

**实现内容**:

1. **Engram 数据结构** (`mini_agent/memory/engram.py`)
   - 定义 Engram 类型: NULL / WORKING / SHORTTERM / LONGTERM
   - 数据字段: `data` (tensor), `induce_counts` (共现矩阵), `engram_types`, `lifespan`, `age`, `engram_ids`
   - 文本适配: 将 tensor 改为文本嵌入向量 (使用 sentence-transformers)

2. **Memoria 核心类** (`mini_agent/memory/memoria_engine.py`)
   - `add_working_memory(text_embedding)`: 添加工作记忆
   - `remind()`: 检索 STM + LTM
     - STM: 余弦相似度 top-K 检索
     - LTM: 基于共现矩阵的 DFS 关联检索
   - `adjust_lifespan_and_memories(indices, lifespan_delta)`: 寿命调整
   - `fire_together_wire_together()`: 关联强化
   - 参数: `num_reminded_stm=4`, `stm_capacity=16`, `ltm_search_depth=5`, `initial_lifespan=3`

3. **文本嵌入适配器** (`mini_agent/memory/embedder.py`)
   - 使用本地 sentence-transformers 模型
   - 提供 `encode(text) → vector` 和 `decode(vector) → text` 接口
   - 支持批量编码

4. **持久化** (`mini_agent/memory/persistence.py`)
   - Engram 状态序列化/反序列化
   - SQLite 存储 (engram 数据 + 共现矩阵稀疏表示)
   - 会话间加载/保存

#### T0.2 GEMINI.md 层次文件系统

**目标**: 实现 Gemini CLI 风格的层次化记忆文件系统

**实现内容**:

1. **文件发现** (`mini_agent/memory/memory_files.py`)
   - 多级作用域: `~/.mini-agent/memory/GEMINI.md` (全局) → `./GEMINI.md` (项目) → `src/GEMINI.md` (子目录)
   - JIT 上下文发现: Agent 访问路径时向上遍历查找 GEMINI.md
   - `@import` 语法支持: 记忆文件组合引用

2. **MEMORY.md 索引** (`mini_agent/memory/memory_index.py`)
   - 活跃记忆索引, 最大 200 行 / 25KB
   - 四类记忆: user / feedback / project / reference
   - 指针模式: 写入主题文件 → 添加指针到索引

3. **每日日志** (`mini_agent/memory/daily_log.py`)
   - Append-only 日志: `daily/YYYY-MM-DD.md`
   - 夜间蒸馏: 定时将当日日志蒸馏到 MEMORY.md
   - 日志压缩: 去除冗余, 保留关键信息

#### T0.3 MemoryTool 自保存工具

**目标**: 实现 Agent 可自主保存和检索记忆的工具

**实现内容**:

1. **工具定义** (`mini_agent/tools/memory_tool.py`)
   - `save(scope, topic, content)`: 保存记忆
     - scope: `global` | `project` | `user` | `feedback` | `reference`
     - 安全扫描: 注入检测、不可见 Unicode 检测
   - `recall(query, limit=5)`: 检索记忆
   - `delete(topic)`: 删除记忆
   - `list()`: 列出所有记忆主题

2. **冻结快照模式** (Hermes)
   - 会话启动时加载记忆快照到系统提示
   - 会话中写入不刷新系统提示 (保持 prompt cache)
   - 下次会话启动时加载最新快照

#### T0.4 FTS5 会话搜索

**目标**: 实现 Hermes 风格的 SQLite FTS5 全文搜索 + LLM 摘要

**实现内容**:

1. **数据库 schema** (`mini_agent/memory/session_db.py`)
   - `sessions` 表: 元数据 (标题、token 数、成本、时间戳)
   - `messages` 表: 完整对话内容
   - `messages_fts` 表: FTS5 虚拟表 (自动同步触发器)
   - WAL 模式 + 被动检查点

2. **搜索工具** (`mini_agent/tools/session_search.py`)
   - 双模式:
     - 无查询: 返回最近会话元数据 (零 LLM 成本)
     - 有关键词: FTS5 搜索 → top-N → 截断 → LLM 摘要
   - FTS5 查询清理: 处理特殊字符、引号、布尔操作符
   - 截断算法: 围绕匹配点 100K 字符窗口
   - 并行摘要: `asyncio.gather()` 批量处理

#### T0.5 两阶段记忆巩固

**目标**: 实现 Codex 风格的后台记忆提取和全局巩固

**实现内容**:

1. **Phase 1: 并行提取** (`mini_agent/memory/consolidation_phase1.py`)
   - Job 租约机制 (3600s 租约, 心跳 90s)
   - 并发上限 8
   - 使用轻量模型 (如 gpt-4o-mini) 提取结构化记忆
   - 输出: `raw_memory`, `rollout_summary`, `rollout_slug`

2. **Phase 2: 全局 Consolidation** (`mini_agent/memory/consolidation_phase2.py`)
   - 单实例执行 (全局锁)
   - 加载 top-N Stage 1 输出 (按使用次数 + 时间排序)
   - 计算选择 diff (added / retained / removed)
   - 使用强模型生成高层次记忆
   - 水位线追踪, 防止重复处理

3. **调度器** (`mini_agent/memory/consolidation_scheduler.py`)
   - 触发时机: 会话结束 / 定时 (每 30 分钟)
   - Job 状态管理 (SQLite)
   - 失败重试 (退避 3600s)

#### T0.6 相关性记忆检索

**目标**: 实现 extracted-src 风格的相关性记忆检索

**实现内容**:

1. **相关性评估** (`mini_agent/memory/relevance.py`)
   - 侧查询: 使用轻量模型评估记忆与当前查询的相关性
   - 返回 top-5 最相关记忆
   - 记忆新鲜度: mtime 追踪并展示

2. **记忆漂移校验**
   - 使用前验证记忆内容与当前状态的一致性
   - 标记可能过时的记忆

#### T0.7 用户画像 (Honcho)

**目标**: 实现 Hermes 的方言问答式用户建模

**实现内容**:

1. **MemoryProvider ABC** (`mini_agent/memory/memory_provider.py`)
   - 定义记忆提供者接口
   - 生命周期钩子: `prefetch`, `sync_turn`, `on_session_end`, `on_delegation`

2. **内置记忆提供者** (`mini_agent/memory/builtin_memory.py`)
   - MEMORY.md / USER.md 管理
   - 条目管理: add / replace / remove (子串匹配, 无需 ID)

3. **用户画像工具** (`mini_agent/tools/user_modeling.py`)
   - `profile()`: 获取用户画像
   - `search(query)`: 语义搜索用户信息
   - `conclude(fact)`: 写入用户结论
   - 方言问答: Agent 主动提问以加深用户理解

---

### P1: 模型管理 (1-2 周)

#### T1.1 自定义 Provider 配置

**目标**: 实现 CC Switch 风格的自定义 Provider 管理

**实现内容**:

1. **Provider 模型** (`mini_agent/model_manager/provider.py`)
   ```python
   class Provider:
       id: str
       name: str
       api_type: str  # "openai" | "anthropic" | "gemini" | "custom"
       api_base: str
       api_key: str
       models: list[str]
       enabled: bool = True
       priority: int = 0
       headers: dict = {}
       timeout: int = 60
   ```

2. **Provider 存储** (`mini_agent/model_manager/provider_store.py`)
   - SQLite 持久化
   - CRUD 操作
   - 密钥加密存储

3. **CLI 命令** (`mini_agent/cli.py`)
   - `mini-agent provider add --name "xxx" --url "xxx" --key "xxx" --type "openai"`
   - `mini-agent provider list`
   - `mini-agent provider remove <id>`
   - `mini-agent provider enable/disable <id>`

4. **API 协议接口** (`mini_agent/model_manager/protocol.py`)
   - 定义 OpenAI / Anthropic / Gemini 三种 API 协议适配器
   - 自定义协议扩展点

#### T1.2 代理路由

**目标**: 实现请求代理和模型映射

**实现内容**:

1. **模型映射器** (`mini_agent/model_manager/model_mapper.py`)
   - 请求模型 → Provider 实际模型映射
   - 模糊匹配: 模型名部分匹配
   - 回退策略: 未匹配时使用 Provider 默认模型

2. **请求转发器** (`mini_agent/model_manager/proxy_server.py`)
   - FastAPI HTTP 代理
   - 拦截请求 → 选择 Provider → 转换协议 → 转发
   - SSE 流式响应支持
   - 请求整流: thinking signature / budget / cache injection

3. **协议适配器** (`mini_agent/model_manager/adapters/`)
   - `openai_adapter.py`: OpenAI Chat Completions / Responses API
   - `anthropic_adapter.py`: Anthropic Messages API
   - `gemini_adapter.py`: Google Gemini API
   - `custom_adapter.py`: 自定义协议扩展

#### T1.3 熔断器

**目标**: 实现三态熔断器, 支持热更新

**实现内容**:

1. **熔断器核心** (`mini_agent/model_manager/circuit_breaker.py`)
   - 三态: Closed (正常) / Open (拒绝) / HalfOpen (探测)
   - 状态转换逻辑
   - 配置: `failure_threshold=4`, `success_threshold=2`, `timeout_seconds=60`
   - 热更新: 配置变更不重置状态

2. **统计追踪**
   - 连续失败计数
   - 成功/失败时间戳
   - 错误率计算

#### T1.4 健康检查

**目标**: Provider 健康监控

**实现内容**:

1. **健康监控器** (`mini_agent/model_manager/health_monitor.py`)
   - 连续失败计数 (可配置阈值)
   - 最后成功/失败时间戳
   - 定期健康探测 (可选)

2. **Dashboard API** (`gateway/routers/model_manager.py`)
   - `GET /api/providers`: 列出所有 Provider
   - `GET /api/providers/{id}/health`: 查看健康状态
   - `GET /api/providers/{id}/stats`: 查看统计数据

#### T1.5 故障转移

**目标**: 自动故障转移和错误分类

**实现内容**:

1. **错误分类** (`mini_agent/model_manager/error_classifier.py`)
   - 可重试错误: 超时、5xx、速率限制
   - 不可重试错误: 认证失败、模型不存在
   - 客户端中止: 用户取消

2. **故障转移逻辑** (`mini_agent/model_manager/failover.py`)
   - 按优先级遍历 Provider 列表
   - 检查熔断器状态
   - 去重: 防止并发切换
   - 切换事件通知

#### T1.6 请求整流器

**目标**: 请求优化和协议转换

**实现内容**:

1. **整流器** (`mini_agent/model_manager/rectifier.py`)
   - Thinking 签名处理: 添加/移除 thinking blocks
   - Thinking budget 调整
   - Cache 注入: 为支持 cache 的 Provider 添加 cache control
   - 协议转换: OpenAI ↔ Anthropic ↔ Gemini

---

### P2: 编程代理 (2-3 周)

#### T2.1 Agent 事件循环

**目标**: 融合 Codex 事件循环和 Gemini Scheduler 状态机

**实现内容**:

1. **Submission Loop** (`mini_agent/code_agent/agent_loop.py`)
   - 基于 `asyncio.Queue` 的事件通道
   - 事件类型: UserInput / Interrupt / ExecApproval / Compact / DropMemories
   - TurnContext 快照: 每次请求独立配置

2. **Scheduler 状态机** (`mini_agent/code_agent/scheduler.py`)
   - 状态: Validating → Scheduled → Executing → Completed / Errored
   - 工具调用编排
   - 并行工具执行 (只读工具可并行)

3. **AgentLoopContext** (`mini_agent/code_agent/context.py`)
   - 简洁的执行上下文接口
   - 包含: config, tool_registry, message_bus, llm_client, sandbox_manager

#### T2.2 Windows 沙箱

**目标**: 移植 Codex 的 Windows Restricted Token 沙箱

**实现内容**:

1. **沙箱管理器** (`mini_agent/code_agent/sandbox/manager.py`)
   - `select_initial()`: 选择沙箱类型
   - `transform(command)`: 封装命令为沙箱执行

2. **Windows 沙箱** (`mini_agent/code_agent/sandbox/windows.py`)
   - Restricted Token 创建
   - 文件系统策略: 读写权限路径配置
   - 网络隔离: 域名白名单/黑名单
   - 审批升级: 首次拒绝 → 缓存审批 → 升级权限

3. **网络代理** (`mini_agent/code_agent/sandbox/network.py`)
   - 域名过滤
   - 网络审批模式: Immediate / Deferred

#### T2.3 工具系统

**目标**: Gemini DeclarativeTool + extracted-src 40+ 属性

**实现内容**:

1. **ToolBuilder** (`mini_agent/code_agent/tools/builder.py`)
   ```python
   class ToolBuilder:
       name: str
       description: str
       schema: dict  # JSON Schema
       kind: ToolKind  # Read | Edit | Delete | Execute | ...
       isReadOnly: bool
       build(params) → ToolInvocation
   ```

2. **ToolInvocation** (`mini_agent/code_agent/tools/invocation.py`)
   ```python
   class ToolInvocation:
       validate() → bool
       shouldConfirmExecute() → bool
       toolLocations() → list[str]
       execute() → ToolResult
   ```

3. **扩展属性** (`mini_agent/code_agent/tools/attributes.py`)
   - `isConcurrencySafe()`, `isDestructive()`, `interruptBehavior()`
   - `maxResultSizeChars`, `renderToolUseMessage()`
   - `shouldDefer`, `alwaysLoad` (懒加载)

4. **内置工具**
   - `read_file`, `write_file`, `edit_file`
   - `bash`, `grep`, `glob`, `list_dir`
   - `web_search`, `web_fetch`
   - `agent_spawn` (子 Agent)

#### T2.4 多 Agent 协调

**目标**: extracted-src Coordinator 模式

**实现内容**:

1. **Coordinator** (`mini_agent/code_agent/coordinator.py`)
   - Research → Synthesis → Implementation → Verification 流程
   - Worker 管理: 创建、监控、结果收集

2. **委托工具** (`mini_agent/code_agent/tools/delegate.py`)
   - 隔离子 Agent: 独立会话、受限工具集
   - 深度限制 (MAX_DEPTH=2)
   - 并发限制 (MAX_CONCURRENT=3)
   - 批量并行模式
   - 凭证路由: 子 Agent 可使用不同 Provider

3. **进度回调**
   - 父级可见子级活动
   - `<task-notification>` XML 块通知

#### T2.5 上下文管理

**目标**: Gemini 反向 Token 预算 + extracted-src 三层压缩

**实现内容**:

1. **反向 Token 预算** (`mini_agent/code_agent/context_compression.py`)
   - 从新到旧遍历历史
   - 保留最近工具输出完整内容
   - 截断旧输出为最后 30 行 + 保存到临时文件
   - 分割点尊重用户消息边界

2. **三层压缩** (extracted-src)
   - Snip compaction: 截断超长工具输出
   - Microcompact: 压缩连续对话
   - Auto-compact: 触发 LLM 摘要

3. **工具输出遮蔽** (`mini_agent/code_agent/output_masking.py`)
   - 标记与当前任务无关的工具输出
   - 从上下文中隐藏

#### T2.6 MCP 客户端

**目标**: Gemini 完整 MCP 客户端

**实现内容**:

1. **MCP 客户端** (`mini_agent/code_agent/mcp_client.py`)
   - 三传输: stdio / SSE / StreamableHTTP
   - OAuth 认证: Google / Service Account / 通用 OAuth
   - 工具发现、资源发现、Prompt 发现
   - 通知处理: 工具/资源/Prompt 列表变更
   - 重连和刷新逻辑

2. **MCP 工具包装** (`mini_agent/code_agent/mcp_tools.py`)
   - 将 MCP 工具包装为 DeclarativeTool
   - 确认流程集成

#### T2.7 权限系统

**目标**: extracted-src 多层权限 + Codex 沙箱审批

**实现内容**:

1. **权限策略** (`mini_agent/code_agent/permissions/policy.py`)
   - 三层: always-allow / always-deny / ask
   - 绕过模式 (full-access)
   - 安全分类器: 工具输入自动分类

2. **审批流程** (`mini_agent/code_agent/permissions/approval.py`)
   - 用户审批
   - 缓存审批 (相同命令不重复询问)
   - 沙箱升级审批 (拒绝后提升权限重试)

---

### P3: 智能体核心 (2-3 周)

#### T3.1 8 级路由分发

**目标**: OpenClaw 绑定匹配路由

**实现内容**:

1. **绑定配置** (`mini_agent/agent_core/routing.py`)
   - 8 级优先级: peer → parent → wildcard → guild → roles → team → account → channel → default
   - 绑定规则配置

2. **路由解析器** (`mini_agent/agent_core/route_resolver.py`)
   - `resolve_agent(channel, account_id, peer, ...)` → Agent ID
   - 两级 WeakMap 缓存 (LRU 4000 路由 / 2000 绑定)

3. **会话键系统** (`mini_agent/agent_core/session_key.py`)
   - 格式: `agent:{agentId}:{channel}:{peerKind}:{peerId}`
   - 线程继承: `{baseSessionKey}:thread:{threadId}`

#### T3.2 技能平台

**目标**: OpenClaw + Hermes 技能系统

**实现内容**:

1. **技能加载器** (`mini_agent/agent_core/skills/loader.py`)
   - SKILL.md 解析 (YAML frontmatter)
   - 渐进式披露: Tier 1 元数据 → Tier 2 指令 → Tier 3 辅助文件
   - 来源: 内置 / 工作区 / 插件 / 远程

2. **自学习技能** (`mini_agent/agent_core/skills/self_improve.py`)
   - 触发条件检测
   - skill_manage: create / patch / edit / delete
   - 模糊匹配补丁
   - 安全扫描 + 回滚

3. **资格检查** (`mini_agent/agent_core/skills/eligibility.py`)
   - OS 兼容性 / 二进制可用性 / 环境变量 / 白名单

#### T3.3 定时任务

**目标**: OpenClaw + Hermes 定时任务

**实现内容**:

1. **调度器** (`mini_agent/agent_core/cron/scheduler.py`)
   - 调度类型: at / every / cron
   - 每秒 tick, 文件锁防并发
   - 快速前进逻辑 + 宽限期

2. **隔离执行** (`mini_agent/agent_core/cron/isolated_run.py`)
   - 创建独立 Agent 实例
   - 技能加载支持
   - [SILENT] 标记处理

3. **传递路由** (`mini_agent/agent_core/cron/delivery.py`)
   - none / announce (QQ/WeChat) / webhook
   - 失败通知

#### T3.4 子 Agent 委托

**目标**: Hermes 子 Agent 委托

**实现内容**:

1. **委托工具** (`mini_agent/agent_core/delegation.py`)
   - 隔离子 Agent (独立会话、受限工具集)
   - 深度/并发限制
   - 批量并行
   - 凭证路由

2. **状态管理**
   - 全局状态保存/恢复
   - 进度回调

#### T3.5 会话管理

**目标**: OpenClaw + Hermes 会话管理

**实现内容**:

1. **会话键解析** (`mini_agent/agent_core/session/session_key.py`)
   - 全键/部分键/ID slug 查找
   - 歧义检测

2. **重置策略** (`mini_agent/agent_core/session/lifecycle.py`)
   - daily / idle / both / none
   - 自动创建新会话

3. **会话谱系** (`mini_agent/agent_core/session/lineage.py`)
   - parent_session_id 链
   - 压缩/委托子会话追踪

#### T3.6 浏览器控制

**目标**: OpenClaw 浏览器 CDP 控制

**实现内容**:

1. **Chrome 生命周期** (`mini_agent/agent_core/browser/chrome.py`)
   - 启动/停止/健康检查
   - 用户数据目录隔离

2. **CDP 操作** (`mini_agent/agent_core/browser/cdp.py`)
   - 截图 (全页/视口)
   - DOM 枚举和交互
   - Tab 管理
   - 导航 (SSRF 防护)
   - JS 执行 (可配置)

3. **Agent 工具接口** (`mini_agent/agent_core/browser/tool.py`)
   - `browser_screenshot`, `browser_act`, `browser_navigate`
   - `browser_tabs`, `browser_profiles`

#### T3.7 DM 配对安全

**目标**: OpenClaw DM 配对

**实现内容**:

1. **配对存储** (`mini_agent/agent_core/security/pairing.py`)
   - 8 位字母数字验证码
   - 每渠道 JSON 存储
   - 文件锁 + 读缓存
   - 1 小时过期, 最多 3 个待处理

2. **访问策略** (`mini_agent/agent_core/security/policy.py`)
   - DM 策略: open / disabled / allowlist / pairing
   - 组策略: allowlist / open / disabled
   - 合并 allowFrom (配置 + 配对 + 组)

---

### P4: 工具与子程序 (1-2 周)

#### T4.1 Docling 文档解析集成

**目标**: 集成 Docling 文档解析能力

**实现内容**:

1. **解析工具** (`mini_agent/tools/docling_parse.py`)
   - 支持格式: PDF / DOCX / PPTX / XLSX / HTML / 图片
   - 输出: Markdown / HTML / JSON
   - OCR 支持

2. **子程序** (`subprograms/document_parser/`)
   - manifest.json 配置
   - Gateway 路由: `/api/document-parser`
   - 批量处理支持

#### T4.2 MaxKB 知识库集成

**目标**: 集成内置知识库 RAG 能力

**实现内容**:

1. **查询工具** (`mini_agent/tools/knowledge_base.py`)
   - 原生知识库检索 tool
   - 面向 agent 的显式 grounded retrieval

2. **子程序** (`subprograms/knowledge_base/`)
   - manifest.json 配置
   - Gateway 路由: `/api/knowledge-base`

#### T4.3 网页搜索工具

**目标**: 多引擎网页搜索

**实现内容**:

1. **搜索工具** (`mini_agent/tools/web_search.py`)
   - 多引擎: SearXNG / Google / Brave / DuckDuckGo
   - 结果去重和排序
   - 网页内容提取

#### T4.4 记忆管理子程序

**目标**: 记忆管理专用子程序

**实现内容**:

1. **子程序** (`subprograms/memory_manager/`)
   - manifest.json 配置
   - Gateway 路由: `/api/memory`
   - 记忆浏览/搜索/编辑/导出

---

### P5: 前端与集成 (1-2 周)

#### T5.1 Open WebUI 集成

**目标**: 集成 Open WebUI 作为可选前端

**实现内容**:

1. **适配器** (`apps/open_webui/`)
   - API 兼容层 (OpenAI-compatible)
   - 认证对接
   - 会话同步

2. **部署配置**
   - Docker Compose 配置
   - 环境变量配置

#### T5.2 Agent Studio 增强

**目标**: 增强原有 WebUI

**实现内容**:

1. **Provider 管理界面**
   - 添加/编辑/删除 Provider
   - 健康状态展示

2. **记忆管理界面**
   - 记忆浏览/搜索
   - 每日日志查看

3. **技能管理界面**
   - 技能列表/安装/启用/禁用

#### T5.3 QQ/微信渠道完善

**目标**: 完善 QQ 和微信渠道实现

**实现内容**:

1. **QQ Bot** (`src/mini_agent/channels/qqbot.py`)
   - 消息收发
   - 媒体消息支持
   - 会话键映射

2. **WeChat** (`src/mini_agent/channels/wechat.py`)
   - 实现预留渠道
   - 消息收发
   - 会话键映射

---

## 五、技术栈

| 类别 | 技术选型 |
|------|---------|
| 语言 | Python >= 3.10 |
| 包管理 | uv (Astral) |
| Web 框架 | FastAPI + Uvicorn |
| 数据验证 | Pydantic >= 2.0 |
| 配置管理 | PyYAML + python-dotenv |
| HTTP 客户端 | httpx + requests |
| LLM 协议 | anthropic + openai SDK |
| MCP | mcp >= 1.0 |
| Token 计算 | tiktoken |
| 终端 UI | prompt-toolkit |
| 向量嵌入 | sentence-transformers |
| 全文搜索 | SQLite FTS5 |
| 数据库 | SQLite (WAL 模式) |
| 浏览器控制 | CDP (Chrome DevTools Protocol) |
| 测试 | pytest + pytest-asyncio |
| 前端 | Open WebUI (Svelte) + Agent Studio (React) |

---

## 六、新增依赖

```toml
[project.dependencies]
# 原有依赖
pydantic = ">=2.0.0"
pyyaml = ">=6.0.0"
httpx = ">=0.27.0"
mcp = ">=1.0.0"
requests = ">=2.31.0"
tiktoken = ">=0.5.0"
prompt-toolkit = ">=3.0.0"
anthropic = ">=0.39.0"
openai = ">=1.57.4"
fastapi = ">=0.100.0"
uvicorn = ">=0.23.0"
python-dotenv = ">=1.0.0"

# 新增
sentence-transformers = ">=3.0.0"    # 文本嵌入
langchain = ">=0.3.0"                # RAG 框架
langchain-openai = ">=0.2.0"        # OpenAI 集成
chromadb = ">=0.5.0"                 # 向量数据库 (可选)
python-qqbot = ">=0.1.0"             # QQ Bot SDK
wechatpy = ">=1.8.0"                 # 微信 SDK
croniter = ">=2.0.0"                 # cron 表达式解析
cryptography = ">=42.0"              # 密钥加密存储
pywin32 = ">=306"                    # Windows API (沙箱)
```

---

## 七、关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 记忆存储 | SQLite + FTS5 + 文件混合 | 轻量、可靠、全文搜索 |
| 向量检索 | 余弦相似度 (非 L2) | 文本嵌入更适合余弦 |
| 沙箱 | 仅 Windows Restricted Token | 目标平台仅 Windows |
| Provider 配置 | 用户自定义 URL+密钥 | 灵活性高, 无预设维护成本 |
| 记忆巩固 | 后台异步 | 不阻塞主流程 |
| 技能格式 | SKILL.md (YAML frontmatter) | 行业事实标准 (Claude/OpenClaw/Hermes 通用) |
| 会话键 | 结构化字符串 | 可编码路由上下文, 支持层级 |
| 熔断器 | 三态热更新 | 生产级, 配置变更不影响状态 |

---

## 八、新目录结构

```
Mini-Agent/
├── mini_agent/                    # 核心库
│   ├── agent.py                   # Agent核心(OpenClaw+Hermes融合循环)
│   ├── cli.py                     # 统一CLI
│   ├── config.py                  # 扩展配置
│   │
│   ├── model_manager/             # [新增] 模型管理(CC Switch提取)
│   │   ├── provider.py            # Provider定义+自定义配置
│   │   ├── proxy_server.py        # HTTP代理
│   │   ├── circuit_breaker.py     # 熔断器
│   │   ├── failover.py            # 故障转移
│   │   ├── health_monitor.py      # 健康检查
│   │   ├── rectifier.py           # 请求整流
│   │   └── model_mapper.py        # 模型映射
│   │
│   ├── memory/                    # [重构] 记忆核心(五源融合)
│   │   ├── memoria_engine.py      # Memoria STM/LTM引擎
│   │   ├── memory_files.py        # GEMINI.md层次文件系统
│   │   ├── memory_tool.py         # MemoryTool自保存
│   │   ├── session_search.py      # FTS5会话搜索+LLM摘要
│   │   ├── consolidation.py       # Codex两阶段巩固管道
│   │   ├── user_modeling.py       # Honcho方言用户建模
│   │   ├── daily_log.py           # 每日日志+夜间蒸馏
│   │   └── relevance.py           # 相关性记忆检索
│   │
│   ├── code_agent/                # [新增] 编程代理(三源融合)
│   │   ├── agent_loop.py          # Codex事件循环+Gemini状态机
│   │   ├── sandbox/               # Codex三平台沙箱
│   │   │   └── windows.py         # Windows沙箱
│   │   ├── tools/                 # DeclarativeTool+40+属性
│   │   ├── coordinator.py         # 多Agent协调
│   │   ├── context_manager.py     # 反向Token预算+三层压缩
│   │   ├── mcp_client.py          # Gemini完整MCP
│   │   ├── permissions.py         # 多层权限
│   │   └── plugin_system.py       # 插件系统
│   │
│   ├── agent_core/                # [重构] 智能体核心(OpenClaw+Hermes)
│   │   ├── routing.py             # 8级绑定匹配路由
│   │   ├── skills/                # 技能平台
│   │   │   ├── loader.py          # SKILL.md加载+渐进式披露
│   │   │   ├── self_improve.py    # 自创建/自修补
│   │   │   ├── registry.py        # ClawHub注册表
│   │   │   └── eligibility.py     # 资格检查
│   │   ├── cron/                  # 定时任务
│   │   │   ├── scheduler.py       # 调度器
│   │   │   ├── isolated_run.py    # 隔离Agent执行
│   │   │   └── delivery.py        # 传递路由
│   │   ├── delegation.py          # Hermes子Agent委托
│   │   ├── session/               # 会话管理
│   │   │   ├── session_key.py     # 会话键格式
│   │   │   ├── lifecycle.py       # 重置策略
│   │   │   └── lineage.py         # 会话谱系
│   │   ├── browser/               # 浏览器控制
│   │   │   ├── chrome.py          # Chrome生命周期
│   │   │   ├── cdp.py             # CDP操作
│   │   │   └── tool.py            # Agent工具接口
│   │   └── security/              # 安全模型
│   │       ├── pairing.py         # DM配对
│   │       └── policy.py          # 访问策略
│   │
│   ├── channels/                  # [精简] 渠道层
│   │   ├── qqbot/                 # QQ Bot
│   │   └── wechat/                # 微信
│   │
│   ├── llm/                       # LLM客户端(扩展)
│   │   ├── minimax_client.py
│   │   ├── openai_client.py
│   │   ├── anthropic_client.py
│   │   ├── gemini_client.py       # [新增]
│   │   └── proxy_router.py        # [新增] 代理路由
│   │
│   ├── tools/                     # 工具集(扩展)
│   │   ├── file_tools.py
│   │   ├── bash_tool.py
│   │   ├── mcp_tools.py
│   │   ├── skill_tools.py
│   │   ├── docling_parse.py       # [新增]
│   │   ├── knowledge_base.py      # [新增]
│   │   └── web_search.py          # [新增]
│   │
│   └── launcher/                  # 启动器
│       ├── scanner.py
│       ├── gateway.py
│       └── orchestrator.py
│
├── gateway/                       # Gateway(增强)
│   ├── core/
│   ├── routers/
│   │   ├── chat.py
│   │   ├── sessions.py
│   │   ├── health.py
│   │   ├── code_agent.py          # [新增]
│   │   └── knowledge_base.py      # [新增]
│   └── channels/
│
├── subprograms/                   # 子程序
│   ├── novel_generator/           # 原有
│   ├── knowledge_base/            # [新增] MaxKB集成
│   ├── document_parser/           # [新增] Docling集成
│   └── memory_manager/            # [新增] 记忆管理
│
├── apps/
│   ├── agent_studio/              # 原有WebUI
│   └── open_webui/                # [新增] Open WebUI集成
│
├── workspace/                     # 工作区
├── tests/
└── pyproject.toml                 # 更新依赖
```
