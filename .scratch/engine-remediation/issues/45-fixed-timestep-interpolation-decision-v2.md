# Decide how fixed-timestep render interpolation should work, now that Transform-Sprite sync exists

Type: grilling
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: fog graduation, follows from Decide how Transform position syncs to
Sprite for rendering, ticket 44; supersedes the original, deferred [Decide how
fixed-timestep render interpolation should work](37-fixed-timestep-interpolation-decision.md)

## Question

The original interpolation ticket deferred because it assumed a `Transform`→`Sprite`
delivery mechanism that didn't exist. Ticket 44 decided one: `Scene.render()`'s
default loop computes `transform.position + sprite.position` (an additive offset,
not an overwrite) at submission time, passed through `RenderSystem.submit()`'s new
optional `position` parameter, every rendered frame.

That combination formula is the hook: an interpolated position substitutes for
`transform.position` in it. The original ticket's questions still apply, now
answerable against a concrete integration point:

- Where does the previous-frame position live? Directly on `Transform` (a new
  `previous_position` field, updated once per fixed step, before physics/steering/
  the platformer controller overwrite `position` for the new step) so every
  `Transform`-owning entity gets it for free, or a separate opt-in component
  (`InterpolatedTransform`) so entities that don't need smooth rendering pay nothing?
- Given interpolation now plugs into `Scene.render()`'s per-entity loop (ticket 44),
  is it opt-in per-entity (checked via `has_component(InterpolatedTransform)` or
  similar) or an engine-wide default once wired (every entity with a `Transform`
  always renders interpolated)?
- Does `Camera2D` need interpolating too (camera smoothing/follow already exists per
  `graphics/components/camera.py`), or is this scoped to entity transforms only for
  now — and if scoped to entities only, does an interpolated camera following a
  non-interpolated (or differently-interpolated) target look visibly wrong?
- Where does `alpha = self._accumulator / fixed_dt` (already commented out in
  `Application.run()`) get computed and threaded to `Scene.render()`'s loop? It's
  computed once per rendered frame in `Application`, but `Scene.render()` is what
  needs it per-entity — does `Application`/`SceneManager` pass it down to
  `Scene.render(world_renderer, ui_renderer, alpha)` (a signature change to an
  already-decided lifecycle hook), or does `Scene` pull it from somewhere else
  (e.g. a value `Application` writes onto the container each frame)?
- `PhysicsSystem` writes `transform.position = rb._body_handle.position` after
  every physics step (`pyguara/physics/physics_system.py:118`) — this becomes the
  *new* `position` for that step. Whatever stores "previous" needs to snapshot the
  pre-step value *before* this line runs, once per fixed step, for every
  `Transform`-bearing entity, not just physics-driven ones (steering also writes
  `transform.position` directly). Is that snapshot taken centrally (e.g.
  `SceneManager.fixed_update()`, before `scene.system_manager.update()`/
  `scene.fixed_update()` run) or does each Transform-mutating system snapshot it
  itself right before mutating (duplicating the snapshot logic across
  Steering/Physics/Platformer)?

## Resolution

**Opt-in via a flag on `Transform` itself: `Transform.interpolate: bool = False`.**
Not a separate `InterpolatedTransform` marker component — `Transform` already has a
documented pattern of internal flags (`_is_dirty`); one more boolean fits its
existing shape rather than fragmenting one concept across two components. Opt-in
(not engine-wide) so static/non-moving entities pay no per-tick snapshot cost,
matching this engine's existing pattern of opt-in capability components
(`RigidBody`, `Collider`).

**Snapshot is centralized, once per fixed tick, at the very start of
`SceneManager.fixed_update()`'s per-scene loop** — before `scene.system_manager.
update(fixed_dt)` runs at all, iterate entities with `Transform.interpolate=True`
and set `previous_position = position`. Every current and future
`Transform`-mutating system (`SteeringSystem`, `PhysicsSystem`, `PlatformerSystem`,
anything added later) just needs to run *after* this point in the tick — none of
them need their own snapshot logic, and nothing new has to remember to call it.
Same reasoning that ruled out a per-system sync in ticket 44: correctness shouldn't
depend on every mutating system cooperating.

**`alpha` reaches the combination logic as an attribute on `Scene`, not a parameter
of `Scene.render()`.** `Scene.render(self, world_renderer, ui_renderer)`'s signature
is fixed by ticket 13, and all 9 demos already override it with that exact signature
(none call `super().render()` yet, per ticket 24). Adding `alpha` as a third
parameter would force a mechanical signature change across all 9 unrelated overrides
for a value only the base default combination path uses. Instead: `Application`
(which already owns `self._accumulator` and, once persisted as `self._fixed_dt`
alongside it, the fixed timestep) computes `alpha = self._accumulator /
self._fixed_dt` in `_render()` and passes it into `SceneManager.render(world_renderer,
ui_renderer, alpha)` — a signature change to `SceneManager.render()` is fine, since
it's engine-internal and has exactly one call site, unlike `Scene.render()` which
every demo overrides. `SceneManager.render()` writes `scene.render_alpha = alpha`
onto each active scene immediately before calling `scene.render(world_renderer,
ui_renderer)` (that call's own signature unchanged); the base `Scene.render()`'s
combination logic reads `self.render_alpha`.

**`Camera2D` is out of scope.** Checked its actual update path:
`CameraFollowSystem.update(dt)` runs from the scene's *variable-rate* `update()`,
not `fixed_update()` — camera smoothing already recomputes every rendered frame via
its own deadzone/max-speed lerp toward a target, a different mechanism solving a
different problem (the camera has no fixed-rate discretization artifact to correct
in the first place).

**Full mechanism:** `SceneManager.fixed_update()` snapshots `previous_position` for
`interpolate=True` entities before any system runs this tick. `Application._render()`
computes `alpha` and passes it to `SceneManager.render(..., alpha)`, which sets
`scene.render_alpha` before calling `scene.render()`. `Scene.render()`'s default
combination formula (from ticket 44)
becomes: for entities with `Transform.interpolate=True`,
`lerp(transform.previous_position, transform.position, self.render_alpha) +
sprite.position`; for everyone else, unchanged (`transform.position + sprite.position`,
or `sprite.position` alone with no `Transform`).

Lands as [Execute fixed-timestep render
interpolation](issues/47-execute-fixed-timestep-interpolation.md).
