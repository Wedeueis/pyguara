# Decide how Checkbox should compute its layout size without mutating state in render()

Type: grilling
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: external code review, verified against the codebase 2026-09-05

## Question

An external code review flagged `Checkbox.render()` (`pyguara/ui/components/
checkbox.py:49`) for mutating `self.rect.width` (computed from `renderer.
get_text_size(self.label, 16)`) inside `render()` rather than a layout pass. Verified
true.

The codebase already has a real hook for exactly this: `UIElement.apply_layout()`
(`pyguara/ui/base.py:126`), which applies constraints and cascades to children.
`Checkbox` doesn't override or use it. But this isn't a one-line move: `apply_layout()`
takes no renderer parameter today, and measuring text width needs one
(`get_text_size()` is a `UIRenderer` method) — so fixing this requires deciding how a
renderer reaches the layout pass, not just relocating one line.

Also checked, since it affects how bad the practical symptom is: `BoxContainer.layout()`
(`pyguara/ui/layout.py`) is only called once per scene, at setup time (`games/*/
scenes.py` call sites), not every frame. So the live symptom today isn't per-frame
visual jitter — it's that sibling positioning in `BoxContainer.layout()` is computed
against `Checkbox`'s placeholder construction-time width (`Vector2(20, 20)`'s width =
20, the "Fixed box size"), and never gets corrected once `render()` later overwrites
`self.rect.width` with the real content width. If layout is ever re-triggered
dynamically in the future (resize, dynamic children), per-frame `render()` mutation
would then race with `layout()`'s reads, which is the jitter scenario the original
report described.

- How does a renderer reach `apply_layout()`? Options include: thread a `UIRenderer`
  parameter through `apply_layout()`/`BoxContainer.layout()` end to end; cache the last
  renderer a widget was rendered with and use that on the next layout pass; or measure
  text width some other way that doesn't need a live renderer (e.g. a font-metrics
  service independent of `UIRenderer`).
- Not specific to `Checkbox`: grepped every `get_text_size()` caller in `pyguara/ui/
  components/`. `label.py` and `text.py` have the exact same pattern (`self.rect.width
  = w; self.rect.height = h` inside `render()`), so whatever's decided applies to all
  three. `text_input.py` and `button.py` also call `get_text_size()`, but only to
  position text within an already-fixed rect (cursor placement, centering) — they
  don't mutate `self.rect`, so they're unaffected either way.
- Is this worth fixing now given `BoxContainer.layout()` is currently a one-shot,
  setup-time call (so the practical bug today is "wrong initial sibling layout," not
  live jitter), or does it wait for a broader UI layout pass (e.g. if a "re-layout on
  demand" feature is ever added, at which point the race becomes real)?

## Resolution

Decide now — cheap enough that deferring buys nothing. The ticket's own premise needed
correcting first: `UIElement.apply_layout()` (the "real hook" it names) and
`LayoutConstraints`/`.constraints` are **entirely dead code** — never invoked or
assigned anywhere in the repo outside `apply_layout()`'s own recursive call to itself.
The only live layout mechanism is `BoxContainer.layout()`, called once per scene
directly by game code in `on_enter()`, before any renderer is available (`UIRenderer`
only arrives later, per-frame, via `Scene.render(world_renderer, ui_renderer)`).

Also found: `Checkbox` is **entirely unused** — exported from three `__init__.py`
files, instantiated by no game, demo, or test anywhere. Every current
`container.layout()` call site (5 of them, across 4 games) only adds fixed-size
`Button`s, never `Label`/`Text`/`Checkbox` — so the reported sibling-corruption bug
has never actually fired in any live demo, for any of the three flagged components.
This didn't change the decision to fix it (still cheap, still correct for when
`Checkbox`/auto-sizing `Label`s in a container do get used), just the urgency.

**Design: a `measure()` hook, not a resurrected `apply_layout()`.** Add
`UIElement.measure(renderer: UIRenderer) -> None` (no-op default). `Checkbox` and both
`Label` classes (`label.py`, `text.py` — see the spun-off duplication ticket below)
override it with exactly their current render()-time sizing logic
(`get_text_size()` + `self.rect.width`/`height` assignment), moved out of `render()`.
`BoxContainer.layout()` gains a `renderer: UIRenderer` parameter and calls
`child.measure(renderer)` on each visible child *before* reading its rect for
stacking math. `render()` still calls `self.measure(renderer)` at its top, so a
widget added standalone (not inside a `BoxContainer`, e.g. `TitleScene`'s title/
subtitle `Label`s) still self-sizes correctly before drawing. The renderer reaches
`container.layout(renderer)` call sites trivially — `Scene.on_enter()` already
resolves `UIManager` via `self.container.get(...)`; resolving `UIRenderer` the same
way is a one-line addition, no new plumbing.

Rejected: caching the last renderer a widget was rendered with (doesn't fix the
*first* `layout()` pass, before anything has ever rendered once — shifts the bug
rather than fixing it) and an independent font-metrics service (new machinery solving
a problem a one-renderer engine doesn't have).

**Found but not fixed here, spun out:** `pyguara/ui/components/label.py` and
`pyguara/ui/components/text.py` both define an unrelated `Label` class. The package
`__init__.py`s (public API) export `text.py`'s version; every game imports
`label.py`'s directly, bypassing the package export — so "the public `Label`" and
"the `Label` every game actually uses" are two independently-diverging classes today
(`text.py`'s has `_auto_size`/`anchor` support `label.py`'s lacks). Not this ticket's
question — see [Decide which Label class is canonical
](41-canonical-label-class-decision.md).
