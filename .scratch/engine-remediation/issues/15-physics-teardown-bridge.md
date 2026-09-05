# Physics teardown bridge

Type: grilling
Status: resolved
Blocked by: 06
Assignee: Wedeueis Braz
Audit ref: fog graduation (from ECS lifecycle contract resolution)

## Question

Two things, previously fog because they depended on the ECS lifecycle contract, now sharp:

1. `IPhysicsEngine.destroy_body()` (`pymunk_impl.py:292`) is a no-op stub — `pass`. A body
   removed from the ECS keeps simulating in `self.space` forever, and `self._bodies` (keyed by
   entity id) is never pruned.
2. Nothing connects entity removal to physics teardown at all. [ECS lifecycle
   contract](06-ecs-lifecycle-contract.md) resolved this: entity destruction now fires
   `EntityDestroyed(entity, timestamp, source)` synchronously, with the entity's components
   (including `RigidBody`) still intact to read at dispatch time.

`RigidBody` (`physics/components.py:36`) carries `_body_handle: Optional[IPhysicsBody]`, the
adapter returned by `create_body()`. Only one physics backend exists (pymunk) — this isn't a
cross-backend concern.

## To resolve

- Where does the `EntityDestroyed` subscription live — a small dedicated system, wired at
  physics bootstrap alongside `create_body()`'s caller, or somewhere else? Whatever registers
  a `RigidBody`'s handle on creation is probably the natural place to unregister it too.
- What does `destroy_body()` actually need to do in `PymunkBodyAdapter`/`self.space`? At
  minimum: remove the body and its attached shapes from `self.space`, and drop the entry from
  `self._bodies`. `add_shape()` doesn't currently track which shapes belong to a body outside
  of pymunk's own `body.shapes` — does teardown read that, or does the adapter need to track
  its own shape list?
- Ordering: `IPhysicsEngine.update()` steps `self.space` once per fixed tick. Is destroying a
  body safe to do synchronously mid-tick (i.e. inside the `EntityDestroyed` dispatch, which
  itself fires synchronously inside `remove_entity()`), or does it need to be deferred to
  before/after the next `update()` call to avoid mutating pymunk's space while it's mid-step?
- Does every entity with a `RigidBody` component necessarily have `_body_handle` set by the
  time `EntityDestroyed` fires, or can the component exist before the physics system has
  initialized it (e.g. an entity created and destroyed in the same frame, before physics
  processes new bodies)? The bridge needs a defined answer for `_body_handle is None`.

## Answer

Grilled live with the dev, one sub-question at a time. **Gap found first:** `EntityDestroyed`
doesn't exist anywhere in the codebase — [ECS lifecycle contract](06-ecs-lifecycle-contract.md)
(soft-dead removal, the event, the `QueryCache` fix) was decided but never executed, apart
from its narrow `Entity.clone()`/copy-rejection carve-out. `EntityManager.remove_entity()`
today is still the original version with no event dispatch. The decisions below don't require
that code to exist yet — only what happens once it does. Decisions:

1. **Subscription location: `PhysicsSystem` subscribes in `__init__`.** Using the
   `event_dispatcher` it already receives (currently unused): `self._dispatcher.subscribe(
   EntityDestroyed, self._on_entity_destroyed)`. Whatever registers a `RigidBody`'s handle on
   creation (`_create_physics_entity`, inside `PhysicsSystem`) is the natural place to
   unregister it — no new system, no new DI wiring.
2. **Teardown implementation: use `body.shapes` directly, no new tracking.**
   `destroy_body(body_handle)` does: `for shape in list(body_handle._body.shapes):
   self.space.remove(shape)`, then `self.space.remove(body_handle._body)`, then
   `del self._bodies[body_handle._body.entity_id]` (guarded in case it's already gone).
   Pymunk's own `body.shapes` is authoritative; no adapter-level shape list needed.
3. **Timing: deferred to a pending-teardown queue, drained in `update()`.** The
   `EntityDestroyed` handler appends the body handle to `self._pending_teardown` rather than
   destroying immediately. `PhysicsSystem.update()` drains and destroys them before calling
   `self._engine.update(dt)` (i.e. before `space.step()`). Safe under every call site today
   (both existing `remove_entity()` callers are in scene `update()`, after physics has already
   stepped) and safe once a collision-triggered-death pattern exists — pymunk forbids mutating
   the space from inside a collision callback while `space.step()` is running.
4. **Unset `_body_handle`: silent no-op.** If `rb._body_handle is None` when `EntityDestroyed`
   fires (entity created and destroyed in the same frame, before `PhysicsSystem.update()` ever
   ran), the handler returns without touching `destroy_body()` or the pending queue. Nothing
   to tear down.

**Execution sequencing:** two sequenced tickets, not combined — unlike *RenderSystem wiring*'s
same-method coupling with ticket 04, the ECS lifecycle contract's execution touches
`EntityManager.remove_entity()` broadly (every removal call site engine-wide), while physics
teardown only needs to subscribe to the resulting event. [Execute the ECS lifecycle
contract](26-execute-ecs-lifecycle-contract.md) lands first; [Execute the physics teardown
bridge](27-execute-physics-teardown-bridge.md) is blocked by it.
