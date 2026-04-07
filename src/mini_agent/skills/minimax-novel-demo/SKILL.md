---
name: minimax-novel-demo
description: 运行“小说生成 + 语音合成 + 文生图封面 + 章节插图 + 可选语音克隆”的 Mini-Agent 附属小程序。用户提到小说自动化创作、有声化、封面/插图生成时使用。
---

# MiniMax Novel Demo

当用户希望在当前工程里体验“小说生成器 + 多模态产物（音频与封面）”时，使用本技能。

## 目标

通过脚本 `examples/mini_agent_demo/minimax_novel_demo/novel_demo.py` 完成：

1. Step1：小说设定生成
2. Step2：章节目录生成
3. Step3：章节草稿生成
4. Step4：章节定稿与状态更新
5. TTS：章节配音
6. 文生图：生成封面图
7. 文生图：按章节批量生成插图
7. 可选：语音克隆

## 执行规则

1. 优先检查环境变量：
   - `MINIMAX_API_KEY`
   - `MINIMAX_API_HOST`（中国大陆一般是 `https://api.minimaxi.com`）
2. 用户未明确要求真实调用时，优先使用 `--dry-run` 快速演示流程。
3. 输出目录默认：
   - `workspace/mini-agent-novel-demo`
4. 基础流程顺序：
   - `setup` → `write` → `finalize`
5. 多模态扩展：
   - 有声化：`tts-chapter`
   - 封面图：`cover-image`
   - 章节插图：`illustrate-chapter`
   - 语音克隆：`clone-voice`

## 常用命令模板

```bash
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py setup --topic "xxx" --genre "xxx" --num-chapters 12 --words-per-chapter 2500
```

```bash
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py write --chapter 1 --guidance "xxx"
```

```bash
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py finalize --chapter 1
```

```bash
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py tts-chapter --chapter 1 --voice-id "Chinese (Mandarin)_Gentle_Senior"
```

```bash
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py cover-image --prompt "科幻悬疑小说封面，霓虹夜景，主角背影，漫画风" --output-name "cover_ch1.png"
```

```bash
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py illustrate-chapter --chapter 1 --count 3 --aspect-ratio "16:9" --style-type "漫画"
```

```bash
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py clone-voice --reference-audio "/path/to/ref.wav" --voice-id "my_narrator_voice"
```
