---
name: buddy-sings
description: Create a short personalized sung demo, jingle, or character-style musical response.
metadata:
  trigger_keywords:
    - 唱歌
    - 欢迎歌
    - 主题曲
    - jingle
    - 短歌
    - sing
---

# Buddy Sings

This is an optional demo-facing skill for turning a short idea into a friendly sung output.

## Primary Boundary

- Use this skill for short, playful, user-facing musical moments.
- Do not use it for serious soundtrack production or structured music generation workflows. For that, prefer `minimax-music-gen`.
- Load `minimax-multimodal-toolkit` when actual script-level generation details are needed.

## Good Use Cases

- a short greeting song
- a buddy theme tune
- a one-topic jingle
- a playful musical reply for demo videos
- a short sung status message

## Workflow

1. Clarify the intent:
   - who the song is for
   - mood
   - length
   - language
   - whether vocals are desired
2. Keep the scope small:
   - short lyrics
   - one clear hook
   - one clear mood
3. Write concise lyrics with visible structure:
   - `[intro]`
   - `[verse]`
   - `[chorus]`
   - `[outro]`
4. Use the MiniMax music generation path to create the sung output.
5. Save results under `minimax-output/`.
6. Return the generated file path together with the final lyrics used.

## Style Guidance

- Prefer memorable hook lines over long verses.
- Keep the concept easy to recognize on first listen.
- Match the tone to the user's request:
  - warm
  - funny
  - cute
  - upbeat
  - dramatic
- Avoid over-long or overly dense lyrics for demo use.

## If The User Wants Spoken + Sung Output

Use this skill for the sung part, and combine with the TTS path from `minimax-multimodal-toolkit` when a spoken intro/outro is also needed.

## Output Expectations

Aim to produce:

- the generated audio file
- the final lyric text
- a short note describing the intended vibe
