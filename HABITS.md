# Mini-Agent 开发习惯与错误记录

> **最后更新**: 2026-04-06
> **维护者**: Mini-Agent Core Team

---

## 🎯 核心开发习惯

### 必须遵守的习惯

| ID | 习惯 | 约束 | 验证方式 |
|----|------|------|----------|
| H-01 | 架构单一真实来源 | 所有变更必须映射到活跃阶段文档 | PR 检查清单 + 任务链接 |
| H-02 | 无兼容层 | 任何回退/遗留适配器都被阻止，除非明确批准 | 代码审查门控 |
| H-03 | 契约优先 API 变更 | 路由器变更必须先更新 DTO/契约 | 契约测试 |
| H-04 | 开发环境一前端一后端 | 重复启动必须快速失败并显示 PID/端口消息 | 启动脚本防护 |
| H-05 | 单一主代理运行时 | 无重复的运行时创建路径 | 运行时管理器断言 |
| H-06 | 渠道入口标准化 | QQ/WeChat 必须进入一个规范的用例 | 集成测试 |
| H-07 | 小而原子的切片 | 每个变更必须包含范围边界和回滚说明 | 开发日志条目 |
| H-08 | 变更后立即验证 | 语法/构建/冒烟检查在移交前必须执行 | 本地检查报告 |
| H-09 | 语言特定验证命令 | Python/TypeScript 验证命令不得在一次调用中混合 | 验证检查清单 |
| H-10 | 仓库卫生管理 | 定期清理缓存文件，保持仓库干净整洁 | 仓库卫生检查清单 |
| H-11 | 提交前清理 | 每次提交前检查并清理缓存文件 | Git 提交前检查 |
| H-12 | .gitignore 维护 | 发现新的缓存目录及时添加到 .gitignore | 定期审查 |

---

## 🧹 仓库卫生管理

### 必须清理的文件

| 类型 | 模式 | 说明 | 清理命令 |
|------|------|------|----------|
| Python 缓存 | `__pycache__/` | Python 字节码缓存 | `Remove-Item -Recurse -Force __pycache__` |
| Python 缓存 | `*.pyc` | Python 编译文件 | `Remove-Item -Recurse -Force *.pyc` |
| 测试缓存 | `.pytest_cache/` | Pytest 测试缓存 | `Remove-Item -Recurse -Force .pytest_cache` |
| Linter 缓存 | `.ruff_cache/` | Ruff linter 缓存 | `Remove-Item -Recurse -Force .ruff_cache` |
| 包元数据 | `*.egg-info/` | Python 包元数据 | `Remove-Item -Recurse -Force *.egg-info` |
| 构建产物 | `build/`, `dist/` | 构建输出 | `Remove-Item -Recurse -Force build, dist` |

### 仓库卫生检查清单

#### 提交前检查
- [ ] 检查是否有 `__pycache__/` 目录
- [ ] 检查是否有 `.pytest_cache/` 目录
- [ ] 检查是否有 `.ruff_cache/` 目录
- [ ] 检查是否有 `*.egg-info/` 目录
- [ ] 检查是否有 `*.pyc` 文件
- [ ] 检查 `git status` 是否干净

#### 定期检查（每周）
- [ ] 审查 .gitignore 是否完善
- [ ] 清理所有缓存目录
- [ ] 检查是否有大文件误提交
- [ ] 检查仓库大小是否合理

### .gitignore 标准配置

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
ENV/
env/
.venv

# Testing
.pytest_cache/
.coverage
htmlcov/

