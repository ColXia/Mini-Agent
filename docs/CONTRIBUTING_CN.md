# 贡献指南

当前仓库以终端优先的 Agent 项目方式开发。

## 提交前先看

- 阅读 [README_CN.md](../README_CN.md) 和 [docs/DEVELOPMENT_GUIDE_CN.md](./DEVELOPMENT_GUIDE_CN.md)
- 用 [docs/ARCHITECTURE.md](./ARCHITECTURE.md) 确认当前架构边界
- `docs/archive/` 只作为历史参考，不作为当前实现依据
- 当前主交互面是 `TUI / CLI / headless`，WebUI 处于暂停开发状态

## 开始开发

1. 克隆你要提交代码的仓库。
   ```bash
   git clone <your-fork-or-origin-url> mini-agent
   cd mini-agent
   ```
2. 安装依赖。
   ```bash
   uv sync
   ```
3. 先做一轮最小验证。
   ```bash
   uv run mini-agent --help
   uv run pytest tests/test_markdown_links.py -q
   ```

## 开发规则

- 修改范围尽量聚焦，不要把清理、重构、功能开发混在一起而不说明原因
- 除非确有兼容性要求，否则优先按当前真实运行路径实现，不要堆兼容壳
- 运行行为或架构边界变更后，要同步更新文档
- 活跃文档与历史文档要明确分层
- 不要提交本地密钥、`.env.local`、运行时状态文件或 workspace 产物

## 测试与脚本边界

- 自动化测试统一放在 `tests/`
- 可复用辅助脚本统一放在 `scripts/`
- 不要把一次性探针脚本和测试样例丢进 `src/` 或仓库根目录
- 先跑最小相关测试，再按需要扩大验证范围

示例：

```bash
uv run pytest tests/test_config_local_env.py tests/test_preset_providers.py -q
uv run pytest tests/test_command_execution_service.py -q
python scripts/test_stable.py
```

## 文档同步

如果你的改动影响了行为或架构，请顺手检查这些文档是否需要更新：

- [README.md](../README.md)
- [README_CN.md](../README_CN.md)
- [docs/DOCS_INDEX.md](./DOCS_INDEX.md)
- [docs/DEVELOPMENT_INDEX.md](./DEVELOPMENT_INDEX.md)
- [docs/REFACTOR_TASKS.md](./REFACTOR_TASKS.md)

## Pull Request

提交 PR 前请确认：

- 改动目标明确
- 已运行与改动相关的测试
- 文档在需要时已同步
- 没有混入无关缓存、生成物和本地临时文件
- 变更说明里同时写清“改了什么”和“为什么这样改”

## Commit 建议前缀

- `feat`：新功能
- `fix`：缺陷修复
- `refactor`：结构调整但不预期改变行为
- `docs`：文档更新
- `test`：测试相关修改
- `chore`：维护和工具链修改

## 有疑问时

优先核对当前代码和活跃文档，再决定实现方式，不要直接沿用历史文档里的旧模式。