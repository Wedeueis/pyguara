# Decide how fixed-timestep render interpolation should work

Type: grilling
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: external code review, verified against the codebase 2026-09-05

## Question

An external code review recommended the Glenn Fiedler "Fix Your Timestep" pattern:
compute `alpha = accumulator / fixed_dt` and render entities lerped between their
previous and current fixed-step positions, avoiding visual jitter when physics runs at
a fixed 60 Hz but the display runs at 144 Hz or unlocked refresh rates.

This is already half-scaffolded, not a new idea to the codebase: `Application.run()`
(`pyguara/application/application.py`) already has the accumulator loop
(`self._accumulator`, the `while self._accumulator >= fixed_dt` step loop), and already
contains a commented-out line anticipating exactly this feature:
```python
# The alpha value represents how far we are between physics steps
# This can be used for interpolation in the future
# alpha = self._accumulator / fixed_dt
```
Nothing currently reads or stores a previous-frame position, so wiring this up is a
real, undecided design question, not a mechanical fill-in.

- Where does the previous-frame position live? Directly on `Transform` (add
  `previous_position`, updated once per fixed step) so every entity gets it for free,
  or a separate opt-in component (e.g. `InterpolatedTransform`) so entities that don't
  need smooth rendering (static geometry, UI) pay no extra field/update cost?
- Is interpolation opt-in per-entity, or an engine-wide default once wired (i.e. does
  `RenderSystem`/`Scene.render()`'s default submission path always use the interpolated
  position, or only for entities carrying whatever marker the previous question
  decides on)?
- Does `Camera2D` need interpolating too (camera smoothing/follow already exists per
  `graphics/components/camera.py`), or is this scoped to entity transforms only for now?
- How does the interpolated position reach `RenderSystem.submit()`/`flush()` without
  disturbing the authoritative `Transform.position` that `_fixed_update()` itself reads
  and writes? (e.g. a read-only computed property vs. writing a second field vs.
  `RenderSystem` accepting `alpha` and computing the lerp itself at submission time.)

## Resolution

Deferred, not decided now — this ticket's own fourth question presupposes a
mechanism that doesn't exist. `RenderSystem.submit(item: Renderable)` reads
`item.position`, and for `Sprite` (what `Scene.render()`'s default path submits per
*RenderSystem wiring*, ticket 13) that's `Sprite.position` — a field the component
owns *separately* from `Transform.position`. Grepped for whatever is supposed to
sync them (`sprite.position = transform.position` or equivalent) and found it
doesn't exist as real, executed code anywhere — the only match was a comment inside
a docstring example in `EntityManager.get_components()`. None of the four
auto-registered engine systems (Steering, AI, AudioSource, Animation) do it either;
the one demo that draws from `transform.position` directly (`ecs_mental_model`)
bypasses `RenderSystem`/`Sprite` entirely via hand-rolled rendering, predating the
migration.

So today, any `Transform`-driven entity (physics, steering, the platformer
controller) submitted through the default `Scene.render()` path would draw at
whatever `Sprite.position` last happened to be — which nothing currently updates.
The plain, non-interpolated sync doesn't exist yet, let alone an interpolated one.
Deciding *how to interpolate* on top of a delivery mechanism that isn't decided or
built risks redoing this ticket once that gap surfaces on its own.

Decided: this ticket blocks on a new prerequisite question — spun off as [Decide how
Transform position syncs to Sprite for rendering
](44-transform-sprite-sync-decision.md). This ticket itself returns to the map's
**Not yet specified** fog rather than closing with an answer, since interpolation's
actual shape (where `previous_position` lives, opt-in vs. engine-wide, whether
`Camera2D` needs it too) depends on whatever sync mechanism that prerequisite ticket
lands on — deciding it in the abstract first would likely need redoing.
