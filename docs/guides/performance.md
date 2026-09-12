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

| Sprites | End-to-end | …of which: instance pack (row loop) | Pack share |
| ---: | ---: | ---: | ---: |
| 1000 | 1.53 | 0.65 | 42% |
| 5000 | 5.09 | 3.44 | 68% |
| 20000 | 16.00 | 12.98 | **81%** |

**The Python pack loop dominates, and its share grows with count.** Filling the
instance array one row at a time accounts for four fifths of an entire
20,000-sprite draw; the GPU work and the upload together are the remaining
fifth. Anything done to speed this path up should be aimed at the pack.

Packing the same data with numpy column writes instead of a row loop: 0.40 ms at
1000, 2.00 ms at 5000, **8.20 ms at 20000** — about 1.6× faster, and the gap
widens with count.

### Instance layout width

Packing and uploading 20000 instances, 7 floats each versus 11:

| Floats per instance | Time |
| ---: | ---: |
| 7 (today) | 9.75 ms |
| 11 (with a per-instance tint) | 9.46 ms |

**Indistinguishable from noise** — across runs the two swap places, so the real
difference is under a few percent. Widening the sprite instance layout to carry
a per-instance tint therefore costs effectively nothing, which makes carrying it
unconditionally cheaper than maintaining a second shader program for untinted
batches. Broadcasting a constant into four extra columns is free once the pack
is vectorised; the bytes uploaded are 320 KB per frame at 20,000 sprites.

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
