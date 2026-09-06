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
Real components across `physics`, `ui` and `ai` may carry logic. **Fix:**
after those subsystems are audited, migrate the tree to `StrictComponent` and
consider making it the default.
*Discovered in:* `ecs`. *Status:* parked — measure adoption per subsystem.

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
