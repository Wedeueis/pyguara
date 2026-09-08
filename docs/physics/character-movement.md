# Character movement: the switch to CharacterMover, resolved

PyGuara used to move platformer characters as **dynamic rigid bodies with
assigned velocity**. That is no longer true: characters are now moved by
**`CharacterMover`**, a swept collide-and-slide mover, and carry no physics
body at all. This document records why the old approach was replaced, the
decision that unblocked the switch, and the shape the engine ended up with.

## Where we were

`PlatformerSystem` read input, worked out a desired velocity, and assigned it
to the body:

```python
rigidbody.handle.velocity = Vector2(new_velocity_x, new_velocity_y)
```

Chipmunk then stepped the world and resolved whatever overlaps resulted.
That was the source of a whole family of bugs, because a character pressed
into geometry is *inside* it until the solver pushes it back out.

Measured in `guara_falcao`, jumping while running:

| | |
| --- | --- |
| depth reached | 8.95px into the floor |
| recovery rate | ~0.04px per tick |
| time visibly sunk | over 3 seconds |

Substepping, a raised penetration-recovery rate, and merging tile colliders
all helped without fixing the cause; jumping while moving still penetrated.
Every bug in this family — sinking, seam catching, wall creep, tunnelling —
came from asking a rigid-body solver to move something that was not really a
rigid body.

## The decision that unblocked the switch

Before wiring the mover in, one question had to be answered: what should a
character still be able to do physically (be knocked back? push crates? ride
platforms?), because that decides how much of the dynamic-body world had to
be rebuilt rather than deleted. Checked against the actual code at the time:
**none of the three existed as working features** — `Hazard.knockback_force`
was declared and read by nothing, crates weren't implemented in
`guara_falcao` at all (GDD-only), and moving platforms had no system driving
them. The decision made: build full physical parity anyway — knockback,
platform riding, and crate pushing — using **Celeste's model** as the
reference (Maddy Thorson's "Celeste and TowerFall Physics"): integer-pixel
positions with a float remainder accumulator, and solids that explicitly
carry/push the actors touching them, rather than leaning on Chipmunk
friction or a continuous bisection sweep.

## What shipped

**`CharacterMover`** (`pyguara/physics/character_mover.py`) sweeps a
character one whole pixel at a time. A float `remainder` accumulates
sub-pixel motion every call (gravity at 900px/s² is rarely a whole number of
pixels per tick); only the whole-pixel part is ever stepped, and every pixel
stepped is tested, so tunnelling is impossible and there is nothing to
bisect for — the last free whole pixel *is* the resting position.
`CharacterMover.probe()` is the same overlap primitive used one pixel off in
a direction, without moving: Celeste's `OnGround()` is exactly
`CollideCheck(Position + Vector2.UnitY)`, not a raycast, and it's what ground
detection uses now.

**`CharacterBody`** (`pyguara/physics/components.py`) replaces `RigidBody`
for a character: velocity, ground state, and knockback state, with *no
shape registered with the physics engine at all*. That is what makes the
old ground-ray self-detection bug class structurally impossible rather than
guarded against — the character has nothing to detect.

**`SolidMover`/`SolidSystem`** (`pyguara/physics/solid_mover.py`,
`solid_system.py`) are the other half: how the *world* moves a character
that isn't driving. Built on Celeste's `Solid.MoveHExact`/`MoveVExact`
rather than a swept move — a rider or a pushed actor is placed directly at
the position a solid's motion dictates (the solid already decided exactly
where it's going), then checked for whether that position is clear of
everything *except* the solid that moved it. If not, it's squished:
flagged on `CharacterBody.squished` and reported via `OnActorSquished`,
since what a squish means (damage, death, nothing) is a game decision, not
a physics one. A `MovingSolid` is still an ordinary `RigidBody`/`Collider`
as far as Chipmunk is concerned, so genuinely dynamic bodies keep colliding
with it normally.

**Pushing** is `Pushable`, a marker on a `MovingSolid`: when
`CharacterMover`'s sweep is blocked by one, `PlatformerSystem` asks
`SolidMover.try_move()` to shove it by the distance the block left
untravelled, retrying the character's own move once if the shove succeeds.
`try_move()` excludes the pushing character from the reactive carry/push
pass that follows — without that, a pushed crate immediately shoves back at
whoever just pushed it, which is exactly the shape a first version of the
test for this caught.

**Knockback** is `apply_knockback()` (`pyguara/physics/platformer_system.py`):
consumed as velocity, not an impulse. It overrides `CharacterBody.velocity`
directly and suppresses input control for a short window, during which the
velocity decays back toward zero and gravity keeps acting underneath it —
an ordinary hit-stun. `games/guara_falcao`'s `HazardSystem` now calls it,
which is what finally gives `Hazard.knockback_force` something to do.

**System ordering** (`GameplayScene.fixed_update()` in `guara_falcao`)
became: whatever authors a solid's motion (a patrol script) → sync kinematic
transforms into the engine, so a query this same tick sees where a solid
already is → `SolidSystem` carries/pushes whatever a solid touched →
`PlatformerSystem` moves the character against that now-current geometry →
`PhysicsSystem` steps whatever is still a genuine Chipmunk dynamic body.
`PhysicsSystem.sync_kinematic_transforms()` was split out of `update()` to
make the middle of that sequence possible.

Two details worth keeping in mind, both handled:

- A box resting exactly flush counts as overlapping in Chipmunk's
  `shape_query` — a touching contact is an overlap. `SKIN` (0.05px) is the
  allowance applied to every query box so a resting contact doesn't poison
  the next step's query; it never changes where anything actually settles.
- Ground/wall detection, riding, and pushing all assert exact pixel
  positions in tests now, not `pytest.approx(..., abs=0.1)` — there is no
  bisection settling near the answer any more, so there's no reason to
  tolerate one.

## Related

- `pyguara/physics/character_mover.py` — the character's own movement
- `pyguara/physics/solid_mover.py`, `solid_system.py` — how the world moves a
  character
- `pyguara/physics/components.py` — `CharacterBody`, `MovingSolid`, `Pushable`
- `pyguara/physics/platformer_system.py` — wiring, gravity integration,
  `apply_knockback()`
- `pyguara/physics/tilemap.py` — collider merging, and why interior faces
  mattered even before the mover
- `pyguara/physics/debug_draw.py` — collider and probe overlay (F1 in
  `guara_falcao`)
- `tests/integration/test_character_mover.py` — the no-penetration property,
  exact-pixel resting positions
- `tests/integration/test_solid_mover.py` — riding, pushing, squish,
  pushable crates end to end
- `tests/integration/test_knockback.py` — override, decay, control handback
- `tests/integration/test_platformer_feel.py` — coyote time, jump reuse,
  one-way platforms
