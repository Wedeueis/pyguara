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

**Defensible scale: roughly 1000 fully-simulated boids at 60 Hz, or 2000 with
steering at 20 Hz** (`groups=3`). Before the optimisation pass it was about 300.

**3000 fully-simulated boids at 60 Hz is not reachable**, and staggering does
not get there — at `groups=4` it is still 21 ms. Staggering does not scale as
1/N either, because a share of every tick cannot be staggered: the spatial hash
is rebuilt, components are resolved, and every agent integrates, whatever group
it is in. That floor is what stops `groups=8` being interesting.

Clumped density costs more, and is not a pathological case — it is a horde
converging on a player. At 3000 agents: 161.9 ms clumped against 53.5 uniform,
down from 664.1 and 177.6 respectively.

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
