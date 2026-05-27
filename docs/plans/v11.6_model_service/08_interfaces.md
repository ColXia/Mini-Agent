# 接口定义开发文档

**模块**: model_manager
**优先级**: P0
**预估时间**: 2 天

---

## 一、功能概述

接口层是模型服务对外的统一入口，负责：
- 定义 Agent 侧可访问的接口
- 实现接口适配器
- 提供视图对象

---

## 二、接口定义

### 2.1 视图对象

```python
# src/mini_agent/model_manager/views.py

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ModelBindingView:
    """Agent 可见的模型绑定视图"""
    agent_id: str
    config_id: str
    model_id: str
    display_name: str
    provider_id: str
    status: str  # active / orphaned


@dataclass(frozen=True, slots=True)
class ModelOptionView:
    """可用模型选项"""
    config_id: str
    model_id: str
    display_name: str
    provider_name: str
    status: str


@dataclass(frozen=True, slots=True)
class ModelCapabilitiesView:
    """Agent 可见的模型能力视图"""
    model_id: str
    config_id: str
    
    # 能力支持
    supports_vision: bool
    supports_streaming: bool
    supports_tools: bool
    supports_structured_output: bool
    supports_thinking: bool
    supports_audio: bool
    
    # 限制
    max_context_tokens: int
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class HealthStatusView:
    """健康状态视图"""
    model_config_id: str
    is_healthy: bool
    success_rate: float
    avg_latency_ms: int
    last_success_time: str | None
    last_failure_time: str | None


@dataclass(frozen=True, slots=True)
class BreakerStatusView:
    """熔断状态视图"""
    model_config_id: str
    is_open: bool
    failure_count: int
    last_failure_reason: str | None
    reset_at: str | None


@dataclass(frozen=True, slots=True)
class ErrorDetailView:
    """错误详情视图"""
    error_type: str
    error_code: str | None
    error_message: str
    suggestion: str
    is_retryable: bool
    should_failover: bool
    timestamp: str


@dataclass(frozen=True, slots=True)
class TokenUsageView:
    """Token 消耗视图"""
    model_config_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    context_window: int
    usage_ratio: float
    remaining_tokens: int
```

### 2.2 通知对象

```python
# src/mini_agent/model_manager/notifications.py

from dataclasses import dataclass
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class BreakerNotification:
    """熔断通知"""
    notification_id: str
    provider_id: str
    model_config_id: str
    state: CircuitState
    failure_count: int
    last_failure_reason: str
    reset_at: str | None
    timestamp: str


@dataclass(frozen=True)
class HealthNotification:
    """健康状态变化通知"""
    notification_id: str
    provider_id: str
    model_config_id: str
    is_healthy: bool
    previous_state: str
    success_rate: float
    avg_latency_ms: int
    timestamp: str
```

---

## 三、接口协议

### 3.1 ModelBindingPort

```python
# src/mini_agent/model_manager/interfaces.py

from typing import Protocol


class ModelBindingPort(Protocol):
    """模型绑定相关接口"""
    
    def get_binding(self, agent_id: str) -> ModelBindingView:
        """获取 Agent 当前模型绑定
        
        Args:
            agent_id: Agent ID
        
        Returns:
            模型绑定视图
        
        Raises:
            BindingNotFoundError: Agent 未绑定模型
        """
    
    def switch_model(self, agent_id: str, target: str) -> ModelBindingView:
        """切换模型
        
        Args:
            agent_id: Agent ID
            target: 目标模型 (config_id / alias / model_id)
        
        Returns:
            切换后的绑定视图
        """
    
    def list_available_models(self) -> list[ModelOptionView]:
        """列出可用模型选项
        
        Returns:
            可用模型列表 (仅 status=active)
        """
```

### 3.2 ModelClientPort

```python
class ModelClientPort(Protocol):
    """模型客户端相关接口"""
    
    def get_client(
        self,
        binding: ModelBindingView,
        params_override: dict[str, Any] | None = None,
    ) -> "LLMClient":
        """获取 LLM 客户端
        
        Args:
            binding: 模型绑定视图
            params_override: 覆盖参数 (覆盖模型默认参数)
        
        Returns:
            已配置的 LLM 客户端
        """
    
    def get_capabilities(self, binding: ModelBindingView) -> ModelCapabilitiesView:
        """获取模型能力
        
        Args:
            binding: 模型绑定视图
        
        Returns:
            模型能力视图
        """
```

