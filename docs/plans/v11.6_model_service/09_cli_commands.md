# CLI 命令开发文档

**模块**: model_manager
**优先级**: P2
**预估时间**: 1 天

---

## 一、功能概述

CLI 命令负责：
- Provider 管理 (添加、删除、列表)
- 模型配置管理
- 能力探测触发
- 状态查看

---

## 二、命令设计

```python
# src/mini_agent/model_manager/cli.py

import click
from typing import Optional
from rich.console import Console
from rich.table import Table

console = Console()


# === Provider 命令组 ===

@click.group("provider")
def provider_group():
    """Provider 管理"""
    pass


@provider_group.command("add")
@click.option("--name", required=True, help="Provider 名称")
@click.option("--api-base", required=True, help="API Base URL")
@click.option("--api-type", default="openai", help="API 类型")
@click.option("--api-key", help="API Key (可选，稍后配置)")
def provider_add(name: str, api_base: str, api_type: str, api_key: Optional[str]):
    """添加 Provider"""
    from mini_agent.model_manager.provider_config import ProviderConfigManager
    
    manager = ProviderConfigManager()
    
    try:
        provider = manager.add_provider(
            name=name,
            api_base=api_base,
            api_type=api_type,
            api_key=api_key,
        )
        console.print(f"[green]✓[/green] Provider '{name}' 添加成功")
        console.print(f"  ID: {provider.provider_id}")
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")


@provider_group.command("list")
def provider_list():
    """列出所有 Provider"""
    from mini_agent.model_manager.provider_config import ProviderConfigManager
    
    manager = ProviderConfigManager()
    providers = manager.list_providers()
    
    table = Table(title="Providers")
    table.add_column("ID", style="cyan")
    table.add_column("名称", style="green")
    table.add_column("API Base", style="blue")
    table.add_column("API 类型", style="yellow")
    table.add_column("状态", style="magenta")
    
    for p in providers:
        status = "已配置" if p.has_api_key else "未配置 Key"
        table.add_row(
            p.provider_id[:8] + "...",
            p.name,
            p.api_base,
            p.api_type,
            status,
        )
    
    console.print(table)


@provider_group.command("delete")
@click.argument("provider_id")
@click.option("--force", is_flag=True, help="强制删除 (包括关联模型)")
def provider_delete(provider_id: str, force: bool):
    """删除 Provider"""
    from mini_agent.model_manager.provider_config import ProviderConfigManager
    
    manager = ProviderConfigManager()
    
    if force:
        manager.delete_provider(provider_id, cascade=True)
        console.print(f"[green]✓[/green] Provider '{provider_id}' 已删除 (包括关联模型)")
    else:
        manager.delete_provider(provider_id, cascade=False)
        console.print(f"[green]✓[/green] Provider '{provider_id}' 已删除")


@provider_group.command("set-key")
@click.argument("provider_id")
@click.option("--key", required=True, help="API Key")
def provider_set_key(provider_id: str, key: str):
    """设置 API Key"""
    from mini_agent.model_manager.provider_config import ProviderConfigManager
    
    manager = ProviderConfigManager()
    manager.set_api_key(provider_id, key)
    console.print(f"[green]✓[/green] API Key 已设置")


# === Model 命令组 ===

@click.group("model")
def model_group():
    """模型管理"""
    pass


@model_group.command("list")
@click.option("--provider", help="按 Provider 过滤")
def model_list(provider: Optional[str]):
    """列出模型"""
    from mini_agent.model_manager.model_registry import ModelRegistryStore
    
    registry = ModelRegistryStore()
    models = registry.list_models(provider_id=provider)
    
    table = Table(title="Models")
    table.add_column("ID", style="cyan")
    table.add_column("Provider", style="green")
    table.add_column("模型 ID", style="blue")
    table.add_column("别名", style="yellow")
    table.add_column("状态", style="magenta")
    
    for m in models:
        aliases = ", ".join(m.aliases[:2]) if m.aliases else "-"
        table.add_row(
            m.config_id[:8] + "...",
            m.provider_id[:8] + "...",
            m.model_id,
            aliases,
            m.status,
        )
    
    console.print(table)


@model_group.command("probe")
@click.argument("model_config_id")
@click.option("--force", is_flag=True, help="强制重新探测")
def model_probe(model_config_id: str, force: bool):
    """探测模型能力"""
    import asyncio
    from mini_agent.model_manager.capability_probe import CapabilityProbeService
    from mini_agent.model_manager.model_registry import ModelRegistryStore
    
    registry = ModelRegistryStore()
    probe = CapabilityProbeService(registry)
    
    # 获取模型信息
    model = registry.get_model(model_config_id)
    if not model:
        console.print(f"[red]✗[/red] 模型配置不存在: {model_config_id}")
        return
    
    console.print(f"[yellow]探测中...[/yellow]")
    
    result = asyncio.run(probe.probe_model(
        model_id=model.model_id,
        provider_id=model.provider_id,
        force=force,
    ))
    
    if result.get("detection_status") == "detected":
        console.print(f"[green]✓[/green] 探测完成")
        
        caps = result.get("capabilities", {})
        table = Table(title="能力")
        table.add_column("能力", style="cyan")
        table.add_column("支持", style="green")
        
        for cap, supported in caps.items():
            status = "[green]✓[/green]" if supported else "[red]✗[/red]"
            table.add_row(cap, status)
        
        console.print(table)
    else:
        console.print(f"[red]✗[/red] 探测失败: {result.get('error')}")


@model_group.command("status")
@click.argument("model_config_id")
def model_status(model_config_id: str):
    """查看模型状态"""
    from mini_agent.model_manager.health_monitor import HealthMonitor
    from mini_agent.model_manager.circuit_breaker import CircuitBreakerManager
    from mini_agent.model_manager.token_stats import TokenStatsManager
    
    health = HealthMonitor()
    breaker = CircuitBreakerManager()
    stats = TokenStatsManager()
    
    health_status = health.get_status(model_config_id)
    breaker_status = breaker.get_status(model_config_id)
    usage = stats.get_usage(model_config_id)
    
    # 健康状态
    console.print("\n[bold]健康状态[/bold]")
    console.print(f"  健康: {'[green]是[/green]' if health_status.is_healthy else '[red]否[/red]'}")
    console.print(f"  成功率: {health_status.success_rate:.1%}")
    console.print(f"  平均延迟: {health_status.avg_latency_ms}ms")
    
    # 熔断状态
    console.print("\n[bold]熔断状态[/bold]")
    state_color = {
        "closed": "green",
        "open": "red",
        "half_open": "yellow",
    }.get(breaker_status.state.value, "white")
    console.print(f"  状态: [{state_color}]{breaker_status.state.value}[/{state_color}]")
    console.print(f"  失败次数: {breaker_status.failure_count}")
    
    # Token 使用
    console.print("\n[bold]Token 使用[/bold]")
    console.print(f"  会话总计: {usage.total_tokens:,}")
    console.print(f"  使用率: {usage.usage_ratio:.1%}")


# === Alias 命令 ===

@click.group("alias")
def alias_group():
    """别名管理"""
    pass


@alias_group.command("list")
def alias_list():
    """列出所有别名"""
    from mini_agent.model_manager.model_alias import AliasResolver
    from mini_agent.model_manager.model_registry import ModelRegistryStore
    
    registry = ModelRegistryStore()
    resolver = AliasResolver(registry)
    aliases = resolver.list_aliases()
    
    table = Table(title="Aliases")
    table.add_column("别名", style="cyan")
    table.add_column("模型 ID", style="green")
    table.add_column("显示名称", style="blue")
    table.add_column("来源", style="yellow")
    
    for a in aliases:
        table.add_row(
            a["alias"],
            a["model_id"],
            a["display_name"],
            a["source"],
        )
    
    console.print(table)


@alias_group.command("resolve")
@click.argument("alias")
def alias_resolve(alias: str):
    """解析别名"""
    from mini_agent.model_manager.model_alias import AliasResolver
    from mini_agent.model_manager.model_registry import ModelRegistryStore
    
    registry = ModelRegistryStore()
    resolver = AliasResolver(registry)
    
    model_id = resolver.resolve(alias)
    is_alias = resolver.is_alias(alias)
    
    if is_alias:
        console.print(f"[cyan]{alias}[/cyan] → [green]{model_id}[/green]")
    else:
        console.print(f"[yellow]'{alias}' 不是已知别名，返回原值[/yellow]")


# === 注册命令 ===

def register_model_commands(cli_group):
    """注册模型管理命令到 CLI"""
    cli_group.add_command(provider_group)
    cli_group.add_command(model_group)
    cli_group.add_command(alias_group)
```

---

## 三、命令列表

| 命令 | 说明 |
|------|------|
| `provider add` | 添加 Provider |
| `provider list` | 列出 Provider |
| `provider delete` | 删除 Provider |
| `provider set-key` | 设置 API Key |
| `model list` | 列出模型 |
| `model probe` | 探测模型能力 |
| `model status` | 查看模型状态 |
| `alias list` | 列出别名 |
| `alias resolve` | 解析别名 |

---

## 四、验收标准

- [ ] 所有命令正常执行
- [ ] 输出格式清晰
- [ ] 错误处理正确

---

## 五、依赖关系

- 依赖: 所有其他模块
- 被依赖: CLI 入口
