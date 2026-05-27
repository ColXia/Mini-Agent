# Token 统计开发文档

**模块**: model_manager
**优先级**: P1
**预估时间**: 1 天

---

## 一、功能概述

Token 统计负责：
- 记录每次调用的 Token 消耗
- 成本估算
- 统计汇总
- 批量写入

---

## 二、数据结构

```python
# src/mini_agent/model_manager/token_stats.py

from dataclasses import dataclass, field
from collections import deque
from typing import Any
from pathlib import Path
from datetime import datetime, timezone
import time
import json


@dataclass(frozen=True)
class TokenUsageRecord:
    """Token 使用记录"""
    model_config_id: str
    provider_id: str
    model_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float
    timestamp: str
    is_probe: bool = False  # 是否为探测请求


@dataclass(frozen=True)
class TokenUsageView:
    """Token 消耗视图"""
    model_config_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    context_window: int
    usage_ratio: float
    remaining_tokens: int


@dataclass
class PricingConfig:
    """定价配置"""
    input_price_per_1k: float
    output_price_per_1k: float
    currency: str = "USD"
    note: str = ""


class TokenStatsManager:
    """Token 统计管理"""
    
    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or Path.home() / ".mini-agent"
        self.usage_file = self.config_dir / "token_usage.json"
        
        # 内存缓存
        self._current_session: dict[str, int] = {}  # config_id -> total_tokens
        self._recent_records: deque[TokenUsageRecord] = deque(maxlen=100)
        
        # 批量写入缓冲
        self._buffer: list[TokenUsageRecord] = []
        self._last_flush = time.time()
        self._flush_interval = 60  # 60 秒
        
        # 定价配置
        self._pricing: dict[str, PricingConfig] = {}
        
        self._load()
    
    def record_usage(
        self,
        model_config_id: str,
        provider_id: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        is_probe: bool = False,
    ) -> TokenUsageRecord:
        """记录 Token 使用
        
        Args:
            model_config_id: 模型配置 ID
            provider_id: Provider ID
            model_id: 模型 ID
            input_tokens: 输入 Token 数
            output_tokens: 输出 Token 数
            is_probe: 是否为探测请求 (不计入统计)
        
        Returns:
            Token 使用记录
        """
        # 计算成本
        pricing = self._pricing.get(f"{provider_id}:{model_id}")
        if pricing:
            input_cost = (input_tokens / 1000) * pricing.input_price_per_1k
            output_cost = (output_tokens / 1000) * pricing.output_price_per_1k
        else:
            input_cost = 0.0
            output_cost = 0.0
        
        record = TokenUsageRecord(
            model_config_id=model_config_id,
            provider_id=provider_id,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=input_cost + output_cost,
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_probe=is_probe,
        )
        
        # 更新内存缓存
        if not is_probe:
            self._current_session[model_config_id] = (
                self._current_session.get(model_config_id, 0) + record.total_tokens
            )
            self._recent_records.append(record)
            self._buffer.append(record)
            self._maybe_flush()
        
        return record
    
    def get_usage(self, model_config_id: str, context_window: int = 200000) -> TokenUsageView:
        """获取当前会话使用情况"""
        total = self._current_session.get(model_config_id, 0)
        
        return TokenUsageView(
            model_config_id=model_config_id,
            input_tokens=0,  # 会话级别不区分输入输出
            output_tokens=0,
            total_tokens=total,
            context_window=context_window,
            usage_ratio=total / context_window if context_window > 0 else 0,
            remaining_tokens=max(0, context_window - total),
        )
    
    def set_pricing(
        self,
        provider_id: str,
        model_id: str,
        input_price_per_1k: float,
        output_price_per_1k: float,
        currency: str = "USD",
        note: str = "",
    ) -> None:
        """设置定价"""
        key = f"{provider_id}:{model_id}"
        self._pricing[key] = PricingConfig(
            input_price_per_1k=input_price_per_1k,
            output_price_per_1k=output_price_per_1k,
            currency=currency,
            note=note,
        )
        self._save_pricing()
    
    def get_pricing(self, provider_id: str, model_id: str) -> PricingConfig | None:
        """获取定价"""
        key = f"{provider_id}:{model_id}"
        return self._pricing.get(key)
    
    def get_summary(
        self,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        """获取统计汇总"""
        # 从文件读取汇总
        data = self._read_usage_file()
        summaries = data.get("summaries", {})
        
        if provider_id and model_id:
            key = f"{provider_id}:{model_id}"
            return summaries.get(key, {})
        
        return summaries
    
    def reset_session(self, model_config_id: str | None = None) -> None:
        """重置会话统计"""
        if model_config_id:
            self._current_session.pop(model_config_id, None)
        else:
            self._current_session.clear()
    
    # === 批量写入 ===
    
    def _maybe_flush(self) -> None:
        """检查是否需要刷新"""
        if time.time() - self._last_flush >= self._flush_interval:
            self._flush()
    
    def _flush(self) -> None:
        """刷新到文件"""
        if not self._buffer:
            return
        
        data = self._read_usage_file()
        
        # 添加记录
        for record in self._buffer:
            data["records"].append({
                "model_config_id": record.model_config_id,
                "provider_id": record.provider_id,
                "model_id": record.model_id,
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "total_tokens": record.total_tokens,
                "input_cost": record.input_cost,
                "output_cost": record.output_cost,
                "total_cost": record.total_cost,
                "timestamp": record.timestamp,
                "is_probe": record.is_probe,
            })
            
            # 更新汇总
            key = f"{record.provider_id}:{record.model_id}"
            if key not in data["summaries"]:
                data["summaries"][key] = {
                    "total_requests": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_cost": 0.0,
                }
            
            data["summaries"][key]["total_requests"] += 1
            data["summaries"][key]["total_input_tokens"] += record.input_tokens
            data["summaries"][key]["total_output_tokens"] += record.output_tokens
            data["summaries"][key]["total_cost"] += record.total_cost
        
        self._write_usage_file(data)
        self._buffer.clear()
        self._last_flush = time.time()
    
    # === 存储 ===
    
    def _load(self) -> None:
        """加载配置"""
        self._load_pricing()
    
    def _load_pricing(self) -> None:
        """加载定价配置"""
        data = self._read_usage_file()
        for key, pricing in data.get("pricing", {}).items():
            self._pricing[key] = PricingConfig(**pricing)
    
    def _save_pricing(self) -> None:
        """保存定价配置"""
        data = self._read_usage_file()
        data["pricing"] = {
            key: {
                "input_price_per_1k": p.input_price_per_1k,
                "output_price_per_1k": p.output_price_per_1k,
                "currency": p.currency,
                "note": p.note,
            }
            for key, p in self._pricing.items()
        }
        self._write_usage_file(data)
    
    def _read_usage_file(self) -> dict[str, Any]:
        """读取使用文件"""
        if not self.usage_file.exists():
            return {"records": [], "summaries": {}, "pricing": {}}
        
        with open(self.usage_file, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def _write_usage_file(self, data: dict[str, Any]) -> None:
        """写入使用文件"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        with open(self.usage_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
```

