# 模型参数配置开发文档

**模块**: model_manager
**优先级**: P1
**预估时间**: 1 天

---

## 一、功能概述

模型参数配置负责：
- 同一模型的多个参数配置管理
- 参数合并逻辑

---

## 二、核心实现

```python
# src/mini_agent/model_manager/model_configs.py

from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class ConfigStatus(str, Enum):
    ACTIVE = "active"
    ORPHANED = "orphaned"


@dataclass
class ModelParameterConfig:
    """模型参数配置"""
    config_id: str
    model_id: str
    provider_id: str
    parameters: dict[str, Any]
    description: str = ""
    status: ConfigStatus = ConfigStatus.ACTIVE


# 系统默认参数
SYSTEM_DEFAULT_PARAMS = {
    "temperature": 1.0,
    "top_p": 1.0,
    "max_tokens": 4096,
    "stream": True,
    "timeout": 60.0,
}


def merge_params(
    default_params: dict[str, Any],
    params_override: dict[str, Any] | None,
) -> dict[str, Any]:
    """合并参数
    
    Args:
        default_params: 模型默认参数
        params_override: Agent 覆盖参数
    
    Returns:
        合并后的参数 (覆盖参数优先，未指定的继承默认值)
    """
    if params_override is None:
        return default_params
    
    merged = {**default_params}
    for key, value in params_override.items():
        if value is not None:
            merged[key] = value
    
    return merged
```

---

## 三、验收标准

- [ ] 参数配置 CRUD 正常
- [ ] 参数合并逻辑正确
- [ ] 配置状态管理正确

---

## 四、依赖关系

- 依赖: ModelRegistry
- 被依赖: ModelServiceImpl