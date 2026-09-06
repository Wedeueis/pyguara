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
- [ModernGL shape shader](issues/14-moderngl-shape-shader.md) — usage check first: `draw_rect`
  on `IRenderer` is a primary per-entity draw call in several demos (placeholder colored
  rects, not textures) plus every editor tool, so this is a real ModernGL rendering gap, not a
  rare debug path. One unified SDF fragment shader handles all three primitives (box/circle/
  segment SDF, selected per-instance), hardware-instanced and batched (not deferred to later,
  given the usage data), fill vs. stroke handled by a per-instance `width` branch in the same
  shader. Batching stays backend-internal to `ModernGLRenderer` — `IRenderer` signatures are
  unchanged, no `RenderSystem`/`RenderQueue`/`Batcher`/`Renderable` changes — trading away
  Z-interleaving between shapes and textures within a frame, judged acceptable since no
  current demo actually mixes the two in a way that needs interleaving. Lands as one execution
  ticket — see [Execute the ModernGL shape shader](issues/25-execute-moderngl-shape-shader.md).
- [Physics teardown bridge](issues/15-physics-teardown-bridge.md) — gap found first:
  `EntityDestroyed` doesn't exist anywhere in the codebase; *ECS lifecycle contract*'s (ticket
  06) decision was never executed. `PhysicsSystem` subscribes to `EntityDestroyed` in
  `__init__` using its already-injected `event_dispatcher`; `destroy_body()` uses pymunk's own
  `body.shapes` directly, no new tracking; teardown is deferred to a pending-queue drained in
  `update()` before `space.step()`, since pymunk forbids space mutation mid-step (relevant once
  a collision-triggered-death pattern exists); an unset `_body_handle` is a silent no-op. Two
  sequenced execution tickets (not combined, since the ECS change is engine-wide and physics is
  a narrow subscriber): [Execute the ECS lifecycle
  contract](issues/26-execute-ecs-lifecycle-contract.md), then [Execute the physics teardown
  bridge](issues/27-execute-physics-teardown-bridge.md) (blocked by it).
- [Execute the logging migration](issues/16-execute-logging-migration.md) — landed the
  `get_logger(name)` accessor backed by a shared `default_log_manager` singleton (also
  now what `bootstrap.py` configures/registers, instead of a second unrelated
  `LogManager()`); `LogManager.configure()` rebuilds already-constructed loggers'
  handlers via a new `EngineLogger.reconfigure()`; `category` dropped from `get_logger()`;
  `context()`/`_context_stack`/`_get_merged_context()`/`ContextualFilter` deleted;
  `EventDispatcher._logger` defaults to `get_logger(__name__)`, fixing both
  `ErrorHandlingStrategy.LOG` and the queue-overflow warning; all 31 leaf modules swept
  onto the accessor. Two things found and fixed mid-execution: the `pyguara.log` ↔
  `pyguara.events.dispatcher` import cycle this default creates (broken via
  `TYPE_CHECKING`-only imports, `EventDispatcher` was never more than a type hint there),
  and several leaf modules' printf-style logging calls, which would have crashed against
  `EngineLogger`'s positional `category` param — fixed by making `category` keyword-only
  and adding `*args` passthrough rather than rewriting every call site.
- [Adopt the generic ai/pathfinding package](issues/17-adopt-generic-pathfinding-package.md)
  — `ai/pathfinding/__init__.py` added, exporting the full `Graph`/`Heuristic`/`Node`/
  `AStarPathfinder`/`GridGraph`/heuristics/smoothing/conversion surface; `grid.py` gained
  `DiagonalDistance`/`OctileDistance` plus `smooth_path`/`path_to_world_coords`/
  `world_to_grid_coords` (ported from the deleted concrete module); `ai/pathfinding.py`
  deleted, `ai/__init__.py` and `tests/test_pathfinding.py` rewritten onto the new names, no
  compatibility aliases. Four old tests dropped (blocked-start/goal short-circuiting and
  iteration/path-length stats — mechanics the generic `AStarPathfinder` doesn't implement,
  and adding them would've meant modifying `astar.py`, outside this ticket's scope). One gap
  found and deliberately not fixed: `GridGraph.get_neighbors()` doesn't prevent diagonal
  corner-cutting the way the deleted `GridMap` did — a gameplay-feel judgment call, not a
  crash risk, so it's spun into [Decide whether GridGraph should prevent diagonal
  corner-cutting](issues/28-diagonal-corner-cutting-decision.md) rather than decided here.
