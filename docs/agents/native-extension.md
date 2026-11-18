# The native extension

Moved out of `AGENTS.md` on 2026-11-14, unchanged, so that file stays short
enough to read every session. `AGENTS.md` keeps the rules; this has the
reasons and the detail.

Four subsystems and one shared primitive had a native implementation
beside a Python one. All five now have only the native one, and the
Python implementations live on as test code in `tests/reference/`:

| | native gain | |
| --- | ---: | --- |
| `FlowFieldService` | **26-32x** | 96x96 recompute, 52 ms -> 1.6 ms |
| `ParticleSystem` | 15-20x | whole frame, update plus render pack |
| `Sparks` | 13-24x | whole frame, via `ShapeBatch` |
| `FlockingSystem` | 8-19x | whole tick, 1000 agents 16 ms -> 1.9 ms |
| `SpatialHash` | 17x | the index; **1.3-4.3x** for its consumers |

**Read the `SpatialHash` row carefully** -- it is the one entry that is a
primitive rather than a subsystem, and the two numbers mean different
things. The index itself goes 7.5 ms to 0.44 ms at 1000 keys. What its
consumers feel is much less, because in each of them the broad-phase was
only ever a fraction of the tick: 1.87x for `TopDownSystem`'s actor
separation at 1000 clumped actors (which is still 104% of a frame down to
56%, the row that justifies the port) and 1.32x for `ProjectileSystem`,
which stays declined as a port of its own. `docs/guides/performance.md`
has the whole table and ADR 0004 Decision 7 has why a primitive is priced
differently.

`SpatialHash` used to be **worse** than Python at one thing: it rebuilt
its grid on the first query after any write, which is free when a caller
syncs the index and then sweeps it and quadratic when a caller
alternates `insert` and a query. A written slot is now kept on a short
pending list and checked directly, and the grid is rebuilt only once
about `sqrt(2n)` slots are pending, so the alternating loop is 5x faster
than Python at 4000 keys where it was 4x slower.
`docs/guides/performance.md` has the table.

A key whose `__hash__` or `__eq__` calls back into the same index raises
`RuntimeError: Already borrowed` on the native store, which holds an
exclusive borrow of itself for the length of a call. No engine key does
that; they are entity ids. Iterating a query's result while removing keys
is safe on both stores, because a query returns a list.

**The wheel ships it**, so an installed PyGuara runs native by default and
nobody runs `cargo` to get the numbers above. maturin is the build
backend, which means a *source* build -- `uv sync`, `uv build`, the sdist,
a platform outside the wheel matrix -- now needs a Rust toolchain, where
none was needed before. That is the price, and
`docs/adr/0006-shipping-the-native-extension.md` has why it is worth
paying.

**`FlowFieldService` is Rust-only** (ADR 0011, Decision 3), the first of
the five to lose its Python store. It takes no `accelerate=`. What it must compute is held three
ways:

- `tests/golden/flow_field.json`: the cost and direction of every cell
  in ten scenarios, as float hex, recorded while the Python and Rust
  stores still agreed. `tests/test_flow_field_golden.py` compares exactly.
- `tests/reference/flow_field.py`: the Python store that was removed,
  kept as test code on the generic `dijkstra_map` and `flow_field`
  functions, which the engine still ships for graphs that are not grids.
  `tests/test_flow_field_reference.py` compares it cell for cell.
- Sabotage: `DIAGONAL` set to `SQRT_2` in `rust/src/flowfield.rs` fails
  30 tests, 9 of them golden.

Those tests fail, not skip, without the extension. The next store to be
retired follows the same three steps, in that order.

**`Sparks` is Rust-only too**, the second. The same three steps, with
one difference: the pool is f32 where the Python pool was f64, so
nothing about it is bit-exact.

- `tests/golden/sparks.json`: every slot, every unbatched primitive and
  every batched row after seven scenarios, recorded from the Rust pool
  where the Python pool agreed to the parity tolerance. Compared to
  0.001, not exactly, because a burst's velocity passes through
  `math.cos` and a row's angle through the platform's `atan2`.
- `tests/reference/sparks.py`: the Python pool, which
  `tests/test_sparks_reference.py` compares with the old tolerances.
  The benchmark tools use it as their Python side.
