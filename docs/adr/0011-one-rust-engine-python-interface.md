# ADR 0011: One Rust engine, with Python as its interface

- **Status:** accepted as a direction (the user's call, 2026-11-14). No
  port below is approved by it; each still has to pass ADR 0004's rule.
- **Date:** 2026-11-14
- **Supersedes:** the position of [ADR 0003](0003-native-core-spike.md),
  that the native core is an accelerator kept beside a Python
  implementation. ADR 0003's measurements stand and are relied on here.
- **Amends:** [ADR 0004](0004-the-native-boundary.md), Decisions 4 and
  5, for subsystems that end up with one implementation.
- **Plan:** `project/backlog/active/engine_completion_roadmap.md`,
  phase 6.

## Context

ADR 0003 answered RFC-0003 by narrowing it. The crate would be an
**accelerator, not a rewrite**: absent-tolerant, with a Python
implementation of every native subsystem kept, tested for parity, and
selected by one engine-wide switch (ADR 0004, Decision 4). Replacing
pymunk was "a separate decision" and "a project, not a milestone"; a
Rust `Vector2` was shelved.

That was right for what was true in October. Four things have changed.

1. **The extension always ships.** ADR 0006 put it inside the wheel and
   rejected a pure-Python wheel, so there is no supported install
   without it. The Python stores were kept for a machine that had not
   built the extension, and that machine is now a source checkout with
   nothing compiled, or a platform outside the wheel matrix.
2. **Rust is already the platform layer, with no Python twin.** The wgpu
   renderer, the window, input, gamepads, image decoding, text, the
   audio mixer, the network transport and the Steam binding are backends
   in Rust and nothing else. ADR 0004 had to be amended to say its
   switch governs *stores*, not *backends*. The engine is no longer a
   Python engine with a native accelerator; it is two engines sharing a
   package.
3. **The twins have a measured price and a measured failure.** Five
   parity suites, three tiers of agreement that differ per subsystem,
   and a second implementation of every change. And `SpatialHash`
   defaulting to native silently turned the flocking suite's Python
   reference into the native one: 69 tests passed with the grid's
   distance test deliberately broken (ADR 0004, Decision 7).
4. **A real game now sets the costs.** Profiling Reclaimer named what is
   expensive, and none of it was on RFC-0003's list: a guest
   interpolating every replicated field of every entity each frame, and
   one Python call per drawn primitive.

So the question ADR 0003 answered, "should some of this be native?", is
settled by what was built. The open one is what the engine is.

## Decision

**The backend is one Rust engine. Python is the interface a game is
written in.** Where a backend subsystem is better in Rust it is replaced
there, whether it is Python today or a third party's C, and it then has
one implementation.

### 1. What is the interface, and stays Python

Scenes and their lifecycle, the service registry (ADR 0010), the event
bus, the UI builder, the gameplay kits, prefabs, Studio and the CLI.
This is where a game's author works, where iteration speed matters more
than execution speed, and where ADR 0004's `T_pinned` lives. None of it
is a candidate.

**Gameplay kits are not ported.** They are the code a game reads,
copies and changes.

### 2. What makes a backend subsystem a candidate

ADR 0004's Decision 1 to 3 and 6 are unchanged: fix the algorithm first,
price the ceiling with the ratio rule, and port a boundary, not a
function. This ADR adds no exemption from measurement. It changes two
things about how the answer is read.

**Unification now counts.** Under ADR 0003 a port had to pay for itself
in milliseconds and for a second implementation forever, so a 2x port
was declined. Where a port *replaces* its Python or C predecessor, the
second cost is gone, and removing a dependency or a duplicate is a
benefit to be weighed. A port may be accepted on those grounds with a
modest speedup. It may not be accepted on those grounds if it is slower
in a regime a consumer actually runs.

**The unit to move is a system with its data.** ADR 0008 measured bulk
work on native columns at 290x to 1000x and per-entity reads from Python
at 4.7x to 9.5x *slower*. So state that Python reads one object at a
time stays in Python until the system that reads it moves too. A native
type that Python touches per entity, per frame, is the wrong boundary.

### 3. One implementation, once native is the only install

A two-store subsystem keeps only its Rust implementation. This retires,
for that subsystem:

- its Python store from the shipped package;
- `accelerate=` on its constructor;
- its share of `native_acceleration` and `PYGUARA_NO_NATIVE`.

**The parity obligation becomes a correctness obligation.** ADR 0004's
Decision 5 defined correct as "agrees with Python". With no Python store
there is no such definition, so before a store is retired its parity
suite is converted, not deleted:

- the bit-exact and constructed-geometry tiers become **golden vectors**:
  the inputs, and the outputs the two stores last agreed on;
- the sabotage tests stay, and must still fail when the Rust is broken;
- the Python implementation may survive under `tests/` as an executable
  reference where a golden vector cannot express the property. It is
  then test code: never imported by the engine, never a fallback.

A store whose suite cannot be converted this way is not retired.

**`native_acceleration` ends as `required`.** When the last two-store
subsystem is retired the switch has nothing to choose between, and an
engine that cannot load its extension fails at startup naming why.

### 4. Third-party C is replaced when it is what holds something back

**pygame** is already replaced on the wgpu path. It becomes an optional
extra once wgpu is the default backend, and leaves `dev` when the pixel
tests hold wgpu to golden images in place of the software renderer.

**pymunk** is replaced by a Rapier backend behind `IPhysicsEngine`. Not
for speed; nothing measured says pymunk is slow. The reasons are:

- it is the last backend the engine does not own;
- cross-machine determinism, which rollback netcode would need and
  Chipmunk through CFFI does not offer;
- it is the reason `Vector2` is a tuple (ADR 0003, finding 1), and so
  the reason every position in the engine depends on a physics library.

ADR 0003 called this "a project, not a milestone", and that has not
changed. Rapier runs beside pymunk, held to the existing physics tests,
until it reproduces joints, queries, triggers, collision events, one-way
platforms and the swept character mover. Then it becomes the default,
and pymunk is retired a release later.

### 5. `Vector2` follows physics, and is not a performance item

A Rust `Vector2` is only possible once pymunk is gone, because pymunk's
C layer accepts tuples and nothing else.

It should not be sold as an optimisation. ADR 0003 counted the traffic:
outside the hot systems a frame performs **1 to 8** vector operations,
and inside them the data has moved or is moving to native arrays, where
no Python vector is built at all. A PyO3 call costs 50 to 100 ns against
today's 290 ns add, so the gain on a single operation is perhaps 3x, on
traffic that is nearly absent.

Its justification is the dependency: a maths type that is the engine's
own. It is done only if the audit ADR 0003 asked for and never ran, of
everything that relies on `Vector2` being a tuple (unpacking, indexing,
hashing, equality against a literal tuple), comes back cheap. If it does
not, `Vector2` becomes a plain Python tuple subclass of the engine's
own, which removes the dependency with no boundary at all.

## Order

Dependency order; the roadmap's phase 6 carries sizes and "done when".

1. Retire the Python stores, one subsystem at a time (Decision 3).
2. pygame becomes an extra.
3. Replication and interpolation in Rust.
4. Batched drawing.
5. Physics on Rapier.
6. `Vector2`, after 5.
7. Columnar components (ADR 0008), with 4 as their first consumer.
8. Golden pixel tests; pygame dropped.

Items 3 and 4 come before physics because they have a measured cost in
a real game behind them today, and Rapier does not.

## Consequences

**A source build with no Rust toolchain stops being a degraded engine
and becomes no engine.** ADR 0006 already made the toolchain the price
of a source build; this removes what the fallback bought. A contributor
who cannot build the crate cannot run the affected subsystems.

**A platform outside the wheel matrix loses the Python path.** Today
that is anything but Linux x86_64 and aarch64, macOS x86_64 and arm64,
and Windows x64. Such a platform builds from the sdist or does not run.

**Debuggability moves.** A Python store can be stepped through and
patched from a game. A Rust one cannot, so a retired subsystem owes its
users what the Python source gave them for free: errors that name the
input at fault, and state that can be read back from Python.

**The Python interface is a compatibility surface now.** If the backend
can change underneath it, the interface is what a game depends on. A
game written against it before a port must run after it, and a port
that needs a signature to change says so as a breaking change.

**Rapier changes results once.** It will not settle a stack as Chipmunk
does. Every replay, golden frame and seeded test containing a rigid body
changes on the switch, and a game tuned on pymunk's feel is retuned.

**Parity sabotage loses a witness.** Two independent implementations
catch a transcription slip that one implementation and its own recorded
output cannot. Golden vectors captured while the stores still agree keep
what was known; they do not catch a defect both stores shared.

**Less code, and fewer rules.** Five Python stores, five parity suites
and the per-subsystem agreement tiers go. So does the section of
`docs/agents/native-extension.md` that exists to explain them.

## Alternatives considered

**Keep ADR 0003's position.** Defensible, and cheaper this quarter.
Rejected because its premise is gone: the twins exist for an install
that is no longer supported, and they have already hidden a broken
native path behind a green suite once.

**Rewrite the engine in Rust, with Python bindings generated from it.**
What RFC-0003 was read as proposing. Rejected for the reason ADR 0003
gave: the ECS, events, scenes and kits are `T_pinned`, the interface is
what the engine is for, and 30,000 lines of demos and a shipping game
are written against it.

**Move the ECS to Rust first, and everything else onto it.** The
architecturally tidy order. Rejected on ADR 0008's measurement:
per-entity access from Python gets slower, and the profile of a real
game showed columnar storage would not have moved any of its costs. It
stays last, behind a consumer that needs it.

**Keep pymunk and stop at the rest.** A reasonable place to stop, and
the plan can stop there: items 1 to 4 and 8 do not depend on physics.
Not chosen as the end state because it leaves `Vector2` tied to a
physics library and rollback netcode out of reach, but nothing earlier
in the order is wasted if 5 and 6 are never built.

## Not decided here

- **Whether rollback netcode is wanted.** It is the strongest reason for
  item 5 and the one that would move it up the order.
- **What the Python interface's stability promise is**, and from which
  version. This ADR creates the need for one.
- **Which crate versions**, and whether Rapier's determinism feature
  costs performance that matters here. Measured when item 5 starts.
