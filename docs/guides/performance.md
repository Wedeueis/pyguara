# Measured limits

Every number on this page came out of `tests/performance/`. Nothing here is
estimated, and nothing here is a target — these are the figures the engine
actually produced on a real machine, reproduced with:

```bash
make benchmark          # the full sweep; prints every table below
make test-performance   # the cheap guards only
```

If you are about to claim the engine can handle *N* of something, this is the
page to check first, and the page to update afterwards.

## How to read these numbers

**A 60 Hz frame is 16.7 ms.** That is the whole budget — every system, plus
rendering, plus whatever the game itself does. A subsystem that takes 16 ms is
not "fast enough", it has eaten the frame.

**CPU-side numbers are portable; GPU-side numbers are not.** The sorting,
batching, flocking, spatial and pooling figures are pure Python and will scale
with a machine's single-core speed in a predictable way. The GL figures depend
entirely on the driver underneath — a real NVIDIA driver, Mesa over D3D12 (what
was used here), and llvmpipe on a CI runner differ by orders of magnitude. When
quoting an engine limit, quote a CPU-side number.

**Measured on:** WSL2 · Mesa 23.2.1 over D3D12 · NVIDIA RTX 3050 · CPython 3.12
· 2026-09-12. Figures are the *minimum* of several rounds, not the mean: a slow
round means something else on the machine got the CPU, and averaging that in
measures the neighbours instead of the code.

---

## Crowd simulation

### `FlockingSystem.update` — milliseconds per tick

Steering can be spread across ticks with `FlockingSystem(..., groups=N)`: one
group re-decides its heading each tick while **every** agent still integrates
its position, so motion stays smooth and only the decision rate drops to 60/N Hz.

| Agents | g=1 | g=2 | g=3 | g=4 | g=1, before |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1000 | 16.0 | 9.6 | 7.4 | 6.2 | 53.7 |
| 1500 | 24.9 | 14.8 | 11.4 | 9.7 | — |
| 2000 | 34.3 | 20.5 | 15.6 | 13.2 | 112.3 |
| 2500 | 44.7 | 26.2 | 19.8 | 17.7 | — |
| 3000 | 53.5 | 32.0 | 24.9 | 21.1 | 177.6 |

**Defensible scale in Python: roughly 1000 fully-simulated boids at 60 Hz, or
2000 with steering at 20 Hz** (`groups=3`). Before the optimisation pass it was
about 300.

**3000 fully-simulated boids at 60 Hz is not reachable in Python**, and
staggering does not get there — at `groups=4` it is still 21 ms. Staggering does
not scale as 1/N either, because a share of every tick cannot be staggered: the
spatial hash is rebuilt, components are resolved, and every agent integrates,
whatever group it is in. That floor is what stops `groups=8` being interesting.

Clumped density costs more, and is not a pathological case — it is a horde
converging on a player. At 3000 agents: 161.9 ms clumped against 53.5 uniform,
down from 664.1 and 177.6 respectively.

#### Ported. 16 ms to 1.9 ms

With the extension built, the same ticks:

| Agents | g=1 | g=2 | g=3 | g=4 | Python g=1 | |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1000 | **1.86** | 1.68 | 1.63 | 1.61 | 16.0 | 8.6x |
| 1500 | **2.79** | 2.54 | 2.60 | 2.54 | 24.9 | 8.9x |
| 2000 | **3.94** | 3.57 | 3.44 | 3.36 | 34.3 | 8.7x |
| 2500 | **5.03** | 4.42 | 4.34 | 4.31 | 44.7 | 8.9x |
| 3000 | **6.21** | 5.41 | 5.34 | 5.36 | 53.5 | 8.6x |

**Defensible scale natively: 3000 fully-simulated boids at 60 Hz**, at 37% of a
frame, with no staggering at all. 1000 agents go from 96% of a frame to 11%.

Three things in that table are worth more than the headline.

**Staggering has become nearly pointless.** 1000 agents at `groups=4` saves
0.25 ms against `groups=1`, where in Python it saved 9.8 ms. What `groups` skips
is the steering decision, and steering is no longer what a tick costs — the
crossing and the component resolution are, and every agent pays those whatever
group it is in. The floor that stopped `groups=8` being interesting in Python is
now most of the tick. A game on the native store should measure before reaching
for it, and probably not reach for it.

**Density is where the port pays most**, which is the case it was built for:

| 3000 agents | Python | native | |
| --- | ---: | ---: | ---: |
| uniform | 52.8 | 6.32 | 8.4x |
| clumped | 156.9 | 8.28 | **19.0x** |

Clumping costs Python 3.0x and the native store 1.3x. What density multiplies is
the per-neighbour arithmetic, which is exactly what moved; the crossing is
unchanged because the same number of agents cross either way. So the speedup is
8x in the easy case and 19x in the hard one, and the hard one is a horde
converging on the player.

**The remaining cost is almost all boundary.** At 1000 agents the 1.86 ms splits
as 0.31 ms resolving entities and components (17%, paid by both stores), 0.29 ms
packing 15 floats per agent (16%), ~0.54 ms of native solve (29%), and the rest
write-back — 2000 `Vector2` constructions, which is why `_tick_natively` builds
them through `tuple.__new__` rather than `Vector2(x, y)`: 1.8x cheaper for an
identical object, worth 15% of the tick. Unlike the flow field, none of this can
be kept native between ticks, because a flock is not opaque — every agent is an
ECS entity whose position other systems read. That is the whole reason this
port prices at 9x where the field prices at 57x.

