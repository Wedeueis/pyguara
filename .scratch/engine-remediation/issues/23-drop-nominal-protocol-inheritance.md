# Drop nominal Protocol inheritance across the 14 sites

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: coherence, follows from Event dispatcher hot path, ticket 11

## Question

Nothing to decide — execute the decision recorded in
[Event dispatcher hot path](11-event-dispatcher-hot-path.md): drop the explicit `(IFoo)` base
class at every site that currently nominally inherits a `Protocol`-based interface, relying on
structural typing instead.

Sites (confirmed by `grep -rn "class.*(I[A-Z][a-zA-Z]*)" pyguara/` against every `Protocol`-based
interface — re-run that grep first in case new sites landed since this ticket was written):

- `pyguara/events/dispatcher.py`: `class EventDispatcher(IEventDispatcher)` → `class
  EventDispatcher:`
- `pyguara/physics/backends/pymunk_impl.py`: `PymunkBodyAdapter(IPhysicsBody)`,
  `PymunkEngine(IPhysicsEngine)`
- `pyguara/graphics/backends/pygame/pygame_renderer.py`: `PygameBackend(IRenderer)`
- `pyguara/graphics/backends/moderngl/renderer.py`: `ModernGLRenderer(IRenderer)`
- `pyguara/graphics/backends/headless_renderer.py`: `HeadlessBackend(IRenderer)`
- `pyguara/graphics/backends/pygame/pygame_window.py`: `PygameWindow(IWindowBackend)`
- `pyguara/graphics/backends/moderngl/window.py`: `PygameGLWindow(IWindowBackend)`
- `pyguara/resources/loaders/data_loader.py`: `JsonLoader(IResourceLoader)`
- `pyguara/prefabs/loader.py`: `PrefabLoader(IResourceLoader)`
- `pyguara/audio/backends/pygame/loaders.py`: `PygameSoundLoader(IResourceLoader)`
- `pyguara/graphics/backends/pygame/loaders.py`: `PygameImageLoader(IMetaAwareLoader)`
- `pyguara/graphics/backends/moderngl/loaders.py`: `GLTextureLoader(IResourceLoader)`
- `pyguara/audio/backends/pygame/pygame_audio.py`: `PygameAudioSystem(IAudioSystem)`

For each: remove the Protocol from the class's base-class list. Leave any *non*-Protocol base
classes (if a class has one) untouched. Do not change method signatures, docstrings, or bodies —
this is a base-class-list-only change.

**Verify the safety net actually holds**, since the whole point of this ticket is that removing
the nominal base doesn't just hide the problem again:
- Every DI registration binding one of these interfaces (e.g. `container.register(IRenderer,
  PygameBackend, ...)` in `bootstrap.py` and any backend-specific bootstrap) must still
  type-check under `mypy pyguara` strict mode — confirming mypy verifies structural compatibility
  at the registration/usage site now that there's no inherited stub to hide behind.
- Spot-check: temporarily delete one required method from one of the 13 non-dispatcher classes
  locally, run `mypy pyguara`, confirm it now errors (proving the structural check fires),
  then restore the method. Do this as a manual check, not a committed test — it's verifying the
  removal has teeth, not asserting behavior to guard long-term.
- `isinstance(instance, IFoo)` / `issubclass(Cls, IFoo)` calls, if any exist in tests or engine
  code, must still pass — `@runtime_checkable` Protocols support structural `isinstance` checks
  without nominal inheritance. Grep for `isinstance(.*I[A-Z]` and `issubclass(.*I[A-Z]` to find
  any such call sites and confirm they still hold.

## Done when

- None of the 13-14 classes above list a `Protocol`-derived interface as an explicit base class.
- `mypy pyguara` stays clean, and the manual delete-a-method spot check confirms a genuinely
  missing method now surfaces as a mypy error at a usage site (not silently swallowed).
- Any `isinstance`/`issubclass` checks against these protocols still pass unchanged.
- `ruff check .` clean, full test suite green.

## Resolution

Commit `9ad1e89`.

**Site count grew from 14 to 24** on re-running the grep, as the ticket anticipated. Two
reasons: the original `class.*(I[A-Z]...)` pattern only matches `I`-prefixed protocol names,
missing `UIRenderer`/`TextureFactory`/`StorageBackend`/`Graph`/`Heuristic` entirely (none of
which start with `I`); and tickets 17/18/19 (all executed earlier this session, after ticket
11 was written) added new nominally-inheriting classes of their own —
`HeadlessWindowBackend(IWindowBackend)`, `HeadlessUIRenderer(UIRenderer)` (ticket 19), and
`GridGraph`/`ManhattanDistance`/`EuclideanDistance`/`DiagonalDistance`/`OctileDistance`
inheriting `Graph[GridNode]`/`Heuristic[GridNode]` (ticket 17). Applied the same mechanical
fix to all 24 across 17 files, per the decision's own framing ("one mechanical policy
applied uniformly") — including `PygameUIRenderer`/`GLUIRenderer` and `FileStorageBackend`,
which the original list also missed for the same `I`-prefix reason.

**Explicitly did not touch** the ~20 `Event(Protocol)` dataclass sites
(`OnActionEvent`, `CollisionEvent`, etc.). `Event` has zero methods — only field
declarations (`timestamp`, `source`) — so the stub-swallowing hazard this ticket exists to
fix doesn't apply; those inherit `Event` nominally to get real dataclass field inheritance,
a legitimate and different use of the same Protocol-inheritance syntax. Confirmed this
reading by checking `Event`'s definition directly before excluding it.

**Safety net verified with a real spot-check**, not just a clean test run: temporarily
deleted `PygameBackend.draw_rect`, ran `mypy pyguara`, confirmed the removal has teeth, then
restored it. Grepped every `isinstance()`/`issubclass()` call against these protocols: the
one real hit (`resources/manager.py`'s `isinstance(loader, IMetaAwareLoader)`) still holds,
since `IMetaAwareLoader` is `@runtime_checkable`.

**Found while spot-checking, not fixed here — spun into [Decide whether to harden
DIContainer's generic signatures](30-di-container-generic-safety-decision.md):** the
ticket's premise that a missing method "surfaces as a mypy structural-mismatch error… at the
DI registration site" doesn't actually hold for most of these 24. `register_instance()`'s
`Type[TInterface], TInterface` and `register_singleton()`'s `Type[TInterface],
Type[TImplementation]` (independent TypeVars, not even the same one) both let mypy infer
jointly rather than enforce the second argument structurally matches the first — confirmed
with an isolated repro outside the codebase reproducing the exact pattern, where
`register(IFoo, Impl())` type-checked cleanly under `mypy --strict` even with `Impl` missing
a required method, and even when passed a wholly unrelated type. Affects the 10 (of 13)
protocols here that aren't `@runtime_checkable`. The fallback the decision also named — a
missing method now raises `AttributeError` at the real call site instead of silently
returning `None` — is still real and independently confirmed; only the earlier,
registration-time mypy catch doesn't materialize. Worth its own decision on whether hardening
the container's generics is worth the engineering cost, not this ticket's to solve.

Full suite green (1059 passed), `ruff check .` and `mypy pyguara` clean.
