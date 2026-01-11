# Implementation Specification: ModernGL Rendering Backend (P1-010)

## 1. Context & Motivation
PyGuara currently uses `pygame-ce` for rendering, which is CPU-bound. While efficient for simple games, it becomes a bottleneck for large entity counts or advanced visual effects (shaders, lighting). ModernGL provides a high-performance, Pythonic wrapper for OpenGL, allowing us to leverage GPU acceleration and hardware instancing.

This migration follows the existing `IRenderer` and `IWindowBackend` protocols, ensuring that game logic remains agnostic of the underlying graphics API.

## 2. Goals
- Implement a GPU-accelerated rendering backend using ModernGL.
- Achieve 10,000+ sprites at 60 FPS via Hardware Instancing.
- Maintain full compatibility with existing `Renderable` components.
- Support custom GLSL shaders for advanced effects.
- Unified coordinate system (mapping OpenGL's NDC to Pygame's pixel coordinates).

## 3. Architecture

### 3.1 Proposed File Structure
```text
pyguara/graphics/backends/moderngl/
├── __init__.py
├── window.py           # Implements IWindowBackend (Setup OpenGL Context)
├── renderer.py         # Implements IRenderer (Buffer management, Drawing)
├── texture.py          # Implements Texture (GL Texture wrapper)
└── shaders/
    ├── sprite.vert     # Vertex Shader (Instancing logic)
    └── sprite.frag     # Fragment Shader
```

### 3.2 Component Roles
- **`PygameGLWindow`**: Uses `pygame.display.set_mode` with `pygame.OPENGL` to create the context.
- **`ModernGLRenderer`**: Manages Vertex Array Objects (VAOs) and Vertex Buffer Objects (VBOs). Implements `render_batch` using `vao.render(instances=N)`.
- **`GLTexture`**: Wraps a `moderngl.Texture` object. Loaded via a new `GLTextureLoader`.

## 4. Implementation Plan

### Phase A: Context & Windowing
1. Add `moderngl` and `numpy` to project dependencies.
2. Create `PygameGLWindow` in `pyguara/graphics/backends/moderngl/window.py`.
3. Ensure context creation handles standard GL attributes (Double buffering, Depth buffer).

### Phase B: Resource Pipeline
1. Create `GLTexture` inheriting from `pyguara.resources.types.Texture`.
2. Implement `GLTextureLoader` in `pyguara.graphics.backends.moderngl.loaders`.
3. Loader logic:
   - Load image via Pygame `image.load()`.
   - Convert Surface to raw bytes.
   - Upload to GPU: `ctx.texture(size, components=4, data=raw_bytes)`.

### Phase C: Shader & Geometry
1. Write `sprite.vert`:
   - Inputs: Quad vertices (constant), Instance Position, Instance Rotation, Instance Scale.
   - Uniforms: `projection` matrix (ortho).
2. Write `sprite.frag`:
   - Basic texture sampler with transparency support.
3. Setup `ModernGLRenderer` with a single static Quad VBO (Triangle Strip).

### Phase D: Batch Rendering (Instancing)
1. Implement `render_batch(batch: RenderBatch)`:
   - Pack instance data (Pos, Rot, Scale) into a `numpy.ndarray`.
   - Update dynamic VBO via `vbo.write()`.
   - Trigger instanced draw call.

## 5. Technical Specifications

### 5.1 Projection Matrix
The Vertex Shader must apply an Orthographic Projection to maintain the "Top-Left (0,0), Y-Down" coordinate system familiar to Pygame users:
```python
# projection = ortho(0, width, height, 0, -1, 1)
```

### 5.2 Instance Data Layout
Each instance in the dynamic VBO should ideally be 5-6 floats:
- `vec2 in_pos` (2 floats)
- `float in_rot` (1 float)
- `vec2 in_scale` (2 floats)
Total: 20 bytes per instance.

## 6. Acceptance Criteria
- [ ] Successfully initializes OpenGL 3.3+ context.
- [ ] Renders all existing `Renderable` entities without code changes.
- [ ] `render_batch` performance is significantly better than Pygame backend for > 2000 sprites.
- [ ] Correct transparency/alpha blending (SrcAlpha/OneMinusSrcAlpha).
- [ ] Clean shutdown (no GL context leaks).

## 7. Future Considerations
- Support for "Post-Processing" passes via Framebuffer Objects (FBOs).
- Integration of a separate "Shape Renderer" for vector primitives (lines, circles) using shaders.
- Support for Tilemaps via optimized UV-panning shaders.
