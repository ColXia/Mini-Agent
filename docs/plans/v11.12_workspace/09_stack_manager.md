# 运行时栈管理器开发文档

**模块**: workspace_runtime/runtime_stack_manager
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

运行时栈管理器负责：

- Gateway 进程管理
- QQ Bot 进程管理
- 运行时栈状态监控
- 进程启停控制

---

## 二、栈管理器组件总览

| 组件 | 职责 |
|------|------|
| `RuntimeStackStatus` | 运行时栈状态 |
| `RuntimeStackManager` | 运行时栈管理器 |

---

## 三、核心栈管理器组件

### 3.1 RuntimeStackStatus

```python
# src/mini_agent/workspace_runtime/runtime_stack_manager.py

@dataclass(slots=True)
class RuntimeStackStatus:
    """Runtime stack status."""
    running: bool                 # 是否运行中
    gateway_running: bool         # Gateway 是否运行
    qqbot_running: bool           # QQ Bot 是否运行
    host: str                     # 主机地址
    gateway_port: int             # Gateway 端口
    workspace: Path               # 工作空间路径
    gateway_pid: int | None       # Gateway 进程 ID
    qqbot_pid: int | None         # QQ Bot 进程 ID
    state_file: Path              # 状态文件路径
    gateway_log: Path             # Gateway 日志路径
    qqbot_log: Path               # QQ Bot 日志路径
    qqbot_enabled: bool           # QQ Bot 是否启用
    qqbot_configured: bool        # QQ Bot 是否配置
    message: str = ""             # 状态消息
```

### 3.2 RuntimeStackManager

```python
class RuntimeStackManager:
    """Manage the local runtime stack used by TUI plus the active QQ remote adapter."""

    def __init__(
        self,
        *,
        source_root: Path,
        repo_root: Path | None = None,
        state_root: Path | None = None,
    ) -> None:
        self.source_root = source_root.resolve()
        self.repo_root = (repo_root or self.source_root.parent).resolve()
        self.qqbot_dir = (self.source_root / "apps" / "qqbot_channel").resolve()
        if state_root is None:
            self.state_dir = Path.home() / ".mini-agent" / "runtime-stack"
        else:
            self.state_dir = state_root.resolve()
        self.logs_dir = self.state_dir / "logs"
        self.state_file = self.state_dir / "state.json"
        self.gateway_log_file = self.logs_dir / "gateway.log"
        self.qqbot_log_file = self.logs_dir / "qqbot.log"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    # === 状态查询 ===

    def status(self) -> RuntimeStackStatus:
        """Get runtime stack status."""
        return self._status_from_payload(self._read_state())

    # === 启动 ===

    def up(
        self,
        *,
        host: str,
        gateway_port: int,
        workspace: Path,
        qqbot: bool | None,
        approval_profile: str | None,
        access_level: str | None,
        startup_timeout: float = 20.0,
    ) -> RuntimeStackStatus:
        """Start runtime stack."""
        current = self.status()
        if current.running:
            raise RuntimeError(
                "Runtime stack is already running. Use `mini-agent stack status` "
                "or `mini-agent stack down` first."
            )

        # 启动 Gateway
        gateway_command = [
            sys.executable,
            "-m", "mini_agent.cli",
            "serve",
            "--host", host,
            "--port", str(gateway_port),
            "--workspace", str(workspace),
        ]
        gateway_pid = self._spawn_process(
            command=gateway_command,
            cwd=self.repo_root,
            env=env,
            log_path=self.gateway_log_file,
        )
        self._wait_for_gateway_ready(
            host=host,
            port=gateway_port,
            pid=gateway_pid,
            timeout_seconds=startup_timeout,
        )

        # 启动 QQ Bot
        if qqbot_enabled:
            npm = self._ensure_qqbot_prerequisites()
            qqbot_env = env.copy()
            qqbot_env["MINI_AGENT_GATEWAY_BASE"] = f"http://{host}:{gateway_port}"
            qqbot_pid = self._spawn_process(
                command=[npm, "run", "start"],
                cwd=self.qqbot_dir,
                env=qqbot_env,
                log_path=self.qqbot_log_file,
            )
            self._wait_for_process_stable(
                pid=qqbot_pid,
                label="QQ bot",
                log_path=self.qqbot_log_file,
            )

        ...

    # === 停止 ===

    def down(self, *, force: bool = False) -> RuntimeStackStatus:
        """Stop runtime stack."""
        payload = self._read_state()
        status = self._status_from_payload(payload)

        gateway_pid = _to_int((payload or {}).get("gateway_pid"))
        qqbot_pid = _to_int((payload or {}).get("qqbot_pid"))

        notes: list[str] = []
        if qqbot_pid:
            stopped = _terminate_process(qqbot_pid, force=force)
            notes.append("qqbot stopped" if stopped else "qqbot stop failed")
        if gateway_pid:
            stopped = _terminate_process(gateway_pid, force=force)
            notes.append("gateway stopped" if stopped else "gateway stop failed")

        self.state_file.unlink(missing_ok=True)
        ...

    # === 日志 ===

    def read_logs(self, *, target: str, lines: int = 120) -> dict[str, str]:
        """Read runtime logs."""
        payload: dict[str, str] = {}
        normalized = str(target or "all").strip().lower()
        if normalized in {"all", "gateway"}:
            payload["gateway"] = _tail_lines(self.gateway_log_file, lines)
        if normalized in {"all", "qqbot"}:
            payload["qqbot"] = _tail_lines(self.qqbot_log_file, lines)
        return payload
```

