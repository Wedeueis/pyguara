# Engine Remediation

Label: wayfinder:map
Effort: engine-remediation
Charted: 2026-08-29
Source: PyGuara Engine Audit — https://claude.ai/code/artifact/49b1a055-d2ff-48a3-9d60-a2cd08758954

## Destination

A locked remediation spec for PyGuara: every architectural fork surfaced by the engine
audit resolved, the composition root already repaired, and the demo suite migrated so it
proves the engine path actually works. An implementation session can pick up any decision
and build it without re-litigating the reasoning.

Reached when no ticket remains and `create_application()` boots, renders, and shuts down
under test on both supported backends.

## Notes

**Domain.** PyGuara 0.4.0 — a 2D game engine for Python 3.12+. ECS with inverted indexes,
reflection-based DI container, event-driven, pygame-ce and ModernGL rendering backends,
pymunk physics. Packaged on hatchling, five alpha tags, `pyguara` CLI entry point,
"Intended Audience :: Developers" — this is a distributable library, not a private
substrate for the demos.

**Execution override.** This map is planning by default, with one exception: tickets typed
`task` DO carry execution and end with the change committed. They exist because no
architectural decision here can be validated against an engine that will not boot. Every
other ticket produces a decision, not a deliverable.

**Skills each session should consult.** `/diagnosing-bugs` for the task tickets;
`/codebase-design` for the seam and ownership questions; `/grilling` and `/domain-modeling`
for anything under-specified; `/tdd` for the integration suite work.

**Standing preferences.**
- `ruff check .` and `mypy pyguara` must stay clean — they are clean today and that is worth
  not losing.
- Every fix lands with a regression test. The audit's root cause was 1,022 passing tests that
  never touched the composition root; adding fixes without tests reproduces it.
- Do not widen a ticket's scope mid-session. Surface the new question as fog or a new ticket.

**Decisions taken at charting time** (settled with the dev before any ticket existed, so
tickets inherit rather than revisit them):

- Mode: planning, with `task` tickets carrying execution.
- GL track: ModernGL is fixed and supported. Two-backend parity is a 0.5 requirement.
- ECS ownership: the Scene owns its world and its SystemManager. The container provides a
  factory, not a global instance.
- Rendering: `RenderSystem` gets wired. Scenes submit; the pipeline sorts, culls, batches.
- Logging: `EngineLogger` survives; the 32 stdlib modules migrate onto it.
- Demos: in scope, as the integration suite. All nine onto `create_application()`.

## Decisions so far

<!-- one line per resolved ticket: gist + link. Nothing resolved yet. -->

- [Fix the EngineLogger kwargs collision](issues/01-engine-logger-kwargs-collision.md) —
  `_log` pulls `exc_info`/`stack_info`/`stacklevel` into real logging args and renames any
  remaining kwarg that collides with a `LogRecord` attribute instead of raising; `shutdown()`
  now closes log handlers.
- [Repair the composition root](issues/02-repair-composition-root.md) — BOOT-1: branch on
  `isinstance(_, RenderGraph)` not resolvability, so Pygame's stub no longer routes into the
  GL render path; BOOT-2: fixed `main.py`'s `BootScene(...)` call to match its actual
  (dispatcher-only) constructor; BOOT-3: removed the duplicate empty `ComponentRegistry()`
  that clobbered the populated one. `create_application()` now boots, renders, and shuts down
  on the pygame backend.
- [Bootstrap smoke test](issues/03-bootstrap-smoke-test.md) — added
  `tests/integration/test_bootstrap_smoke.py`, deliberately unmarked so it runs under
  `make test-unit`/`make ci` despite living in `tests/integration/`; covers both
  `create_application()` and `create_sandbox_application()` for 30 ticks with an asserted
  clean shutdown.
- [Scene-owned world and SystemManager](issues/04-scene-owned-world-and-systems.md) — no
  global `EntityManager` in DI; base `Scene` auto-registers the four engine systems in
  `resolve_dependencies()`; priority band 100-399 reserved for engine, >=500 for game
  systems; `SteeringSystem` gets a real `cleanup()`, called via `SystemManager.cleanup()` on
  scene exit; `SystemManager` becomes mandatory (demos migrate off hand-rolled fields); pause
  uses both the existing `pause_below` skip and an explicit `set_enabled()` toggle.
