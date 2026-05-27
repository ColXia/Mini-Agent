# Provider 配置管理开发文档

**模块**: model_manager
**优先级**: P0
**预估时间**: 2 天

---

## 一、功能概述

Provider 配置管理负责管理 AI 供应商的配置信息，包括：
- Provider 配置的增删改查
- 配置验证
- 环境变量检测
- API Key 安全存储

---

## 二、数据结构

### 2.1 ProviderConfig

```python
# src/mini_agent/model_manager/provider_config.py

from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class ApiType(str, Enum):
    """API 协议类型"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class ProviderConfig:
    """Provider 配置
    
    必填字段: name, api_base, api_key_ref, api_type
    可选字段: models, timeout, priority, headers, enabled
    """
    # 必填字段
    name: str                      # 显示名称
    api_base: str                  # API 地址
    api_key_ref: str               # API Key 引用 (.env 中的变量名)
    api_type: ApiType              # 协议类型
    
    # 可选字段
    models: list[str] = field(default_factory=list)  # 可用模型列表
    timeout: int = 60              # 超时秒数
    priority: int = 0              # 优先级
    headers: dict[str, str] = field(default_factory=dict)  # 额外请求头
    enabled: bool = True           # 是否启用
    
    # 元数据
    provider_id: str = ""          # 内部 ID (自动生成)
    created_at: str = ""           # 创建时间
    updated_at: str = ""           # 更新时间


@dataclass
class ProviderConfigError:
    """配置验证错误"""
    field: str
    message: str
    suggestion: str


@dataclass
class ProviderValidationResult:
    """配置验证结果"""
    valid: bool
    errors: list[ProviderConfigError] = field(default_factory=list)
    warnings: list[ProviderConfigError] = field(default_factory=list)
```

### 2.2 环境变量映射

```python
# 预定义环境变量映射
ENV_KEY_MAPPING: dict[str, tuple[str, str]] = {
    # 环境变量名 -> (Provider 名称, API Base)
    "OPENAI_API_KEY": ("openai", "https://api.openai.com/v1"),
    "ANTHROPIC_API_KEY": ("anthropic", "https://api.anthropic.com"),
    "MINIMAX_API_KEY": ("minimax", "https://api.minimaxi.com"),
}
```

---

## 三、核心类实现

### 3.1 ProviderConfigManager

