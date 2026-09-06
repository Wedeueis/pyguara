# PyGuara Refactor State

Shared memory for the incremental subsystem audit. One subsystem per iteration:
audit (Phase A) -> tests (Phase B) -> docs (Phase C) -> approval -> next.

**Started:** 2026-09-06
**Method:** Never analyse more than one subsystem at a time. Every finding that
touches a *different* subsystem gets parked under "Cross-Cutting Concerns"
rather than fixed in place.

---

## Active Subsystem

`pyguara/scene` — **in review (awaiting approval)**

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
- [x] `pyguara/scene` — Scene base, SceneManager, serializer *(active)*
- [ ] `pyguara/systems` — system manager / base systems

### Tier 3 — Subsystems
- [ ] `pyguara/graphics` — protocols, backends, window, batching
- [ ] `pyguara/physics` — protocols, pymunk backend, joints, materials
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
| `pyguara/application` | 2026-09-06 | Fixed an event budget spent per fixed step (15x per lagged frame), a `shutdown()` that skipped everything after the first failure, and three lifecycle events with no publisher. PR #8. |
| `pyguara/config` | 2026-09-06 | Fixed `Color` not surviving a save/load round trip (a second-launch crash), `fixed_dt` dividing by zero unvalidated, and `update_setting` accepting wrong types and out-of-range values. PR #7. |
| `pyguara/log` | 2026-09-06 | Fixed source attribution (every record reported `logger.py:138`), a `shutdown()` that did not stop logging, handler clobbering on a process-global logger, and a docs page describing a nonexistent API. PR #5. |
| `pyguara/di` | 2026-09-06 | Fixed a missing lock in `DIScope.get()` that fabricated circular dependencies under concurrency (140/160 resolutions), plus captive lifetimes, dead-scope resolution, silent re-registration and varargs injection. PR #4. |
| `pyguara/events` | 2026-09-06 | Broke a latent `log` <-> `events` import cycle, fixed a timestamp sentinel that made 0.0 inexpressible, brought filter errors under the error strategy, and memoised handler resolution (5.7us -> 3.1us per dispatch). PR #3. |
| `pyguara/common` | 2026-09-06 | Fixed `Transform.up` pointing down, an unguarded parent cycle and a falsy-`Vector2` default; renamed `Vector2.rotate` to `rotate_degrees`; wrote the first tests for `Vector2` and `Transform`. PR #2. |
| `pyguara/ecs` | 2026-09-06 | Fixed two silent query bugs (`add_entity()` bypassing the query cache; dead-entity resurrection), replaced the private removal hook with a subscribe/unsubscribe API, and modernised the module. PR #1. |

---

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


### `pyguara/scene` — awaiting approval (2026-09-06)

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
