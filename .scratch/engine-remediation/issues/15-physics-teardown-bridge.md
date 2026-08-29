# Physics teardown bridge

Type: grilling
Status: open
Blocked by: 06
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
