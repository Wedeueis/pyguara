# Execute the ModernGL shape shader

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: coherence, follows from ModernGL shape shader, ticket 14

## Question

Nothing to decide — execute the decisions recorded in [ModernGL shape
shader](14-moderngl-shape-shader.md): a unified SDF fragment shader for rect/circle/line,
hardware-instanced and batched per shape-type, fill/stroke handled by a per-instance `width`
branch, with `IRenderer` signatures unchanged and batching kept backend-internal to
`ModernGLRenderer`.

**New shader files (`pyguara/graphics/backends/moderngl/shaders/`):**
- `shape.vert` / `shape.frag`: unified quad + SDF shader. Per-instance attributes: `in_pos`
  (2f), `in_size` (2f, rect half-extents / circle radius+pad / line half-length+half-width as
  appropriate), `in_rotation` (1f, for lines — angle of the segment), `in_color` (4f,
  normalized via `Color.normalized`), `in_width` (1f, 0 = filled), `in_shape_type` (1f or int,
  0=rect/1=circle/2=line). Fragment shader: compute the SDF for the given shape type in local
  quad space, then `if (u_width == 0.0) { alpha = step(sdf, 0.0); } else { alpha =
  step(abs(sdf), u_width * 0.5); }`, discard or blend accordingly.

**`ModernGLRenderer` (`graphics/backends/moderngl/renderer.py`):**
- Compile the shape shader program alongside the existing sprite program in `__init__`
  (`_create_shape_shader_program()`, same load pattern as `_create_shader_program()`).
- A per-shape-type instance buffer (three logical buckets: rect/circle/line), each grown the
  same way `_grow_instance_buffer()` already does for the sprite instance buffer.
- `draw_rect(rect, color, width=0)` / `draw_circle(center, radius, color, width=0)` /
  `draw_line(start, end, color, width=1)`: pack instance data into the matching bucket instead
  of drawing immediately. No GPU call here.
- `end_frame()`: for each non-empty bucket, upload its instance data and issue one instanced
  draw call against the shape shader (mirrors `render_batch()`'s instancing call), then clear
  the buckets for the next frame.
- `release()`: release the new shape program and instance buffers alongside the existing ones.

## Done when

- `draw_rect`/`draw_circle`/`draw_line` produce visible output on `ModernGLRenderer` (currently
  no-ops) — verified via at least one integration test rendering each primitive and asserting
  the framebuffer isn't blank where the shape should be (or an equivalent instance-buffer
  assertion if pixel readback isn't already wired into the test harness).
- A scene mixing `draw_rect` calls and textured sprites (e.g. one of the demos using placeholder
  rects) renders correctly on both backends — visually equivalent to the existing Pygame output
  for the same scene, modulo the accepted no-Z-interleaving trade-off.
- `PygameBackend`'s existing `draw_rect`/`draw_circle`/`draw_line` are untouched.
- `ruff check .` and `mypy pyguara` stay clean; full suite green.

## Resolution

Executed as specified, with implementation details the decision ticket left open filled
in below. Commit `e7ecefd`.

**Shader design.** `shape.vert`/`shape.frag` implement the unified quad+SDF approach
exactly as decided: one shared program, `in_shape_type` selects a box/circle/capsule SDF
branch, `in_width` (0 = filled) drives the same fill-vs-stroke alpha test from the
ticket's pseudocode (`step(d, 0.0)` vs `step(abs(d), width/2)`). One detail the decision
didn't spell out and this ticket had to resolve: a stroked shape's border extends both
inward and outward from the shape's true edge by `width/2`, so the instance quad must be
padded by `width/2` beyond the shape's true half-extent or the outer half of the border
gets clipped. Resolved by packing `in_size` as the *padded* half-extent (true size +
`width/2` when stroked) and having the fragment shader subtract `v_width/2` back out
before evaluating the SDF — for rects and circles this pad is exactly `width/2`; for
lines (always filled capsules, `in_width` fixed at `0.0`) the same slot instead carries
the capsule's rounded-end-cap padding (`half_length + half_width`), with the fragment
shader recovering the true half-length as `v_size.x - v_size.y`. Documented inline in both
shader files rather than left implicit.

**`ModernGLRenderer`.** Three independent buckets (`SHAPE_TYPE_RECT`/`_CIRCLE`/`_LINE`),
each with its own instance VBO, VAO, and pending-list, grown independently via
`_grow_shape_buffer()` (mirrors `_grow_instance_buffer()`). `draw_rect`/`draw_circle`/
`draw_line` keep their exact `IRenderer` signatures and only append packed instance rows;
`end_frame()` uploads and issues one instanced draw call per non-empty bucket, then clears
it. `_update_projection()` now writes `u_projection` to both the sprite and shape
programs. `release()` releases the shape program, the shape quad VBO, and all three
buckets' VBOs/VAOs. `PygameBackend` untouched (verified by
`test_pygame_backend_draw_rect_untouched`, which asserts its `draw_*` methods still call
`pygame.draw.*` via source inspection).

**Testing, per the ticket's own escape hatch.** Pixel readback isn't wired into this
backend's test harness (`ModernGLRenderer` is exercised only against a `MagicMock` GL
context, never a real framebuffer), so — as the ticket anticipated — five new
instance-buffer-assertion tests in `tests/integration/test_moderngl_backend.py` stand in
for it: draw_rect queues without a GPU call until `end_frame()` flushes it (and a second,
empty `end_frame()` issues nothing further); circle and line each flush through their own
VAO; a mixed draw_rect + `render_batch()` frame drives both the shape and sprite VAOs
without either clobbering the other's instance count; a bucket's buffer grows past its
initial capacity the same way the sprite buffer does; and `PygameBackend`'s draw methods
are confirmed untouched. One pre-existing test
(`test_renderer_initialization`) had its exact-call-count assertions updated to account
for the new shape program and three new VAOs — the renderer legitimately does more GPU
setup now.

**Fixture fix, necessary not incidental.** `mock_ctx`'s `buffer`/`program`/`vertex_array`/
`texture` all returned one shared `MagicMock` via `return_value`, so every VBO/VAO/program
the renderer creates was literally the same object — adequate when there was only one of
each, but this ticket's three independent shape buckets need to be told apart in tests.
Switched to `side_effect` returning a fresh `MagicMock` per call; every pre-existing
assertion in this file only checked call counts or `.called`, not object identity, so
nothing broke.

**Discovery, not fixed here:** [Native Color and Rect value
types](05-native-color-and-rect.md) (ticket 05) was never executed — `common/types.py`
still declares `class Color(pygame.Color)`/`class Rect(pygame.Rect)` today, despite the
map's Decisions-so-far describing the dataclass migration as if it had landed. Same
resolved-but-unexecuted pattern as tickets 04/06/07, except no execution ticket was ever
spawned for it in the first place. This ticket wasn't actually blocked by it — `Color.
normalized` and `Rect.x/y/width/height` already work today regardless of the pygame-
subclass question — so left untouched here rather than widening scope; spun into [Execute
Native Color and Rect value types](31-execute-native-color-and-rect.md).

Full suite green (1088 passed, up from 1083 — the 5 new tests plus 1 pre-existing test's
assertions updated). `ruff check .`, `ruff format --check`, and `mypy pyguara` (216 files)
all clean.
