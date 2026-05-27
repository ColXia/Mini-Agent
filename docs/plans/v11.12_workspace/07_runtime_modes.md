# 运行时模式开发文档

**模块**: workspace_runtime/runtime_modes
**优先级**: P1
**预估时间**: 已实现，文档补全

---

## 一、功能概述

运行时模式定义了工作空间的执行环境类型：

- 直接执行模式
- 容器挂载模式
- 隔离副本模式

---

## 二、运行时模式组件

| 组件 | 职责 |
|------|------|
| `WorkspaceRuntimeMode` | 运行时模式枚举 |
| `WorkspaceRuntimeDescriptor` | 运行时描述符 |

---

## 三、核心运行时模式

### 3.1 WorkspaceRuntimeMode

```python
# src/mini_agent/workspace_runtime/runtime_modes.py

class WorkspaceRuntimeMode(str, Enum):
    """Maintained workspace execution modes from the v11.1 baseline."""
    DIRECT = "direct"                     # 直接执行
    CONTAINER_MOUNTED = "container_mounted" # 容器挂载
    ISOLATED_COPY = "isolated_copy"       # 隔离副本
```

### 3.2 WorkspaceRuntimeDescriptor

```python
@dataclass(frozen=True, slots=True)
class WorkspaceRuntimeDescriptor:
    """Compact descriptor for one workspace execution environment."""
    mode: WorkspaceRuntimeMode
    mounted: bool = True      # 是否挂载
    writable: bool = True     # 是否可写
```

---

## 四、运行时模式说明

```
┌─────────────────────────────────────────────────────────────────┐
│                    Runtime Modes                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  DIRECT                                                  │   │
│  │  - 直接在主机文件系统上执行                              │   │
│  │  - 无隔离                                                │   │
│  │  - 最高性能                                              │   │
│  │  - 适用于开发环境                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  CONTAINER_MOUNTED                                       │   │
│  │  - 在容器中执行                                          │   │
│  │  - 工作空间目录挂载到容器                                │   │
│  │  - 提供进程隔离                                          │   │
│  │  - 适用于生产环境                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ISOLATED_COPY                                           │   │
│  │  - 在容器中执行                                          │   │
│  │  - 工作空间副本到容器                                    │   │
│  │  - 提供完整隔离                                          │   │
│  │  - 适用于不可信代码                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、描述符属性

| 属性 | DIRECT | CONTAINER_MOUNTED | ISOLATED_COPY |
|------|--------|-------------------|---------------|
| mounted | N/A | true | false |
| writable | true | true | false |
| 隔离级别 | 无 | 进程 | 完整 |
| 性能 | 最高 | 中等 | 较低 |

---

## 六、文件位置

```
src/mini_agent/workspace_runtime/
├── runtime_modes.py             # 本文档所述组件
```

---

## 七、验收标准

- [x] 支持运行时模式枚举
- [x] 支持运行时描述符

---

## 八、依赖关系

- 依赖: 无
- 被依赖: workspace_executor.py, snapshot_store.py