# Linting
.ruff_cache/
.mypy_cache/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Workspace (runtime data)
workspace/
*.log
```

### 快速清理脚本

#### PowerShell (Windows)
```powershell
# 清理所有 Python 缓存
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Recurse -File -Filter "*.pyc" | Remove-Item -Force
Remove-Item -Recurse -Force .pytest_cache -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .ruff_cache -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force *.egg-info -ErrorAction SilentlyContinue
```

#### Bash (Linux/macOS)
```bash
# 清理所有 Python 缓存
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
rm -rf .pytest_cache .ruff_cache *.egg-info
```

### 仓库卫生标准

#### ✅ 干净的仓库应该：
1. 无任何 `__pycache__/` 目录（项目源代码中）
2. 无任何 `.pytest_cache/` 目录
3. 无任何 `.ruff_cache/` 目录
4. 无任何 `*.egg-info/` 目录
5. 无任何 `*.pyc` 文件（项目源代码中）
6. 根目录简洁，只保留必要文件
7. .gitignore 配置完善

#### ❌ 不应该提交的内容：
1. Python 字节码缓存
2. 测试缓存
3. Linter 缓存
4. 包元数据
5. 虚拟环境
6. 工作区数据
7. IDE 配置
8. OS 临时文件

---

## ❌ 错误记录

### 2026-04-06 错误

#### E-001: 运行时启动 - Studio 路径绕过 CLI 单实例锁
- **影响**: 重复进程风险，操作混乱
- **根本原因**: 锁只在一个入口路径实现
- **预防规则**: 在 Studio gateway 启动和启动脚本预检查中添加实例锁
- **状态**: ✅ 已修复

#### E-002: 前端服务 - JS 以 `text/plain` 提供导致空白页
- **影响**: WebUI 渲染空白
- **根本原因**: 静态托管路径上缺少/错误的 MIME 映射
- **预防规则**: 强制 `.js/.mjs` MIME 为 `application/javascript` 并冒烟检查头
- **状态**: ✅ 已修复

#### E-003: 开发工作流 - 运行时验证期间使用分离模式启动
- **影响**: 难以跟踪进程状态
- **根本原因**: 当前目标没有统一的启动纪律
- **预防规则**: 默认使用单主机流程并强制重复启动失败
- **状态**: ✅ 已修复

#### E-004: UI 质量 - UI 中混合/乱码的多语言文本
- **影响**: 糟糕的 UX 和调试噪音
- **根本原因**: 编码/历史残留 + 不一致的复制源
- **预防规则**: 集中 UI 副本审查并在构建前运行文本健全性检查
- **状态**: 🔄 进行中

#### E-005: 测试执行 - 并行测试运行在实例锁上冲突
- **影响**: 假阴性测试失败
- **根本原因**: 并发运行锁敏感套件
- **预防规则**: 串行运行 Studio Gateway 测试或为每个工作器隔离锁键/端口
- **状态**: ✅ 已修复

#### E-006: 代码卫生 - 乱码/未终止的字符串字面量破坏启动编译
- **影响**: 运行时阻塞直到手动修复
- **根本原因**: 混合编码文本编辑而没有立即语法检查
- **预防规则**: 编辑后端 Python 文件后立即运行 `py_compile`
- **状态**: ✅ 已修复

#### E-007: 验证工作流 - 对 `.ts` 文件使用 `py_compile`
- **影响**: 减慢验证循环并掩盖真实状态
- **根本原因**: 快速并行检查期间跨语言命令混合
- **预防规则**: Python 编译检查仅用于 Python；TS 使用 `npm run build`/`tsc`
- **状态**: ✅ 已修复

#### E-008: 开发管理器日志 - `dev logs` 在 Windows 控制台编码上崩溃
- **影响**: 活跃开发期间破坏日志检查命令
- **根本原因**: 直接将 UTF-8 日志行打印到 GBK 终端
- **预防规则**: 为日志输出路径添加安全打印回退（`errors=replace`）
- **状态**: ✅ 已修复

#### E-009: 测试隔离 - 开发管理器测试触碰用户级状态路径
- **影响**: 后续手动检查中令人困惑的状态/日志输出
- **根本原因**: 测试使用默认 `~/.mini-agent/studio-dev` 根目录
- **预防规则**: 为所有管理器测试强制使用临时路径下的仅测试状态根
- **状态**: ✅ 已修复

#### E-010: 运行时架构 - v1 主机迁移后遗留 gateway/orchestrator 启动入口仍可调用
- **影响**: 可能重新出现多个后端主机启动路径
- **根本原因**: 删除旧运行时入口点之前迁移完成功能
- **预防规则**: 硬删除遗留入口模块并阻止独立子程序主机启动
- **状态**: ✅ 已修复

#### E-011: CLI UX - 重复的 `mini-agent dev up` 显示完整 Python 回溯
- **影响**: 嘈杂的输出和更难的操作员控制
- **根本原因**: `run_dev_command` 直接传播管理器 `RuntimeError`
- **预防规则**: 在开发命令路径中捕获运行时错误并打印简洁的用户友好错误，退出码为 1
- **状态**: ✅ 已修复

#### E-012: 测试工作流 - Gateway v1 TestClient 套件失败，而本地开发后端持有实例锁
- **影响**: 锁敏感测试产生假阴性
- **根本原因**: 在真实主机进程占用相同锁键/端口时运行后端锁测试
- **预防规则**: 为锁敏感套件强制测试前 `dev down` 或在测试环境中隔离锁主机/端口
- **状态**: ✅ 已修复

---

## 🛡️ 硬重构防护栏

### 强制规则

1. **模块映射**: 任何新模块必须映射到 P18 阶段和任务 ID
2. **跨层变更**: 任何跨越路由器/服务/运行时边界的变更必须包含接口契约更新
3. **测试同步**: 删除遗留代码时，在同一切片中删除测试或重写测试
4. **禁止半迁移**: 没有明确例外，不允许合并半迁移路由路径（旧 + 新并发行为）

### 验证检查清单

- [ ] 代码变更映射到任务 ID
- [ ] 跨层变更包含契约更新
- [ ] 删除代码时同步更新测试
- [ ] 无半迁移路由路径
- [ ] Python 文件通过 `py_compile`
- [ ] TypeScript 文件通过 `tsc` 或 `npm run build`
- [ ] 冒烟测试通过

---

## 📝 会话启动检查清单

### 开始开发前

1. [ ] 检查当前阶段文档（`TASKS.md`）
2. [ ] 查看错误记录（`HABITS.md`）避免重复错误
3. [ ] 确认开发环境状态（`mini-agent dev status`）
4. [ ] 拉取最新代码（`git pull`）

### 开发过程中

1. [ ] 小步提交，每个提交引用任务 ID
2. [ ] 变更后立即运行验证
3. [ ] 遇到新错误及时记录到本文档
4. [ ] 保持测试通过

### 提交前

1. [ ] 运行完整测试套件
2. [ ] 检查代码格式和风格
3. [ ] 更新相关文档
4. [ ] 提交消息清晰说明"为什么"

---

## 📚 学习要点

### 架构相关
- 单一运行时原则：一个后端进程只有一个主代理运行时
- 契约优先：API 变更必须先更新契约
- 无兼容层：硬切割比维护兼容层更简单

### 开发流程
- 原子提交：每个提交应该是单一、完整的变更
- 立即验证：变更后立即运行相关测试
- 语言隔离：不要混合不同语言的验证命令

### 测试相关
- 测试隔离：测试不应触碰用户级状态
- 锁敏感测试：串行运行或隔离锁
- 环境一致性：测试环境应与生产环境一致

### 工具使用
- 进程管理：使用 `dev up/down/status/logs` 管理开发环境
- 日志检查：注意控制台编码问题
- 错误处理：提供用户友好的错误消息

---

## 🔄 持续改进

### 已解决的问题
- 运行时启动冲突
- 前端 MIME 类型问题
- 测试隔离问题
- 控制台编码问题
- CLI 用户体验问题

### 正在改进的领域
- UI 文本质量
- 文档完整性
- 测试覆盖率

### 待改进的领域
- 错误消息友好性
- 开发工具易用性
- 性能优化

---

**维护说明**: 
- 每次遇到新错误，及时添加到错误记录
- 每次解决问题，更新状态和学习要点
- 定期回顾，避免重复错误
- 持续更新核心习惯和防护栏

**维护者**: Mini-Agent Core Team
