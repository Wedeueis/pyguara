# Execute the live-tweakable inspector tools

Type: task
Status: resolved
Assignee: Wedeueis Braz
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

## Resolution

Executed as specified, with three genuine pre-existing bugs found and fixed along
the way -- all three blocked verifying this ticket's own feature, not incidental.

**New `pyguara/tools/tweakable.py`**, the shared dispatch: `collect_tweakable_leaves()`
walks an object's own fields (private-prefixed skipped) via `vars()`, falling back to
`dataclasses.fields()` when `vars()` raises `TypeError` (a `slots=True` dataclass like
`Color` has no `__dict__`) -- one function handles both a plain component and a
slotted value type. Per-type dispatch exactly as decided: `bool` toggle, `Enum` cycle
(`cycle_enum`), `int`/`float` stepper (`apply_click`, split at the row's horizontal
midpoint), `Vector2` -> two numeric sub-leaves, nested dataclass -> recurse, anything
else -> read-only. One detail the grilling session didn't surface: `Vector2.x`/`.y`
are read-only properties (inherited from `pymunk.Vec2d`) -- a `Vector2` field can only
be edited by replacing the whole object on its parent attribute
(`setattr(parent, name, Vector2(new_x, old.y))`), not by mutating in place. Handled
correctly, verified by `test_vector2_becomes_two_number_leaves` plus the click tests.

`EntityInspector`'s existing read-only field loop now calls into this dispatch,
click-editing writing straight back via `apply()` (which is `setattr` on the leaf's
parent). New `ConfigInspector` (F6) walks `ConfigManager.config` (`GameConfig`) the
same way; `S` saves via the already-existing `ConfigManager.save()`, per the decision.

**Three pre-existing bugs found and fixed, all directly blocking verification:**
1. `EntityInspector._render_entity_details()`'s `entity.tag` raised `AttributeError`
   for any entity without a `Tag` component (the common case) -- `Entity.__getattr__`
   only resolves a name if a matching component is actually attached; there was no
   guard. Fixed with `entity.has_component(Tag)`, reading `.name` (the previous code
   would have printed the whole `Tag` component repr even when one existed).
2. The same method's `entity.components.items()` -- `Entity` has no public
   `components` property, only a private `_components` dict. Fixed to
   `entity._components.items()` (privileged debug access, matching this file's
   existing precedent one line above for `_entity_manager._entities`).
3. `GameConfig.to_dict()` (`asdict(self)` alone) never converted `RenderingBackend`
   (a plain `Enum`, unlike the already-JSON-safe `IntEnum` `LogLevel`) to its string
   `.value` -- `json.dump()` raised mid-write inside `ConfigManager.save()`'s bare
   `except Exception: return False`, silently leaving a truncated file on disk.
   `from_dict()` already had the reverse conversion; `to_dict()` never had the
   forward one. This means `ConfigManager.save()` had never actually succeeded
   against the real default `GameConfig` before -- directly contradicting this
   ticket's own decision text ("export... via the already-existing
   `ConfigManager.save()`"), so fixing it was necessary, not optional. Also fixed
   `ConfigInspector.process_event()`'s Save handler (a bug in this ticket's own new
   code, caught by the same debugging session) to only show "Saved." when `save()`
   actually returns `True`, rather than unconditionally.

All three bugs 1-2 mean `EntityInspector` had never been exercised end-to-end against
a populated entity before this ticket's tests -- consistent with this whole
engine-remediation effort's root cause theme (passing tests that never touched the
real path).

New tests: `tests/test_tweakable.py` (14 tests, the dispatch module in isolation) and
`tests/test_inspector_tools.py` (4 tests, both tools through
`create_headless_application()`'s real composition root -- clicking a bool field
toggles the live component, clicking a number field steps it, the config round-trips
through save/reload). Also verified interactively: `SandboxApplication` with F2/F6
toggled on, ticked 10 frames, no crash.

Full suite green (1148 passed, up from 1130 for the 18 new tests), all 4
`validate_demos.py` games unaffected, `ruff check .` and `mypy pyguara` (218 files,
up from 216 for the two new modules) clean. Commit `d2887a0`.
