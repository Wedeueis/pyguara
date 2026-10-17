# ADR 0004: The native boundary — what earns a Rust implementation, and how the engine picks one

Status: **Accepted**. Supersedes RFC-0003's module-by-module sequencing
(`project/backlog/active/rust_core.md`) and extends ADR 0003, which
measured the first milestone without generalising from it.

## Context

RFC-0003 proposed moving parts of the engine into a Rust extension and
organised the work **by module**: a maths milestone, a render-batcher
milestone, a pools milestone, a pathfinding-and-procgen milestone. ADR 0003
gated that behind a spike, corrected its figures, and recommended a
narrower order.

Two increments have since landed and three more have been measured. What
they show is that "which module" is the wrong question. Every one of these
milestones was decided by something the RFC does not mention: **where the
boundary between Python and Rust can be drawn, and how much data has to
cross it per tick.**

Three times now, the same module has been worth anywhere from 1.4x to 25x
depending only on where that line was put:

- **Particles.** `update` was 84% of the frame, so porting it looked
  obviously right. It caps at ~6x, because the remaining 16% becomes the
  whole cost. Moving the boundary out to include the render pack gave
  **18-20x**.
- **Sparks.** The same port, reasoned the same way, caps at **1.4-1.8x** --
  because a spark is a primitive, not a sprite, so 55-73% of its frame is
  `draw_circle`/`draw_line` call overhead rather than arithmetic. Moving
  the boundary out needed a type that did not exist (`ShapeBatch`), and
  then gave **16-25x**.
- **`dijkstra_map`.** A native port of the function as written would be
  *slower* than Python, because it takes a `Graph` protocol and calls
  `get_neighbors` and `cost` per node. The native unit has to be the grid,
  not the graph.

So this ADR replaces "which modules do we port" with a test that can be
applied to a candidate before any Rust is written, and a decision about how
the engine chooses between the two implementations once both exist.

## Decision 1 — The ratio rule

A subsystem earns a native implementation on the strength of

    ceiling = T_py / (T_cross + T_pinned)

| term | what it is |
| --- | --- |
| `T_py` | what the candidate's per-tick work costs in Python today |
| `T_cross` | what getting data in and results out costs **per tick**, measured in Python, because that is where it is paid |
| `T_pinned` | Python work that cannot move at all: the ECS, the event dispatcher, resource handles, caller-supplied callbacks |

`tools/price_native_boundary.py` computes this for every candidate. As of
writing:

| Candidate | `T_py` | `T_cross` | `T_pinned` | ceiling | |
| --- | ---: | ---: | ---: | ---: | --- |
| flow field, 96x96 | 83.247 | 1.479 | — | **56.3x** | landed, 56.3x (priced 161x) |
| particles, 1000 | 1.942 | 0.104 | — | 18.7x | landed, 18.7x |
| sparks, 1000 streaks | 5.865 | 0.339 | — | 17.3x | landed, 17.3x |
| flocking, 1000 agents | 17.206 | 1.118 | — | **15.4x** | not built |
| sparks, 1000 dots | 4.077 | 0.321 | — | 12.7x | landed, 12.7x |
| projectiles, 1000 | 3.041 | 0.339 | 1.143 | **2.1x** | declined |

**The landed rows do not prove the formula**; for built work `T_cross` is
measured directly, so the ceiling and the achieved speedup are the same
number by construction. The formula was tested the only way it can be, in
advance: it predicted ~6x for porting particles' `update` alone and
1.4-1.8x for sparks' alone, which is why both milestones were scoped wider,
and it predicted 13-20x for a batched spark handoff against an achieved
16.6-24.4x. Both predictions preceded the Rust.

**And the flow field is where the word "ceiling" earned its keep.** It
priced at 161x, with `T_cross` as the 0.522 ms wall-mask upload against
84 ms of Python, and it achieved 56x. The formula was not wrong about the
boundary — almost nothing is paid there — it simply does not model the
native work behind it, and the native sweep costs 1.3 ms. So read a
number from this table as the answer to "is this far above 5x", which is
the decision it exists for, and not as a forecast. Three candidates
forecast closely and one overshot by 2.9x; the difference is whether the
native work is negligible beside the handoff, which is a property of the
candidate.

