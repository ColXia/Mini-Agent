# 模型注册表开发文档

**模块**: model_manager
**优先级**: P0
**预估时间**: 1 天

---

## 一、功能概述

模型注册表是模型服务的统一配置中心，负责：
- 统一存储 Provider、模型配置、能力、定价等信息
- 配置导入导出
- 配置版本迁移

---

## 二、数据结构

### 2.1 ModelRegistry

```python
# src/mini_agent/model_manager/model_registry.py

from dataclasses import dataclass, field
from typing import Any
from pathlib import Path
import json


@dataclass
class ModelRegistry:
    """模型注册表 - 统一配置存储"""
    
    # 版本
    version: str = "1.0"
    
    # Provider 配置
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)
    
    # 模型参数配置
    model_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    
    # 模型默认参数
    default_params: dict[str, dict[str, Any]] = field(default_factory=dict)
    
    # 模型能力
    capabilities: dict[str, dict[str, Any]] = field(default_factory=dict)
    
    # 熔断器配置
    breaker_config: dict[str, dict[str, Any]] = field(default_factory=dict)
    
    # 定价配置
    pricing: dict[str, dict[str, Any]] = field(default_factory=dict)
    
    # 模型别名
    aliases: dict[str, str] = field(default_factory=dict)
    
    # 元数据
    created_at: str = ""
    updated_at: str = ""
```

### 2.2 存储文件结构

```json
{
  "version": "1.0",
  "created_at": "2026-05-11T00:00:00Z",
  "updated_at": "2026-05-11T12:00:00Z",
  
  "providers": {
    "openai-abc123": {
      "name": "我的OpenAI",
      "api_base": "https://api.openai.com/v1",
      "api_key_ref": "PROVIDER_OPENAI_KEY",
      "api_type": "openai",
      "models": ["gpt-4o", "gpt-4"],
      "timeout": 60,
      "priority": 0,
      "enabled": true
    }
  },
  
  "model_configs": {
    "sonnet-code": {
      "config_id": "sonnet-code",
      "model_id": "claude-sonnet-4-6",
      "provider_id": "anthropic-def456",
      "status": "active",
      "parameters": {
        "temperature": 0.2,
        "max_tokens": 4096
      },
      "description": "代码助手专用"
    }
  },
  
  "default_params": {
    "anthropic:claude-sonnet-4-6": {
      "temperature": 1.0,
      "max_tokens": 8192,
      "stream": true,
      "timeout": 60.0
    }
  },
  
  "capabilities": {
    "anthropic:claude-sonnet-4-6": {
      "model_id": "claude-sonnet-4-6",
      "provider_id": "anthropic",
      "capabilities": {
        "vision": true,
        "streaming": true,
        "tools": true
      },
      "limits": {
        "max_context_tokens": 200000,
        "max_output_tokens": 16384
      },
      "detection_status": "detected",
      "detected_at": "2026-05-11T10:00:00Z"
    }
  },
  
  "breaker_config": {
    "anthropic-def456": {
      "failure_threshold": 5,
      "success_threshold": 3,
      "timeout_seconds": 60.0
    }
  },
  
  "pricing": {
    "anthropic:claude-sonnet-4-6": {
      "input_price_per_1k": 0.003,
      "output_price_per_1k": 0.015,
      "currency": "USD"
    }
  },
  
  "aliases": {
    "opus": "claude-opus-4-7",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5"
  }
}
```

---

## 三、核心类实现

### 3.1 ModelRegistryStore

