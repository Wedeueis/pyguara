# Execute the Checkbox/Label layout measure() hook

Type: task
Status: open
Blocked by: —
Audit ref: fog graduation, follows from Decide how Checkbox should compute its layout
size without mutating state in render(), ticket 36

## Question

Nothing to decide — execute the decision recorded in [Decide how Checkbox should
compute its layout size without mutating state in render()
](36-checkbox-layout-mutation-decision.md).

**`pyguara/ui/base.py`:**
- Add `def measure(self, renderer: UIRenderer) -> None: pass` to `UIElement`
  (default no-op — most components have fixed sizes and need no measurement step).

**`pyguara/ui/layout.py`:**
- `BoxContainer.layout()` gains a `renderer: UIRenderer` parameter:
  `def layout(self, renderer: UIRenderer) -> None`.
- Before the "1. Calculate total used space" loop, call `child.measure(renderer)` for
  each entry in `visible_children`.

**`pyguara/ui/components/checkbox.py`:**
- Add `measure(self, renderer: UIRenderer) -> None`, moving the
  `text_w, _ = renderer.get_text_size(self.label, 16)` /
  `self.rect.width = self.box_size + self.label_spacing + text_w` lines out of
  `render()` into it.
- `render()` calls `self.measure(renderer)` as its first line, keeping the rest of
  `render()`'s drawing logic unchanged (so a `Checkbox` added standalone, not inside a
  `BoxContainer`, still sizes itself correctly before drawing).

**`pyguara/ui/components/label.py`** and **`pyguara/ui/components/text.py`**
(both `Label` classes — see ticket 41 for their eventual disposition, not blocking
this ticket since both need the same mechanical fix regardless of which survives):
- Add `measure(self, renderer: UIRenderer) -> None`, moving the
  `w, h = renderer.get_text_size(...)` / `self.rect.width = w; self.rect.height = h`
  lines out of `render()` (guarded by `self._auto_size` for `text.py`'s version, which
  has that flag; unconditional for `label.py`'s, which doesn't).
- `render()` calls `self.measure(renderer)` as its first line.

**Every `container.layout()` call site** (5, across `games/guara_falcao/scenes.py`,
`games/true_coral/scenes.py`, `games/protocolo_bandeira/scenes.py` (x2),
`games/ui_scene_graph/scenes.py`):
- Resolve `ui_renderer = self.container.get(UIRenderer)` in the same `on_enter()`
  (or wherever the call site lives) and pass it: `container.layout(ui_renderer)`.

**`button.py`/`text_input.py`:** unaffected — they don't mutate `self.rect` from
`get_text_size()`, per the original ticket's own audit; no `measure()` needed.

## Done when

- `Checkbox`, both `Label` classes have a `measure()` method; none mutate
  `self.rect` inside `render()` anymore (assert by inspection/grep, not just tests).
- `BoxContainer.layout(renderer)` calls `measure()` on every visible child before its
  stacking math; a new regression test builds a `BoxContainer` with 2+ `Label`
  children of different text lengths, calls `layout(renderer)` once, and asserts
  sibling `rect.x`/`rect.y` positions account for the *real* measured widths/heights,
  not construction-time placeholders (this is the test that didn't exist before,
  proving the bug is actually fixed, not just moved).
- All 5 existing `container.layout()` call sites updated to pass a renderer; full
  suite green; all 4 games verified booting via `games/validate_demos.py` (their
  existing `Button`-only containers must still lay out identically — `Button` has no
  `measure()` override, so the no-op default must produce byte-identical positioning
  to today for the fixed-size case).
- `ruff check .` and `mypy pyguara` stay clean.
