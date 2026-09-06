# Execute the live-tweakable inspector tools

Type: task
Status: open
Blocked by: —
Audit ref: fog graduation, follows from Decide how live-tweakable values should work
in the sandbox inspector, ticket 38

## Question

Nothing to decide — execute the decision recorded in [Decide how live-tweakable
values should work in the sandbox inspector](38-live-tweakables-decision.md).

**New shared dispatch** (e.g. `pyguara/tools/tweakable.py`): a function
`render_editable_field(renderer, position, label, value, on_change) -> Any` (or
similar) that, given a field's current value, draws the appropriate control and
returns the new value if changed this frame, else the same value:
- `bool` → toggle (click flips it).
- `int`/`float` → stepper with +/- controls, fixed increment (`1` for `int`,
  `0.1` × current magnitude or a fixed `0.1`/`1.0` for `float` — pick one sane
  default, no per-field range metadata exists to size it against).
- `Enum` → cycle next/prev through `type(value).__members__`.
- `Vector2` → two stepper sub-rows for `.x`/`.y`, reusing the numeric stepper.
- A dataclass instance (`Color`, any `GameConfig` section) → recurse via
  `dataclasses.fields()`, one sub-row per field, indenting nested rows.
- Anything else → read-only display (today's existing behavior), unchanged.

**`pyguara/tools/inspector.py`** (`EntityInspector._render_entity_details()`):
- Replace the current read-only `for attr, value in component.__dict__.items()`
  loop's display-only branch with a call into the shared dispatch; on a returned
  changed value, `setattr(component, attr, new_value)` on the live component.

**New `pyguara/tools/config_inspector.py`** (`ConfigInspector(Tool)`):
- Walks `container.get(ConfigManager).config` (`GameConfig`) via
  `dataclasses.fields()`, recursively, using the same shared dispatch.
- A "Save" action (bound key or on-screen button) calls
  `config_manager.save()`.
- Register in `pyguara/application/sandbox.py` alongside the other tools, bound to
  an unused shortcut (F6).

## Done when

- `EntityInspector` shows editable controls for `bool`/`int`/`float`/`Enum`/
  `Vector2`/nested-dataclass fields on any selected entity's components, and
  editing one visibly changes the live component's value (verified by a regression
  test that edits a field via the dispatch and reads it back off the component).
- `ConfigInspector` (new tool, F6) displays and edits `GameConfig`'s full tree
  (`display`/`audio`/`input`/`physics`/`debug`), and its Save action round-trips
  through `ConfigManager.save()`/`load()` correctly (a regression test: tune a
  value, save, reload from disk, confirm the tuned value persisted).
- Neither tool crashes on a field type the dispatch doesn't recognize (falls back
  to read-only display, per the decision).
- `ruff check .` and `mypy pyguara` stay clean; full suite green; both tools
  verified interactively via `games/validate_demos.py`'s sandbox mode or equivalent
  (not just unit-tested), per this map's UI-change precedent.
