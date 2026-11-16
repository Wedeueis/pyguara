# ADR 0012: How a scene reaches the engine's services

- **Status:** accepted
- **Date:** 2026-11-14

## Context

Game code had no single way to reach a service. Scenes called
`self.container.get(T)` 173 times in `games/`, and 118 of those asked for one
of five services: `UIManager` (35), `SceneManager` (33), `Application` (24),
`EventDispatcher` (16) and `InputManager` (10). The repository's own
`main.py` read the private `app._container`, although `Application.container`
already existed, and a dozen tests did the same.

ADR 0010 proposes shrinking the container into a typed service registry. It
is scheduled for phase 6 of `project/backlog/active/engine_completion_roadmap.md`
and is not accepted. Phase 3 needs only the part of it that decides how game
code asks, which is what this ADR settles, ahead of the rest.

## Decision

1. **`Scene` has typed accessors for the four common services**:
   `application`, `scene_manager`, `ui_manager` and `input_manager`.
   `event_dispatcher` is already an attribute.
2. **Each accessor looks the service up in the scene's container when read.**
   It is not stored at resolve time. A test that substitutes a service in the
   container is then seen by the scene, and a container missing one of the
   four still resolves every scene that does not ask for it.
3. **Before `resolve_dependencies()` an accessor raises `SceneNotReadyError`**,
   a `RuntimeError` naming `on_enter()` as the earliest place to ask.
   `start_coroutine()` raises the same error, for the same reason.
4. **`self.container.get(T)` stays, as the escape hatch** for every other
   service: effects, the physics engine, persistence, the render graph.
5. **`Application.container` is the public way in from outside a scene.**
   Nothing in the repository reads `app._container`.

The demos in `games/` use the accessors throughout.

## Consequences

- No breaking change. `self.container.get(UIManager)` still works; the
  accessor is the documented spelling.
- 86 lookups in `games/` became attribute reads, and the scene code they sit
  in names its dependency by type annotation, so an IDE completes it.
- A scene subclass that defines its own attribute named `application`,
  `scene_manager`, `ui_manager` or `input_manager` now collides with a
  read-only property. None in `games/` or Reclaimer does.
- The scene constructor still took the event dispatcher when this was
  accepted. It is optional now: the engine supplies the application's own
  in `resolve_dependencies()`, which is what `pyguara.run(MyScene)` needs.

## Alternatives considered

**Constructor injection.** A scene declares the services it needs as
constructor parameters and the container builds it. Rejected for the reason
ADR 0010 gives: scenes are constructed by game code, with arguments of their
own (a level, a save slot), and the container cannot supply those. It would
also deepen the reflection ADR 0010 means to remove.

**Keep `self.container.get(T)` as the only way.** It works, but every call
is a lookup by type that mypy types loosely, and it presents the container as
something every scene must understand. The four accessors cover two thirds of
the calls.

**Resolve the four in `resolve_dependencies()` and store them.** Rejected:
see point 2 of the decision.

**An accessor for every registered service.** Rejected: the list would grow
with each subsystem and still need an escape hatch for a game's own services.

## See also

- ADR 0010, which proposes the rest of the container's reduction and
  carries the counts this one starts from.
- `docs/core/scenes.md`, "Reaching the engine's services".
