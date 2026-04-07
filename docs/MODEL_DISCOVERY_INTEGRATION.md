# 模型发现服务集成方案

> **状态**: ✅ 活跃
> **最后更新**: 2026-04-06
> **文档索引**: [DOCS_INDEX.md](./DOCS_INDEX.md)

## 功能概述

自动获取最新可用模型列表，提升用户配置体验。

---

## 核心实现

### 1. ModelDiscoveryService (`mini_agent/model_manager/model_discovery.py`)

**主要功能**:
- 从Provider API动态获取模型列表
- 智能缓存 (默认24小时)
- 自动识别最新基础模型
- 过滤deprecated和fine-tuned模型
- Fallback机制 (API不可用时使用预设列表)

**支持的Provider**:
- OpenAI: 调用 `/v1/models` API
- Gemini: 调用 `/v1beta/models` API
- MiniMax: 调用 `/v1/models` API (兼容OpenAI格式)
- Anthropic: 使用Fallback列表 (无公开API)

---

## 使用场景

### 场景1: CLI命令 - 查看可用模型

```bash
# 列出OpenAI所有可用模型
mini-agent models openai --api-key "sk-..."

# 列出MiniMax可用模型 (自动使用环境变量MINIMAX_API_KEY)
mini-agent models minimax

# 只显示最新基础模型
mini-agent models openai --latest

# 显示所有模型 (包括deprecated)
mini-agent models openai --all
```

**输出示例**:
```
OPENAI Models (15 found):

  - gpt-4o (created: 2024-05-13)
  - gpt-4o-mini (created: 2024-07-18)
  - gpt-4-turbo (created: 2024-04-09)
  - gpt-3.5-turbo (created: 2023-03-01)

  Recommended: gpt-4o-mini
```

---

### 场景2: Provider配置 - 自动选择最新模型

```bash
# 添加provider时自动使用最新模型
mini-agent provider add \
  --name "OpenAI" \
  --url "https://api.openai.com/v1" \
  --key "sk-..." \
  --type openai \
  --auto-model  # 新增参数：自动获取最新模型

# 等价于
mini-agent provider add \
  --name "OpenAI" \
  --url "https://api.openai.com/v1" \
  --key "sk-..." \
  --type openai \
  --models "gpt-4o-mini,gpt-4o,gpt-4-turbo"  # 自动填充
```

---

### 场景3: 运行时覆盖 - 快速选择模型

```bash
# 方式1: 使用最新模型
mini-agent cli --task "..." --provider openai --use-latest-model

# 方式2: 交互式选择
mini-agent cli --task "..."
> Select model for openai:
  1. gpt-4o-mini (latest, recommended)
  2. gpt-4o
  3. gpt-4-turbo
  4. gpt-3.5-turbo
> Enter choice [1-4]: 1
```

---

### 场景4: Provider管理 - 更新模型列表

```bash
# 更新provider的模型列表
mini-agent provider update-models <provider-id>

# 示例
mini-agent provider update-models openai
Fetching latest models from OpenAI...
Updated models: gpt-4o-mini, gpt-4o, gpt-4-turbo, gpt-3.5-turbo
```

---

## 集成步骤

### Step 1: 添加CLI命令

在 `mini_agent/cli.py` 中添加:

```python
# 在 create_main_parser() 中添加
models_parser = subparsers.add_parser(
    "models",
    help="Discover available models from providers",
)
models_parser.add_argument(
    "provider",
    type=str,
    help="Provider name (openai, anthropic, gemini, minimax)",
)
models_parser.add_argument(
    "--api-key",
    type=str,
    default=None,
    help="API key (will use environment variable if not provided)",
)
models_parser.add_argument(
    "--api-base",
    type=str,
    default=None,
    help="Custom API base URL",
)
models_parser.add_argument(
    "--all",
    action="store_true",
    help="Show all models including deprecated and fine-tuned",
)
models_parser.add_argument(
    "--latest",
    action="store_true",
    help="Only show the latest base model ID",
)

# 添加处理函数
def run_models_command(args: argparse.Namespace) -> None:
    """Discover available models from a provider."""
    import asyncio
    import os
    from mini_agent.model_manager.model_discovery import (
        list_available_models,
        get_latest_model_id,
        ProviderType,
    )
    
    # Get API key
    api_key = args.api_key
    if not api_key:
        # Try environment variables
        env_key_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "minimax": "MINIMAX_API_KEY",
        }
        env_key = env_key_map.get(args.provider.lower())
        if env_key:
            api_key = os.getenv(env_key)
        
        if not api_key:
            print(f"Error: No API key provided. Set {env_key} or use --api-key")
            return
    
    if args.latest:
        # Only show latest model ID
        model_id = asyncio.run(get_latest_model_id(
            args.provider,
            api_key,
            args.api_base
        ))
        if model_id:
            print(model_id)
        else:
            print(f"No models found for {args.provider}")
    else:
        # List all models
        asyncio.run(list_available_models(
            args.provider,
            api_key,
            args.api_base,
            show_all=args.all
        ))

# 在 main() 中添加路由
if args.command == "models":
    run_models_command(args)
```

