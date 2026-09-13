# Rendering Pipeline

PyGuara employs a modern, backend-agnostic rendering architecture located in `pyguara.graphics`.

## Render Graph Architecture

The engine uses a multi-pass render graph for compositing:

```
World Pass → Light Pass → Composite Pass → Post-Process Pass → Final Pass → UI
```

### Render Passes

| Pass | Description |
|------|-------------|
| **WorldPass** | Renders sprites/geometry to a world framebuffer |
| **LightPass** | Renders dynamic lights with additive blending to a light map |
| **CompositePass** | Multiplies world × lightmap for the final lit scene |
| **PostProcessPass** | Applies screen-space effects (bloom, vignette) |
| **FinalPass** | Blits the composed result to the screen |

### Framebuffer Management

The `FramebufferManager` handles FBO lifecycle:
- Automatic creation on first request
- Resize handling when window dimensions change
- Proper cleanup on shutdown

## Core Pipeline

The rendering process within each pass follows these stages:

1.  **Submission**: Entities submit `Renderable` items to the `RenderSystem`.
2.  **Queueing**: Items are stored in a `RenderQueue`.
3.  **Sorting**: The queue is sorted by Layer, Material, and Z-Index.
4.  **Batching**: The `Batcher` groups compatible draw calls (same material) into `RenderBatch` objects.
5.  **Execution**: The backend (e.g., `ModernGLRenderer`) executes the batches.

## Material System

Materials combine shader, texture, and uniforms. A `Shader` wraps an
already-compiled `moderngl.Program`; `ShaderCache` is what turns source into
one, keyed by name so the same shader compiles once:

```python
from pyguara.graphics.materials import Material, ShaderCache

cache = ShaderCache(ctx)
grayscale_shader = cache.get_or_compile("grayscale", vert_src, frag_src)
material = Material(
    shader=grayscale_shader,
    texture=my_texture,
    uniforms={"intensity": 0.8},
)

# Assign to sprite
sprite.material = material
```

**What this does today: sorting, and nothing on the GPU.** A material's `id`
reaches `RenderQueue` and `Batcher`, which sort and break batches by it, so
assigning one is visible in the draw-call structure. But `ModernGLRenderer`
never reads `RenderBatch.material` -- it draws every batch through its own
sprite program -- so a custom shader assigned this way has no effect on what
is rendered. Wiring the backend to honour materials is filed, not built.

Sprites without an explicit material sort together as material `0`.

## 2D Lighting

Dynamic lighting uses light components and a compositing pass:

```python
from pyguara.graphics.lighting import LightSource, AmbientLight

# Point light
entity.add_component(LightSource(
    color=Color(255, 200, 100),
    radius=150.0,
    intensity=1.2,
    falloff=2.0  # Quadratic falloff
))

# Global ambient
ambient_entity.add_component(AmbientLight(
    color=Color(30, 30, 50),
    intensity=0.3
))
```

The light pass renders all lights additively, then the composite pass multiplies world × lightmap.

### Light types

`LightType` picks the shape `light.frag` cuts:

| Type | Shape |
|------|-------|
| `POINT` | Radial gradient from the centre, shaped by `falloff`. The default. |
| `DIRECTIONAL` | Parallel rays — the quad is lit evenly, with no distance falloff. `radius` bounds the area rather than shaping it, so a scene-wide sun is a directional light with a large radius. |
| `SPOT` | A `POINT` masked to a cone of `spot_angle` degrees (the **full** opening, so 60 reaches 30 either side) pointed along `spot_direction`. |

```python
entity.add_component(LightSource(
    light_type=LightType.SPOT,
    radius=240.0,
    spot_angle=50.0,      # full cone opening, degrees
    spot_direction=90.0,  # clockwise from screen +x, so this points down
))
```

**Angles run clockwise from screen +x**, because screen Y points down —
the same convention `IRenderer.draw_line` uses. The cosine of the
half-angle is computed once per frame on the CPU and handed to the shader,
which compares dot products rather than calling `cos` per fragment.

### Flicker

Any light can gutter:

```python
entity.add_component(LightSource(
    color=Color(255, 170, 90),
    flicker_enabled=True,
    flicker_speed=9.0,      # Hz
    flicker_intensity=0.25, # bound, not a scale: stays within ±25% of intensity
))
```

`flicker_intensity` is a **bound**, not a scale — a light set to vary by 25%
never drops below 75% of its configured intensity, and never below zero
whatever the value. Two lights with the same settings do not flicker in
lockstep: the starting phase is derived from the entity id, and from a
checksum of it rather than `hash()`, so a replay reproduces the same
flicker on a later run.

