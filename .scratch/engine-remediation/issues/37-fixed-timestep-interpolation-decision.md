# Decide how fixed-timestep render interpolation should work

Type: grilling
Status: open
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
