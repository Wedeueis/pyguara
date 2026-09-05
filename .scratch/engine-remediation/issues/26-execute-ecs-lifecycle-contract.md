# Execute the ECS lifecycle contract

Type: task
Status: open
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
