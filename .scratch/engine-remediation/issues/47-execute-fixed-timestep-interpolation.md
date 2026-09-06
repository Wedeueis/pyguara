# Execute fixed-timestep render interpolation

Type: task
Status: open
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
