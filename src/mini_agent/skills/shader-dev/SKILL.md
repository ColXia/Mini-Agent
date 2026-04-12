---
name: shader-dev
description: Write or debug shaders and GPU-side visual effects, including GLSL, WGSL, HLSL-style logic, material tuning, and render-pipeline visual debugging. Use whenever the user asks for shader code, visual effects, procedural materials, rendering glitches, or GPU-side animation and color work.
metadata:
  trigger_keywords:
    - shader
    - 着色器
    - GLSL
    - WGSL
    - 渲染
    - 特效
---

# Shader Dev

Treat shader work as iterative visual engineering: small changes, fast inspection, clear intent.

## Use This Skill For

- fragment or vertex shader authoring
- procedural color, shape, noise, and motion work
- material tuning and visual effect debugging
- rendering regressions caused by shader logic
- porting shader logic between engines or languages

## Workflow

1. Identify the active environment:
   - GLSL
   - WGSL
   - engine-specific wrapper
   - uniforms and attribute pipeline
2. Isolate the visual goal:
   - color
   - lighting
   - distortion
   - transition
   - procedural pattern
3. Change one visual behavior at a time.
4. Keep math readable with short helper functions when the shader becomes dense.
5. If the issue is visual, produce or inspect screenshots whenever possible.

## Good Practices

- Name uniforms and helper functions clearly.
- Be explicit about coordinate space and normalization assumptions.
- Prefer stable, debuggable math over clever one-liners.
- Watch for precision, branching, and repeated expensive operations.

## Validation

If the repo has a preview harness, use it.

If not, leave the shader code structured so another pass can validate visually with minimal setup. Pair this skill with `vision-analysis` when screenshot comparison is useful.