### 3.3 ModelStatusPort

```python
class ModelStatusPort(Protocol):
    """模型状态查询相关接口"""
    
    def get_health_status(self, model_config_id: str) -> HealthStatusView:
        """获取模型健康状态"""
    
    def get_breaker_status(self, model_config_id: str) -> BreakerStatusView:
        """获取模型熔断状态"""
    
    def get_last_error(self, model_config_id: str) -> ErrorDetailView | None:
        """获取最近一次错误详情"""
    
    def get_token_usage(self, model_config_id: str) -> TokenUsageView:
        """获取 Token 消耗情况"""
```

### 3.4 ModelCallbackPort

```python
from typing import Callable


class ModelCallbackPort(Protocol):
    """模型回调注册相关接口"""
    
    def register_breaker_callback(
        self,
        callback: Callable[[BreakerNotification], None],
    ) -> str:
        """注册熔断触发回调
        
        Args:
            callback: 回调函数
        
        Returns:
            callback_id: 用于取消注册
        """
    
    def register_health_callback(
        self,
        callback: Callable[[HealthNotification], None],
    ) -> str:
        """注册健康状态变化回调"""
    
    def unregister_callback(self, callback_id: str) -> bool:
        """取消注册回调
        
        Returns:
            是否成功取消
        """
    
    def clear_all_callbacks(self) -> None:
        """清除所有回调注册"""
```

---

## 四、接口实现

### 4.1 ModelServiceImpl

