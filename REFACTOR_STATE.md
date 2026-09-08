# PyGuara Refactor State

Shared memory for the incremental subsystem audit. One subsystem per iteration:
audit (Phase A) -> tests (Phase B) -> docs (Phase C) -> approval -> next.

**Started:** 2026-09-06
**Method:** Never analyse more than one subsystem at a time. Every finding that
touches a *different* subsystem gets parked under "Cross-Cutting Concerns"
rather than fixed in place.

---

## How to resume

1. Read **Completed Subsystems** for what is done and **Pending Subsystems**
   for what is next. The queue is ordered by dependency depth: foundations
   first, leaves last.
2. Read **Cross-Cutting Concerns**. Anything found that spans subsystems is
   parked there rather than fixed in place, and several are now GitHub issues.
3. Take the next unticked subsystem. For each one, in order:
   - **Phase A** — audit the code. Reproduce every suspected defect with a
     throwaway probe *before* fixing it. Reading is not enough: every
     significant defect this audit has found looked correct on a read-through
     and was obvious under a probe.
   - **Phase B** — audit the tests. Look for uniform setup rather than missing
     coverage; that is what has hidden most bugs here (see the note below).
   - **Phase C** — audit the docs, and verify the documented API actually
     exists. Three pages have described functions that never existed.
4. Branch from `main` — see "Branching and Pull Requests" in `CLAUDE.md`.
5. Verify each commit **in a clean checkout**, not the working tree:
   `git worktree add --detach <tmp> <sha>` then run the suite there. A working
   tree can pass with unstaged changes the commit does not contain; that has
   happened once.
6. Log the iteration at the bottom of this file and open a PR.

### Two patterns worth carrying forward

**Guards that return a wrong answer.** Four graphics slices and one DI
iteration turned up the same shape: a check that avoids a crash by
substituting a plausible-looking wrong value. `safe_zoom = 0.001` gave
coordinates six orders of magnitude out; `window_ratio ... else 0` gave a
450px viewport for a 0px window. In each case the crash would have been easier
to diagnose. Grep for `if x != 0 else`, `or 1`, and bare `except: pass`.

**Uniform test setup, not missing tests.** The blind spot has repeatedly been
that every existing test built its subject the same way. `test_query_cache.py`
always used `create_entity()`, so an `add_entity()` bug survived;
`test_config.py` always mocked the filesystem, so no round-trip bug could
surface; every DI test was single-threaded, so a missing lock survived. Ask
how the subject is *constructed*, not just what is asserted.

---

## Active Subsystem

`pyguara/physics` — **in progress, subsystem not closed.**
`fix/physics-collision-tunnelling` merged to `main` as **PR #25** (its first
commit went out earlier, alone, as PR #24). Symptom-driven so far: six
defects found and fixed from reported bad collision behaviour, plus one-way
platforms, a collider debug overlay, and the character-mover switch.

The systematic pass over `collision_system`, `trigger_volume`/`trigger_system`
and `joints` is now done on branch `refactor/physics-triggers-joints-audit`:
trigger volumes and the entire `Joint` layer were both inert end to end and
are now built and tested (see the iteration log entry below). Phase B for
those files is done with it.

**To close the subsystem** (one more slice, cut fresh from `main`):

- **Expose the remaining pymunk spatial queries** — `point_query`,
  `shape_query`/`bb_query`, multi-hit `segment_query`. Only `raycast` and
  `overlap_box` are exposed; the rest rule out click-picking, explosion
  radii, melee arcs, piercing shots and "can I fit here". Small backend +
  `IPhysicsEngine` additions. Dependency for the projectile layer in
  issue #28.
- **Body sleeping** — honour `space.sleep_time_threshold`. Every idle body
  is simulated forever; a room-based game carries a lot of settled props
  and debris. Small, pymunk-native.
- **Resolve the `physics.substeps` default** (4 vs 2 — 4 costs ~half a
  60Hz frame at 200 dynamic bodies).
- **Phase C** (subsystem docs) and a last read of `materials.py`,
  `tilemap.py`, `debug_draw.py`.

**Next physics slice, its own build/PR (`CharacterMover`-sized):** a
**top-down kinematic character controller** — 8-directional collide-and-slide
with actor-vs-actor soft separation and push-out-of-overlap. The physics
layer currently serves only platformers; every game the engine targets is
top-down, and dynamic bodies there hit the same sink/creep/jitter family the
platformer did, plus crowd stacking. Platformer polish (slope handling,
variable jump height, corner correction) and `surface_velocity` (conveyors)
are **parked as low priority** given the genre.

Framework-level work above physics — combat spine, seeded RNG service,
stat/modifier system, projectile layer, procgen, tilemap, run/meta save
split, flow-field pathfinding, hit-stop, combat juice, local co-op input —
is **issue #28 (roguelike core)**, out of scope for the physics audit.
Prior art: `github.com/Wedeueis/reclaimer_legacy`, an earlier iteration of
this engine (fused with one game, hence the restart) that already built and
tested combat, stats, equipment/modules, procgen, GOAP/utility AI and
projectiles — read its `reclaimer/game/<subsystem>` module before starting
the matching #28 piece.

**The big decision — move characters off dynamic rigid bodies onto
`CharacterMover` — is resolved, built, and merged.** Full physical parity
(knockback, platform riding, crate pushing), on Celeste's model. See
`docs/physics/character-movement.md` for the shape it took; the summary:
`CharacterBody` replaces `RigidBody` for a character (no engine shape at
all), `SolidMover`/`SolidSystem` carry and push actors for moving platforms
and crates, `apply_knockback()` gives `Hazard.knockback_force` something to
consume. `guara_falcao` has a demo patrolling platform and a pushable crate.

**Tier 2 is complete:** `config`, `application`, `scene`, `systems`.
`pyguara/graphics` is complete too — see Completed Subsystems below.

---

## Pending Subsystems

Ordered roughly by dependency depth: foundations first, leaves last.

### Tier 1 — Foundations (no intra-engine dependencies)
- [x] `pyguara/common` — Vector2, Color, Rect, shared components *(done)*
- [x] `pyguara/log` — logging facade *(done)*
- [x] `pyguara/events` — EventDispatcher, Event protocol *(done)*
- [x] `pyguara/di` — DIContainer, auto-wiring, lifetimes *(done)*

### Tier 2 — Core runtime
- [x] `pyguara/ecs` — Entity, Component, EntityManager, QueryCache *(done)*
- [x] `pyguara/config` — configuration loading/merging *(done)*
- [x] `pyguara/application` — Application loop, bootstrap, sandbox *(done)*
- [x] `pyguara/scene` — Scene base, SceneManager, serializer *(done)*
- [x] `pyguara/systems` — system manager / base systems *(done)*

### Tier 3 — Subsystems
- [x] `pyguara/graphics` — ~8,000 lines, audited in five slices:
    - [x] 1. Window boundary — `window.py`, `IWindowBackend` *(active)*
    - [x] 2. Components — camera, particles, animation, geometry, sprite *(active)*
    - [x] 3. Backends — pygame, ModernGL, headless renderers *(active)*
    - [x] 4. Pipeline — graph, passes, framebuffer, viewport, batching *(active)*
    - [x] 5. Assets & effects — spritesheet, ninepatch, materials, vfx, lighting *(active)*
