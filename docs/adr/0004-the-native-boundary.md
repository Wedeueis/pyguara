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
| flocking, 1000 agents | 16.555 | 1.849 | — | **9.0x** | landed, 9.0x (priced 15.4x) |
| sparks, 1000 dots | 4.077 | 0.321 | — | 12.7x | landed, 12.7x |
| spatial index, 1000 keys | 7.453 | 0.439 | — | **17.0x** | landed, 17.0x |
| projectiles, 1000 | 3.041 | 0.339 | 1.143 | **2.1x** | declined |

The spatial index is the one row that is **not a subsystem**, and reading
it as one would be a mistake: its 17x is what the *index* costs, while
what its consumers feel is 1.3x to 4.3x. Decision 7 is about that gap and
about why a primitive is still admitted on its own figure.

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
the decision it exists for, and not as a forecast.

**Flocking then overshot for the opposite reason, which is the more
useful lesson.** It priced at 15.4x and achieved 9.0x, and here the
native work is *not* the explanation — the solve is 0.5 ms of a 1.85 ms
tick. The crossing itself was underestimated, by 65%, because
`T_cross` was measured as the Python loops that pack and unpack and a
real crossing is more than those loops: PyO3's own conversion of a
15,000-float list into a `Vec<f64>`, the result tuples it allocates
coming back, and the per-tick ECS prologue — resolving entities and
components — which is 0.31 ms and is paid whichever store runs. At 17 ms
that prologue was 2% and invisible; at 1.85 ms it is 17%.

So the two calibration rows fail in different directions and neither is
the formula being wrong. Price a candidate, check it clears 5x by a wide
margin, and expect the achieved figure to be *lower*: by the native work
when the handoff is trivial, and by the conversions and the shared
prologue when the handoff is not. Both corrections point the same way,
which at least makes the formula optimistic rather than unreliable.

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
| `FlockingSystem` | **no** | agents are ECS entities; `Transform` and `FlockingAgent` are read by rendering, the spatial index and AI — built anyway, at 9.0x against the field's 56.7x, which is what non-opacity costs |
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
  regardless. Net 2.0x. The hit check's *broad-phase* has since been
  unpinned by Decision 7's native index, and it moved the whole subsystem
  1.32x — so the decline now stands on a measurement rather than an
  estimate.

That is the useful form of the rule: **native work per element must greatly
exceed the Python values that have to cross back for it.** Particles and
sparks win on opacity, flocking wins on density, projectiles win on
neither.

### The remedies, when opacity is the problem

In order of preference:

1. **Make the consumer batch-aware.** What `ShapeBatch` did for the
   renderer. Best outcome: the boundary moves and the Python side gets
   simpler too.