Two things matter more than the headline number.

First, a flocking tick is O(n·k) — n agents each visiting k neighbours — so
**density is an independent variable**. The uniform figures hold agents-per-cell
constant as n grows, isolating the n term; the clumped ones pack everything into
a fixed area, so k grows with n too.

Second, the cost was never the spatial hash. Rebuilding it for 3000 agents takes
3.1 ms, and the full per-tick rebuild `FlockingSystem` does is defended in its
docstring on correctness grounds — an incrementally maintained hash can
accumulate a stale entry for a despawned entity. The measurement supports
keeping it. Where the time actually went, in the order the optimisation pass
found it: `Vector2` arithmetic in the inner loop (the largest, and the one
nobody predicts), then per-neighbour entity and component re-lookup, then
iterating the neighbour list once per steering behaviour.

### `SpatialHash`

| Keys | Rebuild (ms) | Query (µs/query) | Query, before |
| ---: | ---: | ---: | ---: |
| 1000 | 1.08 | 5.0 | 11.0 |
| 3000 | 3.08 | 5.2 | 11.2 |
| 10000 | 11.73 | 5.1 | 10.8 |

Rebuild is linear. Query cost is **flat in the number of keys held**, which is
the property that makes it an index rather than a list — a query's cost depends
on how many candidates it returns, not on how much is stored. The constant
halved when `_candidates` stopped allocating a set per query to deduplicate keys
that cannot be duplicated: `insert` discards a key from its old cell before
adding it to the new one, so a key lives in exactly one cell.

#### Ported. 7.5 ms to 0.44 ms

A tick of the index is what `SpatialIndexSystem` and its consumers do
together: re-insert every tracked key, then query once per key. At 1000
keys that is 7.45 ms in Python — 45% of a frame for the *index alone*,
before a single consumer has done anything with the results.

| 1000 keys, per tick | Python | native | |
| --- | ---: | ---: | ---: |
| insert all | 0.480 | 0.099 | 4.9x |
| query all (k=17) | 6.973 | 0.340 | **20.5x** |
| both | 7.453 | 0.439 | **17.0x** |

**The ratio barely moves with density**, which is the whole reason this
port exists in the shape it does. ADR 0004 had ruled out a Python-facing
native index because each query hands back a Python list whose length
grows with the candidate count. It does — and so does the Python
broad-phase it replaces, about twenty times more expensively per
candidate, so the two scale together:

| | k | Python | native | |
| --- | ---: | ---: | ---: | ---: |
| radius 64 | 17 | 6.97 | 0.34 | 20.5x |
| radius 128 | 32 | 11.75 | 0.53 | 22.3x |
| every key coincident | 1000 | 210.5 | 13.2 | 16.0x |

#### What a consumer gets, which is much less

Nothing below changed a line of its own code; the index under it changed.
This is Amdahl, and it is the most useful number in this section:

| consumer | Python | native index | | of a frame |
| --- | ---: | ---: | ---: | --- |
| `TopDownSystem` separation, 1000 clumped | 17.30 | 9.25 | 1.87x | 104% → 56% |
| `TopDownSystem` separation, 1000 uniform | 2.82 | 0.83 | 3.42x | 17% → 5% |
| `TopDownSystem` separation, 200 actors | 0.66 | 0.15 | 4.30x | 4.0% → 0.9% |
| `FlockingSystem`, Python steering, 1000 | 16.37 | 9.8 | 1.67x | 98% → 59% |
| `SpatialIndexSystem.update`, 10000 tracked | 13.17 | 9.73 | 1.35x | 79% → 58% |
| `SpatialIndexSystem.update`, 2000 tracked | 1.79 | 1.15 | 1.55x | 11% → 7% |
| `MagnetSystem.update`, 100 magnets | 1.69 | 1.19 | 1.43x | 10% → 7% |
| `ProjectileSystem.update`, 1000 live | 2.81 | 2.13 | 1.32x | 17% → 13% |

A 17x primitive bought 1.3-4.3x, because the broad-phase was never most
of anyone's tick: what follows a query is an ECS lookup, a component
fetch and arithmetic, all of it Python and all of it untouched. The row
that justifies the port is `TopDownSystem` at crowd scale — a dropped
frame becoming half a frame — and the row that does not is projectiles,
which stay declined.

The flocking row is a measurement rather than a configuration: the Python
steering path now pins its own index to `accelerate=False`, because a
"Python path" that indexes natively is not one, and because a parity
suite's Python reference has to be Python all the way down.

#### The regime where Python wins

The native grid rebuilds on the first query after any write. Every
consumer syncs the whole index and then sweeps it, so one rebuild serves
`n` queries and the rebuild is free. A caller that **alternates** insert
and query pays one rebuild per query — O(n²) against Python's O(n):

| keys | Python | native | |
| ---: | ---: | ---: | ---: |
| 250 | 1.29 | 0.69 | 1.9x faster |
| 1000 | 4.81 | 9.21 | 0.52x |
| 4000 | 18.51 | 139.77 | **0.13x** |

Nothing in the engine does this, and `accelerate=False` is the answer for
a game that does. It is the first native store that is *worse* than
Python at something, so
`test_alternating_writes_and_queries_stays_within_its_known_penalty`
bounds it rather than leaving it to be discovered.

### `EntityPool` — draining a full pool, milliseconds

