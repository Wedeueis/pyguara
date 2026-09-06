# Execute the Checkbox/Label layout measure() hook

Type: task
Status: resolved
Assignee: Wedeueis Braz
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

## Resolution

Executed as specified, no deviations.

`UIElement.measure(renderer)` added as a no-op default. `BoxContainer.layout()`
gained a required `renderer: UIRenderer` parameter and now calls `child.measure
(renderer)` on every visible child before the stacking-math loop. `Checkbox`,
`label.py`'s `Label`, and `text.py`'s `Label` each gained a `measure()` override
moving their exact prior `render()`-time sizing logic out of `render()`; `render()`
in all three now calls `self.measure(renderer)` as its first line, preserving
standalone (non-contained) widget behavior exactly.

All 5 `container.layout()` call sites updated to `container.layout(self.container
.get(UIRenderer))` (matching this codebase's existing `# type: ignore[type-abstract]`
convention for resolving a Protocol via DI, per `application.py`'s own pattern).
`tests/test_ui_layout.py`'s two existing tests updated to pass a
`MagicMock(spec=UIRenderer)`.

New regression test (`test_box_layout_measures_children_before_stacking`) is the
first to actually prove the bug is fixed, not just moved: two `Label` children of
different text lengths, laid out with a renderer whose `get_text_size` returns
distinct sizes per string, asserts sibling `rect.y` reflects the real measured
height rather than the construction-time `(0, 0)` placeholder.

One gap found and closed rather than left implicit: `games/ui_scene_graph`'s
`MenuScene` is the one `container.layout()` call site not covered by
`games/validate_demos.py` (that script only validates 4 of the games). No existing
test or harness covers this demo at all. Verified manually by ticking it 10 frames
through a throwaway harness (not committed) rather than skipping verification for
the one site with no existing coverage.

Full suite green (1123 passed, up from 1122 for the new test), all 4
`validate_demos.py` games plus `ui_scene_graph` (verified separately) boot clean,
`ruff check .` and `mypy pyguara` (217 files) clean. Commit `61fdd8d`.
