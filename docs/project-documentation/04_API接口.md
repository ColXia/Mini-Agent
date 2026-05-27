# Mini-Agent API 接口

## 1. 概述

本文档定义 Mini-Agent Gateway API 的 HTTP 接口规范。Gateway 使用 FastAPI 实现，提供 RESTful API 供外部系统集成。

---

## 2. API 设计原则

### 2.1 URL 设计

- 使用名词表示资源
- 使用复数形式
- 使用嵌套表示关系
- 版本化 API

### 2.2 请求/响应格式

- 请求体: JSON
- 响应体: JSON
- 错误响应: 统一格式

### 2.3 认证

- Bearer Token 认证
- API Key 认证

---

## 3. Agent API

### 3.1 列出 Agents

```http
GET /api/v1/agents
```

**响应**

```json
{
  "agents": [
    {
      "agent_id": "default",
      "name": "Default Agent",
      "description": "Default agent for general tasks",
      "status": "ready"
    }
  ]
}
```

### 3.2 获取 Agent 详情

```http
GET /api/v1/agents/{agent_id}
```

**响应**

```json
{
  "agent_id": "default",
  "name": "Default Agent",
  "description": "Default agent for general tasks",
  "status": "ready",
  "model_binding": {
    "model_id": "claude-sonnet-4-6",
    "provider_id": "anthropic"
  },
  "tools": ["read_file", "write_file", "shell_execute"],
  "skills": ["file_operations", "code_analysis"],
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

### 3.3 获取活跃 Agent

```http
GET /api/v1/agents/active
```

**响应**

```json
{
  "agent_id": "default",
  "name": "Default Agent",
  "status": "running",
  "active_run_id": "run_001"
}
```

### 3.4 提交消息

```http
POST /api/v1/agents/{agent_id}/messages
```

**请求体**

```json
{
  "message": "Hello, how can you help me?",
  "session_id": "session_001",
  "attachments": [
    {
      "filename": "document.pdf",
      "content_type": "application/pdf",
      "content_base64": "..."
    }
  ]
}
```

**响应**

```json
{
  "run_id": "run_001",
  "status": "running",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### 3.5 流式消息

```http
POST /api/v1/agents/{agent_id}/messages/stream
Accept: text/event-stream
```

**请求体**

```json
{
  "message": "Hello, how can you help me?",
  "session_id": "session_001"
}
```

**响应 (SSE)**

```
event: message_start
data: {"run_id": "run_001"}

event: content_block_delta
data: {"delta": {"type": "text", "text": "Hello"}}

event: content_block_delta
data: {"delta": {"type": "text", "text": "!"}}

event: message_end
data: {"run_id": "run_001", "status": "completed"}
```

---

## 4. Run API

### 4.1 获取 Run 详情

```http
GET /api/v1/runs/{run_id}
```

**响应**

```json
{
  "run_id": "run_001",
  "agent_id": "default",
  "session_id": "session_001",
  "status": "running",
  "phase": "executing_tools",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:01Z"
}
```

### 4.2 中断 Run

```http
POST /api/v1/runs/{run_id}/interrupt
```

**请求体**

```json
{
  "reason": "User requested interruption",
  "source": "user"
}
```

**响应**

```json
{
  "run_id": "run_001",
  "status": "paused",
  "interrupted_at": "2024-01-01T00:00:02Z"
}
```

### 4.3 恢复 Run

```http
POST /api/v1/runs/{run_id}/resume
```

**请求体**

```json
{
  "resume_token": "token_123",
  "source": "user"
}
```

**响应**

```json
{
  "run_id": "run_001",
  "status": "running",
  "resumed_at": "2024-01-01T00:00:03Z"
}
```

### 4.4 取消 Run

```http
POST /api/v1/runs/{run_id}/cancel
```

**请求体**

```json
{
  "reason": "User cancelled",
  "source": "user"
}
```

**响应**

```json
{
  "run_id": "run_001",
  "status": "cancelled",
  "cancelled_at": "2024-01-01T00:00:04Z"
}
```

### 4.5 解决审批等待

```http
POST /api/v1/runs/{run_id}/resolve-approval
```

**请求体**

```json
{
  "approved": true,
  "token": "approval_token_123",
  "modifications": {
    "path": "/safe/path/file.txt"
  }
}
```

**响应**

```json
{
  "run_id": "run_001",
  "status": "running",
  "approval_resolved_at": "2024-01-01T00:00:05Z"
}
```

---

## 5. Session API

### 5.1 列出 Sessions

```http
GET /api/v1/sessions
```

**查询参数**

- `workspace_id` (可选): 工作空间 ID
- `agent_profile_id` (可选): Agent 配置 ID
- `state` (可选): 状态过滤
- `limit` (可选): 返回数量限制

**响应**

```json
{
  "sessions": [
    {
      "session_id": "session_001",
      "workspace_id": "workspace_001",
      "agent_profile_id": "default",
      "title": "Code Review Session",
      "message_count": 10,
      "state": "active",
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:01:00Z"
    }
  ],
  "total": 1
}
```

### 5.2 创建 Session

```http
POST /api/v1/sessions
```

**请求体**

```json
{
  "workspace_id": "workspace_001",
  "agent_profile_id": "default",
  "title": "New Session"
}
```

**响应**

```json
{
  "session_id": "session_002",
  "workspace_id": "workspace_001",
  "agent_profile_id": "default",
  "title": "New Session",
  "state": "active",
  "created_at": "2024-01-01T00:02:00Z"
}
```

### 5.3 获取 Session 详情

```http
GET /api/v1/sessions/{session_id}
```

**查询参数**

- `recent_limit` (可选): 最近消息数量限制

**响应**

```json
{
  "session_id": "session_001",
  "workspace_id": "workspace_001",
  "agent_profile_id": "default",
  "title": "Code Review Session",
  "messages": [
    {
      "message_id": "msg_001",
      "role": "user",
      "content": "Hello",
      "timestamp": "2024-01-01T00:00:00Z"
    },
    {
      "message_id": "msg_002",
      "role": "assistant",
      "content": "Hi! How can I help?",
      "timestamp": "2024-01-01T00:00:01Z"
    }
  ],
  "recent_runs": [
    {
      "run_id": "run_001",
      "status": "completed",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "state": "active",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:01:00Z"
}
```

### 5.4 删除 Session

```http
DELETE /api/v1/sessions/{session_id}
```

**响应**

```json
{
  "success": true,
  "session_id": "session_001"
}
```

---

## 6. Workspace API

### 6.1 列出 Workspaces

```http
GET /api/v1/workspaces
```

**响应**

```json
{
  "workspaces": [
    {
      "workspace_id": "workspace_001",
      "name": "Project Alpha",
      "root_path": "/home/user/projects/alpha",
      "workspace_kind": "project",
      "session_count": 5,
      "is_active": true
    }
  ]
}
```

### 6.2 获取 Workspace 详情

```http
GET /api/v1/workspaces/{workspace_id}
```

**响应**

```json
{
  "workspace_id": "workspace_001",
  "name": "Project Alpha",
  "root_path": "/home/user/projects/alpha",
  "workspace_kind": "project",
  "permission_table": {
    "allow_read_paths": ["/home/user/projects/alpha"],
    "allow_write_paths": ["/home/user/projects/alpha/src"],
    "allow_network": false,
    "allow_shell": true
  },
  "active_session_id": "session_001",
  "active_agent_instance_id": "instance_001",
  "sessions": [
    {
      "session_id": "session_001",
      "title": "Code Review",
      "state": "active"
    }
  ],
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

### 6.3 切换 Workspace

```http
POST /api/v1/workspaces/{workspace_id}/activate
```

**响应**

```json
{
  "workspace_id": "workspace_001",
  "is_active": true,
  "activated_at": "2024-01-01T00:00:00Z"
}
```

### 6.4 获取 Workspace 状态

```http
GET /api/v1/workspaces/{workspace_id}/status
```

**响应**

```json
{
  "workspace_id": "workspace_001",
  "is_active": true,
  "active_session_id": "session_001",
  "active_run_id": "run_001",
  "active_agent_instance_id": "instance_001",
  "recent_mutations": 10,
  "last_activity_at": "2024-01-01T00:00:00Z"
}
```

---

## 7. Model API

### 7.1 列出模型绑定

```http
GET /api/v1/models/bindings
```

**响应**

```json
{
  "bindings": [
    {
      "agent_id": "default",
      "model_id": "claude-sonnet-4-6",
      "provider_id": "anthropic",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### 7.2 获取模型绑定

```http
GET /api/v1/models/bindings/{agent_id}
```

**响应**

```json
{
  "agent_id": "default",
  "model_id": "claude-sonnet-4-6",
  "provider_id": "anthropic",
  "model_capabilities": {
    "supports_tools": true,
    "supports_vision": true,
    "max_context_tokens": 200000
  },
  "created_at": "2024-01-01T00:00:00Z"
}
```

### 7.3 更新模型绑定

```http
PUT /api/v1/models/bindings/{agent_id}
```

**请求体**

```json
{
  "model_id": "claude-opus-4-7",
  "provider_id": "anthropic"
}
```

**响应**

```json
{
  "agent_id": "default",
  "model_id": "claude-opus-4-7",
  "provider_id": "anthropic",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

### 7.4 列出模型能力

```http
GET /api/v1/models/capabilities
```

**查询参数**

- `agent_id` (可选): Agent ID

**响应**

```json
{
  "capabilities": [
    {
      "model_id": "claude-sonnet-4-6",
      "provider_id": "anthropic",
      "supports_tools": true,
      "supports_vision": true,
      "max_context_tokens": 200000,
      "max_output_tokens": 8192
    }
  ]
}
```

---

## 8. Command API

### 8.1 发现命令

```http
GET /api/v1/commands
```

**响应**

```json
{
  "commands": [
    {
      "name": "/help",
      "description": "Show available commands",
      "usage": "/help [command]"
    },
    {
      "name": "/model",
      "description": "Switch model",
      "usage": "/model <model_id>"
    }
  ]
}
```

### 8.2 获取命令描述

```http
GET /api/v1/commands/{command}
```

**响应**

```json
{
  "name": "/model",
  "description": "Switch or view current model",
  "usage": "/model [model_id]",
  "examples": [
    "/model",
    "/model claude-opus-4-7"
  ],
  "arguments": [
    {
      "name": "model_id",
      "type": "string",
      "required": false,
      "description": "Model ID to switch to"
    }
  ]
}
```

### 8.3 命令补全

```http
POST /api/v1/commands/complete
```

**请求体**

```json
{
  "partial": "/mod"
}
```

**响应**

```json
{
  "completions": [
    "/model"
  ]
}
```

### 8.4 分发命令

```http
POST /api/v1/commands/dispatch
```

**请求体**

```json
{
  "command": "/model",
  "args": ["claude-opus-4-7"]
}
```

**响应**

```json
{
  "success": true,
  "output": "Model switched to claude-opus-4-7",
  "command": "/model"
}
```

---

## 9. 错误响应格式

### 9.1 标准错误格式

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Agent not found",
    "details": {
      "agent_id": "nonexistent_agent"
    }
  }
}
```

### 9.2 错误代码

| 代码 | HTTP 状态码 | 说明 |
|------|------------|------|
| `INVALID_REQUEST` | 400 | 请求参数无效 |
| `UNAUTHORIZED` | 401 | 未认证 |
| `FORBIDDEN` | 403 | 无权限 |
| `RESOURCE_NOT_FOUND` | 404 | 资源不存在 |
| `CONFLICT` | 409 | 资源冲突 |
| `RATE_LIMITED` | 429 | 请求频率超限 |
| `INTERNAL_ERROR` | 500 | 内部错误 |
| `SERVICE_UNAVAILABLE` | 503 | 服务不可用 |

---

## 10. WebSocket API

### 10.1 连接

```javascript
ws://localhost:8000/api/v1/ws?session_id=session_001
```

### 10.2 消息格式

**客户端消息**

```json
{
  "type": "message",
  "content": "Hello",
  "attachments": []
}
```

**服务端消息**

```json
{
  "type": "message_start",
  "run_id": "run_001",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

```json
{
  "type": "content_delta",
  "delta": {
    "type": "text",
    "text": "Hello"
  }
}
```

```json
{
  "type": "tool_call",
  "tool_name": "read_file",
  "arguments": {"path": "/src/main.py"}
}
```

```json
{
  "type": "message_end",
  "run_id": "run_001",
  "status": "completed"
}
```

### 10.3 事件类型

| 类型 | 方向 | 说明 |
|------|------|------|
| `message` | 客户端→服务端 | 发送消息 |
| `interrupt` | 客户端→服务端 | 中断 Run |
| `resume` | 客户端→服务端 | 恢复 Run |
| `message_start` | 服务端→客户端 | 消息开始 |
| `content_delta` | 服务端→客户端 | 内容增量 |
| `tool_call` | 服务端→客户端 | 工具调用 |
| `approval_request` | 服务端→客户端 | 审批请求 |
| `message_end` | 服务端→客户端 | 消息结束 |
| `error` | 服务端→客户端 | 错误 |