| Pool size | Newest-first | Oldest-first | Newest-first, before the fix |
| ---: | ---: | ---: | ---: |
| 500 | 0.10 | 0.10 | 2.26 |
| 1000 | 0.19 | 0.19 | 8.67 |
| 2000 | 0.39 | 0.40 | 33.62 |
| 3000 | 0.59 | 0.61 | 74.18 |

Linear, and **independent of release order** — the two columns agree to within
noise at every size.

They did not always. When the active set was a list, `release()` did an `in`
scan followed by a `list.remove()`, both linear from index 0, so cost depended
entirely on the order entities came back. Oldest-first found its match at index
0 and removed it with a C-level memmove — fast, and an accident. Newest-first
scanned the whole list every time, which made draining a pool quadratic in its
size: 74 ms at 3000, four and a half frames, from a structure whose entire
purpose is high-frequency spawn and despawn.

The active set is now a dict keyed on entity id. At 3000 entities that is **55×
faster** in the worst order, and faster than the old *best* order too, since a
dict insert beats a list memmove. `test_pool_churn_is_linear` measures
newest-first specifically, because it was the order that fell over.

### Filtering disabled entities out of a query

`get_entities_with`, `get_entities_with_cached`, `get_components` and
`get_components_with_entity` all have to drop entities parked by
`set_entity_enabled(False)`. The obvious advice -- "stop testing membership per
entity in Python, do one set difference in C" -- was measured and **is wrong
here**. 10,000 entities, each with `Transform` and `Tag`, min of 5 rounds,
milliseconds:

| query | disabled | per-entity test | `ids - disabled` | `filterfalse` |
| --- | --- | --- | --- | --- |
| `get_entities_with(Transform)` | 0 | 1.37 | 1.21 | **1.19** |
| `get_entities_with(Transform, Tag)` | 0 | 2.06 | 1.87 | **1.69** |
| `get_components(Transform)` | 0 | 9.03 | 8.37 | **6.89** |
| `get_entities_with(Transform)` | 1,000 | **1.48** | 1.42 | 1.57–1.76 |
| `get_entities_with(Transform, Tag)` | 1,000 | **2.05** | 2.41 | 2.04 |
| `get_components(Transform)` | 1,000 | 7.97 | 7.34 | **7.36** |
| `get_entities_with(Transform)` | 5,000 | 1.09 | 1.10 | **1.00** |
| `get_entities_with(Transform, Tag)` | 5,000 | **1.49** | 1.96 | 1.51 |
| `get_components(Transform)` | 5,000 | 4.17 | 3.73 | **3.19** |

The eager difference loses badly exactly where the filter does any work: with
5,000 disabled, `get_entities_with(Transform, Tag)` went from 1.49 ms to
1.96 ms, **32% slower**. Building a new 5,000-entry set costs more than 10,000
membership tests that allocate nothing — and a multi-type query has already
paid to build its intersection, so this is a second full set per call.

`itertools.filterfalse` over a bound `set.__contains__` wins instead: the
per-item work runs in C without materialising anything. Two further reasons it
is the right shape, beyond the numbers:

- It is **lazy, like the code it replaced**. The old loop consulted the live
  `_disabled` set as it went, so disabling an entity mid-iteration took effect;
  an eager difference snapshots instead. Same semantics, not just same results.
- It cannot corrupt the index. For a single-type query `_matching_entity_ids`
  returns the **live component index**, so `ids -= disabled` would delete those
  entities from the index permanently — they would stop matching every later
  query, re-enabled or not. `TestFilteringDisabledLeavesTheIndexIntact` in
  `tests/test_ecs_dormancy.py` fails if anyone writes it that way.

Most of the remaining win is simply **not filtering when nothing is disabled**,
which is the common case for any game that does not pool: the old code paid a
membership test per entity regardless. Where a moderate number are disabled the
three strategies are within noise of each other, and that cell moved around by
±20% between rounds — read the 0-disabled column as the real result.

---

## Components

### The `entity` slot, and why it is initialised per class

`BaseComponent.__slots__` declares `entity`, but almost every component is a
`@dataclass` whose generated `__init__` never chains to the base -- so the slot
stays unset and reading `entity` before `on_attach` raises `AttributeError`.
Around 35 modules work around this with a `__post_init__` that calls the base
`__init__` by name. Four components had simply forgotten to.

Fixing it once on the base class looks obviously right and is not. Both central
options were implemented and measured, against the same tree, min of 7 rounds:

**Construction, nanoseconds**

| | baseline | `__new__` on base | `__getattr__` on base |
| --- | --- | --- | --- |
| `Bare()` (no fields) | 196 | 383 | 195 |
| `Transform()` | 1,116 | 1,357 | 1,190 |
| `Transform(position=…)` | 1,254 | 1,619 | 1,304 |
| `Health()` (dataclass) | 322 | 408 | 212 |

**Attribute reads, nanoseconds** — what a system does thousands of times a frame

| | baseline | `__getattr__` on base |
| --- | --- | --- |
| `tag.name` | 32.2 | 41.0 (+27%) |
| `transform.entity` | 32.3 | 41.2 (+28%) |
| `transform.position` (property) | 52.7 | 100.2 (**+90%**) |
| `transform.world_position` (cached) | 84.9 | 131.1 (+54%) |

`__new__` costs ~190 ns on every component ever constructed, and deleting the 35
redundant `__post_init__` calls only buys ~95 ns of that back.

