from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import textwrap
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from openai import OpenAI


@dataclass
class DemoConfig:
    topic: str
    genre: str
    num_chapters: int
    words_per_chapter: int
    model: str = "MiniMax-M2.5"
    temperature: float = 0.8
    max_tokens: int = 4096

    @classmethod
    def load(cls, path: Path) -> "DemoConfig":
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")


class MiniMaxNovelDemo:
    def __init__(
        self,
        project_dir: Path,
        config: DemoConfig,
        api_key: str | None,
        api_host: str,
        dry_run: bool = False,
    ) -> None:
        self.project_dir = project_dir
        self.config = config
        self.api_key = api_key
        self.api_host = api_host.rstrip("/")
        self.dry_run = dry_run
        self.config_path = self.project_dir / "project_config.json"
        self.setting_path = self.project_dir / "Novel_setting.txt"
        self.directory_path = self.project_dir / "Novel_directory.txt"
        self.summary_path = self.project_dir / "global_summary.txt"
        self.character_state_path = self.project_dir / "character_state.txt"
        self.plot_arcs_path = self.project_dir / "plot_arcs.txt"
        self.chapters_dir = self.project_dir / "chapters"
        self.audio_dir = self.project_dir / "audio"
        self.voices_dir = self.project_dir / "voices"
        self.covers_dir = self.project_dir / "covers"
        self.illustrations_dir = self.project_dir / "illustrations"

    def bootstrap(self) -> None:
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.chapters_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self.covers_dir.mkdir(parents=True, exist_ok=True)
        self.illustrations_dir.mkdir(parents=True, exist_ok=True)
        if not self.summary_path.exists():
            self.summary_path.write_text("暂无章节摘要。", encoding="utf-8")
        if not self.character_state_path.exists():
            self.character_state_path.write_text("暂无角色状态。", encoding="utf-8")
        if not self.plot_arcs_path.exists():
            self.plot_arcs_path.write_text("暂无剧情主线。", encoding="utf-8")
        self.config.save(self.config_path)

    def _chat(self, system_prompt: str, user_prompt: str, fallback: str) -> str:
        if self.dry_run:
            return fallback
        if not self.api_key:
            raise ValueError("Missing MINIMAX_API_KEY. Set it in environment or use --dry-run.")
        client = OpenAI(api_key=self.api_key, base_url=f"{self.api_host}/v1")
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Model returned empty content.")
        return content.strip()

    def setup_project(self) -> None:
        self.bootstrap()
        setting_prompt = textwrap.dedent(
            f"""
            请基于以下信息为长篇小说做“Step1 设定”：
            主题：{self.config.topic}
            类型：{self.config.genre}
            总章节：{self.config.num_chapters}
            单章字数：{self.config.words_per_chapter}

            输出结构：
            1) 世界观
            2) 核心角色（主角/关键配角/反派）
            3) 主线冲突与暗线
            4) 节奏建议
            """
        ).strip()
        setting_fallback = textwrap.dedent(
            f"""
            【世界观】
            这是一个围绕“{self.config.topic}”构建的{self.config.genre}世界。

            【核心角色】
            主角：拥有强动机且成长空间明确。
            配角：承担情节推进、价值冲突和情感拉力。
            反派：具备可解释性目标，不是纯工具人。

            【主线冲突与暗线】
            主线以阶段性升级推进，暗线用于后期反转。

            【节奏建议】
            每3-5章设置小高潮，章节结尾保留钩子。
            """
        ).strip()
        setting_text = self._chat("你是专业小说策划编辑。", setting_prompt, setting_fallback)
        self.setting_path.write_text(setting_text, encoding="utf-8")

        directory_prompt = textwrap.dedent(
            f"""
            下面是小说设定：
            {setting_text}

            请做“Step2 目录生成”，输出{self.config.num_chapters}章目录。
            严格输出 JSON 数组，每项格式：
            {{"chapter": 1, "title": "章节标题", "summary": "本章摘要"}}
            """
        ).strip()
        directory_fallback = json.dumps(
            [
                {
                    "chapter": chapter_index,
                    "title": f"第{chapter_index}章：关键转折",
                    "summary": f"围绕主题“{self.config.topic}”推进第{chapter_index}章核心事件。",
                }
                for chapter_index in range(1, self.config.num_chapters + 1)
            ],
            ensure_ascii=False,
            indent=2,
        )
        directory_raw = self._chat("你是严谨的小说结构师。", directory_prompt, directory_fallback)
        chapter_items = self._parse_directory(directory_raw)
        self.directory_path.write_text(
            json.dumps(chapter_items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[OK] Step1/Step2 completed: {self.setting_path} | {self.directory_path}")

    def _parse_directory(self, content: str) -> list[dict[str, Any]]:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        items: list[dict[str, Any]] = []
        chapter_cursor = 1
        for line in lines:
            items.append({"chapter": chapter_cursor, "title": f"第{chapter_cursor}章", "summary": line})
            chapter_cursor += 1
        if not items:
            raise ValueError("Failed to parse chapter directory.")
        return items

    def write_chapter(self, chapter_number: int, guidance: str = "") -> tuple[Path, Path]:
        self._check_base_files()
        directory = json.loads(self.directory_path.read_text(encoding="utf-8"))
        chapter_info = next((item for item in directory if int(item.get("chapter", -1)) == chapter_number), None)
        if not chapter_info:
            raise ValueError(f"Chapter {chapter_number} not found in directory.")
        global_summary = self.summary_path.read_text(encoding="utf-8")
        setting_text = self.setting_path.read_text(encoding="utf-8")

        chapter_prompt = textwrap.dedent(
            f"""
            请做“Step3 章节草稿生成”。
            你将基于设定、章节目录和前文摘要写本章内容。

            【小说设定】
            {setting_text}

            【章节信息】
            章节：{chapter_info.get("chapter")}
            标题：{chapter_info.get("title")}
            摘要：{chapter_info.get("summary")}
            用户指导：{guidance or "无"}

            【前文摘要】
            {global_summary}

            输出格式固定为：
            【章节大纲】
            ...
            【章节正文】
            ...
            """
        ).strip()
        chapter_fallback = textwrap.dedent(
            f"""
            【章节大纲】
            1. 开场抛出冲突
            2. 中段强化人物关系与动机
            3. 结尾制造下一章悬念

            【章节正文】
            这是第{chapter_number}章《{chapter_info.get("title")}》的示例正文（dry-run），
            主题围绕“{self.config.topic}”，并根据“{self.config.genre}”风格推进剧情。
            """
        ).strip()
        draft_text = self._chat("你是长篇小说主笔作者。", chapter_prompt, chapter_fallback)
        outline_text, chapter_text = self._split_outline_and_chapter(draft_text)

        outline_path = self.chapters_dir / f"outline_{chapter_number}.txt"
        chapter_path = self.chapters_dir / f"chapter_{chapter_number}.txt"
        outline_path.write_text(outline_text, encoding="utf-8")
        chapter_path.write_text(chapter_text, encoding="utf-8")
        print(f"[OK] Step3 completed: {outline_path} | {chapter_path}")
        return outline_path, chapter_path

    def _split_outline_and_chapter(self, text: str) -> tuple[str, str]:
        outline_key = "【章节大纲】"
        chapter_key = "【章节正文】"
        if outline_key in text and chapter_key in text:
            after_outline = text.split(outline_key, 1)[1]
            outline_part, chapter_part = after_outline.split(chapter_key, 1)
            return outline_part.strip(), chapter_part.strip()
        return "未解析到大纲，已将全部内容视为正文。", text.strip()

    def finalize_chapter(self, chapter_number: int) -> None:
        self._check_base_files()
        chapter_path = self.chapters_dir / f"chapter_{chapter_number}.txt"
        if not chapter_path.exists():
            raise FileNotFoundError(f"Chapter draft not found: {chapter_path}")
        chapter_text = chapter_path.read_text(encoding="utf-8")
        old_summary = self.summary_path.read_text(encoding="utf-8")
        old_state = self.character_state_path.read_text(encoding="utf-8")
        old_arcs = self.plot_arcs_path.read_text(encoding="utf-8")

        summary_prompt = textwrap.dedent(
            f"""
            请做“Step4 定稿后的状态更新”，输出新的全局摘要（不超过500字）。
            旧摘要：
            {old_summary}

            新章节：
            {chapter_text}
            """
        ).strip()
        summary_fallback = f"{old_summary}\n- 新增第{chapter_number}章关键事件：主线冲突进一步升级。"
        new_summary = self._chat("你是小说编辑。", summary_prompt, summary_fallback)
        self.summary_path.write_text(new_summary.strip(), encoding="utf-8")

        state_prompt = textwrap.dedent(
            f"""
            根据新章节更新角色状态，输出要点清单。
            旧角色状态：
            {old_state}

            新章节：
            {chapter_text}
            """
        ).strip()
        state_fallback = f"{old_state}\n- 第{chapter_number}章后：主角信念更坚定，反派动机更清晰。"
        new_state = self._chat("你是角色弧光分析师。", state_prompt, state_fallback)
        self.character_state_path.write_text(new_state.strip(), encoding="utf-8")

        arc_prompt = textwrap.dedent(
            f"""
            更新剧情主线追踪，保留历史并追加本章变化，输出条目列表。
            旧主线：
            {old_arcs}

            新章节：
            {chapter_text}
            """
        ).strip()
        arc_fallback = f"{old_arcs}\n- 第{chapter_number}章：主线进入下一阶段。"
        new_arcs = self._chat("你是剧情统筹。", arc_prompt, arc_fallback)
        self.plot_arcs_path.write_text(new_arcs.strip(), encoding="utf-8")

        final_path = self.chapters_dir / f"final_chapter_{chapter_number}.txt"
        final_path.write_text(chapter_text, encoding="utf-8")
        print(f"[OK] Step4 completed: {final_path}")

    def clone_voice(
        self,
        reference_audio: Path,
        voice_id: str,
        clone_model: str = "speech-02-turbo",
        voice_api_base: str = "https://api.minimax.chat",
    ) -> Path:
        if not reference_audio.exists():
            raise FileNotFoundError(f"Reference audio not found: {reference_audio}")
        output_path = self.voices_dir / f"voice_clone_{voice_id}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.dry_run:
            result = {
                "voice_id": voice_id,
                "file_id": f"dry-run-{reference_audio.stem}",
                "model": clone_model,
                "created_at": datetime.now().isoformat(),
                "dry_run": True,
            }
            output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[OK] Voice clone dry-run result: {output_path}")
            return output_path
        if not self.api_key:
            raise ValueError("Missing MINIMAX_API_KEY for voice clone.")

        upload_url = f"{voice_api_base.rstrip('/')}/v1/files/upload"
        clone_url = f"{voice_api_base.rstrip('/')}/v1/voice_clone"
        with reference_audio.open("rb") as file_handle:
            upload_resp = requests.post(
                upload_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (reference_audio.name, file_handle, "audio/wav")},
                data={"purpose": "voice_clone"},
                timeout=60,
            )
        upload_resp.raise_for_status()
        upload_data = upload_resp.json()
        file_id = (
            upload_data.get("file", {}).get("file_id")
            or upload_data.get("data", {}).get("file_id")
            or upload_data.get("file_id")
        )
        if not file_id:
            raise RuntimeError(f"Voice clone upload failed: {upload_data}")

        clone_resp = requests.post(
            clone_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"file_id": file_id, "voice_id": voice_id, "model": clone_model},
            timeout=60,
        )
        clone_resp.raise_for_status()
        clone_data = clone_resp.json()
        result = {
            "voice_id": voice_id,
            "file_id": file_id,
            "model": clone_model,
            "clone_response": clone_data,
            "created_at": datetime.now().isoformat(),
        }
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] Voice clone completed: {output_path}")
        return output_path

    def tts_chapter(
        self,
        chapter_number: int,
        voice_id: str,
        model: str = "speech-2.6-hd",
        emotion: str = "happy",
    ) -> Path:
        chapter_path = self.chapters_dir / f"final_chapter_{chapter_number}.txt"
        if not chapter_path.exists():
            chapter_path = self.chapters_dir / f"chapter_{chapter_number}.txt"
        if not chapter_path.exists():
            raise FileNotFoundError(f"Chapter not found: {chapter_path}")
        text = chapter_path.read_text(encoding="utf-8")
        return self.tts_text(text=text, output_name=f"chapter_{chapter_number}.mp3", voice_id=voice_id, model=model, emotion=emotion)

    def tts_text(
        self,
        text: str,
        output_name: str,
        voice_id: str,
        model: str = "speech-2.6-hd",
        emotion: str = "happy",
    ) -> Path:
        output_path = self.audio_dir / output_name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.dry_run:
            output_path.write_bytes(b"DRY_RUN_AUDIO")
            print(f"[OK] TTS dry-run audio written: {output_path}")
            return output_path
        if not self.api_key:
            raise ValueError("Missing MINIMAX_API_KEY for TTS.")
        tts_url = f"{self.api_host}/v1/t2a_v2"
        response = requests.post(
            tts_url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "text": text,
                "stream": False,
                "voice_setting": {"voice_id": voice_id, "speed": 1, "emotion": emotion},
                "audio_setting": {"sample_rate": 32000, "format": "mp3"},
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        audio_data = payload.get("data", {}).get("audio")
        if not audio_data:
            raise RuntimeError(f"TTS response missing audio data: {payload}")
        audio_bytes = self._decode_audio_payload(audio_data)
        output_path.write_bytes(audio_bytes)
        print(f"[OK] TTS completed: {output_path}")
        return output_path

    def _generate_image_to_path(
        self,
        prompt: str,
        output_path: Path,
        model: str = "image-01-live",
        aspect_ratio: str = "1:1",
        style_type: str = "漫画",
        style_weight: float = 1.0,
        metadata_extra: dict[str, Any] | None = None,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path = output_path.with_suffix(output_path.suffix + ".json")
        metadata_payload: dict[str, Any] = {
            "prompt": prompt,
            "model": model,
            "aspect_ratio": aspect_ratio,
            "style_type": style_type,
            "style_weight": style_weight,
            "created_at": datetime.now().isoformat(),
        }
        if metadata_extra:
            metadata_payload.update(metadata_extra)
        if self.dry_run:
            tiny_png_base64 = (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wn3kJkAAAAASUVORK5CYII="
            )
            output_path.write_bytes(base64.b64decode(tiny_png_base64))
            metadata_payload["dry_run"] = True
            metadata_path.write_text(json.dumps(metadata_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[OK] Image dry-run output: {output_path}")
            return output_path
        if not self.api_key:
            raise ValueError("Missing MINIMAX_API_KEY for image generation.")

        image_url_api = f"{self.api_host}/v1/image_generation"
        response = requests.post(
            image_url_api,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "response_format": "url",
                "style": {"style_type": style_type, "style_weight": style_weight},
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        image_urls = payload.get("data", {}).get("image_urls") or []
        if not image_urls:
            raise RuntimeError(f"Image generation response missing image_urls: {payload}")
        image_url = image_urls[0]

        download_resp = requests.get(image_url, timeout=120)
        download_resp.raise_for_status()
        output_path.write_bytes(download_resp.content)

        metadata_payload["image_url"] = image_url
        metadata_path.write_text(json.dumps(metadata_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] Image completed: {output_path}")
        return output_path

    def generate_cover_image(
        self,
        prompt: str,
        output_name: str = "cover.png",
        model: str = "image-01-live",
        aspect_ratio: str = "1:1",
        style_type: str = "漫画",
        style_weight: float = 1.0,
    ) -> Path:
        output_path = self.covers_dir / output_name
        return self._generate_image_to_path(
            prompt=prompt,
            output_path=output_path,
            model=model,
            aspect_ratio=aspect_ratio,
            style_type=style_type,
            style_weight=style_weight,
            metadata_extra={"asset_type": "cover"},
        )

    def generate_chapter_illustrations(
        self,
        chapter_number: int,
        count: int = 3,
        model: str = "image-01-live",
        aspect_ratio: str = "16:9",
        style_type: str = "漫画",
        style_weight: float = 1.0,
    ) -> list[Path]:
        if count < 1:
            raise ValueError("count must be >= 1")
        chapter_path = self.chapters_dir / f"final_chapter_{chapter_number}.txt"
        if not chapter_path.exists():
            chapter_path = self.chapters_dir / f"chapter_{chapter_number}.txt"
        if not chapter_path.exists():
            raise FileNotFoundError(f"Chapter not found: {chapter_path}")

        chapter_text = chapter_path.read_text(encoding="utf-8")
        prompt_builder = textwrap.dedent(
            f"""
            你是小说插图分镜设计师。请根据以下章节正文提炼 {count} 个“可直接用于文生图”的画面提示词。
            要求：
            1) 每个场景画面明确、可视化强
            2) 人物动作、环境光影、镜头感清晰
            3) 风格统一，适配小说章节插图
            4) 禁止输出解释性文字

            章节正文：
            {chapter_text}

            仅输出 JSON 数组，格式：
            [
              {{"title": "场景标题", "prompt": "文生图提示词"}}
            ]
            """
        ).strip()
        fallback_scenes = [
            {
                "title": f"chapter_{chapter_number}_scene_{index}",
                "prompt": f"小说第{chapter_number}章插图，关键场景{index}，{self.config.genre}风格，电影感构图，细节丰富",
            }
            for index in range(1, count + 1)
        ]
        scene_raw = self._chat("你是专业插画分镜设计师。", prompt_builder, json.dumps(fallback_scenes, ensure_ascii=False))
        scenes = self._parse_illustration_scenes(scene_raw, chapter_number=chapter_number, fallback_count=count)

        generated_paths: list[Path] = []
        for scene_index, scene in enumerate(scenes[:count], start=1):
            title = str(scene.get("title", f"chapter_{chapter_number}_scene_{scene_index}"))
            prompt = str(scene.get("prompt", "")).strip()
            if not prompt:
                prompt = f"小说第{chapter_number}章插图，场景{scene_index}，{self.config.genre}风格，电影感构图"
            output_path = self.illustrations_dir / f"chapter_{chapter_number}_ill_{scene_index}.png"
            image_path = self._generate_image_to_path(
                prompt=prompt,
                output_path=output_path,
                model=model,
                aspect_ratio=aspect_ratio,
                style_type=style_type,
                style_weight=style_weight,
                metadata_extra={
                    "asset_type": "illustration",
                    "chapter": chapter_number,
                    "scene_index": scene_index,
                    "scene_title": title,
                },
            )
            generated_paths.append(image_path)

        manifest = {
            "chapter": chapter_number,
            "count": len(generated_paths),
            "model": model,
            "aspect_ratio": aspect_ratio,
            "style_type": style_type,
            "style_weight": style_weight,
            "items": [
                {
                    "index": item_index,
                    "file": str(path),
                    "scene_title": str(scenes[item_index - 1].get("title", "")) if item_index - 1 < len(scenes) else "",
                    "prompt": str(scenes[item_index - 1].get("prompt", "")) if item_index - 1 < len(scenes) else "",
                }
                for item_index, path in enumerate(generated_paths, start=1)
            ],
            "created_at": datetime.now().isoformat(),
        }
        manifest_path = self.illustrations_dir / f"chapter_{chapter_number}_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] Chapter illustrations completed: {len(generated_paths)} images | {manifest_path}")
        return generated_paths

    def _parse_illustration_scenes(self, raw: str, chapter_number: int, fallback_count: int) -> list[dict[str, Any]]:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                normalized: list[dict[str, Any]] = []
                for index, item in enumerate(parsed, start=1):
                    if isinstance(item, dict):
                        normalized.append(
                            {
                                "title": item.get("title", f"chapter_{chapter_number}_scene_{index}"),
                                "prompt": item.get("prompt", ""),
                            }
                        )
                    elif isinstance(item, str):
                        normalized.append({"title": f"chapter_{chapter_number}_scene_{index}", "prompt": item})
                if normalized:
                    return normalized
        except json.JSONDecodeError:
            pass

        lines = [line.strip("-• \t") for line in raw.splitlines() if line.strip()]
        if lines:
            return [
                {"title": f"chapter_{chapter_number}_scene_{index}", "prompt": line}
                for index, line in enumerate(lines[:fallback_count], start=1)
            ]
        return [
            {
                "title": f"chapter_{chapter_number}_scene_{index}",
                "prompt": f"小说第{chapter_number}章插图，场景{index}，{self.config.genre}风格，电影感构图",
            }
            for index in range(1, fallback_count + 1)
        ]

    def _decode_audio_payload(self, audio_data: str) -> bytes:
        try:
            return bytes.fromhex(audio_data)
        except (ValueError, TypeError):
            pass
        try:
            return base64.b64decode(audio_data)
        except (binascii.Error, ValueError, TypeError) as exc:
            raise RuntimeError("Failed to decode audio payload.") from exc

    def _check_base_files(self) -> None:
        if not self.setting_path.exists() or not self.directory_path.exists():
            raise FileNotFoundError("Project is not initialized. Run setup first.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mini-Agent Demo: Novel Generator + TTS + Image Cover + Voice Clone")
    parser.add_argument("--project-dir", default="workspace/mini-agent-novel-demo", help="Project output directory")
    parser.add_argument("--api-host", default=os.getenv("MINIMAX_API_HOST", "https://api.minimaxi.com"), help="MiniMax API host")
    parser.add_argument("--dry-run", action="store_true", help="Run without real API calls")

    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser("setup", help="Step1+Step2 generate setting and chapter directory")
    setup_parser.add_argument("--topic", required=True)
    setup_parser.add_argument("--genre", required=True)
    setup_parser.add_argument("--num-chapters", type=int, default=12)
    setup_parser.add_argument("--words-per-chapter", type=int, default=2500)
    setup_parser.add_argument("--model", default="MiniMax-M2.5")
    setup_parser.add_argument("--temperature", type=float, default=0.8)
    setup_parser.add_argument("--max-tokens", type=int, default=4096)

    write_parser = subparsers.add_parser("write", help="Step3 generate draft for one chapter")
    write_parser.add_argument("--chapter", type=int, required=True)
    write_parser.add_argument("--guidance", default="")

    finalize_parser = subparsers.add_parser("finalize", help="Step4 finalize one chapter and update states")
    finalize_parser.add_argument("--chapter", type=int, required=True)

    clone_parser = subparsers.add_parser("clone-voice", help="Clone voice from reference audio")
    clone_parser.add_argument("--reference-audio", required=True)
    clone_parser.add_argument("--voice-id", required=True)
    clone_parser.add_argument("--clone-model", default="speech-02-turbo")
    clone_parser.add_argument("--voice-api-base", default="https://api.minimax.chat")

    tts_chapter_parser = subparsers.add_parser("tts-chapter", help="Generate chapter narration audio")
    tts_chapter_parser.add_argument("--chapter", type=int, required=True)
    tts_chapter_parser.add_argument("--voice-id", required=True)
    tts_chapter_parser.add_argument("--tts-model", default="speech-2.6-hd")
    tts_chapter_parser.add_argument("--emotion", default="happy")

    tts_text_parser = subparsers.add_parser("tts-text", help="Generate TTS from plain text")
    tts_text_parser.add_argument("--text", required=True)
    tts_text_parser.add_argument("--output-name", default="custom_text.mp3")
    tts_text_parser.add_argument("--voice-id", required=True)
    tts_text_parser.add_argument("--tts-model", default="speech-2.6-hd")
    tts_text_parser.add_argument("--emotion", default="happy")

    cover_parser = subparsers.add_parser("cover-image", help="Generate podcast/novel cover image")
    cover_parser.add_argument("--prompt", required=True)
    cover_parser.add_argument("--output-name", default="cover.png")
    cover_parser.add_argument("--image-model", default="image-01-live")
    cover_parser.add_argument("--aspect-ratio", default="1:1")
    cover_parser.add_argument("--style-type", default="漫画")
    cover_parser.add_argument("--style-weight", type=float, default=1.0)

    ill_parser = subparsers.add_parser("illustrate-chapter", help="Generate multiple illustrations for a chapter")
    ill_parser.add_argument("--chapter", type=int, required=True)
    ill_parser.add_argument("--count", type=int, default=3)
    ill_parser.add_argument("--image-model", default="image-01-live")
    ill_parser.add_argument("--aspect-ratio", default="16:9")
    ill_parser.add_argument("--style-type", default="漫画")
    ill_parser.add_argument("--style-weight", type=float, default=1.0)

    pipeline_parser = subparsers.add_parser("pipeline", help="Run write+finalize for chapter range")
    pipeline_parser.add_argument("--start", type=int, default=1)
    pipeline_parser.add_argument("--end", type=int, required=True)
    pipeline_parser.add_argument("--guidance", default="")

    return parser.parse_args()


def build_config_from_setup(args: argparse.Namespace) -> DemoConfig:
    return DemoConfig(
        topic=args.topic,
        genre=args.genre,
        num_chapters=args.num_chapters,
        words_per_chapter=args.words_per_chapter,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )


def main() -> None:
    args = parse_args()
    project_dir = Path(args.project_dir).expanduser().resolve()
    api_key = os.getenv("MINIMAX_API_KEY")

    if args.command == "setup":
        config = build_config_from_setup(args)
        demo = MiniMaxNovelDemo(project_dir=project_dir, config=config, api_key=api_key, api_host=args.api_host, dry_run=args.dry_run)
        demo.setup_project()
        return

    config_path = project_dir / "project_config.json"
    config = DemoConfig.load(config_path)
    demo = MiniMaxNovelDemo(project_dir=project_dir, config=config, api_key=api_key, api_host=args.api_host, dry_run=args.dry_run)

    if args.command == "write":
        demo.write_chapter(chapter_number=args.chapter, guidance=args.guidance)
        return

    if args.command == "finalize":
        demo.finalize_chapter(chapter_number=args.chapter)
        return

    if args.command == "clone-voice":
        demo.clone_voice(
            reference_audio=Path(args.reference_audio).expanduser().resolve(),
            voice_id=args.voice_id,
            clone_model=args.clone_model,
            voice_api_base=args.voice_api_base,
        )
        return

    if args.command == "tts-chapter":
        demo.tts_chapter(
            chapter_number=args.chapter,
            voice_id=args.voice_id,
            model=args.tts_model,
            emotion=args.emotion,
        )
        return

    if args.command == "tts-text":
        demo.tts_text(
            text=args.text,
            output_name=args.output_name,
            voice_id=args.voice_id,
            model=args.tts_model,
            emotion=args.emotion,
        )
        return

    if args.command == "cover-image":
        demo.generate_cover_image(
            prompt=args.prompt,
            output_name=args.output_name,
            model=args.image_model,
            aspect_ratio=args.aspect_ratio,
            style_type=args.style_type,
            style_weight=args.style_weight,
        )
        return

    if args.command == "illustrate-chapter":
        demo.generate_chapter_illustrations(
            chapter_number=args.chapter,
            count=args.count,
            model=args.image_model,
            aspect_ratio=args.aspect_ratio,
            style_type=args.style_type,
            style_weight=args.style_weight,
        )
        return

    if args.command == "pipeline":
        for chapter_number in range(args.start, args.end + 1):
            demo.write_chapter(chapter_number=chapter_number, guidance=args.guidance)
            demo.finalize_chapter(chapter_number=chapter_number)
        return

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