**The threshold is 5x**, and it is a judgement about maintenance rather
than about speed: a native implementation is a second implementation
*forever*, and the cost of keeping two in agreement does not scale down
with the size of the win. Below 5x, say no and record the number.

## Decision 2 — Port a boundary, not a function

A candidate is not "a function to rewrite in Rust". It is **a line to draw
around some work**, and the line should sit where the least data crosses
it. Choosing the line is the design work; the Rust is the easy part.

Corollaries, each of which has already bitten:

- **If the unit that makes the boundary cheap does not exist, creating it
  is part of the job.** `ShapeBatch` and `ShapeBatchRenderer` exist because
  sparks needed a renderer that could accept a thousand primitives in one
  call. Without them the milestone was 1.4x.
- **A generic interface at the boundary is a per-element Python callback.**
  `dijkstra_map(graph, goals)` is good Python design and the wrong native
  boundary: `Graph` is a protocol, so each node expansion would call back
  into the interpreter. The native unit is `(width, height, blocked,
  weights, goals)`.
- **Prefer a boundary that answers questions over one that returns state.**
  A native flow field that hands back `dict[Node, Node]` pays 1.4-4.9 ms
  per recompute materialising it. One that *keeps* the field and answers
  `vector_at` pays 0.6 us per query and nothing per recompute.

## Decision 3 — Opacity decides whether the line can move

A subsystem is **opaque** when nothing outside it reads an individual
element. Opacity is what let the particle and spark boundaries move
outward; its absence is what pins projectiles.

| | opaque? | why |
| --- | --- | --- |
| `ParticleSystem` | yes | nothing holds a `Particle`; the output is per-texture batches |
| `Sparks` | yes | nothing holds a `_Spark`; the output is per-kind batches |
| flow field | yes, **built** | `vector_at`/`cost_at` are the only readers, and they ask rather than fetch; the field never returns to Python |
| `FlockingSystem` | **no** | agents are ECS entities; `Transform` and `FlockingAgent` are read by rendering, the spatial index and AI |
| `ProjectileSystem` | **no** | `get_active()` is public, and `games/protocolo_bandeira` reads `.position`/`.velocity` off every projectile, every frame |

Non-opaque does not mean "no". It means the boundary is pinned at the
element level, and the ratio rule then decides on **density**: how much
native work there is per element against the handful of Python values that
must cross back for it.

- **Flocking passes anyway.** Roughly a hundred operations per agent per
  tick — a radius query plus three accumulators over its neighbours — for
  two `Vector2`s written back. The boundary is 6-7% of the tick.
- **Projectiles fail.** Six operations per projectile for the same two
  `Vector2`s. A native pool removes 2.37 ms of integration per 1000 and
  pays 0.35 ms back on the sync, with the 1.15 ms hit check pinned
  regardless. Net 2.0x.

That is the useful form of the rule: **native work per element must greatly
exceed the Python values that have to cross back for it.** Particles and
sparks win on opacity, flocking wins on density, projectiles win on
neither.

### The remedies, when opacity is the problem

In order of preference:

1. **Make the consumer batch-aware.** What `ShapeBatch` did for the
   renderer. Best outcome: the boundary moves and the Python side gets
   simpler too.
2. **Move the consumer inside the line.** The reason a native
   `SpatialHash` is the wrong shape and a native *hit broad-phase* is the
   right one: one returns `list[K]` of Python keys per query, the other
   returns the few pairs that actually collided.
3. **Accept the pinned boundary** if density still passes — flocking.
4. **Decline, and record the ratio** — projectiles.

## Decision 4 — One engine-wide switch, and it is observable

