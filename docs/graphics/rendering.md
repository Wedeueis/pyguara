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
