# Implementation Specification: Advanced Graphics Pipeline (P1-011)

## 1. Context & Motivation
Following the implementation of the GPU-accelerated ModernGL backend (P1-010), PyGuara now has the raw performance capacity to support modern visual features. This proposal outlines the architectural upgrade from a **Forward Renderer** to a **Compositor Pipeline**. This transition enables feature-rich 2D rendering including dynamic lighting, materials (custom shaders), GPU-simulated particles, and post-processing effects, bringing the engine's visual capabilities in line with modern standards (e.g., Godot, Unity 2D).

## 2. Goals
- **Compositor Architecture:** Implement a multi-pass render pipeline (World -> Light -> Composite -> Post-Process).
- **Material System:** Replace simple Textures with Materials (Shader + Uniforms + Texture) for custom visual effects.
- **Dynamic 2D Lighting:** Implement performant 2D lighting using additive light maps and shadow casting.
- **GPU Particles:** Enable massive particle systems (10k+) using Transform Feedback / Compute shaders.
- **Post-Processing Stack:** Allow easy stacking of screen-space effects (Bloom, Vignette, Color Grading).
- **Graceful Degradation:** Ensure the engine remains functional on the legacy Pygame backend (visual features are simply ignored).

## 3. Architecture

### 3.1 New Core Concepts

#### Render Graph (The Pipeline)
The rendering process is no longer a single loop but a graph of **Render Passes**.
1.  **World Pass:** Renders sprites/geometry to a `WorldFBO`.
2.  **Light Pass:** Renders `LightSource` components to a `LightFBO` (black background, additive lights).
3.  **Composite Pass:** Multiplies `WorldFBO * LightFBO`.
4.  **Post-Process Pass:** Applies effects (Ping-Pong FBOs) to the composite result.
5.  **UI Pass:** Renders UI on top (unaffected by lighting).
6.  **Final Blit:** Draws final result to screen.

#### Material System
*   **`Shader`**: Wraps a compiled GL Program (Vert/Frag).
*   **`Material`**: Instance data. Holds reference to a `Shader`, a `Texture`, and a dict of `Uniforms`.
*   **Batching Impact:** `RenderBatch` logic must group by `Material` first, then `Texture`.

### 3.2 Proposed File Structure
```text
pyguara/graphics/
├── materials/
│   ├── shader.py          # Wrapper for GL Program
│   ├── material.py        # Shader + Uniforms + Texture
│   └── defaults.py        # Default Sprite/Text/UI shaders
├── lighting/
│   ├── components.py      # LightSource, ShadowCaster
│   └── light_map.py       # Manages the Light FBO
├── vfx/
│   ├── post_process.py    # Stack manager
│   └── effects/           # Individual effect implementations
│       ├── bloom.py
│       └── vignette.py
└── pipeline/
    ├── render_pass.py     # Base class for passes
    ├── passes/
    │   ├── world_pass.py
    │   ├── light_pass.py
    │   └── composite_pass.py
    └── graph.py           # Orchestrator
```

## 4. Implementation Plan

### Phase A: Pipeline Infrastructure
1.  **Refactor `ModernGLRenderer`**: Move the core render loop into a `RenderGraph` class.
2.  **FBO Management**: Implement a system to manage resizing/recreating Framebuffer Objects when the window resizes.
3.  **Render Pass Protocol**: Define `RenderPass.execute(ctx, scene, output_fbo)`.

### Phase B: Material System
1.  **Create `Material` Class**:
    ```python
    @dataclass
    class Material:
        shader: Shader
        texture: Texture
        uniforms: Dict[str, Any]
    ```
2.  **Update `RenderSystem`**: Sort render commands by Material ID to minimize shader switching.
3.  **Default Material**: Create a `StandardMaterial` that replicates the current sprite behavior.

### Phase C: 2D Lighting
1.  **`LightSource` Component**: `color`, `radius`, `intensity`, `falloff`.
2.  **Light Pass**:
    -   Clear `LightFBO` to ambient color.
    -   Draw "Light Sprites" (quads with radial gradient shader) using Additive Blending.
3.  **Composite Shader**: Write a shader that samples `u_texture` (World) and `u_lightmap` (Light) and multiplies them.

### Phase D: Post-Processing & VFX
1.  **`PostProcessManager`**: Maintains a list of active effects.
2.  **Ping-Pong Rendering**: Implement logic to swap between two temporary FBOs while applying effect chain.
3.  **Standard Effects**: Implement Bloom (threshold + blur) and Vignette as initial proofs of concept.

### Phase E: GPU Particles (Transform Feedback)
1.  **`GPUParticleEmitter`**: Component holding simulation parameters.
2.  **Simulation Shader**: Vertex shader that updates positions (`pos += vel * dt`) and outputs to buffer.
3.  **Rendering**: Draw points/sprites from the updated buffer.

## 5. Graceful Degradation Strategy
The Pygame backend will **not** implement these features. It will remain a "Safe Mode" renderer.
-   **Lighting**: Ignored. Scenes rendered fully lit.
-   **Materials**: Ignored. Uses standard blit.
-   **VFX**: Ignored.
-   **GPU Particles**: Fallback to CPU emitter (low count) or ignored.

## 6. Acceptance Criteria
- [ ] Render Pipeline successfully renders World -> Screen via FBO.
- [ ] Lighting Pass correctly darkens the scene and adds light sources.
- [ ] Can apply a custom shader (e.g., grayscale, wobble) to a specific sprite via Material.
- [ ] Post-processing stack works (e.g., toggle Bloom on/off).
- [ ] Pygame backend still runs the game (without crashing) when these components are present.