Today `pyguara/graphics/components/_native.py` resolves the store silently,
per instance, from whether a compiled library happens to be on disk. That
was defensible while the only subsystems involved were cosmetic. It stops
being defensible the moment a gameplay system is native, because **the same
game, same code, same seed, diverges between a machine that built the
extension and one that did not.**

The choice therefore moves out of the subsystems:

- **One resolution, once, at bootstrap**, from one configuration value with
  three states: `off` (never native), `auto` (native where available), and
  `required` (native, and fail loudly at startup if it is missing).
- **No subsystem decides for itself.** The per-instance `accelerate=`
  argument stays, because the parity tests need to construct both stores
  side by side, but its default becomes "whatever the engine resolved"
  rather than "whatever is on disk".
- **The resolved value is observable** — reportable by the engine and
  visible in Studio — because a silent choice that changes behaviour is the
  thing being fixed.
- **It is recorded wherever reproduction is promised.** A replay stores the
  store it was recorded under, and playback under a different one is
  refused rather than quietly divergent. `ReplayRecorder.FORMAT_VERSION`
  has to move for this, as it did for W11's `controller_id`.

**Implementation status: built.** `pyguara/native.py` resolves the store
once at bootstrap from `PerformanceConfig.native_acceleration`, reports
it through `describe()` in the boot log, and raises at startup under
`required` with no extension. `ReplayMetadata.native_store` records which
store produced a recording, and `Application.load_replay` refuses a
cross-store playback unless asked to allow it. A replay from before the
field reads as unknown rather than as `python`, because there is no way
to know what it ran under and refusing every existing recording would
guard against a divergence nobody can confirm happened.

### What the engine does and does not promise

- **Promised: each store is deterministic given the same iteration
  order.** The native solvers are sequential by default; any `rayon`
  parallelism is opt-in per call and documented as giving up this
  guarantee.

  That wording is a correction. This bullet used to read "same store,
  same seed, same inputs, same result", and **the engine does not keep
  that promise** — neither store does. `EntityManager.create_entity`
  assigns `uuid4` ids and `get_entities_with_cached` iterates a set of
  them, so the order a system visits its entities differs between
  processes. For most systems that is invisible. For a Gauss-Seidel one
  it is the simulation: `FlockingSystem` has agents steering by the
  already-moved positions of those ahead of them, so who goes first
  decides the outcome. Three runs of one seeded flock give three
  different states.

  Found while building the flocking parity suite, from a probe that
  compared two worlds built from the same seed and could not match them
  slot for slot. It is pre-existing, it predates every native store, and
  both stores inherit it identically — the native one is handed its
  agents in whatever order Python resolved them. Tracked as issue #324,
  where the fix is noted as a *behaviour* change rather than a bug fix,
  because the sweep order it would pin is currently arbitrary and every
  existing flock settles the way it does because of it.

  **The consequence for Decision 4's last bullet is worth stating
  plainly.** A replay records the store it was made under and refuses a
  cross-store playback, which is necessary and is not sufficient: a
  replay of anything containing a flock does not reproduce under the
  *same* store either. The guard is still right — it removes one of two
  causes, and the one a player could trip by installing a wheel — but
  "replays reproduce" is not something this engine can claim for
  flocking games until #324 is resolved.
- **Not promised: the two stores agree bit for bit.** They cannot, and the
  reason is worth recording because it is not a thing better engineering
  fixes. `SpatialHash` buckets keys in a Python `set`, and set iteration
  order for realistic integer keys depends on insertion order and the probe
  sequence:

  ```
  inserted [5, 1029, 77, 513, 9]  -> query [513, 1029, 5, 9, 77]
  inserted [1029, 5, 513, 77, 9]  -> query [513, 5, 1029, 9, 77]
  ```

  Neighbours therefore reach a force accumulation in an order no Rust can
  reproduce without reimplementing CPython's set probing. Floating-point
  addition is not associative, so the sums differ in their last bits, and a
  flock is chaotic enough to turn that into visible divergence over time.


  This is the whole reason Decision 4 exists. For particles it would be
  cosmetic; for a flock of enemies it is gameplay.

