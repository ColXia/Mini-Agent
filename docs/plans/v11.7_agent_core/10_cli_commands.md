# CLI 命令开发文档

**模块**: agent_core CLI
**优先级**: P2
**预估时间**: 待开发

---

## 一、功能概述

CLI 命令负责：

- Agent 配置管理
- 模型绑定管理
- 技能管理
- 会话管理

---

## 二、命令设计

### 2.1 Agent 命令组

```python
# src/mini_agent/commands/agent_commands.py

@click.group("agent")
def agent_group():
    """Agent 管理"""
    pass


@agent_group.command("create")
@click.option("--name", required=True, help="Agent 名称")
@click.option("--profile", help="Profile ID")
def agent_create(name: str, profile: str | None):
    """创建 Agent"""
    pass


@agent_group.command("list")
def agent_list():
    """列出所有 Agent"""
    pass


@agent_group.command("show")
@click.argument("agent_id")
def agent_show(agent_id: str):
    """显示 Agent 详情"""
    pass


@agent_group.command("delete")
@click.argument("agent_id")
@click.option("--force", is_flag=True, help="强制删除")
def agent_delete(agent_id: str, force: bool):
    """删除 Agent"""
    pass
```

### 2.2 模型绑定命令组

```python
# src/mini_agent/commands/agent_binding_commands.py

@click.group("binding")
def binding_group():
    """模型绑定管理"""
    pass


@binding_group.command("bind")
@click.argument("agent_id")
@click.option("--config", required=True, help="模型配置 ID")
@click.option("--role", default="primary", help="角色 (primary/fallback_1/fallback_2)")
@click.option("--name", help="自定义名称")
def binding_bind(agent_id: str, config: str, role: str, name: str | None):
    """绑定模型到 Agent"""
    pass


@binding_group.command("unbind")
@click.argument("agent_id")
@click.option("--config", required=True, help="模型配置 ID")
def binding_unbind(agent_id: str, config: str):
    """解除模型绑定"""
    pass


@binding_group.command("list")
@click.argument("agent_id")
def binding_list(agent_id: str):
    """列出 Agent 的模型绑定"""
    pass


@binding_group.command("failover")
@click.argument("agent_id")
@click.option("--enable/--disable", default=True, help="启用/禁用故障转移")
def binding_failover(agent_id: str, enable: bool):
    """配置故障转移"""
    pass
```

### 2.3 技能命令组

```python
# src/mini_agent/commands/skill_commands.py

@click.group("skill")
def skill_group():
    """技能管理"""
    pass


@skill_group.command("list")
@click.option("--eligible-only", is_flag=True, help="只显示可用技能")
def skill_list(eligible_only: bool):
    """列出所有技能"""
    pass


@skill_group.command("show")
@click.argument("skill_name")
def skill_show(skill_name: str):
    """显示技能详情"""
    pass


@skill_group.command("install")
@click.argument("source")
@click.option("--name", help="技能名称")
def skill_install(source: str, name: str | None):
    """安装技能"""
    pass


@skill_group.command("uninstall")
@click.argument("skill_name")
def skill_uninstall(skill_name: str):
    """卸载技能"""
    pass
```

### 2.4 会话命令组

```python
# src/mini_agent/commands/session_commands.py

@click.group("session")
def session_group():
    """会话管理"""
    pass


@session_group.command("list")
@click.option("--agent", help="按 Agent 过滤")
def session_list(agent: str | None):
    """列出所有会话"""
    pass


@session_group.command("show")
@click.argument("session_id")
def session_show(session_id: str):
    """显示会话详情"""
    pass


@session_group.command("reset")
@click.argument("session_id")
@click.option("--reason", help="重置原因")
def session_reset(session_id: str, reason: str | None):
    """重置会话"""
    pass


@session_group.command("lineage")
@click.argument("session_id")
def session_lineage(session_id: str):
    """显示会话血缘"""
    pass
```

---

## 三、命令列表

| 命令 | 说明 |
|------|------|
| `agent create` | 创建 Agent |
| `agent list` | 列出 Agent |
| `agent show` | 显示 Agent 详情 |
| `agent delete` | 删除 Agent |
| `binding bind` | 绑定模型 |
| `binding unbind` | 解除绑定 |
| `binding list` | 列出绑定 |
| `binding failover` | 配置故障转移 |
| `skill list` | 列出技能 |
| `skill show` | 显示技能详情 |
| `skill install` | 安装技能 |
| `skill uninstall` | 卸载技能 |
| `session list` | 列出会话 |
| `session show` | 显示会话详情 |
| `session reset` | 重置会话 |
| `session lineage` | 显示会话血缘 |

---

## 四、验收标准

- [ ] 所有命令正常执行
- [ ] 输出格式清晰
- [ ] 错误处理正确

---

## 五、依赖关系

- 依赖: 所有其他模块
- 被依赖: CLI 入口
