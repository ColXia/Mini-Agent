# 健康监控与熔断器开发文档

**模块**: model_manager
**优先级**: P1
**预估时间**: 2 天

---

## 一、功能概述

健康监控与熔断器负责：
- 监控 API 调用成功率和延迟
- 熔断器状态管理
- 回调通知机制

---

## 二、数据结构

### 2.1 健康监控

```python
# src/mini_agent/model_manager/health_monitor.py

from dataclasses import dataclass, field
from collections import deque
from typing import Any
import time


@dataclass
class HealthMetrics:
    """健康指标"""
    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    latency_samples: deque[float] = field(default_factory=lambda: deque(maxlen=100))
    last_success_time: float | None = None
    last_failure_time: float | None = None
    last_error: dict[str, Any] | None = None


@dataclass(frozen=True)
class HealthStatusView:
    """健康状态视图"""
    model_config_id: str
    is_healthy: bool
    success_rate: float
    avg_latency_ms: int
    p99_latency_ms: int
    total_requests: int
    recent_failures: int
    last_success_time: str | None
    last_failure_time: str | None


class HealthMonitor:
    """健康监控"""
    
    def __init__(self):
        self._metrics: dict[str, HealthMetrics] = {}
    
    def record_request(
        self,
        model_config_id: str,
        latency_ms: float,
        success: bool,
        error: dict[str, Any] | None = None,
    ) -> None:
        """记录请求结果"""
        if model_config_id not in self._metrics:
            self._metrics[model_config_id] = HealthMetrics()
        
        metrics = self._metrics[model_config_id]
        metrics.total_requests += 1
        
        if success:
            metrics.success_count += 1
            metrics.last_success_time = time.time()
        else:
            metrics.failure_count += 1
            metrics.last_failure_time = time.time()
            metrics.last_error = error
        
        metrics.latency_samples.append(latency_ms)
    
    def get_status(self, model_config_id: str) -> HealthStatusView:
        """获取健康状态"""
        metrics = self._metrics.get(model_config_id, HealthMetrics())
        
        success_rate = (
            metrics.success_count / metrics.total_requests
            if metrics.total_requests > 0
            else 1.0
        )
        
        latencies = list(metrics.latency_samples)
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0
        
        return HealthStatusView(
            model_config_id=model_config_id,
            is_healthy=success_rate >= 0.5,  # 成功率 >= 50% 视为健康
            success_rate=success_rate,
            avg_latency_ms=int(avg_latency),
            p99_latency_ms=int(p99_latency),
            total_requests=metrics.total_requests,
            recent_failures=metrics.failure_count,
            last_success_time=self._format_time(metrics.last_success_time),
            last_failure_time=self._format_time(metrics.last_failure_time),
        )
    
    def get_last_error(self, model_config_id: str) -> dict[str, Any] | None:
        """获取最近错误"""
        metrics = self._metrics.get(model_config_id)
        return metrics.last_error if metrics else None
    
    def _format_time(self, timestamp: float | None) -> str | None:
        """格式化时间"""
        if timestamp is None:
            return None
        from datetime import datetime, timezone
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
```

### 2.2 熔断器

```python
# src/mini_agent/model_manager/circuit_breaker.py

from dataclasses import dataclass
from enum import Enum
import time
import uuid


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class BreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: float = 60.0
    half_open_max_calls: int = 3


@dataclass
class BreakerState:
    """熔断器状态"""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float | None = None
    last_failure_reason: str | None = None
    half_open_calls: int = 0


@dataclass(frozen=True)
class BreakerStatusView:
    """熔断状态视图"""
    model_config_id: str
    is_open: bool
    state: CircuitState
    failure_count: int
    last_failure_reason: str | None
    reset_at: str | None


class CircuitBreakerManager:
    """熔断器管理"""
    
    def __init__(self):
        self._states: dict[str, BreakerState] = {}
        self._configs: dict[str, BreakerConfig] = {}
    
    def set_config(self, model_config_id: str, config: BreakerConfig) -> None:
        """设置配置"""
        self._configs[model_config_id] = config
    
    def get_config(self, model_config_id: str) -> BreakerConfig:
        """获取配置"""
        return self._configs.get(model_config_id, BreakerConfig())
    
    def should_allow(self, model_config_id: str) -> bool:
        """判断是否允许请求"""
        if model_config_id not in self._states:
            self._states[model_config_id] = BreakerState()
        
        state = self._states[model_config_id]
        config = self.get_config(model_config_id)
        
        if state.state == CircuitState.CLOSED:
            return True
        
        if state.state == CircuitState.OPEN:
            # 检查是否可以进入半开状态
            if state.last_failure_time:
                elapsed = time.time() - state.last_failure_time
                if elapsed >= config.timeout_seconds:
                    state.state = CircuitState.HALF_OPEN
                    state.half_open_calls = 0
                    return True
            return False
        
        if state.state == CircuitState.HALF_OPEN:
            # 半开状态允许有限请求
            return state.half_open_calls < config.half_open_max_calls
        
        return False
    
    def record_success(self, model_config_id: str) -> None:
        """记录成功"""
        state = self._states.get(model_config_id, BreakerState())
        config = self.get_config(model_config_id)
        
        state.success_count += 1
        state.failure_count = 0
        
        if state.state == CircuitState.HALF_OPEN:
            if state.success_count >= config.success_threshold:
                # 恢复正常
                state.state = CircuitState.CLOSED
                state.success_count = 0
    
    def record_failure(self, model_config_id: str, reason: str) -> None:
        """记录失败"""
        state = self._states.get(model_config_id, BreakerState())
        config = self.get_config(model_config_id)
        
        state.failure_count += 1
        state.last_failure_time = time.time()
        state.last_failure_reason = reason
        state.success_count = 0
        
        if state.state == CircuitState.HALF_OPEN:
            # 半开状态失败立即熔断
            state.state = CircuitState.OPEN
        elif state.failure_count >= config.failure_threshold:
            # 达到阈值熔断
            state.state = CircuitState.OPEN
    
    def get_status(self, model_config_id: str) -> BreakerStatusView:
        """获取状态"""
        state = self._states.get(model_config_id, BreakerState())
        config = self.get_config(model_config_id)
        
        reset_at = None
        if state.state == CircuitState.OPEN and state.last_failure_time:
            reset_at = state.last_failure_time + config.timeout_seconds
        
        return BreakerStatusView(
            model_config_id=model_config_id,
            is_open=state.state == CircuitState.OPEN,
            state=state.state,
            failure_count=state.failure_count,
            last_failure_reason=state.last_failure_reason,
            reset_at=self._format_time(reset_at),
        )
    
    def reset(self, model_config_id: str) -> None:
        """重置熔断器"""
        self._states[model_config_id] = BreakerState()
    
    def _format_time(self, timestamp: float | None) -> str | None:
        if timestamp is None:
            return None
        from datetime import datetime, timezone
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
```