- Sabotage: gravity applied before drag in `rust/src/sparks.rs` fails 7
  golden tests and 3 reference tests.

**`ParticleSystem` is the third**, and the same shape as `Sparks`:
`tests/golden/particles.json` (eight scenarios, compared to 0.001),
`tests/reference/particles.py`, and `tests/test_particles_reference.py`.
Damping applied before acceleration in `rust/src/particles.rs` fails one
golden and one reference test, the ones whose scenario has both. The
`Particle` class went with the Python pool: the Rust pool has no
per-particle objects, and `_native.slot(index)` reads one slot's columns.

**`FlockingSystem` is the fourth**, and the one ADR 0011 was least sure
of, because its two stores never agreed bit for bit: a neighbour sum has
no fixed order in Python. It converts because the Rust solver *is*
reproducible. It is f64, sweeps in a fixed order and calls no platform
maths function, and it gives the same bits across processes and hash
seeds.

- `tests/golden/flocking.json`: every agent's position and velocity
  after ten scenarios, as float hex, recorded from the Rust solver and
  compared exactly. Recorded where the Python path was within 4e-13 on
  the thirty-tick scenarios and 2e-8 after 240 ticks.
- `tests/reference/flocking.py`: the Python path, which
  `tests/test_flocking_reference.py` still compares in its three tiers
  (neighbourhoods exactly, one-flockmate arithmetic exactly, real flocks
  to 1e-9). It uses the Python `SpatialHash` by name.
- Sabotage: the alignment force scaled by the cohesion weight fails one
  golden test and two reference tests. Only the "tuned" scenario has
  unequal weights, which is why it is one.

Recording the vectors is what found that `integrate=False` steered by
positions the solver advanced and then discarded: the two stores were
0.1 apart after one tick. That was fixed before the recording was kept.

**`SpatialHash` is the fifth and last.** Membership is exact, so
`tests/golden/spatial.json` records the sorted answer to every query in
six scripts of interleaved writes (1,000 to 4,000 queries each), and
`tests/test_spatial_hash_golden.py` compares exactly.
`tests/reference/spatial.py` is the Python index;
`tests/test_spatial_hash_reference.py` is the old parity suite against
it. Making the rect query inclusive on its right edge in
`rust/src/spatialhash.rs` fails three golden tests and one reference
test. Tests that exist to prove a caller does not depend on result order
use `ReferenceSpatialHash`, because its order changes per process and the
Rust index's does not.

None of the five runs without the extension, and their tests fail rather
than skip without it.

```bash
uv sync                              # maturin is the backend; this builds it
make native                          # rebuild in place after editing Rust
```

`make native` is `maturin develop --release`, and the `--release` matters:
`maturin develop` alone produces a *debug* build, which is slower than the
Python it replaces. A bare `cargo build --release` still works and is
still found, but it is the second place looked at -- an installed library
wins, so after `uv sync` a plain `cargo build` leaves the new code
silently unused.

**The extension is required.** Bootstrap calls
`pyguara.native.require_extension()` before it builds anything, so a
missing or broken extension stops the game at startup with an error that
lists where it looked. `pyguara.native.describe()` says where it was
loaded from, `pyguara.native.status()` returns the same as fields, and
Studio's `project_overview` reports it.

`PerformanceConfig.native_acceleration` and `PYGUARA_NO_NATIVE`, which
chose between the two stores, are gone with the second store. A config
file that still sets the former loads, with a warning naming the key.
The physics engine is Rapier, in the extension, with no Python twin;
the static-solid mirror ADR 0009 describes went with pymunk.

Written outside the generated block above on purpose: `pyguara studio
instructions` rewrites what is inside it, and an earlier version of this
section was placed there and silently deleted on the next regeneration.

Real-GPU pixel comparisons are in `tests/integration/test_wgpu_pixels.py`,
and they skip when there is no adapter.