## Decision 5 — The parity obligation, in three tiers

The price of two implementations is that they must agree. What the first
two increments show is that agreement has to be checked at three different
levels, because each tier catches what the others cannot:

1. **State parity.** The same operations against both stores produce the
   same numbers, to a stated tolerance, with the tolerance's cause stated
   (f32 against f64, summation order). If a tolerance ever has to be
   loosened, that is a finding and not a maintenance chore.

   **The tolerance is a function of what the subsystem is for, and the
   default is zero.** A spark half a pixel to the left is a spark, so the
   pools compare with a tolerance and say why. A flow field steers
   enemies, so one cell whose descent neighbour differs is a pack that
   goes the other way round a wall — there is no tolerance that means
   anything, and the native field is therefore bit-exact and tested with
   `==` on every cell. Exactness was not free, and it is worth knowing
   what it cost, because the next candidate pays the same bill: f64
   throughout rather than f32, `GridGraph.get_neighbors`' iteration order
   replicated exactly because the descent pass's tie-break *is* that
   order, and the rounded `1.414` kept over `SQRT_2` because agreeing
   matters more than being accurate. What made it reachable at all is that
   a Dijkstra cost map is order-independent given non-negative weights —
   unlike a flock's force sums, which are not. So: ask whether exactness
   is reachable before settling for a tolerance, and state which it is.
2. **Consumer parity.** The same calls reach the renderer, the ECS and the
   dispatcher. This tier exists because the native spark path reaches the
   renderer through *different methods* than the Python one.
3. **Output parity.** The real downstream effect — actual pixels from a
   real GL context, for anything that draws. Both increments needed this,
   because **no demo and no visual snapshot draws a particle or a spark**:
   the 11 Syrupy snapshots pass whatever those code paths do.

Three rules on top, each earned the hard way this quarter:

- **Every parity test must be shown to fail.** Sabotage the native side
  deliberately and watch the right test go red. A reversed colour lerp
  passed its test for a week because the test sampled the midpoint of a
  symmetric fade.
- **Never use a `MagicMock` where the production path tests a protocol
  structurally.** A mock satisfies every `runtime_checkable` protocol, so a
  mocked renderer silently takes the batched route and the per-primitive
  assertions describe a path no longer taken.
- **Never use a `MagicMock` in a benchmark** for an object the hot path
  hashes or compares. It inflated one of these figures to a fictitious
  325x.

## Decision 6 — Algorithm before boundary

Measure whether the work is *necessary* before measuring whether it is
*fast*. A native port that preserves redundant work ships redundant work,
only faster.

The live example found while writing this: `games/vinagre_matilha`'s
`FlankerAssignmentSystem.update` calls `FlowFieldService.recompute()`
unconditionally, every fixed tick. On its 30x20 stage-1 grid that is
**5.0 ms, 30% of a 16.7 ms frame budget, 60 times a second**.

The goal is the jaguar's cell. `CELL_SIZE` is 32 px and the jaguar's
`max_speed` is 158 px/s, so at a dead sprint it enters a new cell every
0.2 s — once per **12 fixed ticks**. At least eleven of every twelve
recomputes therefore produce the field that was already there, and a
jaguar that is circling or winding up produces none at all.

Porting the solver would make that 30% into 0.2% and leave the engine
recomputing an unchanged field sixty times a second. Guarding the
recompute comes first. Both are worth doing; the order is not optional.

**Done, and it changed what the port is for.** `FlowFieldService` now
skips a recompute that would reproduce the field it holds, keyed on the
goals and a content fingerprint of the graph -- 3114x on the unchanged
path, and 30% of a frame down to 0.01%. What it does *not* touch is the
cost of a recompute that genuinely has to happen: still 5 ms at 30x20 and
**85 ms at 96x96**, which is five frames dropped the moment a goal moves.
So the port is still wanted, for **worst-case latency** rather than for
throughput. That is the whole value of taking the two questions in this
order: answering the algorithmic one first did not cancel the boundary
work, it corrected the reason for it.