Flicker resolves **on the CPU**, in `LightingSystem.update(dt)`, folded into
the intensity the shader receives. That system already walks every light and
already has `dt`, so this needs no time uniform and no extra instance
attribute — and it stays testable without a GL context, which is the only
kind of lighting test this repository can run everywhere.

### Day/night cycle

`AmbientCycle` drives an `AmbientLight` around a loop of keyframes, which is the
mechanism under a day/night cycle. What the times of day are *called*, and
whether a loop is a day at all, stays with the game:

```python
from pyguara.graphics.lighting import (
    AmbientCycle,
    AmbientCycleSystem,
    LightKeyframe,
)

ambient_entity.add_component(AmbientLight())
ambient_entity.add_component(AmbientCycle(
    keyframes=[
        LightKeyframe(0.00, Color(12, 14, 34), 0.18),   # midnight
        LightKeyframe(0.25, Color(255, 174, 110), 0.65),  # dawn
        LightKeyframe(0.50, Color(255, 250, 235), 1.00),  # noon
        LightKeyframe(0.75, Color(120, 90, 140), 0.45),   # dusk
    ],
    duration=240.0,  # real seconds for one full loop
))

cycle_system = AmbientCycleSystem(entity_manager)   # scene-owned, ticked with dt
```

The loop is a **ring**: the last keyframe interpolates back round to the first
through 1.0/0.0, so there is no need for a keyframe at both ends. Phases are
wrapped, not clamped — `sample_cycle(keyframes, 1.25)` samples 0.25.

`AmbientCycle` requires an `AmbientLight` on the same entity, and is opt-in per
entity: a scene that attaches no cycle behaves exactly as it did before. The
`LightingSystem` needs no changes either — it re-reads `AmbientLight` from the
ECS every tick regardless of what wrote it.

**A cycle owns the `AmbientLight` on its entity**, overwriting colour and
intensity on every tick it plays. A transient flash — lightning, an explosion
lighting the sky — is therefore either a `LightSource` (arguably what lightning
is) or a `playing = False` for its duration. It is not a second writer setting
`intensity` between ticks; that value does not survive the next one.

`sample_cycle(keyframes, phase)` is a plain function over plain data, so a game
tinting its fog, its particles or its UI by the same phase calls it directly
rather than reaching into the system.

## Post-Processing

Screen-space effects are chained via `PostProcessStack`:

```python
from pyguara.graphics.vfx import PostProcessStack, BloomEffect, VignetteEffect

stack = PostProcessStack(ctx, width, height)
stack.add_effect(BloomEffect(ctx, threshold=0.8, intensity=0.5))
stack.add_effect(VignetteEffect(ctx, radius=0.7, softness=0.4))
```

Effects can be enabled/disabled at runtime via `effect.enabled = False`.

Order matters, and is the caller's to choose. Bloom generally runs first, so it
bleeds the scene's own hot colours rather than whatever a later effect drew over
them; a vignette generally runs last, because it is a lens rather than a light.

Shipped effects:

| Effect | What it does |
| --- | --- |
| `BloomEffect` | Bleeds a halo out of anything past a brightness threshold. |
| `HeatHazeEffect` | Refracts the frame with rising hot air, with dust drifting through it. `gust()` kicks up a cloud that settles on its own. |
| `StormEffect` | Procedural rain, sheet lightning and forked bolts. |
| `VignetteEffect` | Darkens the edges of the frame. |

Each of these owns only how the effect *looks*. What the weather or the heat is
*doing* stays with the caller — which is what lets a game tie a strike, a camera
shake and a thunderclap to the same frame.

### Feedback primitives

`pyguara.graphics.vfx` also holds the two small pooled things a game reaches for
when something is hit. Both are composed into a scene rather than resolved from
DI, the same way `ParticleSystem` is:

- **`Sparks`** — a bounded pool of coloured shape particles (`draw_circle` /
  `draw_line`). `ParticleSystem` is the right tool when particles *are*
  sprites; these are not. The two are separate because a spark has no texture
  to bind and none worth authoring: the shape path batches each shape type into
  one instanced draw call from a colour per primitive, with no texture in
  sight.
- **`Shaker`** — several overlapping `CameraShake` impulses summed into one
  pixel offset, so a second impact adds to the first rather than cutting it
  short. The result is a plain offset: a world-space scene adds it to the camera
  position, a screen-space one adds it to what it draws.

## Components

