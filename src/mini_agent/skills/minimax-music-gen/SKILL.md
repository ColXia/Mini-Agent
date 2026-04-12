---
name: minimax-music-gen
description: Generate songs, instrumentals, and music prompts through MiniMax music capabilities. Use whenever the user asks for music generation, background tracks, short songs, instrumental cues, prompt-driven composition, or audio outputs specifically centered on MiniMax music creation.
metadata:
  trigger_keywords:
    - 音乐
    - 歌曲
    - BGM
    - 配乐
    - 伴奏
    - 生成音乐
---

# MiniMax Music Gen

This skill is the focused music layer on top of Mini-Agent's broader multimodal capability.

## Primary Boundary

- Use this skill when the task is mainly about music generation itself.
- Load `minimax-multimodal-toolkit` as well when the task also needs broader audio/video/image orchestration or direct script details.

## Workflow

1. Clarify the target:
   - instrumental or vocal
   - mood and genre
   - duration expectations
   - use case: demo, background track, jingle, theme, loop
2. Write a concise music prompt that specifies:
   - genre
   - tempo/energy
   - instrumentation
   - mood
   - structure if important
3. Use the music generation path from `minimax-multimodal-toolkit`.
4. Save outputs under `minimax-output/`.
5. If the first result misses the mark, revise the prompt instead of hand-waving the outcome.

## Prompting Guidance

- Prefer specific instrumentation over vague adjectives.
- Specify whether vocals are wanted.
- Mention loopability when the output is for a product/demo background.
- Mention intensity curve when the track should build or stay minimal.

## Operator Notes

The active runnable scripts live under the bundled `minimax-multimodal-toolkit` skill resources. This skill is intentionally narrower so the agent can trigger “music only” guidance without loading the whole multimodal package first.
