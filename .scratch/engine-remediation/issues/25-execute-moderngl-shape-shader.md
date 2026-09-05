# Execute the ModernGL shape shader

Type: task
Status: open
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
