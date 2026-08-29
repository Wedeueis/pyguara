# ModernGL shape shader

Type: grilling
Status: open
Blocked by: —
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
