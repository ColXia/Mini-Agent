# 传输层开发文档

**模块**: transport
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

传输层负责：

- HTTP 通信
- WebSocket/SSE 流式传输
- 远程客户端封装
- 错误处理

---

## 二、核心组件

### 2.1 GatewayClient

```python
# src/mini_agent/transport/gateway_client.py

class GatewayClient:
    """Minimal HTTP client for the local Studio gateway."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        configured = safe_text(base_url or os.getenv("MINI_AGENT_GATEWAY_BASE") or "http://127.0.0.1:8008")
        self.base_url = configured.rstrip("/")
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    # === 会话操作 ===

    async def create_session(
        self,
        *,
        workspace_dir: str,
        title: str | None = None,
        surface: str = "tui",
        shared: bool = False,
    ) -> dict[str, Any]:
        """Create new session."""

    async def list_sessions(
        self,
        *,
        workspace_dir: str,
        shared_only: bool = False,
    ) -> list[dict[str, Any]]:
        """List sessions."""

    async def get_session(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """Get session details."""

    async def delete_session(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """Delete session."""

    # === 聊天操作 ===

    async def chat(
        self,
        *,
        session_id: str,
        message: str,
        surface: str = "tui",
    ) -> dict[str, Any]:
        """Send chat message."""

    async def chat_stream(
        self,
        *,
        session_id: str,
        message: str,
        surface: str = "tui",
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream chat response via SSE."""

    # === Run 控制 ===

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Interrupt running task."""

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Cancel running task."""

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Resume paused task."""

    # === 审批操作 ===

    async def resolve_approval(
        self,
        run_id: str,
        *,
        approved: bool,
        token: str,
    ) -> dict[str, Any]:
        """Resolve pending approval."""
```

---

## 三、远程客户端

### 3.1 客户端列表

| 客户端 | 职责 |
|--------|------|
| `RemoteChatClient` | 聊天操作 |
| `RemoteRunClient` | Run 控制 |
| `RemoteSessionClient` | 会话管理 |
| `RemoteMemoryClient` | 记忆管理 |
| `RemoteModelCatalogClient` | 模型目录 |
| `RemoteProviderClient` | Provider 管理 |
| `RemoteWorkspaceClient` | 工作区管理 |
| `RemoteSystemClient` | 系统信息 |

### 3.2 客户端实现模式

```python
# src/mini_agent/transport/remote_chat_client.py

class RemoteChatClient:
    """Remote client for chat operations via Gateway."""

    def __init__(self, chat_transport: GatewayClient) -> None:
        self._transport = chat_transport

    async def send_message(
        self,
        *,
        session_id: str,
        message: str,
        surface: str = "tui",
    ) -> MainAgentChatResponse:
        """Send chat message."""
        result = await self._transport.chat(
            session_id=session_id,
            message=message,
            surface=surface,
        )
        return MainAgentChatResponse.from_dict(result)

    async def stream_message(
        self,
        *,
        session_id: str,
        message: str,
        surface: str = "tui",
    ) -> AsyncIterator[StreamEvent]:
        """Stream chat response."""
        for event in await self._transport.chat_stream(
            session_id=session_id,
            message=message,
            surface=surface,
        ):
            yield StreamEvent.from_dict(event)
```

---

## 四、传输端口

### 4.1 传输端口协议

```python
# src/mini_agent/transport/chat_transport_port.py

class ChatTransportPort(Protocol):
    """Protocol for chat transport operations."""

    async def send_message(
        self,
        *,
        session_id: str,
        message: str,
        surface: str = "tui",
    ) -> MainAgentChatResponse: ...

    async def stream_message(
        self,
        *,
        session_id: str,
        message: str,
        surface: str = "tui",
    ) -> AsyncIterator[StreamEvent]: ...
```

### 4.2 传输端口列表

| 端口 | 职责 |
|------|------|
| `ChatTransportPort` | 聊天传输 |
| `RunTransportPort` | Run 控制传输 |
| `SessionTransportPort` | 会话传输 |
| `MemoryTransportPort` | 记忆传输 |
| `ModelCatalogTransportPort` | 模型目录传输 |
| `ProviderTransportPort` | Provider 传输 |
| `WorkspaceTransportPort` | 工作区传输 |
| `SystemTransportPort` | 系统传输 |

---

## 五、错误处理

### 5.1 GatewayTransportError

```python
# src/mini_agent/transport/gateway_error.py

@dataclass(frozen=True)
class GatewayTransportError:
    """Structured gateway transport error."""

    error_type: str
    message: str
    status_code: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_http_error(cls, error: HTTPError) -> GatewayTransportError:
        """Create from HTTP error."""
        ...

    @classmethod
    def from_url_error(cls, error: URLError) -> GatewayTransportError:
        """Create from URL error."""
        ...

    def is_retryable(self) -> bool:
        """Check if error is retryable."""
        return self.status_code in {502, 503, 504}

    def is_auth_error(self) -> bool:
        """Check if error is authentication related."""
        return self.status_code in {401, 403}
```

### 5.2 错误类型

| 错误类型 | 说明 |
|---------|------|
| `connection_error` | 连接失败 |
| `timeout_error` | 超时 |
| `auth_error` | 认证失败 |
| `not_found` | 资源不存在 |
| `validation_error` | 参数验证失败 |
| `server_error` | 服务端错误 |

---

## 六、SSE 流式传输

### 6.1 SSE 事件类型

```python
class SSEEventType(str, Enum):
    """Server-Sent Events types."""

    CONTENT_DELTA = "content_delta"
    THINKING_DELTA = "thinking_delta"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_RESULT = "tool_call_result"
    STEP_COMPLETE = "step_complete"
    TURN_COMPLETE = "turn_complete"
    ERROR = "error"
```

### 6.2 SSE 解析

```python
async def parse_sse_stream(
    response: httpx.Response,
) -> AsyncIterator[dict[str, Any]]:
    """Parse SSE stream into events."""
    for line in response.iter_lines():
        if line.startswith("data: "):
            data = line[6:]
            if data:
                yield json.loads(data)
```

---

## 七、文件位置

```
src/mini_agent/transport/
├── __init__.py
├── gateway_client.py             # Gateway HTTP 客户端
├── gateway_error.py              # 错误处理
├── remote_chat_client.py         # 聊天客户端
├── remote_run_client.py          # Run 控制客户端
├── remote_session_client.py      # 会话客户端
├── remote_memory_client.py       # 记忆客户端
├── remote_model_catalog_client.py # 模型目录客户端
├── remote_provider_client.py     # Provider 客户端
├── remote_workspace_client.py    # 工作区客户端
├── remote_system_client.py       # 系统客户端
├── remote_chat_service_port.py   # 聊天服务端口
├── remote_stream_error_service.py # 流式错误服务
├── chat_transport_port.py        # 聊天传输端口
├── run_transport_port.py         # Run 传输端口
├── session_transport_port.py     # 会话传输端口
├── memory_transport_port.py      # 记忆传输端口
├── model_catalog_transport_port.py # 模型目录传输端口
├── provider_transport_port.py    # Provider 传输端口
├── workspace_transport_port.py   # 工作区传输端口
└── system_transport_port.py      # 系统传输端口
```

---

## 八、验收标准

- [x] GatewayClient 支持 HTTP 通信
- [x] 支持 SSE 流式传输
- [x] 支持多种远程客户端
- [x] 支持错误处理

---

## 九、依赖关系

- 依赖: interfaces/
- 被依赖: tui/, desktop/