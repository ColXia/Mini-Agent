# 持久化存储开发文档

**模块**: session/persistence
**优先级**: P0
**预估时间**: 已实现，文档补全

---

## 一、功能概述

持久化存储负责会话状态的文件系统持久化：

- 会话元数据存储
- 转录存储
- 检查点管理
- 会话搜索索引

---

## 二、持久化组件总览

| 组件 | 职责 |
|------|------|
| `SessionPersistence` | 基础会话持久化 |
| `MainAgentRuntimePersistence` | 主代理运行时持久化 |
| `RuntimeSessionPersistenceRecordBuilder` | 记录构建器 |
| `RuntimeSessionPersistenceMetadataRegistry` | 元数据注册表 |
| `RuntimeSessionSharedTranscriptStore` | 共享转录存储 |
| `RuntimeSessionPersistenceLoader` | 记录加载器 |

---

## 三、核心持久化组件

### 3.1 SessionPersistence

```python
# src/mini_agent/session/persistence.py

class SessionPersistence:
    """Filesystem-backed session persistence (metadata + transcript + checkpoints)."""

    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            env_dir = os.getenv("MINI_AGENT_SESSION_STORE_DIR")
            if env_dir:
                base_dir = Path(env_dir)
            else:
                base_dir = Path.home() / ".mini-agent" / "sessions"

        self.base_dir = base_dir.expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.base_dir / "sessions.json"
        self.transcripts_dir = self.base_dir / "transcripts"
        self.checkpoints_dir = self.base_dir / "checkpoints"
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self._session_search = SessionSearchIndex(self.base_dir)

    # === 会话操作 ===

    def save_session(
        self,
        *,
        session_id: str,
        workspace_dir: str,
        created_at: str,
        updated_at: str,
        messages: list[Any],
        execution_policy: dict[str, Any] | None = None,
        configured_execution_policy: dict[str, Any] | None = None,
    ) -> None:
        """Save session to disk."""
        ...

    def load_session(self, session_id: str) -> dict[str, Any] | None:
        """Load session from disk."""
        ...

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions."""
        ...

    def delete_session(self, session_id: str) -> bool:
        """Delete session from disk."""
        ...

    # === 检查点操作 ===

    def save_checkpoint(
        self,
        session_id: str,
        checkpoint_name: str,
        messages: list[Any],
    ) -> dict[str, Any]:
        """Save checkpoint."""
        ...

    def list_checkpoints(self, session_id: str) -> list[dict[str, Any]]:
        """List checkpoints for session."""
        ...

    def load_checkpoint(
        self,
        session_id: str,
        checkpoint_name: str,
    ) -> list[dict[str, Any]] | None:
        """Load checkpoint."""
        ...

    # === 清理操作 ===

    def cleanup(
        self,
        *,
        max_age_seconds: int | None = None,
        max_count: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Cleanup old sessions."""
        ...

    # === 搜索操作 ===

    def search_sessions(
        self,
        *,
        query: str,
        limit: int = 20,
        session_id: str | None = None,
        workspace_anchor_dir: str | None = None,
        exclude_session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search sessions by content."""
        ...

    def search_relevant_memory(
        self,
        *,
        query: str,
        memory_file: Path | str,
        top_k: int = 5,
        stale_after_days: int = 30,
        workspace_anchor_dir: str | None = None,
        exclude_session_id: str | None = None,
    ) -> dict[str, Any]:
        """Search relevant memory across sessions."""
        ...
```

### 3.2 MainAgentRuntimePersistence

```python
class MainAgentRuntimePersistence:
    """Persist live runtime sessions plus transcript sidecars."""

    def __init__(
        self,
        storage_dir: Path | None = None,
        *,
        record_loader: RuntimeSessionPersistenceLoader,
        record_builder,
    ) -> None:
        if storage_dir is None:
            storage_dir = Path(tempfile.gettempdir()) / f"mini-agent-main-agent-runtime-{uuid4().hex}"
        self._session_store = SessionPersistence(storage_dir)
        self._record_loader = record_loader
        self._record_builder = record_builder
        self._metadata_registry = RuntimeSessionPersistenceMetadataRegistry(
            self._session_store.metadata_path,
        )
        self._shared_transcripts = RuntimeSessionSharedTranscriptStore(
            transcripts_dir=self._session_store.base_dir / "main_agent_runtime_transcripts",
            serialize_transcript_entry=self._record_builder.serialize_transcript_entry,
        )

    def read_shared_transcript(
        self,
        session_id: str,
        record: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Read shared transcript."""
        return self._shared_transcripts.read(session_id, record)

    def save_session(
        self,
        session,
        *,
        agent_messages=None,
        sandbox_diagnostics: dict[str, Any] | None = None,
    ) -> None:
        """Save session with full state."""
        ...

    def list_session_records(self) -> list[dict[str, Any]]:
        """List all session records."""
        ...

    def load_session_record(self, session_id: str) -> dict[str, Any] | None:
        """Load session record by ID."""
        ...

    def delete_session(self, session_id: str) -> bool:
        """Delete session."""
        ...
```

