# Execute the ECS lifecycle contract

Type: task
Status: resolved
Assignee: Wedeueis Braz
Blocked by: —
Audit ref: ECS-2, ECS-3, ECS-4 (all high), follows from ECS lifecycle contract, ticket 06

## Question

Nothing to decide — execute items 1-5 recorded in [ECS lifecycle
contract](06-ecs-lifecycle-contract.md) (item 6, `Entity.clone()`/copy-rejection, already
landed). This is a foundational, engine-wide change to entity removal semantics — every
`remove_entity()` call site is affected.

**`pyguara/ecs/manager.py`:**
- `remove_entity(entity_id)`: `del self._entities[entity_id]` still runs immediately (soft-dead
  — nothing can see or resurrect the entity from that instant). Move the
  `self._component_index[comp_type].discard(entity_id)` calls out of `remove_entity()` into a
  deferred queue (`self._pending_index_cleanup: List[Tuple[Type[Component], str]]` or
  equivalent), flushed once at the frame boundary.
- Detach `entity._on_component_added`/`_on_component_removed` immediately on removal.
- `add_component()`/`remove_component()` on a dead entity raise (loud signal of stale-reference
  misuse) rather than silently no-op.
- Add `EntityDestroyed(entity: Entity, timestamp: float, source: Any)` — a new event type.
  Fired synchronously via `dispatch()` at the moment of soft-death, inside `remove_entity()`,
  before the entity's components are torn down (so handlers can still read them).
  `EntityManager` stays decoupled from the event system: it gains an optional removal-hook
  callback (mirroring `_on_component_added`/`_on_component_removed`'s shape), wired by
  `Scene.resolve_dependencies()` to `self.event_dispatcher.dispatch(EntityDestroyed(...))`.
- Every query path (`get_entities_with`, `get_components`, `get_components_with_entity`, the
  cached path) guards its yield with `self._entities.get(eid) is not None`, generalizing the
  check `get_entities_with_cached` already does. This is what makes iteration safe regardless
  of arity — single-type queries currently alias the live index set directly.
- A frame-boundary flush point for the deferred index cleanup — call it from
  `Application._fixed_update()`'s end, per the ticket's decision.

**`pyguara/ecs/query_cache.py`:**
- Wire the same soft-dead-aware removal hook into `QueryCache` (it currently has no removal
  hook at all).
- Store `_cache` values as `frozenset` instead of `Set`; `get_cached()` hands the frozenset out
  directly instead of `.copy()`-ing every call.
- Fix the empty-vs-unregistered ambiguity with an explicit `query_key in
  self._registered_queries` check instead of `if cached_ids:` truthiness.

## Done when

- `remove_entity()` immediately removes the entity from `_entities` and detaches its callbacks;
  physical index cleanup happens at the next frame boundary.
- `EntityDestroyed` is dispatched synchronously at soft-death, with components still readable
  by handlers.
- `add_component()`/`remove_component()` on a removed entity raise.
- Every query path is safe to iterate while `remove_entity()` is called mid-iteration,
  regardless of how many component types are queried (the regression test from ECS-4's report:
  `get_entities_with(A)` no longer raises when an entity is removed mid-iteration).
- `QueryCache` reports correct counts after removal, its cache values are frozensets, and
  `clear_cache()`/empty-vs-unregistered behave per the ticket's decision.
- Regression tests cover all of ECS-2/3/4 from the original ticket's reproductions.
- `ruff check .` and `mypy pyguara` stay clean; full suite green.

**Out of scope here:** the physics teardown bridge itself (subscribing to `EntityDestroyed`
and implementing `destroy_body()`) — that's [Execute the physics teardown
bridge](27-execute-physics-teardown-bridge.md), blocked by this ticket.

## Resolution

Executed as specified, with one necessary adaptation to a later decision this ticket
predates. Commit `44caa5b`.

**Landed as specified.** `remove_entity()` is soft-dead immediately (deleted from
`_entities`, callbacks detached, `entity._is_removed` set) with physical
`_component_index` cleanup deferred to a new `flush_pending_removals()`.
`add_component()`/`remove_component()` raise `RuntimeError` on a removed entity.
`EntityDestroyed(entity, timestamp, source)` (new `pyguara/ecs/events.py`) dispatches
synchronously inside `remove_entity()`, components still intact; `EntityManager` stays
decoupled via an `_on_entity_removed` hook, wired by `Scene.resolve_dependencies()`.
Every query path (`get_entities_with`, `get_components`, `get_components_with_entity`, the
cached path) guards its yield against soft-removed-but-not-yet-swept ids. `QueryCache`'s
three fixes all landed: frozenset cache values; `get_cached()` returning `None`
(unregistered) vs. an empty frozenset (registered, nothing matches); and the removal path
wired through the *existing* `on_component_removed()` (called once per removed entity's
component types from `flush_pending_removals()`) rather than a new API — it already did
exactly what was needed.

**Adapted, not re-decided:** "call the frame-boundary flush from `Application.
_fixed_update()`'s end" assumed a global `EntityManager`, which [Execute Scene-owned
world, SystemManager, and RenderSystem wiring](24-execute-scene-owned-systems-and-rendersystem.md)
(executed earlier this session, after this ticket's decision was written) removed — each
scene now owns its own `EntityManager`. `SceneManager.fixed_update()` calls
`scene.entity_manager.flush_pending_removals()` once per active scene instead, alongside
the `system_manager` tick already added there.

**Left alone, deliberately:** `QueryCache.clear_cache()` still rebuilds rather than clears,
despite its name and docstring. The original audit flagged this as a defect, but ticket 06's
actual Answer never decided to change it — only the three fixes above were decided — so
changing its behavior now would be re-deciding something this task ticket has no authority
to decide. Left as a known, pre-existing inconsistency rather than silently "fixed."

14 new regression tests added to `tests/test_ecs.py`, covering ECS-2/3/4's exact
reproductions plus `EntityDestroyed` (directly and through a real `EventDispatcher`). Full
suite green (1078 passed), `ruff check .` and `mypy pyguara` clean.
