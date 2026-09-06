# Execute the canonical Label merge

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: fog graduation, follows from Decide which Label class is canonical,
ticket 41

## Question

Nothing to decide — execute the decision recorded in [Decide which Label class is
canonical](41-canonical-label-class-decision.md).

- Delete `pyguara/ui/components/label.py`.
- Update imports in `games/guara_falcao/scenes.py`, `games/true_coral/scenes.py`,
  `games/protocolo_bandeira/scenes.py`, `games/ui_scene_graph/scenes.py`: change
  `from pyguara.ui.components.label import Label` to
  `from pyguara.ui.components.text import Label`.
- Confirm `pyguara/ui/__init__.py`, `pyguara/ui/components/__init__.py`,
  `pyguara/graphics/components/__init__.py` already export `text.py`'s `Label`
  (per ticket 41's investigation, they do — no change expected, verify only).
- Apply ticket 36's `measure()` hook decision to `text.py`'s `Label` (the survivor)
  rather than `label.py`'s, if [Execute the Checkbox/Label layout measure()
  hook](42-execute-checkbox-layout-measure-hook.md) hasn't landed yet when this
  executes — check ticket 42's status before starting to avoid duplicating or
  conflicting work on the same file.

## Done when

- `pyguara/ui/components/label.py` no longer exists.
- All 4 games import `Label` from `pyguara.ui.components.text`; `games/
  validate_demos.py` confirms all 4 boot clean with title/subtitle/HUD text
  rendering unchanged (visual spot-check, since no pixel-readback harness exists
  per this map's established precedent).
- No remaining reference to `pyguara.ui.components.label` anywhere in the repo
  (`grep -r "ui.components.label"` returns nothing).
- `ruff check .` and `mypy pyguara` stay clean; full suite green.

## Resolution

Executed as specified, no deviations. `pyguara/ui/components/label.py` deleted.
Import updated to `from pyguara.ui.components.text import Label` in all 5 remaining
call sites (the 4 games' `scenes.py` plus `tests/test_ui_components.py`, which this
ticket's own text didn't list but grep turned up as a 5th real caller). No behavior
change anywhere — `text.py`'s `Label` constructor signature is a strict superset,
confirmed by `test_label_rendering` (which calls `Label(text, position, font_size=,
color=)` positionally-then-kwargs) passing unchanged.

`ui_scene_graph`'s `MenuScene` re-verified via the same throwaway harness ticket 42
used (still the one call site `validate_demos.py` doesn't cover). Full suite green
(1123 passed, unchanged count — no new tests needed for a pure rename), all 4
`validate_demos.py` games plus `ui_scene_graph` boot clean, `ruff check .` and
`mypy pyguara` (216 files, down from 217) clean. Commit `bbb3081`.
