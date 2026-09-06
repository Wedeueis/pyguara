# PyGuara Refactor State

Shared memory for the incremental subsystem audit. One subsystem per iteration:
audit (Phase A) -> tests (Phase B) -> docs (Phase C) -> approval -> next.

**Started:** 2026-09-06
**Method:** Never analyse more than one subsystem at a time. Every finding that
touches a *different* subsystem gets parked under "Cross-Cutting Concerns"
rather than fixed in place.

---

## Active Subsystem

`pyguara/common` — **in review (awaiting approval)**

---

## Pending Subsystems

Ordered roughly by dependency depth: foundations first, leaves last.

### Tier 1 — Foundations (no intra-engine dependencies)
- [x] `pyguara/common` — Vector2, Color, Rect, shared components *(active)*
- [ ] `pyguara/log` — logging facade
- [ ] `pyguara/events` — EventDispatcher, Event protocol
- [ ] `pyguara/di` — DIContainer, auto-wiring, lifetimes

### Tier 2 — Core runtime
- [x] `pyguara/ecs` — Entity, Component, EntityManager, QueryCache *(done)*
- [ ] `pyguara/config` — configuration loading/merging
- [ ] `pyguara/application` — Application loop, bootstrap, sandbox
- [ ] `pyguara/scene` — Scene base, SceneManager, serializer
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
| `pyguara/ecs` | 2026-09-06 | Fixed two silent query bugs (`add_entity()` bypassing the query cache; dead-entity resurrection), replaced the private removal hook with a subscribe/unsubscribe API, and modernised the module. PR #1. |

---

## Cross-Cutting Concerns

Architectural issues that span subsystems. Do **not** fix these inside a
single-subsystem iteration; schedule a dedicated pass.

### CC-1 — Ruff `target-version` is `py39`, project requires `>=3.12`
`pyproject.toml` pins `target-version = "py39"` while `requires-python` is
3.12+. Ruff therefore refuses modernisation fixes engine-wide, which is the
root cause of the legacy `typing.Dict`/`Optional[X]` style found in every
module audited so far. **Fix:** bump to `py312` and enable the `UP`
(pyupgrade), `B` (bugbear) and `D` (pydocstyle, `convention = "google"`) rule
sets in one deliberate formatting commit, so per-subsystem diffs stay
reviewable.
*Discovered in:* `ecs`. *Status:* parked.

### CC-2 — Lint rule set is minimal (`E4, E7, E9, F`)
No pydocstyle, no bugbear, no pyupgrade, no complexity ceiling. Google-style
docstrings (mandated by this refactor) are therefore unenforced and will drift
straight back. **Fix:** land with CC-1.
*Discovered in:* `ecs`. *Status:* parked.

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


### `pyguara/common` — awaiting approval (2026-09-06)

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
