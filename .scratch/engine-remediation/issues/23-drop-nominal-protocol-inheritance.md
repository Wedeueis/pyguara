# Drop nominal Protocol inheritance across the 14 sites

Type: task
Status: open
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