**Both are now done, and each is still doing its own job.** The native
sweep brings 96x96 to 1.6 ms, so the five-frame hitch is a tenth of a
frame. The guard is not thereby redundant: 1.6 ms sixty times a second is
10% of every frame for a field that did not change, so the guard is still
what keeps a per-tick caller off the recompute path. Had the order been
reversed, the port would have shipped and the demo would still be
recomputing an unchanged field sixty times a second — at 1.6 ms instead of
5 ms, which is precisely the kind of win that stops anyone looking.

## Consequences — Track R, re-sequenced by measured ceiling

RFC-0003's order was maths, batcher, pools, pathfinding. The measured order
is almost its reverse:

1. **The flow field — BUILT.** Priced at 161x at 96x96,
   opaque, and already costing a shipped demo 30% of its frame. Preceded
   by the Python guard from Decision 6. This is what ADR 0003's
   recommendation 2 asked for and nobody had measured; measured, a 96x96
   Python recompute is **505% of a frame**, which made it less an
   optimisation than a feature that could not be used at interactive
   rates. It is now **1.6 ms, 46-53x**, and bit-exact with the Python
   sweep rather than merely close — the first native port where that was
   required rather than nice, because a field steers gameplay. The field
   stays native and only the query crosses, which is Decision 3's opacity
   paying for itself.

   **It also calibrated Decision 1, and not entirely flatteringly.** The
   161x was a *ceiling* and the achieved figure is 56x, because `T_cross`
   models the boundary and the native sweep costs 1.3 ms of its own. The
   decision the number was computed for — is this far above 5x — was
   right; a reader comparing prediction to outcome should take 161x as
   "well above the threshold" and not as a forecast. The pools' forecasts
   landed close because their native work was negligible beside their
   handoff, which is a property of those candidates rather than of the
   formula.

   **`AStarPathfinder` and the WFC generator are not ported**, and this
   item should not be read as covering them. Neither has a measurement,
   and A* is a per-query cost rather than a per-frame one, so it does not
   obviously have a ratio worth computing — which is the point: measure
   it before claiming it. The flow field is what the 161x was about.
2. **Flocking** — 14.5x at 1000 agents, which is 98% of a frame today.
   Gated on Decision 4's switch, because it is the first gameplay system
   to go native.
3. **`SpatialHash`, as native state for native consumers only** — never as
   a Python-facing index returning `list[K]`. Projectiles then become a
   consequence of it rather than a milestone of their own.
4. **Marco 2's buffer handoff** — still unprototyped, and now with a bar to
   beat: `ShapeBatch` gets 13-20x out of ordinary Python lists, so the
   zero-copy claim has to be worth more than that.
5. **Projectiles alone — declined** at 2.0x, with the ratio recorded here
   so the decision is re-checkable rather than re-arguable.
6. **Marco 1's maths half — still dropped**, for the reasons in ADR 0003:
   the hot `Vector2` traffic is all inside the systems above, and the code
   outside them does 1-8 vector operations a frame.

## Alternatives considered

**Port by module, as RFC-0003 proposed.** Rejected: it was wrong three
times out of three, in both directions. It would have shipped sparks at
1.4x and skipped the flow field, which is the largest win in the engine by
an order of magnitude.

**Keep the per-subsystem `accelerate=` default.** Rejected under Decision
4: it makes gameplay depend on build state. The argument for it is
consistency with the two landed pools, which is why those are being
retrofitted onto the switch rather than left as the exception.

**Require bit-exact cross-store parity.** Rejected as unachievable, not
merely expensive -- see Decision 4. Pursuing it would mean reimplementing
CPython's set probing in Rust, and the thing it would buy is better bought
by recording which store ran.

**Make everything native and drop the Python implementations.** Rejected:
it forfeits `pip install pyguara` working without a Rust toolchain, which
is the engine's main distribution advantage and the reason the extension
was made optional in the first place.