**Adding a native store to an existing class changes the meaning of every
test that constructs it**, which `SpatialHash` demonstrated the hard way:
the moment it defaulted to `auto`, the Python reference inside
`tests/test_flocking_reference.py` (then the flocking parity suite)
became native and that suite's
first tier compared the native grid with itself -- it passed all 69 tests
with the grid's distance test deliberately broken. So a reference, a
complexity guard and a subsystem's own `accelerate=False` path must each
pin the Python store *explicitly*, and a unit suite for a two-store class
should be parametrised over both. See ADR 0004 Decision 7.

**How closely they have to agree depends on what the subsystem is for.**
The pools compare with a tolerance, because they hold f32 where Python
holds f64 and a spark half a pixel away is a spark. The flow field is
**bit-exact** against its reference and tested with `==` on every cell,
because a field steers
enemies and one cell pointing elsewhere is a pack that goes the other way
round a wall. Changing `1.414` to `SQRT_2` in `rust/src/flowfield.rs`, or
reordering its neighbour table, breaks that on purpose -- both are
sabotage-tested.

Flocking is the one case where exactness is **not available**: a radius
query yields each cell's members in CPython set iteration order, and
`flock_force` sums over them, so the last bits differ. Its parity suite
therefore has one permitted cause and pins everything else exactly --
including a bit-exact tier on constructed geometry where no agent has
more than one flockmate, because a tolerance loose enough to admit the
ordering (6.4e-13) can never catch a transcription slip (one ulp). If
you touch `rust/src/flocking.rs`, read that file's module docstring
first. See `docs/adr/0004-the-native-boundary.md`, Decision 5.

`SpatialHash` is **bit-exact** on membership, for the flow field's
reason: an index decides which enemy a magnet pulls and who is a
flockmate, and `query_radius` confirms every candidate against an exact
squared distance, so being in range is a property of the positions alone.
Exactly one thing diverges, and it is the result's **order** -- Python
yields from a `set`, so for the string keys the engine uses
`PYTHONHASHSEED` randomises it per process and the Python store is not
reproducible against itself. Every comparison in its parity suite sorts,
and a caller wanting a particular one of several results must pick it by
distance or by id rather than taking the first.

The flow field is also where to look for how a native boundary should be
shaped: nothing outside `FlowFieldService` reads a cell, so the cost map
and the field never come back to Python and only `vector_at` crosses --
which is why it prices at 50x where flocking, whose agents are ECS
entities, prices at 15x.

`Sparks` also added `ShapeBatch` and the `ShapeBatchRenderer` capability
(`pyguara/graphics/types.py`, `protocols.py`), because a spark is one
primitive and 55-73% of a Python spark frame is `draw_circle`/`draw_line`
call overhead. Only the wgpu world renderer takes a batch; every
other renderer keeps the per-primitive path, and `tests/test_graphics_protocol_conformance.py`
asserts both halves of that on purpose.

The crate is wired into `pyproject.toml` through maturin, which puts the
extension inside the package: it is importable as
**`pyguara.pyguara_core_rs`**, not as a top-level `pyguara_core_rs`, since
a mixed python/rust wheel requires it to live under the Python package.
Two files spell that name -- `[tool.maturin] module-name` and
`pyguara/native.py` -- and `tests/test_native_loader.py` asserts they
agree, because a mismatch is silent: the import fails, the `target/`
library answers in a checkout, and an installed PyGuara runs pure Python
while reporting nothing wrong.

One wheel per platform, not per platform and interpreter: `abi3-py312`
means the 3.12 build runs natively under 3.13 as well. Five are built --
Linux x86_64 and aarch64, macOS x86_64 and arm64, Windows x64 -- and
`.github/workflows/wheels.yml` says why the omissions are omissions.

**Each `NativeGpu` is a whole wgpu device**: its own instance, adapter and
device. A game holds one. A process that opens applications and never shuts
them down holds one per application until a full garbage collection, and a
driver can segfault past its cap rather than refuse: Mesa's GL-on-D3D12
under WSLg does at the tenth. `NativeGpu.live_devices()` counts them, and
`tests/conftest.py` collects garbage after any test that leaves more than
four alive. A test that crashes inside `present()` or during garbage
collection, only in some orders, is this until shown otherwise.

See `docs/adr/0003-native-core-spike.md` for why this is an accelerator
rather than a rewrite, and `0006-shipping-the-native-extension.md` for why
it ships in the wheel and what that costs.
