# Native Color and Rect value types

Type: grilling
Status: resolved
Blocked by: —
Audit ref: coupling

## Question

`common/types.py:218` and `:267` declare `class Color(pygame.Color)` and
`class Rect(pygame.Rect)`. Virtually every module imports one or both, so pygame is a hard
transitive dependency of the entire engine — the ModernGL path included. Ten non-backend
modules import pygame directly, among them `application.py`, `sandbox.py`,
`input/manager.py`, and `graphics/components/geometry.py`, which builds `pygame.Surface`
objects inside an ECS component.

This was a nice-to-have while pygame was the only real backend. The charting decision to
**fix and support ModernGL** promoted it to a blocker: two supported backends cannot both
receive a value type that is structurally one backend's own class.

## To resolve

- What are `Color` and `Rect` — dataclasses, `NamedTuple`, slotted classes? They are in hot
  paths (per-sprite, per-draw), so the allocation and attribute-access cost is a real input.
- Where does conversion to `pygame.Color` / `pygame.Rect` happen? At the backend boundary in
  every `draw_*` call, or cached on the texture/material?
- `pygame.Rect` brings `colliderect`, `contains`, `clip` and friends, and the UI layout engine
  leans on them. Which of that surface is actually used, and does it get reimplemented or
  dropped? (Worth grepping before deciding.)
- `pygame.Color` supports named colours, HSV, and int/tuple coercion. Same question.
- This is a breaking change across five shipped alpha releases. Is there a deprecation path,
  or does 0.5 simply break it?
- Does `graphics/components/geometry.py` — an ECS component constructing pygame Surfaces —
  get fixed here or ticketed separately?

## Note

This ticket is upstream of most of the fog. RenderSystem wiring and the ModernGL shape shader
both need to know what crosses the backend boundary before they can be specified.

## Why this is unblocked

The audit is sufficient input for the discussion. Implementing the answer wants a booting
engine (Repair the composition root, Bootstrap smoke test), but deciding it does not — so this
sits on the frontier and can run in parallel with the critical fixes.

## Answer

Grilled live with the dev, one sub-question at a time. Decisions:

1. **Structural kind: slotted dataclass.** `@dataclass(slots=True)` for both `Color` and
   `Rect` — mutable (in-place `rect.x = 5` style assignment stays legal), no `__dict__`
   overhead, and consistent with the map's already-planned Component contract push toward
   `slots=True` across the codebase.

2. **Conversion point: explicit helper inside `PygameBackend`.** Small private functions
   (e.g. `_pg_rect()`, `_pg_color()`) called at the top of every `draw_*`/`clear`/
   `set_viewport` method in `pygame_renderer.py`. Only the pygame backend ever constructs a
   `pygame.Rect`/`pygame.Color`; ModernGL never imports pygame types for this purpose.
   Rejected implicit duck-typing (relying on pygame-ce's undocumented `Rect()`/`Color()`
   coercion rules) as too fragile across pygame-ce versions.

3. **Rect surface: reimplement common AABB ops, not just what's grep-confirmed.** Beyond
   `top`/`left`/`right`/`bottom`/`centerx`/`centery`/`contains_point` (all already used),
   also add `colliderect`, `contains`, `inflate` — standard rectangle operations a public 2D
   engine's `Rect` should offer even though nothing in-repo calls them yet.

4. **Color surface: also add HSV conversion + a small named-color table.** Beyond the
   engine-native `r`/`g`/`b`/`a` fields, `from_hex()`, `normalized`, `lerp()` (all already
   defined/used), add HSV round-tripping and common named constants (WHITE, BLACK, RED, etc.)
   for parity with the Rect surface decision, despite no in-repo caller today.

5. **Breaking change: clean break, no deprecation shim.** Pre-Alpha status (CLAUDE.md: "APIs
   are subject to change") makes a compatibility shim not worth the complexity of carrying two
   behaviors. Documented as a `BREAKING` entry in the 0.5.0 changelog.

6. **`graphics/components/geometry.py`: fixed now, narrowly.** `Box._generate_texture()`'s
   `surface.fill(self._color)` breaks the moment `Color` stops being a `pygame.Color`
   subclass, so its `Color` usage gets the same `_pg_color()` conversion treatment as part of
   this ticket. The deeper coupling — `geometry.py` hardcoding `PygameTexture` and building
   `pygame.Surface` objects directly, i.e. backend-agnostic procedural texture generation —
   stays out of scope here; it's still gated on RenderSystem wiring and the ModernGL shape
   shader (both already fog, both explicitly waiting on this ticket's answer).

Not implemented in this session — this ticket is a decision, not a `task`.
