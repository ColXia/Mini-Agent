# 会话绑定开发文档

**模块**: session/bindings
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

会话绑定负责：

- 对话-会话映射
- 远程通道绑定
- 绑定持久化
- 绑定解析

---

## 二、绑定组件总览

| 组件 | 职责 |
|------|------|
| `ConversationBindingStore` | 绑定存储 |
| `ConversationBindingPort` | 绑定端口协议 |
| `ConversationBindingService` | 绑定服务 |

---

## 三、核心绑定组件

### 3.1 ConversationBindingStore

```python
# src/mini_agent/session/bindings.py

class ConversationBindingStore:
    """Persistent binding map from channel conversation key to session_id."""

    def __init__(self, path: Path | None = None):
        if path is None:
            env_path = os.getenv("MINI_AGENT_BINDING_STORE_PATH")
            if env_path:
                path = Path(env_path)
            else:
                path = Path.home() / ".mini-agent" / "sessions" / "conversation_bindings.json"
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        """Load bindings from disk."""
        if not self.path.exists():
            return {"bindings": {}}
        try:
            with open(self.path, encoding="utf-8-sig") as f:
                payload = json.load(f)
        except Exception:
            return {"bindings": {}}
        if not isinstance(payload, dict):
            return {"bindings": {}}
        bindings = payload.get("bindings")
        if not isinstance(bindings, dict):
            payload["bindings"] = {}
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        """Save bindings to disk."""
        _atomic_write_text(
            self.path,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def get(self, binding_key: str) -> dict[str, Any] | None:
        """Get binding by key."""
        payload = self._load()
        record = payload.get("bindings", {}).get(binding_key)
        if isinstance(record, dict):
            return record
        return None

    def get_session_id(self, binding_key: str) -> str | None:
        """Get session ID for binding key."""
        record = self.get(binding_key)
        if not record:
            return None
        session_id = record.get("session_id")
        if isinstance(session_id, str) and session_id:
            return session_id
        return None

    def set(
        self,
        *,
        binding_key: str,
        session_id: str,
        workspace_dir: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
    ) -> None:
        """Set binding."""
        payload = self._load()
        bindings = payload.setdefault("bindings", {})
        bindings[binding_key] = {
            "binding_key": binding_key,
            "session_id": session_id,
            "channel_type": channel_type or "",
            "conversation_id": conversation_id or "",
            "workspace_dir": workspace_dir or "",
            "updated_at": _utc_now_iso(),
        }
        self._save(payload)

    def delete(self, binding_key: str) -> bool:
        """Delete binding."""
        payload = self._load()
        bindings = payload.get("bindings", {})
        if not isinstance(bindings, dict) or binding_key not in bindings:
            return False
        del bindings[binding_key]
        self._save(payload)
        return True
```

### 3.2 ConversationBindingPort

```python
class ConversationBindingPort(Protocol):
    """Minimal binding contract consumed by shared channel ingress flows."""

    def resolve_session_id(
        self,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        explicit_session_id: str | None = None,
        dry_run: bool = False,
    ) -> str | None: ...

    def persist_binding(
        self,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        session_id: str | None = None,
        workspace_dir: str | None = None,
        dry_run: bool = False,
    ) -> None: ...
```

### 3.3 ConversationBindingService

```python
class ConversationBindingService:
    """Resolve and persist remote conversation-to-session bindings centrally."""

    def __init__(self, *, binding_store: ConversationBindingStore | None = None) -> None:
        self._binding_store = binding_store or conversation_binding_store

    def resolve_session_id(
        self,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        explicit_session_id: str | None = None,
        dry_run: bool = False,
    ) -> str | None:
        """Resolve session ID for conversation."""
        explicit = _clean(explicit_session_id)
        if explicit:
            return explicit
        if dry_run:
            return None
        binding = resolve_interaction_binding(
            surface=surface or channel_type,
            channel_type=channel_type,
            conversation_id=conversation_id,
            default_surface=None,
        )
        if binding.entrance != "remote" or not binding.channel_type or not binding.conversation_id:
            return None
        binding_key = f"{binding.channel_type}|{binding.conversation_id}"
        return self._binding_store.get_session_id(binding_key)

    def persist_binding(
        self,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        session_id: str | None = None,
        workspace_dir: str | None = None,
        dry_run: bool = False,
    ) -> None:
        """Persist binding for conversation."""
        if dry_run:
            return
        normalized_session_id = _clean(session_id)
        if not normalized_session_id:
            return
        binding = resolve_interaction_binding(
            surface=surface or channel_type,
            channel_type=channel_type,
            conversation_id=conversation_id,
            default_surface=None,
        )
        if binding.entrance != "remote" or not binding.channel_type or not binding.conversation_id:
            return
        binding_key = f"{binding.channel_type}|{binding.conversation_id}"
        self._binding_store.set(
            binding_key=binding_key,
            session_id=normalized_session_id,
            workspace_dir=_clean(workspace_dir) or None,
            channel_type=binding.channel_type,
            conversation_id=binding.conversation_id,
        )
```

---

## 四、绑定键格式

```
binding_key = "{channel_type}|{conversation_id}"

示例:
- "slack|C12345678"
- "discord|123456789"
- "telegram|-1001234567890"
- "wechat|wx_abc123"
```

---

## 五、绑定存储文件格式

```json
{
  "bindings": {
    "slack|C12345678": {
      "binding_key": "slack|C12345678",
      "session_id": "default",
      "channel_type": "slack",
      "conversation_id": "C12345678",
      "workspace_dir": "/path/to/workspace",
      "updated_at": "2026-05-11T10:00:00Z"
    },
    "discord|123456789": {
      "binding_key": "discord|123456789",
      "session_id": "session_abc",
      "channel_type": "discord",
      "conversation_id": "123456789",
      "workspace_dir": "/path/to/workspace",
      "updated_at": "2026-05-11T11:00:00Z"
    }
  }
}
```

---

## 六、绑定解析流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    Binding Resolution Flow                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Input: surface, channel_type, conversation_id                  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  1. Check explicit_session_id                            │   │
│  │     - If provided, return directly                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  2. Check dry_run                                        │   │
│  │     - If true, return None                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  3. Resolve interaction binding                          │   │
│  │     - Check entrance == "remote"                         │   │
│  │     - Check channel_type and conversation_id             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  4. Build binding_key                                    │   │
│  │     - "{channel_type}|{conversation_id}"                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  5. Lookup in binding_store                              │   │
│  │     - Return session_id or None                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Output: session_id | None                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 七、常量

```python
DEFAULT_SESSION_ID = "default"
DEFAULT_SESSION_TITLE = "Session 1"

def is_default_session_id(session_id: object) -> bool:
    """Check if session ID is default."""
    return " ".join(str(session_id or "").split()) == DEFAULT_SESSION_ID
```

---

## 八、文件位置

```
src/mini_agent/session/
├── bindings.py                  # 本文档所述组件
```

---

## 九、验收标准

- [x] 支持绑定存储
- [x] 支持绑定解析
- [x] 支持绑定持久化
- [x] 支持远程通道绑定

---

## 十、依赖关系

- 依赖: runtime/support/interaction_surface
- 被依赖: application/, transport/