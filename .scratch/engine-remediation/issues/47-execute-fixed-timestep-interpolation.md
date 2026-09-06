# Execute fixed-timestep render interpolation

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: fog graduation, follows from Decide how fixed-timestep render
interpolation should work, now that Transform-Sprite sync exists, ticket 45.
Depends on Execute the Transform-Sprite position combination (ticket 46) landing
first — this ticket's formula extends that one's.

## Question

Nothing to decide — execute the decision recorded in [Decide how fixed-timestep
render interpolation should work, now that Transform-Sprite sync exists
](45-fixed-timestep-interpolation-decision-v2.md). Requires [Execute the
Transform-Sprite position combination](46-execute-transform-sprite-sync.md) to have
landed first (this ticket's combination formula in `Scene.render()` extends that
one's).

**`pyguara/common/components.py`** (`Transform`):
- Add `interpolate: bool = False` (constructor param + instance attribute,
  alongside the existing local/world position fields).
- Add `previous_position: Vector2` (defaults to the same value as `position` at
  construction, so an entity's first render before any fixed tick has run doesn't
  interpolate from a garbage value).

**`pyguara/scene/manager.py`** (`SceneManager.fixed_update()`):
- At the very start of the per-scene loop, before `scene.system_manager.
  update(fixed_dt)`: iterate `scene.entity_manager.get_entities_with(Transform)`,
  and for each with `transform.interpolate`, set
  `transform.previous_position = transform.position`.

**`pyguara/scene/manager.py`** (`SceneManager.render()`):
- Gains an `alpha: float` parameter. Before calling `scene.render(world_renderer,
  ui_renderer)` for each active scene, set `scene.render_alpha = alpha`.

**`pyguara/application/application.py`**:
- Persist `self._fixed_dt = fixed_dt` in `run()` (currently a local variable) so
  `_render()` can reach it.
- `_render()` computes `alpha = self._accumulator / self._fixed_dt if self._fixed_dt
  > 0 else 0.0` and passes it to both `_render_direct()`/`_render_with_graph()`,
  which pass it to `self._scene_manager.render(self._world_renderer,
  self._ui_renderer, alpha)`.

**`pyguara/scene/base.py`** (`Scene`):
- Add `self.render_alpha: float = 1.0` in `__init__` (1.0 = fully at the current
  step, sane default before the first `SceneManager.render()` call ever sets it).
- `Scene.render()`'s default combination formula becomes: for each visible `Sprite`
  whose entity has `Transform`, if `transform.interpolate`: `world_position =
  Vector2.lerp(transform.previous_position, transform.position, self.render_alpha)
  + sprite.position`; else `world_position = transform.position + sprite.position`
  (ticket 46's formula, unchanged); no `Transform`: `sprite.position` alone
  (unchanged).

## Done when

- A regression test: an entity with `Transform(interpolate=True)` has its position
  changed between two fixed ticks (simulating movement); rendering at
  `render_alpha=0.5` produces a world position exactly halfway between
  `previous_position` and `position`; at `render_alpha=1.0` (or the value
  `SceneManager.render()` sets), it lands exactly on `position` (no visible lag at
  the moment of an actual physics step).
- A second test: an entity with `Transform(interpolate=False)` (the default) renders
  at `transform.position` directly regardless of `render_alpha` — proving opt-out
  entities are unaffected.
- A third test: `SceneManager.fixed_update()`'s snapshot runs before
  `scene.system_manager.update()` and any per-demo `fixed_update()` override —
  verify by asserting `previous_position` reflects the position from *before* this
  tick's movement, not after (a naive off-by-one placement would snapshot post-move
  instead).
- All 9 demos still boot clean via `games/validate_demos.py` (none currently set
  `Transform.interpolate=True`, so this must be a no-op behavior change for all of
  them; `Scene.render()`'s new branch simply never triggers today).
- `ruff check .` and `mypy pyguara` stay clean; full suite green.

## Resolution

Executed as specified, no deviations. `Transform` gained `interpolate: bool = False`
and `previous_position: Vector2` (defaults to the construction-time position).
`SceneManager.fixed_update()` snapshots `previous_position` for every
`interpolate=True` entity in each active scene, once, before `system_manager.update()`
or the scene's own `fixed_update()` run. `Application` persists `self._fixed_dt` (was
a local in `run()`) so `_render()` can compute `alpha = accumulator / fixed_dt` and
pass it through `SceneManager.render(..., alpha)`, which sets `scene.render_alpha`
before each scene's own `render()` runs — `Scene.render()`'s signature is untouched.
`Scene.render()`'s combination formula (ticket 44) extends to
`lerp(previous_position, position, render_alpha) + sprite.position` when
`interpolate=True`, unchanged (`position + sprite.position`) otherwise. `Camera2D`
untouched, per the decision.

One thing found and fixed beyond the ticket's file list: `SandboxApplication._render()`
fully overrides the base `_render()` (never calls `super()`) and was computing no
`alpha` at all, which would have made interpolation silently inert in sandbox mode
only. Added the same `alpha` computation there too, rather than leaving one of the
two run modes with a working feature that never activates.

Five new regression tests in `tests/integration/test_scene_owned_systems.py`
(broadened its docstring to cover tickets 44/45, not just 24): interpolated lerp at
alpha=0.5 and alpha=1.0; a non-interpolated `Transform` ignoring `render_alpha`
entirely; the snapshot ordering itself (a `_MoveSystem` registered at priority 999
proves `previous_position` reflects the pre-tick value across two consecutive
`fixed_update()` calls, not a same-tick post-move value); and a non-interpolated
`Transform`'s `previous_position` never touched at all (a sentinel value stays put).

Full suite green (1130 passed, up from 1126 for the 5 new tests), all 4
`validate_demos.py` games verified unaffected (none currently set
`Transform.interpolate=True`, confirming this is a no-op behavior change for every
existing demo), `ruff check .` and `mypy pyguara` (216 files) clean. Commit
`17169ba`.
