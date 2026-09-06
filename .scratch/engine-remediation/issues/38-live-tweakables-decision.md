# Decide how live-tweakable values should work in the sandbox inspector

Type: grilling
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: external code review, verified against the codebase 2026-09-05

## Question

An external code review recommended live-tuning support: instead of editing
`game_config.json`/code constants and restarting to test a jump arc, friction, gravity,
or UI padding value, tune it live in the running sandbox (`pyguara/tools/
inspector.py`) and export the tuned value back out afterward.

Nothing like this exists today — `ConfigManager`/`GameConfig` load once at bootstrap,
and dev tools (`tools/inspector.py`, `tools/performance.py`, etc.) are read-only
displays, not editors.

- What's the registration API shape: a `@tweakable` decorator on dataclass fields
  (`GameConfig`, `PlatformerController`, etc.), a manual `register_tweakable(obj,
  field_name, ...)` call, or automatic introspection of existing config dataclasses
  (walking `dataclasses.fields()` the way `persistence/serializer.py` and `ui/theme.py`
  already do for their own purposes)?
- Which value types get a live editor? Numeric sliders are the obvious case, but does
  this also cover `bool`, `Enum`, `Color`, `Vector2` — and if so, what does each control
  look like in the inspector panel?
- Is this restricted to values already routed through `ConfigManager`/dataclasses, or
  does it need a more general "registry of live-tunable references" independent of
  where the value actually lives (e.g. tuning a `PlatformerController` instance's
  `jump_force` directly on a live entity, not just its config source)?
- Where does "export tuned values" write to — back into `game_config.json`, into a
  prefab file (`prefabs/loader.py`'s `PrefabCache`), both, or does the destination
  depend on what kind of value was tuned?

## Resolution

**Registration: automatic introspection, no decorator, no manual registry.** Three
existing places in this codebase already solve "walk a value's fields generically"
this way — `persistence/serializer.py` and `ui/theme.py` via `dataclasses.fields()`,
and `EntityInspector` itself via `component.__dict__.items()` — a `@tweakable`
decorator or `register_tweakable()` call would be the first registration-based API
where this problem has come up before. Consistency with existing precedent wins.

**Scope: both entity components and global config, as two separate tools** sharing
one underlying "render an editable control for this value" dispatch:
1. **Entity components** — extend `EntityInspector`'s existing per-field display
   loop (already walks every non-underscore field of every component, read-only
   today) to also emit an edit control for editable-typed fields, writing straight
   back via `setattr` onto the live component. Same mechanism, made bidirectional.
2. **Global config** — a new `ConfigInspector` tool walking `GameConfig`'s dataclass
   tree, since there's no entity/selection concept for it (`physics.gravity_x`,
   audio volumes, etc. aren't attached to any entity — `EntityInspector` has no way
   to reach them).

They stay separate `Tool` subclasses because their navigation model differs (cycle
entities vs. walk a static config tree), even though they share the same per-type
edit-control dispatch.

**Value-type dispatch** (checked actual types, not assumed): `bool` → toggle;
`int`/`float` → increment/decrement by a fixed step (no per-field min/max exists
anywhere in these dataclasses today, so a bounded slider isn't buildable without
inventing range metadata — out of scope here, a stepper is the honest fit for what
the data actually supports); `Enum` → cycle next/prev; a nested dataclass (`Color`,
now a real `@dataclass(slots=True)` per ticket 31, or any `GameConfig` section) →
recurse through the same generic dispatch, one sub-row per field; `Vector2` →
special-cased, since it subclasses `pymunk.Vec2d` (a C-extension type, not a
dataclass) and `dataclasses.fields()` can't see its `x`/`y` — exposed as two numeric
stepper sub-rows. Everything else (`str`, collections, non-dataclass objects) stays
read-only, unchanged from `EntityInspector`'s current behavior.

**Export: config-only, via the already-existing `ConfigManager.save()`** (works
today via `self._config.to_dict()` → JSON, zero new machinery). Checked prefab
export as the alternative destination: `PrefabCache`/the prefab loader only has
`load()` — no `Prefab.export_from_entity()` or any serialization path from a live
entity back into a prefab file exists. Building that would be real, separate work,
not squeezed into this ticket's scope. Entity/component-level tuning (via
`EntityInspector`) gets live editing with **no export path** in this ticket — the
value is exercised and observed during the session, then copied into source/prefab
by hand afterward, same as any "tune live, note the number" workflow before proper
export exists.

Lands as [Execute the live-tweakable inspector
tools](issues/48-execute-live-tweakable-inspector.md).
