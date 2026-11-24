# ADR 0013: Hordes are a native swarm, not entities

**Status:** Accepted 2026-11-24. Increment 1 is built.
**Scope:** A new subsystem, `pyguara/ai/swarm.py` over `rust/src/swarm.rs`.
`pyguara/ecs/` is not touched.

## Context

Correição (`examples/correicao/`) raids a calango with up to 10,000 flocking
ants. These are its per-tick costs in play, after the raid has settled, from
`tools/horde_probe.py` with the native solver's call timed separately (WSL2,
CPython 3.12, release build). A tick must fit in 16.7 ms for 60 Hz.

| Ants | Tick | Flock: Python glue | Flock: Rust conversions | Flock: sweep | Animation | Sprite pass (per frame) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5,000 | 24.6 | 8.2 | 3.4 | 4.8 | 4.5 | 16.2 |
| 10,000 | 60.9 | 20.9 | 7.4 | 15.4 | 10.0 | 33.2 |

In play an ant has about 60 flockmates in range. The glue is the query,
reading 15 fields an ant and writing two back. The conversions turn Python
lists into Rust vectors and back. Both exist only because each ant is a
Python entity. The sweep is the steering itself. The bit-exact flocking
goldens fix its Gauss-Seidel order, so it can be neither reordered nor
parallelised.

### Rejected: columns inside `EntityManager`

ADR 0008's spike would store `Transform` and `FlockingAgent` in native columns,
opted into per scene, with the component object kept as a handle bound to a
row. It was drafted and rejected before any code:

- **It would change the core for one workload.** Every ECS feature (clone,
  deepcopy, persistence, Studio, replay, replication, query caching,
  disabled entities) would need to work in two storage modes.
- **It needs hidden binding.** A component that silently proxies a
  column, through a branch in every accessor or a class swap, breaks
  "components are data". The swap breaks `type(component)`, which the
  serializer records.
- **It gets halfway.** It removes the glue and conversions only. The
  estimate at 10,000 ants is still about 33 ms a tick, with the sweep,
  animation and sprite building untouched.

### How other engines do it

None of the engines below makes hordes fast by changing how ordinary game
objects are stored. Each adds a separate bulk path:

- **Unity:** DOTS entities beside GameObjects, with baking from one to
  the other.
- **Unreal:** Mass beside Actors. Simulation level of detail decides how
  often a far agent updates, and an agent can switch to a full Actor
  when the player gets close.
- **Godot:** for thousands of objects, its advice is to skip nodes and
  use the rendering and physics servers, or MultiMesh, directly.
- **Bevy** is the exception: its ECS is native throughout, which works
  only because its game code is Rust too.
- **Survivor-likes** cap neighbours and simplify enemies off screen.

PyGuara already follows this pattern: `Sparks`, `ParticleSystem` and
`FlowFieldService` own their state natively and give Python a small API
(ADR 0011).

## Decision

### 1. A `Swarm` owns its agents natively

A swarm is a pool of agents held in Rust as arrays. An agent is not an
entity: it has no components. Python never iterates agents one at a time.

- **Ids** are 64-bit, slot index and generation, as in ADR 0008's spike.
  A killed agent's id never resolves again, and a stale id raises.
- **Kinds** hold the tuning: speeds, force, radii, weights, the clip and
  the layer, registered once. Each agent carries only its own state:
  position, velocity, heading, kind, animation clock and seek target. The
  kind table is what `FlockingAgent` repeats on every entity.
- **Game data the swarm does not know** stays with the game, keyed by
  agent id or by the slot a bulk read returns.

### 2. Steering reads last tick's state

Each agent's force is computed from every agent's state at the start of the
tick (Jacobi), not from neighbours already moved this tick (Gauss-Seidel).

- The result does not depend on sweep order.
- The sweep can run across threads (`rayon`, a new dependency) and stay
  bit-exact for any thread count. Each agent sums its neighbours in one
  fixed order, cell by cell and then by slot.
- **The forces are `FlockingSystem`'s,** cohesion, alignment,
  separation and seek, in the same arithmetic. Only the order of
  updates differs.
- **The swarm has its own goldens** and a Python reference in
  `tests/reference/`.

`FlockingSystem`, `FlockingAgent` and their goldens are unchanged. They
stay the tool for a flock of entities, up to a couple of thousand, each
running its own logic.

### 3. A neighbour cap, opt-in per kind

