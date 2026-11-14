# The native extension

Moved out of `AGENTS.md` on 2026-11-14, unchanged, so that file stays short
enough to read every session. `AGENTS.md` keeps the rules; this has the
reasons and the detail.

Four subsystems and one shared primitive have a native implementation
beside the Python one:

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

`SpatialHash` is also the first native store that is **worse** than
Python at something. It rebuilds its grid on the first query after any
write, which is free for the pattern every consumer has -- sync the index,
then sweep it -- and quadratic for a caller that alternates `insert` and a
query: 0.13x the Python speed over 4000 keys. Nothing in the engine does
that; `accelerate=False` is the answer for a game that does.

**The wheel ships it**, so an installed PyGuara runs native by default and
nobody runs `cargo` to get the numbers above. maturin is the build
backend, which means a *source* build -- `uv sync`, `uv build`, the sdist,
a platform outside the wheel matrix -- now needs a Rust toolchain, where
none was needed before. That is the price, and
`docs/adr/0006-shipping-the-native-extension.md` has why it is worth
paying.

The pure-Python implementations are kept and still run: under
`PYGUARA_NO_NATIVE=1`, under `native_acceleration = "off"`, on a platform
with no wheel, and in a checkout with nothing built yet.

```bash
uv sync                              # maturin is the backend; this builds it
make native                          # rebuild in place after editing Rust
PYGUARA_NO_NATIVE=1 uv run pytest    # force the Python path
```

**`PYGUARA_NO_NATIVE=1` does not reach audio.** `NativeAudioSystem` is a
*backend* with no Python counterpart, chosen by `AudioConfig.backend`, and is not
one of the stores above: to rule it out, set `PYGUARA_AUDIO_BACKEND=pygame`. See
`docs/systems/audio.md` and ADR 0004, Decision 4.

`make native` is `maturin develop --release`, and the `--release` matters:
`maturin develop` alone produces a *debug* build, which is slower than the
Python it replaces. A bare `cargo build --release` still works and is
still found, but it is the second place looked at -- an installed library
wins, so after `uv sync` a plain `cargo build` leaves the new code
silently unused.

**The store is one engine-wide choice**, not a per-subsystem one:
`PerformanceConfig.native_acceleration` is `off`, `auto` (the default) or
`required`, resolved once at bootstrap by `pyguara.native.configure()` and
reported in the boot log. `required` fails at *startup* without the
extension, which is what a game depending on native performance should
ship. `pyguara.native.describe()` says which store is in force and where
it came from, `pyguara.native.status()` returns the same facts as fields,
and Studio's `project_overview` reports it -- so an agent or an author
who attached to a running session, and never saw the boot line, can still
find out.

It is engine-wide because a store picked silently from whether a `.so`
happens to be on disk means the same game, with the same code and seed,
behaves differently on a machine that built the extension and one that
did not -- invisible for a particle, gameplay for a flock. See
`docs/adr/0004-the-native-boundary.md`, Decision 4.

`accelerate=True`/`False` on a pool or a service still overrides it,
because the parity tests have to construct both stores side by side. That
is what it is for, not a second place to configure the engine.

Written outside the generated block above on purpose: `pyguara studio
instructions` rewrites what is inside it, and an earlier version of this
section was placed there and silently deleted on the next regeneration.

The price of keeping two implementations is that they must agree, which is
paid by `tests/test_native_particle_parity.py`,
`tests/test_native_spark_parity.py`,
`tests/test_native_flow_field_parity.py`,
`tests/test_native_flocking_parity.py` and
`tests/test_native_spatial_hash_parity.py` running the same operations
against both, plus real-GPU pixel comparisons in
`tests/integration/test_wgpu_pixels.py`. All of those **skip** when the
extension is not built, so a contributor without Rust sees a green suite
and has tested none of the accelerator -- build it before trusting a pass
on anything touching particles, sparks, pathfinding, flocking or spatial
queries.

**Adding a native store to an existing class changes the meaning of every
test that constructs it**, which `SpatialHash` demonstrated the hard way:
the moment it defaulted to `auto`, the Python reference inside
`tests/test_native_flocking_parity.py` became native and that suite's
first tier compared the native grid with itself -- it passed all 69 tests
with the grid's distance test deliberately broken. So a reference, a
complexity guard and a subsystem's own `accelerate=False` path must each
pin the Python store *explicitly*, and a unit suite for a two-store class
should be parametrised over both. See ADR 0004 Decision 7.

**How closely they have to agree depends on what the subsystem is for.**
The pools compare with a tolerance, because they hold f32 where Python
holds f64 and a spark half a pixel away is a spark. The flow field is
**bit-exact** and tested with `==` on every cell, because a field steers
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

See `docs/adr/0003-native-core-spike.md` for why this is an accelerator
rather than a rewrite, and `0006-shipping-the-native-extension.md` for why
it ships in the wheel and what that costs.