- [ ] `pyguara/physics` — protocols, pymunk backend, joints, materials
    - [x] Character movement switched to `CharacterMover` (PRs #24, #25)
    - [x] `collision_system.py`, `trigger_volume.py`, `trigger_system.py`,
      `joints.py` — triggers + joints rebuilt end to end
      (branch `refactor/physics-triggers-joints-audit`)
    - [ ] Phase C (docs) for the subsystem as a whole; final read of
      `materials.py`, `tilemap.py`, `debug_draw.py`
- [ ] `pyguara/input` — input manager, rebinding
- [ ] `pyguara/audio` — audio manager, spatial audio
- [ ] `pyguara/animation` — tween, easing, FSM
- [ ] `pyguara/resources` — loaders, meta, hot reload
- [ ] `pyguara/persistence` — save/load, migration
- [ ] `pyguara/ai` — FSM, steering, pathfinding, navmesh, behaviour trees

### Tier 4 — Tooling & authoring
- [ ] `pyguara/ui` — layout engine, widgets, theming
- [ ] `pyguara/prefabs` — prefab definition and instantiation
- [ ] `pyguara/editor` — in-engine editor, inspector tools
- [ ] `pyguara/scripting` — coroutines, script hosting
- [ ] `pyguara/replay` — deterministic replay
- [ ] `pyguara/dev` — dev-only helpers
- [ ] `pyguara/cli` — command line entry points
- [ ] `pyguara/tools` — atlas/build tooling

---

## Completed Subsystems

| Subsystem | Closed | Summary |
| --- | --- | --- |
| `pyguara/graphics` | 2026-09-06 | Audited in five slices: window boundary, components, backends, pipeline, assets. Window reported the requested size not the granted one; `Box`/`Circle` were hard-wired to pygame; the pygame stubs had drifted; a zero-height window produced a 450px viewport; nine-patch produced negative source rects. PRs #12, #14, #15, #17, #18. |
| `pyguara/systems` | 2026-09-06 | Fixed every game system starting up uninitialised (`initialize()` runs before `on_enter()`), an `unregister()` testing truthiness rather than `None`, and silent duplicate registration keys. PR #11. |
| `pyguara/scene` | 2026-09-06 | Fixed `switch_to()` abandoning every stacked scene, unguarded re-entrancy during transitions, and a `pop_scene()` that stranded the scene it returned to. PR #10. |
| `pyguara/application` | 2026-09-06 | Fixed an event budget spent per fixed step (15x per lagged frame), a `shutdown()` that skipped everything after the first failure, and three lifecycle events with no publisher. PR #8. |
| `pyguara/config` | 2026-09-06 | Fixed `Color` not surviving a save/load round trip (a second-launch crash), `fixed_dt` dividing by zero unvalidated, and `update_setting` accepting wrong types and out-of-range values. PR #7. |
| `pyguara/log` | 2026-09-06 | Fixed source attribution (every record reported `logger.py:138`), a `shutdown()` that did not stop logging, handler clobbering on a process-global logger, and a docs page describing a nonexistent API. PR #5. |
| `pyguara/di` | 2026-09-06 | Fixed a missing lock in `DIScope.get()` that fabricated circular dependencies under concurrency (140/160 resolutions), plus captive lifetimes, dead-scope resolution, silent re-registration and varargs injection. PR #4. |
| `pyguara/events` | 2026-09-06 | Broke a latent `log` <-> `events` import cycle, fixed a timestamp sentinel that made 0.0 inexpressible, brought filter errors under the error strategy, and memoised handler resolution (5.7us -> 3.1us per dispatch). PR #3. |
| `pyguara/common` | 2026-09-06 | Fixed `Transform.up` pointing down, an unguarded parent cycle and a falsy-`Vector2` default; renamed `Vector2.rotate` to `rotate_degrees`; wrote the first tests for `Vector2` and `Transform`. PR #2. |
| `pyguara/ecs` | 2026-09-06 | Fixed two silent query bugs (`add_entity()` bypassing the query cache; dead-entity resurrection), replaced the private removal hook with a subscribe/unsubscribe API, and modernised the module. PR #1. |

---

## Tracked as GitHub issues

Concerns that outgrew this file, or that need a decision rather than a fix:

| Issue | Subject |
| --- | --- |
| [#9](https://github.com/Wedeueis/pyguara/issues/9) | pygame reaches into the backend-agnostic core (CC-11) — nine non-backend files across five subsystems |
| [#16](https://github.com/Wedeueis/pyguara/issues/16) | `IFramebuffer`/`IRenderPass` not `runtime_checkable`; `IRenderPass` vs `BaseRenderPass(ABC)` overlap |
| [#19](https://github.com/Wedeueis/pyguara/issues/19) | ~2,700 lines of GPU-dependent graphics code are read-audited only, with no headless GL coverage |
| [#23](https://github.com/Wedeueis/pyguara/issues/23) | `camera.rotation` is applied by `Camera2D.world_to_screen` but ignored by the render path; three definitions of world-to-screen disagree |
| [#28](https://github.com/Wedeueis/pyguara/issues/28) | Roguelike core — framework-level subsystems the target genre needs (combat spine, seeded RNG service, stat/modifier system, projectile layer, procgen, tilemap, run/meta save split, flow-field pathfinding, hit-stop, combat juice, local co-op input) |

---

### Out-of-band: render pipeline snapshots (PR #22)

Not a queued subsystem. Adding Syrupy snapshots of the backend call stream
`RenderSystem.flush()` produces turned up a live defect on the first run.

**Found:** the batcher added `viewport.position` to `viewport.center_vec`,
which is already absolute — the viewport origin was counted twice, displacing
everything by it. Invisible at fullscreen (origin `(0,0)`), so 1514 tests
passed over it. Pre-existing from `bb5fa03`, unchanged at `35ed7fa`.

**Latent, not shipped:** nothing produces an offset viewport.
`RenderSystem.flush()` has one call site passing none, `WorldPass._viewport`
is never set, `Viewport.create_best_fit` has no production callers, and no
config option letterboxes.

**The deeper defect:** `particles.py` already had the transform right. Two
copies of one formula had drifted apart, and under a letterboxed viewport
they disagreed by the viewport origin — which would have presented as
particles detaching from the sprites emitting them, not as a uniform shift.
Both now call `Camera2D.screen_offset()`; a test pins them together.

**Pattern, third instance:** the recurring blind spot here is uniform setup,
not missing coverage. Every existing viewport test used a fullscreen
viewport, exactly as every query-cache test used `create_entity()` and every
config test mocked the filesystem.

**Left open:** issue #23, camera rotation.

## Cross-Cutting Concerns

Architectural issues that span subsystems. Do **not** fix these inside a
single-subsystem iteration; schedule a dedicated pass.

### CC-1 — RESOLVED 2026-09-06 — Ruff `target-version` was `py39`
`pyproject.toml` pins `target-version = "py39"` while `requires-python` is
3.12+. Ruff therefore refuses modernisation fixes engine-wide, which is the
root cause of the legacy `typing.Dict`/`Optional[X]` style found in every
module audited so far. **Fix:** bump to `py312` and enable the `UP`
(pyupgrade), `B` (bugbear) and `D` (pydocstyle, `convention = "google"`) rule
sets in one deliberate formatting commit, so per-subsystem diffs stay
reviewable.
Bumped to `py312` and enabled `UP`, `B`, `I`, `SIM`. 1455 findings fixed
mechanically, the rest by hand. Surfaced one real defect: a mutable `Color`
shared as a default argument in `WorldPass`.
*Discovered in:* `ecs`. *Status:* **resolved**.

### CC-2 — RESOLVED 2026-09-06 — Lint rule set was minimal
No pydocstyle, no bugbear, no pyupgrade, no complexity ceiling. Google-style
docstrings (mandated by this refactor) are therefore unenforced and will drift
straight back.
Resolved with CC-1. Ruff's `D` rules stay off deliberately: pydocstyle runs as
its own hook, and two tools disagreeing about docstring style is worse than one
enforcing it. That hook was also found to be mis-scoped -- it used a `match:`
key pre-commit does not recognise, so it had been linting the whole repository
instead of `pyguara/`.
*Discovered in:* `ecs`. *Status:* **resolved**.

### CC-3 — Internal ticket ids leak into public docstrings
Strings like `P1-008` appear in user-facing API docstrings (`EntityManager
.register_cached_query`, `QueryCache` module header) and in test module
docstrings. Tracker ids are not documentation. **Fix:** sweep
`grep -rn "P[0-9]-[0-9]" pyguara/ tests/` once the per-subsystem passes are
done.
*Discovered in:* `ecs` (removed there). *Status:* open elsewhere.

### CC-4 — Unverifiable benchmark numbers embedded in docstrings
Hard-coded claims ("~8ms for 10,000 entities", "8x faster") sit in docstrings
with no benchmark backing them in CI. They are untestable and rot silently.
**Fix:** move to `.benchmarks/` with an actual `pytest-benchmark` run, and
reference the benchmark rather than restating a number.
*Discovered in:* `ecs` (removed there). *Status:* open elsewhere.

### CC-5 — `EntityManager` internals reached into from outside the package
**Removal hook: RESOLVED (2026-09-06).** `_on_entity_removed` was a single
callback slot assigned directly by `pyguara/scene/base.py`, so any second
observer would have silently displaced the scene's `EntityDestroyed` dispatch.
Replaced with `subscribe_entity_removed()` / `unsubscribe_entity_removed()`,
which fan out to every subscriber, dedupe by equality (so a bound method
subscribed twice notifies once), and tolerate unsubscription during
notification. `Scene`, `tests/test_ecs.py` and `tests/test_physics.py` migrated;
no references to the private attribute remain anywhere in the tree.

**Still open:** `Entity._components` and `_on_component_added` are read across
module boundaries — by `EntityManager` itself (acceptable, same package) and by
serialisation and prefab code (not). Audit when `persistence` and `prefabs` come
up; the likely fix is a public read-only components view.
*Discovered in:* `ecs`. *Status:* partially resolved.

### CC-6 — Component data-purity is advisory, not enforced
`BaseComponent` only *warns* on logic methods; `StrictComponent` errors but is
opt-in and, at the time of the `ecs` audit, had no adopters outside tests.
**Named offender:** `common.Transform` sets `_allow_methods = True` and carries
the whole parent hierarchy, world-transform caching and coordinate conversion
(~330 lines). It is the largest violation in the engine and the one a
`TransformSystem` would have to absorb; every other subsystem touches it, so it
is deliberately not attempted piecemeal. **Fix:** once `physics`, `ui` and `ai`
are audited and the true extent is known, migrate the tree to `StrictComponent`
and consider making it the default.
*Discovered in:* `ecs`; offender identified in `common`. *Status:* parked.

### CC-10 — RESOLVED 2026-09-06 — Documentation described APIs that do not exist
`docs/core/logging.md` documented `pyguara.log.config.setup_logging()` and
`pyguara.log.config.get_logger()`. Neither the module nor the function exists
anywhere in the tree; every code sample on the page raised
`ModuleNotFoundError`. Nothing catches this, because docs are never executed.
**Fix:** enable `pytest --doctest-glob='*.md'` over `docs/`, or add a smoke
test that imports every symbol the docs reference. Until then, treat "verify
the documented API actually exists" as an explicit Phase C step in every
iteration.
`tests/test_docs_api.py` now extracts every `pyguara...` import and backticked
dotted reference from the Markdown under `docs/` and asserts it resolves. It
immediately found two more: `docs/core/application.md` documented an entire
error hierarchy (`pyguara.error`, `EngineException`, `@safe_execute`, `@retry`)
that has never existed, and `PROJECT_STRUCTURE.md` referenced
`create_application_container` instead of `create_application`. Both fixed.
*Discovered in:* `log`. *Status:* **resolved**.

### CC-9 — RESOLVED 2026-09-06 — `ErrorHandlingStrategy` was defined twice
`pyguara/di/types.py` and `pyguara/events/types.py` each declare their own enum
of the same name with identical members (LOG / RAISE / IGNORE) and identical
semantics. They are not interchangeable -- `di.RAISE != events.RAISE` -- so
passing one where the other is expected fails a comparison silently rather than
loudly. **Fix:** hoist a single definition to a shared home once more
subsystems are audited and the full set of consumers is known; `di` must not
import `events` (see CC-8) so it cannot simply re-export.
Hoisted to a new top-level `pyguara/errors.py`, which imports nothing from the
engine and so cannot cycle. `di/types.py` and `events/types.py` re-export it, so
existing import paths keep working. `di.RAISE == events.RAISE` is now True.
*Discovered in:* `di`. *Status:* **resolved**.

### CC-11 — pygame reaches into the backend-agnostic core
**Tracked as GitHub issue #9.**
CLAUDE.md states the engine is backend-agnostic and that code should never
import pygame directly, but `Application` uses `pygame.time.Clock` for all
frame timing, compares against `pygame.QUIT`, calls `pygame.event.pump()` and
catches `pygame.error`. `SandboxApplication` uses `pygame.K_F1`-style constants
for its tool hotkeys. The ModernGL path therefore still depends on pygame for
timing and quit detection.
Not fixed in the `application` pass because the fix belongs on the other side
of the boundary: `Window.poll_events()` would have to yield engine events
rather than raw SDL ones, and a `Clock` protocol would have to join the
graphics protocols. **Fix:** take it with the `graphics` audit, so the protocol
and both backends move together. `WindowResizeEvent` is defined and never
dispatched for the same reason -- nothing detects the resize.
*Discovered in:* `application`. *Status:* parked until `graphics`.

### CC-8 — Package `__init__.py` files export nothing
Most subsystem packages have a docstring-only `__init__.py`, so callers reach
into submodules (`from pyguara.events.dispatcher import ...`). Beyond the
ergonomics, it actively hides import cycles: adding re-exports to
`events/__init__.py` immediately exposed a latent `log` <-> `events` deadlock
(fixed in that pass). Every package still lacking exports may be hiding the
same thing. **Fix:** add a curated `__all__` per package as each is audited,
and treat any cycle it reveals as a finding rather than a reason to revert.
*Discovered in:* `events`. *Status:* open.

### CC-7 — `x or default` used with falsy value types
`pymunk.Vec2d` defines `__bool__`, so `Vector2(0, 0)` is falsy. `Transform
.__init__` used `scale or Vector2(1, 1)`, which silently rewrote an explicitly
requested zero scale to unit scale. Fixed there, but the idiom is common and
the same trap applies to any zero vector, `Color(0,0,0,0)`, an empty `Rect`, or
`0.0` defaults. **Fix:** sweep `grep -rn "or Vector2(\\|or Color(" pyguara/` and
convert to explicit `is None` checks as each subsystem is audited.
*Discovered in:* `common`. *Status:* open.

---

## Iteration Log

### `pyguara/physics` triggers & joints — awaiting approval (branch `refactor/physics-triggers-joints-audit`)

The systematic pass the earlier physics work deferred: `collision_system.py`,
`trigger_volume.py`, `trigger_system.py`, `joints.py`. Both remaining feature
areas turned out to be inert end to end -- full API, docstrings and unit
tests, connected to nothing. Every defect was reproduced with a probe against
the real pymunk backend before being touched.

**Verification:** 1608 tests pass (up from 1591); `ruff check .` clean;
`mypy pyguara` clean across 224 files. Each finding below was confirmed by a
probe, and each fix by watching a new test fail when reverted.

**F1 -- the entire `Joint` ECS layer did nothing.** `Joint` plus all five
`create_*_joint()` factories plus `create_rope_chain()` produced components
that no system consumed: there was no `JointSystem`, and `PhysicsSystem` only
ever looks at `Transform`+`RigidBody`. `engine.create_joint()` was called
only by tests. Probe: a pin-jointed body free-fell 1846px in 2s;
`len(space.constraints) == 0`. `joints.py`'s module and class docstrings both
stated "The joint is created by the PhysicsSystem when both entities have
RigidBody components" -- untrue since the sentence was written.

New `pyguara/physics/joint_system.py`. `JointSystem` reads `Joint`
components, calls `engine.create_joint()` once both entities have a body in
the engine (retrying on later ticks until then, so it is order-independent
w.r.t. `PhysicsSystem`), stores the handle on `Joint._joint_handle` and
mirrors it in an owner-keyed table. It tears the constraint down on
`EntityDestroyed` for either endpoint, and on `Joint` component removal
(reconciled each `update()`). Opt-in and ticked by the game after
`PhysicsSystem.update()`, exactly like `PhysicsSystem` itself -- no
bootstrap/scene auto-registration, matching the existing convention.
`PymunkEngine.destroy_body()` now also removes a body's attached constraints
first, so tearing down a jointed body is self-consistent regardless of which
system gets there first.

**F2 -- trigger volumes fired with the roles swapped, so `TriggerSystem`
dropped every event.** `CollisionSystem.on_collision_begin/persist/end` took
`is_sensor: bool` and unconditionally treated `entity_a` as the trigger and
`entity_b` as the other body. Chipmunk's `arbiter.shapes` order is arbitrary;
the probe showed the dynamic body landing as `entity_a` in *both* entity
creation orders, so `OnTriggerEnter` came out `trigger_entity=<the ball>,
other_entity=<the zone>`. `TriggerSystem._on_trigger_enter` then looked up the
ball, found no `TriggerVolume`, and returned -- `entities_inside` never
populated, `contains_entity()` / `one_shot` / tag filtering all dead. The
callback contract is now `sensor_entity_id: str | None`: the backend resolves
which shape is the sensor (it is the only thing that can) and
`CollisionSystem._order_trigger_pair()` puts it first.

**F3 -- a trigger built the documented way never entered the simulation.**
`trigger_volume.py`'s own usage example adds `Transform` + `TriggerVolume`
and nothing else. `TriggerSystem.update()` added a sensor `Collider`, but
`PhysicsSystem` only registers shapes for entities that also have a
`RigidBody`, so the sensor shape never reached the space and no event ever
fired. `TriggerSystem` now also adds a static `RigidBody` when the entity has
none (a game that needs a moving trigger still supplies its own KINEMATIC
body). This is why `guara_falcao` never used `TriggerVolume` at all -- its
`CheckpointSystem` is a hand-rolled `distance < 40px` check over a bespoke
`ZoneTrigger` component, the workaround you write when the engine's triggers
don't work.

**Pattern, extended.** "Declared and wired to nothing" -- already flagged in
the last physics entry for `fixed_rotation`, `gravity_scale` and the
`return False` collision contract -- now has its two largest instances:
`Joint` (whole ECS layer) and `TriggerVolume` (end-to-end). Both had unit
tests that passed because each built its subject in isolation: joints tested
only via `engine.create_joint()` directly, trigger callbacks tested only with
the sensor hand-passed as `entity_a`. Uniform setup, fifth and sixth
instances.

**Tests (+17 net; ~50 changed).** `test_collision_events.py` rewritten for
the `sensor_entity_id` contract, with a new `TestTriggerRoleOrdering` class
that passes the sensor as `entity_b` and asserts the event still comes out
sensor-first. New `tests/integration/test_trigger_volumes_backend.py` drives
`PymunkEngine`+`CollisionSystem`+`PhysicsSystem`+`TriggerSystem` together --
parametrised on entity creation order (the thing that used to decide whether
triggers worked), plus the no-RigidBody case, tag filtering and one-shot. New
`tests/test_joint_system.py`: pin joint holds, deferred creation, teardown on
either entity's destruction and on component removal, self-target and missing
target tolerated, rope chain holds together, `cleanup()`.

**Docs (Phase C, partial).** `docs/physics/simulation.md` gains a Joints
section and a Trigger-volumes section (the three-system requirement, the
auto-added bodies); the collision section now states the sensor-ordering
guarantee. `test_docs_api.py` passes. Full-subsystem Phase C -- a dedicated
page, and reconciling the scattered `RigidBody` examples -- is still open.

**Deliberately not done:** no demo added (triggers/joints are covered by the
new integration tests and `guara_falcao` has no natural place for a
pendulum); `guara_falcao`'s checkpoints left on their hand-rolled path;
`create_joint`'s GEAR/MOTOR still structural-only (`ratio=1`, `rate=0` -- a
MOTOR joint would need new `Joint` fields to be useful); `set_collision_system`
still absent from the `IPhysicsEngine` protocol (works because bootstrap holds
the concrete `PymunkEngine`).

**Still open for subsystem close:** `physics.substeps` default (4 vs 2, from
the last entry); `point_query`/`bb_query`/`shape_query`/multi-hit segment
queries still unexposed; `surface_velocity`, slope handling, variable jump
height, corner correction, body sleeping still absent (all from the last
entry's reference comparison).

### `pyguara/physics` — IN PROGRESS (PRs #24 and #25, branch `fix/physics-collision-tunnelling`, merged)

Driven by a report that collision "works really poorly", with a brief to
judge the layer as **game** physics: Chipmunk simulates rigid bodies and
knows nothing about characters, ground or jumping, so everything that makes
a platformer feel right is PyGuara's own and is what was audited.

Every defect below was reproduced before being touched, and each fix was
checked by reverting it and watching the new test fail.

**Defects found and fixed**

1. **Tunnelling from 600 px/s** through a 10px wall — one solver step moves a
   body `velocity/60` px in a straight jump. Fixed by substepping
   (`physics.substeps`, default 4). Same cause as the reported *sinking on
   landing*: 11.2px deep for 24 frames before, 0.9px and no visible frames
   after.

2. **No render interpolation reachable from a custom renderer.** The engine
   had `render_alpha`, `previous_position` snapshotting and a lerp in
   `scene/base.py`, but only on the Sprite/RenderSystem path. Drawn raw at
   75Hz a body moves 0–5px per frame where every frame should be 4.
   `Transform.render_position(alpha)`, plus automatic opt-in by
   `PhysicsSystem` — a blanket default is wrong, since interpolating a
   variable-rate-moved transform *adds* judder (measured). `Transform.teleport()`
   covers respawns and screen wraps, which would otherwise streak.

3. **Every character detected itself as ground.** The ground ray starts 1px
   below the collider, but a Chipmunk segment query is a swept circle whose
   radius reaches back inside. `is_grounded` was True in mid-air and with no
   ground in the world at all, so coyote time never started, jump buffering
   had nothing to buffer, and the landing reset never fired — a character
   could jump twice and then never again until it died. `raycast()` gained
   `ignore_entity_id`.

4. **`fixed_rotation` and `gravity_scale` were inert** — declared on
   RigidBody, documented, read by nothing.

5. **pymunk 7 ignores a collision callback's return value**, so every
   `return False` in the backend did nothing — including `CollisionSystem`
   returning False to mean "report but do not resolve physically", which is
   how a non-sensor trigger is meant to work. Now expressed through
   `arbiter.process_collision`.

6. **Walking sank the character 8px permanently.** A floor of separate tile
   colliders has interior faces; a character rests `collision_slop` (0.1px)
   deep, so its leading bottom corner strikes the vertical faces of the tiles
   ahead. Traced: at a tile boundary it was flung upward at 47 px/s, hopped,
   landed 8.4px deep and stayed. `pyguara/physics/tilemap.py` merges solid
   tiles into as few rectangles as a greedy pass finds; sprites stay per-tile.
   Walking then holds 0.10px throughout. Pre-existing — main measures the same.

**Features added** (all absent, all genre staples Chipmunk cannot provide)

- **One-way platforms** (`Collider.one_way`, `one_way_normal`) — decided on
  the contact normal, not velocity (velocity is zero at a jump's apex, which
  flips the surface solid mid-overlap and ejects the character), and
  re-decided every step, not latched at first contact.
- **Collider debug draw** (`physics/debug_draw.py`, F1 in `guara_falcao`) —
  outlines every collider and the platformer's probe rays. Defect 3 would
  have been obvious in one frame of it.
- **`overlap_box`** — the first of pymunk's spatial queries beyond `raycast`
  that this engine exposes.
- **`CharacterMover`** (`physics/character_mover.py`) — swept
  collide-and-slide. **Built and tested, deliberately not wired in at the
  time.** Wired in below.

**Moving platforms already worked.** Measured before building: a kinematic
platform moving 200px carried its rider 187.6px, the rest being friction
slip. Undocumented gotcha: a kinematic body is position-synced *from* its
Transform, so a game moves one by advancing the Transform, not its velocity.
Superseded below: character riding no longer goes through Chipmunk friction
at all.

**The open decision — see `docs/physics/character-movement.md`.** Assigning
velocity to a dynamic body and letting the solver sort out the overlap is
the root of this whole family of bugs: sinking, seam catching, wall creep,
tunnelling. `CharacterMover` removes it by construction, but the character
stops being a physics body, so knockback, platform carrying and crate
pushing all need re-expressing. That document records the cost and the
recommendation; it needs a decision on what a character should still be able
to do physically before the conversion starts.

**Resolved — full parity built, on Celeste's model.** Checked against the
actual code before deciding: none of the three (knockback, riding, pushing)
existed as working features — `Hazard.knockback_force` was declared and read
by nothing, crates weren't implemented in `guara_falcao` at all, moving
platforms had no system driving them. Decision made: build full parity
anyway, using Celeste's integer-position-plus-remainder model (Maddy
Thorson's "Celeste and TowerFall Physics") rather than Chipmunk friction or
a continuous bisection sweep.

What shipped: `CharacterMover` rewritten to whole-pixel stepping with a
remainder accumulator (no more `MAX_STEP`/bisection — the last free whole
pixel is the answer directly), plus a `probe()` primitive that replaced
ground detection's raycast with a one-pixel overlap test (Celeste's
`OnGround()`). `CharacterBody` replaces `RigidBody` for a character —
literally no shape registered with the engine, which makes the ground-ray
self-detection bug class (defect 3, above) structurally impossible rather
than guarded against. `SolidMover`/`SolidSystem` (new) carry and push actors
for `MovingSolid` entities, built on `Solid.MoveHExact`/`MoveVExact` — a
direct placement plus a squish check, not a swept move, which is what a
first attempt using a swept carry got wrong for a platform closing in on a
resting rider (the platform's already-synced destination shape reads as
overlapping the rider mid-sweep, before it catches up). `Pushable` marks a
crate; `PlatformerSystem` asks `SolidMover.try_move()` to shove one when
blocked by it, excluding the pushing character from the reactive
carry/push pass — without that exclusion a pushed crate immediately shoves
back at whoever pushed it. `apply_knockback()` overrides velocity and
suppresses input control for a short window, decaying underneath continuing
gravity; `guara_falcao`'s `HazardSystem` now calls it.
`PhysicsSystem.sync_kinematic_transforms()` was split out of `update()` so
`SolidSystem`/`PlatformerSystem` can query a solid's current-tick position
before the simulation step runs. `guara_falcao` gets a demo patrolling
platform and a pushable crate for manual verification.

**Patterns, now four and five instances deep**

- **Uniform test setup, not missing coverage.** Every viewport test used a
  fullscreen viewport, every collision test a slow body, every platformer
  test a character already resting on the floor. Each defect lived in the
  case no test set up.
- **Declared and wired to nothing.** `fixed_rotation`, `gravity_scale`, the
  `return False` collision contract, interpolation reachable from one render
  path only. A game sets them, nothing happens, and there is no signal
  distinguishing an inert option from a wrong value. Worth a deliberate sweep
  of other subsystems for this shape.

**Reference comparison — mechanisms still missing.** Of pymunk's six spatial
queries the engine now exposes two (`raycast`, `overlap_box`); `point_query`,
`bb_query`, `shape_query` and multi-hit `segment_query` are unexposed, which
rules out click-picking, explosion radii, melee hitboxes and "can I fit here".
Also absent: `surface_velocity` (conveyors), slope handling (no max-slope
angle; a ramp will launch a character), variable jump height (releasing early
does not cut the jump), corner correction, and body sleeping (every idle body
is simulated forever).

**Still not audited:** `collision_system.py`, `trigger_volume.py`,
`trigger_system.py`, `joints.py`; Phase B (test assessment) and Phase C
(docs) for the subsystem as a whole. Given finding 5, the trigger files are
the most suspicious place to resume.

**Also left open:** whether `physics.substeps` should default to 4 or 2 —
4 costs about half a 60Hz frame at 200 dynamic bodies.


### `pyguara/ecs` — CLOSED 2026-09-06 (PR #1, branch `refactor/ecs-audit`)

**Verification:** 1161/1161 tests pass (68 in the two ECS files, up from 55);
`ruff check .` clean; `mypy pyguara` clean across 218 files.

**Correctness fixes (both reproduced by probe before fixing):**
- `EntityManager.add_entity()` indexed pre-attached components straight into
  `_component_index`, bypassing `QueryCache`. Entities entering the world via
  `clone()`, prefabs or deserialisation were invisible to every *cached* query
  while remaining visible to the uncached equivalent. Now routed through
  `_on_entity_component_added()`.
- `EntityManager.add_entity()` accepted a soft-dead entity, contradicting the
  documented terminal-removal invariant and producing a zombie: reachable via
  `get_entity()`, dropped from all queries at the next flush, raising on any
  mutation. Now raises `RuntimeError`.

**Other changes:**
- `StrictComponent.__init_subclass__` swallowed class keyword arguments
  (`object.__init_subclass__()`); now chains via `super(BaseComponent, cls)`.
- Removed a dead branch in `_get_logic_methods()` (both arms `continue`) and
  an unused module logger in `component.py`.
- Extracted `EntityManager._matching_entity_ids()`; the index-intersection
  logic was triplicated across three query methods.
- `QueryCache` now indexes registered queries by component type, so a
  component change visits only the queries it can affect instead of all of them.
- `QueryCache.clear_cache()` -> `rebuild_all()` (it rebuilt, never cleared).
  No callers outside the module.
- `ALLOWED_METHODS` is now a `frozenset` — **minor breaking change** for any
  caller that mutated it. Intentional: it is a module constant.
- Modern typing throughout (`dict`/`list`/`X | None`), Google-style docstrings,
  "what" comments purged, "why" comments kept.

**Docs:** new `docs/core/ecs.md` (full reference, added to mkdocs nav);
`docs/core/architecture.md` ECS section condensed to a summary + link, DI and
Event sections left untouched for their own iterations.

**Follow-up landed in the same pass (CC-5, removal hook):** at the user's
request, `EntityManager._on_entity_removed` — a private single-callback slot
assigned from `pyguara/scene/base.py` — was promoted to a public
`subscribe_entity_removed()` / `unsubscribe_entity_removed()` pair. Made it a
subscriber list rather than a slot: the old design let whichever consumer wired
itself last silently displace the scene's `EntityDestroyed` dispatch, which is
the same class of silent-clobbering bug as the two fixed above. `Scene` and both
test modules migrated; 7 further tests added (1168 total, from 1161).

**Deferred out of this subsystem:** CC-1 through CC-4, CC-6, and the remaining
half of CC-5 (`Entity._components` reached into by `persistence`/`prefabs`).


### `pyguara/common` — CLOSED 2026-09-06 (PR #2, branch `refactor/common-audit`)

**Verification:** 1236/1236 tests pass (up from 1168); ruff clean; mypy clean
across 217 files (one fewer: `constants.py` deleted).

**Correctness fixes (all three reproduced by probe before fixing):**
- `Transform.up` returned `(0, +1)` — the exact opposite of `Vector2.up()`'s
  `(0, -1)`, and pointing *down* on screen. Gravity defaults positive
  (`gravity_y = 900.0` in the shipped games), so the engine is unambiguously
  Y-down; `Transform.up` was wrong. Both now agree, and the convention is
  stated in both module docstrings and the new doc page.
- `Transform.set_parent()` had no cycle guard. `t.set_parent(t)`, or any
  loop, made every later `world_*` read recurse until the stack blew.
  Now raises `ValueError`; `is_ancestor_of()` exposes the check.
- `Transform.__init__` used `scale or Vector2(1, 1)`. `Vector2(0, 0)` is falsy,
  so an explicitly requested zero scale silently became unit scale. Now
  `is None`. Found by a test written against the documented behaviour, not by
  reading the code — see CC-7.

**API changes:**
- `Vector2.rotate(degrees)` → `Vector2.rotate_degrees(degrees)`. It sat one
  letter from `rotated(radians)`, and `Transform.rotate()` also takes radians;
  a one-letter difference deciding the angle unit is unreadable at a call site.
  All three call sites migrated (`camera.py` ×2, `particles.py`); all were
  correct beforehand, so this closes a latent trap rather than a live bug.
- `Color` now coerces channels to `int` and clamps to 0-255. It lost pygame
  .Color's own validation in the ticket-31 migration and gained no replacement,
  so `Color.from_hsv(0, 5, 5)` produced `Color(1275, -5100, -5100)`. Clamping
  rather than raising: colour arithmetic overshoots legitimately, and a crash
  mid-render is worse than saturation.
- Added `Vector2.down()`/`left()` and `Transform.left`/`down` — `up`/`right`
  existed without their opposites.
- Added `Color.to_hex()` and `Rect.size`.
- `Tag` and `ResourceLink` are now `@dataclass(slots=True)`, as the ECS docs
  require. This required replacing `super().__init__()` with an explicit
  `BaseComponent.__init__(self)`: `slots=True` returns a *new* class, so a
  zero-arg `super()` resolves against the discarded original and raises on
  every instantiation. Caught by 10 failing tests, not by review.
- `Rect.inflate()` now truncates the offset towards zero instead of flooring,
  matching `pygame.Rect` for odd negative deltas (was off by one pixel).

**Cleanup:** deleted `pyguara/common/constants.py` (a file containing only a
docstring, imported nowhere). `palette.BasicColors` now re-exports the `Color`
constants instead of redefining all nine.

**Tests:** 52 in `test_common_types.py` (from 24) plus a new
`test_transform.py` with 36. `Vector2` and `Transform` previously had **zero**
direct tests — Transform appeared in ten other modules only as an incidental
fixture, so the most intricate logic in the package was exercised by accident.

**Docs:** new `docs/core/common-types.md`, added to the mkdocs nav.

**Deferred:** CC-1 through CC-4, CC-6, CC-7, and the remaining half of CC-5.


### `pyguara/events` — CLOSED 2026-09-06 (PR #3, branch `refactor/events-audit`)

**Verification:** 1262/1262 tests pass (up from 1236); ruff clean; mypy clean.

**Correctness fixes (all reproduced by probe before fixing):**
- Every event dataclass in `input.py`, `lifecycle.py` and `window.py` used
  `timestamp: float = 0.0` plus a `__post_init__` overwriting zero with
  `time.time()`. A genuine timestamp of 0.0 was therefore impossible to
  express, and the idiom was duplicated five times. Replaced with
  `field(default_factory=time.time)`, which `ecs/events.py` already used --
  the engine had two idioms for the same thing and the more common one was
  the broken one.
- `filter_func` exceptions bypassed `error_strategy` entirely: a raising
  filter propagated even under IGNORE, because only the handler call was
  wrapped. A filter is user code too, and now follows the same policy.
- **Latent `log` <-> `events` import cycle.** `pyguara.log.events` inherits the
  `Event` protocol at runtime, so `log` depends on `events`; but
  `events.dispatcher` imported `pyguara.log` at module scope. The cycle was
  masked only by `events/__init__.py` being empty, and detonated the moment
  re-exports were added. `events` is the more foundational package, so the
  fix is on its side: `EngineLogger` is a type-only import and the default
  logger resolves lazily inside `__init__`. Both import orders are now
  covered by a subprocess regression test.

**API changes:**
- `dispatch()` returns `bool` instead of `None` -- True if every handler ran,
  False if one consumed the event by returning False. The short-circuit
  already worked but was invisible to callers, which is precisely what
  UI-over-game input handling needs. No in-repo caller used the return value,
  so this is additive. `IEventDispatcher` updated to match.
- `max_history_size` is now a constructor parameter; it was hardcoded at 1000
  while `enable_history` was configurable.
- `IEventDispatcher.subscribe` gained the `filter_func` parameter the
  implementation always had.
- `events/__init__.py` re-exports the public surface with an `__all__`.

**Performance:** `dispatch()` rebuilt and re-sorted the merged MRO handler
list on every single call -- in the engine's hottest path. Now memoised per
concrete event type and invalidated when the subscription set changes.
Measured on 20 000 dispatches with 50 handlers: 5.7 us -> 3.1 us per dispatch.

**Tests:** 23 -> 49. The dispatcher's existing tests were genuinely good; the
gaps were the event dataclasses (untested, and where the timestamp bug lived),
filter error handling, `clear_subscribers`, history filtering and sizing,
cache invalidation, snapshot-during-dispatch semantics, and real multi-thread
`queue_event` contention.

**Note:** one existing test caught a regression I introduced -- dropping the
exception text from the handler error message. Restored.

**Docs:** new `docs/core/events.md`; `architecture.md`'s Event section
condensed to a summary and link.

**Deferred:** CC-1 through CC-4, CC-6, CC-7, CC-8, and the rest of CC-5.


### `pyguara/di` — CLOSED 2026-09-06 (PR #4, branch `refactor/di-audit`)

**Verification:** 1286/1286 tests pass (up from 1262); ruff clean; mypy clean.

**Correctness fixes (all reproduced by probe before fixing):**
- **`DIScope.get()` resolved without taking the container lock**, so parallel
  resolutions through scopes shared one mutable cycle-detection stack and saw
  each other's partial chains. With constructors that take a couple of
  milliseconds this reported **140 spurious CircularDependencyExceptions out
  of 160 resolutions**. It hid because every constructor in the test suite is
  instant. Fixed twice over, deliberately: the scope now takes the lock like
  the container does, and the resolution stack is thread-local, so the
  invariant holds structurally rather than by remembering to lock -- which is
  exactly the discipline that failed here.
- **Captive dependency.** A singleton resolved inside a scope captured the
  scoped instance; the scope disposed it and the singleton kept handing out
  the dead object forever. Singletons are now built with `scope=None`, so the
  attempt raises with a message explaining why.
- **A disposed scope still resolved**, tracking new disposables in a list it
  had already emptied -- they would never be cleaned up. Now raises.
- **Re-registering an already-resolved singleton silently did nothing.** The
  registration was replaced but the cached instance was not, so `get()` kept
  returning the old implementation. The cached instance is now evicted.
- **`*args`/`**kwargs` were treated as injection points.** `*args: int` was
  read as a dependency named "args" of type `int`, making any class that
  declares varargs unresolvable. Only POSITIONAL_OR_KEYWORD and KEYWORD_ONLY
  parameters are considered now.
- **`DIScope.dispose()` swallowed every exception** with a bare
  `except Exception: pass`. Failures are logged, and the remaining services
  are still disposed.

**API additions:** `DIContainer.is_registered()` and `DIScope.disposed`, both
needed to write the tests above without reaching into privates.

**Also:** `_create_instance` could fall off the end and return None for a
malformed registration; it now raises. Modern typing, Google-style docstrings,
P2-003 ticket references removed from public docstrings (CC-3).

**Tests:** 26 -> 40. The existing tests were reasonable but entirely
single-threaded and single-scope, which is why the lock bug survived. Added
lifetime-capture rules, disposal semantics, re-registration, signature edge
cases, and three genuine concurrency tests.

**Docs:** new `docs/core/dependency-injection.md`; `architecture.md`'s DI
section condensed to a summary and link. That file's three original sections
(ECS, DI, Events) are now all summaries pointing at dedicated pages.

**Deferred:** CC-1 through CC-4, CC-6 through CC-9, and the rest of CC-5.


### `pyguara/log` — CLOSED 2026-09-06 (PR #5, branch `refactor/log-audit`)

**Verification:** 1303/1303 tests pass (up from 1286); ruff clean; mypy clean.

**Correctness fixes (all reproduced by probe before fixing):**
- **Every log record in the engine reported `logger.py:138` as its source.**
  `EngineLogger._log()` called `self._logger.log()` without a `stacklevel`, so
  the two wrapper frames were never skipped and every record attributed itself
  to the same line inside the wrapper. The file formatter's `%(lineno)d`, and
  the `module`/`line` fields carried into `OnLogEvent`, were that same constant
  for every message ever logged. A caller-supplied `stacklevel` is now offset
  rather than ignored.
- **`reconfigure()` cleared the whole handler list of a process-global stdlib
  logger**, silently tearing down handlers installed by the application, by a
  test, or by a second `LogManager` using the same name. Each logger now tracks
  and removes only the handlers it installed.
- **`shutdown()` closed handlers but left them attached**, and a closed
  `FileHandler` silently reopens its file on the next record -- so shutdown
  did not actually stop logging. It detaches now, and a test asserts nothing
  is written afterwards. (My first probe of this claimed data loss; checking
  the file showed the opposite. The defect is that shutdown is a no-op, not
  that it drops records.)
- **`configure(dispatcher=None)` could not detach a dispatcher**, because
  `if dispatcher:` cannot tell None from unspecified. A sentinel default now
  distinguishes them.

**Also:**
- `EventIntegratedHandler.emit()` built a throwaway `LogRecord` on **every**
  record, purely to compute a constant set of key names. Hoisted to a
  module-level frozenset.
- `propagate` is now configurable. Engine loggers install their own handlers
  *and* propagate, so an application that also configures root logging sees
  every record twice. Default left at True -- propagation is what lets an app
  capture engine output, and the duplication only occurs when the app prints
  too -- but the choice is now explicit and documented rather than implicit.
- Removed a leftover `# FIX:` comment; documented `LogCategory` as orthogonal
  to `LogLevel`. Modern typing, Google-style docstrings.

**Tests:** 9 -> 26. Source attribution, handler ownership, shutdown semantics,
`configure()` dispatcher handling, propagation, and the path from structured
keyword arguments through to `OnLogEvent.context`.

**Docs:** `docs/core/logging.md` **rewritten from scratch** -- see CC-10. It
documented `pyguara.log.config.setup_logging()`, a module and function that
have never existed in this tree; every code sample on the page raised
`ModuleNotFoundError`.

**Tier 1 is now complete:** `common`, `log`, `events`, `di`.

**Deferred:** CC-1 through CC-4, CC-6 through CC-10, and the rest of CC-5.


### Cross-cutting pass — 2026-09-06 (branch `chore/lint-modernization`)

Taken between subsystem iterations, at the user's direction, to clear the two
concerns that were compounding across every audit.

**CC-1 / CC-2 — lint modernisation.** `target-version` bumped `py39` -> `py312`
and `UP`, `B`, `I`, `SIM` enabled. 1455 findings fixed mechanically; the
remainder by hand. 273 files changed.
- One real defect found by `B`: `WorldPass(clear_color=Color(0,0,0,255))`
  shared a single mutable `Color` across every instance.
- Twelve B008 reports were false positives -- `Vector2` is a NamedTuple
  subclass, hence immutable -- handled with
  `flake8-bugbear.extend-immutable-calls` rather than scattered noqa comments.
- `di/decorators.py` needed a rewrite: ruff's B010 fix removed `setattr()`
  calls that existed to dodge mypy, so the errors came straight back. Now uses
  a typed `_DIMarked` protocol, which also collapsed three identical decorator
  bodies into one helper.
- **The pydocstyle pre-commit hook was mis-scoped.** It used a `match:` key
  pre-commit does not recognise -- warning "Unexpected key(s) present" on every
  run for who knows how long -- so it linted the entire repository, not
  `pyguara/`. Fixed to `files:`. This surfaced undocumented public methods in
  `persistence/serializer.py` that the broken scoping had hidden.

**CC-9 — shared `ErrorHandlingStrategy`.** Hoisted to a new top-level
`pyguara/errors.py`. Both `di` and `events` re-export it, so no import path
breaks, and the two enums are now genuinely the same class.

**CC-10 — documentation smoke test.** `tests/test_docs_api.py` checks every
`pyguara...` import and dotted reference in `docs/`. It found two more
fictional APIs on its first run (see CC-10 above).

**Verification:** 1343/1343 tests pass; ruff clean; mypy clean across 218 files.

**Not done:** the filename `docs/guides/Archictecture & Style Guide.md` is
misspelled. Renaming it means touching the mkdocs nav and any inbound links, so
it is left for whoever next edits that file.


### `pyguara/config` — CLOSED 2026-09-06 (PR #7, branch `refactor/config-audit`)

**Verification:** 1371/1371 tests pass (up from 1343); ruff clean; mypy clean.

**Correctness fixes (all ten reproduced by probe before fixing):**
- **`Color` did not survive a save/load round trip.** `asdict()` flattens it to
  `{"r": ..., "g": ...}` and `from_dict` passed that straight back to
  `WindowConfig`, so `display.default_color` came back as a `dict`. Both window
  backends read it as `self._default_color` and pass it to `clear()`, so
  `fill_color.r` raised AttributeError. Reachable on the *ordinary* path: run 1
  finds no config file and writes defaults, run 2 reads them back and breaks.
  `from_dict` is now field-driven and coerces by declared type, which also
  removed five near-identical per-section blocks.
- **`OnConfigurationLoaded` and `OnConfigurationSaved` were permanently stamped
  `timestamp=0.0`.** Unlike the input/lifecycle events fixed in the `events`
  pass, these had no `__post_init__` at all, and the manager never passed a
  timestamp. Now `field(default_factory=time.time)`.
- **`PhysicsConfig.fixed_dt` divided by zero** with nothing validating
  `fixed_timestep_hz`. `Application.run()` reads it on every startup, so a zero
  in a config file crashed the engine with a bare ZeroDivisionError naming
  neither the setting nor the file. Now raises a named ValueError, and the
  validator reports it as CRITICAL.
- **`update_setting()` warned about a type mismatch and then assigned anyway**,
  so `screen_width` could end up holding `"not a number"`. It now refuses, and
  is stricter than `isinstance` where that matters: a `bool` is not an `int`
  here, though `isinstance(True, int)` says otherwise.
- **`update_setting()` bypassed validation entirely**, so it could put the
  config into a state `load()` would have rejected (`master_volume = 99.0`). It
  now reverts and refuses on an ERROR/CRITICAL issue; WARNING passes, since a
  warning is advice.
- **`from_dict` mutated the caller's dict** (the debug section was not copied).
- **Unknown keys were dropped in silence** -- a typo'd setting simply never
  took effect. Now ignored *and* logged, so a config from a newer engine still
  loads but a typo is visible.
- **Invalid env overrides failed silently** (`except ValueError: pass`), so a
  typo in a launch script did nothing at all. Now reported, and the message
  lists the valid values.
- **Every validation issue was logged as a warning**, hiding ERROR and CRITICAL
  among the merely suboptimal. Each is now logged at its own level.
- **`ConfigManager._file_path` was hardcoded**; now a constructor argument,
  which the tests needed anyway.

**Validator coverage** went from 3 rules to 10: screen height, all three
volumes rather than just master, gamepad deadzone, mouse sensitivity, fps
target, fixed timestep and max frame time. `ValidationIssue` is now frozen and
its `suggestion` field is actually populated.

**Tests:** 5 -> 33. The existing five covered defaults, a mocked load, a mocked
missing file and two `update_setting` cases -- all with mocks rather than real
files, which is exactly why no round-trip bug could surface. The new ones use
`tmp_path` and assert on real files, including a whole-config round trip that
will catch the next field that fails to survive one.

**Docs:** new `docs/core/configuration.md`, added to the nav;
`application.md`'s config paragraph now links to it.

**Deferred:** CC-3 through CC-8 (CC-1, CC-2, CC-9, CC-10 resolved).


### `pyguara/application` — CLOSED 2026-09-06 (PR #8, branch `refactor/application-audit`)

**Verification:** 1384/1384 tests pass (up from 1373); ruff clean; mypy clean.

**Correctness fixes (all reproduced by probe before fixing):**
- **The event-queue time budget was spent per fixed step, not per frame.**
  `_fixed_update()` drained the queue, and it runs once per accumulated step,
  so a frame lagging by the full `max_frame_time` called `process_queue(
  max_time_ms=5)` **15 times** -- up to 75ms in one frame. The budget exists
  specifically to stop an event death spiral, and it was multiplied by the step
  count at exactly the moment a spiral begins. Drained once per frame now.
- **`shutdown()` was neither idempotent nor exception-safe.** A raising
  `scene_manager.cleanup()` meant the window was never closed and the log
  manager never shut down -- on the crash path, where releasing them matters
  most. Steps are isolated and logged now, and a second call is a no-op.
- **The ModernGL render path hardcoded `Color(0, 0, 0, 255)`**, so
  `display.default_color` silently did nothing under that backend while the
  pygame path honoured it via `window.clear()`.
- **Three lifecycle events had no publisher.** `ApplicationStartEvent` and
  `QuitEvent` are now dispatched; `pyguara/tools/event_monitor.py` subscribes
  to `QuitEvent`, so its handler had been unreachable. `WindowResizeEvent`
  still has none -- see CC-11.
- **`ServiceNotFoundException` was imported inside the `try` block whose
  `except` names it**, so an ImportError there would have raised NameError
  instead of being handled.
- `raise e` in the loop's handler appended a frame to the traceback; now a bare
  `raise`.

**Tests:** 2 -> 13 in `test_app_flow.py`. The existing two covered a single
frame and a scene switch; nothing covered shutdown, lifecycle events, the event
budget, or the failure paths.

**Docs:** `docs/core/application.md` rewritten. Its "Main Loop" section listed
`Time.tick()`, `Input.process()`, `Update()`, `Render()` -- none of which are
real method names -- so it described the loop's shape without matching the
code. Now documents the actual sequence, why frame time is clamped, and why the
event queue is drained outside the accumulator loop.

**Parked:** CC-11 (pygame in the backend-agnostic core). `bootstrap.py` and
`sandbox.py` were scanned and are otherwise clean; their `# type: ignore[
type-abstract]` markers are the known mypy limitation around Protocol
registration, not defects.

**Deferred:** CC-3 through CC-8, CC-11.


### `pyguara/scene` — CLOSED 2026-09-06 (PR #10, branch `refactor/scene-audit`)

**Verification:** 1399/1399 tests pass (up from 1384); ruff clean; mypy clean.

This module was visibly more careful than earlier ones -- dense "why" comments
from prior wayfinder work, and `cleanup()` written specifically to avoid a
leak. The defects are all at its seams rather than in its core logic.

**Correctness fixes (all five reproduced by probe before fixing):**
- **`switch_to()` abandoned every stacked scene.** It ended in a bare
  `self._stack.clear()`, so a scene pushed under an overlay was never exited
  and its SystemManager never cleaned -- it stayed live holding its
  EntityManager, systems and physics bodies. `cleanup()`'s own docstring warns
  against "leaking whatever's still on the stack past a bare `.clear()`", and
  `switch_to()` did exactly that on every scene change. Now unwinds LIFO:
  current scene first, then the stack top-down.
- **A second stack change during a transition replaced the pending scene.**
  `switch_to("b", fade)` then `switch_to("c", fade)` left 'b' skipped entirely
  -- never entered -- while its predecessor had already been exited. All three
  stack operations now refuse while a transition runs, and log it.
- **`pop_scene()` with a transition stranded the scene it was returning to.**
  The stack entry was removed up front, so between the call and completion the
  previous scene was both off the stack and not yet current: a `cleanup()` in
  that window never exited it. The entry is now held until completion.
- **`cleanup()` missed a scene mid-transition.** A scene a transition had
  started entering but not yet made current was invisible to it. Now included,
  with an identity set so nothing is exited twice.
- **`register()` before `set_container()` silently skipped wiring**, leaving a
  live scene with no camera or render system -- surfacing much later as an
  assertion inside `render()`. `set_container()` now wires any scenes already
  registered.
- **`register()` silently replaced a same-named scene.** Still replaces, since
  that is occasionally intended, but logs that the displaced scene is now
  unreachable.

**Tests:** 18 -> 33 in `test_scene_stack.py`. The existing suite covered the
stack shapes well (pause menu, dialog, inventory, nested pause flags) but
nothing covered what happens to stacked scenes on a *switch*, or any
re-entrancy during a transition -- which is where all five defects lived.

**Note:** my first fix got the unwind order wrong, exiting the stack before
the current scene. A test written for LIFO ordering caught it.

**Docs:** new `docs/core/scenes.md`, added to the nav. The subsystem had no
dedicated page; `pause_below` semantics, the switch-versus-push lifetime
difference and the one-transition-at-a-time rule were undocumented.

**Deferred:** CC-3 through CC-8, CC-11 (now GitHub issue #9).


### `pyguara/systems` — CLOSED 2026-09-06 (PR #11, branch `refactor/systems-audit`)

**Verification:** 1414/1414 tests pass (up from 1401); ruff clean; mypy clean.

The smallest subsystem so far (165 lines of manager, 63 of protocols) with the
best existing test ratio. Three real defects nonetheless.

**Correctness fixes (all reproduced by probe before fixing):**
- **A system registered after `initialize()` was never initialised.**
  `initialize()` sets a flag and returns early on every later call, and
  `Scene.resolve_dependencies()` calls it *before* `on_enter()` -- which is
  precisely where a game is documented to register its own systems (priority
  >=500). Every game system therefore started up uninitialised. A late
  registration now initialises immediately.
- **`unregister()` tested truthiness, not `None`.** A system defining
  `__len__` or `__bool__` falsily was dropped from the lookup table but left
  in the update list: still ticking every frame, never cleaned up, and
  returned as though removed.
- **Duplicate registration keys were silent.** Several systems can share a key
  -- they all update -- but the lookup table holds one entry per key, so the
  earlier ones become unreachable by `get_system()` and survive
  `unregister()`. Now logged, with the fix (`system_type=`) named in the
  message.

**A design choice I reversed mid-iteration.** My first fix made duplicate
registration *evict* the earlier system, on the reasoning that an unreachable
system still consuming a frame budget is a leak. Three existing tests failed:
they register several `MockSystem`/`OrderedSystem` instances under one class
and expect all of them to update. That is a legitimate pattern -- multiple
instances of one generic system -- and eviction destroyed it. The update list
is the source of truth; the type map is a convenience index that simply cannot
represent duplicates. So the fix became surfacing the ambiguity rather than
resolving it by force.

**Also:** `get_system()` was typed `-> Any | None` and now returns the
requested type, so callers stop losing type information at every lookup.

**Tests:** 21 -> 34. The existing suite was genuinely good on the happy paths
and the pause/resume gate; the gaps were registration *after* initialize, key
collisions, and `unregister` edge cases.

**Docs:** `docs/core/scenes.md` gains a Systems section -- a scene's
`SystemManager` is where these are encountered. It records the priority band
convention, that late registration is safe, and that the priority direction is
the opposite of `EventDispatcher`'s (ascending here, descending there), which
was written down nowhere.

**Deferred:** CC-3 through CC-8, CC-11 (GitHub issue #9).

**Tier 2 complete:** `config`, `application`, `scene`, `systems`.

### `pyguara/graphics` iteration 1 — the window boundary — awaiting approval (2026-09-06)

`pyguara/graphics` is ~8,000 lines across five distinct areas, so it is being
audited in slices rather than as one iteration. This is the first: `window.py`
and the `IWindowBackend` contract.

**Verification:** 1427/1427 tests pass; ruff clean; mypy clean.

**Correctness fixes:**
- **`Window.width`/`height` reported the *requested* size, never the granted
  one.** Both returned `WindowConfig` values unconditionally, so a window the
  OS sized differently -- a fullscreen window is routinely handed the desktop
  resolution instead -- reported whatever had been asked for.
  `Application.__init__` feeds these straight into
  `SceneManager.set_screen_size()`, and from there they reach transitions and
  viewport calculations. They now come from the backend once the window
  exists, falling back to config before `create()`.
- **The `IWindowBackend` contract was split three ways.** The protocol declared
  no size accessors, yet the ModernGL window and headless renderer both
  implemented them and the pygame window did not. Nothing checked, because
  nothing asked. `width`/`height` are now on the protocol and implemented by
  all three -- mypy caught the missing headless implementation the moment the
  protocol declared them, which is the protocol finally doing its job.
- Corrected `Window.clear()`'s docstring, which claimed to use the configured
  default colour while actually forwarding `None` for the backend to resolve.

**Tests:** new `tests/test_window_boundary.py`, 13 tests. `Window` had no
dedicated tests at all -- it was exercised only incidentally through
`MagicMock` window fixtures in the application suite, which is why a size
accessor that ignored the backend entirely went unnoticed. Includes protocol
conformance checks for both real backends.

**Issue #9 updated.** Mapping every non-backend pygame import turned up nine
files across five subsystems, not the two originally recorded. Two matter:
`input/manager.py` interprets SDL events directly (`pygame.KEYDOWN`,
`pygame.key.get_mods()`, `KMOD_*`), so event translation is an input change as
much as a graphics one; and `graphics/components/geometry.py` is an ECS
component importing pygame, the clearest single violation and the cheapest to
fix alone. The issue now carries a four-step sequence, each step independently
shippable.

**Deferred:** CC-3 through CC-8, CC-11 (issue #9).


### `pyguara/graphics` iteration 2 — components — awaiting approval (2026-09-06)

**Verification:** 1449/1449 tests pass; ruff clean; mypy clean.

**Correctness fixes:**
- **`components/geometry.py` was hard-wired to pygame** -- it imported pygame,
  drew onto a `pygame.Surface` and constructed a `PygameTexture` directly. So
  `Box` and `Circle` silently produced the wrong texture type under ModernGL:
  an ECS-facing component that only worked on one backend. This was the
  clearest single instance of issue #9, and the one the issue named as
  cheapest to fix alone.

  The abstraction already existed and was already used by `SpriteSheet` in the
  same package: `TextureFactory.create_from_bytes()`. Shapes now rasterise to
  plain RGBA bytes in pure Python and hand them to an injected factory, so they
  work on pygame, ModernGL and headless alike. The module imports no backend at
  all. Circle rasterisation fills by row spans -- each row's half-width follows
  from the circle equation -- so it is O(diameter) rather than O(diameter^2).

  `Box` and `Circle` gain a required `texture_factory` argument. Nothing in
  `pyguara/` or `games/` constructs them, so no production caller breaks; the
  precedent for how to obtain one is `SpriteSheet.from_container()`.

- **`Camera2D.zoom` accepted zero and negative values**, and three code paths
  then disagreed about what that meant: `world_to_screen` collapsed every point
  onto the screen centre, `screen_to_world` substituted `0.001` and returned
  coordinates six orders of magnitude out (`Vec2d(-390000, -290000)` for a
  point at `(10, 10)`), and `get_view_bounds` raised `ZeroDivisionError`. A
  negative zoom silently mirrored the world. `zoom` is now a validated property
  and `zoom_to()` checks its target, so the invariant holds at assignment
  rather than being papered over in one consumer and crashing in another. The
  `safe_zoom = 0.001` fudge is gone.

**Tests:** `test_graphics_geometry.py` rewritten, 6 -> 30. The originals
asserted against `PygameTexture` and read pixels off a `pygame.Surface`, which
is exactly the coupling being removed. Rasterisation is now checked against raw
bytes (backend-free) *and* through the real pygame factory, so both the maths
and the backend path are covered -- plus symmetry, span width, lazy generation
and cache invalidation, which nothing checked before.

**Surveyed and clean:** `animation.py` handles an unknown clip name correctly
(logs and declines); `sprite.py` is a plain data component; `particles.py` uses
a fixed pool with documented degree units. `animation.py` carries
`_allow_methods = True` in two places -- playback and FSM logic on components
-- which belongs to CC-6 rather than this slice.

**Deferred:** CC-3 through CC-8, CC-11 (issue #9, now partly addressed).


### `pyguara/graphics` iteration 3 — backends — awaiting approval (2026-09-06)

**Verification:** 1464/1464 tests pass; ruff clean; mypy clean.

**Correctness fixes:**
- **The pygame compatibility stubs had drifted from the classes they stand in
  for.** `graphics/backends/pygame/stubs.py` exists so game code using
  framebuffers, lighting or post-processing runs unchanged on pygame; its
  entire value is interface parity. Comparing each stub's public surface
  against its real counterpart found two holes:
  `PygameLightingSystem` was missing `collect_lights_screen_space` (called by
  `pipeline/passes/light_pass.py`) and `PygameRenderGraph` was missing `ctx`
  (read by `application.py`). Either is an `AttributeError` that appears only
  after switching backend -- precisely the failure the stubs exist to prevent.
  The file had **no test references at all**.

**Tests:** new `tests/test_pygame_stubs.py`, 15 tests. Two are parametrised
parity checks comparing every stub against its counterpart, by member name and
by argument list, so the next divergence fails in CI rather than in a game.
Verified they bite: removing `collect_lights_screen_space` again reproduces the
failure with a message naming it. The rest cover the no-op behaviour itself --
that the lighting stub reports *full* ambient rather than darkness, that the
post-process stack passes frames through untouched, and that the lifecycle
calls are harmless.

**Surveyed and clean:** all six shipped implementations satisfy their protocols
structurally (`IWindowBackend`, `IRenderer`, `UIRenderer`, `TextureFactory`),
with no missing members and no signature drift; `conversions.py` is two
one-line adapters. One inconsistency noted but not changed: `IFramebuffer` and
`IRenderPass` are the only graphics protocols not marked `@runtime_checkable`,
while the other four are. Nothing currently needs to `isinstance` them, so
changing it now would be speculative -- it belongs with slice 4, which is where
those two protocols are actually implemented.

**Deferred:** CC-3 through CC-8, CC-11 (issue #9).


### `pyguara/graphics` iteration 4 — pipeline — awaiting approval (2026-09-06)

**Verification:** 1485/1485 tests pass; ruff clean; mypy clean.

**Correctness fixes:**
- **`Viewport.create_best_fit()` fabricated a viewport for a zero-area
  window.** The guard `window_ratio = w / h if h != 0 else 0` substituted a
  ratio of zero, which is not greater than any positive target, so it fell
  through to the letterbox branch:
  `create_best_fit(800, 0, 16/9)` returned `Viewport(x=0, y=-225, width=800,
  height=450)` -- a 450-pixel-tall viewport at a negative offset for a window
  with no height. A minimised or mid-resize window is an ordinary transient
  state, so it now yields a zero viewport. Negative dimensions do the same.
  This is the third instance of the same shape in this audit, after the camera's
  `safe_zoom = 0.001` and the DI container's swallowed errors: a zero guard
  that returns a wrong answer instead of signalling.
- **`create_best_fit()` divided by `target_aspect_ratio` with no check**, so
  zero raised `ZeroDivisionError` from inside the letterbox branch and a
  negative silently produced an inverted viewport. Unlike a minimised window
  that is a caller error, so it raises `ValueError` naming the argument.
- **`RenderGraph.passes` returned the live list.** `graph.passes.clear()`
  emptied the pipeline without releasing a single pass. It is a snapshot now,
  matching `SceneManager.children`.
- **Duplicate pass names were silent.** Both passes execute -- the list is the
  source of truth -- but `get_pass()` returns only the first and
  `remove_pass()` removes only the first, so the second is unreachable by name.
  Now logged, the same treatment `SystemManager` duplicate keys got.

**Tests:** new `tests/test_graphics_pipeline.py`, 21 tests. Neither the
viewport nor the graph had dedicated coverage. The viewport is pure arithmetic
needing no GL context, so its edge cases are cheap to pin down; the graph's
bookkeeping runs against a mocked context. Includes property-style checks that
a fitted viewport keeps its target ratio and never exceeds the window, across
four window shapes.

**Surveyed:** `framebuffer.py`, `batch.py`, `queue.py`, `render_system.py` and
the five passes need a live GL context to exercise meaningfully, so they are
covered only by the existing ModernGL integration tests. No defects found by
reading, but that is a weaker guarantee than the rest of this audit and worth
saying plainly.

**Related:** issue #16 records the `IFramebuffer`/`IRenderPass`
`runtime_checkable` inconsistency found in slice 3. Not fixed here: it turns on
whether `IRenderPass` or `BaseRenderPass(ABC)` is the real contract, which is a
design decision rather than a defect.

**Deferred:** CC-3 through CC-8, CC-11 (issue #9), issue #16.


### `pyguara/graphics` iteration 5 — assets & effects — awaiting approval (2026-09-06)

**Verification:** 1503/1503 tests pass; ruff clean; mypy clean.
**This completes the graphics subsystem.**

**Correctness fixes:**
- **`NinePatchSprite.get_patch_rects()` produced negative source rectangles.**
  Edges wider than the texture leave the centre with negative extent, and five
  of the nine source rects came back malformed --
  `Rect(x=40, y=0, width=-32, height=40)` for `uniform(40)` on a 48px texture --
  which reach the renderer as geometry rather than as an error. The asymmetry
  is the tell: `get_dest_rects()` clamps its own input with
  `max(width, min_size)`, three lines the source side never had. Now raises,
  naming both the edges and the texture size.
- **`NinePatchMetrics` accepted negative edges.** `uniform(-5)` was fine, and
  every rect derived from it was malformed. Rejected at construction.
- **`PostProcessStack.effects` returned the live list**, so
  `stack.effects.clear()` emptied the stack without releasing a single effect.
- **Duplicate effect names were silent**, leaving the second unreachable
  through `get_effect()` and surviving `remove_effect()`.

The last two are the *same pair* fixed in `RenderGraph` one slice earlier.
`PostProcessStack` and `RenderGraph` are siblings -- an ordered list plus a
name lookup -- and carried identical defects. Fixed identically, and the
docstrings now cross-reference so the parallel is visible.

**Tests:** +18. `test_ninepatch.py` gains metrics validation, the source/
destination asymmetry, and a check that valid source rects tile the texture
exactly. New `test_post_process_stack.py` covers the stack's bookkeeping.

**Surveyed, not deeply verified:** `materials/`, `vfx/effects/` (bloom,
vignette) and the shader loading in `post_process.py` need a live GL context,
so they remain covered only by the ModernGL integration tests -- the same
caveat as slice 4. `spritesheet.py`, `atlas.py` and `animation_system.py` were
read and probed and behaved correctly on degenerate input.

### `pyguara/graphics` — SUMMARY of all five slices

| Slice | Headline defect |
| --- | --- |
| 1. Boundary | `Window` reported the requested size, not the granted one |
| 2. Components | `Box`/`Circle` hard-wired to pygame; camera zoom accepted 0 |
| 3. Backends | pygame compatibility stubs had drifted from their counterparts |
| 4. Pipeline | a zero-height window produced a 450px viewport at negative y |
| 5. Assets | nine-patch produced negative source rects |

**A pattern worth recording.** Four of the five slices turned up the same
shape: a guard that avoids a crash by returning a wrong answer.
`safe_zoom = 0.001`, `window_ratio ... else 0`, the nine-patch's missing
clamp, and the DI container's swallowed disposal errors from an earlier tier.
In every case the crash would have been easier to diagnose than the
plausible-looking garbage substituted for it.

**Deferred:** CC-3 through CC-8, CC-11 (issue #9), issue #16.
