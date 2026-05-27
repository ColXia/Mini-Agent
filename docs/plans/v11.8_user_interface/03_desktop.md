# Desktop 桌面应用开发文档

**模块**: desktop
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

Desktop 提供图形化用户界面：

- 多页面布局
- 系统托盘
- Gateway 监管
- 远程连接管理

---

## 二、技术栈

- **PySide6 (Qt)** - GUI 框架
- **asyncio** - 异步执行
- **Gateway** - 远程服务

---

## 三、核心组件

### 3.1 Desktop 应用结构

```python
# src/mini_agent/desktop/app.py

def launch_desktop_ui(
    *,
    host: str,
    port: int,
    workspace: Path,
    approval_profile: str | None,
    access_level: str | None,
    startup_timeout: float,
    attach_only: bool,
    source_root: Path,
    repo_root: Path,
) -> int:
    """Launch the minimal DesktopUI shell."""
    # 加载 Qt 模块
    qtwidgets, qtcore = _load_qt_modules()

    # 创建 Gateway 监管
    supervisor = DesktopGatewaySupervisor(
        source_root=source_root,
        repo_root=repo_root,
    )

    # 确保连接
    connection = supervisor.ensure_gateway_running(
        host=host,
        port=port,
        workspace=workspace,
        approval_profile=approval_profile,
        access_level=access_level,
        startup_timeout=startup_timeout,
        attach_only=attach_only,
    )

    # 创建传输绑定
    gateway_client = GatewayClient(
        base_url=connection.base_url,
        timeout_seconds=DESKTOP_GATEWAY_TIMEOUT_SECONDS,
    )
    transport_binding = DesktopGatewayTransportBinding.from_gateway_client(gateway_client)

    # 创建应用
    app = qtwidgets.QApplication(sys.argv)
    app.setApplicationName("Mini-Agent DesktopUI")

    # 创建主窗口
    window = create_desktop_main_window(
        qtwidgets=qtwidgets,
        qtcore=qtcore,
        transport_binding=transport_binding,
        supervisor=supervisor,
        connection=connection,
        reconnect_handler=_ensure_connection,
    )
    window.show()

    return app.exec()
```

### 3.2 页面布局

```python
DESKTOP_PAGE_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "chat",
        "label": "Chat",
        "description": "Focused conversation workspace.",
    },
    {
        "id": "models",
        "label": "Models",
        "description": "Model inventory and capability facts.",
    },
    {
        "id": "providers",
        "label": "Providers",
        "description": "Provider configuration and health.",
    },
    {
        "id": "settings",
        "label": "Settings",
        "description": "Desktop preferences and runtime overview.",
    },
    {
        "id": "sessions",
        "label": "Sessions",
        "description": "Session history and diagnostics.",
    },
    {
        "id": "memory",
        "label": "Memory",
        "description": "Durable note memory workspace.",
    },
)
```

### 3.3 窗口结构

```
┌─────────────────────────────────────────────────────────────────┐
│ Menu Bar: File, Edit, View, Help                                 │
├─────────────────────────────────────────────────────────────────┤
│ Toolbar: New Session, Settings, Connect                          │
├─────────────────────────────────────────────────────────────────┤
│ ┌───────────┬─────────────────────────────────────────────────┐ │
│ │ Sidebar   │                   Main Area                      │ │
│ │           │                                                   │ │
│ │ • Chat    │  ┌─────────────────────────────────────────────┐ │ │
│ │ • Models  │  │                                             │ │ │
│ │ • Providers│ │              Page Content                   │ │ │
│ │ • Settings│  │                                             │ │ │
│ │ • Sessions│  │                                             │ │ │
│ │ • Memory  │  └─────────────────────────────────────────────┘ │ │
│ │           │                                                   │ │
│ └───────────┴─────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ Status Bar: Connection, Model, Session                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、Gateway 监管

### 4.1 Gateway Supervisor

```python
# src/mini_agent/desktop/gateway_supervisor.py

@dataclass
class DesktopGatewayConnection:
    """Gateway connection details."""
    base_url: str
    workspace_dir: Path
    process: subprocess.Popen | None = None
    attached: bool = False


class DesktopGatewaySupervisor:
    """Supervisor for local gateway process."""

    def __init__(
        self,
        *,
        source_root: Path,
        repo_root: Path,
    ) -> None:
        self.source_root = source_root
        self.repo_root = repo_root
        self._connection: DesktopGatewayConnection | None = None

    def ensure_gateway_running(
        self,
        *,
        host: str,
        port: int,
        workspace: Path,
        approval_profile: str | None,
        access_level: str | None,
        startup_timeout: float,
        attach_only: bool,
    ) -> DesktopGatewayConnection:
        """Ensure gateway is running and return connection."""
        if attach_only:
            return self._attach_to_existing(host, port, workspace)
        return self._start_or_attach(host, port, workspace, ...)

    def _start_gateway(
        self,
        host: str,
        port: int,
        workspace: Path,
        ...
    ) -> DesktopGatewayConnection:
        """Start new gateway process."""
        process = subprocess.Popen([
            sys.executable,
            "-m", "mini_agent.gateway",
            "--host", host,
            "--port", str(port),
            "--workspace", str(workspace),
            ...
        ])
        return DesktopGatewayConnection(
            base_url=f"http://{host}:{port}",
            workspace_dir=workspace,
            process=process,
            attached=False,
        )

    def shutdown(self) -> None:
        """Shutdown gateway process."""
        if self._connection and self._connection.process:
            self._connection.process.terminate()