- [Wire replay into InputManager and Application](issues/18-wire-replay-recording-playback.md)
  — `InputManager` gained `attach_recorder()`/`detach_recorder()` (records key/mouse events
  when active, skips the still-legacy `JOY*` branches on purpose) and
  `process_replayed_event()` (feeds a recorded event through the same `_handle_input()`/
  `_handle_axis()`/`_dispatch_action()` paths a live one takes); `Application` gained
  `start_recording()`/`stop_recording()`/`save_recording()`/`load_replay()`, mutually
  exclusive, with `_process_input()` framing recorder frames and driving playback (factored
  into `_begin_replay_frame()`/`_end_replay_frame()` so `SandboxApplication` shares it).
  Regression test seeds both a recording run and a playback run from one template `Entity`
  via `.clone()` and asserts matching final state. Gap found and spun out rather than fixed
  here: [Scene lifecycle repair](07-scene-lifecycle-repair.md) was, like tickets 04 and 06,
  never actually executed — [Execute the scene lifecycle
  repair](issues/29-execute-scene-lifecycle-repair.md).
- [Wire HeadlessBackend as the integration-suite test
  backend](issues/19-wire-headless-test-backend.md) — `HeadlessBackend` was out of date
  with `IRenderer` (missing `begin_frame`/`end_frame`/`draw_circle`, plus a `width`/`height`
  bug hardcoding 800/600), fixed alongside registering it; rounded out the full
  composition-root quartet with new `HeadlessWindowBackend`/`HeadlessUIRenderer`/
  `HeadlessTextureFactory` (none ever touch SDL video); `_setup_container(headless=True)`
  wires all four and zeroes `fps_target` so `Clock.tick(0)` skips its real-time sleep —
  ~50x faster in practice. Also fixed `Application.run()`'s unconditional
  `pygame.event.pump()`, which raised under a backend with no SDL video subsystem at all.
  Two scope adjustments: added `tests/integration/test_headless_backend.py` alongside
  (not replacing) `test_bootstrap_smoke.py`, since that test's job is exercising the real
  pygame/ModernGL branch BOOT-1/2/3 broke — swapping it to headless would've reopened that
  exact gap; left `games/validate_demos.py` untouched since it boots through the four
  separate `games/*/bootstrap.py` files **Bootstrap collapse** (fog, below) already tracks
  for replacement, not through `_setup_container()` at all.
- [Delete confirmed dead code](issues/20-delete-confirmed-dead-code.md) — deleted
  `pyguara/ecs/archetype.py`, `pyguara/error/`, and `games/XXX_scenes/`, all confirmed
  zero-reference. No surprises; executed exactly as specified.
