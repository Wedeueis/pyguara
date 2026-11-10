# Decision log -- choice points resolved during implementation

## Fork as a separate private repository with full history
- **Context:** Isolating the columnar/native-runtime work from `Wedeueis/pyguara` so the original engine carries none of the risk.
- **Alternatives:** (a) a long-lived branch in the original repo; (b) a GitHub fork (not possible into the same account); (c) a fresh repo seeded with a squashed snapshot; (d) a new repo carrying the full history, with the original as a push-disabled `upstream` remote.
- **Chose:** (d). Full history keeps `git blame` and the SHAs the ADRs cite, and `upstream` lets fixes from the original be merged in while a disabled push URL makes writing back to it impossible by accident. Private and named `pyguara-next` as reversible defaults.
- **Tags:** repository, fork, risk

## Sparse sets with deferred order-preserving compaction, not archetype tables
- **Context:** Choosing the storage layout for the native column store (`rust/src/world.rs`).
- **Alternatives:** (a) archetype tables -- aligned columns across components, but an entity moves tables on every add/remove and row order follows swap-removes; (b) sparse set per component with swap-remove -- O(1) removal, reorders rows; (c) sparse set per component with tombstones compacted in insertion order at `flush()`.
- **Chose:** (c). Query order is part of the simulation here (#324), and the existing `EntityManager` already defers index cleanup to the frame boundary, so (c) reproduces today's ordering and removal semantics exactly. Archetypes stay a candidate to price once render extraction exists.
- **Tags:** ecs, columnar world, determinism

## f64 columns for simulation floats
- **Context:** Picking the dtype a Python `float` field maps to.
- **Alternatives:** f32 (half the memory, what the GPU wants, what the particle pools use) or f64 (what Python computes in).
- **Chose:** f64. A column must hold exactly the value Python wrote or every system reading it diverges from the object ECS in its last bits, which is the tolerance regime the pools needed and gameplay state cannot accept. f32 remains available as an explicit dtype and is where a render pack would convert.
- **Tags:** columnar world, determinism, parity

## Structural changes raise while array views are alive
- **Context:** A NumPy array over a column holds a raw pointer into a `Vec` that a later insert may reallocate.
- **Alternatives:** (a) invalidate views on change and raise on later access -- NumPy cannot be told its memory is gone; (b) chunked storage with stable addresses -- views stop being one contiguous array; (c) count live buffer exports and refuse any reallocating or compacting change while the count is non-zero, as `bytearray` does.
- **Chose:** (c). It is the only option that is memory-safe with a plain contiguous `ndarray`, and it fails loudly at the offending write with a `BufferError`.
- **Tags:** columnar world, memory safety, numpy

## The native world has no Python fallback
- **Context:** Whether `pyguara.columnar` follows the two-store pattern of ADR 0004.
- **Alternatives:** write a pure-Python column store alongside and a parity suite, or load through `native.require_extension()` as audio and net do.
- **Chose:** no fallback. The point of the fork is native ownership of state; a NumPy-backed twin would double the work being priced and its parity suite would test nothing the object ECS comparison does not.
- **Tags:** native boundary, columnar world

## Native descriptors for view access, not Python properties
- **Context:** A held view's `Vector2` read measured 350 ns against `Transform.position`'s 37 ns, with the view built from Python `property` objects calling `NativeWorld.get_pair`.
- **Alternatives:** (a) keep properties and accept it; (b) a native view class resolving names in `__getattr__` -- only reached after normal lookup fails, so it pays for the failure first; (c) a native `RowView` base with one native `FieldAccessor` descriptor per field on a generated subclass.
- **Chose:** (c). The interpreter calls `tp_descr_get` directly, so there is no Python frame and no argument tuple. Reads went 350 -> 170 ns for a vector and 105 -> 67 ns for a scalar; writes reached parity with `Transform` (88 vs 94 ns).
- **Tags:** columnar world, performance, native boundary

## Build Vector2 through tuple's own constructor, not a raw allocation
- **Context:** Returning a `Vector2` from a native read without paying 210 ns for `Vec2d.__new__`.
- **Alternatives:** (a) call `Vector2(x, y)` from Rust; (b) `PyType_GenericAlloc` plus `PyTuple_SetItem`, the cheapest; (c) call `tuple`'s `tp_new` slot with the subclass, i.e. `tuple.__new__(Vector2, (x, y))` without the Python call.
- **Chose:** (c). (b) leaves the tuple header to zero-initialisation, and the wheel is `abi3` so it runs on interpreters newer than the one it was built for -- a CPython that caches a tuple's hash in its header would get 0 instead of the "not computed" sentinel and hash every vector alike. (c) runs the allocator that owns the layout.
- **Tags:** columnar world, abi3, memory safety


## Target the profile, not the plan: wall probes before columnar storage
- **Context:** Asked to make the current Reclaimer run much faster on the fork. Profiled it first: at 200 enemies, `CharacterMover`'s per-pixel `overlap_box` was 31% of a rendered frame and half of a host tick, each probe building a `pymunk.Body` and `Poly` in Python.
- **Alternatives:** (a) continue the columnar world into `Transform`/`EntityManager`, the architecture the report leads with; (b) cache and reuse the probe shape in Python; (c) move the swept move itself native.
- **Chose:** (c). The profile says columnar storage would not touch Reclaimer's top costs, and the owner had already ruled (2026-11-09) that the mover waits for a native sweep rather than a Python fix.
- **Tags:** performance, character mover, reclaimer

## A mirror that answers only when certain, not a second collision engine
- **Context:** Making the mover's overlap queries native while Chipmunk stays the physics backend.
- **Alternatives:** (a) reimplement Chipmunk's box and segment queries bit-exactly in Rust; (b) a Rust static-collision backend replacing pymunk for wall-only worlds; (c) a native mirror of the static boxes that returns "certainly clear", "certainly this box" or "ask Chipmunk", deferring anything within 1e-6 px of touching and any multi-box overlap.
- **Chose:** (c). Exactness holds by construction instead of by matching another library's float operations, so it cannot diverge -- only decline. (a) would be a parity obligation against code this project does not own.
- **Tags:** physics, native boundary, parity

## The mirror turns itself off for anything but static axis-aligned boxes
- **Context:** Which spaces may be answered from the mirror.
- **Alternatives:** track dynamic and kinematic bodies in the mirror and refresh them per step, or mirror only when every solid in the space is a static, unrotated box and otherwise return None.
- **Chose:** the second. It is exactly the level-geometry world a mover sweeps against, and a space with anything richer keeps today's behaviour untouched.
- **Tags:** physics, native boundary

## Geometry read from each shape's cached bounding box
- **Context:** Where the mirror reads a wall's extent from.
- **Alternatives:** compute it from the body's position plus the collider's dimensions, or read `shape.bb`.
- **Chose:** `shape.bb`. Chipmunk does not reindex a static body that is repositioned, so its queries keep answering from the old place; the cached box is what those queries test, and the mirror has to share the quirk to stay identical.
- **Tags:** physics, parity

## A shared flag instead of a callback for "a static body moved"
- **Context:** The body adapter must tell the engine to rebuild the mirror when a static body is repositioned.
- **Alternatives:** give the adapter a bound method of the engine, or share a one-element list both can set.
- **Chose:** the list. The bound method made every adapter reference the engine, and Studio's scene snapshot deep-copies `RigidBody` handles: the copy walked into the engine and failed a Studio test.
- **Tags:** physics, studio

## The mover accepts a tuple, not "anything but None"
- **Context:** `CharacterMover` finds the optional `sweep_box` with `getattr`.
- **Alternatives:** a `runtime_checkable` capability protocol and `isinstance`, or checking the returned value's type.
- **Chose:** `type(swept) is tuple`. A `MagicMock` engine satisfies any `getattr` and any structural `isinstance`, and nine existing tests pass one; only the answer's type tells a real engine from a double.
- **Tags:** physics, testing

## One integration branch, `next`, instead of a branch per increment from main
- **Context:** The repo's rule is that every independent branch is cut from `main` and gets its own PR. The increments here are independent of each other, but each one has to be measured against Reclaimer together with all the others.
- **Alternatives:** separate branches from `main`, merged into a throwaway branch for every measurement; or one integration branch carrying one commit per increment.
- **Chose:** `next`, one commit per increment. Nothing here is being reviewed into `main` yet, and the commits stay split so each can be lifted onto its own branch when it is.
- **Tags:** repository, workflow
