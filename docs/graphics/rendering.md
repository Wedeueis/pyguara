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

Materials combine shader, texture, and uniforms:

```python
from pyguara.graphics.materials import Material, Shader

# Custom material with grayscale shader
grayscale_shader = Shader(ctx, vert_src, frag_src)
material = Material(
    shader=grayscale_shader,
    texture=my_texture,
    uniforms={"intensity": 0.8}
)

# Assign to sprite
sprite.material = material
```

Sprites without explicit materials use the default sprite material automatically.

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

## Components

### Camera2D
Handles Coordinate Transformation (World Space <-> Screen Space). Supports Zoom, Rotation, and Panning.

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
| Lighting | Dynamic light maps | Fully lit (no shadows) |
| Post-processing | Bloom, vignette, etc. | Pass-through (no effects) |
| Materials | Custom shaders | Default only |

Game code using these features runs unchanged on Pygame - stubs accept the API calls but skip the GPU operations.

---

# UI System

The UI system (`pyguara.ui`) is immediate-mode friendly but retains state via an Object-Oriented widget tree.

## Architecture
- **UIManager**: Routes input events (`OnMouseEvent`) to widgets.
- **UIElement**: Base class for all widgets (`Button`, `Panel`, `Label`).
- **Layouts**: `BoxContainer` handles automatic positioning (Vertical/Horizontal).
- **Theme**: A centralized `UITheme` controls colors and spacing.

## Integration
The UI is rendered via the `UIRenderer` protocol, allowing it to sit on top of the main game render pass.