- [Execute the input wiring and legacy retirement](issues/21-execute-input-wiring.md) —
  `GamepadManager` becomes the sole gamepad backend: `InputManager` subscribes to its
  already-dispatched `GamepadButtonEvent`/`GamepadAxisEvent` and translates them through
  the existing `_handle_input()`/`_handle_axis()` logic unchanged; `Application.run()` now
  calls `input_manager.update()` once per frame; `process_event()`'s `JOY*` branches,
  `_joysticks`, and `_detect_controllers()` deleted outright. `_cooldowns`/
  `InputAction.cooldown` removed (protocolo_bandeira/true_coral's own ability cooldowns
  untouched) — deleting the field fixed a real latent bug as a side effect: `InputAction`'s
  old field order silently stored `register_action()`'s `deadzone` argument into the
  `cooldown` field instead, so every action's real deadzone was always the `0.1` default.
  `IInputBackend` now mandatory; `bootstrap.py` and, empirically necessarily, all 9
  `games/*/bootstrap.py` register `PygameInputBackend` (confirmed each one raises
  `ServiceNotFoundException` otherwise — not otherwise touched, still **Bootstrap
  collapse**'s to replace). `tests/test_input.py` rewritten onto `IJoystick`/
  `IInputBackend` stubs — it patched `pygame.joystick` directly, not the protocol ticket
  10's answer assumed it already used.
- [Execute the event dispatcher hot-path fixes](issues/22-execute-event-dispatcher-hot-path.md)
  — `enable_history: bool = False` added, `deque(maxlen=1000)` regardless of the flag;
  `_global_listeners` and the Phase B dispatch block deleted outright; `dispatch()`
  rewritten to walk `type(event).__mro__` and process one merged, priority-sorted pass, so
  base-class subscription (`CollisionEvent`/`TriggerEvent`) now actually receives dispatched
  subclasses. No surprises; executed exactly as specified.
- [Drop nominal Protocol inheritance across the 14
  sites](issues/23-drop-nominal-protocol-inheritance.md) — site count grew to 24 on
  re-running the grep (the original `I`-prefix pattern missed `UIRenderer`/
  `TextureFactory`/`StorageBackend`/`Graph`/`Heuristic`; tickets 17/18/19 also added new
  sites of their own); dropped the explicit Protocol base at all 24, across 17 files, per
  the "one mechanical policy" framing. Deliberately left the ~20 `Event(Protocol)` dataclass
  sites alone — `Event` has no methods, so the stub-swallowing hazard doesn't apply there;
  that's field-inheritance, a different use of the same syntax. Verified with a real
  spot-check (deleted `PygameBackend.draw_rect`, confirmed `mypy` errors, restored it).
  Found and spun out rather than fixed: the ticket's DI-registration mypy-catch claim
  doesn't actually hold for 10 of the 13 protocols (the non-`@runtime_checkable` ones) —
  `register_instance()`/`register_singleton()`'s generics don't enforce the relationship —
  [Decide whether to harden DIContainer's generic
  signatures](issues/30-di-container-generic-safety-decision.md).
- [Execute Scene-owned world, SystemManager, and RenderSystem
  wiring](issues/24-execute-scene-owned-systems-and-rendersystem.md) — no global
  `EntityManager`/`SystemManager` in DI; each `Scene` builds and owns both, with
  `resolve_dependencies()` populating the four engine systems (100-399 priority band),
  `camera`, `render_system`, and `prefab_factory` before `on_enter()`; `Scene.render()` is
  concrete (submits visible `Sprite`s, flushes); `SceneManager` ticks each active scene's
  own `system_manager` and centrally enforces cleanup/pause/resume rather than trusting
  scene overrides to call `super()`. Deviated from "Done when" by proving the default
  `render()` path with a purpose-built test scene rather than migrating a real demo (out of
  scope) — investigating why turned up that the engine's own `Sprite` component didn't
  actually conform to `Component` (no `entity`/`on_attach`/`on_detach`; fixed by inheriting
  `BaseComponent`) and was never addable to a real entity, and that three sandbox tools
  (`EntityInspector`/`PhysicsDebugger`/`TransformGizmo`) resolved the now-removed global
  `EntityManager` at construction (fixed with a `Tool`-base `_entity_manager` property
  reaching through the current scene, matching `editor/layer.py`'s existing pattern). Also
  had to patch all 9 `games/*/bootstrap.py` (register `IAudioSystem`/`ComponentRegistry`/
  `PrefabCache`) — confirmed empirically each would break registering its first scene
  otherwise — same **Bootstrap collapse** territory, not otherwise touched.
- [Execute the ECS lifecycle contract](issues/26-execute-ecs-lifecycle-contract.md) —
  `remove_entity()` soft-dead immediately (detached callbacks, `_is_removed` set), physical
  `_component_index` cleanup deferred to a new `flush_pending_removals()`; every query path
  guards its yield against soft-removed-but-unswept ids, making single-type queries safe to
  iterate while `remove_entity()` runs mid-loop; `add_component()`/`remove_component()` now
  raise on a removed entity; new `EntityDestroyed` event dispatches synchronously at
  soft-death via an `_on_entity_removed` hook `Scene.resolve_dependencies()` wires up;
  `QueryCache` gets frozenset values and a `None`-vs-empty registered/unregistered
  distinction, reusing its existing `on_component_removed()` for entity-removal cleanup
  rather than a new API. Adapted "flush from `Application._fixed_update()`" to
  `SceneManager.fixed_update()` flushing each active scene's own `EntityManager`, since
  ticket 24 (executed earlier this session) already removed the global one this ticket's
  text assumed. Deliberately left `QueryCache.clear_cache()`'s rebuild-not-clear behavior
  alone — the audit flagged it, but ticket 06's Answer never actually decided to change it.
- [Execute the physics teardown bridge](issues/27-execute-physics-teardown-bridge.md) —
  `PhysicsSystem` subscribes to `EntityDestroyed` in `__init__`; `_on_entity_destroyed`
  reads `RigidBody` off the event's still-intact entity and queues its `_body_handle` (if
  any) into `self._pending_teardown`; `update(dt)` drains the queue via
  `self._engine.destroy_body(handle)` before the ECS→physics sync pass and before
  `self._engine.update(dt)` steps the space. `PymunkEngine.destroy_body()` removes the
  body and all its shapes from `self.space` and drops the `self._bodies` entry, guarded
  the same way `add_shape()` guards a missing `self.space`. Executed exactly as specified
  from ticket 15, no deviations.
- [Execute the ModernGL shape shader](issues/25-execute-moderngl-shape-shader.md) —
  `shape.vert`/`shape.frag` implement the unified box/circle/capsule SDF shader exactly as
  decided; `ModernGLRenderer` gains three independent instance buckets (rect/circle/line),
  each grown like the existing sprite instance buffer, flushed as one instanced draw call
  per non-empty bucket at `end_frame()`. Filled in a detail the decision ticket left open:
  a stroked shape's border needs its instance quad padded by `width/2` beyond the shape's
  true half-extent (else the outer half of the border clips), recovered back out in the
  fragment shader. `PygameBackend` untouched. Tested via instance-buffer assertions (no
  pixel-readback harness exists), per the ticket's own escape hatch. Gap found and spun
  out rather than fixed: [Native Color and Rect value types](05-native-color-and-rect.md)
  (ticket 05) was never executed — `Color`/`Rect` still subclass `pygame.Color`/
  `pygame.Rect` today — despite not actually blocking this ticket. [Execute Native Color
  and Rect value types](issues/31-execute-native-color-and-rect.md).
- [Execute the scene lifecycle repair](issues/29-execute-scene-lifecycle-repair.md) —
  `TransitionManager.start_transition()` takes `on_from_hidden`/`on_to_shown` callbacks,
  firing together at the two-phase midpoint or immediately at single-phase start (removes
  the hardcoded `on_exit`/`on_enter` calls that caused SCENE-1); `SceneManager` maps each
  operation's callbacks per the decision, substituting the existing
  `_exit_scene`/`_resume_scene` wrappers (not bare hook calls) so ticket 24's
  system-manager-cleanup guarantee survives the new callback path. `_stack: List[StackEntry]`
  replaces the parallel `_scene_stack`/`_pause_below_flags` arrays, fixing SCENE-2's
  off-by-one via a direct pause_below-per-entry mapping instead of index arithmetic.
  `cleanup()` unwinds LIFO; `Application.__init__` now calls `set_screen_size()` with the
  real window dimensions. Following the decision's callback wiring fixed pop_scene's
  synchronous-exit-before-transition bug as a direct consequence, not a separate fix.
- [Execute Native Color and Rect value types](issues/31-execute-native-color-and-rect.md)
  — `Color`/`Rect` are now `@dataclass(slots=True)`, no pygame base class; only the
  pygame backend converts, via new `graphics/backends/pygame/conversions.py`. Both types
  keep their existing surface (mutability, `from_hex`/`normalized`/`lerp`,
  `top`/`left`/`right`/`bottom`/`centerx`/`centery`/`contains_point`) and gain the
  decided additions (Color HSV + named constants, Rect `colliderect`/`contains`/
  `inflate`). `CHANGELOG.md` gets the `BREAKING` entry. Found and fixed beyond the
  ticket's file list: `pygame_window.py`'s `clear()` had the same pygame-Color bug;
  `ModernGLRenderer.set_viewport()` indexed `Rect` (fixed via attribute access, not by
  adding `__getitem__`); `Viewport(Rect)` (the one real `Rect` subclass) called the now-gone
  `collidepoint()`; `Color` gained `__getitem__`/`__len__` since three rendering/lighting
  files do index `Color` instances. `PygameUIRenderer`, named in the ticket, needed no
  changes — it already converted independently. First dedicated test file for
  `common/types.py` (`tests/test_common_types.py`), plus real-pixel assertions added to
  the pygame backend's integration tests.
- [Decide whether GridGraph should prevent diagonal
  corner-cutting](issues/28-diagonal-corner-cutting-decision.md) — yes, unconditionally:
  `GridGraph.get_neighbors()` refuses a diagonal move when either flanking orthogonal
  cell is a wall, matching the deleted `GridMap`, with no opt-in flag since no consumer
  needs the permissive behavior. Edge case resolved by checking the deleted `GridMap`'s
  actual git history rather than deciding fresh: an out-of-bounds flanking cell blocks
  the diagonal too. Lands as [Execute the diagonal corner-cutting
  fix](issues/32-execute-diagonal-corner-cutting-fix.md).
- [Execute the diagonal corner-cutting
  fix](issues/32-execute-diagonal-corner-cutting-fix.md) — `GridGraph.get_neighbors()`
  gained a `_is_walkable()` helper and refuses a diagonal move when either flanking
  orthogonal cell fails it (wall or out of bounds), unconditionally. Four new tests;
  all 40 pre-existing pathfinding tests traced and confirmed unaffected. Executed
  exactly as specified, no deviations.
- [Decide whether to harden DIContainer's generic
  signatures](issues/30-di-container-generic-safety-decision.md) — the current API
  shape can't be hardened at mypy-time at all (confirmed via isolated repro: mypy solves
  a shared unbound TypeVar across two argument positions by joining to `object`, which
  trivially satisfies it; `@overload` per protocol would work but couples the generic
  container to every subsystem's protocols, rejected). Decided: mark the 10
  non-`@runtime_checkable` protocols `@runtime_checkable` and add an `isinstance()`
  assert inside `register_instance()` only — not `register_singleton`/`transient`/
  `scoped`, since those only have the class (needing `issubclass()`, which crashes on
  the 3 of these 10 protocols that have `@property` members) at registration time, and a
  `try/except` fallback there would silently no-op exactly where it matters most.
  Verified this scope covers 100% of current risk: no protocol is ever registered via
  the class-based methods today. Lands as [Execute the DIContainer runtime safety
  check](issues/33-execute-di-container-runtime-safety-check.md).
- [Execute the DIContainer runtime safety
  check](issues/33-execute-di-container-runtime-safety-check.md) — all 10 protocols
  marked `@runtime_checkable`; `register_instance()` gained an `isinstance()` assert,
  scoped to Protocol interfaces only (`_is_protocol`) after the full suite caught a real
  gap the grilling session missed: `RenderGraph` is a concrete class that BOOT-1
  deliberately registers a non-subclass stub against, so an unconditional check broke
  it. Also found and fixed three test fixtures passing bare `MagicMock()` (no `spec=`)
  against protocol interfaces, which turns out to fail `isinstance()` against a
  `@runtime_checkable` protocol despite `hasattr()` succeeding per-method.

- [Decide whether to move PlatformerController/TriggerVolume logic into Systems now
  ](issues/34-platformer-trigger-component-logic-decision.md) — stands alone, resolved
  now. Mutating logic moves to a System when one exists to own it (`PlatformerController`'s
  input methods become a `pending_input: PlatformerInput` field read by `PlatformerSystem`;
  `reset_jump_state()` moves onto `PlatformerSystem`); a trivial single-field mutator with
  no natural System destination gets deleted and inlined instead (`TriggerVolume.clear()`,
  `EntityTags.add_tag()`/`remove_tag()`, the latter having zero production callers at all).
  Pure predicates (`can_jump()`, `matches_tags()`, `has_tag()`, etc.) stay on the components
  unchanged regardless — read-only means there's no ownership question to resolve. Lands as
  [Execute the PlatformerController/TriggerVolume logic
  move](issues/40-execute-platformer-trigger-logic-move.md).

- [Decide how dev tools should consume input instead of raw pygame events
  ](issues/35-dev-tools-raw-pygame-input-decision.md) — deferred, not decided.
  Genuinely more loaded than a relocation: tools intercept raw events *before*
  `InputManager` translates them today, so consuming via `InputManager`'s translated
  output would invert priority order and change what "consume" even means (prevent
  translation vs. veto an already-dispatched event); `InputManager`'s context system
  is dead (`UI`/`MENU` contexts unused, `_context` never switches from `GAMEPLAY`), so
  there's no separate editor context to bind shortcuts into without building that
  first. Revisit when a real non-pygame backend arrives or the context system gets
  built out for other reasons — graduated to **Not yet specified** rather than
  closed silently.

- [Decide how Checkbox should compute its layout size without mutating state in
  render()](issues/36-checkbox-layout-mutation-decision.md) — decided now, cheap fix.
  Corrected the ticket's own premise first: `UIElement.apply_layout()`/
  `LayoutConstraints` are dead code, never invoked anywhere; the only live layout path
  is `BoxContainer.layout()`, called once per scene setup, before any renderer exists
  in scope. Also found `Checkbox` is entirely unused (zero games/tests instantiate
  it), so the reported bug has never actually fired. New `measure(renderer)` hook on
  `UIElement` (no-op default), overridden by `Checkbox` and both `Label` classes,
  moves the `get_text_size()`-and-mutate logic out of `render()`; `BoxContainer.
  layout(renderer)` calls it on each child before stacking math; `render()` still
  calls it too, for standalone (non-contained) widgets. Renderer reaches the call
  site via `self.container.get(UIRenderer)`, one line. Found and spun off rather than
  fixed here: `label.py` and `text.py` define two independently-diverging `Label`
  classes, with the public API exporting one and every game importing the other —
  [Decide which Label class is canonical](issues/41-canonical-label-class-decision.md).
  Lands as [Execute the Checkbox/Label layout measure()
  hook](issues/42-execute-checkbox-layout-measure-hook.md).

- [Decide which Label class is canonical](issues/41-canonical-label-class-decision.md)
  — `text.py`'s `Label` wins (already the public API's export, and a strict superset
  of `label.py`'s — adds `anchor`/`_auto_size`, identical defaults otherwise);
  `label.py`'s gets deleted outright, no merge needed. Verified zero behavioral
  divergence across all 13 real call sites (none use `anchor`/`set_text()`) and that
  `Label` is the only duplicate-class-name pattern in `ui/components/` (AST-scanned).
  No `CHANGELOG.md` entry — nothing observable changes for any caller. Lands as
  [Execute the canonical Label merge](issues/43-execute-canonical-label-merge.md).

- [Decide how fixed-timestep render interpolation should work
  ](issues/37-fixed-timestep-interpolation-decision.md) — deferred, not decided.
  Its own premise assumed a `Transform`→`Sprite` position sync exists for
  interpolation to hook into; verified it doesn't (only a docstring-comment example,
  never executed code) — any `Transform`-driven entity submitted through `Scene.
  render()`'s default path renders at a `Sprite.position` nothing currently updates.
  Blocks on [Decide how Transform position syncs to Sprite for rendering
  ](issues/44-transform-sprite-sync-decision.md) — interpolation's actual shape
  depends on whatever sync mechanism that lands on, so returns to **Not yet
  specified** rather than being decided in the abstract first.

