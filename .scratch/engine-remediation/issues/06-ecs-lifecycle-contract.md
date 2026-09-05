# ECS lifecycle contract

Type: grilling
Status: resolved
Blocked by: 04
Audit ref: ECS-2, ECS-3, ECS-4, ECS-5 (all high)

## Question

Four defects that are really one missing contract: what it means for an entity to stop
existing, and what a query guarantees while you iterate it.

**ECS-2 — removed entities keep their manager callbacks.** `remove_entity()`
(`ecs/manager.py:55`) clears the index but never detaches `entity._on_component_added`. Any
retained reference that adds a component re-inserts the dead id, and queries then dereference
an id that is no longer in `_entities`:

```
em.remove_entity(e.id); e.add_component(Tag("ghost"))
list(em.get_entities_with(Tag))
KeyError: 'd11e6142-ee63-4a13-9592-77a3de093155'
```

This matters because `protocolo_bandeira/pooling.py` ships a 500-entity bullet pool built on
exactly the retain-and-reuse pattern.

**ECS-3 — QueryCache is never told about removal.** It has no removal hook at all.
`get_entities_with_cached()` papers over correctness with an `if eid in self._entities` guard,
so the symptom is pure unbounded growth: create 5, remove 5, cache still reports 5. Two
related problems in the same class — `get_cached()` returns `.copy()` on every call
(allocating a set per query per frame, eroding the advertised 8x), and a registered-but-empty
query is indistinguishable from an unregistered one, so it silently falls back to a full scan
every frame. `clear_cache()` also rebuilds rather than clears.

**ECS-4 — single-type queries iterate the live index set.** `result_ids = sets[0]` is the
index itself; with two or more types the `&` produces a copy. So mutation during iteration is
safe for `get_entities_with(A, B)` and raises for `get_entities_with(A)`.

**ECS-5 — `Entity.__getattr__` recurses infinitely under copy and pickle.** It reads
`self._property_cache`, which does not exist during reconstruction, so the lookup re-enters
`__getattr__`. `copy.deepcopy(Entity())` raises `RecursionError` — which blocks prefab
cloning, save snapshots, and the replay system by construction.

## To resolve

- What does `remove_entity` guarantee? Immediate removal, or deferred to a frame boundary?
  Deferred removal is the usual answer for systems that iterate while mutating, and it would
  resolve ECS-4 as a side effect.
- Does an entity become inert on removal (callbacks detached, further mutation a no-op or an
  error), or is reuse legitimate — as the bullet pool assumes?
- Is there an `EntityDestroyed` event? The physics teardown bridge in the fog needs a hook,
  and this is the natural place for it.
- Do queries snapshot by contract, or is mutation-during-iteration caller-beware? Whichever
  it is, it must be the same for one component type and for four.
- Does `QueryCache` earn its place at all? Fixing removal, the per-call copy, and the
  empty-vs-unregistered ambiguity is real work for a benefit no shipped system currently uses.

## Answer

Grilled live with the dev, one sub-question at a time. Decisions:

1. **`remove_entity`: soft-dead immediately, physical cleanup deferred.** `del
   self._entities[entity_id]` still runs at once — nothing can see or resurrect the entity
   from that instant on. The `_component_index[comp_type].discard(entity_id)` calls move out
   of `remove_entity()` into a deferred queue, flushed once at the frame boundary (end of
   `Application._fixed_update`). This is what makes iteration safe regardless of arity (see 4).

2. **Removal is terminal, not reusable.** `_on_component_added`/`_on_component_removed` detach
   immediately on removal. `add_component()`/`remove_component()` on a dead entity raise
   (loud signal of stale-reference misuse) rather than silently no-op or resurrect. Pooling
   stays the active-flag pattern `protocolo_bandeira/pooling.py` already uses — note that pool
   never actually calls `remove_entity()` today, it just toggles `Poolable.is_active`, so this
   decision doesn't touch it. Reuse via remove-then-re-add the same object is not a supported
   pattern.

3. **Add `EntityDestroyed(entity: Entity, timestamp: float, source: Any)`.** Fired
   synchronously via `dispatch()` at the moment of soft-death, inside `remove_entity()` —
   before the entity's components are torn down, so handlers (e.g. the physics teardown
   bridge) can still read them. `EntityManager` stays decoupled from the event system: it
   gains an optional removal-hook callback mirroring the existing `_on_component_added`/
   `_on_component_removed` shape, wired by `Scene.resolve_dependencies()` to
   `self.event_dispatcher.dispatch(EntityDestroyed(...))`.

