# 能力探测开发文档

**模块**: model_manager
**优先级**: P2
**预估时间**: 1 天

---

## 一、功能概述

能力探测负责：
- 探测模型支持的各项能力
- 缓存探测结果
- 上下文窗口大小配置

---

## 二、核心实现

```python
# src/mini_agent/model_manager/capability_probe.py

from dataclasses import dataclass
from typing import Any
from enum import Enum
import asyncio


class DetectionStatus(str, Enum):
    DETECTED = "detected"
    FAILED = "failed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass
class ProbeResult:
    """探测结果"""
    supported: bool | None  # True/False/None(unknown)
    status: DetectionStatus
    error: dict[str, Any] | None = None
    should_abort: bool = False  # 是否终止后续探测


# 预定义上下文窗口大小
CONTEXT_WINDOW_SIZES: dict[str, int] = {
    "claude-opus-4-7": 200000,
    "claude-sonnet-4-6": 200000,
    "claude-haiku-4-5": 200000,
    "gpt-4o": 128000,
    "gpt-4-turbo": 128000,
    "gemini-2.5-pro": 1048576,
}

DEFAULT_CONTEXT_WINDOW = 4096


class CapabilityProbeService:
    """能力探测服务"""
    
    def __init__(self, registry: "ModelRegistryStore"):
        self.registry = registry
    
    async def probe_model(
        self,
        model_id: str,
        provider_id: str,
        force: bool = False,
    ) -> dict[str, Any]:
        """探测模型能力"""
        key = f"{provider_id}:{model_id}"
        
        # 检查已有结果
        if not force:
            existing = self.registry.get_capabilities(provider_id, model_id)
            if existing and existing.get("detection_status") == DetectionStatus.DETECTED:
                return existing
        
        # 执行探测
        capabilities = {}
        errors = []
        
        for capability in ["vision", "streaming", "tools", "structured_output", "extended_thinking", "audio"]:
            result = await self._probe_capability(model_id, provider_id, capability)
            
            if result.should_abort:
                # 认证/连接失败，终止探测
                return {
                    "model_id": model_id,
                    "provider_id": provider_id,
                    "capabilities": {},
                    "limits": {},
                    "detection_status": DetectionStatus.FAILED,
                    "error": result.error,
                }
            
            capabilities[capability] = result.supported
            if result.error:
                errors.append(result.error)
            
            # 探测间隔
            await asyncio.sleep(1)
        
        # 确定状态
        if errors:
            status = DetectionStatus.PARTIAL if any(capabilities.values()) else DetectionStatus.FAILED
        else:
            status = DetectionStatus.DETECTED
        
        result = {
            "model_id": model_id,
            "provider_id": provider_id,
            "capabilities": capabilities,
            "limits": {
                "max_context_tokens": CONTEXT_WINDOW_SIZES.get(model_id, DEFAULT_CONTEXT_WINDOW),
            },
            "detection_status": status,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # 保存
        self.registry.set_capabilities(provider_id, model_id, result)
        
        return result
    
    async def _probe_capability(
        self,
        model_id: str,
        provider_id: str,
        capability: str,
    ) -> ProbeResult:
        """探测单个能力"""
        # TODO: 实现具体探测逻辑
        # 参考 v11.6_model_service_plan.md 第十一节
        
        return ProbeResult(supported=True, status=DetectionStatus.DETECTED)
```

---

## 三、验收标准

- [ ] 6 种能力探测正常
- [ ] 探测结果缓存正确
- [ ] 错误分支处理正确

---

## 四、依赖关系

- 依赖: ModelRegistry
- 被依赖: ModelServiceImpl