---

## 三、测试用例

```python
# tests/model_manager/test_token_stats.py

import pytest
from pathlib import Path
import tempfile

from mini_agent.model_manager.token_stats import TokenStatsManager


class TestTokenStatsManager:
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)
    
    @pytest.fixture
    def manager(self, temp_dir):
        return TokenStatsManager(config_dir=temp_dir)
    
    def test_record_usage(self, manager):
        """测试记录使用"""
        record = manager.record_usage(
            model_config_id="test-1",
            provider_id="anthropic",
            model_id="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
        )
        
        assert record.total_tokens == 150
        assert record.is_probe is False
    
    def test_probe_not_counted(self, manager):
        """测试探测请求不计入"""
        manager.record_usage(
            model_config_id="test-1",
            provider_id="test",
            model_id="test-model",
            input_tokens=100,
            output_tokens=50,
            is_probe=True,
        )
        
        usage = manager.get_usage("test-1")
        assert usage.total_tokens == 0
    
    def test_pricing(self, manager):
        """测试定价"""
        manager.set_pricing(
            provider_id="anthropic",
            model_id="claude-sonnet-4-6",
            input_price_per_1k=0.003,
            output_price_per_1k=0.015,
        )
        
        record = manager.record_usage(
            model_config_id="test-1",
            provider_id="anthropic",
            model_id="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
        )
        
        assert record.input_cost == 0.003
        assert record.output_cost == 0.0075
        assert record.total_cost == 0.0105
    
    def test_session_usage(self, manager):
        """测试会话统计"""
        manager.record_usage("test-1", "p", "m", 100, 50)
        manager.record_usage("test-1", "p", "m", 200, 100)
        
        usage = manager.get_usage("test-1", context_window=1000)
        
        assert usage.total_tokens == 450
        assert usage.usage_ratio == 0.45
    
    def test_reset_session(self, manager):
        """测试重置会话"""
        manager.record_usage("test-1", "p", "m", 100, 50)
        
        manager.reset_session("test-1")
        
        usage = manager.get_usage("test-1")
        assert usage.total_tokens == 0
```

---

## 四、验收标准

- [ ] Token 使用记录正确
- [ ] 成本估算正确
- [ ] 探测请求不计入统计
- [ ] 批量写入正常
- [ ] 测试覆盖率 >= 80%

---

## 五、依赖关系

- 无前置依赖
- 被依赖: ModelServiceImpl