```

---

## 五、传输绑定

### 5.1 DesktopGatewayTransportBinding

```python
# src/mini_agent/desktop/gateway_transport_binding.py

@dataclass(slots=True)
class DesktopGatewayTransportBinding:
    """Shared gateway transport bundle for DesktopUI surfaces."""

    gateway_client: GatewayClient
    chat_client: RemoteChatClient
    run_client: RemoteRunClient
    session_client: RemoteSessionClient
    system_client: RemoteSystemClient
    memory_client: RemoteMemoryClient
    model_client: RemoteModelCatalogClient
    provider_client: RemoteProviderClient
    workspace_client: RemoteWorkspaceClient

    @classmethod
    def from_gateway_client(
        cls,
        gateway_client: GatewayClient,
    ) -> DesktopGatewayTransportBinding:
        return cls(
            gateway_client=gateway_client,
            chat_client=RemoteChatClient(chat_transport=gateway_client),
            run_client=RemoteRunClient(run_transport=gateway_client),
            session_client=RemoteSessionClient(session_transport=gateway_client),
            system_client=RemoteSystemClient(system_transport=gateway_client),
            memory_client=RemoteMemoryClient(memory_transport=gateway_client),
            model_client=RemoteModelCatalogClient(model_transport=gateway_client),
            provider_client=RemoteProviderClient(provider_transport=gateway_client),
            workspace_client=RemoteWorkspaceClient(workspace_transport=gateway_client),
        )
```

---

## 六、会话操作

### 6.1 Session Actions

```python
# src/mini_agent/desktop/session_actions.py

async def perform_desktop_session_creation(
    *,
    transport_binding: DesktopGatewayTransportBinding,
    workspace_dir: Path,
    title: str | None,
) -> DesktopSessionActionFeedback:
    """Create new session."""

async def perform_desktop_session_fork(
    *,
    transport_binding: DesktopGatewayTransportBinding,
    session_id: str,
    title: str | None,
) -> DesktopSessionActionFeedback:
    """Fork existing session."""

async def perform_desktop_session_rename(
    *,
    transport_binding: DesktopGatewayTransportBinding,
    session_id: str,
    new_title: str,
) -> DesktopSessionActionFeedback:
    """Rename session."""

async def perform_desktop_session_compact(
    *,
    transport_binding: DesktopGatewayTransportBinding,
    session_id: str,
) -> DesktopSessionActionFeedback:
    """Compact session context."""

async def perform_desktop_run_interrupt(
    *,
    transport_binding: DesktopGatewayTransportBinding,
    run_id: str,
    reason: str | None,
) -> DesktopSessionActionFeedback:
    """Interrupt running task."""

async def perform_desktop_run_cancel(
    *,
    transport_binding: DesktopGatewayTransportBinding,
    run_id: str,
    reason: str | None,
) -> DesktopSessionActionFeedback:
    """Cancel running task."""

async def perform_desktop_run_resume(
    *,
    transport_binding: DesktopGatewayTransportBinding,
    run_id: str,
    resume_token: str | None,
) -> DesktopSessionActionFeedback:
    """Resume paused task."""

async def perform_desktop_pending_approval_resolution(
    *,
    transport_binding: DesktopGatewayTransportBinding,
    run_id: str,
    approved: bool,
    token: str,
) -> DesktopSessionActionFeedback:
    """Resolve pending approval."""
```

---

## 七、Provider 预设

```python
DESKTOP_PROVIDER_PRESET_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "openai_official",
        "label": "OpenAI",
        "api_type": "openai",
        "provider_id": "openai-official",
        "provider_name": "OpenAI Official",
        "api_base": "https://api.openai.com/v1",
    },
    {
        "id": "anthropic_official",
        "label": "Anthropic",
        "api_type": "anthropic",
        "provider_id": "anthropic-official",
        "provider_name": "Anthropic Official",
        "api_base": "https://api.anthropic.com",
    },
    {
        "id": "deepseek_official",
        "label": "DeepSeek",
        "api_type": "openai",
        "provider_id": "deepseek-official",
        "provider_name": "DeepSeek Official",
        "api_base": "https://api.deepseek.com",
    },
    ...
)
```

---

## 八、文件位置

```
src/mini_agent/desktop/
├── __init__.py
├── app.py                        # Desktop 启动
├── window.py                     # 主窗口
├── gateway_supervisor.py         # Gateway 监管
├── gateway_transport_binding.py  # 传输绑定
└── session_actions.py            # 会话操作
```

---

## 九、验收标准

- [x] 支持多页面布局
- [x] 支持 Gateway 监管
- [x] 支持远程连接
- [x] 支持会话操作
- [x] 支持 Provider 预设

---

## 十、依赖关系

- 依赖: transport/, gateway/
- 被依赖: 用户交互