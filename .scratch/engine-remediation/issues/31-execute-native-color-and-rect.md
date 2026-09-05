# Execute Native Color and Rect value types

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: coupling, follows from Native Color and Rect value types, ticket 05

## Question

Nothing to decide — execute the decisions recorded in [Native Color and Rect value
types](05-native-color-and-rect.md). Found while executing [Execute the ModernGL shape
shader](25-execute-moderngl-shape-shader.md): `common/types.py` still declares `class
Color(pygame.Color)` and `class Rect(pygame.Rect)` today — the decision was never
implemented, and (unlike tickets 04/06/07/10/11) no execution ticket was ever spawned for
it at charting time, so it sat unexecuted without the map noticing.

**`pyguara/common/types.py`:**
- `Color` becomes `@dataclass(slots=True)` with `r`/`g`/`b`/`a` fields (`a` defaulting to
  255), no longer a `pygame.Color` subclass. Keep `from_hex()`, `normalized`, `lerp()`.
  Add HSV round-tripping and a small named-color table (WHITE, BLACK, RED, etc.), per
  decision 4.
- `Rect` becomes `@dataclass(slots=True)` with `x`/`y`/`width`/`height` fields, no longer a
  `pygame.Rect` subclass. Keep `position`, `center_vec`, and whatever else
  `top`/`left`/`right`/`bottom`/`centerx`/`centery`/`contains_point` surface currently
  exists. Add `colliderect`, `contains`, `inflate`, per decision 3.
- Both stay mutable (in-place `rect.x = 5` assignment must keep working).

**`pyguara/graphics/backends/pygame/` (conversion boundary):**
- Add `_pg_rect(rect: Rect) -> pygame.Rect` / `_pg_color(color: Color) -> pygame.Color`
  helpers, called at the top of every `draw_*`/`clear`/`set_viewport` method across
  `pygame_renderer.py` and `pygame/ui_renderer.py` (and anywhere else in the pygame backend
  that currently relies on `Color`/`Rect` being usable as pygame types directly).
- `ModernGLRenderer`/`GLUIRenderer` never construct pygame types for this purpose — confirm
  this is already true post-[Execute the ModernGL shape
  shader](25-execute-moderngl-shape-shader.md) (it packs `color.normalized` and
  `rect.x/y/width/height` directly, no pygame dependency).

**`pyguara/graphics/components/geometry.py`:**
- `Box._generate_texture()`'s `surface.fill(self._color)` gets the same `_pg_color()`
  conversion treatment, per decision 6. The deeper `PygameTexture`/`pygame.Surface`
  coupling in this file stays out of scope (still gated on demo migration, per the map's
  fog).

