---
name: minimax-music-playlist
description: Plan or generate a small themed multi-track playlist with clear track roles and order.
metadata:
  trigger_keywords:
    - 播放列表
    - 背景音乐播放列表
    - 歌单
    - playlist
    - 曲目集
    - 背景音乐合集
    - 多首音乐
    - 多首曲子
    - 三首曲子
    - 多个曲目
---

# MiniMax Music Playlist

This is an optional demo-oriented orchestration skill for multi-track music generation.

## Primary Boundary

- Use this skill when the user wants multiple related tracks.
- Use `minimax-music-gen` for a single focused track.
- Use `minimax-multimodal-toolkit` when direct script details are required.

## Core Rule

Do not generate a pile of tracks blindly. Plan the set first, then generate only the tracks the user actually wants.

## Workflow

1. Clarify the playlist goal:
   - background playlist
   - product demo soundtrack
   - mood pack
   - study/focus set
   - story arc / scene sequence
2. Decide the playlist size.
   - default to a small set, such as `3` tracks, unless the user asks for more
3. Define each track before generation:
   - title
   - role in the playlist
   - genre / mood / energy
   - instrumental or vocal
   - loopable or full song
4. Write a compact playlist manifest in the workspace:
   - `playlist.md` or `playlist.json`
5. Generate only the approved tracks.
6. Save all outputs under `minimax-output/playlist/`.
7. Return the track list, file paths, and generation prompts used.

## Good Playlist Shapes

- intro / core / outro
- calm / medium / high-energy
- morning / daytime / night
- scene 1 / scene 2 / scene 3

## Prompting Guidance

- Give each track a distinct role so the playlist does not blur together.
- Keep a shared sonic identity across the set.
- Explicitly state whether vocals should appear.
- Mention loopability for product/demo background music.

## Cost And Quota Awareness

Playlist generation is more expensive than single-track generation.

Before generating many tracks:

- confirm the desired count
- keep the first pass small
- revise prompts before scaling up

## Output Structure

Prefer this directory shape:

```text
minimax-output/
  playlist/
    playlist.md
    01-intro.mp3
    02-main.mp3
    03-outro.mp3
```

If the user only wants the playlist design and prompts, stop after the manifest instead of forcing generation.
