from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from types import SimpleNamespace

from mini_agent.agent_core.context.turn_context import RuntimeTurnContext, SkillCatalogTurnContextProvider


DEFAULT_CASES: list[tuple[str, str]] = [
    ("帮我重做这个 React 管理后台页面布局和交互", "frontend-dev"),
    ("给这个项目做一个前后端打通的设置页和保存接口", "fullstack-dev"),
    ("修一下 Android Compose 页面状态和导航", "android-native-dev"),
    ("补一个 SwiftUI 设置页并处理 iOS 权限弹窗", "ios-application-dev"),
    ("改这个 Flutter 页面和路由跳转", "flutter-dev"),
    ("修复 Expo 应用里的 React Native 登录页键盘遮挡", "react-native-dev"),
    ("写一个水波纹 fragment shader 做 hover 效果", "shader-dev"),
    ("生成一段轻柔钢琴背景音乐", "minimax-music-gen"),
    ("看这张界面截图，帮我分析哪里布局错了", "vision-analysis"),
    ("做一个聊天里能发的可爱表情 GIF", "gif-sticker-maker"),
    ("给 nyonyo 做一段简短的欢迎歌曲", "buddy-sings"),
    ("给这个 demo 设计一个三首曲子的背景音乐播放列表", "minimax-music-playlist"),
]


async def run_audit(*, builtin_dir: Path, top_k: int) -> int:
    provider = SkillCatalogTurnContextProvider(
        builtin_dir=builtin_dir,
        top_k=top_k,
        max_description_chars=200,
    )
    misses = 0
    for prompt, expected in DEFAULT_CASES:
        item = await provider.prepare(
            turn_context=RuntimeTurnContext(
                session_id="audit-session",
                submission_id="audit-submission",
                user_input=prompt,
            ),
            agent=SimpleNamespace(messages=[]),
        )
        skills = list(item.metadata.get("skills", [])) if item else []
        top = skills[0] if skills else "<none>"
        ok = top == expected
        if not ok:
            misses += 1
        status = "OK" if ok else "MISS"
        print(f"[{status}] expected={expected} top={top} prompt={prompt}")
        if skills:
            print("  skills=", ", ".join(skills))
    print(f"TOTAL_MISS={misses}")
    return misses


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit builtin skill triggering against sample prompts.")
    parser.add_argument(
        "--builtin-dir",
        default="src/mini_agent/skills",
        help="Builtin skills directory to audit.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="How many ranked skills to inspect for each prompt.",
    )
    args = parser.parse_args()

    misses = asyncio.run(
        run_audit(
            builtin_dir=Path(args.builtin_dir).expanduser().resolve(),
            top_k=max(1, int(args.top_k)),
        )
    )
    raise SystemExit(1 if misses else 0)


if __name__ == "__main__":
    main()