---

## 四、进程管理辅助函数

```python
def is_port_listening(host: str, port: int, *, timeout: float = 0.25) -> bool:
    """Check if port is listening."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

def is_process_alive(pid: int | None) -> bool:
    """Check if process is alive."""
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        ...
    else:
        try:
            os.kill(int(pid), 0)
        except OSError:
            return False
        return True

def _terminate_process(pid: int | None, *, force: bool = False) -> bool:
    """Terminate process."""
    ...
```

---

## 五、运行时栈架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Runtime Stack Architecture                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  TUI / Desktop                                          │   │
│  │  - 用户界面                                              │   │
│  │  - 调用 RuntimeStackManager                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  RuntimeStackManager                                     │   │
│  │  - up(): 启动 Gateway + QQ Bot                           │   │
│  │  - down(): 停止进程                                      │   │
│  │  - status(): 查询状态                                    │   │
│  │  - read_logs(): 读取日志                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│              ┌───────────────┴───────────────┐                  │
│              │                               │                  │
│              ▼                               ▼                  │
│  ┌───────────────────┐              ┌───────────────────┐      │
│  │  Gateway          │              │  QQ Bot           │      │
│  │  - HTTP Server    │              │  - Node.js        │      │
│  │  - Port 8008      │◄────────────►│  - Connect to     │      │
│  │  - Python         │              │    Gateway        │      │
│  └───────────────────┘              └───────────────────┘      │
│                                                                 │
│  State: ~/.mini-agent/runtime-stack/state.json                  │
│  Logs:  ~/.mini-agent/runtime-stack/logs/                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 六、状态文件格式

```json
{
  "host": "127.0.0.1",
  "gateway_port": 8008,
  "workspace": "/path/to/workspace",
  "gateway_pid": 12345,
  "qqbot_pid": 12346,
  "qqbot_enabled": true,
  "started_at": "2026-05-11T10:00:00Z"
}
```

---

## 七、文件位置

```
src/mini_agent/workspace_runtime/
├── runtime_stack_manager.py     # 本文档所述组件
```

---

## 八、验收标准

- [x] 支持进程启动
- [x] 支持进程停止
- [x] 支持状态查询
- [x] 支持日志读取

---

## 九、依赖关系

- 依赖: 无
- 被依赖: tui/, desktop/, cli/