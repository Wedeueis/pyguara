# Execute Native Color and Rect value types

Type: task
Status: open
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