- [Logging migration](issues/08-logging-migration.md) — hybrid leaf access: a shared
  module-level default `LogManager` singleton backs both a new `get_logger(name)` accessor
  (for genuinely non-DI leaves) and constructor injection (same instance, not a second one);
  `EventDispatcher._logger` becomes `Optional[EngineLogger]` defaulting via the accessor,
  sidestepping bootstrap's construction-order bug; `LogCategory` goes per-call-only (the
  per-logger key-suffix was decorative and disconnected from what `EventIntegratedHandler`
  actually reads); `EngineLogger.context()`/`ContextualFilter` dropped as unused and broken
  under concurrency; `LogManager.configure()` gets fixed to rebuild handlers, now
  load-bearing since most loggers will be created eagerly at import time. Lands as one
  execution ticket — see [Execute the logging migration](issues/16-execute-logging-migration.md).
- [Dead-code disposition](issues/09-dead-code-disposition.md) — of the seven islands:
  `ai/pathfinding/` gets finished and adopted (clean break, delete the concrete
  `pathfinding.py` it's shadowed by) rather than deleted, since its public API is already
  live, just backed by the wrong file; `replay/` and `backends/headless_renderer.py` get
  wired now (player-facing feature and test-infra speedup respectively); `dev/` hot reload
  gets deferred (fog — no player-facing need, a product-scope question); `ecs/archetype.py`
  and `error/` get deleted outright (zero references, and archetype storage's cache-locality
  claim doesn't transfer to plain Python objects anyway — fogged as a NumPy-columnar idea
  instead); `games/XXX_scenes/` gets deleted, no fog. Four execution tickets spawned: [Adopt
  the generic ai/pathfinding package](issues/17-adopt-generic-pathfinding-package.md), [Wire
  replay into InputManager and Application](issues/18-wire-replay-recording-playback.md),
  [Wire HeadlessBackend as the integration-suite test
  backend](issues/19-wire-headless-test-backend.md), [Delete confirmed dead
  code](issues/20-delete-confirmed-dead-code.md).
- [Native Color and Rect value types](issues/05-native-color-and-rect.md) — `Color`/`Rect`
  become `@dataclass(slots=True)`, no longer `pygame.Color`/`pygame.Rect` subclasses;
  conversion to pygame types happens via explicit `_pg_rect()`/`_pg_color()` helpers inside
  `PygameBackend` only; Rect gains `colliderect`/`contains`/`inflate`, Color gains HSV + a
  named-color table (beyond current usage, for public-API parity); clean break, no
  deprecation shim; `geometry.py`'s `Color` usage is fixed here, its deeper `PygameTexture`/
  `pygame.Surface` coupling stays out of scope.
- [ECS lifecycle contract](issues/06-ecs-lifecycle-contract.md) — `remove_entity()` goes
  soft-dead immediately (`del self._entities[id]` at once, callbacks detached, further
  mutation raises) with physical index cleanup deferred to the frame boundary, which makes
  every query safe to iterate while mutating regardless of arity; added
  `EntityDestroyed(entity, timestamp, source)`, dispatched synchronously at soft-death;
  `QueryCache` kept and fixed (removal hook, `frozenset` cache values instead of per-call
  `.copy()`, explicit registered-vs-empty check) rather than deleted. Also caught and fixed
  ECS-5 (an `Entity.__getattr__` infinite-recursion under `copy`/pickle) on the spot: `Entity`
  now rejects `deepcopy`/`copy`/pickle with a clear error, and gained `Entity.clone()` for
  prefab duplication — implemented immediately as a deliberate, narrow exception to this
  ticket's decision-only default. Graduates [Physics teardown
  bridge](issues/15-physics-teardown-bridge.md) off the fog now that its `EntityDestroyed`
  hook exists.