```python
# src/mini_agent/model_manager/model_service_impl.py

from dataclasses import dataclass, field
from typing import Callable
import uuid

from .interfaces import (
    ModelBindingPort,
    ModelClientPort,
    ModelStatusPort,
    ModelCallbackPort,
)
from .views import (
    ModelBindingView,
    ModelOptionView,
    ModelCapabilitiesView,
    HealthStatusView,
    BreakerStatusView,
    ErrorDetailView,
    TokenUsageView,
)
from .notifications import BreakerNotification, HealthNotification
from .model_registry import ModelRegistryStore
from .health_monitor import HealthMonitor
from .circuit_breaker import CircuitBreakerManager
from .token_stats import TokenStatsManager
from .model_alias import AliasResolver


@dataclass
class ModelServiceImpl:
    """模型服务实现"""
    
    registry: ModelRegistryStore
    health_monitor: HealthMonitor
    breaker_manager: CircuitBreakerManager
    token_stats: TokenStatsManager
    alias_resolver: AliasResolver
    
    # 回调注册
    _breaker_callbacks: dict[str, Callable[[BreakerNotification], None]] = field(default_factory=dict)
    _health_callbacks: dict[str, Callable[[HealthNotification], None]] = field(default_factory=dict)
    
    # === ModelBindingPort 实现 ===
    
    def get_binding(self, agent_id: str) -> ModelBindingView:
        """获取 Agent 模型绑定"""
        # 从 Agent 绑定存储获取 config_id
        # 这里需要与 Agent 侧交互，暂时返回默认绑定
        configs = self.registry.list_model_configs(status="active")
        if not configs:
            raise ValueError("无可用模型配置")
        
        config = configs[0]
        return self._build_binding_view(config)
    
    def switch_model(self, agent_id: str, target: str) -> ModelBindingView:
        """切换模型"""
        # 解析目标
        config_id = self._resolve_target(target)
        
        config = self.registry.get_model_config(config_id)
        if not config:
            raise ValueError(f"模型配置不存在: {config_id}")
        
        if config.get("status") != "active":
            raise ValueError(f"模型配置不可用: {config_id}")
        
        # 更新 Agent 绑定 (Agent 侧实现)
        # ...
        
        return self._build_binding_view(config)
    
    def list_available_models(self) -> list[ModelOptionView]:
        """列出可用模型"""
        configs = self.registry.list_model_configs(status="active")
        
        options = []
        for config in configs:
            provider = self.registry.get_provider(config.get("provider_id", ""))
            provider_name = provider.get("name", "") if provider else ""
            
            options.append(ModelOptionView(
                config_id=config["config_id"],
                model_id=config["model_id"],
                display_name=config.get("description", config["model_id"]),
                provider_name=provider_name,
                status=config.get("status", "active"),
            ))
        
        return options
    
    # === ModelClientPort 实现 ===
    
    def get_client(self, binding: ModelBindingView, params_override: dict[str, Any] | None = None):
        """获取 LLM 客户端"""
        config = self.registry.get_model_config(binding.config_id)
        if not config:
            raise ValueError(f"模型配置不存在: {binding.config_id}")
        
        provider = self.registry.get_provider(config.get("provider_id", ""))
        if not provider:
            raise ValueError(f"Provider 不存在: {config.get('provider_id')}")
        
        # 获取默认参数
        default_params = self.registry.get_default_params(
            provider["provider_id"],
            config["model_id"],
        ) or {}
        
        # 合并参数
        params = {**default_params}
        if params_override:
            params.update(params_override)
        
        # 构建 LLMClient
        # ... (需要 LLMClient 实现)
        
        return None  # TODO: 返回 LLMClient
    
    def get_capabilities(self, binding: ModelBindingView) -> ModelCapabilitiesView:
        """获取模型能力"""
        config = self.registry.get_model_config(binding.config_id)
        if not config:
            raise ValueError(f"模型配置不存在: {binding.config_id}")
        
        capabilities = self.registry.get_capabilities(
            config.get("provider_id", ""),
            config["model_id"],
        )
        
        if not capabilities:
            # 返回默认能力
            return ModelCapabilitiesView(
                model_id=config["model_id"],
                config_id=binding.config_id,
                supports_vision=False,
                supports_streaming=True,
                supports_tools=True,
                supports_structured_output=False,
                supports_thinking=False,
                supports_audio=False,
                max_context_tokens=4096,
                max_output_tokens=4096,
            )
        
        caps = capabilities.get("capabilities", {})
        limits = capabilities.get("limits", {})
        
        return ModelCapabilitiesView(
            model_id=config["model_id"],
            config_id=binding.config_id,
            supports_vision=caps.get("vision", False),
            supports_streaming=caps.get("streaming", True),
            supports_tools=caps.get("tools", True),
            supports_structured_output=caps.get("structured_output", False),
            supports_thinking=caps.get("extended_thinking", False),
            supports_audio=caps.get("audio", False),
            max_context_tokens=limits.get("max_context_tokens", 4096),
            max_output_tokens=limits.get("max_output_tokens", 4096),
        )
    
    # === ModelStatusPort 实现 ===
    
    def get_health_status(self, model_config_id: str) -> HealthStatusView:
        """获取健康状态"""
        return self.health_monitor.get_status(model_config_id)
    
    def get_breaker_status(self, model_config_id: str) -> BreakerStatusView:
        """获取熔断状态"""
        return self.breaker_manager.get_status(model_config_id)
    
    def get_last_error(self, model_config_id: str) -> ErrorDetailView | None:
        """获取最近错误"""
        return self.health_monitor.get_last_error(model_config_id)
    
    def get_token_usage(self, model_config_id: str) -> TokenUsageView:
        """获取 Token 消耗"""
        return self.token_stats.get_usage(model_config_id)
    
    # === ModelCallbackPort 实现 ===
    
    def register_breaker_callback(
        self,
        callback: Callable[[BreakerNotification], None],
    ) -> str:
        """注册熔断回调"""
        callback_id = str(uuid.uuid4())
        self._breaker_callbacks[callback_id] = callback
        return callback_id
    
    def register_health_callback(
        self,
        callback: Callable[[HealthNotification], None],
    ) -> str:
        """注册健康回调"""
        callback_id = str(uuid.uuid4())
        self._health_callbacks[callback_id] = callback
        return callback_id
    
    def unregister_callback(self, callback_id: str) -> bool:
        """取消注册回调"""
        if callback_id in self._breaker_callbacks:
            del self._breaker_callbacks[callback_id]
            return True
        if callback_id in self._health_callbacks:
            del self._health_callbacks[callback_id]
            return True
        return False
    
    def clear_all_callbacks(self) -> None:
        """清除所有回调"""
        self._breaker_callbacks.clear()
        self._health_callbacks.clear()
    
    # === 内部方法 ===
    
    def _resolve_target(self, target: str) -> str:
        """解析目标为 config_id"""
        # 1. 检查是否是 config_id
        if self.registry.get_model_config(target):
            return target
        
        # 2. 检查是否是别名
        model_id = self.alias_resolver.resolve(target)
        if model_id:
            # 查找对应的 config
            for config in self.registry.list_model_configs(status="active"):
                if config["model_id"] == model_id:
                    return config["config_id"]
        
        raise ValueError(f"无法解析目标: {target}")
    
    def _build_binding_view(self, config: dict[str, Any]) -> ModelBindingView:
        """构建绑定视图"""
        return ModelBindingView(
            agent_id="",  # Agent 侧填充
            config_id=config["config_id"],
            model_id=config["model_id"],
            display_name=config.get("description", config["model_id"]),
            provider_id=config.get("provider_id", ""),
            status=config.get("status", "active"),
        )
    
    def _notify_breaker(self, notification: BreakerNotification) -> None:
        """通知熔断回调"""
        for callback in self._breaker_callbacks.values():
            try:
                callback(notification)
            except Exception:
                pass  # 忽略回调错误
    
    def _notify_health(self, notification: HealthNotification) -> None:
        """通知健康回调"""
        for callback in self._health_callbacks.values():
            try:
                callback(notification)
            except Exception:
                pass
```

