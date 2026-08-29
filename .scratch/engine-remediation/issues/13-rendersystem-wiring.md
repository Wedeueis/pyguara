# RenderSystem wiring

Type: grilling
Status: open
Blocked by: —
Audit ref: coherence

## Question

Graduated from fog: both of this question's stated blockers — *Scene-owned world and
SystemManager* (which world does the system query?) and *Native Color and Rect value types*
(what crosses the backend boundary?) — are now resolved.

`RenderSystem` (`graphics/pipeline/render_system.py`) already exists — submission, sorting
via `RenderQueue`, batching via `Batcher`, dispatch to an `IRenderer` backend — but nothing
wires it in. `Scene.render()` (`scene/base.py:128`) is still an abstract method every scene
must implement by calling backend draw calls directly, and `Application._render_direct()` /
`_render_with_graph()` call `scene_manager.render(world_renderer, ui_renderer)` — there is no
`RenderSystem` in that path at all.

## To resolve

- How do scenes submit renderables? Does `Scene.render()` stop being abstract (default
  implementation submits registered renderables to `self.render_system`), or does a scene
  still author its own `render()` but call `self.render_system.submit(...)` for each item?
- Where does `Camera2D` (`graphics/components/camera.py`) attach — owned by the scene
  alongside `entity_manager`/`system_manager`, or owned by `RenderSystem` itself?
- Per *Scene-owned world and SystemManager*, does `RenderSystem` become a per-scene instance
  (constructed in `resolve_dependencies()` like the other four engine systems), or does
  `Application` own one `RenderSystem` per backend and scenes only submit into it?
- How does the submit path reach both backends identically — does `RenderSystem.submit()`
  end up calling the same `IRenderer.draw_*` methods regardless of backend, or does batching
  strategy differ (Pygame `blits`-based batching vs. ModernGL instancing)?

## Why this is unblocked

Both stated dependencies — the ECS ownership decision and the Color/Rect value-type decision
— are resolved. Implementing the answer still wants the composition root already fixed
(done) plus whatever the ModernGL shape shader ticket settles for primitive drawing, but
deciding this does not.