```python
# src/mini_agent/model_manager/provider_config.py

import os
from pathlib import Path
from datetime import datetime, timezone
import uuid
import json


class ProviderConfigManager:
    """Provider 配置管理器"""
    
    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or Path.home() / ".mini-agent"
        self.config_file = self.config_dir / "model_registry.json"
        self.env_file = self.config_dir / ".env"
        
        self._providers: dict[str, ProviderConfig] = {}
        self._load()
    
    # === CRUD 操作 ===
    
    def create(self, config: ProviderConfig) -> ProviderConfig:
        """创建 Provider 配置
        
        Args:
            config: Provider 配置 (不含 provider_id)
        
        Returns:
            创建后的配置 (含 provider_id)
        
        Raises:
            ValueError: 配置验证失败
        """
        # 验证配置
        result = self.validate(config)
        if not result.valid:
            raise ValueError(f"配置验证失败: {result.errors}")
        
        # 生成 ID
        config.provider_id = self._generate_id(config.name)
        config.created_at = datetime.now(timezone.utc).isoformat()
        config.updated_at = config.created_at
        
        # 保存 API Key 到 .env
        self._save_api_key(config.api_key_ref, config.api_key_ref)
        
        # 存储
        self._providers[config.provider_id] = config
        self._save()
        
        return config
    
    def get(self, provider_id: str) -> ProviderConfig | None:
        """获取 Provider 配置"""
        return self._providers.get(provider_id)
    
    def get_by_name(self, name: str) -> ProviderConfig | None:
        """按名称获取 Provider 配置"""
        for config in self._providers.values():
            if config.name == name:
                return config
        return None
    
    def update(self, provider_id: str, **kwargs) -> ProviderConfig:
        """更新 Provider 配置"""
        config = self._providers.get(provider_id)
        if not config:
            raise ValueError(f"Provider 不存在: {provider_id}")
        
        # 更新字段
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        config.updated_at = datetime.now(timezone.utc).isoformat()
        
        # 验证
        result = self.validate(config)
        if not result.valid:
            raise ValueError(f"配置验证失败: {result.errors}")
        
        self._save()
        return config
    
    def delete(self, provider_id: str) -> bool:
        """删除 Provider 配置
        
        Returns:
            是否成功删除
        """
        if provider_id not in self._providers:
            return False
        
        del self._providers[provider_id]
        self._save()
        return True
    
    def list_all(self) -> list[ProviderConfig]:
        """列出所有 Provider 配置"""
        return list(self._providers.values())
    
    # === 验证 ===
    
    def validate(self, config: ProviderConfig) -> ProviderValidationResult:
        """验证 Provider 配置"""
        errors: list[ProviderConfigError] = []
        warnings: list[ProviderConfigError] = []
        
        # 必填字段检查
        if not config.name:
            errors.append(ProviderConfigError(
                field="name",
                message="名称不能为空",
                suggestion="请提供 Provider 名称"
            ))
        
        if not config.api_base:
            errors.append(ProviderConfigError(
                field="api_base",
                message="API 地址不能为空",
                suggestion="请提供 API Base URL"
            ))
        
        if not config.api_key_ref:
            errors.append(ProviderConfigError(
                field="api_key_ref",
                message="API Key 引用不能为空",
                suggestion="请提供 API Key"
            ))
        
        # API Base 格式检查
        if config.api_base:
            if not config.api_base.startswith(("http://", "https://")):
                errors.append(ProviderConfigError(
                    field="api_base",
                    message="API 地址格式错误",
                    suggestion="API 地址需以 http:// 或 https:// 开头"
                ))
        
        # API Type 检查
        if config.api_type not in (ApiType.OPENAI, ApiType.ANTHROPIC):
            errors.append(ProviderConfigError(
                field="api_type",
                message="协议类型无效",
                suggestion="协议类型必须是 openai 或 anthropic"
            ))
        
        # 模型列表警告
        if not config.models:
            warnings.append(ProviderConfigError(
                field="models",
                message="未配置可用模型",
                suggestion="请手动配置 models 字段或运行 detect-models 命令"
            ))
        
        return ProviderValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    # === 环境变量检测 ===
    
    def detect_from_env(self) -> list[ProviderConfig]:
        """从环境变量检测 Provider 配置
        
        Returns:
            检测到的 Provider 配置列表 (未保存)
        """
        detected = []
        
        for env_key, (name, api_base) in ENV_KEY_MAPPING.items():
            api_key = os.getenv(env_key)
            if api_key:
                config = ProviderConfig(
                    name=name,
                    api_base=api_base,
                    api_key_ref=f"PROVIDER_{name.upper()}_KEY",
                    api_type=ApiType.OPENAI if name != "anthropic" else ApiType.ANTHROPIC,
                )
                detected.append(config)
        
        return detected
    
    # === API Key 管理 ===
    
    def get_api_key(self, config: ProviderConfig) -> str | None:
        """获取 API Key
        
        优先级: 环境变量 > .env 文件
        """
        # 1. 检查环境变量
        for env_key, (name, _) in ENV_KEY_MAPPING.items():
            if name == config.name:
                api_key = os.getenv(env_key)
                if api_key:
                    return api_key
        
        # 2. 从 .env 文件读取
        return self._load_api_key(config.api_key_ref)
    
    def _save_api_key(self, key_ref: str, api_key: str) -> None:
        """保存 API Key 到 .env 文件"""
        self._ensure_config_dir()
        
        # 读取现有内容
        existing = {}
        if self.env_file.exists():
            with open(self.env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        existing[k.strip()] = v.strip()
        
        # 更新
        existing[key_ref] = api_key
        
        # 写入
        with open(self.env_file, "w", encoding="utf-8") as f:
            f.write("# API Keys - 请勿提交到版本控制\n\n")
            for k, v in existing.items():
                f.write(f"{k}={v}\n")
    
    def _load_api_key(self, key_ref: str) -> str | None:
        """从 .env 文件加载 API Key"""
        if not self.env_file.exists():
            return None
        
        with open(self.env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key_ref}="):
                    return line.split("=", 1)[1].strip()
        
        return None
    
    # === 存储 ===
    
    def _load(self) -> None:
        """加载配置"""
        if not self.config_file.exists():
            return
        
        with open(self.config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        for provider_id, config_data in data.get("providers", {}).items():
            config = ProviderConfig(
                provider_id=provider_id,
                **config_data
            )
            self._providers[provider_id] = config
    
    def _save(self) -> None:
        """保存配置"""
        self._ensure_config_dir()
        
        # 读取现有配置
        data = {}
        if self.config_file.exists():
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        
        # 更新 providers
        data["providers"] = {
            config.provider_id: {
                "name": config.name,
                "api_base": config.api_base,
                "api_key_ref": config.api_key_ref,
                "api_type": config.api_type.value,
                "models": config.models,
                "timeout": config.timeout,
                "priority": config.priority,
                "headers": config.headers,
                "enabled": config.enabled,
                "created_at": config.created_at,
                "updated_at": config.updated_at,
            }
            for config in self._providers.values()
        }
        
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _ensure_config_dir(self) -> None:
        """确保配置目录存在"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def _generate_id(self, name: str) -> str:
        """生成 Provider ID"""
        # 使用名称的 slug + 短 UUID
        slug = name.lower().replace(" ", "-").replace("_", "-")
        short_uuid = uuid.uuid4().hex[:8]
        return f"{slug}-{short_uuid}"
```

---

## 四、测试用例

### 4.1 测试文件