4. **Queries: not a frozen snapshot, a live filtered view, safe by construction regardless of
   arity.** Every query path (`get_entities_with`, `get_components`, `get_components_with_entity`,
   and the cached path) guards its yield with `self._entities.get(eid) is not None`,
   generalizing the check `get_entities_with_cached` already does at manager.py:160. Combined
   with (1), this resolves ECS-4: the physical index set is never mutated mid-iteration
   (mutation is deferred to the frame boundary), so aliasing the live set for single-type
   queries stops being unsafe. Confirmed no meaningful perf cost: the `.get()` guard is the
   same dict lookup the code already performs, just non-raising; deferred index cleanup does
   the same total number of `discard()` calls, just batched; stale ids linger in the index for
   at most one frame, bounded by that frame's churn, not by world size.

5. **`QueryCache`: kept, fixed, not deleted.** Its usage today (`asset_pipeline`,
   `ecs_mental_model` demos) is only single-component and doesn't exercise the multi-component
   hot-path case it exists for, but the underlying idea — avoiding a per-call set intersection
   for a query polled every fixed tick — is a legitimate optimization for a Python engine, not
   a premature one. Three fixes, all cheap: (a) wire the same soft-dead-aware removal hook
   every other query path now needs, so this isn't a special tax for keeping the cache; (b)
   store `_cache` values as `frozenset` instead of `Set`, so `get_cached()` hands the frozenset
   out directly instead of `.copy()`-ing every call — a net simplification, not added cost; (c)
   fix the empty-vs-unregistered ambiguity with an explicit `query_key in
   self._registered_queries` check instead of `if cached_ids:` truthiness.

6. **ECS-5 (not in the original "To resolve" list, but part of the ticket's Question — caught
   and resolved before closing):** `Entity.__getattr__` recursed under `copy.deepcopy`/pickle
   because it read `self._property_cache` directly; on a blank instance built via
   `cls.__new__(cls)` during reconstruction (before `__init__` runs), that attribute doesn't
   exist yet, so the lookup re-enters `__getattr__` for the same name, infinitely. Considered
   full `deepcopy`/pickle support vs. a clean-failing guard plus a dedicated `clone()` method;
   chose the latter and **implemented it now** (deviating from this ticket's decision-only
   default, at the dev's explicit request — a small, mechanical fix, not an open architectural
   fork):
   - `__getattr__` now reads via `self.__dict__.get("_property_cache")`, which never
     re-triggers `__getattr__`, fixing the recursion regardless of call site.
   - `Entity.__deepcopy__`/`__copy__`/`__reduce__` all raise `TypeError` with a message
     pointing at `clone()` (for copy) or `SceneSerializer` (for pickle/save-load) — chosen over
     generic support because `Entity` carries state a blind deep-copy shouldn't duplicate:
     `_on_component_added`/`_on_component_removed` are bound callbacks into the *original*
     `EntityManager`, and e.g. `RigidBody._body_handle` wraps a live pymunk body — a naive
     `deepcopy` would alias both rather than detach them. `SceneSerializer` already does
     save/load via explicit field-by-field (de)serialization, not `copy`/`pickle`, so generic
     support wouldn't even serve that need — only prefab cloning, which `clone()` serves
     directly.
   - `Entity.clone(new_id=None)` deep-copies each component's data, resets any field whose
     name starts with `_` (system-injected handles) to its dataclass default, and returns an
     entity registered with no manager — the caller must `entity_manager.add_entity(clone)`.
   - Landed in `pyguara/ecs/entity.py` with regression tests in `tests/test_ecs.py`
     (`test_deepcopy_raises_instead_of_recursing`, `test_copy_raises_type_error`,
     `test_pickle_raises_type_error`, `test_clone_produces_independent_entity`,
     `test_clone_resets_system_injected_fields`, `test_clone_is_unregistered_until_added`).
     `ruff check` and `mypy pyguara` stay clean; full suite (1041 tests) passes.

Not implemented in this session (items 1-5): this ticket is a decision, not a `task`. Item 6
(ECS-5) is the one exception, implemented at the dev's explicit request. Graduates the
**Physics teardown bridge** fog item into [ticket 15](15-physics-teardown-bridge.md), now that
its hook (`EntityDestroyed`) exists.

**Gap found during [Physics teardown bridge](15-physics-teardown-bridge.md):** items 1-5 sat
unexecuted with no task ticket at all — `EntityDestroyed` doesn't exist anywhere in the
codebase, and physics teardown's own execution depends on it. See [Execute the ECS lifecycle
contract](26-execute-ecs-lifecycle-contract.md).