`__getattr__` is free to construct -- and that is the trap. Defining it anywhere
in a class's MRO takes CPython off the `PyObject_GenericGetAttr` fast path for
every instance of that class, so *successful* attribute access gets slower
whether or not the hook ever fires. A property read nearly doubles. Components
are the most-read objects in the engine, so this trades a one-time cost at
construction for a permanent tax on every frame: much the worse deal, and
invisible unless you measure reads rather than construction.

So the slot is still initialised per class, and the guard against forgetting is
`tests/test_component_entity_slot.py`, which finds every `BaseComponent`
subclass by reflection and fails naming the class and the line to add. A test
costs nothing at runtime.

---

## Character movement

### The swept `CharacterMover` probe -- milliseconds per fixed tick

`CharacterMover` moves an entity one **whole pixel** at a time along each
axis and tests every step. That is deliberate: it is the guarantee that stops
a fast mover tunnelling through a wall, and the module docstring says so. Each
step calls `overlap_box`, and `PymunkEngine._probe_shape` answers it by
constructing a fresh kinematic `pymunk.Body` **and** a fresh `pymunk.Poly` on
the CFFI heap -- it is a `@staticmethod`, so there is nowhere to cache them.

The cost therefore grows with how **fast** things move, not how many there
are. Characters running at 240 px/s on a floor, 60 ticks per measurement:

| Movers | ms / tick | Probes / tick | CFFI objects / tick | CFFI objects / simulated second |
| --- | --- | --- | --- | --- |
| 1 | 0.12 | 4.0 | 8.0 | 478 |
| 10 | 1.12 | 39.8 | 79.7 | 4,780 |
| 50 | **6.07** | 209.4 | 418.7 | **25,124** |

Fifty movers spend **over a third of a 16.7 ms frame** on movement alone,
before anything is drawn. The allocation figures are counted rather than
sampled: `_probe_shape` allocates exactly two CFFI objects per call, so the
count is the probe count doubled.

For reference, the audit that raised this estimated "18,000+ CFFI
allocations/second" without saying under what conditions. The shape of the
claim is right; the number lands between 10 and 50 movers at this speed, and
is now pinned to a scenario rather than asserted.

**Measured and deliberately not fixed.** RFC-0003's Marco 4 moves the whole
sweep into Rust against static AABBs, removing the CFFI path rather than
optimising it -- so a Python-side fix (a cached probe body, or routing
`overlap_box` through the `space.bb_query` that `region_query` already uses)
would be thrown away. These numbers are that milestone's acceptance
criterion. If RFC-0003 is declined, they are the justification for doing the
Python fix after all.

What must *not* change in either language: every pixel is still tested.
Bisecting the walk would be faster and would reintroduce tunnelling.

---

## Object pools

### The native particle pool -- milliseconds per frame

`ParticleSystem` can be backed by a native structure-of-arrays pool
(`cargo build --release`; see `pyguara/native.py`). The
Python pool is kept and used whenever the extension is absent, so this is an
accelerator rather than a requirement.

Both paths, the same seeded burst, min of 5 rounds:

| Live | Path | `update` | `render` | Frame | |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1000 | Python | 2.132 | 0.442 | 2.574 | |
| 1000 | **native** | 0.006 | 0.119 | **0.126** | **20.5x** |
| 4000 | Python | 6.517 | 1.326 | 7.843 | |
| 4000 | **native** | 0.025 | 0.511 | **0.537** | **14.6x** |

The arithmetic alone is ~268x (2.13 ms -> 0.006 ms), but `update` is only
84% of the frame, so porting it by itself would have capped out near 6x.
Packing for render natively -- the world-to-screen transform, the colour
lerp and the per-texture grouping -- is what turns that into 15-20x.

**What is left is the Python lists.** Inside the native path, `render` is now
94% of the frame (0.119 ms of 0.126 ms), and almost all of that is building
`list[tuple[float, float]]` for `RenderBatch`. Handing over a buffer instead
needs the renderer to accept one, which is RFC-0003's Marco 2. That is still
the next increment there, and this table is its baseline.

**The table above is the conservative case.** It emits an untinted burst. A
burst with a colour animation -- which fire, smoke and every fading effect
sets -- is far worse in Python and no worse natively, because
`_particle_color` builds two `Color` objects and lerps them per particle
where the native pool lerps four bytes:

| Live | Burst | Python frame | native frame | |
| ---: | --- | ---: | ---: | ---: |
| 1000 | plain | 1.941 | 0.105 | 18.5x |
| 1000 | **fading** | 7.643 | 0.132 | **57.8x** |
| 4000 | plain | 8.335 | 0.484 | 17.2x |
| 4000 | **fading** | 31.260 | 0.568 | **55.0x** |

Read the other way, that is a finding about the *Python* path: 1000 fading
particles spend 6.0 ms of a 7.6 ms frame on colour, and lerping the four
channels as integers instead of through `Color` would reclaim most of it.
Deliberately not done -- see "Deliberately not doing" in the remediation
plan -- but it is the cheapest unclaimed win left in `particles.py`.


### The native spark pool -- milliseconds per frame

`Sparks` can be backed by the same way (`accelerate=`, `PYGUARA_NO_NATIVE=1`),
and the shape of its win is different enough to be worth its own table.

A spark is one primitive, so the Python pool makes one `draw_circle` or
`draw_line` call per live spark. That makes **render the frame**, where for
particles it was the arithmetic:

