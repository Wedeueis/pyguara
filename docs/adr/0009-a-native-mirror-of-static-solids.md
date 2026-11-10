# ADR 0009: A native mirror of static solids, and what running Reclaimer on the fork showed

**Status:** Accepted, in this fork.
**Date:** 2026-11-10

## Context

The fork exists to make the engine much faster without risking
`Wedeueis/pyguara`. The plan led with native, columnar component storage
(ADR 0008). The instruction that followed was narrower and more useful:
make the *current* Reclaimer run on the fork, unchanged, with no bugs, and
much faster.

So Reclaimer was profiled before anything else was built, and the profile
disagreed with the plan.

At 200 enemies, one player, one rendered frame cost 16.8 ms. Where it went,
from a `cProfile` run (shares, not timings -- the profiler inflates
everything):

| | Share of the frame |
| --- | ---: |
| `CharacterMover` asking the physics engine about walls | 31% |
| Enemy AI, mostly line-of-sight rays and `Vector2` arithmetic | 20% |
| Immediate-mode drawing from the game's view code | 27% |
| `Vector2` operators, spread across all of the above | about 18% |

A wall probe was the largest single cost in the game. `CharacterMover`
moves a box one whole pixel at a time and asks `overlap_box` once per
pixel per axis, and the pymunk backend answered each by constructing a
`pymunk.Body` and a `pymunk.Poly` in Python before Chipmunk was called.
The owner had already ruled, on 2026-11-09, that this waits for a native
sweep rather than a Python fix.

None of it was component storage. Columnar storage would not have moved
any row of that table.

## Decision 1 -- Mirror, and answer only when certain

`PymunkEngine` keeps a native copy (`rust/src/solids.rs`) of the boxes of
its static, unrotated, non-sensor box shapes, and answers three questions
from it: a box overlap, a whole swept move, and whether a ray misses.

The mirror does not reimplement Chipmunk. Every answer is one of three:

- **certainly clear**,
- **certainly this one box**, or
- **ask Chipmunk**.

A probe within a millionth of a pixel of a box's edge is the third. So is
a probe overlapping several boxes, because which one Chipmunk names first
depends on the insertion history of its spatial index. A ray is answered
only when it misses; a possible hit goes to Chipmunk, which owns the hit
point and the normal.

The consequence is the reason for the design: **the fast path cannot
disagree with the slow one. It can only decline.** There is no tolerance
in `tests/test_native_solids_parity.py`, and no float operation of
Chipmunk's that this code has to match.

Rejected: reimplementing Chipmunk's box and segment queries bit-exactly.
That is a parity obligation against a library this project does not own,
renewed on every pymunk upgrade.

## Decision 2 -- The mirror steps aside rather than approximating

It exists only while every solid in the space is something it holds
exactly. One dynamic or kinematic body, one circle, one rotated wall, one
body without an entity id, and `_static_solids()` returns None and every
query goes to Chipmunk as before.

That is precisely a world of level geometry, which is what a character
mover sweeps against and what Reclaimer's `Solids` is. A richer space
keeps its old behaviour and its old cost.

Geometry is read from each shape's cached bounding box, not recomputed
from the body. Chipmunk does not reindex a static body that is
repositioned, so its own queries keep answering from the old place; the
mirror shares that, because the alternative is to be right where the
reference is wrong.

## Decision 3 -- Identical includes the types

The Python loop does arithmetic on whatever it is given, so an integer
position stays an integer through it. The native sweep computes in floats
and converts back, because `70` and `70.0` compare equal and encode
differently on the wire. The parity suite compares types as well as
values.

## Decision 4 -- Fast paths for `Vector2`, held to the code they replace

`Vector2` subclasses `pymunk.Vec2d`. Each operator built a `Vec2d` --
which checks its operand with `isinstance(other, numbers.Real)`, an
abstract-base-class test -- and then a second `Vector2` from it.

For another `Vector2`, or a plain `float` or `int`, the operators now do
the same floating-point operations in the same order and construct once.
Anything else takes the old route unchanged. `Camera2D.world_to_screen`
got the same treatment, and `Entity.get_component` lost a `typing.cast`
call.

ADR 0003 declined a native `Vector2` and optimised its call sites one at
a time instead. This is neither: the class stays a `Vec2d`, and every
call site gets faster at once.

## Measured

WSL2, CPython 3.12, release build. Reclaimer at commit `88b2604`,
unchanged apart from pointing its dependency at this fork.

A host's tick with four players, over a simulated 100 ms link:

| Enemies | Original | Fork | |
| ---: | ---: | ---: | ---: |
| 24 | 2.81 ms | 0.93 ms | 3.0x |
| 100 | 7.34 ms | 2.32 ms | 3.2x |
| 200 | 13.97 ms | 4.28 ms | 3.3x |

One rendered frame, one player, enemies in sight:

| Enemies | Original, mean / p95 | Fork, mean / p95 | |
| ---: | ---: | ---: | ---: |
| 24 | 5.64 / 7.45 ms | 4.24 / 5.31 ms | 1.3x |
| 100 | 10.65 / 15.56 ms | 6.07 / 7.50 ms | 1.8x |
| 200 | 16.78 / 26.36 ms | 8.24 / 9.44 ms | 2.0x |

One swept move against five walls: 64 us to 4 us.

## How "no bugs" was checked

- **Reclaimer's own suite**: 630 passed against the fork.
- **The engine's suite**: 8,260 passed.
- **A seeded fight, hashed every tick for 900 ticks**, at 40 and at 150
  enemies: every position, every sub-pixel remainder and the game's own
  `Simulation.state_hash()`. Identical between the original engine code
  and the fork, and identical with the mirror switched on and off.
- **Sabotage.** Three deliberate breakages of `solids.rs` were built and
  run. The parity suite caught one of them. Rounding ties away from zero
  rather than to even, and ignoring a ray's radius, both left 146 tests
  green -- a random float almost never lands on a tie or within a pixel
  of a face. `TestWhatSabotageFound` now aims at both, and each breakage
  fails five or six tests.

Two regressions were introduced and caught by existing tests before
anything was committed. They are recorded because both are shapes worth
recognising:

- The body adapter was given a bound method of the engine to report a
  move. Studio deep-copies `RigidBody` handles to snapshot a scene, and
  the copy followed the method into the engine. It is now a shared flag.
- `getattr(engine, "sweep_box", None)` is satisfied by a `MagicMock`,
  which nine tests pass as an engine. The mover now accepts a tuple and
  nothing else.

## What is left, and why it is a different kind of work

After these changes the 200-enemy frame is 53% rendering and 47%
simulation, and what remains in each is per-entity Python:

- the game's view code issuing one `draw_rect` per enemy part,
- enemy brains and state machines,
- a guest interpolating every replicated field of every entity each
  frame: about 2.8 ms a frame at 200 enemies under the profiler, which
  inflates it, so read that as a ranking and not a cost.

None of that can be made faster from underneath without changing what the
calling code does. That is where ADR 0008's columnar world and a batched
drawing interface come in, and both mean changes to Reclaimer, not only
to the engine.

## Not verified

Everything here ran headless, on SDL's dummy video driver. A capture
proves the simulation and the render path; it does not prove a window on
a screen, and nobody has played the fork.
