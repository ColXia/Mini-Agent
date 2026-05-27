# 模型别名与显示名称开发文档

**模块**: model_manager
**优先级**: P2
**预估时间**: 0.5 天

---

## 一、功能概述

模型别名负责：
- 模型别名解析 (如 "opus" → "claude-opus-4-7")
- 显示名称映射

---

## 二、核心实现

```python
# src/mini_agent/model_manager/model_alias.py

from dataclasses import dataclass


# 预定义别名
DEFAULT_ALIASES: dict[str, str] = {
    "opus": "claude-opus-4-7",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
    "best": "claude-opus-4-7",
    "fast": "claude-haiku-4-5",
    "gpt4": "gpt-4o",
    "gpt": "gpt-4o",
}

# 预定义显示名称
DEFAULT_DISPLAY_NAMES: dict[str, str] = {
    "claude-opus-4-7": "Opus 4.7",
    "claude-opus-4-6": "Opus 4.6",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "claude-sonnet-4-5": "Sonnet 4.5",
    "claude-haiku-4-5": "Haiku 4.5",
    "gpt-4o": "GPT-4o",
    "gpt-4-turbo": "GPT-4 Turbo",
}


class AliasResolver:
    """别名解析器"""
    
    def __init__(self, registry: "ModelRegistryStore"):
        self.registry = registry
    
    def resolve(self, alias_or_id: str) -> str:
        """解析别名到模型 ID
        
        Args:
            alias_or_id: 别名或模型 ID
        
        Returns:
            模型 ID
        """
        # 1. 检查用户自定义别名
        custom = self.registry.resolve_alias(alias_or_id)
        if custom:
            return custom
        
        # 2. 检查预定义别名
        normalized = alias_or_id.lower().strip()
        if normalized in DEFAULT_ALIASES:
            return DEFAULT_ALIASES[normalized]
        
        # 3. 返回原值 (假设是模型 ID)
        return alias_or_id
    
    def is_alias(self, value: str) -> bool:
        """检查是否为别名"""
        normalized = value.lower().strip()
        return normalized in DEFAULT_ALIASES or self.registry.resolve_alias(value) is not None
    
    def list_aliases(self) -> list[dict[str, str]]:
        """列出所有别名"""
        result = []
        
        # 预定义别名
        for alias, model_id in DEFAULT_ALIASES.items():
            result.append({
                "alias": alias,
                "model_id": model_id,
                "display_name": DEFAULT_DISPLAY_NAMES.get(model_id, model_id),
                "source": "preset",
            })
        
        # 用户自定义别名
        for alias, model_id in self.registry._registry.aliases.items():
            if alias not in DEFAULT_ALIASES:
                result.append({
                    "alias": alias,
                    "model_id": model_id,
                    "display_name": DEFAULT_DISPLAY_NAMES.get(model_id, model_id),
                    "source": "custom",
                })
        
        return result


def get_display_name(model_id: str) -> str:
    """获取显示名称"""
    return DEFAULT_DISPLAY_NAMES.get(model_id, model_id)
```

---

## 三、验收标准

- [ ] 别名解析正确
- [ ] 显示名称映射正确
- [ ] 支持用户自定义别名

---

## 四、依赖关系

- 依赖: ModelRegistry
- 被依赖: ModelServiceImpl
