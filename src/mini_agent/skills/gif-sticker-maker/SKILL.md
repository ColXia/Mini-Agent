---
name: gif-sticker-maker
description: Create short looping GIFs, sticker-style animations, reaction assets, and emoji-scale motion graphics. Use whenever the user asks for a GIF, animated sticker, emoji animation, reaction loop, mascot motion, or a lightweight animated asset for chat, social, or demo use.
license: Complete terms in LICENSE.txt
requires:
  python_packages: pillow, imageio, imageio_ffmpeg, numpy
metadata:
  trigger_keywords:
    - GIF
    - 动图
    - 表情包
    - 贴纸
    - 动画
---

# GIF Sticker Maker

Create compact looping motion assets by reusing the bundled toolkit instead of rewriting animation primitives from scratch.

## Toolkit Layout

- `core/gif_builder.py`: frame assembly and export
- `core/validators.py`: size and dimension validation
- `core/visual_effects.py`: reusable visual effects
- `templates/`: motion primitives such as shake, bounce, pulse, slide, flip, zoom, and morph

## Environment

Use `uv` for Python execution:

```bash
if [ ! -d .venv ]; then uv venv; fi
uv pip install -r requirements.txt
```

Create a small driver script in the workspace when the animation is non-trivial, then run it with:

```bash
uv run python your_script.py
```

## Choose An Output Profile First

- Sticker / emoji loop:
  - `128x128`
  - `10-12 fps`
  - `32-64` colors
  - very short seamless loop
- Chat reaction GIF:
  - `320-480px` wide
  - `12-18 fps`
  - about `2-5s`
- If the platform is specified, adapt to that platform's limits and validate before finalizing.

## Workflow

1. Clarify the target:
   - sticker
   - emoji-scale reaction
   - larger chat GIF
2. Choose the motion pattern from `templates/`.
3. Build frames with `core/gif_builder.py`.
4. Validate output size and dimensions with `core/validators.py`.
5. Reduce frames, colors, or canvas size if the file is too large.
6. Save the final asset in the workspace together with the source script when the generation logic is custom.

## Good Defaults

- Keep the subject simple and readable at small sizes.
- Prefer strong silhouette over tiny detail.
- Avoid long loops unless the user specifically wants them.
- Use motion that reads clearly in the first second.

## When To Read More

Read the specific file you need instead of loading the whole toolkit:

- one template under `templates/` when you already know the motion style
- `core/validators.py` when size limits matter
- `core/gif_builder.py` when export behavior needs adjustment

If the user wants image generation first and animation second, combine this skill with `minimax-multimodal-toolkit`.
