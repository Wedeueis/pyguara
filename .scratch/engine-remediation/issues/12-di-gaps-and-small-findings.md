# DI gaps and small findings sweep

Type: task
Status: resolved
Blocked by: —
Assignee: Wedeueis Braz
Audit ref: DI + low-severity findings

## Question

Mostly execute. Two real DI gaps plus the audit's low-severity tail, batched because each is
minutes of work and none warrants its own ticket.

**DI — PEP 604 unions are not unwrapped.** `_extract_dependencies` unwraps
`typing.Optional[X]` by checking `get_origin(...) is Union`, but `X | None` has origin
`types.UnionType` on Python 3.12 and falls through unhandled. Confirmed:

```
get_origin(int | None)  -> <class 'types.UnionType'>
is typing.Union         -> False
```

Live in `physics_system.py:30` and `resources/manager.py:50`, currently masked only because
those parameters have defaults. A required `X | None` parameter would fail to resolve.

**DI — scoped services skip cycle detection.** The resolution stack is pushed for `SINGLETON`
and `TRANSIENT` but not `SCOPED`, so a circular scoped dependency yields `RecursionError`
rather than `CircularDependencyException`.

**Small findings.**

- `validate_demos.py:60` tests `"EventDispatcher" in container._services` — a string against a
  type-keyed dict, so always `False`. Dead branch.
- `pyproject.toml` declares `pillow` twice with conflicting floors: `>=12.1.0` in core deps,
  `>=11.3.0` in the `dev` extra.
- `bootstrap.py:118` rebuilds a `WindowConfig` from `config.display`, which already *is* a
  `WindowConfig`, dropping the user's `title` (hardcoded to "Pyguara Game"), `fps_target`,
  `ui_scale` and `default_color`.
- `physics.gravity_x` / `gravity_y` have no consumer — `PhysicsSystem` defaults to zero gravity
  and every game hardcodes its own. `display.ui_scale` has no consumer either. Wire or remove.
- `CLAUDE.md` points at `docs/dev/backlog/TODO.md`, which does not exist, and states that
  physics updates happen in `Application._update()` — physics is not driven from the
  application loop at all.
- `AudioSourceSystem` computes `_attenuation` and `_pan` then discards them; `IAudioSystem` has
  no channel volume/pan call (TODO at `audio_source_system.py:237`). Spatial audio is computed
  but inaudible. If this is more than a one-line addition, split it out rather than growing
  this ticket.

## Done when

Each item is fixed or explicitly deferred with a note. DI fixes carry regression tests.

## Answer

All items executed.

**DI — PEP 604 unions.** `_extract_dependencies` now checks `get_origin(param_type) is Union or
get_origin(param_type) is types.UnionType`, covering both `typing.Optional[X]`/`Union[X, None]`
and `X | None`. Regression test: `test_pep604_union_dependency_resolves` (a required `X | None`
param, no default, resolves to the registered `X`).

**DI — scoped cycle detection.** `_resolve_service`'s `SCOPED` branch now pushes/pops
`service_type` onto `_resolution_stack` around the call to `scope._get_scoped_service()`,
matching the `SINGLETON`/`TRANSIENT` branches — a scoped resolution chain that circles back on
itself now hits the existing stack check and raises `CircularDependencyException` instead of
recursing until `RecursionError`. Regression test:
`test_circular_dependency_detected_for_scoped_services`.

**`validate_demos.py:60`.** Was `"EventDispatcher" in container._services` (string against a
`Dict[Type, ServiceRegistration]`, always `False`). Fixed to `EventDispatcher in
container._services` (the actual class).

**`pyproject.toml` duplicate pillow.** Removed the `dev` extra's looser `pillow>=11.3.0`
floor — core already requires `>=12.1.0`, which a dev install gets regardless.

**`bootstrap.py:118` WindowConfig rebuild.** `disp_cfg` (`config_manager.config.display`) is
already a `WindowConfig`; the code was reconstructing a new one from a partial field subset,
hardcoding `title` and silently dropping the user's `fps_target`/`ui_scale`/`default_color`
(defied to WindowConfig's own defaults, since the rebuild it never passed them). Replaced with
`win_config = disp_cfg` — no reconstruction. Removed the now-unused `WindowConfig` import.

**`physics.gravity_x`/`gravity_y`: wired up**, per direction from the dev. `PhysicsSystem`
already took a `gravity: Vector2 | None` constructor param; the config fields just had no
consumer feeding it. `guara_falcao/scenes.py` and `physics_integration/scenes.py` now read
`ConfigManager.config.physics.gravity_x/gravity_y` and pass `Vector2(...)` into `PhysicsSystem`
explicitly, instead of a scene-local hardcoded literal. Each demo's own `bootstrap.py` sets its
gravity override on the loaded `PhysicsConfig` in-process (guara_falcao: 800, physics_integration:
900) rather than in the shared `config/game_config.json` file, since every demo's `ConfigManager`
loads that same shared path by default — writing a nonzero gravity into the file would leak a
platformer's gravity into every other demo sharing it. `games/XXX_scenes/` was deliberately left
untouched: it's already marked for deletion by [Delete confirmed dead
code](20-delete-confirmed-dead-code.md), so wiring gravity into code about to be removed would be
wasted work. Bonus find while touching `physics_integration/scenes.py`: its existing "configure
gravity" line (`physics_engine.gravity = Vector2(0, 900)`) was a dead no-op — `PymunkEngine` has
no `gravity` property, only an `initialize(gravity)` method that `PhysicsSystem.__init__` already
calls, so that assignment was just setting an unread instance attribute. Fixed by folding the
value into the `PhysicsSystem(gravity=...)` constructor call instead, the mechanism that actually
works.

**`display.ui_scale`: deleted**, per direction from the dev. Zero consumers anywhere in
graphics/ui code, and wiring UI scaling through the render pipeline for real is a standalone
feature, not a small-findings fix. Removed the field from `WindowConfig`; it wasn't present in
`config/game_config.json` either, so no serialization fallout.

**CLAUDE.md doc fixes.** "Physics updates happen in `Application._update()`" corrected to
`_fixed_update()` (the actual fixed-rate method; `_update()` is the separate variable-rate pass).
Removed the stale "Current Development Focus" section pointing at
`docs/dev/backlog/TODO.md` (doesn't exist) — its role is already filled by the Wayfinder Map
section further down, which stays live rather than rotting again.

**`AudioSourceSystem`'s discarded spatial attenuation/pan: implemented**, not deferred — turned
out to need less than the ticket's "split out if more than one line" threshold implied, since
every piece already existed: `PygameAudioSystem` already tracked `base_volume`/`bus` per channel
in `_playing_sounds` and had a private `_apply_pan()` helper. Added `set_channel_mix(channel,
attenuation, pan)` to `IAudioSystem` and implemented it in `PygameAudioSystem` (looks up the
tracked `PlayingSoundInfo`, recomputes effective volume through the bus hierarchy, applies pan).
`AudioSourceSystem._update_spatial_position()` — called every frame for a playing spatial
source — now calls it instead of leaving `_attenuation`/`_pan` computed and discarded. Regression
tests at both layers: `PygameAudioSystem.set_channel_mix` (volume/pan math, ignores a finished or
unknown channel) and `AudioSourceSystem` (spatial sources call it each frame with the real
channel id; non-spatial sources never call it).

Full suite green (1048 passed), `ruff check .` and `mypy pyguara` clean.