**Every other caller:** grep for `pygame.Rect`/`pygame.Color`-specific method calls
(`colliderect`, `contains`, `clip`, HSV, named-color lookups) across the ten non-backend
modules the original ticket flagged as importing pygame directly (`application.py`,
`sandbox.py`, `input/manager.py`, `graphics/components/geometry.py`, and others) — confirm
each either doesn't need pygame at all once `Color`/`Rect` are native, or is out of scope
per an existing ticket (geometry.py's deeper coupling).

## Done when

- `Color` and `Rect` are `@dataclass(slots=True)`, no `pygame.Color`/`pygame.Rect` base.
- `PygameBackend` converts via `_pg_rect()`/`_pg_color()` at every draw-call boundary;
  `ModernGLRenderer` never imports pygame for this purpose.
- `Box._generate_texture()` works against the new `Color`.
- The UI layout engine and anything else exercising `colliderect`/`contains`/`inflate`
  still passes.
- `CHANGELOG` (or equivalent) gets a `BREAKING` entry per decision 5 — no deprecation shim.
- `ruff check .` and `mypy pyguara` stay clean; full suite green on both backends.

## Resolution

Executed as specified, with several discoveries the ticket's file list didn't anticipate.
Commit `15de452`.

**Landed as specified.** `Color`/`Rect` are `@dataclass(slots=True)`, no pygame base
class. `Color` keeps `from_hex()`/`normalized`/`lerp()` (all reimplemented natively,
no longer delegating to `pygame.Color`), adds `to_hsv()`/`from_hsv()` and named
constants (`WHITE`/`BLACK`/`RED`/`GREEN`/`BLUE`/`YELLOW`/`CYAN`/`MAGENTA`/`TRANSPARENT`).
`Rect` keeps `position`/`center_vec`/`contains_point` plus the
`top`/`left`/`right`/`bottom`/`centerx`/`centery` properties camera.py's deadzone logic
already depended on, adds `colliderect()`/`contains()`/`inflate()`. Both stay mutable.
`graphics/backends/pygame/conversions.py` (new, shared rather than duplicated per the
ticket's file-local `_pg_rect`/`_pg_color` naming, since two files needed it) holds
`to_pygame_color()`/`to_pygame_rect()`; `pygame_renderer.py`'s `clear`/`set_viewport`/
`draw_rect`/`draw_circle`/`draw_line` all convert through it.
`geometry.py`'s `Box._generate_texture()` fixed per decision 6, and `Circle.
_generate_texture()` alongside it -- same file, same `pygame.draw.circle(surface,
self._color, ...)` bug, not explicitly named by the ticket but the identical mechanical
fix. `CHANGELOG.md` gets a new `## [Unreleased]` section with the `BREAKING` entry (no
`0.5.0` heading yet, since that hasn't shipped -- Keep-a-Changelog's own convention).

**Found and fixed, not in the ticket's file list:**
- `pygame_window.py`'s `clear()` also passed a `Color` straight into
  `pygame.Surface.fill()` -- same bug class as `pygame_renderer.py`, same backend
  package, fixed with the same shared `to_pygame_color()`.
- `ModernGLRenderer.set_viewport()` (`graphics/backends/moderngl/renderer.py`) indexed
  `viewport[0..3]` -- a genuine `Rect`-indexing dependency the ticket's grep list didn't
  surface, since it predates the ModernGL shape shader work. Fixed by switching to
  `viewport.x/.y/.width/.height` rather than adding `__getitem__` to `Rect` (unlike
  `Color`, which two *other* real call sites -- `framebuffer.py`, `light_pass.py`,
  `light_system.py` -- do index, so `Color.__getitem__`/`__len__` were added to preserve
  those without touching three unrelated rendering files).
- `Viewport(Rect)` (`graphics/pipeline/viewport.py`) is the one real `Rect` subclass in
  the codebase; its `contains_mouse()` called `self.collidepoint(...)`, a pygame.Rect
  method with no native replacement. Switched to the already-decided `contains_point()`
  instead of adding a new `collidepoint` method nothing else needs. Its docstring's
  "inherits from Rect (and thus pygame.Rect)" claim was also corrected.
- `camera.py`'s `Camera2D.get_view_bounds()` passed floats to `Rect(...)` relying on
  pygame.Rect's silent truncation; mypy caught it once `Rect`'s fields were properly
  typed `int`. Fixed with explicit `int(...)` at the call site -- `Rect.__post_init__`
  already truncates at runtime (preserving the exact old behavior for every other
  caller that doesn't explicitly cast), this only satisfies the stricter static type.
- `PygameUIRenderer` (`pygame/ui_renderer.py`), named in the ticket's file list, turned
  out to need **no changes** -- it already converts `Color`/`Rect` to plain
  tuples/`pygame.Rect` via its own `_to_pygame_color()` and inline `pygame.Rect(...)`
  construction, never relying on the engine types being pygame subclasses. The ticket's
  file list was written before checking; left it alone rather than adding redundant
  conversions.

**Investigated and confirmed out of scope, not touched:** the ticket's "ten non-backend
modules import pygame directly" background (from the original audit) turned out to be
21 files today (drift, same pattern as ticket 23's site-count growth) -- but grepping
each non-backend one (`application.py`, `sandbox.py`, `input/manager.py`, four
`tools/*.py`, `games/validate_demos.py`) showed their pygame usage is entirely event
constants, `pygame.time.Clock`, and `pygame.event.pump` -- none of it Color/Rect-related.
Only `geometry.py` needed a Color-conversion fix; the rest of that background concern is
a broader "should game code import pygame directly" question this ticket's actual
decision (05's Answer) never addressed, so left untouched.

**Left alone, deliberately:** `ui/theme.py`'s `UITheme.clone()` still manually
copies `Color` fields with a comment claiming "pygame.Color cannot be deepcopied" --
no longer true (a slotted dataclass deepcopies fine), but the workaround still produces
correct results, and rewriting it wasn't asked for by this ticket. Left as a
now-slightly-stale comment rather than re-decided.

22 new regression tests: `tests/test_common_types.py` (no dedicated test file existed
for `common/types.py` before this ticket) covers construction, mutability, equality,
`from_hex`, HSV round-trip, named constants, indexing, and all three new `Rect` methods.
`tests/integration/test_graphics_backend.py` gained two pixel-level tests
(`test_draw_primitives_produce_correct_pixels`, `test_set_viewport_clips_to_the_engine_rect`)
proving the conversion helpers produce the exact colors/clipping requested against a
real (dummy-driver) pygame surface, not just "doesn't raise." Manually verified end to
end: real pygame draw calls produce correct pixels, and `games/validate_demos.py` boots
all four demos clean on the pygame backend.

Full suite green (1116 passed, up from 1094 -- the 22 new tests). `ruff check .`,
`ruff format --check` (on touched files only -- pre-existing drift in untouched
`games/*`/`tests/test_physics_materials.py`/`tests/test_render_optimization.py` left
alone, per this session's established practice), and `mypy pyguara` (217 files) all
clean.