### 3.3 RuntimeSessionPersistenceRecordBuilder

```python
@dataclass(slots=True)
class RuntimeSessionPersistenceRecordBuilder:
    """Build persistence records from session state."""
    session_kind: str
    session_token_usage: Callable[["MainAgentSessionState"], int]
    session_token_limit: Callable[["MainAgentSessionState"], int]
    agent_last_memory_automation: Callable[[Any], dict[str, Any]] | None = None
    agent_last_runtime_task_memory: Callable[[Any], dict[str, Any]] | None = None
    active_pending_approvals: Callable[["MainAgentSessionState"], list[dict[str, Any]]] | None = None
    active_run_control_state: Callable[["MainAgentSessionState"], dict[str, Any] | None] | None = None
    active_approval_wait: Callable[["MainAgentSessionState"], dict[str, Any] | None] | None = None
    active_kernel_state: Callable[["MainAgentSessionState"], dict[str, Any] | None] | None = None
    selected_model_identity_for_session: Callable | None = None
    pending_model_identity_for_session: Callable | None = None

    def build_metadata_record(
        self,
        session: "MainAgentSessionState",
        *,
        transcript_path: Path,
        sandbox_diagnostics: dict[str, Any],
        workspace_runtime_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build metadata record for session."""
        ...

    @staticmethod
    def serialize_transcript_entry(entry: "MainAgentSessionTranscriptEntry") -> dict[str, Any]:
        """Serialize transcript entry."""
        ...

    @staticmethod
    def serialize_pending_approval(item: dict[str, Any]) -> dict[str, Any]:
        """Serialize pending approval."""
        ...
```

### 3.4 RuntimeSessionSharedTranscriptStore

```python
class RuntimeSessionSharedTranscriptStore:
    """Store shared transcripts as JSONL files."""

    def __init__(
        self,
        transcripts_dir: Path,
        *,
        serialize_transcript_entry,
    ) -> None:
        self.transcripts_dir = transcripts_dir
        self.serialize_transcript_entry = serialize_transcript_entry
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str) -> Path:
        """Get transcript path for session."""
        ...

    def write(
        self,
        session_id: str,
        entries,
    ) -> Path:
        """Write transcript to disk."""
        ...

    def read(
        self,
        session_id: str,
        record: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Read transcript from disk."""
        ...

    def delete(self, session_id: str) -> None:
        """Delete transcript."""
        ...
```

---

## 四、文件结构

```
~/.mini-agent/sessions/
├── sessions.json                    # 元数据索引
├── transcripts/
│   ├── session_001.jsonl            # 会话转录
│   ├── session_002.jsonl
│   └── ...
├── checkpoints/
│   ├── session_001/
│   │   ├── checkpoint_1.jsonl       # 检查点
│   │   ├── checkpoint_2.jsonl
│   │   └── ...
│   └── ...
└── main_agent_runtime_transcripts/  # 运行时转录
    ├── default.jsonl
    └── ...
```

---

## 五、转录文件格式

```jsonl
{"index": 1, "role": "user", "content": "Hello", "surface": "tui", "created_at": "2026-05-11T10:00:00Z"}
{"index": 2, "role": "assistant", "content": "Hi!", "surface": "tui", "created_at": "2026-05-11T10:00:01Z"}
{"index": 3, "role": "user", "content": "Help me with X", "surface": "slack", "channel_type": "slack", "conversation_id": "C123", "created_at": "2026-05-11T10:01:00Z"}
```

---

## 六、原子写入

```python
def _atomic_write_text(path: Path, content: str) -> None:
    """Atomically write text file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)
```

---

## 七、文件位置

```
src/mini_agent/session/
├── persistence.py               # 本文档所述组件
```

---

## 八、验收标准

- [x] 支持会话持久化
- [x] 支持转录存储
- [x] 支持检查点
- [x] 支持会话搜索
- [x] 支持清理策略

---

## 九、依赖关系

- 依赖: store_records, memory/session_search, workspace_runtime/snapshot_store
- 被依赖: runtime/