---

## 三、测试用例

```python
# tests/model_manager/test_health_breaker.py

import pytest
from mini_agent.model_manager.health_monitor import HealthMonitor
from mini_agent.model_manager.circuit_breaker import (
    CircuitBreakerManager,
    CircuitState,
    BreakerConfig,
)


class TestHealthMonitor:
    
    def test_record_success(self):
        """测试记录成功"""
        monitor = HealthMonitor()
        
        monitor.record_request("test-1", 100.0, success=True)
        
        status = monitor.get_status("test-1")
        assert status.is_healthy is True
        assert status.success_rate == 1.0
    
    def test_record_failure(self):
        """测试记录失败"""
        monitor = HealthMonitor()
        
        monitor.record_request("test-1", 100.0, success=False, error={"type": "timeout"})
        
        status = monitor.get_status("test-1")
        assert status.success_rate == 0.0
    
    def test_mixed_requests(self):
        """测试混合请求"""
        monitor = HealthMonitor()
        
        for _ in range(7):
            monitor.record_request("test-1", 100.0, success=True)
        for _ in range(3):
            monitor.record_request("test-1", 100.0, success=False)
        
        status = monitor.get_status("test-1")
        assert status.success_rate == 0.7


class TestCircuitBreakerManager:
    
    def test_closed_allows_requests(self):
        """测试关闭状态允许请求"""
        breaker = CircuitBreakerManager()
        
        assert breaker.should_allow("test-1") is True
    
    def test_trips_on_failures(self):
        """测试失败后熔断"""
        breaker = CircuitBreakerManager()
        breaker.set_config("test-1", BreakerConfig(failure_threshold=3))
        
        for _ in range(3):
            breaker.record_failure("test-1", "error")
        
        assert breaker.should_allow("test-1") is False
        assert breaker.get_status("test-1").state == CircuitState.OPEN
    
    def test_half_open_to_closed(self):
        """测试半开恢复"""
        breaker = CircuitBreakerManager()
        breaker.set_config("test-1", BreakerConfig(
            failure_threshold=1,
            success_threshold=2,
            timeout_seconds=0.1,
        ))
        
        # 触发熔断
        breaker.record_failure("test-1", "error")
        
        # 等待超时
        import time
        time.sleep(0.2)
        
        # 应该进入半开状态
        assert breaker.should_allow("test-1") is True
        
        # 记录成功
        breaker.record_success("test-1")
        breaker.record_success("test-1")
        
        # 应该恢复
        assert breaker.get_status("test-1").state == CircuitState.CLOSED
    
    def test_reset(self):
        """测试重置"""
        breaker = CircuitBreakerManager()
        breaker.record_failure("test-1", "error")
        breaker.record_failure("test-1", "error")
        breaker.record_failure("test-1", "error")
        
        breaker.reset("test-1")
        
        assert breaker.should_allow("test-1") is True
```

---

## 四、验收标准

- [ ] 健康监控记录请求成功/失败
- [ ] 健康监控计算成功率和延迟
- [ ] 熔断器状态转换正确
- [ ] 熔断器配置可自定义
- [ ] 测试覆盖率 >= 80%

---

## 五、依赖关系

- 无前置依赖
- 被依赖: ModelServiceImpl