```python
# src/mini_agent/model_manager/model_registry.py

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any


class ModelRegistryStore:
    """模型注册表存储"""
    
    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or Path.home() / ".mini-agent"
        self.registry_file = self.config_dir / "model_registry.json"
        self._registry: ModelRegistry = ModelRegistry()
        self._load()
    
    # === Provider 管理 ===
    
    def add_provider(self, provider_id: str, config: dict[str, Any]) -> None:
        """添加 Provider"""
        self._registry.providers[provider_id] = config
        self._touch()
    
    def get_provider(self, provider_id: str) -> dict[str, Any] | None:
        """获取 Provider"""
        return self._registry.providers.get(provider_id)
    
    def update_provider(self, provider_id: str, updates: dict[str, Any]) -> None:
        """更新 Provider"""
        if provider_id in self._registry.providers:
            self._registry.providers[provider_id].update(updates)
            self._touch()
    
    def remove_provider(self, provider_id: str) -> bool:
        """删除 Provider"""
        if provider_id in self._registry.providers:
            del self._registry.providers[provider_id]
            self._touch()
            return True
        return False
    
    def list_providers(self) -> list[tuple[str, dict[str, Any]]]:
        """列出所有 Provider"""
        return list(self._registry.providers.items())
    
    # === 模型配置管理 ===
    
    def add_model_config(self, config_id: str, config: dict[str, Any]) -> None:
        """添加模型配置"""
        self._registry.model_configs[config_id] = config
        self._touch()
    
    def get_model_config(self, config_id: str) -> dict[str, Any] | None:
        """获取模型配置"""
        return self._registry.model_configs.get(config_id)
    
    def update_model_config(self, config_id: str, updates: dict[str, Any]) -> None:
        """更新模型配置"""
        if config_id in self._registry.model_configs:
            self._registry.model_configs[config_id].update(updates)
            self._touch()
    
    def remove_model_config(self, config_id: str) -> bool:
        """删除模型配置"""
        if config_id in self._registry.model_configs:
            del self._registry.model_configs[config_id]
            self._touch()
            return True
        return False
    
    def mark_config_orphaned(self, config_id: str) -> None:
        """标记配置为丢失状态"""
        if config_id in self._registry.model_configs:
            self._registry.model_configs[config_id]["status"] = "orphaned"
            self._touch()
    
    def list_model_configs(self, status: str | None = None) -> list[dict[str, Any]]:
        """列出模型配置
        
        Args:
            status: 过滤状态 (active/orphaned)，None 表示全部
        """
        configs = list(self._registry.model_configs.values())
        if status:
            configs = [c for c in configs if c.get("status") == status]
        return configs
    
    # === 默认参数管理 ===
    
    def get_default_params(self, provider_id: str, model_id: str) -> dict[str, Any] | None:
        """获取模型默认参数"""
        key = f"{provider_id}:{model_id}"
        return self._registry.default_params.get(key)
    
    def set_default_params(self, provider_id: str, model_id: str, params: dict[str, Any]) -> None:
        """设置模型默认参数"""
        key = f"{provider_id}:{model_id}"
        self._registry.default_params[key] = params
        self._touch()
    
    # === 能力管理 ===
    
    def get_capabilities(self, provider_id: str, model_id: str) -> dict[str, Any] | None:
        """获取模型能力"""
        key = f"{provider_id}:{model_id}"
        return self._registry.capabilities.get(key)
    
    def set_capabilities(self, provider_id: str, model_id: str, capabilities: dict[str, Any]) -> None:
        """设置模型能力"""
        key = f"{provider_id}:{model_id}"
        self._registry.capabilities[key] = capabilities
        self._touch()
    
    # === 别名管理 ===
    
    def resolve_alias(self, alias: str) -> str | None:
        """解析别名"""
        return self._registry.aliases.get(alias)
    
    def add_alias(self, alias: str, model_id: str) -> None:
        """添加别名"""
        self._registry.aliases[alias] = model_id
        self._touch()
    
    def remove_alias(self, alias: str) -> bool:
        """删除别名"""
        if alias in self._registry.aliases:
            del self._registry.aliases[alias]
            self._touch()
            return True
        return False
    
    # === 导入导出 ===
    
    def export_config(self, include_secrets: bool = False) -> dict[str, Any]:
        """导出配置
        
        Args:
            include_secrets: 是否包含敏感信息
        """
        data = {
            "version": self._registry.version,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "contains_secrets": include_secrets,
            "data": {
                "providers": dict(self._registry.providers),
                "model_configs": dict(self._registry.model_configs),
                "default_params": dict(self._registry.default_params),
                "capabilities": dict(self._registry.capabilities),
                "breaker_config": dict(self._registry.breaker_config),
                "pricing": dict(self._registry.pricing),
                "aliases": dict(self._registry.aliases),
            }
        }
        
        if not include_secrets:
            # 移除敏感信息
            for provider in data["data"]["providers"].values():
                provider.pop("api_key_ref", None)
        
        return data
    
    def import_config(self, data: dict[str, Any], overwrite: bool = False) -> None:
        """导入配置
        
        Args:
            data: 导入的配置数据
            overwrite: 是否覆盖现有配置
        """
        imported = data.get("data", {})
        
        if overwrite:
            self._registry.providers = imported.get("providers", {})
            self._registry.model_configs = imported.get("model_configs", {})
            self._registry.default_params = imported.get("default_params", {})
            self._registry.capabilities = imported.get("capabilities", {})
            self._registry.breaker_config = imported.get("breaker_config", {})
            self._registry.pricing = imported.get("pricing", {})
            self._registry.aliases = imported.get("aliases", {})
        else:
            # 合并配置
            self._registry.providers.update(imported.get("providers", {}))
            self._registry.model_configs.update(imported.get("model_configs", {}))
            self._registry.default_params.update(imported.get("default_params", {}))
            self._registry.capabilities.update(imported.get("capabilities", {}))
            self._registry.breaker_config.update(imported.get("breaker_config", {}))
            self._registry.pricing.update(imported.get("pricing", {}))
            self._registry.aliases.update(imported.get("aliases", {}))
        
        self._touch()
    
    # === 重置 ===
    
    def reset_to_template(self, template: str = "default") -> None:
        """重置为模板配置
        
        Args:
            template: 模板名称 (default/openai-only/anthropic-only/local-models)
        """
        templates = {
            "default": self._get_default_template(),
            "openai-only": self._get_openai_template(),
            "anthropic-only": self._get_anthropic_template(),
            "local-models": self._get_local_template(),
        }
        
        template_data = templates.get(template, templates["default"])
        
        self._registry = ModelRegistry(**template_data)
        self._touch()
    
    def _get_default_template(self) -> dict[str, Any]:
        """默认模板"""
        return {
            "version": "1.0",
            "providers": {},
            "model_configs": {},
            "default_params": {},
            "capabilities": {},
            "breaker_config": {},
            "pricing": {},
            "aliases": {
                "opus": "claude-opus-4-7",
                "sonnet": "claude-sonnet-4-6",
                "haiku": "claude-haiku-4-5",
            },
        }
    
    def _get_openai_template(self) -> dict[str, Any]:
        """OpenAI 模板"""
        return {
            **self._get_default_template(),
            "aliases": {
                "gpt4": "gpt-4o",
                "gpt": "gpt-4o",
            },
        }
    
    def _get_anthropic_template(self) -> dict[str, Any]:
        """Anthropic 模板"""
        return self._get_default_template()
    
    def _get_local_template(self) -> dict[str, Any]:
        """本地模型模板"""
        return {
            **self._get_default_template(),
            "aliases": {
                "llama": "llama3-70b",
                "mistral": "mistral-large",
            },
        }
    
    # === 存储 ===
    
    def _load(self) -> None:
        """加载配置"""
        if not self.registry_file.exists():
            self._registry = ModelRegistry()
            return
        
        with open(self.registry_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 版本迁移
        data = self._migrate(data)
        
        self._registry = ModelRegistry(
            version=data.get("version", "1.0"),
            providers=data.get("providers", {}),
            model_configs=data.get("model_configs", {}),
            default_params=data.get("default_params", {}),
            capabilities=data.get("capabilities", {}),
            breaker_config=data.get("breaker_config", {}),
            pricing=data.get("pricing", {}),
            aliases=data.get("aliases", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
    
    def _save(self) -> None:
        """保存配置"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        data = {
            "version": self._registry.version,
            "created_at": self._registry.created_at,
            "updated_at": self._registry.updated_at,
            "providers": self._registry.providers,
            "model_configs": self._registry.model_configs,
            "default_params": self._registry.default_params,
            "capabilities": self._registry.capabilities,
            "breaker_config": self._registry.breaker_config,
            "pricing": self._registry.pricing,
            "aliases": self._registry.aliases,
        }
        
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _touch(self) -> None:
        """更新时间戳并保存"""
        now = datetime.now(timezone.utc).isoformat()
        if not self._registry.created_at:
            self._registry.created_at = now
        self._registry.updated_at = now
        self._save()
    
    def _migrate(self, data: dict[str, Any]) -> dict[str, Any]:
        """配置迁移"""
        version = data.get("version", "0.0")
        
        # 未来版本迁移
        # if version < "1.1":
        #     data = migrate_1_0_to_1_1(data)
        
        return data
```