### Camera2D
Handles Coordinate Transformation (World Space <-> Screen Space). Supports Zoom
and Panning. There is one world-to-screen transform (`screen_offset`);
`world_to_screen` / `screen_to_world` / `get_view_bounds` are conveniences
built on it and take an optional `viewport` (defaulting to the camera's
constructed size). Camera rotation is not supported — the render path does not
rotate.

### Viewport
Defines the drawable region on the screen. Used for:
- Split-screen multiplayer.
- Minimaps.
- Aspect ratio enforcement (Letterboxing).

### Geometry
Procedural shapes (`Box`, `Circle`) that lazy-generate their textures. This allows them to be batched alongside standard sprites.

## Backends

The engine uses the `IRenderer` protocol, allowing for different implementations:

- **ModernGLRenderer** (Recommended): GPU-accelerated OpenGL 3.3+ with hardware instancing. Supports all advanced features (lighting, post-processing).
- **PygameBackend**: CPU-based `pygame-ce` rendering. Uses stub implementations for advanced features (renders fully lit, no post-processing).
- **HeadlessBackend**: Discards draw calls. Useful for CI/CD and server-side simulation.

### Graceful Degradation

When using Pygame backend, advanced graphics features gracefully degrade:

| Feature | ModernGL | Pygame |
|---------|----------|--------|
| Sprite rendering | Hardware instanced | Software blitting |
| Per-sprite tint | Per-instance vertex attribute | `BLEND_RGBA_MULT` per sprite |
| Lighting | Dynamic light maps | Fully lit (no shadows) |
| Post-processing | Bloom, vignette, etc. | Pass-through (no effects) |
| Materials | Custom shaders | Default only |

Game code using these features runs unchanged on Pygame - stubs accept the API calls but skip the GPU operations.

---

# UI System

The UI system (`pyguara.ui`) is immediate-mode friendly but retains state via an Object-Oriented widget tree.

## Architecture
- **UIManager**: Routes input events (`OnMouseEvent`) to widgets, and runs a
  layout pass over every root before rendering -- applying `LayoutConstraints`
  and container stacking -- re-run on window resize or `invalidate_layout()`.
- **UIElement**: Base class for all widgets (`Button`, `Panel`, `Label`).
- **Layouts**: `LayoutConstraints` position/size an element against its parent
  (anchor, margin, percentage); `BoxContainer` stacks children
  vertically/horizontally with alignment.
- **Theme**: a global `UITheme` (`get_theme()`/`set_theme()`) controls colors
  and spacing; elements read it live, so a swap re-skins existing widgets.

## Keyboard focus

`UIManager` keeps a focus ring, so a menu is reachable without a mouse:

| Key | Moves |
|---|---|
| `Tab` / `Down` / `Right` | Focus forward, wrapping at the end |
| `Shift+Tab` / `Up` / `Left` | Focus back, wrapping at the start |

```python
element.focusable = True          # Button/Checkbox/Slider/TextInput: already True
manager.focus_next()              # or focus_previous()
manager.focus_ring()              # every focusable element, in order
```

**Order is the element tree, depth-first**, in the order roots were added and
children were parented — the order a reader's eye takes through a declared
layout, with no geometry involved. A hidden or disabled element is skipped
along with its whole subtree, so a collapsed panel's contents aren't reachable
by Tab just because they still exist.

**Traversal is the fallback, not the first move.** The focused element sees the
key first and Tab or an arrow only moves focus if it didn't consume it — which
is what lets a text input keep its arrow keys for the caret while the same keys
traverse a row of buttons.

`focusable` is off by default: a container, a label or a decorative panel is
not a stop on the ring, and opting in is a smaller thing to get right than
opting every layout box out.

## Integration
The UI is rendered via the `UIRenderer` protocol, allowing it to sit on top of the main game render pass.

## Measured ceiling

The render path has been benchmarked; the figures live in
[Measured Limits](../guides/performance.md). Two results are worth knowing
before optimising anything here:

- **At scale the bottleneck is the CPU, not the GPU.** A 20,000-sprite batch
  costs about 16 ms end to end on the ModernGL backend, and four fifths of that
  is the Python loop that packs the instance array. The pack's share grows with
  sprite count -- 42% at 1,000, 81% at 20,000.
- **`Batcher.create_batches` costs more than the draw does** — roughly 53 ms
  for the same 20,000 sprites, more than three times the GL path. Texture
  switching adds about 50% on top.

`RenderQueue.sort` is linear and cheap (2.9 ms at 8,000 commands), so its
per-command lambda is not worth chasing. There is no visibility culling; the
page records what that costs so the trade can be argued from a number.