- [Input wiring and legacy retirement](issues/10-input-wiring-and-legacy-retirement.md) — the
  two non-integrated gamepad paths (raw pygame `JOY*` events driving bound Actions vs. the
  inert `GamepadManager`) converge on `GamepadManager` as the sole model: `InputManager.
  update()` calls it once per frame before `poll_events()`, bound gamepad Actions fire off its
  polled/deadzone-filtered state, `process_event()`'s `JOY*` branches and the legacy
  `_joysticks`/`_detect_controllers` bookkeeping are deleted (the OS event pump keeps running
  unchanged for keyboard/mouse/quit — this only changes how gamepad state is read, not whether
  it's read). `_cooldowns`/`InputAction.cooldown` are removed as a different concept from the
  games' own ability cooldowns, which stay untouched. `IInputBackend` becomes a required
  constructor param on `InputManager`/`GamepadManager`, with `PygameInputBackend` registered in
  DI. Lands as one execution ticket — see [Execute the input wiring and legacy
  retirement](issues/21-execute-input-wiring.md).
- [Scene lifecycle repair](issues/07-scene-lifecycle-repair.md) — `TransitionManager` stops
  hardcoding `on_exit`/`on_enter`; takes `on_from_hidden`/`on_to_shown` callbacks supplied per
  operation instead (fixing push-with-transition destroying the paused scene underneath, and
  single-phase transitions rendering the incoming scene before its `on_enter()` ever runs).
  `_scene_stack` + `_pause_below_flags` (parallel arrays, source of the SCENE-2 off-by-one)
  become one `_stack: List[StackEntry]` plus a tracked `_current_pause_below` gate.
  `cleanup()` unwinds the whole stack LIFO instead of leaking everything still on it.
  `Application` calls `scene_manager.set_screen_size()` once at init (live window-resize
  support doesn't exist anywhere yet — separate feature, out of scope).
- [Event dispatcher hot path](issues/11-event-dispatcher-hot-path.md) — history becomes opt-in
  (`enable_history=False` default) backed by a `deque(maxlen=...)`, confirmed dead in every
  current caller; `_global_listeners` deleted outright, no `subscribe_global()` added, since
  nothing consumes it and `EventMonitor` already gets its subset another way; base-class
  subscription (`CollisionEvent`/`TriggerEvent`) now works via a per-dispatch MRO walk merged
  into one priority-sorted pass, no subscribe-time cache; default `ErrorHandlingStrategy` stays
  `RAISE` as the correct engine-library fail-fast default, with the "`LOG` logs nowhere" half of
  the concern already fixed by Logging migration's accessor-backed default logger. Also widened
  scope on inspection: the audit's "nominal Protocol inheritance" pattern isn't 4 sites, it's 14
  — decided here to drop the explicit `(IFoo)` base at all of them, relying on structural typing
  so a missing method surfaces as a real mypy/AttributeError instead of silently no-opping. Two
  execution tickets: [Execute the event dispatcher hot-path
  fixes](issues/22-execute-event-dispatcher-hot-path.md), [Drop nominal Protocol inheritance
  across the 14 sites](issues/23-drop-nominal-protocol-inheritance.md).
- [DI gaps and small findings sweep](issues/12-di-gaps-and-small-findings.md) — execution
  ticket, all items fixed: DI now unwraps PEP 604 `X | None` unions (not just
  `typing.Optional`); scoped-service circular dependencies now raise
  `CircularDependencyException` instead of `RecursionError`; `validate_demos.py`'s dead
  string-vs-type check fixed; duplicate conflicting `pillow` floor removed from `pyproject.toml`;
  `bootstrap.py`'s `WindowConfig` rebuild (which dropped `title`/`fps_target`/`ui_scale`/
  `default_color`) replaced with using `config_manager.config.display` directly;
  `physics.gravity_x`/`gravity_y` wired into `PhysicsSystem` construction in `guara_falcao` and
  `physics_integration` (each demo overrides its own gravity on the loaded config in-process,
  since the shared `config/game_config.json` file would otherwise leak one demo's gravity into
  every other); `display.ui_scale` deleted (zero consumers, real UI-scaling is a standalone
  feature); CLAUDE.md's stale physics-loop claim and dead backlog pointer fixed; `AudioSourceSystem`'s
  discarded spatial attenuation/pan wired end-to-end via a new `IAudioSystem.set_channel_mix()`.
  Full suite green, `ruff`/`mypy` clean.
- [RenderSystem wiring](issues/13-rendersystem-wiring.md) — `Scene.render()` stops being
  abstract; the base default submits every entity carrying a `Renderable`-compliant component
  to `self.render_system` and flushes, with scenes overriding only for extra manual draws.
  `Camera2D` becomes scene-owned (`self.camera`), matching the existing informal per-demo
  pattern. `RenderSystem` becomes a per-scene instance built in `resolve_dependencies()`, same
  as the four engine systems — the backend (`IRenderer`) itself stays a DI singleton. Backend
  parity was already true by construction (`Batcher` is backend-agnostic; `render_batch()` is
  the only per-backend seam), nothing to decide there. Mid-grill discovery: this ticket's
  premise depended on *Scene-owned world and SystemManager*'s (ticket 04) decision, which was
  never executed — no task ticket existed for it. The two now execute together in one ticket:
  [Execute Scene-owned world, SystemManager, and RenderSystem
  wiring](issues/24-execute-scene-owned-systems-and-rendersystem.md).

## Not yet specified

Fog toward the destination. In scope, not yet sharp enough to ticket. Each patch graduates
into one or more tickets as the frontier reaches it.

- **RenderGraph per-backend wiring.** What replaces the stub-registration pattern that caused
  BOOT-1. Depends on how the render architecture lands.
- **Component contract.** Whether `StrictComponent` gets adopted, `_allow_methods` gets
  removed, and `slots=True` gets applied across the 109 dataclasses that currently defeat the
  documented `__slots__` optimisation. Depends on the ECS lifecycle contract.
- **Demo migration.** Moving nine games onto `create_application()` and submit-based
  rendering, and the disposition of `games/XXX_scenes/`. Cannot be scoped until the render
  architecture is specified. Now also includes migrating each demo's hand-rolled system
  fields (e.g. `games/guara_falcao/scenes.py`) onto its scene's `SystemManager`, per
  *Scene-owned world and SystemManager* — SystemManager is mandatory going forward.
- **Bootstrap collapse.** Replacing ~650 LOC of copy-paste game bootstraps with a
  parameterised factory, and promoting `validate_demos.py` into `tests/integration/`.
  Depends on demo migration.
- **Public API surface.** `pyguara/__init__.py` is empty; every import is a deep path. What a
  0.5 user is meant to import is undecided, and depends on which subsystems survive
  Dead-code disposition.
- **Unify `NavMeshPathfinder` under the generic pathfinding `Graph` abstraction.** Once *Adopt
  the generic ai/pathfinding package* lands, `ai/navmesh.py`'s separate polygon-adjacency A* +
  string-pulling funnel algorithm (`Vector2` paths, not discrete `Node`s) is the only
  pathfinding code left outside the `Graph[Node]`/`AStarPathfinder` design. Doesn't map onto
  it without a real refactor (funnel algorithm, polygon containment) — deliberately kept out
  of that ticket's scope. Worth a dedicated look once that ticket's shape is visible.
- **Hot-reload integration.** `dev/` (`HotReloadManager`, `PollingFileWatcher`) is fully built
  and tested but has no integration point in `Application`/`SystemManager`, and no
  player-facing need calls for it. Whether a pre-alpha engine carries live code reload — and
  where it would hook in if so — is a product-scope question, not a dead-code cleanup call.
- **NumPy-backed columnar component storage.** `ecs/archetype.py` (deleted per Dead-code
  disposition) claimed cache-friendly contiguous arrays but stored plain Python object
  references — the cache-locality payoff doesn't transfer to CPython objects the way it does
  in Unity DOTS/Bevy/EnTT. NumPy is already a core dependency (currently only used for
  ModernGL vertex-buffer prep). A real version of this idea would back hot, purely-numeric
  components (e.g. `Transform`) with parallel NumPy arrays, opt-in per system, rather than a
  wholesale ECS storage rewrite — revisit once `slots=True` lands on the Component contract
  and only if profiling still shows a gap the sparse-set/inverted-index model doesn't cover.

## Out of scope

Work consciously ruled beyond this destination. Never graduates; returns only as a fresh
effort if the destination is redrawn.

_Nothing ruled out yet. The dev was asked at charting time and had nothing to exclude._