| | `update` | `render` | render's share |
| --- | ---: | ---: | ---: |
| 1000 particles, plain | 1.574 | 0.367 | 19% |
| 1000 sparks, dots | 2.063 | 2.759 | 57% |
| 1000 sparks, streaks | 2.009 | 5.360 | 73% |

So porting only `update` would have capped sparks at 1.4-1.8x however fast
the arithmetic got. The render half needs the primitives handed over in one
call, which is what `ShapeBatch` and `ShapeBatchRenderer` exist for -- and
measuring the alternatives is what chose that shape:

| Render candidate | 1000 dots | 1000 streaks | frame |
| --- | ---: | ---: | ---: |
| Python, per primitive | 2.525 | 5.165 | — |
| native rows + `ShapeBatch` | **0.329** | **0.349** | **13-20x** |
| native params + draw calls | 2.318 | 3.096 | 1.9-2.3x |
| native params + NumPy pack | 1.288 | 1.217 | 3.4-5.8x |

Packing the instance rows natively wins by 4-10x over handing back draw-call
parameters, because anything that then walks the sparks in Python gives the
saving straight back. That is why `ShapeBatch.instances` carries packed rows
in the layout `graphics/types.py` documents rather than semantic arrays.

End to end, both stores, min of 5 rounds:

| Live | Path | `update` | `render` | Frame | |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1000 dots | Python | 2.063 | 2.759 | 4.822 | |
| 1000 dots | **native** | 0.003 | 0.287 | **0.290** | **16.6x** |
| 1000 streaks | Python | 2.009 | 5.360 | 7.368 | |
| 1000 streaks | **native** | 0.003 | 0.299 | **0.302** | **24.4x** |
| 4000 dots | Python | 8.077 | 11.012 | 19.089 | |
| 4000 dots | **native** | 0.011 | 1.161 | **1.172** | **16.3x** |
| 4000 streaks | Python | 8.085 | 21.937 | 30.021 | |
| 4000 streaks | **native** | 0.011 | 1.269 | **1.280** | **23.5x** |

A streak costs the Python pool twice what a dot does and costs the native
pool the same, which is the clearest statement of what moved: the geometry a
capsule needs is arithmetic, and arithmetic is no longer the frame.

**Only the ModernGL world renderer takes the batch.** Any other renderer gets
one call per spark, as before, keeping the native arithmetic and about 1.9x.
That is deliberate: a software backend would be looping internally anyway, so
claiming the capability would buy nothing and hide that fact.

Reproduce both tables with `uv run python tools/bench_native_pool.py`.


### Pricing a native port before writing it

`docs/adr/0004-the-native-boundary.md` turns the two tables above into a
test a candidate can be put through in advance:

    ceiling = T_py / (T_cross + T_pinned)

where `T_cross` is what getting data in and results out costs per tick,
measured in Python because that is where it is paid, and `T_pinned` is work
that cannot move at all -- the ECS, the event dispatcher, resource handles.

`uv run python tools/price_native_boundary.py` computes it for every
candidate:

| Candidate | `T_py` | `T_cross` | `T_pinned` | ceiling | |
| --- | ---: | ---: | ---: | ---: | --- |
| flow field, 96x96 | 83.247 | 1.479 | — | **56.3x** | landed |
| particles, 1000 | 1.942 | 0.104 | — | 18.7x | landed |
| sparks, 1000 streaks | 5.865 | 0.339 | — | 17.3x | landed |
| flocking, 1000 agents | 16.555 | 1.849 | — | **9.0x** | landed, 9.0x (priced 15.4x) |
| sparks, 1000 dots | 4.077 | 0.321 | — | 12.7x | landed |
| projectiles, 1000 | 3.041 | 0.339 | 1.143 | **2.1x** | declined |

As a share of a 16.7 ms frame, `T_py` alone is 499% for a 96x96 flow-field
recompute, 99% for 1000 flocking agents, 35% for 1000 streaked sparks and
18% for 1000 projectiles.

**The two landed gameplay rows miss their prices in opposite directions**, and
the pair is more instructive than either. The flow field priced at 161x and
achieved 57x, because `T_cross` models the handoff and not the native work
behind it. Flocking priced at 15.4x and achieved 9.0x with the opposite cause:
its native solve is only 0.5 ms of a 1.85 ms tick, and what was underestimated
is the crossing itself — `T_cross` was measured as the Python loops that pack
and unpack, while a real crossing also pays PyO3's conversion of a
15,000-float list, the tuples it allocates coming back, and the per-tick ECS
prologue that both stores share. Both errors are optimistic, so a price is a
threshold test and the achieved figure should be expected lower.

**What the flow-field row looked like before it was built, and why the
difference matters.** Priced in advance its `T_cross` was the wall-mask
upload alone -- 0.522 ms against 84.139 ms -- for a ceiling of **161x**.
Built, it achieves **56x**. Nothing about the prediction was wrong: the
upload really is almost free, and the formula models the *boundary*, not
the native work behind it. The native sweep costs 1.3 ms, and for the
first time among these candidates that, rather than the handoff, is the
limit. The pools' predictions landed close because their native work was
genuinely negligible beside their handoff; that is a property of those
candidates, not of the arithmetic. A ceiling of 161x means "far above the
5x threshold", which is the decision it was computed for, and it does not
mean "expect 161x".


### Flow fields -- the number nobody had measured

