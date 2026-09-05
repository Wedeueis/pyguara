# ModernGL shape shader

Type: grilling
Status: resolved
Blocked by: —
Assignee: Wedeueis Braz
Audit ref: coherence

## Question

Graduated from fog: its stated blocker — *Native Color and Rect value types* (what a `Color`
and a `Rect` are on the GPU side) — is now resolved (`Color.normalized` already exposes
0.0-1.0 floats; `Rect` is a plain `x`/`y`/`width`/`height` dataclass).

`ModernGLRenderer.draw_rect`/`draw_circle`/`draw_line` (`graphics/backends/moderngl/renderer.py:368-393`)
are stub no-ops with `# TODO: Implement with dedicated shape shader` — the `PygameBackend`
equivalents (`pygame.draw.rect`/`circle`/`line`) work today, so primitive drawing is
GL-backend-incomplete, not merely coupling-broken.

## To resolve

- One shape shader for all three primitives (rect/circle/line as a unified quad+SDF
  fragment shader), or a separate shader per primitive type?
- Immediate-mode (one draw call per `draw_*` invocation, matching current stub call
  signatures) or batched (accumulate primitives per-frame like `RenderBatch` does for
  textures, submit once)? The audit's "batching and multi-camera support" TODO suggests
  batching is the eventual direction engine-wide.
- How does `width` (0 = filled) map to the shader — a fill/stroke fragment branch, or two
  separate shader programs?
- Do these become part of `RenderSystem`'s submission path (see *RenderSystem wiring*), or
  remain directly-called `IRenderer` methods independent of it?

## Why this is unblocked

The value-type question is resolved. Sequencing note: deciding this alongside or after
*RenderSystem wiring* may be worth doing together, since how primitives get submitted could
depend on that ticket's answer — but nothing here is blocked on it by scope, only by
sequencing convenience.

## Answer

Grilled live with the dev, one sub-question at a time. Usage check first: `draw_rect` on
`IRenderer` (not just `UIRenderer`) is called constantly across almost every demo
(`guara_falcao`, `true_coral`, `protocolo_bandeira`, `physics_integration`) as the primary
per-entity draw call — several demos render entities as colored rects, not textures — plus
every editor tool (`gizmos.py`, `inspector.py`, `debugger.py`, `performance.py`,
`event_monitor.py`, `shortcuts_panel.py`). This is a real rendering gap on ModernGL, not a
rare debug path. Decisions:

1. **Shader unification: one unified SDF shader.** A single fragment shader computes a signed
   distance function per shape type (box SDF for rect, circle SDF, capsule/segment SDF for
   line), selected by a per-instance shape-type value. Matches the existing single-program
   pattern already used for textured sprites (`sprite.vert`/`sprite.frag`); one program to
   compile/release.
2. **Batching: batched now, not deferred.** Given the usage data above, primitive draws get
   hardware-instanced the same way `render_batch()` already does for textures, rather than
   shipping immediate-mode now and revisiting later.
3. **Fill vs. stroke: one shader, branch on a per-instance `width`.** The fragment shader
   fills when `width == 0` (`distance < 0`) or draws a band when `width > 0`
   (`abs(distance) < width/2`) — mirrors the existing `has_transforms` fast-path branch in the
   texture `Batcher`. No second shader program.
4. **Submission path: backend-internal batching, `IRenderer` signatures unchanged.**
   `draw_rect`/`draw_circle`/`draw_line` keep their exact current signatures and stay
   directly-called from callers' perspective. `ModernGLRenderer` internally accumulates
   instance data per shape-type across calls issued between `begin_frame()`/`end_frame()` and
   flushes at `end_frame()`. `PygameBackend` is unaffected (keeps calling `pygame.draw.*`
   immediately). No changes to `RenderSystem`, `RenderQueue`, `Batcher`, or the `Renderable`
   protocol.
   **Trade-off accepted:** shapes and textures are not Z-interleaved — all shapes draw as one
   group relative to all textures within a frame, rather than sorted together by `z_index`.
   Judged acceptable because today's `draw_rect` usage is either debug/editor overlays (which
   render on top regardless) or whole-scene placeholder rects with no textures present in the
   same scene — cross-type interleaving isn't actually exercised by any current demo.

Lands as one execution ticket — see [Execute the ModernGL shape
shader](25-execute-moderngl-shape-shader.md).
