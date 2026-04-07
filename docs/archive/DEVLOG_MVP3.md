# MVP3 开发日志: 编程代理基础

> Started: 2026-04-05
> Status: Completed
> Developer: Claude (Opencode)

---

## 一、目标

实现 Agent 安全执行代码的能力，包括沙箱和工具构建器。

---

## 二、任务清单

- [x] T3.1 创建 `mini_agent/code_agent/` 目录结构
- [x] T3.2 实现 `sandbox/windows.py` - Windows 沙箱
- [x] T3.3 实现 `tools/builder.py` - DeclarativeTool 基类
- [x] T3.4 实现 `coordinator.py` - 协调器
- [x] T3.5 实现 `permissions/` - 权限系统
- [x] T3.6 测试验证

---

## 三、开发记录

### 2026-04-05 开发会话

#### 步骤 1: 检查现有实现 ✅

**发现**:
1. ✅ `mini_agent/code_agent/` 目录已存在且完整实现
2. ✅ `WindowsRestrictedSandbox` - Windows 沙箱已实现
3. ✅ `DeclarativeTool` - 声明式工具基类已实现
4. ✅ `MiniCoordinator` - 协调器已实现
5. ✅ `ApprovalEngine` - 审批引擎已实现
6. ✅ `LayeredContextCompactor` - 上下文压缩已实现
7. ✅ `TurnScheduler` - 调度器已实现

#### 步骤 2: 验证测试 ✅

**测试结果**:
```
tests/test_code_agent_sandbox.py::test_extract_domains_from_command_detects_urls_and_hosts PASSED
tests/test_code_agent_sandbox.py::test_network_policy_allowlist_blocks_unknown_domain PASSED
tests/test_code_agent_sandbox.py::test_windows_restricted_sandbox_blocks_elevated_command PASSED
tests/test_code_agent_sandbox.py::test_windows_restricted_sandbox_blocks_disallowed_network_domain PASSED
tests/test_code_agent_sandbox.py::test_windows_restricted_sandbox_transforms_safe_command PASSED
tests/test_code_agent_sandbox.py::test_sandbox_manager_selects_windows_backend_and_transforms PASSED
tests/test_code_agent_sandbox.py::test_sandbox_manager_unrestricted_mode_uses_passthrough_backend PASSED
tests/test_code_agent_tools.py::test_builder_from_tool_infers_read_contract PASSED
tests/test_code_agent_tools.py::test_invocation_validate_rejects_missing_required PASSED
tests/test_code_agent_tools.py::test_invocation_should_confirm_for_write_tool PASSED
tests/test_code_agent_tools.py::test_invocation_tool_locations_extracts_path PASSED
tests/test_code_agent_tools.py::test_invocation_execute_applies_result_size_limit PASSED
tests/test_code_agent_tools.py::test_runtime_adapter_path_executes_wrapped_tool PASSED
tests/test_code_agent_coordinator.py::test_coordinator_runs_staged_plan_and_emits_progress PASSED
tests/test_code_agent_coordinator.py::test_coordinator_stops_next_stages_on_failure PASSED
tests/test_code_agent_coordinator.py::test_coordinator_respects_worker_concurrency_limit PASSED
```

#### 步骤 3: MVP3 完成状态

**已完成**:
- [x] Windows 沙箱 (`sandbox/windows.py`)
- [x] 网络策略 (`sandbox/network.py`)
- [x] 声明式工具 (`tools/builder.py`)
- [x] 协调器 (`coordinator.py`)
- [x] 权限系统 (`permissions/`)
- [x] 上下文压缩 (`context_compression.py`)
- [x] 调度器 (`scheduler.py`)
- [x] 单元测试覆盖

**MVP3 状态**: ✅ 完成

---

## 四、模块结构

```
mini_agent/code_agent/
├── __init__.py              # 模块导出
├── sandbox/
│   ├── __init__.py          # 沙箱入口
│   ├── windows.py           # Windows 沙箱
│   ├── network.py           # 网络策略
│   └── manager.py           # 沙箱管理器
├── tools/
│   ├── __init__.py          # 工具入口
│   ├── builder.py           # DeclarativeTool 构建器
│   ├── attributes.py        # 工具属性
│   ├── invocation.py        # 工具调用
│   └── runtime_adapter.py   # 运行时适配器
├── permissions/
│   ├── __init__.py          # 权限入口
│   ├── policy.py            # 权限策略
│   └── approval.py          # 审批引擎
├── coordinator.py           # 多阶段协调器
├── context_compression.py   # 上下文压缩
├── scheduler.py             # 调度器
├── agent_loop.py            # Agent 循环
├── context.py               # 上下文管理
├── output_masking.py        # 输出脱敏
├── mcp_client.py            # MCP 客户端
└── mcp_tools.py             # MCP 工具
```

---

## 五、验收标准

```python
# Windows 沙箱
from mini_agent.code_agent import WindowsRestrictedSandbox, WindowsSandboxPolicy
policy = WindowsSandboxPolicy.from_workspace(".")
sandbox = WindowsRestrictedSandbox(policy)
result = sandbox.transform("Get-ChildItem")

# 声明式工具
from mini_agent.code_agent import DeclarativeTool, ToolBuilder
tool = ToolBuilder.from_tool(my_tool)
invocation = tool.build({"path": "/tmp/test"})
result = await invocation.execute()
```

---

## 六、后续迭代增强

- [ ] Linux 沙箱支持
- [ ] 容器沙箱支持
- [ ] 反向 Token 预算优化
- [ ] 完整 MCP OAuth
