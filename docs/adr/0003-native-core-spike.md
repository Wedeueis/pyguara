# ADR 0003: RFC-0003's native Rust core — what Marco 0 found

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

**That is the thing to measure next, and it has not been measured.**

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

## Recommendation

**Narrow the RFC to its best-evidenced parts, and do not start with Marco 1.**

1. **Decide Marco 1's maths half on a measurement that does not exist yet**
   -- how many `Vector2` operations a real frame performs. The pymunk tax is
   0.024 ms and does not decide it; the per-op cost (up to 1,847 ns) could
   decide it either way. `SpatialHash` has no such constraint and can
   proceed regardless. See "Options for the maths rewrite".
2. **Benchmark `dijkstra_map`, the flow field and WFC first.** They are the
   RFC's own best-value claim and the only numbers with nothing behind them.
   A flow field is pure in, pure out — dimensions and seeds in, coordinates
   out — so it is both the cheapest thing to measure and the cheapest thing
   to port.
3. **Then prototype exactly that one module**, as Marco 0 intended, with the
   toolchain pins verified.
4. **Keep Marco 3.** Finding 3 supports it, and the baselines now exist.
5. **Hold Marco 2** (the render batcher) until the zero-copy buffer claim is
   prototyped. It is the most invasive milestone and depends on the buffer
   protocol working exactly as described.

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

**A is the default**, being the only one that needs no further evidence. B
becomes right if a frame turns out to perform thousands of vector operations
outside the already-optimised loops. C is a separate decision about the
physics backend, which should not be smuggled in as a consequence of a
maths optimisation.


## What this spike produced

- `tests/performance/test_perf_pools.py` — the pool baselines (Finding 3).
- `tests/performance/test_perf_physics_probe.py` — the sweep baseline, added
  as W8 ahead of this.
- Pool and probe figures in `docs/guides/performance.md`.
- The pymunk/CFFI pre-flight result, reproducible from the snippet in
  Finding 1.
