# Character movement: two approaches, and a pending switch

PyGuara currently moves platformer characters as **dynamic rigid bodies with
assigned velocity**. `pyguara/physics/character_mover.py` implements the
other approach, **swept collide-and-slide**, and is not yet wired in. This
document records why, what it would change, and what has to be rewritten if
we go through with it.

## Where we are

`PlatformerSystem` reads input, works out a desired velocity, and assigns it
to the body:

```python
rigidbody.handle.velocity = Vector2(new_velocity_x, new_velocity_y)
```

Chipmunk then steps the world and resolves whatever overlaps result. That is
the source of a family of bugs, because a character pressed into geometry is
*inside* it until the solver pushes it back out.

Measured in `guara_falcao`, jumping while running:

| | |
| --- | --- |
| depth reached | 8.95px into the floor |
| recovery rate | ~0.04px per tick |
| time visibly sunk | over 3 seconds |

Two mitigations are in place and both help without fixing the cause:

- `physics.substeps` (default 4) shortens the jump a body makes per solver
  step, so it penetrates less far and cannot pass through thin walls at
  ordinary speeds.
- `physics.penetration_recovery` (default 0.3) raises Chipmunk's overlap
  correction from its own 10% per tick, which loses to gravity.

A third fix was structural rather than a tuning knob: solid tiles are merged
into as few colliders as possible (`pyguara/physics/tilemap.py`), because a
floor of separate tiles has interior faces that a character's leading corner
catches on. That removed the walking case entirely. Jumping while moving
still penetrates.

## Where the mover would take us

`CharacterMover.move()` advances the character in steps of at most 4px,
testing each candidate position with `IPhysicsEngine.overlap_box`, and stops
it flush at the first blocked step. Axes resolve one at a time, which is
what makes it slide rather than stick.

The property that matters: **penetration cannot occur**, so there is nothing
to recover from. Walking 200 steps across a deliberately tiled floor stays
within 0.1px, and a 3000 px/s move is still stopped by a 4px wall.

Two details worth keeping in mind, both already handled:

- A box resting exactly flush counts as overlapping — a touching contact is
  an overlap. Without an allowance every candidate position looks blocked
  and the character freezes. `SKIN` (0.05px, what Unity calls skin width) is
  that allowance.
- Tests have to assert geometry rather than the boolean overlap query, since
  that query cannot tell "resting on" from "inside".

## What switching would cost

The character stops being a physics body, and everything that relied on it
being one has to be re-expressed:

- **Knockback and explosions** currently apply impulses to the body. They
  would become velocity the mover consumes.
- **Moving platforms** currently carry the character through friction, which
  measurably works (a platform moving 200px took its rider 187.6px). A
  kinematic character is not carried by friction; it has to sample the
  platform's motion and add it.
- **Pushing dynamic bodies** — crates, debris — stops happening for free.
  The mover does not push what it hits.
- **Slopes** are unhandled either way, but a mover makes them our problem
  explicitly rather than the solver's implicitly.
- **Ground detection** could stop being a raycast: the mover already knows
  whether downward motion was blocked, which is a better answer than a probe
  ray and cannot detect the character itself.

## Recommendation

Do it, but as its own change with its own verification, and keep the dynamic
path for non-character bodies. The mover is the reference approach for a
reason: every bug in this family — sinking, seam catching, wall creep,
tunnelling — comes from asking a rigid-body solver to move something that is
not really a rigid body.

Before starting, decide what a character should still be able to do
physically (be knocked back? push crates?), because that determines how much
has to be rebuilt rather than deleted.

## Related

- `pyguara/physics/character_mover.py` — the mover
- `pyguara/physics/tilemap.py` — collider merging, and why interior faces matter
- `pyguara/physics/debug_draw.py` — collider and probe-ray overlay (F1 in `guara_falcao`)
- `tests/integration/test_character_mover.py` — the no-penetration property
- `tests/integration/test_platformer_feel.py` — coyote time, jump reuse, one-way platforms
