# Mini-Agent Demo：小说生成 + 语音合成 + 文生图封面

这个 Demo 融合了：

- `AI_NovelGenerator` 的小说四步流程（设定 → 目录 → 草稿 → 定稿）
- MiniMax AI Podcast 方案中的 3 个核心能力：
  - 文本生成（脚本/章节）
  - 语音合成（TTS）
  - 文生图（封面图）
- 以及可选的语音克隆

## 目录结构

- `novel_demo.py`：主程序（CLI）
- `config.example.json`：配置示例

默认输出目录：`workspace/mini-agent-novel-demo/`

- `Novel_setting.txt`
- `Novel_directory.txt`
- `chapters/outline_*.txt`
- `chapters/chapter_*.txt`
- `chapters/final_chapter_*.txt`
- `global_summary.txt`
- `character_state.txt`
- `plot_arcs.txt`
- `voices/voice_clone_*.json`
- `audio/*.mp3`
- `covers/*.png`
- `illustrations/*.png`

## 环境准备

在 `Mini-Agent` 项目根目录执行过 `uv sync` 后，设置环境变量：

```powershell
setx MINIMAX_API_KEY "你的真实Key"
setx MINIMAX_API_HOST "https://api.minimaxi.com"
```

重开终端后生效。

## 快速演示（不消耗额度）

```powershell
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py --dry-run setup --topic "失落星舰的回声" --genre "太空歌剧" --num-chapters 6 --words-per-chapter 1800
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py --dry-run write --chapter 1 --guidance "首章直接抛出危机"
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py --dry-run finalize --chapter 1
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py --dry-run tts-chapter --chapter 1 --voice-id "Chinese (Mandarin)_Gentle_Senior"
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py --dry-run cover-image --prompt "赛博朋克悬疑小说封面，霓虹夜景，侦探背影，电影感" --output-name "cover_ch1.png"
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py --dry-run illustrate-chapter --chapter 1 --count 3 --aspect-ratio "16:9" --style-type "漫画"
```

## 真实生成流程

### 1) Step1 + Step2：生成设定和目录

```powershell
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py setup --topic "失落星舰的回声" --genre "太空歌剧" --num-chapters 12 --words-per-chapter 2500
```

### 2) Step3：生成章节草稿

```powershell
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py write --chapter 1 --guidance "强调角色间的不信任"
```

### 3) Step4：定稿并更新状态

```powershell
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py finalize --chapter 1
```

### 4) 章节配音（TTS）

```powershell
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py tts-chapter --chapter 1 --voice-id "Chinese (Mandarin)_Gentle_Senior"
```

### 5) 文生图封面（Image Generation）

```powershell
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py cover-image --prompt "科幻悬疑小说封面，赛博城市，主角站在高楼边缘，1:1，漫画风" --output-name "cover_ch1.png" --aspect-ratio "1:1" --style-type "漫画"
```

### 6) 语音克隆（可选）

参考音频建议 10 秒到 5 分钟（建议约 15 秒）。

```powershell
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py clone-voice --reference-audio "C:/path/to/ref.wav" --voice-id "my_narrator_voice"
```

### 7) 章节插图（Illustrations）

```powershell
uv run python examples/mini_agent_demo/minimax_novel_demo/novel_demo.py illustrate-chapter --chapter 1 --count 3 --aspect-ratio "16:9" --style-type "漫画"
```

说明：
- 会基于该章节正文自动拆分出多个可视化场景提示词。
- 默认写入 `illustrations/chapter_1_ill_1.png` 等文件。
- 同时会生成 `illustrations/chapter_1_manifest.json` 记录每张图的 prompt。

## 在 Mini-Agent 中调用

```powershell
uv run mini-agent --workspace C:/Users/Conli/Mini-Agent/workspace
```

然后在对话中说：

“请使用 `minimax-novel-demo`，先完成 Step1/2，再生成第1章、定稿、配音，并生成封面和3张插图。”
