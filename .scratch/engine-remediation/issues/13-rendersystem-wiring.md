# RenderSystem wiring

Type: grilling
Status: resolved
Blocked by: —
Assignee: Wedeueis Braz
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

## Answer

Grilled live with the dev, one sub-question at a time. Decisions:

1. **Submission path: `Scene.render()` stops being abstract.** The base class provides a
   default implementation that iterates entities carrying a `Renderable`-compliant component
   (`Sprite` already documents itself as implementing `Renderable` directly) and submits each
   to `self.render_system`, then flushes. A scene overrides `render()` only for extra manual
   draws (debug overlays, UI-adjacent world drawing), calling `super().render()` first. This
   replaces the ~9x duplicated "clear -> iterate entities -> draw_texture" loop every demo
   currently hand-rolls (e.g. `games/guara_falcao/scenes.py:436-446`).
2. **Camera ownership: the Scene owns it.** `Scene` gains `self.camera: Camera2D`, alongside
   `entity_manager`/`system_manager`. Matches the existing informal pattern (every demo
   already holds a `self._camera: Optional[Camera2D]` field) and preserves "no shared world"
   — a pushed scene's camera is independent of the one beneath it.
3. **RenderSystem scope: per-scene instance.** Constructed in `resolve_dependencies()`, same
   pattern as the four engine systems from *Scene-owned world and SystemManager*. The backend
   (`IRenderer`) itself stays a DI singleton; only the `RenderSystem` wrapper (queue + batcher
   + camera/viewport state) is per-scene, so a paused scene's in-flight `RenderQueue` state
   can't bleed into the scene pushed over it.
4. **Backend parity: already true by construction, nothing to decide.** `Batcher.
   create_batches()` (`graphics/pipeline/batch.py`) groups by `(texture, material)` and does
   the world->screen transform in backend-agnostic code; each backend's only seam is how
   `IRenderer.render_batch()` executes the batch (Pygame blits vs. ModernGL hardware
   instancing). Submission and batching are identical for both backends today.

**Coupling discovered mid-grill:** this ticket's premise — RenderSystem constructed "like the
other four engine systems" — assumed [Scene-owned world and SystemManager](04-scene-owned-world-and-systems.md)'s
decision was already executed. It wasn't: no execution ticket was ever spawned for it (only
its demo-migration item made it into the *Demo migration* fog patch); `SystemManager` is
still a DI singleton built once in `application/bootstrap.py:223-224`, and
`Scene.resolve_dependencies()` doesn't auto-register anything. Since both land in the same
method as the same per-scene-construction pattern, they execute together — see [Execute
Scene-owned world, SystemManager, and RenderSystem
wiring](24-execute-scene-owned-systems-and-rendersystem.md).