```python
# tests/model_manager/test_provider_config.py

import pytest
from pathlib import Path
import tempfile
import os

from mini_agent.model_manager.provider_config import (
    ProviderConfig,
    ProviderConfigManager,
    ApiType,
)


class TestProviderConfig:
    """ProviderConfig 数据结构测试"""
    
    def test_create_minimal_config(self):
        """测试最小配置创建"""
        config = ProviderConfig(
            name="test",
            api_base="https://api.test.com/v1",
            api_key_ref="TEST_KEY",
            api_type=ApiType.OPENAI,
        )
        
        assert config.name == "test"
        assert config.models == []
        assert config.timeout == 60
        assert config.enabled is True
    
    def test_create_full_config(self):
        """测试完整配置创建"""
        config = ProviderConfig(
            name="test",
            api_base="https://api.test.com/v1",
            api_key_ref="TEST_KEY",
            api_type=ApiType.ANTHROPIC,
            models=["model-1", "model-2"],
            timeout=120,
            priority=10,
            headers={"X-Custom": "value"},
            enabled=False,
        )
        
        assert config.models == ["model-1", "model-2"]
        assert config.timeout == 120
        assert config.priority == 10
        assert config.headers == {"X-Custom": "value"}
        assert config.enabled is False


class TestProviderConfigManager:
    """ProviderConfigManager 测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """临时目录"""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)
    
    @pytest.fixture
    def manager(self, temp_dir):
        """配置管理器"""
        return ProviderConfigManager(config_dir=temp_dir)
    
    def test_create_provider(self, manager):
        """测试创建 Provider"""
        config = ProviderConfig(
            name="Test Provider",
            api_base="https://api.test.com/v1",
            api_key_ref="TEST_KEY",
            api_type=ApiType.OPENAI,
        )
        
        created = manager.create(config)
        
        assert created.provider_id != ""
        assert created.created_at != ""
        assert manager.get(created.provider_id) is not None
    
    def test_get_by_name(self, manager):
        """测试按名称获取"""
        config = ProviderConfig(
            name="Unique Name",
            api_base="https://api.test.com/v1",
            api_key_ref="TEST_KEY",
            api_type=ApiType.OPENAI,
        )
        
        manager.create(config)
        
        found = manager.get_by_name("Unique Name")
        assert found is not None
        assert found.name == "Unique Name"
    
    def test_update_provider(self, manager):
        """测试更新 Provider"""
        config = ProviderConfig(
            name="Test",
            api_base="https://api.test.com/v1",
            api_key_ref="TEST_KEY",
            api_type=ApiType.OPENAI,
        )
        
        created = manager.create(config)
        updated = manager.update(created.provider_id, timeout=120)
        
        assert updated.timeout == 120
    
    def test_delete_provider(self, manager):
        """测试删除 Provider"""
        config = ProviderConfig(
            name="Test",
            api_base="https://api.test.com/v1",
            api_key_ref="TEST_KEY",
            api_type=ApiType.OPENAI,
        )
        
        created = manager.create(config)
        assert manager.delete(created.provider_id) is True
        assert manager.get(created.provider_id) is None
    
    def test_validate_missing_name(self, manager):
        """测试验证 - 缺少名称"""
        config = ProviderConfig(
            name="",
            api_base="https://api.test.com/v1",
            api_key_ref="TEST_KEY",
            api_type=ApiType.OPENAI,
        )
        
        result = manager.validate(config)
        
        assert result.valid is False
        assert any(e.field == "name" for e in result.errors)
    
    def test_validate_invalid_api_base(self, manager):
        """测试验证 - 无效 API Base"""
        config = ProviderConfig(
            name="Test",
            api_base="invalid-url",
            api_key_ref="TEST_KEY",
            api_type=ApiType.OPENAI,
        )
        
        result = manager.validate(config)
        
        assert result.valid is False
        assert any(e.field == "api_base" for e in result.errors)
    
    def test_validate_warning_no_models(self, manager):
        """测试验证 - 警告无模型"""
        config = ProviderConfig(
            name="Test",
            api_base="https://api.test.com/v1",
            api_key_ref="TEST_KEY",
            api_type=ApiType.OPENAI,
            models=[],
        )
        
        result = manager.validate(config)
        
        assert result.valid is True  # 警告不影响验证结果
        assert any(w.field == "models" for w in result.warnings)
    
    def test_detect_from_env(self, manager, monkeypatch):
        """测试环境变量检测"""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        
        detected = manager.detect_from_env()
        
        assert len(detected) > 0
        assert any(c.name == "openai" for c in detected)
```

---

## 五、验收标准

- [ ] ProviderConfig 数据结构定义完整
- [ ] CRUD 操作正常工作
- [ ] 配置验证覆盖所有必填字段
- [ ] 环境变量检测正常工作
- [ ] API Key 安全存储到 .env 文件
- [ ] 测试覆盖率 >= 80%

---

## 六、依赖关系

- 无前置依赖
- 被依赖: ModelRegistry, ModelConfigs