`dijkstra_map` + `flow_field` over a `GridGraph`, 12% walls, 8-directional:

| Grid | Cells | `dijkstra_map` | `flow_field` | recompute | share of a frame |
| --- | ---: | ---: | ---: | ---: | ---: |
| 30x20 | 600 | 2.911 | 2.114 | **5.024** | 30% |
| 48x48 | 2304 | 11.716 | 8.548 | 20.264 | 122% |
| 96x96 | 9216 | 48.534 | 35.225 | **83.759** | 505% |
| 160x160 | 25600 | 139.231 | 100.161 | 239.392 | 1436% |

A `vector_at` query against a computed field, by contrast, is **0.6 us**.
So the field is cheap to *use* and, above about 2000 cells, cannot be
recomputed at interactive rates at all.

Two separate causes, and they want separate fixes:

- **The interface.** `dijkstra_map(graph, goals)` takes a `Graph`
  **protocol** and calls `get_neighbors` and `cost` per node expansion. For
  8-directional movement with corner-cutting refused, one expansion is
  roughly thirty interpreter operations. This is also why a native port
  must take the grid rather than the graph -- see ADR 0004, Decision 2.
- **The cadence.** `games/vinagre_matilha` recomputed **every fixed tick**,
  60 times a second, on the 30x20 row above. Its goal is the jaguar's cell,
  which at 158 px/s across 32 px cells changes once every 12 ticks at a
  sprint -- so at least eleven of twelve recomputes reproduced the field
  that was already there. **Fixed**, in the engine rather than the demo:

  | Grid | cold recompute | unchanged re-ask | |
  | --- | ---: | ---: | ---: |
  | 30x20 | 5.000 ms (30% of a frame) | **0.0016 ms** (0.01%) | 3114x |
  | 96x96 | 85.859 ms (515%) | **0.0336 ms** (0.20%) | 2557x |

  `FlowFieldService.recompute()` now skips work that would reproduce the
  field it holds, keyed on the goals **and a fingerprint of the graph** --
  by content, because a `GridGraph` is mutated at runtime and a key over
  the goals alone would steer through a wall that had been opened.
  Fingerprinting the walls and weights costs 0.03-0.06% of a recompute
  (2.7 us against 5.0 ms at 30x20; 77 us against 241 ms at 160x160), so
  soundness is free and there is no invalidation contract to forget.

**What that does to the native port is worth stating, because it is not
"never mind".** The guard removes the *redundant* recomputes; a genuine one
still costs what the table above says. On a 30x20 grid that is a 5 ms spike
every fifth of a second, survivable. On 96x96 it is a single **85 ms
stall** -- five frames dropped the moment a goal moves. So the port's
justification moves from throughput to **worst-case latency**: it turns a
five-frame hitch into a sub-millisecond one. ADR 0004's Decision 6 says to
settle the algorithm before the boundary, and this is what that looks like
in practice -- the guard did not remove the case for porting, it changed
what the porting is for.


#### Ported. 85 ms to 1.6 ms

`FlowFieldService` is backed by the native sweep when the extension is
built, measured end to end -- a fresh service per round, so the wall-mask
upload is paid rather than skipped:

| Grid | Cells | Python | native | | share of a frame |
| --- | ---: | ---: | ---: | ---: | ---: |
| 30x30 | 900 | 7.519 | **0.162** | 46x | 45% -> 1.0% |
| 64x64 | 4096 | 36.449 | **0.739** | 49x | 219% -> 4.4% |
| 96x96 | 9216 | 85.586 | **1.629** | 53x | 513% -> 9.8% |

The five-frame hitch is a tenth of a frame. Note what that does *not*
change: the guard above is still what keeps a per-tick caller off the
recompute path at all, because 1.6 ms sixty times a second is still 10% of
every frame for a field that did not change.

**The field never comes back to Python**, and that is the whole reason the
margin is this size. Nothing outside `FlowFieldService` reads an individual
cell -- `vector_at` and `cost_at` are the only ways in -- so the cost map
and the descent field both stay native and there is no download. ADR 0004
calls this opacity, and it is the difference between this row and
flocking's, which has to hand every agent's position back every tick --
measured, 57x against 9x.

`vector_at` got cheaper too, by **5.7x** (3.27 us -> 0.575 us), and the
boundary had to be picked for it to. A crossing that returned the descent
neighbour would have made the method *slower*: the lookup was never the
cost. Four `Vector2` operations after it are 3.1 us of the 3.27, against
0.044 us for a crossing. So the direction is computed natively and the
whole method is one crossing.

**Bit-exact, not close.** The pools compare with a tolerance because they
hold f32 and a spark half a pixel off is a spark. A flow field steers
gameplay, so `tests/test_native_flow_field_parity.py` asserts equality on
every cell of every grid it builds. Three things make that reachable: f64
on both sides, `GridGraph.get_neighbors`' order replicated exactly
(the descent pass takes the first strictly-cheaper neighbour, so the order
*is* the tie-break), and the fact that a Dijkstra cost map is
order-independent given non-negative weights.

Reproduce with `uv run python tools/price_native_boundary.py`, or
`uv run pytest tests/performance/test_perf_pathfinding.py -m slow` for the
table.

**Two things to know before trusting a re-measurement.** Use a real texture
object, not a `MagicMock`: the Python path hashes and compares the texture
once per particle, which is cheap for a real object and pathological for a
mock -- it inflated an early version of this table to a fictitious 325x.
And the native pool stores f32 where Python uses f64, so positions drift
sub-pixel over a lifetime; the parity tests bound that rather than ignoring
it.


