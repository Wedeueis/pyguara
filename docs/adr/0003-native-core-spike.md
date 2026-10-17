# ADR 0003: RFC-0003's native Rust core — what Marco 0 found

> **Generalised by [ADR 0004](0004-the-native-boundary.md).** This
> document measured the first milestone and recommended an order.
> ADR 0004 replaces that order with a test a candidate can be put
> through before any Rust is written, after the sparks increment
> below showed the same reasoning giving answers between 1.4x and
> 25x for the same module depending only on where the boundary was
> drawn. Read this for the measurements; read 0004 for the rule.

- **Status:** proposed — the decision in "Recommendation" is the one being asked for
- **Date:** 2026-10-16
- **Context:** `project/backlog/active/rust_core.md` (RFC-0003), [issue #305](https://github.com/Wedeueis/pyguara/issues/305)

## Context

RFC-0003 proposes moving the numeric, spatial and batching engines into a
compiled Rust extension -- a new `_core_rs` module -- via PyO3 and maturin, keeping
the ECS, DI container, event bus, kits, UI and Studio in Python. It is
sequenced as four milestones: maths and `SpatialHash`, the render batcher,
the object pools and flocking, then pathfinding, procgen and the character
sweep.

It was accepted into the plan as **gated**, not approved: this repository's
norm is to measure before building, which is why issue #161 reads *DEFERRED
by measurement, do not build yet*. Marco 0 is that gate — establish real
baselines, run the pre-flight checks that could sink a milestone, and decide
on the evidence rather than on the proposal's own numbers.

This records what it found. **No Rust was written**, and the reason is
finding 1.

## Finding 1 — `Vector2` cannot be a `#[pyclass]` while pymunk is the physics backend

This is the one that changes the plan.

RFC-0003's Marco 1 reimplements `Vector2` as `#[pyclass(frozen, eq, hash)]`
wrapping `glam::Vec2`, and states it stays *"compatível com desempacotamento
de tuplo `(x, y)` para manter compatibilidade total com o Pymunk CFFI quando
passado para `body.position = vec`"*.

It does not. Measured against pymunk 7.2.0 with a class offering `__iter__`,
`__len__` and `__getitem__` — everything a PyO3 pyclass can provide —
**9 of 10 pymunk entry points reject it**:

```
TypeError: initializer for ctype 'struct cpVect' must be a list or tuple
           or dict or struct-cdata, not RustLikeVector2
```

`body.position`, `body.velocity`, `space.gravity`, `apply_impulse_at_local_point`,
`apply_force_at_world_point`, `pymunk.Circle`'s offset, `pymunk.Poly`'s
vertices, `point_query_nearest` and `segment_query_first` all refuse it. Only
`pymunk.Transform(tx=…, ty=…)` works, because it takes floats.

The reason today's `Vector2` works is in its MRO:

```
Vector2 -> Vec2d -> tuple -> object
```

`pymunk.Vec2d` **is a tuple subclass**, so our `Vector2` is literally a
tuple and CFFI accepts it structurally. A PyO3 `#[pyclass]` cannot extend a
variable-length built-in like `tuple`, so a Rust `Vector2` cannot be one.

### What that costs — measured, and smaller than it first looked

Converting at the boundary works: `body.position = (v.x, v.y)`, at **+85 ns
per crossing** (608 ns → 694 ns), across 21 vector-passing call sites in
`physics/backends/pymunk_impl.py` — the only file in the engine that touches
pymunk.

The first version of this ADR stopped there and recommended dropping the
maths rewrite, reasoning that a conversion tax is the wrong direction for a
change meant to remove overhead. **That was asserted, not measured, and it
was wrong.** Counting the crossings a tick actually makes, by wrapping the
CFFI-facing property accessors:

| Scene | Crossings / tick | Tax at 85 ns |
| --- | ---: | ---: |
| 100 dynamic bodies | 200 (all reads) | 0.017 ms |
| 100 bodies + 20 movers | 280 | **0.024 ms** |
| 50 movers | 211 (all writes) | 0.018 ms |

0.024 ms is **0.14% of a 16.7 ms frame**. The tax is noise.

What is *not* noise is what `Vector2` costs today:

| Operation | ns |
| --- | ---: |
| `Vector2 + Vector2` | 432 |
| `Vector2 * float` | **1,115** |
| `Vector2.normalize()` | **1,847** |
| `Vector2.magnitude` | 253 |
| `Vector2(x, y)` | 246 |
| scalar equivalent | ~67 |

So the question is not the pymunk tax. It is whether enough game code does
vector arithmetic for a faster `Vector2` to repay a rewrite — and there is a
reason to doubt it: the RFC's own motivation notes that `flock_force` was
already rewritten in scalar variables to escape this cost. If the hot loops
have already hand-optimised `Vector2` away, what remains are API boundaries
where 400 ns does not matter.

### Measured: where the `Vector2` traffic actually is

Counted with `tools/count_vector_ops.py`, which wraps the operators and
tallies them.

**The Python code that runs every frame barely touches `Vector2`.** Across
every demo that runs without a GL context: **1–8 operations per frame**,
0.0002–0.0022 ms. Those demos sit in menus and idle scenes, so this is a
floor rather than a representative figure — but it is the floor for
general game and engine code.

**The hot systems are saturated with it.** Per tick:

| System | Vector2 ops | Implied ms | Share of that system's measured cost |
| --- | ---: | ---: | ---: |
| Flocking, 500 agents | 5,502 | 2.85 | — |
| Flocking, 1000 agents | 11,000 | 5.69 | **36%** of 16.0 ms |
| Flocking, 2000 agents | 22,001 | 11.38 | **33%** of 34.3 ms |
| Particles, 1000 live | 4,000 | 0.99 | **45%** of 2.20 ms |
| Particles, 4000 live | 16,000 | 3.94 | **44%** of 9.02 ms |
| Sparks, 1000 live | 5,000 | 2.29 | **80%** of 2.85 ms |

Construction dominates — 6 `Vector2` objects per agent per tick in
flocking, 4 per particle — not arithmetic.

This **refutes the doubt stated above**. `flock_force` itself is scalar, but
the system around it (reading and writing `transform.position`, integrating
velocity) builds `Vector2` objects per element per tick. A third to four
fifths of the hot systems' cost is this type.

### And yet the conclusion does not change

A Rust `Vector2` would address that traffic — and **Marco 3 removes it
entirely**. Rewriting the pools and the flocking solver as Rust SoA means
positions and velocities live in native arrays; no Python `Vector2` is
constructed per element at all. Optimising the type would be optimising
traffic the next milestone deletes.

So the two readings converge on the same answer for opposite reasons:

- If Marco 3 happens, a Rust `Vector2` is **redundant** — it speeds up what
  Marco 3 removes, and what remains in Python does 1–8 ops a frame.
- If Marco 3 does *not* happen, a Rust `Vector2` becomes **the cheapest
  substantial win available**: it would recover a large share of 33–80% of
  the hot systems' cost without restructuring them, for one type's
  compatibility risk.

That is a real fork, and it is about Marco 3 rather than about the maths.



### Consequence

The blocker is real but narrower than "drop the maths rewrite": `Vector2`
cannot be a pyclass *and* keep structural pymunk compatibility, so Marco 1
has to pick a boundary strategy. Four exist — see "Options for the maths
rewrite".

Note also that pymunk is not a thin layer to swap: 7 of the demos use
`RigidBody` dynamics, and the backend implements joints, collision
callbacks, raycasts and region queries on top of Chipmunk's solver.


## Finding 2 — the "today" column was not measured against this tree

| RFC's claim | This repository |
| --- | --- |
| Batching + packing 20,000 sprites: ~55.0 ms | **49.4–53.5 ms** — accurate |
| Flocking, 2000 agents: ~18.5 ms | **34.3 ms** (documented); 1000 agents is 16.0 ms |
| Update + pack 10,000 particles/projectiles: ~14.0 ms | **~22.5 ms** extrapolated from 9.02 ms at 4000 |
| Swept `CharacterMover`, 50 actors: ~3.2 ms | **6.07 ms** measured, 25,124 CFFI allocations/simulated second |
| Flow field 100×100: ~9.5 ms; WFC 40×40: ~45.0 ms | **unmeasured** — no benchmark exists |

Three of the five understate the current cost by 1.6–1.9×. Note the
direction: understating the baseline makes the claimed speedup *smaller*
than reality, so the RFC's case is conservative rather than inflated. The
figure it gets right is the one with an existing benchmark behind it.

The two it quotes for pathfinding and procgen have no benchmark in the tree
at all, and those are the modules it calls *"a melhor relação
custo-benefício de toda a engine"* — so the best-justified milestone is the
one resting entirely on unverified numbers.

## Finding 3 — the pools' cost is not where the proposal implies

Marco 3 replaces the particle, spark and projectile pools with Rust SoA.
Benchmarks added by this spike (`tests/performance/test_perf_pools.py`,
figures in `docs/guides/performance.md`):

| | Capacity | Live | ms / update |
| --- | ---: | ---: | ---: |
| particles | 1000 | 0 | 0.024 |
| particles | 1000 | 1000 | 2.196 |
| particles | 4000 | 4000 | 9.020 |
| sparks | 4000 | 4000 | 11.454 |

A dead slot costs 0.024 µs; a live one 2.2 µs — ninety times as much. The
"walks its whole capacity every frame" observation is true and nearly free,
which also **retires the active-prefix compaction** this plan had queued as
likely "most of the available win": it would recover 0.024 ms.

This *strengthens* Marco 3. The cost is per-element arithmetic, which is
exactly what SoA plus SIMD addresses.

## Finding 4 — the toolchain cost is real and unpaid

There is no Rust toolchain on this machine: no `rustc`, `cargo`, `rustup` or
`maturin`. That is not an obstacle to installing one; it is the concrete form
of the cost the plan flagged — after Marco 1, `uv sync` no longer produces a
working checkout. Every contributor needs a Rust toolchain and
`maturin develop`, CI grows a build matrix, and an editable install stops
being editable for half the engine.

Two pins the RFC specifies could not be checked without a toolchain and
should be before Marco 1 starts: it pairs `pyo3 = "0.23"` with Rust
**edition 2024**, which requires Rust ≥ 1.85 — newer than that pyo3 line —
and it assumes `abi3-py312` supports the `frozen`, `eq` and `hash` pyclass
features it wants.

## Finding 5 — Marco 3 prototyped: 268× on the arithmetic, ~6× on the frame

A Rust toolchain was installed (1.99.1, so edition 2024 is available — one of
finding 4's open pins resolved) and one of Marco 3's three pools built as a
structure-of-arrays `#[pyclass]`: `rust/src/pools.rs`, measured by
`tools/bench_native_pool.py`.

Scope is deliberately one pool, not three plus flocking. One real number
decides the milestone; three would not decide it harder.

**Parity first.** Both pools seeded with identical state and ticked 60
times agree to 0.000038 px — f32 rounding, nothing else. `ParticleSystem.emit`
randomises speed over `[speed*0.5, speed*1.5]`, so the two cannot be seeded
through their own emit paths and compared; the first attempt at this
"disagreed" by 40 px for exactly that reason.

**The arithmetic:**

| Scenario | Python | Rust | Speedup |
| --- | ---: | ---: | ---: |
| 1000 live / 1000 capacity | 1.63 ms | 0.006 ms | **268×** |
| 4000 live / 4000 capacity | 6.66 ms | 0.025 ms | **268×** |
| 0 live / 1000 capacity | 0.022 ms | 0.001 ms | 36× |

The RFC claimed ~45×. The measured figure is six times better than claimed —
the first of its numbers to come out *in its favour*.

**But the frame is not only arithmetic.** `update` is 84% of the pool's cost
and `render` the other 16% (0.442 ms of 2.73 ms at 1000 live; 1.85 ms of
10.99 ms at 4000). So porting `update` alone is bounded by Amdahl:

| Live | Python frame | With native update | End to end |
| ---: | ---: | ---: | ---: |
| 1000 | 2.73 ms | 0.45 ms | **6.1×** |
| 4000 | 10.99 ms | 1.87 ms | **5.9×** |

**~6× end to end, and render becomes the bottleneck.** Getting past that
needs the RFC's `pack_for_render` writing `GpuSpriteInstance` buffers
directly — which is untested here, and carries the same zero-copy
buffer-protocol risk as Marco 2.

### What the prototype does not do

Honest limits, because they are where the remaining design risk is:

- **No textures, colour interpolation or material.** The real `Particle`
  carries a `Texture` reference and `color_start`/`color_end`. Those are
  Python objects; an SoA pool needs them indexed or kept Python-side, and
  that interface is unexplored.
- **f32, where Python uses f64.** Fine for particles (0.000038 px over 60
  ticks) and a deliberate choice for memory and SIMD, but it is a
  behaviour change, not a free one.
- **No render packing**, per above — the thing that decides whether the
  milestone is worth 6× or much more.
- **One pool of three.** Sparks and projectiles have the same shape;
  projectiles additionally query the spatial hash, which means either a
  native hash too or a crossing per projectile.

The crate is **not wired into `pyproject.toml`**: it builds standalone via
`cargo build --release`, so `uv sync` keeps working for anyone without a
Rust toolchain and the repository stays buildable while this is still a
question. Note that `maturin build` reads the project name from
`pyproject.toml` and produces a wheel called `pyguara-0.5.0`, which would
overwrite the real package — the benchmark loads the compiled library
directly instead.

## Recommendation

**Narrow the RFC to its best-evidenced parts, and do not start with Marco 1.**

1. **Drop Marco 1's maths half.** Both halves of this are now measured, so
   it is a decision rather than a bet. The hot systems spend 33–80% of their
   time in `Vector2`; Marco 3 deletes that traffic by moving the data into
   native arrays, and finding 5 shows it does so at 268x on the arithmetic.
   The Python code that remains does 1–8 vector operations a frame. So the
   maths rewrite optimises what Marco 3 removes, for a compatibility risk
   (`Vector2` is a `tuple`; pymunk needs it to be) that buys nothing once
   Marco 3 lands. `SpatialHash` is unaffected and can proceed.
2. **Benchmark `dijkstra_map`, the flow field and WFC first.** They are the
   RFC's own best-value claim and the only numbers with nothing behind them.
   A flow field is pure in, pure out — dimensions and seeds in, coordinates
   out — so it is both the cheapest thing to measure and the cheapest thing
   to port.
   *Done, and it was the right place to look.* Measured, a 96x96 Python
   recompute is 85 ms — 513% of a frame, so the feature could not be used
   at interactive rates on a grid that size at all. Guarded first per ADR
   0004's Decision 6, then ported: **1.6 ms, 46-53x**, bit-exact. WFC
   remains unmeasured.
3. **Then prototype exactly that one module**, as Marco 0 intended, with the
   toolchain pins verified.
4. **Do Marco 3, and do its render packing in the same milestone.** Finding
   5 measured the pool: 268x on the arithmetic, six times better than the
   RFC claimed. But `update` is only 84% of the pool's frame, so porting it
   alone caps out at ~6x end to end and makes `render` the bottleneck. The
   milestone is worth doing and worth scoping to include `pack_for_render`,
   which is also where the remaining risk is -- textures and colour are
   Python objects an SoA pool has nowhere to put, and the zero-copy buffer
   claim is still untested.
5. **Hold Marco 2** (the render batcher) until the zero-copy buffer claim is
   prototyped. It is the most invasive milestone and depends on the buffer
   protocol working exactly as described.
   *Amended after the sparks increment below:* a narrow slice of batched
   submission came forward out of necessity, as `ShapeBatch` — Python lists
   of packed rows, not a zero-copy buffer. The claim Marco 2 rests on is
   still untested.

## Marco 3, increment 2 — sparks, where the render half *is* the frame

Recommendation 4 above said to port the pools' render packing as well as
their arithmetic, on the evidence that `update` was 84% of a particle
frame. Applied to `Sparks` that reasoning inverts, and the measurement is
the only thing that showed it:

| | `update` | `render` | render's share |
| --- | ---: | ---: | ---: |
| 1000 particles | 1.574 ms | 0.367 ms | 19% |
| 1000 sparks, dots | 2.063 ms | 2.759 ms | 57% |
| 1000 sparks, streaks | 2.009 ms | 5.360 ms | **73%** |

The cause is structural rather than incidental. A particle is a sprite, so
a thousand of them reach the renderer as **one** `RenderBatch` per texture.
A spark is a primitive, so a thousand of them reach it as a thousand
`draw_circle` or `draw_line` calls. Porting only the arithmetic would
therefore have capped sparks at **1.4-1.8x** however fast the arithmetic
became — a milestone not worth shipping.

### So the render half needed a batched submission, and its shape was measured

Four candidates, at 1000 live:

| Candidate | dots | streaks | frame speedup |
| --- | ---: | ---: | ---: |
| Python, per primitive (baseline) | 2.525 ms | 5.165 ms | — |
| native rows, handed over whole | **0.329 ms** | **0.349 ms** | **13-20x** |
| native draw-call parameters, looped | 2.318 ms | 3.096 ms | 1.9-2.3x |
| native draw-call parameters, NumPy pack | 1.288 ms | 1.217 ms | 3.4-5.8x |

The two "parameters" candidates are the ones that keep the instance layout
private to the renderer, which is the cleaner layering. They lose by 4-10x,
for the reason that keeps recurring in this ADR: anything that walks the
elements in Python afterwards gives the saving straight back.

So `ShapeBatch` carries **packed rows** in the eleven-float layout now
documented in `pyguara/graphics/types.py`, and `ShapeBatchRenderer` is an
optional capability that only the ModernGL world renderer satisfies —
because it is the only backend where accepting one is a list `extend` of
something it already holds. Every other renderer keeps the per-primitive
path and the native arithmetic, which is the 1.9x that remains.

That layout was already being built by `GLRenderer.draw_rect`,
`draw_circle` and `draw_line` and read per instance by the shape shader.
What changed is that it is now named and documented, because a layout that
crosses a boundary undeclared is exactly how the texture-orientation
convention drifted (W6).

### End to end

| Live | Path | `update` | `render` | Frame | |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1000 dots | Python | 2.063 | 2.759 | 4.822 | |
| 1000 dots | **native** | 0.003 | 0.287 | **0.290** | **16.6x** |
| 1000 streaks | Python | 2.009 | 5.360 | 7.368 | |
| 1000 streaks | **native** | 0.003 | 0.299 | **0.302** | **24.4x** |
| 4000 streaks | Python | 8.085 | 21.937 | 30.021 | |
| 4000 streaks | **native** | 0.011 | 1.269 | **1.280** | **23.5x** |

### Two bugs this increment turned up

**The native emission paths consumed the RNG stream differently from the
Python ones.** `ParticleSystem.emit` and `Sparks.burst` ask for a free slot
*before* they draw, so a burst that overflows the pool consumes nothing for
the elements it drops. Both `_emit_native` and a first draft of
`_burst_native` drew `count` sets regardless, which left the two stores'
streams at different positions after any overflowing burst — and then every
*later* burst differed, while the burst that caused it looked correct. This
was live in the merged particle pool. Both now clamp to the free slots, and
`test_an_overflowing_burst_leaves_both_streams_in_step` in each parity file
fails without the clamp.

**`tools/bench_native_pool.py` had been broken since the particle pool
landed**, raising `StopIteration`: it was written against the spike's pool
API (`emit(count, x, y, ...)`, `position_at`) and hand-seeded a Python
`Particle` that the accelerated default no longer creates. Rewritten to
measure whole frames of both pools through the public API, with parity left
to the parity tests — a benchmark that also claimed to prove correctness
proved neither.

### And one finding about the *Python* path

The published particle table emits an untinted burst. A burst with a colour
animation — fire, smoke, anything that fades — costs the Python path 6.0 ms
of a 7.6 ms frame at 1000 live, because `_particle_color` constructs two
`Color` objects and lerps them per particle. Natively it is unchanged, so
the speedup there is **55-58x** rather than 18x. Read the other way, that is
the cheapest unclaimed win left in `particles.py`, and it is in Python.
Recorded, deliberately not taken: the remediation plan's "no interim Python
optimisation that Rust would replace" still holds.


## Options for the maths rewrite

Four, in increasing order of commitment. The pymunk tax (0.024 ms/tick)
does not distinguish them; what does is how much the engine would gain from
a faster `Vector2`, which is unmeasured.

**A. Keep `Vector2` in Python; Rust uses `glam` internally.** The Rust
modules take and return floats, tuples or buffers. Nothing about
`pathfinding.rs`, `procgen.rs` or the pools needs the Python-facing vector
to be Rust. Zero compatibility risk, zero tax, and it forfeits the per-op
win — which may be most of the win already gone, if the hot loops have
hand-optimised `Vector2` away.

**B. Rust `Vector2`, converting to tuples at the pymunk seam.** The tax is
0.024 ms/tick, confined to one file. The real compatibility surface is
**not** pymunk: it is everything relying on `Vector2` being a `tuple` —
unpacking (`x, y = v`), `tuple(v)`, equality against literal tuples, use as
a dict key, indexing. The 10 `isinstance(..., Vector2)` sites are fine, a
pyclass being a real type; the tuple-ness needs an audit this spike did not
do. Gated on the frame-op measurement above.

**C. Replace pymunk with a Rust physics crate** (`rapier2d` the obvious
candidate). Removes the CFFI boundary, lets `Vector2` be Rust natively, and
makes Marco 4's sweep native in the same stroke. It is also a different
proposal from the one on the table: a different solver changes game feel,
and the backend's `one_way` platform behaviour, joints, collision callbacks
and every physics test would be reimplemented against it. Seven demos use
`RigidBody`, so this is not a corner of the engine. The honest version of
this option is that it is a project, not a milestone.

**D. A hand-written C-level type that genuinely subclasses `tuple`.**
CPython permits it — `Vec2d` is one — but PyO3's `#[pyclass]` cannot express
it, so this means raw `pyo3::ffi` and a manually built `PyTypeObject`,
giving up the memory safety that motivates using Rust at all. Named so it is
considered-and-rejected rather than unexplored.

**A.** The measurements settle it rather than leaving it conditional: a
frame does perform thousands of vector operations, all of them inside the
systems Marco 3 rewrites — and Marco 3 is now measured working, at 268x on
the pool arithmetic. Outside those systems a frame does 1–8 operations, so
there is nothing left for a faster `Vector2` to speed up.

**B only if Marco 3 is abandoned.** Then that 33–80% stays in Python and a
Rust `Vector2` recovers a large share of it without restructuring anything,
subject to the tuple-compatibility audit above. Keep this on the shelf
rather than in the plan.

**C is a separate decision** about the physics backend and should not be
smuggled in as a consequence of a maths optimisation. **D stays rejected.**


## What this spike produced

- `tests/performance/test_perf_pools.py` — the pool baselines (Finding 3).
- `tests/performance/test_perf_physics_probe.py` — the sweep baseline, added
  as W8 ahead of this.
- Pool and probe figures in `docs/guides/performance.md`.
- `tools/preflight_pymunk_vector.py` — finding 1, re-runnable against a
  future pymunk rather than trusted from a document written against 7.2.0.
- `tools/count_vector_ops.py` — the `Vector2` frame-traffic measurement that
  decides Marco 1.
- `Cargo.toml`, `rust/src/` — the Marco 3 pools, standalone so `uv sync`
  still works without Rust: `particles.rs` and `sparks.rs`.
- `tools/bench_native_pool.py` — Marco 3's numbers, for both pools and
  whole frames rather than `update` alone.
- `pyguara/graphics/types.py`'s `ShapeBatch` / `ShapeKind` and
  `protocols.py`'s `ShapeBatchRenderer` — what the sparks increment needed
  and the measurement above chose the shape of.
- `rust/src/flowfield.rs` and `tests/performance/test_perf_pathfinding.py`
  — recommendation 2's module, which turned out to be the engine's largest
  margin and its first native port of something that is not cosmetic. Its
  standard is `docs/adr/0004-the-native-boundary.md`, which this spike's
  findings are what produced.