- [Decide how Transform position syncs to Sprite for rendering
  ](issues/44-transform-sprite-sync-decision.md) — no sync system; `Sprite.position`
  is documented as an offset ("combined with entity Transform for final rendering
  position"), so overwriting it would silently destroy that offset every frame, same
  mutation-smell class as the Checkbox ticket. Instead, `Scene.render()`'s existing
  default loop computes `transform.position + sprite.position` at submission time
  (falling back to `sprite.position` alone when there's no `Transform`) and passes it
  through a new optional `position` parameter on `RenderSystem.submit()` — never
  written back to `sprite.position`. Runs after all of the tick's fixed-update work
  by construction (it's in `render()`), sidestepping a priority-ordering dependency
  on physics/platformer joining `SystemManager` (still-open **Demo migration** fog).
  Purely additive — doesn't reopen *Scene-owned world and SystemManager* or
  *RenderSystem wiring*. Unblocks and graduates [Decide how fixed-timestep render
  interpolation should work, now that Transform-Sprite sync exists
  ](issues/45-fixed-timestep-interpolation-decision-v2.md) (supersedes the original,
  deferred [ticket 37](issues/37-fixed-timestep-interpolation-decision.md)). Lands as
  [Execute the Transform-Sprite position
  combination](issues/46-execute-transform-sprite-sync.md).

- [Decide how fixed-timestep render interpolation should work, now that
  Transform-Sprite sync exists](issues/45-fixed-timestep-interpolation-decision-v2.md)
  — opt-in via `Transform.interpolate: bool = False` (a flag, not a separate marker
  component — fits `Transform`'s existing internal-flag pattern like `_is_dirty`).
  `previous_position` snapshot is centralized once per fixed tick, at the very start
  of `SceneManager.fixed_update()`, before any system runs — not duplicated across
  Steering/Physics/Platformer, same reasoning that ruled out a sync system in ticket
  44. `alpha` reaches `Scene.render()`'s combination logic (ticket 44's formula,
  extended) as a `self.render_alpha` attribute set by `SceneManager.render()`, not a
  new parameter on `Scene.render()` — avoids a mechanical signature ripple across all
  9 demo overrides for a value only the base default path uses. `Camera2D` ruled out
  of scope: its `CameraFollowSystem` already smooths every variable-rate frame via
  its own deadzone/lerp mechanism, no fixed-rate discretization artifact to correct.
  Lands as [Execute fixed-timestep render
  interpolation](issues/47-execute-fixed-timestep-interpolation.md) (depends on
  [Execute the Transform-Sprite position
  combination](issues/46-execute-transform-sprite-sync.md) landing first).

- [Decide how live-tweakable values should work in the sandbox inspector
  ](issues/38-live-tweakables-decision.md) — automatic dataclass/`__dict__`
  introspection (matching 3 existing precedents in this codebase — `persistence/
  serializer.py`, `ui/theme.py`, `EntityInspector` itself), not a decorator or manual
  registry. Covers both domains as two `Tool` subclasses sharing one edit-control
  dispatch: `EntityInspector` gets its existing read-only field display made
  editable (writes back via `setattr`); a new `ConfigInspector` tool walks
  `GameConfig`'s dataclass tree, since global config isn't attached to any entity.
  Type dispatch: bool toggle, int/float stepper (no range metadata exists for
  sliders), Enum cycle, `Color` recurses generically (a real dataclass since ticket
  31), `Vector2` special-cased (subclasses `pymunk.Vec2d`, not a dataclass).
  Export is config-only, via the already-existing `ConfigManager.save()` — prefab
  export doesn't exist as a mechanism and isn't built here. Lands as [Execute the
  live-tweakable inspector tools](issues/48-execute-live-tweakable-inspector.md).

- [Decide on a declarative builder API for UI hierarchies
  ](issues/39-declarative-ui-builder-decision.md) — architecture settled without
  needing a prototype: opt-in sugar coexisting indefinitely alongside today's
  imperative API (not a replacement — avoids overlapping the separate, larger **Demo
  migration** fog for a purely ergonomic change); callbacks need no new mechanism
  (`on_click` is already a bare post-construction attribute assignment in every
  demo, the builder just does the same thing); theming needs no wiring
  (`UIElement.__init__` already calls `get_theme()` unconditionally). The one open
  question — DSL syntax ergonomics — isn't answerable from the codebase's current
  state, so it's spun off rather than decided in the abstract: [Prototype the
  declarative UI builder API](issues/49-prototype-ui-builder.md).

- [Execute the PlatformerController/TriggerVolume logic
  move](issues/40-execute-platformer-trigger-logic-move.md) — executed exactly as
  specified. `PlatformerController` gained `PlatformerInput`/`pending_input`, lost
  its four movement methods and `reset_jump_state()` (moved onto `PlatformerSystem`,
  called from both its internal call site and the respawn handler);
  `TriggerVolume.clear()`/`EntityTags.add_tag()`/`remove_tag()` deleted in favor of
  direct field mutation. One quirk preserved deliberately: `PlayerControlSystem`'s
  `PlayerJumpedEvent` dispatch guard was already dead code (always true), simplified
  to match without changing the pre-existing "fires even for a rejected jump"
  behavior — not this ticket's job to fix. Full suite green (1122 passed), all 4
  demos verified, `ruff`/`mypy` clean.

- [Execute the Checkbox/Label layout measure()
  hook](issues/42-execute-checkbox-layout-measure-hook.md) — executed exactly as
  specified. `UIElement.measure(renderer)` (no-op default) added; `Checkbox` and
  both `Label` classes override it, moving their `render()`-time sizing logic out;
  `BoxContainer.layout()` gained a required `renderer` parameter and calls
  `measure()` on every visible child before stacking math. New regression test
  proves the fix (two differently-sized `Label`s, sibling position reflects real
  measured height, not the placeholder). Found and closed rather than left implicit:
  `games/ui_scene_graph`'s `MenuScene` is the one `container.layout()` call site
  `validate_demos.py` doesn't cover — verified manually via a throwaway harness.
  Full suite green (1123 passed), `ruff`/`mypy` clean.

- [Execute the Transform-Sprite position
  combination](issues/46-execute-transform-sprite-sync.md) — executed exactly as
  specified. `RenderSystem.submit()` gained an optional `position` override,
  `Scene.render()`'s default loop computes `transform.position + sprite.position`
  without ever mutating `sprite.position`. Three new regression tests (offset
  combination, standalone fallback, live recomputation across two `render()` calls
  with no system tick) extend ticket 24's existing headless-application-based
  suite. Full suite green (1126 passed), all 4 demos verified, `ruff`/`mypy` clean.
  Unblocks [Execute fixed-timestep render
  interpolation](issues/47-execute-fixed-timestep-interpolation.md).

- [Execute the canonical Label merge](issues/43-execute-canonical-label-merge.md) —
  executed exactly as specified, `label.py` deleted. Found a 5th real caller the
  ticket's text didn't list (`tests/test_ui_components.py`) via grep before editing;
  updated it too. No behavior change anywhere. Full suite green (1123 passed,
  unchanged count), all games boot clean, `ruff`/`mypy` (216 files) clean.

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
  Depends on demo migration. Should pick up headless-backend wiring when it lands —
  `validate_demos.py` currently boots each demo through its own
  `games/*/bootstrap.py`'s hand-rolled `configure_game_container()`, none of which go
  through `_setup_container()`, so [Wire HeadlessBackend as the integration-suite test
  backend](issues/19-wire-headless-test-backend.md) left it on the real Pygame backend
  rather than wiring headless into four separate soon-to-be-deleted files.
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
- **Dev tools' input consumption.** `TransformGizmo`/`EntityInspector`/`ToolManager`
  parse raw pygame key events directly instead of going through `InputManager`,
  duplicating translation logic. Not ticketable yet: fixing it means either building
  real context-switching (`InputContext.UI`/`MENU` are currently dead — never bound,
  never switched to) so tools get their own binding context, or redefining what
  "consume" means once translation must happen before tools see an event instead of
  after. Revisit when a real non-pygame-windowed backend is on the roadmap, or when
  the input-context system gets built out for its own reasons. See [Decide how dev
  tools should consume input instead of raw pygame
  events](issues/35-dev-tools-raw-pygame-input-decision.md) for the full investigation.
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