### `ParticleSystem` / `Sparks` update -- milliseconds per frame

All three self-contained pools -- particles, sparks and projectiles --
pre-allocate their slots and hand them out, so they allocate nothing per
frame. They do walk their **whole capacity** every frame, live slots and dead
alike, and that reads like the thing to fix.

Measured, it is not:

| Pool | Capacity | Live | ms / update | us / slot |
| --- | ---: | ---: | ---: | ---: |
| particles | 1000 | 0 | 0.024 | 0.024 |
| particles | 1000 | 10 | 0.046 | — |
| particles | 1000 | 1000 | 2.196 | 2.196 |
| particles | 4000 | 0 | 0.104 | 0.026 |
| particles | 4000 | 4000 | **9.020** | 2.255 |
| sparks | 1000 | 0 | 0.011 | 0.011 |
| sparks | 1000 | 1000 | 2.849 | 2.849 |
| sparks | 4000 | 4000 | **11.454** | 2.863 |

A dead slot costs one boolean test: **0.024 us**. A live one costs **2.2 us**,
ninety times as much. So an idle 1000-slot pool costs 0.024 ms -- nothing --
and compacting the pool to skip dead slots would buy back exactly that.

**The cost is the per-element arithmetic.** 4000 live particles take 9 ms and
4000 sparks 11.5 ms, over half a 16.7 ms frame for one pool. That is where a
vectorised rewrite would have to win, and it is the opposite of where the
"walks the whole capacity" reading points.

Defensible scale on this machine: roughly **1000 live particles at 60 Hz**
(2.2 ms) alongside everything else a frame does; 4000 is not reachable.

---

## Rendering, CPU side

These are the portable figures, and the surprise is where the time goes.

### `Batcher.create_batches` — milliseconds

| Sprites | One texture | Transformed | Tinted |
| ---: | ---: | ---: | ---: |
| 1000 | 2.25 | 2.23 | 2.50 |
| 5000 | 11.88 | 11.86 | 13.73 |
| 20000 | 49.39 | 48.99 | 53.50 |

**The CPU batcher is the bottleneck at scale, not the GPU.** At 20000 sprites it
costs 53.8 ms — more than three times the entire GL path for the same batch. This
had never been measured: the pre-existing benchmark ran 1000 commands and
asserted nothing about time.

Texture switching, at a fixed 8000 commands: 21.8 ms with one texture, 31.6 ms
with ten, 32.2 ms with fifty. Batch breaks cost about 50%, and almost all of
that is paid going from one texture to a handful.

### `RenderQueue.sort` — milliseconds

| Commands | Time |
| ---: | ---: |
| 2000 | 0.59 |
| 8000 | 2.87 |

Linear and cheap. The per-command lambda and tuple allocation in the sort key
are real, but at 8000 commands they cost under 3 ms, so **no action is
warranted** — recorded here so the question does not get re-opened from first
principles.

### Visibility culling headroom

Sorting and batching 8000 commands of which roughly a tenth are on screen costs
**25.2 ms**. `RenderSystem` has no visibility rejection at all, so all of that
is paid. This is the number a culling change would have to beat; it is recorded
rather than acted on, because for a game where everything is on screen anyway
culling buys nothing, and the trade only pays in a large scrolling world.

---

## Rendering, GL side

Machine-dependent — see the caveat at the top. Recorded because the *split*
between Python and GPU work is itself informative.

### Instanced sprite draw — milliseconds

All on the transform path, so the pack column is genuinely a *component* of
the end-to-end column rather than a figure from a different code path.

| Sprites | End-to-end | …of which: instance pack | Pack share | Pack, as a row loop |
| ---: | ---: | ---: | ---: | ---: |
| 1000 | 1.86 | 0.40 | 21% | 0.85 |
| 5000 | 3.33 | 1.99 | 60% | 4.46 |
| 20000 | 11.62 | 8.07 | **69%** | 17.47 |

**The Python pack still dominates at scale, but it no longer runs a row at a
time.** The last column is the row loop the path used to run, measured at the
same widths for comparison: filling the instance array with numpy column writes
instead is about 2.2× faster at 20000, and that alone took the whole
20,000-sprite draw from roughly 16 ms to 11.6 ms. The pack's *share* fell from
four fifths to a bit over two thirds — it is still where the time is, so
anything further done to this path should still be aimed at it, and the
remaining cost is dominated by turning Python lists of tuples into arrays.

### `draw_text` — milliseconds per frame, 20 strings

`draw_text` rasterises a string with `pygame.font` and uploads it as a GL
texture. It used to release that texture at the end of the call, reasoning that
"a fresh piece of text has nothing to reuse anyway" -- true of a string seen
once, and wrong about what actually calls it. `FloatingText` redraws the same
damage numbers every frame for the life of the entry, and the debug overlays
redraw whole static panels, so the common case was twenty uploads and twenty
frees per frame for pixels identical to the previous frame's.

Real GL, standalone context, min of 5 rounds of 120 frames:

| 20 strings per frame | released per call | cached |
| --- | --- | --- |
| the same 20 strings each frame | 9.98 | **1.03** |
| 20 brand-new strings each frame | **11.10** | 16.44 |

The steady-state case is where the engine actually lives, and it gives back
**9 ms of a 16.7 ms frame**.