`max_neighbours` limits each agent to its *k* nearest flockmates, with
ties broken by slot. The default is no cap. A crushed raid at 60
neighbours an ant is the case it exists for. Selecting the nearest *k*
costs a partial sort per agent. That cost is measured against the sweep
it saves.

### 4. Simulation level of detail, opt-in per swarm

The game sets a focus, usually the camera centre, and distance bands, each
with a steering period:

- Agents inside the nearest band steer every tick.
- Agents in the bands beyond steer every *n*-th tick, picked by
  `(slot + tick) % n`.
- Every agent still integrates every tick, so motion stays smooth, as
  `FlockingSystem(groups=...)` already does.

With no bands set, every agent steers every tick.

### 5. Animation from a clock

Each kind has one looping clip. An agent's frame is its clock times the
frame rate, wrapped to the clip's length, computed while drawing. No
per-agent work happens in Python, and no per-tick work happens unless
drawn. Frame events and state machines are not supported. An agent that
needs them is promoted (section 7).

### 6. Drawing

The swarm culls natively, and hands each kind's visible agents to the
renderer as `RenderBatch`es with rotations, the path `ParticleSystem`
uses. That path is the same on wgpu and pygame, so the pixel tests apply.
Its batches enter the render queue at the kind's layer, so ground below
and a player above sort as they do now.

### 7. Gameplay goes through batch calls

All of these are deterministic, and anything returning ids returns them
sorted by id:

- spawning a kind at a list of positions;
- killing ids;
- the ids within a radius;
- positions for ids, or for all agents as arrays;
- setting the seek target per kind or per id;
- the count.

The swarm also supports **promotion**:

- `promote(id, entity_manager)` turns an agent into an entity with
  `Transform`, `FlockingAgent` and `Sprite`, and removes the agent;
- `adopt(entity)` does the reverse.

That is how one ant gets individual logic: a boss, a carried one, a
selected one.

### 8. What the swarm does not do

- **Studio:** it shows a swarm as one object, not 10,000.
- **Saving:** a save stores the swarm as one serialised blob, added when
  a game needs it.
- **Networking:** replication is not covered (`net_horde` replicates its
  own way).
- **Replay:** rewinding restarts and re-simulates, which needs only
  determinism.

## Exit criteria

Fixed before any code. Measured on this machine (12 threads) with the
horde probe:

1. **Correição at 10,000 ants:** in play, with the cap and level of
   detail on, a tick takes 16.7 ms or less.
2. **No regression without them:** with the cap, level of detail and
   threads all off, the swarm's tick at 10,000 is no slower than today's
   native sweep alone, 15.4 ms. All Python glue and conversions are gone.
3. **Threads:** with threads on, cap and level of detail off, the steering
   is at least 3x faster than criterion 2's, and bit-identical to it.
4. **Drawing:** the CPU cost of drawing 10,000 ants (about 2,000 on
   screen) is 5 ms or less, against 33.2 ms for today's sprite pass.
5. **Animation:** 10,000 agents add 1 ms or less a frame, against 10.0 ms
   a tick today.
6. **Determinism:** the same seed gives bit-identical state across runs,
   thread counts and platforms. The swarm's goldens and the Python
   reference agree.
7. **Nothing else changes:** `pyguara/ecs/` is untouched, and the
   flocking goldens, visual snapshots and demo frames are unchanged.

## Increments

Each is one PR, measured where it claims a number:

1. **The swarm core:** kinds, ids, spawn and kill, single-threaded
   Jacobi steering and integration, and the radius query. Includes the
   Python reference and goldens. Measures criterion 2.
2. **The neighbour cap.**
3. **Level of detail.**
4. **Animation and drawing,** with pixel tests on both backends. Measures
   criteria 4 and 5.
5. **Threads.** Measures criterion 3.
6. **Correição moves to the swarm,** with the probe rerun into
   `docs/guides/performance.md`. Measures criterion 1.
7. **Promotion and adoption.**

If an increment misses its criterion, work stops and the numbers come back
here before anything more is built.

## Consequences

- **Two ways to have many things in the world.**
  `docs/guides/performance.md` and the AI docs must say plainly when to
  use each: entities for anything with its own logic, a swarm for
  thousands that share it.
- **A swarm of one kind costs no more than its arithmetic,** whether its
  agents are on screen or not.
- **A game that later wants per-agent components promotes those agents,**
  rather than the swarm growing a component model.
