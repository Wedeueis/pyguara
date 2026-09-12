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

| Agents | Uniform density | Clumped |
| ---: | ---: | ---: |
| 250 | 12.3 | — |
| 500 | 26.0 | 29.9 |
| 1000 | 53.7 | 92.4 |
| 2000 | 112.3 | 323.6 |
| 3000 | 177.6 | 664.1 |

**Defensible scale: roughly 300 boids at 60 Hz**, and fewer if they bunch up.

Two things matter more than the headline number. First, a flocking tick is
O(n·k) — n agents each visiting k neighbours — so **density is an independent
variable**. The "uniform" column holds agents-per-cell constant as n grows,
which isolates the n term; the "clumped" column packs everything into a fixed
area, so k grows with n too. Clumping is not a pathological case, it is a horde
converging on a player.

Second, the cost is *not* the spatial hash. Rebuilding the hash for 3000 agents
takes 3.2 ms of a 177.6 ms tick — under 2%. The full rebuild that
`FlockingSystem` does every tick is defended in its docstring on correctness
grounds, and the measurement supports keeping it. The time goes on
per-neighbour entity and component re-lookup, on iterating the neighbour list
once per steering behaviour, and on `Vector2` allocation.

### `SpatialHash`

| Keys | Rebuild (ms) | Query cost (µs/query) |
| ---: | ---: | ---: |
| 1000 | 1.12 | 11.0 |
| 3000 | 3.20 | 11.2 |
| 10000 | 11.84 | 10.8 |

Rebuild is linear. Query cost is **flat in the number of keys held**, which is
the property that makes it an index rather than a list — a query's cost depends
on how many candidates it returns, not on how much is stored.

### `EntityPool` — draining a full pool, milliseconds

| Pool size | Release newest-first | Release oldest-first |
| ---: | ---: | ---: |
| 500 | 2.26 | 0.10 |
| 1000 | 8.67 | 0.23 |
| 2000 | 33.62 | 0.53 |
| 3000 | 74.18 | 1.05 |

**This is a defect, and the fast column is an accident.** `release()` does an
`in` scan followed by a `list.remove()`, both linear from index 0. Releasing
oldest-first finds its match immediately and the removal is a C-level memmove;
releasing newest-first scans the whole list with Python-level equality every
time. Anything other than strictly-oldest-first order is quadratic.

Draining 3000 pooled entities therefore costs four and a half frames. The pool
exists specifically to support high-frequency spawn and despawn, so this
contradicts its own contract. `tests/performance/test_perf_ecs.py` carries an
expected-failure guard that will flip to passing when it is fixed.

---

## Rendering, CPU side

These are the portable figures, and the surprise is where the time goes.

### `Batcher.create_batches` — milliseconds

| Sprites | One texture | Transformed | Tinted |
| ---: | ---: | ---: | ---: |
| 1000 | 2.43 | 2.21 | 2.50 |
| 5000 | 13.69 | 12.39 | 13.73 |
| 20000 | 53.82 | 49.10 | 53.50 |

**The CPU batcher is the bottleneck at scale, not the GPU.** At 20000 sprites it
costs 53.8 ms — roughly four times the entire GL path for the same batch. This
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

| Sprites | End-to-end | …of which: instance pack (row loop) |
| ---: | ---: | ---: |
| 1000 | 1.59 | 0.63 |
| 5000 | 4.23 | 3.22 |
| 20000 | 13.13 | 13.38 |

**At 20000 sprites the draw is essentially all Python.** The pack loop — filling
a numpy array one row at a time — accounts for the entire end-to-end figure
within measurement noise. The GPU work is negligible.

Packing the same data with numpy column writes instead of a row loop: 0.41 ms at
1000, 1.97 ms at 5000, **8.53 ms at 20000** — about 1.6× faster, and the gap
widens with count.

### Instance layout width

Packing and uploading 20000 instances, 7 floats each versus 11:

| Floats per instance | Time |
| ---: | ---: |
| 7 (today) | 10.11 ms |
| 11 (with a per-instance tint) | 10.35 ms |

**A 2.2% difference.** Widening the sprite instance layout to carry a per-vertex
tint costs almost nothing, which makes carrying it unconditionally cheaper than
maintaining a second shader program for untinted batches.

---

## What the test suite guarantees

`tests/performance/` runs in two tiers, and they exist for different reasons.

**Guards** (`-m "performance and not slow"`, ~1.7 s) assert a **complexity
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