The second row is the honest cost, and it is not the bound's fault -- it
measures the same at a limit of 32, 64, 128 and 256. Releasing inside the call
meant the driver freed a block and immediately allocated one the same size, over
and over, which an allocator handles about as well as it handles anything.
Caching decouples the two: a miss allocates a new texture while freeing one from
hundreds of frames ago, and the reuse is gone. So text that never repeats pays
~45% more than it did.

That is accepted rather than solved. Twenty entirely new strings every frame
already cost 11 ms before this change -- two thirds of the frame -- so it was
not a case anything could ship with, and the shape that *is* shipped is the
first row. A string that changes every frame on its own (an FPS counter) is one
miss, not twenty.

Two limitations worth knowing: the cache is bounded by **entry count, not
bytes**, so 256 long strings hold more than 256 short ones; and these textures
are the renderer's own, outside `ResourceManager`, so they do not count towards
its cache budget.

### Instance layout width

Packing and uploading 20000 instances, at each width the layout has had:

| Floats per instance | Time |
| ---: | ---: |
| 7 (position and transform only) | 9.29 ms |
| 11 (with a per-instance tint) | 9.72 ms |
| 15 (with an atlas UV rect) | 9.85 ms |

**A few percent per widening, and the steps are small enough that the 11→15 one
lands inside run-to-run noise about as often as not** — measured across repeats
it ranged from 0.07 ms to 0.44 ms, against a standard deviation of roughly
0.15–0.39 ms. The ordering is consistent; the size of each gap is not.

That is why the GL sprite path carries both the tint and the UV rect
unconditionally, rather than keeping extra shader programs for batches that
want neither — a plain sprite broadcasts white into the four colour columns
and `(0,0)`/`(1,1)` into the four UV columns, which is free once the pack is
vectorised. A uniform would instead force a per-batch state change, which for
the UV rect would defeat the entire purpose: an atlas exists so that sprites
with *different* regions share one draw call.

The bytes uploaded are 1.2 MB per frame at 20,000 sprites.

---

## Resource loading, and the GIL

What decides the shape of asynchronous loading here. `pygame-ce` decodes
images in SDL with the GIL **released**; `json` parses with it **held**. So
"load assets on a worker thread" is right for one and a pessimisation for
the other, and the difference is measured rather than assumed.

Per item, 24 items, 4 worker threads, CPython 3.12.10 (a standard GIL
build -- `Py_GIL_DISABLED` is unset), 12 logical CPUs:

| Operation | Sequential | 4 threads | Speed-up | GIL |
| --- | ---: | ---: | ---: | --- |
| `pygame.image.load`, 2356×1824 jpg | 30.87 ms | 10.58 ms | **2.92×** | released |
| `pygame.image.load`, 1024×1024 png | 6.91 ms | 2.05 ms | **3.37×** | released |
| …plus `convert_alpha` + `tobytes` | 15.12 ms | 7.93 ms | 1.91× | mostly released |
| `json.loads`, ~4k entries | 4.64 ms | 6.51 ms | **0.71×** | held |
| `open().read()`, 2.5 MB, page-cached | 0.17 ms | 0.84 ms | 0.20× | n/a |

Three things follow.

**One image decode can cost more than a frame.** 30.87 ms for a 2356×1824
jpg is nearly two 60 Hz frames, so a scene that loads a dozen textures on
entry stalls for a third of a second. This is the cost asynchronous loading
exists to move.

**Threading pays for image decode and costs for JSON.** 2.9–3.4× against
0.71×: offloading a GIL-holding parse adds contention and returns nothing,
so it finishes *slower* than doing it inline. A loader therefore opts in to
threaded decode rather than getting it by default.

**`asyncio` is the wrong tool for this problem.** It overlaps I/O *waits*,
and there is no wait here worth overlapping -- reading 2.5 MB costs 0.17 ms
while decoding it costs 30.87 ms. The expense is CPU, which an event loop
cannot parallelise on a GIL build; it would also mean running an event loop
inside a synchronous frame loop. A thread pool for the phases that release
the GIL, plus a time-budgeted main-thread pump for everything else, is what
the measurements support.

The last row measures thread-pool overhead, not disk: 2.5 MB out of the
page cache costs 0.17 ms, less than the ~0.7 ms it takes to hand the work
to a pool. Quoted so nobody reads it as "file I/O does not parallelise".

---

## What the test suite guarantees

`tests/performance/` runs in two tiers, and they exist for different reasons.

**Guards** (`-m "performance and not slow"`, ~3 s) assert a **complexity
class**, never a wall-clock time. Each measures the same operation at N and at a
multiple of N in the same process, and asserts the ratio between them. That
cancels machine speed out entirely, which is what makes them safe on a shared CI
runner: a laptop, a loaded container and a CI box all agree that a linear
algorithm costs roughly 4× for 4× the work, even while disagreeing about every
absolute number involved. They catch a change of complexity class — the kind of
regression that is invisible in review and fatal at scale — and deliberately do
not catch a 2× constant-factor slowdown.

**Sweeps** (`-m "performance and slow"`) assert nothing. They are
`pytest-benchmark` runs at sizes too large for CI, and their only job is to
produce the tables above.

Neither tier should ever run under coverage. Tracing every line costs more than
the code being timed and turns every measurement into noise; both `make`
targets pass `--no-cov`.

A machine with no GL context skips the GL tier rather than failing it.
