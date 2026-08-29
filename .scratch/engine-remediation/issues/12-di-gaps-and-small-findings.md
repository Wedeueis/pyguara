# DI gaps and small findings sweep

Type: task
Status: open
Blocked by: —
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
