# ADR 0010: The container is a service registry

- **Status:** proposed
- **Date:** 2026-11-14

Not accepted, and nothing here is built. It changes the DI container,
which `AGENTS.md` lists among the core systems to ask about first, and it
deletes public API. It is scheduled after the fork merges back into
`pyguara`; see `project/backlog/active/engine_completion_roadmap.md`,
phase 6.

## Context

`pyguara/di/` is about 840 lines: a reflection-based container that
auto-wires constructors from type hints, three lifetimes (`SINGLETON`,
`TRANSIENT`, `SCOPED`), a `DIScope` with disposal, a run scope spanning
scenes, registration decorators, and circular-dependency detection.

Counted on `next` at `6154b5a`, outside `pyguara/di/` itself:

| Feature | Engine | Games | Tests |
| --- | ---: | ---: | ---: |
| `register_instance` | 41 | 23 | 74 |
| `register_singleton` (auto-wired) | 5 | 7 | 21 |
| `register_transient` | 0 | 0 | 17 |
| `register_scoped` | 0 | 0 | 16 |
| `@singleton` / `@transient` / `@scoped` | 0 | 0 | 0 |
| `create_scope` | 1 | 0 | 15 |
| `container.get(...)` | 65 | 173 | 145 |

So the container is, in use, a typed registry of singletons that were
built before they were registered, read through `get`.

- **Transient, scoped and the decorators are exercised only by their own
  tests.**
- **The one `create_scope` call** is `Scene.resolve_dependencies`, which
  gives every scene a scope that nothing registers a scoped service into.
- **Auto-wiring serves five classes**, all in `bootstrap.py`:
  `InputManager`, `SceneManager`, `UIManager`, `AudioManager` and
  `Application`. (The seven in `games/` are `boot_process`, which wires
  by hand on purpose.)
- **Game code does not inject; it looks up.** Of the 173 `container.get`
  calls in `games/`, 118 ask for one of five services: `UIManager` (35),
  `SceneManager` (33), `Application` (24), `EventDispatcher` (16) and
  `InputManager` (10).
- **34 `# type: ignore[type-abstract]` comments** exist because
  `get(type[T])` is typed for a concrete class and the engine's
  interfaces are Protocols.

### What the container does earn

Three things, and they are why it is not simply removed:

1. **Backend selection.** `bootstrap.py` chooses pygame or wgpu, native
   or pygame audio, and registers the choice under `IRenderer`,
   `IAudioSystem` and `IInputBackend`. That lookup is what lets game code
   obey "never import the rendering backend".
2. **Attachment.** `attach_studio(app.container)`, the agent harness and
   the headless tools find a running game's services by type.
3. **Substitution in tests.** The 74 `register_instance` calls in
   `tests/` replace real services with fakes.

A module-level global, or passing every service by hand, loses all three.

## Decision

Reduce the container to what is used, and name it for what it is.

1. **`DIContainer` becomes a typed service registry.** It keeps
   `register_instance`, `get` and `is_registered`. `TRANSIENT`, `SCOPED`,
   `DIScope`, the run scope, the decorators, `auto_register`, the
   reflection over constructors and the resolution stack are deleted.
   Roughly 840 lines become roughly 100.
2. **The five auto-wired services are constructed explicitly** in
   `bootstrap.py`. A wrong argument is then a type error at the call,
   not a resolution failure at startup.
3. **`Scene` gains typed accessors for the services nearly every scene
   reaches for**: the UI manager, the scene manager, the application, the
   input manager. `event_dispatcher` is already an attribute; the engine
   supplies it, so a scene's constructor stops taking one.
4. **`scene.container.get(T)` stays as the escape hatch** for everything
   else, documented as a service locator. `Application.container` is the
   public way in; nothing reads `_container`.
5. **`get` accepts a Protocol.** One typing change removes the 34
   `type-abstract` ignores. Whether by overload or by a small typed key
   is settled when it is written, against what mypy strict accepts.
6. **It is renamed `ServiceRegistry`**, with `DIContainer` kept as an
   alias for one release.

**Systems are unchanged.** A system already takes what it needs through
its constructor, and the scene that owns it builds it. That is
constructor injection with no container in it, and it stays the pattern.

## Consequences

- **Breaking.** `register_transient`, `register_scoped`, `create_scope`,
  `begin_run_scope`, `Scene.scope` and the decorators go. Nothing in the
  engine or `games/` uses them, but a game outside this repository might;
  the changelog entry is marked breaking.
- **The run scope (#65) goes with them.** It was built for a roguelike
  run that outlives its floor transitions, and nothing uses it. A game
  that needs one owns a plain object and registers it with
  `register_instance`; ending the run is replacing it.
- **About fifty tests are deleted**, being tests of the deleted features.
  The thread-safety test stays: registration and lookup still need the
  lock an earlier audit found missing.
- **A scene's constructor signature changes**, which touches every scene
  in `games/` and in Reclaimer. Mechanical, and the one-call entry point
  in the roadmap's phase 4 wants the same change, so they land together.
- **The README stops claiming "native Dependency Injection."** What is
  left is more modest and is what was always there.
- **A dependency cycle among the five services is no longer detected at
  run time.** It cannot occur: they are built in order, in one function,
  and a cycle would not type-check.

## Alternatives considered

**Keep it as it is.** It works, it is tested, and it costs nothing at
run time. Rejected because the cost is in what a newcomer has to learn:
three lifetimes and a scope hierarchy presented as the engine's
architecture, of which a game uses none.

**Remove the container; pass services by hand or hold them in module
globals.** Rejected for the three reasons under "What the container does
earn". Globals in particular would let game code import a backend's
module to reach its service.

**Go the other way: real injection everywhere.** Scenes declare their
services as constructor parameters and the container builds them. This
is what the existing machinery was designed for. Rejected because scenes
are constructed by game code, with arguments of their own (a level, a
save slot), in 30,000 lines of demos that do not work that way, and
because it deepens the reflection rather than removing it.

**Keep the lifetimes, hide them from the docs.** Rejected: code that is
kept is code that is maintained and tested, and an undocumented feature
is the worst of both.

## See also

- `project/backlog/active/engine_completion_roadmap.md`, phases 3, 4
  and 6.
- `docs/core/dependency-injection.md`, which this replaces when accepted.
- `REFACTOR_STATE.md`, the DI iteration, for the missing-lock finding.
