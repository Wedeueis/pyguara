# ADR 0008: The columnar world spike

**Status:** In progress -- increment 1 of the spike, measured. No decision yet.
**Date:** 2026-11-10
**Scope:** This fork only. `Wedeueis/pyguara` is unchanged by any of it.

## Context

ADR 0004 ports one boundary at a time and leaves state in Python. Its own
numbers show where that stops: native flocking spends 63% of its tick
crossing, a native render batcher was deferred at 7.4-8.9x because batches
must come back, and snapshot encoding priced at 1.2-1.9x because component
reads cannot move. Decision 3 names what would change that -- "a design
where the native side *owns* sprite state" -- and says it has not been
priced.

This spike prices it. The proposal is that component state lives in
native, typed, contiguous columns; that a native system reads and writes
them in place; and that Python reaches them one value at a time through a
view, or as NumPy arrays over the same memory.

It was given four exit criteria before any code was written:

1. CPU render path at 20,000 sprites: 39.2 ms -> under 4 ms.
2. Native flocking at 1,000 agents: 1.86 ms -> under 0.8 ms.
3. Per-entity attribute access from Python no more than 1.5x slower than
   today.
4. All demos render and the visual snapshots are unchanged.

## What increment 1 built

`rust/src/world.rs` and `pyguara/columnar/`, standing beside the object ECS
and wired into nothing:

- **Entity ids** are 64-bit: slot index low, generation high. A despawned
  id never resolves again.
- **One sparse set per component**, rows in insertion order. Removal
  tombstones a row and `flush()` compacts in order, which is
  `EntityManager`'s deferred-removal rule and keeps the ordering #324
  depends on.
- **A schema derived from the dataclass**: `float` -> `f8`, `int` -> `i8`,
  `bool` -> `u1`, `Vector2` -> two `f8`. Anything else is refused by name,
  and that component stays in the object ECS.
- **`arrays()`** hands back NumPy arrays over the column memory, no copy.
  While one is alive, a change that would move that memory raises
  `BufferError`.
- **`view()`** is a native descriptor per field on a generated subclass of
  a native `RowView`.
- **Per-column write counters**, the automatic form of
  `notify_component_changed`.
- **`add_scaled`**, one native system working in place, as the stand-in
  for the systems the later increments port.

`tests/test_columnar_world.py` holds 38 tests. `tools/columnar_probe.py`
reproduces every number below.

## Measured

WSL2, CPython 3.12, release build, minimum of several rounds.

### Bulk work: 290x to 1000x

`position += velocity * dt` over every entity, milliseconds per tick:

| Entities | Object ECS, Python loop | Columns, NumPy | Columns, native |
| ---: | ---: | ---: | ---: |
| 10,000 | 12.28 | 0.019 (633x) | 0.042 (292x) |
| 100,000 | 137.39 | 0.136 (1007x) | 0.385 (357x) |

NumPy beats the native loop because `add_scaled` joins two sparse sets by
entity -- a gather per row -- while NumPy adds two contiguous arrays that
happen to be aligned. That is the archetype-table argument in one row, and
it is worth 3x here.

### Spawning: 7x to 9x

Two components per entity, milliseconds:

| Entities | Object ECS | Columnar | |
| ---: | ---: | ---: | ---: |
| 10,000 | 141.9 | 21.2 | 6.7x |
| 100,000 | 1961.5 | 214.6 | 9.1x |

Still one crossing per `add`. A bulk insert from arrays is the obvious
next step and has not been written.

### Per-entity access: criterion 3 fails

Nanoseconds per access, through a view the caller already holds:

| | Object ECS | Columnar view | |
| --- | ---: | ---: | ---: |
| Read a scalar field | 7 (slots dataclass) | 67 | 9.5x slower |
| Read a `Vector2` | 37 (`Transform.position`) | 170 | 4.7x slower |
| Write a `Vector2` | 94 (`Transform.position`) | 88 | parity |
| Make a view | -- | 297 | |

**Reads miss the 1.5x bar by a wide margin, and the floor is structural.**
A native method call that does nothing but check a generation costs 46 ns,
which is already more than `Transform.position` costs in full. The first
version, built on Python properties, read a vector in 350 ns; moving to
native descriptors halved that, and what is left is the crossing (about 60
ns) plus building the `Vector2` (about 105 ns, against 210 ns for
`Vector2(x, y)` itself).

Writes are at parity only because `Transform`'s setter is expensive: it
marks a subtree dirty. Against a plain dataclass a view write is 10x
slower too.

## What this means

The bulk numbers say native ownership is worth far more than any port
ADR 0004 priced. The access numbers say it cannot be the *only* way game
code touches a component: a system that walks 1,000 entities reading
twenty fields each pays about 1.2 ms more per frame through views than
through objects.

That splits components into two kinds rather than refuting the design.

- **Bulk-consumed state** -- transforms for rendering, velocities,
  anything a native system or an array expression reads -- gains two to
  three orders of magnitude and loses nothing that matters, because its
  consumers stop going through per-entity access at all.
- **Per-entity logic state** -- cooldowns, inventories, AI blackboards --
  should stay Python objects. It was never going to be a column anyway if
  it holds a string or a list.

Three ways to lower the read floor exist and none is built:

1. **Stable-address storage.** Chunked columns never move, so a view
   could hold a `memoryview` and a row and index it directly, with no
   native call. It also retires the `BufferError` rule, since nothing an
   array points at would ever be reallocated. The cost is that a column
   stops being one contiguous array.
2. **Scalar-first APIs.** Most of a vector read is constructing the
   `Vector2`. Code that wants `x` should be able to ask for `x`.
3. **Free `Vector2` from `pymunk.Vec2d`.** ADR 0003 measured this and
   declined it while pymunk is the physics backend.

## Not yet measured, and what decides the spike

Criteria 1, 2 and 4 are untouched. **Criterion 1 is the one that
decides**: render extraction over columns is the largest single cost the
design claims to remove, and it is the first consumer that reads
`Transform` in bulk rather than per entity.

Increment 2 is therefore a columnar `Transform` and `Sprite`, a native
extraction that sorts, batches and packs instances from them, and the
20,000-sprite frame measured against the 39.2 ms in
`docs/guides/performance.md`.

## Decisions taken in this increment

Recorded with their alternatives in `.claude/decision-log.md`: sparse
sets over archetypes, `f8` for Python floats, the export-pinning rule, no
Python fallback, native descriptors, and building `Vector2` through
`tuple`'s own constructor.
