# Decide how Checkbox should compute its layout size without mutating state in render()

Type: grilling
Status: open
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