---

### Step 2: Provider命令集成

修改 `run_provider_command()`:

```python
elif args.action == "add":
    # ... existing code ...
    
    # Auto-discover models if --auto-model flag
    if hasattr(args, 'auto_model') and args.auto_model:
        import asyncio
        from mini_agent.model_manager.model_discovery import (
            get_latest_model_id,
            ProviderType,
        )
        
        print(f"Discovering latest models from {args.type}...")
        latest_model = asyncio.run(get_latest_model_id(
            args.type,
            args.key,
            args.url
        ))
        
        if latest_model:
            models = [latest_model]
            print(f"Found latest model: {latest_model}")
        else:
            print("Warning: Could not discover models, using default")
            models = ["default"]
    
    # ... rest of add logic ...

elif args.action == "update-models":
    if not args.id:
        print("Error: --id is required for update-models action")
        return
    
    # Load provider
    # Fetch latest models
    # Update providers.json
```

---

### Step 3: CLI参数支持

修改 `cli_interactive.py`:

```python
async def build_agent(workspace: Path, ...) -> Agent:
    config = Config.load()
    
    # Runtime override with auto-discovery
    if runtime_provider and runtime_use_latest_model:
        from mini_agent.model_manager.model_discovery import get_latest_model_id
        
        api_key = runtime_api_key or os.getenv(f"{runtime_provider.upper()}_API_KEY")
        latest_model = await get_latest_model_id(runtime_provider, api_key)
        
        if latest_model:
            runtime_model = latest_model
            print(f"Using latest model: {latest_model}")
    
    # ... rest of build logic ...
```

---

## 缓存策略

**缓存位置**: `~/.mini-agent/cache/models_<provider>.json`

**缓存格式**:
```json
{
  "provider": "openai",
  "models": [
    {
      "id": "gpt-4o-mini",
      "name": "gpt-4o-mini",
      "provider": "openai",
      "created": "2024-07-18T00:00:00",
      "is_deprecated": false,
      "is_fine_tuned": false
    }
  ],
  "fetched_at": "2026-04-06T01:30:00",
  "error": null
}
```

**TTL**: 24小时 (可配置)

**清理**: 自动过期清理

---

## 环境变量映射

| Provider | 环境变量 | API Endpoint |
|----------|---------|--------------|
| OpenAI | `OPENAI_API_KEY` | `/v1/models` |
| Anthropic | `ANTHROPIC_API_KEY` | N/A (fallback) |
| Gemini | `GEMINI_API_KEY` | `/v1beta/models` |
| MiniMax | `MINIMAX_API_KEY` | `/v1/models` |

---

## UX优化建议

### 1. 交互式模型选择

```bash
$ mini-agent cli --provider openai
? Select model:
  ❯ gpt-4o-mini (latest, recommended)
    gpt-4o
    gpt-4-turbo
    gpt-3.5-turbo
    [Enter model ID manually]
```

### 2. 模型推荐提示

```bash
$ mini-agent provider add --name "OpenAI" --key "sk-..." --type openai
✓ Discovering available models...
✓ Found 15 models
✓ Recommended: gpt-4o-mini (latest base model)
? Use recommended model? [Y/n]: y
✓ Provider added with model: gpt-4o-mini
```

### 3. 模型更新提醒

```bash
$ mini-agent provider list
⚠ Provider 'openai' has new models available
  Current: gpt-4
  Latest: gpt-4o-mini
  
  Run: mini-agent provider update-models openai
```

---

## 安全考虑

1. **API密钥安全**: 
   - 不在日志中记录API密钥
   - 缓存文件不包含API密钥
   - 环境变量优先级最高

2. **缓存安全**:
   - 缓存文件仅存储模型元数据
   - 不存储敏感信息
   - 定期自动清理

3. **网络超时**:
   - 默认10秒超时
   - 失败时使用fallback列表
   - 不阻塞主流程

---

## 测试用例

```python
# tests/test_model_discovery.py

import pytest
from mini_agent.model_manager.model_discovery import (
    ModelDiscoveryService,
    ProviderType,
)

@pytest.mark.asyncio
async def test_discover_openai_models():
    """Test OpenAI model discovery."""
    service = ModelDiscoveryService()
    result = await service.discover_models(
        ProviderType.OPENAI,
        api_key="test-key",
        use_cache=False
    )
    
    assert result.provider == ProviderType.OPENAI
    assert len(result.models) > 0
    assert result.latest_base_model is not None

def test_cache_ttl():
    """Test cache expiration."""
    from datetime import datetime, timedelta
    from mini_agent.model_manager.model_discovery import ModelDiscoveryCache
    
    cache = ModelDiscoveryCache(ttl_hours=1)
    # ... test cache logic ...
```

---

## 后续优化

1. **模型能力标签**: 自动识别模型能力 (vision, function-calling, etc.)
2. **价格信息**: 集成模型定价信息
3. **性能指标**: 集成模型性能基准测试结果
4. **多语言支持**: 模型名称和描述的本地化
