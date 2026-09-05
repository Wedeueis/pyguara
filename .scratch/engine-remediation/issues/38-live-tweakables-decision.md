# Decide how live-tweakable values should work in the sandbox inspector

Type: grilling
Status: open
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