---

## 四、测试用例

```python
# tests/model_manager/test_model_registry.py

import pytest
from pathlib import Path
import tempfile

from mini_agent.model_manager.model_registry import ModelRegistryStore


class TestModelRegistryStore:
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)
    
    @pytest.fixture
    def store(self, temp_dir):
        return ModelRegistryStore(config_dir=temp_dir)
    
    def test_add_and_get_provider(self, store):
        """测试添加和获取 Provider"""
        store.add_provider("test-123", {"name": "Test"})
        
        result = store.get_provider("test-123")
        assert result is not None
        assert result["name"] == "Test"
    
    def test_remove_provider(self, store):
        """测试删除 Provider"""
        store.add_provider("test-123", {"name": "Test"})
        
        assert store.remove_provider("test-123") is True
        assert store.get_provider("test-123") is None
    
    def test_add_model_config(self, store):
        """测试添加模型配置"""
        store.add_model_config("sonnet-code", {
            "config_id": "sonnet-code",
            "model_id": "claude-sonnet-4-6",
            "status": "active",
        })
        
        result = store.get_model_config("sonnet-code")
        assert result["model_id"] == "claude-sonnet-4-6"
    
    def test_mark_config_orphaned(self, store):
        """测试标记配置丢失"""
        store.add_model_config("test", {"status": "active"})
        store.mark_config_orphaned("test")
        
        result = store.get_model_config("test")
        assert result["status"] == "orphaned"
    
    def test_list_configs_by_status(self, store):
        """测试按状态列出配置"""
        store.add_model_config("active-1", {"status": "active"})
        store.add_model_config("orphaned-1", {"status": "orphaned"})
        
        active = store.list_model_configs(status="active")
        assert len(active) == 1
        
        orphaned = store.list_model_configs(status="orphaned")
        assert len(orphaned) == 1
    
    def test_alias_operations(self, store):
        """测试别名操作"""
        store.add_alias("opus", "claude-opus-4-7")
        
        assert store.resolve_alias("opus") == "claude-opus-4-7"
        assert store.remove_alias("opus") is True
        assert store.resolve_alias("opus") is None
    
    def test_export_import(self, store):
        """测试导出导入"""
        store.add_provider("test", {"name": "Test"})
        store.add_model_config("config-1", {"model_id": "test-model"})
        
        exported = store.export_config()
        
        # 创建新 store 并导入
        with tempfile.TemporaryDirectory() as d:
            new_store = ModelRegistryStore(config_dir=Path(d))
            new_store.import_config(exported)
            
            assert new_store.get_provider("test") is not None
            assert new_store.get_model_config("config-1") is not None
    
    def test_export_without_secrets(self, store):
        """测试导出时移除敏感信息"""
        store.add_provider("test", {
            "name": "Test",
            "api_key_ref": "SECRET_KEY",
        })
        
        exported = store.export_config(include_secrets=False)
        
        provider = exported["data"]["providers"]["test"]
        assert "api_key_ref" not in provider
    
    def test_reset_to_template(self, store):
        """测试重置为模板"""
        store.add_provider("test", {"name": "Test"})
        store.reset_to_template("default")
        
        assert len(store.list_providers()) == 0
```

---

## 五、验收标准

- [ ] ModelRegistry 数据结构完整
- [ ] Provider/ModelConfig CRUD 正常
- [ ] 配置导入导出正常
- [ ] 配置重置功能正常
- [ ] 测试覆盖率 >= 80%

---

## 六、依赖关系

- 依赖: ProviderConfig
- 被依赖: 所有其他模块