2. **Move the consumer inside the line.** Sometimes right, and the
   example this originally gave was not: it said a native `SpatialHash`
   was the wrong shape because it "returns `list[K]` of Python keys per
   query", where a native hit broad-phase would return only the pairs
   that collided. Measured, that crossing is 4% of the Python broad-phase
   it replaces, and the index landed at 17x as a Python-facing store —
   see **Decision 7**, which also explains why the instinct that it would
   not rescue projectiles was right for an entirely different reason.
   Keep the remedy; distrust the argument. A crossing that scales with
   `k` is only expensive if the work it replaces does not.
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

   **Flocking is the case where the answer was no, and working out why
   changed what the tolerance is for.** The first reason is the obvious
   one: `SpatialHash._cells` is a `dict[Cell, set[int]]`, so a radius
   query yields each cell's members in CPython set iteration order, and
   `flock_force` sums over them. Different order, different last bit —
   measured at 46% of agents and a worst relative difference of 6.4e-13.
   Reproducing that order in Rust would mean reimplementing a CPython
   internal and depending on it not changing.

   The second reason is sharper and was found by accident, while
   debugging a parity probe that compared two worlds built from the same
   seed. **A seeded flock does not tick the same way twice in Python
   either.** `EntityManager` hands out random uuid4 ids and
   `get_entities_with_cached` iterates a set of them, so the sweep
   order — which *is* the Gauss-Seidel order, and therefore part of the
   simulation — differs between processes. Three runs of one seeded
   flock give three different states. So "bit-exact with Python" was
   never an available contract here: there is no single Python answer to
   be exact to. That is a pre-existing defect rather than anything the
   port introduced — it is issue #324, and the fix is a behaviour change
   rather than a bug fix, because the sweep order it would pin is
   currently arbitrary — and it does not block the port — but it does mean the native store is *more* reproducible than
   the Python one it mirrors, which is the opposite of what a tolerance
   usually implies.

   **What the tolerance then has to be is: one permitted cause, stated,
   with everything else pinned exactly.** This is the rule the flocking
   port adds, and the reason it matters is a measurement. A transcription
   slip — writing `dx * (target / len)` for `(dx / len) * target`, which
   is the same expression refactored — moves a result by about one ulp.
   The ordering noise it is being compared against is 6.4e-13, three
   orders of magnitude *larger*. **No tolerance wide enough to admit the
   ordering could ever catch such a slip**, so a tolerance-only parity
   suite does not test the arithmetic at all; it only tests that nothing
   is grossly wrong. Confirmed by sabotage: that exact refactor passes
   every tolerance test in the suite.

   The remedy is to find a regime where the permitted cause cannot
   operate, and assert `==` there. For flocking that is constructed
   geometry in which no agent has more than one flockmate, so the sum has
   no order to differ in — and it has to be *constructed*, because
   picking the one-neighbour agents out of a random flock leaks: a lone
   agent reads its flockmate's live position, and that flockmate may
   itself have been perturbed (measured: 47 of 48 agreed, and the one
   exception had inherited a neighbour's divergence). In that regime the
   whole tick is bit-exact through every branch — clamping, coincident
   agents, seek, staggering, forty ticks — which is what makes the
   tolerance on real flocks evidence of summation order rather than a
   blanket amnesty.

   Two smaller findings from the same round, recorded so nobody re-derives
   them. **Getting `Vector2.length` exact required changing it**: pymunk
   spells it `sqrt(x**2 + y**2)`, `x**2` goes through the platform's
   `pow`, and glibc's `pow` disagrees with `x * x` for 0.08% of inputs,
   so the length — and everything `normalized()` divides by — was only as
   portable as the libm underneath. It is now `sqrt(x * x + y * y)`,
   which is also 1.6x faster and no less accurate (over 200k vectors the
   two differ 70 times, with the `pow` form closer 34 and the
   multiplication form 36). And **several plausible-looking sabotages
   turn out not to be differences at all**: `>` against `>=` on any of
   the three clamps is unobservable, because at the threshold the scale
   factor is `max / sqrt(max * max)`, which is exactly 1.0; a flockmate
   exactly on the separation radius contributes `(1 - d/r) * max_speed`,
   which is exactly 0.0; and the `want_cohesion`-style flags are a pure
   optimisation, because a term scaled by a zero weight is zero either
   way. A sabotage that nothing catches is sometimes a complete suite
   rather than a missing test, and the way to tell is to work out whether
   the sabotage changed the answer at all.
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

## Decision 7 — A shared primitive is priced on itself, and Amdahl decides what a consumer feels

This decision exists because **Decision 3 got one wrong, and the way it
was wrong is more useful than the correction.**

Decision 3's remedy 2 said a native `SpatialHash` is "the wrong shape"
because it "returns `list[K]` of Python keys per query", and Track R item
3 was sequenced as native state for native consumers only. The reasoning
is that a per-query crossing scales with how many candidates the query
found. **That is true and it does not matter**, which the measurement
settles:

| | |
| --- | ---: |
| Python broad-phase, 1000 keys, one query each, k=17 | 6.97 ms |
| the `list[K]` crossing alone | 0.39 ms |
| …as a share of what it replaces | **4%** |

The crossing scales with `k`. So does the Python broad-phase, at about
twenty times the cost per candidate: Python pays a dict lookup, two
subtractions and a multiply-add where the crossing pays an incref and a
list append. **The ratio is therefore roughly flat in density** — 20.5x
at k=17, 22.3x at k=32, and still 16.0x in the degenerate case where
every key is everyone's neighbour. Decision 3 reasoned about one side of
a ratio.

Two things made it work that are worth copying. The index **holds** the
`PyObject` the caller inserted, so returning a candidate is a reference
count rather than a string allocation — returning `Vec<String>` would have
made the original objection true. And `Vector2` is a `tuple` subclass, so
a position crosses through PyO3's tuple fast path with no attribute
access.

### What it delivered, and the number that matters more

The index itself: **17x** on a tick of re-sync-then-query at 1000 keys,
insert 4.9x and queries 20.5x. Every consumer got it **without changing a
line**, which is the argument for this shape over a per-consumer port.

And then Amdahl:

| consumer, unchanged | Python | native index | |
| --- | ---: | ---: | ---: |
| `TopDownSystem` separation, 1000 clumped | 17.3 ms | 9.25 ms | 1.87x |
| `TopDownSystem` separation, 1000 uniform | 2.82 ms | 0.83 ms | 3.42x |
| `TopDownSystem` separation, 200 | 0.66 ms | 0.15 ms | 4.30x |
| `FlockingSystem`, Python steering, 1000 | 16.4 ms | 9.8 ms | 1.67x |
| `SpatialIndexSystem.update`, 2000 tracked | 1.79 ms | 1.15 ms | 1.55x |
| `MagnetSystem.update`, 100 magnets | 1.69 ms | 1.19 ms | 1.43x |
| `ProjectileSystem.update`, 1000 live | 2.81 ms | 2.13 ms | 1.32x |

**A 17x primitive bought between 1.3x and 4.3x.** The broad-phase was
never most of any consumer's tick — what follows a query is an ECS lookup,
a component fetch and some arithmetic, all of it Python, all of it
untouched. So:

> **Price a shared primitive on itself; price a subsystem end to end. Do
> not quote the first and mean the second.**

The 5x threshold in Decision 1 is written for a subsystem. A primitive
clears it on its own figure *and* pays its parity bill once for five
consumers instead of once each, which is better leverage per unit of
permanent maintenance than any previous port — the flow field's 56x
serves one caller. That is the case for admitting it at 17x while its
consumers see 1.3x, and it is a weaker case than any row above it.

### Where Decision 3 was right after all

"Projectiles then become a consequence of it" — item 3's second sentence —
is **false, measured at 1.32x.** A first projection said 10.7x, by
assuming the pinned 1.53 ms hit check would move native wholesale. Only
its broad-phase did; the ECS lookups, the `Hurtbox`/`Health` checks and
the team comparison stayed, and they are the bulk. Reaching 10x there
needs a native pool that also filters by team natively, which puts
gameplay data inside the index — a separate decision, not a consequence of
this one. **Projectiles stay declined**, now at 1.32x with an accelerated
index rather than an estimated 2.0x, which makes the decline firmer.

### The cost, stated

**One access pattern is asymptotically slower than Python.** The native
grid rebuilds on the first query after any write — free for the pattern
every consumer has (sync the whole index, then sweep it: one rebuild for
`n` queries) and quadratic for a caller that *alternates* insert and
query, where Python's incremental insert is O(1).

| keys | alternating, native against Python |
| ---: | ---: |
| 250 | 1.9x faster |
| 1000 | 0.52x |
| 4000 | **0.13x** |

Nothing in the engine alternates and `accelerate=False` is the remedy, but
this is the first native store that is *worse* at something rather than
merely different, so it is written down here and bounded by a test rather
than left to be discovered.

### Two findings about the parity discipline itself

**A store that becomes the default silently disarms its own references.**
`tests/test_native_flocking_parity.py` rebuilds a Python `SpatialHash` as
the reference its first tier compares against. The moment `SpatialHash`
had a native store and defaulted to `auto`, that reference became native
and the tier compared the native grid with itself. Demonstrated: with the
distance test sabotaged from `<=` to `<`, the unpinned suite passed all 69
tests and the pinned one failed 2. The same applies to
`tests/performance/conftest.py`'s `build_hash`, whose complexity guards
would have measured whichever store the contributor happened to have
built, and to `tests/test_common_spatial.py`, which would have gone on
passing while testing only one store.

> **Adding a native store to an existing class changes the meaning of
> every test that constructs it.** Pin every reference and every
> complexity guard to the Python store explicitly, and parametrise the
> unit suite over both.

**And `accelerate=False` has to mean it all the way down.**
`FlockingSystem`'s Python path builds its own `SpatialHash`, with no
`accelerate` argument — so `FlockingSystem(accelerate=False)` quietly
indexed natively, and the "Python" flocking tick measured 9.8 ms instead
of 16.4 ms. That silently restated Decision 1's flocking row from 9.0x to
5.2x, and put native code inside a parity suite's Python reference. A
subsystem that forces the Python path must force it in everything it
constructs.

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
2. **Flocking — BUILT.** Priced at 15.4x at 1000 agents, which was 99%
   of a frame, and achieved **9.0x** — 16.6 ms down to 1.85 ms, or 11% of
   a frame. The first port of something that is *not* opaque: every agent
   is an ECS entity, so unlike the field, the whole flock crosses every
   tick and the crossing is 63% of the native tick rather than a rounding
   error. That is the price of non-opacity, measured, and it is the
   difference between this row and the field's 56.7x.

   Where it pays best is the case it was really for. A flock converging
   on the player makes every agent everyone's neighbour, so the tick goes
   quadratic: at 2000 agents Python goes from 34 ms spread to 74 ms
   clumped, while the native store goes from 3.9 ms to 4.6 ms. Clumping
   costs Python 2.2x and the native store 1.26x, because what density
   multiplies is the per-neighbour arithmetic and not the handoff. So the
   advantage *grows* in the regime a horde actually creates, which the
   uniform-density figure above understates.

   **Staggering is now largely redundant**, which is worth saying because
   it is a knob demos set. `groups` exists to spread steering across
   ticks, and in Python it works: 3000 agents go from 50 ms to 20 ms at
   `groups=4`. Natively the same change moves 6.2 ms to 5.2 ms, because
   what it skips is the steering and what remains is the crossing and the
   prologue. A game on the native store should reach for it only after
   measuring.

   It is also the first port to need a **tolerance** rather than `==`,
   with one permitted cause and the arithmetic pinned separately — see
   Decision 5, which this increment rewrote.
3. **`SpatialHash` — BUILT, and not in the shape this item specified.**
   It said "native state for native consumers only — never as a
   Python-facing index returning `list[K]`", and the `list[K]` crossing
   measures at **4%** of the Python broad-phase it replaces. So it landed
   as a drop-in native store behind the same methods: **17x** on the
   index, and every consumer — flocking, actor separation, magnet
   pickups, projectile hits, two demos — got it without changing a line.
   Decision 7 has the measurement, and what it cost to have been wrong.

   **What the consumers actually feel is 1.3x to 4.3x**, because the
   broad-phase was never most of anyone's tick. The best of them is the
   case this is really for: `TopDownSystem`'s actor separation at 1000
   clumped actors, 104% of a frame down to 56%. The worst is projectiles
   at 1.32x, so this item's second sentence — "projectiles then become a
   consequence of it" — is **false**, and they stay declined.

   It is also the first native store that is *worse* than Python at
   something: an alternating insert/query loop is quadratic against
   Python's linear, 0.13x at 4000 keys. No consumer does that; the cost is
   bounded by a test and `accelerate=False` is the remedy.
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