---

## 五、测试用例

```python
# tests/model_manager/test_interfaces.py

import pytest
from unittest.mock import Mock, MagicMock

from mini_agent.model_manager.model_service_impl import ModelServiceImpl
from mini_agent.model_manager.views import ModelBindingView


class TestModelServiceImpl:
    
    @pytest.fixture
    def service(self):
        """创建服务实例"""
        registry = Mock()
        health_monitor = Mock()
        breaker_manager = Mock()
        token_stats = Mock()
        alias_resolver = Mock()
        
        return ModelServiceImpl(
            registry=registry,
            health_monitor=health_monitor,
            breaker_manager=breaker_manager,
            token_stats=token_stats,
            alias_resolver=alias_resolver,
        )
    
    def test_list_available_models(self, service):
        """测试列出可用模型"""
        service.registry.list_model_configs.return_value = [
            {
                "config_id": "test-1",
                "model_id": "test-model",
                "provider_id": "provider-1",
                "status": "active",
            }
        ]
        service.registry.get_provider.return_value = {"name": "Test Provider"}
        
        models = service.list_available_models()
        
        assert len(models) == 1
        assert models[0].config_id == "test-1"
    
    def test_register_breaker_callback(self, service):
        """测试注册熔断回调"""
        callback = Mock()
        
        callback_id = service.register_breaker_callback(callback)
        
        assert callback_id != ""
        assert callback_id in service._breaker_callbacks
    
    def test_unregister_callback(self, service):
        """测试取消注册回调"""
        callback = Mock()
        callback_id = service.register_breaker_callback(callback)
        
        result = service.unregister_callback(callback_id)
        
        assert result is True
        assert callback_id not in service._breaker_callbacks
    
    def test_clear_all_callbacks(self, service):
        """测试清除所有回调"""
        service.register_breaker_callback(Mock())
        service.register_health_callback(Mock())
        
        service.clear_all_callbacks()
        
        assert len(service._breaker_callbacks) == 0
        assert len(service._health_callbacks) == 0
```

---

## 六、验收标准

- [ ] 四个接口协议定义完整
- [ ] 视图对象定义完整
- [ ] 通知对象定义完整
- [ ] ModelServiceImpl 实现完整
- [ ] 测试覆盖率 >= 80%

---

## 七、依赖关系

- 依赖: ProviderConfig, ModelRegistry, HealthMonitor, CircuitBreaker, TokenStats, AliasResolver
- 被依赖: Agent Core
